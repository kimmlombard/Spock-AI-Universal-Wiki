#!/usr/bin/env python3
"""Reset ship_computer.db for a fresh wiki-scan run.

Modes:
  content — wipe corpus / logs / queue / quarantine / embeddings / host recipes;
            keep Spock_Console settings and spock_profile rows. Drop content indexes
            → DELETE → VACUUM → rebuild FTS/indexes/triggers so the DB is wiki-scan
            ready. The sqlite-vec index (documents_vec) is dropped and rebuilt by the
            next embedding pass. ``spock_host_recipe`` is cleared (and its
            sqlite_sequence restarted) so Bringup / Maintenance can re-probe hardware
            and ask for a primary AI GPU on multi-GPU hosts.
            (default)
  full    — rename away the DB and recreate every table from ship_computer_schema.sql
            (settings and profiles are lost unless restored from backup).
"""
from __future__ import annotations

import argparse
import gc
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Iterable, List, Sequence

WIKI_ROOT = Path(__file__).parent.resolve()
DB_PATH = WIKI_ROOT / "ship_computer.db"
SCHEMA_PATH = WIKI_ROOT / "ship_computer_schema.sql"
LOGS = [WIKI_ROOT / "captains_log.md", WIKI_ROOT / "index.md"]

# Kept across --mode content
PRESERVE_TABLES = frozenset(
    {
        "Spock_Console",
        "spock_profile",
        "config",  # legacy key/value store (if present)
    }
)

# Wiped by --mode content (order: dependents first when FKs are on)
CONTENT_TABLES: Sequence[str] = (
    "document_attachments",
    "document_tags",
    "links",
    "entity_mentions",
    "memory_entities",
    "captains_log",
    "agent_queue",
    "quarantine",
    "ask_timing_history",
    "tags",
    "documents",
    "kb_embedding_corpus",
    "spock_host_profile",
    "spock_host_recipe",
)

CONTENT_INDEXES: Sequence[str] = (
    "idx_documents_role",
    "idx_documents_updated",
    "idx_documents_embed_model",
)

CONTENT_TRIGGERS: Sequence[str] = (
    "documents_ad",
    "documents_ai",
    "documents_au",
)

FTS_TABLE = "docs_fts"

# Recreated after a content wipe (subset of ship_computer_schema.sql)
REBUILD_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
    title, content_plain, role, filename,
    content='documents', content_rowid='id',
    tokenize='porter unicode61 remove_diacritics 1'
);

CREATE INDEX IF NOT EXISTS idx_documents_role ON documents(role);
CREATE INDEX IF NOT EXISTS idx_documents_updated ON documents(updated_at);
CREATE INDEX IF NOT EXISTS idx_documents_embed_model ON documents(embedding_model_path);

CREATE TRIGGER documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO docs_fts(docs_fts, rowid) VALUES ('delete', old.id);
END;

CREATE TRIGGER documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO docs_fts(rowid, title, content_plain, role, filename)
    VALUES (new.id, new.title, new.content_plain, new.role, new.filename);
END;

CREATE TRIGGER documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO docs_fts(docs_fts, rowid) VALUES ('delete', old.id);
    INSERT INTO docs_fts(rowid, title, content_plain, role, filename)
    VALUES (new.id, new.title, new.content_plain, new.role, new.filename);
END;
"""


def _table_names(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return [r[0] for r in rows]


def _clear_markdown_logs() -> None:
    for log_file in LOGS:
        if log_file.name == "captains_log.md":
            log_file.write_text("# Captain's Log\nStardate: Fresh run\n", encoding="utf-8")
        else:
            log_file.write_text("# Index\nFresh start\n", encoding="utf-8")
        print(f"  Cleared {log_file.name}")


def _maybe_clear_markdown_logs(db_path: Path) -> None:
    """Only touch the repo logs when resetting the repo's own database."""
    try:
        if Path(db_path).resolve() == DB_PATH.resolve():
            _clear_markdown_logs()
    except OSError:
        pass


def reset_content(db_path: Path = DB_PATH, schema_path: Path = SCHEMA_PATH) -> None:
    """Wipe ship data while preserving settings and profiles."""
    if not db_path.is_file():
        print(f"  ERROR: Database not found: {db_path}")
        sys.exit(1)

    from WarpCore.ship_schema import ensure_ship_computer_schema
    from WarpCore.db import (
        connect as wc_connect,
        drop_vec_table,
        vec_shadow_names,
        vec_table_names,
    )
    from db_maintenance import force_drop_docs_fts

    ensure_ship_computer_schema(str(db_path))

    print(f"  Content reset (preserve {', '.join(sorted(PRESERVE_TABLES))})")
    # WarpCore.connect loads sqlite-vec; a plain sqlite3.connect cannot touch
    # documents_vec ("no such module: vec0").
    conn = wc_connect(str(db_path), timeout=60)
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        existing = set(_table_names(conn))

        for trig in CONTENT_TRIGGERS:
            try:
                conn.execute(f"DROP TRIGGER IF EXISTS [{trig}]")
                print(f"  Dropped trigger {trig}")
            except sqlite3.Error as e:
                print(f"  Trigger {trig}: {e}")

        # Corrupt FTS5 vtables fail DROP TABLE — scrub via writable_schema.
        if any(
            name == FTS_TABLE or name.startswith(f"{FTS_TABLE}_")
            for name in existing
        ):
            conn = force_drop_docs_fts(db_path, conn=conn, log=print)
            conn.execute("PRAGMA foreign_keys=OFF")
            existing = set(_table_names(conn))

        # Vector indexes are derived from documents.embedding: drop them so the
        # next embedding pass recreates them (also clears stale dims/vectors).
        vec_skip: set[str] = set()
        for vec_table in vec_table_names(conn):
            vec_skip.add(vec_table)
            vec_skip.update(vec_shadow_names(conn, vec_table))
            if drop_vec_table(conn, vec_table):
                print(f"  Dropped vector index {vec_table}")
            else:
                print(f"  WARNING: could not drop vector index {vec_table}")
        existing = set(_table_names(conn))

        for idx in CONTENT_INDEXES:
            conn.execute(f"DROP INDEX IF EXISTS [{idx}]")
            print(f"  Dropped index {idx}")

        wiped: List[str] = []
        for table in CONTENT_TABLES:
            if table not in existing:
                continue
            conn.execute(f"DELETE FROM [{table}]")
            wiped.append(table)
            print(f"  Deleted rows from {table}")

        # Drop host-recipe pointer in Spock_Console (table itself is preserved).
        if "Spock_Console" in existing:
            try:
                n = conn.execute(
                    "DELETE FROM Spock_Console WHERE Variable_Name = ?",
                    ("app.host_recipe.current_id",),
                ).rowcount
                if n:
                    print(f"  Cleared Spock_Console app.host_recipe.current_id ({n})")
            except sqlite3.Error as e:
                print(f"  Spock_Console host_recipe pointer: {e}")

        # Any other non-preserved user tables (future schema) — clear too
        existing = set(_table_names(conn))
        for table in sorted(existing):
            if table in PRESERVE_TABLES or table in CONTENT_TABLES:
                continue
            if table == FTS_TABLE or table.startswith(f"{FTS_TABLE}_"):
                continue
            if table in vec_skip:
                continue
            conn.execute(f"DELETE FROM [{table}]")
            wiped.append(table)
            print(f"  Deleted rows from {table} (extra)")

        # Reset AUTOINCREMENT high-water marks for every table (including
        # preserved ones such as spock_profile). Emptied tables — notably
        # spock_host_recipe — restart at id 1.
        try:
            seq_tables = conn.execute("SELECT COUNT(*) FROM sqlite_sequence").fetchone()[0]
            conn.execute("DELETE FROM sqlite_sequence")
            if seq_tables:
                print(f"  Reset sqlite_sequence ({seq_tables} table(s))")
        except sqlite3.Error:
            pass

        conn.commit()
        conn.executescript(REBUILD_SQL)
        print("  Rebuilt FTS / indexes / triggers")

        conn.execute("PRAGMA foreign_keys=ON")
        conn.commit()

        conn.execute("VACUUM")
        print("  VACUUM complete")
        conn.execute("ANALYZE")
        print("  ANALYZE complete")

        preserved = [t for t in sorted(PRESERVE_TABLES) if t in set(_table_names(conn))]
        for t in preserved:
            n = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
            print(f"  Preserved {t}: {n} row(s)")
    finally:
        try:
            conn.close()
        except Exception:
            pass

    _maybe_clear_markdown_logs(db_path)
    print(f"\nDone (content). Database ready for wiki scan: {db_path.name}")


def rebuild_host_recipe_after_reset(
    db_path: Path = DB_PATH,
    *,
    interactive: bool = True,
    skip: bool = False,
) -> None:
    """Re-probe hardware and create a host recipe after recipes were wiped.

    Multi-GPU hosts are asked which card is primary for embed + chat. This is
    the path used by ``python reset.py`` (CLI), not only the Maintenance GUI.
    """
    if skip:
        print(
            "  Host recipe: skipped (--no-host-recipe). "
            "Spock-Menu will ask on next launch if needed."
        )
        return
    try:
        from WarpCore import host_recipe as hr
    except Exception as e:
        print(f"  Host recipe rebuild unavailable: {e}")
        return

    db = str(db_path)
    if hr.get_current_recipe(db) is not None:
        print("  Host recipe: already present — left as-is")
        return

    print("  Host recipe: probing hardware…")
    try:
        hw = hr.probe_hardware()
    except Exception as e:
        print(f"  Host recipe: hardware probe failed: {e}")
        return

    print(f"  Detected: {hw.get('gpu_summary') or '(no GPUs)'}")
    print(f"  Host RAM: {hw.get('host_ram_gb')} GB")
    rec = hr.propose_recipe(hw)

    if hr.multi_gpu_host(hw):
        rows = hr.gpu_choice_rows(hw)
        print("  Multiple GPUs — pick the primary AI GPU for embed + chat:")
        for r in rows:
            print(f"    {r.get('label')}")
        default = hr.default_primary_ai_gpu_index(hw)
        idx = default
        if interactive and sys.stdin.isatty() and sys.stdout.isatty():
            while True:
                raw = input(
                    f"  Primary AI GPU index [{default}] (or 's' to skip): "
                ).strip()
                if raw.lower() in ("s", "skip"):
                    print(
                        "  Host recipe not created — Spock-Menu will ask on launch."
                    )
                    return
                if not raw:
                    idx = default
                    break
                try:
                    idx = int(raw)
                except ValueError:
                    print("  Enter a GPU index number, Enter for default, or s to skip.")
                    continue
                # Do not use ``index or -1`` — GPU 0 is a valid index.
                if any(int(r["index"]) == idx for r in rows if r.get("index") is not None):
                    break
                print(f"  {idx} is not in the list above.")
        else:
            print(
                "  Non-interactive console — not auto-picking a multi-GPU primary.\n"
                "  Host recipe left empty; Spock-Menu will ask on next launch."
            )
            return
        rec = hr.apply_primary_ai_gpu(rec, idx, hardware=hw)
        print(f"  Using primary AI GPU {idx}")
    else:
        rec = dict(rec)
        rec["primary_ai_gpu_confirmed"] = True

    try:
        row = hr.create_recipe(
            db,
            hardware=hw,
            recipe=rec,
            reason="Rebuilt after database reset (CLI)",
            created_by="reset",
        )
        print(
            f"  Host recipe v{row.get('version')} created "
            f"(policy={rec.get('gpu_policy')}, "
            f"AI GPU {rec.get('embed_gpu_index')})"
        )
    except Exception as e:
        print(f"  Host recipe create failed: {e}")


def reset_full(db_path: Path = DB_PATH, schema_path: Path = SCHEMA_PATH) -> None:
    """Delete/recreate the entire database from schema (settings/profiles lost)."""
    if not schema_path.is_file():
        print(f"  ERROR: Schema not found: {schema_path}")
        sys.exit(1)

    gc.collect()
    stamp = int(time.time())
    for f in [db_path, db_path.with_suffix(".db-wal"), db_path.with_suffix(".db-shm")]:
        if f.exists():
            backup = f.with_name(f"{f.name}.{stamp}.old")
            try:
                os.rename(f, backup)
                print(f"  Renamed {f.name} -> {backup.name}")
            except PermissionError:
                print(f"  ERROR: Cannot rename {f.name} — still locked")
                sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.close()
    print(f"  Recreated {db_path.name} from {schema_path.name}")

    _maybe_clear_markdown_logs(db_path)

    time.sleep(1)
    for f in WIKI_ROOT.glob(f"{db_path.name}.*.old"):
        try:
            f.unlink()
            print(f"  Cleaned up {f.name}")
        except PermissionError:
            pass

    print(
        "\nDone (full). Settings/profiles were wiped — restore from backup or "
        "re-import overlays. Run: python -u wiki_agent.py"
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reset ship_computer.db")
    parser.add_argument(
        "--mode",
        choices=("content", "full"),
        default="content",
        help="content = wipe corpus/logs/recipes keep settings+profiles (default); "
        "full = recreate all tables",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help="Path to ship_computer.db",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=SCHEMA_PATH,
        help="Path to ship_computer_schema.sql",
    )
    parser.add_argument(
        "--no-host-recipe",
        action="store_true",
        help="Do not re-probe / create a host recipe after wipe "
        "(Spock-Menu will ask on launch instead)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Non-interactive: skip multi-GPU primary prompt "
        "(leaves recipe empty on multi-GPU hosts)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    print(f"Reset mode: {args.mode}")
    print(f"Database:   {args.db.resolve()}")
    if args.mode == "content":
        reset_content(args.db, args.schema)
    else:
        reset_full(args.db, args.schema)

    rebuild_host_recipe_after_reset(
        args.db,
        interactive=not args.yes,
        skip=args.no_host_recipe,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
