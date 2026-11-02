"""Auto-generate "Code Structure" pages for the MkDocs site.

Uses the Python `ast` module (no execution) to extract:
  - the internal module/import graph  -> structure/module-map.md
  - per-package symbol inventory + call graph -> structure/<pkg>/index.md
  - root-script inventory -> structure/root-scripts.md
  - entry points (main guards + launcher scripts) -> structure/entrypoints.md

Registered in mkdocs.yml under `plugins.gen-files.scripts`.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import mkdocs_gen_files

ROOT = Path(__file__).resolve().parent.parent

_INDEXED: frozenset[str] | None = None


def indexed_set() -> frozenset[str]:
    global _INDEXED
    if _INDEXED is None:
        _INDEXED = frozenset(indexed_files())
    return _INDEXED

PACKAGES = [
    "Orchestrator",
    "NavigationStation",
    "EngineeringDeck",
    "LongRangeSensors",
    "ScienceStation",
    "WarpCore",
    "spock_onboarding",
    "spock_bringup",
    "spock_bringup_menu",
    "spock_shell",
    "spock_rag_adapter",
    "spock_mcp_adapter",
    "spock_wiki_adapter",
    "spock_live_monitor",
    "spock_status",
    "spock_probe",
    "spock_progress_log",
    "model_selector",
    "bootstrap_wizard",
]

# Root-level .py files worth indexing (excludes tests / helpers).
ROOT_SCRIPTS_EXCLUDE = {
    "_warpcore_path.py",
    "test_embeddings.py",
    "llm_enhance.py",  # covered by docs pipeline docs
}


def indexed_root_scripts() -> list[str]:
    out = []
    for p in sorted(ROOT.glob("*.py")):
        if p.name in ROOT_SCRIPTS_EXCLUDE or p.name.startswith("test_"):
            continue
        out.append(p.name)
    return out


def package_files(pkg: str) -> list[str]:
    base = ROOT / pkg
    return sorted(
        str(p.relative_to(ROOT)).replace("\\", "/")
        for p in base.rglob("*.py")
        if "@" not in p.name
    )


def indexed_files() -> list[str]:
    """All .py files this indexer covers (packages + selected root scripts)."""
    files: list[str] = []
    for pkg in PACKAGES:
        files.extend(package_files(pkg))
    files.extend(indexed_root_scripts())
    return sorted(set(files))


# --------------------------------------------------------------------------- #
# AST extraction
# --------------------------------------------------------------------------- #
def read_source(rel: str) -> str | None:
    p = ROOT / rel
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        try:
            return p.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            return None


def has_main_guard(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            for sub in ast.walk(node.test):
                if isinstance(sub, ast.Constant) and sub.value == "__main__":
                    return True
    return False


def _args_sig(args: ast.arguments) -> list[str]:
    out: list[str] = []
    out.extend(a.arg for a in (args.posonlyargs or []))
    out.extend(a.arg for a in (args.args or []))
    if getattr(args, "vararg", None):
        out.append("*" + args.vararg.arg)
    out.extend(f"{a.arg}" for a in (args.kwonlyargs or []))
    if getattr(args, "kwarg", None):
        out.append("**" + args.kwarg.arg)
    return out


def _decorators(node: ast.AST) -> list[str]:
    return [ast.unparse(d) for d in getattr(node, "decorator_list", [])]


def _func_info(node: ast.AST) -> dict:
    return {
        "name": node.name,
        "args": _args_sig(node.args),
        "decorators": _decorators(node),
        "doc": ast.get_docstring(node),
        "line": getattr(node, "lineno", 0),
        "end": getattr(node, "end_lineno", getattr(node, "lineno", 0) or 0),
    }


def _class_info(node: ast.ClassDef) -> dict:
    methods = []
    nested = []
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.append(_func_info(item))
        elif isinstance(item, ast.ClassDef):
            nested.append(item.name)
    return {
        "name": node.name,
        "bases": [ast.unparse(b) for b in node.bases],
        "doc": ast.get_docstring(node),
        "line": getattr(node, "lineno", 0),
        "end": getattr(node, "end_lineno", getattr(node, "lineno", 0) or 0),
        "methods": methods,
        "nested": nested,
    }


def extract_symbols(rel: str) -> dict | None:
    """Return structural summary for one module (or None if unreadable)."""
    src = read_source(rel)
    if src is None:
        return None
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {"error": "SyntaxError", "rel": rel}
    imports: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imports.append(
                    {
                        "module": a.name,
                        "alias": a.asname,
                        "from": False,
                        "level": 0,
                        "line": getattr(node, "lineno", 0),
                    }
                )
        elif isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                imports.append(
                    {
                        "module": node.module,
                        "alias": a.asname,
                        "from": True,
                        "level": getattr(node, "level", 0),
                        "name": a.name,
                        "line": getattr(node, "lineno", 0),
                    }
                )
    classes: list[dict] = []
    functions: list[dict] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(_class_info(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("test_"):
                functions.append(_func_info(node))
    return {
        "rel": rel,
        "doc": ast.get_docstring(tree),
        "lines": (getattr(tree, "end_lineno", None) or src.count("\n")),
        "imports": imports,
        "classes": classes,
        "functions": functions,
        "main": has_main_guard(tree),
    }


def resolve_import(import_rec: dict, caller_rel: str) -> str | None:
    """Best-effort resolve an import record to an indexed project file.

    Returns a relative path ('WarpCore/db.py') or None if external/unknown.
    """
    level = int(import_rec.get("level") or 0)
    mod = str(import_rec.get("module") or "")
    caller_dir = Path(caller_rel).parent

    if level > 0:
        # Relative import: dots walk up from the caller's package.
        parts = [p for p in caller_dir.parts if p != ".."]
        up = level - 1
        segs = (list(parts)) if up == 0 else parts[: max(0, len(parts) - up)]
        mod = ".".join(segs + mod.split(".")) if not mod else ".".join(segs) + "." + mod
    return _resolve_module_path(mod)


def _resolve_module_path(mod: str) -> str | None:
    if not mod:
        return None
    parts = mod.split(".")
    # Try descending specificity: WarpCore.db -> WarpCore/db.py
    for cut in range(len(parts), 0, -1):
        cand = Path(*parts[:cut])
        rel = str(cand).replace("\\", "/")
        if (ROOT / (rel + ".py")).is_file():
            if rel in indexed_set():
                return rel + ".py"
            return None
    # A package dir
    cand = ROOT / parts[0]
    if cand.is_dir() and (cand / "__init__.py").is_file() and parts[0] in PACKAGES:
        return parts[0]
    # Root script referenced as bare name (e.g. `import main` or `main` module)
    if len(parts) == 1 and (ROOT / (parts[0] + ".py")).is_file():
        if parts[0] + ".py" in indexed_set():
            return parts[0] + ".py"
    return None


# --------------------------------------------------------------------------- #
# Call-graph analysis (module file -> module file)
# --------------------------------------------------------------------------- #
def module_call_edges(rel: str, tree: ast.AST | None) -> list[tuple[str, str]]:
    """Return (caller_rel, target_rel) edges derived from import-aliased calls.

    Covers patterns like `from WarpCore.db import ShipComputer` stored in a
    variable, `requests.get(...)` (external), and `db.ShipComputer()` where
    `db` is a `from X import ...  as db`. We focus on reachable attribute
    calls through imports.
    """
    if tree is None:
        return []
    alias_map: dict[str, tuple[str, str | None, int]] = {}

    def rec(node: ast.AST) -> None:
        if isinstance(node, ast.Import):
            for a in node.names:
                local = a.asname or a.name.split(".")[0]
                alias_map[local] = (a.name, None, 0)
        elif isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                local = a.asname or a.name
                alias_map[local] = (node.module, a.name, getattr(node, "level", 0))
        for child in ast.iter_child_nodes(node):
            rec(child)

    rec(tree)
    edges: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            owner, attr = f.value.id, f.attr
            if owner not in alias_map:
                continue
            mod, name, level = alias_map[owner]
            if level:
                continue  # relative-import alias call: resolve via caller path
            target = _resolve_module_path(mod)
            if target:
                edges.add((rel, target))
    return sorted(edges)


# --------------------------------------------------------------------------- #
# Import graph (module file -> module file)
# --------------------------------------------------------------------------- #
def module_import_edges(rel: str, imports: list[dict]) -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    indexed = indexed_set()
    for imp in imports:
        tgt = resolve_import(imp, rel)
        if tgt and tgt != rel and tgt in indexed:
            edges.add((rel, tgt))
    return edges


def package_import_graph(pkg: str) -> dict[str, set[str]]:
    """{module_rel: set(target_rel)} restricted to files inside the package."""
    files = package_files(pkg)
    all_files = indexed_set()
    graph: dict[str, set[str]] = {}
    for rel in files:
        sym = read_source(rel)
        if not sym:
            continue
        try:
            tree = ast.parse(sym)
        except SyntaxError:
            graph[rel] = set()
            continue
        local = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    tgt = _resolve_module_path(a.name)
                    if tgt and tgt != rel and tgt in all_files and tgt.startswith(pkg + "/"):
                        local.add(tgt)
            elif isinstance(n, ast.ImportFrom) and n.module:
                tgt = resolve_import(
                    {"module": n.module, "level": getattr(n, "level", 0)}, rel
                )
                if tgt and tgt != rel and tgt in all_files and tgt.startswith(pkg + "/"):
                    local.add(tgt)
        graph[rel] = local
    return graph


def package_call_graph(pkg: str, all_syms: dict[str, dict]) -> dict[str, set[str]]:
    """{module_rel: set(target_rel)} for attribute-call edges inside the package."""
    all_files = indexed_set()
    graph: dict[str, set[str]] = {}
    for rel, sym in all_syms.items():
        if not rel.startswith(pkg + "/"):
            continue
        graph[rel] = set()
        for _caller, tgt in module_call_edges(rel, _tree_of(sym)):
            if tgt.startswith(pkg + "/") and tgt != rel:
                graph[rel].add(tgt)
    return graph


def _tree_of(sym: dict) -> ast.AST | None:
    src = read_source(sym.get("rel", ""))
    if not src:
        return None
    try:
        return ast.parse(src)
    except SyntaxError:
        return None


# --------------------------------------------------------------------------- #
# Mermaid helpers
# --------------------------------------------------------------------------- #
def _ids(items: list[str]) -> dict[str, str]:
    return {rel: f"m{i}" for i, rel in enumerate(items)}


def mermaid_flowchart(edges: list[tuple[str, str]], nodes: list[str], title: str) -> str:
    """Render a flowchart LR. Falls back to a bullet list if too large."""
    ids = _ids(nodes)
    lines = [
        "```mermaid",
        "---",
        f"title: {json.dumps(title)}",
        "---",
        "flowchart LR",
    ]
    for rel in nodes:
        label = rel.replace('"', "'")
        lines.append(f"    {ids[rel]}[\"{label}\"]")
    edges = [(a, b) for a, b in edges if a in ids and b in ids]
    if len(edges) > 160:
        lines = ["```mermaid", "flowchart LR", "    A[Diagram omitted - too many edges]"]
        lines.append("```")
        return "\n".join(lines)
    for a, b in sorted(set(edges)):
        lines.append(f"    {ids[a]} --> {ids[b]}")
    lines.append("```")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Page builders
# --------------------------------------------------------------------------- #
def build_module_map() -> str:
    files = indexed_files()
    all_edges: set[tuple[str, str]] = set()
    for rel in files:
        sym = extract_symbols(rel)
        if not sym or "error" in sym:
            continue
        all_edges |= module_import_edges(rel, sym["imports"])
    only = sorted({a for a, _ in all_edges} | {b for _, b in all_edges})
    all_nodes = [f for f in files if f in only or "main" in f or f.endswith("__main__.py")]

    out = [
        "# Module Map",
        "",
        "Import relationships between every indexed module. Edges point from the "
        "importing module to the module it imports. Only **project-internal** edges "
        "are shown; stdlib / third-party imports are skipped.",
        "",
        f"**Indexed:** {len(files)} files · **Internal imports:** {len(all_edges)}",
        "",
    ]
    out.append(mermaid_flowchart(sorted(all_edges), all_nodes, "Project module imports"))
    out.append("")
    out.append("## Import Details (text)")
    out.append("")
    out.append("| Module | Imports (project-internal) |")
    out.append("|--------|----------------------------|")
    for rel in sorted(files):
        sym = extract_symbols(rel)
        if not sym:
            continue
        targets = sorted(t.replace("\\", "/") for _, t in module_import_edges(rel, sym.get("imports", [])))
        out.append(f"| `{rel}` | {', '.join(f'`{t}`' for t in targets) if targets else '_none_'} |")
    return "\n".join(out)


def build_entrypoints(all_syms: dict[str, dict]) -> str:
    launchers: dict[str, list[str]] = {}
    pat_py_any = re.compile(r"([A-Za-z_][\w.-]*\.py)", re.IGNORECASE)
    pat_m = re.compile(r"(?:-m\s+)([A-Za-z_][\w.-]*)", re.IGNORECASE)

    def _scan(text: str, launcher: str) -> None:
        text = re.sub(r"%~(?:dp0|p0|d0)", "", text)
        for line in text.splitlines():
            if "python" not in line.lower():
                continue
            for m in pat_py_any.finditer(line):
                launchers.setdefault(m.group(1), []).append(launcher)
            for m in pat_m.finditer(line):
                launchers.setdefault(m.group(1) + "/__main__.py", []).append(launcher)

    for script in sorted(ROOT.glob("*.bat")):
        try:
            text = script.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        _scan(text, script.name)
    for script in sorted(ROOT.glob("*.ps1")):
        try:
            text = script.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        _scan(text, script.name)

    rows = []
    for rel in sorted(all_syms):
        sym = all_syms[rel]
        if not sym:
            continue
        kind = "package module" if "/" in rel else "root script"
        launch = launchers.get(rel, [])
        rows.append((rel, kind, sym.get("main", False), launch))

    out = [
        "# Entry Points",
        "",
        "Every module with a `__main__` guard, and every launcher script that "
        "invokes one of the indexed Python files.",
        "",
    ]
    launch_edges = []
    launch_nodes = set()
    for rel, launch in ((r, l) for r, _k, _m, l in rows):
        for l in launch:
            launch_edges.append((l, rel))
            launch_nodes.add(l)
            launch_nodes.add(rel)
    out.append(mermaid_flowchart(sorted(launch_edges), sorted(launch_nodes), "Launcher -> module"))
    out.append("")
    out.append("| Module | Kind | `__main__` guard | Launchers |")
    out.append("|--------|------|------------------|-----------|")
    for rel, kind, main, launch in rows:
        out.append(
            f"| `{rel}` | {kind} | {'yes' if main else 'no'} | {', '.join(f'`{l}`' for l in launch) if launch else '_none found_'} |"
        )
    return "\n".join(out)


def build_root_scripts() -> str:
    out = [
        "# Root Scripts",
        "",
        "Inventory of the entry-point style Python scripts at the repository root. "
        "Each is described by its documentation and structural summary extracted "
        "from source (not executed).",
        "",
        "| Script | Lines | Classes | Functions | Main guard | Purpose |",
        "|--------|-------|---------|-----------|------------|---------|",
    ]
    for rel in indexed_root_scripts():
        sym = extract_symbols(rel)
        if not sym:
            continue
        doc = (sym.get("doc") or "").strip().splitlines()
        purpose = (doc[0] if doc else "")[:90] or "_no module docstring_"
        out.append(
            f"| `{rel}` | {sym['lines']} | {len(sym['classes'])} | {len(sym['functions'])} | "
            f"{'yes' if sym.get('main') else 'no'} | {purpose} |"
        )
    return "\n".join(out)


def build_package_page(pkg: str) -> str:
    files = package_files(pkg)
    syms = {rel: extract_symbols(rel) for rel in files}
    import_g = package_import_graph(pkg)
    call_g = package_call_graph(pkg, syms)

    n_classes = sum(len(s.get("classes", [])) for s in syms.values() if s)
    n_funcs = sum(len(s.get("functions", [])) for s in syms.values() if s)
    n_methods = sum(
        len(c.get("methods", []))
        for s in syms.values()
        if s
        for c in s.get("classes", [])
    )
    n_lines = sum(s.get("lines", 0) for s in syms.values() if s)

    edges = []
    for rel in files:
        for t in sorted(set(import_g.get(rel, set())) | set(call_g.get(rel, set()))):
            edges.append((rel, t))
    rendered = mermaid_flowchart(sorted(set(edges)), files, f"{pkg} module relationships")

    out = [
        f"# Structure: {pkg}",
        "",
        f"**Files:** {len(files)} · **Lines:** {n_lines:,} · **Classes:** {n_classes} · "
        f"**Functions:** {n_funcs} · **Methods:** {n_methods}",
        "",
        "Solid edges = module-level import/call relationships (determined statically "
        "from source; only relationships *within this package* are drawn).",
        "",
        rendered,
        "",
        "## Modules",
        "",
    ]
    for rel in files:
        sym = syms[rel]
        if not sym:
            out.append(f"### `{rel}`")
            out.append("", "_unreadable / syntax error_", "")
            continue
        doc = (sym.get("doc") or "").strip() or "_no module docstring_"
        out.append(f"### `{rel}`")
        out.append("")
        out.append(f"*{escape_md(doc[:400])}*")
        out.append("")
        if sym.get("main"):
            out.append("> Contains a `__main__` guard (run directly).")
            out.append("")
        imp_text = []
        for imp in sym["imports"]:
            kind = "from" if imp.get("from") else "import"
            name = f"{imp['module']} as {imp['alias']}" if imp.get("alias") else imp["module"]
            if kind == "from" and not imp.get("alias"):
                name = f"{imp['module']} import {imp.get('name')}"
            imp_text.append(f"`{kind} {name}`")
        if imp_text:
            out.append(f"**Imports:** {', '.join(imp_text)}")
            out.append("")
        if sym["classes"]:
            out.append("**Classes**")
            out.append("")
            for c in sym["classes"]:
                base = f"({', '.join(c['bases'])})" if c["bases"] else ""
                out.append(f"- **`{c['name']}{base}`** — lines {c['line']}-{c['end']}")
                cdoc = (c["doc"] or "").strip().splitlines()
                if cdoc:
                    out.append(f"  - *{escape_md(cdoc[0][:200])}*")
                for m in c["methods"]:
                    if m["name"].startswith("_"):
                        continue
                    out.append(
                        f"  - `{m['name']}({', '.join(m['args'])})`"
                        f"{' *' + escape_md((m['doc'] or '').splitlines()[0][:160]) + '*' if (m['doc'] or '').strip() else ''}"
                    )
        if sym["functions"]:
            out.append("")
            out.append("**Functions**")
            out.append("")
            for f in sym["functions"]:
                if f["name"].startswith("_"):
                    continue
                out.append(
                    f"- **`{f['name']}({', '.join(f['args'])})`** — lines {f['line']}-{f['end']}"
                )
                fdoc = (f["doc"] or "").strip().splitlines()
                if fdoc:
                    out.append(f"  - *{escape_md(fdoc[0][:200])}*")
        out.append("")
    return "\n".join(out)


def escape_md(text: str) -> str:
    return text.replace("|", "\\|")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    files = indexed_files()
    all_syms = {rel: extract_symbols(rel) for rel in files}

    index_links = []
    for pkg in PACKAGES:
        link = f"[{pkg}]({pkg}/index.md)"
        index_links.append(link)
    index = [
        "# Code Structure",
        "",
        "Machine-generated pages describing the *internal construct* of the codebase: "
        "module dependencies, call relationships, function/class inventory, entry "
        "points, and the live database schema. Generated from `ast` parsing and "
        "SQLite introspection — nothing in this section executes application code.",
        "",
        "## Pages",
        "",
        "- [Module Map](module-map.md) — internal import graph",
        "- [Entry Points](entrypoints.md) — launch scripts and `__main__` guards",
        "- [Root Scripts](root-scripts.md) — inventory of top-level scripts",
        "- [Database Schema](database-schema.md) — live tables, columns, foreign keys",
        "- [Logic Deep Dives](logic/index.md) — per-module walkthroughs",
        "",
        "## Packages",
        "",
        " - ".join(index_links) if index_links else "",
        "",
        "## Totals",
        "",
        f"- **Indexed files:** {len(files)}",
        f"- **Classes:** {sum(len(s.get('classes', [])) for s in all_syms.values() if s)}",
        f"- **Functions:** {sum(len(s.get('functions', [])) for s in all_syms.values() if s)}",
        f"- **Methods:** {sum(len(c.get('methods', [])) for s in all_syms.values() if s for c in s.get('classes', []))}",
        f"- **Lines inspected:** {sum(s.get('lines', 0) for s in all_syms.values() if s):,}",
    ]
    with mkdocs_gen_files.open("structure/index.md", "w") as fd:
        fd.write("\n".join(index))

    with mkdocs_gen_files.open("structure/module-map.md", "w") as fd:
        fd.write(build_module_map())
    with mkdocs_gen_files.open("structure/entrypoints.md", "w") as fd:
        fd.write(build_entrypoints(all_syms))
    with mkdocs_gen_files.open("structure/root-scripts.md", "w") as fd:
        fd.write(build_root_scripts())
    for pkg in PACKAGES:
        with mkdocs_gen_files.open(f"structure/{pkg}/index.md", "w") as fd:
            fd.write(build_package_page(pkg))


if __name__ in ("__main__", "<run_path>"):  # direct run, or mkdocs-gen-files runpy
    main()