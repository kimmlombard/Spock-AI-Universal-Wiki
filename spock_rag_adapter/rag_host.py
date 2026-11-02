"""Start / stop the Spock RAG API subprocess for the standalone window."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from PyQt6.QtWidgets import QMessageBox, QWidget

from spock_mcp_adapter.proc_guard import (
    exclusive_start,
    kill_script_pids,
    pids_running_script,
    tcp_open,
)
from spock_rag_adapter.paths import RAG_SCRIPT, ROOT

_SPAWNED: list[subprocess.Popen] = []


def rag_bind(config: Optional[Dict[str, Any]] = None) -> Tuple[str, int]:
    rag = (config or {}).get("rag_api") if isinstance(config, dict) else {}
    rag = rag or {}
    host = str(rag.get("host") or "127.0.0.1").strip() or "127.0.0.1"
    try:
        port = int(rag.get("port") or 8090)
    except (TypeError, ValueError):
        port = 8090
    return host, port


def rag_url(host: str = "127.0.0.1", port: int = 8090) -> str:
    return f"http://{host}:{int(port)}"


def is_rag_up(
    host: str = "127.0.0.1",
    port: int = 8090,
    *,
    timeout: float = 1.5,
) -> bool:
    url = f"{rag_url(host, port)}/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= int(resp.status) < 300
    except Exception:
        return False


class RagAdapterHost:
    """Own RAG API lifecycle for EmbeddingProfilePanel callbacks."""

    def __init__(
        self,
        config: Dict[str, Any],
        save_config: Callable[[], None],
        *,
        python_exe: Optional[Path] = None,
        parent: Optional[QWidget] = None,
    ):
        self.config = config
        self._save_config = save_config
        self.parent = parent
        self.panel = None
        self.python_exe = python_exe or self._default_python()

    def _default_python(self) -> Path:
        venv_py = ROOT / ".venv" / "Scripts" / "python.exe"
        if venv_py.is_file():
            return venv_py
        return Path(sys.executable)

    def _log(self, msg: str) -> None:
        if self.panel is not None and hasattr(self.panel, "activity_log"):
            try:
                self.panel.activity_log.append(msg)
            except Exception:
                pass

    def refresh_panel(self) -> None:
        if self.panel is None:
            return
        host, port = rag_bind(self.config)
        base = rag_url(host, port)
        if is_rag_up(host, port):
            self.panel.set_rag_running(True, f"{base}/v1")
        else:
            self.panel.set_rag_running(False)

    def on_profile_applied(self, profile: dict) -> None:
        from WarpCore.config_defaults import merge_embedding_profile
        from spock_rag_adapter.embedding_utils import write_embedding_env

        self.config["embedding_profile"] = merge_embedding_profile(profile)
        if self.panel is not None:
            self.config["rag_api"] = self.panel.collect_rag_api()
        write_embedding_env(self.config["embedding_profile"])
        self._save_config()
        self._log("Embedding profile saved to ship_computer.db + .env")

    def start_rag(self) -> None:
        if self.panel is None:
            return
        self.config["rag_api"] = self.panel.collect_rag_api()
        self.config.setdefault("rag_api", {})["enabled"] = True
        self._save_config()

        host, port = rag_bind(self.config)
        url = rag_url(host, port)
        script = RAG_SCRIPT
        py = self.python_exe

        if not script.is_file():
            QMessageBox.critical(self.parent, "RAG API", f"Script not found:\n{script}")
            return
        if not py.is_file():
            QMessageBox.critical(self.parent, "RAG API", f"Python not found:\n{py}")
            return

        self._log(f"Starting RAG API at {url} …")

        if is_rag_up(host, port):
            self._log(f"Already running at {url}")
            self.panel.set_rag_running(True, f"{url}/v1")
            return

        with exclusive_start("rag_api") as locked:
            existing = pids_running_script(script)
            if existing or tcp_open(str(host), int(port)):
                deadline = time.time() + 8.0
                while time.time() < deadline:
                    if is_rag_up(host, port, timeout=1.0):
                        self._log(f"RAG API ready at {url}")
                        self.panel.set_rag_running(True, f"{url}/v1")
                        return
                    time.sleep(0.4)
                if existing:
                    self._log(f"RAG API starting (PIDs {', '.join(str(p) for p in existing)})")
                    self.panel.set_rag_running(True, f"{url}/v1")
                    return
            if not locked:
                self._log("Another window is starting the RAG API — waiting…")
                QMessageBox.information(
                    self.parent,
                    "RAG API",
                    "Another process is starting the RAG API. Retry in a few seconds.",
                )
                return

            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
            try:
                proc = subprocess.Popen(
                    [str(py), "-u", str(script)],
                    cwd=str(ROOT),
                    env=env,
                    creationflags=creationflags,
                )
                _SPAWNED.append(proc)
            except OSError as e:
                self._log(f"Failed to launch RAG API: {e}")
                QMessageBox.critical(self.parent, "RAG API", f"Failed to launch:\n{e}")
                return

            deadline = time.time() + 12.0
            while time.time() < deadline:
                if is_rag_up(host, port, timeout=1.0):
                    self._log(f"RAG API running at {url}/v1 · Web UI {url}/")
                    self.panel.set_rag_running(True, f"{url}/v1")
                    return
                if proc.poll() is not None:
                    break
                time.sleep(0.4)

        if is_rag_up(host, port):
            self.panel.set_rag_running(True, f"{url}/v1")
            return

        self._log(f"Started _start_rag_api.py but {url}/health is not answering yet")
        QMessageBox.warning(
            self.parent,
            "RAG API",
            f"RAG API process started but {url}/health is not answering yet.\n\n"
            "Check the RAG console window for errors (embeddings :8080, chat :8081).",
        )

    def stop_rag(self) -> None:
        host, port = rag_bind(self.config)
        stopped = 0
        for proc in list(_SPAWNED):
            if proc.poll() is not None:
                continue
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                stopped += 1
            except Exception:
                pass
        _SPAWNED.clear()
        stopped += len(kill_script_pids(RAG_SCRIPT))

        self.config.setdefault("rag_api", {})["enabled"] = False
        self._save_config()
        if self.panel is not None:
            self.panel.set_rag_running(False)
        if stopped:
            self._log(f"Stopped RAG API ({stopped} process(es))")
        else:
            self._log("RAG API was not running")

        if is_rag_up(host, port):
            self._log(f"Note: something still responds on {rag_url(host, port)}/health")
