"""OpenAI-compatible tab probes: health, properties, and LLM ping.

These cover the failure paths the three test buttons have to show in the
status line instead of raising into the Qt event loop.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
import requests

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from spock_shell.configure_ai import (
    _ProbeJob,
    probe_called_llm,
    probe_rag_health,
    probe_rag_props,
    rag_api_base,
)


def _resp(code=200, body="", payload=None, json_error=None):
    resp = MagicMock()
    resp.status_code = code
    resp.text = body
    if json_error is not None:
        resp.json.side_effect = json_error
    else:
        resp.json.return_value = payload
    return resp


def test_rag_api_base_defaults_and_repairs_bad_port():
    assert rag_api_base({}) == "http://127.0.0.1:8090"
    assert rag_api_base({"rag_api": {"host": "localhost", "port": 9000}}) == (
        "http://localhost:9000"
    )
    assert rag_api_base({"rag_api": {"host": "  ", "port": "nope"}}) == (
        "http://127.0.0.1:8090"
    )
    assert rag_api_base({"rag_api": {"port": 0}}) == "http://127.0.0.1:8090"


@patch("spock_shell.configure_ai.requests.get")
def test_health_connection_timeout_and_http_errors(mock_get):
    mock_get.side_effect = requests.ConnectionError("refused")
    ok, msg = probe_rag_health("http://127.0.0.1:8090")
    assert ok is False
    assert "Could not connect" in msg
    assert "/health" in msg

    mock_get.side_effect = requests.ConnectionError(
        "HTTPConnectionPool(host='127.0.0.1', port=8090): Max retries exceeded "
        "(Caused by NewConnectionError(\"Failed to establish a new connection: "
        "[WinError 10061] No connection could be made because the target machine "
        "actively refused it\"))"
    )
    ok, msg = probe_rag_health("http://127.0.0.1:8090")
    assert ok is False
    assert msg.endswith(
        "Could not connect: [WinError 10061] No connection could be made "
        "because the target machine actively refused it"
    )
    assert "HTTPConnectionPool" not in msg

    mock_get.side_effect = requests.Timeout("slow")
    ok, msg = probe_rag_health("http://127.0.0.1:8090", timeout=8)
    assert ok is False
    assert "Timed out after 8s" in msg

    mock_get.side_effect = None
    mock_get.return_value = _resp(503, body="bad gateway")
    ok, msg = probe_rag_health("http://127.0.0.1:8090")
    assert ok is False
    assert "HTTP 503" in msg
    assert "bad gateway" in msg


@patch("spock_shell.configure_ai.requests.get")
def test_health_rejects_empty_non_json_and_non_object(mock_get):
    mock_get.return_value = _resp(200, body="   ")
    ok, msg = probe_rag_health("http://127.0.0.1:8090")
    assert ok is False
    assert "empty body" in msg

    mock_get.return_value = _resp(
        200, body="<html>nope</html>", json_error=ValueError("Expecting value")
    )
    ok, msg = probe_rag_health("http://127.0.0.1:8090")
    assert ok is False
    assert "not JSON" in msg

    mock_get.return_value = _resp(200, body="[]", payload=[])
    ok, msg = probe_rag_health("http://127.0.0.1:8090")
    assert ok is False
    assert "JSON object" in msg


@patch("spock_shell.configure_ai.requests.get")
def test_health_requires_status_ok(mock_get):
    mock_get.return_value = _resp(
        200,
        body='{"status":"degraded"}',
        payload={"status": "degraded", "llm_provider": "None"},
    )
    ok, msg = probe_rag_health("http://127.0.0.1:8090")
    assert ok is False
    assert "status=degraded" in msg

    mock_get.return_value = _resp(
        200,
        body="{}",
        payload={
            "status": "ok",
            "llm_provider": "OpenAI-compatible",
            "model": "google/gemini-2.5-flash",
            "embeddings_url": "http://localhost:8080/embeddings",
            "web_ui": "http://127.0.0.1:8090/",
        },
    )
    ok, msg = probe_rag_health("http://127.0.0.1:8090")
    assert ok is True
    assert msg.startswith("Health OK")
    assert "OpenAI-compatible" in msg
    assert "gemini-2.5-flash" in msg


@patch("spock_shell.configure_ai.requests.get")
def test_props_error_trapping(mock_get):
    mock_get.side_effect = requests.ConnectionError("down")
    ok, msg = probe_rag_props("http://127.0.0.1:8090")
    assert ok is False
    assert "/props" in msg
    assert "Could not connect" in msg

    mock_get.side_effect = None
    mock_get.return_value = _resp(200, body="{}", payload={"total_slots": 1})
    ok, msg = probe_rag_props("http://127.0.0.1:8090")
    assert ok is False
    assert "default_generation_settings" in msg

    mock_get.return_value = _resp(
        200,
        body="{}",
        payload={"default_generation_settings": {"model": "  "}},
    )
    ok, msg = probe_rag_props("http://127.0.0.1:8090")
    assert ok is False
    assert "model is empty" in msg

    mock_get.return_value = _resp(
        200,
        body="{}",
        payload={
            "default_generation_settings": {"model": "spock-ships-computer"},
            "total_slots": 1,
            "model_path": "spock-ships-computer",
            "spock_note": "This is the Spock RAG API.",
        },
    )
    ok, msg = probe_rag_props("http://127.0.0.1:8090")
    assert ok is True
    assert "spock-ships-computer" in msg
    assert "slots=1" in msg


class _BoomClient:
    @property
    def active_provider(self):
        raise RuntimeError("probe blew up")


class _ScriptedClient:
    def __init__(self):
        self.active_provider = "OpenAI-compatible"
        self.model = "google/gemini-2.5-flash"
        self.is_available = False
        self.last_error = "connection refused"
        self.ask_with_context = MagicMock()


def _patched_llm(client, load_error=None):
    fake_start = MagicMock()
    if load_error is not None:
        fake_start.load_cfg.side_effect = load_error
    else:
        fake_start.load_cfg.return_value = {"ask_ai_provider": "OpenAI-compatible"}
    fake_bridge = MagicMock()
    fake_bridge.make_llm_client.return_value = client
    return patch.dict(
        "sys.modules",
        {"_start_rag_api": fake_start, "spock_rag_adapter.bridge_host": fake_bridge},
    )


def test_llm_status_traps_setup_and_call_failures():
    with _patched_llm(None, load_error=OSError("db locked")):
        ok, msg = probe_called_llm()
    assert ok is False
    assert "Could not build LLM client:" in msg
    assert "OSError" in msg
    assert "db locked" in msg

    with _patched_llm(_BoomClient()):
        ok, msg = probe_called_llm()
    assert ok is False
    assert "LLM status read failed" in msg
    assert "RuntimeError" in msg

    client = _ScriptedClient()
    with _patched_llm(client):
        ok, msg = probe_called_llm()
    assert ok is False
    assert "Available: False" in msg
    assert "connection refused" in msg

    client.is_available = True
    client.ask_with_context.side_effect = TimeoutError("hung")
    with _patched_llm(client):
        ok, msg = probe_called_llm()
    assert ok is False
    assert "LLM call failed: TimeoutError" in msg

    client.ask_with_context.side_effect = None
    client.ask_with_context.return_value = "Could not reach LLM provider.\nHTTP 401"
    with _patched_llm(client):
        ok, msg = probe_called_llm()
    assert ok is False
    assert "Could not reach LLM provider" in msg

    client.ask_with_context.return_value = ""
    client.last_error = "empty completion"
    with _patched_llm(client):
        ok, msg = probe_called_llm()
    assert ok is False
    assert "empty completion" in msg

    client.ask_with_context.return_value = "I am here"
    with _patched_llm(client):
        ok, msg = probe_called_llm()
    assert ok is False
    assert "did not include PING" in msg

    client.ask_with_context.return_value = "PING"
    with _patched_llm(client):
        ok, msg = probe_called_llm()
    assert ok is True
    assert "Provider: OpenAI-compatible" in msg
    assert "Response: PING" in msg
    client.ask_with_context.assert_called_with(
        "Reply with PING", "Context: PING", timeout=300
    )


def test_probe_job_traps_exceptions_and_bad_returns():
    pytest.importorskip("PyQt6.QtWidgets")
    from PyQt6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])

    seen = {}

    def boom():
        raise RuntimeError("boom")

    job = _ProbeJob("Health", boom)
    job.result.connect(lambda ok, msg: seen.update(ok=ok, msg=msg))
    job.run()
    assert seen["ok"] is False
    assert "Health failed: RuntimeError: boom" == seen["msg"]

    job = _ProbeJob("Properties", lambda: "nope")
    job.result.connect(lambda ok, msg: seen.update(ok=ok, msg=msg))
    job.run()
    assert seen["ok"] is False
    assert "expected (bool, str)" in seen["msg"]

    job = _ProbeJob("LLM status", lambda: (True, "pong"))
    job.result.connect(lambda ok, msg: seen.update(ok=ok, msg=msg))
    job.run()
    assert seen == {"ok": True, "msg": "pong"}


def _wait_for(app, predicate, seconds=3.0):
    import time

    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("timed out waiting for probe result")


def test_health_button_traps_raised_errors_and_reenables():
    pytest.importorskip("PyQt6.QtWidgets")
    from PyQt6.QtWidgets import QApplication

    from spock_shell.configure_ai import OpenAiCompatTab

    app = QApplication.instance() or QApplication([])
    tab = OpenAiCompatTab({"rag_api": {"host": "127.0.0.1", "port": 8090}})
    assert [b.text() for b in tab._extra_btns] == [
        "Test health",
        "Test properties",
        "Test LLM status",
    ]
    assert tab.health_btn.toolTip() == "GET http://127.0.0.1:8090/health"
    assert tab.props_btn.toolTip() == "GET http://127.0.0.1:8090/props"

    with patch(
        "spock_shell.configure_ai.probe_rag_health",
        side_effect=ConnectionError("8090 down"),
    ):
        tab.health_btn.click()
        _wait_for(
            app,
            lambda: "8090 down" in tab.status.text() and tab.health_btn.isEnabled(),
        )
    assert tab.status.text().startswith("\u2717")
    assert "Health failed: ConnectionError: 8090 down" in tab.status.text()
    assert tab.props_btn.isEnabled()
    assert tab.llm_status_btn.isEnabled()
    assert tab.test_btn.isEnabled()

    with patch(
        "spock_shell.configure_ai.probe_rag_props",
        return_value=(False, "Properties http://127.0.0.1:8090/props — HTTP 404: missing"),
    ):
        tab.props_btn.click()
        _wait_for(
            app,
            lambda: "HTTP 404" in tab.status.text() and tab.props_btn.isEnabled(),
        )
    assert "HTTP 404" in tab.status.text()
    assert tab.status.text().startswith("\u2717")
