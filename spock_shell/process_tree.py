"""Process-tree terminate helpers (Windows-safe Stop Scan / Bringup stop)."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Iterable, Optional

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore


def terminate_process_tree(pid: int, timeout: float = 8.0) -> None:
    """Terminate ``pid`` and all descendants; escalate to kill if needed."""
    if pid <= 0:
        return
    if psutil is None:
        try:
            os.kill(pid, 15)
        except OSError:
            pass
        return
    try:
        parent = psutil.Process(pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return
    try:
        kids = parent.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        kids = []
    targets = list(kids)
    try:
        # Re-resolve parent in case it exited while listing children.
        targets.append(psutil.Process(pid))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    for child in kids:
        try:
            child.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    try:
        parent.terminate()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    if not targets:
        return
    _, alive = psutil.wait_procs(targets, timeout=timeout)
    for proc in alive:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def _norm(s: str) -> str:
    return os.path.normcase(os.path.normpath(s or "")).replace("\\", "/")


def iter_wiki_scan_pids(root: Path) -> Iterable[int]:
    """PIDs whose cmdline looks like wiki_agent / universal extractor for ``root``."""
    if psutil is None:
        return
    root_n = _norm(str(root))
    markers = ("wiki_agent.py", "starfleet_universal_extractor.py")
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmd_list = proc.info.get("cmdline") or []
            cmd = " ".join(str(x) for x in cmd_list)
        except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError):
            continue
        if not cmd:
            continue
        folded = _norm(cmd)
        if root_n not in folded:
            continue
        if not any(m in folded for m in markers):
            continue
        yield int(proc.info["pid"])


def cancel_wiki_queue(db_path: Path | str, reason: str = "Stopped by user") -> int:
    """Mark pending/running agent_queue rows failed so bootstrap can re-queue."""
    path = Path(db_path)
    if not path.is_file():
        return 0
    now = int(time.time())
    try:
        conn = sqlite3.connect(str(path), timeout=30)
        try:
            cur = conn.execute(
                """
                UPDATE agent_queue
                SET status='failed',
                    finished_at=?,
                    error_msg=?
                WHERE status IN ('pending', 'running')
                """,
                (now, (reason or "Stopped by user")[:2000]),
            )
            conn.commit()
            return int(cur.rowcount or 0)
        finally:
            conn.close()
    except sqlite3.Error:
        return 0


def clear_wiki_agent_lockfiles(root: Path) -> None:
    root = Path(root)
    for p in (
        root / "wiki_agent.pid",
        root / "wiki_agent_session.json",
        root / "logs" / "wiki_ingest_progress.json",
    ):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass
    try:
        import _warpcore_path

        _warpcore_path.ensure()
        from WarpCore import settings_store

        db = root / "ship_computer.db"
        if db.is_file():
            settings_store.delete(str(db), "wiki_agent.session")
    except Exception:
        pass


def stop_wiki_scan(
    root: Path,
    *,
    proc_pid: Optional[int] = None,
    db_path: Optional[Path | str] = None,
) -> dict:
    """Kill wiki_agent + extractor tree, cancel queue, clear lock/progress files."""
    root = Path(root)
    db = Path(db_path) if db_path else root / "ship_computer.db"
    pids: set[int] = set()
    if proc_pid and int(proc_pid) > 0:
        pids.add(int(proc_pid))
    lock = root / "wiki_agent.pid"
    if lock.is_file():
        try:
            pids.add(int(lock.read_text(encoding="utf-8").strip()))
        except (ValueError, OSError):
            pass
    pids.update(iter_wiki_scan_pids(root))
    pids.discard(0)
    pids.discard(os.getpid())

    for pid in sorted(pids):
        try:
            terminate_process_tree(pid)
        except Exception:
            pass

    cancelled = cancel_wiki_queue(db, reason="Stopped by user (Stop Scan)")
    clear_wiki_agent_lockfiles(root)
    return {"killed_pids": sorted(pids), "queue_cancelled": cancelled}
