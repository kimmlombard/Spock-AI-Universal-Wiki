"""llmfit bridge resolution tests (mocked)."""

from unittest.mock import patch

from spock_onboarding import llmfit_bridge


def test_available_disabled_env(monkeypatch):
    monkeypatch.setenv("SPOCK_LLMFIT", "0")
    assert llmfit_bridge.available() is False


@patch("spock_onboarding.llmfit_bridge.find_llmfit_exe", return_value=None)
@patch("spock_onboarding.llmfit_bridge.find_uvx", return_value=None)
def test_available_missing(_uvx, _exe, monkeypatch):
    monkeypatch.delenv("SPOCK_LLMFIT", raising=False)
    assert llmfit_bridge.available() is False


def test_suggest_ngl_from_plan_verify():
    ngl, why = llmfit_bridge.suggest_ngl_from_plan(
        {"verify_command": "llama-server -m x.gguf -ngl 42"}
    )
    assert ngl == "42"
    assert "42" in why


def test_resolve_ngl_explicit():
    ngl, why = llmfit_bridge.resolve_ngl("x.gguf", current_ngl="33")
    assert ngl == "33"
    assert "explicit" in why
