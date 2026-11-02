"""Repo paths shared by suite apps."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from WarpCore.service_endpoints import resolve_spock_root
except ImportError:  # pragma: no cover — early bootstrap before WarpCore on path
    def resolve_spock_root() -> Path:
        env = (os.environ.get("SPOCK_ROOT") or "").strip()
        if env:
            candidate = Path(env).expanduser().resolve()
            if (candidate / "WarpCore").is_dir():
                return candidate
        return Path(__file__).resolve().parent.parent


ROOT = resolve_spock_root()
SHIP_COMPUTER_DB = str(ROOT / "ship_computer.db")


def ensure_root_on_path() -> Path:
    root = str(ROOT)
    import sys

    if root not in sys.path:
        sys.path.insert(0, root)
    return ROOT
