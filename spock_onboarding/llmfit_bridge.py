"""Thin subprocess bridge to llmfit JSON CLI (local exe or uvx)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Path used by resolve_ngl catalog name cleanup

_DEFAULT_TIMEOUT_S = 45
_VERIFY_NGL_RE = re.compile(r"-ngl\s+(\d+|-1)\b", re.IGNORECASE)

try:
    from WarpCore.service_endpoints import llmfit_binary_candidates

    _CANDIDATE_EXES = tuple(llmfit_binary_candidates())
except Exception:  # pragma: no cover — early bootstrap without WarpCore
    _CANDIDATE_EXES = ()


def find_llmfit_exe() -> Optional[Path]:
    try:
        from WarpCore.service_endpoints import is_runnable_host_binary
    except Exception:  # pragma: no cover

        def is_runnable_host_binary(path: Path | str) -> bool:  # type: ignore
            p = Path(path)
            return p.is_file() and (os.name == "nt" or p.suffix.lower() != ".exe")

    env = (os.environ.get("SPOCK_LLMFIT_EXE") or os.environ.get("LLMFIT_EXE") or "").strip()
    if env:
        p = Path(env)
        if is_runnable_host_binary(p):
            return p
    try:
        from WarpCore.service_endpoints import llmfit_binary_candidates as _cands

        candidates = _cands()
    except Exception:
        candidates = list(_CANDIDATE_EXES)
    for cand in candidates:
        try:
            if is_runnable_host_binary(cand):
                return cand
        except OSError:
            continue
    which = shutil.which("llmfit")
    if which and is_runnable_host_binary(which):
        return Path(which)
    if os.name == "nt":
        which_exe = shutil.which("llmfit.exe")
        if which_exe and is_runnable_host_binary(which_exe):
            return Path(which_exe)
    return None


def find_uvx() -> Optional[str]:
    try:
        from WarpCore.service_endpoints import is_runnable_host_binary
    except Exception:  # pragma: no cover

        def is_runnable_host_binary(path: Path | str) -> bool:  # type: ignore
            p = Path(path)
            return p.is_file() and (os.name == "nt" or p.suffix.lower() != ".exe")

    uvx = shutil.which("uvx")
    if uvx and is_runnable_host_binary(uvx):
        return uvx
    if os.name == "nt":
        uvx_exe = shutil.which("uvx.exe")
        if uvx_exe and is_runnable_host_binary(uvx_exe):
            return uvx_exe
    return None


def available() -> bool:
    flag = (os.environ.get("SPOCK_LLMFIT") or "1").strip().lower()
    if flag in ("0", "false", "off", "no"):
        return False
    # Source clone under tools/llmfit without a built binary does not count.
    return find_llmfit_exe() is not None or find_uvx() is not None


def _base_cmd() -> Optional[List[str]]:
    exe = find_llmfit_exe()
    if exe is not None:
        return [str(exe)]
    uvx = find_uvx()
    if uvx:
        return [uvx, "llmfit"]
    return None


def _run_json(args: List[str], *, timeout_s: float = _DEFAULT_TIMEOUT_S) -> Optional[Any]:
    base = _base_cmd()
    if base is None:
        return None
    cmd = [*base, *args]
    try:
        creation = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            creationflags=creation,
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
    return data if isinstance(data, dict) else None


def recommend(
    *,
    limit: int = 5,
    force_runtime: str = "llamacpp",
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> Optional[Dict[str, Any]]:
    args = [
        "recommend",
        "--json",
        "--force-runtime",
        force_runtime,
        "--limit",
        str(max(1, int(limit))),
    ]
    data = _run_json(args, timeout_s=timeout_s)
    return data if isinstance(data, dict) else None


def fit(*, limit: int = 10, timeout_s: float = 90.0) -> Optional[Dict[str, Any]]:
    data = _run_json(["--json", "fit", "-n", str(max(1, int(limit)))], timeout_s=timeout_s)
    return data if isinstance(data, dict) else None


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
        args.extend(["--quant", str(quant).strip()])
    data = _run_json(args, timeout_s=timeout_s)
    return data if isinstance(data, dict) else None


def suggest_ngl_from_plan(plan_data: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    if not isinstance(plan_data, dict):
        return "-1", "no llmfit plan"
    verify = str(plan_data.get("verify_command") or "")
    m = _VERIFY_NGL_RE.search(verify)
    if m:
        return m.group(1), f"llmfit verify_command -ngl {m.group(1)}"
    current = plan_data.get("current") if isinstance(plan_data.get("current"), dict) else {}
    run_mode = str(
        current.get("run_mode")
        or plan_data.get("run_mode")
        or plan_data.get("fit_level")
        or ""
    ).lower()
    if run_mode in ("cpu", "cpu_only"):
        return "0", f"llmfit run_mode={run_mode}"
    return "-1", f"llmfit default ({run_mode or 'gpu'})"


def suggest_ngl_from_payloads(
    *,
    plan_data: Optional[Dict[str, Any]] = None,
    model_row: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """Derive llama-server ``-ngl`` from llmfit plan/fit JSON (MCP + GUI)."""
    if model_row and isinstance(model_row, dict):
        run_mode = str(model_row.get("run_mode") or model_row.get("run_mode_label") or "").lower()
        if "cpu" in run_mode and "gpu" not in run_mode and "offload" not in run_mode:
            return "0", "llmfit run_mode=CPU"
        verify = str(model_row.get("verify_command") or "")
        m = _VERIFY_NGL_RE.search(verify)
        if m:
            return m.group(1), f"llmfit verify_command -ngl {m.group(1)}"
    return suggest_ngl_from_plan(plan_data)


def resolve_ngl(
    model_path: str,
    *,
    n_ctx: int = 8192,
    current_ngl: str = "-1",
    use_llmfit: bool = True,
) -> Tuple[str, str]:
    cur = str(current_ngl or "-1").strip()
    if cur != "-1":
        return cur, "explicit -ngl"
    if not use_llmfit or not available():
        return "-1", "llmfit unavailable"
    stem = Path(model_path).stem
    # Strip common quant suffix for catalog match
    name = re.sub(
        r"-(?i:Q\d[_A-Z0-9]+|IQ\d[_A-Z0-9]+)$",
        "",
        stem,
    )
    data = plan(name, context=n_ctx)
    return suggest_ngl_from_plan(data)


# Dashboard HTTP helpers live on the shell bridge; re-export for onboarding callers.
try:
    from spock_shell.llmfit_bridge import (  # noqa: F401
        best_fit_ids,
        dashboard_available,
        dashboard_base,
        dashboard_rows_as_hub,
        query_models,
    )
except ImportError:  # pragma: no cover
    def dashboard_base() -> str:
        return (os.environ.get("SPOCK_LLMFIT_DASHBOARD") or "http://127.0.0.1:8787").rstrip("/")

    def dashboard_available(*, timeout_s: float = 1.5) -> bool:
        return False

    def query_models(**_kwargs: Any) -> Optional[Dict[str, Any]]:
        return None

    def best_fit_ids(**_kwargs: Any) -> List[str]:
        return []

    def dashboard_rows_as_hub(**_kwargs: Any) -> List[Dict[str, Any]]:
        return []
