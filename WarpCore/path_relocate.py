"""Heal Spock_Console (and related) absolute paths after the DB moves OS/root.

Dual-boot / folder-copy leaves Linux paths in ``ship_computer.db`` when the
tree is opened on Windows (and the reverse). Host-recipe drift already covers
GPUs; this module remaps Spock-rooted filesystem paths on first launch.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Dict, List, Optional, Tuple

# Relative anchors that identify Spock-tree paths even when the old absolute
# prefix is unknown (different username / drive letter).
_SPOCK_ANCHORS = (
    "models",
    "tools",
    "captured_files",
    "promoted_research",
    "logs",
    "data",
    "ship_computer.db",
    "uieg_capture.db",
    "first_models_last.json",
)

_WIN_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")
_SETTINGS_ROOT_KEY = "settings.spock_root"
_SETTINGS_HOST_OS_KEY = "settings.host_os"

# One full heal pass per process unless force=True.
_HEAL_CACHE: Dict[str, Dict[str, Any]] = {}


def host_os_name() -> str:
    return "nt" if os.name == "nt" else "posix"


def looks_like_windows_path(value: str) -> bool:
    s = (value or "").strip().strip('"')
    if not s:
        return False
    if _WIN_ABS_RE.match(s) or s.startswith("\\\\"):
        return True
    return "\\" in s and not s.startswith("/")


def looks_like_posix_path(value: str) -> bool:
    s = (value or "").strip().strip('"')
    if not s or s.startswith("//"):
        return False
    if s.startswith("/") and not _WIN_ABS_RE.match(s):
        return True
    return False


def looks_like_url(value: str) -> bool:
    low = (value or "").strip().lower()
    return low.startswith(("http://", "https://", "ws://", "wss://", "file:"))


def _pure_parts(value: str) -> Tuple[str, ...]:
    s = (value or "").strip().strip('"')
    if looks_like_windows_path(s):
        return PureWindowsPath(s).parts
    return PurePosixPath(s).parts


def _rel_under_anchor(value: str) -> Optional[Path]:
    """If ``value`` contains a Spock anchor, return path from that anchor down."""
    parts = _pure_parts(value)
    if not parts:
        return None
    lowered = [p.lower() for p in parts]
    for anchor in _SPOCK_ANCHORS:
        want = anchor.lower()
        for i, part in enumerate(lowered):
            if part == want:
                return Path(*parts[i:])
    # Repo folder name + relative (…/Spock-AI-Universal-Wiki/models/…)
    for i, part in enumerate(parts):
        if part.lower() in {"spock-ai-universal-wiki", "spock-onboarding"}:
            if i + 1 < len(parts):
                return Path(*parts[i + 1 :])
            return Path()
    return None


def _exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def relocate_path(
    value: str,
    *,
    new_root: Path,
    old_root: str = "",
) -> Optional[str]:
    """Return a host-native path under ``new_root``, or None if unchanged/skip.

    Prefer prefix-replace with ``old_root`` (from ``settings.spock_root``), then
    Spock-relative anchors. Only rewrite when the foreign path looks absolute
    or the stored root moved, and prefer a candidate that exists on disk.
    """
    raw = (value or "").strip().strip('"')
    if not raw or looks_like_url(raw):
        return None

    new_root = Path(new_root).resolve()
    host = host_os_name()
    foreign = (host == "nt" and looks_like_posix_path(raw)) or (
        host == "posix" and looks_like_windows_path(raw)
    )
    old = (old_root or "").strip().strip('"')

    candidates: List[Path] = []

    if old:
        # Case-insensitive prefix match for Windows; exact for POSIX stored roots.
        old_norm = old.replace("\\", "/").rstrip("/")
        raw_norm = raw.replace("\\", "/").rstrip("/")
        if host == "nt":
            match = raw_norm.lower().startswith(old_norm.lower())
        else:
            match = raw_norm.startswith(old_norm) or raw_norm.lower().startswith(
                old_norm.lower()
            )
        if match:
            suffix = raw_norm[len(old_norm) :].lstrip("/")
            candidates.append(new_root / Path(*PurePosixPath(suffix).parts) if suffix else new_root)

    rel = _rel_under_anchor(raw)
    if rel is not None:
        candidates.append(new_root / rel)

    # Already under new_root but wrong separators / drive from the other OS
    try:
        as_path = Path(raw)
        if not foreign and _exists(as_path):
            return None
    except (OSError, ValueError):
        pass

    if not candidates and not foreign:
        # Same OS, path missing: try anchor remap when root moved
        if old and Path(old).resolve() != new_root:
            rel2 = _rel_under_anchor(raw)
            if rel2 is not None:
                candidates.append(new_root / rel2)
        if not candidates:
            return None

    # Prefer existing files/dirs; otherwise first candidate when foreign
    for cand in candidates:
        if _exists(cand):
            return str(cand.resolve())
    if foreign and candidates:
        return str(candidates[0])
    if candidates and old and Path(old).resolve() != new_root:
        # Root moved on same OS — rewrite even if target not yet present
        # (e.g. models not copied) when prefix matched.
        return str(candidates[0])
    return None


def relocate_value(
    value: Any,
    *,
    new_root: Path,
    old_root: str = "",
) -> Tuple[Any, int]:
    """Deep-walk str / list / dict; return (new_value, change_count)."""
    if isinstance(value, str):
        healed = relocate_path(value, new_root=new_root, old_root=old_root)
        if healed is not None and healed != value:
            return healed, 1
        return value, 0
    if isinstance(value, list):
        out: List[Any] = []
        n = 0
        for item in value:
            ni, c = relocate_value(item, new_root=new_root, old_root=old_root)
            out.append(ni)
            n += c
        return out, n
    if isinstance(value, dict):
        out_d: Dict[str, Any] = {}
        n = 0
        for k, v in value.items():
            nv, c = relocate_value(v, new_root=new_root, old_root=old_root)
            out_d[k] = nv
            n += c
        return out_d, n
    return value, 0


def _heal_first_models_json(root: Path, old_root: str) -> int:
    path = root / "first_models_last.json"
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if not isinstance(data, dict):
        return 0
    new_data, n = relocate_value(data, new_root=root, old_root=old_root)
    if n:
        try:
            path.write_text(
                json.dumps(new_data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError:
            return 0
    return n


def heal_relocated_paths(
    db_path: str,
    *,
    root: Optional[Path] = None,
    by: str = "path_relocate",
    force: bool = False,
) -> Dict[str, Any]:
    """Rewrite foreign / moved Spock paths in Spock_Console.

    Idempotent: when ``settings.spock_root`` already matches this root and
    ``settings.host_os`` matches, returns quickly unless ``force=True``.
    """
    from WarpCore import settings_store as st

    new_root = Path(root).resolve() if root is not None else Path(db_path).resolve().parent
    cache_key = f"{os.path.normcase(str(Path(db_path).resolve()))}|{new_root}|{host_os_name()}"
    if not force and cache_key in _HEAL_CACHE:
        cached = dict(_HEAL_CACHE[cache_key])
        cached["skipped"] = True
        return cached

    report: Dict[str, Any] = {
        "ok": True,
        "changed": [],
        "root": str(new_root),
        "host_os": host_os_name(),
        "skipped": False,
    }

    old_root = ""
    old_os = ""
    try:
        if st.has(db_path, _SETTINGS_ROOT_KEY):
            old_root = str(st.get(db_path, _SETTINGS_ROOT_KEY) or "")
        if st.has(db_path, _SETTINGS_HOST_OS_KEY):
            old_os = str(st.get(db_path, _SETTINGS_HOST_OS_KEY) or "")
    except Exception:
        pass

    same_root = False
    if old_root:
        try:
            same_root = Path(old_root).resolve() == new_root
        except OSError:
            same_root = os.path.normcase(old_root.rstrip("/\\")) == os.path.normcase(
                str(new_root).rstrip("/\\")
            )
    same_os = (old_os == host_os_name()) if old_os else False
    if same_root and same_os and not force:
        # Still scan for any foreign-looking path strings (partial prior heal).
        rows = st.get_all(db_path)
        foreign_left = False
        for val in rows.values():
            if isinstance(val, str) and (
                (host_os_name() == "nt" and looks_like_posix_path(val))
                or (host_os_name() == "posix" and looks_like_windows_path(val))
            ):
                foreign_left = True
                break
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and (
                        (host_os_name() == "nt" and looks_like_posix_path(item))
                        or (host_os_name() == "posix" and looks_like_windows_path(item))
                    ):
                        foreign_left = True
                        break
            if foreign_left:
                break
        if not foreign_left:
            report["skipped"] = True
            return report

    rows = st.get_all(db_path)
    updates: Dict[str, Any] = {}
    for name, value in rows.items():
        if name in (_SETTINGS_ROOT_KEY, _SETTINGS_HOST_OS_KEY):
            continue
        if name.startswith("secret.") or name.endswith(".token"):
            continue
        new_val, n = relocate_value(value, new_root=new_root, old_root=old_root)
        if n:
            updates[name] = new_val
            report["changed"].append({"key": name, "edits": n})

    if updates:
        st.set_many(db_path, updates, by=by)

    fm_edits = _heal_first_models_json(new_root, old_root)
    if fm_edits:
        report["changed"].append(
            {"key": "first_models_last.json", "edits": fm_edits}
        )

    st.set(db_path, _SETTINGS_ROOT_KEY, str(new_root), by=by)
    st.set(db_path, _SETTINGS_HOST_OS_KEY, host_os_name(), by=by)
    report["updated_keys"] = len(updates)
    _HEAL_CACHE[cache_key] = dict(report)
    return report
