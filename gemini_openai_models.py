"""Gemini / Vertex OpenAI-compatible model catalog and listing helpers."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

# Documented Chat Completions model ids (Vertex OpenAI-compat uses google/ prefix).
# /models often 404s on Vertex; this catalog is the practical source of truth.
VERTEX_OPENAI_GEMINI_CATALOG: List[Dict[str, str]] = [
    {
        "id": "google/gemini-2.5-flash",
        "family": "Gemini 2.5",
        "tier": "Flash",
        "notes": "Fast / default Ask AI",
    },
    {
        "id": "google/gemini-2.5-pro",
        "family": "Gemini 2.5",
        "tier": "Pro",
        "notes": "Higher quality, slower",
    },
    {
        "id": "google/gemini-2.5-flash-lite",
        "family": "Gemini 2.5",
        "tier": "Flash-Lite",
        "notes": "Cheapest / fastest 2.5",
    },
    {
        "id": "google/gemini-2.0-flash-001",
        "family": "Gemini 2.0",
        "tier": "Flash",
        "notes": "2.0 Flash (may be retired in some regions)",
    },
    {
        "id": "google/gemini-2.0-flash",
        "family": "Gemini 2.0",
        "tier": "Flash",
        "notes": "Alias — may 404; prefer -001",
    },
    {
        "id": "google/gemini-1.5-flash",
        "family": "Gemini 1.5",
        "tier": "Flash",
        "notes": "Legacy",
    },
    {
        "id": "google/gemini-1.5-pro",
        "family": "Gemini 1.5",
        "tier": "Pro",
        "notes": "Legacy",
    },
    {
        "id": "google/gemini-3.5-flash",
        "family": "Gemini 3.5",
        "tier": "Flash",
        "notes": "Global endpoint only — 404s on regional roots",
    },
]


def _auth_headers(api_key: str, base_url: str) -> Dict[str, str]:
    key = (api_key or "").strip()
    headers = {"Content-Type": "application/json"}
    lower = (base_url or "").lower()
    use_adc = (
        key.lower() in ("", "adc", "application-default", "vertexaiapikey", "gcloud")
        and "googleapis.com" in lower
    )
    if use_adc:
        from google.auth import default
        from google.auth.transport.requests import Request

        creds, _ = default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        if not getattr(creds, "valid", False) or not creds.token:
            creds.refresh(Request())
        else:
            try:
                creds.refresh(Request())
            except Exception:
                pass
        headers["Authorization"] = f"Bearer {creds.token}"
    elif key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def try_openai_list_models(
    base_url: str, api_key: str = "adc", timeout: float = 20.0
) -> Tuple[List[str], str]:
    """GET {base}/models. Returns (ids, detail). Empty ids if unsupported."""
    base = (base_url or "").rstrip("/")
    if not base:
        return [], "No OpenAI-compatible base URL configured"
    url = f"{base}/models"
    try:
        req = urllib.request.Request(url, headers=_auth_headers(api_key, base))
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        ids = []
        for m in data.get("data") or data.get("models") or []:
            mid = m.get("id") or m.get("name") or ""
            if mid:
                ids.append(str(mid))
        return ids, f"Listed {len(ids)} from {url}"
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        return [], f"HTTP {e.code} from /models ({body[:120]})"
    except Exception as e:
        return [], f"/models failed: {e}"


def catalog_models() -> List[Dict[str, str]]:
    return [dict(row) for row in VERTEX_OPENAI_GEMINI_CATALOG]


def merge_catalog_with_remote(remote_ids: List[str]) -> List[Dict[str, str]]:
    """Prefer remote ids when present; always include catalog entries."""
    by_id = {row["id"]: dict(row) for row in catalog_models()}
    for mid in remote_ids:
        if mid not in by_id:
            by_id[mid] = {
                "id": mid,
                "family": "Remote",
                "tier": "",
                "notes": "From GET /models",
            }
        else:
            by_id[mid]["notes"] = (by_id[mid].get("notes") or "") + " · listed by API"
    # Keep catalog order first, then extras
    ordered: List[Dict[str, str]] = []
    seen = set()
    for row in catalog_models():
        ordered.append(by_id[row["id"]])
        seen.add(row["id"])
    for mid, row in by_id.items():
        if mid not in seen:
            ordered.append(row)
    return ordered


def probe_model_chat(
    base_url: str,
    model_id: str,
    api_key: str = "adc",
    timeout: float = 45.0,
) -> Tuple[bool, str]:
    """Tiny chat completions probe. Returns (ok, detail)."""
    base = (base_url or "").rstrip("/")
    if not base or not model_id:
        return False, "Missing base URL or model id"
    url = f"{base}/chat/completions"
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
        "max_tokens": 8,
        "temperature": 0,
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=_auth_headers(api_key, base),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = (
            ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
            or ""
        )
        return True, f"OK — {text!r}"[:120]
    except urllib.error.HTTPError as e:
        body = ""
        try:
            err = json.loads(e.read().decode("utf-8", "replace"))
            body = err.get("error", {}).get("message") or str(err)[:160]
        except Exception:
            body = f"HTTP {e.code}"
        return False, body[:200]
    except Exception as e:
        return False, str(e)[:200]


def list_models_for_ui(
    base_url: str, api_key: str = "adc"
) -> Tuple[List[Dict[str, Any]], str]:
    """Catalog + optional remote /models merge for the Models panel."""
    remote, detail = try_openai_list_models(base_url, api_key)
    rows = merge_catalog_with_remote(remote)
    if remote:
        status = f"{detail} · showing catalog + remote"
    else:
        status = (
            f"Vertex OpenAI /models unavailable ({detail}). "
            "Showing documented google/gemini-* catalog — use Probe to verify access."
        )
    return rows, status
