"""EngineeringDeck — Ask AI mini-app + maintenance (+ legacy facade)."""

from __future__ import annotations

__all__ = [
    "app",
    "ask_panel",
    "maintenance_app",
    "onboarding_wizard",
    "db_maintenance",
]

_LAZY = {
    "app": "EngineeringDeck.app",
    "ask_panel": "EngineeringDeck.ask_panel",
    "maintenance_app": "EngineeringDeck.maintenance_app",
    "onboarding_wizard": "onboarding_wizard",
    "db_maintenance": "db_maintenance",
}


def __getattr__(name: str):
    import importlib

    if name in _LAZY:
        return importlib.import_module(_LAZY[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
