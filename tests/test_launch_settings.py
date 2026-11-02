"""Pinned Launch flags: portable knobs in settings, hardware shape in the recipe.

``app.launch.*`` holds what the user typed and means the same thing on any
machine (``-ngl``, embed ``-np``). GPU policy, tensor-split and ``-c`` stay with
the host recipe, which is re-proposed when the hardware changes — so a pin must
survive a move while a stale tensor-split must not.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from WarpCore import host_recipe as hr
from WarpCore import settings_store
from WarpCore.config_defaults import DEFAULT_LAUNCH_SETTINGS, merge_launch_settings

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


def _fresh_db() -> str:
    return str(Path(tempfile.mkdtemp()) / "ship_computer.db")


def _pin(db: str, **pins) -> None:
    settings_store.set_many(
        db, {f"app.launch.{k}": v for k, v in pins.items()}, by="test"
    )


# ── merge_launch_settings ────────────────────────────────────────────────
def test_defaults_leave_ngl_on_auto():
    assert merge_launch_settings(None) == {
        "ngl": "-1",
        "embed_np": 1,
        "flash_attn": True,
        "cache_type_k": "q8_0",
        "cache_type_v": "q8_0",
        "reasoning": "off",
        "llama_gui_embed_command": "",
        "llama_gui_chat_command": "",
    }
    assert merge_launch_settings({}) == dict(DEFAULT_LAUNCH_SETTINGS)


def test_ngl_accepts_the_shapes_a_settings_row_can_hold():
    assert merge_launch_settings({"ngl": "99"})["ngl"] == "99"
    assert merge_launch_settings({"ngl": 99})["ngl"] == "99"
    assert merge_launch_settings({"ngl": " 99 "})["ngl"] == "99"
    assert merge_launch_settings({"ngl": "auto"})["ngl"] == "-1"
    assert merge_launch_settings({"ngl": ""})["ngl"] == "-1"


def test_nonsense_ngl_falls_back_to_auto_rather_than_reaching_llama_server():
    for bad in ("1000", "-5", "abc", None, [1]):
        assert merge_launch_settings({"ngl": bad})["ngl"] == "-1"


def test_embed_np_is_clamped_to_the_slots_the_panel_offers():
    assert merge_launch_settings({"embed_np": 4})["embed_np"] == 4
    assert merge_launch_settings({"embed_np": "4"})["embed_np"] == 4
    assert merge_launch_settings({"embed_np": 0})["embed_np"] == 1
    assert merge_launch_settings({"embed_np": 99})["embed_np"] == 16
    assert merge_launch_settings({"embed_np": "x"})["embed_np"] == 1


# ── launch_plan_for_role ─────────────────────────────────────────────────
def test_unpinned_launch_leaves_ngl_for_llmfit_to_answer():
    db = _fresh_db()
    recipe = hr.propose_recipe(WORKSTATION)
    plan = hr.launch_plan_for_role(db, recipe, "chat")

    assert plan["ngl"] == "-1", "-1 is what makes the manager ask llmfit"
    assert plan["ngl_source"] == ""


def test_pinned_ngl_overrides_the_recipe_default():
    db = _fresh_db()
    _pin(db, ngl="99")
    plan = hr.launch_plan_for_role(db, hr.propose_recipe(WORKSTATION), "chat")

    assert plan["ngl"] == "99"
    assert "app.launch.ngl" in plan["ngl_source"]


def test_pinned_embed_np_applies_to_the_embedding_server_only():
    db = _fresh_db()
    _pin(db, embed_np=4)
    recipe = hr.propose_recipe(WORKSTATION)

    assert hr.launch_plan_for_role(db, recipe, "embedding")["n_parallel"] == 4
    assert hr.launch_plan_for_role(db, recipe, "chat")["n_parallel"] is None


def test_the_recipe_still_owns_the_hardware_shape():
    db = _fresh_db()
    _pin(db, ngl="99", embed_np=2)
    recipe = hr.propose_recipe(SECOND_BOX)
    plan = hr.launch_plan_for_role(db, recipe, "chat")

    assert plan["tensor_split"] == "0.5,0.5"
    assert plan["split_mode"] == "layer"
    assert plan["pin_cuda"] is False
    assert plan["n_ctx"] == recipe["chat_n_ctx"]


def test_pins_survive_a_move_but_a_stale_tensor_split_does_not():
    """The pin is a layer cap; the split names cards this machine may not have."""
    db = _fresh_db()
    hr.create_recipe(
        db,
        hardware=SECOND_BOX,
        recipe=hr.propose_recipe(SECOND_BOX),
        reason="made on the dual-3060 box",
        created_by="test",
    )
    _pin(db, ngl="99")
    moved = hr.effective_recipe(db, live=WORKSTATION)
    plan = hr.launch_plan_for_role(db, moved["recipe"], "chat")

    assert moved["source"] == "live-proposal"
    assert plan["ngl"] == "99", "a pinned layer count is portable"
    assert plan["tensor_split"] == "", "the 3060 pair's split must not follow"
    assert plan["cuda_device"] == "0"


def test_chat_plan_enables_flash_attn_and_q8_kv_and_embed_omits_them():
    db = _fresh_db()
    recipe = hr.propose_recipe(WORKSTATION)
    chat = hr.launch_plan_for_role(db, recipe, "chat")
    embed = hr.launch_plan_for_role(db, recipe, "embedding")

    assert chat["flash_attn"] is True
    assert chat["cache_type_k"] == "q8_0"
    assert chat["cache_type_v"] == "q8_0"
    assert chat["n_cpu_moe"] == 0
    assert chat["reasoning"] == "off"
    assert embed["flash_attn"] is False
    assert embed["cache_type_k"] == ""
    assert embed["cache_type_v"] == ""
    assert embed["n_cpu_moe"] == 0
    assert "reasoning" not in embed


def test_pinned_off_attention_flags_stay_off():
    db = _fresh_db()
    _pin(db, flash_attn=False, cache_type_k="", cache_type_v="f16")
    plan = hr.launch_plan_for_role(db, hr.propose_recipe(WORKSTATION), "chat")
    assert plan["flash_attn"] is False
    assert plan["cache_type_k"] == ""
    assert plan["cache_type_v"] == "f16"

    from llama_server_manager import attention_launch_args

    assert attention_launch_args("chat", True, "q8_0", "q8_0") == [
        "--flash-attn",
        "on",
        "-ctk",
        "q8_0",
        "-ctv",
        "q8_0",
    ]
    assert attention_launch_args("chat", False, "", "") == []
    assert attention_launch_args("embedding", True, "q8_0", "q8_0") == []
    assert attention_launch_args("chat") == [
        "--flash-attn",
        "on",
        "-ctk",
        "q8_0",
        "-ctv",
        "q8_0",
    ]


def test_loopback_lm_studio_blocks_llama_launch():
    from llama_server_manager import loopback_blocks_llama

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"error":"Unexpected endpoint or method. (GET /health)"}'

    with patch("llama_server_manager.urllib.request.urlopen", return_value=_Resp()):
        msg = loopback_blocks_llama(8081)
    assert "LM Studio" in msg
    assert "127.0.0.1:8081" in msg


def test_missing_settings_table_falls_back_to_defaults():
    plan = hr.launch_plan_for_role(
        str(Path(tempfile.mkdtemp()) / "nope.db"), hr.propose_recipe(WORKSTATION), "chat"
    )
    assert plan["ngl"] == "-1"
    assert plan["flash_attn"] is True
    assert plan["cache_type_k"] == "q8_0"
    assert plan["reasoning"] == "off"
    assert plan["n_cpu_moe"] == 0


# ── round-trip into app_config.json ──────────────────────────────────────
def test_pins_export_into_app_config_json():
    db = _fresh_db()
    _pin(db, ngl="99", embed_np=2)
    out_dir = tempfile.mkdtemp()
    written = settings_store.export_to_json(db, out_dir)

    payload = json.loads(Path(written["app_config.json"]).read_text(encoding="utf-8"))
    assert payload["launch"] == {
        "ngl": "99",
        "embed_np": 2,
        "flash_attn": True,
        "cache_type_k": "q8_0",
        "cache_type_v": "q8_0",
        "reasoning": "off",
        "llama_gui_embed_command": "",
        "llama_gui_chat_command": "",
    }


def test_app_config_exposes_launch_pins_to_readers():
    db = _fresh_db()
    settings_store.set(db, "app.theme", "dark", by="test")
    _pin(db, ngl="99")

    assert settings_store.load_app_config(db)["launch"]["ngl"] == "99"
    assert settings_store.load_app_config(db)["launch"]["reasoning"] == "off"


def test_reasoning_pin_accepts_off_auto_on_and_drops_anything_else():
    assert merge_launch_settings({"reasoning": "auto"})["reasoning"] == "auto"
    assert merge_launch_settings({"reasoning": "ON"})["reasoning"] == "on"
    assert merge_launch_settings({"reasoning": "off"})["reasoning"] == "off"
    assert merge_launch_settings({"reasoning": "64"})["reasoning"] == "off"
    assert merge_launch_settings({"reasoning": ""})["reasoning"] == "off"


def test_dual_small_gpus_propose_ncmoe_and_chat_plan_keeps_it():
    recipe = hr.propose_recipe(SECOND_BOX)
    assert recipe["n_cpu_moe"] == 28
    assert hr.propose_recipe(WORKSTATION)["n_cpu_moe"] == 0

    db = _fresh_db()
    chat = hr.launch_plan_for_role(db, recipe, "chat")
    embed = hr.launch_plan_for_role(db, recipe, "embedding")

    assert chat["n_cpu_moe"] == 28
    assert chat["reasoning"] == "off"
    assert embed["n_cpu_moe"] == 0
    assert "reasoning" not in embed


def test_a_saved_recipe_without_n_cpu_moe_does_not_start_offloading():
    recipe = hr.propose_recipe(SECOND_BOX)
    recipe.pop("n_cpu_moe")
    plan = hr.launch_plan_for_role(_fresh_db(), recipe, "chat")
    assert plan["n_cpu_moe"] == 0
