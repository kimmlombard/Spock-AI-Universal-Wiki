"""OS credential store for Spock API tokens (Windows Credential Manager, etc.).

Plaintext leftovers in Spock_Console are migrated on read, then replaced with
PLACEHOLDER. JSON export never writes secret values.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

SERVICE = "Spock-UIE-Wiki-KB-HUB"
PLACEHOLDER = "__keyring__"

# In-process backend for tests; None means try the keyring package.
_memory: Optional[Dict[Tuple[str, str], str]] = None


def use_memory_backend(store: Optional[Dict[Tuple[str, str], str]] = None) -> None:
    """Pin secrets to a dict (tests). Pass None to restore the OS keyring."""
    global _memory
    _memory = {} if store is None else store


def clear_memory_backend() -> None:
    global _memory
    _memory = None


def _backend_get(name: str) -> Optional[str]:
    if _memory is not None:
        return _memory.get((SERVICE, name))
    try:
        import keyring
    except Exception:
        return None
    try:
        return keyring.get_password(SERVICE, name)
    except Exception:
        return None


def _backend_set(name: str, value: str) -> bool:
    if _memory is not None:
        if value:
            _memory[(SERVICE, name)] = value
        else:
            _memory.pop((SERVICE, name), None)
        return True
    try:
        import keyring
    except Exception:
        return False
    try:
        if value:
            keyring.set_password(SERVICE, name, value)
        else:
            try:
                keyring.delete_password(SERVICE, name)
            except Exception:
                pass
        return True
    except Exception:
        return False


def put(name: str, value: str) -> bool:
    """Store a secret. Empty value deletes. Returns False if the OS store failed."""
    text = "" if value is None else str(value)
    if text == PLACEHOLDER:
        return True
    return _backend_set(name, text)


def get(name: str) -> str:
    raw = _backend_get(name)
    return raw if raw else ""


def is_placeholder(value: object) -> bool:
    return value == PLACEHOLDER
