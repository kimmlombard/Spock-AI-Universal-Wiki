"""Paths and config for UIEG capture (Search + Save).

Provenance: adapted from D:\\Spock-To-Bridge-UIEG-Scanner (ueig_capture.db → uieg_capture.db).
"""

from __future__ import annotations

import os
import shutil
from typing import Any, Dict, Tuple

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_CAPTURE_FOLDER = os.path.join(SCRIPT_DIR, "captured_files")
DEFAULT_DB_PATH = os.path.join(SCRIPT_DIR, "uieg_capture.db")
DEFAULT_PROMOTED_FOLDER = os.path.join(SCRIPT_DIR, "promoted_research")
LEGACY_DB_NAMES = ("ueig_capture.db",)

CHANNEL_CRAWL = "crawl"
CHANNEL_REPO = "repo"


def channel_disk_folder(capture_folder: str, channel: str) -> str:
    """On-disk home for a workflow channel under captured_files/."""
    sub = "crawl" if channel == CHANNEL_CRAWL else "repos"
    path = os.path.join(capture_folder, sub)
    os.makedirs(path, exist_ok=True)
    return path


def default_crawl_folder(capture_folder: str) -> str:
    return channel_disk_folder(capture_folder, CHANNEL_CRAWL)


def default_repo_folder(capture_folder: str) -> str:
    return channel_disk_folder(capture_folder, CHANNEL_REPO)


def merge_uieg_config(raw: Dict[str, Any] | None = None) -> Dict[str, Any]:
    cfg = {
        "capture_folder": DEFAULT_CAPTURE_FOLDER,
        "database_path": DEFAULT_DB_PATH,
        "promoted_folder": DEFAULT_PROMOTED_FOLDER,
        "crawl_link_limit": 10,
        "crawl_levels": 2,
        "crawl_timeout_sec": 15,
        "repo_extensions": [".md", ".py", ".txt", ".rst", ".json", ".toml", ".yml", ".yaml"],
    }
    if raw:
        for k, v in raw.items():
            if k in cfg and v is not None:
                cfg[k] = v
    # Normalize to absolute paths under Spock root when relative
    for path_key in ("capture_folder", "database_path", "promoted_folder"):
        p = cfg[path_key]
        if not os.path.isabs(p):
            cfg[path_key] = os.path.join(SCRIPT_DIR, p)
    return cfg


def ensure_capture_folder(capture_folder: str) -> str:
    os.makedirs(capture_folder, exist_ok=True)
    return capture_folder


def is_drive_root(path: str) -> bool:
    """True for Windows drive roots like D:\\ or D:/ (and Unix /)."""
    if not path or not str(path).strip():
        return False
    ap = os.path.abspath(path.strip())
    drive, tail = os.path.splitdrive(ap)
    if drive:
        return tail in ("\\", "/", "")
    # Unix root
    return ap == os.sep


def resolve_repo_capture_folder(path: str, *, folder_name: str = "captured_files") -> str:
    """Normalize a user-picked dest for repo fetch.

    If the pick is a drive root (e.g. D:\\), create <drive>\\captured_files and use that
    so files are not dumped at the root of the volume. When the pick is the capture root
    or ends with captured_files, ensure repos/ exists and return it.
    """
    raw = (path or "").strip() or DEFAULT_CAPTURE_FOLDER
    ap = os.path.abspath(raw)
    if is_drive_root(ap):
        drive, _ = os.path.splitdrive(ap)
        if drive:
            dest = os.path.join(drive + os.sep, folder_name)
        else:
            dest = os.path.join(os.sep, folder_name)
        os.makedirs(dest, exist_ok=True)
        return default_repo_folder(dest)
    os.makedirs(ap, exist_ok=True)
    base_name = os.path.basename(ap.rstrip("\\/"))
    if base_name == folder_name or ap == os.path.abspath(DEFAULT_CAPTURE_FOLDER):
        return default_repo_folder(ap)
    return ap


def ensure_promoted_folder(promoted_folder: str) -> str:
    os.makedirs(promoted_folder, exist_ok=True)
    return promoted_folder


def migrate_legacy_db(database_path: str) -> Tuple[bool, str]:
    """Rename/copy ueig_capture.db → uieg_capture.db if needed.

    Returns (did_migrate, message).
    """
    target = database_path
    if os.path.isfile(target):
        return False, "uieg_capture.db already present"

    search_dirs = [
        SCRIPT_DIR,
        os.path.dirname(target),
        os.path.join(os.path.dirname(SCRIPT_DIR), "Spock-To-Bridge-UIEG-Scanner"),
        r"D:\Spock-To-Bridge-UIEG-Scanner",
    ]
    for d in search_dirs:
        if not d or not os.path.isdir(d):
            continue
        for legacy_name in LEGACY_DB_NAMES:
            legacy = os.path.join(d, legacy_name)
            if os.path.isfile(legacy) and os.path.abspath(legacy) != os.path.abspath(target):
                os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
                try:
                    # Prefer rename when same directory; else copy
                    if os.path.dirname(os.path.abspath(legacy)) == os.path.dirname(
                        os.path.abspath(target)
                    ):
                        os.rename(legacy, target)
                        return True, f"Renamed {legacy_name} → {os.path.basename(target)}"
                    shutil.copy2(legacy, target)
                    return True, f"Copied {legacy} → {target}"
                except OSError as e:
                    return False, f"Migration failed: {e}"
    return False, "No legacy ueig_capture.db found"
