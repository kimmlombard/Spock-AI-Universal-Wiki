"""MCP adapter control panel (stdio + HTTP) with logging."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import requests
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from WarpCore.config_defaults import DEFAULT_LLAMA_SERVER, merge_mcp_settings


def _panel_stylesheet(t: dict) -> str:
    return f"""
        QWidget {{ background-color: {t['bg']}; color: {t['fg']}; }}
        QTextEdit, QLineEdit, QSpinBox, QComboBox {{
            background-color: {t['panel_bg']};
            color: {t['fg']};
            border: 1px solid {t['border']};
            border-radius: 4px;
            padding: 4px;
        }}
        QGroupBox {{
            border: 1px solid {t['border']};
            margin-top: 8px;
            padding-top: 8px;
        }}
        """


def _title(text: str) -> QLabel:
    label = QLabel(text)
    font = QFont()
    font.setPointSize(14)
    font.setBold(True)
    label.setFont(font)
    label.setStyleSheet("color: #FF9800;")
    return label


def _btn(text: str, color: str = "#5C6BC0") -> QPushButton:
    b = QPushButton(text)
    b.setMinimumHeight(32)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(
        f"""
        QPushButton {{
            background-color: {color};
            color: #FFFFFF;
            border: none;
            border-radius: 4px;
            padding: 6px 14px;
            font-weight: bold;
        }}
        QPushButton:hover {{ background-color: {color}CC; }}
        QPushButton:disabled {{ background-color: #555; color: #999; }}
        """
    )
    return b


class McpControlPanel(QWidget):
    """MCP adapter controls: transport, HTTP host/port, start/stop, health, log."""

    refresh_requested = pyqtSignal()
    settings_changed = pyqtSignal(dict)

    def __init__(
        self,
        theme: dict,
        *,
        script_path: Path,
        python_exe: Path,
        start_adapter: Callable[..., None],
        stop_adapter: Callable[[], None],
        find_adapter: Callable[[], None],
        adapter_status: Callable[[], str],
        adapter_pids: Callable[[], list],
        health_context: Callable[[], Dict[str, str]],
        ensure_http_adapter: Optional[Callable[[], None]] = None,
        settings: Optional[dict] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.theme = theme
        self.script_path = Path(script_path)
        self.python_exe = Path(python_exe)
        self._start_adapter = start_adapter
        self._stop_adapter = stop_adapter
        self._find_adapter = find_adapter
        self._adapter_status = adapter_status
        self._adapter_pids = adapter_pids
        self._health_context = health_context
        self._ensure_http_adapter = ensure_http_adapter
        self._settings = merge_mcp_settings(settings)
        self._last_auto_start_ts: float = 0.0
        self._build()
        self.apply_settings(self._settings)
        self.apply_theme()
        QTimer.singleShot(0, self.refresh_status)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.addWidget(_title("MCP"))

        hint = QLabel(
            "Expose ship_computer.db tools to Cursor (stdio) or llama.cpp WebUI (HTTP). "
            "spock_ask also needs Embedding / RAG → START RAG API. "
            "Save settings so a Spock profile can restore them on load."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #aaa;")
        lay.addWidget(hint)

        self.status_lbl = QLabel("Status: —")
        self.status_lbl.setStyleSheet("font-weight: bold;")
        lay.addWidget(self.status_lbl)

        form = QFormLayout()
        self.transport_combo = QComboBox()
        self.transport_combo.addItem("stdio (Cursor / OpenCode)", "stdio")
        self.transport_combo.addItem(
            "streamable-http (llama.cpp Server URL)", "streamable-http"
        )
        self.transport_combo.addItem("sse (legacy URL …/sse)", "sse")
        form.addRow("Transport", self.transport_combo)

        self.host_edit = QLineEdit("127.0.0.1")
        form.addRow("HTTP host", self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(8765)
        form.addRow("HTTP port", self.port_spin)
        lay.addLayout(form)

        urls = QGroupBox("llama.cpp Server URL (when HTTP is running)")
        urls_l = QVBoxLayout(urls)
        self.url_mcp_lbl = QLabel()
        self.url_sse_lbl = QLabel()
        self.url_mcp_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.url_sse_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        urls_l.addWidget(self.url_mcp_lbl)
        urls_l.addWidget(self.url_sse_lbl)
        lay.addWidget(urls)
        self._update_url_labels()
        self.port_spin.valueChanged.connect(self._update_url_labels)
        self.host_edit.textChanged.connect(self._update_url_labels)

        row = QHBoxLayout()
        start = _btn("Start adapter", "#6D9E5A")
        start.clicked.connect(self._on_start_adapter)
        row.addWidget(start)
        stop = _btn("Stop adapter", "#C62828")
        stop.clicked.connect(self._on_stop_adapter)
        row.addWidget(stop)
        find = _btn("Find running", "#5C6BC0")
        find.clicked.connect(self._on_find)
        row.addWidget(find)
        check = _btn("Check HTTP :port", "#FF9800")
        check.clicked.connect(self._on_check_http)
        row.addWidget(check)
        save_btn = _btn("Save MCP Settings", "#6D9E5A")
        save_btn.setToolTip(
            "Save adapter settings and mark adapter_autostart for next launch."
        )
        save_btn.clicked.connect(self._on_save_mcp_settings)
        row.addWidget(save_btn)
        row.addStretch()
        lay.addLayout(row)

        self.http_health_lbl = QLabel("HTTP endpoint: not checked")
        self.http_health_lbl.setWordWrap(True)
        lay.addWidget(self.http_health_lbl)

        self.adapter_log = QTextEdit()
        self.adapter_log.setReadOnly(True)
        self.adapter_log.setFont(QFont("Consolas", 10))
        self.adapter_log.setMinimumHeight(220)
        lay.addWidget(self.adapter_log, 1)

    def collect_settings(self) -> Dict[str, Any]:
        return {
            "transport": self.transport_combo.currentData() or "streamable-http",
            "http_host": (self.host_edit.text() or "127.0.0.1").strip(),
            "http_port": int(self.port_spin.value()),
            "llama_server_path": str(
                self._settings.get("llama_server_path") or DEFAULT_LLAMA_SERVER
            ).strip(),
        }

    def apply_settings(self, settings: Optional[dict]):
        s = merge_mcp_settings(settings)
        self._settings = s
        for i in range(self.transport_combo.count()):
            if self.transport_combo.itemData(i) == s["transport"]:
                self.transport_combo.setCurrentIndex(i)
                break
        self.host_edit.setText(str(s["http_host"]))
        self.port_spin.setValue(int(s["http_port"]))
        self._update_url_labels()

    def _emit_settings(self):
        s = self.collect_settings()
        self._settings.update(s)
        self.settings_changed.emit(s)

    def _on_save_mcp_settings(self):
        s = self.collect_settings()
        s["adapter_autostart"] = True
        self._settings.update(s)
        self.settings_changed.emit(s)
        self.adapter_log.append(
            "MCP Adapter settings saved (adapter_autostart=on for profile/startup)."
        )
        self._maybe_auto_start_http(force=True)
        QMessageBox.information(
            self,
            "Save MCP Settings",
            "Adapter settings saved.\n\n"
            "adapter_autostart is ON — next launch can bring the MCP HTTP adapter back up.",
        )

    def _update_url_labels(self):
        host = (self.host_edit.text() or "127.0.0.1").strip()
        port = int(self.port_spin.value())
        self.url_mcp_lbl.setText(f"MCP:  http://{host}:{port}/mcp")
        self.url_sse_lbl.setText(f"SSE:  http://{host}:{port}/sse")

    def _http_transport_selected(self) -> bool:
        transport = str(
            self.transport_combo.currentData()
            or self._settings.get("transport")
            or "streamable-http"
        ).strip().lower()
        return transport in ("http", "streamable-http", "streamable_http", "sse")

    def _maybe_auto_start_http(self, *, force: bool = False) -> None:
        if not self._http_transport_selected() or self._ensure_http_adapter is None:
            return
        now = time.time()
        if not force and now - self._last_auto_start_ts < 12.0:
            return
        self._last_auto_start_ts = now
        self.adapter_log.append("Starting HTTP MCP adapter in background…")
        try:
            self._ensure_http_adapter()
        except Exception as e:
            self.adapter_log.append(f"Auto-start HTTP MCP failed: {e}")

    def refresh_status(self):
        try:
            status = self._adapter_status() or "unknown"
        except Exception as e:
            status = f"error: {e}"
        pids = []
        try:
            pids = list(self._adapter_pids() or [])
        except Exception:
            pass
        extra = f" · PIDs: {', '.join(pids)}" if pids else ""
        self.status_lbl.setText(f"Adapter: {status}{extra}")
        if self.adapter_log.toPlainText().strip() == "":
            self.adapter_log.setPlainText(
                f"Script: {self.script_path}\nPython: {self.python_exe}\n"
            )
        try:
            self._on_check_http()
        except Exception:
            pass
        self.refresh_requested.emit()

    def _on_start_adapter(self):
        self._emit_settings()
        transport = self.transport_combo.currentData() or "streamable-http"
        host = (self.host_edit.text() or "127.0.0.1").strip()
        port = int(self.port_spin.value())
        self.adapter_log.append(
            f"Starting transport={transport} host={host} port={port}…"
        )
        try:
            self._start_adapter(
                quiet=False,
                transport=str(transport),
                http_host=host,
                http_port=port,
            )
        except TypeError:
            self._start_adapter(quiet=False, transport=str(transport))
        except Exception as e:
            self.adapter_log.append(f"ERROR: {e}")
        self.refresh_status()

    def _on_stop_adapter(self):
        self.adapter_log.append("Stopping adapter…")
        try:
            self._stop_adapter()
        except Exception as e:
            self.adapter_log.append(f"ERROR: {e}")
        self.refresh_status()

    def _on_find(self):
        try:
            self._find_adapter()
        except Exception as e:
            self.adapter_log.append(f"ERROR: {e}")
        self.refresh_status()

    def _on_check_http(self):
        host = (self.host_edit.text() or "127.0.0.1").strip()
        port = int(self.port_spin.value())
        url = f"http://{host}:{port}/mcp"
        self.adapter_log.append(f"Checking {url} …")
        try:
            r = requests.options(
                url,
                headers={
                    "Origin": "http://127.0.0.1:8082",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type,accept",
                },
                timeout=3,
            )
            aca = r.headers.get("access-control-allow-origin") or "(none)"
            if r.status_code == 200 and aca:
                msg = f"HTTP OK — {url} listening (CORS: {aca})"
                self.http_health_lbl.setStyleSheet("color: #81C784; font-weight: bold;")
            else:
                msg = (
                    f"HTTP odd — OPTIONS {r.status_code}, CORS={aca}. "
                    "Restart the adapter with streamable-http."
                )
                self.http_health_lbl.setStyleSheet("color: #FFC107; font-weight: bold;")
            self.http_health_lbl.setText(msg)
            self.adapter_log.append(msg)
        except Exception as e:
            err = str(e)
            if "10061" in err or "refused" in err.lower() or "Failed to establish" in err:
                msg = (
                    f"NOT LISTENING — nothing on {url}.\n"
                    "Select transport streamable-http → Start adapter, "
                    "then retry in llama.cpp. (stdio does not open this URL.)"
                )
            else:
                msg = f"Check failed: {e}"
            self.http_health_lbl.setText(msg)
            self.http_health_lbl.setStyleSheet("color: #EF5350; font-weight: bold;")
            self.adapter_log.append(msg)

    def apply_theme(self):
        self.setStyleSheet(_panel_stylesheet(self.theme))
