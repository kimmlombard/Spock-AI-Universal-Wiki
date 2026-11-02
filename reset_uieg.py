#!/usr/bin/env python3
"""Reset uieg_capture.db for a fresh run.

Mirrors reset.py (ship_computer.db): rename the old DB (works with open
handles on Windows), recreate from uieg_capture.sql, then clean up.
"""
import gc
import os
import sqlite3
import sys
import time
from pathlib import Path

WIKI_ROOT = Path(__file__).parent.resolve()
DB_PATH = WIKI_ROOT / "uieg_capture.db"
SCHEMA_PATH = WIKI_ROOT / "uieg_capture.sql"

# 1. Force-close any lingering sqlite3 connections in this process
gc.collect()

# 2. Rename old DB files (rename works even with open handles on Windows)
STAMP = int(time.time())
for f in [DB_PATH, DB_PATH.with_suffix(".db-wal"), DB_PATH.with_suffix(".db-shm")]:
    if f.exists():
        backup = f.with_name(f"{f.name}.{STAMP}.old")
        try:
            os.rename(f, backup)
            print(f"  Renamed {f.name} -> {backup.name}")
        except PermissionError:
            print(f"  ERROR: Cannot rename {f.name} — still locked")
            sys.exit(1)

# 3. Recreate from schema
conn = sqlite3.connect(str(DB_PATH))
conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
conn.close()
print(f"  Recreated {DB_PATH.name}")

# 4. Clean up old renamed files
time.sleep(1)
for f in WIKI_ROOT.glob(f"{DB_PATH.name}.*.old"):
    try:
        f.unlink()
        print(f"  Cleaned up {f.name}")
    except PermissionError:
        pass  # still locked, will be cleaned up later

print("\nDone. Run: Spock-UIEG-KnowledgeBase.bat")
