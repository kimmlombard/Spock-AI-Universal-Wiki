"""WarpCore: shared pure-sqlite helpers for Spock V2.

No PyQt imports — safe for the GUI, wiki_agent daemon, extractor,
RAG API server, MCP server, and CLI maintenance scripts.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

DEFAULT_SHIPS_DB = "ship_computer.db"
DEFAULT_UIEG_DB = "uieg_capture.db"


try:
    import sqlite_vec  # type: ignore

    _SQLITE_VEC_AVAILABLE = True
except Exception:
    sqlite_vec = None
    _SQLITE_VEC_AVAILABLE = False


_VEC_TABLE_NAME = "documents_vec"


def resolve_db_path(path: Optional[str] = None, name: str = DEFAULT_SHIPS_DB) -> str:
    """Return an absolute DB path, defaulting to <workspace>/<name>."""
    if path:
        return str(Path(path).resolve())
    return str(Path.cwd() / name)


def connect(db_path: str, timeout: float = 30.0) -> sqlite3.Connection:
    """Open a connection with WAL + busy_timeout for multi-process safety."""
    conn = sqlite3.connect(db_path, timeout=timeout)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=%d" % int(timeout * 1000))
    conn.execute("PRAGMA foreign_keys=ON")
    # Opportunistic query-planner stats refresh (SQLite throttles this to
    # once per 24h per DB and only re-analyzes tables whose data shifted).
    conn.execute("PRAGMA optimize")
    _load_sqlite_vec(conn)
    return conn


def ensure_schema(db_path: str, schema_sql: str) -> None:
    """Execute a batch of DDL (safe to call repeatedly)."""
    conn = connect(db_path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()


def _load_sqlite_vec(conn: sqlite3.Connection) -> None:
    if not _SQLITE_VEC_AVAILABLE:
        return
    try:
        if hasattr(conn, "enable_load_extension"):
            conn.enable_load_extension(True)
        sqlite_vec.load(conn)  # type: ignore
    except Exception:
        try:
            if hasattr(conn, "enable_load_extension"):
                conn.enable_load_extension(False)
        except Exception:
            pass
        return
    try:
        if hasattr(conn, "enable_load_extension"):
            conn.enable_load_extension(False)
    except Exception:
        pass


def vec_table_exists(conn: sqlite3.Connection) -> bool:
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (_VEC_TABLE_NAME,),
        ).fetchone()
        return row is not None
    except Exception:
        return False


def vec_table_names(conn: sqlite3.Connection) -> list[str]:
    """Names of sqlite-vec virtual tables in the main schema."""
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND sql LIKE '%USING vec0%'"
        ).fetchall()
    except sqlite3.Error:
        return []
    return [str(r[0]) for r in rows]


def vec_shadow_names(conn: sqlite3.Connection, name: str = _VEC_TABLE_NAME) -> list[str]:
    """Shadow tables (``<vec>_chunks`` etc.) belonging to a vec0 table."""
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND substr(name, 1, ?) = ?",
            (len(name) + 1, f"{name}_"),
        ).fetchall()
    except sqlite3.Error:
        return []
    return [str(r[0]) for r in rows]


def drop_vec_table(conn: sqlite3.Connection, name: str = _VEC_TABLE_NAME) -> bool:
    """Drop a vec0 table (and its shadow tables) on any connection.

    Both ``DELETE FROM`` and ``DROP TABLE`` fail with ``no such module: vec0``
    unless the extension is loaded on *this* connection, so load it first.
    If the module is unavailable, scrub the schema rows instead so later
    DDL/VACUUM doesn't trip over the orphaned virtual table.
    """
    _load_sqlite_vec(conn)
    try:
        conn.execute(f'DROP TABLE IF EXISTS "{name}"')
        conn.commit()
        return True
    except sqlite3.Error:
        pass

    try:
        # Real b-tree shadow tables can be dropped without the module.
        for shadow in vec_shadow_names(conn, name):
            conn.execute(f'DROP TABLE IF EXISTS "{shadow}"')
        version = conn.execute("PRAGMA schema_version").fetchone()
        conn.execute("PRAGMA writable_schema=ON")
        conn.execute(
            "DELETE FROM sqlite_master WHERE type='table' AND name=?", (name,)
        )
        conn.execute("PRAGMA writable_schema=OFF")
        if version:
            conn.execute(f"PRAGMA schema_version={int(version[0]) + 1}")
        conn.commit()
        return True
    except sqlite3.Error:
        try:
            conn.execute("PRAGMA writable_schema=OFF")
        except sqlite3.Error:
            pass
        return False


def delete_documents_vec(conn: sqlite3.Connection, doc_ids) -> int:
    """Remove specific documents from the vec index (no-op when absent)."""
    ids = [int(i) for i in (doc_ids or []) if i is not None]
    if not ids or not _SQLITE_VEC_AVAILABLE:
        return 0
    _load_sqlite_vec(conn)
    if not vec_table_exists(conn):
        return 0
    removed = 0
    for start in range(0, len(ids), 500):
        chunk = ids[start : start + 500]
        placeholders = ",".join("?" for _ in chunk)
        try:
            conn.execute(
                f"DELETE FROM {_VEC_TABLE_NAME} WHERE doc_id IN ({placeholders})",
                chunk,
            )
            removed += len(chunk)
        except sqlite3.Error:
            continue
    return removed


def ensure_documents_vec(conn: sqlite3.Connection, dim: Optional[int] = None) -> None:
    if not _SQLITE_VEC_AVAILABLE:
        return
    try:
        if not vec_table_exists(conn):
            if dim is None:
                dim = _infer_embedding_dim(conn)
            if dim is None or dim <= 0:
                return
            conn.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS {_VEC_TABLE_NAME} USING vec0(doc_id INTEGER PRIMARY KEY, embedding float[{dim}])"
            )
            conn.commit()
            return
    except Exception:
        pass


def _infer_embedding_dim(conn: sqlite3.Connection) -> Optional[int]:
    try:
        row = conn.execute(
            "SELECT length(embedding) FROM documents WHERE embedding IS NOT NULL AND length(embedding) > 0 LIMIT 1"
        ).fetchone()
        if not row or not row[0]:
            return None
        size = int(row[0])
        if size % 4 != 0:
            return None
        return size // 4
    except Exception:
        return None


def rebuild_documents_vec(conn: sqlite3.Connection) -> int:
    if not _SQLITE_VEC_AVAILABLE:
        return 0
    try:
        dim = _infer_embedding_dim(conn)
        if dim is None or dim <= 0:
            # No embeddings left (e.g. "Clear Embeddings"): the index must not
            # keep serving stale vectors for rows that are no longer embedded.
            drop_vec_table(conn)
            return 0
        drop_vec_table(conn)
        conn.execute(
            f"CREATE VIRTUAL TABLE {_VEC_TABLE_NAME} USING vec0(doc_id INTEGER PRIMARY KEY, embedding float[{dim}])"
        )
        from sqlite_vec import serialize_float32  # type: ignore

        inserted = 0
        rows = conn.execute(
            "SELECT id, embedding FROM documents WHERE embedding IS NOT NULL AND length(embedding) > 0"
        ).fetchall()
        import struct

        for docid, emb in rows:
            try:
                floats = struct.unpack("<" + "f" * (len(emb) // 4), emb)
                conn.execute(
                    f"INSERT INTO {_VEC_TABLE_NAME}(doc_id, embedding) VALUES(?, ?)",
                    (int(docid), serialize_float32(floats)),
                )
                inserted += 1
            except Exception:
                continue
        conn.commit()
        return inserted
    except Exception:
        return 0


def upsert_documents_vec(conn: sqlite3.Connection, doc_ids) -> int:
    """Sync specific documents (by id) into documents_vec without a full rebuild."""
    if not _SQLITE_VEC_AVAILABLE or not doc_ids:
        return 0
    _load_sqlite_vec(conn)
    ensure_documents_vec(conn)
    if not vec_table_exists(conn):
        return 0
    try:
        from sqlite_vec import serialize_float32  # type: ignore
        import struct

        placeholders = ",".join("?" for _ in doc_ids)
        rows = conn.execute(
            f"SELECT id, embedding FROM documents WHERE id IN ({placeholders}) "
            f"AND embedding IS NOT NULL AND length(embedding) > 0",
            [int(i) for i in doc_ids],
        ).fetchall()
        updated = 0
        for docid, emb in rows:
            try:
                floats = struct.unpack("<" + "f" * (len(emb) // 4), emb)
                conn.execute(
                    f"DELETE FROM {_VEC_TABLE_NAME} WHERE doc_id = ?",
                    (int(docid),),
                )
                conn.execute(
                    f"INSERT INTO {_VEC_TABLE_NAME}(doc_id, embedding) VALUES(?, ?)",
                    (int(docid), serialize_float32(floats)),
                )
                updated += 1
            except Exception:
                continue
        return updated
    except Exception:
        return 0


def table_exists(db_path: str, table: str) -> bool:
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def row_count(db_path: str, table: str) -> int:
    conn = connect(db_path)
    try:
        row = conn.execute('SELECT COUNT(*) FROM "%s"' % table).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def table_names(db_path: str) -> list[str]:
    conn = connect(db_path)
    try:
        return [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
    finally:
        conn.close()
