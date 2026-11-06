"""VRAM-aware Hugging Face GGUF picks for Spock embed :8080 + chat :8081.

Policy (ship_computer.db RAG first):
1. Keep existing embedding dimensions when the DB already has vectors.
2. Spend remaining VRAM on the largest *safe* chat context, not a bigger
   parameter count past ~8–14B instruct.
3. Prefer Q4_K_M chat (speed) and Q8_0 on small embedding models (vector quality).
"""

from __future__ import annotations

import json
import math
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# llama-server KV is typically f16. GQA Qwen3-class ≈ 0.14 MiB/token at 8B.
# Scale linearly with parameter count as a portable stand-in for layers/KV heads.
_KV_GB_PER_PARAM_B_PER_TOKEN = 1.75e-5

# Leave headroom for CUDA context, two llama-server processes, OS compositor.
_VRAM_USABLE_FRAC = 0.82

# Chat synthesis quality plateaus for wiki RAG around 8B instruct.

CTX_LADDER: Tuple[int, ...] = (131072, 65536, 32768, 16384, 8192, 4096, 2048)

_NOT_CHAT_SIGNALS = (
    "asr",
    "whisper",
    "parakeet",
    "speech-to-text",
    "speech_to_text",
    "speech2text",
    "transcri",
    "tts",
    "text-to-speech",
    "vocoder",
    "wav2vec",
    "rerank",
    "-vl-",
    "vl-instruct",
    "vision",
    "base-gguf",
    "-base-gguf",
    "-base.",
)

_PUBLISHER_BONUS = {
    "qwen/": 20,
    "google/": 50,
    "nvidia/": 36,
    "nomic-ai/": 35,
    "bartowski/": 30,
    "ggml-org/": 28,
    "unsloth/": 25,
    "lmstudio-community/": 22,
}


# Official / well-supported llama.cpp GGUF repos (Aug 2026).
EMBED_CATALOG: Tuple[Dict[str, Any], ...] = (
    {
        "id": "Qwen/Qwen3-Embedding-8B-GGUF",
        "params_b": 8.0,
        "dim": 4096,
        "native_ctx": 32768,
        "quality": 90,
        "speed": 55,
        "quant": "q8_0",
        "family": "qwen3-embedding",
    },
    {
        "id": "Qwen/Qwen3-Embedding-4B-GGUF",
        "params_b": 4.0,
        "dim": 2560,
        "native_ctx": 32768,
        "quality": 92,
        "speed": 78,
        "quant": "q8_0",
        "family": "qwen3-embedding",
    },
    {
        "id": "Qwen/Qwen3-Embedding-0.6B-GGUF",
        "params_b": 0.6,
        "dim": 1024,
        "native_ctx": 32768,
        "quality": 78,
        "speed": 98,
        "quant": "q8_0",
        "family": "qwen3-embedding",
    },
    {
        "id": "nomic-ai/nomic-embed-text-v1.5-GGUF",
        "params_b": 0.14,
        "dim": 768,
        "native_ctx": 8192,
        "quality": 70,
        "speed": 100,
        "quant": "q8_0",
        "family": "nomic",
    },
    {
        "id": "ggml-org/embeddinggemma-2-GGUF",
        "params_b": 0.27,
        "dim": 768,
        "native_ctx": 8192,
        "quality": 88,
        "speed": 94,
        "quant": "q8_0",
        "family": "embeddinggemma2",
    },
    {
        "id": "ggml-org/embeddinggemma-300M-GGUF",
        "params_b": 0.3,
        "dim": 768,
        "native_ctx": 2048,
        "quality": 76,
        "speed": 96,
        "quant": "q8_0",
        "family": "embeddinggemma",
    },
)

CHAT_CATALOG: Tuple[Dict[str, Any], ...] = (
    {
        "id": "Qwen/Qwen3-32B-GGUF",
        "params_b": 32.0,
        "native_ctx": 40960,
        "yarn_ctx": 131072,
        "quality": 94,
        "speed": 28,
        "quant": "q4_k_m",
        "family": "qwen3",
    },
    {
        "id": "Qwen/Qwen3-14B-GGUF",
        "params_b": 14.0,
        "native_ctx": 40960,
        "yarn_ctx": 131072,
        "quality": 90,
        "speed": 52,
        "quant": "q4_k_m",
        "family": "qwen3",
    },
    {
        "id": "Qwen/Qwen3-8B-GGUF",
        "params_b": 8.0,
        "native_ctx": 40960,
        "yarn_ctx": 131072,
        "quality": 86,
        "speed": 72,
        "quant": "q4_k_m",
        "family": "qwen3",
    },
    {
        "id": "Qwen/Qwen3-4B-GGUF",
        "params_b": 4.0,
        "native_ctx": 40960,
        "yarn_ctx": 131072,
        "quality": 74,
        "speed": 88,
        "quant": "q4_k_m",
        "family": "qwen3",
    },
    {
        "id": "Qwen/Qwen3-1.7B-GGUF",
        "params_b": 1.7,
        "native_ctx": 32768,
        "yarn_ctx": 32768,
        "quality": 58,
        "speed": 96,
        "quant": "q4_k_m",
        "family": "qwen3",
    },
    {
        "id": "google/gemma-3-27b-it-qat-q4_0-gguf",
        "params_b": 27.0,
        "native_ctx": 131072,
        "yarn_ctx": 131072,
        "quality": 90,
        "speed": 34,
        "quant": "q4_0",
        "family": "gemma3",
    },
    {
        "id": "bartowski/gemma-3-12b-it-GGUF",
        "params_b": 12.0,
        "native_ctx": 131072,
        "yarn_ctx": 131072,
        "quality": 86,
        "speed": 54,
        "quant": "q4_k_m",
        "family": "gemma3",
    },
    {
        "id": "google/gemma-3-12b-it-qat-q4_0-gguf",
        "params_b": 12.0,
        "native_ctx": 131072,
        "yarn_ctx": 131072,
        "quality": 87,
        "speed": 54,
        "quant": "q4_0",
        "family": "gemma3",
    },
    {
        # Prefer public bartowski mirror for try-out without HF_TOKEN.
        # Official google/* Gemma repos remain gated on Hugging Face.
        "id": "bartowski/gemma-3-4b-it-GGUF",
        "params_b": 4.0,
        "native_ctx": 131072,
        "yarn_ctx": 131072,
        "quality": 74,
        "speed": 90,
        "quant": "q4_k_m",
        "family": "gemma3",
    },
    {
        "id": "google/gemma-3-4b-it-qat-q4_0-gguf",
        "params_b": 4.0,
        "native_ctx": 131072,
        "yarn_ctx": 131072,
        "quality": 75,
        "speed": 90,
        "quant": "q4_0",
        "family": "gemma3",
    },
    {
        "id": "bartowski/gemma-2-9b-it-GGUF",
        "params_b": 9.2,
        "native_ctx": 8192,
        "yarn_ctx": 8192,
        "quality": 80,
        "speed": 62,
        "quant": "q4_k_m",
        "family": "gemma2",
    },
    {
        "id": "google/gemma-4-E4B-it-qat-q4_0-gguf",
        "params_b": 8.0,
        "native_ctx": 131072,
        "yarn_ctx": 131072,
        "quality": 88,
        "speed": 70,
        "quant": "q4_0",
        "family": "gemma4",
    },
    {
        "id": "google/gemma-4-26B-A4B-it-qat-q4_0-gguf",
        "params_b": 26.0,
        "native_ctx": 131072,
        "yarn_ctx": 131072,
        "quality": 93,
        "speed": 36,
        "quant": "q4_0",
        "family": "gemma4",
    },
    {
        "id": "google/gemma-4-31B-it-qat-q4_0-gguf",
        "params_b": 31.0,
        "native_ctx": 131072,
        "yarn_ctx": 131072,
        "quality": 94,
        "speed": 30,
        "quant": "q4_0",
        "family": "gemma4",
    },
    {
        "id": "nvidia/Llama-3.1-Nemotron-Nano-8B-v1-GGUF",
        "params_b": 8.0,
        "native_ctx": 131072,
        "yarn_ctx": 131072,
        "quality": 86,
        "speed": 74,
        "quant": "q4_k_m",
        "family": "nemotron",
    },
    {
        "id": "nvidia/NVIDIA-Nemotron-Nano-9B-v2-GGUF",
        "params_b": 8.9,
        "native_ctx": 131072,
        "yarn_ctx": 131072,
        "quality": 87,
        "speed": 68,
        "quant": "q4_k_m",
        "family": "nemotron",
    },
    {
        "id": "nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF",
        "params_b": 4.0,
        "native_ctx": 131072,
        "yarn_ctx": 131072,
        "quality": 76,
        "speed": 90,
        "quant": "q4_k_m",
        "family": "nemotron",
    },
    {
        "id": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-GGUF",
        "params_b": 30.0,
        "native_ctx": 131072,
        "yarn_ctx": 131072,
        "quality": 92,
        "speed": 32,
        "quant": "q4_k_m",
        "family": "nemotron",
    },
    {
        "id": "bartowski/Phi-4-GGUF",
        "params_b": 14.7,
        "native_ctx": 16384,
        "yarn_ctx": 16384,
        "quality": 82,
        "speed": 48,
        "quant": "q4_k_m",
        "family": "phi4",
    },
)

# Targeted Hub searches — beats “top 200 GGUF by downloads”.
HF_CHAT_SEARCHES: Tuple[str, ...] = (
    "Qwen3-8B-GGUF",
    "Qwen3-14B-GGUF",
    "Qwen3-4B-GGUF",
    "Qwen3-32B-GGUF",
    "Qwen3-1.7B-GGUF",
    "gemma-3-12b-it-GGUF",
    "gemma-3-4b-it-GGUF",
    "gemma-3-27b-it",
    "gemma-3-12b-it-qat",
    "gemma-3-4b-it-qat",
    "gemma-2-9b-it-GGUF",
    "gemma-4-E4B-it",
    "gemma-4-26B-A4B-it",
    "gemma-4-31B-it",
    "Nemotron-Nano-8B",
    "Nemotron-Nano-9B-v2",
    "Nemotron-3-Nano-4B",
    "Nemotron-3-Nano-30B-A3B",
    "Phi-4-GGUF",
)
HF_EMBED_SEARCHES: Tuple[str, ...] = (
    "Qwen3-Embedding-4B-GGUF",
    "Qwen3-Embedding-0.6B-GGUF",
    "Qwen3-Embedding-8B-GGUF",
    "nomic-embed-text-v1.5-GGUF",
    "embeddinggemma-2-GGUF",
    "embeddinggemma-300M-GGUF",
)


def active_hf_searches(kind: str = "chat") -> Tuple[str, ...]:
    """HF search terms narrowed by the session provider allow-list (empty = all)."""
    base = HF_EMBED_SEARCHES if kind == "embedding" else HF_CHAT_SEARCHES
    try:
        from llmfit_session_criteria import provider_allowlist, _signals_for_provider

        names = provider_allowlist()
    except Exception:
        return base
    if not names:
        return base
    tokens: List[str] = []
    for name in names:
        _prefs, toks = _signals_for_provider(name)
        tokens.extend(toks)
    if not tokens:
        return base
    kept = [term for term in base if any(tok in term.lower() for tok in tokens if tok)]
    return tuple(kept) if kept else base

_QUANT_BYTES = {
    "f16": 2.0,
    "fp16": 2.0,
    "bf16": 2.0,
    "q8": 1.05,
    "q6": 0.80,
    "q5": 0.68,
    "q4": 0.58,
    "iq4": 0.50,
    "q3": 0.42,
}


def usable_vram_gb(vram_gb: float) -> float:
    vram = max(0.0, float(vram_gb or 0.0))
    return round(vram * _VRAM_USABLE_FRAC, 2)


def quant_bytes_per_param(quant: str) -> float:
    q = (quant or "q4_k_m").lower()
    for key, val in _QUANT_BYTES.items():
        if key in q:
            return val
    return 0.58


def weight_gb(params_b: float, quant: str = "q4_k_m") -> float:
    return round(float(params_b) * quant_bytes_per_param(quant), 2)


def estimate_kv_cache_gb(params_b: float, n_ctx: int) -> float:
    """Order-of-magnitude f16 KV size for GQA instruct models."""
    p = max(0.05, float(params_b or 0.0))
    ctx = max(1, int(n_ctx or 1))
    return round(p * ctx * _KV_GB_PER_PARAM_B_PER_TOKEN, 3)


def pair_vram_gb(
    embed_params_b: float,
    chat_params_b: float,
    embed_n_ctx: int,
    chat_n_ctx: int,
    embed_quant: str = "q8_0",
    chat_quant: str = "q4_k_m",
) -> float:
    return round(
        weight_gb(embed_params_b, embed_quant)
        + weight_gb(chat_params_b, chat_quant)
        + estimate_kv_cache_gb(embed_params_b, embed_n_ctx)
        + estimate_kv_cache_gb(chat_params_b, chat_n_ctx),
        2,
    )


def _publisher_bonus(model_id: str) -> int:
    low = (model_id or "").lower()
    for prefix, bonus in _PUBLISHER_BONUS.items():
        if low.startswith(prefix):
            return bonus
    return 0


def _exempt_from_vision_signal(low: str) -> bool:
    """Gemma / Nemotron text instruct ids often mention vision without being VL."""
    if "-vl-" in low or "vl-instruct" in low:
        return False
    if any(bad in low for bad in ("asr", "speech", "whisper", "diffusion")):
        return False
    if "nemotron" in low:
        return "parse" not in low
    gemma = any(
        sig in low
        for sig in ("gemma-2", "gemma-3", "gemma-4", "gemma2", "gemma3", "gemma4")
    )
    if not gemma:
        return False
    return "instruct" in low or "-it" in low


def is_non_chat_model(model_id: str) -> bool:
    low = (model_id or "").lower()
    for sig in _NOT_CHAT_SIGNALS:
        if sig not in low:
            continue
        if sig == "vision" and _exempt_from_vision_signal(low):
            continue
        return True
    if "embedding" in low or "nomic-embed" in low:
        return True
    if "diffusion" in low:
        return True
    if "nemotron" in low and "parse" in low:
        return True
    return False


def is_strong_embed_id(model_id: str) -> bool:
    low = (model_id or "").lower()
    if "rerank" in low or "-vl-" in low or "vl-embedding" in low:
        return False
    return any(
        sig in low
        for sig in (
            "embedding",
            "nomic-embed",
            "bge-m3",
            "gte-qwen",
            "snowflake-arctic-embed",
        )
    )


def parse_size_b(name: str) -> Optional[float]:
    """Parse 0.6B / 1.7B / 8B style tokens from a repo or file name."""
    low = (name or "").lower().replace("_", "-")
    # Gemma 4 E4B/E2B names are effective size, not weight size.
    if "gemma-4" in low and "e4b" in low:
        return 8.0
    if "gemma-4" in low and "e2b" in low:
        return 5.1
    # MoE ``30B-A3B``: VRAM follows the full expert stack, not the active count.
    moe = re.search(r"(\d+(?:\.\d+)?)b-a\d+(?:\.\d+)?b", low)
    if moe:
        return float(moe.group(1))
    matches = re.findall(r"(?:^|[-/._])(\d+(?:\.\d+)?)b(?:$|[-/._])", low)
    if not matches:
        # last-token fallback: "... 8b"
        for token in low.replace("-", " ").split():
            if token.endswith("b") and len(token) > 1 and token[:-1].replace(".", "").isdigit():
                matches.append(token[:-1])
    if not matches:
        millions = re.findall(r"(?:^|[-/._])(\d+(?:\.\d+)?)m(?:$|[-/._])", low)
        if millions:
            return round(float(millions[-1]) / 1000.0, 3)
        return None
    # Prefer the last size token (Qwen3-Embedding-4B, not a stray 3).
    vals = [float(m) for m in matches if float(m) > 0]
    if not vals:
        return None
    # Ignore tiny false positives like "2.5" from "qwen2.5" when a later Nb exists.
    if len(vals) > 1:
        vals = [v for v in vals if v != 2.5] or vals
        vals = [v for v in vals if v != 3.0 and v != 3.1 and v != 3.2 and v != 3.3] or vals
    return vals[-1]


def infer_native_ctx(model_id: str, kind: str = "chat") -> int:
    low = (model_id or "").lower()
    if "embeddinggemma-2" in low or "embeddinggemma2" in low:
        return 8192
    if "embeddinggemma" in low:
        return 2048
    if any(sig in low for sig in ("gemma-4", "gemma4", "gemma-3", "gemma3")):
        return 131072
    if "gemma-2" in low or "gemma2" in low:
        return 8192
    if "nemotron" in low:
        return 131072
    if "qwen3" in low:
        return 40960 if kind == "chat" else 32768
    if "nomic-embed" in low:
        return 8192
    if "phi-4" in low or "phi4" in low:
        return 16384
    if "llama-3.1" in low or "llama-3.3" in low or "llama3.1" in low:
        return 131072
    return 32768 if kind == "chat" else 2048


def infer_embed_dim(model_id: str) -> Optional[int]:
    low = (model_id or "").lower()
    if "qwen3-embedding-8b" in low:
        return 4096
    if "qwen3-embedding-4b" in low:
        return 2560
    if "qwen3-embedding-0.6b" in low or "qwen3-embedding-0-6b" in low:
        return 1024
    if "embeddinggemma" in low:
        return 768
    if "nomic-embed" in low:
        return 768
    if "bge-m3" in low:
        return 1024
    return None


def _family_chat_score(model_id: str) -> int:
    low = (model_id or "").lower()
    if is_non_chat_model(low):
        return -10_000
    score = _publisher_bonus(low)
    try:
        from llmfit_session_criteria import family_preference_bonus

        score += family_preference_bonus(low, role="chat")
    except Exception:
        # Offline / import failure: keep a portable Gemma-first ladder.
        if any(
            sig in low
            for sig in ("gemma-4", "gemma4", "gemma-3", "gemma3", "gemma-2", "gemma2")
        ):
            score += 180
        elif "nemotron" in low:
            score += 150
        elif "qwen3" in low and "embedding" not in low:
            score += 140
        elif "phi-4" in low or "phi4" in low:
            score += 110
        elif "llama-3.3" in low or "llama-3.1" in low:
            score += 100
        elif "qwen2.5" in low or "qwen2-" in low:
            score += 40
    if "instruct" in low or "-it-" in low or "-it." in low or low.endswith("-it"):
        score += 50
    if "thinking" in low and "instruct" not in low:
        score -= 15
    return score


def _family_embed_score(model_id: str) -> int:
    low = (model_id or "").lower()
    if not is_strong_embed_id(low):
        return -5_000
    score = _publisher_bonus(low)
    try:
        from llmfit_session_criteria import family_preference_bonus

        score += family_preference_bonus(low, role="embed")
    except Exception:
        if "embeddinggemma" in low:
            score += 220
        elif "qwen3-embedding-4b" in low:
            score += 180
        elif "qwen3-embedding-8b" in low:
            score += 160
        elif "qwen3-embedding-0.6b" in low:
            score += 140
        elif "nomic-embed-text-v1.5" in low:
            score += 120
        elif "nomic-embed" in low:
            score += 90
        elif "bge-m3" in low:
            score += 80
    return score


def rag_pair_score(
    embed_quality: float,
    chat_params_b: float,
    chat_n_ctx: int,
    chat_speed: float,
) -> float:
    """Higher is better for ship_computer.db Ask AI / Deep Dive.

    Retrieval quality dominates. After ~8B instruct, extra params lose to extra ctx.
    """
    # 8B is "enough" for wiki RAG synthesis; 14B is only a small bump.
    chat_q = min(1.0, float(chat_params_b) / 8.0)
    if float(chat_params_b) > 8.0:
        chat_q = min(1.08, chat_q + 0.01 * (float(chat_params_b) - 8.0))
    ctx = math.log2(max(2048, int(chat_n_ctx))) / math.log2(131072)
    speed = min(1.0, max(0.0, float(chat_speed) / 100.0))
    embed = min(1.0, max(0.0, float(embed_quality) / 100.0))
    return round(100.0 * (0.40 * embed + 0.18 * chat_q + 0.32 * ctx + 0.10 * speed), 2)


def recommended_embed_n_ctx(vram_gb: float, native_ctx: int = 32768) -> int:
    vram = float(vram_gb or 0.0)
    if vram < 4:
        n = 1024
    elif vram < 8:
        n = 2048
    elif vram < 16:
        n = 4096
    else:
        n = 8192
    return int(min(max(512, n), int(native_ctx or n)))


def _embed_quant_for_vram(params_b: float, vram_gb: float) -> str:
    if params_b <= 1.0:
        return "q8_0"
    if params_b <= 4.5 and vram_gb >= 16:
        return "q8_0"
    if params_b <= 4.5:
        return "q4_k_m"
    if vram_gb >= 40:
        return "q8_0"
    return "q4_k_m"


def _chat_quant_for_headroom(params_b: float, vram_left_gb: float, n_ctx: int) -> str:
    q4 = weight_gb(params_b, "q4_k_m") + estimate_kv_cache_gb(params_b, n_ctx)
    q5 = weight_gb(params_b, "q5_k_m") + estimate_kv_cache_gb(params_b, n_ctx)
    if vram_left_gb >= q5 + 1.5:
        return "q5_k_m"
    if vram_left_gb >= q4:
        return "q4_k_m"
    return "q4_k_m"


def detect_existing_embedding_dim(
    root: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Optional[int]:
    """Prefer live ship_computer.db vectors, then app_config profile dim."""
    base = root or SCRIPT_DIR
    path = db_path or os.path.join(base, "ship_computer.db")
    try:
        from model_selector_core import sample_db_embedding_dim

        dim = sample_db_embedding_dim(path)
        if dim and dim > 8:
            return int(dim)
    except Exception:
        pass
    cfg_path = os.path.join(base, "app_config.json")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        prof = data.get("embedding_profile") if isinstance(data, dict) else None
        if isinstance(prof, dict) and prof.get("embeddings_dim"):
            return int(prof["embeddings_dim"])
    except Exception:
        pass
    return None


def _catalog_by_dim(dim: Optional[int]) -> List[Dict[str, Any]]:
    rows = [dict(r) for r in EMBED_CATALOG]
    if not dim:
        return rows
    matched = [r for r in rows if int(r.get("dim") or 0) == int(dim)]
    return matched or rows


def plan_model_pair(
    specs: Dict[str, Any],
    *,
    existing_dim: Optional[int] = None,
) -> Dict[str, Any]:
    """Choose embed+chat GGUF ids and n_ctx that co-reside on one GPU."""
    vram = float(specs.get("vram_gb") or 0.0)
    budget = usable_vram_gb(vram) if vram > 0 else max(2.0, float(specs.get("ram_gb") or 8) * 0.35)
    allow_change = True
    try:
        from llmfit_session_criteria import allow_dim_change

        allow_change = allow_dim_change()
    except Exception:
        allow_change = True
    # When criteria allow a dim change (user will re-embed), search the full
    # embed catalog instead of locking to the old vector width.
    embed_pool = (
        [dict(r) for r in EMBED_CATALOG]
        if allow_change
        else _catalog_by_dim(existing_dim)
    )
    # Session criteria can narrow the embed pool to preferred families first.
    try:
        from llmfit_session_criteria import preferred_families

        prefs = preferred_families("embed")
        if prefs:
            narrowed = [
                r
                for r in embed_pool
                if any(p in str(r.get("id") or "").lower() for p in prefs)
            ]
            if narrowed:
                embed_pool = narrowed
    except Exception:
        pass
    dim_locked = bool(existing_dim) and any(
        int(r.get("dim") or 0) == int(existing_dim) for r in embed_pool
    )

    best: Optional[Dict[str, Any]] = None
    best_score = -1.0

    for embed in embed_pool:
        embed_ctx = recommended_embed_n_ctx(vram, int(embed.get("native_ctx") or 8192))
        embed_q = _embed_quant_for_vram(float(embed["params_b"]), vram)
        embed_w = weight_gb(float(embed["params_b"]), embed_q)
        embed_kv = estimate_kv_cache_gb(float(embed["params_b"]), embed_ctx)
        remain_after_embed = budget - embed_w - embed_kv
        if remain_after_embed < 1.5:
            continue
        for chat in CHAT_CATALOG:
            max_ctx = min(
                int(chat.get("yarn_ctx") or chat.get("native_ctx") or 32768),
                131072,
            )
            for n_ctx in CTX_LADDER:
                if n_ctx > max_ctx:
                    continue
                chat_q = _chat_quant_for_headroom(
                    float(chat["params_b"]), remain_after_embed, n_ctx
                )
                total = pair_vram_gb(
                    float(embed["params_b"]),
                    float(chat["params_b"]),
                    embed_ctx,
                    n_ctx,
                    embed_q,
                    chat_q,
                )
                if total > budget:
                    continue
                score = rag_pair_score(
                    float(embed["quality"]),
                    float(chat["params_b"]),
                    n_ctx,
                    float(chat["speed"]),
                )
                # Prefer criteria-aligned pairs (default: EmbeddingGemma + Gemma chat).
                emb_fam = str(embed.get("family") or "").lower()
                chat_fam = str(chat.get("family") or "").lower()
                try:
                    from llmfit_session_criteria import family_preference_bonus

                    # Scale bonuses into rag_pair_score units (~0–100).
                    score += family_preference_bonus(str(embed.get("id") or ""), "embed") / 20.0
                    score += family_preference_bonus(str(chat.get("id") or ""), "chat") / 20.0
                except Exception:
                    if emb_fam.startswith("embeddinggemma") and chat_fam.startswith("gemma"):
                        score += 12.0
                    elif emb_fam == "qwen3-embedding" and chat_fam == "qwen3":
                        score += 1.0
                else:
                    if emb_fam.startswith("embeddinggemma") and chat_fam.startswith("gemma"):
                        score += 4.0
                    elif emb_fam == "qwen3-embedding" and chat_fam == "qwen3":
                        score += 0.5
                # When dim change is allowed (user will re-embed), do not lock to old vectors.
                if (
                    not allow_change
                    and dim_locked
                    and int(embed.get("dim") or 0) == int(existing_dim)
                ):
                    score += 8.0
                if score > best_score:
                    best_score = score
                    best = {
                        "embed_id": embed["id"],
                        "chat_id": chat["id"],
                        "embed_params_b": float(embed["params_b"]),
                        "chat_params_b": float(chat["params_b"]),
                        "embed_dim": int(embed.get("dim") or 0) or None,
                        "embed_n_ctx": int(embed_ctx),
                        "chat_n_ctx": int(n_ctx),
                        "embed_quant": embed_q,
                        "chat_quant": chat_q,
                        "vram_gb": vram,
                        "budget_gb": budget,
                        "estimated_pair_gb": total,
                        "score": round(score, 2),
                        "existing_dim": existing_dim,
                        "dim_locked": dim_locked,
                    }

    if not best:
        # Ultra-low VRAM: smallest pair, shortest ctx.
        embed = embed_pool[-1]
        chat = CHAT_CATALOG[-2] if len(CHAT_CATALOG) > 1 else CHAT_CATALOG[-1]
        best = {
            "embed_id": embed["id"],
            "chat_id": chat["id"],
            "embed_params_b": float(embed["params_b"]),
            "chat_params_b": float(chat["params_b"]),
            "embed_dim": int(embed.get("dim") or 0) or None,
            "embed_n_ctx": 1024,
            "chat_n_ctx": 2048,
            "embed_quant": "q4_k_m",
            "chat_quant": "q4_k_m",
            "vram_gb": vram,
            "budget_gb": budget,
            "estimated_pair_gb": pair_vram_gb(
                float(embed["params_b"]), float(chat["params_b"]), 1024, 2048
            ),
            "score": 0.0,
            "existing_dim": existing_dim,
            "dim_locked": dim_locked,
            "fallback": True,
        }

    best["note"] = format_plan_note(best)
    return best


def format_plan_note(plan: Dict[str, Any]) -> str:
    parts = [
        f"VRAM budget ~{plan.get('budget_gb')}GB of {plan.get('vram_gb')}GB",
        f"pair ≈{plan.get('estimated_pair_gb')}GB",
        f"embed -c {plan.get('embed_n_ctx')} ({plan.get('embed_quant')})",
        f"chat -c {plan.get('chat_n_ctx')} ({plan.get('chat_quant')})",
        f"score {plan.get('score')}",
    ]
    if plan.get("dim_locked"):
        parts.append(f"locked embed dim={plan.get('existing_dim')} (existing ship_computer.db)")
    if plan.get("fallback"):
        parts.append("low-VRAM fallback pair")
    return "; ".join(str(p) for p in parts)


def score_hub_row(row: Dict[str, Any], *, kind: str) -> int:
    mid = str(row.get("id") or "")
    if kind == "embedding":
        score = _family_embed_score(mid)
    else:
        score = _family_chat_score(mid)
    score += min(30, int(row.get("likes") or 0) // 50)
    # Downloads are a weak popularity prior, not quality.
    score += min(15, int(row.get("downloads") or 0) // 200_000)
    size_b = row.get("size_b")
    if size_b and kind == "chat":
        # Prefer the 4–14B RAG sweet spot.
        sb = float(size_b)
        if 3.5 <= sb <= 16:
            score += 25
        elif sb > 32:
            score -= 20
    if size_b and kind == "embedding":
        sb = float(size_b)
        if 0.4 <= sb <= 4.5:
            score += 20
        elif sb >= 8:
            score += 5
    return int(score)


def annotate_hub_row(row: Dict[str, Any], kind: str) -> Dict[str, Any]:
    out = dict(row)
    mid = str(out.get("id") or "")
    if out.get("size_b") in (None, 0):
        parsed = parse_size_b(mid)
        if parsed:
            out["size_b"] = parsed
    out["kind"] = kind
    out["native_ctx"] = infer_native_ctx(mid, kind)
    if kind == "embedding":
        out["dim"] = infer_embed_dim(mid)
    out["score"] = score_hub_row(out, kind=kind)
    return out


def enrich_hub_rows_llmfit_tps(
    rows: Sequence[Dict[str, Any]],
    *,
    enabled: bool = True,
) -> List[Dict[str, Any]]:
    """Attach llmfit estimated tok/s / fit badges when the CLI is available."""
    if not enabled or not rows:
        return [dict(r) for r in rows]
    try:
        from spock_shell.llmfit_bridge import available, enrich_hub_row_with_fit, fit_estimate_index
    except Exception:
        return [dict(r) for r in rows]
    if not available():
        return [dict(r) for r in rows]
    try:
        index = fit_estimate_index(limit=40)
    except Exception:
        index = {}
    if not index:
        return [dict(r) for r in rows]
    return [enrich_hub_row_with_fit(dict(r), index=index) for r in rows]


def rank_hub_rows(
    rows: Sequence[Dict[str, Any]],
    *,
    kind: str,
    max_b: Optional[float] = None,
    llmfit_tps: bool = False,
) -> List[Dict[str, Any]]:
    annotated: List[Dict[str, Any]] = []
    for row in rows:
        if row.get("error"):
            continue
        mid = str(row.get("id") or "")
        if not mid:
            continue
        try:
            from llmfit_session_criteria import model_id_allowed

            if not model_id_allowed(mid):
                continue
        except Exception:
            pass
        if kind == "chat" and is_non_chat_model(mid):
            continue
        if kind == "embedding" and not is_strong_embed_id(mid):
            continue
        item = annotate_hub_row(row, kind)
        if max_b is not None and item.get("size_b") and float(item["size_b"]) > float(max_b):
            continue
        if item.get("score", 0) < 0:
            continue
        annotated.append(item)
    if llmfit_tps:
        annotated = enrich_hub_rows_llmfit_tps(annotated)
    annotated.sort(
        key=lambda r: (
            -int(r.get("score") or 0),
            -int(r.get("likes") or 0),
            float(r.get("size_gb") or 99),
        )
    )
    return annotated


def preferred_quant_tokens(quant: str) -> Tuple[str, ...]:
    q = (quant or "q4_k_m").lower()
    if "q8" in q:
        return ("q8_0", "q8", "q6_k", "q5_k_m", "q4_k_m")
    if "q5" in q:
        return ("q5_k_m", "q5_k_s", "q5_0", "q4_k_m", "q8_0")
    return ("q4_k_m", "q4_k_s", "q5_k_m", "q4_0", "iq4_xs", "q3_k_m")


def pick_from_hub_or_catalog(
    hub_rows: Iterable[Dict[str, Any]],
    catalog_id: str,
    *,
    kind: str,
) -> str:
    """Prefer a live Hub hit that matches the planned family; else catalog id."""
    want = catalog_id.lower()
    family = want.split("/")[-1].replace("-gguf", "")
    ranked = rank_hub_rows(list(hub_rows), kind=kind)
    try:
        from llmfit_session_criteria import preferred_publisher_prefixes

        preferred_orgs = preferred_publisher_prefixes()
    except Exception:
        preferred_orgs = [
            catalog_id.split("/")[0].lower() + "/",
            "google/",
            "ggml-org/",
            "nomic-ai/",
            "qwen/",
        ]
    catalog_org = catalog_id.split("/")[0].lower() + "/"
    for row in ranked:
        mid = str(row.get("id") or "").lower()
        if mid == want:
            return str(row["id"])
    for row in ranked:
        mid = str(row.get("id") or "").lower()
        short = mid.split("/")[-1].replace("-gguf", "")
        if family in short or short in family:
            # Prefer session-criteria publishers (e.g. google/, ggml-org/).
            if any(mid.startswith(p) for p in preferred_orgs) or mid.startswith(catalog_org):
                return str(row["id"])
    for row in ranked:
        mid = str(row.get("id") or "").lower()
        if family.replace("-instruct", "") in mid:
            return str(row["id"])
    return catalog_id


# ── Recipe-aware fit matching (llmfit vocabulary, computed locally) ──────
# llmfit labels a model against the machine; these do the same against the
# host recipe, so Acquire can rank candidates even when the llmfit CLI is
# absent. llmfit's own verdict wins whenever it has one for the model.
FIT_LEVELS: Tuple[str, ...] = ("perfect", "good", "tight", "impossible")
_FIT_RANK = {level: i for i, level in enumerate(FIT_LEVELS)}

# Footprint of the recipe's embed size class, reserved when both roles share a
# card, so a chat candidate is not sized as if it owned the whole GPU.
_EMBED_CLASS_PARAMS_B = {"small": 0.6, "medium": 4.0, "large": 8.0}


def fit_rank(level: str) -> int:
    return _FIT_RANK.get(str(level or "").lower(), len(FIT_LEVELS))


# Community respins are fine models but a poor first-run menu: onboarding wants
# the reference instruct releases.
_COMMUNITY_VARIANT_SIGNALS = (
    "distill",
    "abliterat",
    "uncensored",
    "roleplay",
    "nsfw",
    "-merge",
    "slerp",
    "-ties",
    "-dpo",
    "lora",
)


def is_community_variant(model_id: str) -> bool:
    low = (model_id or "").lower()
    return any(sig in low for sig in _COMMUNITY_VARIANT_SIGNALS)


_FAMILY_NOISE_RES = (
    re.compile(r"[-_.]iq\d+_?x*s"),          # -iq4_xs
    re.compile(r"[-_.]q\d+(_[0-9a-z]+)*"),   # -q4_k_m, -q8_0, -q5_k_s
    re.compile(r"[-_.](f16|fp16|bf16)"),
    re.compile(r"[-_.](i1|imat|imatrix)"),   # imatrix requants of the same model
    re.compile(r"[-_.]?ggufs?"),
)


def model_family_key(model_id: str) -> str:
    """Publisher- and quant-free identity, so re-uploads collapse together.

    ``Qwen/Qwen3-Embedding-4B-GGUF`` and
    ``enacimie/Qwen3-Embedding-4B-Q4_K_M-GGUF`` are the same model.
    """
    low = (model_id or "").lower().replace("\\", "/")
    if "/" in low:
        low = low.rsplit("/", 1)[-1]
    for pattern in _FAMILY_NOISE_RES:
        low = pattern.sub("", low)
    return re.sub(r"[^a-z0-9]+", "", low)


def _gpu_vram_by_index(hardware: Dict[str, Any]) -> Dict[int, float]:
    out: Dict[int, float] = {}
    for gpu in (hardware or {}).get("gpus") or []:
        if not isinstance(gpu, dict):
            continue
        try:
            out[int(gpu.get("index") or 0)] = float(gpu.get("vram_gb") or 0.0)
        except (TypeError, ValueError):
            continue
    return out


def recipe_role_budget(
    recipe: Dict[str, Any],
    hardware: Dict[str, Any],
    *,
    role: str,
) -> Dict[str, Any]:
    """VRAM budget and n_ctx the recipe leaves for one role.

    ``role`` is ``"embed"`` or ``"chat"``. Embed is sized first (it is small and
    loads first), so only chat pays a reserve when the two share a device.
    """
    rec = recipe or {}
    vram_by_idx = _gpu_vram_by_index(hardware)
    vrams = [v for v in vram_by_idx.values() if v > 0]
    policy = str(rec.get("gpu_policy") or "")
    idx_key = "embed_gpu_index" if role == "embed" else "chat_gpu_index"
    try:
        own_idx = int(rec.get(idx_key) or 0)
    except (TypeError, ValueError):
        own_idx = 0

    if policy == "pin_per_role" and len(vrams) >= 2:
        pool = vram_by_idx.get(own_idx) or (max(vrams) if vrams else 0.0)
        shared = False
    elif policy == "tensor_split_chat" and role == "chat" and len(vrams) >= 2:
        pool = sum(vrams)
        shared = True
    else:
        pool = vram_by_idx.get(own_idx) or (max(vrams) if vrams else 0.0)
        shared = True

    if pool > 0:
        budget = usable_vram_gb(pool)
    else:
        # CPU / unknown GPU: spend a slice of host RAM instead.
        budget = max(2.0, float(rec.get("host_ram_gb") or 8.0) * 0.35)

    reserve = 0.0
    if role == "chat" and shared:
        embed_b = _EMBED_CLASS_PARAMS_B.get(
            str(rec.get("embed_size_class") or "medium"), 4.0
        )
        embed_ctx = int(rec.get("embed_n_ctx") or 4096)
        reserve = weight_gb(embed_b, "q8_0") + estimate_kv_cache_gb(embed_b, embed_ctx)

    n_ctx = int(rec.get("embed_n_ctx" if role == "embed" else "chat_n_ctx") or 4096)
    return {
        "role": role,
        "pool_gb": round(pool, 2),
        "budget_gb": round(max(0.5, budget - reserve), 2),
        "reserve_gb": round(reserve, 2),
        "n_ctx": n_ctx,
        "shared": shared,
        "gpu_policy": policy,
        "gpu_index": own_idx,
    }


def local_fit_level(need_gb: float, budget_gb: float) -> str:
    """Fit verdict from footprint vs budget, in llmfit's vocabulary."""
    budget = max(0.1, float(budget_gb or 0.0))
    need = max(0.0, float(need_gb or 0.0))
    if need > budget:
        return "impossible"
    used = need / budget
    if used <= 0.75:
        return "perfect"
    if used <= 0.92:
        return "good"
    return "tight"


def fit_hub_row(
    row: Dict[str, Any],
    *,
    kind: str,
    budget: Dict[str, Any],
) -> Dict[str, Any]:
    """Annotate one candidate with quant, footprint, headroom and fit level."""
    out = dict(row)
    mid = str(out.get("id") or "")
    size_b = out.get("size_b") or parse_size_b(mid) or 0.0
    size_b = float(size_b)
    budget_gb = float(budget.get("budget_gb") or 0.0)
    native_ctx = int(out.get("native_ctx") or infer_native_ctx(mid, kind))
    n_ctx = max(512, min(int(budget.get("n_ctx") or 4096), native_ctx))

    if kind == "embedding":
        quant = _embed_quant_for_vram(size_b, float(budget.get("pool_gb") or 0.0))
    else:
        quant = _chat_quant_for_headroom(size_b, budget_gb, n_ctx)

    need = round(weight_gb(size_b, quant) + estimate_kv_cache_gb(size_b, n_ctx), 2)
    local = local_fit_level(need, budget_gb) if size_b > 0 else "impossible"
    llmfit_level = str(out.get("fit_level") or "").lower()

    out["size_b"] = size_b
    out["fit_quant"] = quant
    out["fit_n_ctx"] = n_ctx
    out["need_gb"] = need
    out["headroom_gb"] = round(budget_gb - need, 2)
    out["budget_gb"] = round(budget_gb, 2)
    out["local_fit_level"] = local
    if llmfit_level in _FIT_RANK:
        out["fit_level"] = llmfit_level
        out["fit_source"] = "llmfit"
    else:
        out["fit_level"] = local
        out["fit_source"] = "recipe"
    return out


def vendor_family(model_id: str) -> str:
    """Coarse family used to keep one publisher from filling the Acquire menu."""
    low = (model_id or "").lower()
    if "qwen" in low:
        return "qwen"
    if "gemma" in low:
        return "gemma"
    if "nemotron" in low:
        return "nemotron"
    if "nomic" in low:
        return "nomic"
    if "phi" in low:
        return "phi"
    return model_family_key(model_id) or "other"


def _diverse_role_picks(
    unique: Sequence[Dict[str, Any]],
    *,
    limit: int,
    per_family: int,
) -> List[Dict[str, Any]]:
    """Walk the ranked list family by family so Qwen cannot take every slot."""
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []
    for row in unique:
        fam = vendor_family(str(row.get("id") or ""))
        if fam not in buckets:
            buckets[fam] = []
            order.append(fam)
        buckets[fam].append(row)
    picked: List[Dict[str, Any]] = []
    seen: Set[int] = set()
    cap = max(1, int(per_family))
    for round_i in range(cap):
        for fam in order:
            if len(picked) >= limit:
                return picked
            group = buckets[fam]
            if len(group) <= round_i:
                continue
            row = group[round_i]
            picked.append(row)
            seen.add(id(row))
    for row in unique:
        if len(picked) >= limit:
            break
        if id(row) in seen:
            continue
        picked.append(row)
    return picked


def top_role_fits(
    rows: Sequence[Dict[str, Any]],
    *,
    kind: str,
    budget: Dict[str, Any],
    limit: int = 3,
    mainstream_only: bool = True,
    per_family: int = 2,
) -> List[Dict[str, Any]]:
    """Best-fitting candidates for one role: perfect first, impossible dropped."""
    scored = [fit_hub_row(r, kind=kind, budget=budget) for r in rows if r.get("id")]
    keep = [r for r in scored if r.get("fit_level") != "impossible"]
    if mainstream_only:
        mainstream = [r for r in keep if not is_community_variant(str(r.get("id") or ""))]
        keep = mainstream or keep

    def sort_key(r: Dict[str, Any]):
        # Chat: among models that fit, the bigger one is the better answer, so
        # capability leads and publisher quality breaks ties. Embedding: size is
        # not quality (and dim is a commitment), so score leads.
        if kind == "chat":
            return (
                fit_rank(str(r.get("fit_level"))),
                -float(r.get("size_b") or 0.0),
                -int(r.get("score") or 0),
            )
        return (
            fit_rank(str(r.get("fit_level"))),
            -int(r.get("score") or 0),
            -float(r.get("estimated_tps") or 0.0),
        )

    keep.sort(key=sort_key)
    # One entry per model, not per re-upload: three publishers of the same 14B
    # is a menu with one real choice on it. Then rotate vendors so the first
    # slots are not three sizes of the same family.
    unique: List[Dict[str, Any]] = []
    seen_keys: Set[str] = set()
    for row in keep:
        key = model_family_key(str(row.get("id") or ""))
        if key and key not in seen_keys:
            seen_keys.add(key)
            unique.append(row)
    return _diverse_role_picks(
        unique,
        limit=max(1, int(limit)),
        per_family=max(1, int(per_family)),
    )


def catalog_rows(kind: str) -> List[Dict[str, Any]]:
    """Offline candidates in Hub-row shape, for when the Hub is unreachable."""
    source = EMBED_CATALOG if kind == "embedding" else CHAT_CATALOG
    rows: List[Dict[str, Any]] = []
    for entry in source:
        row = {
            "id": entry["id"],
            "size_b": float(entry.get("params_b") or 0.0),
            "kind": kind,
            "native_ctx": int(entry.get("native_ctx") or 8192),
            "size_gb": weight_gb(
                float(entry.get("params_b") or 0.0), str(entry.get("quant") or "q4_k_m")
            ),
            "source": "catalog",
        }
        if kind == "embedding":
            row["dim"] = entry.get("dim")
        row["score"] = score_hub_row(row, kind=kind) + int(entry.get("quality") or 0)
        rows.append(row)
    return rows


def hardware_tier_labels(vram_gb: float) -> Tuple[str, str]:
    """Human-readable chat/embed guidance for Hardware Scan."""
    plan = plan_model_pair({"vram_gb": vram_gb})
    chat = (
        f"{plan['chat_id'].split('/')[-1]} {str(plan['chat_quant']).upper()} "
        f"(n_ctx {plan['chat_n_ctx']})"
    )
    embed = (
        f"{plan['embed_id'].split('/')[-1]} {str(plan['embed_quant']).upper()} "
        f"(n_ctx {plan['embed_n_ctx']})"
    )
    return chat, embed
