"""Run scan + write the seven docs/codebase markdown files (deterministic fill)."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from spock_codebase_knowledge.filters import load_skip_dir_names
from spock_codebase_knowledge.populate import build_docs, split_scan_sections

PACKAGE_ROOT = Path(__file__).resolve().parent
SCAN_SCRIPT = PACKAGE_ROOT / "scripts" / "scan.py"

DOC_NAMES = (
    "STACK.md",
    "STRUCTURE.md",
    "ARCHITECTURE.md",
    "CONVENTIONS.md",
    "INTEGRATIONS.md",
    "TESTING.md",
    "CONCERNS.md",
)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_scan(root: Path, output: Optional[Path] = None) -> Path:
    """Execute vendored scan.py against ``root`` with Spock skip filters."""
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Root is not a directory: {root}")
    if not SCAN_SCRIPT.is_file():
        raise FileNotFoundError(f"Missing scan script: {SCAN_SCRIPT}")
    out = (output or (root / "docs" / "codebase" / ".codebase-scan.txt")).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    skip = load_skip_dir_names(root)
    env = os.environ.copy()
    env["SPOCK_CODEBASE_SKIP_DIRS"] = os.pathsep.join(sorted(skip))
    env["PYTHONUNBUFFERED"] = "1"

    cmd = [sys.executable, str(SCAN_SCRIPT), "--output", str(out)]
    result = subprocess.run(
        cmd,
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if result.returncode != 0 and not out.is_file():
        err = (result.stderr or result.stdout or "scan failed").strip()
        raise RuntimeError(f"scan.py failed ({result.returncode}): {err[:500]}")
    if not out.is_file():
        out.write_text(result.stdout or "", encoding="utf-8")
    return out


def write_docs_from_scan(
    root: Path,
    scan_path: Path,
    *,
    output_rel: str = "docs/codebase",
    focus: str = "",
) -> List[Path]:
    """Fill and write the seven docs under ``root / output_rel``."""
    root = root.resolve()
    out_dir = (root / (output_rel or "docs/codebase")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    scan_text = scan_path.read_text(encoding="utf-8", errors="replace")
    sections = split_scan_sections(scan_text)
    docs = build_docs(
        root=root,
        scan_path=scan_path,
        sections=sections,
        focus=(focus or "").strip(),
        generated_at=_utc_stamp(),
    )
    written: List[Path] = []
    for name in DOC_NAMES:
        content = docs.get(name)
        if not content:
            raise RuntimeError(f"populate.py did not produce {name}")
        dest = out_dir / name
        dest.write_text(content, encoding="utf-8")
        written.append(dest)
    scan_dest = out_dir / ".codebase-scan.txt"
    if scan_path.resolve() != scan_dest.resolve():
        scan_dest.write_text(scan_text, encoding="utf-8")
    return written


def acquire_codebase_knowledge(
    root_path: str,
    *,
    focus: str = "",
    output_rel: str = "docs/codebase",
) -> Dict[str, Any]:
    """Scan (filtered) → deterministic docs. Returns paths + summary."""
    root = Path(root_path).expanduser().resolve()
    out_dir = root / (output_rel or "docs/codebase")
    scan_path = run_scan(root, output=out_dir / ".codebase-scan.txt")
    written = write_docs_from_scan(
        root, scan_path, output_rel=output_rel or "docs/codebase", focus=focus
    )
    return {
        "ok": True,
        "root": str(root),
        "scan_path": str(scan_path),
        "output_dir": str(out_dir.resolve()),
        "docs": [str(p) for p in written],
        "focus": (focus or "").strip(),
        "skip_dirs": sorted(load_skip_dir_names(root)),
    }
