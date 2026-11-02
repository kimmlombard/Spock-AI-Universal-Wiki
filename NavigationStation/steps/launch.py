"""Launch embed :8080 + chat :8081 step."""

from __future__ import annotations

from typing import Dict

from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from llama_server_manager import LlamaServerManager
from model_selector_panels import LaunchPanel, ModelSelectorState


def build_launch_step(
    theme: Dict[str, str],
    state: ModelSelectorState,
    manager: LlamaServerManager,
) -> QWidget:
    wrap = QWidget()
    lay = QVBoxLayout(wrap)
    tip = QLabel(
        "Launch an <b>embedding</b> GGUF on :8080 and an <b>instruct chat</b> GGUF on :8081. "
        "Do not use RAG :8090 here."
    )
    tip.setWordWrap(True)
    lay.addWidget(tip)
    panel = LaunchPanel(theme, state, manager)
    lay.addWidget(panel, 1)
    wrap._panel = panel  # type: ignore[attr-defined]
    return wrap
