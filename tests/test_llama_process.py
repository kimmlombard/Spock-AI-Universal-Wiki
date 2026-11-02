"""Unit tests for cmdline parse / role / argv assembly."""

from spock_onboarding.llama_process import (
    build_server_argv,
    is_embedding_gguf_path,
    parse_cmdline,
    role_from_parsed,
)


def test_parse_cmdline_basic():
    parsed = parse_cmdline(
        [
            "llama-server",
            "-m",
            r"C:\models\chat.gguf",
            "--port",
            "8081",
            "-c",
            "8192",
            "-ngl",
            "99",
        ]
    )
    assert parsed["model_path"].endswith("chat.gguf")
    assert parsed["port"] == "8081"
    assert parsed["n_ctx"] == "8192"
    assert parsed["ngl"] == "99"
    assert parsed["embeddings"] == "0"


def test_parse_cmdline_embeddings():
    parsed = parse_cmdline(
        ["llama-server", "-m", "emb.gguf", "--port", "8080", "--embeddings"]
    )
    assert parsed["embeddings"] == "1"
    assert role_from_parsed(parsed) == "embedding"


def test_is_embedding_gguf_path():
    assert is_embedding_gguf_path("Qwen3-Embedding-0.6B-Q8_0.gguf")
    assert not is_embedding_gguf_path("Qwen3-8B-Q5_K_M.gguf")


def test_build_server_argv_embed_flags():
    argv = build_server_argv(
        "llama-server.exe",
        r"D:\models\Qwen3-Embedding-0.6B.gguf",
        port=8080,
        n_ctx=4096,
        ngl="40",
        role="embedding",
    )
    assert "--embeddings" in argv
    assert "--no-webui" in argv
    assert argv[argv.index("--pooling") + 1] == "last"
    assert argv[argv.index("--port") + 1] == "8080"
    assert argv[argv.index("-ngl") + 1] == "40"


def test_build_server_argv_embeddinggemma2_uses_mean_pooling():
    argv = build_server_argv(
        "llama-server.exe",
        r"D:\models\embeddinggemma-2-Q8_0.gguf",
        port=8080,
        n_ctx=2048,
        ngl="99",
        role="embedding",
    )
    assert "--embeddings" in argv
    assert argv[argv.index("--pooling") + 1] == "mean"


def test_build_server_argv_chat_no_embed_flag():
    argv = build_server_argv(
        "llama-server.exe",
        r"D:\models\Qwen3-8B.gguf",
        port=8081,
        role="chat",
    )
    assert "--embeddings" not in argv
    assert argv[argv.index("--port") + 1] == "8081"
    assert "-ncmoe" not in argv
    assert "--reasoning" not in argv


def test_build_server_argv_chat_includes_ncmoe_and_reasoning():
    argv = build_server_argv(
        "llama-server",
        "chat.gguf",
        port=8081,
        role="chat",
        n_cpu_moe=28,
        reasoning="off",
    )
    assert argv[argv.index("-ncmoe") + 1] == "28"
    assert argv[argv.index("--reasoning") + 1] == "off"


def test_build_server_argv_omits_ncmoe_when_zero():
    argv = build_server_argv(
        "llama-server",
        "chat.gguf",
        port=8081,
        role="chat",
        n_cpu_moe=0,
        reasoning="off",
    )
    assert "-ncmoe" not in argv
    assert argv[argv.index("--reasoning") + 1] == "off"


def test_build_server_argv_embed_omits_moe_and_reasoning():
    argv = build_server_argv(
        "llama-server",
        "emb.gguf",
        port=8080,
        role="embedding",
        n_cpu_moe=28,
        reasoning="off",
    )
    assert "-ncmoe" not in argv
    assert "--reasoning" not in argv
