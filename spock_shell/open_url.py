"""Open http(s)/file URLs in a real browser — WSL/WSLg safe.

Under WSLg, ``gio open`` / ``xdg-open`` often fail with
``Operation not supported`` (no xdg-desktop-portal). Prefer Firefox / Chrome
directly when present; fall back to ``webbrowser`` then Qt.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List


def running_under_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text(
            encoding="utf-8", errors="ignore"
        ).lower()
    except Exception:
        return False


def _candidate_browsers() -> List[str]:
    out: List[str] = []
    env_b = (os.environ.get("BROWSER") or "").strip()
    if env_b:
        # BROWSER may be a bare name or an absolute path.
        resolved = shutil.which(env_b) or env_b
        out.append(resolved)
    for name in (
        "firefox",
        "google-chrome",
        "chromium-browser",
        "chromium",
        "microsoft-edge",
        "xdg-open",
    ):
        path = shutil.which(name)
        if path and path not in out:
            out.append(path)
    return out


def open_url(url: str) -> bool:
    """Best-effort open ``url``; returns True if a launch was attempted successfully."""
    target = (url or "").strip()
    if not target:
        return False

    # On WSL/Linux prefer a concrete browser binary — gio/xdg often fail for http.
    if running_under_wsl() or sys.platform.startswith("linux"):
        for browser in _candidate_browsers():
            if browser.endswith("xdg-open") and running_under_wsl():
                continue  # known-broken path under WSLg without portals
            try:
                subprocess.Popen(
                    [browser, target],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return True
            except OSError:
                continue

    try:
        import webbrowser

        if webbrowser.open(target):
            return True
    except Exception:
        pass

    try:
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices

        return bool(QDesktopServices.openUrl(QUrl(target)))
    except Exception:
        return False
