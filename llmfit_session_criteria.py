"""Session-rooted LLMFit-shaped model pick criteria for Spock.

Loads ``llmfit_session_criteria.json`` once per process (or from
``SPOCK_LLMFIT_CRITERIA_JSON``). ``filters.providers`` is a hard allow-list:
empty list = ALL providers; non-empty excludes other orgs/families from
Acquire / HF Models / Launch.
"""

from __future__ import annotations

import copy
import datetime
import json
import os
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CRITERIA_PATH = os.path.join(SCRIPT_DIR, "llmfit_session_criteria.json")

_SCHEMA_VERSION = 2

# Display name → (org prefixes, id substrings). Custom names use name/ + name token.
KNOWN_PROVIDER_MAP: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]] = {
    "google": (("google/", "ggml-org/"), ("gemma", "embeddinggemma", "gemini")),
    "alibaba": (("qwen/",), ("qwen",)),
    "nvidia": (("nvidia/",), ("nemotron",)),
    "microsoft": (("microsoft/",), ("phi-", "phi4", "phi-4")),
    "meta": (("meta-llama/", "meta/"), ("llama-3", "llama3")),
}

KNOWN_PROVIDER_NAMES: Tuple[str, ...] = (
    "Google",
    "Alibaba",
    "Nvidia",
    "Microsoft",
    "Meta",
)

_DEFAULT_CRITERIA: Dict[str, Any] = {
    "schema_version": _SCHEMA_VERSION,
    "source": "spock-default",
    "created_at": "",
    "filters": {
        # Hard allow-list of display names. Empty = ALL. Legacy ``provider`` migrates in.
        "providers": ["Google"],
        "provider": "Google",  # mirrored first entry for llmfit query compat
        "search": "gemma",
        "min_fit": "marginal",
        "runtime": "llamacpp",
        "use_case": "chat",
        "sort": "score",
        "limit": 20,
        "include_too_tight": False,
        "max_context": None,
    },
    "chat": {
        "preferred_families": ["gemma", "gemma4", "gemma3"],
        "fallback_families": ["nemotron", "qwen"],
        "fallback_model_id": "bartowski/gemma-3-12b-it-GGUF",
    },
    "embed": {
        "preferred_families": ["embeddinggemma"],
        "fallback_families": ["nomic", "qwen3-embedding"],
        "fallback_model_id": "ggml-org/embeddinggemma-2-GGUF",
        "allow_dim_change": True,
    },
}

_cached: Optional[Dict[str, Any]] = None
_cached_path: Optional[str] = None


def criteria_path() -> str:
    env = (os.environ.get("SPOCK_LLMFIT_CRITERIA_JSON") or "").strip()
    return env or DEFAULT_CRITERIA_PATH


def default_criteria() -> Dict[str, Any]:
    data = copy.deepcopy(_DEFAULT_CRITERIA)
    data["created_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return data


def _as_provider_list(raw: Any) -> List[str]:
    if isinstance(raw, list):
        out: List[str] = []
        seen = set()
        for item in raw:
            name = str(item or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            # Canonicalize known names
            canon = next((n for n in KNOWN_PROVIDER_NAMES if n.lower() == key), name)
            out.append(canon)
        return out
    if isinstance(raw, str) and raw.strip():
        name = raw.strip()
        canon = next((n for n in KNOWN_PROVIDER_NAMES if n.lower() == name.lower()), name)
        return [canon]
    return []


def _sync_provider_fields(filters: Dict[str, Any]) -> None:
    """Keep ``providers`` + legacy ``provider`` consistent. Empty providers = ALL."""
    providers = _as_provider_list(filters.get("providers"))
    filters["providers"] = providers
    filters["provider"] = providers[0] if providers else ""


def _normalize(data: Dict[str, Any]) -> Dict[str, Any]:
    out = default_criteria()
    if not isinstance(data, dict):
        return out
    if data.get("schema_version") is not None:
        try:
            out["schema_version"] = int(data["schema_version"])
        except (TypeError, ValueError):
            pass
    if data.get("source"):
        out["source"] = str(data["source"])
    if data.get("created_at"):
        out["created_at"] = str(data["created_at"])
    filters = data.get("filters") if isinstance(data.get("filters"), dict) else {}
    # Copy scalar filter keys except provider fields (handled next).
    for key in list(out["filters"].keys()):
        if key in ("providers", "provider"):
            continue
        if key in filters:
            out["filters"][key] = filters[key]
    # Provider allow-list: prefer explicit ``providers`` (incl. empty=ALL);
    # else migrate legacy single ``provider`` string; else keep defaults.
    if "providers" in filters:
        out["filters"]["providers"] = filters.get("providers")
    elif "provider" in filters:
        out["filters"]["providers"] = _as_provider_list(filters.get("provider"))
    _sync_provider_fields(out["filters"])
    for role in ("chat", "embed"):
        role_data = data.get(role) if isinstance(data.get(role), dict) else {}
        for key, default in list(out[role].items()):
            if key not in role_data:
                continue
            val = role_data[key]
            if isinstance(default, list):
                if isinstance(val, list):
                    out[role][key] = [str(x) for x in val if str(x).strip()]
            elif isinstance(default, bool):
                out[role][key] = bool(val)
            else:
                out[role][key] = val
    out["schema_version"] = max(int(out.get("schema_version") or 1), _SCHEMA_VERSION)
    return out


def save_criteria(data: Optional[Dict[str, Any]] = None, *, path: Optional[str] = None) -> Dict[str, Any]:
    """Write criteria JSON and refresh the process cache."""
    global _cached, _cached_path
    target = path or criteria_path()
    payload = _normalize(data or (_cached if _cached is not None else default_criteria()))
    if not payload.get("created_at"):
        payload["created_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    parent = os.path.dirname(os.path.abspath(target))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    _cached = copy.deepcopy(payload)
    _cached_path = target
    return copy.deepcopy(payload)


def reload_criteria(*, path: Optional[str] = None) -> Dict[str, Any]:
    """Force re-read from disk (or bootstrap default file if missing)."""
    global _cached, _cached_path
    target = path or criteria_path()
    if not os.path.isfile(target):
        return save_criteria(default_criteria(), path=target)
    try:
        with open(target, encoding="utf-8-sig") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return save_criteria(default_criteria(), path=target)
    payload = _normalize(raw if isinstance(raw, dict) else {})
    _cached = payload
    _cached_path = target
    return copy.deepcopy(payload)


def load_criteria(*, refresh: bool = False) -> Dict[str, Any]:
    """Return process-session criteria (load once unless ``refresh``)."""
    global _cached, _cached_path
    target = criteria_path()
    if refresh or _cached is None or _cached_path != target:
        return reload_criteria(path=target)
    return copy.deepcopy(_cached)


def clear_criteria_cache() -> None:
    """Test helper: drop the process cache without touching disk."""
    global _cached, _cached_path
    _cached = None
    _cached_path = None


def role_block(role: str = "chat", *, criteria: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = criteria if isinstance(criteria, dict) else load_criteria()
    key = "embed" if role in ("embed", "embedding") else "chat"
    block = data.get(key)
    return dict(block) if isinstance(block, dict) else {}


def allow_dim_change(*, criteria: Optional[Dict[str, Any]] = None) -> bool:
    embed = role_block("embed", criteria=criteria)
    return bool(embed.get("allow_dim_change", True))


def preferred_families(role: str = "chat", *, criteria: Optional[Dict[str, Any]] = None) -> List[str]:
    block = role_block(role, criteria=criteria)
    prefs = block.get("preferred_families") or []
    return [str(x).lower() for x in prefs if str(x).strip()]


def fallback_families(role: str = "chat", *, criteria: Optional[Dict[str, Any]] = None) -> List[str]:
    """Fallback families used only when provider allow-list is empty (ALL)."""
    if provider_allowlist(criteria=criteria):
        return []
    block = role_block(role, criteria=criteria)
    falls = block.get("fallback_families") or []
    return [str(x).lower() for x in falls if str(x).strip()]


def fallback_model_id(role: str = "chat", *, criteria: Optional[Dict[str, Any]] = None) -> str:
    block = role_block(role, criteria=criteria)
    fid = str(block.get("fallback_model_id") or "").strip()
    if fid and not model_id_allowed(fid, criteria=criteria):
        return ""
    return fid


def provider_allowlist(*, criteria: Optional[Dict[str, Any]] = None) -> List[str]:
    """Display-name allow-list. Empty means ALL providers."""
    data = criteria if isinstance(criteria, dict) else load_criteria()
    filters = data.get("filters") if isinstance(data.get("filters"), dict) else {}
    return _as_provider_list(filters.get("providers"))


def provider_filter_label(*, criteria: Optional[Dict[str, Any]] = None) -> str:
    names = provider_allowlist(criteria=criteria)
    if not names:
        return "ALL"
    return ", ".join(names)


def set_providers(
    names: Sequence[str],
    *,
    path: Optional[str] = None,
    criteria: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Replace the allow-list and persist. Empty names = ALL."""
    data = criteria if isinstance(criteria, dict) else load_criteria()
    data = copy.deepcopy(data)
    filters = dict(data.get("filters") or {})
    filters["providers"] = _as_provider_list(list(names))
    _sync_provider_fields(filters)
    # Keep search hint aligned when Google-only.
    if filters["providers"] == ["Google"] and not str(filters.get("search") or "").strip():
        filters["search"] = "gemma"
    if not filters["providers"]:
        # ALL — leave search alone unless it was gemma-only; do not force clear.
        pass
    data["filters"] = filters
    return save_criteria(data, path=path)


def clear_provider_filter(*, path: Optional[str] = None) -> Dict[str, Any]:
    """Empty allow-list → ALL providers."""
    return set_providers([], path=path)


def _signals_for_provider(name: str) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    key = (name or "").strip().lower()
    if key in KNOWN_PROVIDER_MAP:
        return KNOWN_PROVIDER_MAP[key]
    token = key.replace(" ", "-")
    prefixes = (f"{token}/",) if token else ()
    tokens = (token,) if token else ()
    return prefixes, tokens


def model_id_allowed(model_id: str, *, criteria: Optional[Dict[str, Any]] = None) -> bool:
    """True if ``model_id`` (or local path/name) passes the provider allow-list."""
    names = provider_allowlist(criteria=criteria)
    if not names:
        return True
    low = (model_id or "").strip().lower().replace("\\", "/")
    if not low:
        return False
    # Meta exclude: llama matches must not be Nemotron when Meta is allowed alone
    # (handled per-provider below).
    for name in names:
        prefixes, tokens = _signals_for_provider(name)
        if any(low.startswith(p) or f"/{p.rstrip('/')}/" in f"/{low}" for p in prefixes):
            return True
        # Org segment in HF id
        if "/" in low:
            org = low.split("/", 1)[0] + "/"
            if org in prefixes:
                return True
        for tok in tokens:
            if not tok:
                continue
            if name.lower() == "meta" and "nemotron" in low:
                continue
            if tok in low:
                return True
    return False


def filter_model_rows(
    rows: Sequence[Dict[str, Any]],
    *,
    id_key: str = "id",
    criteria: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Drop Hub/catalog rows whose model id fails the provider allow-list."""
    if not provider_allowlist(criteria=criteria):
        return list(rows)
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        mid = str(row.get(id_key) or row.get("model_id") or "")
        if model_id_allowed(mid, criteria=criteria):
            out.append(row)
    return out


def filters_as_query(
    *,
    role: str = "chat",
    criteria: Optional[Dict[str, Any]] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """LLMFit ``GET /api/v1/models`` query params derived from session criteria."""
    data = criteria if isinstance(criteria, dict) else load_criteria()
    filters = dict(data.get("filters") or {})
    _sync_provider_fields(filters)
    if role in ("embed", "embedding"):
        filters["use_case"] = "embedding"
        if not filters.get("search"):
            filters["search"] = "gemma"
    if overrides:
        filters.update({k: v for k, v in overrides.items() if v is not None})
    out: Dict[str, Any] = {}
    for key, val in filters.items():
        if key == "providers":
            # llmfit API expects a single provider string when set.
            continue
        if val is None or val == "":
            continue
        if key == "include_too_tight":
            out[key] = "true" if val else "false"
            continue
        out[key] = val
    # When ALL, omit provider so dashboard is unfiltered.
    if not filters.get("providers"):
        out.pop("provider", None)
    return out


def _family_rank(mid: str, preferred: Sequence[str], fallback: Sequence[str]) -> int:
    low = (mid or "").lower()
    for i, fam in enumerate(preferred):
        if fam and fam in low:
            return i
    for i, fam in enumerate(fallback):
        if fam and fam in low:
            return 1000 + i
    return 10_000


def model_id_matches(mid: str, role: str = "chat", *, criteria: Optional[Dict[str, Any]] = None) -> bool:
    if not model_id_allowed(mid, criteria=criteria):
        return False
    prefs = preferred_families(role, criteria=criteria)
    falls = fallback_families(role, criteria=criteria)
    if not prefs and not falls:
        return True
    return _family_rank(mid, prefs, falls) < 10_000


def family_preference_bonus(
    mid: str,
    role: str = "chat",
    *,
    criteria: Optional[Dict[str, Any]] = None,
) -> int:
    """Higher is better. Preferred families beat fallbacks; unknown get 0."""
    if not model_id_allowed(mid, criteria=criteria):
        return -10_000
    prefs = preferred_families(role, criteria=criteria)
    falls = fallback_families(role, criteria=criteria)
    rank = _family_rank(mid, prefs, falls)
    if rank >= 10_000:
        return 0
    if rank < 1000:
        return 220 - min(rank, 10) * 8
    return 140 - min(rank - 1000, 10) * 8


def preferred_publisher_prefixes(*, criteria: Optional[Dict[str, Any]] = None) -> List[str]:
    """Org prefixes to prefer when resolving Hub family matches."""
    data = criteria if isinstance(criteria, dict) else load_criteria()
    names = provider_allowlist(criteria=data)
    prefixes: List[str] = []
    if names:
        for name in names:
            prefs, _tokens = _signals_for_provider(name)
            prefixes.extend(prefs)
    else:
        # ALL — include common publishers + fallback catalog orgs.
        for name in KNOWN_PROVIDER_NAMES:
            prefs, _tokens = _signals_for_provider(name)
            prefixes.extend(prefs)
        for role in ("chat", "embed"):
            fid = str(role_block(role, criteria=data).get("fallback_model_id") or "")
            if "/" in fid:
                prefixes.append(fid.split("/", 1)[0].lower() + "/")
        prefixes.extend(["nomic-ai/", "bartowski/"])
    seen = set()
    out: List[str] = []
    for p in prefixes:
        pl = (p or "").lower()
        if pl and pl not in seen:
            seen.add(pl)
            out.append(pl)
    return out


def pick_from_ids(
    ids: Iterable[str],
    role: str = "chat",
    *,
    criteria: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Choose the best loaded/listed model id for ``role`` using session criteria."""
    data = criteria if isinstance(criteria, dict) else load_criteria()
    cleaned = [
        str(mid).strip()
        for mid in ids
        if str(mid).strip() and model_id_allowed(str(mid), criteria=data)
    ]
    if not cleaned:
        return None
    prefs = preferred_families(role, criteria=data)
    falls = fallback_families(role, criteria=data)

    def sort_key(mid: str):
        return (_family_rank(mid, prefs, falls), -len(mid))

    ranked = sorted(cleaned, key=sort_key)
    best = ranked[0]
    if _family_rank(best, prefs, falls) < 10_000 or not prefs:
        return best
    return cleaned[0]


def pick_loaded_or_fallback(
    ids: Iterable[str],
    role: str = "chat",
    *,
    criteria: Optional[Dict[str, Any]] = None,
) -> str:
    data = criteria if isinstance(criteria, dict) else load_criteria()
    picked = pick_from_ids(ids, role, criteria=data)
    if picked:
        prefs = preferred_families(role, criteria=data)
        falls = fallback_families(role, criteria=data)
        if not prefs or _family_rank(picked, prefs, falls) < 10_000:
            return picked
    return fallback_model_id(role, criteria=data) or (picked or "")
