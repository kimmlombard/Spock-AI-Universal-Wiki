"""Promote selected uieg_capture.db rows into ship_computer.db via extractor.

Writes BLOBs under promoted_research/, then runs starfleet_universal_extractor.py
on those paths. Does not auto-watch capture folders.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Callable, List, Optional, Sequence, Tuple

from LongRangeSensors.uieg_database import (
    get_capture_content,
    get_capture_row,
    init_db,
    mark_capture_promoted,
)
from LongRangeSensors.uieg_paths import ensure_promoted_folder

LogFn = Callable[[str], None]

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTRACTOR = os.path.join(SCRIPT_DIR, "starfleet_universal_extractor.py")


def _safe_name(filename: str, capture_id: int) -> str:
    base = os.path.basename(filename or f"capture_{capture_id}")
    safe = re.sub(r"[^\w.\-]+", "_", base).strip("._") or f"capture_{capture_id}"
    if len(safe) > 160:
        root, ext = os.path.splitext(safe)
        safe = root[:140] + ext
    return f"{capture_id}_{safe}"


def promote_capture(
    db_path: str,
    capture_id: int,
    promoted_folder: str,
    *,
    python_exe: Optional[str] = None,
    log: Optional[LogFn] = None,
) -> Tuple[bool, str]:
    """Promote one capture. Returns (ok, message)."""
    _log = log or (lambda _m: None)
    init_db(db_path)
    row = get_capture_row(db_path, capture_id)
    content = get_capture_content(db_path, capture_id)
    if not row or content is None:
        return False, f"#{capture_id}: not found or empty"

    filename = row[1] or f"capture_{capture_id}"
    already = row[7] if len(row) > 7 else None
    if already:
        _log(f"#{capture_id}: already promoted at {row[8] if len(row) > 8 else already}")
        # Allow re-promote with --reprocess via overwrite + extract
        _log(f"#{capture_id}: re-promoting…")

    dest_dir = ensure_promoted_folder(promoted_folder)
    dest_name = _safe_name(filename, capture_id)
    dest_path = os.path.join(dest_dir, dest_name)
    try:
        with open(dest_path, "wb") as f:
            f.write(content if isinstance(content, (bytes, bytearray)) else bytes(content))
    except OSError as e:
        return False, f"#{capture_id}: write failed: {e}"

    py = python_exe or sys.executable
    if not os.path.isfile(EXTRACTOR):
        return False, f"Extractor not found: {EXTRACTOR}"

    try:
        result = subprocess.run(
            [py, EXTRACTOR, dest_path, "--reprocess"],
            cwd=SCRIPT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return False, f"#{capture_id}: extractor timed out"
    except OSError as e:
        return False, f"#{capture_id}: extractor launch failed: {e}"

    out = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    if result.returncode != 0:
        snip = out[-500:] if out else "(no output)"
        return False, f"#{capture_id}: extractor exit {result.returncode}: {snip}"

    mark_capture_promoted(db_path, capture_id, dest_path)
    _log(f"#{capture_id}: promoted → {dest_path}")
    if out:
        for line in out.splitlines()[-8:]:
            _log(f"  {line}")
    return True, dest_path


def promote_captures(
    db_path: str,
    capture_ids: Sequence[int],
    promoted_folder: str,
    *,
    python_exe: Optional[str] = None,
    log: Optional[LogFn] = None,
) -> Tuple[int, int, List[str]]:
    """Promote many. Returns (ok_count, fail_count, messages)."""
    ok_n = 0
    fail_n = 0
    messages: List[str] = []
    for cid in capture_ids:
        ok, msg = promote_capture(
            db_path,
            int(cid),
            promoted_folder,
            python_exe=python_exe,
            log=log,
        )
        messages.append(msg)
        if ok:
            ok_n += 1
        else:
            fail_n += 1
            if log:
                log(msg)
    return ok_n, fail_n, messages
