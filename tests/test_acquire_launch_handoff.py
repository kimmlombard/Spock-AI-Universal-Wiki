"""Acquire → RAG → Launch handoff: -c must reach the host recipe.

USE ACQUIRE RESULT used to copy only the embedding GGUF path. Deep Dive then
kept launching with the previous machine's chat -c / single-GPU pin, which on a
dual-3060 host leaves both servers on CUDA 0 and packs almost no context.
"""

import json
import tempfile
from pathlib import Path

from model_selector_core import (
    acquire_embedding_result,
    sync_acquire_n_ctx_to_recipe,
)
from WarpCore import host_recipe as hr

WORKSTATION = {
    "host_ram_gb": 127.7,
    "gpu_count": 1,
    "gpus": [{"index": 0, "name": "Quadro RTX 6000", "vram_gb": 22.5}],
    "gpu_summary": "[0] Quadro RTX 6000 (22GB)",
}
SECOND_BOX = {
    "host_ram_gb": 32.0,
    "gpu_count": 2,
    "gpus": [
        {"index": 0, "name": "RTX 3060", "vram_gb": 12.0},
        {"index": 1, "name": "RTX 3060", "vram_gb": 12.0},
    ],
    "gpu_summary": "[0] RTX 3060 (12GB) [1] RTX 3060 (12GB)",
}


def _write_acquire(root: Path, **fields) -> None:
    payload = {
        "embed_gguf_path": str(root / "embed.gguf"),
        "embed_model_id": "Qwen/Qwen3-Embedding-8B-GGUF",
        "chat_gguf_path": str(root / "chat.gguf"),
        "chat_model_id": "Qwen/Qwen3-14B-GGUF",
        "embed_n_ctx": 4096,
        "chat_n_ctx": 8192,
        "embed_quant": "Q4_K_M",
        "chat_quant": "Q4_K_M",
        "embed_dim": 4096,
    }
    payload.update(fields)
    (root / "first_models_last.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_acquire_result_exposes_both_roles_n_ctx(tmp_path: Path):
    _write_acquire(tmp_path, embed_n_ctx=4096, chat_n_ctx=8192)
    info = acquire_embedding_result(str(tmp_path))
    assert info["embed_n_ctx"] == 4096
    assert info["chat_n_ctx"] == 8192
    assert info["model_id"] == "Qwen/Qwen3-Embedding-8B-GGUF"
    assert info["chat_model_id"] == "Qwen/Qwen3-14B-GGUF"


def test_use_acquire_result_writes_n_ctx_onto_the_host_recipe():
    db = str(Path(tempfile.mkdtemp()) / "ship_computer.db")
    hr.create_recipe(
        db,
        hardware=SECOND_BOX,
        recipe=hr.propose_recipe(SECOND_BOX),
        reason="dual 3060",
        created_by="test",
    )
    # Pass live= so this test is not rewritten by the workstation probe.
    out = sync_acquire_n_ctx_to_recipe(
        db, embed_n_ctx=4096, chat_n_ctx=8192, live=SECOND_BOX
    )
    assert out["recipe"]["embed_n_ctx"] == 4096
    assert out["recipe"]["chat_n_ctx"] == 8192
    assert out["recipe"]["gpu_policy"] == "tensor_split_chat"
    assert out["recipe"]["tensor_split"] == "0.5,0.5"


def test_stale_workstation_ctx_is_capped_on_the_3060_box():
    """first_models_last.json can still carry the old machine's chat -c."""
    db = str(Path(tempfile.mkdtemp()) / "ship_computer.db")
    hr.create_recipe(
        db,
        hardware=WORKSTATION,
        recipe=hr.propose_recipe(WORKSTATION),
        reason="workstation",
        created_by="test",
    )
    out = sync_acquire_n_ctx_to_recipe(
        db,
        embed_n_ctx=4096,
        chat_n_ctx=32768,
        created_by="test",
        live=SECOND_BOX,
    )
    assert out["updated"] is True
    assert out["recipe"]["gpu_policy"] == "tensor_split_chat"
    assert out["recipe"]["chat_n_ctx"] == 16384
    assert out["recipe"]["tensor_split"] == "0.5,0.5"
    assert hr.effective_recipe(db, live=SECOND_BOX)["source"] == "current"


def test_launch_plan_for_dual_box_does_not_pin_chat_to_one_card():
    recipe = hr.propose_recipe(SECOND_BOX)
    db = str(Path(tempfile.mkdtemp()) / "ship_computer.db")
    hr.create_recipe(
        db, hardware=SECOND_BOX, recipe=recipe, reason="dual", created_by="test"
    )
    chat = hr.launch_plan_for_role(db, recipe, "chat")
    embed = hr.launch_plan_for_role(db, recipe, "embedding")

    assert chat["tensor_split"] == "0.5,0.5"
    assert chat["pin_cuda"] is False
    assert chat["n_ctx"] == 16384
    assert embed["pin_cuda"] is True
    assert embed["cuda_device"] == "0"
    assert embed["n_ctx"] == 4096


def test_build_server_argv_includes_tensor_split_for_chat():
    from spock_onboarding.llama_process import build_server_argv

    cmd = build_server_argv(
        "llama-server",
        "chat.gguf",
        port=8081,
        n_ctx=8192,
        ngl="99",
        role="chat",
        tensor_split="0.5,0.5",
        split_mode="layer",
    )
    assert "--tensor-split" in cmd
    assert "0.5,0.5" in cmd
    assert "--split-mode" in cmd
    emb = build_server_argv(
        "llama-server",
        "embed.gguf",
        port=8080,
        n_ctx=4096,
        role="embedding",
        tensor_split="0.5,0.5",
        n_parallel=2,
    )
    assert "--tensor-split" not in emb
    assert "-np" in emb and "2" in emb
