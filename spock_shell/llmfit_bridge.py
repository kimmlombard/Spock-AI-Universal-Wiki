"""Thin subprocess bridge to local llmfit CLI JSON (fit / plan / system).

Prefers ``{SPOCK_ROOT}/tools/llmfit``, then PATH. All helpers degrade
gracefully when the binary is missing or returns non-JSON.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from WarpCore.service_endpoints import llmfit_binary_candidates

_DEFAULT_TIMEOUT_S = 45
_VERIFY_NGL_RE = re.compile(r"-ngl\s+(\d+|-1)\b", re.IGNORECASE)

# App-relative candidates (tests may import this name).
_CANDIDATE_EXES = tuple(llmfit_binary_candidates())


def find_llmfit_exe() -> Optional[Path]:
    from WarpCore.service_endpoints import is_runnable_host_binary

    env = (os.environ.get("SPOCK_LLMFIT_EXE") or os.environ.get("LLMFIT_EXE") or "").strip()
    if env:
        p = Path(env)
        if is_runnable_host_binary(p):
            return p
    for cand in llmfit_binary_candidates():
        try:
            if is_runnable_host_binary(cand):
                return cand
        except OSError:
            continue
    # WSL PATH often includes Windows *.exe — never pick those on POSIX.
    which = shutil.which("llmfit")
    if which and is_runnable_host_binary(which):
        return Path(which)
    if os.name == "nt":
        which_exe = shutil.which("llmfit.exe")
        if which_exe and is_runnable_host_binary(which_exe):
            return Path(which_exe)
    return None


def available() -> bool:
    flag = (os.environ.get("SPOCK_LLMFIT") or "1").strip().lower()
    if flag in ("0", "false", "off", "no"):
        return False
    # Cloned llmfit source under tools/llmfit is not enough — need a built CLI.
    return find_llmfit_exe() is not None


def _run_json(args: List[str], *, timeout_s: float = _DEFAULT_TIMEOUT_S) -> Optional[Any]:
    exe = find_llmfit_exe()
    if exe is None:
        return None
    cmd = [str(exe), *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    raw = (proc.stdout or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Some builds may emit a leading log line; take the last JSON object.
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                return None
        return None


def system_info(*, timeout_s: float = _DEFAULT_TIMEOUT_S) -> Optional[Dict[str, Any]]:
    data = _run_json(["--json", "system"], timeout_s=timeout_s)
    if isinstance(data, dict):
        return data
    return None


@lru_cache(maxsize=1)
def _system_info_json() -> Optional[str]:
    data = system_info()
    return json.dumps(data) if isinstance(data, dict) else None


def system_info_cached(*, refresh: bool = False) -> Optional[Dict[str, Any]]:
    """Session-cached ``llmfit --json system``.

    The raw call is a subprocess with a 45 s timeout, and it sits behind every
    Hub query through ``hardware_fingerprint``. Hardware does not change
    mid-session, so probe once and hand back a copy.
    """
    if refresh:
        _system_info_json.cache_clear()
    raw = _system_info_json()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def recommend(
    *,
    limit: int = 5,
    force_runtime: str = "llamacpp",
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> Optional[Dict[str, Any]]:
    args = ["recommend", "--json", "--force-runtime", force_runtime, "--limit", str(max(1, int(limit)))]
    data = _run_json(args, timeout_s=timeout_s)
    if isinstance(data, dict):
        return data
    return None


def fit(*, limit: int = 10, timeout_s: float = 90.0) -> Optional[Dict[str, Any]]:
    data = _run_json(["--json", "fit", "-n", str(max(1, int(limit)))], timeout_s=timeout_s)
    if isinstance(data, dict):
        return data
    return None


def plan(
    model: str,
    *,
    context: int = 8192,
    quant: Optional[str] = None,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> Optional[Dict[str, Any]]:
    model = (model or "").strip()
    if not model:
        return None
    args = ["plan", model, "--context", str(int(context)), "--json"]
    if quant:
        args.extend(["--quant", str(quant)])
    data = _run_json(args, timeout_s=timeout_s)
    if isinstance(data, dict):
        return data
    return None


def parse_ngl_from_verify_command(cmd: Optional[str]) -> Optional[str]:
    if not cmd:
        return None
    m = _VERIFY_NGL_RE.search(cmd)
    return m.group(1) if m else None


def model_hint_from_path(model_path: str) -> str:
    """Best-effort selector string for ``llmfit plan`` from a GGUF path."""
    stem = Path(model_path).stem
    # Strip common quant suffixes so llmfit can fuzzy-match the catalog name.
    stem = re.sub(
        r"[.\-_](Q\d+_K(_[MSXL])?|Q\d+_0|IQ\d+_XXS|f16|fp16|bf16)$",
        "",
        stem,
        flags=re.IGNORECASE,
    )
    return stem.replace("_", "-")


def suggest_ngl_from_payloads(
    *,
    plan_data: Optional[Dict[str, Any]] = None,
    model_row: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """Derive a llama-server ``-ngl`` value from llmfit JSON.

    Returns ``(ngl, reason)``. Falls back to ``-1`` (full offload) when the
    payloads do not justify a safer partial/CPU setting.
    """
    if model_row:
        from_verify = parse_ngl_from_verify_command(str(model_row.get("verify_command") or ""))
        run_mode = str(model_row.get("run_mode") or model_row.get("run_mode_label") or "").lower()
        avail = model_row.get("memory_available_gb")
        req = model_row.get("memory_required_gb")
        fit_level = str(model_row.get("fit_level") or model_row.get("fit_label") or "").lower()

        if "cpu" in run_mode and "gpu" not in run_mode and "offload" not in run_mode:
            return "0", "llmfit run_mode=CPU"

        try:
            avail_f = float(avail) if avail is not None else None
            req_f = float(req) if req is not None else None
        except (TypeError, ValueError):
            avail_f = req_f = None

        if avail_f is not None and req_f is not None and req_f > 0 and avail_f < req_f * 0.92:
            # Oversubscribed: map free fraction onto 1..99 layers (llmfit verify uses 99).
            frac = max(0.05, min(0.95, (avail_f / req_f) * 0.85))
            ngl = str(max(1, min(99, int(round(99 * frac)))))
            return ngl, f"llmfit VRAM tight ({avail_f:.1f}/{req_f:.1f} GiB) → partial -ngl {ngl}"

        if from_verify and fit_level in ("perfect", "good", ""):
            return from_verify, f"llmfit verify_command -ngl {from_verify}"

        if fit_level in ("perfect", "good") or "gpu" in run_mode:
            return "-1", f"llmfit fit_level={fit_level or 'gpu'}"

    if plan_data:
        current = plan_data.get("current") if isinstance(plan_data.get("current"), dict) else {}
        run_mode = str(current.get("run_mode") or "").lower()
        fit_level = str(current.get("fit_level") or "").lower()
        if run_mode in ("cpu", "cpu_only") or fit_level == "impossible":
            return "0", f"llmfit plan run_mode={run_mode or fit_level}"
        if "offload" in run_mode:
            return "24", "llmfit plan suggests CPU+GPU offload (conservative -ngl 24)"
        if fit_level in ("perfect", "good") or run_mode in ("gpu",):
            return "-1", f"llmfit plan fit_level={fit_level or run_mode}"

    return "-1", "llmfit default full offload"


@lru_cache(maxsize=32)
def _cached_plan(model: str, context: int, quant: str) -> Optional[str]:
    """Cache plan JSON as text to keep lru_cache hashable."""
    data = plan(model, context=context, quant=quant or None)
    if data is None:
        return None
    return json.dumps(data)


def resolve_ngl(
    model_path: str,
    *,
    n_ctx: int = 8192,
    quant: Optional[str] = None,
    current_ngl: str = "-1",
    use_llmfit: bool = True,
) -> Tuple[str, str]:
    """Resolve launch ``-ngl``.

    When ``current_ngl`` is not the sentinel ``-1`` / ``auto``, it wins.
    Otherwise consult llmfit plan for the GGUF stem.
    """
    cur = (current_ngl or "-1").strip()
    if cur.lower() == "auto":
        cur = "-1"
    if cur != "-1":
        return cur, "explicit -ngl"

    if not use_llmfit or not available():
        return "-1", "llmfit unavailable"

    hint = model_hint_from_path(model_path)
    raw = _cached_plan(hint, int(n_ctx), quant or "")
    plan_data = json.loads(raw) if raw else None
    return suggest_ngl_from_payloads(plan_data=plan_data)


def load_fixture(name: str) -> Any:
    """Load checked-in JSON under tests/fixtures/llmfit/ (utf-8-sig safe)."""
    root = Path(__file__).resolve().parent.parent
    path = root / "tests" / "fixtures" / "llmfit" / name
    with path.open(encoding="utf-8-sig") as fh:
        return json.load(fh)


def system_to_gpu_list(system_payload: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert ``llmfit --json system`` into scanner-style GPU dicts."""
    if not isinstance(system_payload, dict):
        return []
    sysinfo = system_payload.get("system") if isinstance(system_payload.get("system"), dict) else system_payload
    if not isinstance(sysinfo, dict):
        return []
    out: List[Dict[str, Any]] = []
    gpus = sysinfo.get("gpus")
    if isinstance(gpus, list) and gpus:
        for g in gpus:
            if not isinstance(g, dict):
                continue
            name = str(g.get("name") or "").strip()
            if not name:
                continue
            # Skip useless display-only iGPUs when llmfit marks tiny/null VRAM
            # and a discrete GPU is also present (filter later if needed).
            try:
                vram_gb = float(g.get("vram_gb") if g.get("vram_gb") is not None else 0.0)
            except (TypeError, ValueError):
                vram_gb = 0.0
            backend = str(g.get("backend") or "").upper()
            vendor = "nvidia" if "CUDA" in backend or "NVIDIA" in name.upper() else "other"
            if "APPLE" in backend or "METAL" in backend:
                vendor = "apple"
            if "ROCM" in backend or "AMD" in name.upper():
                vendor = "amd"
            if "INTEL" in name.upper() or "ARC" in name.upper():
                vendor = "intel"
            out.append(
                {
                    "vendor": vendor,
                    "name": name,
                    "vram_mb": int(round(vram_gb * 1024)),
                    "source": "llmfit",
                    "backend": backend or None,
                    "unified_memory": bool(g.get("unified_memory")),
                }
            )
    elif sysinfo.get("has_gpu") and sysinfo.get("gpu_name"):
        try:
            vram_gb = float(sysinfo.get("gpu_vram_gb") or 0.0)
        except (TypeError, ValueError):
            vram_gb = 0.0
        name = str(sysinfo.get("gpu_name") or "GPU")
        backend = str(sysinfo.get("backend") or "").upper()
        vendor = "nvidia" if "CUDA" in backend else "other"
        out.append(
            {
                "vendor": vendor,
                "name": name,
                "vram_mb": int(round(vram_gb * 1024)),
                "source": "llmfit",
                "backend": backend or None,
                "unified_memory": bool(sysinfo.get("unified_memory")),
            }
        )
    # Drop zero-VRAM stubs when any positive-VRAM device exists
    if any(g.get("vram_mb", 0) > 0 for g in out):
        out = [g for g in out if int(g.get("vram_mb") or 0) > 256]
    return out


def hardware_fingerprint(system_payload: Optional[Dict[str, Any]] = None) -> str:
    """Stable key for caching fit estimates against this machine."""
    payload = system_payload if system_payload is not None else system_info_cached()
    if not isinstance(payload, dict):
        return "unknown"
    sysinfo = payload.get("system") if isinstance(payload.get("system"), dict) else payload
    if not isinstance(sysinfo, dict):
        return "unknown"
    gpu = str(sysinfo.get("gpu_name") or "")
    try:
        vram = float(sysinfo.get("gpu_vram_gb") or 0.0)
    except (TypeError, ValueError):
        vram = 0.0
    try:
        ram = float(sysinfo.get("total_ram_gb") or 0.0)
    except (TypeError, ValueError):
        ram = 0.0
    backend = str(sysinfo.get("backend") or "")
    return f"{backend}|{gpu}|{vram:.1f}|{ram:.0f}"


def _normalize_model_key(name: str) -> str:
    s = (name or "").lower().replace("\\", "/")
    if "/" in s:
        s = s.split("/")[-1]
    s = s.replace("-gguf", "").replace("_gguf", "")
    s = re.sub(r"[.\-_](q\d+_k(_[msxl])?|q\d+_0|iq\d+_xxs|f16|fp16|bf16)$", "", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def _models_from_fit_like(payload: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    models = payload.get("models")
    return [m for m in models if isinstance(m, dict)] if isinstance(models, list) else []


@lru_cache(maxsize=8)
def _fit_estimate_index_json(fingerprint: str, limit: int) -> str:
    """Build name→estimate map from recommend/fit; stored as JSON for lru_cache."""
    _ = fingerprint
    rows: List[Dict[str, Any]] = []
    for payload in (recommend(limit=limit, force_runtime="llamacpp"), fit(limit=limit)):
        rows.extend(_models_from_fit_like(payload))
    index: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        name = str(row.get("name") or "")
        key = _normalize_model_key(name)
        if not key:
            continue
        tps = row.get("estimated_tps")
        try:
            tps_f = float(tps) if tps is not None else None
        except (TypeError, ValueError):
            tps_f = None
        entry = {
            "name": name,
            "estimated_tps": tps_f,
            "fit_level": row.get("fit_level") or row.get("fit_label"),
            "run_mode": row.get("run_mode") or row.get("run_mode_label"),
            "memory_required_gb": row.get("memory_required_gb"),
            "best_quant": row.get("best_quant"),
        }
        # Prefer higher tps / better names when duplicates collide
        prev = index.get(key)
        if prev is None or (tps_f or 0) > float(prev.get("estimated_tps") or 0):
            index[key] = entry
        # Also index gguf_sources repos for HF id matching
        for src in row.get("gguf_sources") or []:
            if not isinstance(src, dict):
                continue
            repo = str(src.get("repo") or "")
            rkey = _normalize_model_key(repo)
            if rkey and rkey not in index:
                index[rkey] = {**entry, "name": repo or name}
    return json.dumps(index)


def fit_estimate_index(*, limit: int = 40, system_payload: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    if not available():
        return {}
    fp = hardware_fingerprint(system_payload)
    raw = _fit_estimate_index_json(fp, max(5, int(limit)))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def lookup_fit_estimate(
    model_id: str,
    *,
    index: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Match an HF / catalog id to a cached llmfit fit row."""
    key = _normalize_model_key(model_id)
    if not key:
        return None
    idx = index if index is not None else fit_estimate_index()
    if key in idx:
        return idx[key]
    # Substring / containment fallback for publisher-prefixed ids
    best: Optional[Dict[str, Any]] = None
    best_len = 0
    for k, entry in idx.items():
        if len(k) < 6:
            continue
        if k in key or key in k:
            if len(k) > best_len:
                best = entry
                best_len = len(k)
    return best


def enrich_hub_row_with_fit(
    row: Dict[str, Any],
    *,
    index: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Attach estimated_tps / fit_level / llmfit_run_mode when a match exists."""
    out = dict(row)
    mid = str(out.get("id") or out.get("name") or "")
    hit = lookup_fit_estimate(mid, index=index)
    if not hit:
        return out
    if hit.get("estimated_tps") is not None:
        out["estimated_tps"] = hit["estimated_tps"]
    if hit.get("fit_level"):
        out["fit_level"] = hit["fit_level"]
    if hit.get("run_mode"):
        out["llmfit_run_mode"] = hit["run_mode"]
    if hit.get("best_quant"):
        out.setdefault("llmfit_best_quant", hit["best_quant"])
    return out


# ── Dashboard HTTP (llmfit serve, default :8787) ─────────────────────────

_DEFAULT_DASHBOARD = "http://127.0.0.1:8787"


def dashboard_base() -> str:
    """Base URL for ``llmfit serve`` (external; not a Spock in-repo port)."""
    env = (os.environ.get("SPOCK_LLMFIT_DASHBOARD") or "").strip().rstrip("/")
    return env or _DEFAULT_DASHBOARD


def dashboard_available(*, timeout_s: float = 1.5) -> bool:
    """True when ``GET /health`` succeeds on the dashboard base URL."""
    try:
        import urllib.error
        import urllib.request

        req = urllib.request.Request(
            dashboard_base() + "/health",
            headers={"Accept": "application/json"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            if resp.status != 200:
                return False
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw) if raw else {}
        return isinstance(data, dict) and str(data.get("status") or "").lower() == "ok"
    except Exception:
        return False


def query_models(
    *,
    role: str = "chat",
    filters: Optional[Dict[str, Any]] = None,
    timeout_s: float = 30.0,
) -> Optional[Dict[str, Any]]:
    """``GET /api/v1/models`` with session criteria (or explicit ``filters``).

    Returns the JSON envelope, or ``None`` when the dashboard is offline /
    returns non-JSON. Never raises for connectivity failures.
    """
    try:
        import urllib.error
        import urllib.parse
        import urllib.request

        from llmfit_session_criteria import filters_as_query

        params = filters if isinstance(filters, dict) else filters_as_query(role=role)
        query = urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None and v != ""},
            doseq=True,
        )
        url = dashboard_base() + "/api/v1/models"
        if query:
            url = url + "?" + query
        req = urllib.request.Request(
            url, headers={"Accept": "application/json"}, method="GET"
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw) if raw else None
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def best_fit_ids(
    *,
    role: str = "chat",
    limit: int = 6,
    timeout_s: float = 30.0,
) -> List[str]:
    """Top model names / GGUF repos from the dashboard, else empty (caller falls back)."""
    overrides = {"limit": max(1, int(limit))}
    try:
        from llmfit_session_criteria import filters_as_query

        filters = filters_as_query(role=role, overrides=overrides)
    except Exception:
        filters = dict(overrides)
    payload = query_models(role=role, filters=filters, timeout_s=timeout_s)
    if not payload:
        return []
    models = payload.get("models")
    if not isinstance(models, list):
        return []
    out: List[str] = []
    seen = set()
    for row in models:
        if not isinstance(row, dict):
            continue
        candidates: List[str] = []
        name = str(row.get("name") or "").strip()
        if name:
            candidates.append(name)
        for src in row.get("gguf_sources") or []:
            if isinstance(src, dict):
                repo = str(src.get("repo") or "").strip()
                if repo:
                    candidates.append(repo)
        for cand in candidates:
            key = cand.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(cand)
            break
        if len(out) >= max(1, int(limit)):
            break
    return out


def dashboard_rows_as_hub(
    *,
    role: str = "chat",
    limit: int = 6,
    timeout_s: float = 30.0,
) -> List[Dict[str, Any]]:
    """Map dashboard model rows into Hub-ish dicts for ``top_role_fits``."""
    overrides = {"limit": max(1, int(limit))}
    try:
        from llmfit_session_criteria import filters_as_query

        filters = filters_as_query(role=role, overrides=overrides)
    except Exception:
        filters = dict(overrides)
    payload = query_models(role=role, filters=filters, timeout_s=timeout_s)
    if not payload:
        return []
    kind = "embedding" if role in ("embed", "embedding") else "chat"
    rows: List[Dict[str, Any]] = []
    for row in payload.get("models") or []:
        if not isinstance(row, dict):
            continue
        mid = ""
        for src in row.get("gguf_sources") or []:
            if isinstance(src, dict) and src.get("repo"):
                mid = str(src["repo"]).strip()
                break
        if not mid:
            mid = str(row.get("name") or "").strip()
        if not mid:
            continue
        try:
            size_b = float(row.get("params_b") or 0.0)
        except (TypeError, ValueError):
            size_b = 0.0
        hub = {
            "id": mid,
            "size_b": size_b,
            "kind": kind,
            "native_ctx": int(row.get("context_length") or row.get("usable_context") or 8192),
            "fit_level": row.get("fit_level") or row.get("fit_label"),
            "estimated_tps": row.get("estimated_tps"),
            "score": int(round(float(row.get("score") or 0.0))),
            "source": "llmfit-dashboard",
            "llmfit_best_quant": row.get("best_quant"),
        }
        rows.append(hub)
    return rows
