"""WarpCore: spock_profile store — the sole owner of the profile table.

Consolidated into ships_computer.db (previously shared between
spock_profile_store.py and uieg_database.py in uieg_capture.db).

Pure sqlite — safe for the GUI and any subprocess.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .db import connect, table_exists, DEFAULT_SHIPS_DB, resolve_db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS spock_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    stardate TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
"""


def stardate() -> str:
    return datetime.now().strftime("%Y.%m.%d.%H.%M.%S")


def ensure_schema(db_path: str = DEFAULT_SHIPS_DB) -> None:
    from .db import ensure_schema as _es

    # Uniqueness of name lives in the table DDL (UNIQUE COLLATE NOCASE), same
    # as ship_computer_schema.sql — the former idx_spock_profile_name duplicate
    # is dropped by WarpCore.ship_schema._drop_redundant_indexes.
    _es(db_path, SCHEMA)


def list_profiles(db_path: str = DEFAULT_SHIPS_DB) -> List[Tuple[int, str, str, str]]:
    """Return (id, name, stardate, created_at) newest first."""
    ensure_schema(db_path)
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        rows = conn.execute(
            "SELECT id, name, stardate, created_at FROM spock_profile ORDER BY id DESC"
        ).fetchall()
        return [(int(r[0]), str(r[1]), str(r[2]), str(r[3])) for r in rows]
    finally:
        conn.close()


def count_profiles(db_path: str = DEFAULT_SHIPS_DB) -> int:
    ensure_schema(db_path)
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        row = conn.execute("SELECT COUNT(*) FROM spock_profile").fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def get_profile(db_path: str = DEFAULT_SHIPS_DB, profile_id: int = 0) -> Optional[Dict[str, Any]]:
    """Return {id, name, stardate, created_at, payload} or None."""
    ensure_schema(db_path)
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        row = conn.execute(
            "SELECT id, name, stardate, created_at, payload_json FROM spock_profile WHERE id = ?",
            (profile_id,),
        ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row[4] or "{}")
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        return {
            "id": int(row[0]),
            "name": str(row[1]),
            "stardate": str(row[2]),
            "created_at": str(row[3]),
            "payload": payload,
        }
    finally:
        conn.close()


def find_profile_by_name(
    db_path: str = DEFAULT_SHIPS_DB, name: str = ""
) -> Optional[Dict[str, Any]]:
    """Newest row whose name matches case-insensitively, or None."""
    needle = (name or "").strip().lower()
    if not needle:
        return None
    ensure_schema(db_path)
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        rows = conn.execute(
            "SELECT id, name FROM spock_profile ORDER BY id DESC"
        ).fetchall()
    finally:
        conn.close()
    for pid, pname in rows:
        if str(pname or "").strip().lower() == needle:
            return get_profile(db_path, int(pid))
    return None


def upsert_profile(
    db_path: str = DEFAULT_SHIPS_DB,
    name: str = "",
    payload: Optional[Dict[str, Any]] = None,
    profile_stardate: Optional[str] = None,
) -> Tuple[int, bool]:
    """Insert or replace by name. Returns (id, replaced)."""
    ensure_schema(db_path)
    sd = profile_stardate or stardate()
    created = datetime.now().isoformat(timespec="seconds")
    label = (name or "").strip() or sd
    blob = json.dumps(payload or {}, indent=2)
    existing = find_profile_by_name(db_path, label)
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        c = conn.cursor()
        if existing:
            c.execute(
                """
                UPDATE spock_profile
                SET name = ?, stardate = ?, created_at = ?, payload_json = ?
                WHERE id = ?
                """,
                (label, sd, created, blob, int(existing["id"])),
            )
            conn.commit()
            return int(existing["id"]), True
        c.execute(
            """
            INSERT INTO spock_profile (name, stardate, created_at, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (label, sd, created, blob),
        )
        conn.commit()
        return int(c.lastrowid), False
    finally:
        conn.close()


def list_profile_summaries(db_path: str = DEFAULT_SHIPS_DB) -> List[Dict[str, Any]]:
    """Newest first, with embedding GGUF + Ask AI provider from payload."""
    ensure_schema(db_path)
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        rows = conn.execute(
            """
            SELECT id, name, stardate, created_at, payload_json
            FROM spock_profile ORDER BY id DESC
            """
        ).fetchall()
    finally:
        conn.close()
    out: List[Dict[str, Any]] = []
    for pid, name, sd, created, payload_json in rows:
        try:
            payload = json.loads(payload_json or "{}")
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        cfg = payload.get("config") or {}
        ep = cfg.get("embedding_profile") or {}
        embed_path = str(ep.get("model_path") or "").strip()
        if not embed_path:
            for srv in payload.get("servers") or []:
                if isinstance(srv, dict) and str(srv.get("role") or "").lower() == "embedding":
                    embed_path = str(srv.get("model_path") or "").strip()
                    if embed_path:
                        break
        embed_name = os.path.basename(embed_path.replace("\\", "/")) if embed_path else ""
        out.append(
            {
                "id": int(pid),
                "name": str(name),
                "stardate": str(sd),
                "created_at": str(created),
                "ask_ai_provider": str(cfg.get("ask_ai_provider") or ""),
                "chat_model": str(
                    cfg.get("openai_compat_model")
                    or cfg.get("lm_studio_model")
                    or cfg.get("ollama_model")
                    or ""
                ),
                "embedding_model_path": embed_path,
                "embedding_model_name": embed_name,
                "embeddings_url": str(ep.get("embeddings_url") or ""),
                "payload": payload,
            }
        )
    return out


def insert_profile(
    db_path: str = DEFAULT_SHIPS_DB,
    name: str = "",
    payload: Optional[Dict[str, Any]] = None,
    profile_stardate: Optional[str] = None,
) -> int:
    """Insert a row. Prefer upsert_profile so duplicate names replace."""
    pid, _replaced = upsert_profile(db_path, name, payload, profile_stardate)
    return pid


def delete_profiles(db_path: str = DEFAULT_SHIPS_DB, profile_ids: Optional[List[int]] = None) -> int:
    """Delete by id; return number of rows removed."""
    profile_ids = profile_ids or []
    if not profile_ids:
        return 0
    ensure_schema(db_path)
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        placeholders = ",".join("?" * len(profile_ids))
        c = conn.cursor()
        c.execute(
            f"DELETE FROM spock_profile WHERE id IN ({placeholders})",
            [int(i) for i in profile_ids],
        )
        conn.commit()
        return int(c.rowcount)
    finally:
        conn.close()


def migrate_from_legacy(
    legacy_db: str,
    target_db: str = DEFAULT_SHIPS_DB,
    archive_legacy_rows: bool = True,
) -> Dict[str, Any]:
    """Copy all rows from a legacy uieg_capture.db spock_profile table.

    Skips rows already present (matched by stardate) so re-runs are idempotent.
    Returns a report dict.
    """
    from .db import table_exists as _te

    report: Dict[str, Any] = {"copied": 0, "skipped": 0, "source_table": False}
    if not _te(legacy_db, "spock_profile"):
        return report
    report["source_table"] = True

    ensure_schema(target_db)
    conn_legacy = sqlite3.connect(legacy_db, timeout=30)
    conn_target = sqlite3.connect(target_db, timeout=30)
    try:
        existing = {
            r[0] for r in conn_target.execute("SELECT stardate FROM spock_profile").fetchall()
        }
        rows = conn_legacy.execute(
            "SELECT name, stardate, created_at, payload_json FROM spock_profile ORDER BY id"
        ).fetchall()
        for name, sd, created, payload in rows:
            if sd in existing:
                report["skipped"] += 1
                continue
            conn_target.execute(
                "INSERT INTO spock_profile (name, stardate, created_at, payload_json) VALUES (?, ?, ?, ?)",
                (str(name), str(sd), str(created), str(payload)),
            )
            report["copied"] += 1
        conn_target.commit()

        if archive_legacy_rows and report["copied"]:
            conn_legacy.execute("DELETE FROM spock_profile")
            conn_legacy.commit()
    finally:
        conn_legacy.close()
        conn_target.close()
    return report
