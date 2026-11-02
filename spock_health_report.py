"""RAG API + llama-server health probe / report (no Qt).

Used by MCP panel "Run spock-status" and scripts/mcp_spock_server.spock_health.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from spock_onboarding.llama_process import is_embedding_gguf_path

try:
    from WarpCore.service_endpoints import (
        DEFAULT_CHAT_PORT,
        DEFAULT_EMBED_PORT,
        DEFAULT_MCP_PORT,
        DEFAULT_MCP_WEBUI_PORT,
        DEFAULT_RAG_PORT,
    )
except ImportError:  # pragma: no cover
    DEFAULT_EMBED_PORT = 8080
    DEFAULT_CHAT_PORT = 8081
    DEFAULT_RAG_PORT = 8090
    DEFAULT_MCP_PORT = 8765
    DEFAULT_MCP_WEBUI_PORT = 8082

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore


def _parse_host_port(url_or_host: str, default_port: int) -> Tuple[str, int]:
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


def embeddings_host_port(embeddings_url: str) -> Tuple[str, int]:
    """Host/port for the embeddings llama-server."""
    return _parse_host_port(
        embeddings_url or f"http://localhost:{DEFAULT_EMBED_PORT}/embeddings",
        DEFAULT_EMBED_PORT,
    )


def probe_llama_server(
    host: str = "127.0.0.1",
    port: int = DEFAULT_EMBED_PORT,
    *,
    role_hint: str = "",
    timeout: float = 1.5,
) -> Dict[str, Any]:
    """Probe one llama-server: /health, /props (n_ctx + model), /slots."""
    host = (host or "127.0.0.1").strip() or "127.0.0.1"
    try:
        port_i = int(port)
    except (TypeError, ValueError):
        port_i = DEFAULT_EMBED_PORT
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
        out["health_http"] = r.status_code
        if r.status_code != 200:
            out["detail"] = f"HTTP {r.status_code} on /health"
            return out
        try:
            health_body = r.json()
        except Exception:
            health_body = {}
        # LM Studio answers HTTP 200 with {"error": "Unexpected endpoint..."}
        # and can bind 127.0.0.1 while llama-server holds 0.0.0.0 on the same port.
        err_text = ""
        status_ok = False
        if isinstance(health_body, dict):
            err_text = str(health_body.get("error") or "")
            status_ok = str(health_body.get("status") or "").lower() == "ok"
        if not status_ok:
            low = err_text.lower()
            if (
                "unexpected endpoint" in low
                or "lms load" in low
                or "no models loaded" in low
            ):
                out["detail"] = (
                    f"127.0.0.1:{port_i} is LM Studio, not llama-server. "
                    "Quit LM Studio's local server or move it off this port. "
                    "localhost prefers that binding over llama-server on 0.0.0.0."
                )
            else:
                out["detail"] = err_text or "HTTP 200 but /health is not llama-server"
            out["health"] = health_body
            return out
        out["reachable"] = True
        out["health"] = health_body
    except requests.RequestException as e:
        out["detail"] = str(e).splitlines()[0][:160] if str(e) else "unreachable"
        return out

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

    if n_ctx is None:
        try:
            slots = requests.get(f"{root}/slots", timeout=timeout).json()
            if isinstance(slots, list) and slots:
                try:
                    n_ctx = int(slots[0].get("n_ctx"))
                except (TypeError, ValueError, AttributeError):
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
        out["role"] = (
            "embedding" if is_embedding_gguf_path(model_path) else "chat"
        )
    elif out["role"] == "unknown" and role_hint:
        out["role"] = role_hint
    out["detail"] = "ok"
    return out


def _fold_path(text: str) -> str:
    return os.path.normcase(str(text or "")).replace("\\", "/")


def _this_repo_mcp_script() -> str:
    root = os.path.dirname(os.path.abspath(__file__))
    return _fold_path(os.path.join(root, "scripts", "mcp_spock_server.py"))


def discover_mcp_adapter_pids() -> List[Dict[str, Any]]:
    """Find running scripts/mcp_spock_server.py processes."""
    found: List[Dict[str, Any]] = []
    if psutil is None:
        return found
    marker = _this_repo_mcp_script()
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = [str(c) for c in (proc.info.get("cmdline") or [])]
            joined = " ".join(cmdline)
            if "mcp_spock_server.py" not in joined.lower().replace("\\", "/"):
                continue
            found.append(
                {
                    "pid": int(proc.info["pid"]),
                    "cmdline": joined,
                    "ours": marker in _fold_path(joined),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError, ValueError):
            continue
    found.sort(key=lambda x: int(x.get("pid") or 0))
    return found


def discover_ui_mcp_proxy() -> List[Dict[str, Any]]:
    """Find llama-server processes launched with --ui-mcp-proxy."""
    found: List[Dict[str, Any]] = []
    if psutil is None:
        return found
    for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            exe = (proc.info.get("exe") or "").lower()
            cmdline = [str(c) for c in (proc.info.get("cmdline") or [])]
            joined = " ".join(cmdline)
            if "llama-server" not in name and "llama-server" not in exe:
                continue
            if "--ui-mcp-proxy" not in joined:
                continue
            host = "127.0.0.1"
            port = DEFAULT_MCP_WEBUI_PORT
            i = 0
            while i < len(cmdline):
                arg = cmdline[i]
                if arg in ("--host", "-h") and i + 1 < len(cmdline):
                    host = cmdline[i + 1] or host
                    i += 2
                    continue
                if arg in ("--port", "-p") and i + 1 < len(cmdline):
                    if str(cmdline[i + 1]).isdigit():
                        port = int(cmdline[i + 1])
                    i += 2
                    continue
                i += 1
            found.append(
                {
                    "pid": int(proc.info["pid"]),
                    "host": host,
                    "port": port,
                    "cmdline": joined,
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError, ValueError):
            continue
    found.sort(key=lambda x: (int(x.get("port") or 0), int(x.get("pid") or 0)))
    return found


def discover_rag_api_pids() -> List[Dict[str, Any]]:
    """Find ``_start_rag_api.py`` / ``rag_api_server`` processes."""
    found: List[Dict[str, Any]] = []
    if psutil is None:
        return found
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = [str(c) for c in (proc.info.get("cmdline") or [])]
            joined = " ".join(cmdline).lower().replace("\\", "/")
            if "_start_rag_api.py" not in joined and "rag_api_server" not in joined:
                continue
            pid = int(proc.info["pid"])
            port = DEFAULT_RAG_PORT
            for i, arg in enumerate(cmdline):
                if arg in ("--port", "-p") and i + 1 < len(cmdline):
                    if str(cmdline[i + 1]).isdigit():
                        port = int(cmdline[i + 1])
            try:
                env = psutil.Process(pid).environ()
                for key in ("SPOCK_RAG_PORT", "RAG_API_PORT"):
                    raw = str(env.get(key) or "").strip()
                    if raw.isdigit():
                        port = int(raw)
                        break
            except (psutil.Error, TypeError, ValueError):
                pass
            found.append({"pid": pid, "port": port, "cmdline": " ".join(cmdline)})
        except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError, ValueError):
            continue
    found.sort(key=lambda x: int(x.get("pid") or 0))
    return found


def discover_suite_service_rows(
    *,
    webui_port: int = DEFAULT_MCP_WEBUI_PORT,
    rag_port: int = DEFAULT_RAG_PORT,
    mcp_port: int = DEFAULT_MCP_PORT,
) -> List[Dict[str, Any]]:
    """Rows for Live Monitor: WebUI :8082, RAG :8090, MCP :8765 when launched."""
    rows: List[Dict[str, Any]] = []
    for info in discover_ui_mcp_proxy():
        port = int(info.get("port") or webui_port)
        rows.append(
            {
                "role": "webui",
                "model": "--ui-mcp-proxy",
                "port": port,
                "pid": int(info.get("pid") or 0),
                "gpu_label": "",
                "service": True,
            }
        )
    for info in discover_rag_api_pids():
        rows.append(
            {
                "role": "rag",
                "model": "RAG API",
                "port": int(info.get("port") or rag_port),
                "pid": int(info.get("pid") or 0),
                "gpu_label": "",
                "service": True,
            }
        )
    for info in discover_mcp_adapter_pids():
        # Prefer HTTP adapters that own a listen port; still show stdio copies.
        pid = int(info.get("pid") or 0)
        port = mcp_port
        transport = "mcp"
        if psutil is not None and pid:
            try:
                for conn in psutil.Process(pid).net_connections(kind="inet"):
                    if conn.status == psutil.CONN_LISTEN and conn.laddr:
                        port = int(conn.laddr.port)
                        transport = "streamable-http"
                        break
            except (psutil.Error, TypeError, ValueError, AttributeError):
                pass
        rows.append(
            {
                "role": "mcp",
                "model": transport,
                "port": port,
                "pid": pid,
                "gpu_label": "",
                "service": True,
            }
        )
    # Stable order: webui → rag → mcp, then port/pid
    order = {"webui": 0, "rag": 1, "mcp": 2}
    rows.sort(
        key=lambda r: (
            order.get(str(r.get("role") or ""), 9),
            int(r.get("port") or 0),
            int(r.get("pid") or 0),
        )
    )
    return rows


def probe_mcp_adapter(
    host: str = "127.0.0.1",
    port: int = DEFAULT_MCP_PORT,
    *,
    transport: str = "streamable-http",
    timeout: float = 2.0,
) -> Dict[str, Any]:
    """Probe Spock MCP HTTP adapter (/mcp) and list adapter PIDs."""
    host = (host or "127.0.0.1").strip() or "127.0.0.1"
    try:
        port_i = int(port)
    except (TypeError, ValueError):
        port_i = DEFAULT_MCP_PORT
    transport = (transport or "streamable-http").strip().lower() or "streamable-http"
    mcp_url = f"http://{host}:{port_i}/mcp"
    sse_url = f"http://{host}:{port_i}/sse"
    out: Dict[str, Any] = {
        "host": host,
        "port": port_i,
        "transport": transport,
        "mcp_url": mcp_url,
        "sse_url": sse_url,
        "reachable": False,
        "http_status": None,
        "cors": "",
        "pids": [],
        "processes": [],
        "detail": "",
    }
    procs = discover_mcp_adapter_pids()
    out["processes"] = procs
    out["pids"] = [int(p["pid"]) for p in procs]

    if transport == "stdio":
        out["detail"] = "stdio transport (no HTTP /mcp endpoint)"
        out["reachable"] = bool(out["pids"])
        if out["reachable"]:
            out["detail"] = f"stdio · {len(out['pids'])} process(es)"
        return out

    try:
        r = requests.options(
            mcp_url,
            headers={
                "Origin": f"http://127.0.0.1:{DEFAULT_MCP_WEBUI_PORT}",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,accept",
            },
            timeout=timeout,
        )
        out["http_status"] = r.status_code
        out["cors"] = r.headers.get("access-control-allow-origin") or ""
        # FastMCP may answer OPTIONS 200 or POST-only 405; either means listening.
        if r.status_code in (200, 204, 405) or out["cors"]:
            out["reachable"] = True
            out["detail"] = f"listening (HTTP {r.status_code}"
            if out["cors"]:
                out["detail"] += f", CORS {out['cors']}"
            out["detail"] += ")"
        else:
            out["detail"] = f"HTTP {r.status_code} on OPTIONS /mcp"
    except requests.RequestException as e:
        # Fallback: GET/POST-ish probe — some stacks reject OPTIONS
        try:
            r2 = requests.get(mcp_url, timeout=timeout)
            out["http_status"] = r2.status_code
            # 405 Method Not Allowed still means the route exists
            if r2.status_code in (200, 400, 405, 406):
                out["reachable"] = True
                out["detail"] = f"listening (HTTP {r2.status_code} on GET /mcp)"
            else:
                out["detail"] = f"HTTP {r2.status_code} on /mcp"
        except requests.RequestException:
            out["detail"] = str(e).splitlines()[0][:160] if str(e) else "unreachable"
            if not out["pids"]:
                out["detail"] += " — open Configure tab 6 MCP or click Start adapter"
            if out["pids"]:
                out["detail"] += f" · {len(out['pids'])} process(es) still running"
    return out


def probe_ui_mcp_proxy(
    host: str = "127.0.0.1",
    port: int = DEFAULT_MCP_WEBUI_PORT,
    *,
    timeout: float = 1.5,
) -> Dict[str, Any]:
    """Probe llama-server --ui-mcp-proxy WebUI."""
    host = (host or "127.0.0.1").strip() or "127.0.0.1"
    try:
        port_i = int(port)
    except (TypeError, ValueError):
        port_i = DEFAULT_MCP_WEBUI_PORT
    root = f"http://{host}:{port_i}"
    out: Dict[str, Any] = {
        "host": host,
        "port": port_i,
        "url": root,
        "reachable": False,
        "health_http": None,
        "pids": [],
        "processes": [],
        "detail": "",
        "flag": "--ui-mcp-proxy",
    }
    procs = discover_ui_mcp_proxy()
    # Prefer configured host/port match; still list all discovered
    out["processes"] = procs
    matched = [
        p
        for p in procs
        if int(p.get("port") or 0) == port_i
        and str(p.get("host") or "").strip() in ("", host, "127.0.0.1", "localhost", "0.0.0.0")
    ]
    out["pids"] = [int(p["pid"]) for p in (matched or procs)]

    try:
        r = requests.get(f"{root}/health", timeout=timeout)
        out["health_http"] = r.status_code
        if r.status_code == 200:
            out["reachable"] = True
            out["detail"] = "ok"
            try:
                out["health"] = r.json()
            except Exception:
                pass
        else:
            out["detail"] = f"HTTP {r.status_code} on /health"
    except requests.RequestException as e:
        out["detail"] = str(e).splitlines()[0][:160] if str(e) else "unreachable"
        if out["pids"]:
            out["detail"] += f" · process PID(s) {', '.join(str(p) for p in out['pids'])}"
    return out


def probe_spock_health(
    *,
    api_base: str,
    db_path: str,
    embeddings_url: str,
    api_key: str = "",
    chat_host: str = "localhost",
    chat_port: int = DEFAULT_CHAT_PORT,
    embed_host: str = "",
    embed_port: Optional[int] = None,
    mcp_host: str = "127.0.0.1",
    mcp_port: int = DEFAULT_MCP_PORT,
    mcp_transport: str = "streamable-http",
    webui_host: str = "127.0.0.1",
    webui_port: int = DEFAULT_MCP_WEBUI_PORT,
) -> Dict[str, Any]:
    """Same payload shape as MCP tool ``spock_health``, plus llama/MCP ports."""
    base = (api_base or "").rstrip("/")
    out: Dict[str, Any] = {
        "api_base": base,
        "db_path": db_path,
        "db_exists": os.path.isfile(db_path),
        "embeddings_url": embeddings_url,
    }
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        r = requests.get(f"{base}/health", headers=headers, timeout=5)
        out["health_http"] = r.status_code
        try:
            out["health"] = r.json()
        except Exception:
            out["health_text"] = (r.text or "")[:500]
    except requests.RequestException as e:
        out["health_error"] = str(e)
        out["hint"] = (
            "Start Embedding / RAG → START RAG API "
            f"(expected {base})."
        )

    eh, ep = embeddings_host_port(embeddings_url)
    if embed_host:
        eh = embed_host
    if embed_port is not None:
        try:
            ep = int(embed_port)
        except (TypeError, ValueError):
            pass

    try:
        ch_port = int(chat_port)
    except (TypeError, ValueError):
        ch_port = DEFAULT_CHAT_PORT
    ch_host = (chat_host or "localhost").strip() or "localhost"

    embed = probe_llama_server(eh, ep, role_hint="embedding")
    chat = probe_llama_server(ch_host, ch_port, role_hint="chat")
    out["llama_servers"] = {
        "embedding": embed,
        "chat": chat,
    }
    out["chat_url"] = f"http://{ch_host}:{ch_port}"

    pinned = ""
    oai_url = ""
    oai_model = ""
    try:
        import _warpcore_path

        _warpcore_path.ensure()
        from WarpCore import settings_store

        cfg = settings_store.load_app_config(str(Path(__file__).resolve().parent / "ship_computer.db"))
        pinned = str(cfg.get("ask_ai_provider") or "").strip()
        oai_url = str(cfg.get("openai_compat_base_url") or "").strip()
        oai_model = str(cfg.get("openai_compat_model") or "").strip()
    except Exception:
        pinned = ""
        oai_url = ""
        oai_model = ""
    out["ask_ai_provider"] = pinned or None
    if oai_model:
        out["openai_compat_model"] = oai_model
    if pinned == "OpenAI-compatible" and oai_url:
        out["chat_url"] = oai_url.rstrip("/")

    health = out.get("health") if isinstance(out.get("health"), dict) else {}
    live = (
        (health.get("llm_provider") if health else None)
        or ""
    )
    if str(live).strip() in ("", "None"):
        live = pinned
    out["llm_provider"] = live or None

    try:
        mcp_port_i = int(mcp_port)
    except (TypeError, ValueError):
        mcp_port_i = DEFAULT_MCP_PORT
    try:
        webui_port_i = int(webui_port)
    except (TypeError, ValueError):
        webui_port_i = DEFAULT_MCP_WEBUI_PORT

    out["mcp_adapter"] = probe_mcp_adapter(
        str(mcp_host or "127.0.0.1"),
        mcp_port_i,
        transport=str(mcp_transport or "streamable-http"),
    )
    out["ui_mcp_proxy"] = probe_ui_mcp_proxy(
        str(webui_host or "127.0.0.1"),
        webui_port_i,
    )
    return out


def format_spock_health_report(data: Dict[str, Any]) -> str:
    """Human report matching the llama.cpp WebUI spock_health summary style."""
    api_base = data.get("api_base") or "—"
    db_path = data.get("db_path") or "—"
    db_exists = bool(data.get("db_exists"))
    emb_url = data.get("embeddings_url") or "—"
    health = data.get("health") if isinstance(data.get("health"), dict) else {}
    http_code = data.get("health_http")
    err = data.get("health_error")
    servers = data.get("llama_servers") if isinstance(data.get("llama_servers"), dict) else {}
    embed = servers.get("embedding") if isinstance(servers.get("embedding"), dict) else {}
    chat = servers.get("chat") if isinstance(servers.get("chat"), dict) else {}
    mcp = data.get("mcp_adapter") if isinstance(data.get("mcp_adapter"), dict) else {}
    webui = data.get("ui_mcp_proxy") if isinstance(data.get("ui_mcp_proxy"), dict) else {}

    ok = http_code == 200 and not err
    title = "Spock RAG API Health Status ✓" if ok else "Spock RAG API Health Status ✗"

    lines = [
        title,
        "",
        "API configuration",
        f"  API Base URL     : {api_base}",
        f"  Database Path    : {db_path}",
        f"  Database Exists  : {'true' if db_exists else 'false'}",
        f"  Embeddings URL   : {emb_url}",
        f"  Chat URL         : {data.get('chat_url') or '—'}",
        "",
        "Health check",
    ]
    if err:
        lines.append(f"  Error            : {err}")
        if data.get("hint"):
            lines.append(f"  Hint             : {data.get('hint')}")
    else:
        status = health.get("status") or ("ok" if http_code == 200 else "—")
        llm = data.get("llm_provider") or health.get("llm_provider") or "None"
        emb_h = health.get("embeddings_url") or emb_url
        http_s = f"{http_code} OK" if http_code == 200 else str(http_code)
        lines.append(f"  HTTP Status      : {http_s}")
        lines.append(f"  Overall Status   : {status}")
        lines.append(f"  LLM Provider     : {llm}")
        lines.append(f"  Embeddings       : {emb_h}")
        if data.get("health_text"):
            lines.append(f"  Body             : {data.get('health_text')}")

    lines.extend(["", "Llama-server endpoints"])
    emb_port = embed.get("port") if isinstance(embed, dict) else None
    chat_port_lbl = chat.get("port") if isinstance(chat, dict) else None
    lines.extend(
        _format_llama_lines(
            embed, label=f"{emb_port or DEFAULT_EMBED_PORT}/embed"
        )
    )
    lines.extend(
        _format_llama_lines(
            chat, label=f"{chat_port_lbl or DEFAULT_CHAT_PORT}/chat"
        )
    )

    lines.extend(["", "MCP Adapter"])
    lines.extend(_format_mcp_adapter_lines(mcp))

    lines.extend(["", "llama-server --ui-mcp-proxy"])
    lines.extend(_format_ui_mcp_proxy_lines(webui))

    lines.extend(["", "Summary"])
    lines.append(
        f"  {'✅' if http_code == 200 else '❌'} API server "
        f"{'responding' if http_code == 200 else 'not reachable'} on {api_base}"
    )
    lines.append(
        f"  {'✅' if db_exists else '❌'} SQLite database "
        f"{'loaded and accessible' if db_exists else 'missing'}"
    )
    emb_ok = bool(emb_url) and "health_error" not in data
    lines.append(
        f"  {'✅' if emb_ok else '⚠️'} Embeddings URL configured: {emb_url}"
    )
    lines.append(_summary_llama_line(embed, role="embedding"))
    lines.append(_summary_llama_line(chat, role="chat"))
    lines.append(_summary_mcp_adapter_line(mcp))
    lines.append(_summary_ui_mcp_proxy_line(webui))
    llm = (
        data.get("llm_provider")
        or (health.get("llm_provider") if health else None)
        or "None"
    )
    if llm and llm != "None":
        extra = ""
        model = data.get("openai_compat_model") or health.get("model")
        if model:
            extra = f" ({model})"
        lines.append(f"  ✅ LLM provider: {llm}{extra}")
    else:
        lines.append("  ⚠️ LLM provider not yet configured (None)")

    lines.append("")
    lines.append(json.dumps(data, indent=2, default=str))
    return "\n".join(lines)


def _format_llama_lines(info: Dict[str, Any], *, label: str) -> List[str]:
    if not info:
        return [f"  {label:<16}: not checked"]
    port = info.get("port")
    role = info.get("role") or "unknown"
    reachable = bool(info.get("reachable"))
    n_ctx = info.get("n_ctx")
    model = info.get("model_name") or info.get("model_path") or "—"
    status = "up" if reachable else "down"
    ctx_s = f"n_ctx={n_ctx}" if n_ctx is not None else "n_ctx=?"
    detail = "" if reachable else f" ({info.get('detail') or 'unreachable'})"
    return [
        f"  :{port} {role:<10}: {status}  ({ctx_s}){detail}",
        f"                 model: {model}",
    ]


def _format_mcp_adapter_lines(info: Dict[str, Any]) -> List[str]:
    if not info:
        return ["  (not checked)"]
    transport = info.get("transport") or "—"
    reachable = bool(info.get("reachable"))
    status = "up" if reachable else "down"
    pids = info.get("pids") or []
    foreign = [
        p for p in (info.get("processes") or []) if p.get("ours") is False
    ]
    lines = [
        f"  Status           : {status}  ({info.get('detail') or '—'})",
        f"  Transport        : {transport}",
        f"  Server URL       : {info.get('mcp_url') or '—'}",
        f"  SSE fallback     : {info.get('sse_url') or '—'}",
        f"  PIDs             : {', '.join(str(p) for p in pids) if pids else '(none)'}",
    ]
    if foreign:
        lines.append(
            "  ⚠️ OTHER install : "
            + ", ".join(str(p.get("pid")) for p in foreign)
            + "  (Cursor mcp.json still points at another repo)"
        )
    for proc in info.get("processes") or []:
        cmd = str(proc.get("cmdline") or "")
        if len(cmd) > 140:
            cmd = cmd[:137] + "..."
        tag = "this install" if proc.get("ours") else "OTHER INSTALL"
        lines.append(f"    {proc.get('pid')} [{tag}]: {cmd}")
    return lines


def _format_ui_mcp_proxy_lines(info: Dict[str, Any]) -> List[str]:
    if not info:
        return ["  (not checked)"]
    reachable = bool(info.get("reachable"))
    status = "up" if reachable else "down"
    pids = info.get("pids") or []
    lines = [
        f"  Status           : {status}  ({info.get('detail') or '—'})",
        f"  WebUI URL        : {info.get('url') or '—'}",
        f"  Flag             : {info.get('flag') or '--ui-mcp-proxy'}",
        f"  PIDs             : {', '.join(str(p) for p in pids) if pids else '(none)'}",
    ]
    for proc in info.get("processes") or []:
        cmd = str(proc.get("cmdline") or "")
        if len(cmd) > 140:
            cmd = cmd[:137] + "..."
        lines.append(f"    {proc.get('pid')}: {cmd}")
    return lines


def _summary_llama_line(info: Dict[str, Any], *, role: str) -> str:
    label = "Embeddings server" if role == "embedding" else "Chat server"
    if not info:
        return f"  ⚠️ {label}: not checked"
    port = info.get("port")
    reachable = bool(info.get("reachable"))
    n_ctx = info.get("n_ctx")
    ctx_s = f"ctx {n_ctx}" if n_ctx is not None else "ctx unknown"
    if reachable:
        return f"  ✅ {label} on :{port} ({ctx_s})"
    return f"  ❌ {label} on :{port} not reachable"


def _summary_mcp_adapter_line(info: Dict[str, Any]) -> str:
    if not info:
        return "  ⚠️ MCP Adapter: not checked"
    port = info.get("port")
    transport = info.get("transport") or "?"
    pids = info.get("pids") or []
    foreign = [p for p in (info.get("processes") or []) if p.get("ours") is False]
    if info.get("reachable"):
        extra = f", PIDs {', '.join(str(p) for p in pids)}" if pids else ""
        line = f"  ✅ MCP Adapter on :{port} ({transport}{extra})"
        if foreign:
            line += (
                f" — ⚠️ {len(foreign)} process(es) from another install"
            )
        return line
    if pids:
        note = ""
        if foreign:
            note = " (includes another install — check Cursor mcp.json)"
        elif transport not in ("stdio", "?"):
            note = " — likely Cursor stdio copies; start HTTP adapter from Configure"
        return (
            f"  ⚠️ MCP Adapter processes running (PIDs {', '.join(str(p) for p in pids)}) "
            f"but :{port}/mcp not reachable{note}"
        )
    return f"  ❌ MCP Adapter on :{port} not running"


def _summary_ui_mcp_proxy_line(info: Dict[str, Any]) -> str:
    if not info:
        return "  ⚠️ llama-server --ui-mcp-proxy: not checked"
    port = info.get("port")
    pids = info.get("pids") or []
    if info.get("reachable"):
        extra = f", PID {pids[0]}" if pids else ""
        return f"  ✅ llama-server --ui-mcp-proxy on :{port}{extra}"
    if pids:
        return (
            f"  ⚠️ --ui-mcp-proxy process(es) {', '.join(str(p) for p in pids)} "
            f"but :{port} not reachable"
        )
    return f"  ❌ llama-server --ui-mcp-proxy on :{port} not running"
