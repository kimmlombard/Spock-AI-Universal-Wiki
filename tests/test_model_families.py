"""Gemma and Nemotron sit in the chat picker beside Qwen."""

from model_pick_policy import (
    CHAT_CATALOG,
    EMBED_CATALOG,
    HF_CHAT_SEARCHES,
    HF_EMBED_SEARCHES,
    _family_chat_score,
    infer_embed_dim,
    infer_native_ctx,
    is_non_chat_model,
    parse_size_b,
    plan_model_pair,
)
from spock_onboarding.llmfit_bridge import _CANDIDATE_EXES as ONBOARD_EXES
from spock_shell.llmfit_bridge import _CANDIDATE_EXES as SHELL_EXES


def _ids():
    return [row["id"] for row in CHAT_CATALOG]


def test_catalog_keeps_qwen_and_adds_gemma_and_nemotron():
    ids = _ids()
    assert "Qwen/Qwen3-8B-GGUF" in ids
    assert "google/gemma-3-27b-it-qat-q4_0-gguf" in ids
    assert "google/gemma-4-31B-it-qat-q4_0-gguf" in ids
    assert "bartowski/gemma-2-9b-it-GGUF" in ids
    assert "nvidia/Llama-3.1-Nemotron-Nano-8B-v1-GGUF" in ids
    assert "nvidia/NVIDIA-Nemotron-Nano-9B-v2-GGUF" in ids
    assert "nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF" in ids
    assert "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-GGUF" in ids
    assert not any("120B" in mid or "550B" in mid for mid in ids)


def test_hub_searches_include_gemma_and_nemotron():
    joined = " ".join(HF_CHAT_SEARCHES)
    assert "Qwen3-8B-GGUF" in HF_CHAT_SEARCHES
    assert "gemma-4-E4B-it" in HF_CHAT_SEARCHES
    assert "gemma-4-26B-A4B-it" in HF_CHAT_SEARCHES
    assert "gemma-3-27b-it" in HF_CHAT_SEARCHES
    assert "Nemotron-Nano-8B" in joined
    assert "Nemotron-3-Nano-30B-A3B" in joined


def test_criteria_prefers_gemma_over_qwen_and_nemotron():
    qwen = _family_chat_score("Qwen/Qwen3-8B-GGUF")
    gemma = _family_chat_score("google/gemma-3-12b-it-qat-q4_0-gguf")
    nemo = _family_chat_score("nvidia/Llama-3.1-Nemotron-Nano-8B-v1-GGUF")
    assert gemma > nemo > 0
    assert gemma > qwen > 0
    assert _family_chat_score("google/gemma-4-31B-it-qat-q4_0-gguf") > 0
    assert _family_chat_score("bartowski/gemma-2-9b-it-GGUF") > 0


def test_vision_mention_does_not_drop_text_instruct_gemma_or_nemotron():
    assert is_non_chat_model("google/gemma-3-12b-it-vision-GGUF") is False
    assert is_non_chat_model("nvidia/NVIDIA-Nemotron-Nano-9B-v2-vision-GGUF") is False
    assert is_non_chat_model("nvidia/Llama-3.1-Nemotron-Nano-VL-8B-v1") is True
    assert is_non_chat_model("nvidia/Nemotron-Parse-v1") is True


def test_native_ctx_for_new_families():
    assert infer_native_ctx("google/gemma-3-12b-it") == 131072
    assert infer_native_ctx("google/gemma-4-E4B-it") == 131072
    assert infer_native_ctx("nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF") == 131072
    assert infer_native_ctx("bartowski/gemma-2-9b-it-GGUF") == 8192


def test_moe_and_e4b_sizes_follow_weight_not_active_experts():
    assert parse_size_b("NVIDIA-Nemotron-3-Nano-30B-A3B") == 30.0
    assert parse_size_b("gemma-4-26B-A4B-it") == 26.0
    assert parse_size_b("google/gemma-4-E4B-it") == 8.0


def test_embed_catalog_includes_embeddinggemma():
    ids = [row["id"] for row in EMBED_CATALOG]
    assert "ggml-org/embeddinggemma-2-GGUF" in ids
    assert "ggml-org/embeddinggemma-300M-GGUF" in ids
    assert "embeddinggemma-2-GGUF" in HF_EMBED_SEARCHES
    assert "embeddinggemma-300M-GGUF" in HF_EMBED_SEARCHES
    assert infer_embed_dim("ggml-org/embeddinggemma-2-GGUF") == 768
    assert infer_embed_dim("ggml-org/embeddinggemma-300M-GGUF") == 768
    assert infer_native_ctx("ggml-org/embeddinggemma-2-GGUF", "embedding") == 8192
    assert infer_native_ctx("ggml-org/embeddinggemma-300M-GGUF", "embedding") == 2048
    assert parse_size_b("embeddinggemma-300M-GGUF") == 0.3
    assert is_non_chat_model("ggml-org/embeddinggemma-2-GGUF") is True
    assert is_non_chat_model("ggml-org/embeddinggemma-300M-GGUF") is True


def test_roomy_gpu_pairs_gemma_chat_and_embeddinggemma():
    plan = plan_model_pair({"vram_gb": 80})
    assert "gemma" in plan["chat_id"].lower()
    assert plan["embed_id"] == "ggml-org/embeddinggemma-2-GGUF"


def test_allow_dim_change_does_not_force_old_qwen_embed():
    # Existing Qwen3-Embedding-4B dim is 2560; criteria allow_dim_change=true.
    plan = plan_model_pair({"vram_gb": 80}, existing_dim=2560)
    assert plan["embed_id"] == "ggml-org/embeddinggemma-2-GGUF"
    assert int(plan.get("embed_dim") or 0) == 768


def test_llmfit_exe_search_prefers_app_tools_tree():
    from WarpCore.service_endpoints import llmfit_install_dir, resolve_spock_root

    install = llmfit_install_dir(resolve_spock_root())
    for cands in (SHELL_EXES, ONBOARD_EXES):
        assert cands, "expected llmfit candidate paths"
        # First hits should live under {SPOCK_ROOT}/tools/llmfit
        assert str(install) in str(cands[0])
        as_text = {str(p).replace("\\", "/") for p in cands}
        assert any("/tools/llmfit" in p or p.endswith("/tools/llmfit") or "tools/llmfit/" in p for p in as_text)
