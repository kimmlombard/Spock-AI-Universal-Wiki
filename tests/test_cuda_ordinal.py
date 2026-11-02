"""CUDA_VISIBLE_DEVICES must use the CUDA ordinal, not the nvidia-smi index.

The Quadro P2200 is video-only. The driver does not publish it to CUDA, so
the Quadro RTX 6000 is CUDA device 0 even though nvidia-smi lists it as GPU 1.
"""

from WarpCore.host_recipe import propose_recipe
from model_selector_core import cuda_ordinal_for_launch

THIS_HOST = [
    {"index": "0", "name": "Quadro P2200", "vram_gb": 5.0},
    {"index": "1", "name": "Quadro RTX 6000", "vram_gb": 22.5},
]
CUDA_MAP = {"Quadro RTX 6000": 0}
RTX_LABEL = "[1] Quadro RTX 6000 (22.5 GB)"


def test_rtx_6000_label_maps_to_cuda_zero():
    ordinal, source = cuda_ordinal_for_launch(
        "1", THIS_HOST, RTX_LABEL, cuda_map=CUDA_MAP
    )
    assert ordinal == "0"
    assert "CUDA[0]" in source


def test_nvidia_smi_index_one_is_not_passed_through():
    ordinal, source = cuda_ordinal_for_launch("1", THIS_HOST, "", cuda_map=CUDA_MAP)
    assert ordinal == "0"
    assert "1" in source or "RTX 6000" in source


def test_selecting_the_p2200_still_lands_on_the_rtx_6000():
    ordinal, _source = cuda_ordinal_for_launch(
        "0",
        THIS_HOST,
        "[0] Quadro P2200 (5.0 GB)",
        cuda_map=CUDA_MAP,
    )
    assert ordinal == "0"


def test_two_cuda_gpus_keep_an_explicit_second_device():
    gpus = [
        {"index": "0", "name": "RTX 3060", "vram_gb": 12.0},
        {"index": "1", "name": "RTX 3060", "vram_gb": 12.0},
    ]
    ordinal, _source = cuda_ordinal_for_launch(
        "1", gpus, "", cuda_map={"RTX 3060": 0}
    )
    # Name-keyed cuda_map still collapses duplicates (legacy path).
    assert ordinal == "0"


def test_annotate_dual_identical_names_get_distinct_ordinals():
    from model_selector_core import annotate_gpus_with_cuda

    gpus = [
        {"index": 0, "name": "NVIDIA GeForce RTX 3060", "vram_gb": 12.0},
        {"index": 1, "name": "NVIDIA GeForce RTX 3060", "vram_gb": 12.0},
    ]
    cuda = [
        {"index": 0, "name": "NVIDIA GeForce RTX 3060"},
        {"index": 1, "name": "NVIDIA GeForce RTX 3060"},
    ]
    out = annotate_gpus_with_cuda(gpus, cuda)
    assert [g.get("cuda_index") for g in out] == [0, 1]


def test_launch_ordinal_zero_with_dual_identical_without_collapsed_map(monkeypatch):
    """Bringup used to call cuda_ordinal_for_launch with no gpu_list; the
    name-keyed map kept only CUDA[1] for dual 3060s, so recipe GPU 0 launched
    on device 1."""
    from model_selector_core import cuda_ordinal_for_launch
    import model_selector_core as msc

    monkeypatch.setattr(
        msc,
        "get_cuda_devices",
        lambda: [
            {"index": 0, "name": "NVIDIA GeForce RTX 3060"},
            {"index": 1, "name": "NVIDIA GeForce RTX 3060"},
        ],
    )
    ordinal, source = cuda_ordinal_for_launch("0", gpu_list=None, cuda_map=None)
    assert ordinal == "0"
    assert "CUDA[0]" in source or "nvidia-smi[0]" in source
    ordinal1, _ = cuda_ordinal_for_launch("1", gpu_list=None, cuda_map=None)
    assert ordinal1 == "1"


def test_distinct_cuda_gpus_honor_the_requested_ordinal():
    gpus = [
        {"index": 0, "name": "RTX 3060", "vram_gb": 12.0, "cuda_index": 0},
        {"index": 1, "name": "RTX 4070", "vram_gb": 12.0, "cuda_index": 1},
    ]
    ordinal, source = cuda_ordinal_for_launch("1", gpus, "", cuda_map={})
    assert ordinal == "1"
    assert "CUDA[1]" in source


def test_without_a_cuda_map_the_requested_index_is_kept():
    ordinal, source = cuda_ordinal_for_launch("1", [], "", cuda_map={})
    assert ordinal == "1"
    assert source == "host recipe / explicit cuda_device"


def test_recipe_keeps_llm_roles_off_the_display_card():
    recipe = propose_recipe(
        {
            "host_ram_gb": 128.0,
            "gpu_count": 2,
            "gpus": [
                {"index": 0, "name": "Quadro P2200", "vram_gb": 5.0},
                {
                    "index": 1,
                    "name": "Quadro RTX 6000",
                    "vram_gb": 22.5,
                    "cuda_index": 0,
                },
            ],
        }
    )
    assert recipe["gpu_policy"] == "single_gpu"
    assert recipe["embed_gpu_index"] == 1
    assert recipe["chat_gpu_index"] == 1
    assert any("P2200" in note and "Video only" in note for note in recipe["notes"])
