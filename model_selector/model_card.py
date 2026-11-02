"""Model card HTML helpers and ModelInfoPanel."""

from __future__ import annotations

import re
from typing import Optional

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    _HAS_WEBENGINE = True
except ImportError:
    QWebEngineView = None  # type: ignore
    _HAS_WEBENGINE = False

from .state import ModelSelectorState
from .widgets import _action_btn, _panel_stylesheet
from .workers import ModelCardWorker


def _strip_yaml_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    if len(parts) >= 3:
        return parts[2].lstrip("\n")
    return text


def _looks_like_html(text: str) -> bool:
    sample = text[:4000].lower()
    return any(
        tag in sample
        for tag in (
            "<div",
            "<p ",
            "<p>",
            "<h1",
            "<h2",
            "<img",
            "<a ",
            "<table",
            "<ul",
            "<ol",
            "<br",
            "<span",
            "<em>",
            "<strong",
        )
    )


def _looks_like_markdown(text: str) -> bool:
    """HF READMEs are usually Markdown (headers, links, pipe tables)."""
    sample = text[:12000]
    if re.search(r"(?m)^#{1,6}\s+\S", sample):
        return True
    if re.search(r"(?m)^\|.+\|\s*$", sample) and "---" in sample:
        return True
    if re.search(r"\[[^\]]+\]\([^)]+\)", sample):
        return True
    if re.search(r"(?m)^```", sample):
        return True
    return False


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _markdown_to_html(body: str) -> str:
    """Convert HF README markdown to HTML (tables, code fences, lists)."""
    try:
        import markdown as md

        return md.markdown(
            body,
            extensions=[
                "markdown.extensions.tables",
                "markdown.extensions.fenced_code",
                "markdown.extensions.nl2br",
                "markdown.extensions.sane_lists",
            ],
        )
    except Exception:
        return ""


def model_card_to_html(text: str, theme: dict) -> str:
    """Wrap HF README (HTML fragments and/or markdown) for QWebEngineView."""
    body = _strip_yaml_frontmatter(text or "")
    bg = theme.get("bg", "#1e1e1e")
    fg = theme.get("fg", "#ffffff")
    panel = theme.get("panel_bg", "#2d2d2d")
    accent = theme.get("accent", "#5C6BC0")

    is_md = _looks_like_markdown(body)
    is_html = _looks_like_html(body)
    kind = "text"
    if is_md or not is_html:
        converted = _markdown_to_html(body)
        if converted:
            content = converted
            kind = "markdown (rendered)"
        elif is_html:
            content = body
            kind = "HTML (rendered)"
        else:
            content = (
                f"<pre style='white-space:pre-wrap;font-family:Consolas,monospace;'>"
                f"{_escape_html(body)}</pre>"
            )
            kind = "text"
    else:
        content = body
        kind = "HTML (rendered)"

    # Stash kind on theme dict? Better return tuple — but callers expect str.
    # Encode kind via HTML comment for status, or change signature.
    # Keep simple: store last kind on function attribute.
    model_card_to_html.last_kind = kind  # type: ignore[attr-defined]

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  html, body {{
    margin: 0;
    padding: 16px;
    background: {bg};
    color: {fg};
    font-family: Segoe UI, system-ui, sans-serif;
    font-size: 14px;
    line-height: 1.55;
  }}
  a {{ color: {accent}; }}
  img {{ max-width: 100%; height: auto; vertical-align: middle; }}
  h1, h2, h3, h4 {{ color: #FF9800; }}
  code, pre {{
    background: {panel};
    border-radius: 4px;
    padding: 2px 6px;
  }}
  pre {{ padding: 12px; overflow-x: auto; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
  th, td {{ border: 1px solid #444; padding: 6px 8px; text-align: left; }}
  th {{ background: {panel}; }}
  blockquote {{
    border-left: 3px solid {accent};
    margin-left: 0;
    padding-left: 12px;
    color: #ccc;
  }}
  hr {{ border: none; border-top: 1px solid #444; margin: 16px 0; }}
</style>
</head>
<body>
{content}
</body>
</html>"""


model_card_to_html.last_kind = "text"  # type: ignore[attr-defined]


class ModelInfoPanel(QWidget):
    def __init__(self, theme: dict, state: ModelSelectorState, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.state = state
        self._worker: Optional[ModelCardWorker] = None
        self.web_view = None
        self.info_text = None
        self._build()
        self.apply_theme()
        self._refresh_from_state()

    def _build(self):
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.title = QLabel("MODEL INFO")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        self.title.setFont(title_font)
        self.title.setStyleSheet("color: #FF9800;")
        self.url_lbl = QLabel("")
        self.url_lbl.setStyleSheet("color: #5C6BC0;")
        self.url_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.url_lbl.mousePressEvent = self._open_url  # type: ignore
        header.addWidget(self.title)
        header.addWidget(self.url_lbl)
        header.addStretch()
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color: #aaa;")
        header.addWidget(self.status_lbl)
        layout.addLayout(header)

        self.stack = QStackedWidget()
        if _HAS_WEBENGINE and QWebEngineView is not None:
            self.web_view = QWebEngineView()
            self.stack.addWidget(self.web_view)
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setFont(QFont("Consolas", 10))
        self.stack.addWidget(self.info_text)
        layout.addWidget(self.stack)

    def _base_url(self) -> QUrl:
        mid = self.state.selected_hf_model_id
        if mid:
            return QUrl(f"https://huggingface.co/{mid}/resolve/main/")
        return QUrl("https://huggingface.co/")

    def _display_card(self, text: str):
        """Render model card as HTML (fixes raw-HTML bug from tkinter viewer)."""
        if self.web_view is not None:
            html = model_card_to_html(text, self.theme)
            self.web_view.setHtml(html, self._base_url())
            self.stack.setCurrentWidget(self.web_view)
            self.status_lbl.setText(getattr(model_card_to_html, "last_kind", "rendered"))
        else:
            # Fallback: try markdown → HTML for QTextEdit
            body = _strip_yaml_frontmatter(text or "")
            converted = _markdown_to_html(body)
            if converted:
                self.info_text.setHtml(converted)
                self.status_lbl.setText("markdown (QTextEdit)")
            else:
                self.info_text.setPlainText(text)
                self.status_lbl.setText("text (no WebEngine)")
            self.stack.setCurrentWidget(self.info_text)

    def _refresh_from_state(self):
        mid = self.state.selected_hf_model_id
        if mid:
            self.title.setText(f"MODEL: {mid}")
            self.url_lbl.setText(f"https://huggingface.co/{mid}")
        text = self.state.info_card_text or (
            "Select a model from the Models tab to view its details here."
        )
        self._display_card(text)

    def load_model(self, model_id: str):
        self.state.selected_hf_model_id = model_id
        self.title.setText(f"MODEL: {model_id}")
        self.url_lbl.setText(f"https://huggingface.co/{model_id}")
        self._display_card(f"<p>Loading model card for <b>{model_id}</b>...</p>")
        self.status_lbl.setText("loading...")
        self._worker = ModelCardWorker(model_id, self)
        self._worker.finished_ok.connect(self._on_card)
        self._worker.start()

    def _on_card(self, text: str):
        self.state.info_card_text = text
        self._display_card(text)

    def _open_url(self, _event):
        url = self.url_lbl.text().strip()
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def apply_theme(self):
        self.setStyleSheet(_panel_stylesheet(self.theme))
        # Re-render so wrapper colors match theme
        if self.state.info_card_text and self.web_view is not None:
            self._display_card(self.state.info_card_text)


# ── Launch ──────────────────────────────────────────────────────────────
