"""Compatibility shim — canonical panel is ``model_selector.embedding_panel``.

Stand-alone RAG adapter and older imports keep working via this re-export.
"""

from __future__ import annotations

from model_selector.embedding_panel import EmbeddingProfilePanel
from model_selector.widgets import _action_btn, _panel_stylesheet

__all__ = ["EmbeddingProfilePanel", "_action_btn", "_panel_stylesheet"]
