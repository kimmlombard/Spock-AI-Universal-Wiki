"""Linux ↔ Windows Spock_Console path healing after ship_computer.db moves."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from WarpCore import path_relocate as pr
from WarpCore import settings_store as st


def test_relocate_posix_to_windows_style(tmp_path: Path, monkeypatch):
    root = tmp_path / "Spock-AI-Universal-Wiki"
    models = root / "models" / "embeddinggemma-2-GGUF"
    models.mkdir(parents=True)
    gguf = models / "embeddinggemma-2-Q8_0.gguf"
    gguf.write_bytes(b"gguf")
    (root / "tools" / "llama-server").mkdir(parents=True)
    llama = root / "tools" / "llama-server" / "llama-server.exe"
    llama.write_bytes(b"MZ")

    # Only stub host_os_name — do not patch os.name (breaks pathlib on Linux).
    monkeypatch.setattr(pr, "host_os_name", lambda: "nt")

    foreign = "/home/kimml/src/Spock-AI-Universal-Wiki/models/embeddinggemma-2-GGUF/embeddinggemma-2-Q8_0.gguf"
    out = pr.relocate_path(
        foreign,
        new_root=root,
        old_root="/home/kimml/src/Spock-AI-Universal-Wiki",
    )
    assert out is not None
    assert Path(out) == gguf.resolve()
    assert "\\" in out or out.lower().endswith(".gguf")


def test_relocate_windows_to_posix(tmp_path: Path, monkeypatch):
    root = tmp_path / "Spock-AI-Universal-Wiki"
    models = root / "models" / "foo"
    models.mkdir(parents=True)
    gguf = models / "a.gguf"
    gguf.write_bytes(b"x")

    monkeypatch.setattr(pr, "host_os_name", lambda: "posix")

    foreign = r"D:\Spock-AI-Universal-Wiki\models\foo\a.gguf"
    out = pr.relocate_path(
        foreign,
        new_root=root,
        old_root=r"D:\Spock-AI-Universal-Wiki",
    )
    assert out is not None
    assert Path(out) == gguf.resolve()


def test_heal_spock_console_roundtrip(tmp_path: Path, monkeypatch):
    root = tmp_path / "Spock-AI-Universal-Wiki"
    root.mkdir()
    db = root / "ship_computer.db"
    (root / "models" / "m").mkdir(parents=True)
    gguf = root / "models" / "m" / "x.gguf"
    gguf.write_bytes(b"g")
    (root / "tools" / "llama-server").mkdir(parents=True)
    llama = root / "tools" / "llama-server" / "llama-server"
    llama.write_bytes(b"ELF")
    (root / "captured_files").mkdir()

    st.set(
        str(db),
        "app.embedding_profile.model_path",
        "/home/old/Spock-AI-Universal-Wiki/models/m/x.gguf",
        by="test",
    )
    st.set(
        str(db),
        "app.mcp.llama_server_path",
        "/home/old/Spock-AI-Universal-Wiki/tools/llama-server/llama-server",
        by="test",
    )
    st.set(
        str(db),
        "scan.scan_roots",
        ["/home/old/Spock-AI-Universal-Wiki"],
        by="test",
    )
    st.set(
        str(db),
        "app.uieg.capture_folder",
        "/home/old/Spock-AI-Universal-Wiki/captured_files",
        by="test",
    )
    st.set(
        str(db),
        "onboarding.first_models",
        {
            "llama_server_path": "/home/old/Spock-AI-Universal-Wiki/tools/llama-server/llama-server",
            "embed_gguf_path": "/home/old/Spock-AI-Universal-Wiki/models/m/x.gguf",
        },
        by="test",
    )
    st.set(str(db), "settings.spock_root", "/home/old/Spock-AI-Universal-Wiki", by="test")
    st.set(str(db), "settings.host_os", "posix", by="test")

    # Simulate landing on this host (posix tmp) from another posix root.
    monkeypatch.setattr(pr, "host_os_name", lambda: "posix")
    pr._HEAL_CACHE.clear()
    report = pr.heal_relocated_paths(str(db), root=root, by="test", force=True)
    assert report["updated_keys"] >= 3

    assert Path(st.get(str(db), "app.embedding_profile.model_path")) == gguf.resolve()
    assert Path(st.get(str(db), "app.mcp.llama_server_path")) == llama.resolve()
    roots = st.get(str(db), "scan.scan_roots")
    assert roots == [str(root.resolve())]
    assert Path(st.get(str(db), "settings.spock_root")) == root.resolve()

    # Idempotent second pass
    pr._HEAL_CACHE.clear()
    report2 = pr.heal_relocated_paths(str(db), root=root, by="test")
    assert report2.get("skipped") is True or report2.get("updated_keys", 0) == 0


def test_heal_first_models_json(tmp_path: Path, monkeypatch):
    root = tmp_path / "Spock-AI-Universal-Wiki"
    root.mkdir()
    db = root / "ship_computer.db"
    (root / "models").mkdir()
    gguf = root / "models" / "a.gguf"
    gguf.write_bytes(b"g")
    fm = {
        "embed_gguf_path": "/home/x/Spock-AI-Universal-Wiki/models/a.gguf",
        "chat_gguf_path": "/home/x/Spock-AI-Universal-Wiki/models/a.gguf",
    }
    (root / "first_models_last.json").write_text(json.dumps(fm), encoding="utf-8")
    st.set(str(db), "settings.spock_root", "/home/x/Spock-AI-Universal-Wiki", by="test")
    st.set(str(db), "settings.host_os", "posix", by="test")
    monkeypatch.setattr(pr, "host_os_name", lambda: "posix")
    pr._HEAL_CACHE.clear()
    pr.heal_relocated_paths(str(db), root=root, by="test", force=True)
    data = json.loads((root / "first_models_last.json").read_text(encoding="utf-8"))
    assert Path(data["embed_gguf_path"]) == gguf.resolve()


def test_skips_urls_and_external_windows_tools(tmp_path: Path, monkeypatch):
    root = tmp_path / "Spock"
    root.mkdir()
    monkeypatch.setattr(pr, "host_os_name", lambda: "posix")
    assert (
        pr.relocate_path("http://localhost:8080/embeddings", new_root=root) is None
    )
    # External Win path with no Spock anchor — leave alone on Linux
    assert (
        pr.relocate_path(
            r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
            new_root=root,
            old_root=r"D:\Spock",
        )
        is None
    )
