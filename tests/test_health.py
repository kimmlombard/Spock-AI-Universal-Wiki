"""Health probe unit tests (mocked HTTP)."""

from unittest.mock import MagicMock, patch

from spock_onboarding.health import probe_embed_chat, probe_llama_server


def _resp(code=200, payload=None):
    m = MagicMock()
    m.status_code = code
    m.json.return_value = payload if payload is not None else {}
    return m


@patch("spock_onboarding.health.requests.get")
def test_probe_llama_server_up(mock_get):
    def side_effect(url, timeout=1.5):
        if url.endswith("/health"):
            return _resp(200, {"status": "ok"})
        if url.endswith("/props"):
            return _resp(
                200,
                {
                    "model_path": r"D:\models\chat.gguf",
                    "default_generation_settings": {"n_ctx": 8192},
                },
            )
        return _resp(404)

    mock_get.side_effect = side_effect
    info = probe_llama_server("127.0.0.1", 8081, role_hint="chat")
    assert info["reachable"] is True
    assert info["model_name"] == "chat.gguf"
    assert info["n_ctx"] == 8192
    assert info["role"] == "chat"


@patch("spock_onboarding.health.requests.get")
def test_probe_llama_server_down(mock_get):
    mock_get.side_effect = Exception("connection refused")
    # requests raises RequestException — simulate via ConnectionError subclass
    import requests

    mock_get.side_effect = requests.ConnectionError("nope")
    info = probe_llama_server("127.0.0.1", 8080)
    assert info["reachable"] is False


@patch("spock_onboarding.health.probe_llama_server")
def test_probe_embed_chat(mock_probe):
    mock_probe.side_effect = [
        {"reachable": True, "port": 8080},
        {"reachable": True, "port": 8081},
    ]
    out = probe_embed_chat()
    assert out["servers_ready"] is True


@patch("spock_health_report.requests.get")
def test_ship_status_does_not_call_lm_studio_a_llama_server(mock_get):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "error": "Unexpected endpoint or method. (GET /health)"
    }
    mock_get.return_value = resp
    from spock_health_report import probe_llama_server as ship_probe

    info = ship_probe("127.0.0.1", 8081, role_hint="chat")
    assert info["reachable"] is False
    assert "LM Studio" in info["detail"]
