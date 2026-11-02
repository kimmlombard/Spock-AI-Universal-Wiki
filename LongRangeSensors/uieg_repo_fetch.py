"""Fetch a GitHub (or git) repo into captured_files via clone or zip.

Secondary path for Option 3 step 1 — source truth for .md/.py when HTML crawl is a shell.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from typing import Callable, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse

import requests

LogFn = Callable[[str], None]

USER_AGENT = "Spock-to-bridge-UIEG-Capture/1.0"
DEFAULT_EXTS = {".md", ".py", ".txt", ".rst", ".json", ".toml", ".yml", ".yaml"}


def parse_github_repo(url_or_slug: str) -> Optional[Tuple[str, str, str]]:
    """Return (owner, repo, ref) or None. Default ref=main."""
    s = (url_or_slug or "").strip().rstrip("/")
    if not s:
        return None
    # owner/repo[@ref]
    m = re.match(r"^([^/\s]+)/([^/\s@#]+)(?:@([^/\s]+))?$", s)
    if m and "github.com" not in s:
        return m.group(1), m.group(2).removesuffix(".git"), m.group(3) or "main"

    if not s.startswith(("http://", "https://")):
        s = "https://" + s
    try:
        p = urlparse(s)
    except Exception:
        return None
    if "github.com" not in (p.netloc or "").lower():
        return None
    parts = [x for x in p.path.split("/") if x]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1].removesuffix(".git")
    ref = "main"
    if len(parts) >= 4 and parts[2] in ("tree", "blob"):
        ref = parts[3]
    return owner, repo, ref


def _copy_allowlisted(
    src_root: str,
    dest_root: str,
    extensions: Set[str],
    log: LogFn,
) -> List[str]:
    written: List[str] = []
    skip = {".git", "__pycache__", "node_modules", ".venv", "venv"}
    for root, dirs, files in os.walk(src_root):
        dirs[:] = [d for d in dirs if d not in skip and not d.startswith(".")]
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in extensions:
                continue
            src = os.path.join(root, name)
            rel = os.path.relpath(src, src_root)
            dest = os.path.join(dest_root, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src, dest)
            written.append(dest)
    log(f"Copied {len(written)} allowlisted file(s) -> {dest_root}")
    return written


def fetch_repo_to_capture(
    url_or_slug: str,
    capture_folder: str,
    *,
    method: str = "auto",  # auto | git | zip
    extensions: Optional[Sequence[str]] = None,
    timeout_sec: int = 120,
    log: Optional[LogFn] = None,
) -> List[str]:
    """Clone or zip-download repo; extract allowlisted files under captured_files/<owner>_<repo>/."""
    _log = log or (lambda _m: None)
    parsed = parse_github_repo(url_or_slug)
    if not parsed:
        _log("Could not parse GitHub owner/repo from input.")
        return []
    owner, repo, ref = parsed
    exts = {
        e.lower() if str(e).startswith(".") else f".{str(e).lower()}"
        for e in (extensions or DEFAULT_EXTS)
    }
    dest_leaf = f"{owner}_{repo}"
    dest_root = os.path.join(capture_folder, dest_leaf)
    os.makedirs(capture_folder, exist_ok=True)

    use_git = method == "git" or (
        method == "auto" and shutil.which("git") is not None
    )
    if method == "zip":
        use_git = False

    if use_git:
        written = _fetch_via_git(owner, repo, ref, dest_root, exts, timeout_sec, _log)
        if written:
            return written
        _log("git clone failed or empty - trying zip...")

    return _fetch_via_zip(owner, repo, ref, dest_root, exts, timeout_sec, _log)


def _fetch_via_git(
    owner: str,
    repo: str,
    ref: str,
    dest_root: str,
    exts: Set[str],
    timeout_sec: int,
    log: LogFn,
) -> List[str]:
    clone_parent = os.path.join(os.path.dirname(dest_root), "_repos")
    os.makedirs(clone_parent, exist_ok=True)
    clone_dir = os.path.join(clone_parent, f"{owner}_{repo}_{ref}")
    if os.path.isdir(clone_dir):
        shutil.rmtree(clone_dir, ignore_errors=True)
    url = f"https://github.com/{owner}/{repo}.git"
    log(f"git clone --depth 1 --branch {ref} {url}")
    try:
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                ref,
                url,
                clone_dir,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        # branch may not exist — try without --branch (default HEAD)
        log(f"Clone with branch={ref} failed ({e}); retrying default HEAD…")
        if os.path.isdir(clone_dir):
            shutil.rmtree(clone_dir, ignore_errors=True)
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", url, clone_dir],
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e2:
            log(f"git clone failed: {e2}")
            return []

    if os.path.isdir(dest_root):
        shutil.rmtree(dest_root, ignore_errors=True)
    os.makedirs(dest_root, exist_ok=True)
    return _copy_allowlisted(clone_dir, dest_root, exts, log)


def _fetch_via_zip(
    owner: str,
    repo: str,
    ref: str,
    dest_root: str,
    exts: Set[str],
    timeout_sec: int,
    log: LogFn,
) -> List[str]:
    zip_urls = [
        f"https://github.com/{owner}/{repo}/archive/refs/heads/{ref}.zip",
        f"https://github.com/{owner}/{repo}/archive/refs/tags/{ref}.zip",
        f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{ref}",
    ]
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    data = None
    used = None
    for zurl in zip_urls:
        try:
            log(f"Downloading {zurl}")
            r = session.get(zurl, timeout=timeout_sec, allow_redirects=True)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            data = r.content
            used = zurl
            break
        except Exception as e:
            log(f"Zip fetch failed ({zurl}): {e}")
    if not data:
        log("All zip download attempts failed.")
        return []

    with tempfile.TemporaryDirectory(prefix="spock_uieg_") as tmp:
        zpath = os.path.join(tmp, "repo.zip")
        with open(zpath, "wb") as f:
            f.write(data)
        extract_dir = os.path.join(tmp, "extract")
        os.makedirs(extract_dir, exist_ok=True)
        try:
            with zipfile.ZipFile(zpath, "r") as zf:
                zf.extractall(extract_dir)
        except zipfile.BadZipFile as e:
            log(f"Bad zip from {used}: {e}")
            return []
        # GitHub zips nest under owner-repo-ref/
        children = [os.path.join(extract_dir, n) for n in os.listdir(extract_dir)]
        src_root = children[0] if len(children) == 1 and os.path.isdir(children[0]) else extract_dir
        if os.path.isdir(dest_root):
            shutil.rmtree(dest_root, ignore_errors=True)
        os.makedirs(dest_root, exist_ok=True)
        log(f"Extracted zip from {used}")
        return _copy_allowlisted(src_root, dest_root, exts, log)
