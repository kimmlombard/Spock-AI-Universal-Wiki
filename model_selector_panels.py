"""Compatibility facade — implementation lives in the ``model_selector`` package.

Prefer: ``from model_selector import ModelsPanel, ModelSelectorState, ...``
This module re-exports the same public API so existing imports keep working.
"""

from __future__ import annotations

from model_selector import (  # noqa: F401
    DownloadWorker,
    EmbeddingProfilePanel,
    HardwareScanPanel,
    HardwareScanWorker,
    HfQueryWorker,
    LaunchPanel,
    LlamaConfigWorker,
    LlmStatusWindow,
    ModelCardWorker,
    ModelInfoPanel,
    ModelSelectorState,
    ModelsPanel,
    _SortableTableItem,
    _action_btn,
    _panel_stylesheet,
    model_card_to_html,
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
