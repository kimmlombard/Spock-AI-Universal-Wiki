"""Recipe-driven fit matching for Bringup step 3 Acquire."""

from model_pick_policy import (
    catalog_rows,
    fit_hub_row,
    fit_rank,
    is_community_variant,
    local_fit_level,
    model_family_key,
    recipe_role_budget,
    top_role_fits,
    vendor_family,
)

SINGLE_GPU = {
    "gpu_policy": "single_gpu",
    "embed_gpu_index": 0,
    "chat_gpu_index": 0,
    "embed_n_ctx": 4096,
    "chat_n_ctx": 16384,
    "embed_size_class": "medium",
}
PINNED = {
    "gpu_policy": "pin_per_role",
    "embed_gpu_index": 0,
    "chat_gpu_index": 1,
    "embed_n_ctx": 4096,
    "chat_n_ctx": 8192,
    "embed_size_class": "small",
}
SPLIT = {
    "gpu_policy": "tensor_split_chat",
    "embed_gpu_index": 0,
    "chat_gpu_index": 0,
    "embed_n_ctx": 4096,
    "chat_n_ctx": 8192,
    "embed_size_class": "small",
}
ONE_CARD = {"gpus": [{"index": 0, "vram_gb": 22.5}], "host_ram_gb": 128.0}
TWO_CARDS = {
    "gpus": [{"index": 0, "vram_gb": 12.0}, {"index": 1, "vram_gb": 12.0}],
    "host_ram_gb": 32.0,
}


def test_shared_card_reserves_room_for_the_embedding_model():
    embed = recipe_role_budget(SINGLE_GPU, ONE_CARD, role="embed")
    chat = recipe_role_budget(SINGLE_GPU, ONE_CARD, role="chat")
    assert embed["reserve_gb"] == 0.0
    assert chat["reserve_gb"] > 0
    assert chat["budget_gb"] < embed["budget_gb"]
    assert chat["n_ctx"] == 16384


def test_pinned_roles_each_own_their_card():
    embed = recipe_role_budget(PINNED, TWO_CARDS, role="embed")
    chat = recipe_role_budget(PINNED, TWO_CARDS, role="chat")
    assert embed["shared"] is False and chat["shared"] is False
    assert chat["reserve_gb"] == 0.0
    assert embed["pool_gb"] == 12.0 and chat["pool_gb"] == 12.0


def test_tensor_split_pools_both_cards_for_chat():
    chat = recipe_role_budget(SPLIT, TWO_CARDS, role="chat")
    assert chat["pool_gb"] == 24.0
    assert chat["budget_gb"] > recipe_role_budget(SPLIT, TWO_CARDS, role="embed")["budget_gb"]


def test_no_gpu_falls_back_to_a_slice_of_host_ram():
    budget = recipe_role_budget(
        {**SINGLE_GPU, "host_ram_gb": 32.0}, {"gpus": [], "host_ram_gb": 32.0}, role="chat"
    )
    assert budget["pool_gb"] == 0.0
    assert budget["budget_gb"] > 1.0


def test_fit_levels_follow_headroom():
    assert local_fit_level(5.0, 20.0) == "perfect"
    assert local_fit_level(16.0, 20.0) == "good"
    assert local_fit_level(19.0, 20.0) == "tight"
    assert local_fit_level(21.0, 20.0) == "impossible"
    assert fit_rank("perfect") < fit_rank("tight") < fit_rank("impossible")


def test_llmfit_verdict_wins_over_local_maths():
    budget = recipe_role_budget(SINGLE_GPU, ONE_CARD, role="chat")
    row = fit_hub_row(
        {"id": "Qwen/Qwen3-8B-GGUF", "size_b": 8.0, "fit_level": "tight"},
        kind="chat",
        budget=budget,
    )
    assert row["fit_level"] == "tight"
    assert row["fit_source"] == "llmfit"
    assert row["local_fit_level"] == "perfect"


def test_local_verdict_used_when_llmfit_is_absent():
    budget = recipe_role_budget(SINGLE_GPU, ONE_CARD, role="chat")
    row = fit_hub_row({"id": "Qwen/Qwen3-8B-GGUF", "size_b": 8.0}, kind="chat", budget=budget)
    assert row["fit_source"] == "recipe"
    assert row["fit_level"] == row["local_fit_level"]
    assert row["need_gb"] > 0 and row["headroom_gb"] > 0
    assert row["fit_n_ctx"] <= budget["n_ctx"]


def test_oversized_models_are_dropped():
    budget = recipe_role_budget(PINNED, TWO_CARDS, role="chat")
    picks = top_role_fits(
        [
            {"id": "Qwen/Qwen3-235B-GGUF", "size_b": 235.0},
            {"id": "Qwen/Qwen3-4B-GGUF", "size_b": 4.0},
        ],
        kind="chat",
        budget=budget,
    )
    assert [p["id"] for p in picks] == ["Qwen/Qwen3-4B-GGUF"]


def test_among_perfect_fits_chat_prefers_the_bigger_model():
    """Both fit comfortably, so spend the card: 8B over 4B despite a lower score."""
    budget = recipe_role_budget(SINGLE_GPU, ONE_CARD, role="chat")
    picks = top_role_fits(
        [
            {"id": "Qwen/Qwen3-4B-GGUF", "size_b": 4.0, "score": 90},
            {"id": "Qwen/Qwen3-8B-GGUF", "size_b": 8.0, "score": 50},
        ],
        kind="chat",
        budget=budget,
    )
    assert [p["fit_level"] for p in picks] == ["perfect", "perfect"]
    assert picks[0]["id"] == "Qwen/Qwen3-8B-GGUF"


def test_a_perfect_fit_outranks_a_bigger_tight_one():
    """The step asks for perfect fits, so headroom beats parameter count."""
    budget = recipe_role_budget(SINGLE_GPU, ONE_CARD, role="chat")
    picks = top_role_fits(
        [
            {"id": "Qwen/Qwen3-14B-GGUF", "size_b": 14.0},
            {"id": "Qwen/Qwen3-8B-GGUF", "size_b": 8.0},
        ],
        kind="chat",
        budget=budget,
    )
    assert picks[0]["id"] == "Qwen/Qwen3-8B-GGUF"
    assert picks[0]["fit_level"] == "perfect"
    assert picks[1]["fit_level"] in ("good", "tight")


def test_reuploads_collapse_so_the_menu_has_three_real_choices():
    budget = recipe_role_budget(SINGLE_GPU, ONE_CARD, role="chat")
    picks = top_role_fits(
        [
            {"id": "Qwen/Qwen3-8B-GGUF", "size_b": 8.0, "score": 90},
            {"id": "unsloth/Qwen3-8B-GGUF", "size_b": 8.0, "score": 80},
            {"id": "someone/Qwen3-8B-Q4_K_M-GGUF", "size_b": 8.0, "score": 70},
            {"id": "Qwen/Qwen3-4B-GGUF", "size_b": 4.0, "score": 85},
            {"id": "Qwen/Qwen3-1.7B-GGUF", "size_b": 1.7, "score": 84},
        ],
        kind="chat",
        budget=budget,
        limit=3,
    )
    assert [p["id"] for p in picks] == [
        "Qwen/Qwen3-8B-GGUF",
        "Qwen/Qwen3-4B-GGUF",
        "Qwen/Qwen3-1.7B-GGUF",
    ]


def test_acquire_limit_rotates_families_instead_of_three_qwen():
    budget = recipe_role_budget(SINGLE_GPU, ONE_CARD, role="chat")
    picks = top_role_fits(
        [
            {"id": "Qwen/Qwen3-14B-GGUF", "size_b": 14.0},
            {"id": "Qwen/Qwen3-8B-GGUF", "size_b": 8.0},
            {"id": "Qwen/Qwen3-4B-GGUF", "size_b": 4.0},
            {"id": "google/gemma-3-12b-it-qat-q4_0-gguf", "size_b": 12.0},
            {"id": "google/gemma-3-4b-it-qat-q4_0-gguf", "size_b": 4.0},
            {"id": "nvidia/NVIDIA-Nemotron-Nano-9B-v2-GGUF", "size_b": 8.9},
            {"id": "nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF", "size_b": 4.0},
        ],
        kind="chat",
        budget=budget,
        limit=6,
    )
    families = [vendor_family(p["id"]) for p in picks]
    assert len(set(families[:3])) == 3
    assert families.count("qwen") == 2
    assert families.count("gemma") == 2
    assert families.count("nemotron") == 2
    qwen_ids = [p["id"] for p in picks if vendor_family(p["id"]) == "qwen"]
    assert qwen_ids[0] == "Qwen/Qwen3-8B-GGUF"


def test_family_key_ignores_publisher_quant_and_requant():
    key = model_family_key("Qwen/Qwen3-Embedding-4B-GGUF")
    for variant in (
        "unsloth/Qwen3-Embedding-4B-GGUF",
        "enacimie/Qwen3-Embedding-4B-Q4_K_M-GGUF",
        "Casual-Autopsy/Qwen3-Embedding-4B-GGUFs",
        "mradermacher/Qwen3-Embedding-4B-i1-GGUF",
    ):
        assert model_family_key(variant) == key
    assert model_family_key("Qwen/Qwen3-Embedding-8B-GGUF") != key


def test_community_respins_are_recognised_but_not_lost_when_alone():
    assert is_community_variant("TheDrummer/Qwen3-14B-abliterated-GGUF")
    assert not is_community_variant("Qwen/Qwen3-14B-GGUF")
    budget = recipe_role_budget(SINGLE_GPU, ONE_CARD, role="chat")
    only_respins = top_role_fits(
        [{"id": "x/Qwen3-8B-uncensored-GGUF", "size_b": 8.0}], kind="chat", budget=budget
    )
    assert len(only_respins) == 1


def test_catalog_rows_are_offline_candidates_with_sizes():
    for kind in ("chat", "embedding"):
        rows = catalog_rows(kind)
        assert rows and all(r["id"] and r["size_b"] > 0 for r in rows)
    assert all(r.get("dim") for r in catalog_rows("embedding"))
