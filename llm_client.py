"""Unified chat LLM client for the Spock suite.

Extracted from the retired Spock-to-bridge monolith so every mini-app can talk
to LM Studio / Ollama / llama-server / any OpenAI-compatible endpoint without
loading a GUI. Embeddings are never served from here — those stay in
WarpCore.search, which this module only reads to avoid pointing chat at the
embeddings port.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Callable, Dict, List, Optional, Union
from urllib.parse import urlparse

TimeoutSec = Optional[int]  # None = no socket timeout (wait until canceled)

import _warpcore_path

_warpcore_path.ensure()

import WarpCore.search as _warp_search
from lm_studio_api import loaded_models as lm_loaded_models

__all__ = [
    "ASK_SYSTEM_PROMPT",
    "LLMClient",
    "embeddings_chat_collision",
    "google_adc_bearer_token",
    "normalize_openai_compat_base",
    "repair_openai_compat_settings",
]

# Grounding contract for context-backed answers. Deep Dive passes its own
# prompt; every other caller gets this one. The name clause matters: the corpus
# holds the user's own projects, which often share a name with a public package
# the model already "knows" — that resemblance is what produces confident
# answers about the wrong software.
ASK_SYSTEM_PROMPT = (
    "You answer strictly from the excerpts provided below, which were retrieved "
    "from the ship's computer knowledge base (ship_computer.db). Those excerpts "
    "are your only source of truth.\n"
    "- Do not answer from prior or outside knowledge, even when a project, "
    "library, or file shares a name with something you recognize. The corpus "
    "describes this user's own code, not a public package of the same name.\n"
    "- Do not invent APIs, file paths, commands, or usage examples. Any code you "
    "show must appear in the excerpts.\n"
    "- Cite the full file paths you drew from.\n"
    "- Ask AI retrieves short snippets, so a broad question ('how does X work') "
    "can land on excerpts too thin to answer from. When that happens, do not "
    "guess: name what is missing in a sentence or two, then close with a line "
    "beginning 'Next step:' that recommends re-running the same question with "
    "Deep Dive, which packs whole files instead of snippets. Where it would "
    "help, add that the user can set the repository root as the path filter and "
    "include or exclude extensions (.md, .txt, source types) to steer "
    "retrieval. A short answer that admits the gap and points at Deep Dive is "
    "correct; a plausible answer from memory is not."
)


def _embeddings_url() -> str:
    """Current embeddings endpoint. Read live — set_embeddings_url() rebinds it."""
    return getattr(_warp_search, "EMBEDDINGS_URL", "") or ""


def _http_netloc(url: str) -> str:
    """Return host:port for comparison (empty if unparseable)."""
    try:
        u = urlparse((url or "").strip())
    except Exception:
        return ""
    host = (u.hostname or "").lower()
    if not host:
        return ""
    port = u.port
    if port is None:
        port = 443 if (u.scheme or "").lower() == "https" else 80
    return f"{host}:{int(port)}"


def embeddings_chat_collision(chat_url: str, embeddings_url: Optional[str] = None) -> bool:
    """True when chat would hit the same host:port as the RAG embeddings server."""
    emb = embeddings_url if embeddings_url is not None else _embeddings_url()
    a, b = _http_netloc(chat_url), _http_netloc(emb)
    return bool(a and b and a == b)


def vertex_global_base(base_url: str) -> str:
    """Rewrite a regional Vertex OpenAI-compat root to the global endpoint.

    Newer publisher models (gemini-3.5-*) are only served from `locations/global`
    on the unprefixed host; a regional root 404s with "Publisher model ... was not
    found". Returns "" when the URL is not a regional Vertex root.
    """
    base = (base_url or "").strip().rstrip("/")
    if not base or "aiplatform.googleapis.com" not in base.lower():
        return ""
    match = re.match(
        r"^(https?://)([a-z0-9-]+)-aiplatform\.googleapis\.com(/.*)$", base, re.I
    )
    if not match:
        return ""
    scheme, region, path = match.groups()
    if region.lower() == "global":
        return ""
    path = re.sub(r"/locations/[^/]+", "/locations/global", path, count=1)
    return f"{scheme}aiplatform.googleapis.com{path}"


def repair_openai_compat_settings(
    base_url: str,
    api_key: str = "",
    model: str = "",
) -> tuple:
    """Fix common mis-pastes (Google Console page URLs) into a Vertex OpenAI root."""
    base = (base_url or "").strip()
    key = api_key or ""
    model_id = model or ""
    lower = base.lower()
    if "console.cloud.google.com" in lower:
        project = "gen-lang-client-0702412255"
        marker = "project="
        if marker in base:
            frag = base.split(marker, 1)[1]
            project = (
                frag.split("&")[0].split("/")[0].split("?")[0].strip() or project
            )
        # Global serves every published Gemini, including ids that regional
        # endpoints 404 on, so it is the safe root to guess from a console URL.
        base = (
            "https://aiplatform.googleapis.com/v1/projects/"
            f"{project}/locations/global/endpoints/openapi"
        )
        if _is_adc_api_key(key) or key.strip().lower() == "vertexaiapikey":
            key = "adc"
        if not model_id:
            model_id = "google/gemini-2.5-flash"
    # Vertex OpenAI-compat ids carry a publisher prefix; keep the caller's choice.
    if model_id.startswith("gemini-"):
        model_id = f"google/{model_id}"
    return base, key, model_id


def normalize_openai_compat_base(base_url: str) -> str:
    """Normalize OpenAI-compat root. Do not append /v1 onto Google Vertex/Gemini paths."""
    repaired, _key, _model = repair_openai_compat_settings(base_url)
    base = (repaired or "").strip().rstrip("/")
    if not base:
        return ""
    lower = base.lower()
    # Google Console pages sometimes end with .../v1 from our old auto-append —
    # never treat console.cloud as a real API root (handled in repair above).
    if "console.cloud.google.com" in lower:
        return ""
    if (
        lower.endswith("/v1")
        or lower.endswith("/openai")
        or lower.endswith("/endpoints/openapi")
        or "/openai/" in lower
        or "/endpoints/openapi" in lower
        or "/v1beta/" in lower
    ):
        return base
    return base + "/v1"


def _looks_like_google_openai_url(url: str) -> bool:
    lower = (url or "").lower()
    if "console.cloud.google.com" in lower:
        return False
    return "googleapis.com" in lower or "generativelanguage.googleapis.com" in lower


def _is_adc_api_key(api_key: str) -> bool:
    key = (api_key or "").strip().lower()
    return key in ("", "adc", "application-default", "vertexaiapikey", "gcloud")


def google_adc_bearer_token() -> str:
    """Fresh Application Default Credentials access token for Vertex / Google APIs."""
    try:
        from google.auth import default
        from google.auth.transport.requests import Request
    except ImportError as e:
        raise RuntimeError(
            "google-auth is required for Google Cloud ADC. "
            "Install with: pip install google-auth"
        ) from e
    creds, _project = default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    if not getattr(creds, "valid", False) or not getattr(creds, "token", None):
        creds.refresh(Request())
    elif hasattr(creds, "refresh"):
        # Keep token fresh for long Ask AI / Deep Dive sessions
        try:
            creds.refresh(Request())
        except Exception:
            if not creds.token:
                raise
    if not creds.token:
        raise RuntimeError(
            "No ADC token. Run: gcloud auth application-default login"
        )
    return str(creds.token)


def fit_llama_messages(
    messages: List[Dict[str, str]],
    *,
    n_ctx: int,
    max_tokens: int,
    chars_per_token: float = 1.8,
) -> tuple:
    """Keep a local llama-server prompt from filling n_ctx.

    ``chars_per_token`` is a dense ceiling. Qwen code is often near 2
    characters per token, so a looser estimate can report a pack as fitting
    when the rendered prompt is already the whole window. Returns a copy of
    ``messages`` and the completion cap that still fits.
    """
    try:
        ctx = int(n_ctx)
    except (TypeError, ValueError):
        ctx = 0
    try:
        out_cap = int(max_tokens)
    except (TypeError, ValueError):
        out_cap = 2048
    out_cap = max(256, out_cap)
    copied = [dict(m) for m in messages or []]
    if ctx < 1024:
        return copied, out_cap
    out_cap = min(out_cap, max(256, ctx // 8))
    room = ctx - out_cap - 64
    if room < 512:
        return copied, out_cap
    char_budget = max(1000, int(room * float(chars_per_token)))
    total = sum(len(str(m.get("content") or "")) for m in copied)
    if total <= char_budget:
        return copied, out_cap
    idx = None
    for i in range(len(copied) - 1, -1, -1):
        if copied[i].get("role") == "user":
            idx = i
            break
    if idx is None:
        return copied, out_cap
    content = str(copied[idx].get("content") or "")
    others = total - len(content)
    marker = "\n\nQuestion:"
    if marker in content:
        head, tail = content.rsplit(marker, 1)
        tail = marker + tail
    else:
        head, tail = content, ""
    note = "\n\n[Context truncated to fit the chat window]"
    allow = char_budget - others - len(tail) - len(note)
    if allow < 400:
        allow = 400
    if len(head) > allow:
        head = head[:allow].rstrip() + note
    copied[idx]["content"] = head + tail
    return copied, out_cap


class LLMClient:
    """Unified LLM client with automatic provider detection.

    Ask AI prefers LM Studio for chat by default. Ollama, llama-server and a
    custom OpenAI-compatible endpoint can be selected from Configure Spock AI.
    Embeddings still come from the Embedding Profile (never used for chat).
    """

    # Chat llama-server defaults to :8081; embeddings conventionally use :8080.
    LLAMA_SERVER_URL = "http://localhost:8081/v1/chat/completions"
    LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"
    OLLAMA_URL = "http://localhost:11434/api/chat"
    OPENAI_COMPAT_URL: Optional[str] = None
    _llama_host = "localhost"
    _llama_port = 8081
    _lm_studio_host = "localhost"
    _lm_studio_port = 1234
    _lm_studio_model: str = ""
    _ollama_host = "localhost"
    _ollama_port = 11434
    _ollama_model: str = ""
    _llama_model_name: str = ""
    _LEGACY_LLAMA_MODEL = "qwen2.5-coder-7b-instruct"
    _openai_api_key: str = ""
    _openai_model: str = ""
    _openai_n_ctx: int = 131072
    _openai_max_tokens: int = 8192
    _chat_max_tokens: int = 2048

    HEALTH_PROBES = {
        "llama-server": "http://localhost:8081/health",
        "LM Studio": "http://localhost:1234/v1/models",
        "Ollama": "http://localhost:11434/api/tags",
        "OpenAI-compatible": "",
    }

    def __init__(
        self,
        model: str = "",
        prefer_lm_studio: bool = True,
        preferred_provider: Optional[str] = None,
        auto_detect: bool = True,
    ):
        if not (model or "").strip():
            try:
                from llmfit_session_criteria import fallback_model_id

                model = fallback_model_id("chat") or "google/gemma-3-12b-it-qat-q4_0-gguf"
            except Exception:
                model = "google/gemma-3-12b-it-qat-q4_0-gguf"
        self.model = model
        self.prefer_lm_studio = prefer_lm_studio
        self.preferred_provider = preferred_provider
        self.active_url: Optional[str] = None
        self.active_provider_name: str = "None"
        self.last_error: str = ""
        self.last_was_timeout: bool = False
        if auto_detect:
            self._detect_provider()
        else:
            self.assume_preferred()

    def assume_preferred(self):
        """Set active provider from config without network I/O (fast UI open)."""
        preferred = self.preferred_provider
        if not preferred:
            preferred = "LM Studio" if self.prefer_lm_studio else "llama-server"
        for name, chat_url in self._provider_candidates():
            if name == preferred and chat_url:
                self.active_url = chat_url
                self.active_provider_name = name
                self._adopt_provider_model(name)
                return
        self.active_url = None
        self.active_provider_name = preferred or "None"

    def _adopt_provider_model(self, name: str) -> None:
        """Use the model id configured for the provider we just selected."""
        if name == "LM Studio" and self._lm_studio_model:
            self.model = self._lm_studio_model
        elif name == "Ollama" and self._ollama_model:
            self.model = self._ollama_model
        elif name == "OpenAI-compatible" and self._openai_model:
            self.model = self._openai_model

    @classmethod
    def configure_llama_port(cls, port: int):
        """Point llama-server chat/health URLs at the launched port (chat only)."""
        cls.configure_llama_server(cls._llama_host or "localhost", port)

    @classmethod
    def configure_llama_server(cls, host: str = "localhost", port: int = 8081):
        """Point Ask AI at a llamaccp / llama-server OpenAI-compatible API."""
        host = (host or "localhost").strip() or "localhost"
        port = int(port)
        # Never bind chat to the embeddings host:port — use conventional chat port.
        emb_net = _http_netloc(_embeddings_url())
        if emb_net and emb_net == f"{host.lower()}:{port}":
            port = 8081 if port != 8081 else 8080
        cls._llama_host = host
        cls._llama_port = port
        base = f"http://{host}:{port}"
        cls.LLAMA_SERVER_URL = f"{base}/v1/chat/completions"
        cls.HEALTH_PROBES["llama-server"] = f"{base}/health"

    @classmethod
    def configure_chat_max_tokens(cls, max_tokens: int = 2048) -> None:
        """Set completion length for local providers (LM Studio / Ollama / llama-server)."""
        try:
            n = int(max_tokens)
        except (TypeError, ValueError):
            n = 2048
        cls._chat_max_tokens = max(256, min(65536, n))

    @classmethod
    def configure_lm_studio(
        cls,
        host: str = "localhost",
        port: int = 1234,
        model: str = "",
    ):
        """Point Ask AI chat at LM Studio OpenAI-compatible API."""
        host = (host or "localhost").strip() or "localhost"
        port = int(port)
        cls._lm_studio_host = host
        cls._lm_studio_port = port
        base = f"http://{host}:{port}"
        cls.LM_STUDIO_URL = f"{base}/v1/chat/completions"
        cls.HEALTH_PROBES["LM Studio"] = f"{base}/v1/models"
        if model is not None and str(model).strip():
            cls._lm_studio_model = str(model).strip()

    @classmethod
    def configure_ollama(
        cls,
        host: str = "localhost",
        port: int = 11434,
        model: str = "",
    ):
        """Point Ask AI chat at an Ollama daemon (native /api/chat protocol)."""
        host = (host or "localhost").strip() or "localhost"
        try:
            port = int(port or 11434)
        except (TypeError, ValueError):
            port = 11434
        cls._ollama_host = host
        cls._ollama_port = port
        base = f"http://{host}:{port}"
        cls.OLLAMA_URL = f"{base}/api/chat"
        cls.HEALTH_PROBES["Ollama"] = f"{base}/api/tags"
        cls._ollama_model = str(model or "").strip()

    @classmethod
    def configure_openai_compat(
        cls,
        base_url: str,
        api_key: str = "",
        model: str = "",
        n_ctx: int = 131072,
        max_tokens: int = 8192,
    ):
        """Point Ask AI at any OpenAI-compatible /v1 endpoint."""
        repaired_url, repaired_key, repaired_model = repair_openai_compat_settings(
            base_url, api_key, model
        )
        base = normalize_openai_compat_base(repaired_url)
        if not base:
            cls.OPENAI_COMPAT_URL = None
            cls.HEALTH_PROBES["OpenAI-compatible"] = ""
            cls._openai_api_key = ""
            cls._openai_model = ""
            return
        cls.OPENAI_COMPAT_URL = f"{base}/chat/completions"
        cls.HEALTH_PROBES["OpenAI-compatible"] = f"{base}/models"
        cls._openai_api_key = repaired_key or ""
        cls._openai_model = repaired_model or ""
        try:
            cls._openai_n_ctx = max(2048, int(n_ctx or 131072))
        except (TypeError, ValueError):
            cls._openai_n_ctx = 131072
        try:
            cls._openai_max_tokens = max(256, int(max_tokens or 8192))
        except (TypeError, ValueError):
            cls._openai_max_tokens = 8192
        # Do not copy this onto _chat_max_tokens. Local llama-server keeps
        # chat_max_tokens (typically 2048). A Vertex budget of 13k–65k on a
        # 16k window makes the model generate until it loops.

    def _openai_compat_auth_headers(self) -> Dict[str, str]:
        """Bearer for OpenAI-compat: static key, or Google ADC when configured."""
        headers: Dict[str, str] = {}
        key = self._openai_api_key or ""
        url = self.active_url or self.OPENAI_COMPAT_URL or ""
        use_adc = _is_adc_api_key(key) and _looks_like_google_openai_url(url)
        if use_adc:
            try:
                headers["Authorization"] = f"Bearer {google_adc_bearer_token()}"
            except Exception as e:
                self.last_error = f"Google ADC auth failed: {e}"
            return headers
        if key and not _is_adc_api_key(key):
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def refresh(self):
        """Re-detect provider (e.g. after Launch / Stop / LM Studio connect)."""
        self._detect_provider()

    def _provider_candidates(self) -> List[tuple]:
        preferred = self.preferred_provider
        if not preferred:
            preferred = "LM Studio" if self.prefer_lm_studio else "llama-server"

        # OpenAI-compatible is opt-in only. Config often points it at the Spock
        # RAG API (:8090), which itself calls LLMClient — using it as an
        # automatic fallback causes recursive RAG → ConnectionAbortedError.
        all_providers: List[tuple] = []
        if preferred == "OpenAI-compatible" and self.OPENAI_COMPAT_URL:
            all_providers.append(("OpenAI-compatible", self.OPENAI_COMPAT_URL))

        # Prefer real chat backends for Ask AI / Deep Dive
        all_providers.extend(
            [
                ("LM Studio", self.LM_STUDIO_URL),
                ("llama-server", self.LLAMA_SERVER_URL),
                ("Ollama", self.OLLAMA_URL),
            ]
        )
        # If configured llama port collides with embeddings, also try chat :8081.
        llama_url = self.LLAMA_SERVER_URL
        if embeddings_chat_collision(llama_url):
            host = self._llama_host or "localhost"
            alt_port = 8081 if self._llama_port != 8081 else 8080
            alt = f"http://{host}:{alt_port}/v1/chat/completions"
            if alt != llama_url:
                all_providers.append(("llama-server", alt))
        elif self._llama_port not in (8081,) and not embeddings_chat_collision(
            f"http://{self._llama_host or 'localhost'}:8081/v1/chat/completions"
        ):
            # Prefer discovering a live instruct server on :8081 when config
            # still points at a non-chat port (legacy default was :8080).
            alt = f"http://{self._llama_host or 'localhost'}:8081/v1/chat/completions"
            if alt != llama_url:
                all_providers.append(("llama-server", alt))

        ordered = [p for p in all_providers if p[0] == preferred]
        # Stable fallback order after preferred: llama-server, LM Studio, Ollama
        fallback_order = ("llama-server", "LM Studio", "Ollama", "OpenAI-compatible")
        for name in fallback_order:
            ordered.extend(p for p in all_providers if p[0] == name and p[0] != preferred)
        return ordered

    def _detect_provider(self):
        """Auto-detect available LLM provider (preferred first)."""
        seen_urls = set()
        for name, chat_url in self._provider_candidates():
            if not chat_url or chat_url in seen_urls:
                continue
            seen_urls.add(chat_url)
            # Embeddings llama-server often answers /health and even tiny chats,
            # but with a tiny n_ctx — never use it for Ask AI.
            if name == "llama-server" and embeddings_chat_collision(chat_url):
                continue
            # Never chat through the Spock RAG gateway unless explicitly preferred
            # (already gated in candidates); belt-and-suspenders skip :8090.
            if name != "OpenAI-compatible" and self._looks_like_spock_rag_url(chat_url):
                continue
            health_url = self.HEALTH_PROBES.get(name) or ""
            if name == "llama-server":
                # Health probe may still point at the configured (wrong) port;
                # derive from this candidate URL.
                base = chat_url
                if base.endswith("/v1/chat/completions"):
                    health_url = base[: -len("/v1/chat/completions")] + "/health"
                elif base.endswith("/chat/completions"):
                    health_url = base[: -len("/chat/completions")] + "/health"
            if name == "OpenAI-compatible" and _looks_like_google_openai_url(chat_url):
                # Vertex OpenAI-compat often 404s GET /models; validate ADC / key instead.
                if not self._google_openai_ready(chat_url):
                    continue
            elif health_url and not self._ping(health_url):
                continue
            elif not health_url and name == "OpenAI-compatible":
                continue
            self.active_url = chat_url
            self.active_provider_name = name
            if name == "llama-server":
                # Keep class URLs aligned with the live chat port we selected.
                try:
                    u = urlparse(chat_url)
                    if u.hostname and u.port:
                        type(self).configure_llama_server(u.hostname, int(u.port))
                except Exception:
                    pass
            self._adopt_provider_model(name)
            return
        self.active_url = None
        self.active_provider_name = "None"

    def _google_openai_ready(self, chat_url: str) -> bool:
        """True when Google Vertex/Gemini OpenAI-compat can authenticate."""
        try:
            if _is_adc_api_key(self._openai_api_key):
                google_adc_bearer_token()
                return True
            # Static API key (AI Studio / Gemini developer key)
            return bool((self._openai_api_key or "").strip())
        except Exception as e:
            self.last_error = f"Google ADC auth failed: {e}"
            return False

    @staticmethod
    def _looks_like_spock_rag_url(url: str) -> bool:
        try:
            u = urlparse(url or "")
        except Exception:
            return False
        if u.port == 8090:
            return True
        path = (u.path or "").rstrip("/")
        return path.endswith("/v1/chat/completions") and u.port in (8090,)

    def _ping(self, url: str, timeout: float = 0.4) -> bool:
        try:
            headers = {}
            if url == self.HEALTH_PROBES.get("OpenAI-compatible"):
                if _looks_like_google_openai_url(url) and _is_adc_api_key(
                    self._openai_api_key
                ):
                    headers["Authorization"] = f"Bearer {google_adc_bearer_token()}"
                    timeout = max(timeout, 8.0)
                elif self._openai_api_key and not _is_adc_api_key(self._openai_api_key):
                    headers["Authorization"] = f"Bearer {self._openai_api_key}"
            req = urllib.request.Request(url, headers=headers)
            urllib.request.urlopen(req, timeout=timeout)
            return True
        except Exception:
            return False

    @property
    def is_available(self) -> bool:
        return self.active_url is not None

    @property
    def active_provider(self) -> str:
        return self.active_provider_name

    def _mark_timeout(self, timeout: TimeoutSec) -> None:
        self.last_was_timeout = True
        if timeout is None or int(timeout) <= 0:
            waited = "an unlimited wait"
        else:
            waited = f"{int(timeout)}s"
        self.last_error = (
            f"Timed out after {waited} waiting for "
            f"{self.active_provider_name} ({self.active_url}). "
            "The local model may still be generating (slow CPU/GPU offload)."
        )

    @staticmethod
    def _is_timeout_exc(exc: BaseException) -> bool:
        msg = str(exc).lower()
        name = type(exc).__name__.lower()
        return (
            "timed out" in msg
            or "timeout" in name
            or isinstance(exc, TimeoutError)
        )

    @staticmethod
    def _urlopen_timeout(timeout: TimeoutSec):
        """urllib: None = block forever; <=0 treated as None."""
        if timeout is None:
            return None
        try:
            sec = int(timeout)
        except (TypeError, ValueError):
            return 300
        return None if sec <= 0 else sec

    def chat(self, messages: List[Dict[str, str]], timeout: TimeoutSec = 300) -> Optional[str]:
        """Send chat completion request to active provider."""
        self.last_error = ""
        self.last_was_timeout = False
        if not self.active_url:
            self._detect_provider()
        if not self.active_url:
            self.last_error = (
                "No chat provider reachable. "
                "Open Configure Spock AI and connect to LM Studio / Ollama / "
                "llamaccp (use the chat port, not embeddings)."
            )
            return None

        if self.active_provider_name == "Ollama":
            return self._chat_ollama(messages, timeout)
        return self._chat_openai_compat(messages, timeout)

    def _resolve_chat_model(self) -> str:
        """Pick a model id the active provider will accept."""
        if self.active_provider_name == "OpenAI-compatible" and self._openai_model:
            return self._openai_model
        if self.active_provider_name == "Ollama" and self._ollama_model:
            return self._ollama_model
        if self.active_provider_name == "llama-server":
            return self.refresh_llama_model()
        if self.active_provider_name == "LM Studio":
            if self._lm_studio_model:
                return self._lm_studio_model
            # Prefer whatever is already loaded in LM Studio over stale defaults
            try:
                loaded = lm_loaded_models(
                    self._lm_studio_host, self._lm_studio_port, ""
                )
                for entry in loaded:
                    if str(entry.get("type") or "llm") == "embedding":
                        continue
                    key = str(entry.get("key") or entry.get("instance_id") or "")
                    if key:
                        type(self)._lm_studio_model = key
                        self.model = key
                        return key
            except Exception:
                pass
        return self.model

    def _extract_chat_text(self, data: dict) -> Optional[str]:
        msg = (data.get("choices") or [{}])[0].get("message") or {}
        text = (msg.get("content") or "").strip()
        if text:
            return text
        # Thinking models may leave content empty until late; prefer final
        # content, else last non-empty reasoning chunk as a weak fallback.
        reasoning = (msg.get("reasoning_content") or msg.get("reasoning") or "").strip()
        if reasoning:
            # Prefer a short trailing answer if the model embedded one
            lines = [ln.strip() for ln in reasoning.splitlines() if ln.strip()]
            for ln in reversed(lines[-8:]):
                if ln.lower().startswith(("answer:", "final:", "result:")):
                    return ln.split(":", 1)[-1].strip() or ln
            return reasoning
        return None

    def refresh_llama_model(self) -> str:
        """Model id Ask AI should show and send for the local chat server.

        The old built-in default was ``qwen2.5-coder-7b-instruct``. The saved
        chat GGUF (``app.chat_model_name``) replaces it, and a running
        llama-server ``/props`` path wins when one model is already loaded.
        """
        loaded = self._llama_loaded_model_name()
        if loaded:
            self.model = loaded
            return loaded
        configured = str(type(self)._llama_model_name or "").strip()
        if configured:
            self.model = configured
            return configured
        if self.model == self._LEGACY_LLAMA_MODEL:
            self.model = ""
        return self.model

    def _llama_loaded_model_name(self) -> str:
        base = f"http://{type(self)._llama_host or 'localhost'}:{int(type(self)._llama_port or 8081)}"
        try:
            req = urllib.request.Request(base + "/props")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception:
            return ""
        if not isinstance(data, dict):
            return ""
        path = str(data.get("model_path") or data.get("model") or "").strip()
        if not path:
            settings = data.get("default_generation_settings") or {}
            if isinstance(settings, dict):
                path = str(settings.get("model") or "").strip()
        if not path or path in (self._LEGACY_LLAMA_MODEL, "spock-ships-computer"):
            return ""
        return os.path.basename(path.replace("\\", "/"))

    def _cached_llama_n_ctx(self) -> int:
        """Live slot n_ctx from llama-server /props. 0 if it cannot be read."""
        cached = int(getattr(type(self), "_llama_n_ctx_cache", 0) or 0)
        if cached >= 1024:
            return cached
        base = (self.active_url or "").rstrip("/")
        for suffix in ("/v1/chat/completions", "/chat/completions"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        if not base:
            return 0
        try:
            req = urllib.request.Request(base + "/props")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            n_ctx = int(
                (data.get("default_generation_settings") or {}).get("n_ctx") or 0
            )
        except Exception:
            return 0
        if n_ctx >= 1024:
            type(self)._llama_n_ctx_cache = n_ctx
        return n_ctx

    def _chat_openai_compat(
        self, messages: List[Dict[str, str]], timeout: TimeoutSec
    ) -> Optional[str]:
        model = self._resolve_chat_model()
        max_tokens = int(getattr(type(self), "_chat_max_tokens", 2048) or 2048)
        if self.active_provider_name == "OpenAI-compatible":
            max_tokens = int(getattr(type(self), "_openai_max_tokens", max_tokens) or max_tokens)
        elif self.active_provider_name == "llama-server":
            messages, max_tokens = fit_llama_messages(
                messages,
                n_ctx=self._cached_llama_n_ctx(),
                max_tokens=max_tokens,
            )
        payload_obj = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": max(256, max_tokens),
            # Helps llama-server Qwen3; LM Studio / Vertex may ignore it.
            "chat_template_kwargs": {"enable_thinking": False},
        }
        headers = {"Content-Type": "application/json"}
        if self.active_provider_name == "OpenAI-compatible":
            auth = self._openai_compat_auth_headers()
            headers.update(auth)
            url = self.active_url or ""
            if (
                _looks_like_google_openai_url(url)
                and _is_adc_api_key(self._openai_api_key)
                and "Authorization" not in auth
            ):
                return None
        sock_timeout = self._urlopen_timeout(timeout)

        def _post(body: dict) -> dict:
            req = urllib.request.Request(
                self.active_url,
                data=json.dumps(body).encode(),
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=sock_timeout) as resp:
                return json.loads(resp.read().decode())

        try:
            data = _post(payload_obj)
            text = self._extract_chat_text(data)
            if text:
                return text
            self.last_error = (
                f"{self.active_provider_name} returned empty content "
                f"(model={model}). Thinking models may need a higher max_tokens."
            )
            return None
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            # LM Studio rejects stale/default model ids even when a model is loaded.
            if (
                e.code == 400
                and self.active_provider_name == "LM Studio"
                and "invalid model" in (body or "").lower()
            ):
                try:
                    loaded = lm_loaded_models(
                        self._lm_studio_host, self._lm_studio_port, ""
                    )
                    alt = ""
                    for entry in loaded:
                        if str(entry.get("type") or "llm") == "embedding":
                            continue
                        alt = str(entry.get("key") or entry.get("instance_id") or "")
                        if alt:
                            break
                    if alt and alt != model:
                        type(self)._lm_studio_model = alt
                        self.model = alt
                        payload_obj["model"] = alt
                        data = _post(payload_obj)
                        text = self._extract_chat_text(data)
                        if text:
                            return text
                except Exception as e2:
                    self.last_error = (
                        f"HTTP {e.code} from LM Studio ({self.active_url}): "
                        f"{body or e.reason}; retry with loaded model failed: {e2}"
                    )
                    return None
            # Retry once without chat_template_kwargs if server rejects unknown field
            if e.code == 400 and "chat_template_kwargs" in (body or "").lower():
                try:
                    payload_obj.pop("chat_template_kwargs", None)
                    data = _post(payload_obj)
                    return self._extract_chat_text(data)
                except Exception as e2:
                    self.last_error = (
                        f"HTTP {e.code} from {self.active_provider_name} "
                        f"({self.active_url}): {body or e.reason}; retry: {e2}"
                    )
                    return None
            self.last_error = (
                f"HTTP {e.code} from {self.active_provider_name} "
                f"({self.active_url}): {body or e.reason}"
            )
            body_l = (body or "").lower()
            if "no models loaded" in body_l or "lms load" in body_l:
                self.last_error += (
                    " — tip: that response is LM Studio with no model loaded. "
                    "It is bound to 127.0.0.1 on this port, so localhost never "
                    "reaches llama-server on 0.0.0.0. Quit LM Studio's local "
                    "server or move it off this port, then retry."
                )
            elif (
                e.code in (400, 404, 501)
                and self.active_provider_name == "llama-server"
            ):
                self.last_error += (
                    " — tip: chat must use the instruct llama-server port "
                    "(e.g. :8081), not the embeddings port (:8080)."
                )
            elif (
                e.code == 400
                and self.active_provider_name == "LM Studio"
                and "invalid model" in (body or "").lower()
            ):
                self.last_error += (
                    " — tip: Status → LM Studio → List Models → select the "
                    "loaded chat model → Load Selected Model (sets Ask AI model id)."
                )
            return None
        except Exception as e:
            if self._is_timeout_exc(e):
                self._mark_timeout(timeout)
                return None
            self.last_error = (
                f"{type(e).__name__} talking to {self.active_provider_name} "
                f"({self.active_url}): {e}"
            )
            return None

    def _chat_ollama(
        self, messages: List[Dict[str, str]], timeout: TimeoutSec
    ) -> Optional[str]:
        payload = json.dumps({
            "model": self._resolve_chat_model(),
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.1},
        }).encode()
        try:
            req = urllib.request.Request(
                self.active_url or self.OLLAMA_URL,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(
                req, timeout=self._urlopen_timeout(timeout)
            ) as resp:
                data = json.loads(resp.read().decode())
                return (data.get("message") or {}).get("content")
        except Exception as e:
            if self._is_timeout_exc(e):
                self._mark_timeout(timeout)
                return None
            self.last_error = f"Ollama error: {e}"
            return None

    def chat_stream(self, messages: List[Dict[str, str]], timeout: TimeoutSec = 300):
        """Yield content tokens from the active provider (OpenAI-compat / Ollama)."""
        self.last_error = ""
        self.last_was_timeout = False
        if not self.active_url:
            self._detect_provider()
        if not self.active_url:
            self.last_error = (
                "No chat provider reachable. "
                "Open Configure Spock AI and connect to LM Studio / Ollama / "
                "llamaccp (use the chat port, not embeddings)."
            )
            return
        if self.active_provider_name == "Ollama":
            yield from self._chat_stream_ollama(messages, timeout)
            return
        yield from self._chat_stream_openai_compat(messages, timeout)

    def _chat_stream_openai_compat(
        self, messages: List[Dict[str, str]], timeout: TimeoutSec
    ):
        model = self._resolve_chat_model()
        max_tokens = int(getattr(type(self), "_chat_max_tokens", 2048) or 2048)
        if self.active_provider_name == "OpenAI-compatible":
            max_tokens = int(
                getattr(type(self), "_openai_max_tokens", max_tokens) or max_tokens
            )
        elif self.active_provider_name == "llama-server":
            messages, max_tokens = fit_llama_messages(
                messages,
                n_ctx=self._cached_llama_n_ctx(),
                max_tokens=max_tokens,
            )
        payload_obj = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": max(256, max_tokens),
            "stream": True,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        headers = {"Content-Type": "application/json"}
        if self.active_provider_name == "OpenAI-compatible":
            headers.update(self._openai_compat_auth_headers())
        sock_timeout = self._urlopen_timeout(timeout)

        def _iter(body: dict):
            req = urllib.request.Request(
                self.active_url,
                data=json.dumps(body).encode(),
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=sock_timeout) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                    text = delta.get("content") or ""
                    if text:
                        yield text

        try:
            yield from _iter(payload_obj)
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            if e.code == 400 and "chat_template_kwargs" in (body or "").lower():
                try:
                    payload_obj.pop("chat_template_kwargs", None)
                    yield from _iter(payload_obj)
                    return
                except Exception as e2:
                    self.last_error = (
                        f"HTTP {e.code} from {self.active_provider_name} "
                        f"({self.active_url}): {body or e.reason}; retry: {e2}"
                    )
                    return
            # Non-streaming fallback when the server rejects stream=True
            if e.code in (400, 404, 501):
                text = self.chat(messages, timeout=timeout)
                if text:
                    yield text
                return
            self.last_error = (
                f"HTTP {e.code} from {self.active_provider_name} "
                f"({self.active_url}): {body or e.reason}"
            )
        except Exception as e:
            if self._is_timeout_exc(e):
                self._mark_timeout(timeout)
                return
            self.last_error = (
                f"Error streaming from {self.active_provider_name} "
                f"({self.active_url}): {e}"
            )

    def _chat_stream_ollama(self, messages: List[Dict[str, str]], timeout: TimeoutSec):
        payload = json.dumps(
            {
                "model": self._resolve_chat_model(),
                "messages": messages,
                "stream": True,
                "options": {"temperature": 0.1},
            }
        ).encode()
        try:
            req = urllib.request.Request(
                self.active_url or self.OLLAMA_URL,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(
                req, timeout=self._urlopen_timeout(timeout)
            ) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    text = (chunk.get("message") or {}).get("content") or ""
                    if text:
                        yield text
                    if chunk.get("done"):
                        break
        except Exception as e:
            if self._is_timeout_exc(e):
                self._mark_timeout(timeout)
                return
            self.last_error = f"Ollama stream error: {e}"
            text = self._chat_ollama(messages, timeout)
            if text:
                yield text

    def ask_with_context(
        self,
        question: str,
        context: str,
        system_prompt: str = "",
        history: Optional[List[Dict[str, str]]] = None,
        timeout: TimeoutSec = 300,
        on_timeout_continue: Optional[Callable[[str], Union[bool, TimeoutSec]]] = None,
    ) -> str:
        """Ask a question with document context (optional prior chat turns).

        If ``on_timeout_continue`` is set and a request times out, it is called
        with the timeout detail. Return values:
        - ``None`` / ``False`` — stop and surface the error
        - ``True`` — retry with the same timeout
        - ``int > 0`` — retry with that many seconds
        - ``0`` / negative — retry with no socket timeout (until canceled)
        """
        messages = self._context_messages(question, context, system_prompt, history)
        while True:
            text = self.chat(messages, timeout=timeout)
            if text:
                return text
            if not (self.last_was_timeout and callable(on_timeout_continue)):
                detail = self.last_error or "No details available."
                return f"Could not reach LLM provider.\n{detail}"
            decision = on_timeout_continue(self.last_error or "")
            if decision is False or decision is None:
                detail = self.last_error or "No details available."
                return f"Could not reach LLM provider.\n{detail}"
            if decision is True:
                continue
            try:
                nxt = int(decision)
            except (TypeError, ValueError):
                continue
            timeout = None if nxt <= 0 else nxt

    def ask_with_context_stream(
        self,
        question: str,
        context: str,
        system_prompt: str = "",
        history: Optional[List[Dict[str, str]]] = None,
        timeout: TimeoutSec = 300,
        on_timeout_continue: Optional[Callable[[str], Union[bool, TimeoutSec]]] = None,
    ):
        """Yield tokens for a context-grounded answer.

        On a timeout with no tokens received, ``on_timeout_continue`` may approve
        another attempt (same return semantics as ``ask_with_context``).
        """
        messages = self._context_messages(question, context, system_prompt, history)
        while True:
            yielded = False
            for tok in self.chat_stream(messages, timeout=timeout):
                yielded = True
                yield tok
            if yielded:
                return
            if not (self.last_was_timeout and callable(on_timeout_continue)):
                if self.last_error:
                    yield f"Could not reach LLM provider.\n{self.last_error}"
                return
            decision = on_timeout_continue(self.last_error or "")
            if decision is False or decision is None:
                if self.last_error:
                    yield f"Could not reach LLM provider.\n{self.last_error}"
                return
            if decision is True:
                continue
            try:
                nxt = int(decision)
            except (TypeError, ValueError):
                continue
            timeout = None if nxt <= 0 else nxt
            continue

    @staticmethod
    def _context_messages(
        question: str,
        context: str,
        system_prompt: str = "",
        history: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, str]]:
        if not system_prompt:
            system_prompt = ASK_SYSTEM_PROMPT
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]
        for turn in history or []:
            role = (turn.get("role") or "").strip()
            content = (turn.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append(
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {question}",
            }
        )
        return messages
