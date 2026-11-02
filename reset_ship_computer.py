#!/usr/bin/env python3
"""Reset ship_computer.db and logs for a fresh run."""
import gc
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

WIKI_ROOT = Path(__file__).parent.resolve()
DB_PATH = WIKI_ROOT / "ship_computer.db"
SCHEMA_PATH = WIKI_ROOT / "ship_computer_schema.sql"
LOGS = [WIKI_ROOT / "captains_log.md", WIKI_ROOT / "index.md"]

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

# 4. Reset markdown logs
for log_file in LOGS:
    if log_file.name == "captains_log.md":
        log_file.write_text(f"# Captain's Log\nStardate: Fresh run\n", encoding="utf-8")
    else:
        log_file.write_text(f"# Index\nFresh start\n", encoding="utf-8")
    print(f"  Cleared {log_file.name}")

# 5. Clean up old renamed files
time.sleep(1)
for f in WIKI_ROOT.glob(f"{DB_PATH.name}.*.old"):
    try:
        f.unlink()
        print(f"  Cleaned up {f.name}")
    except PermissionError:
        pass  # still locked, will be cleaned up later

print("\nDone. Run: python -u wiki_agent.py")
