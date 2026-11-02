"""Generate "Logic Deep Dive" pages for core modules using the local LLM.

Pipeline:
  1. AST-parse each configured module (compile-only, never executes it).
  2. Feed the LLM (localhost llama-server via the OpenAI-compatible API) a
     compact structure summary + source excerpt and ask for a technical
     walkthrough: purpose, control flow, data flow, key logic, gotchas.
  3. Cache results in `docs/.logic_cache.json` keyed by source mtime, so
     rebuilds are fast. If the LLM is unreachable, falls back to an
     auto-generated structural summary — the build never fails.

Registered in mkdocs.yml under `plugins.gen-files.scripts`.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import time
from pathlib import Path

import mkdocs_gen_files

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "docs" / ".logic_cache.json"


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in ("1", "true", "yes")


def _pick_loaded_model() -> str | None:
    """Prefer the qwen3.5 family from /v1/models, then any qwen, then the first.

    LM Studio lists every installed model, not just the loaded one, so taking
    the first entry can pick an unloadable model (e.g. nemotron) and 400.
    """
    try:
        import urllib.request

        with urllib.request.urlopen(LLM_BASE_URL + "/models", timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        ids = [(item.get("id") or "").strip() for item in data.get("data") or []]
        ids = [mid for mid in ids if mid]
        for mid in ids:
            if "qwen3.5" in mid.lower():
                return mid
        for mid in ids:
            if "qwen" in mid.lower() and "9b" in mid.lower():
                return mid
        for mid in ids:
            if "qwen" in mid.lower():
                return mid
        if ids:
            return ids[0]
        obj = data.get("model") or data.get("id") or data.get("models") or ""
        if isinstance(obj, str) and obj.strip():
            return obj.strip()
        if isinstance(obj, list) and obj:
            first = obj[0]
            if isinstance(first, dict):
                return (first.get("id") or first.get("model") or first.get("name") or "").strip() or None
            return str(first).strip() or None
    except Exception:
        return None
    return None


def _model_id() -> str:
    global _loaded_model
    if _loaded_model is None:
        env = os.environ.get("SPOCK_LLM_MODEL", "").strip()
        _loaded_model = env or _pick_loaded_model() or LLM_MODEL
    return _loaded_model

LLM_BASE_URL = os.environ.get("SPOCK_LLM_BASE_URL", "http://localhost:8081/v1")
LLM_API_KEY = "llamaccp"  # llama-server / LM Studio accept any non-empty key
LLM_MODEL = "qwen3.5-9b"  # fallback; overwritten by auto-detection of the loaded model
# 9B models and first-time model loading in LM Studio can take minutes.
LLM_TIMEOUT = int(os.environ.get("SPOCK_LLM_TIMEOUT", "300"))  # seconds per chunk request
LLM_RETRIES = int(os.environ.get("SPOCK_LLM_RETRIES", "2"))

# Cap the whole LLM pass: if the cumulative wall time exceeds this, remaining
# modules fall back to the structural summary so a build can never hang.
LLM_TIME_BUDGET = 600  # seconds

# Send at most this many source chunks per module (structure summary always goes).
MAX_SOURCE_CHUNKS = 2

MAX_CHUNK_CHARS = 5000  # source excerpt per LLM call
MAX_MODULE_CHARS = 12000  # total source sent per module

_skip_llm = _env_flag("SPOCK_GEN_LOGIC_SKIP_LLM")
_llm_start: float | None = None
_loaded_model: str | None = None

# Modules worth a human-readable logic walkthrough.
LOGIC_MODULES = [
    "Spock-UIE-Wiki-KB.py",
    "main.py",
    "WarpCore/db.py",
    "deep_dive.py",
    "llm_client.py",
    "rag_api_server.py",
    "WarpCore/search.py",
    "LongRangeSensors/uieg_crawler.py",
    "spock_shell/window.py",
]

SYSTEM_PROMPT = """You are a senior software engineer writing technical documentation for a Python/SQLite application called Spock-Onboarding.

Given a module's AST structure summary and source excerpt, write a "Logic Deep Dive" in Markdown with these sections:
- ## Purpose — what the module does and why it exists
- ## Structure — how classes/functions are organized
- ## Control flow — how execution proceeds, entry points, state changes
- ## Data flow — what data moves in/out, database or IPC interactions
- ## Key logic — notable algorithms, edge cases, and why they matter
- ## Gotchas / maintenance notes — risks, coupling, things to be careful with

Rules:
- Be specific: name real functions/classes and cite file:line where valuable.
- Stay strictly within the global context budget; do not invent APIs.
- Return ONLY the Markdown walkthrough, no preamble or code fences around it."""


def _read(rel: str) -> str | None:
    try:
        return (ROOT / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        try:
            return (ROOT / rel).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            return None


def _structure_summary(rel: str, src: str) -> str:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return f"module: {rel}\n  (syntax error — cannot parse)"
    lines: list[str] = [f"module: {rel}"]
    doc = ast.get_docstring(tree)
    if doc:
        lines.append("  module docstring: " + doc.strip().splitlines()[0][:160])
    imports: list[str] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imports.extend(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            imports.append(n.module)
    if imports:
        lines.append("  imports: " + ", ".join(sorted(set(imports))[:40]) + (" …" if len(set(imports)) > 40 else ""))
    for n in tree.body:
        if isinstance(n, ast.ClassDef):
            methods = [m.name for m in n.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
            lines.append(
                f"  class {n.name}({', '.join(ast.unparse(b) for b in n.bases) or ''}) "
                f"[L{n.lineno}-{n.end_lineno}]: methods={methods}"
            )
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if n.name in {"main", "run", "app", "launch"} or not n.name.startswith("_"):
                lines.append(
                    f"  def {n.name}({', '.join(a.arg for a in n.args.args)}) [L{n.lineno}-{n.end_lineno}]"
                )
    return "\n".join(lines[:120])


def _chunk_source(src: str) -> list[str]:
    """Split source into chunks of <= MAX_CHUNK_CHARS at line boundaries."""
    if len(src) <= MAX_CHUNK_CHARS:
        return [src]
    chunks: list[str] = []
    lines = src.splitlines(keepends=True)
    cur: list[str] = []
    size = 0
    for line in lines:
        if size + len(line) > MAX_CHUNK_CHARS and cur:
            chunks.append("".join(cur))
            cur, size = [], 0
        cur.append(line)
        size += len(line)
    if cur:
        chunks.append("".join(cur))
    return chunks


def _llm_ask(prompt: str) -> str | None:
    if _skip_llm or _budget_exhausted():
        return None
    try:
        import openai
    except Exception:
        return None
    try:
        client = openai.OpenAI(
            base_url=LLM_BASE_URL, api_key=LLM_API_KEY, timeout=LLM_TIMEOUT
        )
        last: Exception | None = None
        for attempt in range(LLM_RETRIES + 1):
            try:
                resp = client.chat.completions.create(
                    model=_model_id(),
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt + "\n/no_think"},
                    ],
                    temperature=0.3,
                )
                return resp.choices[0].message.content or None
            except Exception as e:  # timeouts / connection drops (model (re)loading)
                last = e
                if attempt < LLM_RETRIES:
                    time.sleep(3 * (attempt + 1))
        print(f"[gen_logic] LLM call failed after retries: {last}")
        return None
    except Exception:
        return None


def _budget_exhausted() -> bool:
    global _llm_start
    if _llm_start is None:
        return False
    return (time.time() - _llm_start) > LLM_TIME_BUDGET


def _synthetic_walkthrough(rel: str, summary: str, src: str) -> str:
    return (
        f"# Logic Deep Dive: {rel}\n\n"
        "> **Note:** The local LLM (LM Studio / llama-server on port 8081) was not "
        "reachable or the time budget expired, so this page shows the "
        "machine-extracted structure instead of a written walkthrough. Rebuild "
        "with the model loaded to generate prose.\n\n"
        "## AST structure\n\n```text\n" + summary + "\n```\n"
    )


def _load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_cache(data: dict) -> None:
    try:
        CACHE.write_text(json.dumps(data, indent=1), encoding="utf-8")
    except OSError:
        pass


def generate_module(rel: str) -> tuple[str, str]:
    """Returns (markdown, title)."""
    global _llm_start
    if _llm_start is None:
        _llm_start = time.time()
    src = _read(rel)
    if src is None:
        return (
            f"# Logic Deep Dive: {rel}\n\nSource not found.",
            rel,
        )
    digest = hashlib.sha256(src.encode("utf-8")).hexdigest()[:16]
    cache = _load_cache()
    slot = cache.get(rel)
    # Reuse cached prose only if it was produced by the LLM ('ok'); a cached
    # synthetic fallback is regenerated once the LLM becomes available.
    if slot and slot.get("digest") == digest and slot.get("md") and slot.get("ok"):
        return slot["md"], rel

    summary = _structure_summary(rel, src)
    chunks = _chunk_source(src[:MAX_MODULE_CHARS])[:MAX_SOURCE_CHUNKS]
    parts: list[str] = []
    for i, chunk in enumerate(chunks):
        done_mark = "\n\n---\n\n## Appendix: source excerpt\n" if i == 0 else f"\n\n## Source excerpt (part {i + 1})\n"
        prompt = (
            f"Module structure:\n{summary}\n\n"
            f"(Excerpt {i + 1} of {len(chunks)} of the module source.)\n```python\n{chunk}\n```\n\n"
            f"Write section {i + 1} of the Logic Deep Dive now.{done_mark}" + (" (FIRST part: include ## Purpose and ## Structure)" if i == 0 else "")
        )
        answer = _llm_ask(prompt)
        if answer:
            parts.append(answer.strip())
    if parts:
        md = "\n\n".join(parts)
    else:
        md = _synthetic_walkthrough(rel, summary, src)
    cache[rel] = {"digest": digest, "md": md, "ts": time.time(), "ok": bool(parts)}
    _save_cache(cache)
    return md, rel


def build_index(entries: list[str]) -> str:
    out = [
        "# Logic Deep Dives",
        "",
        "Written walkthroughs of the core modules: purpose, control flow, data "
        "flow, key logic, and maintenance gotchas. Generated by feeding the AST "
        "structure + source of each module to the local llama-server; cached so "
        "rebuilds are fast. If the LLM was unavailable the page shows the raw "
        "structure instead.",
        "",
        "| Module | Status |",
        "|--------|--------|",
    ]
    for rel in entries:
        md = _read(rel) is not None
        out.append(f"| [`{rel}`]({rel.replace('.py', '').replace('/', '_')}.md) | {'source found' if md else 'missing'} |")
    out.append("")
    return "\n".join(out)


def main() -> None:
    for rel in LOGIC_MODULES:
        md, _title = generate_module(rel)
        name = rel.replace("/", "_").replace(".py", "")
        with mkdocs_gen_files.open(f"structure/logic/{name}.md", "w") as fd:
            fd.write(md)
    with mkdocs_gen_files.open("structure/logic/index.md", "w") as fd:
        fd.write(build_index(LOGIC_MODULES))


if __name__ in ("__main__", "<run_path>"):  # direct run, or mkdocs-gen-files runpy
    main()