"""Ensure ship_computer.db has wiki/corpus tables (documents, FTS, etc.).

First launch only creates Spock_Console via settings_store; wiki scan and
embedding_corpus need the full schema from ship_computer_schema.sql.
Safe to call repeatedly — applies only DDL for objects that are still missing.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .db import DEFAULT_SHIPS_DB, connect, resolve_db_path, table_exists

_REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = _REPO_ROOT / "ship_computer_schema.sql"
CORE_TABLE = "documents"

_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:(?:\"([^\"]+)\")|(?:\[([^\]]+)\])|(?:`([^`]+)`)|([A-Za-z_][A-Za-z0-9_]*))",
    re.IGNORECASE,
)
_CREATE_VTABLE = re.compile(
    r"CREATE\s+VIRTUAL\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:(?:\"([^\"]+)\")|(?:\[([^\]]+)\])|(?:`([^`]+)`)|([A-Za-z_][A-Za-z0-9_]*))",
    re.IGNORECASE,
)
_CREATE_INDEX = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:(?:\"([^\"]+)\")|(?:\[([^\]]+)\])|(?:`([^`]+)`)|([A-Za-z_][A-Za-z0-9_]*))",
    re.IGNORECASE,
)
_CREATE_TRIGGER = re.compile(
    r"CREATE\s+TRIGGER\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:(?:\"([^\"]+)\")|(?:\[([^\]]+)\])|(?:`([^`]+)`)|([A-Za-z_][A-Za-z0-9_]*))",
    re.IGNORECASE,
)


def _first_group(match: re.Match[str]) -> str:
    return next(g for g in match.groups() if g)


def _split_sql(schema_sql: str) -> list[str]:
    """Split SQL file into statements; respect BEGIN…END blocks in triggers."""
    statements: list[str] = []
    buf: list[str] = []
    depth = 0
    for line in schema_sql.splitlines():
        if line.strip().startswith("--"):
            continue
        buf.append(line)
        upper = line.upper()
        if re.search(r"\bBEGIN\b", upper):
            depth += len(re.findall(r"\bBEGIN\b", upper))
        if re.search(r"\bEND\b", upper):
            depth -= len(re.findall(r"\bEND\b", upper))
        if line.rstrip().endswith(";") and depth <= 0:
            stmt = "\n".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            depth = 0
    tail = "\n".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def _object_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','index','trigger')"
    ).fetchall()
    return {str(r[0]) for r in rows}


def _statement_object_name(stmt: str) -> tuple[str, str] | None:
    for kind, pattern in (
        ("table", _CREATE_TABLE),
        ("vtable", _CREATE_VTABLE),
        ("index", _CREATE_INDEX),
        ("trigger", _CREATE_TRIGGER),
    ):
        match = pattern.search(stmt)
        if match:
            return kind, _first_group(match)
    return None


def _apply_missing_schema(conn: sqlite3.Connection, schema_sql: str) -> None:
    existing = _object_names(conn)
    for stmt in _split_sql(schema_sql):
        info = _statement_object_name(stmt)
        if info:
            kind, name = info
            if name in existing:
                continue
            if kind == "index" and "IF NOT EXISTS" not in stmt.upper():
                stmt = re.sub(
                    r"CREATE\s+(UNIQUE\s+)?INDEX\s+",
                    r"CREATE \1INDEX IF NOT EXISTS ",
                    stmt,
                    count=1,
                    flags=re.IGNORECASE,
                )
        conn.execute(stmt)
        if info:
            existing.add(info[1])
    conn.commit()


# Redundant leftovers: the canonical table DDL already declares the same column
# as UNIQUE (sqlite_autoindex_*), so these only double the index-maintenance
# cost. Each drop is guarded so a database whose table lacks the UNIQUE
# constraint (e.g. spock_profile created by profile_store's older DDL) keeps
# the index instead of silently losing its only uniqueness guarantee.
_LEGACY_INDEX_DROPS = (
    ("idx_documents_path", "documents", "path", "BINARY"),
    ("idx_spock_profile_name", "spock_profile", "name", "NOCASE"),
)


def _has_unique_column_index(
    conn: sqlite3.Connection, table: str, column: str, collate: str, exclude: str
) -> bool:
    """True when a UNIQUE single-column index (other than ``exclude``) exists."""
    try:
        indexes = list(conn.execute(f'PRAGMA index_list("{table}")'))
    except sqlite3.Error:
        return False
    for info in indexes:
        name, unique = info[1], info[2]
        if name == exclude or not unique:
            continue
        try:
            cols = [
                c
                for c in conn.execute(f'PRAGMA index_xinfo("{name}")')
                if c[5]  # key columns only (key=1); rowid entry has key=0
            ]
        except sqlite3.Error:
            continue
        if (
            len(cols) == 1
            and cols[0][2] == column
            and cols[0][4] == collate
        ):
            return True
    return False


def _drop_redundant_indexes(conn: sqlite3.Connection) -> None:
    changed = False
    for index, table, column, collate in _LEGACY_INDEX_DROPS:
        try:
            names = {r[1] for r in conn.execute(f'PRAGMA index_list("{table}")')}
        except sqlite3.Error:
            continue
        if index not in names:
            continue
        if _has_unique_column_index(conn, table, column, collate, exclude=index):
            conn.execute(f'DROP INDEX IF EXISTS "{index}"')
            changed = True
    if changed:
        conn.commit()


def ensure_ship_computer_schema(db_path: str = DEFAULT_SHIPS_DB) -> str:
    """Create or repair wiki tables; return absolute db path."""
    path = resolve_db_path(db_path)
    if not SCHEMA_PATH.is_file():
        raise FileNotFoundError(f"Missing schema file: {SCHEMA_PATH}")
    conn = connect(path)
    try:
        _apply_missing_schema(conn, SCHEMA_PATH.read_text(encoding="utf-8"))
        _drop_redundant_indexes(conn)
    finally:
        conn.close()
    if not table_exists(path, CORE_TABLE):
        raise RuntimeError(
            f"Failed to create {CORE_TABLE} table in {path}. "
            f"Check {SCHEMA_PATH.name}."
        )
    return path
