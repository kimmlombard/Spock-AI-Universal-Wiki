"""Backup / restore / reindex / channel reset for uieg_capture.db."""

from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import datetime
from typing import Optional, Tuple

from LongRangeSensors.uieg_database import clear_database, init_db
from LongRangeSensors.uieg_paths import CHANNEL_CRAWL, CHANNEL_REPO

UIEG_BACKUP_PREFIX = "uieg_capture_"


def backup_dir_for(db_path: str) -> str:
    path = os.path.join(os.path.dirname(os.path.abspath(db_path)), "backups")
    os.makedirs(path, exist_ok=True)
    return path


def backup_db(db_path: str) -> str:
    """Copy uieg_capture.db into backups/ with timestamp. Returns backup path."""
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir_for(db_path), f"{UIEG_BACKUP_PREFIX}{ts}.db")
    src = sqlite3.connect(db_path, timeout=30)
    try:
        dst = sqlite3.connect(backup_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return backup_path


def list_backups(db_path: str) -> list[str]:
    bdir = backup_dir_for(db_path)
    if not os.path.isdir(bdir):
        return []
    return sorted(
        f
        for f in os.listdir(bdir)
        if f.startswith(UIEG_BACKUP_PREFIX) and f.endswith(".db")
    )


def restore_db(db_path: str, backup_name: str) -> None:
    """Overwrite uieg_capture.db from a named backup file."""
    src = os.path.join(backup_dir_for(db_path), backup_name)
    if not os.path.isfile(src):
        raise FileNotFoundError(f"Backup not found: {src}")
    for suffix in ("", "-wal", "-shm"):
        target = db_path + suffix if suffix else db_path
        if os.path.exists(target):
            os.remove(target)
    shutil.copy2(src, db_path)
    init_db(db_path)


def reindex_db(db_path: str) -> None:
    """Run ANALYZE then VACUUM on uieg_capture.db."""
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute("ANALYZE")
        conn.commit()
    finally:
        conn.close()
    vac = sqlite3.connect(db_path, timeout=120)
    try:
        vac.execute("VACUUM")
    finally:
        vac.close()


def reset_channel(db_path: str, channel: str) -> Tuple[int, int]:
    """Delete captures and batches for one channel. Returns (captures, batches)."""
    if channel not in (CHANNEL_CRAWL, CHANNEL_REPO):
        raise ValueError(f"Unknown channel: {channel}")
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        cap = conn.execute(
            "SELECT COUNT(*) FROM captures WHERE channel = ?", (channel,)
        ).fetchone()[0]
        bat = conn.execute(
            "SELECT COUNT(*) FROM capture_batches WHERE channel = ?", (channel,)
        ).fetchone()[0]
        conn.execute("DELETE FROM captures WHERE channel = ?", (channel,))
        conn.execute("DELETE FROM capture_batches WHERE channel = ?", (channel,))
        conn.commit()
        return int(cap or 0), int(bat or 0)
    finally:
        conn.close()


def reset_all(db_path: str) -> None:
    """Wipe all captures and batches."""
    clear_database(db_path)


def auto_backup_before_reset(db_path: str, tag: str) -> str:
    """Create a pre-reset backup; returns path."""
    if not os.path.isfile(db_path):
        init_db(db_path)
        return ""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(
        backup_dir_for(db_path), f"{UIEG_BACKUP_PREFIX}pre_reset_{tag}_{ts}.db"
    )
    src = sqlite3.connect(db_path, timeout=30)
    try:
        dst = sqlite3.connect(backup_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return backup_path
