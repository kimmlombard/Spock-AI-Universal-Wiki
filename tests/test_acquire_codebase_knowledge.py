"""Tests for acquire_codebase_knowledge skill (deterministic scan + docs)."""

from __future__ import annotations

from pathlib import Path

from WarpCore.skills import validate_payload
from spock_codebase_knowledge import DOC_NAMES, acquire_codebase_knowledge


def test_validate_payload_requires_root():
    try:
        validate_payload("acquire_codebase_knowledge", {})
        assert False, "expected ValueError"
    except ValueError as e:
        assert "root_path" in str(e)


def test_validate_payload_defaults():
    p = validate_payload(
        "acquire_codebase_knowledge", {"root_path": r"D:\example"}
    )
    assert p["root_path"] == r"D:\example"
    assert p["output_rel"] == "docs/codebase"
    assert p["ingest"] is True
    assert p["focus"] == ""


def test_acquire_writes_seven_docs(tmp_path: Path):
    (tmp_path / "README.md").write_text(
        "# Demo\n\nA tiny project for Spock acquire tests.\n", encoding="utf-8"
    )
    (tmp_path / "main.py").write_text("def main():\n    return 42\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("requests==2.0.0\nPyQt6>=6.0\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("models/\ndata/\n.venv/\n", encoding="utf-8")
    # Noise that must not dominate TODOs / tree
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "blob.cpp").write_text("// TODO: noise\n", encoding="utf-8")
    (tmp_path / "models").mkdir()
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "__main__.py").write_text("print('hi')\n", encoding="utf-8")

    result = acquire_codebase_knowledge(str(tmp_path), focus="structure")
    assert result["ok"] is True
    assert "data" in result["skip_dirs"]
    assert "models" in result["skip_dirs"]
    out = Path(result["output_dir"])
    stack = (out / "STACK.md").read_text(encoding="utf-8")
    assert "requests" in stack
    assert "PyQt6" in stack
    assert "[VALUE]" not in stack
    assert "Demo" in stack
    structure = (out / "STRUCTURE.md").read_text(encoding="utf-8")
    assert "pkg" in structure
    assert "Focus area: structure" in structure
    scan = (out / ".codebase-scan.txt").read_text(encoding="utf-8")
    assert "data\\blob.cpp" not in scan and "data/blob.cpp" not in scan
    concerns = (out / "CONCERNS.md").read_text(encoding="utf-8")
    assert "blob.cpp" not in concerns


def test_split_scan_sections_understands_equals_headings():
    from spock_codebase_knowledge.populate import split_scan_sections

    text = "pre\n=== STACK DETECTION (manifest files) ===\nhello\n=== ENTRY POINTS ===\nFound: main.py\n"
    secs = split_scan_sections(text)
    assert "STACK DETECTION (MANIFEST FILES)" in secs or any(
        "STACK" in k for k in secs
    )
    assert any("ENTRY" in k for k in secs)
    entry_key = next(k for k in secs if "ENTRY" in k)
    assert "main.py" in secs[entry_key]
