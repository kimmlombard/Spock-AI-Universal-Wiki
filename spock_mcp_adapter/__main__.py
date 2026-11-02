"""Stand-alone MCP Adapter window (PyQt6)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMainWindow, QScrollArea, QVBoxLayout, QWidget

from WarpCore import settings_store
from WarpCore.config_defaults import merge_mcp_settings
from WarpCore.theme import apply_theme_to, theme_by_name
from spock_mcp_adapter.mcp_host import McpAdapterHost
from spock_mcp_adapter.mcp_panel import McpControlPanel
from spock_mcp_adapter.paths import ROOT as DEFAULT_ROOT


class McpAdapterWindow(QMainWindow):
    def __init__(self, root: Optional[Path] = None) -> None:
        super().__init__()
        self.root = (root or DEFAULT_ROOT).resolve()
        self.db_path = self.root / "ship_computer.db"
        self.config = settings_store.load_app_config(str(self.db_path))
        theme_name = str(self.config.get("theme") or "dark")
        self.theme = theme_by_name(theme_name)

        self.setWindowTitle("MCP Adapter")
        self.resize(820, 720)

        self.mcp_host = McpAdapterHost(
            self.config,
            self._save_config,
            parent=self,
        )

        panel = McpControlPanel(
            self.theme,
            script_path=self.mcp_host.script_path(),
            python_exe=self.mcp_host.python_exe(),
            start_adapter=self.mcp_host.start_adapter,
            stop_adapter=self.mcp_host.stop_adapter,
            find_adapter=self.mcp_host.find_adapter,
            adapter_status=self.mcp_host.adapter_status_text,
            adapter_pids=self.mcp_host.running_pids,
            health_context=self.mcp_host.health_context,
            ensure_http_adapter=self.mcp_host.ensure_http_adapter_async,
            settings=merge_mcp_settings(self.config.get("mcp")),
        )
        panel.settings_changed.connect(self.mcp_host.on_settings_changed)
        self.mcp_host.panel = panel

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(12, 12, 12, 12)
        inner_lay.addWidget(panel)
        scroll.setWidget(inner)
        self.setCentralWidget(scroll)

        apply_theme_to(self, self.theme, scope="main")

        mcp = merge_mcp_settings(self.config.get("mcp"))
        if mcp.get("adapter_autostart"):
            QTimer.singleShot(300, self.mcp_host.ensure_http_adapter_async)

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(8000)
        self._status_timer.timeout.connect(panel.refresh_status)
        self._status_timer.start()

    def _save_config(self) -> None:
        settings_store.save_app_config(str(self.db_path), self.config, by="mcp_adapter")

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._status_timer.isActive():
            self._status_timer.stop()
        super().closeEvent(event)


def main(argv: Optional[list] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    root = Path.cwd()
    if "--root" in args:
        i = args.index("--root")
        if i + 1 < len(args):
            root = Path(args[i + 1])
    app = QApplication(sys.argv)
    win = McpAdapterWindow(root=root)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
