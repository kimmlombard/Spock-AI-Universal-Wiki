"""Spock-UIEG-KnowledgeBase — Repo fetch / Website crawl / Promote."""

from __future__ import annotations

from typing import Any, Dict, Sequence

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from LongRangeSensors.uieg_capture_panel import UiegCapturePanel
from LongRangeSensors.uieg_status import build_uieg_status_panel
from spock_shell.brave_search import build_brave_search_panel
from spock_shell.markdown_home import build_markdown_home, reload_markdown_home
from spock_shell.paths import ensure_root_on_path
from spock_shell.widgets import SidePanel
from spock_shell.window import NavItem, SuiteShellWindow

HELPER_MD = "AIHelperDocuments/Spock-UIEG-HELPER.md"


class UiegKnowledgeBaseWindow(SuiteShellWindow):
    app_title = "Spock-UIEG-KnowledgeBase"
    app_subtitle = (
        "External capture (UIEG): GitHub repo fetch, website crawl, promote to ship's computer."
    )

    def __init__(self, parent=None):
        ensure_root_on_path()
        self._steps: Dict[str, Any] = {}
        super().__init__(parent)

    def on_ready(self) -> None:
        self._build_steps()
        self.show_home()

    def build_home_widget(self) -> QWidget:
        return build_markdown_home(
            self.theme,
            HELPER_MD,
            fallback_title=self.app_title,
            fallback_subtitle=self.app_subtitle,
        )

    def show_home(self) -> None:
        reload_markdown_home(self._home, self.theme)
        super().show_home()

    def nav_steps(self) -> Sequence[NavItem]:
        # AI Helper / Ship Status / About / Google Search live on the right Tools dock.
        return [
            ("Home", self.show_home),
            ("1 Repo / GitHub Fetch", lambda: self.show_center(self._steps["repo"])),
            ("2 Crawl — Website / Import", lambda: self.show_center(self._steps["crawl"])),
            ("3 UIEG DB Status", self._show_status),
            ("-----", None),
            ("Exit", self.close),
        ]

    def build_right_dock(self, layout: QVBoxLayout) -> None:
        search = SidePanel("Search", self.theme)
        search.add_button("Google Search", self._show_brave_search)
        layout.addWidget(search)
        super().build_right_dock(layout)

    def _build_steps(self) -> None:
        uieg = self.config.get("uieg") or {}
        self._steps["repo"] = UiegCapturePanel(self.theme, uieg_cfg=uieg, mode="repo")
        self._steps["crawl"] = UiegCapturePanel(self.theme, uieg_cfg=uieg, mode="crawl")
        self._steps["status"] = build_uieg_status_panel(
            self.theme,
            uieg_cfg=uieg,
            on_db_changed=self._refresh_capture_panels,
        )
        self._steps["brave"] = build_brave_search_panel(self.theme)
        for w in self._steps.values():
            self.stack.addWidget(w)

    def _show_status(self) -> None:
        panel = self._steps["status"]
        refresh = getattr(panel, "refresh", None)
        if callable(refresh):
            refresh()
        self.show_center(panel)

    def _refresh_capture_panels(self) -> None:
        for key in ("repo", "crawl"):
            panel = self._steps.get(key)
            refresh = getattr(panel, "refresh_db_view", None)
            if callable(refresh):
                refresh()

    def _show_brave_search(self) -> None:
        self.show_center(self._steps["brave"])
