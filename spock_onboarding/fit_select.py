"""Recipe-driven GGUF shortlists for Bringup step 3 Acquire.

Acquire used to auto-pick from a three-tier catalog keyed on one VRAM number.
This module instead reads the host recipe — the same artefact Launch uses — and
ranks candidates per role the way llmfit does, so the user chooses from models
that actually fit the machine they are on.

The Hub is preferred for candidates and the built-in catalog is the offline
fallback; either way the fit verdict is computed locally, with llmfit's own
verdict taking precedence when its CLI is installed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import _warpcore_path

_warpcore_path.ensure()

from model_pick_policy import (
    catalog_rows,
    detect_existing_embedding_dim,
    infer_embed_dim,
    recipe_role_budget,
    top_role_fits,
    usable_vram_gb,
)

ROLE_KINDS = {"embed": "embedding", "chat": "chat"}


def existing_embedding_dim() -> Optional[int]:
    """Dim already in ship_computer.db — switching it invalidates those vectors."""
    try:
        return detect_existing_embedding_dim()
    except Exception:
        return None


def host_planning_inputs(db_path: str = "") -> Dict[str, Any]:
    """Recipe + live hardware to size models against.

    Always pass the result of this (or ``host_recipe.effective_recipe``) into
    the shortlists. Reading hardware off the stored recipe row plans for the
    machine that created it, which breaks the moment ship_computer.db is copied
    to a different box.
    """
    from WarpCore import host_recipe as hr

    if not db_path:
        from spock_shell.paths import SHIP_COMPUTER_DB

        db_path = SHIP_COMPUTER_DB
    return hr.effective_recipe(
        db_path, reason="Auto-created for model selection", created_by="fit-select"
    )


def specs_from_recipe(recipe: Dict[str, Any], hardware: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal specs dict for the Hub queries, from a live hardware probe.

    ``hardware`` must be a live probe, not the snapshot stored on the recipe
    row — see ``host_planning_inputs``.
    """
    vrams = [
        float(g.get("vram_gb") or 0.0)
        for g in (hardware or {}).get("gpus") or []
        if isinstance(g, dict)
    ]
    vram = max(vrams) if vrams else 0.0
    ram = float((hardware or {}).get("host_ram_gb") or (recipe or {}).get("host_ram_gb") or 0.0)
    usable = usable_vram_gb(vram) if vram > 0 else max(2.0, ram * 0.35)
    return {
        "vram_gb": vram,
        "ram_gb": ram,
        "ram_available_gb": ram,
        "gpu": str((hardware or {}).get("gpu_summary") or ""),
        "all_gpus": list((hardware or {}).get("gpus") or []),
        "max_params_q4": round(usable / 0.5, 1),
        "max_params_q8": round(usable / 1.0, 1),
        "max_params_fp16": round(usable / 2.0, 1),
    }


def _hub_rows(kind: str, specs: Dict[str, Any]) -> List[Dict[str, Any]]:
    from model_selector_core import query_hf_embedding_models, query_hf_models

    if kind == "embedding":
        results, close = query_hf_embedding_models(specs)
    else:
        results, close = query_hf_models(specs)
    rows = [r for r in list(results) + list(close) if isinstance(r, dict) and not r.get("error")]
    return rows


def _dedupe_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep first occurrence of each model id (case-insensitive)."""
    seen = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        mid = str(row.get("id") or "").strip().lower()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        out.append(row)
    return out


def role_shortlist(
    role: str,
    *,
    recipe: Dict[str, Any],
    hardware: Dict[str, Any],
    limit: int = 6,
    use_hub: bool = True,
    specs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Top ``limit`` fitting models for ``role`` ("embed" or "chat")."""
    kind = ROLE_KINDS.get(role, "chat")
    budget = recipe_role_budget(recipe, hardware, role=role)
    spec = specs if isinstance(specs, dict) else specs_from_recipe(recipe, hardware)

    rows: List[Dict[str, Any]] = []
    sources: List[str] = []
    error = ""
    # Pool size before fit ranking — llmfit alone can return a single Google hit
    # (e.g. txgemma) while Hub/catalog still have many Gemma GGUFs.
    pool_target = max(limit * 2, 8)

    # Seed with live llmfit dashboard when up, then *supplement* until pool_target.
    try:
        from spock_shell.llmfit_bridge import dashboard_rows_as_hub

        dash_rows = dashboard_rows_as_hub(role=role, limit=pool_target)
        if dash_rows:
            rows.extend(dash_rows)
            sources.append("llmfit-dashboard")
    except Exception:
        pass

    if len(rows) < pool_target and use_hub:
        try:
            hub = _hub_rows(kind, spec)
            if hub:
                rows.extend(hub)
                sources.append("hub")
        except Exception as e:  # offline, no token, hub outage
            error = str(e)

    if len(rows) < pool_target:
        rows.extend(catalog_rows(kind))
        sources.append("catalog")

    rows = _dedupe_rows(rows)

    # Hard provider allow-list (empty = ALL). Excludes Qwen/Nvidia/etc. when set.
    try:
        from llmfit_session_criteria import filter_model_rows

        rows = filter_model_rows(rows)
    except Exception:
        pass

    source = "+".join(sources) if sources else "catalog"

    picks = top_role_fits(rows, kind=kind, budget=budget, limit=limit)
    if not picks:
        # Everything overflowed the budget: offer the smallest catalog entries
        # so Acquire still has something to download.
        fallback = sorted(catalog_rows(kind), key=lambda r: float(r.get("size_b") or 99))
        try:
            from llmfit_session_criteria import filter_model_rows

            fallback = filter_model_rows(fallback)
        except Exception:
            pass
        picks = top_role_fits(fallback[: max(2, limit)], kind=kind, budget=budget, limit=limit)

    existing_dim = existing_embedding_dim() if role == "embed" else None
    if existing_dim:
        for pick in picks:
            dim = pick.get("dim") or infer_embed_dim(str(pick.get("id") or ""))
            pick["dim"] = dim
            pick["dim_mismatch"] = bool(dim and int(dim) != int(existing_dim))
            if pick.get("dim_mismatch"):
                pick["dim_change_note"] = (
                    "Dimension differs from ship_computer.db — re-embed and "
                    "re-run wiki scan after switching."
                )
    return {
        "role": role,
        "kind": kind,
        "budget": budget,
        "picks": picks,
        "source": source,
        "error": error,
        "candidates_seen": len(rows),
        "existing_dim": existing_dim,
    }


def shortlists(
    *,
    recipe: Dict[str, Any],
    hardware: Dict[str, Any],
    limit: int = 6,
    use_hub: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """Shortlists for both roles from one recipe read."""
    specs = specs_from_recipe(recipe, hardware)
    return {
        role: role_shortlist(
            role,
            recipe=recipe,
            hardware=hardware,
            limit=limit,
            use_hub=use_hub,
            specs=specs,
        )
        for role in ("embed", "chat")
    }


def describe_pick(row: Dict[str, Any]) -> str:
    """One-line summary for menus and logs."""
    mid = str(row.get("id") or "?")
    level = str(row.get("fit_level") or "?")
    quant = str(row.get("fit_quant") or "").upper()
    need = row.get("need_gb")
    ctx = row.get("fit_n_ctx")
    tps = row.get("estimated_tps")
    bits = [f"{mid}", f"{level}", f"{quant}", f"~{need}GB", f"-c {ctx}"]
    if tps:
        bits.append(f"~{float(tps):.0f} tok/s")
    if row.get("fit_source") == "llmfit":
        bits.append("llmfit")
    return "  ".join(bits)
