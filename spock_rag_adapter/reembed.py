"""Clear document embeddings and kb_embedding_corpus for a clean re-embed.

Does NOT delete documents, settings, or profiles — unlike reset.py --mode content.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from spock_rag_adapter.paths import ROOT, SHIP_COMPUTER_DB, ensure_root_on_path

ensure_root_on_path()


def _db_path(db_path: str = "") -> str:
    return str(Path(db_path or SHIP_COMPUTER_DB).resolve())


def clear_embeddings(db_path: str = "") -> Dict[str, Any]:
    """Null document vectors and clear kb_embedding_corpus. Keep document rows."""
    from WarpCore.ship_schema import ensure_ship_computer_schema
    from WarpCore.search import build_documents_vec

    path = _db_path(db_path)
    ensure_ship_computer_schema(path)
    from spock_rag_adapter.embedding_corpus import ensure_schema

    ensure_schema(path)

    conn = sqlite3.connect(path, timeout=60)
    try:
        before_emb = int(
            conn.execute(
                "SELECT COUNT(*) FROM documents WHERE embedding IS NOT NULL"
            ).fetchone()[0]
        )
        before_docs = int(conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
        try:
            before_corpus = int(
                conn.execute("SELECT COUNT(*) FROM kb_embedding_corpus").fetchone()[0]
            )
        except sqlite3.OperationalError:
            before_corpus = 0

        conn.execute(
            """
            UPDATE documents
            SET embedding = NULL,
                embedding_model_path = NULL,
                embedding_dim = NULL
            WHERE embedding IS NOT NULL
               OR embedding_model_path IS NOT NULL
               OR embedding_dim IS NOT NULL
            """
        )
        cleared_docs = conn.total_changes
        try:
            conn.execute("DELETE FROM kb_embedding_corpus")
        except sqlite3.OperationalError:
            pass
        conn.commit()
        build_documents_vec(path)

        after_emb = int(
            conn.execute(
                "SELECT COUNT(*) FROM documents WHERE embedding IS NOT NULL"
            ).fetchone()[0]
        )
        try:
            after_corpus = int(
                conn.execute("SELECT COUNT(*) FROM kb_embedding_corpus").fetchone()[0]
            )
        except sqlite3.OperationalError:
            after_corpus = 0
    finally:
        conn.close()

    return {
        "ok": True,
        "db_path": path,
        "documents_total": before_docs,
        "embeddings_before": before_emb,
        "embeddings_after": after_emb,
        "rows_touched": cleared_docs,
        "corpus_before": before_corpus,
        "corpus_after": after_corpus,
    }


def embedding_status(
    db_path: str = "",
    embeddings_url: str = "http://localhost:8080/embeddings",
) -> Dict[str, Any]:
    """Counts + corpus row + live :8080 probe."""
    from WarpCore.ship_schema import ensure_ship_computer_schema
    from spock_rag_adapter.embedding_corpus import (
        ensure_schema,
        probe_live_model,
        read_corpus,
    )

    path = _db_path(db_path)
    out: Dict[str, Any] = {
        "db_path": path,
        "db_exists": os.path.isfile(path),
        "documents": 0,
        "with_embedding": 0,
        "without_embedding": 0,
        "corpus": None,
        "live": None,
    }
    if not out["db_exists"]:
        out["live"] = probe_live_model(embeddings_url)
        return out

    ensure_ship_computer_schema(path)
    ensure_schema(path)
    conn = sqlite3.connect(path, timeout=30)
    try:
        out["documents"] = int(
            conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        )
        out["with_embedding"] = int(
            conn.execute(
                "SELECT COUNT(*) FROM documents WHERE embedding IS NOT NULL"
            ).fetchone()[0]
        )
        out["without_embedding"] = out["documents"] - out["with_embedding"]
    except sqlite3.OperationalError as e:
        out["error"] = str(e)
    finally:
        conn.close()

    out["corpus"] = read_corpus(path)
    out["live"] = probe_live_model(embeddings_url)
    return out


def format_status(report: Dict[str, Any]) -> str:
    lines = [
        f"Database: {report.get('db_path')}",
        f"Documents: {report.get('documents')}  "
        f"(with embedding: {report.get('with_embedding')}, "
        f"without: {report.get('without_embedding')})",
    ]
    corpus = report.get("corpus") or {}
    if corpus:
        lines.append(
            f"Corpus GGUF: {corpus.get('model_name') or corpus.get('model_path') or '—'}"
        )
        if corpus.get("embeddings_dim") is not None:
            lines.append(f"Corpus dim: {corpus.get('embeddings_dim')}")
    else:
        lines.append("Corpus: (empty - ready for a fresh Wiki Scan record)")
    live = report.get("live") or {}
    if live.get("reachable"):
        lines.append(
            f"Live :8080: {live.get('model_name') or live.get('model_path') or 'up'}"
        )
    else:
        lines.append(
            f"Live :8080: not answering ({live.get('detail') or 'unreachable'})"
        )
    return "\n".join(lines)


def format_clear_result(result: Dict[str, Any]) -> str:
    return "\n".join(
        [
            f"Cleared embeddings in {result.get('db_path')}",
            f"  Documents kept: {result.get('documents_total')}",
            f"  Embeddings before -> after: "
            f"{result.get('embeddings_before')} -> {result.get('embeddings_after')}",
            f"  Rows updated: {result.get('rows_touched')}",
            f"  kb_embedding_corpus: "
            f"{result.get('corpus_before')} -> {result.get('corpus_after')}",
            "",
            "Next:",
            "  1) Launch the new embedding GGUF on :8080 (Bringup step 4 / Navigation Launch)",
            "  2) Confirm Embedding Profile dim matches the model",
            "  3) Run Wiki Scan (Bringup step 9 / Navigation step 6)",
            "     — Scan re-queues every document whose embedding is NULL,",
            "       even when the file itself did not change; the extractor",
            "       will re-embed those rows (it no longer skips on hash match).",
        ]
    )


def _confirm_yes(prompt: str, *, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print("Refusing wipe without --yes (non-interactive).", file=sys.stderr)
        return False
    reply = input(f"{prompt} [y/N] ").strip().lower()
    return reply in ("y", "yes")


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m spock_rag_adapter.reembed",
        description="Clear embeddings / show re-embed status (keeps documents).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    cl = sub.add_parser("clear", help="Null document embeddings + clear corpus row")
    cl.add_argument(
        "--db",
        default="",
        help=f"Path to ship_computer.db (default: {SHIP_COMPUTER_DB})",
    )
    cl.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Do not prompt for confirmation",
    )

    st = sub.add_parser("status", help="Show embedding counts, corpus, and live :8080")
    st.add_argument(
        "--db",
        default="",
        help=f"Path to ship_computer.db (default: {SHIP_COMPUTER_DB})",
    )
    st.add_argument(
        "--embeddings-url",
        default="http://localhost:8080/embeddings",
        help="Live embedding server URL for status",
    )

    args = p.parse_args(argv)
    db = getattr(args, "db", None) or str(ROOT / "ship_computer.db")

    if args.cmd == "status":
        report = embedding_status(
            db, embeddings_url=str(getattr(args, "embeddings_url", "") or "")
        )
        print(format_status(report), flush=True)
        return 0

    if args.cmd == "clear":
        if not _confirm_yes(
            "Clear all document embeddings and kb_embedding_corpus "
            "(documents and settings are kept)?",
            assume_yes=bool(args.yes),
        ):
            print("Cancelled.", flush=True)
            return 1
        result = clear_embeddings(db)
        print(format_clear_result(result), flush=True)
        return 0 if result.get("ok") else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
