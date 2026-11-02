"""Session-rooted LLMFit criteria: load/cache, providers allow-list, family preference."""

from __future__ import annotations

import json
from pathlib import Path

import llmfit_session_criteria as crit


def test_default_criteria_prefers_google_gemma(tmp_path: Path, monkeypatch):
    path = tmp_path / "llmfit_session_criteria.json"
    monkeypatch.setenv("SPOCK_LLMFIT_CRITERIA_JSON", str(path))
    crit.clear_criteria_cache()
    data = crit.load_criteria()
    assert path.is_file()
    assert data["filters"]["providers"] == ["Google"]
    assert data["filters"]["provider"] == "Google"
    assert "gemma" in data["chat"]["preferred_families"][0]
    assert data["embed"]["preferred_families"][0] == "embeddinggemma"
    assert data["embed"]["allow_dim_change"] is True


def test_legacy_provider_string_migrates_to_providers(tmp_path: Path, monkeypatch):
    path = tmp_path / "legacy.json"
    monkeypatch.setenv("SPOCK_LLMFIT_CRITERIA_JSON", str(path))
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "filters": {"provider": "Nvidia", "search": "nemotron"},
                "chat": {"preferred_families": ["nemotron"], "fallback_families": []},
                "embed": {"preferred_families": ["nomic"], "fallback_families": []},
            }
        ),
        encoding="utf-8",
    )
    crit.clear_criteria_cache()
    data = crit.load_criteria()
    assert data["filters"]["providers"] == ["Nvidia"]
    assert data["filters"]["provider"] == "Nvidia"


def test_empty_providers_means_all(tmp_path: Path, monkeypatch):
    path = tmp_path / "c.json"
    monkeypatch.setenv("SPOCK_LLMFIT_CRITERIA_JSON", str(path))
    crit.clear_criteria_cache()
    crit.clear_provider_filter(path=str(path))
    assert crit.provider_allowlist() == []
    assert crit.model_id_allowed("Qwen/Qwen3-8B-GGUF")
    assert crit.model_id_allowed("google/gemma-3-12b")
    assert crit.provider_filter_label() == "ALL"


def test_google_allowlist_excludes_qwen_nvidia(tmp_path: Path, monkeypatch):
    path = tmp_path / "c.json"
    monkeypatch.setenv("SPOCK_LLMFIT_CRITERIA_JSON", str(path))
    crit.clear_criteria_cache()
    crit.set_providers(["Google"], path=str(path))
    assert crit.model_id_allowed("google/gemma-3-12b-it-qat-q4_0-gguf")
    assert crit.model_id_allowed("ggml-org/embeddinggemma-2-GGUF")
    assert crit.model_id_allowed(r"D:\models\gemma-3-12b-it-Q4_K_M.gguf")
    assert not crit.model_id_allowed("Qwen/Qwen3-8B-GGUF")
    assert not crit.model_id_allowed("nvidia/NVIDIA-Nemotron-Nano-9B-v2-GGUF")
    assert not crit.model_id_allowed("microsoft/Phi-4-GGUF")


def test_clear_provider_filter_button_semantics(tmp_path: Path, monkeypatch):
    path = tmp_path / "c.json"
    monkeypatch.setenv("SPOCK_LLMFIT_CRITERIA_JSON", str(path))
    crit.clear_criteria_cache()
    crit.set_providers(["Google", "Alibaba"], path=str(path))
    assert crit.provider_allowlist() == ["Google", "Alibaba"]
    crit.clear_provider_filter(path=str(path))
    assert crit.provider_allowlist() == []


def test_pick_from_ids_prefers_gemma_over_qwen(tmp_path: Path, monkeypatch):
    path = tmp_path / "c.json"
    monkeypatch.setenv("SPOCK_LLMFIT_CRITERIA_JSON", str(path))
    crit.clear_criteria_cache()
    # ALL providers so both Gemma and Qwen remain candidates for preference scoring.
    crit.clear_provider_filter(path=str(path))
    data = crit.load_criteria()
    data["chat"]["preferred_families"] = ["gemma", "gemma4", "gemma3"]
    data["chat"]["fallback_families"] = ["nemotron", "qwen"]
    crit.save_criteria(data, path=str(path))
    ids = [
        "Qwen/Qwen3-8B-GGUF",
        "nvidia/NVIDIA-Nemotron-Nano-9B-v2-GGUF",
        "google/gemma-3-12b-it-qat-q4_0-gguf",
    ]
    assert crit.pick_from_ids(ids, role="chat") == "google/gemma-3-12b-it-qat-q4_0-gguf"


def test_pick_from_ids_prefers_embeddinggemma(tmp_path: Path, monkeypatch):
    path = tmp_path / "c.json"
    monkeypatch.setenv("SPOCK_LLMFIT_CRITERIA_JSON", str(path))
    crit.clear_criteria_cache()
    crit.clear_provider_filter(path=str(path))
    data = crit.load_criteria()
    data["embed"]["preferred_families"] = ["embeddinggemma"]
    data["embed"]["fallback_families"] = ["nomic", "qwen3-embedding"]
    crit.save_criteria(data, path=str(path))
    ids = [
        "Qwen/Qwen3-Embedding-4B-GGUF",
        "ggml-org/embeddinggemma-300M-GGUF",
        "ggml-org/embeddinggemma-2-GGUF",
        "nomic-ai/nomic-embed-text-v1.5-GGUF",
    ]
    picked = crit.pick_from_ids(ids, role="embed")
    assert picked is not None and "embeddinggemma" in picked.lower()
    assert crit.fallback_model_id("embed") == "ggml-org/embeddinggemma-2-GGUF"


def test_process_cache_roots_session(tmp_path: Path, monkeypatch):
    path = tmp_path / "c.json"
    monkeypatch.setenv("SPOCK_LLMFIT_CRITERIA_JSON", str(path))
    crit.clear_criteria_cache()
    first = crit.load_criteria()
    altered = dict(first)
    altered["filters"] = dict(first["filters"])
    altered["filters"]["providers"] = ["Alibaba"]
    altered["filters"]["provider"] = "Alibaba"
    path.write_text(json.dumps(altered), encoding="utf-8")
    second = crit.load_criteria()
    assert second["filters"]["providers"] == ["Google"]
    reloaded = crit.load_criteria(refresh=True)
    assert reloaded["filters"]["providers"] == ["Alibaba"]


def test_filters_as_query_embed_use_case(tmp_path: Path, monkeypatch):
    path = tmp_path / "c.json"
    monkeypatch.setenv("SPOCK_LLMFIT_CRITERIA_JSON", str(path))
    crit.clear_criteria_cache()
    crit.save_criteria(crit.default_criteria(), path=str(path))
    q = crit.filters_as_query(role="embed")
    assert q.get("provider") == "Google"
    assert "providers" not in q
    assert q.get("use_case") == "embedding"
    assert q.get("min_fit") == "marginal"


def test_filters_as_query_omits_provider_when_all(tmp_path: Path, monkeypatch):
    path = tmp_path / "c.json"
    monkeypatch.setenv("SPOCK_LLMFIT_CRITERIA_JSON", str(path))
    crit.clear_criteria_cache()
    crit.clear_provider_filter(path=str(path))
    q = crit.filters_as_query(role="chat")
    assert "provider" not in q


def test_family_preference_bonus_orders_chat(tmp_path: Path, monkeypatch):
    path = tmp_path / "c.json"
    monkeypatch.setenv("SPOCK_LLMFIT_CRITERIA_JSON", str(path))
    crit.clear_criteria_cache()
    crit.clear_provider_filter(path=str(path))
    data = crit.load_criteria()
    data["chat"]["preferred_families"] = ["gemma", "gemma4", "gemma3"]
    data["chat"]["fallback_families"] = ["nemotron", "qwen"]
    crit.save_criteria(data, path=str(path))
    gemma = crit.family_preference_bonus("google/gemma-3-12b", role="chat")
    nemo = crit.family_preference_bonus("nvidia/nemotron-9b", role="chat")
    qwen = crit.family_preference_bonus("Qwen/Qwen3-8B", role="chat")
    other = crit.family_preference_bonus("mistral/mistral-7b", role="chat")
    assert gemma > nemo >= qwen > other == 0


def test_filter_model_rows(tmp_path: Path, monkeypatch):
    path = tmp_path / "c.json"
    monkeypatch.setenv("SPOCK_LLMFIT_CRITERIA_JSON", str(path))
    crit.clear_criteria_cache()
    crit.set_providers(["Google"], path=str(path))
    rows = [
        {"id": "google/gemma-3-12b"},
        {"id": "Qwen/Qwen3-8B"},
        {"id": "ggml-org/embeddinggemma-2-GGUF"},
    ]
    kept = crit.filter_model_rows(rows)
    assert [r["id"] for r in kept] == [
        "google/gemma-3-12b",
        "ggml-org/embeddinggemma-2-GGUF",
    ]
