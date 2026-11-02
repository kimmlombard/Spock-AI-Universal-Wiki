"""Spock-Scanner assessment logic for Spock-to-bridge Hardware Scan.

Ported from D:\\Spock-Scanner (hardware check, spock_quartermaster, nvidia_detailed)
plus live-monitor / llamaccp config helpers. Launch is intentionally omitted.
Assesses LM Studio + llama.cpp (llamaccp / llama-server) for Spock workflows.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import psutil

    PSUTIL = True
except ImportError:
    PSUTIL = False

try:
    import pynvml

    PYNVML = True
except ImportError:
    PYNVML = False

SCRIPT_DIR = Path(__file__).resolve().parent
MODEL_GUIDE_PATH = SCRIPT_DIR / "MinimumHardwareForOllama.md"
# Prefer local copy; fall back to sibling / legacy install trees
_GUIDE_FALLBACKS = (
    Path(r"D:\Spock-Scanner\MinimumHardwareForOllama.md"),
    Path(r"D:\Spock-to-bridge\MinimumHardwareForOllama.md"),
    Path("/mnt/d/Spock-to-bridge/MinimumHardwareForOllama.md"),
    Path("/mnt/d/Spock-Scanner/MinimumHardwareForOllama.md"),
)
try:
    from WarpCore.service_endpoints import resolve_llama_server_path

    _llama_resolved, _ = resolve_llama_server_path()
    _llama_path = Path(_llama_resolved)
    if _llama_path.name.lower().startswith("llama-server"):
        DEFAULT_LLAMACPP_DIR = str(_llama_path.parent)
    else:
        DEFAULT_LLAMACPP_DIR = str(_llama_path)
except Exception:
    DEFAULT_LLAMACPP_DIR = os.environ.get(
        "LLAMA_SERVER_PATH", str(SCRIPT_DIR / "tools" / "llama-server")
    )
    _p = Path(DEFAULT_LLAMACPP_DIR)
    if _p.name.lower().startswith("llama-server"):
        DEFAULT_LLAMACPP_DIR = str(_p.parent)


# ── Ship status / LM Studio + llamaccp assessment ───────────────────────


def recommend_n_ctx(
    vram_gb: float,
    role: str = "chat",
    model_size_gb: Optional[float] = None,
    sibling_size_gb: Optional[float] = None,
) -> Dict[str, Any]:
    """Heuristic llama-server ``-c`` / n_ctx from VRAM (portable for public clones).

    Model weights consume VRAM first; remaining capacity roughly funds the KV cache.
    When embed (:8080) and chat (:8081) share one GPU, pass the other GGUF size as
    ``sibling_size_gb`` so chat context is not planned as if it owned the whole card.
    Large train-context models (e.g. 256K) still need enough free VRAM — Spock should
    pass an explicit ``-c`` rather than relying on the GGUF default.
    """
    from model_pick_policy import (
        CTX_LADDER,
        estimate_kv_cache_gb,
        plan_model_pair,
        recommended_embed_n_ctx,
        usable_vram_gb,
    )

    role = (role or "chat").lower()
    vram = float(vram_gb or 0.0)
    weights = float(model_size_gb or 0.0)
    sibling = float(sibling_size_gb or 0.0)
    budget = usable_vram_gb(vram) if vram > 0 else vram
    headroom = max(0.0, budget - weights * 1.10 - sibling * 1.10)

    if role.startswith("embed"):
        n_ctx = recommended_embed_n_ctx(vram)
        # 512 is too small for Spock truncate_chars≈1500 (~400–500 tokens).
        if vram >= 4:
            n_ctx = max(n_ctx, 1024)
        if vram >= 8:
            n_ctx = max(n_ctx, 2048)
        reason = (
            f"Embedding role on ~{vram:.0f}GB VRAM — batch size matters more than n_ctx; "
            f"recommend -c {n_ctx} so ingest chunks fit."
        )
    else:
        if weights > 0 and headroom > 0:
            params_b = max(1.0, weights / 0.58)
            chosen = 2048
            for cand in sorted(CTX_LADDER):
                if estimate_kv_cache_gb(params_b, cand) <= headroom:
                    chosen = cand
            n_ctx = int(chosen)
            reason = (
                f"Chat on ~{vram:.0f}GB VRAM, model ~{weights:.1f}GB"
                + (f", sibling ~{sibling:.1f}GB" if sibling else "")
                + f" -> ~{headroom:.1f}GB headroom for KV -> recommend -c {n_ctx}."
            )
        else:
            plan = plan_model_pair({"vram_gb": vram})
            n_ctx = int(plan.get("chat_n_ctx") or 8192)
            reason = (
                f"Chat on ~{vram:.0f}GB VRAM (no model size yet) -> "
                f"recommend -c {n_ctx} from the shared embed+chat planner. "
                "Re-check after picking a GGUF."
            )

    return {
        "n_ctx": int(n_ctx),
        "role": role,
        "vram_gb": vram,
        "model_size_gb": weights or None,
        "sibling_size_gb": sibling or None,
        "headroom_gb": round(headroom, 2) if (weights or sibling) else None,
        "reason": reason,
        "cli": f"-c {int(n_ctx)}",
    }


def get_ram_gb() -> float:
    if PSUTIL:
        return round(psutil.virtual_memory().total / (1024**3), 1)
    system = platform.system()
    try:
        if system == "Linux":
            with open("/proc/meminfo") as f:
                for line in f:
                    if "MemTotal" in line:
                        return round(int(line.split()[1]) / 1024 / 1024, 1)
        elif system == "Darwin":
            out = subprocess.check_output(["sysctl", "hw.memsize"]).decode()
            return round(int(out.split()[1]) / (1024**3), 1)
        elif system == "Windows":
            out = subprocess.check_output(
                ["wmic", "computersystem", "get", "TotalPhysicalMemory"],
                stderr=subprocess.DEVNULL,
            ).decode()
            return round(
                int([x for x in out.split() if x.isdigit()][0]) / (1024**3), 1
            )
    except Exception:
        pass
    return 4.0


def get_cpu_info():
    phys = psutil.cpu_count(logical=False) if PSUTIL else 2
    logical = psutil.cpu_count(logical=True) if PSUTIL else 4
    return phys, logical, platform.processor() or platform.machine()


def _gpus_look_weak(gpus: List[Dict[str, Any]]) -> bool:
    """True when NVML/nvidia-smi gave nothing usable (non-NVIDIA / broken driver)."""
    if not gpus:
        return True
    return not any(int(g.get("vram_mb") or 0) > 0 for g in gpus)


def _gpus_from_llmfit() -> List[Dict[str, Any]]:
    try:
        from spock_shell.llmfit_bridge import system_info, system_to_gpu_list
    except Exception:
        return []
    try:
        payload = system_info(timeout_s=20)
    except Exception:
        return []
    return system_to_gpu_list(payload)


def get_gpu_info() -> List[Dict[str, Any]]:
    gpus: List[Dict[str, Any]] = []
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        for line in out.decode().strip().split("\n"):
            if line:
                name, mem = [x.strip() for x in line.split(",")]
                vram_mb = int(mem.split()[0])
                gpus.append(
                    {
                        "vendor": "nvidia",
                        "name": name,
                        "vram_mb": vram_mb,
                        "source": "nvidia-smi",
                    }
                )
    except Exception:
        pass
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        ram_gb = get_ram_gb()
        gpus.append(
            {
                "vendor": "apple",
                "name": "Apple Silicon",
                "vram_mb": int(ram_gb * 1024 * 0.75),
                "source": "darwin-unified",
            }
        )
    # NVIDIA primary when healthy; otherwise merge llmfit (APU / AMD / weak NVML).
    if _gpus_look_weak(gpus):
        enriched = _gpus_from_llmfit()
        if enriched:
            gpus = enriched
    return gpus


def get_disk_free_gb(path: str = ".") -> float:
    total, used, free = shutil.disk_usage(path)
    return round(free / (1024**3), 1)


def _hardware_llm_tier(ram: float, gpus: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Shared VRAM/RAM tier used by LM Studio and llamaccp assessments."""
    disk = get_disk_free_gb()
    base: Dict[str, Any] = {
        "can_run": False,
        "tier": "none",
        "chat_model": None,
        "embed_model": None,
        "estimated_tokens_per_sec": 0,
        "ngl": 0,
        "reason": "",
        "vram_gb": 0.0,
        "best_gpu": None,
        "gpu_count": len(gpus),
        "gpus": gpus,
        "disk_free_gb": disk,
        "has_nvidia": any(g.get("vendor") == "nvidia" for g in gpus),
        "has_metal": any(g.get("vendor") == "apple" for g in gpus),
    }

    if gpus:
        best_gpu = max(gpus, key=lambda g: g.get("vram_mb", 0))
        vram_gb = best_gpu["vram_mb"] / 1024
        base["best_gpu"] = best_gpu
        base["vram_gb"] = vram_gb
        from model_pick_policy import hardware_tier_labels

        chat_lbl, embed_lbl = hardware_tier_labels(vram_gb)
        if vram_gb >= 40:
            base.update(
                {
                    "can_run": True,
                    "tier": "gpu_high",
                    "chat_model": chat_lbl,
                    "embed_model": embed_lbl,
                    "estimated_tokens_per_sec": 22,
                    "ngl": 99,
                    "reason": f"{vram_gb:.0f}GB VRAM (best GPU) — prefer 8–14B + large n_ctx over 70B",
                }
            )
        elif vram_gb >= 20:
            base.update(
                {
                    "can_run": True,
                    "tier": "gpu_mid_high",
                    "chat_model": chat_lbl,
                    "embed_model": embed_lbl,
                    "estimated_tokens_per_sec": 28,
                    "ngl": 99,
                    "reason": f"{vram_gb:.0f}GB VRAM (best GPU)",
                }
            )
        elif vram_gb >= 12:
            base.update(
                {
                    "can_run": True,
                    "tier": "gpu_mid",
                    "chat_model": chat_lbl,
                    "embed_model": embed_lbl,
                    "estimated_tokens_per_sec": 35,
                    "ngl": 99,
                    "reason": f"{vram_gb:.0f}GB VRAM (best GPU)",
                }
            )
        elif vram_gb >= 6:
            base.update(
                {
                    "can_run": True,
                    "tier": "gpu_low",
                    "chat_model": chat_lbl,
                    "embed_model": embed_lbl,
                    "estimated_tokens_per_sec": 40,
                    "ngl": 99,
                    "reason": f"{vram_gb:.0f}GB VRAM (best GPU)",
                }
            )
        else:
            base["reason"] = (
                f"GPU VRAM {vram_gb:.1f}GB too low for comfortable GPU offload. "
                "Falling back to CPU / partial offload."
            )

    if not base["can_run"]:
        from model_pick_policy import hardware_tier_labels

        # plan_model_pair with tiny/zero VRAM still returns criteria-aligned pairs.
        chat_lbl, embed_lbl = hardware_tier_labels(0.0)
        if ram < 2:
            base.update(
                {
                    "tier": "none",
                    "reason": "<2GB RAM. OS needs this.",
                    "chat_model": None,
                    "embed_model": None,
                }
            )
        elif ram < 4:
            base.update(
                {
                    "can_run": True,
                    "tier": "cpu_tiny",
                    "chat_model": chat_lbl,
                    "embed_model": embed_lbl,
                    "estimated_tokens_per_sec": 5,
                    "ngl": 0,
                    "reason": f"{ram}GB RAM (CPU)",
                }
            )
        elif ram < 8:
            base.update(
                {
                    "can_run": True,
                    "tier": "cpu_small",
                    "chat_model": chat_lbl,
                    "embed_model": embed_lbl,
                    "estimated_tokens_per_sec": 3,
                    "ngl": 0,
                    "reason": f"{ram}GB RAM (CPU)",
                }
            )
        elif ram < 16:
            base.update(
                {
                    "can_run": True,
                    "tier": "cpu_medium",
                    "chat_model": chat_lbl,
                    "embed_model": embed_lbl,
                    "estimated_tokens_per_sec": 1.5,
                    "ngl": 0,
                    "reason": f"{ram}GB RAM (CPU)",
                }
            )
        else:
            base.update(
                {
                    "can_run": True,
                    "tier": "cpu_large",
                    "chat_model": chat_lbl,
                    "embed_model": embed_lbl,
                    "estimated_tokens_per_sec": 0.5,
                    "ngl": 0,
                    "reason": f"{ram}GB RAM (CPU)",
                }
            )
            if base.get("vram_gb", 0) > 0:
                base["ngl"] = max(1, int(base["vram_gb"] * 3))

    return base


def assess_lm_studio(ram: float, gpus: List[Dict[str, Any]]) -> Dict[str, Any]:
    """LM Studio: GUI GGUF chat host (Ask AI often on :1234)."""
    base = _hardware_llm_tier(ram, gpus)
    disk = base["disk_free_gb"]
    result = {
        **base,
        "engine": "lm_studio",
        "role": "Chat / Ask AI (instruct models)",
        "typical_port": "1234",
        "backend": "LM Studio server (OpenAI-compatible)",
        "recommended": base.get("chat_model"),
        "advice": "",
        "details": [],
        "notes": [],
    }

    details = [
        "Load an instruct/chat GGUF in LM Studio (not an embedding model).",
        "Start Local Server (default http://localhost:1234).",
        "In Spock: right dock → Ask AI → Connect to LM Studio → Save.",
        "Keep embeddings on Spock Launch / Config (separate process + URL).",
    ]
    if result["has_nvidia"]:
        details.append(
            "Enable GPU acceleration (CUDA) in LM Studio hardware settings."
        )
    elif result["has_metal"]:
        details.append(
            "Apple Silicon: LM Studio uses Metal; unified memory shared with OS."
        )
    else:
        details.append("No NVIDIA/Metal GPU detected — expect CPU-only speeds.")

    if result["gpu_count"] >= 2:
        details.append(
            f"{result['gpu_count']} GPUs detected: use LM Studio for chat on one GPU; "
            "run Spock Launch embedding server on the other."
        )

    advice_parts = []
    if not result["can_run"]:
        advice_parts.append(
            "Not suitable for local chat. Use a cloud API or Colab while learning."
        )
    elif str(result["tier"]).startswith("cpu_"):
        advice_parts.append(
            "LM Studio will run, but CPU-only is slow. Prefer small Q4 models for demos."
        )
    else:
        advice_parts.append(
            "Good fit for Spock Ask AI chat. Pair with a Launch embedding server for RAG."
        )
    if disk < 10:
        advice_parts.append(
            f"WARNING: only {disk}GB disk free — GGUF models are often 2–15GB each."
        )

    result["details"] = details
    result["advice"] = " ".join(advice_parts)
    result["notes"] = [
        "Do not point Spock Embeddings URL at LM Studio chat.",
        "Embedding GGUFs on the LM Studio chat endpoint produce garbage answers.",
    ]
    return result


def assess_llamaccp(ram: float, gpus: List[Dict[str, Any]]) -> Dict[str, Any]:
    """llama.cpp / llamaccp llama-server via Spock Launch (chat + embeddings)."""
    base = _hardware_llm_tier(ram, gpus)
    disk = base["disk_free_gb"]
    result = {
        **base,
        "engine": "llamaccp",
        "role": "Chat + Embeddings (Spock Launch / llama-server)",
        "typical_ports": "embeddings :8080 · chat :8081 · RAG API :8090",
        "backend": "llama-server (llamaccp) with CUDA_VISIBLE_DEVICES / -ngl",
        "recommended_chat": base.get("chat_model"),
        "recommended_embed": base.get("embed_model"),
        "advice": "",
        "details": [],
        "notes": [],
    }

    details = [
        "Spock left-nav → Launch → SCAN MODELS → pick a .gguf.",
        "Chat: instruct GGUF, “Use as embedding server” OFF, own port (e.g. 8081).",
        "Embeddings: embedding GGUF, checkbox ON, different port (e.g. 8080).",
        "Config → Embeddings URL must match the embedding port "
        "(e.g. http://localhost:8080/embeddings).",
        "Optional: Config → START RAG API on :8090 (JSON API, not a chat page).",
    ]
    if result["has_nvidia"]:
        details.append(
            f"Recommended GPU offload: -ngl {result.get('ngl', 99)} "
            "(Launch GPU Layers; -1 = auto)."
        )
        details.append(
            "NVIDIA drivers + CUDA build of llama-server required for GPU layers."
        )
    elif result["has_metal"]:
        details.append(
            "macOS: use a Metal-capable llama-server build; -ngl still helps."
        )
    else:
        details.append(
            "No NVIDIA GPU — llama-server will be CPU-bound; keep -ngl 0 / small models."
        )

    vram = float(result.get("vram_gb") or 0.0)
    chat_ctx = recommend_n_ctx(vram, role="chat")
    embed_ctx = recommend_n_ctx(vram if vram else 8.0, role="embedding")
    result["recommended_n_ctx_chat"] = chat_ctx["n_ctx"]
    result["recommended_n_ctx_embed"] = embed_ctx["n_ctx"]
    result["n_ctx_chat_info"] = chat_ctx
    result["n_ctx_embed_info"] = embed_ctx
    details.append(
        f"Recommended chat context: -c {chat_ctx['n_ctx']} ({chat_ctx['reason']})"
    )
    details.append(
        f"Recommended embed context: -c {embed_ctx['n_ctx']} ({embed_ctx['reason']})"
    )
    details.append(
        "Launch → Context (-c) applies this; prefer chat on the largest GPU. "
        "GGUF train-ctx defaults (e.g. 256K) can OOM smaller cards — set -c explicitly."
    )

    if result["gpu_count"] >= 2:
        names = ", ".join(
            f"{g.get('name')} ({g.get('vram_mb', 0) // 1024}GB)" for g in gpus
        )
        details.append(
            f"Dual/multi-GPU ({names}): assign chat to one GPU and embeddings to "
            "another via Launch GPU combo (CUDA_VISIBLE_DEVICES)."
        )

    advice_parts = []
    if not result["can_run"]:
        advice_parts.append(
            "Cannot comfortably run llama-server locally. Upgrade RAM/GPU first."
        )
    elif not result["has_nvidia"] and not result["has_metal"]:
        advice_parts.append(
            "CPU mode works for learning RAG plumbing; ingest will be slow."
        )
    else:
        advice_parts.append(
            "Ready for Spock dual-server layout (chat + embeddings on separate ports)."
        )
    if disk < 10:
        advice_parts.append(
            f"WARNING: only {disk}GB disk free — keep models under "
            "LM Studio / Spock models folders with room to spare."
        )

    result["details"] = details
    result["advice"] = " ".join(advice_parts)
    result["notes"] = [
        "Never mix chat and embeddings on the same port.",
        "Do not open an embedding server’s web UI for chat — use Ask AI / instruct port.",
        "See Hardware Scan → llamaccp config for sample scripts.",
    ]
    return result


def assess_ollama(ram, cpu_phys, gpus) -> Dict[str, Any]:
    """Deprecated alias — Ollama removed from Ship status; returns llamaccp assessment."""
    _ = cpu_phys
    return assess_llamaccp(ram, gpus)


def run_ship_status_scan() -> Dict[str, Any]:
    ram = get_ram_gb()
    cpu_phys, cpu_log, cpu_name = get_cpu_info()
    gpus = get_gpu_info()
    gpu_sources = sorted({str(g.get("source") or "unknown") for g in gpus})
    sysinfo = {
        "os": f"{platform.system()} {platform.release()}",
        "cpu_name": cpu_name,
        "cpu_physical": cpu_phys,
        "cpu_logical": cpu_log,
        "ram_gb": ram,
        "disk_free_gb": get_disk_free_gb(),
        "gpus": gpus,
        "gpu_sources": gpu_sources,
        "llmfit_gpu_enrichment": any(g.get("source") == "llmfit" for g in gpus),
        "psutil_installed": PSUTIL,
    }
    return {
        "system": sysinfo,
        "lm_studio": assess_lm_studio(ram, gpus),
        "llamaccp": assess_llamaccp(ram, gpus),
    }


def _format_compat_block(title: str, data: Dict[str, Any]) -> List[str]:
    lines = [
        "",
        "=" * 50,
        title,
        "=" * 50,
        "",
    ]
    if data.get("can_run", False):
        lines.append("RESULT: CAN RUN")
    else:
        lines.append("RESULT: NOT RECOMMENDED")
    lines.append(f"TIER: {data.get('tier', 'N/A')}")
    if data.get("role"):
        lines.append(f"ROLE: {data['role']}")
    if data.get("backend"):
        lines.append(f"BACKEND: {data['backend']}")
    if data.get("typical_port"):
        lines.append(f"TYPICAL PORT: {data['typical_port']}")
    if data.get("typical_ports"):
        lines.append(f"TYPICAL PORTS: {data['typical_ports']}")

    if data.get("engine") == "lm_studio":
        lines.append(f"RECOMMENDED CHAT: {data.get('recommended') or 'N/A'}")
    else:
        lines.append(f"RECOMMENDED CHAT: {data.get('recommended_chat') or 'N/A'}")
        lines.append(f"RECOMMENDED EMBED: {data.get('recommended_embed') or 'N/A'}")
        if data.get("ngl") is not None:
            lines.append(f"GPU LAYERS (-ngl): {data.get('ngl')}")
        if data.get("recommended_n_ctx_chat"):
            lines.append(f"CHAT CONTEXT (-c): {data.get('recommended_n_ctx_chat')}")
        if data.get("recommended_n_ctx_embed"):
            lines.append(f"EMBED CONTEXT (-c): {data.get('recommended_n_ctx_embed')}")

    speed = data.get("estimated_tokens_per_sec", 0)
    lines.append(f"SPEED: ~{speed} tokens/sec (rough chat estimate)")
    lines.append(f"REASON: {data.get('reason', 'N/A')}")

    details = data.get("details") or []
    if details:
        lines.append("")
        lines.append("DETAILS:")
        for d in details:
            lines.append(f"  • {d}")

    notes = data.get("notes") or []
    if notes:
        lines.append("")
        lines.append("NOTES:")
        for n in notes:
            lines.append(f"  • {n}")

    lines.append(f"\nADVICE: {data.get('advice', '')}")
    return lines


def format_ship_status(data: Dict[str, Any], capacity_report: str = "") -> str:
    sysinfo = data.get("system", {})
    lines = [
        "=" * 50,
        "HARDWARE SCAN RESULTS",
        "=" * 50,
        "",
        f"OS: {sysinfo.get('os', 'N/A')}",
        f"RAM: {sysinfo.get('ram_gb', 'N/A')} GB",
        f"CPU: {sysinfo.get('cpu_name', 'N/A')}",
        f"Cores: {sysinfo.get('cpu_physical', '?')}/{sysinfo.get('cpu_logical', '?')} (P/L)",
        f"Disk Free: {sysinfo.get('disk_free_gb', 'N/A')} GB",
    ]
    gpus = sysinfo.get("gpus", [])
    if gpus:
        for gpu in gpus:
            vram_gb = gpu.get("vram_mb", 0) // 1024
            lines.append(f"GPU: {gpu.get('name', 'Unknown')} ({vram_gb}GB)")
        best = max(gpus, key=lambda g: g.get("vram_mb", 0))
        lines.append(
            f"Best GPU: {best.get('name')} ({best.get('vram_mb', 0) // 1024}GB)"
        )
    else:
        lines.append("GPU: None (CPU mode)")

    lm = data.get("lm_studio")
    llama = data.get("llamaccp")
    if lm is None and data.get("ollama"):
        lm = data["ollama"]
    if llama is None and data.get("ollama"):
        llama = data["ollama"]

    if lm:
        lines.extend(_format_compat_block("LM STUDIO COMPATIBILITY", lm))
    if llama:
        lines.extend(
            _format_compat_block("LLAMACCP / llama.cpp COMPATIBILITY", llama)
        )

    if capacity_report:
        lines.extend(["", capacity_report])

    return "\n".join(lines)


# ── Upgrade advice ──────────────────────────────────────────────────────


def get_upgrade_recommendations() -> Dict[str, Any]:
    try:
        ram_gb = round(psutil.virtual_memory().total / (1024**3), 1) if PSUTIL else 8
        has_psutil = PSUTIL
    except Exception:
        ram_gb = 8
        has_psutil = False

    recommendations = []

    if ram_gb < 8:
        recommendations.append(
            {
                "priority": "high",
                "component": "RAM",
                "current": f"{ram_gb}GB",
                "recommended": "16GB",
                "reason": "8GB is the sweet spot for local AI. 16GB opens up 3B–4B Q4 GGUFs in LM Studio / llama-server.",
                "estimated_cost": "$40-80",
            }
        )
    elif ram_gb < 16:
        recommendations.append(
            {
                "priority": "medium",
                "component": "RAM",
                "current": f"{ram_gb}GB",
                "recommended": "32GB",
                "reason": "32GB enables 8B GGUF models at acceptable CPU/partial-GPU speeds.",
                "estimated_cost": "$80-150",
            }
        )

    try:
        total, used, free = shutil.disk_usage(".")
        free_gb = round(free / (1024**3), 1)
        if free_gb < 10:
            recommendations.append(
                {
                    "priority": "high",
                    "component": "Storage",
                    "current": f"{free_gb}GB free",
                    "recommended": "50GB+ free",
                    "reason": "GGUF models are often 2–15GB each. Keep room for chat + embedding models.",
                    "estimated_cost": "$0 (clear space)",
                }
            )
    except Exception:
        pass

    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        gpu_lines = out.decode().strip().split("\n")
        gpu_descs = []
        best_vram = 0
        best_name = ""
        for line in gpu_lines:
            if line.strip():
                parts = [x.strip() for x in line.split(",")]
                name = parts[0]
                vram = int(parts[1].split()[0]) if len(parts) > 1 else 0
                gpu_descs.append(f"{name} ({vram // 1024}GB)")
                if vram > best_vram:
                    best_vram = vram
                    best_name = name
        current_str = ", ".join(gpu_descs) if gpu_descs else "Nvidia detected"
        recommendations.append(
            {
                "priority": "optional",
                "component": "GPU",
                "current": current_str,
                "recommended": "Already have GPU(s)!",
                "reason": (
                    f"Best GPU: {best_name} ({best_vram // 1024}GB VRAM)"
                    if best_name
                    else "You can run local AI at full speed."
                ),
                "estimated_cost": "$0",
            }
        )
    except Exception:
        if ram_gb >= 16:
            recommendations.append(
                {
                    "priority": "medium",
                    "component": "GPU",
                    "current": "No GPU",
                    "recommended": "NVIDIA RTX 3060+ (12GB VRAM)",
                    "reason": "Unlocks 7B-13B models at 20+ tokens/sec.",
                    "estimated_cost": "$200-400",
                }
            )

    if ram_gb >= 16:
        overall = "ready"
        message = "Your system is ready for local AI experiments!"
    elif ram_gb >= 8:
        overall = "limited"
        message = "You can run small Q4 GGUFs (Phi-class). Consider RAM upgrade for better experience."
    else:
        overall = "minimal"
        message = "CPU-only mode. Works for learning but limited. Consider upgrading RAM."

    return {
        "has_psutil": has_psutil,
        "overall": overall,
        "message": message,
        "recommendations": recommendations,
        "platform": platform.system(),
    }


def format_upgrade_report(data: Dict[str, Any]) -> str:
    lines = [
        "=" * 50,
        "UPGRADE RECOMMENDATIONS",
        "=" * 50,
        "",
        f"Assessment: {data.get('overall', 'unknown').upper()}",
        f"{data.get('message', '')}",
        "",
    ]
    for rec in data.get("recommendations", []):
        lines.append(f"[{rec.get('priority', '').upper()}] {rec.get('component', '')}")
        lines.append(f"  Current: {rec.get('current', '')}")
        lines.append(f"  Recommended: {rec.get('recommended', '')}")
        lines.append(f"  Reason: {rec.get('reason', '')}")
        lines.append(f"  Est. Cost: {rec.get('estimated_cost', '')}")
        lines.append("")
    if not data.get("recommendations"):
        lines.append("No upgrades needed. You're ready!")
        lines.append("")
    lines.extend(
        [
            "=" * 50,
            "Next steps: https://lmstudio.ai  ·  Spock Launch / llamaccp config",
        ]
    )
    return "\n".join(lines)


# ── GPU details (NVML) ──────────────────────────────────────────────────


def _query_gpu(handle, index: int) -> Dict[str, Any]:
    try:
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode("utf-8")
    except Exception:
        name = f"GPU {index}"

    try:
        uuid = pynvml.nvmlDeviceGetUUID(handle)
        if isinstance(uuid, bytes):
            uuid = uuid.decode("utf-8")
    except Exception:
        uuid = ""

    try:
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
    except Exception:
        info = type("obj", (object,), {"total": 0, "used": 0, "free": 0})()

    try:
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
    except Exception:
        util = type("obj", (object,), {"gpu": 0, "encoder": 0, "decoder": 0})()

    try:
        mem_util = pynvml.nvmlDeviceGetMemoryUtilizationRates(handle)
        mem_util_percent = getattr(mem_util, "memory", 0)
    except Exception:
        mem_util_percent = 0

    try:
        clock_sm = pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_SM)
        clock_mem = pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_MEM)
        max_clock_sm = pynvml.nvmlDeviceGetMaxClockInfo(handle, pynvml.NVML_CLOCK_SM)
        max_clock_mem = pynvml.nvmlDeviceGetMaxClockInfo(handle, pynvml.NVML_CLOCK_MEM)
    except Exception:
        clock_sm = clock_mem = max_clock_sm = max_clock_mem = 0

    try:
        temp_sensor = getattr(
            pynvml, "NVML_TEMPERATURE_GPU", getattr(pynvml, "NVML_TEMPSENSOR_GPU", 0)
        )
        temp = pynvml.nvmlDeviceGetTemperature(handle, temp_sensor)
    except Exception:
        temp = 0

    try:
        power = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0
        power_limit = pynvml.nvmlDeviceGetPowerManagementLimit(handle) / 1000.0
    except Exception:
        power = power_limit = 0

    try:
        fan_speed = pynvml.nvmlDeviceGetFanSpeed(handle)
    except Exception:
        fan_speed = 0

    try:
        pcie = pynvml.nvmlDeviceGetPciInfo(handle)
        pci_bus = f"{pcie.bus:02x}:{pcie.device:02x}.{pcie.function}"
        pci_generation = pynvml.nvmlDeviceGetMaxPcieLinkGeneration(handle)
        pci_width = pynvml.nvmlDeviceGetMaxPcieLinkWidth(handle)
    except Exception:
        pci_bus = ""
        pci_generation = 0
        pci_width = 0

    try:
        compute_cap = pynvml.nvmlDeviceGetCudaComputeCapability(handle)
        compute_cap_str = f"{compute_cap[0]}.{compute_cap[1]}"
    except Exception:
        compute_cap_str = ""

    return {
        "index": index,
        "name": name,
        "uuid": uuid,
        "pci_bus": pci_bus,
        "compute_capability": compute_cap_str,
        "memory": {
            "total_mb": info.total // (1024 * 1024),
            "used_mb": info.used // (1024 * 1024),
            "free_mb": info.free // (1024 * 1024),
            "total_gb": round(info.total / (1024**3), 2),
            "used_gb": round(info.used / (1024**3), 2),
            "free_gb": round(info.free / (1024**3), 2),
        },
        "utilization": {
            "gpu_percent": util.gpu,
            "memory_percent": mem_util_percent,
            "encoder_percent": getattr(util, "encoder", 0),
            "decoder_percent": getattr(util, "decoder", 0),
        },
        "clocks": {
            "current_sm_mhz": clock_sm,
            "current_memory_mhz": clock_mem,
            "max_sm_mhz": max_clock_sm,
            "max_memory_mhz": max_clock_mem,
        },
        "thermal": {"temperature_c": temp},
        "power": {"current_watts": power, "limit_watts": power_limit},
        "pcie": {"generation": pci_generation, "width": f"x{pci_width}"},
        "fan": {"speed_percent": fan_speed},
    }


def get_gpu_details() -> Dict[str, Any]:
    if not PYNVML:
        import sys

        py = sys.executable
        return {
            "available": False,
            "error": (
                "nvidia-ml-py (import pynvml) is not installed for the Python "
                f"running this app:\n  {py}\n\n"
                "Install into THAT interpreter:\n"
                f'  "{py}" -m pip install nvidia-ml-py\n\n'
                "Note: activating a different project's .venv, or running bare "
                "`pip install`, can put the package in the wrong environment."
            ),
        }
    try:
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        gpus = []
        for i in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            gpus.append(_query_gpu(handle, i))
        return {"available": True, "gpu_count": count, "gpus": gpus}
    except Exception as e:
        return {"available": False, "error": str(e)}


def format_gpu_details(data: Dict[str, Any]) -> str:
    if not data.get("available", False):
        return (
            "=" * 48
            + "\nNVIDIA GPU DETAILS\n"
            + "=" * 48
            + f"\n\nERROR: {data.get('error', 'Unknown')}\n"
        )

    lines = [
        "=" * 48,
        f"NVIDIA DEEP DIVE - {data.get('gpu_count', 0)} GPU(s)",
        "=" * 48,
        "",
    ]
    for gpu in data.get("gpus", []):
        mem = gpu.get("memory", {})
        util = gpu.get("utilization", {})
        clocks = gpu.get("clocks", {})
        thermal = gpu.get("thermal", {})
        power = gpu.get("power", {})
        pcie = gpu.get("pcie", {})
        fan = gpu.get("fan", {})
        lines.extend(
            [
                "=" * 48,
                f"GPU #{gpu.get('index')}: {gpu.get('name')}",
                "=" * 48,
                "",
                f"  UUID: {gpu.get('uuid')}",
                f"  PCI Bus: {gpu.get('pci_bus')}",
                f"  Compute Capability: {gpu.get('compute_capability')}",
                "",
                "  [MEMORY]",
                f"    Total: {mem.get('total_gb')} GB",
                f"    Used:  {mem.get('used_gb')} GB",
                f"    Free:  {mem.get('free_gb')} GB",
                "",
                "  [UTILIZATION]",
                f"    GPU:     {util.get('gpu_percent')}%",
                f"    Memory:  {util.get('memory_percent')}%",
                f"    Encoder: {util.get('encoder_percent')}%",
                f"    Decoder: {util.get('decoder_percent')}%",
                "",
                "  [CLOCKS]",
                f"    Current SM/Mem: {clocks.get('current_sm_mhz')} / {clocks.get('current_memory_mhz')} MHz",
                f"    Max SM/Mem:     {clocks.get('max_sm_mhz')} / {clocks.get('max_memory_mhz')} MHz",
                "",
                "  [THERMAL]",
                f"    Temperature: {thermal.get('temperature_c')}C",
                "",
                "  [POWER]",
                f"    Current: {power.get('current_watts')} W",
                f"    Limit:   {power.get('limit_watts')} W",
                "",
                "  [PCIe]",
                f"    Generation: Gen{pcie.get('generation')}",
                f"    Width:     {pcie.get('width')}",
                "",
                "  [FAN]",
                f"    Speed: {fan.get('speed_percent')}%",
                "",
            ]
        )
    lines.append("=" * 48)
    return "\n".join(lines)


# ── Live monitor snapshot ───────────────────────────────────────────────


def get_live_monitor_snapshot() -> Dict[str, Dict[str, str]]:
    """CPU/Memory plus one section per GPU (not averaged)."""
    snap: Dict[str, Dict[str, str]] = {
        "CPU": {"Usage": "--", "Threads": "--", "Cores": "--", "Frequency": "--"},
        "Memory": {
            "Total": "--",
            "Used": "--",
            "Available": "--",
            "Percent": "--",
        },
    }
    if PSUTIL:
        cpu = psutil.cpu_percent(interval=0)
        cpu_count = psutil.cpu_count()
        freq = psutil.cpu_freq()
        freq_str = f"{freq.current:.0f} MHz" if freq else "N/A"
        mem = psutil.virtual_memory()
        try:
            threads = len(psutil.Process().threads())
        except Exception:
            threads = "--"
        snap["CPU"] = {
            "Usage": f"{cpu}%",
            "Threads": str(threads),
            "Cores": str(cpu_count),
            "Frequency": freq_str,
        }
        snap["Memory"] = {
            "Total": f"{round(mem.total / (1024**3), 1)} GB",
            "Used": f"{round(mem.used / (1024**3), 1)} GB",
            "Available": f"{round(mem.available / (1024**3), 1)} GB",
            "Percent": f"{mem.percent}%",
        }

    if PYNVML:
        try:
            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            for i in range(count):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(h)
                if isinstance(name, bytes):
                    name = name.decode("utf-8")
                util = pynvml.nvmlDeviceGetUtilizationRates(h)
                mem = pynvml.nvmlDeviceGetMemoryInfo(h)
                try:
                    power = pynvml.nvmlDeviceGetPowerUsage(h) / 1000.0
                    power_s = f"{power:.1f} W"
                except Exception:
                    power_s = "N/A"
                try:
                    temp_sensor = getattr(
                        pynvml,
                        "NVML_TEMPERATURE_GPU",
                        getattr(pynvml, "NVML_TEMPSENSOR_GPU", 0),
                    )
                    temp = pynvml.nvmlDeviceGetTemperature(h, temp_sensor)
                    temp_s = f"{temp} C"
                except Exception:
                    temp_s = "N/A"
                short = name if len(name) <= 28 else name[:25] + "..."
                snap[f"GPU {i}"] = {
                    "Name": short,
                    "Utilization": f"{util.gpu}%",
                    "Temperature": temp_s,
                    "VRAM Used": f"{round(mem.used / (1024**3), 2)} GB",
                    "VRAM Free": f"{round(mem.free / (1024**3), 2)} GB",
                    "Power": power_s,
                }
        except Exception:
            snap["GPU 0"] = {
                "Name": "--",
                "Utilization": "--",
                "Temperature": "--",
                "VRAM Used": "--",
                "VRAM Free": "--",
                "Power": "--",
            }
    else:
        snap["GPU 0"] = {
            "Name": "NVML unavailable",
            "Utilization": "--",
            "Temperature": "--",
            "VRAM Used": "--",
            "VRAM Free": "--",
            "Power": "--",
        }
    return snap


# ── llama.cpp config ────────────────────────────────────────────────────


def _get_best_gpu_info() -> Optional[Dict[str, Any]]:
    if not PYNVML:
        return None
    best = None
    try:
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        for i in range(count):
            h = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(h)
            if isinstance(name, bytes):
                name = name.decode("utf-8")
            mem = pynvml.nvmlDeviceGetMemoryInfo(h)
            vram_gb = round(mem.total / (1024**3), 1)
            if best is None or mem.total > best["mem_bytes"]:
                best = {
                    "index": i,
                    "name": name,
                    "vram_gb": vram_gb,
                    "mem_bytes": mem.total,
                    "gpu_count": count,
                }
    except Exception:
        return None
    return best


def _find_gguf_models(llama_dir: str) -> List[Path]:
    models = []
    search_paths = [
        Path(llama_dir) / "models",
        Path.home() / ".lmstudio" / "models",
        Path.home() / ".ollama" / "models",
        SCRIPT_DIR / "models",
        Path(r"D:\Spock-Model-Selector\models"),
    ]
    for sp in search_paths:
        if sp.exists():
            for f in sp.rglob("*.gguf"):
                if f.name.startswith("mmproj"):
                    continue
                models.append(f)
    return models


def generate_llamaccp_config(llama_dir: Optional[str] = None) -> str:
    llama_dir = llama_dir or DEFAULT_LLAMACPP_DIR
    best = _get_best_gpu_info()
    lines = [
        "=" * 50,
        "LLAMACCP / llama-server — Spock-to-bridge layout",
        "=" * 50,
        "",
        "Spock separates THREE things:",
        "",
        "  1) CHAT LLM  — instruct GGUF for Ask AI answers",
        "       • LM Studio (often :1234)  OR",
        "       • Launch → select chat GGUF, embedding checkbox OFF",
        "",
        "  2) EMBEDDINGS — embedding GGUF for wiki ingest + hybrid RAG",
        "       • Launch → embedding GGUF + “Use as embedding server”",
        "       • App Tools → Config → Embeddings URL must match that port",
        "       • Example: http://localhost:8080/embeddings",
        "",
        "  3) RAG API (optional) — OpenAI-compatible front door over ship_computer.db",
        "       • Config → START RAG API → http://127.0.0.1:8090/v1",
        "       • Model id: spock-ships-computer",
        "       • Not a browser chat page (JSON API only)",
        "",
        "Do NOT put chat and embeddings on the same port.",
        "Do NOT open the embedding server’s web UI for chat.",
        "Prefer left-nav → Launch over hand-edited scripts when possible.",
        "",
        "-" * 50,
        "GPU / -ngl RECOMMENDATION",
        "-" * 50,
        "",
    ]
    if not best:
        lines.append("ERROR: No NVIDIA GPU detected.")
        lines.append("llamaccp requires an NVIDIA GPU with CUDA.")
        lines.append("")
        lines.append("Use left-nav Launch in Spock-to-bridge to start llama-server.")
        return "\n".join(lines)

    vram_gb = best["vram_gb"]
    gpu_index = best["index"]
    gpu_name = best["name"]
    gpu_count = best.get("gpu_count", 1)

    if vram_gb >= 20:
        layers = 99
        model_tier = "large (13B-70B quantized OK)"
    elif vram_gb >= 10:
        layers = 99
        model_tier = "medium (7B-13B)"
    else:
        layers = max(1, int(vram_gb * 3))
        model_tier = "small (1B-3B) or offload carefully"

    chat_ctx = recommend_n_ctx(vram_gb, role="chat")
    embed_ctx = recommend_n_ctx(vram_gb, role="embedding")

    lines.extend(
        [
            f"Detected GPUs: {gpu_count}",
            f"Best GPU: GPU #{gpu_index} - {gpu_name} ({vram_gb} GB VRAM)",
            f"llamaccp path: {llama_dir}",
            "",
            f"Recommended GPU offload: -ngl {layers}",
            f"Recommended chat model tier: {model_tier}",
            f"Recommended chat context: -c {chat_ctx['n_ctx']}",
            f"  ({chat_ctx['reason']})",
            f"Recommended embed context: -c {embed_ctx['n_ctx']}",
            f"  ({embed_ctx['reason']})",
            "",
            "Note: Many GGUFs advertise huge train contexts (e.g. 256K). That default can",
            "fill a 24GB card with KV cache alone. Spock Launch should pass an explicit -c.",
            "",
            "Suggested ports (example dual-server setup):",
            "  Embeddings:          :8080   (--embeddings --no-webui)",
            "  Chat (instruct):     :8081   (no --embeddings, web UI OK)",
            "  RAG API (optional):  :8090   (Spock START RAG API)",
            "",
        ]
    )

    models = _find_gguf_models(llama_dir)
    chat_model = None
    embed_model = None
    if models:
        lines.append(f"Found {len(models)} model(s) under local paths (sample):")
        for i, m in enumerate(models[:25]):
            tag = ""
            name_l = m.name.lower()
            if "embed" in name_l:
                tag = "  [embedding]"
                if embed_model is None:
                    embed_model = m
            else:
                if chat_model is None:
                    chat_model = m
            lines.append(f"  [{i + 1}] {m}{tag}")
        if len(models) > 25:
            lines.append(f"  ... and {len(models) - 25} more")
        lines.append("")
        # Prefer size near ~half VRAM for chat pick among non-embed
        if chat_model is None:
            chat_model = models[0]
        best_size = 0.0
        for m in models:
            if "embed" in m.name.lower():
                continue
            size_gb = m.stat().st_size / (1024**3)
            if best_size == 0 or abs(size_gb - vram_gb * 0.5) < abs(
                best_size - vram_gb * 0.5
            ):
                chat_model = m
                best_size = size_gb
        if embed_model is None:
            for m in models:
                if "embed" in m.name.lower():
                    embed_model = m
                    break
    else:
        lines.append("WARNING: No .gguf models found in scanned paths.")
        lines.append("Use Launch → All sources → SCAN MODELS.")
        lines.append("")

    chat_path = str(chat_model) if chat_model else r".\models\your-chat-instruct.gguf"
    embed_path = (
        str(embed_model) if embed_model else r".\models\your-embedding-model.gguf"
    )

    lines.extend(
        [
            "-" * 50,
            "EXAMPLE A — EMBEDDING server (PowerShell)",
            "-" * 50,
            "",
            "# Vectors only — Config Embeddings URL = http://localhost:8080/embeddings",
            f'Set-Location "{llama_dir}"',
            '$env:CUDA_DEVICE_ORDER = "PCI_BUS_ID"',
            f'$env:CUDA_VISIBLE_DEVICES = "{gpu_index}"',
            '$env:LLAMA_CUDA = "1"',
            f'$embedModel = "{embed_path}"',
            ".\\llama-server.exe `",
            "    -m $embedModel `",
            "    --host 127.0.0.1 `",
            "    --port 8080 `",
            f"    -c {embed_ctx['n_ctx']} `",
            f"    -ngl {layers} `",
            "    -b 512 -ub 512 `",
            "    --embeddings `",
            "    --no-webui",
            "",
            "-" * 50,
            "EXAMPLE B — CHAT server (PowerShell)",
            "-" * 50,
            "",
            "# Instruct / chat only — Ask AI → Connect to llamaccp → port 8081",
            f'Set-Location "{llama_dir}"',
            '$env:CUDA_DEVICE_ORDER = "PCI_BUS_ID"',
            f'$env:CUDA_VISIBLE_DEVICES = "{gpu_index}"',
            '$env:LLAMA_CUDA = "1"',
            f'$chatModel = "{chat_path}"',
            ".\\llama-server.exe `",
            "    -m $chatModel `",
            "    --host 127.0.0.1 `",
            "    --port 8081 `",
            f"    -c {chat_ctx['n_ctx']} `",
            f"    -ngl {layers}",
            "",
            "-" * 50,
            "CMD — EMBEDDINGS (embedded.cmd)",
            "-" * 50,
            "",
            "@echo off",
            f"REM Embeddings for Config URL http://localhost:8080/embeddings",
            "set CUDA_DEVICE_ORDER=PCI_BUS_ID",
            f"set CUDA_VISIBLE_DEVICES={gpu_index}",
            "set LLAMA_CUDA=1",
            f'cd /d "{llama_dir}"',
            "llama-server.exe ^",
            f"  -m {embed_path} ^",
            "  --host 127.0.0.1 ^",
            "  --port 8080 ^",
            f"  -c {embed_ctx['n_ctx']} ^",
            f"  -ngl {layers} ^",
            "  -b 512 -ub 512 ^",
            "  --embeddings ^",
            "  --no-webui",
            "",
            "-" * 50,
            "CMD — CHAT (llamaccp-chat.cmd)",
            "-" * 50,
            "",
            "@echo off",
            f"REM Best GPU: {gpu_name} (GPU #{gpu_index}, {vram_gb} GB)",
            "set CUDA_DEVICE_ORDER=PCI_BUS_ID",
            f"set CUDA_VISIBLE_DEVICES={gpu_index}",
            "set LLAMA_CUDA=1",
            f'cd /d "{llama_dir}"',
            "llama-server.exe ^",
            f"  -m {chat_path} ^",
            "  --host 127.0.0.1 ^",
            "  --port 8081 ^",
            f"  -c {chat_ctx['n_ctx']} ^",
            f"  -ngl {layers}",
            "",
            "=" * 50,
            "Prefer Spock UI: Launch + Config + Status (multi-instance Stop/Restart).",
            "=" * 50,
        ]
    )
    return "\n".join(lines)


def load_model_guide() -> str:
    for path in (MODEL_GUIDE_PATH, *_GUIDE_FALLBACKS):
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8")
            except Exception as e:
                return f"(Error reading {path}: {e})"
    return (
        "Model guide not found.\n"
        f"Expected: {MODEL_GUIDE_PATH}\n"
        "or D:\\Spock-Scanner\\MinimumHardwareForOllama.md"
    )


ABOUT_TEXT = """
SPOCK-TO-BRIDGE — Hardware Scan & Ship's Computer
Starfleet Academy / Spock-UIEG toolkit

Purpose
  Assess this PC for local AI (LM Studio, llama-server / llamaccp)
  and operate the Starfleet knowledge base (ship_computer.db): ingest, RAG, Ask AI.

Architecture (remember the ports)
  • Chat LLM     — LM Studio (:1234) OR Launch instruct GGUF (own port)
  • Embeddings   — Launch embedding GGUF; Config URL e.g. :8080/embeddings
  • RAG API      — optional OpenAI front door on :8090/v1 (spock-ships-computer)
  • Ask AI       — hybrid search over DB, then your connected chat provider
  • Wiki Agent   — ingest/embed using Embedding Profile env

Hardware Scan tabs
  1. SCAN HARDWARE
  2. Ship status — LM Studio + llamaccp compatibility / capacity notes
  3. Upgrade advice — what to buy or change
  4. Model guide — chat vs embedding selection (current Spock workflow)
  5. GPU details — NVIDIA NVML (needs nvidia-ml-py in THIS app's .venv)
  6. llamaccp config — dual embed/chat scripts + -ngl tips
  7. About — this page

Elsewhere in the console
  • Launch / Status — start/stop llama-server instances (multi-instance)
  • Live Monitor    — Status window (not this tab set)
  • Config          — App Tools → Embedding Profile + START RAG API
  • Documents       — path filter scopes Ask AI (clear if 0 matches)

Requirements
  Python 3.10+ recommended, project .venv with PyQt6, psutil, nvidia-ml-py,
  huggingface_hub, requests, etc. (see requirements.txt)

---
"Live long and learn."
""".strip()


def run_full_hardware_assessment() -> Dict[str, Any]:
    """One-shot scan used by HardwareScanWorker."""
    from model_selector_core import format_hardware_report, get_system_specs

    specs = get_system_specs()
    capacity = format_hardware_report(specs)
    ship = run_ship_status_scan()
    upgrade = get_upgrade_recommendations()
    gpu = get_gpu_details()
    return {
        "specs": specs,
        "ship_status_report": format_ship_status(ship, capacity_report=capacity),
        "upgrade_report": format_upgrade_report(upgrade),
        "gpu_details_report": format_gpu_details(gpu),
        "ship_data": ship,
        "upgrade_data": upgrade,
        "gpu_data": gpu,
    }
