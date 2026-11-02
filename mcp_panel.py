"""Center-panel MCP controls (stdio + HTTP) and the llama.cpp WebUI launcher.

`McpControlPanel` and `LlamaWebUiPanel` are siblings that share one saved ``mcp``
settings block. Each emits ``settings_changed`` with only the keys it owns, so a
host merging those partials can never let one panel revert the other's edits.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import requests
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
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

from model_selector_core import DEFAULT_LLAMA_SERVER

DEFAULT_MCP_SETTINGS: Dict[str, Any] = {
    "transport": "streamable-http",
    "http_host": "127.0.0.1",
    "http_port": 8765,
    "llama_server_path": DEFAULT_LLAMA_SERVER,
    "webui_host": "127.0.0.1",
    "webui_port": 8082,
    "adapter_autostart": False,
    "webui_autostart": False,
    "cloudflared_path": r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
    "tunnel_public_url": "",
}


def merge_mcp_settings(raw: Optional[dict] = None) -> Dict[str, Any]:
    out = dict(DEFAULT_MCP_SETTINGS)
    if isinstance(raw, dict):
        out.update({k: v for k, v in raw.items() if v is not None})
    try:
        out["http_port"] = max(1024, min(int(out.get("http_port") or 8765), 65535))
    except (TypeError, ValueError):
        out["http_port"] = 8765
    try:
        out["webui_port"] = max(1024, min(int(out.get("webui_port") or 8082), 65535))
    except (TypeError, ValueError):
        out["webui_port"] = 8082
    out["http_host"] = str(out.get("http_host") or "127.0.0.1").strip() or "127.0.0.1"
    out["webui_host"] = str(out.get("webui_host") or "127.0.0.1").strip() or "127.0.0.1"
    out["llama_server_path"] = str(
        out.get("llama_server_path") or DEFAULT_LLAMA_SERVER
    ).strip()
    out["cloudflared_path"] = str(
        out.get("cloudflared_path")
        or r"C:\Program Files (x86)\cloudflared\cloudflared.exe"
    ).strip()
    out["tunnel_public_url"] = str(out.get("tunnel_public_url") or "").strip()
    transport = str(out.get("transport") or "streamable-http").strip().lower()
    if transport not in ("stdio", "streamable-http", "sse"):
        transport = "streamable-http"
    out["transport"] = transport
    out["adapter_autostart"] = bool(out.get("adapter_autostart"))
    out["webui_autostart"] = bool(out.get("webui_autostart"))
    # Keep only known keys
    return {k: out[k] for k in DEFAULT_MCP_SETTINGS}


def discover_webui_procs() -> list:
    """llama-server processes launched with --ui-mcp-proxy (any panel)."""
    try:
        from spock_health_report import discover_ui_mcp_proxy

        return list(discover_ui_mcp_proxy() or [])
    except Exception:
        return []


def resolve_webui_chat_model(
    root: Optional[str] = None,
) -> Tuple[str, int]:
    """Chat GGUF + n_ctx for the WebUI router (never the embedding model).

    Reads ``first_models_last.json`` then ``spock_ready_last.json``. Returns
    ``("", 0)`` when no chat path is known.
    """
    base = Path(root) if root else Path(__file__).resolve().parent
    chat_path = ""
    n_ctx = 0
    first = base / "first_models_last.json"
    if first.is_file():
        try:
            import json

            data = json.loads(first.read_text(encoding="utf-8"))
            chat_path = str(data.get("chat_gguf_path") or "").strip()
            try:
                n_ctx = int(data.get("chat_n_ctx") or 0)
            except (TypeError, ValueError):
                n_ctx = 0
        except Exception:
            pass
    if (not chat_path or not os.path.isfile(chat_path)) and (
        base / "spock_ready_last.json"
    ).is_file():
        try:
            import json

            data = json.loads((base / "spock_ready_last.json").read_text(encoding="utf-8"))
            chat = data.get("chat") if isinstance(data.get("chat"), dict) else {}
            chat_path = str(chat.get("model_path") or "").strip()
            try:
                n_ctx = int(chat.get("n_ctx") or n_ctx or 0)
            except (TypeError, ValueError):
                pass
        except Exception:
            pass
    if chat_path and os.path.isfile(chat_path):
        return chat_path, max(0, int(n_ctx or 0))
    return "", 0


def build_ui_mcp_proxy_argv(
    llama_server_path: str,
    *,
    host: str = "127.0.0.1",
    port: int = 8082,
    chat_model_path: str = "",
    chat_n_ctx: int = 0,
) -> list:
    """Argv for WebUI + MCP CORS proxy without autoloading embeddings.

    Recent llama-server enters **router mode** when ``-m`` is omitted and will
    autoload the first discovered GGUF (often EmbeddingGemma after Acquire).
    We always pass ``--no-models-autoload``. When a chat GGUF is known, scope
    ``--models-dir`` to that model's folder so the router lists chat, not embed.
    """
    path = str(llama_server_path or "").strip()
    host = (host or "127.0.0.1").strip() or "127.0.0.1"
    try:
        port_i = max(1024, min(int(port or 8082), 65535))
    except (TypeError, ValueError):
        port_i = 8082
    cmd = [
        path,
        "--host",
        host,
        "--port",
        str(port_i),
        "--ui-mcp-proxy",
        "--no-models-autoload",
    ]
    chat = str(chat_model_path or "").strip()
    if chat and os.path.isfile(chat):
        models_dir = str(Path(chat).resolve().parent)
        cmd.extend(["--models-dir", models_dir])
        if chat_n_ctx and int(chat_n_ctx) > 0:
            # Hint for when the user loads the chat model in the WebUI.
            cmd.extend(["-c", str(int(chat_n_ctx))])
    return cmd


def build_ui_mcp_proxy_env(
    *,
    chat_model_path: str = "",
    base_env: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Child env that hides the HF/llama GGUF cache from the WebUI router.

    llama.cpp merges HF cache presets even when ``--models-dir`` is set, so
    EmbeddingGemma can still appear in the Models list. Point cache vars at an
    empty temp dir so only ``--models-dir`` (chat) is visible.
    """
    env = dict(base_env if base_env is not None else os.environ)
    chat = str(chat_model_path or "").strip()
    if not (chat and os.path.isfile(chat)):
        return env
    # Stable per-user empty cache so we do not recreate dirs every spawn.
    empty = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    empty = empty / "Spock" / "llama-webui-empty-cache"
    try:
        empty.mkdir(parents=True, exist_ok=True)
    except OSError:
        return env
    cache = str(empty)
    for key in (
        "LLAMA_CACHE",
        "HF_HUB_CACHE",
        "HUGGINGFACE_HUB_CACHE",
        "HF_HOME",
    ):
        env[key] = cache
    return env


def webui_status_text(
    proc: Optional[subprocess.Popen] = None,
    settings: Optional[dict] = None,
) -> str:
    """Live label: this panel's spawn, else any discovered --ui-mcp-proxy."""
    if proc is not None and proc.poll() is None:
        s = merge_mcp_settings(settings)
        url = f"http://{s['webui_host']}:{s['webui_port']}"
        return f"WebUI running (PID {proc.pid}) · {url}"
    found = discover_webui_procs()
    if found:
        bits = [
            "PID {pid} · http://{host}:{port}".format(
                pid=p.get("pid"),
                host=p.get("host") or "127.0.0.1",
                port=p.get("port") or 8082,
            )
            for p in found
        ]
        return "WebUI running (" + "; ".join(bits) + ")"
    return "WebUI: not running"


def spawn_ui_mcp_proxy(
    settings: Optional[dict] = None,
) -> Tuple[bool, str, Optional[subprocess.Popen]]:
    """Start llama-server --ui-mcp-proxy. No-op (ok) if one is already up."""
    s = merge_mcp_settings(settings)
    found = discover_webui_procs()
    if found:
        p = found[0]
        url = f"http://{p.get('host') or '127.0.0.1'}:{p.get('port') or 8082}"
        return (
            True,
            f"already running (PID {p.get('pid')}) · {url} — "
            "Stop WebUI first if it still shows an embedding model",
            None,
        )
    path = str(s.get("llama_server_path") or "").strip()
    if not path or not os.path.isfile(path):
        return False, f"llama-server not found: {path}", None
    host = str(s.get("webui_host") or "127.0.0.1").strip() or "127.0.0.1"
    port = int(s.get("webui_port") or 8082)
    chat_path, chat_n_ctx = resolve_webui_chat_model()
    cmd = build_ui_mcp_proxy_argv(
        path,
        host=host,
        port=port,
        chat_model_path=chat_path,
        chat_n_ctx=chat_n_ctx,
    )
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]
    child_env = build_ui_mcp_proxy_env(chat_model_path=chat_path)
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=os.path.dirname(path) or None,
            creationflags=creationflags,
            env=child_env,
        )
    except OSError as e:
        return False, str(e), None
    url = f"http://{host}:{port}"
    detail = f"Started PID {proc.pid} · {url} · no-models-autoload"
    if chat_path:
        detail += f" · models-dir={Path(chat_path).parent.name} (chat, cache isolated)"
    return True, detail, proc


def stop_ui_mcp_proxy(
    proc: Optional[subprocess.Popen] = None,
) -> Tuple[bool, str]:
    """Stop this panel's spawn and any other --ui-mcp-proxy llama-server."""
    killed: list = []
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
            killed.append(str(proc.pid))
        except Exception as e:
            return False, str(e)
    for info in discover_webui_procs():
        pid = str(info.get("pid") or "")
        if not pid or pid in killed:
            continue
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", pid, "/F"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            else:
                os.kill(int(pid), 15)
            killed.append(pid)
        except Exception:
            pass
    if killed:
        return True, f"Stopped PID {', '.join(killed)}"
    return True, "WebUI was not running"


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
    """MCP adapter controls: transport, HTTP host/port, start/stop, health."""

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
        self._tunnel_proc: Optional[subprocess.Popen] = None
        self._last_auto_start_ts: float = 0.0
        self._build()
        self.apply_settings(self._settings)
        self.apply_theme()
        # Defer first status poll — panel init must not block the UI thread.
        QTimer.singleShot(0, self.refresh_status)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.addWidget(_title("MCP"))

        hint = QLabel(
            "Expose ship_computer.db tools to Cursor (stdio) or llama.cpp WebUI (HTTP). "
            "spock_ask also needs Embedding / RAG → START RAG API. "
            "Save settings so a Spock profile can restore them on load. "
            "Tool list and port map are under About."
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
            "Save Adapter settings and mark adapter_autostart so a Spock profile "
            "/ next launch can restore and start this MCP HTTP adapter."
        )
        save_btn.clicked.connect(self._on_save_mcp_settings)
        row.addWidget(save_btn)
        row.addStretch()
        lay.addLayout(row)

        self.http_health_lbl = QLabel("HTTP endpoint: not checked")
        self.http_health_lbl.setWordWrap(True)
        lay.addWidget(self.http_health_lbl)

        tunnel = QGroupBox("Cloudflare tunnel (optional — public HTTPS URL)")
        tunnel_l = QVBoxLayout(tunnel)
        tunnel_hint = QLabel(
            "Starts cloudflared quick tunnel → local MCP HTTP adapter. "
            "Use the public …/mcp URL in llama.cpp when localhost fails. "
            "Requires streamable-http listening on the port above first."
        )
        tunnel_hint.setWordWrap(True)
        tunnel_hint.setStyleSheet("color: #aaa;")
        tunnel_l.addWidget(tunnel_hint)
        tunnel_form = QFormLayout()
        self.cloudflared_edit = QLineEdit(
            str(self._settings.get("cloudflared_path") or "")
        )
        tunnel_form.addRow("cloudflared path", self.cloudflared_edit)
        tunnel_l.addLayout(tunnel_form)
        self.tunnel_url_lbl = QLabel("Public URL: (not started)")
        self.tunnel_url_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.tunnel_url_lbl.setWordWrap(True)
        tunnel_l.addWidget(self.tunnel_url_lbl)
        tunnel_row = QHBoxLayout()
        tunnel_start = _btn("Start Cloudflare tunnel", "#6D9E5A")
        tunnel_start.clicked.connect(self._on_start_tunnel)
        tunnel_row.addWidget(tunnel_start)
        tunnel_stop = _btn("Stop tunnel", "#C62828")
        tunnel_stop.clicked.connect(self._on_stop_tunnel)
        tunnel_row.addWidget(tunnel_stop)
        tunnel_copy = _btn("Copy public /mcp URL", "#5C6BC0")
        tunnel_copy.clicked.connect(self._on_copy_tunnel_url)
        tunnel_row.addWidget(tunnel_copy)
        tunnel_row.addStretch()
        tunnel_l.addLayout(tunnel_row)
        lay.addWidget(tunnel)

        self.adapter_log = QTextEdit()
        self.adapter_log.setReadOnly(True)
        self.adapter_log.setFont(QFont("Consolas", 10))
        self.adapter_log.setMinimumHeight(180)
        lay.addWidget(self.adapter_log, 1)

    def collect_settings(self) -> Dict[str, Any]:
        """Only the adapter's own keys — the host merges this into the block."""
        return {
            "transport": self.transport_combo.currentData() or "streamable-http",
            "http_host": (self.host_edit.text() or "127.0.0.1").strip(),
            "http_port": int(self.port_spin.value()),
            "cloudflared_path": (self.cloudflared_edit.text() or "").strip(),
            "tunnel_public_url": str(self._settings.get("tunnel_public_url") or "").strip(),
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
        self.cloudflared_edit.setText(str(s.get("cloudflared_path") or ""))
        pub = str(s.get("tunnel_public_url") or "").strip()
        if pub:
            self.tunnel_url_lbl.setText(f"Public URL: {pub.rstrip('/')}/mcp")
        self._update_url_labels()

    def _emit_settings(self):
        s = self.collect_settings()
        self._settings.update(s)
        self.settings_changed.emit(s)

    def _on_save_mcp_settings(self):
        """Persist adapter settings and enable adapter autostart for profiles."""
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
            "adapter_autostart is ON — loading a Spock profile (or next app start) "
            "can bring the MCP HTTP adapter back up.",
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
        """Bring up streamable-http when this tab is open and :port is down."""
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
        self._refresh_tunnel_status()
        self.refresh_requested.emit()

    def _refresh_tunnel_status(self) -> None:
        try:
            from spock_shell.mcp_tunnel import read_public_url, discover_tunnel_pids

            url = read_public_url() or str(self._settings.get("tunnel_public_url") or "")
            pids = discover_tunnel_pids()
            if url:
                self.tunnel_url_lbl.setText(f"Public URL: {url.rstrip('/')}/mcp")
            elif pids:
                self.tunnel_url_lbl.setText(
                    f"cloudflared running (PID {pids[0]}) — waiting for URL in log…"
                )
            else:
                self.tunnel_url_lbl.setText("Public URL: (not started)")
        except Exception:
            pass

    def _on_start_tunnel(self) -> None:
        from spock_shell.mcp_tunnel import start_quick_tunnel

        self._emit_settings()
        host = (self.host_edit.text() or "127.0.0.1").strip()
        port = int(self.port_spin.value())
        cf = (self.cloudflared_edit.text() or "").strip()
        self.adapter_log.append(f"Starting Cloudflare tunnel → {host}:{port} …")
        ok, detail, proc, public = start_quick_tunnel(
            local_port=port,
            local_host=host,
            cloudflared=cf or None,
        )
        self.adapter_log.append(detail)
        if proc is not None:
            self._tunnel_proc = proc
        if ok and public:
            self._settings["tunnel_public_url"] = public
            self.settings_changed.emit(
                {
                    "cloudflared_path": cf,
                    "tunnel_public_url": public,
                }
            )
            self.tunnel_url_lbl.setText(f"Public URL: {public.rstrip('/')}/mcp")
            QMessageBox.information(
                self,
                "Cloudflare tunnel",
                f"{detail}\n\nPaste in llama.cpp MCP Server URL:\n"
                f"  {public.rstrip('/')}/mcp",
            )
        elif not ok:
            QMessageBox.warning(self, "Cloudflare tunnel", detail)

    def _on_stop_tunnel(self) -> None:
        from spock_shell.mcp_tunnel import stop_tunnel

        ok, detail = stop_tunnel(self._tunnel_proc)
        self._tunnel_proc = None
        self._settings["tunnel_public_url"] = ""
        self.settings_changed.emit({"tunnel_public_url": ""})
        self.tunnel_url_lbl.setText("Public URL: (not started)")
        self.adapter_log.append(detail)

    def _on_copy_tunnel_url(self) -> None:
        from spock_shell.mcp_tunnel import read_public_url

        url = read_public_url() or str(self._settings.get("tunnel_public_url") or "")
        if not url:
            QMessageBox.information(self, "Copy URL", "No tunnel URL yet. Start tunnel first.")
            return
        mcp_url = f"{url.rstrip('/')}/mcp"
        QApplication.clipboard().setText(mcp_url)
        self.adapter_log.append(f"Copied: {mcp_url}")

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


class LlamaWebUiPanel(QWidget):
    """Launch llama-server --ui-mcp-proxy so its WebUI can reach Spock's MCP."""

    settings_changed = pyqtSignal(dict)

    def __init__(
        self,
        theme: dict,
        settings: Optional[dict] = None,
        ensure_http_adapter: Optional[Callable[[], None]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.theme = theme
        self._settings = merge_mcp_settings(settings)
        self._ensure_http_adapter = ensure_http_adapter
        self._webui_proc: Optional[subprocess.Popen] = None
        self._build()
        self.apply_settings(self._settings)
        self.apply_theme()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.addWidget(_title("llama.cpp WebUI"))

        info = QLabel(
            "Spawn llama-server with --ui-mcp-proxy in a new console "
            "(same pattern as Wiki Agent). Open the WebUI, add Spock MCP URL, "
            "toggle the server ON. CORS is enabled on Spock's HTTP adapter; "
            "the proxy toggle is optional.\n\n"
            "Router mode uses --no-models-autoload and scopes --models-dir to "
            "the Acquire chat GGUF folder so EmbeddingGemma on :8080 is not "
            "auto-loaded here. Load gemma chat (or your chat pick) in the WebUI "
            "Models list when you want to chat."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #aaa;")
        lay.addWidget(info)

        form = QFormLayout()
        self.llama_path_edit = QLineEdit(DEFAULT_LLAMA_SERVER)
        form.addRow("llama-server path", self.llama_path_edit)

        self.webui_host_edit = QLineEdit("127.0.0.1")
        form.addRow("WebUI host", self.webui_host_edit)

        self.webui_port_spin = QSpinBox()
        self.webui_port_spin.setRange(1024, 65535)
        self.webui_port_spin.setValue(8082)
        form.addRow("WebUI port", self.webui_port_spin)
        lay.addLayout(form)

        warn = QLabel(
            "Note: embeddings often use :8080 and chat :8081 — pick a free port "
            "(default 8082) unless you want router mode on that port."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet("color: #FFC107;")
        lay.addWidget(warn)

        row = QHBoxLayout()
        spawn = _btn("Start llama-server --ui-mcp-proxy", "#6D9E5A")
        spawn.clicked.connect(self._on_spawn_webui)
        row.addWidget(spawn)
        open_btn = _btn("Open WebUI in browser", "#5C6BC0")
        open_btn.clicked.connect(self._on_open_webui)
        row.addWidget(open_btn)
        stop = _btn("Stop WebUI process", "#C62828")
        stop.clicked.connect(self._on_stop_webui)
        row.addWidget(stop)
        save_webui = _btn("Save llama-server", "#6D9E5A")
        save_webui.setToolTip(
            "Save llama-server path / WebUI host:port and mark webui_autostart "
            "so a Spock profile / next launch can restore --ui-mcp-proxy."
        )
        save_webui.clicked.connect(self._on_save_llama_server)
        row.addWidget(save_webui)
        row.addStretch()
        lay.addLayout(row)

        self.webui_status = QLabel("WebUI: not running")
        lay.addWidget(self.webui_status)

        self.webui_log = QTextEdit()
        self.webui_log.setReadOnly(True)
        self.webui_log.setFont(QFont("Consolas", 10))
        self.webui_log.setPlainText(
            "After Start:\n"
            "1. Open WebUI → MCP → add the Server URL shown on the MCP panel\n"
            "2. Prefer 127.0.0.1 (not localhost)\n"
            "3. Toggle Spock MCP ON — tools should list (spock_search_kb, …)\n"
        )
        lay.addWidget(self.webui_log, 1)

    def collect_settings(self) -> Dict[str, Any]:
        """Only the WebUI's own keys — the host merges this into the block."""
        return {
            "llama_server_path": (self.llama_path_edit.text() or "").strip(),
            "webui_host": (self.webui_host_edit.text() or "127.0.0.1").strip(),
            "webui_port": int(self.webui_port_spin.value()),
        }

    def apply_settings(self, settings: Optional[dict]):
        s = merge_mcp_settings(settings)
        self._settings = s
        self.llama_path_edit.setText(str(s["llama_server_path"]))
        self.webui_host_edit.setText(str(s["webui_host"]))
        self.webui_port_spin.setValue(int(s["webui_port"]))
        if getattr(self, "webui_status", None) is not None:
            self.refresh_status()

    def _emit_settings(self):
        s = self.collect_settings()
        self._settings.update(s)
        self.settings_changed.emit(s)

    def _on_save_llama_server(self):
        """Persist WebUI llama-server settings and enable webui + adapter autostart."""
        s = self.collect_settings()
        s["webui_autostart"] = True
        # WebUI MCP tools need the HTTP adapter on :8765.
        s["adapter_autostart"] = True
        self._settings.update(s)
        self.settings_changed.emit(s)
        if self._ensure_http_adapter is not None:
            try:
                self._ensure_http_adapter()
            except Exception as e:
                self.webui_log.append(f"MCP adapter ensure failed: {e}")
        self.webui_log.append(
            "llama-server WebUI settings saved "
            "(webui_autostart + adapter_autostart=on for profile/startup).\n"
        )
        QMessageBox.information(
            self,
            "Save llama-server",
            "llama-server / WebUI settings saved.\n\n"
            "webui_autostart and adapter_autostart are ON — loading a Spock "
            "profile (or next app start) can launch --ui-mcp-proxy and the "
            "MCP HTTP adapter again.",
        )

    def refresh_status(self) -> None:
        """Adopt any --ui-mcp-proxy, including ones started outside this widget."""
        if self._webui_proc is not None and self._webui_proc.poll() is not None:
            self._webui_proc = None
        self.webui_status.setText(
            webui_status_text(self._webui_proc, self.collect_settings())
        )

    def is_webui_running(self) -> bool:
        if self._webui_proc is not None and self._webui_proc.poll() is None:
            return True
        return bool(discover_webui_procs())

    def start_ui_mcp_proxy(self, *, quiet: bool = False) -> Tuple[bool, str]:
        """Start --ui-mcp-proxy from current settings. Returns (ok, detail)."""
        self._emit_settings()
        # MCP tools in the WebUI need Spock's HTTP adapter listening.
        if self._ensure_http_adapter is not None:
            try:
                self._ensure_http_adapter()
            except Exception as e:
                if not quiet:
                    self.webui_log.append(f"MCP adapter ensure failed: {e}")
        s = dict(self._settings)
        if self._webui_proc is not None and self._webui_proc.poll() is None:
            self.refresh_status()
            return True, f"already running (PID {self._webui_proc.pid})"
        ok, detail, proc = spawn_ui_mcp_proxy(s)
        if proc is not None:
            self._webui_proc = proc
            path = str(s.get("llama_server_path") or "").strip()
            host = str(s.get("webui_host") or "127.0.0.1").strip() or "127.0.0.1"
            port = int(s.get("webui_port") or 8082)
            chat_path, chat_n_ctx = resolve_webui_chat_model()
            cmd = build_ui_mcp_proxy_argv(
                path,
                host=host,
                port=port,
                chat_model_path=chat_path,
                chat_n_ctx=chat_n_ctx,
            )
            self.webui_log.append(f"$ {' '.join(cmd)}\n{detail}\n")
            QTimer.singleShot(1500, self.refresh_status)
        else:
            self.webui_log.append(detail + "\n")
        self.refresh_status()
        if not ok:
            return False, detail
        if not quiet and not detail.startswith("already"):
            QMessageBox.information(
                self,
                "llama-server --ui-mcp-proxy",
                f"{detail}\n\n"
                f"Add MCP Server URL: http://{s.get('http_host') or '127.0.0.1'}:"
                f"{s.get('http_port') or 8765}/mcp",
            )
        return True, detail

    def _on_spawn_webui(self):
        ok, detail = self.start_ui_mcp_proxy(quiet=False)
        if not ok:
            QMessageBox.critical(self, "llama-server", f"Failed to start:\n{detail}")

    def _on_open_webui(self):
        host = (self.webui_host_edit.text() or "127.0.0.1").strip()
        port = int(self.webui_port_spin.value())
        found = discover_webui_procs()
        if found:
            host = str(found[0].get("host") or host)
            try:
                port = int(found[0].get("port") or port)
            except (TypeError, ValueError):
                pass
        from spock_shell.open_url import open_url

        open_url(f"http://{host}:{port}")

    def _on_stop_webui(self):
        ok, detail = stop_ui_mcp_proxy(self._webui_proc)
        self._webui_proc = None
        self.refresh_status()
        self.webui_log.append(detail + "\n")
        if not ok:
            QMessageBox.warning(self, "llama-server", f"Stop failed: {detail}")

    def apply_theme(self):
        self.setStyleSheet(_panel_stylesheet(self.theme))
