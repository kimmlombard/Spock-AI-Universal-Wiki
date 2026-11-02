"""Avoid duplicate sidecar processes (MCP HTTP) across windows."""

from __future__ import annotations

import os
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Union

from spock_mcp_adapter.paths import ROOT

Pathish = Union[str, Path]


def fold_path(text: str) -> str:
    return os.path.normcase(str(text or "")).replace("\\", "/")


def pids_running_script(script: Pathish) -> List[int]:
    """PIDs whose command line contains this install's script path."""
    raw = Path(script)
    try:
        marker = fold_path(str(raw.resolve() if raw.exists() else raw))
    except OSError:
        marker = fold_path(str(raw))
    found: List[int] = []
    try:
        import psutil
    except ImportError:
        return found
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = [str(c) for c in (proc.info.get("cmdline") or [])]
            if marker not in fold_path(" ".join(cmdline)):
                continue
            found.append(int(proc.info["pid"]))
        except (TypeError, ValueError):
            continue
        except Exception:
            continue
    found.sort()
    return found


def tcp_open(host: str, port: int, timeout: float = 0.4) -> bool:
    host = (host or "127.0.0.1").strip() or "127.0.0.1"
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def kill_script_pids(script: Pathish) -> List[int]:
    """Terminate every PID running this install's script (Windows /taskkill)."""
    killed: List[int] = []
    for pid in pids_running_script(script):
        try:
            if os.name == "nt":
                p = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if p.returncode == 0:
                    killed.append(pid)
            else:
                os.kill(pid, 15)
                killed.append(pid)
        except Exception:
            continue
    return killed


@contextmanager
def exclusive_start(name: str, timeout: float = 20.0) -> Iterator[bool]:
    """Named inter-process lock. Yields True if this caller holds it."""
    path = ROOT / "logs" / f".{name}.startlock"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    try:
        fh = open(path, "a+b")
    except OSError:
        yield False
        return
    locked = False
    deadline = time.time() + max(1.0, float(timeout))
    try:
        try:
            fh.seek(0, os.SEEK_END)
            if fh.tell() == 0:
                fh.write(b"x")
                fh.flush()
        except OSError:
            pass
        while True:
            try:
                fh.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError:
                if time.time() >= deadline:
                    break
                time.sleep(0.15)
        yield locked
    finally:
        if locked:
            try:
                fh.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        try:
            fh.close()
        except OSError:
            pass
