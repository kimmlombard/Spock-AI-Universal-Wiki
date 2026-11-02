"""Content reset clears spock_host_recipe and restarts its sqlite_sequence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from WarpCore import host_recipe as hr
from reset import CONTENT_TABLES, PRESERVE_TABLES, reset_content

WORKSTATION = {
    "host_ram_gb": 64.0,
    "gpu_count": 1,
    "gpus": [{"index": 0, "name": "Quadro RTX 6000", "vram_gb": 22.5, "vendor": "nvidia"}],
    "gpu_summary": "[0] Quadro RTX 6000 (22GB)",
}


def test_content_tables_include_host_recipe_not_preserve():
    assert "spock_host_recipe" in CONTENT_TABLES
    assert "spock_host_recipe" not in PRESERVE_TABLES
    assert "spock_profile" in PRESERVE_TABLES
    assert "Spock_Console" in PRESERVE_TABLES


def test_content_reset_nukes_host_recipe_and_sequence(tmp_path: Path):
    db = tmp_path / "ship_computer.db"
    schema = Path(__file__).resolve().parents[1] / "ship_computer_schema.sql"
    assert schema.is_file()

    hr.create_recipe(
        str(db),
        hardware=WORKSTATION,
        recipe=hr.propose_recipe(WORKSTATION),
        reason="seed",
        created_by="test",
    )
    before = hr.get_current_recipe(str(db))
    assert before is not None
    assert int(before.get("id") or 0) >= 1

    reset_content(db_path=db, schema_path=schema)

    assert hr.get_current_recipe(str(db)) is None
    conn = sqlite3.connect(str(db))
    try:
        n = conn.execute("SELECT COUNT(*) FROM spock_host_recipe").fetchone()[0]
        assert n == 0
        seq = conn.execute(
            "SELECT seq FROM sqlite_sequence WHERE name = 'spock_host_recipe'"
        ).fetchone()
        assert seq is None
        ptr = conn.execute(
            "SELECT COUNT(*) FROM Spock_Console WHERE Variable_Name = ?",
            ("app.host_recipe.current_id",),
        ).fetchone()[0]
        assert ptr == 0
    finally:
        conn.close()

    # Next create restarts at version/id 1.
    row = hr.create_recipe(
        str(db),
        hardware=WORKSTATION,
        recipe=hr.propose_recipe(WORKSTATION),
        reason="after reset",
        created_by="test",
    )
    assert int(row.get("id") or 0) == 1
    assert int(row.get("version") or 0) == 1


def test_cli_rebuild_creates_single_gpu_recipe(tmp_path: Path, monkeypatch):
    from reset import rebuild_host_recipe_after_reset

    db = tmp_path / "ship_computer.db"
    monkeypatch.setattr(hr, "probe_hardware", lambda: WORKSTATION)
    rebuild_host_recipe_after_reset(db, interactive=False)
    row = hr.get_current_recipe(str(db))
    assert row is not None
    assert row["recipe"]["primary_ai_gpu_confirmed"] is True


def test_cli_rebuild_multi_gpu_noninteractive_leaves_empty(tmp_path: Path, monkeypatch):
    from reset import rebuild_host_recipe_after_reset

    dual = {
        "host_ram_gb": 32.0,
        "gpu_count": 2,
        "gpus": [
            {"index": 0, "name": "A", "vram_gb": 12.0, "vendor": "nvidia", "cuda_index": 0},
            {"index": 1, "name": "B", "vram_gb": 22.0, "vendor": "nvidia", "cuda_index": 1},
        ],
        "gpu_summary": "[0] A (12GB), [1] B (22GB)",
    }
    db = tmp_path / "ship_computer.db"
    monkeypatch.setattr(hr, "probe_hardware", lambda: dual)
    rebuild_host_recipe_after_reset(db, interactive=False)
    assert hr.get_current_recipe(str(db)) is None
