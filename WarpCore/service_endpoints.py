"""Canonical Spock service ports, URLs, and context/token budgets.

All suite consumers should resolve endpoints through this module instead of
scattering 8080/8081/8082/8090/8765/8000 literals. Precedence:

  1. SPOCK_* environment overrides (and EMBEDDINGS_URL for embed URL)
  2. Loaded app config (ship_computer.db / DEFAULT_APP_CONFIG keys)
  3. DEFAULT_PORTS / DEFAULT_CTX below

llama.cpp's future default bind port (:9931) is irrelevant while Spock always
passes an explicit ``--port`` from this config.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple
from urllib.parse import urlparse


def resolve_spock_root() -> Path:
    """Suite root: SPOCK_ROOT env (must contain WarpCore/) else package parent."""
    env = (os.environ.get("SPOCK_ROOT") or "").strip()
    if env:
        candidate = Path(env).expanduser().resolve()
        if (candidate / "WarpCore").is_dir():
            return candidate
    return Path(__file__).resolve().parent.parent


SPOCK_ROOT = resolve_spock_root()


# ── Portable tool installs (under the Spock app tree) ─────────────────────
# Prefer {SPOCK_ROOT}/tools/… so Windows and WSL share the same relative layout.
# Override with LLAMA_SERVER_PATH / SPOCK_LLMFIT_EXE when needed.


def is_runnable_host_binary(path: Path | str) -> bool:
    """True if ``path`` is a file this OS can exec (skip Windows PE under WSL).

    WSL often has ``*.exe`` on PATH via ``/mnt/c/...``; Spock must not treat
    those as Linux llmfit / llama-server.
    """
    try:
        p = Path(path)
    except (TypeError, ValueError):
        return False
    try:
        if not p.is_file():
            return False
    except OSError:
        return False
    if os.name == "nt":
        return True
    # POSIX / WSL: never run PE tooling
    if p.suffix.lower() == ".exe":
        return False
    try:
        with p.open("rb") as fh:
            mag = fh.read(4)
    except OSError:
        return False
    # ELF, shebang scripts, or Mach-O / universal (macOS Metal llama-server, llmfit)
    if mag[:4] == b"\x7fELF":
        return True
    if mag[:2] == b"#!":
        return True
    if mag[:4] in (
        b"\xfe\xed\xfa\xce",  # MH_MAGIC
        b"\xfe\xed\xfa\xcf",  # MH_MAGIC_64
        b"\xce\xfa\xed\xfe",  # MH_CIGAM
        b"\xcf\xfa\xed\xfe",  # MH_CIGAM_64
        b"\xca\xfe\xba\xbe",  # FAT_MAGIC
        b"\xbe\xba\xfe\xca",  # FAT_CIGAM
    ):
        return True
    return False


def llama_server_install_dir(root: Optional[Path] = None) -> Path:
    """Canonical llama.cpp install dir: ``{root}/tools/llama-server``."""
    base = Path(root) if root is not None else resolve_spock_root()
    return (base / "tools" / "llama-server").resolve()


def llmfit_install_dir(root: Optional[Path] = None) -> Path:
    """Canonical llmfit install dir: ``{root}/tools/llmfit``."""
    base = Path(root) if root is not None else resolve_spock_root()
    return (base / "tools" / "llmfit").resolve()


def _llama_server_binary_names() -> Tuple[str, ...]:
    if os.name == "nt":
        return ("llama-server.exe", "llama-server")
    return ("llama-server", "llama-server.exe")


def _llmfit_binary_names() -> Tuple[str, ...]:
    if os.name == "nt":
        return ("llmfit.exe", "llmfit")
    return ("llmfit", "llmfit.exe")


def llama_server_binary_candidates(
    root: Optional[Path] = None,
    *,
    explicit: Optional[str] = None,
) -> list[Path]:
    """Ordered search list for the llama-server binary (app-relative first)."""
    base = Path(root) if root is not None else resolve_spock_root()
    install = llama_server_install_dir(base)
    names = _llama_server_binary_names()
    out: list[Path] = []

    def _add(p: Path) -> None:
        try:
            key = str(p)
        except Exception:
            return
        if any(str(x) == key for x in out):
            return
        out.append(p)

    if explicit and str(explicit).strip():
        ep = Path(str(explicit).strip())
        _add(ep)
        if ep.is_dir():
            for name in names:
                _add(ep / name)
    env = (os.environ.get("LLAMA_SERVER_PATH") or "").strip()
    if env:
        ep = Path(env)
        _add(ep)
        if ep.is_dir() or not ep.suffix:
            for name in names:
                _add(ep / name)
    which = shutil.which("llama-server")
    if which and is_runnable_host_binary(which):
        _add(Path(which))
    if os.name == "nt":
        which_exe = shutil.which("llama-server.exe")
        if which_exe:
            _add(Path(which_exe))
    for name in names:
        # On Linux skip listing *.exe ahead of the real binary in search order
        if os.name != "nt" and name.endswith(".exe"):
            continue
        _add(install / name)
    # Alternate / historical relative names under the same app tree
    for name in names:
        _add(base / "tools" / "llamacpp" / name)
        _add(base / "llamaccp" / name)
    tip = install / "SPOCK_LLAMA_PATH.txt"
    if tip.is_file():
        try:
            line = tip.read_text(encoding="utf-8").strip().splitlines()[0]
            if line:
                out.insert(0, Path(line))
        except OSError:
            pass
    return out


def llmfit_binary_candidates(root: Optional[Path] = None) -> list[Path]:
    """Ordered search list for the llmfit CLI (app-relative first)."""
    base = Path(root) if root is not None else resolve_spock_root()
    install = llmfit_install_dir(base)
    names = _llmfit_binary_names()
    out: list[Path] = []
    for name in names:
        if os.name != "nt" and name.endswith(".exe"):
            continue
        out.append(install / name)
        out.append(install / "target" / "release" / name)
        out.append(install / "bin" / name)
    # Optional user-local install (Windows LOCALAPPDATA only — not WSL AppData)
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        out.append(Path(local) / "llmfit" / "llmfit.exe")
    else:
        out.append(Path.home() / ".local" / "bin" / "llmfit")
    return out


DEFAULT_PORTS: Dict[str, int] = {
    "embed": 8080,
    "chat": 8081,
    "mcp_webui": 8082,
    "rag": 8090,
    "mcp_http": 8765,
    "docs": 8000,
}

ENV_PORT_KEYS: Dict[str, str] = {
    "embed": "SPOCK_EMBED_PORT",
    "chat": "SPOCK_CHAT_PORT",
    "mcp_webui": "SPOCK_MCP_WEBUI_PORT",
    "rag": "SPOCK_RAG_PORT",
    "mcp_http": "SPOCK_MCP_PORT",
    "docs": "SPOCK_DOCS_PORT",
}

DEFAULT_CTX: Dict[str, int] = {
    "embed_n_ctx": 8192,
    "chat_n_ctx": 32768,
    "chat_max_tokens": 2048,
}


def clamp_port(value: Any, default: int) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return int(default)
    if port < 1 or port > 65535:
        return int(default)
    return port


def clamp_ctx(value: Any, default: int, *, lo: int = 512, hi: int = 1_048_576) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return int(default)
    return max(lo, min(hi, n))


def clamp_max_tokens(value: Any, default: int = 2048) -> int:
    return clamp_ctx(value, default, lo=256, hi=65536)


def _port_from_url(url: str, default: int) -> int:
    try:
        u = urlparse((url or "").strip())
        if u.port:
            return int(u.port)
    except Exception:
        pass
    return int(default)


def _cfg_get(cfg: Optional[Mapping[str, Any]], *keys: str, default: Any = None) -> Any:
    if not cfg:
        return default
    cur: Any = cfg
    for key in keys:
        if not isinstance(cur, Mapping) or key not in cur:
            return default
        cur = cur[key]
    return cur


def resolve_ports(cfg: Optional[Mapping[str, Any]] = None) -> Dict[str, int]:
    """Resolved port map for embed/chat/mcp_webui/rag/mcp_http/docs."""
    emb_url = (
        os.environ.get("SPOCK_EMBEDDINGS_URL")
        or os.environ.get("EMBEDDINGS_URL")
        or str(_cfg_get(cfg, "embedding_profile", "embeddings_url", default="") or "")
        or f"http://localhost:{DEFAULT_PORTS['embed']}/embeddings"
    )
    ports = {
        "embed": _port_from_url(emb_url, DEFAULT_PORTS["embed"]),
        "chat": clamp_port(
            _cfg_get(cfg, "llama_port", default=DEFAULT_PORTS["chat"]),
            DEFAULT_PORTS["chat"],
        ),
        "mcp_webui": clamp_port(
            _cfg_get(cfg, "mcp", "webui_port", default=DEFAULT_PORTS["mcp_webui"]),
            DEFAULT_PORTS["mcp_webui"],
        ),
        "rag": clamp_port(
            _cfg_get(cfg, "rag_api", "port", default=DEFAULT_PORTS["rag"]),
            DEFAULT_PORTS["rag"],
        ),
        "mcp_http": clamp_port(
            _cfg_get(cfg, "mcp", "http_port", default=DEFAULT_PORTS["mcp_http"]),
            DEFAULT_PORTS["mcp_http"],
        ),
        "docs": clamp_port(
            _cfg_get(cfg, "docs_port", default=DEFAULT_PORTS["docs"]),
            DEFAULT_PORTS["docs"],
        ),
    }
    if cfg and cfg.get("embed_port") is not None:
        ports["embed"] = clamp_port(cfg.get("embed_port"), ports["embed"])

    for name, env_key in ENV_PORT_KEYS.items():
        raw = (os.environ.get(env_key) or "").strip()
        if raw:
            ports[name] = clamp_port(raw, ports[name])
    return ports


def resolve_ctx(cfg: Optional[Mapping[str, Any]] = None) -> Dict[str, int]:
    """embed_n_ctx / chat_n_ctx / chat_max_tokens from config + defaults."""
    return {
        "embed_n_ctx": clamp_ctx(
            _cfg_get(cfg, "embed_n_ctx", default=DEFAULT_CTX["embed_n_ctx"]),
            DEFAULT_CTX["embed_n_ctx"],
        ),
        "chat_n_ctx": clamp_ctx(
            _cfg_get(cfg, "chat_n_ctx", default=DEFAULT_CTX["chat_n_ctx"]),
            DEFAULT_CTX["chat_n_ctx"],
        ),
        "chat_max_tokens": clamp_max_tokens(
            _cfg_get(cfg, "chat_max_tokens", default=DEFAULT_CTX["chat_max_tokens"]),
            DEFAULT_CTX["chat_max_tokens"],
        ),
    }


def embeddings_url(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    host: str = "localhost",
) -> str:
    env = (
        os.environ.get("SPOCK_EMBEDDINGS_URL")
        or os.environ.get("EMBEDDINGS_URL")
        or ""
    ).strip()
    if env:
        return env.rstrip("/")
    stored = str(
        _cfg_get(cfg, "embedding_profile", "embeddings_url", default="") or ""
    ).strip()
    if stored:
        return stored.rstrip("/")
    ports = resolve_ports(cfg)
    return f"http://{host}:{ports['embed']}/embeddings"


def chat_base_url(cfg: Optional[Mapping[str, Any]] = None) -> str:
    host = str(_cfg_get(cfg, "llama_host", default="localhost") or "localhost").strip()
    ports = resolve_ports(cfg)
    return f"http://{host}:{ports['chat']}"


def rag_base_url(cfg: Optional[Mapping[str, Any]] = None) -> str:
    host = str(
        _cfg_get(cfg, "rag_api", "host", default="127.0.0.1") or "127.0.0.1"
    ).strip()
    ports = resolve_ports(cfg)
    return f"http://{host}:{ports['rag']}"


def docs_base_url(cfg: Optional[Mapping[str, Any]] = None) -> str:
    ports = resolve_ports(cfg)
    return f"http://127.0.0.1:{ports['docs']}"


def sync_embedding_url_port(
    cfg: Dict[str, Any],
    embed_port: Optional[int] = None,
) -> Dict[str, Any]:
    """Keep embedding_profile.embeddings_url host/path; update port if needed."""
    out = dict(cfg)
    ports = resolve_ports(out)
    port = clamp_port(
        embed_port if embed_port is not None else ports["embed"], ports["embed"]
    )
    out["embed_port"] = port
    profile = dict(out.get("embedding_profile") or {})
    current = str(profile.get("embeddings_url") or "").strip()
    if current:
        try:
            u = urlparse(current)
            h = u.hostname or "localhost"
            scheme = u.scheme or "http"
            path = u.path or "/embeddings"
            if not path.endswith("/embeddings"):
                path = "/embeddings"
            profile["embeddings_url"] = f"{scheme}://{h}:{port}{path}"
        except Exception:
            profile["embeddings_url"] = f"http://localhost:{port}/embeddings"
    else:
        profile["embeddings_url"] = f"http://localhost:{port}/embeddings"
    out["embedding_profile"] = profile
    return out


def resolve_llama_server_path(explicit: Optional[str] = None) -> Tuple[str, str]:
    """Return (path, note). Prefer env / PATH, then ``{SPOCK_ROOT}/tools/llama-server``."""
    root = resolve_spock_root()
    install = llama_server_install_dir(root)
    note = ""
    env = (os.environ.get("LLAMA_SERVER_PATH") or "").strip()
    if env:
        note = "from LLAMA_SERVER_PATH"
    for path in llama_server_binary_candidates(root, explicit=explicit):
        try:
            if is_runnable_host_binary(path):
                return str(path.resolve()), note or f"found at {path}"
        except OSError:
            continue
    fallback = install / _llama_server_binary_names()[0]
    return str(fallback), (
        "llama-server not found — set LLAMA_SERVER_PATH or install under "
        f"{install}"
    )


DEFAULT_EMBED_PORT = DEFAULT_PORTS["embed"]
DEFAULT_CHAT_PORT = DEFAULT_PORTS["chat"]
DEFAULT_RAG_PORT = DEFAULT_PORTS["rag"]
DEFAULT_MCP_PORT = DEFAULT_PORTS["mcp_http"]
DEFAULT_DOCS_PORT = DEFAULT_PORTS["docs"]
DEFAULT_MCP_WEBUI_PORT = DEFAULT_PORTS["mcp_webui"]
