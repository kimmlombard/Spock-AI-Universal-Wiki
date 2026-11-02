"""Tests for Good Results coach tips."""

from __future__ import annotations

from spock_shell.good_results_coach import (
    collect_ask_tips,
    path_filter_excludes_spock,
    tip_pack_saturation,
    tip_path_vs_question,
    tip_timeout,
)


def test_path_filter_excludes_spock_when_llama_only():
    assert path_filter_excludes_spock(r"C:\DEV\ggml-org-llama-cpp\llama.cpp")
    assert not path_filter_excludes_spock("")
    assert not path_filter_excludes_spock(r"D:\Spock-Universal-AI-Wiki")
    assert not path_filter_excludes_spock("Spock-Universal-AI-Wiki; llama.cpp")


def test_tip_path_vs_question():
    tip = tip_path_vs_question(
        "How do I tune context in Spock Navigation Station?",
        r"C:\DEV\llama.cpp",
    )
    assert tip and "Path filter" in tip
    assert tip_path_vs_question("what is ctx_shift in llama.cpp?", r"C:\DEV\llama.cpp") is None


def test_tip_pack_saturation():
    tip = tip_pack_saturation(
        {
            "mode": "deep_dive",
            "budget_used_pct": 99.0,
            "used_docs": 8,
            "n_ctx": 16384,
        }
    )
    assert tip and "filled" in tip.lower()
    assert tip_pack_saturation({"mode": "ask", "budget_used_pct": 99}) is None
    assert tip_pack_saturation({"mode": "deep_dive", "budget_used_pct": 50}) is None


def test_collect_ask_tips_timeout():
    tips = collect_ask_tips(
        question="hi",
        path_filter="",
        answer="Could not reach LLM provider.\nTimed out after 300s",
        timed_out=True,
    )
    assert tips and tip_timeout() in tips
