"""Ask AI / Deep Dive timing history — append-only rows in ship_computer.db.

Config knobs stay in Spock_Console (app.ctx.*). This table is wiped by
content reset (see reset.CONTENT_TABLES), not preserved like Spock_Console.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from .db import DEFAULT_SHIPS_DB, connect, ensure_schema, resolve_db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS ask_timing_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    mode TEXT NOT NULL CHECK(mode IN ('ask','deep_dive')),
    question TEXT NOT NULL,
    response_length INTEGER NOT NULL DEFAULT 0,
    total_ms INTEGER,
    retrieve_ms INTEGER,
    pack_ms INTEGER,
    llm_ms INTEGER,
    n_ctx INTEGER,
    budget INTEGER,
    budget_used INTEGER,
    budget_used_pct REAL,
    docs_used INTEGER,
    match_count INTEGER,
    inventory_shown INTEGER,
    forced_count INTEGER,
    unresolved_count INTEGER,
    max_out INTEGER,
    pack_summary TEXT,
    provider TEXT,
    stage_timings_json TEXT,
    filter_json TEXT,
    meta_json TEXT,
    updated_by TEXT DEFAULT 'ask_panel'
);
CREATE INDEX IF NOT EXISTS idx_ask_timing_created
    ON ask_timing_history(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ask_timing_mode_created
    ON ask_timing_history(mode, created_at DESC);
"""

_EXTRA_COLUMNS: Dict[str, str] = {
    "budget_used_pct": "REAL",
    "inventory_shown": "INTEGER",
    "forced_count": "INTEGER",
    "unresolved_count": "INTEGER",
    "pack_summary": "TEXT",
}

QUESTION_MAX = 2000
SUMMARY_MAX = 500
MODE_LABELS = {"ask": "Ask AI", "deep_dive": "Deep Dive"}


def ensure_timing_schema(db_path: str = DEFAULT_SHIPS_DB) -> str:
    path = resolve_db_path(db_path)
    ensure_schema(path, SCHEMA)
    conn = connect(path)
    try:
        existing = {
            str(r[1])
            for r in conn.execute("PRAGMA table_info(ask_timing_history)").fetchall()
        }
        for col, decl in _EXTRA_COLUMNS.items():
            if col not in existing:
                conn.execute(
                    f"ALTER TABLE ask_timing_history ADD COLUMN {col} {decl}"
                )
        conn.commit()
    finally:
        conn.close()
    return path


def _truncate(text: str, limit: int = QUESTION_MAX) -> str:
    s = text or ""
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _json_dump(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return None


def insert_timing(
    *,
    mode: str,
    question: str,
    response_length: int,
    total_ms: Optional[int] = None,
    retrieve_ms: Optional[int] = None,
    pack_ms: Optional[int] = None,
    llm_ms: Optional[int] = None,
    n_ctx: Optional[int] = None,
    budget: Optional[int] = None,
    budget_used: Optional[int] = None,
    budget_used_pct: Optional[float] = None,
    docs_used: Optional[int] = None,
    match_count: Optional[int] = None,
    inventory_shown: Optional[int] = None,
    forced_count: Optional[int] = None,
    unresolved_count: Optional[int] = None,
    max_out: Optional[int] = None,
    pack_summary: Optional[str] = None,
    provider: Optional[str] = None,
    stage_timings: Optional[Dict[str, Any]] = None,
    filter_info: Optional[Dict[str, Any]] = None,
    meta: Optional[Dict[str, Any]] = None,
    updated_by: str = "ask_panel",
    db_path: str = DEFAULT_SHIPS_DB,
) -> Optional[int]:
    """Insert one timing row. Best-effort — returns row id or None on failure."""
    mode_key = (mode or "").strip().lower()
    if mode_key not in ("ask", "deep_dive"):
        mode_key = "ask"
    stages = dict(stage_timings or {})
    if retrieve_ms is not None:
        stages.setdefault("retrieve_ms", retrieve_ms)
    if pack_ms is not None:
        stages.setdefault("pack_ms", pack_ms)
    if llm_ms is not None:
        stages.setdefault("llm_ms", llm_ms)
    if total_ms is not None:
        stages.setdefault("total_ms", total_ms)

    try:
        path = ensure_timing_schema(db_path)
        conn = connect(path)
        try:
            cur = conn.execute(
                """
                INSERT INTO ask_timing_history (
                    mode, question, response_length,
                    total_ms, retrieve_ms, pack_ms, llm_ms,
                    n_ctx, budget, budget_used, budget_used_pct,
                    docs_used, match_count, inventory_shown, forced_count,
                    unresolved_count, max_out, pack_summary,
                    provider, stage_timings_json, filter_json, meta_json, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mode_key,
                    _truncate(question),
                    int(response_length or 0),
                    total_ms,
                    retrieve_ms,
                    pack_ms,
                    llm_ms,
                    n_ctx,
                    budget,
                    budget_used,
                    budget_used_pct,
                    docs_used,
                    match_count,
                    inventory_shown,
                    forced_count,
                    unresolved_count,
                    max_out,
                    _truncate(pack_summary or "", SUMMARY_MAX) or None,
                    (provider or "")[:200] or None,
                    _json_dump(stages),
                    _json_dump(filter_info),
                    _json_dump(meta),
                    (updated_by or "ask_panel")[:80],
                ),
            )
            conn.commit()
            return int(cur.lastrowid) if cur.lastrowid else None
        finally:
            conn.close()
    except Exception:
        return None


def list_timings(
    db_path: str = DEFAULT_SHIPS_DB,
    *,
    mode: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Newest-first timing rows for the Maintenance grid."""
    path = ensure_timing_schema(db_path)
    mode_key = (mode or "").strip().lower()
    limit = max(1, min(int(limit or 200), 2000))
    conn = connect(path)
    try:
        sql = """
            SELECT id, created_at, mode, question, response_length,
                   total_ms, retrieve_ms, pack_ms, llm_ms,
                   n_ctx, budget, budget_used, budget_used_pct,
                   docs_used, match_count, inventory_shown, forced_count,
                   unresolved_count, max_out, pack_summary,
                   provider, updated_by
            FROM ask_timing_history
        """
        if mode_key in ("ask", "deep_dive"):
            rows = conn.execute(
                sql + " WHERE mode = ? ORDER BY created_at DESC, id DESC LIMIT ?",
                (mode_key, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                sql + " ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        cols = (
            "id",
            "created_at",
            "mode",
            "question",
            "response_length",
            "total_ms",
            "retrieve_ms",
            "pack_ms",
            "llm_ms",
            "n_ctx",
            "budget",
            "budget_used",
            "budget_used_pct",
            "docs_used",
            "match_count",
            "inventory_shown",
            "forced_count",
            "unresolved_count",
            "max_out",
            "pack_summary",
            "provider",
            "updated_by",
        )
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


def count_timings(db_path: str = DEFAULT_SHIPS_DB) -> int:
    path = ensure_timing_schema(db_path)
    conn = connect(path)
    try:
        row = conn.execute("SELECT COUNT(*) FROM ask_timing_history").fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def purge_older_than_days(
    days: int, db_path: str = DEFAULT_SHIPS_DB
) -> int:
    """Delete rows older than ``days``. Returns deleted count."""
    days = max(0, int(days))
    path = ensure_timing_schema(db_path)
    conn = connect(path)
    try:
        if days <= 0:
            cur = conn.execute("DELETE FROM ask_timing_history")
        else:
            cur = conn.execute(
                """
                DELETE FROM ask_timing_history
                WHERE created_at < strftime('%s','now') - ?
                """,
                (days * 86400,),
            )
        conn.commit()
        return int(cur.rowcount or 0)
    finally:
        conn.close()


def mode_label(mode: str) -> str:
    return MODE_LABELS.get((mode or "").strip().lower(), mode or "")
