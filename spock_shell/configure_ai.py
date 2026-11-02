"""Configure Spock AI — one tabbed form for every chat / RAG / MCP backend.

Replaces the scattered connection modals and one-off "test" buttons that used to
live in the monolith and in Chat AI Helper. Each connector tab owns its
settings, a Test connection probe, and a single Save action that also pins
``ask_ai_provider`` so there is exactly one answer to "what will Ask AI use?".
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

import requests
from PyQt6.QtCore import QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from spock_shell.paths import ensure_root_on_path

ensure_root_on_path()

from llm_client import (  # noqa: E402  (needs ROOT on sys.path first)
    embeddings_chat_collision,
    google_adc_bearer_token,
    normalize_openai_compat_base,
    vertex_global_base,
)
from llm_client import _is_adc_api_key as is_adc_api_key  # noqa: E402
from llm_client import (  # noqa: E402
    _looks_like_google_openai_url as looks_like_google_openai_url,
)
from spock_shell.bridge_host import (  # noqa: E402
    apply_provider_config,
    make_llm_client,
)

OK_COLOR = "#4caf50"
BAD_COLOR = "#f44336"
BUSY_COLOR = "#FFC107"

# Model id the Spock RAG gateway advertises. Chatting with it would recurse.
RAG_GATEWAY_MODEL = "spock-ships-computer"
ProbeResult = Tuple[bool, str]


def _one_line(text: str, limit: int = 240) -> str:
    return " ".join((text or "").split())[:limit]


def rag_api_base(config: Optional[Dict[str, Any]]) -> str:
    """RAG API origin. Defaults match ``Invoke-RestMethod http://127.0.0.1:8090``."""
    rag = (config or {}).get("rag_api") if isinstance(config, dict) else None
    rag = rag if isinstance(rag, dict) else {}
    host = str(rag.get("host") or "127.0.0.1").strip() or "127.0.0.1"
    try:
        port = int(rag.get("port") or 8090)
    except (TypeError, ValueError):
        port = 8090
    if port < 1 or port > 65535:
        port = 8090
    return f"http://{host}:{port}"


def _connect_reason(exc: BaseException) -> str:
    """Keep the OS reason from a requests/urllib3 connection error."""
    text = str(exc)
    for needle in (
        "[WinError",
        "[Errno",
        "Connection refused",
        "No connection could be made",
        "Name or service not known",
        "nodename nor servname",
    ):
        at = text.find(needle)
        if at != -1:
            snippet = text[at:].split("'))")[0].split('"))')[0]
            return _one_line(snippet, 200)
    return _one_line(text, 200)


def _fetch_json(url: str, timeout: float = 8) -> Tuple[Optional[dict], Optional[str]]:
    """GET ``url`` and parse a JSON object. Errors are returned, never raised."""
    try:
        resp = requests.get(url, timeout=timeout)
    except requests.Timeout:
        return None, f"Timed out after {timeout:g}s"
    except requests.ConnectionError as e:
        return None, f"Could not connect: {_connect_reason(e)}"
    except requests.RequestException as e:
        return None, f"Request failed: {type(e).__name__}: {e}"
    except Exception as e:
        return None, f"Request failed: {type(e).__name__}: {e}"

    body = resp.text or ""
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}: {_one_line(body) or '(empty body)'}"
    if not body.strip():
        return None, "HTTP 200 with an empty body"
    try:
        data = resp.json()
    except ValueError as e:
        return None, f"Response was not JSON ({e}): {_one_line(body)}"
    if not isinstance(data, dict):
        return None, f"Expected a JSON object, got {type(data).__name__}"
    return data, None


def probe_rag_health(base_url: str, timeout: float = 8) -> ProbeResult:
    """Check OpenAI-compatible RAG ``GET /health``."""
    url = base_url.rstrip("/") + "/health"
    data, err = _fetch_json(url, timeout)
    if err or data is None:
        return False, f"Health {url} — {err}"
    status = str(data.get("status") or "").strip()
    summary = (
        f"status={status or '(missing)'} | "
        f"llm_provider={data.get('llm_provider') or 'None'} | "
        f"model={data.get('model') or '(none)'} | "
        f"embeddings={data.get('embeddings_url') or '(none)'} | "
        f"web_ui={data.get('web_ui') or '(none)'}"
    )
    if status.lower() != "ok":
        return False, f"Health {url} — {summary}"
    return True, f"Health OK — {summary}"


def probe_rag_props(base_url: str, timeout: float = 8) -> ProbeResult:
    """Check OpenAI-compatible RAG ``GET /props``."""
    url = base_url.rstrip("/") + "/props"
    data, err = _fetch_json(url, timeout)
    if err or data is None:
        return False, f"Properties {url} — {err}"
    settings = data.get("default_generation_settings")
    if not isinstance(settings, dict):
        return False, f"Properties {url} — missing default_generation_settings"
    model = str(settings.get("model") or "").strip()
    if not model:
        return False, f"Properties {url} — default_generation_settings.model is empty"
    summary = (
        f"model={model} | slots={data.get('total_slots')} | "
        f"model_path={data.get('model_path') or '(none)'}"
    )
    note = str(data.get("spock_note") or "").strip()
    if note:
        summary += f" | {_one_line(note, 160)}"
    return True, f"Properties OK — {summary}"


def probe_called_llm(timeout: int = 300) -> ProbeResult:
    """Ask the saved LLM client to reply PING. Failures are returned, not raised.

    Same path as::

        from _start_rag_api import load_cfg
        from spock_rag_adapter.bridge_host import make_llm_client
        llm = make_llm_client(load_cfg())
        llm.ask_with_context('Reply with PING', 'Context: PING')
    """
    try:
        from _start_rag_api import load_cfg
        from spock_rag_adapter.bridge_host import make_llm_client

        llm = make_llm_client(load_cfg())
    except Exception as e:
        return False, f"Could not build LLM client: {type(e).__name__}: {e}"
    try:
        provider = llm.active_provider
        model = llm.model
        available = bool(llm.is_available)
    except Exception as e:
        return False, f"LLM status read failed: {type(e).__name__}: {e}"
    header = f"Provider: {provider} | Model: {model} | Available: {available}"
    if not available:
        detail = getattr(llm, "last_error", "") or "No reachable provider."
        return False, f"{header}\n{detail}"
    try:
        response = llm.ask_with_context(
            "Reply with PING", "Context: PING", timeout=timeout
        )
    except Exception as e:
        return False, f"{header}\nLLM call failed: {type(e).__name__}: {e}"
    text = str(response or "").strip()
    if not text:
        detail = getattr(llm, "last_error", "") or "Empty response."
        return False, f"{header}\n{detail}"
    if text.lower().startswith("could not reach"):
        return False, f"{header}\nResponse: {_one_line(text, 500)}"
    if "ping" not in text.lower():
        return False, (
            f"{header}\nResponse did not include PING: {_one_line(text, 500)}"
        )
    return True, f"{header}\nResponse: {_one_line(text, 500)}"


class _ProbeJob(QThread):
    """Run a probe off the UI thread and always emit ``(ok, message)``."""

    result = pyqtSignal(bool, str)

    def __init__(self, title: str, fn: Callable[[], ProbeResult], parent=None):
        super().__init__(parent)
        self._title = title
        self._fn = fn

    def run(self) -> None:
        try:
            outcome = self._fn()
            if not isinstance(outcome, tuple) or len(outcome) != 2:
                raise TypeError(
                    f"probe returned {type(outcome).__name__}, expected (bool, str)"
                )
            ok, msg = outcome
            if not isinstance(ok, bool) or not isinstance(msg, str):
                raise TypeError(
                    f"probe returned ({type(ok).__name__}, {type(msg).__name__}), "
                    "expected (bool, str)"
                )
        except Exception as e:
            ok, msg = False, f"{self._title} failed: {type(e).__name__}: {e}"
        self.result.emit(ok, msg)


def _model_ids(payload: Any) -> list:
    if not isinstance(payload, dict):
        return []
    entries = payload.get("data") or payload.get("models") or []
    ids = []
    for m in entries:
        if isinstance(m, dict):
            ids.append(str(m.get("id") or m.get("name") or m.get("model") or ""))
        else:
            ids.append(str(m))
    return [i for i in ids if i]


class _ConnectorTab(QWidget):
    """Shared skeleton: hint, form rows, Test connection, Save & Use."""

    saved = pyqtSignal(dict, str)

    provider_name = ""
    hint_text = ""
    save_label = "Save & Use"
    _extra_btns: tuple = ()

    def __init__(self, config: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.config = config
        outer = QVBoxLayout(self)
        hint = QLabel(self.hint_text)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #aaa;")
        outer.addWidget(hint)

        self.form = QFormLayout()
        outer.addLayout(self.form)
        self.build_fields()

        row = QHBoxLayout()
        self.test_btn = QPushButton("Test connection")
        self.test_btn.clicked.connect(self._run_test)
        row.addWidget(self.test_btn)
        self.save_btn = QPushButton(self.save_label)
        self.save_btn.clicked.connect(self._save)
        row.addWidget(self.save_btn)
        row.addStretch()
        outer.addLayout(row)
        self.add_extra_actions(outer)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        outer.addStretch()

    # --- subclass hooks ---
    def build_fields(self) -> None:
        raise NotImplementedError

    def collect(self) -> Dict[str, Any]:
        raise NotImplementedError

    def test_connection(self) -> None:
        raise NotImplementedError

    def add_extra_actions(self, outer: QVBoxLayout) -> None:
        return

    # --- shared behaviour ---
    def set_status(self, text: str, color: str = BUSY_COLOR) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {color};")

    def ok(self, text: str) -> None:
        self.set_status(f"\u2713 {text}", OK_COLOR)

    def bad(self, text: str) -> None:
        self.set_status(f"\u2717 {text}", BAD_COLOR)

    def _probe_buttons(self) -> tuple:
        return (self.test_btn, *self._extra_btns)

    def _set_probe_buttons(self, enabled: bool) -> None:
        for button in self._probe_buttons():
            button.setEnabled(enabled)

    def _probe_busy(self) -> bool:
        job = getattr(self, "_probe_job", None)
        return job is not None and job.isRunning()

    def _run_test(self) -> None:
        if self._probe_busy():
            self.set_status("A test is already running…")
            return
        self.set_status("Testing…")
        self._set_probe_buttons(False)
        try:
            self.test_connection()
        except Exception as e:
            self.bad(f"Test failed: {type(e).__name__}: {e}")
        finally:
            self._set_probe_buttons(True)

    def _run_background_probe(self, title: str, fn: Callable[[], ProbeResult]) -> None:
        """Run ``fn`` off the UI thread. Exceptions become a red status line."""
        if self._probe_busy():
            self.set_status("A test is already running…")
            return
        self.set_status(f"{title}…")
        self._set_probe_buttons(False)
        job = _ProbeJob(title, fn, self)

        def _finish(ok: bool, msg: str) -> None:
            if ok:
                self.ok(msg)
            else:
                self.bad(msg)
            self._set_probe_buttons(True)
            self._probe_job = None

        job.result.connect(_finish)
        self._probe_job = job
        try:
            job.start()
        except Exception as e:
            self.bad(f"{title} failed: {type(e).__name__}: {e}")
            self._set_probe_buttons(True)
            self._probe_job = None

    def _save(self) -> None:
        self.saved.emit(self.collect(), self.provider_name)
        self.ok(f"Saved. Ask AI now uses {self.provider_name}.")


class LmStudioTab(_ConnectorTab):
    provider_name = "LM Studio"
    hint_text = (
        "Chat completions from LM Studio's OpenAI-compatible server. "
        "RAG vectors still come from the Embedding / RAG tab. "
        "Load context overrides LM Studio's multi-GPU clamp of 8192."
    )

    def build_fields(self) -> None:
        self.host = QLineEdit(str(self.config.get("lm_studio_host") or "localhost"))
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(int(self.config.get("lm_studio_port") or 1234))
        self.model = QLineEdit(str(self.config.get("lm_studio_model") or ""))
        self.model.setPlaceholderText("blank = use whatever LM Studio has loaded")
        self.ctx = QSpinBox()
        self.ctx.setRange(512, 262144)
        self.ctx.setSingleStep(1024)
        self.ctx.setValue(int(self.config.get("lm_studio_context_length") or 32768))
        self.ctx.setToolTip(
            "context_length sent to LM Studio on load.\n"
            "Use 32768–65536 on RTX 6000; avoid 262144 unless VRAM is free."
        )
        self.key = QLineEdit(str(self.config.get("lm_studio_key") or ""))
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.form.addRow("Host", self.host)
        self.form.addRow("Port", self.port)
        self.form.addRow("Model id", self.model)
        self.form.addRow("Load context", self.ctx)
        self.form.addRow("API key (optional)", self.key)

    def collect(self) -> Dict[str, Any]:
        return {
            "lm_studio_host": self.host.text().strip() or "localhost",
            "lm_studio_port": self.port.value(),
            "lm_studio_model": self.model.text().strip(),
            "lm_studio_context_length": int(self.ctx.value()),
            "lm_studio_key": self.key.text(),
        }

    def test_connection(self) -> None:
        host = self.host.text().strip() or "localhost"
        url = f"http://{host}:{self.port.value()}/v1/models"
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            self.bad(f"HTTP {resp.status_code} from {url}")
            return
        ids = _model_ids(resp.json() if resp.content else {})
        loaded = ", ".join(ids[:4]) or "no models loaded"
        self.ok(f"LM Studio reachable — {loaded}")


class OllamaTab(_ConnectorTab):
    provider_name = "Ollama"
    hint_text = (
        "Chat completions from a local Ollama daemon over its native /api/chat "
        "protocol. Defaults match a stock install (localhost:11434). "
        "Model id must be one Ollama has pulled, e.g. llama3.1:8b."
    )

    def build_fields(self) -> None:
        self.host = QLineEdit(str(self.config.get("ollama_host") or "localhost"))
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(int(self.config.get("ollama_port") or 11434))
        self.model = QLineEdit(str(self.config.get("ollama_model") or ""))
        self.model.setPlaceholderText("e.g. llama3.1:8b — Test connection lists these")
        self.form.addRow("Host", self.host)
        self.form.addRow("Port", self.port)
        self.form.addRow("Model", self.model)

    def collect(self) -> Dict[str, Any]:
        return {
            "ollama_host": self.host.text().strip() or "localhost",
            "ollama_port": self.port.value(),
            "ollama_model": self.model.text().strip(),
        }

    def test_connection(self) -> None:
        host = self.host.text().strip() or "localhost"
        url = f"http://{host}:{self.port.value()}/api/tags"
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            self.bad(f"HTTP {resp.status_code} from {url}")
            return
        ids = _model_ids(resp.json() if resp.content else {})
        if not ids:
            self.bad("Ollama is up but has no models. Run: ollama pull llama3.1:8b")
            return
        if not self.model.text().strip():
            self.model.setText(ids[0])
        self.ok(f"Ollama reachable — pulled models: {', '.join(ids[:6])}")


class LlamaCppTab(_ConnectorTab):
    provider_name = "llama-server"
    hint_text = (
        "Chat completions from llama-server (llamaccp). Use an instruct / chat "
        "GGUF on the chat port (usually 8081) — not the embeddings port (8080) "
        "and not the Spock RAG gateway (8090).\n"
        "Also sets suite-wide embed/docs ports and local completion max_tokens "
        "(AI Helper stream length)."
    )

    def build_fields(self) -> None:
        from WarpCore.service_endpoints import (
            DEFAULT_CHAT_PORT,
            DEFAULT_DOCS_PORT,
            DEFAULT_EMBED_PORT,
            DEFAULT_CTX,
            resolve_ctx,
            resolve_ports,
        )

        ports = resolve_ports(self.config)
        ctx = resolve_ctx(self.config)
        self.host = QLineEdit(str(self.config.get("llama_host") or "localhost"))
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(int(self.config.get("llama_port") or ports["chat"] or DEFAULT_CHAT_PORT))
        self.port.setToolTip(
            "Instruct / chat llama-server port (typically 8081). "
            "Do not use the embeddings port (typically 8080)."
        )
        self.embed_port = QSpinBox()
        self.embed_port.setRange(1, 65535)
        self.embed_port.setValue(
            int(self.config.get("embed_port") or ports["embed"] or DEFAULT_EMBED_PORT)
        )
        self.embed_port.setToolTip(
            "Embeddings llama-server port. Updates embedding_profile.embeddings_url."
        )
        self.docs_port = QSpinBox()
        self.docs_port.setRange(1, 65535)
        self.docs_port.setValue(
            int(self.config.get("docs_port") or ports["docs"] or DEFAULT_DOCS_PORT)
        )
        self.docs_port.setToolTip("AI Helper MkDocs site/ HTTP port (helper_main).")
        self.chat_n_ctx = QSpinBox()
        self.chat_n_ctx.setRange(512, 1_048_576)
        self.chat_n_ctx.setSingleStep(1024)
        self.chat_n_ctx.setValue(int(ctx["chat_n_ctx"]))
        self.chat_n_ctx.setToolTip("Preferred chat llama-server -c when launching.")
        self.embed_n_ctx = QSpinBox()
        self.embed_n_ctx.setRange(512, 1_048_576)
        self.embed_n_ctx.setSingleStep(1024)
        self.embed_n_ctx.setValue(int(ctx["embed_n_ctx"]))
        self.embed_n_ctx.setToolTip("Preferred embed llama-server -c when launching.")
        self.chat_max_tokens = QSpinBox()
        self.chat_max_tokens.setRange(256, 65536)
        self.chat_max_tokens.setSingleStep(256)
        self.chat_max_tokens.setValue(
            int(ctx["chat_max_tokens"] or DEFAULT_CTX["chat_max_tokens"])
        )
        self.chat_max_tokens.setToolTip(
            "Local chat / AI Helper stream completion cap (max_tokens)."
        )
        self.form.addRow("Host", self.host)
        self.form.addRow("Chat port", self.port)
        self.form.addRow("Embed port", self.embed_port)
        self.form.addRow("Docs port (AI Helper)", self.docs_port)
        self.form.addRow("Chat n_ctx (-c)", self.chat_n_ctx)
        self.form.addRow("Embed n_ctx (-c)", self.embed_n_ctx)
        self.form.addRow("Chat max_tokens", self.chat_max_tokens)

    def collect(self) -> Dict[str, Any]:
        from WarpCore.service_endpoints import sync_embedding_url_port

        patch = {
            "llama_host": self.host.text().strip() or "localhost",
            "llama_port": self.port.value(),
            "embed_port": self.embed_port.value(),
            "docs_port": self.docs_port.value(),
            "chat_n_ctx": self.chat_n_ctx.value(),
            "embed_n_ctx": self.embed_n_ctx.value(),
            "chat_max_tokens": self.chat_max_tokens.value(),
        }
        merged = dict(self.config)
        merged.update(patch)
        synced = sync_embedding_url_port(merged, embed_port=self.embed_port.value())
        patch["embedding_profile"] = synced.get("embedding_profile")
        return patch

    def test_connection(self) -> None:
        host = self.host.text().strip() or "localhost"
        port = self.port.value()
        chat_probe = f"http://{host}:{port}/v1/chat/completions"
        if embeddings_chat_collision(chat_probe):
            self.bad(
                "That port is the embeddings server. Point llamaccp at the "
                "instruct chat port (often 8081)."
            )
            return
        try:
            resp = requests.get(f"http://{host}:{port}/v1/models", timeout=5)
        except Exception as e:
            self.bad(f"Connection failed: {e}")
            return
        if resp.status_code == 200:
            if any(RAG_GATEWAY_MODEL in i for i in _model_ids(
                resp.json() if resp.content else {}
            )):
                self.bad(
                    "That port is the Spock RAG API, not llama-server. "
                    "Use the Launch chat port (often 8081)."
                )
                return
            self.ok("llama-server reachable (/v1/models)")
            return
        # /v1/models can 404 on older builds — fall back to /health.
        resp = requests.get(f"http://{host}:{port}/health", timeout=5)
        if resp.status_code != 200:
            self.bad(f"HTTP {resp.status_code} from {host}:{port}")
            return
        body = (resp.text or "").lower()
        if "llm_provider" in body or "embeddings_url" in body:
            self.bad(
                "That /health looks like the Spock RAG API, not llama-server. "
                "Use the Launch chat port, usually 8081."
            )
            return
        self.ok("/health OK (confirm this is llama-server, not the RAG API)")


class OpenAiCompatTab(_ConnectorTab):
    provider_name = "OpenAI-compatible"
    hint_text = (
        "Any OpenAI-compatible endpoint: Vertex Gemini, OpenAI, a proxy, or a "
        "remote instruct server.\n"
        "Do NOT point this at Spock RAG (:8090) — that gateway calls this client "
        "and would recurse.\n"
        "Vertex with gcloud Application Default Credentials: set API key to  adc\n"
        "Vertex regions only serve some models — gemini-3.5-* needs the global "
        "root (aiplatform.googleapis.com/…/locations/global/endpoints/openapi). "
        "Test connection switches you there automatically on a 404.\n"
        "Test health and Test properties call the local RAG API "
        "(http://127.0.0.1:8090 by default). Test LLM status asks the saved "
        "Ask AI provider to reply PING."
    )

    def add_extra_actions(self, outer: QVBoxLayout) -> None:
        row = QHBoxLayout()
        base = rag_api_base(self.config)
        self.health_btn = QPushButton("Test health")
        self.health_btn.setToolTip(f"GET {base}/health")
        self.health_btn.clicked.connect(self._test_health)
        self.props_btn = QPushButton("Test properties")
        self.props_btn.setToolTip(f"GET {base}/props")
        self.props_btn.clicked.connect(self._test_props)
        self.llm_status_btn = QPushButton("Test LLM status")
        self.llm_status_btn.setToolTip(
            "Build the saved LLM client (load_cfg + make_llm_client) and ask "
            "it to reply PING. Save & Use first if these fields are unsaved."
        )
        self.llm_status_btn.clicked.connect(self._test_llm_status)
        self._extra_btns = (self.health_btn, self.props_btn, self.llm_status_btn)
        for button in self._extra_btns:
            row.addWidget(button)
        row.addStretch()
        outer.addLayout(row)

    def _test_health(self) -> None:
        base = rag_api_base(self.config)
        self.health_btn.setToolTip(f"GET {base}/health")
        self._run_background_probe("Health", lambda: probe_rag_health(base))

    def _test_props(self) -> None:
        base = rag_api_base(self.config)
        self.props_btn.setToolTip(f"GET {base}/props")
        self._run_background_probe("Properties", lambda: probe_rag_props(base))

    def _test_llm_status(self) -> None:
        self._run_background_probe("LLM status", probe_called_llm)

    def build_fields(self) -> None:
        self.url = QLineEdit(str(self.config.get("openai_compat_base_url") or ""))
        self.url.setPlaceholderText(
            "http://127.0.0.1:8081/v1  or  …/endpoints/openapi"
        )
        self.key = QLineEdit(str(self.config.get("openai_compat_api_key") or ""))
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("adc  (gcloud Application Default Credentials)")
        self.model = QLineEdit(str(self.config.get("openai_compat_model") or ""))
        self.model.setPlaceholderText("e.g. google/gemini-2.5-flash")
        self.n_ctx = QSpinBox()
        self.n_ctx.setRange(2048, 1_048_576)
        self.n_ctx.setSingleStep(8192)
        self.n_ctx.setValue(int(self.config.get("openai_compat_n_ctx") or 131072))
        self.n_ctx.setToolTip(
            "Deep Dive packing budget. Vertex Gemini can use 128k–1M."
        )
        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(256, 65536)
        self.max_tokens.setSingleStep(1024)
        self.max_tokens.setValue(
            int(self.config.get("openai_compat_max_tokens") or 8192)
        )
        self.max_tokens.setToolTip(
            "Completion length cap. Raise this if answers cut off mid-sentence."
        )
        self.form.addRow("Base URL", self.url)
        self.form.addRow("API key (optional)", self.key)
        self.form.addRow("Model", self.model)
        self.form.addRow("Context window (n_ctx)", self.n_ctx)
        self.form.addRow("Max output tokens", self.max_tokens)

    def collect(self) -> Dict[str, Any]:
        base = normalize_openai_compat_base(self.url.text()) or self.url.text().strip()
        if base and base != self.url.text().strip():
            self.url.setText(base)
        return {
            "openai_compat_base_url": base,
            "openai_compat_api_key": self.key.text().strip(),
            "openai_compat_model": self.model.text().strip(),
            "openai_compat_n_ctx": int(self.n_ctx.value()),
            "openai_compat_max_tokens": int(self.max_tokens.value()),
        }

    def test_connection(self) -> None:
        base = normalize_openai_compat_base(self.url.text())
        if not base:
            self.bad("Enter a base URL")
            return
        key = self.key.text().strip()
        headers = {"Content-Type": "application/json"}
        try:
            if looks_like_google_openai_url(base) and is_adc_api_key(key):
                headers["Authorization"] = f"Bearer {google_adc_bearer_token()}"
            elif key and not is_adc_api_key(key):
                headers["Authorization"] = f"Bearer {key}"
        except Exception as e:
            self.bad(f"ADC auth failed: {e}")
            return

        google = looks_like_google_openai_url(base)
        try:
            resp = requests.get(f"{base}/models", headers=headers, timeout=12)
            if resp.status_code == 200:
                ids = _model_ids(resp.json() if resp.content else {})
                if any(RAG_GATEWAY_MODEL in i for i in ids):
                    self.bad(
                        "That URL is the Spock RAG gateway (:8090), not a chat "
                        "LLM. Point this at instruct chat (:8081) or Vertex."
                    )
                    return
                self.ok("OpenAI-compatible endpoint reachable")
                return
            if not google:
                self.bad(f"HTTP {resp.status_code} from {base}/models")
                return
        except Exception as e:
            if not google:
                self.bad(f"Connection failed: {e}")
                return

        # Vertex OpenAI-compat commonly 404s GET /models — probe a tiny chat.
        model = self.model.text().strip() or "google/gemini-2.5-flash"
        chat = self._chat_probe(base, model, headers)
        if chat.status_code == 200:
            self.ok(f"Vertex / Gemini chat OK (model={model})")
            return

        # Newer publisher models (gemini-3.5-*) only exist on locations/global,
        # so a regional root 404s. Retry there before reporting failure.
        global_base = vertex_global_base(base)
        if chat.status_code == 404 and global_base:
            retry = self._chat_probe(global_base, model, headers)
            if retry.status_code == 200:
                self.url.setText(global_base)
                self.ok(
                    f"{model} is only served from locations/global. "
                    "Switched the base URL to the global endpoint — press "
                    "Save & Use to keep it."
                )
                return

        detail = (chat.text or "")[:180].replace("\n", " ")
        self.bad(f"Chat test {chat.status_code}: {detail}")

    def _chat_probe(self, base: str, model: str, headers: Dict[str, str]):
        return requests.post(
            f"{base}/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 8,
            },
            timeout=45,
        )


class ConfigureAiPanel(QWidget):
    """Tabbed configuration for every AI backend the suite can talk to."""

    provider_changed = pyqtSignal(str)
    save_profile_requested = pyqtSignal()

    def __init__(
        self,
        theme: Dict[str, str],
        config: Dict[str, Any],
        save_config: Callable[[], None],
        *,
        db_path: str = "",
        mcp_host: Optional[Any] = None,
        on_rag_start: Optional[Callable[[], None]] = None,
        on_rag_stop: Optional[Callable[[], None]] = None,
        on_profile_applied: Optional[Callable[[dict], None]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.theme = theme
        self.config = config
        self._save_config = save_config
        self.db_path = db_path
        self.mcp_host = mcp_host
        # Only a host that actually owns a RagApiServer can start/stop it. Without
        # these the embedding tab just explains where the server lives.
        self._on_rag_start = on_rag_start
        self._on_rag_stop = on_rag_stop
        self._on_profile_applied = on_profile_applied
        self.mcp_panel = None
        self.webui_panel = None

        outer = QVBoxLayout(self)
        outer.addWidget(self._build_header())

        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setDocumentMode(False)
        try:
            from PyQt6.QtCore import Qt

            self.tabs.tabBar().setElideMode(Qt.TextElideMode.ElideNone)
            self.tabs.tabBar().setExpanding(False)
        except Exception:
            pass
        self.setMinimumWidth(1100)
        self.connectors = {}
        for number, cls in enumerate(
            (LmStudioTab, OllamaTab, LlamaCppTab, OpenAiCompatTab), start=1
        ):
            tab = cls(config)
            tab.saved.connect(self._on_connector_saved)
            self.connectors[cls.provider_name] = tab
            label = {
                "LM Studio": "Connect to LM Studio",
                "Ollama": "Connect to Ollama",
                "llama-server": "Connect to llamaccp",
                "OpenAI-compatible": "Connect OpenAI-compatible",
            }[cls.provider_name]
            self.tabs.addTab(tab, f"{number}  {label}")
        self.tabs.addTab(self._build_embedding_tab(), "5  Embedding / RAG")
        self.tabs.addTab(self._build_mcp_tab(), "6  MCP")
        self.tabs.addTab(self._build_webui_tab(), "7  llama.cpp WebUI")
        self.llama_gui_embed = LlamaGuiCommandTab(
            self.config, role="embedding", db_path=self.db_path
        )
        self.llama_gui_chat = LlamaGuiCommandTab(
            self.config, role="chat", db_path=self.db_path
        )
        self.tabs.addTab(self.llama_gui_embed, "8  LLama GUI Embed")
        self.tabs.addTab(self.llama_gui_chat, "9  LLama GUI Chat")
        self.tabs.currentChanged.connect(self._on_config_tab_changed)
        outer.addWidget(self.tabs, 1)

        footer = QHBoxLayout()
        self.profile_btn = QPushButton("Save to Profile…")
        self.profile_btn.setToolTip(
            "Store these settings as a named Spock profile in ship_computer.db"
        )
        self.profile_btn.clicked.connect(self.save_profile_requested.emit)
        footer.addWidget(self.profile_btn)
        manage_btn = QPushButton("Manage profiles…")
        manage_btn.setToolTip("Review and delete saved profiles (obsolete GGUFs, duplicates)")
        manage_btn.clicked.connect(self._manage_profiles)
        footer.addWidget(manage_btn)
        footer.addStretch()
        outer.addLayout(footer)

        self.refresh_active_provider()

    def _manage_profiles(self) -> None:
        from spock_shell.profiles import open_manage_profiles_dialog

        open_manage_profiles_dialog(self)

    # --- header ---
    def _build_header(self) -> QWidget:
        box = QGroupBox("Active provider")
        lay = QHBoxLayout(box)
        self.active_lbl = QLabel("")
        self.active_lbl.setWordWrap(True)
        lay.addWidget(self.active_lbl, 1)
        probe = QPushButton("Re-detect")
        probe.setToolTip("Ask the client which backend it can actually reach now")
        probe.clicked.connect(self.probe_active_provider)
        lay.addWidget(probe)
        return box

    def refresh_active_provider(self) -> None:
        name = self.config.get("ask_ai_provider") or "llama-server"
        self.active_lbl.setText(
            f"Ask AI and Deep Dive are pinned to <b>{name}</b>. "
            "Saving on a connector tab re-pins it."
        )

    def collect_all(self) -> Dict[str, Any]:
        """Snapshot every tab — used when saving or naming a Spock profile."""
        out: Dict[str, Any] = {}
        for tab in self.connectors.values():
            try:
                out.update(tab.collect())
            except Exception:
                pass
        panel = getattr(self, "embedding_panel", None)
        if panel is not None:
            try:
                out["embedding_profile"] = panel._collect_profile()
            except Exception:
                pass
            try:
                out["rag_api"] = panel.collect_rag_api()
            except Exception:
                pass
        from mcp_panel import merge_mcp_settings

        mcp_cfg = merge_mcp_settings(self.config.get("mcp"))
        for name in ("mcp_panel", "webui_panel"):
            sibling = getattr(self, name, None)
            collect = getattr(sibling, "collect_settings", None)
            if callable(collect):
                try:
                    mcp_cfg.update(collect())
                except Exception:
                    pass
        out["mcp"] = mcp_cfg
        launch = dict(self.config.get("launch") or {})
        if getattr(self, "llama_gui_embed", None) is not None:
            launch["llama_gui_embed_command"] = self.llama_gui_embed.editor.toPlainText()
        if getattr(self, "llama_gui_chat", None) is not None:
            launch["llama_gui_chat_command"] = self.llama_gui_chat.editor.toPlainText()
        out["launch"] = launch
        provider = str(self.config.get("ask_ai_provider") or "").strip()
        if provider:
            out["ask_ai_provider"] = provider
        return out

    def _on_config_tab_changed(self, _index: int) -> None:
        w = self.tabs.currentWidget()
        refresh = getattr(w, "refresh_status", None)
        if callable(refresh):
            QTimer.singleShot(0, refresh)
        if w is self.mcp_panel and self.mcp_host is not None:
            QTimer.singleShot(400, self.mcp_host.ensure_http_adapter_async)

    def probe_active_provider(self) -> None:
        try:
            client = make_llm_client(self.config)
        except Exception as e:
            self.active_lbl.setText(f"Provider probe failed: {e}")
            return
        pinned = self.config.get("ask_ai_provider") or "llama-server"
        if not client.is_available:
            self.active_lbl.setText(
                f"Pinned to <b>{pinned}</b> but nothing is reachable. "
                f"{client.last_error or 'Start the backend, then Re-detect.'}"
            )
            return
        reached = client.active_provider
        detail = f"reached <b>{reached}</b> at {client.active_url}"
        if reached != pinned:
            detail += f" (pinned provider {pinned} is not answering)"
        self.active_lbl.setText(f"Pinned to <b>{pinned}</b>, {detail}")

    # --- tabs ---
    def _build_embedding_tab(self) -> QWidget:
        from model_selector_core import merge_embedding_profile
        from model_selector_panels import EmbeddingProfilePanel

        panel = EmbeddingProfilePanel(
            self.theme,
            profile=merge_embedding_profile(self.config.get("embedding_profile")),
            rag_api=self.config.get("rag_api") or {},
            db_path=self.db_path,
        )
        panel.profile_applied.connect(self._profile_applied)
        panel.rag_api_start.connect(
            lambda: self._rag_lifecycle("START RAG API", self._on_rag_start)
        )
        panel.rag_api_stop.connect(
            lambda: self._rag_lifecycle("STOP RAG API", self._on_rag_stop)
        )
        self.embedding_panel = panel
        return panel

    def _mcp_settings(self) -> Dict[str, Any]:
        from mcp_panel import merge_mcp_settings

        mcp_cfg = merge_mcp_settings(self.config.get("mcp"))
        # Legacy flat key wins when present so old configs keep their port.
        if self.config.get("mcp_http_port"):
            try:
                mcp_cfg["http_port"] = int(self.config["mcp_http_port"])
            except (TypeError, ValueError):
                pass
        return mcp_cfg

    def _unavailable(self, message: str) -> QWidget:
        placeholder = QWidget()
        lay = QVBoxLayout(placeholder)
        msg = QLabel(message)
        msg.setWordWrap(True)
        lay.addWidget(msg)
        lay.addStretch()
        return placeholder

    def _build_mcp_tab(self) -> QWidget:
        from mcp_panel import McpControlPanel

        if self.mcp_host is None:
            return self._unavailable(
                "MCP adapter control is unavailable in this window."
            )

        mcp_cfg = self._mcp_settings()
        panel = McpControlPanel(
            self.theme,
            script_path=self.mcp_host.script_path(),
            python_exe=self.mcp_host.python_exe(),
            start_adapter=self.mcp_host.start_adapter,
            stop_adapter=self.mcp_host.stop_adapter,
            find_adapter=self.mcp_host.find_adapter,
            adapter_status=self.mcp_host.adapter_status_text,
            adapter_pids=self.mcp_host.running_pids,
            health_context=self.mcp_host.health_context,
            ensure_http_adapter=self.mcp_host.ensure_http_adapter_async,
            settings=mcp_cfg,
        )
        panel.settings_changed.connect(self.mcp_host.on_settings_changed)
        self.mcp_host.panel = panel
        self.mcp_panel = panel
        return panel

    def _build_webui_tab(self) -> QWidget:
        from mcp_panel import LlamaWebUiPanel

        if self.mcp_host is None:
            return self._unavailable(
                "llama.cpp WebUI control is unavailable in this window."
            )
        panel = LlamaWebUiPanel(
            self.theme,
            settings=self._mcp_settings(),
            ensure_http_adapter=self.mcp_host.ensure_http_adapter_async,
        )
        panel.settings_changed.connect(self.mcp_host.on_settings_changed)
        self.webui_panel = panel
        return panel

    # --- persistence ---
    def _persist(self) -> None:
        try:
            self._save_config()
        except Exception as e:
            QMessageBox.warning(self, "Configure Spock AI", f"Could not save:\n{e}")

    def _on_connector_saved(self, values: Dict[str, Any], provider: str) -> None:
        self.config.update(values)
        self.config["ask_ai_provider"] = provider
        self._persist()
        try:
            apply_provider_config(self.config)
        except Exception as e:
            QMessageBox.warning(
                self, "Configure Spock AI", f"Settings saved but not applied:\n{e}"
            )
        self.refresh_active_provider()
        self.provider_changed.emit(provider)

    def _profile_applied(self, profile: Dict[str, Any]) -> None:
        if self._on_profile_applied is not None:
            self._on_profile_applied(profile)
            return
        self.config["embedding_profile"] = profile
        self.config["rag_api"] = self.embedding_panel.collect_rag_api()
        self._persist()

    def _rag_lifecycle(
        self, action: str, handler: Optional[Callable[[], None]]
    ) -> None:
        if handler is None:
            QMessageBox.information(
                self,
                action,
                "This window cannot run the RAG API server.\n\n"
                "Open Spock Navigation Station → Configure and use the same "
                "buttons there. Host, port and API key saved here are what it "
                "will bind to.",
            )
            return
        try:
            handler()
        except Exception as e:
            QMessageBox.warning(self, action, f"{action} failed:\n{e}")


class LlamaGuiCommandTab(QWidget):
    """Paste a Llama GUI Quick Launch View Command and save it for one role."""

    def __init__(self, config: Dict[str, Any], role: str, db_path: str, parent=None):
        super().__init__(parent)
        self.config = config
        self.role = "embedding" if role in ("embedding", "embed") else "chat"
        self.db_path = db_path
        from WarpCore.service_endpoints import (
            DEFAULT_CHAT_PORT,
            DEFAULT_EMBED_PORT,
            resolve_ports,
        )

        ports = resolve_ports(config)
        self.expected_port = int(
            ports["embed"] if self.role == "embedding" else ports["chat"]
            or (DEFAULT_EMBED_PORT if self.role == "embedding" else DEFAULT_CHAT_PORT)
        )
        lay = QVBoxLayout(self)
        note = QLabel(
            "In Llama GUI, open Quick Launch, choose View Command, copy the line, "
            "then Paste. Save stores it for the Launch LLama GUI button."
        )
        note.setWordWrap(True)
        lay.addWidget(note)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("llama-server.exe -m ... --port ...")
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        launch = config.get("launch") if isinstance(config.get("launch"), dict) else {}
        key = (
            "llama_gui_embed_command"
            if self.role == "embedding"
            else "llama_gui_chat_command"
        )
        self.editor.setPlainText(str(launch.get(key) or ""))
        lay.addWidget(self.editor, 1)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)
        row = QHBoxLayout()
        paste = QPushButton("Paste")
        paste.setToolTip("Replace the box with the current clipboard text")
        paste.clicked.connect(self._paste)
        save = QPushButton("Save")
        save.clicked.connect(self._save)
        clear = QPushButton("Clear")
        clear.clicked.connect(self._clear)
        row.addWidget(paste)
        row.addWidget(save)
        row.addWidget(clear)
        row.addStretch()
        lay.addLayout(row)
        self._refresh_summary()

    def _paste(self) -> None:
        clip = QApplication.clipboard()
        text = clip.text() if clip is not None else ""
        self.editor.setPlainText(text or "")
        self._refresh_summary()

    def _clear(self) -> None:
        self.editor.setPlainText("")
        self._save()

    def _save(self) -> None:
        from spock_shell.llama_gui_command import save_saved_text

        text = self.editor.toPlainText()
        try:
            save_saved_text(self.db_path, self.role, text)
        except Exception as exc:
            QMessageBox.warning(self, "LLama GUI command", f"Could not save:\n{exc}")
            return
        launch = dict(self.config.get("launch") or {})
        key = (
            "llama_gui_embed_command"
            if self.role == "embedding"
            else "llama_gui_chat_command"
        )
        launch[key] = text
        self.config["launch"] = launch
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        from spock_shell.llama_gui_command import (
            command_warnings,
            flag_value,
            parse_llama_gui_command,
            parse_port,
        )

        text = self.editor.toPlainText().strip()
        if not text:
            self.summary.setText("No command saved yet.")
            return
        try:
            argv = parse_llama_gui_command(text)
        except ValueError as exc:
            self.summary.setText(str(exc))
            return
        model = flag_value(argv, ("-m", "--model"))
        port = parse_port(argv, self.expected_port)
        lines = [f"Model: {model}", f"Port: {port}"]
        lines.extend(command_warnings(argv, self.role, self.expected_port))
        self.summary.setText("\n".join(lines))
