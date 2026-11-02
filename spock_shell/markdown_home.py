"""Center Home pane that renders a module HELPER markdown file."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Union

from PyQt6.QtWidgets import QLabel, QTextBrowser, QVBoxLayout, QWidget

from spock_shell.paths import ROOT

HELPER_DIR = "AIHelperDocuments"


def helper_md_path(filename: str) -> Path:
    """Resolve a HELPER doc under AIHelperDocuments/ (or absolute / repo-relative path)."""
    p = Path(filename)
    if p.is_absolute():
        return p
    if len(p.parts) > 1:
        return ROOT / p
    return ROOT / HELPER_DIR / p


def about_me_path(filename: str) -> Path:
    """Backward-compatible alias for ``helper_md_path``."""
    return helper_md_path(filename)


def build_markdown_home(
    theme: Dict[str, str],
    md_path: Union[str, Path],
    *,
    fallback_title: str = "Home",
    fallback_subtitle: str = "",
) -> QWidget:
    """QWidget with a scrollable markdown view of ``md_path`` (HELPER or abs)."""
    path = Path(md_path)
    if not path.is_absolute():
        path = helper_md_path(str(md_path))

    wrap = QWidget()
    lay = QVBoxLayout(wrap)
    lay.setContentsMargins(12, 12, 12, 12)

    browser = QTextBrowser()
    browser.setOpenExternalLinks(True)
    browser.setStyleSheet(
        f"""
        QTextBrowser {{
            background: {theme.get('panel_bg', theme.get('bg', '#1e1e1e'))};
            color: {theme.get('fg', '#e0e0e0')};
            border: 1px solid {theme.get('border', '#444')};
            border-radius: 6px;
            padding: 12px;
            font-size: 13px;
        }}
        """
    )

    if path.is_file():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            text = f"# Missing HELPER doc\n\nCould not read `{path}`: {e}"
        browser.setMarkdown(text)
        lay.addWidget(browser)
    else:
        title = QLabel(fallback_title)
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        sub = QLabel(
            fallback_subtitle
            or f"Create `{HELPER_DIR}/{path.name}` for this module’s Home page."
        )
        sub.setWordWrap(True)
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addStretch()

    wrap._md_path = path  # type: ignore[attr-defined]
    wrap._browser = browser if path.is_file() else None  # type: ignore[attr-defined]
    return wrap


def reload_markdown_home(widget: QWidget, theme: Optional[Dict[str, str]] = None) -> None:
    browser = getattr(widget, "_browser", None)
    path = getattr(widget, "_md_path", None)
    if browser is None or path is None or not Path(path).is_file():
        return
    try:
        browser.setMarkdown(Path(path).read_text(encoding="utf-8"))
    except OSError:
        pass
    if theme:
        browser.setStyleSheet(
            f"""
            QTextBrowser {{
                background: {theme.get('panel_bg', theme.get('bg', '#1e1e1e'))};
                color: {theme.get('fg', '#e0e0e0')};
                border: 1px solid {theme.get('border', '#444')};
                border-radius: 6px;
                padding: 12px;
                font-size: 13px;
            }}
            """
        )
