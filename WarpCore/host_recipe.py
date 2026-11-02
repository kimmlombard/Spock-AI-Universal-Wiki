"""WarpCore: host recipe profiles — machine capability for Launch defaults.

Separate from session ``spock_profile`` snapshots. Create / Update only via
explicit caller actions; never silent-mutate. Content DB reset **clears**
``spock_host_recipe`` (and its sqlite_sequence) so Bringup / Maintenance can
re-probe and ask for a primary AI GPU on multi-GPU hosts.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from .config_defaults import clamp_n_cpu_moe
from .db import DEFAULT_SHIPS_DB, connect, ensure_schema as _es, resolve_db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS spock_host_recipe (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT 'app',
    reason TEXT NOT NULL DEFAULT '',
    hardware_json TEXT NOT NULL DEFAULT '{}',
    recipe_json TEXT NOT NULL DEFAULT '{}',
    is_current INTEGER NOT NULL DEFAULT 0 CHECK (is_current IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_spock_host_recipe_current
    ON spock_host_recipe(is_current);
CREATE INDEX IF NOT EXISTS idx_spock_host_recipe_version
    ON spock_host_recipe(version DESC);
"""

CURRENT_ID_KEY = "app.host_recipe.current_id"

GPU_POLICY_PIN = "pin_per_role"
GPU_POLICY_SPLIT = "tensor_split_chat"
GPU_POLICY_SINGLE = "single_gpu"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gpu_index(gpu: Any, default: int = -1) -> int:
    """Read a GPU index without treating 0 as missing (``x or default`` is wrong)."""
    if not isinstance(gpu, dict):
        return int(default)
    v = gpu.get("index")
    if v is None:
        return int(default)
    try:
        return int(v)
    except (TypeError, ValueError):
        return int(default)


def ensure_schema(db_path: str = DEFAULT_SHIPS_DB) -> str:
    path = resolve_db_path(db_path)
    _es(path, SCHEMA)
    return path


def probe_hardware() -> Dict[str, Any]:
    """Snapshot host RAM + GPUs for recipe inputs."""
    from spock_scanner_core import get_gpu_info, get_ram_gb

    ram_gb = float(get_ram_gb() or 0.0)
    raw_gpus = get_gpu_info() or []
    gpus: List[Dict[str, Any]] = []
    for i, g in enumerate(raw_gpus):
        if not isinstance(g, dict):
            continue
        vram_mb = float(g.get("vram_mb") or 0)
        vram_gb = float(g.get("vram_gb") or 0)
        if vram_gb <= 0 and vram_mb > 0:
            vram_gb = vram_mb / 1024.0
        gpus.append(
            {
                "index": int(g.get("index") if g.get("index") is not None else i),
                "name": str(g.get("name") or f"GPU {i}"),
                "vram_gb": round(vram_gb, 2),
                "vendor": str(g.get("vendor") or ""),
                "source": str(g.get("source") or ""),
            }
        )
    cuda_devices: List[Dict[str, Any]] = []
    try:
        from model_selector_core import annotate_gpus_with_cuda, get_cuda_devices

        cuda_devices = get_cuda_devices()
        gpus = annotate_gpus_with_cuda(gpus, cuda_devices)
    except Exception:
        cuda_devices = []
    summary = ", ".join(
        f"[{g['index']}] {g['name']} ({g['vram_gb']:.0f}GB)" for g in gpus
    ) or "(no GPUs detected)"
    return {
        "host_ram_gb": round(ram_gb, 1),
        "gpu_count": len(gpus),
        "gpus": gpus,
        "gpu_summary": summary,
        "cuda_device_count": len(cuda_devices),
        "probed_at": _now(),
    }


def propose_recipe(hardware: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Heuristic Launch defaults from a hardware snapshot."""
    hw = hardware if isinstance(hardware, dict) else probe_hardware()
    ram = float(hw.get("host_ram_gb") or 0.0)
    gpus = list(hw.get("gpus") or [])
    gpu_count = len(gpus)
    vrams = [float(g.get("vram_gb") or 0) for g in gpus]
    max_vram = max(vrams) if vrams else 0.0
    all_small = gpu_count >= 2 and all(v <= 12.5 for v in vrams if v > 0)

    notes: List[str] = []
    n_cpu_moe = 0
    # A card nvidia-smi lists but CUDA does not enumerate (the P2200 on this
    # host) is video-only. LLM roles stay on the CUDA GPU, the RTX 6000.
    if any("cuda_index" in g for g in gpus):
        display_only = [g for g in gpus if g.get("cuda_index") is None]
        compute = [g for g in gpus if g.get("cuda_index") is not None]
        if compute and display_only:
            gpus = compute
            gpu_count = len(gpus)
            vrams = [float(g.get("vram_gb") or 0) for g in gpus]
            max_vram = max(vrams) if vrams else 0.0
            all_small = gpu_count >= 2 and all(v <= 12.5 for v in vrams if v > 0)
            notes.append(
                "Video only (no CUDA device): "
                + ", ".join(str(g.get("name") or "GPU") for g in display_only)
                + ". LLM roles use "
                + ", ".join(str(g.get("name") or "GPU") for g in compute)
                + "."
            )
    if gpu_count >= 2 and all_small and ram <= 40.0:
        policy = GPU_POLICY_SPLIT
        chat_n_ctx = 16384
        embed_n_ctx = 4096
        embed_gpu = _gpu_index(gpus[0], 0)
        chat_gpu = _gpu_index(gpus[0], 0)
        tensor_split = ",".join(["1"] * gpu_count)
        # Even split: 0.5,0.5 for two cards
        if gpu_count == 2:
            tensor_split = "0.5,0.5"
        else:
            frac = round(1.0 / gpu_count, 4)
            tensor_split = ",".join(str(frac) for _ in range(gpu_count))
        split_mode = "layer"
        embed_class = "medium"
        n_cpu_moe = 28
        notes.append(
            "Dual ≤12GB GPUs + ≤40GB RAM: tensor-split chat across GPUs; "
            "keep embed modest (prefer ≤4B for daily use; 8B raises host RAM). "
            "Chat -ncmoe 28 keeps the first MoE expert layers in CPU RAM."
        )
    elif gpu_count == 1 and max_vram >= 20.0:
        policy = GPU_POLICY_SINGLE
        idx = _gpu_index(gpus[0], 0)
        embed_gpu = chat_gpu = idx
        chat_n_ctx = 32768
        embed_n_ctx = 4096
        tensor_split = ""
        split_mode = "layer"
        embed_class = "medium"
        notes.append(
            f"Single ≥20GB GPU ({max_vram:.0f}GB): both roles on GPU {idx}; "
            "chat -c 32768 is a starting default."
        )
    elif gpu_count >= 2:
        policy = GPU_POLICY_PIN
        embed_gpu = _gpu_index(gpus[0], 0)
        chat_gpu = _gpu_index(gpus[1], 1)
        chat_n_ctx = 16384
        embed_n_ctx = 4096
        tensor_split = ""
        split_mode = "layer"
        embed_class = "medium"
        notes.append(
            f"Pin embed→GPU {embed_gpu}, chat→GPU {chat_gpu} "
            "(one process per card)."
        )
    else:
        policy = GPU_POLICY_SINGLE
        embed_gpu = chat_gpu = _gpu_index(gpus[0], 0) if gpus else 0
        chat_n_ctx = 16384 if max_vram >= 10 else 4096
        embed_n_ctx = 4096
        tensor_split = ""
        split_mode = "layer"
        embed_class = "small" if max_vram < 10 else "medium"
        notes.append("Single/unknown GPU: conservative -c defaults.")

    return {
        "gpu_policy": policy,
        "embed_gpu_index": embed_gpu,
        "chat_gpu_index": chat_gpu,
        "split_mode": split_mode,
        "tensor_split": tensor_split,
        "embed_n_ctx": int(embed_n_ctx),
        "chat_n_ctx": int(chat_n_ctx),
        "embed_np": 1,
        "n_cpu_moe": int(n_cpu_moe),
        "ngl_default": "-1",
        "embed_size_class": embed_class,
        "host_ram_gb": float(hw.get("host_ram_gb") or 0.0),
        "gpu_summary": str(hw.get("gpu_summary") or ""),
        "notes": notes,
    }


def gpu_choice_rows(hardware: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """GPU rows for a primary-AI picker (nvidia-smi order, CUDA flagged)."""
    hw = hardware if isinstance(hardware, dict) else probe_hardware()
    cuda_count = int(hw.get("cuda_device_count") or 0)
    # If the snapshot predates cuda_device_count, infer from attached indexes.
    if "cuda_device_count" not in hw:
        cuda_count = sum(
            1
            for g in list(hw.get("gpus") or [])
            if isinstance(g, dict) and g.get("cuda_index") is not None
        )
    rows: List[Dict[str, Any]] = []
    for g in list(hw.get("gpus") or []):
        if not isinstance(g, dict):
            continue
        idx = _gpu_index(g, len(rows))
        cuda = g.get("cuda_index")
        if cuda is not None:
            tag = f" — CUDA[{int(cuda)}]"
        elif cuda_count > 0:
            # CUDA enumerated other cards; this one is not visible to the driver.
            tag = " — display/video (not visible to CUDA)"
        else:
            # nvcuda probe empty/failed — do not claim the card is display-only.
            tag = " — CUDA status unknown"
        rows.append(
            {
                "index": idx,
                "name": str(g.get("name") or f"GPU {idx}"),
                "vram_gb": float(g.get("vram_gb") or 0.0),
                "cuda_index": cuda,
                "has_cuda": cuda is not None,
                "label": (
                    f"[{idx}] {g.get('name') or f'GPU {idx}'} "
                    f"({float(g.get('vram_gb') or 0):.0f} GB)"
                    + tag
                ),
            }
        )
    return rows


def default_primary_ai_gpu_index(hardware: Optional[Dict[str, Any]] = None) -> int:
    """Prefer the largest CUDA GPU; else largest listed GPU; else 0."""
    rows = gpu_choice_rows(hardware)
    if not rows:
        return 0
    cuda_rows = [r for r in rows if r.get("has_cuda")]
    pool = cuda_rows or rows
    best = max(pool, key=lambda r: float(r.get("vram_gb") or 0.0))
    return _gpu_index(best, 0)


def multi_gpu_host(hardware: Optional[Dict[str, Any]] = None) -> bool:
    """True when the live probe lists two or more GPUs."""
    hw = hardware if isinstance(hardware, dict) else {}
    return len([g for g in list(hw.get("gpus") or []) if isinstance(g, dict)]) >= 2


def primary_ai_gpu_confirmed(recipe: Optional[Dict[str, Any]]) -> bool:
    """True when a recipe records an explicit user primary-AI pick."""
    rec = recipe if isinstance(recipe, dict) else {}
    if rec.get("primary_ai_gpu_confirmed"):
        return True
    for n in list(rec.get("notes") or []):
        if "User primary AI GPU" in str(n):
            return True
    return False


def needs_primary_ai_gpu_prompt(
    hardware: Optional[Dict[str, Any]] = None,
    recipe: Optional[Dict[str, Any]] = None,
) -> bool:
    """Multi-GPU hosts need an explicit primary AI GPU before we persist a recipe."""
    return multi_gpu_host(hardware) and not primary_ai_gpu_confirmed(recipe)


def apply_primary_ai_gpu(
    recipe: Dict[str, Any],
    primary_index: int,
    *,
    hardware: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Pin embed + chat to one primary AI GPU (multi-GPU / video+compute boxes)."""
    rec = dict(recipe or {})
    idx = int(primary_index)
    rec["embed_gpu_index"] = idx
    rec["chat_gpu_index"] = idx
    rec["primary_ai_gpu_confirmed"] = True
    hw = hardware if isinstance(hardware, dict) else {}
    gpus = list(hw.get("gpus") or [])
    if len(gpus) >= 2:
        # One AI card for both roles — do not tensor-split across a video GPU.
        rec["gpu_policy"] = GPU_POLICY_SINGLE
        rec["tensor_split"] = ""
        rec["split_mode"] = str(rec.get("split_mode") or "layer")
    notes = list(rec.get("notes") or [])
    name = ""
    for g in gpus:
        if isinstance(g, dict) and _gpu_index(g) == idx:
            name = str(g.get("name") or "")
            break
    tag = f"User primary AI GPU {idx}" + (f" ({name})" if name else "") + " for embed + chat."
    if tag not in notes:
        notes.append(tag)
    rec["notes"] = notes
    return rec


def _row_to_dict(row: sqlite3.Row | Tuple) -> Dict[str, Any]:
    if isinstance(row, sqlite3.Row):
        d = dict(row)
    else:
        d = {
            "id": row[0],
            "version": row[1],
            "created_at": row[2],
            "created_by": row[3],
            "reason": row[4],
            "hardware_json": row[5],
            "recipe_json": row[6],
            "is_current": row[7],
        }
    try:
        d["hardware"] = json.loads(d.get("hardware_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        d["hardware"] = {}
    try:
        d["recipe"] = json.loads(d.get("recipe_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        d["recipe"] = {}
    d["is_current"] = bool(d.get("is_current"))
    return d


def _set_current_pointer(db_path: str, recipe_id: int, by: str) -> None:
    try:
        from WarpCore import settings_store

        settings_store.set(db_path, CURRENT_ID_KEY, int(recipe_id), by=by)
    except Exception:
        pass


def _next_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(version), 0) FROM spock_host_recipe"
    ).fetchone()
    return int(row[0] or 0) + 1


def _insert_current(
    db_path: str,
    *,
    hardware: Dict[str, Any],
    recipe: Dict[str, Any],
    reason: str,
    created_by: str,
) -> Dict[str, Any]:
    path = ensure_schema(db_path)
    conn = connect(path)
    try:
        version = _next_version(conn)
        conn.execute("UPDATE spock_host_recipe SET is_current = 0 WHERE is_current = 1")
        cur = conn.execute(
            """
            INSERT INTO spock_host_recipe
                (version, created_at, created_by, reason, hardware_json, recipe_json, is_current)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (
                version,
                _now(),
                str(created_by or "app"),
                str(reason or "").strip(),
                json.dumps(hardware or {}),
                json.dumps(recipe or {}),
            ),
        )
        rid = int(cur.lastrowid)
        conn.commit()
    finally:
        conn.close()
    _set_current_pointer(path, rid, created_by or "app")
    out = get_recipe_by_id(path, rid)
    return out or {}


def create_recipe(
    db_path: str = DEFAULT_SHIPS_DB,
    *,
    hardware: Optional[Dict[str, Any]] = None,
    recipe: Optional[Dict[str, Any]] = None,
    reason: str = "Initial host recipe",
    created_by: str = "maintenance",
) -> Dict[str, Any]:
    """Create version 1 (or next) only when no current recipe exists."""
    path = ensure_schema(db_path)
    if get_current_recipe(path) is not None:
        raise RuntimeError(
            "A current host recipe already exists. Use Update recipe profile instead."
        )
    hw = hardware if isinstance(hardware, dict) else probe_hardware()
    rec = recipe if isinstance(recipe, dict) else propose_recipe(hw)
    return _insert_current(
        path, hardware=hw, recipe=rec, reason=reason, created_by=created_by
    )


def update_recipe(
    db_path: str = DEFAULT_SHIPS_DB,
    *,
    reason: str,
    hardware: Optional[Dict[str, Any]] = None,
    recipe: Optional[Dict[str, Any]] = None,
    created_by: str = "maintenance",
) -> Dict[str, Any]:
    """Append a new current version. ``reason`` is required."""
    why = str(reason or "").strip()
    if not why:
        raise ValueError("Update requires a non-empty reason (audit trail).")
    path = ensure_schema(db_path)
    if get_current_recipe(path) is None:
        raise RuntimeError("No current recipe to update. Use Create recipe profile first.")
    hw = hardware if isinstance(hardware, dict) else probe_hardware()
    rec = recipe if isinstance(recipe, dict) else propose_recipe(hw)
    return _insert_current(
        path, hardware=hw, recipe=rec, reason=why, created_by=created_by
    )


def ensure_recipe(
    db_path: str = DEFAULT_SHIPS_DB,
    *,
    hardware: Optional[Dict[str, Any]] = None,
    reason: str = "Auto-created on first probe",
    created_by: str = "app",
) -> Tuple[Optional[Dict[str, Any]], str, List[str]]:
    """Guarantee a current recipe exists when it is safe to auto-create.

    Multi-GPU hosts are **not** auto-created here — the UI must ask which card
    is the primary AI GPU (display vs compute). Returns
    ``(recipe_row, action, drift)`` where action is ``"created"``,
    ``"existing"``, or ``"needs-primary"`` (row is None).
    """
    path = ensure_schema(db_path)
    hw = hardware if isinstance(hardware, dict) else probe_hardware()
    current = get_current_recipe(path)
    if current is None:
        if multi_gpu_host(hw):
            return None, "needs-primary", []
        row = create_recipe(
            path,
            hardware=hw,
            recipe=propose_recipe(hw),
            reason=reason,
            created_by=created_by,
        )
        return row, "created", []
    return current, "existing", hardware_drift(current, live=hw)


@lru_cache(maxsize=1)
def _probe_json() -> str:
    return json.dumps(probe_hardware())


def probe_hardware_cached(*, refresh: bool = False) -> Dict[str, Any]:
    """Session-cached probe — cards do not appear mid-run, nvidia-smi is slow."""
    if refresh:
        _probe_json.cache_clear()
    try:
        data = json.loads(_probe_json())
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def effective_recipe(
    db_path: str = DEFAULT_SHIPS_DB,
    *,
    live: Optional[Dict[str, Any]] = None,
    reason: str = "Auto-created on first probe",
    created_by: str = "app",
) -> Dict[str, Any]:
    """The recipe to *plan* with, always measured against live hardware.

    A stored recipe carries the hardware snapshot it was created from. Planning
    model sizes or launch budgets from that snapshot is wrong the moment the
    database moves to another machine, so hardware here is always a fresh probe.
    When it disagrees with the stored recipe, the stored policy is stale too
    (a single-GPU policy cannot describe two cards), so planning falls back to
    a proposal derived from the live probe.

    Returns ``{recipe, hardware, source, drift, stored}`` where source is
    ``created``, ``current``, ``live-proposal``, or ``needs-primary``.
    Multi-GPU hosts with no stored recipe are **not** written here — planning
    uses a live proposal until the UI records a primary AI GPU. The stored
    recipe is never rewritten here — persisting a drifted machine stays an
    explicit, reason-carrying update.
    """
    path = ensure_schema(db_path)
    hw = live if isinstance(live, dict) else probe_hardware_cached()
    stored = get_current_recipe(path)
    if stored is None:
        if multi_gpu_host(hw):
            return {
                "recipe": propose_recipe(hw),
                "hardware": hw,
                "source": "needs-primary",
                "drift": [],
                "stored": None,
            }
        row = create_recipe(
            path,
            hardware=hw,
            recipe=propose_recipe(hw),
            reason=reason,
            created_by=created_by,
        )
        return {
            "recipe": row.get("recipe") or {},
            "hardware": hw,
            "source": "created",
            "drift": [],
            "stored": row,
        }
    drift = hardware_drift(stored, live=hw)
    if drift:
        return {
            "recipe": propose_recipe(hw),
            "hardware": hw,
            "source": "live-proposal",
            "drift": drift,
            "stored": stored,
        }
    return {
        "recipe": stored.get("recipe") or {},
        "hardware": hw,
        "source": "current",
        "drift": [],
        "stored": stored,
    }


def apply_drift_update(
    db_path: str = DEFAULT_SHIPS_DB,
    *,
    live: Optional[Dict[str, Any]] = None,
    drift: Optional[List[str]] = None,
    created_by: str = "app",
) -> Dict[str, Any]:
    """Persist a new recipe version for hardware that moved, with an audit line."""
    hw = live if isinstance(live, dict) else probe_hardware()
    why = "Hardware drift: " + ("; ".join(drift) if drift else "re-probed host")
    return update_recipe(
        db_path,
        reason=why,
        hardware=hw,
        recipe=propose_recipe(hw),
        created_by=created_by,
    )


def get_recipe_by_id(
    db_path: str = DEFAULT_SHIPS_DB, recipe_id: int = 0
) -> Optional[Dict[str, Any]]:
    path = ensure_schema(db_path)
    conn = connect(path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, version, created_at, created_by, reason,
                   hardware_json, recipe_json, is_current
            FROM spock_host_recipe WHERE id = ?
            """,
            (int(recipe_id),),
        ).fetchone()
    finally:
        conn.close()
    return _row_to_dict(row) if row else None


def get_current_recipe(db_path: str = DEFAULT_SHIPS_DB) -> Optional[Dict[str, Any]]:
    path = ensure_schema(db_path)
    conn = connect(path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, version, created_at, created_by, reason,
                   hardware_json, recipe_json, is_current
            FROM spock_host_recipe WHERE is_current = 1
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()
    return _row_to_dict(row) if row else None


def list_recipe_history(
    db_path: str = DEFAULT_SHIPS_DB, limit: int = 100
) -> List[Dict[str, Any]]:
    path = ensure_schema(db_path)
    conn = connect(path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, version, created_at, created_by, reason,
                   hardware_json, recipe_json, is_current
            FROM spock_host_recipe
            ORDER BY version DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_dict(r) for r in rows]


def hardware_drift(
    current: Optional[Dict[str, Any]] = None,
    *,
    live: Optional[Dict[str, Any]] = None,
    ram_tol_gb: float = 1.0,
    vram_tol_gb: float = 0.75,
) -> List[str]:
    """Human messages when probed hardware disagrees with the saved recipe inputs."""
    cur = current if isinstance(current, dict) else get_current_recipe()
    if not cur:
        return []
    saved = cur.get("hardware") if isinstance(cur.get("hardware"), dict) else {}
    now = live if isinstance(live, dict) else probe_hardware()
    msgs: List[str] = []
    try:
        s_ram = float(saved.get("host_ram_gb") or 0)
        n_ram = float(now.get("host_ram_gb") or 0)
    except (TypeError, ValueError):
        s_ram = n_ram = 0.0
    if s_ram > 0 and n_ram > 0 and abs(s_ram - n_ram) > ram_tol_gb:
        msgs.append(f"Host RAM {n_ram:.0f}GB (recipe was {s_ram:.0f}GB).")
    s_count = int(saved.get("gpu_count") or len(saved.get("gpus") or []))
    n_count = int(now.get("gpu_count") or len(now.get("gpus") or []))
    if s_count != n_count:
        msgs.append(f"GPU count {n_count} (recipe was {s_count}).")
    s_gpus = list(saved.get("gpus") or [])
    n_gpus = list(now.get("gpus") or [])
    for i, sg in enumerate(s_gpus):
        if i >= len(n_gpus):
            break
        try:
            sv = float(sg.get("vram_gb") or 0)
            nv = float(n_gpus[i].get("vram_gb") or 0)
        except (TypeError, ValueError):
            continue
        if sv > 0 and nv > 0 and abs(sv - nv) > vram_tol_gb:
            msgs.append(
                f"GPU[{i}] VRAM ~{nv:.0f}GB (recipe was ~{sv:.0f}GB)."
            )
    s_sum = str(saved.get("gpu_summary") or "").strip()
    n_sum = str(now.get("gpu_summary") or "").strip()
    if s_sum and n_sum and s_sum != n_sum and not msgs:
        # Name-only change still worth a soft note
        if s_count == n_count:
            msgs.append(f"GPU labels changed: now {n_sum}.")
    recipe = cur.get("recipe") if isinstance(cur.get("recipe"), dict) else {}
    cuda_known = any(
        isinstance(g, dict) and g.get("cuda_index") is not None for g in n_gpus
    )
    if cuda_known and recipe:
        by_index: Dict[int, Dict[str, Any]] = {}
        for g in n_gpus:
            if not isinstance(g, dict):
                continue
            try:
                by_index[int(g.get("index"))] = g
            except (TypeError, ValueError):
                continue
        for label, key in (("embed", "embed_gpu_index"), ("chat", "chat_gpu_index")):
            try:
                idx = int(recipe.get(key))
            except (TypeError, ValueError):
                continue
            gpu = by_index.get(idx)
            if gpu is not None and gpu.get("cuda_index") is None:
                msgs.append(
                    f"{label} is pinned to {gpu.get('name') or ('GPU ' + str(idx))}, "
                    "which is not a CUDA device."
                )
    return msgs


def roles_share_physical_gpu(recipe: Optional[Dict[str, Any]]) -> bool:
    """True when Suggest Context should subtract sibling GGUF from the same card."""
    if not isinstance(recipe, dict):
        return True
    policy = str(recipe.get("gpu_policy") or "")
    if policy == GPU_POLICY_SPLIT:
        return False  # chat spans cards; embed usually pinned separately in practice
    if policy == GPU_POLICY_PIN:
        return int(recipe.get("embed_gpu_index") or 0) == int(
            recipe.get("chat_gpu_index") or 0
        )
    return True


def launch_overrides_for_role(
    recipe: Optional[Dict[str, Any]], role: str
) -> Dict[str, Any]:
    """Args to merge into LlamaServerManager.launch / LaunchPanel."""
    if not isinstance(recipe, dict):
        return {}
    role_l = (role or "chat").lower()
    is_embed = role_l in ("embedding", "embed")
    out: Dict[str, Any] = {
        "ngl": str(recipe.get("ngl_default") or "-1"),
        "n_ctx": int(
            recipe.get("embed_n_ctx") if is_embed else recipe.get("chat_n_ctx") or 8192
        ),
        # Missing key stays 0 so an older recipe does not start offloading MoE.
        "n_cpu_moe": 0 if is_embed else clamp_n_cpu_moe(recipe.get("n_cpu_moe") or 0),
    }
    policy = str(recipe.get("gpu_policy") or GPU_POLICY_SINGLE)
    if is_embed:
        out["n_parallel"] = int(recipe.get("embed_np") or 1)
        out["cuda_device"] = str(recipe.get("embed_gpu_index")
                                 if recipe.get("embed_gpu_index") is not None
                                 else "0")
        out["split_mode"] = ""
        out["tensor_split"] = ""
        out["pin_cuda"] = True
    else:
        out["n_parallel"] = None
        if policy == GPU_POLICY_SPLIT and str(recipe.get("tensor_split") or "").strip():
            out["split_mode"] = str(recipe.get("split_mode") or "layer")
            out["tensor_split"] = str(recipe.get("tensor_split") or "").strip()
            out["pin_cuda"] = False
            out["cuda_device"] = ""
        else:
            out["split_mode"] = ""
            out["tensor_split"] = ""
            out["pin_cuda"] = True
            out["cuda_device"] = str(
                recipe.get("chat_gpu_index")
                if recipe.get("chat_gpu_index") is not None
                else "0"
            )
    out["gpu_policy"] = policy
    return out


def pinned_launch_settings(db_path: str = DEFAULT_SHIPS_DB) -> Dict[str, Any]:
    """The user's ``app.launch.*`` pins, or defaults when the store is unreachable."""
    from .config_defaults import merge_launch_settings

    try:
        from . import settings_store

        rows = settings_store.get_all(db_path, "app.launch.")
    except Exception:
        return merge_launch_settings(None)
    return merge_launch_settings(
        {key.rsplit(".", 1)[-1]: value for key, value in (rows or {}).items()}
    )


def launch_plan_for_role(
    db_path: str, recipe: Optional[Dict[str, Any]], role: str
) -> Dict[str, Any]:
    """Recipe overrides with the pinned Launch flags applied on top.

    The recipe describes the machine; ``app.launch.*`` is what the user pinned
    by hand and wins for the portable knobs. ``-ngl`` stays ``-1`` unless pinned,
    because ``-1`` is what makes the manager ask llmfit for a VRAM-safe count.
    ``ngl_source`` names where the number came from, so a launch log can tell a
    pinned value apart from llmfit's.
    """
    out = launch_overrides_for_role(recipe, role)
    pinned = pinned_launch_settings(db_path)
    ngl = str(pinned.get("ngl") or "-1")
    if ngl != "-1":
        out["ngl"] = ngl
        out["ngl_source"] = "pinned in app.launch.ngl"
    else:
        out.setdefault("ngl", "-1")
        out["ngl_source"] = ""
    if (role or "").lower() in ("embedding", "embed"):
        out["n_parallel"] = int(pinned.get("embed_np") or 1)
        out["n_cpu_moe"] = 0
        out["flash_attn"] = False
        out["cache_type_k"] = ""
        out["cache_type_v"] = ""
        out.pop("reasoning", None)
    else:
        out["flash_attn"] = bool(pinned.get("flash_attn", True))
        out["cache_type_k"] = str(pinned.get("cache_type_k") or "")
        out["cache_type_v"] = str(pinned.get("cache_type_v") or "")
        out["reasoning"] = str(pinned.get("reasoning") or "off")
    return out
