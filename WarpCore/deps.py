"""Dependency tier checks: pure logic (no PyQt) — shared by the GUI and tools.

Phase A installs only `requirements-ui.txt`, so ingest and crawl features can be
reached from the menu before their packages exist. These helpers turn that into
a readable "run Phase B" message instead of an import traceback.
"""

from __future__ import annotations

import importlib.util
from typing import Dict, Iterable, List

def _phase_b_hint() -> str:
    import os
    import sys

    if os.name == "nt":
        pip = r".venv\Scripts\python.exe -m pip install -r requirements-full.txt"
    else:
        pip = ".venv/bin/pip install -r requirements-full.txt"
    return (
        "Run Bringup step 2 (Phase B) to install the full dependency tier, or:\n"
        f"    {pip}"
    )


# Resolved at import so callers can still use PHASE_B_HINT as a string.
PHASE_B_HINT = _phase_b_hint()

# Import name -> distribution name, for everything above the UI tier that the
# ingest path imports unguarded.
INGEST_MODULES: Dict[str, str] = {
    "watchdog": "watchdog",
    "pymupdf": "PyMuPDF",
    "PIL": "Pillow",
    "bs4": "beautifulsoup4",
    "lxml": "lxml",
    "docx": "python-docx",
    "openpyxl": "openpyxl",
    "pandas": "pandas",
}

CRAWLER_MODULES: Dict[str, str] = {
    "bs4": "beautifulsoup4",
}


def missing_modules(modules: Dict[str, str]) -> List[str]:
    """Distribution names for any of `modules` that cannot be imported."""
    missing: List[str] = []
    for import_name, dist_name in modules.items():
        try:
            found = importlib.util.find_spec(import_name) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            missing.append(dist_name)
    return missing


def missing_ingest_deps() -> List[str]:
    """Packages Wiki Scan needs that Phase A does not install."""
    return missing_modules(INGEST_MODULES)


def missing_crawler_deps() -> List[str]:
    """Packages the UIEG crawler needs that Phase A does not install."""
    return missing_modules(CRAWLER_MODULES)


def missing_deps_message(missing: Iterable[str], feature: str) -> str:
    """Human-readable 'install the full tier' message for a missing-deps list."""
    names = ", ".join(missing)
    return f"{feature} needs packages that are not installed: {names}.\n\n{PHASE_B_HINT}"
