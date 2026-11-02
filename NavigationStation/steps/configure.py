"""Configure step — the full tabbed Configure Spock AI form.

This used to be the Embedding Profile panel alone, with MCP and the llama.cpp
WebUI living behind a separate "Connect" step. Both are tabs of
``ConfigureAiPanel`` now, so Navigation shows one form instead of three doors to
the same settings.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from spock_shell.configure_ai import ConfigureAiPanel
from spock_shell.paths import SHIP_COMPUTER_DB


def build_configure_step(
    theme: Dict[str, str],
    config: Dict[str, Any],
    mcp_host: Any,
    on_profile_applied: Optional[Callable[[dict], None]] = None,
    on_rag_start: Optional[Callable[[], None]] = None,
    on_rag_stop: Optional[Callable[[], None]] = None,
    save_config: Optional[Callable[[], None]] = None,
) -> ConfigureAiPanel:
    return ConfigureAiPanel(
        theme,
        config,
        save_config or (lambda: None),
        db_path=SHIP_COMPUTER_DB,
        mcp_host=mcp_host,
        on_rag_start=on_rag_start,
        on_rag_stop=on_rag_stop,
        on_profile_applied=on_profile_applied,
    )
