"""ScienceStation — Wiki Agent mini-app (+ legacy facade)."""

from __future__ import annotations

__all__ = ["app", "chat_ai_helper", "deep_dive", "gemini_openai_models"]

_LAZY = {
    "app": "ScienceStation.app",
    "chat_ai_helper": "chat_ai_helper",
    "deep_dive": "deep_dive",
    "gemini_openai_models": "gemini_openai_models",
}


def __getattr__(name: str):
    import importlib

    if name in _LAZY:
        return importlib.import_module(_LAZY[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
