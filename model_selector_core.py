"""Pure logic for Spock Model Selector (hardware, HF Hub, GGUF scan, PDF)."""

from __future__ import annotations

import ctypes
import datetime
import json
import os
import platform
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

import psutil
import requests
from huggingface_hub import HfApi, hf_hub_download, snapshot_download

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
MODELS_DIR = os.path.join(SCRIPT_DIR, "models")
try:
    from WarpCore.service_endpoints import resolve_llama_server_path

    DEFAULT_LLAMA_SERVER, _ = resolve_llama_server_path()
except ImportError:  # pragma: no cover
    DEFAULT_LLAMA_SERVER = os.environ.get(
        "LLAMA_SERVER_PATH",
        os.path.join(SCRIPT_DIR, "tools", "llama-server", "llama-server.exe"),
    )


def get_llamaccp_dir() -> str:
    """Directory that contains llama-server (and often a sibling models/)."""
    path = os.environ.get("LLAMA_SERVER_PATH", "").strip()
    if not path:
        try:
            cfg = load_config()
            # Prefer app-style mcp path if present in config.json variants
            mcp = cfg.get("mcp") if isinstance(cfg.get("mcp"), dict) else {}
            path = str(mcp.get("llama_server_path") or "").strip()
        except Exception:
            path = ""
    if not path:
        # app_config.json via onboarding store (best-effort)
        try:
            from pathlib import Path as _P

            app_cfg = _P(SCRIPT_DIR) / "app_config.json"
            if app_cfg.is_file():
                import json as _json

                data = _json.loads(app_cfg.read_text(encoding="utf-8"))
                mcp = data.get("mcp") if isinstance(data.get("mcp"), dict) else {}
                path = str(mcp.get("llama_server_path") or "").strip()
        except Exception:
            path = ""
    if not path:
        try:
            from WarpCore.service_endpoints import resolve_llama_server_path as _resolve

            found, _ = _resolve()
            path = found
        except Exception:
            try:
                from WarpCore.service_endpoints import llama_server_install_dir as _install

                path = str(_install())
            except Exception:
                path = os.path.join(SCRIPT_DIR, "tools", "llama-server")
    base = os.path.basename(path).lower()
    if base in ("llama-server", "llama-server.exe"):
        return os.path.dirname(path) or path
    return path


def get_model_directory_options() -> List[Tuple[str, Optional[str]]]:
    """Dropdown options: All sources + known local model roots."""
    from pathlib import Path

    options: List[Tuple[str, Optional[str]]] = [("All sources", None)]
    llama_models = str(Path(get_llamaccp_dir()) / "models")
    local_app = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    llmfit_models = str(Path(local_app) / "llmfit" / "models")
    hf_hub = str(Path.home() / ".cache" / "huggingface" / "hub")
    candidates = [
        ("Spock Models", MODELS_DIR),
        ("LM Studio", str(Path.home() / ".lmstudio" / "models")),
        ("Ollama", str(Path.home() / ".ollama" / "models")),
        ("llamaccp", llama_models),
        ("LLM Fit", llmfit_models),
        ("HuggingFace Hub", hf_hub),
    ]
    for name, path in candidates:
        if os.path.isdir(path):
            options.append((f"{name}  ({path})", path))
        else:
            options.append((f"{name}  (not found)", path))
    return options


def scan_local_gguf_models(models_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    root_dir = models_dir or MODELS_DIR
    local_models: List[Dict[str, Any]] = []
    if not os.path.isdir(root_dir):
        return local_models
    for root, _dirs, files in os.walk(root_dir):
        for f in files:
            if f.lower().endswith(".gguf") and not f.lower().startswith("mmproj"):
                full_path = os.path.join(root, f)
                try:
                    size_gb = round(os.path.getsize(full_path) / (1024**3), 2)
                except OSError:
                    size_gb = 0
                local_models.append(
                    {"file": f, "size_gb": size_gb, "path": full_path}
                )
    local_models.sort(key=lambda m: m["size_gb"], reverse=True)
    return local_models


def scan_gguf_models_from_directory(selected_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """Scan one model directory, or all known sources when selected_dir is None."""
    if selected_dir:
        return scan_local_gguf_models(selected_dir)

    seen = set()
    merged: List[Dict[str, Any]] = []
    for _label, path in get_model_directory_options():
        if not path or not os.path.isdir(path):
            continue
        for m in scan_local_gguf_models(path):
            if m["path"] not in seen:
                seen.add(m["path"])
                merged.append(m)
    merged.sort(key=lambda m: m["size_gb"], reverse=True)
    return merged


def load_config() -> Dict[str, Any]:
    """HF config (hf.token) — from WarpCore Spock_Console, JSON fallback."""
    try:
        import _warpcore_path

        _warpcore_path.ensure()
        from WarpCore import settings_store

        db_path = os.path.join(SCRIPT_DIR, "ship_computer.db")
        if os.path.exists(db_path):
            token = settings_store.get_hf_token(db_path)
            return {"hf_token": token or ""}
    except Exception:
        pass
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"hf_token": ""}


def get_hf_token() -> Optional[str]:
    token = load_config().get("hf_token", "").strip()
    return token or None


def stardate() -> str:
    return datetime.datetime.now().strftime("%Y.%m.%d.%H.%M.%S")


def get_cuda_devices() -> List[Dict[str, Any]]:
    """CUDA devices in driver order: ``[{index, name}, ...]``.

    Unlike ``get_cuda_device_map``, duplicate names (two RTX 3060s) each keep
    their own ordinal. Empty list means the CUDA driver was unavailable — not
    that nvidia-smi GPUs are display-only.
    """
    devices: List[Dict[str, Any]] = []
    if sys.platform == "win32":
        try:
            nvcuda = ctypes.windll.nvcuda
            if int(nvcuda.cuInit(0) or 0) != 0:
                return devices
            count = ctypes.c_int(0)
            if int(nvcuda.cuDeviceGetCount(ctypes.byref(count)) or 0) != 0:
                return devices
            for i in range(int(count.value)):
                dev = ctypes.c_int(0)
                if nvcuda.cuDeviceGet(ctypes.byref(dev), i) != 0:
                    continue
                name_buf = ctypes.create_string_buffer(256)
                if nvcuda.cuDeviceGetName(name_buf, 256, dev) != 0:
                    continue
                name = name_buf.value.decode("utf-8", errors="replace")
                devices.append({"index": i, "name": name})
        except Exception:
            return []
    return devices


def get_cuda_device_map() -> Dict[str, int]:
    """Map GPU name -> CUDA ordinal (CUDA driver order, not nvidia-smi order).

    Duplicate names collapse to the **last** ordinal. Prefer
    ``get_cuda_devices`` + ``annotate_gpus_with_cuda`` when two cards share a
    name (e.g. dual RTX 3060).
    """
    cuda_map: Dict[str, int] = {}
    for d in get_cuda_devices():
        name = str(d.get("name") or "")
        if name:
            cuda_map[name] = int(d.get("index") or 0)
    return cuda_map


def annotate_gpus_with_cuda(
    gpus: Optional[List[Dict[str, Any]]],
    cuda_devices: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Attach ``cuda_index`` to nvidia-smi GPU rows.

    Unique names match by substring. Identical names (dual 3060) are paired in
    order among the remaining CUDA devices so each card gets its own ordinal.
    """
    annotated: List[Dict[str, Any]] = [
        dict(raw) for raw in (gpus or []) if isinstance(raw, dict)
    ]
    if not annotated:
        return annotated

    cuda_list = (
        list(cuda_devices)
        if isinstance(cuda_devices, list)
        else get_cuda_devices()
    )
    if not cuda_list:
        return annotated

    used_cuda: set = {
        int(g["cuda_index"])
        for g in annotated
        if g.get("cuda_index") is not None
    }
    name_counts: Dict[str, int] = {}
    for d in cuda_list:
        n = str(d.get("name") or "")
        name_counts[n] = name_counts.get(n, 0) + 1

    def _name_match(gpu_name: str, cuda_name: str) -> bool:
        return bool(
            gpu_name
            and cuda_name
            and (cuda_name in gpu_name or gpu_name in cuda_name)
        )

    def _cuda_idx(d: Dict[str, Any]) -> int:
        return int(d["index"]) if d.get("index") is not None else -1

    # Pass 1: unique CUDA product names → matching smi rows.
    for gpu in annotated:
        if gpu.get("cuda_index") is not None:
            continue
        name = str(gpu.get("name") or "")
        unique = [
            d
            for d in cuda_list
            if _name_match(name, str(d.get("name") or ""))
            and name_counts.get(str(d.get("name") or ""), 0) == 1
            and _cuda_idx(d) not in used_cuda
        ]
        if len(unique) == 1:
            idx = _cuda_idx(unique[0])
            gpu["cuda_index"] = idx
            used_cuda.add(idx)

    # Pass 2: remaining smi rows ↔ remaining CUDA devices (same-name first).
    remaining = [d for d in cuda_list if _cuda_idx(d) not in used_cuda]
    for gpu in annotated:
        if gpu.get("cuda_index") is not None:
            continue
        if not remaining:
            break
        name = str(gpu.get("name") or "")
        pick_i = 0
        for i, d in enumerate(remaining):
            if _name_match(name, str(d.get("name") or "")):
                pick_i = i
                break
        pick = remaining.pop(pick_i)
        idx = _cuda_idx(pick)
        gpu["cuda_index"] = idx
        used_cuda.add(idx)
    return annotated


def get_system_specs() -> Dict[str, Any]:
    specs: Dict[str, Any] = {}

    specs["cpu"] = platform.processor() or platform.machine()
    specs["cpu_cores"] = psutil.cpu_count(logical=False)
    specs["cpu_threads"] = psutil.cpu_count(logical=True)

    ram = psutil.virtual_memory()
    specs["ram_gb"] = round(ram.total / (1024**3), 1)
    specs["ram_available_gb"] = round(ram.available / (1024**3), 1)

    specs["gpu"] = "No GPU detected"
    specs["vram_gb"] = 0
    specs["cuda"] = False
    specs["metal"] = False
    specs["all_gpus"] = []

    # GPU discovery via nvidia-smi; spock_scanner_core adds NVML detail on top.
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            best_name, best_vram = None, 0
            for line in result.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2:
                    idx, name, vram_mb = parts[0], parts[1], parts[2]
                    vram_gb = round(int(vram_mb) / 1024, 1)
                    specs["all_gpus"].append(
                        {"index": idx, "name": name, "vram_gb": vram_gb}
                    )
                    if vram_gb > best_vram:
                        best_vram = vram_gb
                        best_name = name
            if best_name:
                specs["gpu"] = best_name
                specs["vram_gb"] = best_vram
                specs["cuda"] = True
    except Exception:
        pass

    if specs["all_gpus"]:
        try:
            specs["all_gpus"] = annotate_gpus_with_cuda(specs["all_gpus"])
        except Exception:
            pass

    usable_vram = (
        specs["vram_gb"] * 0.8
        if specs["vram_gb"] > 0
        else specs["ram_available_gb"] * 0.6
    )
    specs["max_params_fp16"] = round(usable_vram / 2, 1)
    specs["max_params_q8"] = round(usable_vram / 1, 1)
    specs["max_params_q4"] = round(usable_vram / 0.5, 1)

    return specs


def format_hardware_report(specs: Dict[str, Any]) -> str:
    lines = [
        "=" * 55,
        "HARDWARE SPECIFICATIONS",
        "=" * 55,
        "",
        f"  CPU:      {specs['cpu']}",
        f"  CORES:    {specs['cpu_cores']} cores / {specs['cpu_threads']} threads",
        f"  RAM:      {specs['ram_gb']} GB total / {specs['ram_available_gb']} GB available",
        "",
    ]
    if specs.get("all_gpus") and len(specs["all_gpus"]) > 1:
        lines.append("  ALL GPUs:")
        for g in specs["all_gpus"]:
            idx = g.get("index", "")
            label = f"    [{idx}] " if idx != "" else "    - "
            lines.append(f"  {label}{g['name']} ({g['vram_gb']} GB)")
        lines.append("")
    accel = "CUDA" if specs["cuda"] else "Metal" if specs["metal"] else "CPU"
    lines.extend(
        [
            f"  GPU:      {specs['gpu']}",
            f"  VRAM:     {specs['vram_gb']} GB",
            f"  ACCEL:    {accel}",
            "",
            "-" * 55,
            "MODEL CAPACITY ESTIMATES",
            "-" * 55,
            "",
            f"  FP16:  up to {specs['max_params_fp16']}B parameters",
            f"  Q8:    up to {specs['max_params_q8']}B parameters",
            f"  Q4:    up to {specs['max_params_q4']}B parameters",
            "",
            "=" * 55,
        ]
    )
    return "\n".join(lines)


def gpu_combo_labels(gpu_list: List[Dict[str, Any]]) -> Tuple[List[str], Optional[int]]:
    """Return display labels and preferred default index (RTX 6000 if present)."""
    gpu_names: List[str] = []
    default_idx: Optional[int] = None
    for i, g in enumerate(gpu_list):
        idx = g.get("index", "")
        label = (
            f"[{idx}] {g['name']} ({g['vram_gb']} GB)"
            if idx != ""
            else f"{g['name']} ({g['vram_gb']} GB)"
        )
        gpu_names.append(label)
        if "RTX 6000" in g["name"] or "rtx 6000" in g["name"].lower():
            default_idx = i
    if not gpu_names:
        gpu_names.append("(no GPUs detected)")
        default_idx = None
    return gpu_names, default_idx


def resolve_cuda_visible_devices(
    gpu_list: List[Dict[str, Any]], gpu_name: str
) -> Tuple[Optional[str], str]:
    """Map combo label to CUDA_VISIBLE_DEVICES value and a human description."""
    for g in gpu_list:
        expected = (
            f"[{g.get('index', '')}] {g['name']} ({g['vram_gb']} GB)"
            if g.get("index", "") != ""
            else f"{g['name']} ({g['vram_gb']} GB)"
        )
        if gpu_name == expected or gpu_name == f"[{g.get('index', '')}] {g['name']} ({g['vram_gb']} GB)":
            if "cuda_index" in g and g.get("cuda_index") is not None:
                gpu_idx = str(g["cuda_index"])
                return gpu_idx, f"nvidia-smi[{g.get('index', '')}] -> CUDA[{gpu_idx}]"
            return None, f"{g.get('name')} is not a CUDA device"
    return None, "CUDA_VISIBLE_DEVICES not set"


def _with_cuda_indices(
    gpu_list: Optional[List[Dict[str, Any]]],
    cuda_map: Dict[str, int],
) -> List[Dict[str, Any]]:
    """Copy ``gpu_list`` and fill ``cuda_index`` from the CUDA driver order."""
    annotated: List[Dict[str, Any]] = []
    for raw in gpu_list or []:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        if row.get("cuda_index") is None and cuda_map:
            name = str(row.get("name") or "")
            for cuda_name, cuda_idx in cuda_map.items():
                if cuda_name and name and (cuda_name in name or name in cuda_name):
                    row["cuda_index"] = cuda_idx
                    break
        annotated.append(row)
    return annotated


def _default_cuda_gpu(gpus: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Prefer the RTX 6000, otherwise the CUDA GPU with the most VRAM."""
    cuda_gpus = [g for g in gpus if g.get("cuda_index") is not None]
    if not cuda_gpus:
        return None
    for g in cuda_gpus:
        if "RTX 6000" in str(g.get("name") or ""):
            return g
    return max(cuda_gpus, key=lambda g: float(g.get("vram_gb") or 0))


def cuda_ordinal_for_launch(
    cuda_device: str = "",
    gpu_list: Optional[List[Dict[str, Any]]] = None,
    gpu_name: str = "",
    cuda_map: Optional[Dict[str, int]] = None,
) -> Tuple[Optional[str], str]:
    """CUDA_VISIBLE_DEVICES value for a launch.

    ``cuda_device`` is an nvidia-smi index from the host recipe. That is mapped
    to a CUDA ordinal (they differ when a display-only card sits at smi 0).

    Production path uses ``get_cuda_devices`` + ``annotate_gpus_with_cuda`` so
    dual identical cards (two RTX 3060s) each keep their own ordinal. Passing
    an explicit ``cuda_map`` keeps the legacy name→ordinal collapse for tests.
    """
    if cuda_map is not None:
        gpus = _with_cuda_indices(gpu_list, cuda_map)
        if not gpus and cuda_map:
            gpus = [
                {"index": idx, "name": name, "vram_gb": 0, "cuda_index": idx}
                for name, idx in cuda_map.items()
            ]
    else:
        try:
            cuda_devs = get_cuda_devices()
        except Exception:
            cuda_devs = []
        if gpu_list:
            gpus = annotate_gpus_with_cuda(gpu_list, cuda_devs)
        elif cuda_devs:
            # No smi list (Bringup / headless) — CUDA order is the index space.
            gpus = [
                {
                    "index": int(d["index"]) if d.get("index") is not None else i,
                    "name": str(d.get("name") or f"GPU {i}"),
                    "vram_gb": 0,
                    "cuda_index": int(d["index"]) if d.get("index") is not None else i,
                }
                for i, d in enumerate(cuda_devs)
            ]
        else:
            gpus = []

    ordinals = {str(g.get("cuda_index")) for g in gpus if g.get("cuda_index") is not None}

    if gpu_name:
        mapped, source = resolve_cuda_visible_devices(gpus, gpu_name)
        if mapped is not None:
            return mapped, source

    requested = str(cuda_device or "").strip()
    if requested:
        for g in gpus:
            if str(g.get("index")) != requested:
                continue
            if g.get("cuda_index") is not None:
                idx = str(g["cuda_index"])
                return idx, f"nvidia-smi[{requested}] -> CUDA[{idx}]"
            # Smi index exists but is not a CUDA device — fall through to default.
            requested = ""
            break
        if requested and (not ordinals or requested in ordinals):
            if not ordinals:
                return requested, "host recipe / explicit cuda_device"
            return requested, "CUDA ordinal"

    chosen = _default_cuda_gpu(gpus)
    if chosen is not None:
        idx = str(chosen["cuda_index"])
        return idx, f"default CUDA GPU {chosen.get('name')} -> CUDA[{idx}]"
    if str(cuda_device or "").strip():
        return str(cuda_device).strip(), "host recipe / explicit cuda_device"
    return None, "CUDA_VISIBLE_DEVICES not set"


def _iter_gguf_search(api, queries: List[str], limit_each: int = 20):
    """Yield Hub models from targeted searches (deduped)."""
    seen = set()
    for q in queries:
        try:
            models = api.list_models(
                search=q, filter="gguf", sort="downloads", limit=limit_each
            )
        except Exception:
            continue
        for model in models:
            try:
                mid = model.id
            except Exception:
                continue
            if not mid or mid in seen:
                continue
            seen.add(mid)
            yield model


def query_hf_models(
    specs: Dict[str, Any], task: str = "text-generation"
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    from huggingface_hub import HfApi

    from model_pick_policy import (
        active_hf_searches,
        annotate_hub_row,
        is_non_chat_model,
        rank_hub_rows,
    )

    api = HfApi(token=get_hf_token())
    results: List[Dict[str, Any]] = []
    close_matches: List[Dict[str, Any]] = []
    max_b = float(specs.get("max_params_q4") or 8.0)
    page_cache: Dict[str, str] = {}
    raw: List[Dict[str, Any]] = []

    try:
        for model in _iter_gguf_search(api, list(active_hf_searches("chat")), limit_each=15):
            try:
                name_lower = model.id.lower()
            except Exception:
                continue
            if _is_embedding_model(model, page_cache=page_cache):
                continue
            if is_non_chat_model(name_lower):
                continue
            size_b = _parse_size_b(name_lower)
            if not size_b:
                continue
            size_gb = _estimate_gguf_size_gb(size_b, name_lower)
            raw.append(
                annotate_hub_row(
                    {
                        "id": model.id,
                        "size_b": size_b,
                        "size_gb": size_gb,
                        "downloads": getattr(model, "downloads", 0) or 0,
                        "likes": getattr(model, "likes", 0) or 0,
                        "kind": "chat",
                    },
                    "chat",
                )
            )
        ranked = rank_hub_rows(raw, kind="chat", llmfit_tps=True)
        for model_info in ranked:
            size_b = float(model_info.get("size_b") or 0)
            if size_b <= max_b:
                results.append(model_info)
            elif size_b <= max_b * 2.5:
                close_matches.append(model_info)
            if len(results) >= 15 and len(close_matches) >= 10:
                break
        # Size Hub files only for the shortlist (avoid 200 model_info calls).
        for bucket in (results[:15], close_matches[:10]):
            for model_info in bucket:
                try:
                    model_info["size_gb"] = _gguf_repo_size_gb(
                        api,
                        model_info["id"],
                        float(model_info.get("size_b") or 0),
                        str(model_info["id"]).lower(),
                    )
                except Exception:
                    pass
    except Exception as e:
        results.append({"error": str(e)})

    return results, close_matches


# Cheap id/tag signals — candidates only; page keywords must confirm for listing.
_EMBEDDING_ID_SIGNALS = (
    "embedding",
    "embeddings",
    "embed",
    "feature-extraction",
    "vl-embedding",
    "gte-",
    "bge-",
    "e5-",
    "nomic-embed",
    "sentence-transformers",
    "text-embedding",
)

# Must appear on the model page (README) to confirm embedding use.
_EMBEDDING_PAGE_KEYWORDS = (
    "embedding",
    "embeddings",
    "embedded",
    "vector",
    "vectors",
    "feature-extraction",
    "feature extraction",
    "sentence-transformers",
    "sentence transformers",
    "text-embedding",
    "text embedding",
    "dense retrieval",
    "semantic search",
    "matryoshka",
    "retrieval score",
    "mteb",
)

_STRONG_EMBED_PIPELINES = frozenset(
    {"feature-extraction", "sentence-similarity"}
)


def _parse_size_b(name_lower: str) -> Optional[float]:
    from model_pick_policy import parse_size_b

    return parse_size_b(name_lower)


def _estimate_gguf_size_gb(params_b: float, name_lower: str = "") -> float:
    """Rough on-disk / VRAM weight size for a typical quant (for GPU fit planning)."""
    n = (name_lower or "").lower()
    if any(q in n for q in ("f16", "fp16", "bf16")):
        bytes_per_param = 2.0
    elif "q8" in n:
        bytes_per_param = 1.0
    elif "q6" in n:
        bytes_per_param = 0.75
    elif "q5" in n:
        bytes_per_param = 0.65
    elif any(q in n for q in ("q3", "iq3")):
        bytes_per_param = 0.4
    elif any(q in n for q in ("q2", "iq2")):
        bytes_per_param = 0.3
    else:
        # Default Q4_K_M-ish — matches Hardware Scan Q4 capacity (~0.5 GB/B)
        bytes_per_param = 0.55
    return round(float(params_b) * bytes_per_param, 2)


def _gguf_repo_size_gb(
    api,
    model_id: str,
    params_b: float,
    name_lower: str = "",
) -> float:
    """Best-effort GGUF size in GB from Hub file metadata (prefer Q4), else estimate.

    Multi-quant repos list many .gguf files — we pick a representative Q4 (or median)
    rather than summing all quants.
    """
    try:
        info = api.model_info(model_id, files_metadata=True)
        preferred: List[int] = []
        any_gguf: List[int] = []
        for sib in getattr(info, "siblings", None) or []:
            fn = str(getattr(sib, "rfilename", "") or "").lower()
            size = getattr(sib, "size", None)
            if not fn.endswith(".gguf") or not size:
                continue
            try:
                size_i = int(size)
            except (TypeError, ValueError):
                continue
            any_gguf.append(size_i)
            if any(
                q in fn
                for q in (
                    "q4_k_m",
                    "q4_k_s",
                    "q4_0",
                    "q4_1",
                    "q4_k",
                    "q4.",
                )
            ):
                preferred.append(size_i)
        pool = preferred or any_gguf
        if pool:
            pool.sort()
            mid = pool[len(pool) // 2]
            return round(mid / (1024**3), 2)
    except Exception:
        pass
    return _estimate_gguf_size_gb(params_b, name_lower)


def _model_meta_blob(model) -> Tuple[str, str, List[str]]:
    try:
        name_lower = model.id.lower()
    except Exception:
        name_lower = ""
    tags: List[str] = []
    try:
        tags = [str(t).lower() for t in (getattr(model, "tags", None) or [])]
    except Exception:
        pass
    pipeline = str(getattr(model, "pipeline_tag", "") or "").lower()
    return name_lower, pipeline, tags


def _looks_like_embedding_candidate(model) -> bool:
    """Fast id/tag/pipeline heuristic (may false-positive)."""
    name_lower, pipeline, tags = _model_meta_blob(model)
    if pipeline in _STRONG_EMBED_PIPELINES:
        return True
    blob = " ".join([name_lower, pipeline] + tags)
    return any(sig in blob for sig in _EMBEDDING_ID_SIGNALS)


def _looks_like_embedding_model(model) -> bool:
    """Backward-compatible alias for the cheap candidate check."""
    return _looks_like_embedding_candidate(model)


def _fetch_model_page_text(model_id: str, page_cache: Optional[Dict[str, str]] = None) -> str:
    """Fetch model README/page text (lowercased). Cached per query."""
    if page_cache is not None and model_id in page_cache:
        return page_cache[model_id]
    raw = fetch_model_card(model_id) or ""
    text = raw.lower()
    if page_cache is not None:
        page_cache[model_id] = text
    return text


def _page_confirms_embedding(page_text: str) -> bool:
    if not page_text:
        return False
    if page_text.startswith("(no readme") or page_text.startswith("(error"):
        return False

    for key in _EMBEDDING_PAGE_KEYWORDS:
        if " " in key or "-" in key:
            if key in page_text:
                return True
        elif re.search(rf"\b{re.escape(key)}\b", page_text):
            return True
    return False


def _is_embedding_model(
    model,
    *,
    page_cache: Optional[Dict[str, str]] = None,
) -> bool:
    """True only when meta suggests embedding AND model page keywords confirm.

    Strong Hub pipeline tags (feature-extraction / sentence-similarity) may pass
    without page text when the README is missing; weak id/tag hits require a
    page keyword hit to avoid chat GGUF false positives.
    """
    try:
        from model_pick_policy import is_strong_embed_id

        mid = str(getattr(model, "id", "") or "")
        if is_strong_embed_id(mid):
            return True
    except Exception:
        pass
    if not _looks_like_embedding_candidate(model):
        return False
    try:
        model_id = model.id
    except Exception:
        return False
    _, pipeline, _ = _model_meta_blob(model)
    page = _fetch_model_page_text(model_id, page_cache)
    if _page_confirms_embedding(page):
        return True
    # No usable page: only trust strong pipeline tags
    if pipeline in _STRONG_EMBED_PIPELINES and (
        not page or page.startswith("(no readme") or page.startswith("(error")
    ):
        return True
    return False


def query_hf_embedding_models(
    specs: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Recommend GGUF embedding models (e.g. Qwen3-Embedding-4B) for ingest/RAG."""
    from huggingface_hub import HfApi

    from model_pick_policy import (
        active_hf_searches,
        annotate_hub_row,
        rank_hub_rows,
    )

    api = HfApi(token=get_hf_token())
    results: List[Dict[str, Any]] = []
    close_matches: List[Dict[str, Any]] = []
    max_b = float(specs.get("max_params_q4") or 8.0)
    page_cache: Dict[str, str] = {}
    raw: List[Dict[str, Any]] = []

    try:
        for model in _iter_gguf_search(
            api, list(active_hf_searches("embedding")), limit_each=15
        ):
            if not _is_embedding_model(model, page_cache=page_cache):
                continue
            try:
                name_lower = model.id.lower()
            except Exception:
                continue
            size_b = _parse_size_b(name_lower) or 4.0
            size_gb = _estimate_gguf_size_gb(size_b, name_lower)
            raw.append(
                annotate_hub_row(
                    {
                        "id": model.id,
                        "size_b": size_b,
                        "size_gb": size_gb,
                        "downloads": getattr(model, "downloads", 0) or 0,
                        "likes": getattr(model, "likes", 0) or 0,
                        "kind": "embedding",
                    },
                    "embedding",
                )
            )
        ranked = rank_hub_rows(raw, kind="embedding", llmfit_tps=True)
        for model_info in ranked:
            size_b = float(model_info.get("size_b") or 0)
            if size_b <= max_b:
                results.append(model_info)
            elif size_b <= max_b * 2.5:
                close_matches.append(model_info)
            if len(results) >= 15 and len(close_matches) >= 10:
                break
        for bucket in (results[:15], close_matches[:10]):
            for model_info in bucket:
                try:
                    model_info["size_gb"] = _gguf_repo_size_gb(
                        api,
                        model_info["id"],
                        float(model_info.get("size_b") or 0),
                        str(model_info["id"]).lower(),
                    )
                except Exception:
                    pass
    except Exception as e:
        results.append({"error": str(e)})

    return results, close_matches


def is_embedding_gguf_path(path: str) -> bool:
    name = os.path.basename(path).lower()
    return any(sig in name for sig in _EMBEDDING_ID_SIGNALS)


def embedding_profile_identity(
    model_path: str,
    model_id: str = "",
    known_ids: Optional[List[str]] = None,
) -> Dict[str, str]:
    """Model path and id for the Embedding / RAG profile after a Launch.

    ``model_path`` is the GGUF file. ``model_id`` prefers an explicit id, then
    a known Hugging Face id whose short name matches the download folder, then
    the Acquire pick when it is the same file, then that folder name.
    """
    path = os.path.abspath(model_path) if model_path else ""
    folder = os.path.basename(os.path.dirname(path)) if path else ""
    stem = os.path.splitext(os.path.basename(path))[0] if path else ""
    chosen = str(model_id or "").strip()
    if not chosen:
        for mid in known_ids or []:
            text = str(mid or "").strip()
            short = text.split("/")[-1]
            if text and (short == folder or short == stem or text.endswith("/" + folder)):
                chosen = text
                break
    if not chosen and path:
        info = acquire_embedding_result()
        got = str(info.get("model_path") or "")
        if got and os.path.normcase(os.path.abspath(got)) == os.path.normcase(path):
            chosen = str(info.get("model_id") or "").strip()
    if not chosen:
        chosen = folder or os.path.basename(path)
    return {"model_path": path, "model_id": chosen}


DEFAULT_EMBEDDING_PROFILE: Dict[str, Any] = {
    "embeddings_url": "http://localhost:8080/embeddings",
    "embeddings_dim": 4096,
    "truncate_chars": 1500,
    "batch_chunk": 32,
    "batch_workers": 8,
    "llama_batch": 512,
    "llama_ubatch": 512,
    "model_path": "",
    "model_id": "",
    "probe_on_apply": True,
}


def merge_embedding_profile(raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    profile = dict(DEFAULT_EMBEDDING_PROFILE)
    if raw:
        profile.update({k: v for k, v in raw.items() if k in profile})
    return profile


def acquire_embedding_result(root: Optional[str] = None) -> Dict[str, Any]:
    """Models picked by Bringup step 3 Acquire (``first_models_last.json``).

    Empty dict when Acquire has not run (or wrote nothing usable). Includes
    embed *and* chat ``n_ctx`` so RAG / Launch can adopt the fit shortlist's
    context sizes, not only the GGUF path.
    """
    base = root or SCRIPT_DIR
    path = os.path.join(base, "first_models_last.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    try:
        dim = int(data.get("embed_dim") or 0) or None
    except (TypeError, ValueError):
        dim = None
    try:
        embed_n_ctx = int(data.get("embed_n_ctx") or 0) or None
    except (TypeError, ValueError):
        embed_n_ctx = None
    try:
        chat_n_ctx = int(data.get("chat_n_ctx") or 0) or None
    except (TypeError, ValueError):
        chat_n_ctx = None
    result = {
        "model_path": str(data.get("embed_gguf_path") or "").strip(),
        "model_id": str(data.get("embed_model_id") or "").strip(),
        "chat_model_path": str(data.get("chat_gguf_path") or "").strip(),
        "chat_model_id": str(data.get("chat_model_id") or "").strip(),
        "embeddings_dim": dim,
        "quant": str(data.get("embed_quant") or "").strip(),
        "chat_quant": str(data.get("chat_quant") or "").strip(),
        "embed_n_ctx": embed_n_ctx,
        "chat_n_ctx": chat_n_ctx,
        "summary_path": path,
    }
    if not result["model_path"] and not result["model_id"]:
        return {}
    return result


def sync_acquire_n_ctx_to_recipe(
    db_path: str,
    *,
    embed_n_ctx: Optional[int] = None,
    chat_n_ctx: Optional[int] = None,
    created_by: str = "acquire-result",
    live: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Write Acquire's ``-c`` values onto the current host recipe.

    GPU policy / tensor-split stay with the live recipe (or live proposal when
    the database moved machines). Only the context slots change, so a dual-3060
    recipe does not get rewritten as single-GPU just because Acquire ran.
    ``live`` is the hardware probe; omit it to measure this machine.
    """
    from WarpCore import host_recipe as hr

    plan = hr.effective_recipe(db_path, live=live, created_by=created_by)
    recipe = dict(plan.get("recipe") or {})
    # Never inflate -c past what this host's hardware proposes — a first_models
    # left over from another machine (or from before the recipe was updated)
    # must not push a larger machine's chat -c past this host's proposal.
    proposed = hr.propose_recipe(plan.get("hardware") or {})
    changed = False
    if embed_n_ctx and int(embed_n_ctx) >= 512:
        cap = int(proposed.get("embed_n_ctx") or embed_n_ctx)
        value = min(int(embed_n_ctx), cap)
        if int(recipe.get("embed_n_ctx") or 0) != value:
            recipe["embed_n_ctx"] = value
            changed = True
    if chat_n_ctx and int(chat_n_ctx) >= 512:
        cap = int(proposed.get("chat_n_ctx") or chat_n_ctx)
        value = min(int(chat_n_ctx), cap)
        if int(recipe.get("chat_n_ctx") or 0) != value:
            recipe["chat_n_ctx"] = value
            changed = True
    # Drift means the stored recipe still describes another machine. Persist the
    # live proposal even when -c already matched, so Launch stops pinning both
    # roles to CUDA 0 with the old chat -c.
    if plan.get("drift") or plan.get("source") == "live-proposal":
        changed = True
    if not changed:
        return {
            "updated": False,
            "recipe": recipe,
            "source": plan.get("source"),
            "version": (plan.get("stored") or {}).get("version"),
        }
    reason = (
        f"Acquire result: embed -c {recipe.get('embed_n_ctx')}, "
        f"chat -c {recipe.get('chat_n_ctx')}"
    )
    if plan.get("drift"):
        reason += " (saved for this host after drift)"
    row = hr.update_recipe(
        db_path,
        reason=reason,
        hardware=plan.get("hardware"),
        recipe=recipe,
        created_by=created_by,
    )
    return {
        "updated": True,
        "recipe": row.get("recipe") or recipe,
        "source": "updated",
        "version": row.get("version"),
        "reason": reason,
    }


def probe_embeddings_dim(url: str, timeout: int = 30) -> Optional[int]:
    """POST a short string to /embeddings and return vector length."""
    payload = json.dumps({"input": "spock probe"}).encode("utf-8")
    try:
        req = requests.post(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
        if req.status_code != 200:
            return None
        data = req.json()
        raw = None
        if isinstance(data, list) and data:
            raw = data[0].get("embedding") if isinstance(data[0], dict) else data[0]
        elif isinstance(data, dict):
            for key in ("data", "embeddings"):
                if key in data and data[key]:
                    item = data[key][0]
                    raw = item["embedding"] if isinstance(item, dict) else item
                    break
        if raw is None:
            return None
        if isinstance(raw, list) and raw and isinstance(raw[0], list):
            return len(raw[0])
        if isinstance(raw, list):
            return len(raw)
    except Exception:
        return None
    return None


def sample_db_embedding_dim(db_path: str) -> Optional[int]:
    import sqlite3
    import struct

    try:
        conn = sqlite3.connect(db_path, timeout=5)
        row = conn.execute(
            "SELECT embedding FROM documents WHERE embedding IS NOT NULL LIMIT 1"
        ).fetchone()
        conn.close()
        if not row or not row[0]:
            return None
        blob = row[0]
        return len(blob) // 4
    except Exception:
        return None


def write_embedding_env(profile: Dict[str, Any], env_path: Optional[str] = None) -> None:
    """Upsert embedding-related keys in .env (create if missing)."""
    path = env_path or os.path.join(SCRIPT_DIR, ".env")
    keys = {
        "EMBEDDINGS_URL": str(profile.get("embeddings_url", "")),
        "EMBEDDINGS_DIM": str(profile.get("embeddings_dim", 4096)),
        "EMBEDDINGS_TRUNCATE": str(profile.get("truncate_chars", 1500)),
        "EMBEDDINGS_BATCH_CHUNK": str(profile.get("batch_chunk", 32)),
        "EMBEDDINGS_BATCH_WORKERS": str(profile.get("batch_workers", 8)),
    }
    lines_out: List[str] = []
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped == "# Embedding profile (managed by Spock-to-bridge)":
                    continue
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    lines_out.append(line.rstrip("\n"))
                    continue
                k, _, _v = stripped.partition("=")
                if k in keys:
                    continue
                lines_out.append(line.rstrip("\n"))
    # Drop trailing empties then add one blank line before managed block
    while lines_out and lines_out[-1] == "":
        lines_out.pop()
    lines_out.append("")
    lines_out.append("# Embedding profile (managed by Spock-to-bridge)")
    for k, v in keys.items():
        lines_out.append(f"{k}={v}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines_out) + "\n")


def fetch_model_card(model_id: str) -> str:
    try:
        url = f"https://huggingface.co/{model_id}/raw/main/README.md"
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            return resp.text
        return f"(No README found - HTTP {resp.status_code})"
    except Exception as e:
        return f"(Error fetching README: {e})"


def _count_gguf_files(root: str) -> int:
    if not os.path.isdir(root):
        return 0
    n = 0
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if name.lower().endswith(".gguf") and not name.lower().startswith("mmproj"):
                n += 1
    return n


# Prefer these quants for Spock Launch (matches Hardware Scan Q4 planning).
_PREFERRED_QUANT_TOKENS: Tuple[str, ...] = (
    "q4_k_m",
    "q4_k_s",
    "q5_k_m",
    "q5_k_s",
    "q4_0",
    "q4_1",
    "q3_k_m",
    "iq4_xs",
)


def _prepare_hf_download_env() -> None:
    """Quiet Windows HF Hub noise that PowerShell surfaces as NativeCommandError."""
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    # Avoid interactive prompts on gated repos when no token is set.
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


def _format_hf_download_error(model_id: str, exc: BaseException) -> str:
    """Human-readable HF errors (401 gated/private often looks like 'not found')."""
    name = type(exc).__name__
    text = str(exc)
    low = text.lower()
    tips = (
        f"Model: {model_id}\n"
        f"{name}: {text}\n\n"
        "Common new-PC fixes:\n"
        "1) Open the model page in a browser, accept any license/gate, then retry.\n"
        "2) Create a Hugging Face token (read access) and set config.json → "
        '"hf_token": "hf_..." (Onboarding / config.json).\n'
        "3) Pick a fully public GGUF repo (e.g. bartowski/*-GGUF) if this one stays 401.\n"
        "4) Ignore PowerShell NativeCommandError noise — use the in-app dialog/status."
    )
    if "401" in text or "403" in text or "gated" in low or "invalid username" in low:
        return (
            "Hugging Face denied download (auth / gated / private).\n\n" + tips
        )
    if "404" in text or "not found" in low:
        return "Hugging Face model not found or not downloadable.\n\n" + tips
    return tips


def _list_repo_gguf_files(model_id: str, token: Optional[str]) -> List[Tuple[str, int]]:
    """Return (rfilename, size_bytes) for .gguf files (skip mmproj)."""
    api = HfApi(token=token)
    try:
        info = api.model_info(model_id, files_metadata=True)
    except Exception:
        # Retry anonymous — a bad/expired token can 401 even public repos.
        if token:
            api = HfApi(token=None)
            info = api.model_info(model_id, files_metadata=True)
        else:
            raise
    out: List[Tuple[str, int]] = []
    for sib in getattr(info, "siblings", None) or []:
        fn = str(getattr(sib, "rfilename", "") or "")
        low = fn.lower()
        if not low.endswith(".gguf") or "mmproj" in low:
            continue
        size = getattr(sib, "size", None) or 0
        try:
            size_i = int(size)
        except (TypeError, ValueError):
            size_i = 0
        out.append((fn, size_i))
    if out:
        return out
    # Fallback without sizes
    try:
        from huggingface_hub import list_repo_files

        names = list_repo_files(model_id, token=token)
        return [
            (fn, 0)
            for fn in names
            if fn.lower().endswith(".gguf") and "mmproj" not in fn.lower()
        ]
    except Exception:
        return out


def _pick_gguf_files_for_download(
    files: List[Tuple[str, int]],
    preferred_tokens: Optional[Tuple[str, ...]] = None,
) -> List[str]:
    """Pick one (or a few) GGUF files — never the entire multi-quant dump."""
    if not files:
        return []
    tokens = preferred_tokens or _PREFERRED_QUANT_TOKENS
    # Exact preferred quant in priority order
    for token in tokens:
        hits = [(fn, sz) for fn, sz in files if token in fn.lower()]
        if not hits:
            continue
        # Sharded quant: take all matching shards
        shards = [fn for fn, _sz in hits if "-of-" in fn.lower()]
        if shards and len(shards) >= 2:
            return sorted(shards)
        # Prefer a non-split file; else smallest hit
        singles = [(fn, sz) for fn, sz in hits if "-of-" not in fn.lower()]
        pool = singles or hits
        pool.sort(key=lambda x: x[1] or 10**18)
        return [pool[0][0]]
    # Fallback: median-sized single GGUF
    singles = [(fn, sz) for fn, sz in files if "-of-" not in fn.lower()]
    pool = singles or files
    pool = sorted(pool, key=lambda x: x[1] or 0)
    mid = pool[len(pool) // 2]
    return [mid[0]]


def download_models(
    model_ids: List[str],
    progress_cb=None,
    quant_by_id: Optional[Dict[str, Tuple[str, ...]]] = None,
) -> Dict[str, Any]:
    """Download GGUF snapshots into MODELS_DIR (Spock Launch / llama-server).

    Does not require LM Studio. progress_cb(text, value) optional.
    Returns {downloaded: [...], failed: [...], gguf_total: int}.

    On multi-quant Hub repos, downloads a preferred Q4/Q5 file (not every quant).
    """
    _prepare_hf_download_env()
    os.makedirs(MODELS_DIR, exist_ok=True)
    token = get_hf_token()
    total = len(model_ids)
    downloaded: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    quants = quant_by_id or {}
    for i, model_id in enumerate(model_ids, 1):
        short_name = model_id.split("/")[-1]
        dest = os.path.join(MODELS_DIR, short_name)
        os.makedirs(dest, exist_ok=True)
        if progress_cb:
            progress_cb(
                f"[{i}/{total}] Resolving GGUF files for {model_id} ...",
                i - 0.7,
            )
        try:
            try:
                listed = _list_repo_gguf_files(model_id, token)
            except Exception as list_err:
                # Fall back to narrow snapshot patterns if model_info fails
                listed = []
                if progress_cb:
                    progress_cb(
                        f"[{i}/{total}] File list failed ({list_err}); trying Q4 snapshot ...",
                        i - 0.6,
                    )

            preferred = quants.get(model_id)
            picked = (
                _pick_gguf_files_for_download(listed, preferred_tokens=preferred)
                if listed
                else []
            )
            if picked:
                if progress_cb:
                    preview = ", ".join(os.path.basename(p) for p in picked[:3])
                    progress_cb(
                        f"[{i}/{total}] Downloading {len(picked)} file(s): {preview}",
                        i - 0.5,
                    )
                for fn in picked:
                    hf_hub_download(
                        repo_id=model_id,
                        filename=fn,
                        local_dir=dest,
                        token=token,
                    )
                # Small text companions (best-effort)
                for companion in ("README.md", "Modelfile", "config.json"):
                    try:
                        hf_hub_download(
                            repo_id=model_id,
                            filename=companion,
                            local_dir=dest,
                            token=token,
                        )
                    except Exception:
                        pass
            else:
                # Last resort: snapshot with preferred quant globs only (not all *.gguf)
                if progress_cb:
                    progress_cb(
                        f"[{i}/{total}] Downloading preferred Q4/Q5 GGUF pattern -> models/{short_name}/",
                        i - 0.5,
                    )
                snapshot_download(
                    repo_id=model_id,
                    local_dir=dest,
                    allow_patterns=[
                        "*q4_k_m*.gguf",
                        "*Q4_K_M*.gguf",
                        "*q4_k_s*.gguf",
                        "*Q4_K_S*.gguf",
                        "*q5_k_m*.gguf",
                        "*Q5_K_M*.gguf",
                        "*.md",
                        "*.txt",
                        "*.json",
                    ],
                    ignore_patterns=["*.safetensors", "*.bin", "*.pt", "*.onnx"],
                    token=token,
                )

            gguf_n = _count_gguf_files(dest)
            if gguf_n <= 0:
                msg = (
                    f"No .gguf files landed in models/{short_name}/. "
                    f"Repo may be safetensors-only, gated (set hf_token in config.json), "
                    f"or network/blocked. See https://huggingface.co/{model_id}"
                )
                failed.append({"id": model_id, "dest": dest, "error": msg})
                if progress_cb:
                    progress_cb(f"[{i}/{total}] FAILED: {short_name} - {msg}", float(i))
                continue
            downloaded.append(
                {"id": model_id, "dest": dest, "gguf_count": gguf_n, "files": picked}
            )
            if progress_cb:
                progress_cb(
                    f"[{i}/{total}] DONE: {short_name} ({gguf_n} GGUF) -> {dest}",
                    float(i),
                )
        except Exception as e:
            err = _format_hf_download_error(model_id, e)
            failed.append({"id": model_id, "dest": dest, "error": err})
            if progress_cb:
                progress_cb(
                    f"[{i}/{total}] FAILED: {short_name} - {type(e).__name__}",
                    float(i),
                )
    return {
        "downloaded": downloaded,
        "failed": failed,
        "gguf_total": sum(int(d.get("gguf_count") or 0) for d in downloaded),
    }





def export_report_pdf(
    filename: str, hw_content: str, model_lines: List[str]
) -> None:
    if not PDF_AVAILABLE:
        raise RuntimeError("reportlab not installed. Run: pip install reportlab")

    c = canvas.Canvas(filename, pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 16)
    c.setFillColorRGB(0.612, 0.541, 0.643)
    c.drawString(50, height - 50, "SPOCK-MODEL-SELECTOR REPORT")

    c.setFont("Helvetica", 10)
    days_passed = (datetime.datetime.now() - datetime.datetime(2024, 1, 1)).days
    stardate_int = int(78254 + days_passed)
    c.drawString(50, height - 75, f"Stardate: {stardate_int}")
    c.drawString(
        450,
        height - 50,
        f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
    )
    c.setLineWidth(1)
    c.line(50, height - 85, width - 50, height - 85)

    y = height - 110
    c.setFont("Helvetica-Bold", 12)
    c.setFillColorRGB(1, 0.596, 0.0)
    c.drawString(50, y, "HARDWARE SPECIFICATIONS")
    y -= 20

    c.setFont("Courier", 9)
    c.setFillColorRGB(0, 0, 0)
    for line in hw_content.split("\n"):
        if y < 50:
            c.showPage()
            y = height - 50
            c.setFont("Courier", 9)
            c.setFillColorRGB(0, 0, 0)
        c.drawString(50, y, line[:80])
        y -= 12

    y -= 25
    c.setFont("Helvetica-Bold", 12)
    c.setFillColorRGB(1, 0.757, 0.027)
    c.drawString(50, y, "COMPATIBLE MODELS")
    y -= 20

    c.setFont("Courier", 8)
    c.setFillColorRGB(0, 0, 0)
    for line in model_lines:
        if y < 50:
            c.showPage()
            y = height - 50
            c.setFont("Courier", 8)
            c.setFillColorRGB(0, 0, 0)
        c.drawString(50, y, line[:90])
        y -= 10

    c.save()
