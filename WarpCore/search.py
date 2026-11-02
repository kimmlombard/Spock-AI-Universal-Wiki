"""Search + embeddings: pure logic, no PyQt — usable from any process.

Moved out of the monolith (Spock-to-bridge.py) so wiki_agent, RAG API, and the
GUI all share one implementation. All functions are standalone; callers pass a
db_path and get plain data back.
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import struct
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .db import (
    _SQLITE_VEC_AVAILABLE,
    _VEC_TABLE_NAME,
    connect,
    ensure_documents_vec,
    rebuild_documents_vec,
    vec_table_exists,
)


def _connect(db_path: str, timeout: float = 30.0) -> sqlite3.Connection:
    return connect(db_path, timeout=timeout)

EMBEDDINGS_URL = os.environ.get("EMBEDDINGS_URL", "http://localhost:8080/embeddings")


@dataclass
class SearchResult:
    """Search result from vector/FTS search"""

    doc_id: int
    title: str
    path: str
    score: float
    content_snippet: str


def set_embeddings_url(url: str) -> None:
    """Update the module-level embeddings endpoint used by RAG search."""
    global EMBEDDINGS_URL
    EMBEDDINGS_URL = url


def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def deserialize_embedding(blob: Optional[bytes]) -> Optional[List[float]]:
    if blob is None:
        return None
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def get_query_embedding(text: str, url: Optional[str] = None) -> Optional[List[float]]:
    """Get embedding vector from llama-server"""
    if url is None:
        url = EMBEDDINGS_URL
    payload = json.dumps({"input": text}).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception:
        return None

    try:
        from spock_rag_adapter.embedding_utils import embedding_from_response

        return embedding_from_response(data)
    except ValueError:
        raise
    except Exception:
        return None


def make_snippet(
    content: str,
    terms=None,
    max_chars: int = 3000,
    context_chars: int = 800,
) -> str:
    """Build a snippet centered on the first matched term, clipped at line/
    sentence boundaries. Falls back to a plain prefix when nothing matches."""
    if not content:
        return ""
    text = content.strip()
    if len(text) <= max_chars:
        return text

    low = text.lower()
    pos = -1
    for t in terms or ():
        if not t:
            continue
        idx = low.find(t.lower())
        if idx >= 0 and (pos < 0 or idx < pos):
            pos = idx

    if pos < 0:
        return text[:max_chars].rstrip() + "..."

    half = max_chars // 2
    start = max(0, pos - half)
    end = min(len(text), pos + half)

    # Align start to a line boundary just before the match (avoid mid-line).
    if start > 0:
        nl = text.find("\n", start)
        if 0 <= nl < pos:
            start = nl + 1
        else:
            prev_nl = text.rfind("\n", 0, start)
            if start - prev_nl <= context_chars:
                start = prev_nl + 1
            else:
                prev_dot = text.rfind(". ", 0, start)
                if start - prev_dot <= context_chars:
                    start = prev_dot + 2

    # Align end back to a line boundary after the match (avoid mid-line).
    if end < len(text):
        nl = text.find("\n", pos)
        if 0 < nl < end:
            end = nl
        else:
            prev_nl = text.rfind("\n", pos, end)
            if prev_nl > pos:
                end = prev_nl
            else:
                dot = text.find(". ", pos)
                if 0 < dot < end:
                    end = dot + 2

    snippet = text[start:end].strip()
    if not snippet:
        return text[:max_chars].rstrip() + "..."
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return prefix + snippet + suffix


def vector_search(
    db_path: str,
    query: str,
    top_k: int = 10,
    threshold: float = 0.25,
    embeddings_url: Optional[str] = None,
    filter_clause: str = "",
) -> List[SearchResult]:
    """Search documents by embedding similarity"""
    if embeddings_url is None:
        embeddings_url = EMBEDDINGS_URL
    query_vec = get_query_embedding(query, embeddings_url)
    if query_vec is None:
        return []

    conn = _connect(db_path)
    try:
        # Try sqlite-vec first if available
        if _SQLITE_VEC_AVAILABLE:
            if not vec_table_exists(conn):
                # Lazy-build on first search if embeddings already exist
                rebuild_documents_vec(conn)
            if vec_table_exists(conn):
                ensure_documents_vec(conn)
                try:
                    from sqlite_vec import serialize_float32  # type: ignore

                    qser = serialize_float32(query_vec)
                    overfetch = max(top_k * 10, 50) if filter_clause else top_k
                    base_sql = (
                        f"SELECT d.id, d.title, d.path, d.content_plain, t.distance "
                        f"FROM (SELECT doc_id, distance FROM {_VEC_TABLE_NAME} "
                        f"WHERE embedding MATCH ? ORDER BY distance ASC LIMIT ?) t "
                        f"JOIN documents d ON d.id = t.doc_id"
                    )
                    params: List[Any] = [qser, overfetch]
                    if filter_clause:
                        base_sql += f" WHERE ({filter_clause})"
                    base_sql += " ORDER BY t.distance ASC LIMIT ?"
                    params.append(top_k)
                    rows = conn.execute(base_sql, params).fetchall()
                    results: List[SearchResult] = []
                    for doc_id, title, path, content, dist in rows:
                        # vec0 uses Euclidean (L2) distance on unit-normalized vectors;
                        # cos_sim = 1 - d^2/2
                        d = float(dist)
                        sim = 1.0 - (d * d) / 2.0
                        if sim < threshold:
                            continue
                        snippet = make_snippet(content or "", terms=extract_search_terms(query))
                        results.append(SearchResult(int(doc_id), title or "", path or "", sim, snippet))
                    results.sort(key=lambda r: r.score, reverse=True)
                    return results
                except Exception:
                    pass

        # Fallback to full scan
        sql = "SELECT id, title, path, content_plain, embedding FROM documents WHERE embedding IS NOT NULL"
        if filter_clause:
            sql += f" AND ({filter_clause})"
        rows = conn.execute(sql).fetchall()
        results = []
        for doc_id, title, path, content, blob in rows:
            doc_vec = deserialize_embedding(blob)
            if doc_vec and len(doc_vec) == len(query_vec):
                sim = cosine_similarity(query_vec, doc_vec)
                if sim >= threshold:
                    snippet = make_snippet(content or "", terms=extract_search_terms(query))
                    results.append(SearchResult(doc_id, title, path, sim, snippet))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]
    finally:
        conn.close()


_FTS_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "if", "then", "else", "when",
        "where", "why", "how", "what", "which", "who", "whom", "whose",
        "is", "are", "was", "were", "be", "been", "being", "do", "does",
        "did", "doing", "to", "of", "in", "on", "at", "for", "from", "by",
        "with", "about", "into", "over", "after", "before", "between",
        "this", "that", "these", "those", "it", "its", "as", "can", "could",
        "should", "would", "will", "just", "than", "too", "very", "also",
        "python", "app", "application", "please", "me", "my", "our",
        "work", "works", "working", "use", "used", "using",
    }
)


def extract_search_terms(query: str) -> List[str]:
    """Pull meaningful tokens from a natural-language Ask AI question."""
    tokens = re.findall(r"[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*", query or "")
    terms: List[str] = []
    seen = set()
    for tok in tokens:
        low = tok.lower()
        if len(tok) < 2 or low in _FTS_STOPWORDS:
            continue
        if low in seen:
            continue
        seen.add(low)
        terms.append(tok)
    return terms


def sanitize_fts_query(query: str) -> str:
    """Build an FTS5-safe MATCH string (hyphenated names must be quoted)."""
    terms = extract_search_terms(query)
    if not terms:
        cleaned = re.sub(r"[^\w\s]", " ", query or "").strip()
        return cleaned
    parts = []
    for t in terms:
        if re.search(r"[^A-Za-z0-9_]", t):
            parts.append(f'"{t}"')
        else:
            parts.append(t)
    return " OR ".join(parts)


def embeddings_endpoint_ok(
    url: Optional[str] = None,
    timeout: float = 0.5,
    light: bool = False,
) -> Tuple[bool, str]:
    """Return (ok, detail) for the RAG embeddings HTTP endpoint.

    Prefers a cheap GET /health on the same host (no model work). Falls back to a
    tiny POST /embeddings only when light=False.
    """
    if url is None:
        url = EMBEDDINGS_URL
    health_err = ""
    if url.rstrip("/").endswith("/embeddings"):
        health = url.rstrip("/")[: -len("/embeddings")] + "/health"
        try:
            req = urllib.request.Request(health)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    return True, "ok"
                health_err = f"health HTTP {resp.status}"
        except urllib.error.HTTPError as e:
            health_err = f"health HTTP {e.code}"
        except Exception as e:
            health_err = str(e)
        if light:
            return False, health_err or "embeddings host unreachable"

    if light:
        return False, "embeddings URL must end with /embeddings"

    try:
        payload = json.dumps({"input": "ping"}).encode()
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return True, "ok"
            return False, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        if e.code == 501:
            return (
                False,
                "501 Not Implemented — this port is a chat model, not embeddings. "
                "Launch the embedding GGUF on another port and set Embedding Profile.",
            )
        return False, f"HTTP {e.code}"
    except Exception as e:
        detail = str(e)
        if health_err:
            detail = f"{detail} (health: {health_err})"
        return False, detail


def fts_search(
    db_path: str, query: str, top_k: int = 10, filter_clause: str = ""
) -> List[SearchResult]:
    """FTS5 keyword search (sanitized for natural-language questions)."""
    match_q = sanitize_fts_query(query)
    if not match_q:
        return []
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT rowid, rank FROM docs_fts WHERE docs_fts MATCH ? ORDER BY rank LIMIT ?",
            (match_q, top_k),
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return []

    results = []
    for rowid, rank in rows:
        doc_sql = "SELECT id, title, path, content_plain FROM documents WHERE id = ?"
        params: List = [rowid]
        if filter_clause:
            doc_sql += f" AND ({filter_clause})"
        doc = conn.execute(doc_sql, params).fetchone()
        if doc:
            content = doc[3] or ""
            snippet = make_snippet(content, terms=extract_search_terms(query))
            results.append(SearchResult(doc[0], doc[1], doc[2], abs(rank), snippet))
    conn.close()
    return results


def like_search(
    db_path: str, query: str, top_k: int = 10, filter_clause: str = ""
) -> List[SearchResult]:
    """Fallback LIKE search when FTS/vector return nothing."""
    terms = extract_search_terms(query)[:8]
    if not terms:
        return []
    conn = _connect(db_path)
    clauses = []
    params: List = []
    for t in terms:
        clauses.append("(title LIKE ? OR path LIKE ? OR content_plain LIKE ?)")
        pat = f"%{t}%"
        params.extend([pat, pat, pat])
    sql = (
        "SELECT id, title, path, content_plain FROM documents WHERE ("
        + " OR ".join(clauses)
        + ")"
    )
    if filter_clause:
        sql += f" AND ({filter_clause})"
    sql += " LIMIT 80"
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        conn.close()
        return []
    conn.close()

    scored: List[SearchResult] = []
    lower_terms = [t.lower() for t in terms]
    for doc_id, title, path, content in rows:
        blob = f"{title or ''}\n{path or ''}\n{content or ''}".lower()
        hits = sum(1 for t in lower_terms if t.lower() in blob)
        if hits <= 0:
            continue
        snippet = make_snippet(content, terms=terms)
        scored.append(SearchResult(doc_id, title, path, float(hits), snippet))
    scored.sort(key=lambda r: r.score, reverse=True)
    return scored[:top_k]


def hybrid_search(
    db_path: str,
    query: str,
    top_k: int = 10,
    embeddings_url: Optional[str] = None,
    filter_clause: str = "",
) -> List[SearchResult]:
    """Combine vector and FTS5 search results (LIKE fallback if both empty)."""
    if embeddings_url is None:
        embeddings_url = EMBEDDINGS_URL
    vec_results = vector_search(
        db_path, query, top_k=top_k, embeddings_url=embeddings_url, filter_clause=filter_clause
    )
    fts_results = fts_search(db_path, query, top_k=top_k, filter_clause=filter_clause)

    seen_ids = set()
    merged = []

    for r in vec_results:
        if r.doc_id not in seen_ids:
            seen_ids.add(r.doc_id)
            merged.append(r)

    for r in fts_results:
        if r.doc_id not in seen_ids:
            seen_ids.add(r.doc_id)
            merged.append(r)

    if not merged:
        for r in like_search(db_path, query, top_k=top_k, filter_clause=filter_clause):
            if r.doc_id not in seen_ids:
                seen_ids.add(r.doc_id)
                merged.append(r)

    return merged[:top_k]


def has_embeddings(db_path: str) -> bool:
    """Check if the database has embedding data"""
    try:
        conn = _connect(db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE embedding IS NOT NULL"
        ).fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def build_documents_vec(db_path: str) -> int:
    """Build (or rebuild) the sqlite-vec virtual table from documents.embedding."""
    conn = _connect(db_path)
    try:
        return rebuild_documents_vec(conn)
    finally:
        conn.close()
