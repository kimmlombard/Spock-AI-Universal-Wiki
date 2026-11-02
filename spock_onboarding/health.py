"""HTTP health probes for llama-server (no Qt)."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from spock_onboarding.llama_process import is_embedding_gguf_path


def parse_host_port(url_or_host: str, default_port: int) -> Tuple[str, int]:
    text = (url_or_host or "").strip()
    if not text:
        return "127.0.0.1", default_port
    if "://" not in text:
        if ":" in text and text.rsplit(":", 1)[-1].isdigit():
            host, port_s = text.rsplit(":", 1)
            return (host or "127.0.0.1").strip() or "127.0.0.1", int(port_s)
        return text or "127.0.0.1", default_port
    u = urlparse(text)
    host = (u.hostname or "127.0.0.1").strip() or "127.0.0.1"
    port = int(u.port) if u.port else default_port
    return host, port


def probe_llama_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    *,
    role_hint: str = "",
    timeout: float = 1.5,
) -> Dict[str, Any]:
    host = (host or "127.0.0.1").strip() or "127.0.0.1"
    try:
        port_i = int(port)
    except (TypeError, ValueError):
        port_i = 8080
    root = f"http://{host}:{port_i}"
    out: Dict[str, Any] = {
        "host": host,
        "port": port_i,
        "url": root,
        "reachable": False,
        "role": (role_hint or "").strip().lower() or "unknown",
        "n_ctx": None,
        "model_path": "",
        "model_name": "",
        "detail": "",
    }
    try:
        r = requests.get(f"{root}/health", timeout=timeout)
    except requests.RequestException as e:
        out["detail"] = str(e).splitlines()[0][:160] if str(e) else "unreachable"
        return out
    out["health_http"] = r.status_code
    if r.status_code != 200:
        out["detail"] = f"HTTP {r.status_code} on /health"
        return out
    out["reachable"] = True
    try:
        out["health"] = r.json()
    except Exception:
        pass

    model_path = ""
    n_ctx: Optional[int] = None
    try:
        props = requests.get(f"{root}/props", timeout=timeout).json()
        if isinstance(props, dict):
            model_path = str(props.get("model_path") or "")
            gen = props.get("default_generation_settings") or {}
            if isinstance(gen, dict) and gen.get("n_ctx") is not None:
                try:
                    n_ctx = int(gen["n_ctx"])
                except (TypeError, ValueError):
                    n_ctx = None
    except Exception:
        pass

    if not model_path:
        try:
            mods = requests.get(f"{root}/v1/models", timeout=timeout).json()
            rows = mods.get("models") or mods.get("data") or []
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                model_path = str(
                    rows[0].get("model") or rows[0].get("id") or rows[0].get("name") or ""
                )
        except Exception:
            pass

    out["n_ctx"] = n_ctx
    out["model_path"] = model_path
    out["model_name"] = os.path.basename(model_path) if model_path else ""
    if out["role"] == "unknown" and model_path:
        out["role"] = "embedding" if is_embedding_gguf_path(model_path) else "chat"
    out["detail"] = "ok"
    return out


def format_llama_line(info: Dict[str, Any], *, label: str) -> str:
    if not info.get("reachable"):
        return f"{label}: DOWN ({info.get('detail') or 'unreachable'})"
    model = info.get("model_name") or info.get("model_path") or "?"
    n_ctx = info.get("n_ctx")
    ctx = f" n_ctx={n_ctx}" if n_ctx else ""
    return f"{label}: UP {model}{ctx}"


def probe_embed_chat(
    *,
    embed_port: int = 8080,
    chat_port: int = 8081,
    host: str = "127.0.0.1",
    timeout: float = 1.5,
) -> Dict[str, Any]:
    embed = probe_llama_server(host, embed_port, role_hint="embedding", timeout=timeout)
    chat = probe_llama_server(host, chat_port, role_hint="chat", timeout=timeout)
    return {
        "embed": embed,
        "chat": chat,
        "servers_ready": bool(embed.get("reachable") and chat.get("reachable")),
    }
