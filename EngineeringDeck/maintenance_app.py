"""Spock-Engineering-Maintenance — Wiki / App maintenance + theme."""

from __future__ import annotations

from typing import Any, Dict, Sequence

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from spock_shell.brave_search import build_brave_search_panel
from spock_shell.markdown_home import build_markdown_home, reload_markdown_home
from spock_shell.paths import ensure_root_on_path
from spock_shell.widgets import SidePanel
from spock_shell.window import NavItem, SuiteShellWindow

HELPER_MD = "AIHelperDocuments/Spock-Engineering-Maintenance-HELPER.md"


class EngineeringMaintenanceWindow(SuiteShellWindow):
    app_title = "Spock-Engineering-Maintenance"
    app_subtitle = "Console maintenance tabs, Ship Computer DB Health, and Color Scheme."

    def __init__(self, parent=None):
        ensure_root_on_path()
        self._hub: QWidget | None = None
        self._health: QWidget | None = None
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
            ("1 Maintenance", self._show_maintenance),
            ("2 Ship Computer DB Health", self._show_db_health),
            ("-----", None),
            ("Exit", self.close),
        ]

    def build_right_dock(self, layout: QVBoxLayout) -> None:
        search = SidePanel("Search", self.theme)
        search.add_button("Google Search", self._show_brave_search)
        layout.addWidget(search)
        super().build_right_dock(layout)

    def _build_steps(self) -> None:
        from EngineeringDeck.ship_computer_health import ShipComputerHealthPanel
        from wiki_maintenance import WikiMaintenancePanel

        self._hub = WikiMaintenancePanel(self.theme, parent=self)
        self._health = ShipComputerHealthPanel(self.theme, parent=self)
        self._steps["brave"] = build_brave_search_panel(self.theme)
        self.stack.addWidget(self._hub)
        self.stack.addWidget(self._health)
        for w in self._steps.values():
            self.stack.addWidget(w)

    def _show_maintenance(self) -> None:
        if self._hub is not None:
            self.show_center(self._hub)

    def _show_db_health(self) -> None:
        if self._health is not None:
            refresh = getattr(self._health, "refresh_overview", None)
            if callable(refresh):
                refresh()
            self.show_center(self._health)

    def _show_brave_search(self) -> None:
        self.show_center(self._steps["brave"])
