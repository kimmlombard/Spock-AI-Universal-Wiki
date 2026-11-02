"""Install root paths for Embedding / RAG adapter."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHIP_COMPUTER_DB = str(ROOT / "ship_computer.db")
RAG_SCRIPT = ROOT / "_start_rag_api.py"


def ensure_root_on_path() -> Path:
    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    return ROOT
