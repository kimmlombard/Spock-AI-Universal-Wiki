"""Status step — health report in center."""

from __future__ import annotations

from typing import Any, Dict

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from spock_shell.status_panel import StatusConsole


def build_status_step(theme: Dict[str, str], config: Dict[str, Any]) -> QWidget:
    wrap = QWidget()
    lay = QVBoxLayout(wrap)
    lay.setContentsMargins(0, 0, 0, 0)
    console = StatusConsole(theme, config, as_window=False)
    lay.addWidget(console)
    wrap._console = console  # type: ignore[attr-defined]
    return wrap
