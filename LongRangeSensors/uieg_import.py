"""Import files from captured_files/ into uieg_capture.db."""

from __future__ import annotations

import os
import shutil
from typing import Callable, List, Optional, Set

from LongRangeSensors.uieg_database import (
    create_batch,
    file_exists_in_db,
    insert_capture,
    update_batch_file_count,
)
from LongRangeSensors.uieg_paths import CHANNEL_CRAWL, CHANNEL_REPO

LogFn = Callable[[str], None]

SKIP_DIR_NAMES = {".git", "__pycache__", "node_modules", ".venv", "venv", "_repos"}
DEFAULT_IMPORT_EXTS = {
    ".html",
    ".htm",
    ".md",
    ".py",
    ".txt",
    ".rst",
    ".json",
    ".toml",
    ".yml",
    ".yaml",
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".pdf",
}


def _rel_filename(capture_folder: str, path: str) -> str:
    try:
        rel = os.path.relpath(path, capture_folder)
    except ValueError:
        rel = os.path.basename(path)
    return rel.replace("\\", "/")


def _default_source_kind(channel: str, override: Optional[str]) -> str:
    if override:
        return override
    if channel == CHANNEL_REPO:
        return "repo_file"
    return "crawl_html"


def import_captured_files(
    capture_folder: str,
    db_path: str,
    *,
    channel: str = CHANNEL_CRAWL,
    batch_id: Optional[int] = None,
    batch_label: Optional[str] = None,
    extensions: Optional[Set[str]] = None,
    source_kind: Optional[str] = None,
    source_url: Optional[str] = None,
    skip_existing: bool = True,
    log: Optional[LogFn] = None,
) -> int:
    """Scan capture_folder recursively; insert new files into DB. Returns count inserted."""
    _log = log or (lambda _m: None)
    exts = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in (extensions or DEFAULT_IMPORT_EXTS)}
    if not os.path.isdir(capture_folder):
        _log(f"Capture folder missing: {capture_folder}")
        return 0

    kind = _default_source_kind(channel, source_kind)
    if batch_id is None:
        label = (batch_label or os.path.basename(capture_folder.rstrip("\\/")) or channel).strip()
        batch_id = create_batch(
            db_path,
            channel,
            label,
            source_url=source_url,
            disk_root=capture_folder,
        )
        _log(f"Created batch #{batch_id} ({channel}) — {label}")

    inserted = 0
    for root, dirs, files in os.walk(capture_folder):
        dirs[:] = [d for d in dirs if d not in SKIP_DIR_NAMES and not d.startswith(".")]
        # Skip raw git clone trees under _repos (extracted copies live elsewhere)
        if os.path.basename(root) == "_repos" or f"{os.sep}_repos{os.sep}" in (root + os.sep):
            dirs.clear()
            continue
        for name in files:
            if name.startswith("."):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in exts:
                continue
            fpath = os.path.join(root, name)
            filename = _rel_filename(capture_folder, fpath)
            if skip_existing and file_exists_in_db(db_path, filename):
                continue
            try:
                with open(fpath, "rb") as f:
                    content = f.read()
            except OSError as e:
                _log(f"Skip {filename}: {e}")
                continue
            filetype = ext.lstrip(".") or "bin"
            insert_capture(
                db_path,
                filename,
                fpath,
                filetype,
                content,
                source_url=source_url,
                source_kind=kind,
                batch_id=batch_id,
                channel=channel,
            )
            inserted += 1
            _log(f"Imported {filename}")
    update_batch_file_count(db_path, batch_id, inserted)
    _log(f"Import done — {inserted} new row(s) in batch #{batch_id}.")
    return inserted


def copy_local_file_to_capture(
    src_path: str,
    capture_folder: str,
    *,
    log: Optional[LogFn] = None,
) -> Optional[str]:
    """Copy a user-picked file into captured_files. Returns dest path."""
    _log = log or (lambda _m: None)
    if not os.path.isfile(src_path):
        _log("File not found.")
        return None
    os.makedirs(capture_folder, exist_ok=True)
    dest = os.path.join(capture_folder, os.path.basename(src_path))
    if os.path.abspath(src_path) != os.path.abspath(dest):
        shutil.copy2(src_path, dest)
    _log(f"Copied -> {dest}")
    return dest
