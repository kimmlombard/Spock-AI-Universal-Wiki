"""WarpCore: single source of truth for Spock default config + merge functions.

Absorbs DEFAULT_APP_CONFIG / DEFAULT_SCAN_CONFIG plus the merge helpers that
previously lived in model_selector_core, mcp_panel, uieg_paths, and
web_search_clients so every consumer (GUI, wizard, subprocess, CLI) shares one
definition of what a valid config looks like.

No PyQt imports.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from WarpCore.service_endpoints import (
    DEFAULT_CHAT_PORT,
    DEFAULT_CTX,
    DEFAULT_DOCS_PORT,
    DEFAULT_EMBED_PORT,
    DEFAULT_MCP_PORT,
    DEFAULT_MCP_WEBUI_PORT,
    DEFAULT_PORTS,
    DEFAULT_RAG_PORT,
    resolve_llama_server_path,
    resolve_spock_root,
)

SPOCK_ROOT = resolve_spock_root()

_LLAMA_PATH, _LLAMA_NOTE = resolve_llama_server_path()
DEFAULT_LLAMA_SERVER = _LLAMA_PATH
# Kept for diagnostics / bringup messages (may note a missing binary).
DEFAULT_LLAMA_SERVER_NOTE = _LLAMA_NOTE

# ── Embedding profile ────────────────────────────────────────────────────
DEFAULT_EMBEDDING_PROFILE: Dict[str, Any] = {
    "embeddings_url": f"http://localhost:{DEFAULT_EMBED_PORT}/embeddings",
    # Default matches shipping EmbeddingGemma; Launch/Apply still overwrite from probe.
    "embeddings_dim": 768,
    "truncate_chars": 1500,
    "batch_chunk": 32,
    "batch_workers": 8,
    "llama_batch": 512,
    "llama_ubatch": 512,
    "model_path": "",
    "model_id": "",
    "probe_on_apply": True,
}


def merge_embedding_profile(raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    profile = dict(DEFAULT_EMBEDDING_PROFILE)
    if raw:
        profile.update({k: v for k, v in raw.items() if k in profile})
    return profile


# ── Launch flags the user pins (Spock_Console app.launch.*) ──────────────
# Only knobs that mean the same thing on any machine live here. GPU policy,
# tensor-split, split-mode, -ncmoe and -c are hardware shape and belong to the
# host recipe, which is versioned and re-proposed when the hardware changes.
_KV_CACHE_TYPES = (
    "",
    "f32",
    "f16",
    "bf16",
    "q8_0",
    "q4_0",
    "q4_1",
    "iq4_nl",
    "q5_0",
    "q5_1",
)

_REASONING_VALUES = ("off", "auto", "on")

DEFAULT_LAUNCH_SETTINGS: Dict[str, Any] = {
    # "-1" asks llmfit for a VRAM-safe layer count at launch; a number pins
    # -ngl and skips that check ("99" = offload every layer).
    "ngl": "-1",
    # llama-server -np for the embedding server (slots).
    "embed_np": 1,
    # Chat server only. Embedding launches ignore these.
    "flash_attn": True,
    "cache_type_k": "q8_0",
    "cache_type_v": "q8_0",
    # llama-server --reasoning. "off" disables thinking on every chat launch.
    "reasoning": "off",
    # Raw Llama GUI "View Command" lines. Empty means the flag builder runs.
    "llama_gui_embed_command": "",
    "llama_gui_chat_command": "",
}


def clamp_n_cpu_moe(value: Any) -> int:
    """llama-server -ncmoe: 0 omits the flag, 1–999 is the layer count."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    if n < 0:
        return 0
    if n > 999:
        return 999
    return n


def chat_moe_reasoning_argv(
    role: Optional[str],
    n_cpu_moe: Any = 0,
    reasoning: Any = "",
) -> List[str]:
    """Chat-only ``-ncmoe`` and ``--reasoning``. Embedding servers omit both.

    ``n_cpu_moe`` of 0 and a blank reasoning value omit that flag. Reasoning
    is passed only for ``off``, ``auto``, or ``on``.
    """
    if (role or "").lower() in ("embedding", "embed"):
        return []
    args: List[str] = []
    n = clamp_n_cpu_moe(n_cpu_moe)
    if n > 0:
        args.extend(["-ncmoe", str(n)])
    text = str(reasoning or "").strip().lower()
    if text in _REASONING_VALUES:
        args.extend(["--reasoning", text])
    return args


def merge_launch_settings(raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Pinned Launch flags (DB: app.launch.*), clamped to what llama-server takes."""
    out = dict(DEFAULT_LAUNCH_SETTINGS)
    if not isinstance(raw, dict):
        return out
    ngl = raw.get("ngl")
    if ngl is not None:
        text = str(ngl).strip().lower()
        if text in ("", "auto"):
            text = "-1"
        if text.lstrip("-").isdigit() and -1 <= int(text) <= 999:
            out["ngl"] = str(int(text))
    np_val = raw.get("embed_np")
    if np_val is not None:
        try:
            out["embed_np"] = max(1, min(16, int(np_val)))
        except (TypeError, ValueError):
            pass
    if "flash_attn" in raw and raw.get("flash_attn") is not None:
        flag = raw.get("flash_attn")
        if isinstance(flag, str):
            out["flash_attn"] = flag.strip().lower() in ("1", "true", "yes", "on")
        else:
            out["flash_attn"] = bool(flag)
    for key in ("cache_type_k", "cache_type_v"):
        if key not in raw or raw.get(key) is None:
            continue
        text = str(raw.get(key) or "").strip().lower()
        if text in _KV_CACHE_TYPES:
            out[key] = text
    if "reasoning" in raw and raw.get("reasoning") is not None:
        text = str(raw.get("reasoning") or "").strip().lower()
        out["reasoning"] = text if text in _REASONING_VALUES else "off"
    for key in ("llama_gui_embed_command", "llama_gui_chat_command"):
        if key not in raw or raw.get(key) is None:
            continue
        out[key] = str(raw.get(key) or "")
    return out


# ── MCP settings ─────────────────────────────────────────────────────────
DEFAULT_MCP_SETTINGS: Dict[str, Any] = {
    "transport": "streamable-http",
    "http_host": "127.0.0.1",
    "http_port": DEFAULT_MCP_PORT,
    "llama_server_path": DEFAULT_LLAMA_SERVER,
    "webui_host": "127.0.0.1",
    "webui_port": DEFAULT_MCP_WEBUI_PORT,
    "adapter_autostart": False,
    "webui_autostart": False,
}


def merge_mcp_settings(raw: Optional[dict] = None) -> Dict[str, Any]:
    out = dict(DEFAULT_MCP_SETTINGS)
    if isinstance(raw, dict):
        out.update({k: v for k, v in raw.items() if v is not None})
    try:
        out["http_port"] = max(
            1024, min(int(out.get("http_port") or DEFAULT_MCP_PORT), 65535)
        )
    except (TypeError, ValueError):
        out["http_port"] = DEFAULT_MCP_PORT
    try:
        out["webui_port"] = max(
            1024, min(int(out.get("webui_port") or DEFAULT_MCP_WEBUI_PORT), 65535)
        )
    except (TypeError, ValueError):
        out["webui_port"] = DEFAULT_MCP_WEBUI_PORT
    out["http_host"] = str(out.get("http_host") or "127.0.0.1").strip() or "127.0.0.1"
    out["webui_host"] = str(out.get("webui_host") or "127.0.0.1").strip() or "127.0.0.1"
    out["llama_server_path"] = str(
        out.get("llama_server_path") or DEFAULT_LLAMA_SERVER
    ).strip()
    transport = str(out.get("transport") or "streamable-http").strip().lower()
    if transport not in ("stdio", "streamable-http", "sse"):
        transport = "streamable-http"
    out["transport"] = transport
    out["adapter_autostart"] = bool(out.get("adapter_autostart"))
    out["webui_autostart"] = bool(out.get("webui_autostart"))
    return {k: out[k] for k in DEFAULT_MCP_SETTINGS}


# ── UIEG capture paths ───────────────────────────────────────────────────
DEFAULT_CAPTURE_FOLDER = str(SPOCK_ROOT / "captured_files")
DEFAULT_DB_PATH = str(SPOCK_ROOT / "uieg_capture.db")
DEFAULT_PROMOTED_FOLDER = str(SPOCK_ROOT / "promoted_research")


def merge_uieg_config(raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = {
        "capture_folder": DEFAULT_CAPTURE_FOLDER,
        "database_path": DEFAULT_DB_PATH,
        "promoted_folder": DEFAULT_PROMOTED_FOLDER,
        "crawl_link_limit": 10,
        "crawl_timeout_sec": 15,
        "repo_extensions": [".md", ".py", ".txt", ".rst", ".json", ".toml", ".yml", ".yaml"],
    }
    if raw:
        for k, v in raw.items():
            if k in cfg and v is not None:
                cfg[k] = v
    for path_key in ("capture_folder", "database_path", "promoted_folder"):
        p = cfg[path_key]
        if not os.path.isabs(p):
            cfg[path_key] = os.path.join(str(SPOCK_ROOT), p)
    return cfg


# ── Search (GitHub / Brave) tokens ──────────────────────────────────────
def merge_search_config(raw: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    cfg = {"github_token": "", "brave_api_key": ""}
    if raw:
        for k in cfg:
            if raw.get(k) is not None:
                cfg[k] = str(raw.get(k) or "")
    env_gh = os.environ.get("GITHUB_TOKEN", "").strip()
    env_brave = os.environ.get("BRAVE_API_KEY", "").strip()
    if env_gh:
        cfg["github_token"] = env_gh
    if env_brave:
        cfg["brave_api_key"] = env_brave
    return cfg


# ── Full app config defaults (what a fresh install looks like) ───────────
# ── Ask AI / Deep Dive context packing (Spock_Console app.ctx.*) ──────────
DEFAULT_CTX_SETTINGS: Dict[str, Any] = {
    # Snippets Ask AI retrieves per question. Ask is grounded strictly in what it
    # retrieves, so too few hits turns "how does X work" into "not in the KB".
    # 20 snippets is ~4k chars against an 8k-token chat window; ask_panel trims
    # to the window's real budget, so raising this cannot overflow the prompt.
    "ask_top_k": 20,
    "deep_budget_chars": 96000,
    "deep_budget_floor": 8000,
    "deep_excerpt_chars": 6000,
    "deep_forced_excerpt_chars": 24000,
    "deep_top_k": 24,
    "deep_fill_top_k": 48,
    "deep_inventory_limit": 80,
    # Local llama-server pack ceiling. n_ctx stays large for history and
    # forced files; 0 disables the cap. Cloud windows ignore it.
    "deep_pack_token_cap": 16000,
    "chars_per_token": 2.2,
    "max_out_tokens": 2048,
    "stream_response": False,
    "timing_enabled": True,
    "timing_retain_days": 30,
}


def merge_ctx_settings(raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Ask / Deep Dive packing knobs (DB: app.ctx.*)."""
    out = dict(DEFAULT_CTX_SETTINGS)
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        if key not in out or value is None:
            continue
        if key in ("stream_response", "timing_enabled"):
            if isinstance(value, str):
                out[key] = value.strip().lower() in ("1", "true", "yes", "on")
            else:
                out[key] = bool(value)
            continue
        if key == "chars_per_token":
            try:
                out[key] = float(value)
            except (TypeError, ValueError):
                pass
            continue
        try:
            out[key] = int(value)
        except (TypeError, ValueError):
            continue
        if key == "ask_top_k":
            # Ask packs whole snippets with no budget of its own; keep a hand-set
            # value from overflowing the chat context window.
            out[key] = max(1, min(50, int(out[key])))
    return out


DEFAULT_APP_CONFIG: Dict[str, Any] = {
    "theme": "light",
    "lm_studio_host": "localhost",
    "lm_studio_port": 1234,
    "lm_studio_key": "",
    "lm_studio_model": "",
    "lm_studio_context_length": 32768,
    "ollama_host": "localhost",
    "ollama_port": 11434,
    "ollama_model": "",
    "llama_host": "localhost",
    "llama_port": DEFAULT_CHAT_PORT,
    "embed_port": DEFAULT_EMBED_PORT,
    "docs_port": DEFAULT_DOCS_PORT,
    "embed_n_ctx": DEFAULT_CTX["embed_n_ctx"],
    "chat_n_ctx": DEFAULT_CTX["chat_n_ctx"],
    "chat_max_tokens": DEFAULT_CTX["chat_max_tokens"],
    "openai_compat_base_url": "",
    "openai_compat_api_key": "",
    "openai_compat_model": "",
    "openai_compat_n_ctx": 131072,
    "openai_compat_max_tokens": 13107,
    "ask_ai_provider": "llama-server",
    "ctx": dict(DEFAULT_CTX_SETTINGS),
    "launch": dict(DEFAULT_LAUNCH_SETTINGS),
    "embedding_profile": {
        **DEFAULT_EMBEDDING_PROFILE,
        "embeddings_url": f"http://localhost:{DEFAULT_EMBED_PORT}/embeddings",
    },
    "rag_api": {
        "enabled": False,
        "host": "127.0.0.1",
        "port": DEFAULT_RAG_PORT,
        "api_key": "",
    },
    "mcp": {},
    "search": {
        "github_token": "",
        "brave_api_key": "",
    },
    "uieg": {
        "capture_folder": DEFAULT_CAPTURE_FOLDER,
        "database_path": DEFAULT_DB_PATH,
        "promoted_folder": DEFAULT_PROMOTED_FOLDER,
        "crawl_link_limit": 10,
        "crawl_timeout_sec": 15,
        "repo_extensions": [".md", ".py", ".txt", ".rst", ".json", ".toml", ".yml", ".yaml"],
    },
}

DEFAULT_SCAN_CONFIG: Dict[str, Any] = {
    "scan_roots": [str(SPOCK_ROOT)],
    # Broad enough to research a repo in any mainstream language, since Ask AI
    # can only answer from what the scan ingested.
    "allowed_extensions": [
        # docs / data
        ".md", ".rst", ".txt", ".adoc", ".html", ".pdf", ".sql",
        ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".xml", ".proto",
        # languages
        ".py", ".js", ".jsx", ".mjs", ".ts", ".tsx", ".vue", ".svelte",
        ".rs", ".go", ".java", ".kt", ".kts", ".swift", ".scala", ".dart",
        ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".rb", ".php", ".lua",
        ".r", ".jl", ".ex", ".exs", ".hs", ".zig",
        # shell / build
        ".sh", ".bash", ".ps1", ".psm1", ".bat", ".cmd", ".gradle", ".cmake",
        ".tf", ".css", ".scss",
    ],
    # Hidden directories (.git, .venv, .cargo, .next …) are skipped by the
    # walker already. These are the visible dependency and build trees — a
    # single node_modules or target/ dwarfs the repo it belongs to.
    "skip_dirs": [
        ".venv",
        ".git",
        "__pycache__",
        "__init__",
        ".github",
        "logs",
        "data",
        "research_raw",
        "quarantine",
        "node_modules",
        "target",
        "dist",
        "build",
        "out",
        "obj",
        "vendor",
        "coverage",
        "site-packages",
        "venv",
        "Pods",
    ],
    "skip_filenames": [
        "captains_log.md",
        "lint_report.md",
        "index.md",
        "uieg_capture.db",
        "ship_computer.db",
    ],
}

# Leaf names considered secret → stored with Variable_Type='secret'.
SECRET_LEAF_NAMES: set[str] = {
    "lm_studio_key",
    "openai_compat_api_key",
    "api_key",
    "github_token",
    "brave_api_key",
    "hf_token",
    "token",
}

# Keys that are lists / nested JSON (stored with Variable_Type='json' or 'list').
LIST_KEYS: set[str] = {
    "scan.scan_roots",
    "scan.allowed_extensions",
    "scan.skip_dirs",
    "scan.skip_filenames",
    "uieg.repo_extensions",
}
JSON_KEYS: set[str] = {
    "embedding_profile",
    "mcp",
    "rag_api",
    "wiki_agent.session",
}


def infer_type(name: str, value: Any) -> str:
    """Best-effort Variable_Type for a namespaced key / value."""
    leaf = name.split(".")[-1]
    if leaf in SECRET_LEAF_NAMES or name in SECRET_LEAF_NAMES:
        return "secret"
    if name in LIST_KEYS or isinstance(value, list):
        return "list"
    if name in JSON_KEYS or isinstance(value, dict):
        return "json"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return "str"


def flatten_config(nested: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    """Flatten a nested config dict into namespaced dotted keys.

    Dicts recurse into the namespace; lists / scalars are leaf values.
    E.g. {"app": {"llama_port": 8081}, "scan": {"scan_roots": [...]}}
    →   {"app.llama_port": 8081, "scan.scan_roots": [...]}
    """
    flat: Dict[str, Any] = {}
    for key, value in nested.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(flatten_config(value, prefix=name))
        else:
            flat[name] = value
    return flat
