"""Embedding profile helpers (probe dim, .env, DB sample)."""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

import requests

from spock_rag_adapter.paths import ROOT

NULL_EMBEDDING = (
    "llama-server returned an embedding made of nulls. "
    "That is a NaN vector serialized as JSON null, so it cannot be stored. "
    "Qwen3-VL-Embedding does this for some documents. On the GPU, every later "
    "request stays null until that llama-server process is restarted. "
    "Qwen3-Embedding-8B embeds those same documents."
)


def flatten_embedding(raw: Any) -> List[float]:
    """Turn a llama-server embedding payload into one finite vector.

    Nested token rows are averaged. A null component is a NaN from the server
    and is not a number that can be added into the vector.
    """
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        rows = [row for row in raw if isinstance(row, list) and row]
        if not rows:
            raise ValueError(NULL_EMBEDDING)
        dim = len(rows[0])
        acc = [0.0] * dim
        used = 0
        for row in rows:
            if len(row) != dim:
                continue
            if any(not isinstance(value, (int, float)) for value in row):
                continue
            for index, value in enumerate(row):
                acc[index] += float(value)
            used += 1
        if used == 0:
            raise ValueError(NULL_EMBEDDING)
        return [value / used for value in acc]
    if isinstance(raw, list) and raw:
        if any(not isinstance(value, (int, float)) for value in raw):
            raise ValueError(NULL_EMBEDDING)
        return [float(value) for value in raw]
    raise ValueError(NULL_EMBEDDING)


def embeddings_from_response(
    data: Any, count: int
) -> Tuple[List[Optional[List[float]]], bool]:
    """One vector per input, plus whether any vector was a JSON null.

    A null vector becomes None so the rest of the batch can still be stored.
    """
    slots: List[Optional[List[float]]] = [None] * max(0, int(count))
    saw_null = False
    items: List[Any] = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        inner = data.get("data")
        if not isinstance(inner, list):
            inner = data.get("embeddings")
        if isinstance(inner, list):
            items = inner
    for pos, item in enumerate(items):
        if isinstance(item, dict):
            idx = item.get("index", pos)
            raw = item.get("embedding")
        else:
            idx = pos
            raw = item
        if not isinstance(idx, int) or isinstance(idx, bool) or idx < 0 or idx >= len(slots):
            continue
        try:
            slots[idx] = flatten_embedding(raw)
        except ValueError as exc:
            slots[idx] = None
            if "null" in str(exc).lower():
                saw_null = True
    return slots, saw_null


def embedding_from_response(data: Any) -> List[float]:
    """Pull the first embedding out of a llama.cpp or OpenAI-style response."""
    raw = None
    if isinstance(data, list) and data:
        item = data[0]
        if isinstance(item, dict) and "embedding" in item:
            raw = item["embedding"]
        elif isinstance(item, list):
            raw = item
    elif isinstance(data, dict):
        for key in ("data", "embeddings"):
            inner = data.get(key)
            if isinstance(inner, list) and inner:
                item = inner[0]
                raw = item["embedding"] if isinstance(item, dict) else item
                break
    if raw is None:
        raise ValueError("The embedding response did not contain a vector.")
    return flatten_embedding(raw)


def probe_embeddings_dim(url: str, timeout: int = 30) -> Optional[int]:
    """POST a short string to /embeddings and return vector length."""
    payload = json.dumps({"input": "spock probe"}).encode("utf-8")
    try:
        req = requests.post(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
        if req.status_code != 200:
            return None
        return len(embedding_from_response(req.json()))
    except Exception:
        return None


def sample_db_embedding_dim(db_path: str) -> Optional[int]:
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        row = conn.execute(
            "SELECT embedding FROM documents WHERE embedding IS NOT NULL LIMIT 1"
        ).fetchone()
        conn.close()
        if not row or not row[0]:
            return None
        blob = row[0]
        return len(blob) // 4
    except Exception:
        return None


def write_embedding_env(profile: Dict[str, Any], env_path: Optional[str] = None) -> None:
    """Upsert embedding-related keys in .env (create if missing)."""
    path = env_path or str(ROOT / ".env")
    keys = {
        "EMBEDDINGS_URL": str(profile.get("embeddings_url", "")),
        "EMBEDDINGS_DIM": str(profile.get("embeddings_dim", 4096)),
        "EMBEDDINGS_TRUNCATE": str(profile.get("truncate_chars", 1500)),
        "EMBEDDINGS_BATCH_CHUNK": str(profile.get("batch_chunk", 32)),
        "EMBEDDINGS_BATCH_WORKERS": str(profile.get("batch_workers", 8)),
    }
    lines_out: List[str] = []
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped == "# Embedding profile (managed by Spock-onboarding)":
                    continue
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    lines_out.append(line.rstrip("\n"))
                    continue
                k, _, _v = stripped.partition("=")
                if k in keys:
                    continue
                lines_out.append(line.rstrip("\n"))
    while lines_out and lines_out[-1] == "":
        lines_out.pop()
    lines_out.append("")
    lines_out.append("# Embedding profile (managed by Spock-onboarding)")
    for k, v in keys.items():
        lines_out.append(f"{k}={v}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines_out) + "\n")
