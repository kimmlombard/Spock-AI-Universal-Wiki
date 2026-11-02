"""Spock-to-bridge MCP adapter for Cursor / Codex / OpenCode / llama.cpp WebUI.

Foundation: Gemma AI Helper scripts/mcp_gemma_server.py (FastMCP + file logging).

Transports (env SPOCK_MCP_TRANSPORT):
  stdio (default)     — Cursor/OpenCode mcp.json
  streamable-http     — llama.cpp browser MCP URL http://127.0.0.1:8765/mcp
  sse                 — legacy SSE URL http://127.0.0.1:8765/sse

Tools call Spock's RAG API when available, and read ship_computer.db / scanner
helpers directly so the adapter works even without GUI imports (avoids PyQt6).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import sys
import tempfile
import warnings
from pathlib import Path
from typing import Any, Literal, Optional

import requests

# FastMCP still imports deprecated authlib.jose. Authlib registers
# simplefilter("always", AuthlibDeprecationWarning), so ignore must be applied
# *after* that import and target AuthlibDeprecationWarning specifically.
try:
    from authlib.deprecate import AuthlibDeprecationWarning
except Exception:  # pragma: no cover
    AuthlibDeprecationWarning = DeprecationWarning  # type: ignore[misc,assignment]
warnings.filterwarnings("ignore", category=AuthlibDeprecationWarning)

from fastmcp import FastMCP  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _setup_logging() -> str:
    """
    MCP STDIO servers shouldn't write to stdout (it can corrupt protocol output).
    We log to a file so startup failures are debuggable when Cursor/Codex spawns us.
    """
    log_path = os.getenv("SPOCK_MCP_LOG_PATH")
    if not log_path:
        log_dir = ROOT / "logs"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = str(log_dir / "spock-mcp.log")
        except OSError:
            log_path = os.path.join(tempfile.gettempdir(), "spock-mcp.log")

    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.info("Starting Spock MCP adapter")
    logging.info("python=%s", sys.executable)
    logging.info("cwd=%s", os.getcwd())
    logging.info("SPOCK_API_BASE_URL=%s", os.getenv("SPOCK_API_BASE_URL"))
    logging.info("SPOCK_DB_PATH=%s", os.getenv("SPOCK_DB_PATH"))
    logging.info("SPOCK_API_KEY set=%s", bool(os.getenv("SPOCK_API_KEY")))
    return log_path


def _load_app_config() -> dict[str, Any]:
    try:
        import _warpcore_path

        _warpcore_path.ensure()
        from WarpCore import settings_store

        return settings_store.load_app_config(str(ROOT / "ship_computer.db"))
    except Exception:
        pass
    cfg_path = ROOT / "app_config.json"
    if not cfg_path.is_file():
        return {}
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        logging.exception("Failed to read app_config.json")
        return {}


def _api_base() -> str:
    env = os.getenv("SPOCK_API_BASE_URL", "").strip()
    if env:
        return env.rstrip("/")
    rag = (_load_app_config().get("rag_api") or {})
    host = rag.get("host", "127.0.0.1")
    port = int(rag.get("port", 8090))
    return f"http://{host}:{port}".rstrip("/")


def _api_key() -> str:
    env = os.getenv("SPOCK_API_KEY", "").strip()
    if env:
        return env
    rag = (_load_app_config().get("rag_api") or {})
    return str(rag.get("api_key") or "").strip()


def _headers() -> dict[str, str]:
    key = _api_key()
    if not key:
        return {}
    return {"Authorization": f"Bearer {key}"}


def _db_path() -> str:
    env = os.getenv("SPOCK_DB_PATH", "").strip()
    if env:
        return env
    return str(ROOT / "ship_computer.db")


def _connect(db: str, timeout: float = 30.0) -> sqlite3.Connection:
    try:
        from WarpCore.db import connect as _wc_connect

        conn = _wc_connect(db, timeout=timeout)
    except Exception:
        conn = sqlite3.connect(db, timeout=timeout)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=%d" % int(timeout * 1000))
        conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def _embeddings_url() -> str:
    env = os.getenv("SPOCK_EMBEDDINGS_URL", "").strip()
    if env:
        return env
    profile = (_load_app_config().get("embedding_profile") or {})
    return str(profile.get("embeddings_url") or "http://localhost:8080/embeddings")


mcp = FastMCP("Spock-to-bridge (local)")


@mcp.tool()
def spock_health() -> dict[str, Any]:
    """Probe Spock RAG API /health, llama :8080/:8081, MCP adapter, and --ui-mcp-proxy."""
    from spock_health_report import probe_spock_health

    cfg = _load_app_config()
    mcp = cfg.get("mcp") or {}
    try:
        chat_port = int(cfg.get("llama_port") or 8081)
    except (TypeError, ValueError):
        chat_port = 8081
    try:
        mcp_port = int(mcp.get("http_port") or cfg.get("mcp_http_port") or 8765)
    except (TypeError, ValueError):
        mcp_port = 8765
    try:
        webui_port = int(mcp.get("webui_port") or 8082)
    except (TypeError, ValueError):
        webui_port = 8082
    return probe_spock_health(
        api_base=_api_base(),
        db_path=_db_path(),
        embeddings_url=_embeddings_url(),
        api_key=os.getenv("SPOCK_API_KEY", "").strip()
        or str((cfg.get("rag_api") or {}).get("api_key") or ""),
        chat_host=str(cfg.get("llama_host") or "localhost"),
        chat_port=chat_port,
        mcp_host=str(mcp.get("http_host") or "127.0.0.1"),
        mcp_port=mcp_port,
        mcp_transport=str(mcp.get("transport") or "streamable-http"),
        webui_host=str(mcp.get("webui_host") or "127.0.0.1"),
        webui_port=webui_port,
    )


@mcp.tool()
def spock_ask(question: str, model: str = "spock-ships-computer") -> dict[str, Any]:
    """Ask Spock RAG (OpenAI-compatible chat) with ship_computer.db context."""
    if not (question or "").strip():
        raise ValueError("question is required")
    url = f"{_api_base()}/v1/chat/completions"
    r = requests.post(
        url,
        headers={**_headers(), "Content-Type": "application/json"},
        json={
            "model": model or "spock-ships-computer",
            "messages": [{"role": "user", "content": question}],
        },
        timeout=180,
    )
    r.raise_for_status()
    data = r.json()
    answer = ""
    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        answer = ""
    return {"answer": answer, "raw": data}


_FTS_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "if", "then", "else", "when",
        "where", "why", "how", "what", "which", "who", "is", "are", "was",
        "were", "be", "to", "of", "in", "on", "at", "for", "from", "by",
        "with", "this", "that", "it", "as", "can", "please", "me", "my",
    }
)


def _fts_match(query: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*", query or "")
    parts: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        low = tok.lower()
        if len(tok) < 2 or low in _FTS_STOPWORDS or low in seen:
            continue
        seen.add(low)
        if re.search(r"[^A-Za-z0-9_]", tok):
            parts.append(f'"{tok}"')
        else:
            parts.append(tok)
    if parts:
        return " OR ".join(parts)
    return re.sub(r"[^\w\s]", " ", query or "").strip()


@mcp.tool()
def spock_search_kb(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Keyword search ship_computer.db (FTS5 docs_fts, LIKE fallback)."""
    if not (query or "").strip():
        raise ValueError("query is required")
    limit = max(1, min(int(limit), 100))
    db = _db_path()
    if not os.path.isfile(db):
        raise FileNotFoundError(f"Database not found: {db}")

    conn = _connect(db)
    conn.row_factory = sqlite3.Row
    results: list[dict[str, Any]] = []
    match = _fts_match(query)
    try:
        if match:
            rows = conn.execute(
                """
                SELECT d.id AS doc_id, d.title, d.path, d.content_plain, f.rank AS score
                FROM docs_fts f
                JOIN documents d ON d.id = f.rowid
                WHERE docs_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (match, limit),
            ).fetchall()
            for row in rows:
                content = row["content_plain"] or ""
                snippet = content[:1200] + ("..." if len(content) > 1200 else "")
                results.append(
                    {
                        "doc_id": row["doc_id"],
                        "title": row["title"],
                        "path": row["path"],
                        "score": row["score"],
                        "snippet": snippet,
                        "source": "fts5",
                    }
                )
    except sqlite3.Error as e:
        logging.info("FTS search failed (%s); trying LIKE", e)

    if not results:
        terms = [t for t in re.findall(r"[A-Za-z0-9_]{2,}", query) if t.lower() not in _FTS_STOPWORDS][:6]
        if terms:
            clauses = []
            params: list[Any] = []
            for t in terms:
                clauses.append("(title LIKE ? OR path LIKE ? OR content_plain LIKE ?)")
                pat = f"%{t}%"
                params.extend([pat, pat, pat])
            sql = (
                "SELECT id AS doc_id, title, path, content_plain FROM documents WHERE ("
                + " OR ".join(clauses)
                + ") LIMIT ?"
            )
            params.append(limit * 4)
            try:
                rows = conn.execute(sql, params).fetchall()
                scored: list[tuple[int, sqlite3.Row]] = []
                lower_terms = [t.lower() for t in terms]
                for row in rows:
                    blob = f"{row['title'] or ''}\n{row['path'] or ''}\n{row['content_plain'] or ''}".lower()
                    hits = sum(1 for t in lower_terms if t in blob)
                    if hits:
                        scored.append((hits, row))
                scored.sort(key=lambda x: x[0], reverse=True)
                for hits, row in scored[:limit]:
                    content = row["content_plain"] or ""
                    snippet = content[:1200] + ("..." if len(content) > 1200 else "")
                    results.append(
                        {
                            "doc_id": row["doc_id"],
                            "title": row["title"],
                            "path": row["path"],
                            "score": float(hits),
                            "snippet": snippet,
                            "source": "like",
                        }
                    )
            except sqlite3.Error:
                logging.exception("LIKE search failed")
    conn.close()
    return results


@mcp.tool()
def spock_status() -> dict[str, Any]:
    """Full Spock status: RAG/llama/MCP health report + hardware ship-status.

    Same enhancements as the GUI \"Run Spock Status\" / MCP \"Run spock-status\"
    report (API, embeddings :8080 ctx, chat :8081 ctx, MCP adapter, --ui-mcp-proxy),
    plus scanner ship-status / GPU details.
    """
    from spock_health_report import format_spock_health_report, probe_spock_health

    cfg = _load_app_config()
    mcp = cfg.get("mcp") or {}
    try:
        chat_port = int(cfg.get("llama_port") or 8081)
    except (TypeError, ValueError):
        chat_port = 8081
    try:
        mcp_port = int(mcp.get("http_port") or cfg.get("mcp_http_port") or 8765)
    except (TypeError, ValueError):
        mcp_port = 8765
    try:
        webui_port = int(mcp.get("webui_port") or 8082)
    except (TypeError, ValueError):
        webui_port = 8082

    health = probe_spock_health(
        api_base=_api_base(),
        db_path=_db_path(),
        embeddings_url=_embeddings_url(),
        api_key=os.getenv("SPOCK_API_KEY", "").strip()
        or str((cfg.get("rag_api") or {}).get("api_key") or ""),
        chat_host=str(cfg.get("llama_host") or "localhost"),
        chat_port=chat_port,
        mcp_host=str(mcp.get("http_host") or "127.0.0.1"),
        mcp_port=mcp_port,
        mcp_transport=str(mcp.get("transport") or "streamable-http"),
        webui_host=str(mcp.get("webui_host") or "127.0.0.1"),
        webui_port=webui_port,
    )
    out: dict[str, Any] = {
        "health": health,
        "health_report": format_spock_health_report(health),
        "db": _db_counts(),
        "rag_api": _api_base(),
        "embeddings_url": _embeddings_url(),
    }

    try:
        from spock_scanner_core import (
            format_ship_status,
            get_gpu_details,
            run_ship_status_scan,
        )

        data = run_ship_status_scan()
        gpu = get_gpu_details()
        out["ship_status"] = data
        out["ship_status_text"] = format_ship_status(data)
        out["gpu_details"] = {
            "available": gpu.get("available"),
            "error": gpu.get("error"),
            "gpus": gpu.get("gpus") if gpu.get("available") else [],
        }
    except Exception as e:
        out["ship_status_error"] = f"Could not import/run spock_scanner_core: {e}"

    return out


def _db_counts() -> dict[str, Any]:
    db = _db_path()
    if not os.path.isfile(db):
        return {"exists": False, "path": db}
    try:
        conn = _connect(db)
        docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        emb = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE embedding IS NOT NULL"
        ).fetchone()[0]
        logs = conn.execute("SELECT COUNT(*) FROM captains_log").fetchone()[0]
        queue = conn.execute("SELECT COUNT(*) FROM agent_queue").fetchone()[0]
        quar = conn.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]
        conn.close()
        return {
            "exists": True,
            "path": db,
            "documents": docs,
            "embeddings": emb,
            "captains_log": logs,
            "agent_queue": queue,
            "quarantine": quar,
            "size_mb": round(os.path.getsize(db) / (1024 * 1024), 2),
        }
    except Exception as e:
        return {"exists": True, "path": db, "error": str(e)}


@mcp.tool()
def spock_queue(
    limit: int = 20,
    status: Optional[str] = None,
) -> dict[str, Any]:
    """Sample agent_queue rows (and optional status filter)."""
    limit = max(1, min(int(limit), 200))
    db = _db_path()
    if not os.path.isfile(db):
        raise FileNotFoundError(f"Database not found: {db}")
    conn = _connect(db)
    conn.row_factory = sqlite3.Row
    cols = [r[1] for r in conn.execute("PRAGMA table_info(agent_queue)").fetchall()]
    sql = "SELECT * FROM agent_queue"
    params: list[Any] = []
    if status and "status" in cols:
        sql += " WHERE status = ?"
        params.append(status)
    # newest first when possible
    if "id" in cols:
        sql += " ORDER BY id DESC"
    sql += " LIMIT ?"
    params.append(limit)
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    counts: dict[str, int] = {}
    if "status" in cols:
        for r in conn.execute(
            "SELECT status, COUNT(*) AS n FROM agent_queue GROUP BY status"
        ):
            counts[str(r["status"])] = int(r["n"])
    else:
        counts["total"] = conn.execute("SELECT COUNT(*) FROM agent_queue").fetchone()[0]
    conn.close()
    return {"counts": counts, "rows": rows}


@mcp.tool()
def spock_captains_log(
    limit: int = 20,
    alert_level: Optional[Literal["GREEN", "YELLOW", "RED"]] = None,
    officer: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Recent captains_log entries from ship_computer.db."""
    limit = max(1, min(int(limit), 200))
    db = _db_path()
    if not os.path.isfile(db):
        raise FileNotFoundError(f"Database not found: {db}")
    conn = _connect(db)
    conn.row_factory = sqlite3.Row
    clauses: list[str] = []
    params: list[Any] = []
    if alert_level:
        clauses.append("alert_level = ?")
        params.append(alert_level)
    if officer:
        clauses.append("officer = ?")
        params.append(officer)
    sql = "SELECT * FROM captains_log"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


@mcp.tool()
def spock_llmfit_fit(limit: int = 10) -> dict[str, Any]:
    """Rank models that fit this machine via local llmfit (tok/s + fit level).

    Requires ``llmfit`` on PATH or ``{SPOCK_ROOT}/tools/llmfit``.
    Degrades with ``available: false`` when the binary is missing.
    """
    from spock_onboarding import llmfit_bridge as bridge

    limit = max(1, min(int(limit), 50))
    if not bridge.available():
        return {
            "available": False,
            "error": "llmfit binary not found (set SPOCK_LLMFIT_EXE or install llmfit)",
            "models": [],
        }
    data = bridge.fit(limit=limit) or bridge.recommend(limit=limit, force_runtime="llamacpp")
    if not isinstance(data, dict):
        return {"available": True, "error": "llmfit returned no JSON", "models": []}
    models = data.get("models") if isinstance(data.get("models"), list) else []
    slim = []
    for m in models:
        if not isinstance(m, dict):
            continue
        slim.append(
            {
                "name": m.get("name"),
                "estimated_tps": m.get("estimated_tps"),
                "fit_level": m.get("fit_level") or m.get("fit_label"),
                "run_mode": m.get("run_mode") or m.get("run_mode_label"),
                "memory_required_gb": m.get("memory_required_gb"),
                "memory_available_gb": m.get("memory_available_gb"),
                "best_quant": m.get("best_quant"),
                "params_b": m.get("params_b"),
                "score": m.get("score"),
            }
        )
    return {
        "available": True,
        "system": data.get("system"),
        "models": slim,
        "count": len(slim),
    }


@mcp.tool()
def spock_hardware_plan(
    model: str,
    context: int = 8192,
    quant: Optional[str] = None,
) -> dict[str, Any]:
    """Plan VRAM/RAM/tok/s for a model via local ``llmfit plan … --json``.

    Also returns Spock's suggested llama-server ``-ngl`` derived from the plan.
    """
    from spock_onboarding import llmfit_bridge as bridge

    model = (model or "").strip()
    if not model:
        raise ValueError("model is required")
    context = max(512, min(int(context), 1_048_576))
    if not bridge.available():
        return {
            "available": False,
            "error": "llmfit binary not found (set SPOCK_LLMFIT_EXE or install llmfit)",
            "model": model,
            "context": context,
        }
    plan = bridge.plan(model, context=context, quant=quant)
    if not isinstance(plan, dict):
        return {
            "available": True,
            "error": f"No llmfit plan for model {model!r}",
            "model": model,
            "context": context,
        }
    ngl, ngl_reason = bridge.suggest_ngl_from_payloads(plan_data=plan)
    return {
        "available": True,
        "model": model,
        "context": context,
        "quant": quant,
        "plan": plan,
        "suggested_ngl": ngl,
        "ngl_reason": ngl_reason,
    }


if __name__ == "__main__":
    log_path = _setup_logging()
    # stdio = Cursor/OpenCode (default). sse / http = llama.cpp browser MCP URL.
    transport = (os.getenv("SPOCK_MCP_TRANSPORT") or "stdio").strip().lower()
    if transport in ("http", "streamable-http", "streamable_http"):
        transport = "streamable-http"
    elif transport in ("sse", "http-sse"):
        transport = "sse"
    else:
        transport = "stdio"

    host = (os.getenv("SPOCK_MCP_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    try:
        port = int(os.getenv("SPOCK_MCP_PORT") or "8765")
    except ValueError:
        port = 8765

    logging.info("transport=%s host=%s port=%s", transport, host, port)
    try:
        if transport == "stdio":
            mcp.run(transport="stdio")
        else:
            # Browser clients (llama.cpp WebUI on :8080) need CORS; without it
            # fetch() fails with "Failed to fetch (check CORS?)".
            from starlette.middleware import Middleware
            from starlette.middleware.cors import CORSMiddleware

            cors = [
                Middleware(
                    CORSMiddleware,
                    allow_origins=["*"],
                    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                    allow_headers=["*"],
                    expose_headers=["mcp-session-id", "MCP-Session-Id"],
                    # Chrome Private Network Access: WebUI :8082 → MCP :8765
                    allow_private_network=True,
                )
            ]
            # streamable-http → http://127.0.0.1:8765/mcp
            # sse             → http://127.0.0.1:8765/sse
            mcp.run(
                transport=transport,
                host=host,
                port=port,
                middleware=cors,
                show_banner=False,
            )
    except Exception:
        logging.exception("MCP server crashed. Log: %s", log_path)
        raise
