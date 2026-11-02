"""LongRangeSensors — Search + Save (UIEG) and Run Search.

Modules live in this package. Imports are lazy so `import LongRangeSensors`
stays cheap until a module is actually touched.
"""

from __future__ import annotations

__all__ = [
    "app",
    "external_search_panel",
    "web_search_clients",
    "uieg_capture_panel",
    "uieg_crawler",
    "uieg_database",
    "uieg_import",
    "uieg_paths",
    "uieg_preview",
    "uieg_promote",
    "uieg_repo_fetch",
]

_LAZY = {
    "app": "LongRangeSensors.app",
    "external_search_panel": "LongRangeSensors.external_search_panel",
    "web_search_clients": "LongRangeSensors.web_search_clients",
    "uieg_capture_panel": "LongRangeSensors.uieg_capture_panel",
    "uieg_crawler": "LongRangeSensors.uieg_crawler",
    "uieg_database": "LongRangeSensors.uieg_database",
    "uieg_import": "LongRangeSensors.uieg_import",
    "uieg_paths": "LongRangeSensors.uieg_paths",
    "uieg_preview": "LongRangeSensors.uieg_preview",
    "uieg_promote": "LongRangeSensors.uieg_promote",
    "uieg_repo_fetch": "LongRangeSensors.uieg_repo_fetch",
}


def __getattr__(name: str):
    import importlib

    if name in _LAZY:
        return importlib.import_module(_LAZY[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
