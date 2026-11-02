"""Model selector UI package (split from model_selector_panels.py)."""

from __future__ import annotations

from .embedding_panel import EmbeddingProfilePanel
from .hardware_panel import HardwareScanPanel
from .launch_panel import LaunchPanel
from .model_card import ModelInfoPanel, model_card_to_html
from .models_panel import ModelsPanel
from .state import ModelSelectorState
from .status_window import LlmStatusWindow
from .widgets import _SortableTableItem, _action_btn, _panel_stylesheet
from .workers import (
    DownloadWorker,
    HardwareScanWorker,
    HfQueryWorker,
    LlamaConfigWorker,
    ModelCardWorker,
)

__all__ = [
    "ModelSelectorState",
    "HardwareScanPanel",
    "ModelsPanel",
    "ModelInfoPanel",
    "LaunchPanel",
    "EmbeddingProfilePanel",
    "LlmStatusWindow",
    "model_card_to_html",
    "HardwareScanWorker",
    "LlamaConfigWorker",
    "HfQueryWorker",
    "DownloadWorker",
    "ModelCardWorker",
    "_action_btn",
    "_panel_stylesheet",
    "_SortableTableItem",
]
