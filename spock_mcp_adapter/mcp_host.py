"""Host-side MCP adapter control shared by suite mini-apps.

Ports the adapter lifecycle from Spock-to-bridge.py so any SuiteShellWindow can
drive mcp_panel.McpControlPanel without copying process-management code.
"""

from __future__ import annotations

try:
    from WarpCore.service_endpoints import (
        DEFAULT_MCP_PORT,
        DEFAULT_MCP_WEBUI_PORT,
        DEFAULT_RAG_PORT,
    )
except ImportError:  # pragma: no cover
    DEFAULT_MCP_PORT = 8765
    DEFAULT_MCP_WEBUI_PORT = 8082
    DEFAULT_RAG_PORT = 8090

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import QTimer

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from WarpCore.config_defaults import DEFAULT_MCP_SETTINGS, merge_mcp_settings
from spock_mcp_adapter.paths import ROOT, SHIP_COMPUTER_DB

ADAPTER_SCRIPT_NAME = "mcp_spock_server.py"
_HTTP_TRANSPORTS = ("http", "streamable-http", "streamable_http", "sse")


def _mcp_deps_ok(python_exe: Path) -> tuple[bool, str]:
    """Verify fastmcp is importable in the venv before spawning the adapter."""
    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        # Authlib forces AuthlibDeprecationWarning to "always"; silence after import.
        proc = subprocess.run(
            [
                str(python_exe),
                "-c",
                (
                    "import warnings;"
                    "from authlib.deprecate import AuthlibDeprecationWarning;"
                    "warnings.filterwarnings('ignore', category=AuthlibDeprecationWarning);"
                    "import fastmcp"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=creationflags,
        )
    except Exception as e:
        return False, str(e)
    if proc.returncode == 0:
        return True, ""
    err = (proc.stderr or proc.stdout or "").strip()
    if "fastmcp" in err.lower():
        req = ROOT / "requirements-mcp.txt"
        return False, (
            "Missing Python package: fastmcp\n\n"
            "Install MCP adapter deps from the repo root:\n"
            f'  "{python_exe}" -m pip install -r "{req}"'
        )
    return False, err or "MCP dependency check failed (fastmcp not importable)"


def _fold(text: str) -> str:
    """Case-fold a path/command line so Windows drive letters and slashes match."""
    return os.path.normcase(str(text or "")).replace("\\", "/")


def _mcp_transport_for_pid(pid: int | str) -> str:
    """Read SPOCK_MCP_TRANSPORT from a live process; empty if unavailable."""
    try:
        import psutil

        env = psutil.Process(int(pid)).environ()
        return str(env.get("SPOCK_MCP_TRANSPORT") or "").strip().lower()
    except Exception:
        return ""


def show_output_dialog(parent: Optional[QWidget], title: str, text: str) -> None:
    """Scrollable output viewer with Select All / Copy (MCP / diagnostics)."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setMinimumSize(750, 500)
    dlg.setModal(True)
    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(10, 10, 10, 10)
    viewer = QTextEdit()
    viewer.setReadOnly(True)
    viewer.setFont(QFont("Consolas", 10))
    viewer.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
    viewer.setPlainText(text)
    layout.addWidget(viewer)
    btn_row = QHBoxLayout()
    select_btn = QPushButton("Select All")
    select_btn.setMinimumWidth(90)
    select_btn.clicked.connect(viewer.selectAll)
    btn_row.addWidget(select_btn)
    copy_btn = QPushButton("Copy")
    copy_btn.setMinimumWidth(70)
    copy_btn.setToolTip("Copy all text to the clipboard")
    copy_btn.clicked.connect(
        lambda: QApplication.clipboard().setText(viewer.toPlainText())
    )
    btn_row.addWidget(copy_btn)
    btn_row.addStretch()
    close_btn = QPushButton("Close")
    close_btn.setMinimumWidth(70)
    close_btn.clicked.connect(dlg.accept)
    btn_row.addWidget(close_btn)
    layout.addLayout(btn_row)
    dlg.exec()


class McpAdapterHost:
    """Start/stop/find the MCP adapter and feed McpControlPanel callbacks."""

    def __init__(
        self,
        config: Dict[str, Any],
        save_config: Callable[[], None],
        *,
        parent: Optional[QWidget] = None,
    ):
        self.config = config
        self._save_config = save_config
        self.parent = parent
        self.panel = None
        self.adapter_proc: Optional[subprocess.Popen] = None
        self._last_reap_ts: float = 0.0
        self._http_work_busy: bool = False
        self._http_async_pending: bool = False

    # --- environment ---
    def script_path(self) -> Path:
        return ROOT / "scripts" / ADAPTER_SCRIPT_NAME

    def python_exe(self) -> Path:
        for candidate in (
            ROOT / ".venv" / "bin" / "python",
            ROOT / ".venv" / "Scripts" / "python.exe",
        ):
            if candidate.is_file():
                return candidate
        return Path(sys.executable)

    def _save(self) -> None:
        try:
            self._save_config()
        except Exception:
            pass

    # --- discovery ---
    def _ps_python_dump(self) -> str:
        """List python processes (Windows: PowerShell CIM; Linux/macOS: psutil)."""
        if os.name != "nt":
            try:
                import psutil
            except ImportError as e:
                raise RuntimeError(
                    "psutil is required to list MCP adapter processes on Linux/macOS"
                ) from e
            lines: List[str] = []
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    name = (proc.info.get("name") or "").lower()
                    cmd = proc.info.get("cmdline") or []
                    if "python" not in name and not any(
                        "python" in str(c).lower() for c in cmd[:1]
                    ):
                        continue
                    cl = " ".join(str(c) for c in cmd)
                    lines.append(f"{proc.info.get('pid')} {cl}")
                except (psutil.Error, TypeError, ValueError):
                    continue
            return "\n".join(lines) if lines else "(No python processes found.)"
        cmd = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.Name -match 'python' } | "
            "Select-Object ProcessId, CommandLine | "
            "Format-Table -Auto | Out-String -Width 4000"
        )
        try:
            p = subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=20,
            )
        except OSError as e:
            raise RuntimeError(f"PowerShell unavailable: {e}") from e
        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()
        if p.returncode != 0:
            raise RuntimeError(err or f"PowerShell failed with exit code {p.returncode}")
        return out or "(No python processes found.)"

    def _script_fold(self) -> str:
        return _fold(str(self.script_path()))

    def _line_is_ours(self, line: str) -> bool:
        return self._script_fold() in _fold(line)

    def _all_adapter_processes(self) -> List[Dict[str, Any]]:
        try:
            from spock_health_report import discover_mcp_adapter_pids

            return list(discover_mcp_adapter_pids() or [])
        except Exception:
            return []

    def find_text(self, needle: str = ADAPTER_SCRIPT_NAME) -> str:
        txt = self._ps_python_dump()
        hits = [line for line in txt.splitlines() if needle.lower() in line.lower()]
        script = self.script_path()
        ours = [line for line in hits if self._line_is_ours(line)]
        foreign = [line for line in hits if not self._line_is_ours(line)]
        header = (
            f"This install: {script}\n"
            "Start/Stop from Spock manages every process running this script.\n"
        )
        if not hits:
            if script.is_file():
                return (
                    f"{header}\nNot found (running): {needle}\n\n"
                    "No active python process is running it.\n"
                    "Start from project root with:\n"
                    f'"{self.python_exe()}" "{script}"'
                    "\n\n"
                    f"Full list:\n{txt}"
                )
            return (
                f"{header}\nNot found: {needle}\n\n"
                f"Script missing: {script}\n\nFull list:\n{txt}"
            )
        blocks = [header]
        if ours:
            blocks.append("This install:\n" + "\n".join(ours))
        if foreign:
            blocks.append(
                "OTHER install(s) — not started/stopped by this Spock "
                "(often leftover Cursor mcp.json):\n" + "\n".join(foreign)
            )
        return "\n\n".join(blocks)

    def running_pids(self) -> List[str]:
        """PIDs for THIS repo's scripts/mcp_spock_server.py only."""
        marker = self._script_fold()
        pids: List[str] = []
        for proc in self._all_adapter_processes():
            if marker in _fold(str(proc.get("cmdline") or "")):
                pids.append(str(proc.get("pid") or ""))
        pids = [p for p in pids if p.isdigit()]
        if pids:
            return pids
        try:
            txt = self._ps_python_dump()
        except Exception:
            return []
        fallback: List[str] = []
        for line in txt.splitlines():
            if ADAPTER_SCRIPT_NAME.lower() not in line.lower():
                continue
            if not self._line_is_ours(line):
                continue
            parts = line.strip().split(maxsplit=1)
            if parts and parts[0].isdigit():
                fallback.append(parts[0])
        return fallback

    def adapter_status_text(self) -> str:
        if self.adapter_proc is not None and self.adapter_proc.poll() is not None:
            self.adapter_proc = None
        pids = self.running_pids()
        if pids:
            return f"running ({len(pids)} process(es))"
        return "stopped"

    def _maybe_reap_http_duplicates(self) -> None:
        """Drop extra Spock HTTP adapter PIDs (Start path only — not status polls)."""
        now = time.time()
        if now - self._last_reap_ts < 30.0:
            return
        pids = self.running_pids()
        if len(pids) <= 1:
            return
        mcp = merge_mcp_settings(self.config.get("mcp"))
        transport = str(mcp.get("transport") or "streamable-http").strip().lower()
        if transport not in _HTTP_TRANSPORTS:
            return
        host = str(mcp.get("http_host") or "127.0.0.1")
        try:
            port = int(mcp.get("http_port") or DEFAULT_MCP_PORT)
        except (TypeError, ValueError):
            port = DEFAULT_MCP_PORT
        killed = self._reap_duplicate_http_adapters(host, port, transport)
        if killed:
            self._last_reap_ts = now
            print(f"[mcp] reaped duplicate adapter PIDs: {', '.join(killed)}")

    # --- panel callbacks ---
    def health_context(self) -> Dict[str, Any]:
        rag = self.config.get("rag_api") or {}
        host = rag.get("host", "127.0.0.1")
        port = int(rag.get("port", DEFAULT_RAG_PORT))
        ep = self.config.get("embedding_profile") or {}
        try:
            chat_port = int(self.config.get("llama_port") or 8081)
        except (TypeError, ValueError):
            chat_port = 8081
        mcp = merge_mcp_settings(self.config.get("mcp"))
        return {
            "api_base": f"http://{host}:{port}",
            "db_path": SHIP_COMPUTER_DB,
            "embeddings_url": str(
                ep.get("embeddings_url") or "http://localhost:8080/embeddings"
            ),
            "api_key": str(rag.get("api_key") or ""),
            "chat_host": str(self.config.get("llama_host") or "localhost"),
            "chat_port": chat_port,
            "mcp_host": str(mcp.get("http_host") or "127.0.0.1"),
            "mcp_port": int(mcp.get("http_port") or DEFAULT_MCP_PORT),
            "mcp_transport": str(mcp.get("transport") or "streamable-http"),
            "webui_host": str(mcp.get("webui_host") or "127.0.0.1"),
            "webui_port": int(mcp.get("webui_port") or DEFAULT_MCP_WEBUI_PORT),
        }

    def on_settings_changed(self, settings: dict) -> None:
        """Merge a panel's partial update so sibling panels never clobber it."""
        block = merge_mcp_settings(self.config.get("mcp"))
        block.update(
            {k: v for k, v in (settings or {}).items() if k in DEFAULT_MCP_SETTINGS}
        )
        merged = merge_mcp_settings(block)
        self.config["mcp"] = merged
        self.config["mcp_http_port"] = int(merged.get("http_port") or DEFAULT_MCP_PORT)
        self._save()

    def refresh_panel(self) -> None:
        if self.panel is not None:
            try:
                self.panel.refresh_status()
            except Exception:
                pass

    def _pid_cwd(self, pid: str) -> str:
        try:
            import psutil

            return str(psutil.Process(int(pid)).cwd())
        except Exception:
            return ""

    def _pid_age_seconds(self, pid: str) -> float:
        try:
            import psutil

            return time.time() - psutil.Process(int(pid)).create_time()
        except Exception:
            return 9999.0

    def _kill_stale_spock_adapters(self, port: int) -> List[str]:
        """Drop this-install Spock-spawned PIDs that never bound :port (not Cursor stdio)."""
        root_fold = _fold(str(ROOT))
        listeners = set(self._pids_listening_on(int(port)))
        killed: List[str] = []
        own_pid = (
            str(self.adapter_proc.pid)
            if self.adapter_proc is not None and self.adapter_proc.poll() is None
            else ""
        )
        for pid in self.running_pids():
            if pid in listeners or pid == own_pid:
                continue
            if self._pid_age_seconds(pid) < 20.0:
                continue
            cwd = _fold(self._pid_cwd(pid))
            if not cwd or root_fold not in cwd:
                continue
            if self._taskkill(pid, tree=False):
                killed.append(pid)
        if killed:
            time.sleep(0.35)
        return killed

    def _spawn_stderr_path(self, pid: int | str | None = None) -> Path:
        if pid and str(pid) not in ("0", ""):
            return ROOT / "logs" / f"mcp-adapter-{pid}.stderr.log"
        return ROOT / "logs" / "mcp-adapter-last.stderr.log"

    def _read_spawn_failure(self, proc: subprocess.Popen, stderr_path: Path) -> str:
        lines: List[str] = []
        if stderr_path.is_file():
            try:
                lines = stderr_path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                pass
        tail = "\n".join(lines[-16:]).strip()
        code = proc.poll()
        base = f"Adapter exited (code {code})." if code is not None else (
            "Adapter started but never opened the HTTP port."
        )
        if tail:
            return f"{base}\n\nStderr/log tail:\n{tail}"
        return (
            f"{base}\n\nSee {ROOT / 'logs' / 'spock-mcp.log'} and {stderr_path}."
        )

    def ensure_http_adapter(self, *, quiet: bool = True) -> bool:
        """Start streamable-http when autostart expects it and :port is down."""
        mcp = merge_mcp_settings(self.config.get("mcp"))
        transport = str(mcp.get("transport") or "streamable-http").strip().lower()
        if transport not in _HTTP_TRANSPORTS:
            return False
        host = str(mcp.get("http_host") or "127.0.0.1")
        try:
            port = int(mcp.get("http_port") or DEFAULT_MCP_PORT)
        except (TypeError, ValueError):
            port = DEFAULT_MCP_PORT
        from spock_mcp_adapter.proc_guard import tcp_open

        if tcp_open(host, port) or self._http_reachable(host, port, transport):
            return True
        self.start_adapter(
            quiet=quiet,
            transport=transport,
            http_host=host,
            http_port=port,
        )
        return tcp_open(host, port) or self._http_reachable(host, port, transport)

    def ensure_http_adapter_async(self, *, quiet: bool = True) -> None:
        """Start HTTP adapter on a worker thread so the Qt UI stays responsive."""
        if self._http_work_busy or self._http_async_pending:
            return
        mcp = merge_mcp_settings(self.config.get("mcp"))
        transport = str(mcp.get("transport") or "streamable-http").strip().lower()
        if transport not in _HTTP_TRANSPORTS:
            return
        host = str(mcp.get("http_host") or "127.0.0.1")
        try:
            port = int(mcp.get("http_port") or DEFAULT_MCP_PORT)
        except (TypeError, ValueError):
            port = DEFAULT_MCP_PORT
        from spock_mcp_adapter.proc_guard import tcp_open

        if tcp_open(host, port) or self._http_reachable(host, port, transport):
            return

        self._http_async_pending = True

        def _work() -> None:
            try:
                self.ensure_http_adapter(quiet=quiet)
            finally:
                self._http_async_pending = False
                QTimer.singleShot(0, self.refresh_panel)

        threading.Thread(target=_work, daemon=True, name="mcp-http-start").start()

    # --- lifecycle ---
    def start_adapter(
        self,
        quiet: bool = False,
        transport: Optional[str] = None,
        http_host: Optional[str] = None,
        http_port: Optional[int] = None,
    ) -> None:
        """Start MCP adapter using saved MCP settings unless overrides are passed."""
        script = self.script_path()
        python_exe = self.python_exe()
        mcp = merge_mcp_settings(self.config.get("mcp"))
        if transport is None or not str(transport).strip():
            transport = str(mcp.get("transport") or "streamable-http")
        if http_host is None or not str(http_host).strip():
            http_host = str(mcp.get("http_host") or "127.0.0.1")
        if http_port is None:
            try:
                http_port = int(mcp.get("http_port") or DEFAULT_MCP_PORT)
            except (TypeError, ValueError):
                http_port = DEFAULT_MCP_PORT

        if not script.is_file():
            if not quiet:
                QMessageBox.critical(
                    self.parent, "MCP adapter", f"Script not found:\n{script}"
                )
            return
        if not python_exe.is_file():
            if not quiet:
                QMessageBox.critical(
                    self.parent, "MCP adapter", f"Python not found:\n{python_exe}"
                )
            return

        deps_ok, deps_detail = _mcp_deps_ok(python_exe)
        if not deps_ok:
            if self.panel is not None:
                try:
                    self.panel.adapter_log.append(deps_detail)
                except Exception:
                    pass
            if not quiet:
                QMessageBox.critical(self.parent, "MCP adapter", deps_detail)
            else:
                print(f"[profile] MCP adapter deps missing: {deps_detail}")
            return

        want_http = (transport or "stdio").strip().lower() in _HTTP_TRANSPORTS
        if want_http and self._http_work_busy:
            if not quiet:
                QMessageBox.information(
                    self.parent,
                    "MCP adapter",
                    "HTTP adapter start already in progress…",
                )
            return
        from contextlib import nullcontext

        from spock_mcp_adapter.proc_guard import exclusive_start, tcp_open

        if want_http:
            self._http_work_busy = True
        try:
            if want_http:
                self._kill_stale_spock_adapters(int(http_port))
                from spock_mcp_adapter.proc_guard import tcp_open as _tcp

                if _tcp(str(http_host), int(http_port)) or self._http_reachable(
                    str(http_host), int(http_port), str(transport)
                ):
                    if not quiet:
                        QMessageBox.information(
                            self.parent,
                            "MCP adapter",
                            f"HTTP MCP adapter already listening on "
                            f"{http_host}:{http_port}",
                        )
                    return
                self._maybe_reap_http_duplicates()

            lock_ctx = exclusive_start("mcp_http") if want_http else nullcontext(True)
            with lock_ctx as locked:
                # Skip a second HTTP copy. One Cursor stdio plus one HTTP is OK;
                # any other this-install PID without a listener is a Start race.
                if want_http:
                    reason = self._http_start_skip_reason(
                        str(http_host), int(http_port), str(transport)
                    )
                    if not reason and not locked:
                        if self._wait_for_http_ready(
                            str(http_host), int(http_port), str(transport), timeout=2.0
                        ):
                            reason = (
                                f"HTTP MCP adapter already listening on "
                                f"{http_host}:{http_port}"
                            )
                    if reason:
                        pids = self.running_pids()
                        if pids:
                            reason += f"\nThis install PID(s): {', '.join(pids)}"
                        self.refresh_panel()
                        if not quiet:
                            show_output_dialog(
                                self.parent,
                                "Start MCP adapter",
                                f"{reason}.\n\nNot spawning another copy.\n\n"
                                f"{self.find_text()}",
                            )
                        else:
                            print(f"[profile] MCP adapter: {reason}; skipped start")
                        return
                else:
                    existing = self.running_pids()
                    if existing:
                        self.refresh_panel()
                        if not quiet:
                            show_output_dialog(
                                self.parent,
                                "Start MCP adapter",
                                "MCP adapter already running for this install.\n\n"
                                f"Existing PID(s): {', '.join(existing)}\n\n"
                                f"{self.find_text()}",
                            )
                        return

                env = os.environ.copy()
                rag = self.config.get("rag_api") or {}
                host = rag.get("host", "127.0.0.1")
                port = int(rag.get("port", DEFAULT_RAG_PORT))
                env["SPOCK_API_BASE_URL"] = f"http://{host}:{port}"
                if rag.get("api_key"):
                    env["SPOCK_API_KEY"] = str(rag["api_key"])
                env["SPOCK_DB_PATH"] = SHIP_COMPUTER_DB
                ep = self.config.get("embedding_profile") or {}
                if ep.get("embeddings_url"):
                    env["SPOCK_EMBEDDINGS_URL"] = str(ep["embeddings_url"])
                env["SPOCK_MCP_LOG_PATH"] = str(ROOT / "logs" / "spock-mcp.log")
                transport = (transport or "stdio").strip().lower()
                if transport in _HTTP_TRANSPORTS:
                    if transport in ("http", "streamable_http"):
                        transport = "streamable-http"
                    env["SPOCK_MCP_TRANSPORT"] = transport
                    env["SPOCK_MCP_HOST"] = (http_host or "127.0.0.1").strip() or "127.0.0.1"
                    port_i = (
                        int(http_port)
                        if http_port is not None
                        else int(
                            mcp.get("http_port")
                            or self.config.get("mcp_http_port")
                            or DEFAULT_MCP_PORT
                        )
                    )
                    env["SPOCK_MCP_PORT"] = str(port_i)
                    self.config["mcp_http_port"] = port_i
                    mcp_block = merge_mcp_settings(self.config.get("mcp"))
                    mcp_block["transport"] = transport
                    mcp_block["http_host"] = env["SPOCK_MCP_HOST"]
                    mcp_block["http_port"] = port_i
                    self.config["mcp"] = mcp_block
                    self._save()
                else:
                    env["SPOCK_MCP_TRANSPORT"] = "stdio"
                try:
                    (ROOT / "logs").mkdir(parents=True, exist_ok=True)
                except OSError:
                    pass

                stderr_path = self._spawn_stderr_path()
                stderr_fh = None
                try:
                    stderr_path.parent.mkdir(parents=True, exist_ok=True)
                    stderr_fh = open(stderr_path, "w", encoding="utf-8", errors="replace")
                except OSError:
                    stderr_fh = None

                creationflags = 0
                if os.name == "nt":
                    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                try:
                    proc = subprocess.Popen(
                        [str(python_exe), "-u", str(script)],
                        cwd=str(ROOT),
                        env=env,
                        stdin=(
                            subprocess.PIPE
                            if env["SPOCK_MCP_TRANSPORT"] == "stdio"
                            else subprocess.DEVNULL
                        ),
                        stdout=subprocess.DEVNULL,
                        stderr=stderr_fh or subprocess.DEVNULL,
                        creationflags=creationflags,
                    )
                except OSError as e:
                    if stderr_fh is not None:
                        stderr_fh.close()
                    if not quiet:
                        QMessageBox.critical(
                            self.parent, "MCP adapter", f"Failed to launch:\n{e}"
                        )
                    else:
                        print(f"[profile] MCP adapter launch failed: {e}")
                    return

                if stderr_fh is not None:
                    stderr_fh.close()

                if proc.poll() is not None:
                    if not quiet:
                        QMessageBox.critical(
                            self.parent,
                            "MCP adapter",
                            "MCP adapter exited immediately after launch.\n"
                            "Install deps: pip install -r requirements-mcp.txt\n"
                            f"Log: {env.get('SPOCK_MCP_LOG_PATH')}",
                        )
                    else:
                        print(
                            "[profile] MCP adapter exited immediately; "
                            f"see {env.get('SPOCK_MCP_LOG_PATH')}"
                        )
                    return

                self.adapter_proc = proc
                http_ready = True
                if want_http:
                    deadline = time.time() + 20.0
                    http_ready = False
                    while time.time() < deadline:
                        if proc.poll() is not None:
                            break
                        if tcp_open(str(http_host), int(http_port)):
                            http_ready = True
                            break
                        if self._http_reachable(
                            str(http_host), int(http_port), str(transport)
                        ):
                            http_ready = True
                            break
                        time.sleep(0.2)
                    if not http_ready and proc.poll() is None:
                        http_ready = (
                            tcp_open(str(http_host), int(http_port))
                            or self._http_reachable(
                                str(http_host), int(http_port), str(transport)
                            )
                        )
                    if not http_ready:
                        fail = self._read_spawn_failure(
                            proc, self._spawn_stderr_path(proc.pid)
                        )
                        try:
                            if proc.poll() is None:
                                proc.terminate()
                                proc.wait(timeout=2)
                        except Exception:
                            try:
                                proc.kill()
                            except Exception:
                                pass
                        self.adapter_proc = None
                        self.refresh_panel()
                        if not quiet:
                            QMessageBox.critical(
                                self.parent,
                                "MCP adapter",
                                "HTTP adapter did not open the port.\n\n"
                                f"{fail}\n\n"
                                "Cursor stdio copies (cwd ≠ repo) do not serve "
                                f"http://{http_host}:{http_port}/mcp — only "
                                "streamable-http from this panel does.",
                            )
                        else:
                            print(f"[profile] MCP adapter failed to bind: {fail}")
                        return
                else:
                    time.sleep(0.8)

            find_output = self.find_text()
            self.refresh_panel()
            if quiet:
                print(
                    f"[profile] MCP adapter started "
                    f"({env.get('SPOCK_MCP_TRANSPORT')} "
                    f"{env.get('SPOCK_MCP_HOST', '')}:{env.get('SPOCK_MCP_PORT', '')})"
                )
                return

            mcp_port = env.get("SPOCK_MCP_PORT", str(DEFAULT_MCP_PORT))
            mcp_host = env.get("SPOCK_MCP_HOST", "127.0.0.1")
            if env["SPOCK_MCP_TRANSPORT"] == "stdio":
                snippet = (
                    "{\n"
                    '  "mcpServers": {\n'
                    '    "spock-to-bridge": {\n'
                    f'      "command": "{python_exe.as_posix()}",\n'
                    f'      "args": ["-u", "{script.as_posix()}"]\n'
                    "    }\n"
                    "  }\n"
                    "}"
                )
                body = (
                    "MCP adapter launch requested (stdio).\n\n"
                    f"PID: {proc.pid}\n"
                    f'Command: "{python_exe}" -u "{script}"\n\n'
                    "Cursor/OpenCode use mcp.json (stdio).\n"
                    "Example mcp.json entry:\n"
                    f"{snippet}\n\n"
                    f"Auto-check:\n{find_output}"
                )
            else:
                url_mcp = f"http://{mcp_host}:{mcp_port}/mcp"
                url_sse = f"http://{mcp_host}:{mcp_port}/sse"
                body = (
                    "MCP adapter launch requested (HTTP for llama.cpp WebUI).\n\n"
                    f"PID: {proc.pid}\n"
                    f"Transport: {env['SPOCK_MCP_TRANSPORT']}\n\n"
                    "In llama.cpp browser MCP dialog, set Server URL to:\n"
                    f"  {url_mcp}\n"
                    f"(SSE fallback: {url_sse})\n\n"
                    "Tips:\n"
                    "1. CORS is enabled on this HTTP adapter\n"
                    "2. Optional: llama.cpp WebUI → Start --ui-mcp-proxy\n"
                    "3. Prefer 127.0.0.1; toggle the server ON\n"
                    "4. Run → START RAG API so spock_ask works\n"
                    "5. Tools: spock_search_kb, spock_ask, spock_health, spock_llmfit_fit, …\n\n"
                    f"Auto-check:\n{find_output}"
                )
            show_output_dialog(self.parent, "Start MCP adapter", body)
            if self.panel is not None:
                try:
                    self.panel.adapter_log.append(body)
                    self.panel.refresh_status()
                except Exception:
                    pass
        finally:
            if want_http:
                self._http_work_busy = False

    def _wait_for_http_ready(
        self,
        host: str,
        port: int,
        transport: str,
        timeout: float = 10.0,
    ) -> bool:
        """True when :port answers or every peer PID exited."""
        from spock_mcp_adapter.proc_guard import tcp_open

        deadline = time.time() + max(0.5, float(timeout))
        while time.time() < deadline:
            if self._http_reachable(host, port, transport) or tcp_open(host, port):
                return True
            if not self.running_pids():
                return False
            time.sleep(0.25)
        return self._http_reachable(host, port, transport) or tcp_open(host, port)

    def _reap_duplicate_http_adapters(
        self, host: str, port: int, transport: str
    ) -> List[str]:
        """Kill extra Spock-spawned HTTP adapters; keep the PID bound on :port."""
        root_fold = _fold(str(ROOT))
        pids = self.running_pids()
        if len(pids) <= 1:
            return []
        listeners = self._pids_listening_on(port)
        if len(listeners) == 1:
            keep = listeners[0]
        elif listeners:
            keep = listeners[0]
        elif self._http_reachable(host, port, transport):
            return []
        else:
            return []
        killed: List[str] = []
        for pid in pids:
            if pid == keep:
                continue
            cwd = _fold(self._pid_cwd(pid))
            if not cwd or root_fold not in cwd:
                continue
            if self._taskkill(pid, tree=False):
                killed.append(pid)
        if killed:
            time.sleep(0.35)
        return killed

    def _http_start_skip_reason(
        self, host: str, port: int, transport: str
    ) -> str:
        """Why Start must not spawn another HTTP copy. Empty = allowed."""
        if self._http_reachable(host, port, transport):
            return f"HTTP MCP adapter already listening on {host}:{port}"
        from spock_mcp_adapter.proc_guard import tcp_open

        if tcp_open(host, port):
            return f"port {host}:{port} already in use"
        bound = self._pids_listening_on(int(port))
        if bound:
            return (
                "HTTP MCP adapter already bound on "
                f"{host}:{port} (PIDs {', '.join(bound)})"
            )
        if self.adapter_proc is not None and self.adapter_proc.poll() is None:
            return f"HTTP MCP adapter already started (PID {self.adapter_proc.pid})"

        existing = self.running_pids()
        if not existing:
            return ""

        if self._wait_for_http_ready(host, port, transport, timeout=1.0):
            return f"HTTP MCP adapter already listening on {host}:{port}"

        http_pids = self._http_pids()
        if http_pids:
            return (
                "HTTP MCP adapter already running (PIDs "
                f"{', '.join(http_pids)})"
            )

        # No listener on :port — remaining PIDs are Cursor stdio copies or a
        # failed bind. HTTP spawn is allowed (stdio does not hold :8765).
        return ""

    def _http_reachable(self, host: str, port: int, transport: str) -> bool:
        try:
            from spock_health_report import probe_mcp_adapter

            info = probe_mcp_adapter(
                host, port, transport=transport or "streamable-http", timeout=1.0
            )
            return bool(info.get("reachable"))
        except Exception:
            return False

    def _pids_listening_on(self, port: int) -> List[str]:
        """This-install adapter PIDs with a LISTEN socket on port (HTTP, not stdio)."""
        found: List[str] = []
        ours = {int(p) for p in self.running_pids() if str(p).isdigit()}
        if not ours:
            return found
        try:
            import psutil
        except ImportError:
            return found
        try:
            port_i = int(port)
        except (TypeError, ValueError):
            return found
        for pid in sorted(ours):
            try:
                proc = psutil.Process(pid)
                conns = proc.net_connections(kind="inet")
            except Exception:
                continue
            for conn in conns or []:
                try:
                    laddr = conn.laddr
                    status = str(getattr(conn, "status", "") or "")
                    if not laddr:
                        continue
                    if int(getattr(laddr, "port", 0) or 0) != port_i:
                        continue
                    if status.upper() in ("LISTEN", "LISTENING", ""):
                        found.append(str(pid))
                        break
                except Exception:
                    continue
        return found

    def _http_pids(self) -> List[str]:
        env_hits = [
            pid
            for pid in self.running_pids()
            if _mcp_transport_for_pid(pid) in _HTTP_TRANSPORTS
        ]
        mcp = merge_mcp_settings(self.config.get("mcp"))
        try:
            port = int(mcp.get("http_port") or DEFAULT_MCP_PORT)
        except (TypeError, ValueError):
            port = DEFAULT_MCP_PORT
        bound = self._pids_listening_on(port)
        # Env is often unreadable on Windows; LISTEN sockets are the source of truth.
        return list(dict.fromkeys(env_hits + bound))

    def _taskkill(self, pid: str, *, tree: bool = True) -> bool:
        if os.name != "nt":
            try:
                import signal

                import psutil

                proc = psutil.Process(int(pid))
                if tree:
                    for child in proc.children(recursive=True):
                        try:
                            child.send_signal(signal.SIGTERM)
                        except (psutil.Error, ProcessLookupError):
                            pass
                proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=2)
                except psutil.TimeoutExpired:
                    proc.kill()
                return True
            except Exception:
                try:
                    import signal as _signal

                    os.kill(int(pid), _signal.SIGTERM)
                    return True
                except Exception:
                    return False
        try:
            args = ["taskkill", "/PID", str(pid), "/F"]
            if tree:
                args.insert(2, "/T")
            p = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return p.returncode == 0
        except Exception:
            return False

    def kill_processes(self) -> List[str]:
        """Stop every this-install mcp_spock_server.py (HTTP and stdio)."""
        killed: List[str] = []
        if self.adapter_proc is not None:
            try:
                if self.adapter_proc.poll() is None:
                    pid = str(self.adapter_proc.pid)
                    self.adapter_proc.terminate()
                    try:
                        self.adapter_proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.adapter_proc.kill()
                    killed.append(pid)
            except Exception:
                pass
            self.adapter_proc = None

        for pid in self.running_pids():
            if pid in killed:
                continue
            if self._taskkill(pid):
                killed.append(pid)
        time.sleep(0.4)
        for pid in self.running_pids():
            if pid in killed:
                continue
            if self._taskkill(pid):
                killed.append(pid)
        return killed

    def stop_adapter(self) -> None:
        killed = self.kill_processes()
        leftover = self.running_pids()
        self.refresh_panel()
        if leftover:
            QMessageBox.warning(
                self.parent,
                "Stop MCP adapter",
                "Tried to stop this install's MCP adapter PID(s): "
                f"{', '.join(killed) or '(none)'}\n\n"
                f"Still running: {', '.join(leftover)}\n"
                "Cursor may immediately respawn stdio adapters from mcp.json.",
            )
            return
        if killed:
            QMessageBox.information(
                self.parent,
                "Stop MCP adapter",
                "Stopped this install's MCP adapter PID(s): "
                f"{', '.join(killed)}\n\n"
                "Cursor may respawn a stdio adapter from mcp.json; "
                "that is one copy, not a Spock duplicate.",
            )
            return
        QMessageBox.information(
            self.parent,
            "Stop MCP adapter",
            f"No running {ADAPTER_SCRIPT_NAME} for this install.",
        )

    def find_adapter(self) -> None:
        try:
            text = self.find_text(ADAPTER_SCRIPT_NAME)
        except Exception as e:
            QMessageBox.critical(self.parent, "Find MCP adapter", str(e))
            return
        self.refresh_panel()
        show_output_dialog(self.parent, "Find MCP adapter", text)
