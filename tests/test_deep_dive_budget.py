"""Deep Dive pack budget follows the chat window, not a 4k leftover."""

from deep_dive import (
    apply_local_pack_cap,
    context_token_budget,
    pack_deep_dive_context,
    packing_opts_from_config,
)
from WarpCore.host_recipe import propose_recipe


def test_follow_up_budget_on_8k_is_the_old_cap():
    budget = context_token_budget(
        8192,
        max_out_tokens=2048,
        system_reserve_tokens=1024,
        history_reserve_tokens=1900,
    )
    assert budget == 3220


def test_32k_window_leaves_room_after_the_same_reserves():
    budget = context_token_budget(
        32768,
        max_out_tokens=2048,
        system_reserve_tokens=1024,
        history_reserve_tokens=1900,
    )
    assert budget == 32768 - 2048 - 1024 - 1900
    assert budget > 20000


def test_32k_llama_pack_is_capped_at_16000_tokens():
    raw = context_token_budget(
        32768,
        max_out_tokens=2048,
        system_reserve_tokens=1024,
        history_reserve_tokens=1900,
    )
    assert raw > 16000
    assert (
        apply_local_pack_cap(raw, provider="llama-server", cap=16000) == 16000
    )


def test_8k_llama_pack_stays_under_the_cap():
    raw = context_token_budget(
        8192,
        max_out_tokens=2048,
        system_reserve_tokens=1024,
        history_reserve_tokens=1900,
    )
    assert raw == 3220
    assert apply_local_pack_cap(raw, provider="llama-server", cap=16000) == 3220


def test_cloud_pack_is_not_capped():
    assert (
        apply_local_pack_cap(80_000, provider="OpenAI-compatible", cap=16000)
        == 80_000
    )
    assert apply_local_pack_cap(80_000, provider="llama-server", cap=0) == 80_000


def test_pack_token_cap_default_is_16000_and_zero_disables():
    from WarpCore.config_defaults import merge_ctx_settings

    assert merge_ctx_settings(None)["deep_pack_token_cap"] == 16000
    assert merge_ctx_settings({"deep_pack_token_cap": 0})["deep_pack_token_cap"] == 0


def test_packing_opts_use_configured_chat_ctx_when_props_are_down(monkeypatch):
    monkeypatch.setattr("deep_dive.probe_llama_n_ctx", lambda *_a, **_k: None)
    opts = packing_opts_from_config(
        {"ask_ai_provider": "llama-server", "chat_n_ctx": 32768, "ctx": {"max_out_tokens": 2048}}
    )
    assert opts["n_ctx"] == 32768
    assert opts["max_out_tokens"] == 2048


def test_packing_opts_default_chat_ctx_is_32k(monkeypatch):
    monkeypatch.setattr("deep_dive.probe_llama_n_ctx", lambda *_a, **_k: None)
    opts = packing_opts_from_config({"ask_ai_provider": "llama-server"})
    assert opts["n_ctx"] == 32768


def test_live_props_still_win_over_the_configured_window(monkeypatch):
    monkeypatch.setattr("deep_dive.probe_llama_n_ctx", lambda *_a, **_k: 8192)
    opts = packing_opts_from_config(
        {"ask_ai_provider": "llama-server", "chat_n_ctx": 32768}
    )
    assert opts["n_ctx"] == 8192


def test_inventory_sample_is_capped_near_1200_tokens():
    inventory = [
        {"path": f"D:/src/module_{i:03d}.py", "title": f"m{i}", "chars": 4000}
        for i in range(80)
    ]
    context, _used, stats = pack_deep_dive_context(
        inventory,
        [],
        "1=1",
        match_count=80,
        budget=50_000,
        unit="tokens",
        measure=lambda text: max(1, len(text) // 2),
    )
    assert "more not listed" in context
    assert stats.inventory_shown < 80
    assert "tokens" in stats.summary_line()
    assert "chars" in stats.summary_line()
    assert "Matching documents: 80" in context


def test_llama_fit_caps_cloud_max_tokens_and_shrinks_a_full_window():
    from llm_client import fit_llama_messages

    messages = [
        {"role": "system", "content": "Be brief."},
        {
            "role": "user",
            "content": "Context:\n" + ("x" * 40000) + "\n\nQuestion: where is LLMFIT?",
        },
    ]
    fitted, max_tokens = fit_llama_messages(
        messages, n_ctx=16384, max_tokens=13107
    )
    assert max_tokens == 2048
    body = fitted[-1]["content"]
    assert "where is LLMFIT?" in body
    assert "truncated" in body
    assert len(body) < 30000
    assert messages[-1]["content"].startswith("Context:\nxxxx")


def test_openai_budget_does_not_replace_local_chat_max_tokens():
    from llm_client import LLMClient

    previous = LLMClient._chat_max_tokens
    try:
        LLMClient._chat_max_tokens = 2048
        LLMClient.configure_openai_compat(
            "https://us-central1-aiplatform.googleapis.com/v1/projects/p/locations/us-central1/endpoints/openapi",
            "",
            "google/gemini-2.5-flash",
            n_ctx=131072,
            max_tokens=65536,
        )
        assert LLMClient._chat_max_tokens == 2048
        assert LLMClient._openai_max_tokens == 65536
    finally:
        LLMClient._chat_max_tokens = previous


def test_propose_recipe_raises_chat_context_with_vram():
    big = propose_recipe(
        {"host_ram_gb": 64, "gpus": [{"index": 0, "vram_gb": 24, "name": "GPU"}]}
    )
    mid = propose_recipe(
        {"host_ram_gb": 32, "gpus": [{"index": 0, "vram_gb": 12, "name": "GPU"}]}
    )
    small = propose_recipe(
        {"host_ram_gb": 16, "gpus": [{"index": 0, "vram_gb": 8, "name": "GPU"}]}
    )
    assert big["chat_n_ctx"] == 32768
    assert mid["chat_n_ctx"] == 16384
    assert small["chat_n_ctx"] == 4096
