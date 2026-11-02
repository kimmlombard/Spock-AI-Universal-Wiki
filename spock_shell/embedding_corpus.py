"""Which embedding GGUF produced documents.embedding in ship_computer.db.

Wiki scan records a singleton row (kb_embedding_corpus) and stamps each
document. Ask AI, RAG, Maintenance tests, and profile load compare the live
llama-server on :8080 to that row.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from spock_shell.paths import SHIP_COMPUTER_DB

CORPUS_TABLE = """
CREATE TABLE IF NOT EXISTS kb_embedding_corpus (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    model_path TEXT NOT NULL DEFAULT '',
    model_name TEXT NOT NULL DEFAULT '',
    model_id TEXT NOT NULL DEFAULT '',
    embeddings_url TEXT NOT NULL DEFAULT '',
    embeddings_dim INTEGER,
    recorded_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'wiki_scan'
)
"""


def fold_path(text: str) -> str:
    return os.path.normcase(str(text or "").strip()).replace("\\", "/")


def model_basename(path: str) -> str:
    return os.path.basename(str(path or "").replace("\\", "/").rstrip("/")) or ""


def is_gguf_path(path: str) -> bool:
    low = str(path or "").strip().lower().replace("\\", "/")
    return low.endswith(".gguf") or low.endswith(".ggml")


def resolve_gguf_identity(path: str = "", model_id: str = "") -> str:
    """Best GGUF identity from a path and/or model id.

    Embedding profiles sometimes store a *directory* in ``model_path`` and the
    filename in ``model_id``. A bare directory must not be compared as a GGUF
    (basename would be ``models`` and false-mismatch KB/live).
    """
    p = str(path or "").strip()
    mid = str(model_id or "").strip()
    if p and is_gguf_path(p):
        return p
    if p and os.path.isdir(p) and mid and is_gguf_path(mid):
        joined = os.path.join(p, model_basename(mid))
        if os.path.isfile(joined):
            return joined
        return mid
    if mid and is_gguf_path(mid):
        return mid
    if p and os.path.isfile(p):
        return p
    return ""


def models_match(a: str, b: str) -> bool:
    """True if two GGUF identities are the same path or the same basename."""
    fa, fb = fold_path(a), fold_path(b)
    if not fa or not fb:
        return False
    if fa == fb:
        return True
    return fold_path(model_basename(a)) == fold_path(model_basename(b))


def ensure_schema(db_path: str = "") -> str:
    from WarpCore.ship_schema import ensure_ship_computer_schema

    path = ensure_ship_computer_schema(db_path or SHIP_COMPUTER_DB)
    conn = sqlite3.connect(path, timeout=30)
    try:
        conn.execute(CORPUS_TABLE)
        cols = {
            r[1]
            for r in conn.execute("PRAGMA table_info(documents)").fetchall()
        }
        if "embedding_model_path" not in cols:
            conn.execute(
                "ALTER TABLE documents ADD COLUMN embedding_model_path TEXT"
            )
        if "embedding_dim" not in cols:
            conn.execute("ALTER TABLE documents ADD COLUMN embedding_dim INTEGER")
        conn.commit()
    finally:
        conn.close()
    return path


def read_corpus(db_path: str = "") -> Optional[Dict[str, Any]]:
    path = db_path or SHIP_COMPUTER_DB
    if not os.path.isfile(path):
        return None
    ensure_schema(path)
    conn = sqlite3.connect(path, timeout=30)
    try:
        row = conn.execute(
            """
            SELECT model_path, model_name, model_id, embeddings_url,
                   embeddings_dim, recorded_at, source
            FROM kb_embedding_corpus WHERE id = 1
            """
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
    if not row:
        return None
    return {
        "model_path": str(row[0] or ""),
        "model_name": str(row[1] or "") or model_basename(str(row[0] or "")),
        "model_id": str(row[2] or ""),
        "embeddings_url": str(row[3] or ""),
        "embeddings_dim": int(row[4]) if row[4] is not None else None,
        "recorded_at": str(row[5] or ""),
        "source": str(row[6] or ""),
    }


def write_corpus(
    *,
    model_path: str,
    embeddings_url: str,
    embeddings_dim: Optional[int] = None,
    model_id: str = "",
    source: str = "wiki_scan",
    db_path: str = "",
) -> Dict[str, Any]:
    path = ensure_schema(db_path or SHIP_COMPUTER_DB)
    model_path = str(model_path or "").strip()
    name = model_basename(model_path)
    recorded = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = sqlite3.connect(path, timeout=30)
    try:
        conn.execute(
            """
            INSERT INTO kb_embedding_corpus
                (id, model_path, model_name, model_id, embeddings_url,
                 embeddings_dim, recorded_at, source)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                model_path = excluded.model_path,
                model_name = excluded.model_name,
                model_id = excluded.model_id,
                embeddings_url = excluded.embeddings_url,
                embeddings_dim = excluded.embeddings_dim,
                recorded_at = excluded.recorded_at,
                source = excluded.source
            """,
            (
                model_path,
                name,
                str(model_id or ""),
                str(embeddings_url or ""),
                int(embeddings_dim) if embeddings_dim is not None else None,
                recorded,
                str(source or "wiki_scan"),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return read_corpus(path) or {}


def probe_live_model(
    embeddings_url: str = "http://localhost:8080/embeddings",
    *,
    timeout: float = 2.0,
) -> Dict[str, Any]:
    """Ask the llama-server behind embeddings_url which GGUF is loaded."""
    from spock_health_report import embeddings_host_port, probe_llama_server

    host, port = embeddings_host_port(embeddings_url)
    info = probe_llama_server(host, port, role_hint="embedding", timeout=timeout)
    path = str(info.get("model_path") or "")
    return {
        "reachable": bool(info.get("reachable")),
        "model_path": path,
        "model_name": str(info.get("model_name") or "") or model_basename(path),
        "host": host,
        "port": port,
        "detail": str(info.get("detail") or ""),
        "embeddings_url": embeddings_url,
    }


def record_from_live_server(
    embeddings_url: str,
    *,
    embeddings_dim: Optional[int] = None,
    model_id: str = "",
    db_path: str = "",
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Probe :8080 and persist kb_embedding_corpus. False if server/model unknown."""
    live = probe_live_model(embeddings_url)
    if not live.get("reachable"):
        return False, (
            "Embedding server is not answering on "
            f"{live.get('host')}:{live.get('port')}. "
            "Launch the embedding GGUF on :8080 before Wiki Scan."
        ), live
    if not live.get("model_path"):
        return False, (
            "Embedding server is up but did not report a GGUF path "
            "(/props or /v1/models). Will not scan under an unknown model."
        ), live
    row = write_corpus(
        model_path=str(live["model_path"]),
        embeddings_url=embeddings_url,
        embeddings_dim=embeddings_dim,
        model_id=model_id,
        db_path=db_path,
    )
    return True, f"Recording embeddings from {row.get('model_name') or row.get('model_path')}", row


def live_vs_corpus(
    embeddings_url: str = "",
    *,
    profile_model_path: str = "",
    profile_model_id: str = "",
    db_path: str = "",
) -> Dict[str, Any]:
    """Compare live :8080, optional profile GGUF, and kb_embedding_corpus.

    Hard mismatch is live server vs KB corpus (what actually embeds vs stored
    vectors). Profile path is advisory: a directory-only ``model_path`` is
    ignored unless ``model_id`` / a joined file yields a real GGUF identity.
    """
    corpus = read_corpus(db_path)
    url = embeddings_url or (corpus or {}).get("embeddings_url") or (
        "http://localhost:8080/embeddings"
    )
    live = probe_live_model(url)
    corpus_path = str((corpus or {}).get("model_path") or "")
    live_path = str(live.get("model_path") or "")
    profile_path = resolve_gguf_identity(profile_model_path, profile_model_id)
    out: Dict[str, Any] = {
        "corpus": corpus,
        "live": live,
        "profile_model_path": profile_path or str(profile_model_path or ""),
        "ok": True,
        "mismatch": False,
        "profile_mismatch": False,
        "port_occupied_wrong_model": False,
        "message": "",
    }
    if not corpus_path:
        return out
    # Blocking: live GGUF must match the wiki-scan corpus when the server is up.
    if live.get("reachable") and live_path and not models_match(live_path, corpus_path):
        out["ok"] = False
        out["mismatch"] = True
        out["port_occupied_wrong_model"] = True
    # Advisory: profile GGUF (if resolvable) differs from corpus/live.
    if profile_path and corpus_path and not models_match(profile_path, corpus_path):
        out["profile_mismatch"] = True
    if profile_path and live_path and live.get("reachable") and not models_match(
        profile_path, live_path
    ):
        out["profile_mismatch"] = True
    if out["mismatch"]:
        out["message"] = format_mismatch(
            corpus_path=corpus_path,
            live_path=live_path if live.get("reachable") else "",
            profile_path=profile_path,
            live_reachable=bool(live.get("reachable")),
        )
    elif out["profile_mismatch"]:
        out["message"] = (
            format_mismatch(
                corpus_path=corpus_path,
                live_path=live_path if live.get("reachable") else "",
                profile_path=profile_path,
                live_reachable=bool(live.get("reachable")),
            )
            + "\n\nNote: live server matches the KB; only the saved profile "
            "path/id looks stale. Wiki Scan can proceed."
        )
    return out


def format_mismatch(
    *,
    corpus_path: str,
    live_path: str = "",
    profile_path: str = "",
    live_reachable: bool = True,
) -> str:
    lines = [
        "The knowledge base embeddings were built with a different GGUF "
        "than the embedding server (or this profile) is using.",
        "",
        f"KB (wiki-scan):  {model_basename(corpus_path) or corpus_path or '—'}",
    ]
    if profile_path:
        lines.append(
            f"This profile:    {model_basename(profile_path) or profile_path}"
        )
    if live_reachable:
        lines.append(
            f"Live on :8080:   {model_basename(live_path) or live_path or '(unknown)'}"
        )
    else:
        lines.append("Live on :8080:   (not reachable)")
    lines.extend(
        [
            "",
            "Launch the matching embedding GGUF on :8080, or re-run Wiki Scan "
            "after a model upgrade so the stored vectors match.",
        ]
    )
    return "\n".join(lines)


def assert_live_matches_corpus(
    embeddings_url: str = "",
    *,
    db_path: str = "",
) -> None:
    """Raise RuntimeError when a corpus exists and live :8080 is a different GGUF."""
    report = live_vs_corpus(embeddings_url, db_path=db_path)
    if report.get("mismatch") and report.get("message"):
        raise RuntimeError(report["message"])


def guarded_hybrid_search(hybrid_search_fn):
    """Wrap WarpCore.hybrid_search so a wrong :8080 GGUF fails instead of mixing spaces."""

    def _wrapped(*args, **kwargs):
        url = str(kwargs.get("embeddings_url") or "")
        assert_live_matches_corpus(url)
        return hybrid_search_fn(*args, **kwargs)

    return _wrapped


def model_counts(db_path: str = "") -> Dict[str, int]:
    path = db_path or SHIP_COMPUTER_DB
    if not os.path.isfile(path):
        return {}
    ensure_schema(path)
    conn = sqlite3.connect(path, timeout=30)
    try:
        rows = conn.execute(
            """
            SELECT COALESCE(NULLIF(embedding_model_path, ''), '(unstamped)'),
                   COUNT(*)
            FROM documents
            WHERE embedding IS NOT NULL
            GROUP BY 1
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()
    return {str(k): int(v) for k, v in rows}


def profile_embedding_path(payload: Optional[Dict[str, Any]]) -> str:
    cfg = (payload or {}).get("config") or {}
    ep = cfg.get("embedding_profile") or {}
    path = str(ep.get("model_path") or "").strip()
    if path:
        return path
    for srv in (payload or {}).get("servers") or []:
        if not isinstance(srv, dict):
            continue
        if str(srv.get("role") or "").lower() == "embedding":
            return str(srv.get("model_path") or "").strip()
    return ""
