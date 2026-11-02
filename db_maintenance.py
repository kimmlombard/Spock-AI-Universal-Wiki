#!/usr/bin/env python3
"""
ship_computer.db — Database Maintenance Utility

Usage:
    python db_maintenance.py
"""
import sqlite3
import shutil
import sys
import os
import subprocess
import json
from pathlib import Path
from datetime import datetime

WIKI_ROOT = Path(__file__).parent.resolve()
DB_PATH = WIKI_ROOT / "ship_computer.db"
SCHEMA_PATH = WIKI_ROOT / "ship_computer_schema.sql"
BACKUP_DIR = WIKI_ROOT / "backups"
CONFIG_PATH = WIKI_ROOT / "scan_config.json"

# ── Helpers ──────────────────────────────────────────────────────────

def cls():
    os.system("cls" if os.name == "nt" else "clear")

def pause():
    input("\n  Press Enter to continue...")

def log(msg):
    print(f"  {msg}")

def db_info(conn):
    docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    emb = conn.execute("SELECT COUNT(*) FROM documents WHERE embedding IS NOT NULL").fetchone()[0]
    logs = conn.execute("SELECT COUNT(*) FROM captains_log").fetchone()[0]
    queue = conn.execute("SELECT COUNT(*) FROM agent_queue").fetchone()[0]
    quar = conn.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]
    size_mb = DB_PATH.stat().st_size / 1024 / 1024 if DB_PATH.exists() else 0
    return {"docs": docs, "emb": emb, "logs": logs, "queue": queue, "quar": quar, "size_mb": size_mb}

def print_header(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")

def print_db_status(conn):
    info = db_info(conn)
    print(f"\n  Database: {DB_PATH.name}")
    print(f"  Size:     {info['size_mb']:.1f} MB")
    print(f"  Documents:     {info['docs']:>6d}  ({info['emb']} with embeddings)")
    print(f"  Captains log:  {info['logs']:>6d}")
    print(f"  Agent queue:   {info['queue']:>6d}")
    print(f"  Quarantine:    {info['quar']:>6d}")

def get_project_roots(conn):
    """Extract unique top-level directories from documents.path."""
    rows = conn.execute("""
        SELECT DISTINCT
            CASE
                WHEN INSTR(SUBSTR(path, 4), '\\') > 0
                THEN SUBSTR(path, 1, 3 + INSTR(SUBSTR(path, 4), '\\') - 1)
                ELSE path
            END AS root_dir
        FROM documents
        WHERE path IS NOT NULL AND path != ''
        ORDER BY root_dir
    """).fetchall()
    return [r[0] for r in rows]

def get_project_doc_count(conn, root):
    """Count documents whose path starts with root."""
    return conn.execute(
        "SELECT COUNT(*) FROM documents WHERE path LIKE ?",
        (root + "%",)
    ).fetchone()[0]

def get_project_tables(conn, root):
    """Count rows across all tables for a project root."""
    counts = {}
    # documents
    counts["documents"] = conn.execute(
        "SELECT COUNT(*) FROM documents WHERE path LIKE ?", (root + "%",)
    ).fetchone()[0]

    # get doc IDs for this project
    doc_ids = [r[0] for r in conn.execute(
        "SELECT id FROM documents WHERE path LIKE ?", (root + "%",)
    ).fetchall()]

    if not doc_ids:
        return counts

    id_list = ",".join(str(i) for i in doc_ids)

    # document_attachments
    counts["document_attachments"] = conn.execute(
        f"SELECT COUNT(*) FROM document_attachments WHERE doc_id IN ({id_list})"
    ).fetchone()[0]

    # document_tags
    counts["document_tags"] = conn.execute(
        f"SELECT COUNT(*) FROM document_tags WHERE doc_id IN ({id_list})"
    ).fetchone()[0]

    # links (source or target)
    counts["links"] = conn.execute(
        f"SELECT COUNT(*) FROM links WHERE src_doc_id IN ({id_list}) OR dst_doc_id IN ({id_list})"
    ).fetchone()[0]

    # captains_log
    counts["captains_log"] = conn.execute(
        f"SELECT COUNT(*) FROM captains_log WHERE target_doc_id IN ({id_list})"
    ).fetchone()[0]

    # entity_mentions
    counts["entity_mentions"] = conn.execute(
        f"SELECT COUNT(*) FROM entity_mentions WHERE doc_id IN ({id_list})"
    ).fetchone()[0]

    # memory_entities (first_seen or last_updated)
    counts["memory_entities"] = conn.execute(
        f"SELECT COUNT(*) FROM memory_entities WHERE first_seen_doc_id IN ({id_list}) OR last_updated_doc_id IN ({id_list})"
    ).fetchone()[0]

    return counts


def load_scan_roots(
    config_path: Path | None = None, db_path: str | Path | None = None
) -> list:
    """Scan roots from Spock_Console (same list Wiki Agent watches)."""
    db = str(db_path or DB_PATH)
    if config_path is None:
        try:
            import _warpcore_path

            _warpcore_path.ensure()
            from WarpCore import settings_store

            roots = settings_store.get(db, "scan.scan_roots")
            if roots:
                return [str(r) for r in roots if r]
        except Exception:
            pass
    path = Path(config_path) if config_path else CONFIG_PATH
    if not path.is_file():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        roots = cfg.get("scan_roots") or []
        return [str(r) for r in roots if r]
    except (OSError, json.JSONDecodeError, TypeError):
        return []


def format_configured_scan_roots(db_path: str | Path | None = None) -> str:
    """Human-readable list of configured scan roots (not a path-prefix heuristic)."""
    db = Path(db_path or DB_PATH)
    roots = load_scan_roots(db_path=db)
    if not roots:
        return (
            "No scan roots configured.\n\n"
            "Use Update Scan Roots to add folders to index."
        )
    lines = [
        "Configured scan roots (same list as Update Scan Roots):",
        "",
    ]
    conn = None
    try:
        if db.is_file():
            conn = sqlite3.connect(str(db), timeout=5)
    except sqlite3.Error:
        conn = None
    try:
        for i, root in enumerate(roots, 1):
            exists = Path(root).is_dir()
            flag = "ok" if exists else "MISSING"
            n = 0
            if conn is not None:
                try:
                    n = len(docs_under_root(conn, root))
                except sqlite3.Error:
                    n = 0
            lines.append(f"  {i}. [{flag}] {root}")
            lines.append(f"      documents under root: {n}")
    finally:
        if conn is not None:
            conn.close()
    lines.append("")
    lines.append(f"{len(roots)} root(s) configured.")
    return "\n".join(lines)


def normalize_scan_root_path(path: str) -> str:
    """Absolute scan-root path with OS-native separators.

    Also heals a common bug: Windows dialogs used to force ``/`` → ``\\``,
    which turns Linux ``/home/...`` into the non-existent ``\\home\\...``.
    """
    p = (path or "").strip()
    if not p:
        return ""
    if os.name != "nt" and "\\" in p:
        # UNC //server/share is rare in WSL scan roots; treat as forced-backslash.
        if not p.startswith("//"):
            p = p.replace("\\", "/")
    try:
        resolved = str(Path(p).expanduser().resolve())
    except OSError:
        resolved = os.path.abspath(os.path.expanduser(p))
    if os.name == "nt":
        return os.path.normcase(os.path.normpath(resolved))
    return os.path.normpath(resolved)


# Back-compat alias
_normalize_win_path = normalize_scan_root_path


def docs_under_root(conn, root: str) -> list:
    """Return (id, path) for documents under a scan/project root."""
    key = normalize_scan_root_path(root).rstrip("\\/")
    if not key:
        return []
    if os.name == "nt":
        return conn.execute(
            """
            SELECT id, path FROM documents
            WHERE lower(replace(path, '/', '\\')) LIKE lower(?)
               OR lower(replace(path, '/', '\\')) = lower(?)
            """,
            (key + "\\%", key),
        ).fetchall()
    return conn.execute(
        """
        SELECT id, path FROM documents
        WHERE replace(path, '\\', '/') LIKE ?
           OR replace(path, '\\', '/') = ?
        """,
        (key + "/%", key),
    ).fetchall()


def _delete_vec_ids(conn, doc_ids) -> None:
    """Drop purged docs from the sqlite-vec index (needs the vec0 module)."""
    try:
        from WarpCore.db import delete_documents_vec

        delete_documents_vec(conn, doc_ids)
        conn.commit()
    except Exception:
        pass


def _drop_vec_index(conn) -> None:
    """Drop the whole sqlite-vec index so it is rebuilt from documents."""
    try:
        from WarpCore.db import drop_vec_table, vec_table_names

        for name in vec_table_names(conn):
            drop_vec_table(conn, name)
    except Exception:
        pass


def purge_documents_by_ids(conn, doc_ids) -> int:
    """Delete documents and related rows; rebuild FTS. Returns count purged."""
    ids = sorted({int(i) for i in doc_ids if i is not None})
    if not ids:
        return 0
    id_list = ",".join(str(i) for i in ids)
    deletions = [
        f"DELETE FROM entity_mentions WHERE doc_id IN ({id_list})",
        f"DELETE FROM document_tags WHERE doc_id IN ({id_list})",
        f"DELETE FROM document_attachments WHERE doc_id IN ({id_list})",
        f"DELETE FROM links WHERE src_doc_id IN ({id_list}) OR dst_doc_id IN ({id_list})",
        f"DELETE FROM captains_log WHERE target_doc_id IN ({id_list})",
        f"DELETE FROM memory_entities WHERE first_seen_doc_id IN ({id_list}) OR last_updated_doc_id IN ({id_list})",
        f"DELETE FROM documents WHERE id IN ({id_list})",
    ]
    for sql in deletions:
        try:
            conn.execute(sql)
            conn.commit()
        except Exception:
            pass
    _delete_vec_ids(conn, ids)
    try:
        conn.execute("INSERT INTO docs_fts(docs_fts) VALUES('rebuild')")
        conn.commit()
    except Exception:
        pass
    return len(ids)


def find_missing_documents(conn, roots=None) -> list:
    """
    Quick scan of scan roots: documents whose path no longer exists on disk.
    Returns list of (id, path).
    """
    if roots is None:
        roots = load_scan_roots()
    if not roots:
        return []

    seen = set()
    missing = []
    for root in roots:
        for doc_id, path in docs_under_root(conn, root):
            if doc_id in seen:
                continue
            seen.add(doc_id)
            if not path or not os.path.isfile(path):
                missing.append((int(doc_id), path or ""))
    return missing


def purge_missing_content(db_path=None, roots=None) -> dict:
    """
    Quick-scan scan roots and purge documents whose files are gone.
    Returns {roots, checked, missing, purged, paths}.
    """
    path = Path(db_path) if db_path else DB_PATH
    root_list = list(roots) if roots is not None else load_scan_roots()
    result = {
        "roots": root_list,
        "checked": 0,
        "missing": 0,
        "purged": 0,
        "paths": [],
    }
    if not path.is_file():
        result["error"] = f"Database not found: {path}"
        return result
    if not root_list:
        result["error"] = "No scan roots in scan_config.json"
        return result

    conn = sqlite3.connect(str(path), timeout=60)
    try:
        checked = 0
        for root in root_list:
            checked += len(docs_under_root(conn, root))
        missing = find_missing_documents(conn, root_list)
        result["checked"] = checked
        result["missing"] = len(missing)
        result["paths"] = [p for _, p in missing[:50]]
        if missing:
            result["purged"] = purge_documents_by_ids(conn, [i for i, _ in missing])
        return result
    finally:
        conn.close()


# ── Operations ───────────────────────────────────────────────────────

def op_show_status(conn):
    print_header("DATABASE STATUS")
    print_db_status(conn)

    # Show table breakdown
    tables = ["documents", "document_attachments", "tags", "document_tags",
              "links", "captains_log", "quarantine", "agent_queue",
              "memory_entities", "entity_mentions", "config"]
    print(f"\n  Table row counts:")
    for t in tables:
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
            print(f"    {t:25s} {n:>6d}")
        except:
            print(f"    {t:25s} (missing)")

    # FTS5 status
    try:
        fts = conn.execute("SELECT COUNT(*) FROM docs_fts").fetchone()[0]
        print(f"    {'docs_fts (FTS5)':25s} {fts:>6d}")
    except Exception as e:
        print(f"    {'docs_fts (FTS5)':25s} ERROR: {e}")

def op_picklist_projects(conn):
    print_header("UNIQUE PROJECT ROOTS")
    roots = get_project_roots(conn)

    if not roots:
        log("No projects found in documents table.")
        return

    print(f"\n  {'#':>3s}  {'Project Root':<40s}  {'Docs':>6s}")
    print(f"  {'─'*3}  {'─'*40}  {'─'*6}")

    for i, root in enumerate(roots, 1):
        count = get_project_doc_count(conn, root)
        print(f"  {i:>3d}  {root:<40s}  {count:>6d}")

    print(f"\n  Total: {len(roots)} projects")

def op_purge_project(conn):
    print_header("PURGE PROJECT")
    roots = get_project_roots(conn)

    if not roots:
        log("No projects found.")
        return

    # Show picklist
    print(f"\n  {'#':>3s}  {'Project Root':<40s}  {'Docs':>6s}")
    print(f"  {'─'*3}  {'─'*40}  {'─'*6}")
    for i, root in enumerate(roots, 1):
        count = get_project_doc_count(conn, root)
        print(f"  {i:>3d}  {root:<40s}  {count:>6d}")

    try:
        choice = input(f"\n  Enter project # to purge (1-{len(roots)}): ").strip()
        idx = int(choice) - 1
        if idx < 0 or idx >= len(roots):
            log("Invalid selection.")
            return
    except (ValueError, EOFError):
        log("Invalid input.")
        return

    root = roots[idx]
    counts = get_project_tables(conn, root)

    print(f"\n  Project: {root}")
    print(f"  Rows to delete:")
    total = 0
    for table, count in counts.items():
        if count > 0:
            print(f"    {table:25s} {count:>6d}")
            total += count
    print(f"    {'─'*35}")
    print(f"    {'TOTAL':25s} {total:>6d}")

    confirm = input(f"\n  Type YES to purge {root}: ").strip()
    if confirm != "YES":
        log("Cancelled.")
        return

    doc_ids = [r[0] for r in conn.execute(
        "SELECT id FROM documents WHERE path LIKE ?", (root + "%",)
    ).fetchall()]

    if not doc_ids:
        log("No documents found.")
        return

    id_list = ",".join(str(i) for i in doc_ids)

    # Delete in order (FK dependencies)
    deletions = [
        ("entity_mentions", f"DELETE FROM entity_mentions WHERE doc_id IN ({id_list})"),
        ("document_tags", f"DELETE FROM document_tags WHERE doc_id IN ({id_list})"),
        ("document_attachments", f"DELETE FROM document_attachments WHERE doc_id IN ({id_list})"),
        ("links", f"DELETE FROM links WHERE src_doc_id IN ({id_list}) OR dst_doc_id IN ({id_list})"),
        ("captains_log", f"DELETE FROM captains_log WHERE target_doc_id IN ({id_list})"),
        ("memory_entities", f"DELETE FROM memory_entities WHERE first_seen_doc_id IN ({id_list}) OR last_updated_doc_id IN ({id_list})"),
        ("documents", f"DELETE FROM documents WHERE id IN ({id_list})"),
    ]

    log(f"Purging {root}...")
    for table, sql in deletions:
        try:
            conn.execute(sql)
            conn.commit()
        except Exception as e:
            log(f"  {table}: {e}")

    _delete_vec_ids(conn, doc_ids)

    # Rebuild FTS
    try:
        conn.execute("INSERT INTO docs_fts(docs_fts) VALUES('rebuild')")
        conn.commit()
    except:
        pass

    remaining = get_project_doc_count(conn, root)
    log(f"Purge complete. {root}: {remaining} docs remaining.")

def op_clear_db(conn):
    print_header("CLEAR DATABASE")
    print_db_status(conn)

    confirm = input(f"\n  Type YES to delete ALL data from {DB_PATH.name}: ").strip()
    if confirm != "YES":
        log("Cancelled.")
        return

    tables = [
        "entity_mentions", "document_tags", "document_attachments",
        "links", "captains_log", "memory_entities",
        "agent_queue", "quarantine", "documents", "tags", "config"
    ]

    log("Clearing all tables...")
    for t in tables:
        try:
            conn.execute(f"DELETE FROM [{t}]")
        except:
            pass
    conn.commit()

    _drop_vec_index(conn)

    # Reset FTS
    try:
        conn.execute("DELETE FROM docs_fts")
        conn.commit()
    except:
        pass

    log("Database cleared.")

def op_create_db(conn):
    print_header("CREATE DATABASE")
    if DB_PATH.exists():
        log(f"Database already exists: {DB_PATH}")
        log(f"Size: {DB_PATH.stat().st_size / 1024 / 1024:.1f} MB")
        confirm = input("  Overwrite? Type YES: ").strip()
        if confirm != "YES":
            log("Cancelled.")
            return

        # Close current connection
        conn.close()

        # Remove old DB
        for suffix in ["", "-wal", "-shm"]:
            f = DB_PATH.with_suffix(DB_PATH.suffix + suffix)
            if f.exists():
                f.unlink()
                log(f"  Deleted {f.name}")

        # Create fresh
        new_conn = sqlite3.connect(str(DB_PATH))
        new_conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        new_conn.close()
        log(f"Fresh database created from schema.sql")

        # Reopen
        return sqlite3.connect(str(DB_PATH))
    else:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        log(f"Database created from schema.sql")
        return conn

def force_drop_docs_fts(
    db_path: str | Path,
    conn: sqlite3.Connection | None = None,
    log=print,
) -> sqlite3.Connection:
    """Remove docs_fts (+ shadows/triggers) even when the vtable is corrupt.

    Returns a **new** connection to ``db_path`` after scrubbing (caller's old
    connection is closed). Safe for content reset and FTS repair.
    """
    path = Path(db_path)
    own = conn is None
    if conn is None:
        conn = sqlite3.connect(str(path), timeout=60)

    def _scrub(c: sqlite3.Connection) -> None:
        for trig in ("documents_ai", "documents_au", "documents_ad"):
            try:
                c.execute(f"DROP TRIGGER IF EXISTS [{trig}]")
            except Exception:
                pass
        try:
            c.execute("DROP TABLE IF EXISTS docs_fts")
            c.commit()
            log("  Dropped docs_fts")
            return
        except Exception as e:
            log(f"  DROP TABLE docs_fts failed ({e}) — scrubbing sqlite_master")
        c.execute("PRAGMA writable_schema=ON")
        c.execute(
            "DELETE FROM sqlite_master WHERE name LIKE 'docs_fts%' "
            "OR name IN ('documents_ai','documents_au','documents_ad')"
        )
        c.execute("PRAGMA writable_schema=OFF")
        c.commit()
        log("  Scrubbed docs_fts* / document FTS triggers from sqlite_master")

    try:
        _scrub(conn)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    conn = sqlite3.connect(str(path), timeout=60)
    left = conn.execute(
        "SELECT name FROM sqlite_master WHERE name LIKE 'docs_fts%' "
        "OR name IN ('documents_ai','documents_au','documents_ad')"
    ).fetchall()
    if left:
        log(f"  Residual FTS schema rows: {left} — scrubbing again")
        _scrub(conn)
        conn.close()
        conn = sqlite3.connect(str(path), timeout=60)
    return conn


def repair_docs_fts(conn: sqlite3.Connection, log=print) -> bool:
    """Drop/recreate corrupted docs_fts and rebuild from documents.

    Safe to call when ``PRAGMA integrity_check`` or FTS queries fail with
    ``vtable constructor failed: docs_fts``.
    """
    fts_sql = """
        CREATE VIRTUAL TABLE docs_fts USING fts5(
            title, content_plain, role, filename,
            content='documents', content_rowid='id',
            tokenize='porter unicode61 remove_diacritics 1'
        )
    """
    triggers_sql = """
        CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
            INSERT INTO docs_fts(rowid, title, content_plain, role, filename)
            VALUES (new.id, new.title, new.content_plain, new.role, new.filename);
        END;
        CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
            INSERT INTO docs_fts(docs_fts, rowid) VALUES ('delete', old.id);
        END;
        CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
            INSERT INTO docs_fts(docs_fts, rowid) VALUES ('delete', old.id);
            INSERT INTO docs_fts(rowid, title, content_plain, role, filename)
            VALUES (new.id, new.title, new.content_plain, new.role, new.filename);
        END;
    """
    row = conn.execute("PRAGMA database_list").fetchone()
    db_path = Path(row[2] or "") if row else Path()
    if not db_path.is_file():
        log("Could not resolve DB path for FTS repair")
        return False

    try:
        conn = force_drop_docs_fts(db_path, conn=conn, log=log)
    except Exception as e:
        log(f"Schema clear failed: {e}")
        return False

    try:
        conn.execute(fts_sql)
        conn.execute("INSERT INTO docs_fts(docs_fts) VALUES('rebuild')")
        conn.executescript(triggers_sql)
        conn.commit()
        fts = conn.execute("SELECT COUNT(*) FROM docs_fts").fetchone()[0]
        docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        log(f"docs_fts repaired: {fts} FTS rows / {docs} documents")
        conn.close()
        return True
    except Exception as e:
        log(f"docs_fts recreate/rebuild failed: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return False


def op_reindex_db(conn):
    print_header("REINDEX DATABASE")
    log("Rebuilding FTS5 index...")
    try:
        conn.execute("INSERT INTO docs_fts(docs_fts) VALUES('rebuild')")
        conn.commit()
        fts = conn.execute("SELECT COUNT(*) FROM docs_fts").fetchone()[0]
        log(f"FTS5 rebuilt: {fts} entries")
    except Exception as e:
        log(f"FTS5 rebuild failed: {e}")
        log("Attempting drop + recreate + rebuild...")
        if not repair_docs_fts(conn, log=log):
            log("FTS5 repair failed.")

    log("Running ANALYZE...")
    try:
        conn.execute("ANALYZE")
        conn.commit()
        log("ANALYZE complete.")
    except Exception as e:
        log(f"ANALYZE failed: {e}")

    log("Running VACUUM...")
    try:
        conn.execute("VACUUM")
        log("VACUUM complete.")
    except Exception as e:
        log(f"VACUUM failed: {e}")

    info = db_info(conn)
    log(f"Final size: {info['size_mb']:.1f} MB")

def op_backup_db(conn):
    print_header("BACKUP DATABASE")
    if not DB_PATH.exists():
        log("No database to backup.")
        return

    BACKUP_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"ship_computer_{ts}.db"
    backup_path = BACKUP_DIR / backup_name

    log(f"Backing up to: {backup_path}")
    try:
        # Online backup via SQLite backup API
        src_conn = sqlite3.connect(str(DB_PATH))
        dst_conn = sqlite3.connect(str(backup_path))
        src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()

        size_mb = backup_path.stat().st_size / 1024 / 1024
        log(f"Backup complete: {backup_name} ({size_mb:.1f} MB)")
    except Exception as e:
        log(f"Backup API failed: {e}")
        log("Falling back to file copy...")
        shutil.copy2(DB_PATH, backup_path)
        # Copy WAL too if exists
        wal = DB_PATH.with_suffix(DB_PATH.suffix + "-wal")
        if wal.exists():
            shutil.copy2(wal, backup_path.with_suffix(backup_path.suffix + "-wal"))
        log(f"File copy complete: {backup_name}")

    # List existing backups
    backups = sorted(BACKUP_DIR.glob("ship_computer_*.db"))
    if backups:
        print(f"\n  Available backups ({len(backups)}):")
        for b in backups[-10:]:  # show last 10
            sz = b.stat().st_size / 1024 / 1024
            print(f"    {b.name:<35s} {sz:>6.1f} MB")

def op_restore_db(conn):
    print_header("RESTORE DATABASE")
    if not BACKUP_DIR.exists():
        log("No backups directory found.")
        return

    backups = sorted(BACKUP_DIR.glob("ship_computer_*.db"))
    if not backups:
        log("No backups found.")
        return

    print(f"\n  {'#':>3s}  {'Backup File':<35s}  {'Size':>8s}  {'Date'}")
    print(f"  {'─'*3}  {'─'*35}  {'─'*8}  {'─'*20}")
    for i, b in enumerate(backups, 1):
        sz = b.stat().st_size / 1024 / 1024
        dt = datetime.fromtimestamp(b.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  {i:>3d}  {b.name:<35s}  {sz:>6.1f} MB  {dt}")

    try:
        choice = input(f"\n  Enter backup # to restore (1-{len(backups)}): ").strip()
        idx = int(choice) - 1
        if idx < 0 or idx >= len(backups):
            log("Invalid selection.")
            return
    except (ValueError, EOFError):
        log("Invalid input.")
        return

    backup_path = backups[idx]
    log(f"Restoring from: {backup_path.name}")

    confirm = input(f"  This will OVERWRITE {DB_PATH.name}. Type YES: ").strip()
    if confirm != "YES":
        log("Cancelled.")
        return

    # Close current connection
    conn.close()

    # Remove current DB
    for suffix in ["", "-wal", "-shm"]:
        f = DB_PATH.with_suffix(DB_PATH.suffix + suffix)
        if f.exists():
            f.unlink()

    # Copy backup
    shutil.copy2(backup_path, DB_PATH)
    wal = backup_path.with_suffix(backup_path.suffix + "-wal")
    if wal.exists():
        shutil.copy2(wal, DB_PATH.with_suffix(DB_PATH.suffix + "-wal"))

    log(f"Restored: {DB_PATH.name}")

    # Reopen
    return sqlite3.connect(str(DB_PATH))

# ── Script Runners ───────────────────────────────────────────────────

def run_script(script_path, args=None):
    """Run a Python script as a subprocess."""
    if not script_path.exists():
        log(f"Script not found: {script_path}")
        return

    cmd = [sys.executable, str(script_path)]
    if args:
        cmd.extend(args)

    log(f"Running: {script_path.name}")
    print(f"  {'─' * 56}")

    try:
        result = subprocess.run(cmd, cwd=str(WIKI_ROOT))
        print(f"  {'─' * 56}")
        if result.returncode == 0:
            log(f"Completed successfully (exit code 0)")
        else:
            log(f"Exited with code {result.returncode}")
    except KeyboardInterrupt:
        log("Interrupted by user")
    except Exception as e:
        log(f"Error: {e}")

def op_run_model_selector(conn):
    print_header("RUN Spock-Model-Selector.py")
    run_script(WIKI_ROOT / "Spock-Model-Selector.py")

def op_run_wiki_agent(conn):
    print_header("RUN wiki_agent.py")
    run_script(WIKI_ROOT / "wiki_agent.py", args=["-u"])

def op_run_test_embeddings(conn):
    print_header("RUN test_embeddings.py")
    run_script(WIKI_ROOT / "test_embeddings.py")

def op_run_status(conn):
    print_header("RUN wiki_agent_status.py")
    run_script(WIKI_ROOT / "wiki_agent_status.py")

def op_edit_config(conn):
    print_header("EDIT scan configuration")

    try:
        import _warpcore_path

        _warpcore_path.ensure()
        from WarpCore import settings_store

        config = settings_store.load_scan_config(str(DB_PATH))
    except Exception as e:
        log(f"Error reading config from Spock_Console: {e}")
        return

    print(f"\n  Current configuration:\n")
    print(json.dumps(config, indent=2))

    print(f"""
  ┌─────────────────────────────────────────────┐
  │  Edit options:                              │
  │                                             │
  │  1.  Add scan root                          │
  │  2.  Remove scan root                       │
  │  3.  Add allowed extension                  │
  │  4.  Remove allowed extension               │
  │  5.  Add skip directory                     │
  │  6.  Remove skip directory                  │
  │  7.  Open in system editor                  │
  │  8.  Raw JSON edit                          │
  │                                             │
  │  0.  Cancel                                 │
  └─────────────────────────────────────────────┘""")

    choice = input("\n  Select option: ").strip()

    if choice == "1":
        root = input("  Enter new scan root path: ").strip()
        if root and root not in config.get("scan_roots", []):
            config.setdefault("scan_roots", []).append(root)
            _save_config(config)
            log(f"Added: {root}")
        elif root in config.get("scan_roots", []):
            log("Already exists.")
    elif choice == "2":
        roots = config.get("scan_roots", [])
        for i, r in enumerate(roots, 1):
            print(f"    {i}. {r}")
        try:
            idx = int(input("  Enter # to remove: ").strip()) - 1
            if 0 <= idx < len(roots):
                removed = roots.pop(idx)
                _save_config(config)
                log(f"Removed: {removed}")
            else:
                log("Invalid selection.")
        except (ValueError, EOFError):
            log("Invalid input.")
    elif choice == "3":
        ext = input("  Enter extension (e.g., .json): ").strip()
        if ext and ext not in config.get("allowed_extensions", []):
            config.setdefault("allowed_extensions", []).append(ext)
            _save_config(config)
            log(f"Added: {ext}")
        elif ext in config.get("allowed_extensions", []):
            log("Already exists.")
    elif choice == "4":
        exts = config.get("allowed_extensions", [])
        for i, e in enumerate(exts, 1):
            print(f"    {i}. {e}")
        try:
            idx = int(input("  Enter # to remove: ").strip()) - 1
            if 0 <= idx < len(exts):
                removed = exts.pop(idx)
                _save_config(config)
                log(f"Removed: {removed}")
            else:
                log("Invalid selection.")
        except (ValueError, EOFError):
            log("Invalid input.")
    elif choice == "5":
        d = input("  Enter skip directory name: ").strip()
        if d and d not in config.get("skip_dirs", []):
            config.setdefault("skip_dirs", []).append(d)
            _save_config(config)
            log(f"Added: {d}")
    elif choice == "6":
        dirs = config.get("skip_dirs", [])
        for i, d in enumerate(dirs, 1):
            print(f"    {i}. {d}")
        try:
            idx = int(input("  Enter # to remove: ").strip()) - 1
            if 0 <= idx < len(dirs):
                removed = dirs.pop(idx)
                _save_config(config)
                log(f"Removed: {removed}")
            else:
                log("Invalid selection.")
        except (ValueError, EOFError):
            log("Invalid input.")
    elif choice == "7":
        import tempfile

        tmp = Path(tempfile.gettempdir()) / "scan_config_edit.json"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        log(f"Opening {tmp.name} in system editor...")
        os.startfile(str(tmp))
        input("\n  Press Enter after closing the editor to reload...")
        try:
            with open(tmp, "r", encoding="utf-8") as f:
                config = json.load(f)
            _save_config(config)
            log("Config updated.")
        except Exception as e:
            log(f"Error reloading config: {e}")
    elif choice == "8":
        print(f"\n  Edit the JSON below. Press Enter when done.")
        print(f"  (Paste new JSON or type 'cancel' to abort)\n")
        lines = []
        while True:
            try:
                line = input()
                if line.strip().lower() == "cancel":
                    log("Cancelled.")
                    return
                if line == "":
                    break
                lines.append(line)
            except EOFError:
                break

        if lines:
            raw = "\n".join(lines)
            try:
                new_config = json.loads(raw)
                _save_config(new_config)
                log("Config updated.")
            except json.JSONDecodeError as e:
                log(f"Invalid JSON: {e}")
    elif choice == "0":
        return
    else:
        log("Invalid option.")

def _save_config(config):
    """Write config to Spock_Console (authoritative store)."""
    try:
        import _warpcore_path

        _warpcore_path.ensure()
        from WarpCore import settings_store

        settings_store.save_scan_config(str(DB_PATH), config, by="maintenance")
        log(f"Saved to Spock_Console: {DB_PATH.name}")
    except Exception as e:
        log(f"Error saving config: {e}")

# ── Main Menu ────────────────────────────────────────────────────────

def main():
    conn = sqlite3.connect(str(DB_PATH))

    while True:
        cls()
        print_header("SHIP COMPUTER — DATABASE MAINTENANCE")
        print_db_status(conn)
        print(f"""
  ┌─────────────────────────────────────────────┐
  │  DATABASE                                   │
  │  1.  Show status                            │
  │  2.  List project roots                     │
  │  3.  Purge project                          │
  │  4.  Clear database (start fresh)           │
  │  5.  Create database (from schema.sql)      │
  │  6.  Reindex database                       │
  │  7.  Backup database                        │
  │  8.  Restore database                       │
  │                                             │
  │  SCRIPTS                                    │
  │  9.  Spock-Model-Selector.py                │
  │  10. wiki_agent.py                         │
  │  11. test_embeddings.py                     │
  │  12. wiki_agent_status.py                              │
  │  13. Edit scan_config.json                  │
  │                                             │
  │  0.  Exit                                   │
  └─────────────────────────────────────────────┘""")

        choice = input("\n  Select option: ").strip()

        if choice == "1":
            op_show_status(conn)
            pause()
        elif choice == "2":
            op_picklist_projects(conn)
            pause()
        elif choice == "3":
            op_purge_project(conn)
            pause()
        elif choice == "4":
            op_clear_db(conn)
            pause()
        elif choice == "5":
            result = op_create_db(conn)
            if result is not conn:
                conn = result
            pause()
        elif choice == "6":
            op_reindex_db(conn)
            pause()
        elif choice == "7":
            op_backup_db(conn)
            pause()
        elif choice == "8":
            result = op_restore_db(conn)
            if result is not conn:
                conn = result
            pause()
        elif choice == "9":
            op_run_model_selector(conn)
            pause()
        elif choice == "10":
            op_run_wiki_agent(conn)
            pause()
        elif choice == "11":
            op_run_test_embeddings(conn)
            pause()
        elif choice == "12":
            op_run_status(conn)
            pause()
        elif choice == "13":
            op_edit_config(conn)
            pause()
        elif choice == "0":
            print("\n  Goodbye.\n")
            break
        else:
            log("Invalid option.")
            pause()

    conn.close()

if __name__ == "__main__":
    main()
