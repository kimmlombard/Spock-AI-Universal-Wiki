"""Deterministic fill of the seven docs/codebase templates from scan + filesystem."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from spock_codebase_knowledge.filters import load_skip_dir_names

_SECTION_RE = re.compile(r"^===\s*(.+?)\s*===\s*$")


def split_scan_sections(scan_text: str) -> Dict[str, str]:
    """Split scan.py output on ``=== TITLE ===`` headings."""
    sections: Dict[str, str] = {"_preamble": ""}
    current = "_preamble"
    buf: List[str] = []
    for line in (scan_text or "").splitlines():
        m = _SECTION_RE.match(line.strip())
        if m:
            sections[current] = "\n".join(buf).strip()
            current = m.group(1).strip().upper()
            buf = []
            continue
        buf.append(line)
    sections[current] = "\n".join(buf).strip()
    return sections


def _section(sections: Dict[str, str], *needles: str) -> str:
    for name, body in sections.items():
        if name == "_preamble":
            continue
        upper = name.upper()
        if any(n.upper() in upper for n in needles):
            return body
    return ""


def _table(rows: Sequence[Sequence[str]], headers: Sequence[str]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        cells = [str(c).replace("|", "\\|") for c in row]
        while len(cells) < len(headers):
            cells.append("")
        lines.append("| " + " | ".join(cells[: len(headers)]) + " |")
    return "\n".join(lines)


def _req_deps(root: Path) -> List[Tuple[str, str, str, str]]:
    """Return (name, version, role, evidence) from requirements*.txt."""
    rows: List[Tuple[str, str, str, str]] = []
    role_hints = {
        "PyQt6": "GUI",
        "torch": "ML / embeddings (optional)",
        "watchdog": "Wiki file watcher",
        "requests": "HTTP",
        "httpx": "HTTP",
        "fastapi": "RAG / HTTP API",
        "uvicorn": "ASGI server",
        "openai": "OpenAI-compatible client",
        "numpy": "Numeric",
        "pytest": "Tests (dev)",
        "mkdocs": "Docs site",
        "psutil": "Process / hardware",
    }
    for name in (
        "requirements.txt",
        "requirements-full.txt",
        "requirements-ui.txt",
        "requirements-mcp.txt",
        "requirements-dev.txt",
        "requirements-docs.txt",
    ):
        path = root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("-r "):
                continue
            pkg = re.split(r"[<>=!~;\[]", s, maxsplit=1)[0].strip()
            ver = ""
            m = re.search(r"([<>=!~]=?)\s*([^\s;#]+)", s)
            if m:
                ver = m.group(1) + m.group(2)
            role = role_hints.get(pkg, "dependency")
            rows.append((pkg, ver or "[unpinned]", role, name))
            if len(rows) >= 40:
                return rows
    return rows


def _top_level_map(root: Path, skip: frozenset) -> List[Tuple[str, str, str]]:
    purpose = {
        "WarpCore": "Shared DB / settings / skill contracts",
        "NavigationStation": "Primary operator GUI",
        "EngineeringDeck": "Ask AI + Engineering Maintenance",
        "ScienceStation": "Science / wiki / ships logs GUI",
        "spock_shell": "Shared shell widgets / busy UI / paths",
        "spock_onboarding": "Bringup / acquire / fit select",
        "spock_bringup": "CLI bringup steps",
        "spock_bringup_menu": "Bringup GUI",
        "spock_wiki_adapter": "Wiki Scan panel",
        "spock_rag_adapter": "RAG / embeddings bridge",
        "spock_mcp_adapter": "MCP adapter",
        "model_selector": "Model launch / status",
        "docs": "MkDocs + generated structure docs",
        "tests": "Pytest suite",
        "AIHelperDocuments": "Helper / Ask AI source markdown",
        "spock_codebase_knowledge": "Acquire codebase knowledge skill",
        "wiki_agent.py": "Wiki agent + Skills handlers",
        "deep_dive.py": "Deep Dive packing / retrieve",
        "llm_client.py": "Chat LLM client",
        "ship_computer_schema.sql": "SQLite schema",
        "bootstrap.ps1": "Bootstrap installer",
        "main.py": "Legacy / root entry",
    }
    rows: List[Tuple[str, str, str]] = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        return rows
    for item in entries:
        if item.name.startswith(".") and item.name not in {".github"}:
            continue
        if item.name in skip:
            continue
        if item.is_dir() and item.name in skip:
            continue
        rel = item.name + ("/" if item.is_dir() else "")
        rows.append((rel, purpose.get(item.name, "[TODO]"), f"`{item.name}`"))
        if len(rows) >= 35:
            break
    return rows


def _python_packages(root: Path, skip: frozenset) -> List[str]:
    pkgs: List[str] = []
    try:
        for item in sorted(root.iterdir()):
            if not item.is_dir() or item.name in skip or item.name.startswith("."):
                continue
            if (item / "__init__.py").is_file() or (item / "__main__.py").is_file():
                pkgs.append(item.name)
    except OSError:
        pass
    return pkgs


def _entry_points(root: Path, sections: Dict[str, str], skip: frozenset) -> List[str]:
    found: List[str] = []
    body = _section(sections, "ENTRY POINTS")
    for line in body.splitlines():
        line = line.strip()
        if line.lower().startswith("found:"):
            found.append(line.split(":", 1)[1].strip())
        elif line and not line.lower().startswith("no common"):
            if line.endswith(".py") or "/" in line or "\\" in line:
                found.append(line.replace("\\", "/"))
    # Extra: package -m style
    for pkg in _python_packages(root, skip):
        main = root / pkg / "__main__.py"
        if main.is_file():
            found.append(f"python -m {pkg}  ({pkg}/__main__.py)")
    # Dedup preserve order
    out: List[str] = []
    seen = set()
    for f in found:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def _readme_intent(root: Path) -> str:
    for name in ("README.md", "README.rst", "README.txt"):
        path = root / name
        if path.is_file():
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[:50]
            except OSError:
                continue
            return f"From `{name}`:\n\n" + "\n".join(lines)
    # Spock often uses HELPER docs
    helper = root / "AIHelperDocuments"
    if helper.is_dir():
        for path in sorted(helper.glob("*Overview*.md"))[:1]:
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[:40]
            except OSError:
                continue
            return f"From `{path.relative_to(root)}` (no root README):\n\n" + "\n".join(lines)
    return "[TODO] No README/ROADMAP/SPEC found at project root."


def _env_vars_hint(root: Path) -> List[str]:
    hints = [
        "EMBEDDINGS_URL",
        "EMBEDDINGS_DIM",
        "HF_TOKEN",
        "SPOCK_EMBED_MODEL_PATH",
        "PYTHONUNBUFFERED",
    ]
    found: List[str] = []
    for name in (".env.example", ".env.template", ".env.sample"):
        if (root / name).is_file():
            found.append(name)
    return found or hints


def _pytest_layout(root: Path) -> Tuple[str, List[str]]:
    tests = root / "tests"
    files: List[str] = []
    if tests.is_dir():
        for p in sorted(tests.glob("test_*.py"))[:25]:
            files.append(str(p.relative_to(root)).replace("\\", "/"))
    framework = "pytest" if files or (root / "pytest.ini").is_file() or (root / "pyproject.toml").is_file() else "[TODO]"
    return framework, files


def _integrations(root: Path) -> List[Tuple[str, str, str]]:
    rows = [
        ("llama-server embeddings", ":8080", "llama_server_manager / Launch"),
        ("llama-server chat", ":8081", "llama_server_manager / Launch"),
        ("RAG API", ":8090 (typical)", "rag_api_server.py"),
        ("MCP", ":8765 (typical)", "spock_mcp_adapter / mcp_spock_server"),
        ("SQLite ship computer", "ship_computer.db", "WarpCore / wiki_agent"),
        ("Hugging Face Hub", "model download", "model_selector / acquire"),
    ]
    if (root / "mkdocs.yml").is_file():
        rows.append(("MkDocs", "docs/", "mkdocs.yml"))
    return rows


def _architecture_layers(root: Path, skip: frozenset) -> List[Tuple[str, str, str]]:
    pkgs = _python_packages(root, skip)
    layers = [
        ("UI / Stations", "NavigationStation, EngineeringDeck, ScienceStation, Bringup Menu", "PyQt6 apps"),
        ("Wiki agent / ingest", "wiki_agent, starfleet_universal_extractor, onboarding skill", "agent_queue → documents"),
        ("RAG / Ask AI", "deep_dive, llm_client, spock_rag_adapter, AskAiPanel", "hybrid search + LLM"),
        ("Hardware / models", "spock_scanner_core, model_selector, host_recipe, llmfit", "VRAM-aware launch"),
        ("Persistence", "WarpCore.settings_store, ship_computer.db", "SQLite + FTS5 + embeddings"),
    ]
    if pkgs:
        layers.append(("Python packages present", ", ".join(pkgs[:20]), "filesystem"))
    return layers


def _conventions(root: Path) -> List[str]:
    bits = [
        "- Python packages use PascalCase or snake_case package dirs with `__init__.py`.",
        "- Wiki agent skills are methods on `Skills` validated via `WarpCore.skills`.",
        "- Prefer `spock_shell.paths` for ROOT / DB paths.",
    ]
    if (root / "pyproject.toml").is_file() or (root / "ruff.toml").is_file():
        bits.append("- Lint/format config present at repo root (see LINTING section in scan).")
    else:
        bits.append("- [TODO] No root ruff/black/flake8 config detected by scan.")
    return bits


def _concerns(sections: Dict[str, str], skip: frozenset) -> List[str]:
    lines: List[str] = []
    todos = _section(sections, "TODO", "FIXME")
    if todos and "None found" not in todos:
        kept = []
        for line in todos.splitlines():
            if not line.strip():
                continue
            if any(s in line.replace("\\", "/") for s in skip):
                continue
            # also skip data/blobs style
            if "/data/" in line.replace("\\", "/") or line.replace("\\", "/").startswith("data/"):
                continue
            kept.append(line)
        if kept:
            lines.append("### Sample TODO/FIXME (filtered)\n")
            lines.extend(f"- `{k}`" for k in kept[:15])
        else:
            lines.append("- No production TODOs after skip_dirs filter.")
    else:
        lines.append("- No TODO/FIXME hits in filtered scan.")
    churn = _section(sections, "HIGH-CHURN", "CHURN")
    if churn and "None" not in churn[:40]:
        lines.append("\n### High-churn files (git, filtered)\n")
        lines.append("```\n" + "\n".join(churn.splitlines()[:15]) + "\n```")
    return lines


def _evidence_block(sections: Dict[str, str], *needles: str, limit: int = 3500) -> str:
    body = _section(sections, *needles)
    if not body:
        return ""
    return f"### Raw scan excerpt\n\n```\n{body[:limit]}\n```\n"


def build_docs(
    *,
    root: Path,
    scan_path: Path,
    sections: Dict[str, str],
    focus: str = "",
    generated_at: str = "",
) -> Dict[str, str]:
    """Return mapping of DOC_NAME → filled markdown."""
    skip = load_skip_dir_names(root)
    focus_note = f"\n_Focus area: {focus}_\n" if focus else "\n"
    header = (
        f"<!-- Generated by Spock acquire_codebase_knowledge (deterministic fill) "
        f"at {generated_at} for {root} -->\n"
        f"<!-- Scan: {scan_path} -->\n"
        f"<!-- Skip dirs: {', '.join(sorted(skip)[:40])}{'…' if len(skip) > 40 else ''} -->\n\n"
    )

    def wrap(title: str, body: str, extra_evidence: str = "") -> str:
        return (
            header
            + f"# {title}\n"
            + focus_note
            + "\n"
            + body.strip()
            + "\n\n## Evidence\n\n"
            + f"- `{scan_path}`\n"
            + f"- Filters: `.gitignore` + `scan.skip_dirs` + built-in extras\n"
            + (f"\n{extra_evidence}" if extra_evidence else "")
            + "\n"
        )

    # STACK
    deps = _req_deps(root)
    stack_rows = [
        ("Primary language", "Python", "requirements*.txt / *.py"),
        ("Runtime", "CPython 3.x (venv under `.venv`)", ".venv / bootstrap"),
        ("Package manager", "pip + requirements-*.txt tiers", "requirements.txt"),
        ("GUI", "PyQt6", "requirements-ui.txt"),
        ("Local LLM", "llama-server (OpenAI-compatible)", "llama_server_manager"),
        ("Database", "SQLite (ship_computer.db)", "ship_computer_schema.sql"),
    ]
    stack = "## Runtime summary\n\n" + _table(stack_rows, ("Area", "Value", "Evidence"))
    stack += "\n\n## Stated project intent\n\n" + _readme_intent(root)
    stack += "\n\n## Production / install dependencies (from requirements*)\n\n"
    if deps:
        stack += _table(deps, ("Dependency", "Version", "Role", "Evidence"))
    else:
        stack += "[TODO] No requirements*.txt parsed.\n"
    stack += "\n\n## Key commands\n\n```bash\n"
    stack += "python -m spock_bringup_menu\n"
    stack += "python -m EngineeringDeck   # or NavigationStation / ScienceStation\n"
    stack += "python -m pytest\n"
    stack += "pip install -r requirements-ui.txt   # Phase A\n"
    stack += "pip install -r requirements-full.txt # Phase B\n"
    stack += "```\n\n## Environment / config\n\n"
    stack += "- Config: `WarpCore.settings_store` in `ship_computer.db` (scan.*, app.*, secrets)\n"
    stack += "- Optional overlays: `scan_config.json`, `.env` (gitignored)\n"
    stack += "- Notable vars: " + ", ".join(f"`{v}`" for v in _env_vars_hint(root)) + "\n"
    stack += "\n" + _evidence_block(sections, "STACK", "MANIFEST", "CODE METRICS")

    # STRUCTURE
    top = _top_level_map(root, skip)
    entries = _entry_points(root, sections, skip)
    struct = "## Top-level map\n\n" + (
        _table(top, ("Path", "Purpose", "Evidence")) if top else "[TODO]\n"
    )
    struct += "\n\n## Entry points\n\n"
    if entries:
        struct += "\n".join(f"- `{e}`" for e in entries[:40]) + "\n"
    else:
        struct += "- [TODO] No entry points detected\n"
    struct += "\n\n## Module boundaries (packages)\n\n"
    pkgs = _python_packages(root, skip)
    if pkgs:
        struct += _table(
            [(p, f"`{p}/`", "importable package") for p in pkgs],
            ("Package", "Path", "Notes"),
        )
    else:
        struct += "[TODO] No packages with `__init__.py` found.\n"
    struct += "\n\n## Naming\n\n"
    struct += "- Python modules: snake_case files; packages often TitleCase (stations) or snake_case (`spock_*`).\n"
    struct += "\n" + _evidence_block(sections, "DIRECTORY", "ENTRY", "TREE")

    # ARCHITECTURE
    arch = "## Layers\n\n" + _table(
        _architecture_layers(root, skip),
        ("Layer", "Components", "Evidence"),
    )
    arch += "\n\n## Data flow (ingest → Ask AI)\n\n"
    arch += (
        "1. Wiki Scan / watcher enqueues `onboarding` → extractor → `documents` + embeddings\n"
        "2. Ask AI / Deep Dive hybrid-searches `ship_computer.db`, packs context, calls chat LLM\n"
        "3. Settings / recipes in WarpCore drive launch `-c`, ports, and scan roots\n"
    )
    arch += "\n[ASK USER] Confirm intended production topology (single host vs dual-GPU).\n"
    arch += "\n" + _evidence_block(sections, "CODE METRICS", "MONOREPO")

    # CONVENTIONS
    conv = "## Observed conventions\n\n" + "\n".join(_conventions(root)) + "\n"
    conv += "\n## Error handling\n\n"
    conv += "- Skills return `SkillResult(ok, evidence, log_lines)` rather than raising into the queue loop.\n"
    conv += "- GUI long work uses wait cursor / busy `QProgressBar` (`spock_shell.busy_ui`).\n"
    conv += "\n" + _evidence_block(sections, "LINTING", "FORMAT")

    # INTEGRATIONS
    integ = "## External systems\n\n" + _table(
        _integrations(root),
        ("Integration", "Endpoint / artifact", "Evidence"),
    )
    integ += "\n\n## CI / containers (from scan)\n\n"
    cicd = _section(sections, "CI/CD")
    containers = _section(sections, "CONTAINER")
    integ += "```\n" + (cicd or "None detected.")[:1500] + "\n```\n\n"
    integ += "```\n" + (containers or "None detected.")[:1500] + "\n```\n"
    integ += "\n" + _evidence_block(sections, "SECURITY", "CI/CD")

    # TESTING
    fw, test_files = _pytest_layout(root)
    testing = f"## Framework\n\n- Detected: **{fw}**\n\n## Test files (sample)\n\n"
    if test_files:
        testing += "\n".join(f"- `{t}`" for t in test_files) + "\n"
    else:
        testing += "- [TODO] No `tests/test_*.py` found\n"
    testing += "\n## How to run\n\n```bash\npython -m pytest\n```\n"
    testing += "\n" + _evidence_block(sections, "PERFORMANCE", "TESTING")

    # CONCERNS
    concerns = "## Concerns (deterministic)\n\n" + "\n".join(_concerns(sections, skip)) + "\n"
    concerns += "\n## Filter note\n\n"
    concerns += (
        "TODOs under skipped trees (`data/`, `models/`, … from `.gitignore` / "
        "`scan.skip_dirs`) are omitted so llama.cpp blobs do not dominate.\n"
    )
    concerns += "\n" + _evidence_block(sections, "TODO", "CHURN", "LARGEST")

    return {
        "STACK.md": wrap("Technology Stack", stack),
        "STRUCTURE.md": wrap("Codebase Structure", struct),
        "ARCHITECTURE.md": wrap("Architecture", arch),
        "CONVENTIONS.md": wrap("Conventions", conv),
        "INTEGRATIONS.md": wrap("Integrations", integ),
        "TESTING.md": wrap("Testing", testing),
        "CONCERNS.md": wrap("Concerns", concerns),
    }
