"""Planning must follow live hardware when ship_computer.db changes machines.

A stored recipe carries the hardware snapshot it was created from. Sizing models
or launch flags from that snapshot picks models for the machine that is no longer
there, which is what happens when the database is copied to another box.
"""

import tempfile
from pathlib import Path

from model_pick_policy import catalog_rows, recipe_role_budget, top_role_fits
from WarpCore import host_recipe as hr

WORKSTATION = {
    "host_ram_gb": 127.7,
    "gpu_count": 1,
    "gpus": [{"index": 0, "name": "Quadro RTX 6000", "vram_gb": 22.5, "vendor": "nvidia"}],
    "gpu_summary": "[0] Quadro RTX 6000 (22GB)",
}
SECOND_BOX = {
    "host_ram_gb": 32.0,
    "gpu_count": 2,
    "gpus": [
        {"index": 0, "name": "RTX 3060", "vram_gb": 12.0, "vendor": "nvidia"},
        {"index": 1, "name": "RTX 3060", "vram_gb": 12.0, "vendor": "nvidia"},
    ],
    "gpu_summary": "[0] RTX 3060 (12GB) [1] RTX 3060 (12GB)",
}
# Display GPU 0 + compute GPU 1 (both may expose CUDA; user picks AI card).
VIDEO_PLUS_COMPUTE = {
    "host_ram_gb": 64.0,
    "gpu_count": 2,
    "gpus": [
        {
            "index": 0,
            "name": "Quadro P2200",
            "vram_gb": 5.0,
            "vendor": "nvidia",
            "cuda_index": 0,
        },
        {
            "index": 1,
            "name": "Quadro RTX 6000",
            "vram_gb": 22.5,
            "vendor": "nvidia",
            "cuda_index": 1,
        },
    ],
    "gpu_summary": "[0] Quadro P2200 (5GB), [1] Quadro RTX 6000 (22GB)",
}


def _fresh_db() -> str:
    return str(Path(tempfile.mkdtemp()) / "ship_computer.db")


def _db_on_workstation() -> str:
    db = _fresh_db()
    hr.create_recipe(
        db,
        hardware=WORKSTATION,
        recipe=hr.propose_recipe(WORKSTATION),
        reason="initial",
        created_by="test",
    )
    return db


def test_default_primary_ai_gpu_prefers_largest_cuda_card():
    assert hr.default_primary_ai_gpu_index(VIDEO_PLUS_COMPUTE) == 1
    rows = hr.gpu_choice_rows(VIDEO_PLUS_COMPUTE)
    assert len(rows) == 2
    assert "P2200" in rows[0]["label"]
    assert "RTX 6000" in rows[1]["label"]


def test_gpu_index_zero_is_valid():
    """Regression: ``index or -1`` treated GPU 0 as missing."""
    assert hr._gpu_index({"index": 0}, -1) == 0
    rows = hr.gpu_choice_rows(VIDEO_PLUS_COMPUTE)
    assert any(int(r["index"]) == 0 for r in rows if r.get("index") is not None)
    pinned = hr.apply_primary_ai_gpu(
        hr.propose_recipe(VIDEO_PLUS_COMPUTE), 0, hardware=VIDEO_PLUS_COMPUTE
    )
    assert pinned["embed_gpu_index"] == 0
    assert pinned["chat_gpu_index"] == 0


def test_apply_primary_ai_gpu_pins_both_roles_to_compute_card():
    proposed = hr.propose_recipe(VIDEO_PLUS_COMPUTE)
    pinned = hr.apply_primary_ai_gpu(proposed, 1, hardware=VIDEO_PLUS_COMPUTE)
    assert pinned["embed_gpu_index"] == 1
    assert pinned["chat_gpu_index"] == 1
    assert pinned["gpu_policy"] == "single_gpu"
    assert pinned["tensor_split"] == ""
    assert any("primary AI GPU 1" in n for n in pinned["notes"])


def test_creates_a_recipe_when_the_database_has_none_single_gpu():
    plan = hr.effective_recipe(_fresh_db(), live=WORKSTATION)
    assert plan["source"] == "created"
    assert plan["drift"] == []
    assert plan["hardware"] is WORKSTATION
    assert plan["recipe"]["gpu_policy"] == "single_gpu"


def test_multi_gpu_does_not_silent_create_without_primary():
    db = _fresh_db()
    plan = hr.effective_recipe(db, live=SECOND_BOX)
    assert plan["source"] == "needs-primary"
    assert plan["stored"] is None
    assert hr.get_current_recipe(db) is None
    assert plan["recipe"]["gpu_policy"] == "tensor_split_chat"
    row, action, drift = hr.ensure_recipe(db, hardware=SECOND_BOX)
    assert row is None and action == "needs-primary" and drift == []


def test_needs_primary_prompt_until_user_confirms():
    assert hr.needs_primary_ai_gpu_prompt(VIDEO_PLUS_COMPUTE, None)
    proposed = hr.propose_recipe(VIDEO_PLUS_COMPUTE)
    assert hr.needs_primary_ai_gpu_prompt(VIDEO_PLUS_COMPUTE, proposed)
    pinned = hr.apply_primary_ai_gpu(proposed, 1, hardware=VIDEO_PLUS_COMPUTE)
    assert pinned["primary_ai_gpu_confirmed"] is True
    assert not hr.needs_primary_ai_gpu_prompt(VIDEO_PLUS_COMPUTE, pinned)


def test_unchanged_hardware_uses_the_stored_recipe():
    plan = hr.effective_recipe(_db_on_workstation(), live=WORKSTATION)
    assert plan["source"] == "current"
    assert plan["drift"] == []
    assert plan["recipe"]["gpu_policy"] == "single_gpu"


def test_moved_database_plans_for_the_live_machine():
    db = _db_on_workstation()
    plan = hr.effective_recipe(db, live=SECOND_BOX)

    assert plan["source"] == "live-proposal"
    assert plan["drift"], "moving to different hardware must be reported"
    # The stale single-GPU policy cannot describe two cards.
    assert plan["recipe"]["gpu_policy"] == "tensor_split_chat"
    assert plan["recipe"]["tensor_split"] == "0.5,0.5"
    assert plan["recipe"]["chat_n_ctx"] == 16384
    assert plan["hardware"]["host_ram_gb"] == 32.0


def test_planning_never_reads_the_stored_hardware_snapshot():
    db = _db_on_workstation()
    plan = hr.effective_recipe(db, live=SECOND_BOX)
    embed = recipe_role_budget(plan["recipe"], plan["hardware"], role="embed")
    stored = hr.get_current_recipe(db)
    stale = recipe_role_budget(stored["recipe"], stored["hardware"], role="embed")

    # One 3060, not the 22.5 GB card that created the recipe.
    assert embed["pool_gb"] == 12.0
    assert stale["pool_gb"] == 22.5
    assert embed["budget_gb"] < stale["budget_gb"]


def test_moved_database_stops_offering_models_that_need_the_old_card():
    """A 22 GB card fits an 8B embed at Q8_0; a 12 GB card does not."""
    db = _db_on_workstation()
    plan = hr.effective_recipe(db, live=SECOND_BOX)
    budget = recipe_role_budget(plan["recipe"], plan["hardware"], role="embed")
    picks = top_role_fits(catalog_rows("embedding"), kind="embedding", budget=budget, limit=3)

    assert picks, "the shortlist must still offer something"
    for pick in picks:
        assert pick["need_gb"] <= budget["budget_gb"]
        assert pick["fit_level"] != "impossible"


def test_effective_recipe_leaves_the_stored_version_alone():
    db = _db_on_workstation()
    before = hr.get_current_recipe(db)
    hr.effective_recipe(db, live=SECOND_BOX)
    hr.effective_recipe(db, live=SECOND_BOX)
    after = hr.get_current_recipe(db)

    assert after["version"] == before["version"] == 1
    assert after["recipe"]["gpu_policy"] == "single_gpu"
    assert len(hr.list_recipe_history(db)) == 1


def test_saving_edits_while_drifted_builds_on_the_live_proposal():
    """What Launch's SAVE TO RECIPE does after the database changes machines.

    The edits are the user's; the hardware and the fields they did not touch
    must come from this host, never from the recipe made on the old one.
    """
    db = _db_on_workstation()
    plan = hr.effective_recipe(db, live=SECOND_BOX)
    edited = dict(plan["recipe"])
    edited["chat_n_ctx"] = 12288

    row = hr.update_recipe(
        db,
        reason="Launch panel: tensor_split_chat, chat -c 12288",
        hardware=plan["hardware"],
        recipe=edited,
        created_by="launch-panel",
    )

    assert row["recipe"]["chat_n_ctx"] == 12288, "the edit is kept"
    assert row["recipe"]["gpu_policy"] == "tensor_split_chat"
    assert row["recipe"]["tensor_split"] == "0.5,0.5"
    assert row["hardware"]["gpu_count"] == 2, "saved against the live host"
    assert hr.effective_recipe(db, live=SECOND_BOX)["source"] == "current"


def test_explicit_update_records_the_move_and_clears_the_drift():
    db = _db_on_workstation()
    drift = hr.hardware_drift(hr.get_current_recipe(db), live=SECOND_BOX)
    row = hr.apply_drift_update(db, live=SECOND_BOX, drift=drift, created_by="test")

    assert row["version"] == 2
    assert row["recipe"]["gpu_policy"] == "tensor_split_chat"
    assert "Hardware drift" in row["reason"]
    assert "GPU count 2" in row["reason"], "the audit line names what changed"
    assert hr.effective_recipe(db, live=SECOND_BOX)["source"] == "current"
    # History keeps the workstation version.
    versions = {r["version"]: r["recipe"]["gpu_policy"] for r in hr.list_recipe_history(db)}
    assert versions == {1: "single_gpu", 2: "tensor_split_chat"}
