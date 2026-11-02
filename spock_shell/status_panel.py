"""Non-modal Status console (spock_health_report)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from spock_shell.paths import SHIP_COMPUTER_DB, ensure_root_on_path


class StatusConsole(QWidget):
    """Standalone Status window used by every suite mini-app."""

    def __init__(
        self,
        theme: Dict[str, str],
        config: Optional[Dict[str, Any]] = None,
        parent=None,
        *,
        as_window: bool = True,
    ):
        super().__init__(parent)
        self.theme = theme
        self.config = dict(config or {})
        self.setWindowTitle("Spock Status")
        self.setMinimumSize(720, 520)
        if as_window:
            from PyQt6.QtCore import Qt

            self.setWindowFlags(
                self.windowFlags() | Qt.WindowType.Window
            )
        layout = QVBoxLayout(self)
        title = QLabel("Status console")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(title)
        row = QHBoxLayout()
        self.refresh_btn = QPushButton("Run Spock Status")
        self.refresh_btn.clicked.connect(self.refresh)
        row.addWidget(self.refresh_btn)
        row.addStretch()
        layout.addLayout(row)
        self.out = QTextEdit()
        self.out.setReadOnly(True)
        self.out.setFont(QFont("Consolas", 10))
        layout.addWidget(self.out, 1)
        self.apply_theme()
        self.out.setPlainText("Click Run Spock Status to probe RAG / llama / MCP.")

    def apply_theme(self) -> None:
        self.setStyleSheet(
            f"""
            QWidget {{ background: {self.theme['bg']}; color: {self.theme['fg']}; }}
            QTextEdit {{
                background: {self.theme['panel_bg']};
                color: {self.theme['fg']};
                border: 1px solid {self.theme['border']};
            }}
            QPushButton {{
                background: {self.theme['accent']};
                color: {self.theme['fg']};
                padding: 8px 14px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }}
            """
        )

    def refresh(self) -> None:
        ensure_root_on_path()
        from spock_health_report import format_spock_health_report, probe_spock_health

        cfg = self.config
        rag = cfg.get("rag_api") or {}
        emb = (cfg.get("embedding_profile") or {}).get(
            "embeddings_url", "http://localhost:8080/embeddings"
        )
        mcp = cfg.get("mcp") or {}
        host = rag.get("host", "127.0.0.1")
        port = int(rag.get("port", 8090))
        try:
            data = probe_spock_health(
                api_base=f"http://{host}:{port}",
                db_path=SHIP_COMPUTER_DB,
                embeddings_url=emb,
                api_key=str(rag.get("api_key") or ""),
                chat_host=str(cfg.get("llama_host") or "localhost"),
                chat_port=int(cfg.get("llama_port") or 8081),
                mcp_host=str(mcp.get("http_host") or "127.0.0.1"),
                mcp_port=int(mcp.get("http_port") or 8765),
                mcp_transport=str(mcp.get("transport") or "streamable-http"),
                webui_host=str(mcp.get("webui_host") or "127.0.0.1"),
                webui_port=int(mcp.get("webui_port") or 8082),
            )
            self.out.setPlainText(format_spock_health_report(data))
        except Exception as e:
            self.out.setPlainText(f"Status probe failed:\n{e}")
