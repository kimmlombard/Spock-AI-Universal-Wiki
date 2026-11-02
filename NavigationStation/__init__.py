"""Navigation Station — browser Spock Ask AI (RAG :8090 / templates/webui)."""

from __future__ import annotations

__all__ = [
    "app",
    "model_selector_core",
    "model_selector_panels",
    "spock_scanner_core",
    "llama_server_manager",
    "wiki_agent",
    "wiki_agent_status",
]

_LAZY = {
    "app": "NavigationStation.app",
    "model_selector_core": "model_selector_core",
    "model_selector_panels": "model_selector_panels",
    "spock_scanner_core": "spock_scanner_core",
    "llama_server_manager": "llama_server_manager",
    "wiki_agent": "wiki_agent",
    "wiki_agent_status": "wiki_agent_status",
}


def __getattr__(name: str):
    import importlib

    if name in _LAZY:
        return importlib.import_module(_LAZY[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
