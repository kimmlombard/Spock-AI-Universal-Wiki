"""Shared LLM provider wiring for the Spock suite.

`make_llm_client(cfg)` is the one entry point every mini-app uses to get a chat
client configured from the app config. Provider settings are class-level on
`LLMClient`, so `apply_provider_config()` must run before constructing one.
"""

from __future__ import annotations

import os
from typing import Any

from spock_shell.paths import ensure_root_on_path

ensure_root_on_path()

from llm_client import (  # noqa: E402  (needs ROOT on sys.path first)
    LLMClient,
    normalize_openai_compat_base,
    repair_openai_compat_settings,
)

try:
    from WarpCore.service_endpoints import (  # noqa: E402
        DEFAULT_CHAT_PORT,
        resolve_ctx,
        resolve_ports,
    )
except ImportError:  # pragma: no cover
    DEFAULT_CHAT_PORT = 8081

    def resolve_ports(cfg=None):
        return {"chat": int((cfg or {}).get("llama_port") or DEFAULT_CHAT_PORT)}

    def resolve_ctx(cfg=None):
        return {"chat_max_tokens": int((cfg or {}).get("chat_max_tokens") or 2048)}


# Providers Ask AI can be pinned to. Order is the picker order.
PROVIDERS = ("LM Studio", "Ollama", "llama-server", "OpenAI-compatible")


def apply_provider_config(cfg: dict) -> None:
    """Push config into the LLMClient class-level provider settings."""
    ports = resolve_ports(cfg)
    ctx = resolve_ctx(cfg)
    LLMClient.configure_lm_studio(
        cfg.get("lm_studio_host", "localhost"),
        int(cfg.get("lm_studio_port", 1234)),
        cfg.get("lm_studio_model", ""),
    )
    LLMClient.configure_ollama(
        cfg.get("ollama_host", "localhost"),
        int(cfg.get("ollama_port", 11434)),
        cfg.get("ollama_model", ""),
    )
    LLMClient.configure_llama_server(
        cfg.get("llama_host", "localhost"),
        int(cfg.get("llama_port") or ports["chat"] or DEFAULT_CHAT_PORT),
    )
    LLMClient.configure_chat_max_tokens(int(ctx["chat_max_tokens"]))
    url, key, model = repair_openai_compat_settings(
        cfg.get("openai_compat_base_url", ""),
        cfg.get("openai_compat_api_key", ""),
        cfg.get("openai_compat_model", ""),
    )
    LLMClient.configure_openai_compat(
        normalize_openai_compat_base(url),
        key,
        model,
        n_ctx=int(cfg.get("openai_compat_n_ctx") or 131072),
        max_tokens=int(cfg.get("openai_compat_max_tokens") or 8192),
    )


def make_llm_client(cfg: dict) -> Any:
    """Build a chat client for the provider named in cfg['ask_ai_provider']."""
    apply_provider_config(cfg)
    preferred = cfg.get("ask_ai_provider") or "llama-server"
    client = LLMClient(
        prefer_lm_studio=(preferred == "LM Studio"),
        preferred_provider=preferred,
        auto_detect=True,
    )
    if preferred == "OpenAI-compatible" and cfg.get("openai_compat_model"):
        client.model = cfg["openai_compat_model"]
    elif preferred == "LM Studio" and cfg.get("lm_studio_model"):
        client.model = cfg["lm_studio_model"]
    elif preferred == "Ollama" and cfg.get("ollama_model"):
        client.model = cfg["ollama_model"]
    elif preferred == "llama-server":
        name = str(cfg.get("chat_model_name") or "").strip()
        path = str(cfg.get("chat_model_path") or "").strip()
        if not name and path:
            name = os.path.basename(path)
        LLMClient._llama_model_name = name
        client.model = client.refresh_llama_model()
    return client
