"""OpenAI-compatible RAG HTTP API + browser Ask AI / Deep Dive Web UI (stdlib only)."""

from __future__ import annotations

import json
import mimetypes
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import unquote, urlparse

MODEL_ID = "spock-ships-computer"
WEBUI_DIR = Path(__file__).resolve().parent / "templates" / "webui"
ASK_CONTEXT_CHAR_BUDGET = 80_000
HISTORY_MESSAGE_CAP = 24  # role messages retained before latest user turn


def _path_is_open_get(path: str) -> bool:
    p = (path or "").split("?", 1)[0]
    if p in (
        "/health",
        "/v1/health",
        "/props",
        "/v1/props",
        "/",
        "/index.html",
    ):
        return True
    if p.startswith("/webui/") or p == "/webui":
        return True
    # Static assets for templates/webui
    if p.lstrip("/") in ("app.js", "style.css", "favicon.ico"):
        return True
    return False


def _exclude_generated_flag(value: Any) -> bool:
    """Missing or unrecognized values keep the generated-site exclude on."""
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    text = str(value).strip().lower()
    if text in ("0", "false", "no", "off"):
        return False
    if text in ("1", "true", "yes", "on"):
        return True
    return True


def _ask_top_k(db_path: str, default: int = 12) -> int:
    """Snippets to retrieve per Ask request (Spock_Console app.ctx.ask_top_k)."""
    try:
        from WarpCore import settings_store
        from WarpCore.config_defaults import merge_ctx_settings

        raw = settings_store.load_app_config(db_path).get("ctx")
        return int(merge_ctx_settings(raw if isinstance(raw, dict) else None)["ask_top_k"])
    except Exception:
        return default


def _message_text(content: Any) -> str:
    if isinstance(content, list):
        parts = [
            p.get("text", "")
            for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        return "\n".join(parts)
    return str(content or "")


def _split_messages(messages: List[dict]) -> tuple:
    """Return (history_before_last_user, last_user_text)."""
    if not messages:
        return [], ""
    last_user_idx = None
    for i in range(len(messages) - 1, -1, -1):
        if (messages[i].get("role") or "") == "user":
            last_user_idx = i
            break
    if last_user_idx is None:
        return [], ""
    user_text = _message_text(messages[last_user_idx].get("content")).strip()
    history: List[Dict[str, str]] = []
    for m in messages[:last_user_idx]:
        role = (m.get("role") or "").strip()
        if role not in ("user", "assistant"):
            continue
        text = _message_text(m.get("content")).strip()
        if text:
            history.append({"role": role, "content": text})
    if len(history) > HISTORY_MESSAGE_CAP:
        history = history[-HISTORY_MESSAGE_CAP:]
    return history, user_text


def _result_to_source(r: Any) -> Dict[str, Any]:
    title = getattr(r, "title", None) or (r.get("title") if isinstance(r, dict) else "") or ""
    path = getattr(r, "path", None) or (r.get("path") if isinstance(r, dict) else "") or ""
    score = getattr(r, "score", None)
    if score is None and isinstance(r, dict):
        score = r.get("score", 0)
    snippet = (
        getattr(r, "content_snippet", None)
        or getattr(r, "snippet", None)
        or (r.get("snippet") if isinstance(r, dict) else "")
        or (r.get("content_snippet") if isinstance(r, dict) else "")
        or ""
    )
    return {
        "title": title or path or "doc",
        "path": path,
        "score": float(score or 0),
        "snippet": (snippet or "")[:500],
    }


class RagApiServer:
    """ThreadingHTTPServer: OpenAI-compat RAG + static Ask AI / Deep Dive Web UI."""

    def __init__(
        self,
        host: str,
        port: int,
        db_path: str,
        api_key: str = "",
        get_embeddings_url: Optional[Callable[[], str]] = None,
        get_llm_client: Optional[Callable[[], Any]] = None,
        hybrid_search_fn: Optional[Callable[..., Any]] = None,
        build_filter_fn: Optional[Callable[..., str]] = None,
        deep_dive_fn: Optional[Callable[..., Dict[str, Any]]] = None,
        webui_dir: Optional[Path] = None,
    ):
        self.host = host
        self.port = int(port)
        self.db_path = db_path
        self.api_key = (api_key or "").strip()
        self.get_embeddings_url = get_embeddings_url or (
            lambda: "http://localhost:8080/embeddings"
        )
        self.get_llm_client = get_llm_client
        self.hybrid_search_fn = hybrid_search_fn
        self.build_filter_fn = build_filter_fn
        self.deep_dive_fn = deep_dive_fn
        self.webui_dir = Path(webui_dir) if webui_dir else WEBUI_DIR
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        return (
            self._httpd is not None
            and self._thread is not None
            and self._thread.is_alive()
        )

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}/v1"

    @property
    def web_url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def start(self) -> None:
        if self.is_running:
            return
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def _auth_ok(self) -> bool:
                if not server.api_key:
                    return True
                auth = self.headers.get("Authorization", "")
                return auth == f"Bearer {server.api_key}"

            def _cors(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header(
                    "Access-Control-Allow-Headers", "Content-Type, Authorization"
                )
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

            def _send_json(self, code: int, payload: dict):
                body = json.dumps(payload).encode("utf-8")
                try:
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self._cors()
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    return

            def _send_bytes(self, code: int, data: bytes, content_type: str):
                try:
                    self.send_response(code)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(data)))
                    # Avoid stale llama.cpp SPA / SW caches masking templates/webui.
                    if "text/html" in (content_type or ""):
                        self.send_header("Cache-Control", "no-store, max-age=0")
                        self.send_header("Pragma", "no-cache")
                    self._cors()
                    self.end_headers()
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    return

            def _send_chat_sse(
                self,
                *,
                model: str,
                answer: str,
                sources: List[Dict[str, Any]],
                stats: Dict[str, Any],
            ) -> None:
                """OpenAI-style SSE for clients that set stream:true (llama.cpp WebUI)."""
                created = int(time.time())
                cid = f"chatcmpl-{uuid.uuid4().hex[:12]}"
                text = answer or ""

                def _chunk(delta: dict, finish_reason=None) -> bytes:
                    payload = {
                        "id": cid,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": delta,
                                "finish_reason": finish_reason,
                            }
                        ],
                    }
                    if finish_reason == "stop":
                        payload["spock_sources"] = sources
                        payload["spock_stats"] = stats
                    return f"data: {json.dumps(payload)}\n\n".encode("utf-8")

                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "close")
                    self._cors()
                    self.end_headers()
                    self.wfile.write(_chunk({"role": "assistant", "content": ""}))
                    # Single content chunk (RAG answer is already complete).
                    if text:
                        self.wfile.write(_chunk({"content": text}))
                    self.wfile.write(_chunk({}, finish_reason="stop"))
                    self.wfile.write(b"data: [DONE]\n\n")
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    return

            def _read_json(self) -> dict:
                length = int(self.headers.get("Content-Length", 0) or 0)
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    return json.loads(raw.decode("utf-8") or "{}")
                except Exception:
                    return {}

            def _serve_webui(self, req_path: str) -> bool:
                """Serve static files from templates/webui. Returns True if handled."""
                raw = unquote(urlparse(req_path).path or "/")
                if raw in ("/", "/index.html"):
                    rel = "index.html"
                elif raw.startswith("/webui/"):
                    rel = raw[len("/webui/") :]
                elif raw == "/webui":
                    rel = "index.html"
                else:
                    # Also allow /app.js, /style.css at root for simpler HTML refs
                    if raw.lstrip("/") in ("app.js", "style.css", "favicon.ico"):
                        rel = raw.lstrip("/")
                    else:
                        return False
                if ".." in rel.replace("\\", "/").split("/"):
                    self._send_json(
                        400, {"error": {"message": "Invalid path", "type": "invalid_request"}}
                    )
                    return True
                target = (server.webui_dir / rel).resolve()
                try:
                    target.relative_to(server.webui_dir.resolve())
                except ValueError:
                    self._send_json(
                        403, {"error": {"message": "Forbidden", "type": "auth"}}
                    )
                    return True
                if not target.is_file():
                    self._send_json(
                        404, {"error": {"message": "Not found", "type": "invalid_request"}}
                    )
                    return True
                data = target.read_bytes()
                ctype, _ = mimetypes.guess_type(str(target))
                if not ctype:
                    if target.suffix == ".js":
                        ctype = "application/javascript; charset=utf-8"
                    elif target.suffix == ".css":
                        ctype = "text/css; charset=utf-8"
                    elif target.suffix == ".html":
                        ctype = "text/html; charset=utf-8"
                    else:
                        ctype = "application/octet-stream"
                elif "charset" not in ctype and ctype.startswith("text/"):
                    ctype = ctype + "; charset=utf-8"
                self._send_bytes(200, data, ctype)
                return True

            def do_OPTIONS(self):
                self.send_response(204)
                self._cors()
                self.end_headers()

            def do_GET(self):
                path = urlparse(self.path).path or "/"
                if not _path_is_open_get(path) and not self._auth_ok():
                    self._send_json(
                        401, {"error": {"message": "Unauthorized", "type": "auth"}}
                    )
                    return
                if path in ("/health", "/v1/health"):
                    llm = server.get_llm_client() if server.get_llm_client else None
                    # Do not call llm.refresh() here — ADC / provider probes can block
                    # the browser health badge for a long time (or look "down").
                    provider = "None"
                    model_name = ""
                    if llm is not None:
                        provider = (
                            getattr(llm, "active_provider_name", None)
                            or getattr(llm, "active_provider", None)
                            or "None"
                        )
                        if callable(provider):
                            try:
                                provider = provider()
                            except Exception:
                                provider = "None"
                        if not provider or provider == "None":
                            preferred = getattr(llm, "preferred_provider", None)
                            if preferred:
                                provider = f"{preferred} (not probed)"
                        model_name = str(getattr(llm, "model", None) or "").strip()
                        if str(provider).startswith("llama-server"):
                            refresh = getattr(llm, "refresh_llama_model", None)
                            if callable(refresh):
                                try:
                                    model_name = str(refresh() or model_name).strip()
                                except Exception:
                                    pass
                        if not model_name:
                            try:
                                resolve = getattr(llm, "resolve_model", None)
                                if callable(resolve):
                                    model_name = str(resolve() or "").strip()
                            except Exception:
                                model_name = ""
                    self._send_json(
                        200,
                        {
                            "status": "ok",
                            "llm_provider": provider,
                            "model": model_name,
                            "embeddings_url": server.get_embeddings_url(),
                            "web_ui": server.web_url,
                            "api_key_required": bool(server.api_key),
                        },
                    )
                    return
                # llama.cpp WebUI probes /props on connect. Without this stub it
                # shows "Server unavailable / Not found" even when /v1/models works.
                # Spock Ask AI itself is templates/webui at GET / — not this shell.
                if path in ("/props", "/v1/props"):
                    self._send_json(
                        200,
                        {
                            "default_generation_settings": {
                                "model": MODEL_ID,
                            },
                            "total_slots": 1,
                            "model_path": MODEL_ID,
                            "modalities": {"vision": False},
                            "spock_web_ui": server.web_url,
                            "spock_note": (
                                "This is the Spock RAG API. For Ask AI / Deep Dive "
                                f"open {server.web_url} (templates/webui), not "
                                "llama.cpp WebUI (:8082)."
                            ),
                        },
                    )
                    return
                if path in ("/v1/models", "/models"):
                    if not self._auth_ok():
                        self._send_json(
                            401, {"error": {"message": "Unauthorized", "type": "auth"}}
                        )
                        return
                    self._send_json(
                        200,
                        {
                            "object": "list",
                            "data": [
                                {
                                    "id": MODEL_ID,
                                    "object": "model",
                                    "owned_by": "spock-to-bridge",
                                }
                            ],
                        },
                    )
                    return
                if self._serve_webui(self.path):
                    return
                self._send_json(
                    404, {"error": {"message": "Not found", "type": "invalid_request"}}
                )

            def do_POST(self):
                if not self._auth_ok():
                    self._send_json(
                        401, {"error": {"message": "Unauthorized", "type": "auth"}}
                    )
                    return
                path = urlparse(self.path).path or "/"
                if path not in ("/v1/chat/completions", "/chat/completions"):
                    self._send_json(
                        404, {"error": {"message": "Not found", "type": "invalid_request"}}
                    )
                    return
                body = self._read_json()
                messages = body.get("messages") or []
                history, user_text = _split_messages(messages)
                if not user_text.strip():
                    self._send_json(
                        400,
                        {
                            "error": {
                                "message": "No user message found",
                                "type": "invalid_request",
                            }
                        },
                    )
                    return

                mode = str(body.get("spock_mode") or "ask").strip().lower()
                if mode not in ("ask", "deep_dive"):
                    mode = "ask"
                path_filter = str(body.get("spock_path_filter") or "").strip()
                ext_filter = str(
                    body.get("spock_extension")
                    or body.get("spock_lang_filter")
                    or ""
                ).strip()
                exclude_generated = _exclude_generated_flag(
                    body.get("spock_exclude_generated")
                )
                filter_clause = ""
                if server.build_filter_fn:
                    try:
                        try:
                            filter_clause = (
                                server.build_filter_fn(
                                    path_filter, ext_filter, exclude_generated
                                )
                                or ""
                            )
                        except TypeError:
                            try:
                                filter_clause = (
                                    server.build_filter_fn(path_filter, ext_filter)
                                    or ""
                                )
                            except TypeError:
                                filter_clause = (
                                    server.build_filter_fn(path_filter) or ""
                                )
                    except Exception:
                        filter_clause = ""

                llm = server.get_llm_client() if server.get_llm_client else None
                if llm is None:
                    self._send_json(
                        503,
                        {
                            "error": {
                                "message": "LLM client not available",
                                "type": "server",
                            }
                        },
                    )
                    return
                if hasattr(llm, "refresh"):
                    llm.refresh()
                if not getattr(llm, "is_available", False):
                    self._send_json(
                        503,
                        {
                            "error": {
                                "message": (
                                    "No LLM provider available "
                                    "(start LM Studio, llama-server, or OpenAI-compatible)"
                                ),
                                "type": "server",
                            }
                        },
                    )
                    return

                emb_url = server.get_embeddings_url()
                sources: List[Dict[str, Any]] = []
                stats: Dict[str, Any] = {"mode": mode}
                answer = ""

                if mode == "deep_dive":
                    if not server.deep_dive_fn:
                        self._send_json(
                            501,
                            {
                                "error": {
                                    "message": "Deep Dive not wired on this RAG server",
                                    "type": "server",
                                }
                            },
                        )
                        return
                    try:
                        result = server.deep_dive_fn(
                            question=user_text,
                            filter_clause=filter_clause,
                            history=history,
                            llm=llm,
                            embeddings_url=emb_url,
                            db_path=server.db_path,
                        )
                    except Exception as e:
                        self._send_json(
                            500,
                            {
                                "error": {
                                    "message": f"Deep Dive failed: {e}",
                                    "type": "server",
                                }
                            },
                        )
                        return
                    answer = (result or {}).get("answer") or ""
                    sources = list((result or {}).get("sources") or [])
                    stats = dict((result or {}).get("stats") or {})
                    stats["mode"] = "deep_dive"
                else:
                    results = []
                    context = "(hybrid search not wired)"
                    if server.hybrid_search_fn:
                        top_k = _ask_top_k(server.db_path)
                        try:
                            try:
                                results = server.hybrid_search_fn(
                                    server.db_path,
                                    user_text,
                                    top_k=top_k,
                                    embeddings_url=emb_url,
                                    filter_clause=filter_clause,
                                )
                            except TypeError:
                                results = server.hybrid_search_fn(
                                    server.db_path,
                                    user_text,
                                    top_k=top_k,
                                    embeddings_url=emb_url,
                                )
                        except Exception as e:
                            results = []
                            context = f"(search error: {e})"
                        else:
                            parts = []
                            for r in results:
                                src = _result_to_source(r)
                                sources.append(src)
                                parts.append(
                                    f"### {src['title']}\nPath: {src['path']}\n{src['snippet']}"
                                )
                            context = (
                                "\n\n".join(parts)
                                if parts
                                else "(no matching documents)"
                            )
                    if len(context) > ASK_CONTEXT_CHAR_BUDGET:
                        context = (
                            context[:ASK_CONTEXT_CHAR_BUDGET]
                            + "\n\n[Context truncated]"
                        )
                    from llm_client import ASK_SYSTEM_PROMPT

                    answer = llm.ask_with_context(
                        user_text, context, ASK_SYSTEM_PROMPT, history=history
                    )
                    stats = {
                        "mode": "ask",
                        "sources": len(sources),
                        "filter": path_filter or None,
                        "extension": ext_filter or None,
                    }

                created = int(time.time())
                model_out = body.get("model") or MODEL_ID
                want_stream = bool(body.get("stream"))
                if want_stream:
                    self._send_chat_sse(
                        model=model_out,
                        answer=answer or "",
                        sources=sources,
                        stats=stats,
                    )
                    return
                self._send_json(
                    200,
                    {
                        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                        "object": "chat.completion",
                        "created": created,
                        "model": model_out,
                        "choices": [
                            {
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": answer or "",
                                },
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_tokens": 0,
                        },
                        "spock_sources": sources,
                        "spock_stats": stats,
                    },
                )

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
            except Exception:
                pass
            try:
                self._httpd.server_close()
            except Exception:
                pass
        self._httpd = None
        self._thread = None
