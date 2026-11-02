"""WebUI --ui-mcp-proxy must not autoload the embedding GGUF."""

from __future__ import annotations

import json
from pathlib import Path

from mcp_panel import (
    build_ui_mcp_proxy_argv,
    build_ui_mcp_proxy_env,
    resolve_webui_chat_model,
)


def test_build_ui_mcp_proxy_argv_disables_autoload():
    argv = build_ui_mcp_proxy_argv(
        r"tools\llama-server\llama-server.exe",
        host="127.0.0.1",
        port=8082,
    )
    assert "--ui-mcp-proxy" in argv
    assert "--no-models-autoload" in argv
    assert "-m" not in argv


def test_build_ui_mcp_proxy_argv_scopes_models_dir_to_chat(tmp_path: Path):
    chat_dir = tmp_path / "gemma-4-E4B-it-GGUF"
    chat_dir.mkdir()
    chat = chat_dir / "gemma-4-E4B-it-Q4_K_M.gguf"
    chat.write_bytes(b"x")
    argv = build_ui_mcp_proxy_argv(
        "llama-server.exe",
        chat_model_path=str(chat),
        chat_n_ctx=16384,
    )
    assert argv[argv.index("--models-dir") + 1] == str(chat_dir.resolve())
    assert argv[argv.index("-c") + 1] == "16384"
    assert "--no-models-autoload" in argv
    # Must not point at an embedding folder name.
    assert "embeddinggemma" not in " ".join(argv).lower()


def test_resolve_webui_chat_model_prefers_first_models(tmp_path: Path):
    chat = tmp_path / "chat.gguf"
    chat.write_bytes(b"x")
    (tmp_path / "first_models_last.json").write_text(
        json.dumps(
            {
                "chat_gguf_path": str(chat),
                "chat_n_ctx": 16384,
                "embed_gguf_path": str(tmp_path / "embeddinggemma-2.gguf"),
            }
        ),
        encoding="utf-8",
    )
    path, n_ctx = resolve_webui_chat_model(str(tmp_path))
    assert path == str(chat)
    assert n_ctx == 16384


def test_build_ui_mcp_proxy_env_isolates_hf_cache(tmp_path: Path):
    chat = tmp_path / "chat.gguf"
    chat.write_bytes(b"x")
    env = build_ui_mcp_proxy_env(
        chat_model_path=str(chat),
        base_env={"PATH": "x", "HF_HUB_CACHE": r"C:\old-cache"},
    )
    assert env["PATH"] == "x"
    assert env["HF_HUB_CACHE"] != r"C:\old-cache"
    assert "llama-webui-empty-cache" in env["HF_HUB_CACHE"].replace("\\", "/")
    assert env["LLAMA_CACHE"] == env["HF_HUB_CACHE"]


def test_build_ui_mcp_proxy_env_unchanged_without_chat():
    env = build_ui_mcp_proxy_env(
        chat_model_path="",
        base_env={"HF_HUB_CACHE": r"C:\keep-me"},
    )
    assert env["HF_HUB_CACHE"] == r"C:\keep-me"
