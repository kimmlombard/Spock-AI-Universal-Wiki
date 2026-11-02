"""Spock Status report (same intent as Ship Status -> Run Spock Status)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from spock_onboarding.health import probe_embed_chat
from spock_onboarding.llama_process import discover_llama_servers


def _probe_http(url: str, *, timeout: float = 2.0) -> Dict[str, Any]:
    out: Dict[str, Any] = {"url": url, "reachable": False, "detail": ""}
    try:
        r = requests.get(url, timeout=timeout)
        out["http"] = r.status_code
        out["reachable"] = 200 <= r.status_code < 500
        out["detail"] = "ok" if r.status_code == 200 else f"HTTP {r.status_code}"
        try:
            out["json"] = r.json()
        except Exception:
            out["text"] = (r.text or "")[:300]
    except requests.RequestException as e:
        out["detail"] = str(e).splitlines()[0][:160] if str(e) else "unreachable"
    return out


def _probe_mcp_http(
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    timeout: float = 2.0,
) -> Dict[str, Any]:
    """Probe MCP streamable-http adapter via OPTIONS /mcp (CORS preflight)."""
    url = f"http://{host}:{port}/mcp"
    out: Dict[str, Any] = {"url": url, "reachable": False, "detail": ""}
    try:
        r = requests.options(
            url,
            headers={
                "Origin": "http://127.0.0.1:8082",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,accept",
            },
            timeout=timeout,
        )
        out["http"] = r.status_code
        aca = r.headers.get("access-control-allow-origin") or ""
        out["cors"] = aca
        if r.status_code in (200, 204, 405) or aca:
            out["reachable"] = True
            out["detail"] = f"listening (HTTP {r.status_code}"
            if aca:
                out["detail"] += f", CORS {aca}"
            out["detail"] += ")"
        else:
            out["detail"] = f"HTTP {r.status_code} on OPTIONS /mcp"
    except requests.RequestException as e:
        out["detail"] = str(e).splitlines()[0][:160] if str(e) else "unreachable"
    return out


def probe_spock_status(
    *,
    root: Optional[Path] = None,
    embed_port: int = 8080,
    chat_port: int = 8081,
    rag_url: str = "http://127.0.0.1:8090/health",
    mcp_host: str = "127.0.0.1",
    mcp_port: int = 8765,
) -> Dict[str, Any]:
    root = Path(root) if root else Path.cwd()
    probes = probe_embed_chat(embed_port=embed_port, chat_port=chat_port)
    rag = _probe_http(rag_url)
    mcp = _probe_mcp_http(mcp_host, mcp_port)
    discovered = discover_llama_servers()
    ready_path = root / "spock_ready_last.json"
    ready = None
    if ready_path.is_file():
        try:
            ready = json.loads(ready_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            ready = None
    return {
        "root": str(root.resolve()),
        "embed": probes.get("embed") or {},
        "chat": probes.get("chat") or {},
        "servers_ready": bool(probes.get("servers_ready")),
        "rag": rag,
        "mcp": mcp,
        "discovered": discovered,
        "readiness": ready,
    }


def format_spock_status_report(data: Dict[str, Any]) -> str:
    embed = data.get("embed") or {}
    chat = data.get("chat") or {}
    rag = data.get("rag") or {}
    mcp = data.get("mcp") or {}
    discovered = data.get("discovered") or []
    ready = data.get("readiness") if isinstance(data.get("readiness"), dict) else {}

    lines: List[str] = [
        "Spock Status (spock-status)",
        "",
        "API / readiness",
        f"  Install root     : {data.get('root') or '-'}",
        f"  ui_ready         : {ready.get('ui_ready', '-')}",
        f"  servers_ready    : {data.get('servers_ready')}",
        f"  full_deps_ok     : {ready.get('full_deps_ok', '-')}",
        "",
        "RAG API",
        f"  URL              : {rag.get('url')}",
        f"  Reachable        : {rag.get('reachable')} ({rag.get('detail') or '-'})",
        "",
        "MCP adapter",
        f"  URL              : {mcp.get('url')}",
        f"  Reachable        : {mcp.get('reachable')} ({mcp.get('detail') or '-'})",
        "",
        "Llama-server endpoints",
    ]

    def _llama_block(label: str, info: Dict[str, Any]) -> List[str]:
        ok = bool(info.get("reachable"))
        mark = "OK" if ok else "DOWN"
        model = info.get("model_name") or info.get("model_path") or "-"
        return [
            f"  {label}",
            f"    Status         : {mark}",
            f"    Port           : {info.get('port')}",
            f"    Model          : {model}",
            f"    n_ctx          : {info.get('n_ctx') if info.get('n_ctx') is not None else '-'}",
            f"    Detail         : {info.get('detail') or '-'}",
        ]

    lines.extend(_llama_block(":8080 embed", embed))
    lines.extend(_llama_block(":8081 chat", chat))

    lines.extend(["", "Discovered llama-server processes"])
    if not discovered:
        lines.append("  (none)")
    else:
        for row in discovered:
            lines.append(
                f"  PID {row.get('pid')}  role={row.get('role')}  "
                f"port={row.get('port')}  "
                f"model={Path(str(row.get('model_path') or '')).name or '-'}"
            )

    lines.extend(["", "Summary"])
    lines.append(
        f"  {'OK' if rag.get('reachable') else 'MISS'} RAG API "
        f"{'responding' if rag.get('reachable') else 'not reachable'}"
    )
    lines.append(
        f"  {'OK' if embed.get('reachable') else 'MISS'} embedding llama-server "
        f":{embed.get('port', 8080)}"
    )
    lines.append(
        f"  {'OK' if chat.get('reachable') else 'MISS'} chat llama-server "
        f":{chat.get('port', 8081)}"
    )
    lines.append(
        f"  {'OK' if mcp.get('reachable') else 'MISS'} MCP adapter "
        f"{'responding' if mcp.get('reachable') else 'not reachable'}"
    )
    return "\n".join(lines)


def run_spock_status_text(**kwargs: Any) -> str:
    return format_spock_status_report(probe_spock_status(**kwargs))
