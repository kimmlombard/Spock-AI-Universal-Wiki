"""Start / detect the Spock RAG API so a profile load can bring :8090 up.

Navigation Station can host RagApiServer in-process. The hub and other windows
do not, so they spawn ``_start_rag_api.py`` in a new console (same pattern as
the llama.cpp WebUI launcher).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from typing import Any, Dict, Optional, Tuple

from spock_shell.paths import ROOT
from spock_shell.proc_guard import exclusive_start, pids_running_script

_SPAWNED: list = []


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


def spawn_rag_api(
    config: Optional[Dict[str, Any]] = None,
    *,
    wait_s: float = 8.0,
) -> Tuple[bool, str]:
    """Launch ``_start_rag_api.py`` if this install is not already serving :8090."""
    host, port = rag_bind(config)
    url = rag_url(host, port)
    script = ROOT / "_start_rag_api.py"
    with exclusive_start("rag_api") as locked:
        if is_rag_up(host, port):
            return True, f"already running at {url}"
        existing = pids_running_script(script)
        if existing:
            deadline = time.time() + max(0.5, float(wait_s))
            while time.time() < deadline:
                if is_rag_up(host, port, timeout=1.0):
                    return True, f"already running at {url}"
                time.sleep(0.4)
            pids = ", ".join(str(p) for p in existing)
            return True, f"already starting (PIDs {pids}); not spawning another"
        if not locked:
            if is_rag_up(host, port):
                return True, f"already running at {url}"
            return False, "another window is starting the RAG API"
        if not script.is_file():
            return False, f"missing {script}"
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]
        try:
            proc = subprocess.Popen(
                [sys.executable, "-u", str(script)],
                cwd=str(ROOT),
                env=os.environ.copy(),
                creationflags=creationflags,
            )
            _SPAWNED.append(proc)
        except OSError as e:
            return False, str(e)
        deadline = time.time() + max(0.5, float(wait_s))
        while time.time() < deadline:
            if is_rag_up(host, port, timeout=1.0):
                return True, f"Started RAG API at {url}"
            time.sleep(0.4)
        return False, f"Started _start_rag_api.py but {url}/health is not answering yet"


def stop_spawned_rag() -> int:
    """Terminate RAG API processes this process started via spawn_rag_api()."""
    stopped = 0
    for proc in list(_SPAWNED):
        if proc.poll() is not None:
            continue
        try:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
            stopped += 1
        except Exception:
            pass
    _SPAWNED.clear()
    return stopped
