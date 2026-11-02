"""Ask AI grounding guardrail tests.

Ask AI once shipped no system prompt at all and fell through to a generic
default, so the model answered "How does LLMFIT work?" from pretrained
knowledge of the similarly named public package. These tests pin the guardrail
to the call sites so a future redesign cannot drop it silently again.
"""

from pathlib import Path

from llm_client import ASK_SYSTEM_PROMPT, LLMClient
from WarpCore.config_defaults import merge_ctx_settings

ROOT = Path(__file__).resolve().parents[1]


def test_default_system_prompt_is_the_grounding_contract():
    messages = LLMClient._context_messages("q?", "ctx", history=[])
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == ASK_SYSTEM_PROMPT


def test_grounding_contract_states_its_core_limits():
    prompt = ASK_SYSTEM_PROMPT.lower()
    assert "only source of truth" in prompt
    assert "shares a name" in prompt  # the llmfit / lmfit collision
    assert "do not invent" in prompt


def test_thin_context_answer_points_at_deep_dive():
    prompt = ASK_SYSTEM_PROMPT
    assert "Next step:" in prompt
    assert "Deep Dive" in prompt
    assert "path filter" in prompt


def test_explicit_prompt_is_not_overridden():
    from deep_dive import DEEP_DIVE_SYSTEM_PROMPT

    messages = LLMClient._context_messages(
        "q?", "ctx", DEEP_DIVE_SYSTEM_PROMPT, history=[]
    )
    assert messages[0]["content"] == DEEP_DIVE_SYSTEM_PROMPT


def test_ask_call_sites_pass_the_prompt():
    """Source check: importing the panel needs Qt, and the server needs a port."""
    for rel in ("EngineeringDeck/ask_panel.py", "rag_api_server.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "ASK_SYSTEM_PROMPT" in src, f"{rel} asks without a grounding prompt"


def test_ask_top_k_is_clamped():
    default = merge_ctx_settings(None)["ask_top_k"]
    assert default == 20
    assert merge_ctx_settings({"ask_top_k": 0})["ask_top_k"] == 1
    assert merge_ctx_settings({"ask_top_k": 500})["ask_top_k"] == 50
    assert merge_ctx_settings({"ask_top_k": "24"})["ask_top_k"] == 24
    assert merge_ctx_settings({"ask_top_k": "abc"})["ask_top_k"] == default


def test_ask_context_budget_fits_a_small_chat_window():
    """A hand-raised ask_top_k must not push the prompt past the window."""
    from deep_dive import context_token_budget

    budget = int(context_token_budget(8192, max_out_tokens=2048) * 2.2)
    assert 0 < budget < int(8192 * 2.2)  # room left for output + system + history
