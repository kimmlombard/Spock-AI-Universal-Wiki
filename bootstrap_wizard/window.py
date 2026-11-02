"""Spock Bootstrap Control Wizard — Phase B suite shell."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from PyQt6.QtWidgets import QMessageBox, QVBoxLayout

from bootstrap_wizard.panel import BootstrapControlPanel
from spock_shell.brave_search import build_brave_search_panel
from spock_shell.markdown_home import build_markdown_home, reload_markdown_home
from spock_shell.paths import ROOT, ensure_root_on_path
from spock_shell.widgets import ModernButton, SidePanel
from spock_shell.window import NavItem, SuiteShellWindow

HELPER_MD = "AIHelperDocuments/Spock-Bootstrap-Wizard-HELPER.md"


class BootstrapWizardWindow(SuiteShellWindow):
    app_title = "Spock Bootstrap Control"
    app_subtitle = (
        "Phase B: live log, progress, and status for bootstrap.ps1 "
        "(after Python/venv/wizard deps)."
    )

    def __init__(self, install_root: Optional[Path] = None, parent=None):
        ensure_root_on_path()
        self.install_root = Path(install_root or ROOT).resolve()
        self._brave = None
        self._panel: Optional[BootstrapControlPanel] = None
        super().__init__(parent)

    def on_ready(self) -> None:
        self._disable_ship_status()
        self._panel = BootstrapControlPanel(self.install_root, self.theme)
        self.stack.addWidget(self._panel)
        self.show_center(self._panel)

    def build_home_widget(self):
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
        return [
            ("Home", self.show_home),
            ("1 Control Panel", self._show_panel),
            ("-----", None),
            ("Exit", self.close),
        ]

    def build_right_dock(self, layout: QVBoxLayout) -> None:
        search = SidePanel("Search", self.theme)
        search.add_button("Google Search", self._show_brave)
        layout.addWidget(search)
        super().build_right_dock(layout)

    def _build_ui(self) -> None:
        super()._build_ui()
        self._disable_ship_status()

    def _disable_ship_status(self) -> None:
        for btn in self.findChildren(ModernButton):
            if btn.text() == "Ship Status":
                btn.setEnabled(False)
                btn.setToolTip(
                    "Ship Status is inactive during bootstrap — use health check "
                    "on the Control Panel, or open a station after setup."
                )
                break

    def open_status(self) -> None:
        QMessageBox.information(
            self,
            "Ship Status inactive",
            "Use Control Panel → Run health check during bootstrap.\n"
            "After setup, open Ship Status from a suite station.",
        )

    def _show_panel(self) -> None:
        if self._panel is None:
            self._panel = BootstrapControlPanel(self.install_root, self.theme)
            self.stack.addWidget(self._panel)
        self.show_center(self._panel)

    def _show_brave(self) -> None:
        if self._brave is None:
            self._brave = build_brave_search_panel(self.theme)
            self.stack.addWidget(self._brave)
        self.show_center(self._brave)
