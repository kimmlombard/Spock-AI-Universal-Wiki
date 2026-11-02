"""About dialog for suite mini-apps.

Also carries the MCP tool / port reference that used to sit behind a Help
sub-tab inside the MCP panel, so it is reachable from every window.
"""

from __future__ import annotations

from typing import Dict

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from spock_shell.paths import ROOT, SHIP_COMPUTER_DB

MCP_REFERENCE = """\
Tools (Spock MCP adapter)
─────────────────────────
spock_health       — RAG API /health, db, embeddings, llama :8080/:8081 ctx,
                     MCP adapter (:8765), llama-server --ui-mcp-proxy (:8082)
spock_ask          — RAG chat over ship_computer.db (needs RAG API)
spock_search_kb    — FTS5 / keyword search
spock_status       — full Spock status (health report + ship/GPU scan)
spock_queue        — agent_queue sample
spock_captains_log — recent captains_log rows
spock_llmfit_fit   — local llmfit fit/recommend (tok/s + fit level)
spock_hardware_plan— llmfit plan for a model/ctx + suggested -ngl

Typical port layout
───────────────────
:8080  embeddings llama-server
:8081  chat llama-server (optional)
:8082  llama-server --ui-mcp-proxy (Engineering Deck → llama.cpp WebUI)
:8090  Spock RAG API (Embedding / RAG → START)
:8765  Spock MCP HTTP (MCP panel → streamable-http)

Connecting a client
───────────────────
Cursor / OpenCode use stdio and spawn the adapter themselves via mcp.json:

{
  "mcpServers": {
    "spock": {
      "command": "<repo>/.venv/Scripts/python.exe",
      "args": ["-u", "<repo>/scripts/mcp_spock_server.py"]
    }
  }
}

llama.cpp WebUI uses the HTTP URL instead: start the adapter with transport
streamable-http, then add http://127.0.0.1:8765/mcp as the Server URL.
Prefer 127.0.0.1 over localhost. CORS is already enabled on the adapter.
"""


class AboutDialog(QDialog):
    def __init__(
        self,
        theme: Dict[str, str],
        app_name: str = "Spock Suite",
        parent=None,
    ):
        super().__init__(parent)
        self.theme = theme
        self.setWindowTitle(f"About — {app_name}")
        self.resize(680, 520)
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._about_tab(app_name), "About")
        tabs.addTab(self._mcp_tab(), "MCP reference")
        layout.addWidget(tabs, 1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        self.setStyleSheet(
            f"""
            QDialog, QTabWidget, QWidget {{
                background: {theme['bg']}; color: {theme['fg']};
            }}
            QTextEdit {{
                background: {theme['panel_bg']}; color: {theme['fg']};
                border: 1px solid {theme['border']};
            }}
            QTabBar::tab {{
                background: {theme['panel_bg']}; color: {theme['fg']};
                padding: 8px 14px; margin-right: 2px;
                border: 1px solid {theme['border']};
            }}
            QTabBar::tab:selected {{
                background: {theme['accent']}; font-weight: bold;
            }}
            QPushButton {{
                background: {theme['accent']}; color: {theme['fg']};
                padding: 8px 16px; border: none; border-radius: 4px;
            }}
            """
        )

    def _about_tab(self, app_name: str) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        body = QLabel(
            f"<h2>{app_name}</h2>"
            "<p>Spock-UIE-Wiki-KB suite mini-app (shared <code>spock_shell</code>).</p>"
            f"<p><b>Repo:</b> {ROOT}</p>"
            f"<p><b>ship_computer.db:</b> {SHIP_COMPUTER_DB}</p>"
            "<p>Launch the full suite with <code>python Spock-UIE-Wiki-KB.py</code>.</p>"
        )
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(body)
        lay.addStretch()
        return page

    def _mcp_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        view = QTextEdit()
        view.setReadOnly(True)
        view.setFont(QFont("Consolas", 10))
        view.setPlainText(MCP_REFERENCE)
        lay.addWidget(view)
        return page
