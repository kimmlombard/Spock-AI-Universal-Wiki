"""Hardware scan step."""

from __future__ import annotations

from typing import Any, Dict

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from model_selector_panels import HardwareScanPanel, ModelSelectorState


def build_hardware_step(theme: Dict[str, str], state: ModelSelectorState) -> QWidget:
    wrap = QWidget()
    lay = QVBoxLayout(wrap)
    lay.setContentsMargins(0, 0, 0, 0)
    panel = HardwareScanPanel(theme, state)
    lay.addWidget(panel)
    wrap._panel = panel  # type: ignore[attr-defined]
    return wrap
