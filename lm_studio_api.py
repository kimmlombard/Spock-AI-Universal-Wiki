"""LM Studio native + OpenAI-compatible helpers for Spock-to-bridge.

Prefers /api/v1/* (LM Studio 0.4+); falls back to /api/v0/* and /v1/models.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

import requests

DEFAULT_TIMEOUT = 3.0
LOAD_TIMEOUT = 600.0


def base_url(host: str = "localhost", port: int = 1234) -> str:
    host = (host or "localhost").strip() or "localhost"
    try:
        port_i = int(port)
    except (TypeError, ValueError):
        port_i = 1234
    return f"http://{host}:{port_i}"


def _headers(api_key: str = "") -> Dict[str, str]:
    h = {"Content-Type": "application/json"}
    key = (api_key or "").strip()
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


def normalize_model_id(value: str) -> str:
    """Loose id for comparing LM Studio keys vs GGUF basenames."""
    text = (value or "").strip().lower().replace("\\", "/")
    if "/" in text and not text.endswith(".gguf"):
        # keep last path segment of publisher/name@quant
        text = text.rsplit("/", 1)[-1]
    text = os.path.basename(text)
    if text.endswith(".gguf"):
        text = text[:-5]
    text = re.sub(r"@[^@]+$", "", text)
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def _model_family(value: str) -> str:
    text = (value or "").strip().lower()
    for fam in (
        "deepseek",
        "mistral",
        "llama",
        "qwen",
        "gemma",
        "gemini",        
        "phi",
        "nomic",
        "gpt",
    ):
        if fam in text:
            return fam
    return ""


def _model_param_size(value: str) -> str:
    """Largest N B size tag in a name (e.g. '9' from qwen3.5-9b-…)."""
    text = (value or "").lower().replace("_", "-")
    sizes = re.findall(r"(\d+(?:\.\d+)?)\s*-?b\b", text)
    if not sizes:
        return ""
    # Prefer the largest parameter size (9b over 3.5 when both appear)
    def _key(s: str) -> float:
        try:
            return float(s)
        except ValueError:
            return 0.0

    return max(sizes, key=_key)


def models_match(a: str, b: str) -> bool:
    na, nb = normalize_model_id(a), normalize_model_id(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    # Family + param size: qwen3.5-9b-fable… ≈ qwen_qwen3.5-9b
    fa, fb = _model_family(a), _model_family(b)
    sa, sb = _model_param_size(a), _model_param_size(b)
    if fa and fa == fb and sa and sa == sb:
        return True
    return False


def _short_conn_detail(exc: BaseException, host: str, port: int) -> str:
    """Compact offline message — avoid dumping full urllib retry stacks."""
    text = str(exc) or type(exc).__name__
    low = text.lower()
    if "10061" in text or "actively refused" in low or "connection refused" in low:
        return f"offline (nothing listening on {host}:{port})"
    if "timed out" in low or "timeout" in low:
        return f"timeout contacting {host}:{port}"
    if "name or service not known" in low or "getaddrinfo" in low:
        return f"host not found: {host}"
    # Keep first line only; strip noisy wrappers
    first = text.splitlines()[0].strip()
    if len(first) > 160:
        first = first[:157] + "..."
    return first


def check_reachable(
    host: str = "localhost",
    port: int = 1234,
    api_key: str = "",
    timeout: float = DEFAULT_TIMEOUT,
) -> Tuple[bool, str]:
    """Return (ok, detail). Tries native then OpenAI /v1/models."""
    root = base_url(host, port)
    headers = _headers(api_key)
    detail = "unreachable"
    for path in ("/api/v1/models", "/api/v0/models", "/v1/models"):
        url = root + path
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return True, f"OK ({path})"
            detail = f"HTTP {r.status_code} on {path}"
        except requests.RequestException as e:
            detail = _short_conn_detail(e, host, int(port) if str(port).isdigit() else 1234)
            continue
        else:
            # got a non-200; keep trying other paths
            continue
    return False, detail


def list_models(
    host: str = "localhost",
    port: int = 1234,
    api_key: str = "",
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """
    Return {
      ok, detail, api, models: [{key, display_name, type, loaded_instance_ids, raw}]
    }
    """
    root = base_url(host, port)
    headers = _headers(api_key)

    # v1 native
    try:
        r = requests.get(root + "/api/v1/models", headers=headers, timeout=timeout)
        if r.status_code == 200:
            data = r.json() if r.content else {}
            models_in = data.get("models") if isinstance(data, dict) else None
            out = []
            for m in models_in or []:
                if not isinstance(m, dict):
                    continue
                loaded = m.get("loaded_instances") or []
                ids = []
                for inst in loaded:
                    if isinstance(inst, dict) and inst.get("id"):
                        ids.append(str(inst["id"]))
                out.append(
                    {
                        "key": str(m.get("key") or ""),
                        "display_name": str(m.get("display_name") or m.get("key") or ""),
                        "type": str(m.get("type") or "llm"),
                        "loaded_instance_ids": ids,
                        "raw": m,
                    }
                )
            return {
                "ok": True,
                "detail": f"{len(out)} model(s) via /api/v1/models",
                "api": "v1",
                "models": out,
            }
    except (requests.RequestException, ValueError):
        pass

    # v0 native
    try:
        r = requests.get(root + "/api/v0/models", headers=headers, timeout=timeout)
        if r.status_code == 200:
            data = r.json() if r.content else {}
            items = data.get("data") if isinstance(data, dict) else None
            out = []
            for m in items or []:
                if not isinstance(m, dict):
                    continue
                mid = str(m.get("id") or "")
                state = str(m.get("state") or "")
                loaded_ids = [mid] if state == "loaded" and mid else []
                mtype = "embedding" if "embed" in str(m.get("type") or "").lower() else "llm"
                if str(m.get("type") or "").lower() in ("embedding", "embeddings"):
                    mtype = "embedding"
                out.append(
                    {
                        "key": mid,
                        "display_name": mid,
                        "type": mtype,
                        "loaded_instance_ids": loaded_ids,
                        "raw": m,
                    }
                )
            return {
                "ok": True,
                "detail": f"{len(out)} model(s) via /api/v0/models",
                "api": "v0",
                "models": out,
            }
    except (requests.RequestException, ValueError):
        pass

    # OpenAI-compatible loaded-only list
    try:
        r = requests.get(root + "/v1/models", headers=headers, timeout=timeout)
        if r.status_code == 200:
            data = r.json() if r.content else {}
            items = data.get("data") if isinstance(data, dict) else None
            out = []
            for m in items or []:
                if not isinstance(m, dict):
                    continue
                mid = str(m.get("id") or "")
                if not mid:
                    continue
                out.append(
                    {
                        "key": mid,
                        "display_name": mid,
                        "type": "llm",
                        "loaded_instance_ids": [mid],
                        "raw": m,
                    }
                )
            return {
                "ok": True,
                "detail": f"{len(out)} loaded model(s) via /v1/models",
                "api": "openai",
                "models": out,
            }
        return {
            "ok": False,
            "detail": f"HTTP {r.status_code} on /v1/models",
            "api": None,
            "models": [],
        }
    except requests.RequestException as e:
        return {"ok": False, "detail": str(e), "api": None, "models": []}


def loaded_models(
    host: str = "localhost",
    port: int = 1234,
    api_key: str = "",
    timeout: float = DEFAULT_TIMEOUT,
) -> List[Dict[str, str]]:
    """Return [{instance_id, key, type}] for currently loaded instances."""
    info = list_models(host, port, api_key, timeout=timeout)
    if not info.get("ok"):
        return []
    out: List[Dict[str, str]] = []
    for m in info.get("models") or []:
        for iid in m.get("loaded_instance_ids") or []:
            out.append(
                {
                    "instance_id": str(iid),
                    "key": str(m.get("key") or iid),
                    "type": str(m.get("type") or "llm"),
                }
            )
    return out


def unload_model(
    instance_id: str,
    host: str = "localhost",
    port: int = 1234,
    api_key: str = "",
    timeout: float = 60.0,
) -> Tuple[bool, str]:
    root = base_url(host, port)
    headers = _headers(api_key)
    body = {"instance_id": instance_id}
    # v1
    try:
        r = requests.post(
            root + "/api/v1/models/unload",
            headers=headers,
            json=body,
            timeout=timeout,
        )
        if r.status_code in (200, 204):
            return True, f"Unloaded {instance_id}"
        v1_err = f"v1 HTTP {r.status_code}: {(r.text or '')[:200]}"
    except requests.RequestException as e:
        v1_err = str(e)

    # v0: POST /api/v0/models/unload with {"identifier": ...} (best-effort)
    try:
        r = requests.post(
            root + "/api/v0/models/unload",
            headers=headers,
            json={"identifier": instance_id, "instance_id": instance_id},
            timeout=timeout,
        )
        if r.status_code in (200, 204):
            return True, f"Unloaded {instance_id} (v0)"
        return False, f"{v1_err}; v0 HTTP {r.status_code}: {(r.text or '')[:200]}"
    except requests.RequestException as e:
        return False, f"{v1_err}; v0 {e}"


def load_model(
    model: str,
    host: str = "localhost",
    port: int = 1234,
    api_key: str = "",
    timeout: float = LOAD_TIMEOUT,
    context_length: Optional[int] = None,
    flash_attention: bool = True,
    offload_kv_cache_to_gpu: bool = True,
    echo_load_config: bool = True,
) -> Tuple[bool, str]:
    """Load a model via POST /api/v1/models/load.

    Pass ``context_length`` to override LM Studio's conservative single-GPU
    VRAM estimate (often clamps to 8192 even when the RTX 6000 has headroom).
    """
    root = base_url(host, port)
    headers = _headers(api_key)
    body: Dict[str, Any] = {"model": model}
    if context_length is not None:
        try:
            ctx = int(context_length)
        except (TypeError, ValueError):
            ctx = 0
        if ctx >= 512:
            body["context_length"] = ctx
    if flash_attention is not None:
        body["flash_attention"] = bool(flash_attention)
    if offload_kv_cache_to_gpu is not None:
        body["offload_kv_cache_to_gpu"] = bool(offload_kv_cache_to_gpu)
    if echo_load_config:
        body["echo_load_config"] = True
    try:
        r = requests.post(
            root + "/api/v1/models/load",
            headers=headers,
            json=body,
            timeout=timeout,
        )
        if r.status_code in (200, 201):
            try:
                data = r.json() if r.content else {}
            except ValueError:
                data = {}
            iid = data.get("instance_id") or model
            cfg = data.get("load_config") if isinstance(data, dict) else None
            if isinstance(cfg, dict) and cfg.get("context_length") is not None:
                return (
                    True,
                    f"Loaded {iid} (context_length={cfg.get('context_length')})",
                )
            requested = body.get("context_length")
            if requested:
                return True, f"Loaded {iid} (requested context_length={requested})"
            return True, f"Loaded {iid}"
        v1_err = f"v1 HTTP {r.status_code}: {(r.text or '')[:300]}"
    except requests.RequestException as e:
        v1_err = str(e)

    # Older JIT: hitting chat/completions can load; prefer explicit fail with guidance
    return False, v1_err


def loaded_instance_context_length(
    host: str = "localhost",
    port: int = 1234,
    api_key: str = "",
    model_key: str = "",
    timeout: float = DEFAULT_TIMEOUT,
) -> Optional[int]:
    """Return context_length of a loaded instance matching model_key, if known."""
    info = list_models(host, port, api_key, timeout=timeout)
    if not info.get("ok"):
        return None
    for m in info.get("models") or []:
        key = str(m.get("key") or "")
        if model_key and not (
            models_match(model_key, key) or model_key == key
        ):
            continue
        raw = m.get("raw") if isinstance(m.get("raw"), dict) else {}
        for inst in raw.get("loaded_instances") or []:
            if not isinstance(inst, dict):
                continue
            cfg = inst.get("config") if isinstance(inst.get("config"), dict) else {}
            ctx = cfg.get("context_length")
            if ctx is not None:
                try:
                    return int(ctx)
                except (TypeError, ValueError):
                    continue
    return None


def find_catalog_key_for_path(
    model_path_or_id: str,
    catalog: List[Dict[str, Any]],
) -> Optional[str]:
    """Match a GGUF path / id to an LM Studio catalog key."""
    if not model_path_or_id:
        return None
    # Exact key hit
    for m in catalog:
        key = str(m.get("key") or "")
        if key and (
            key == model_path_or_id
            or models_match(key, model_path_or_id)
            or models_match(str(m.get("display_name") or ""), model_path_or_id)
        ):
            return key
    return None


def snapshot(
    host: str = "localhost",
    port: int = 1234,
    api_key: str = "",
) -> Dict[str, Any]:
    ok, detail = check_reachable(host, port, api_key)
    loaded = loaded_models(host, port, api_key) if ok else []
    return {
        "reachable": ok,
        "detail": detail,
        "host": host,
        "port": int(port) if str(port).isdigit() else port,
        "loaded": loaded,
    }
