"""Ask AI Deep Dive — budgeted multi-file codebase context from ship_computer.db.

Single-pass: inventory under Documents filter + expanded hybrid retrieval,
forced path pulls from the question, then fill remaining char budget.
No disk I/O — uses documents.content_plain.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import urllib.error
import urllib.request
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

# Deep Dive knobs
DEFAULT_TOP_K = 24
FILL_TOP_K = 48  # hybrid pool when filling budget / follow-ups
DEFAULT_EXCERPT_CHARS = 6000
FORCED_EXCERPT_CHARS = 24_000  # prefer near-full small/medium modules
DEFAULT_CONTEXT_BUDGET = 96_000
DEFAULT_INVENTORY_LIMIT = 80
# Inventory is a path list, not evidence. Keep it from eating the pack.
INVENTORY_TOKEN_CAP = 1200
LARGE_CORPUS_WARN = 200
FORCED_SCORE = 1000.0
# Conservative chars/token for code-heavy prompts (llama exceed-context errors).
# Dense source often tokenizes closer to ~2.0–2.3 chars/token than 3.0.
CHARS_PER_TOKEN = 2.2
_CLOUD_PROVIDERS = (
    "openai-compatible",
    "openai",
    "gemini",
    "google",
    "vertex",
    "vertex-ai",
    "anthropic",
    "claude",
)

# Common source extensions for Ship's Logs / Ask AI multi-language presets.
CODE_EXTENSIONS = (
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".rs",
    ".go",
    ".java",
    ".kt",
    ".cs",
    ".cpp",
    ".cc",
    ".c",
    ".h",
    ".hpp",
    ".vue",
    ".svelte",
    ".rb",
    ".php",
    ".swift",
    ".sql",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
)
DOC_EXTENSIONS = (".md", ".txt", ".rst", ".adoc", ".html")


def use_llama_tokenize(provider: str) -> bool:
    """True for local llama-server Ask AI; False for Gemini / OpenAI-compatible."""
    p = (provider or "llama-server").strip().lower()
    if p in _CLOUD_PROVIDERS:
        return False
    return p in ("", "llama-server", "llama", "llama.cpp", "llamacpp") or p.startswith(
        "llama"
    )


def _server_root_from_chat_url(url: str) -> str:
    """``http://host:port/v1/chat/completions`` → ``http://host:port``."""
    u = (url or "").strip().rstrip("/")
    if not u:
        return ""
    for suffix in ("/v1/chat/completions", "/chat/completions", "/v1"):
        if u.lower().endswith(suffix):
            return u[: -len(suffix)]
    return u


def _is_loopback_chat_url(url: str) -> bool:
    u = (url or "").lower()
    return any(
        h in u
        for h in (
            "://localhost",
            "://127.0.0.1",
            "://[::1]",
            "://0.0.0.0",
        )
    )


def llama_token_count(
    text: str, server_url: str, timeout: float = 2.0
) -> Optional[int]:
    """Count tokens via llama-server POST /tokenize. None if the server is down."""
    url = (server_url or "").rstrip("/") + "/tokenize"
    if not (server_url or "").strip():
        return None
    try:
        payload = json.dumps({"content": text or ""}).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tokens = data.get("tokens") if isinstance(data, dict) else data
        if isinstance(tokens, list):
            return len(tokens)
        if isinstance(data, dict) and "tokens" in data:
            return len(data["tokens"])
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        return None
    return None


def probe_llama_n_ctx(server_url: str, timeout: float = 1.5) -> Optional[int]:
    """Runtime slot n_ctx from llama-server /props (never n_ctx_train)."""
    try:
        req = urllib.request.Request((server_url or "").rstrip("/") + "/props")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    settings = data.get("default_generation_settings") or {}
    for blob in (settings if isinstance(settings, dict) else {}, data):
        try:
            n = int(blob.get("n_ctx") or 0)
            if n > 0:
                return n
        except (TypeError, ValueError):
            pass
    return None


def _configured_chat_n_ctx(cfg: Dict[str, Any]) -> int:
    """Chat window from config when llama-server ``/props`` is unreachable."""
    try:
        from WarpCore.service_endpoints import DEFAULT_CTX

        default = int(DEFAULT_CTX["chat_n_ctx"])
    except Exception:
        default = 32768
    try:
        return max(512, int(cfg.get("chat_n_ctx") or default))
    except (TypeError, ValueError):
        return default


def packing_opts_from_config(cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """n_ctx / chat_url / provider for Deep Dive.

    Always prefer the **live** completion slot when the chat endpoint is a
    loopback llama-server (even if ``ask_ai_provider`` says OpenAI-compatible).
    That prevents packing a 131k cloud budget into a 32k local GGUF.
    """
    cfg = cfg or {}
    try:
        from WarpCore.config_defaults import merge_ctx_settings
    except Exception:  # pragma: no cover
        merge_ctx_settings = None  # type: ignore
    ctx_raw = cfg.get("ctx") if isinstance(cfg.get("ctx"), dict) else {}
    ctx = merge_ctx_settings(ctx_raw) if callable(merge_ctx_settings) else dict(ctx_raw or {})

    provider = str(cfg.get("ask_ai_provider") or "llama-server")
    host = str(cfg.get("llama_host") or "localhost")
    try:
        port = int(cfg.get("llama_port") or 8081)
    except (TypeError, ValueError):
        port = 8081
    llama_root = f"http://{host}:{port}"

    oai_base = str(
        cfg.get("openai_compat_base_url")
        or cfg.get("openai_base_url")
        or cfg.get("openai_compat_url")
        or ""
    ).strip()
    oai_root = _server_root_from_chat_url(oai_base) if oai_base else ""

    # Probe whichever endpoint will actually answer chat completions.
    probe_roots: List[str] = []
    if use_llama_tokenize(provider):
        probe_roots.append(llama_root)
    elif oai_root and _is_loopback_chat_url(oai_root):
        probe_roots.append(oai_root)
        probe_roots.append(llama_root)
    else:
        # Cloud label — still probe local llama in case the client falls back.
        probe_roots.append(llama_root)
        if oai_root:
            probe_roots.append(oai_root)

    live_n_ctx: Optional[int] = None
    chat_url = ""
    for root in probe_roots:
        live = probe_llama_n_ctx(root)
        if live:
            live_n_ctx = int(live)
            chat_url = root
            break

    try:
        cloud_n_ctx = int(cfg.get("openai_compat_n_ctx") or 131072)
    except (TypeError, ValueError):
        cloud_n_ctx = 131072
    try:
        cloud_max_out = int(cfg.get("openai_compat_max_tokens") or 8192)
    except (TypeError, ValueError):
        cloud_max_out = 8192

    try:
        user_max_out = int(ctx.get("max_out_tokens") or 2048)
    except (TypeError, ValueError):
        user_max_out = 2048
    user_max_out = max(256, user_max_out)

    if live_n_ctx:
        # Live local slot wins — pack and tokenize against it.
        live_cap = max(256, int(live_n_ctx) // 8)
        return {
            "n_ctx": int(live_n_ctx),
            "max_out_tokens": min(user_max_out, live_cap),
            "ask_ai_provider": "llama-server",
            "chat_url": chat_url or llama_root,
            "ctx": ctx,
        }

    if use_llama_tokenize(provider):
        return {
            "n_ctx": _configured_chat_n_ctx(cfg),
            "max_out_tokens": min(user_max_out, 2048),
            "ask_ai_provider": provider,
            "chat_url": llama_root,
            "ctx": ctx,
        }

    return {
        "n_ctx": cloud_n_ctx,
        "max_out_tokens": min(user_max_out, cloud_max_out),
        "ask_ai_provider": provider,
        "chat_url": "",
        "ctx": ctx,
    }


def packing_opts_for_llm(
    cfg: Optional[Dict[str, Any]],
    llm: Any = None,
) -> Dict[str, Any]:
    """Like ``packing_opts_from_config``, refined with the active LLM client URL."""
    opts = packing_opts_from_config(cfg)
    ctx = opts.get("ctx") if isinstance(opts.get("ctx"), dict) else {}
    try:
        user_max_out = int(ctx.get("max_out_tokens") or opts.get("max_out_tokens") or 2048)
    except (TypeError, ValueError):
        user_max_out = int(opts.get("max_out_tokens") or 2048)
    if llm is None:
        return opts
    active_url = str(getattr(llm, "active_url", None) or "").strip()
    root = _server_root_from_chat_url(active_url)
    if not root:
        return opts
    live = probe_llama_n_ctx(root)
    if not live:
        return opts
    live_cap = max(256, int(live) // 8)
    return {
        "n_ctx": int(live),
        "max_out_tokens": max(256, min(user_max_out, live_cap)),
        "ask_ai_provider": "llama-server",
        "chat_url": root,
        "ctx": ctx,
    }


_CONTEXT_WRAP_RE = re.compile(
    r"^Context:\n.*?\n\nQuestion:\s*",
    re.DOTALL,
)
DEEP_DIVE_HISTORY_TURNS = 4  # last 2 user+assistant pairs
DEEP_DIVE_HISTORY_ASSISTANT_CHARS = 6000


def sanitize_deep_dive_history(
    history: Optional[List[Dict[str, str]]],
) -> List[Dict[str, str]]:
    """Keep follow-up Q&A; strip prior packed Context dumps that would double n_ctx."""
    out: List[Dict[str, str]] = []
    for turn in history or []:
        role = (turn.get("role") or "").strip()
        content = (turn.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        if role == "user":
            m = _CONTEXT_WRAP_RE.match(content)
            if m:
                content = content[m.end() :].strip()
            if "=== PACK STATS ===" in content:
                parts = re.split(r"\nQuestion:\s*", content, maxsplit=1)
                content = (parts[-1] if parts else content).strip()
            if len(content) > 2000:
                content = content[:2000] + "\n…"
        elif len(content) > DEEP_DIVE_HISTORY_ASSISTANT_CHARS:
            content = content[:DEEP_DIVE_HISTORY_ASSISTANT_CHARS] + "\n…"
        if content:
            out.append({"role": role, "content": content})
    if len(out) > DEEP_DIVE_HISTORY_TURNS:
        out = out[-DEEP_DIVE_HISTORY_TURNS:]
    return out


def measure_history_tokens(
    history: Sequence[Dict[str, str]],
    measure: Optional[Callable[[str], int]] = None,
) -> int:
    total = 0
    for turn in history or []:
        text = str(turn.get("content") or "")
        if measure is not None:
            total += max(0, int(measure(text)))
        else:
            total += max(1, int(len(text) / CHARS_PER_TOKEN))
    return total


def context_token_budget(
    n_ctx: int,
    *,
    max_out_tokens: int = 2048,
    system_reserve_tokens: int = 768,
    history_reserve_tokens: int = 2048,
) -> int:
    """Usable prompt tokens after reserving output, system, and history."""
    try:
        ctx = int(n_ctx)
    except (TypeError, ValueError):
        ctx = 8192
    try:
        max_out = max(256, int(max_out_tokens))
    except (TypeError, ValueError):
        max_out = 2048
    return max(512, ctx - max_out - system_reserve_tokens - history_reserve_tokens)


def apply_local_pack_cap(
    budget: int,
    *,
    provider: str,
    cap: int = 0,
    unit: str = "tokens",
    chars_per_token: float = CHARS_PER_TOKEN,
) -> int:
    """Keep a local llama-server pack from filling a 32k/64k window.

    ``cap`` is in tokens. ``0`` disables the cap. Cloud providers are unchanged.
    Char-mode budgets scale the cap by ``chars_per_token``.
    """
    try:
        size = int(budget)
    except (TypeError, ValueError):
        size = 0
    if not use_llama_tokenize(provider):
        return size
    try:
        cap_i = int(cap)
    except (TypeError, ValueError):
        return size
    if cap_i <= 0:
        return size
    if unit != "tokens":
        cap_i = max(1, int(cap_i * float(chars_per_token)))
    return min(size, cap_i)


def context_budget_for_n_ctx(
    n_ctx: int,
    *,
    max_out_tokens: int = 2048,
    system_reserve_tokens: int = 768,
    history_reserve_tokens: int = 2048,
    chars_per_token: float = CHARS_PER_TOKEN,
    floor: int = 8_000,
    ceiling: int = DEFAULT_CONTEXT_BUDGET,
) -> int:
    """Char budget for Deep Dive packing so prompt fits chat ``n_ctx``.

    Reserves space for system prompt, follow-up history, and ``max_tokens`` output.
    Ceiling scales up for large cloud windows (Vertex / Gemini).
    """
    try:
        ctx = int(n_ctx)
    except (TypeError, ValueError):
        ctx = 8192
    usable = context_token_budget(
        ctx,
        max_out_tokens=max_out_tokens,
        system_reserve_tokens=system_reserve_tokens,
        history_reserve_tokens=history_reserve_tokens,
    )
    budget = int(usable * float(chars_per_token))
    # Allow larger packs when the model window is huge (don't stay stuck at 96k).
    scaled_ceiling = max(int(ceiling), min(500_000, int(ctx * chars_per_token * 0.35)))
    return max(int(floor), min(scaled_ceiling, budget))

_ENTRYPOINT_PATTERNS = (
    r"(^|[/\\])main\.py$",
    r"(^|[/\\])app\.py$",
    r"__init__\.py$",
    r"window",
    r"dialog",
    r"manager",
    r"model",
)
_ENTRYPOINT_RE = [re.compile(p, re.IGNORECASE) for p in _ENTRYPOINT_PATTERNS]

# Absolute Windows / POSIX paths ending in a source-ish extension
_ABS_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s\"'`<>|]+?\.(?:py|md|json|txt|sql|js|ts|tsx|jsx)"
    r"|/(?:[^\s\"'`<>|]+?/)+[^\s\"'`<>|]+?\.(?:py|md|json|txt|sql))",
    re.IGNORECASE,
)
# Bare filenames or module tails: table_alias_manager.py, query_builder.py
_BASENAME_RE = re.compile(
    r"\b([A-Za-z_][\w.-]*\.(?:py|md|json|txt|sql))\b",
    re.IGNORECASE,
)
_IMPORT_STOP = frozenset(
    {
        "and", "or", "the", "a", "an", "as", "in", "on", "to", "for", "from",
        "import", "with", "is", "are", "be", "this", "that", "if", "else",
        "not", "no", "yes", "please", "retrieve", "request", "file", "files",
    }
)
_IMPORT_RE = re.compile(
    r"(?:from|import)\s+([A-Za-z_][\w.]*)",
    re.IGNORECASE,
)


def _normalize_ext_list(extension: str) -> Tuple[List[str], List[str]]:
    """Split an extension field into (include, exclude) lists.

    Supports comma/semicolon lists. A piece starting with ``!`` is exclude
    (``!.md,!.txt``). Bare pieces are include (``.py,.ts,.rs``).
    """
    include: List[str] = []
    exclude: List[str] = []
    raw = (extension or "").strip()
    if not raw or raw in ("*", "Any", "any", "(any)", "all", "All"):
        return include, exclude
    for piece in raw.replace(";", ",").split(","):
        piece = piece.strip()
        if not piece or piece in ("*", "Any", "any"):
            continue
        is_excl = piece.startswith("!")
        if is_excl:
            piece = piece[1:].strip()
        piece = piece.lstrip("*")
        if not piece:
            continue
        if not piece.startswith("."):
            piece = "." + piece
        piece = piece.lower()
        if is_excl:
            exclude.append(piece)
        else:
            include.append(piece)
    return include, exclude


def _path_like_group(piece: str) -> str:
    """`(path LIKE …)` for one root, matched with either separator style.

    An absolute root (``D:\\repo``, ``\\\\host\\share``, ``/srv``) anchors at the
    start so it selects that subtree; anything else is a substring match.
    """
    safe = piece.replace("'", "''")
    safe_fwd = safe.replace("\\", "/")
    safe_bs = safe.replace("/", "\\")
    is_abs = (
        (len(piece) >= 2 and piece[1] == ":")
        or piece.startswith("\\\\")
        or piece.startswith("/")
    )
    if is_abs:
        return f"(path LIKE '{safe_bs}%' OR path LIKE '{safe_fwd}%')"
    return f"(path LIKE '%{safe_bs}%' OR path LIKE '%{safe_fwd}%')"


def split_path_filter(path_contains: str) -> List[str]:
    """Semicolon-separated roots, e.g. ``Spock-Universal-AI-Wiki; LLMFIT``."""
    return [p.strip() for p in (path_contains or "").split(";") if p.strip()]


# MkDocs build output. Not every .html — templates/webui is source.
DEFAULT_GENERATED_PATH_EXCLUDES = ("\\site\\", "search_index.json")


def _root_names_site(piece: str) -> bool:
    """True when a path root is the ``site`` directory itself, not a substring."""
    norm = (piece or "").replace("/", "\\").strip("\\").lower()
    if not norm:
        return False
    return "site" in [part for part in norm.split("\\") if part]


def _exclude_fragment_clause(fragment: str) -> str:
    """``path NOT LIKE`` for one fragment, matched with either separator."""
    safe = (fragment or "").replace("'", "''")
    forms: List[str] = []
    for form in (safe.replace("/", "\\"), safe.replace("\\", "/")):
        if form and form not in forms:
            forms.append(form)
    parts = [f"path NOT LIKE '%{form}%'" for form in forms]
    if len(parts) == 1:
        return parts[0]
    return "(" + " AND ".join(parts) + ")"


def generated_path_exclude_clauses(path_contains: str = "") -> List[str]:
    """Drop generated ``site\\`` trees unless a root already names that folder."""
    paths = split_path_filter(path_contains)
    skip_site = any(_root_names_site(p) for p in paths)
    clauses: List[str] = []
    for fragment in DEFAULT_GENERATED_PATH_EXCLUDES:
        if skip_site and fragment.replace("/", "\\").strip("\\").lower() == "site":
            continue
        clauses.append(_exclude_fragment_clause(fragment))
    return clauses


def build_documents_filter_clause(
    path_contains: str,
    extension: str = "",
    exclude_extensions: str = "",
    exclude_generated: bool = True,
) -> str:
    """Build SQL AND clause for Documents path + include/exclude extensions.

    ``path_contains`` accepts several roots separated by ``;`` — they are OR'd,
    so ``Spock-Universal-AI-Wiki; LLMFIT`` researches both repos at once.
    ``extension`` may mix includes and ``!``-prefixed excludes
    (e.g. ``.py,.ts,!.md``). ``exclude_extensions`` is always exclude-only
    (e.g. ``.md,.txt``).
    ``exclude_generated`` drops MkDocs ``site\\`` and ``search_index.json``.
    A root that already names ``site`` keeps that tree and still drops the
    search index file.
    """
    clauses: List[str] = []
    paths = split_path_filter(path_contains)
    if len(paths) == 1:
        clauses.append(_path_like_group(paths[0]))
    elif paths:
        groups = " OR ".join(_path_like_group(p) for p in paths)
        clauses.append(f"({groups})")
    if exclude_generated:
        clauses.extend(generated_path_exclude_clauses(path_contains))

    include, exclude = _normalize_ext_list(extension)
    _, excl_extra = _normalize_ext_list(
        ",".join(
            (e if str(e).startswith("!") else f"!{e}")
            for e in (exclude_extensions or "").replace(";", ",").split(",")
            if e.strip()
        )
    )
    for e in excl_extra:
        if e not in exclude:
            exclude.append(e)

    if include:
        ext_ors = [
            f"lower(path) LIKE '%{e.replace(chr(39), chr(39)+chr(39))}'" for e in include
        ]
        if len(ext_ors) == 1:
            clauses.append(ext_ors[0])
        else:
            clauses.append("(" + " OR ".join(ext_ors) + ")")

    if exclude:
        for e in exclude:
            safe_ext = e.replace("'", "''")
            clauses.append(f"lower(path) NOT LIKE '%{safe_ext}'")

    return " AND ".join(clauses)


def count_filtered_docs(db_path: str, filter_clause: str) -> int:
    if not filter_clause or not db_path:
        return 0
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        n = conn.execute(
            f"SELECT COUNT(*) FROM documents WHERE ({filter_clause})"
        ).fetchone()[0]
        conn.close()
        return int(n)
    except Exception:
        return 0


def build_inventory(
    db_path: str,
    filter_clause: str,
    limit: int = DEFAULT_INVENTORY_LIMIT,
) -> List[Dict[str, Any]]:
    """List filtered documents (path, title, chars), largest first, capped."""
    if not filter_clause or not db_path:
        return []
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        rows = conn.execute(
            f"""
            SELECT path, title, LENGTH(content_plain) AS chars
            FROM documents
            WHERE ({filter_clause})
            ORDER BY chars DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        conn.close()
    except Exception:
        return []
    return [
        {"path": path or "", "title": title or "", "chars": int(chars or 0)}
        for path, title, chars in rows
    ]


def extract_requested_paths(question: str) -> List[str]:
    """Pull explicit file paths / basenames the user asked to retrieve."""
    q = question or ""
    found: List[str] = []
    seen: Set[str] = set()

    def _add(raw: str) -> None:
        text = (raw or "").strip().strip("`\"'")
        if not text:
            return
        key = text.replace("/", "\\").lower()
        if key in seen:
            return
        seen.add(key)
        found.append(text)

    for m in _ABS_PATH_RE.finditer(q):
        _add(m.group(0))
    for m in _BASENAME_RE.finditer(q):
        _add(m.group(1))
    for m in _IMPORT_RE.finditer(q):
        mod = m.group(1).strip(".")
        if not mod:
            continue
        # ui.table_alias_manager → table_alias_manager.py
        leaf = mod.split(".")[-1]
        if not leaf or leaf.lower() in _IMPORT_STOP:
            continue
        _add(f"{leaf}.py")

    return found


def entrypoint_boost(path: str) -> float:
    """Small score bonus for likely entrypoints / core modules when packing."""
    if not path:
        return 0.0
    name = os.path.basename(path)
    boost = 0.0
    for i, rx in enumerate(_ENTRYPOINT_RE):
        target = name if i < 3 else path
        if rx.search(target):
            boost = max(boost, 0.35 if i < 3 else 0.15)
    return boost


def request_boost(path: str, requests: Sequence[str]) -> float:
    """Large boost when path matches a user-requested file."""
    if not path or not requests:
        return 0.0
    pl = path.replace("/", "\\").lower()
    base = os.path.basename(pl)
    for req in requests:
        rl = req.replace("/", "\\").lower()
        rb = os.path.basename(rl)
        if pl == rl or pl.endswith("\\" + rl) or base == rb or base == rl:
            return FORCED_SCORE
        if rl in pl:
            return FORCED_SCORE * 0.9
    return 0.0


def _truncate_excerpt(text: str, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... [truncated]"


def _as_dive_doc(
    doc_id: int,
    title: str,
    path: str,
    score: float,
    content: str,
    excerpt_chars: int,
) -> Any:
    """Build a SearchResult-compatible object without importing Spock-to-bridge."""
    excerpt = _truncate_excerpt(content or "", excerpt_chars)

    @dataclass
    class _DiveDoc:
        doc_id: int
        title: str
        path: str
        score: float
        content_snippet: str

    return _DiveDoc(doc_id, title or "", path or "", float(score), excerpt)


def expand_excerpts(
    db_path: str,
    results: Sequence[Any],
    excerpt_chars: int = DEFAULT_EXCERPT_CHARS,
) -> List[Any]:
    """Re-load content_plain for hit docs and widen snippets for Deep Dive."""
    if not results:
        return []
    ids = [getattr(r, "doc_id", None) for r in results]
    ids = [i for i in ids if i is not None]
    if not ids:
        return list(results)
    placeholders = ",".join("?" * len(ids))
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        rows = conn.execute(
            f"SELECT id, content_plain FROM documents WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
        conn.close()
        by_id = {doc_id: content or "" for doc_id, content in rows}
    except Exception:
        by_id = {}

    out = []
    for r in results:
        content = by_id.get(
            getattr(r, "doc_id", None), getattr(r, "content_snippet", "") or ""
        )
        excerpt = _truncate_excerpt(content, excerpt_chars)
        try:
            out.append(replace(r, content_snippet=excerpt))
        except Exception:
            try:
                r.content_snippet = excerpt  # type: ignore[attr-defined]
            except Exception:
                pass
            out.append(r)
    return out


def fetch_docs_for_requests(
    db_path: str,
    filter_clause: str,
    requests: Sequence[str],
    excerpt_chars: int = FORCED_EXCERPT_CHARS,
) -> Tuple[List[Any], List[str], List[str]]:
    """Load documents matching explicit path/basename requests under the filter.

    Returns (docs, resolved_paths, unresolved_requests).
    """
    if not requests or not filter_clause or not db_path:
        return [], [], list(requests or [])

    try:
        conn = sqlite3.connect(db_path, timeout=5)
        rows = conn.execute(
            f"""
            SELECT id, title, path, content_plain, filename
            FROM documents
            WHERE ({filter_clause})
            """
        ).fetchall()
        conn.close()
    except Exception:
        return [], [], list(requests)

    # Normalize helpers
    def _norm(p: str) -> str:
        return (p or "").replace("/", "\\").lower()

    by_norm_path = {_norm(path): (doc_id, title, path, content) for doc_id, title, path, content, _fn in rows}
    by_base: Dict[str, List[Tuple[int, str, str, str]]] = {}
    for doc_id, title, path, content, filename in rows:
        base = (filename or os.path.basename(path or "")).lower()
        by_base.setdefault(base, []).append((doc_id, title, path, content or ""))

    resolved: List[Any] = []
    resolved_paths: List[str] = []
    unresolved: List[str] = []
    seen_ids: Set[int] = set()

    for req in requests:
        req_clean = req.strip().strip("`\"'")
        if not req_clean:
            continue
        nreq = _norm(req_clean)
        base = os.path.basename(nreq)
        hit = None
        if nreq in by_norm_path:
            hit = by_norm_path[nreq]
        else:
            # suffix match on full path
            for np, tup in by_norm_path.items():
                if np.endswith("\\" + nreq) or np.endswith(nreq):
                    hit = tup
                    break
        if hit is None and base in by_base:
            # Prefer shortest path (most specific leaf)
            cands = sorted(by_base[base], key=lambda t: len(t[2] or ""))
            hit = cands[0]
        if hit is None:
            unresolved.append(req_clean)
            continue
        doc_id, title, path, content = hit
        if doc_id in seen_ids:
            continue
        seen_ids.add(doc_id)
        resolved.append(
            _as_dive_doc(
                doc_id,
                title,
                path,
                FORCED_SCORE,
                content or "",
                excerpt_chars,
            )
        )
        resolved_paths.append(path or "")

    return resolved, resolved_paths, unresolved


def fetch_fill_docs(
    db_path: str,
    filter_clause: str,
    exclude_ids: Set[int],
    limit: int = 40,
    excerpt_chars: int = DEFAULT_EXCERPT_CHARS,
) -> List[Any]:
    """Extra filtered docs to soak remaining context budget (medium size first)."""
    if not filter_clause or not db_path or limit <= 0:
        return []
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        rows = conn.execute(
            f"""
            SELECT id, title, path, content_plain, LENGTH(content_plain) AS chars
            FROM documents
            WHERE ({filter_clause})
            ORDER BY
              CASE
                WHEN LENGTH(content_plain) BETWEEN 500 AND 20000 THEN 0
                WHEN LENGTH(content_plain) < 500 THEN 1
                ELSE 2
              END,
              LENGTH(content_plain) DESC
            LIMIT ?
            """,
            (max(limit * 3, limit),),
        ).fetchall()
        conn.close()
    except Exception:
        return []

    out: List[Any] = []
    for doc_id, title, path, content, _chars in rows:
        if doc_id in exclude_ids:
            continue
        out.append(
            _as_dive_doc(
                doc_id,
                title,
                path,
                0.05 + entrypoint_boost(path or ""),
                content or "",
                excerpt_chars,
            )
        )
        if len(out) >= limit:
            break
    return out


def deep_dive_retrieve(
    db_path: str,
    question: str,
    filter_clause: str,
    hybrid_search_fn: Callable[..., List[Any]],
    embeddings_url: Optional[str] = None,
    top_k: int = DEFAULT_TOP_K,
    excerpt_chars: int = DEFAULT_EXCERPT_CHARS,
    fill_budget: bool = True,
    fill_top_k: int = FILL_TOP_K,
    forced_excerpt_chars: int = FORCED_EXCERPT_CHARS,
) -> Tuple[List[Any], List[str], List[str], List[str]]:
    """Hybrid search + forced path pulls + optional fill candidates.

    Returns (results, requested, forced_paths, unresolved_requests).
    """
    requested = extract_requested_paths(question)
    forced, forced_paths, unresolved = fetch_docs_for_requests(
        db_path, filter_clause, requested, excerpt_chars=forced_excerpt_chars
    )

    # Larger hybrid pool when user named files or we plan to fill budget
    pool_k = fill_top_k if (requested or fill_budget) else top_k
    hybrid = hybrid_search_fn(
        db_path,
        question,
        top_k=pool_k,
        embeddings_url=embeddings_url,
        filter_clause=filter_clause,
    )
    hybrid = expand_excerpts(db_path, hybrid, excerpt_chars=excerpt_chars)

    seen: Set[int] = set()
    merged: List[Any] = []
    for r in forced:
        did = getattr(r, "doc_id", None)
        if did is not None:
            seen.add(did)
        merged.append(r)
    for r in hybrid:
        did = getattr(r, "doc_id", None)
        if did is not None and did in seen:
            continue
        if did is not None:
            seen.add(did)
        # Tag requested hybrid hits with boost via score bump for packing
        boost = request_boost(getattr(r, "path", "") or "", requested)
        if boost and hasattr(r, "score"):
            try:
                r = replace(r, score=float(getattr(r, "score", 0) or 0) + boost)
            except Exception:
                try:
                    r.score = float(getattr(r, "score", 0) or 0) + boost
                except Exception:
                    pass
        merged.append(r)

    if fill_budget:
        fillers = fetch_fill_docs(
            db_path, filter_clause, seen, limit=40, excerpt_chars=excerpt_chars
        )
        for r in fillers:
            did = getattr(r, "doc_id", None)
            if did is not None and did in seen:
                continue
            if did is not None:
                seen.add(did)
            merged.append(r)

    return merged, requested, forced_paths, unresolved


@dataclass
class DeepDivePackStats:
    match_count: int = 0
    inventory_shown: int = 0
    used_docs: int = 0
    context_chars: int = 0
    budget: int = DEFAULT_CONTEXT_BUDGET
    filter_clause: str = ""
    large_corpus: bool = False
    used_paths: List[str] = field(default_factory=list)
    requested: List[str] = field(default_factory=list)
    forced_paths: List[str] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)
    budget_used_pct: float = 0.0
    unit: str = "chars"
    measured_units: int = 0

    def summary_line(self) -> str:
        forced_n = len(self.forced_paths)
        miss = f" · missing {len(self.unresolved)}" if self.unresolved else ""
        if self.unit == "tokens" and self.measured_units:
            amount = (
                f"{self.measured_units:,} tokens"
                f" · {self.context_chars:,} chars"
            )
        else:
            unit = "tokens" if self.unit == "tokens" else "chars"
            amount = f"{self.context_chars:,} {unit}"
        return (
            f"Deep Dive: {self.match_count} match(es) · "
            f"inventory {self.inventory_shown} · "
            f"used {self.used_docs} · "
            f"forced {forced_n}{miss} · "
            f"{amount} "
            f"({self.budget_used_pct:.0f}% of {self.budget:,})"
        )


def pack_deep_dive_context(
    inventory: List[Dict[str, Any]],
    results: Sequence[Any],
    filter_clause: str,
    match_count: int,
    budget: int = DEFAULT_CONTEXT_BUDGET,
    requested: Optional[Sequence[str]] = None,
    forced_paths: Optional[Sequence[str]] = None,
    unresolved: Optional[Sequence[str]] = None,
    measure: Optional[Callable[[str], int]] = None,
    unit: str = "chars",
) -> Tuple[str, List[Any], DeepDivePackStats]:
    """Build prompt context: inventory + forced/hybrid excerpts until budget full."""
    requested = list(requested or [])
    forced_paths = list(forced_paths or [])
    unresolved = list(unresolved or [])
    size = measure or len
    token_mode = unit == "tokens"
    min_keep = 40 if token_mode else 200
    header_pad = 40 if token_mode else 120
    stats = DeepDivePackStats(
        match_count=match_count,
        inventory_shown=0,
        filter_clause=filter_clause or "",
        large_corpus=match_count > LARGE_CORPUS_WARN,
        budget=budget,
        requested=requested,
        forced_paths=forced_paths,
        unresolved=unresolved,
        unit="tokens" if token_mode else "chars",
    )

    header_lines = [
        "=== DEEP DIVE CORPUS ===",
        f"Filter: {filter_clause or '(none)'}",
        f"Matching documents: {match_count}",
    ]
    if requested:
        header_lines.append("User-requested files: " + ", ".join(requested))
    if forced_paths:
        header_lines.append("Forced into excerpts: " + ", ".join(forced_paths))
    if unresolved:
        header_lines.append(
            "Requested but NOT found under filter: " + ", ".join(unresolved)
        )
    header_lines.extend(["", "Inventory (sample, by size):"])
    inv_cap = INVENTORY_TOKEN_CAP if token_mode else int(INVENTORY_TOKEN_CAP * CHARS_PER_TOKEN)
    inv_lines: List[str] = []
    shown = 0
    if inventory:
        for item in inventory:
            line = f"  - {item.get('path', '')}  ({item.get('chars', 0):,} chars)"
            trial = "\n".join(inv_lines + [line])
            if inv_lines and size(trial) > inv_cap:
                break
            inv_lines.append(line)
            shown += 1
        hidden = len(inventory) - shown
        if hidden:
            inv_lines.append(f"  … {hidden} more not listed")
        header_lines.extend(inv_lines)
    else:
        header_lines.append("  (empty inventory)")
    stats.inventory_shown = shown
    header_lines.append("")
    header_lines.append("=== RETRIEVED EXCERPTS ===")
    header = "\n".join(header_lines) + "\n"

    # Forced / requested first, then score + entrypoint
    def _pack_key(r: Any) -> Tuple[float, float]:
        path = getattr(r, "path", "") or ""
        return (
            request_boost(path, requested) + float(getattr(r, "score", 0.0) or 0.0),
            entrypoint_boost(path),
        )

    ranked = sorted(results, key=_pack_key, reverse=True)

    used: List[Any] = []
    body_parts: List[str] = []
    remaining = max(0, budget - size(header) - header_pad)

    for i, r in enumerate(ranked, 1):
        if remaining < min_keep:
            break
        path = getattr(r, "path", "") or ""
        forced_tag = " [FORCED]" if request_boost(path, requested) else ""
        content = getattr(r, "content_snippet", "") or ""
        block = (
            f"[Doc {i}] {getattr(r, 'title', '')}{forced_tag}\n"
            f"  Path: {path}\n"
            f"  Relevance: {float(getattr(r, 'score', 0.0) or 0.0):.3f}\n"
            f"  Content:\n{content}\n"
        )
        block_n = size(block)
        if block_n > remaining:
            room = remaining - (20 if token_mode else 200)
            if room < (20 if token_mode else 100):
                break
            room_chars = int(room * 4) if token_mode else room
            short = _truncate_excerpt(content, max(100, room_chars))
            block = (
                f"[Doc {i}] {getattr(r, 'title', '')}{forced_tag}\n"
                f"  Path: {path}\n"
                f"  Relevance: {float(getattr(r, 'score', 0.0) or 0.0):.3f}\n"
                f"  Content:\n{short}\n"
            )
            block_n = size(block)
            if block_n > remaining:
                break
        body_parts.append(block)
        used.append(r)
        remaining -= block_n
        stats.used_paths.append(path)

    if not body_parts:
        body = (
            "(No relevant excerpts packed under the context budget. "
            "Keyword and vector search both returned empty, or budget exhausted.)\n"
        )
    else:
        body = "\n".join(body_parts)

    packed = size(header) + size(body)
    footer = (
        f"\n=== PACK STATS ===\n"
        f"used {len(used)} of {match_count} matching docs, "
        f"{packed:,} / {budget:,} {unit}, "
        f"headroom {max(0, budget - packed):,}\n"
    )
    if forced_paths:
        footer += "Forced excerpts included: " + ", ".join(forced_paths) + "\n"
    if unresolved:
        footer += "Still missing under filter: " + ", ".join(unresolved) + "\n"

    context = header + body + footer
    stats.used_docs = len(used)
    stats.context_chars = len(context)
    stats.measured_units = int(packed)
    stats.budget_used_pct = 100.0 * packed / budget if budget else 0.0
    return context, used, stats


DEEP_DIVE_SYSTEM_PROMPT = (
    "You are performing a Deep Dive over a filtered codebase corpus from the "
    "ship's computer (ship_computer.db). Prefer architecture, call flow, and "
    "file-level citations using full paths. Be technical and structured. "
    "Files marked [FORCED] were explicitly requested by the user — treat them as "
    "primary evidence and quote/summarize their actual content. "
    "Only say a file is missing if it appears under "
    "'Requested but NOT found under filter' or is absent from the excerpts. "
    "If prior conversation turns are provided, continue from that analysis; "
    "do not repeat the whole report unless asked."
)


def run_http_deep_dive(
    *,
    question: str,
    filter_clause: str,
    history: Optional[List[Dict[str, str]]],
    llm: Any,
    embeddings_url: str,
    db_path: str,
    hybrid_search_fn: Callable[..., Any],
    n_ctx: int = 131072,
    max_out_tokens: int = 8192,
    ask_ai_provider: str = "",
    chat_url: str = "",
    record_timing: bool = True,
    ctx: Optional[Dict[str, Any]] = None,
    stream: bool = False,
    on_token: Optional[Callable[[str], None]] = None,
    on_timeout_continue: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Any]:
    """Deep Dive for RAG HTTP / Web UI. Returns answer, sources, stats."""
    import time

    try:
        from WarpCore.config_defaults import merge_ctx_settings
    except Exception:  # pragma: no cover
        merge_ctx_settings = None  # type: ignore
    ctx_opts = merge_ctx_settings(ctx) if callable(merge_ctx_settings) else dict(ctx or {})

    t0 = time.perf_counter()
    # Empty filter → entire corpus (SQL tautology for inventory / retrieve).
    clause = (filter_clause or "").strip() or "1=1"
    match_count = count_filtered_docs(db_path, clause)
    if match_count == 0:
        stats = {
            "mode": "deep_dive",
            "summary": "0 matches under filter",
            "pack_summary": "Deep Dive: 0 match(es)",
            "match_count": 0,
            "n_ctx": int(n_ctx),
            "total_ms": int((time.perf_counter() - t0) * 1000),
            "retrieve_ms": 0,
            "pack_ms": 0,
            "llm_ms": 0,
            "inventory_shown": 0,
            "forced_count": 0,
            "unresolved_count": 0,
            "budget_used_pct": 0.0,
        }
        if record_timing and ctx_opts.get("timing_enabled", True):
            try:
                from WarpCore.ask_timing_store import insert_timing

                insert_timing(
                    mode="deep_dive",
                    question=question,
                    response_length=len(
                        "Deep Dive could not run — no documents match the active filter."
                    ),
                    total_ms=stats["total_ms"],
                    retrieve_ms=0,
                    pack_ms=0,
                    llm_ms=0,
                    n_ctx=int(n_ctx),
                    match_count=0,
                    inventory_shown=0,
                    forced_count=0,
                    unresolved_count=0,
                    budget_used_pct=0.0,
                    pack_summary=stats["pack_summary"],
                    provider=str(ask_ai_provider or ""),
                    filter_info={"filter_clause": filter_clause or ""},
                    updated_by="deep_dive",
                    db_path=db_path,
                )
            except Exception:
                pass
        return {
            "answer": "Deep Dive could not run — no documents match the active filter.",
            "sources": [],
            "stats": stats,
        }

    inv_limit = int(ctx_opts.get("deep_inventory_limit") or DEFAULT_INVENTORY_LIMIT)
    excerpt_chars = int(ctx_opts.get("deep_excerpt_chars") or DEFAULT_EXCERPT_CHARS)
    forced_excerpt = int(
        ctx_opts.get("deep_forced_excerpt_chars") or FORCED_EXCERPT_CHARS
    )
    top_k = int(ctx_opts.get("deep_top_k") or DEFAULT_TOP_K)
    fill_top_k = int(ctx_opts.get("deep_fill_top_k") or FILL_TOP_K)
    try:
        chars_per_token = float(ctx_opts.get("chars_per_token") or CHARS_PER_TOKEN)
    except (TypeError, ValueError):
        chars_per_token = CHARS_PER_TOKEN
    budget_ceiling = int(ctx_opts.get("deep_budget_chars") or DEFAULT_CONTEXT_BUDGET)
    budget_floor = int(ctx_opts.get("deep_budget_floor") or 8_000)

    t_ret0 = time.perf_counter()
    inventory = build_inventory(db_path, clause, limit=inv_limit)
    results, requested, forced_paths, unresolved = deep_dive_retrieve(
        db_path,
        question,
        clause,
        hybrid_search_fn=hybrid_search_fn,
        embeddings_url=embeddings_url,
        top_k=top_k,
        excerpt_chars=excerpt_chars,
        fill_budget=True,
        fill_top_k=fill_top_k,
        forced_excerpt_chars=forced_excerpt,
    )
    retrieve_ms = int((time.perf_counter() - t_ret0) * 1000)

    history = sanitize_deep_dive_history(history)
    if use_llama_tokenize(ask_ai_provider) and chat_url:
        live_ctx = probe_llama_n_ctx(chat_url)
        if live_ctx:
            n_ctx = int(live_ctx)
    measure: Optional[Callable[[str], int]] = None
    unit = "chars"
    hist_tokens = 256
    if use_llama_tokenize(ask_ai_provider) and chat_url:
        if llama_token_count("ok", chat_url) is not None:
            cache: Dict[str, int] = {}

            def _count(text: str) -> int:
                hit = cache.get(text)
                if hit is not None:
                    return hit
                n = llama_token_count(text, chat_url)
                if n is None:
                    n = max(1, int(len(text) / chars_per_token))
                cache[text] = n
                return n

            measure = _count
            unit = "tokens"
            hist_tokens = max(256, measure_history_tokens(history, measure))
            budget = context_token_budget(
                int(n_ctx or 8192),
                max_out_tokens=int(max_out_tokens or 2048),
                system_reserve_tokens=1024,
                history_reserve_tokens=hist_tokens,
            )
        else:
            hist_tokens = max(256, measure_history_tokens(history))
            budget = context_budget_for_n_ctx(
                int(n_ctx or 8192),
                max_out_tokens=int(max_out_tokens or 2048),
                system_reserve_tokens=1024,
                history_reserve_tokens=hist_tokens,
                chars_per_token=chars_per_token,
                floor=budget_floor,
                ceiling=budget_ceiling,
            )
    else:
        hist_tokens = max(256, measure_history_tokens(history))
        budget = context_budget_for_n_ctx(
            int(n_ctx or 131072),
            max_out_tokens=int(max_out_tokens or 8192),
            history_reserve_tokens=hist_tokens,
            chars_per_token=chars_per_token,
            floor=budget_floor,
            ceiling=budget_ceiling,
        )

    try:
        pack_cap = int(ctx_opts.get("deep_pack_token_cap") or 0)
    except (TypeError, ValueError):
        pack_cap = 0
    budget = apply_local_pack_cap(
        budget,
        provider=str(ask_ai_provider or ""),
        cap=pack_cap,
        unit=unit,
        chars_per_token=chars_per_token,
    )

    t_pack0 = time.perf_counter()
    context, used, pack_stats = pack_deep_dive_context(
        inventory,
        results,
        filter_clause=clause,
        match_count=match_count or max(len(inventory), len(results)),
        budget=budget,
        requested=requested,
        forced_paths=forced_paths,
        unresolved=unresolved,
        measure=measure,
        unit=unit,
    )
    pack_ms = int((time.perf_counter() - t_pack0) * 1000)

    t_llm0 = time.perf_counter()
    stream_fn = getattr(llm, "ask_with_context_stream", None) if stream else None
    if stream and callable(stream_fn):
        chunks: List[str] = []
        for tok in stream_fn(
            question,
            context,
            DEEP_DIVE_SYSTEM_PROMPT,
            history=history,
            on_timeout_continue=on_timeout_continue,
        ):
            if not tok:
                continue
            chunks.append(tok)
            if on_token is not None:
                try:
                    on_token(tok)
                except Exception:
                    pass
        answer = "".join(chunks)
    else:
        answer = llm.ask_with_context(
            question,
            context,
            DEEP_DIVE_SYSTEM_PROMPT,
            history=history,
            on_timeout_continue=on_timeout_continue,
        )
    llm_ms = int((time.perf_counter() - t_llm0) * 1000)
    total_ms = int((time.perf_counter() - t0) * 1000)

    sources: List[Dict[str, Any]] = []
    for r in used:
        sources.append(
            {
                "title": getattr(r, "title", "") or getattr(r, "path", "") or "doc",
                "path": getattr(r, "path", "") or "",
                "score": float(getattr(r, "score", 0) or 0),
                "snippet": (
                    getattr(r, "content_snippet", None)
                    or getattr(r, "snippet", None)
                    or ""
                )[:500],
            }
        )
    answer_text = answer or ""
    pack_summary = pack_stats.summary_line()
    stats = {
        "mode": "deep_dive",
        "summary": pack_summary,
        "pack_summary": pack_summary,
        "match_count": pack_stats.match_count,
        "used_docs": pack_stats.used_docs,
        "inventory_shown": pack_stats.inventory_shown,
        "forced_count": len(pack_stats.forced_paths or []),
        "unresolved_count": len(pack_stats.unresolved or []),
        "context_chars": pack_stats.context_chars,
        "budget": pack_stats.budget,
        "budget_used_pct": float(pack_stats.budget_used_pct or 0.0),
        "n_ctx": int(n_ctx),
        "max_out": int(max_out_tokens),
        "history_tokens": int(hist_tokens),
        "filter": filter_clause or None,
        "total_ms": total_ms,
        "retrieve_ms": retrieve_ms,
        "pack_ms": pack_ms,
        "llm_ms": llm_ms,
        "response_length": len(answer_text),
        "streamed": bool(stream and callable(stream_fn)),
    }
    if record_timing and ctx_opts.get("timing_enabled", True):
        try:
            from WarpCore.ask_timing_store import insert_timing

            insert_timing(
                mode="deep_dive",
                question=question,
                response_length=len(answer_text),
                total_ms=total_ms,
                retrieve_ms=retrieve_ms,
                pack_ms=pack_ms,
                llm_ms=llm_ms,
                n_ctx=int(n_ctx),
                budget=int(pack_stats.budget or 0),
                budget_used=int(pack_stats.context_chars or 0),
                budget_used_pct=float(pack_stats.budget_used_pct or 0.0),
                docs_used=int(pack_stats.used_docs or 0),
                match_count=int(pack_stats.match_count or 0),
                inventory_shown=int(pack_stats.inventory_shown or 0),
                forced_count=len(pack_stats.forced_paths or []),
                unresolved_count=len(pack_stats.unresolved or []),
                max_out=int(max_out_tokens or 0),
                pack_summary=pack_summary,
                provider=str(ask_ai_provider or ""),
                stage_timings={
                    "retrieve_ms": retrieve_ms,
                    "pack_ms": pack_ms,
                    "llm_ms": llm_ms,
                    "total_ms": total_ms,
                },
                filter_info={"filter_clause": filter_clause or ""},
                meta={
                    "summary": pack_summary,
                    "unit": unit,
                    "streamed": stats["streamed"],
                },
                updated_by="deep_dive",
                db_path=db_path,
            )
        except Exception:
            pass
    return {
        "answer": answer_text,
        "sources": sources,
        "stats": stats,
    }
