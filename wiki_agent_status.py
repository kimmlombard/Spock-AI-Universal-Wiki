#!/usr/bin/env python3
"""Ship Computer / Wiki Agent progress report.

Reads ship_computer.db + optional wiki_agent_session.json (written when the
agent acquires its lock) so elapsed time reflects the live session, not a
stale last_done − first_start window.

Onboarding may be one queue row with many ``paths`` (folder ingest). Progress,
rate, and ETA count those files, not queue rows. While a batch runs, the
extractor writes ``logs/wiki_ingest_progress.json`` so Embedding Status can
show mid-job flushes (otherwise a 2k-file job stays at 0% until done). Work
window is busy time on onboarding jobs so idle watcher time does not deflate
files/s.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get("SHIP_COMPUTER_DB", ROOT / "ship_computer.db"))
SESSION_PATH = ROOT / "wiki_agent_session.json"
LOCK_PATH = ROOT / "wiki_agent.pid"
PROGRESS_PATH = Path(
    os.environ.get(
        "SPOCK_INGEST_PROGRESS",
        str(ROOT / "logs" / "wiki_ingest_progress.json"),
    )
)


def fmt_dur(sec: float | None) -> str:
    if sec is None or sec < 0:
        return "N/A"
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def fmt_ts(epoch: int | None) -> str:
    if not epoch:
        return "—"
    return datetime.fromtimestamp(int(epoch)).strftime("%Y-%m-%d %H:%M:%S")


def load_session() -> dict | None:
    # Prefer WarpCore Spock_Console session; fall back to legacy JSON.
    try:
        import _warpcore_path

        _warpcore_path.ensure()
        from WarpCore import settings_store

        if str(DB).lower().endswith("ship_computer.db"):
            data = settings_store.get(str(DB), "wiki_agent.session")
            if isinstance(data, dict) and data:
                return data
    except Exception:
        pass
    if not SESSION_PATH.exists():
        return None
    try:
        data = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_ingest_progress(
    now: int | None = None, *, agent_alive: bool = True
) -> dict | None:
    """Live mid-batch counters from starfleet_universal_extractor."""
    if not PROGRESS_PATH.exists():
        return None
    try:
        data = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    now = int(now or time.time())
    updated = int(data.get("updated_at") or 0)
    # Ignore stale leftovers from a killed extractor (>30 min quiet).
    if updated and (now - updated) > 1800:
        return None
    # Finished batches clear the file; if a done snapshot remains, hide it when idle.
    if str(data.get("phase") or "") == "done" and not agent_alive:
        return None
    if not agent_alive:
        return None
    total = int(data.get("total") or 0)
    if total <= 0:
        return None
    return data


def is_user_cancelled(error_msg: str | None) -> bool:
    err = (error_msg or "").strip().lower()
    return err.startswith("stopped by user")


def pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def onboarding_file_count(payload_json: str | None) -> int:
    """Files represented by one onboarding queue row (batch ``paths`` or one ``path``)."""
    try:
        data = json.loads(payload_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return 1
    if not isinstance(data, dict):
        return 1
    paths = data.get("paths")
    if isinstance(paths, list) and paths:
        return max(1, len(paths))
    if data.get("path"):
        return 1
    return 1


def work_units(skill_name: str, payload_json: str | None) -> int:
    """Ingest files for onboarding; other skills stay 1 queue job."""
    if str(skill_name or "") == "onboarding":
        return onboarding_file_count(payload_json)
    return 1


def _connect():
    try:
        import _warpcore_path

        _warpcore_path.ensure()
        from WarpCore.db import connect as _wc_connect

        conn = _wc_connect(str(DB), timeout=30.0)
    except Exception:
        conn = sqlite3.connect(str(DB), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    return conn


def agent_alive(session: dict | None) -> bool:
    if session:
        pid = int(session.get("pid") or 0)
        if pid and pid_running(pid):
            return True
    if LOCK_PATH.exists():
        try:
            pid = int(LOCK_PATH.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            pid = 0
        return bool(pid and pid_running(pid))
    return False


def main() -> int:
    if not DB.exists():
        print(f"Database not found: {DB}")
        return 1

    now = int(time.time())
    session = load_session()
    alive = agent_alive(session)

    conn = _connect()

    jobs_pending = conn.execute(
        "SELECT count(*) FROM agent_queue WHERE status='pending'"
    ).fetchone()[0]
    jobs_running = conn.execute(
        "SELECT count(*) FROM agent_queue WHERE status='running'"
    ).fetchone()[0]
    jobs_active = jobs_pending + jobs_running

    # Prefer wiki_agent session start; else earliest pending/running created_at;
    # else last 24h (idle lookback — labeled as such).
    scope = "session"
    if session and session.get("started_at"):
        run_start = int(session["started_at"])
        scope = "agent session"
    else:
        row = conn.execute(
            "SELECT MIN(created_at) FROM agent_queue "
            "WHERE status IN ('pending','running')"
        ).fetchone()
        if row and row[0]:
            run_start = int(row[0])
            scope = "active queue"
        else:
            run_start = now - 86400
            scope = "last 24h (idle)"

    scope_rows = conn.execute(
        """
        SELECT skill_name, status, payload_json, started_at, finished_at,
               created_at, error_msg
        FROM agent_queue
        WHERE status IN ('pending','running')
           OR (status IN ('done','failed') AND finished_at >= ?)
        """,
        (run_start,),
    ).fetchall()

    files_pending = files_running = files_done = files_failed = files_cancelled = 0
    jobs_done = jobs_failed = jobs_cancelled = 0
    by_skill: dict[str, dict[str, int]] = {}
    for r in scope_rows:
        skill = str(r["skill_name"] or "")
        status = str(r["status"] or "")
        units = work_units(skill, r["payload_json"])
        cancelled = status == "failed" and is_user_cancelled(r["error_msg"])
        slot = by_skill.setdefault(
            skill,
            {
                "pending": 0,
                "running": 0,
                "done": 0,
                "failed": 0,
                "cancelled": 0,
                "files": 0,
            },
        )
        if cancelled:
            slot["cancelled"] += 1
        elif status in slot:
            slot[status] += 1
        if skill == "onboarding":
            if cancelled:
                files_cancelled += units
            else:
                slot["files"] += units
                if status == "pending":
                    files_pending += units
                elif status == "running":
                    files_running += units
                elif status == "done":
                    files_done += units
                elif status == "failed":
                    files_failed += units
        if status == "done":
            jobs_done += 1
        elif cancelled:
            jobs_cancelled += 1
        elif status == "failed":
            jobs_failed += 1

    ingest_active = files_pending + files_running
    # Stop Scan aborts are not ingest failures — keep them out of the % bar.
    ingest_total = ingest_active + files_done + files_failed
    jobs_total = jobs_pending + jobs_running + jobs_done + jobs_failed

    # Mid-batch progress from extractor (one big onboarding job otherwise stays 0%).
    progress = load_ingest_progress(now, agent_alive=alive)
    progress_note = ""
    if progress and files_running > 0:
        mid_total = int(progress.get("total") or 0)
        mid_done = int(progress.get("processed") or 0)
        # Match running onboarding payload size (allow small drift if files vanished).
        if mid_total > 0 and abs(mid_total - files_running) <= max(8, files_running // 50):
            credited = max(0, min(mid_done, mid_total))
            files_done += credited
            files_running = max(0, mid_total - credited)
            ingest_active = files_pending + files_running
            ingest_total = ingest_active + files_done + files_failed
            phase = str(progress.get("phase") or "")
            progress_note = (
                f"  Live flush: {credited}/{mid_total} "
                f"(ready {progress.get('ready', 0)}, "
                f"skipped {progress.get('skipped', 0)}, "
                f"failed {progress.get('failed', 0)}"
                + (f", phase {phase}" if phase else "")
                + ")"
            )

    # Progress bar is file-level when this session had onboarding; else queue jobs.
    if ingest_total:
        done = files_done
        total = ingest_total
        pending = files_pending
        running = files_running
        failed = files_failed
        unit_label = "files"
    else:
        done = jobs_done
        total = jobs_total
        pending = jobs_pending
        running = jobs_running
        failed = jobs_failed
        unit_label = "jobs"

    pct = (done * 100 // total) if total else 0
    bar_len = 30
    filled = int(bar_len * done / total) if total else 0
    bar = "█" * filled + "░" * (bar_len - filled)

    docs = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
    embedded = conn.execute(
        "SELECT count(*) FROM documents WHERE embedding IS NOT NULL"
    ).fetchone()[0]
    missing_emb = docs - embedded

    # Wall-clock session elapsed (what the user asked for)
    session_elapsed = None
    session_elapsed_note = ""
    if session and session.get("started_at"):
        session_elapsed = max(0, now - int(session["started_at"]))
    elif alive and jobs_active:
        # No session file (older agent) — approximate from first start in scope
        fs = conn.execute(
            "SELECT MIN(started_at) FROM agent_queue "
            "WHERE started_at IS NOT NULL AND started_at >= ?",
            (run_start,),
        ).fetchone()[0]
        if fs:
            session_elapsed = max(0, now - int(fs))
            session_elapsed_note = " (approx — restart agent for exact session clock)"
    elif not alive and session and session.get("started_at"):
        session_elapsed = max(0, now - int(session["started_at"]))
        session_elapsed_note = " (stale session file)"

    # Throughput on ingest files (batch onboarding), not queue-row count.
    onboard_job_secs: list[float] = []
    for r in scope_rows:
        if is_user_cancelled(r["error_msg"]):
            continue
        if (
            r["skill_name"] == "onboarding"
            and r["status"] in ("done", "failed")
            and r["started_at"]
            and r["finished_at"]
            and int(r["finished_at"]) > int(r["started_at"])
        ):
            onboard_job_secs.append(float(int(r["finished_at"]) - int(r["started_at"])))

    if ingest_total:
        timed = [
            r
            for r in scope_rows
            if r["skill_name"] == "onboarding" and not is_user_cancelled(r["error_msg"])
        ]
    else:
        timed = [r for r in scope_rows if not is_user_cancelled(r["error_msg"])]
    starts = [int(r["started_at"]) for r in timed if r["started_at"]]
    finishes = [
        int(r["finished_at"])
        for r in timed
        if r["status"] in ("done", "failed") and r["finished_at"]
    ]
    first_start = min(starts) if starts else None
    last_done = max(finishes) if finishes else None

    last_queue_finish = conn.execute(
        "SELECT MAX(finished_at) FROM agent_queue "
        "WHERE status IN ('done','failed') AND finished_at >= ?",
        (run_start,),
    ).fetchone()[0]

    rate_str = "N/A"
    eta_str = "N/A"
    work_elapsed = None
    still_working = ingest_active if ingest_total else jobs_active
    if ingest_total:
        busy = sum(onboard_job_secs)
        for r in scope_rows:
            if (
                r["skill_name"] == "onboarding"
                and r["status"] == "running"
                and r["started_at"]
            ):
                busy += max(0, now - int(r["started_at"]))
        work_elapsed = max(1, int(busy)) if busy else None
    elif first_start:
        work_elapsed = (
            max(1, now - int(first_start))
            if still_working
            else (max(1, int(last_done) - int(first_start)) if last_done else None)
        )
    if work_elapsed and done > 0:
        rate = done / work_elapsed
        if unit_label == "files":
            rate_str = f"{rate:.2f} files/s ({rate * 60:.0f} files/min)"
        else:
            rate_str = f"{rate:.2f}/s ({rate * 60:.0f}/min)"
        remaining = pending + running
        if rate > 0 and remaining > 0:
            eta_str = fmt_dur(remaining / rate)
        elif remaining == 0:
            eta_str = "done"

    avg_dur = "N/A"
    if onboard_job_secs and files_done:
        avg_job = sum(onboard_job_secs) / len(onboard_job_secs)
        avg_file = sum(onboard_job_secs) / files_done
        avg_dur = (
            f"{fmt_dur(avg_job)} / job ({files_done} files, "
            f"{avg_file:.2f}s/file)"
        )
    else:
        avg_row = conn.execute(
            """
            SELECT AVG(finished_at - started_at)
            FROM agent_queue
            WHERE status IN ('done','failed')
              AND started_at IS NOT NULL AND finished_at IS NOT NULL
              AND finished_at >= ?
              AND finished_at > started_at
            """,
            (run_start,),
        ).fetchone()[0]
        avg_dur = fmt_dur(float(avg_row)) if avg_row else "N/A"

    last_path = conn.execute(
        """
        SELECT path, updated_at FROM documents
        ORDER BY updated_at DESC LIMIT 1
        """
    ).fetchone()

    fail_samples = conn.execute(
        """
        SELECT skill_name, substr(COALESCE(error_msg,''), 1, 80), finished_at
        FROM agent_queue
        WHERE status='failed' AND finished_at >= ?
        ORDER BY finished_at DESC LIMIT 3
        """,
        (run_start,),
    ).fetchall()

    try:
        quarantine = conn.execute("SELECT count(*) FROM quarantine").fetchone()[0]
    except sqlite3.Error:
        quarantine = None

    try:
        links = conn.execute("SELECT count(*) FROM links").fetchone()[0]
    except sqlite3.Error:
        links = None

    try:
        tags = conn.execute("SELECT count(*) FROM tags").fetchone()[0]
    except sqlite3.Error:
        tags = None

    # Oldest pending age (queue stall signal)
    oldest_pending = conn.execute(
        "SELECT MIN(created_at) FROM agent_queue WHERE status='pending'"
    ).fetchone()[0]
    oldest_pending_age = fmt_dur(now - int(oldest_pending)) if oldest_pending else "—"

    # Running task ages
    running_ages = conn.execute(
        """
        SELECT skill_name, started_at, payload_json
        FROM agent_queue WHERE status='running'
        ORDER BY started_at ASC LIMIT 5
        """
    ).fetchall()

    conn.close()

    # --- Report ---
    print("=== SPICE / Wiki Agent Status ===")
    agent_line = "RUNNING" if alive else "not running"
    if session and session.get("pid"):
        agent_line += f" (PID {session['pid']})"
    print(f"  Agent:   {agent_line}")
    print(f"  Scope:   {scope} since {fmt_ts(run_start)}")
    if session:
        filt = session.get("filter") or "all"
        exts = session.get("extensions") or []
        ext_s = ",".join(exts) if exts else "(scan_config / all)"
        print(f"  Filter:  {filt} → {ext_s}")
        roots = session.get("scan_roots") or []
        if roots:
            print(f"  Roots:   {len(roots)} ({', '.join(Path(r).name for r in roots[:4])}"
                  + ("…" if len(roots) > 4 else "") + ")")

    print()
    print(f"  [{bar}] {pct}%")
    verb = "ingested" if unit_label == "files" else "processed"
    print(
        f"  {done}/{total} {unit_label} {verb} | {pending} queued | "
        f"{running} active | {failed} failed"
    )
    if files_cancelled or jobs_cancelled:
        print(
            f"  Stop Scan cancelled: {files_cancelled} files "
            f"({jobs_cancelled} job(s)) — excluded from % bar"
        )
    if progress_note:
        print(progress_note)
    if ingest_total or jobs_cancelled:
        print(
            f"  Queue jobs: {jobs_done + jobs_failed + jobs_cancelled + jobs_active} "
            f"({jobs_pending} queued, {jobs_running} active, "
            f"{jobs_done} done, {jobs_failed} failed, {jobs_cancelled} cancelled)"
        )
    print(f"  Documents: {docs} ({embedded} embedded, {missing_emb} missing)")
    if not alive and jobs_active == 0 and docs and missing_emb == 0:
        print("  Corpus:    complete (all documents have embeddings)")
    if quarantine is not None:
        print(f"  Quarantine: {quarantine}  |  Links: {links}  |  Tags: {tags}")
    print()
    print(f"  Elapsed (this session): {fmt_dur(session_elapsed)}{session_elapsed_note}")
    print(f"  Work window:            {fmt_dur(work_elapsed)}")
    print(f"  Rate:                   {rate_str}")
    print(f"  Avg ingest:             {avg_dur}" if ingest_total else f"  Avg task duration:      {avg_dur}")
    print(f"  ETA (remaining):        {eta_str}")
    print(f"  Oldest pending age:     {oldest_pending_age}")
    if last_path:
        print(f"  Last document update:   {fmt_ts(last_path[1])}")
        print(f"                          {last_path[0]}")
    if progress and progress.get("last_path"):
        print(f"  Last ingest path:       {progress.get('last_path')}")
        if progress.get("updated_at"):
            print(f"                          progress @ {fmt_ts(progress.get('updated_at'))}")
    if last_queue_finish:
        print(f"  Last queue finish:      {fmt_ts(last_queue_finish)}")

    if by_skill:
        print()
        print("  By skill (scope):")
        print(
            f"    {'skill':<16} {'pend':>5} {'run':>4} {'done':>5} "
            f"{'fail':>4} {'canc':>4} {'files':>6}"
        )
        skill_rows = sorted(
            by_skill.items(),
            key=lambda kv: (kv[1]["pending"] + kv[1]["running"], kv[1]["done"]),
            reverse=True,
        )
        for name, s in skill_rows:
            files_s = str(s["files"]) if name == "onboarding" and s["files"] else "—"
            print(
                f"    {name:<16} {s['pending']:>5} {s['running']:>4} "
                f"{s['done']:>5} {s['failed']:>4} {s.get('cancelled', 0):>4} "
                f"{files_s:>6}"
            )

    if running_ages:
        print()
        print("  Active tasks:")
        for row in running_ages:
            skill = row["skill_name"] if isinstance(row, sqlite3.Row) else row[0]
            started = row["started_at"] if isinstance(row, sqlite3.Row) else row[1]
            payload = row["payload_json"] if isinstance(row, sqlite3.Row) else row[2]
            age = fmt_dur(now - int(started)) if started else "?"
            n = work_units(str(skill), payload)
            if str(skill) == "onboarding":
                detail = f"{n} file(s)"
            else:
                detail = (str(payload or "")[:50] + "…") if payload else ""
            print(f"    {skill} · {age} · {detail}")

    if fail_samples:
        real_fails = [r for r in fail_samples if not is_user_cancelled(r[1])]
        cancels = [r for r in fail_samples if is_user_cancelled(r[1])]
        if real_fails:
            print()
            print("  Recent failures:")
            for skill, err, fin in real_fails:
                print(f"    [{fmt_ts(fin)}] {skill}: {err or '(no message)'}")
        if cancels:
            print()
            print("  Recent Stop Scan cancels:")
            for skill, err, fin in cancels:
                print(f"    [{fmt_ts(fin)}] {skill}: {err or '(no message)'}")

    print()
    print(f"  DB: {DB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
