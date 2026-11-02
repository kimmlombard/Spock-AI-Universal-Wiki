"""Skip filters for codebase acquire: .gitignore + scan_config skip_dirs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import FrozenSet, Iterable, List, Optional, Set

# Always noisy for Spock / local LLM workspaces even if config is thin.
_EXTRA_SKIP = frozenset(
    {
        ".venv",
        "venv",
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
        "models",
        "data",
        "logs",
        "backups",
        "tools",
        "site",
        "captured_files",
        "promoted_research",
        "config_archive",
        "quarantine",
        "research_raw",
        "dist",
        "build",
        "out",
        "vendor",
        "coverage",
        "site-packages",
        "Pods",
        "target",
        "obj",
        ".cache",
        ".turbo",
        ".next",
        ".nuxt",
    }
)


def _dir_names_from_gitignore(root: Path) -> Set[str]:
    """Collect directory basenames to skip from ``.gitignore`` lines."""
    path = root / ".gitignore"
    names: Set[str] = set()
    if not path.is_file():
        return names
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return names
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        if "*" in line or "?" in line or line.startswith("%"):
            continue
        line = line.lstrip("/").replace("\\", "/")
        explicit_dir = line.endswith("/")
        line = line.rstrip("/")
        if not line:
            continue
        parts = [p for p in line.split("/") if p and p != "**"]
        if not parts:
            continue
        name = parts[-1]
        if not name or name.startswith("%"):
            continue
        if explicit_dir or "/" in line:
            names.add(name)
            continue
        # Bare token: directory-like only (.venv / models), not files (.env, *.md)
        if name.startswith("."):
            # Single-dot cache/env dirs: .venv, .git, .pytest_cache
            if name.count(".") == 1 or name in {
                ".venv",
                ".git",
                ".github",
                ".idea",
                ".vscode",
                ".pytest_cache",
                ".mypy_cache",
                ".ruff_cache",
                ".cache",
                ".tox",
                ".next",
                ".nuxt",
            }:
                # Reject clear secret *files*
                if name in {".env", ".HF_TOKEN", ".DS_Store"}:
                    continue
                names.add(name)
            continue
        if "." not in name:
            names.add(name)
    return names


def _skip_dirs_from_scan_config(root: Path) -> List[str]:
    """Load skip_dirs from ship_computer settings, then scan_config.json, then defaults."""
    # 1) Spock Console DB (avoid importing spock_shell — it pulls PyQt6)
    db_candidates = [
        root / "ship_computer.db",
        Path(__file__).resolve().parents[1] / "ship_computer.db",
    ]
    for db in db_candidates:
        if not db.is_file():
            continue
        try:
            from WarpCore.settings_store import load_scan_config

            cfg = load_scan_config(str(db))
            dirs = cfg.get("skip_dirs") or []
            if isinstance(dirs, list) and dirs:
                return [str(d) for d in dirs if d]
        except Exception:
            continue
    # 2) Root scan_config.json (may be gitignored but often present locally)
    for candidate in (root / "scan_config.json", Path.cwd() / "scan_config.json"):
        if not candidate.is_file():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
            dirs = data.get("skip_dirs") or []
            if isinstance(dirs, list) and dirs:
                return [str(d) for d in dirs if d]
        except Exception:
            continue
    # 3) Built-in Spock defaults
    try:
        from WarpCore.config_defaults import DEFAULT_SCAN_CONFIG

        dirs = DEFAULT_SCAN_CONFIG.get("skip_dirs") or []
        return [str(d) for d in dirs if d]
    except Exception:
        return []


def load_skip_dir_names(root: Path) -> FrozenSet[str]:
    """Union of scan_config skip_dirs, .gitignore directory names, and extras."""
    root = root.resolve()
    names: Set[str] = set(_EXTRA_SKIP)
    names.update(_skip_dirs_from_scan_config(root))
    names.update(_dir_names_from_gitignore(root))
    # Normalize: strip trailing slashes / empties
    clean = {n.strip().strip("/\\") for n in names if n and str(n).strip()}
    return frozenset(clean)


def path_is_skipped(path: Path, skip_dirs: Iterable[str], *, root: Optional[Path] = None) -> bool:
    """True if any path component is in skip_dirs."""
    skip = {str(s) for s in skip_dirs}
    try:
        parts = path.resolve().parts if path.is_absolute() else path.parts
    except OSError:
        parts = path.parts
    if root is not None:
        try:
            parts = path.resolve().relative_to(root.resolve()).parts
        except Exception:
            pass
    return any(part in skip for part in parts)
