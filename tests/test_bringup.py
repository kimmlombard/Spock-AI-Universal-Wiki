"""Acquire / readiness orchestration tests (mocked)."""

import json
from pathlib import Path
from unittest.mock import patch

from spock_onboarding.pick import ModelPick, pick_model_pair
from spock_onboarding.readiness import write_readiness, format_status_text
from spock_onboarding.state import FirstModelsState
from spock_bringup import cmd_acquire, cmd_status
from spock_bringup_menu.steps import build_cli_command, build_spawn_command


def test_pick_model_pair_vram_tiers():
    low = pick_model_pair(4.0)
    mid = pick_model_pair(12.0)
    high = pick_model_pair(24.0)
    assert low.embed_repo == "ggml-org/embeddinggemma-2-GGUF"
    assert "gemma" in low.chat_repo.lower()
    assert mid.chat_repo != high.chat_repo or mid.note != high.note
    assert "12b" in high.chat_repo.lower() or "gemma" in high.chat_repo.lower()
    assert high.embed_repo == "ggml-org/embeddinggemma-2-GGUF"
    # Try-out defaults must be public mirrors (no HF_TOKEN).
    assert not mid.chat_repo.startswith("google/")
    assert not high.chat_repo.startswith("google/")
    assert mid.chat_repo.startswith("bartowski/")
    assert high.chat_repo.startswith("bartowski/")


def test_prefer_public_pick_remaps_gated_google_without_token():
    from spock_onboarding.pick import ModelPick, prefer_public_pick

    gated = ModelPick(
        "ggml-org/embeddinggemma-2-GGUF",
        "google/gemma-3-4b-it-qat-q4_0-gguf",
        "Q8_0",
        "Q4_0",
        2048,
        16384,
        "fit shortlist",
    )
    out = prefer_public_pick(gated, token=None)
    assert out.chat_repo == "bartowski/gemma-3-4b-it-GGUF"
    assert out.chat_quant == "Q4_K_M"
    kept = prefer_public_pick(gated, token="hf_test")
    assert kept.chat_repo.startswith("google/")


def test_write_and_format_readiness(tmp_path: Path):
    path = write_readiness(
        tmp_path,
        ui_ready=True,
        servers_ready=False,
        reasons=["SERVERS_NOT_READY"],
        next_ui_prompts=["hf_token"],
        embed={"port": 8080, "reachable": False},
        chat={"port": 8081, "reachable": False},
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["ui_ready"] is True
    assert data["servers_ready"] is False
    text = format_status_text(data)
    assert "ui_ready" in text
    assert "SERVERS_NOT_READY" in text


def test_first_models_state_roundtrip(tmp_path: Path):
    st = FirstModelsState(
        root=tmp_path,
        llama_server_path=r"tools\llama-server\llama-server.exe",
        embed_gguf_path=str(tmp_path / "e.gguf"),
        chat_gguf_path=str(tmp_path / "c.gguf"),
        embed_n_ctx=4096,
        chat_n_ctx=8192,
        pick_note="test",
    )
    st.write_summary_json()
    loaded = FirstModelsState.load(tmp_path)
    assert loaded is not None
    assert loaded.llama_server_path.endswith("llama-server.exe")
    assert loaded.embed_n_ctx == 4096


@patch("spock_bringup.ensure_llama_server", return_value=r"C:\llama\llama-server.exe")
@patch("spock_bringup.download_pair")
@patch("spock_bringup.pick_model_pair")
@patch("spock_bringup.resolve_hf_token", return_value="hf_test")
@patch("spock_bringup.llmfit_bridge.available", return_value=False)
def test_cmd_acquire_mocked(
    _avail, _tok, mock_pick, mock_dl, _ensure, tmp_path: Path
):
    mock_pick.return_value = ModelPick(
        "Qwen/Qwen3-Embedding-0.6B-GGUF",
        "Qwen/Qwen3-1.7B-GGUF",
        "Q8_0",
        "Q4_K_M",
        4096,
        8192,
        "test pick",
    )
    mock_dl.return_value = (tmp_path / "e.gguf", tmp_path / "c.gguf")
    (tmp_path / "e.gguf").write_bytes(b"x")
    (tmp_path / "c.gguf").write_bytes(b"x")
    result = cmd_acquire(tmp_path, cb=lambda _m: None)
    assert result["ok"] is True
    assert (tmp_path / "first_models_last.json").is_file()


@patch("spock_bringup.probe_embed_chat")
@patch("spock_bringup.check_ui_ready")
@patch("spock_bringup.resolve_hf_token", return_value=None)
def test_cmd_status_writes_ready(mock_tok, mock_ui, mock_probe, tmp_path: Path):
    mock_ui.return_value = {
        "ui_ready": False,
        "venv_python": "",
        "detail": "missing .venv",
    }
    mock_probe.return_value = {
        "embed": {"reachable": False, "port": 8080},
        "chat": {"reachable": False, "port": 8081},
        "servers_ready": False,
    }
    result = cmd_status(tmp_path, cb=lambda _m: None)
    assert result["ok"] is False
    assert (tmp_path / "spock_ready_last.json").is_file()
    data = result["readiness"]
    assert "NEED_ACQUIRE" in data["reasons"]


def test_phase_a_cli_uses_bootstrap_sh_on_posix(tmp_path: Path):
    with patch("spock_bringup_menu.steps.os.name", "posix"):
        cmd = build_cli_command(1, tmp_path)
    assert cmd is not None
    assert cmd[0] == "bash"
    assert cmd[1].endswith("bootstrap.sh")
    assert "--phase-a" in cmd
    assert "--install-root" in cmd


def test_phase_a_cli_uses_powershell_on_windows(tmp_path: Path):
    with patch("spock_bringup_menu.steps.os.name", "nt"):
        with patch(
            "spock_bringup_menu.steps.powershell_exe",
            return_value="powershell.exe",
        ):
            cmd = build_cli_command(1, tmp_path)
    assert cmd is not None
    assert "powershell.exe" in cmd[0]
    assert str(tmp_path / "bootstrap.ps1") in cmd


def test_spawn_wiki_scan_uses_venv_module(tmp_path: Path):
    cmd = build_spawn_command(9, tmp_path)
    assert cmd is not None
    assert "-m" in cmd
    assert "spock_wiki_adapter" in cmd
