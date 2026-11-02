"""Detect / download llama-server (Windows) — headless."""

from __future__ import annotations

import json
import os
import shutil
import zipfile
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from urllib.request import Request, urlopen

LLAMA_RELEASES_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
ProgressCb = Optional[Callable[[str], None]]


def _say(cb: ProgressCb, msg: str) -> None:
    if cb:
        cb(msg)


def normalize_fs_path(path: str) -> str:
    raw = (path or "").strip()
    if not raw:
        return ""
    expanded = os.path.expandvars(os.path.expanduser(raw))
    p = Path(expanded)
    try:
        if p.exists():
            return str(p.resolve())
    except OSError:
        pass
    return os.path.normpath(str(p))


def default_llama_install_dir(root: Path) -> str:
    """Portable default: ``{SPOCK_ROOT}/tools/llama-server`` (Windows + WSL)."""
    try:
        from WarpCore.service_endpoints import llama_server_install_dir

        return str(llama_server_install_dir(root))
    except Exception:
        return str((root / "tools" / "llama-server").resolve())


def detect_llama_server(
    root: Path,
    config_hint: str = "",
    install_dir: str = "",
) -> Optional[str]:
    try:
        from WarpCore.service_endpoints import is_runnable_host_binary
    except Exception:  # pragma: no cover

        def is_runnable_host_binary(path: Path) -> bool:  # type: ignore
            return path.is_file() and (os.name == "nt" or path.suffix.lower() != ".exe")

    names = (
        ("llama-server.exe", "llama-server")
        if os.name == "nt"
        else ("llama-server", "llama-server.exe")
    )
    candidates: List[Path] = []
    if config_hint:
        p = Path(config_hint)
        candidates.append(p)
        if p.is_dir():
            for name in names:
                if os.name != "nt" and name.endswith(".exe"):
                    continue
                candidates.append(p / name)
    if install_dir:
        d = Path(install_dir)
        for name in names:
            if os.name != "nt" and name.endswith(".exe"):
                continue
            candidates.append(d / name)
        if d.is_dir():
            try:
                for name in names:
                    if os.name != "nt" and name.endswith(".exe"):
                        continue
                    for p in d.rglob(name):
                        candidates.append(p)
            except OSError:
                pass
    env = os.environ.get("LLAMA_SERVER_PATH", "").strip()
    if env:
        candidates.append(Path(env))
    try:
        from WarpCore.service_endpoints import llama_server_binary_candidates

        candidates.extend(llama_server_binary_candidates(root))
    except Exception:
        for name in names:
            if os.name != "nt" and name.endswith(".exe"):
                continue
            candidates.append(root / "tools" / "llama-server" / name)
            candidates.append(root / "tools" / "llamacpp" / name)
        which = shutil.which("llama-server")
        if which:
            candidates.append(Path(which))
        if os.name == "nt":
            which_exe = shutil.which("llama-server.exe")
            if which_exe:
                candidates.append(Path(which_exe))
    seen = set()
    for c in candidates:
        try:
            key = str(c.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            if is_runnable_host_binary(c):
                return str(c.resolve())
        except OSError:
            continue
    return None


def _http_json(url: str) -> dict:
    req = Request(
        url, headers={"User-Agent": "Spock-Onboarding/0.1", "Accept": "application/json"}
    )
    with urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download_file(url: str, dest: Path, cb: ProgressCb = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    name = url.split("/")[-1]
    req = Request(url, headers={"User-Agent": "Spock-Onboarding/0.1"})
    _say(cb, f"Downloading {name} …")
    with urlopen(req, timeout=600) as resp, open(dest, "wb") as out:
        total = 0
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            total += len(chunk)
            if total % (25 * 1024 * 1024) < 1024 * 1024:
                _say(cb, f"  … {name}: {total // (1024 * 1024)} MB")
    _say(cb, f"Saved {dest.name}")


def _pick_windows_assets(assets: list) -> Tuple[Optional[dict], Optional[dict]]:
    zips = [
        a
        for a in assets
        if a.get("browser_download_url") and str(a.get("name", "")).lower().endswith(".zip")
    ]

    def find_llama(*parts: str) -> Optional[dict]:
        for a in zips:
            low = str(a.get("name", "")).lower()
            if "cudart" in low:
                continue
            if not low.startswith("llama-"):
                continue
            if all(p in low for p in parts):
                return a
        return None

    def find_cudart(*parts: str) -> Optional[dict]:
        for a in zips:
            low = str(a.get("name", "")).lower()
            if "cudart" not in low:
                continue
            if all(p in low for p in parts):
                return a
        return None

    bin_asset = (
        find_llama("bin-win-cuda-12.4", "x64")
        or find_llama("bin-win-cuda-12", "x64")
        or find_llama("bin-win-cuda-13", "x64")
        or find_llama("bin-win-vulkan", "x64")
        or find_llama("bin-win-cpu", "x64")
    )
    cudart = None
    if bin_asset:
        low = bin_asset["name"].lower()
        if "cuda-12.4" in low:
            cudart = find_cudart("cuda-12.4")
        elif "cuda-13" in low:
            cudart = find_cudart("cuda-13")
        elif "cuda-12" in low:
            cudart = find_cudart("cuda-12")
    return bin_asset, cudart


def download_llama_server_windows(
    root: Path,
    install_dir: Optional[Path] = None,
    cb: ProgressCb = None,
) -> str:
    if os.name != "nt":
        raise RuntimeError("Automatic llama.cpp zip download is Windows-only in this build.")
    dest_dir = Path(install_dir) if install_dir else (root / "tools" / "llama-server")
    dest_dir = Path(normalize_fs_path(str(dest_dir)))
    if dest_dir.suffix.lower() == ".exe":
        dest_dir = dest_dir.parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / "models").mkdir(parents=True, exist_ok=True)

    _say(cb, f"Install folder: {dest_dir}")
    _say(cb, "Fetching latest llama.cpp release metadata…")
    data = _http_json(LLAMA_RELEASES_API)
    tag = data.get("tag_name", "?")
    assets = data.get("assets") or []
    bin_asset, cudart = _pick_windows_assets(assets)
    if not bin_asset:
        raise RuntimeError(f"No Windows llama-*.zip found in release {tag}.")
    _say(cb, f"Release {tag}: binary={bin_asset.get('name')}")

    staging = dest_dir / "_download"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    bin_zip = staging / bin_asset["name"]
    _download_file(bin_asset["browser_download_url"], bin_zip, cb)
    with zipfile.ZipFile(bin_zip, "r") as zf:
        zf.extractall(dest_dir)

    if cudart and cudart.get("name") != bin_asset.get("name"):
        crt_zip = staging / cudart["name"]
        _download_file(cudart["browser_download_url"], crt_zip, cb)
        with zipfile.ZipFile(crt_zip, "r") as zf:
            zf.extractall(dest_dir)

    exe = detect_llama_server(root, install_dir=str(dest_dir))
    if not exe:
        raise RuntimeError(
            f"Downloaded release {tag} but llama-server.exe not found under {dest_dir}"
        )
    tip = dest_dir / "SPOCK_LLAMA_PATH.txt"
    tip.write_text(exe + "\n", encoding="utf-8")
    root_tip = root / "tools" / "llama-server"
    root_tip.mkdir(parents=True, exist_ok=True)
    (root_tip / "SPOCK_LLAMA_PATH.txt").write_text(exe + "\n", encoding="utf-8")
    _say(cb, f"llama-server ready: {exe}")
    shutil.rmtree(staging, ignore_errors=True)
    return exe


def ensure_llama_server(
    root: Path,
    *,
    hint: str = "",
    install_dir: str = "",
    download_if_missing: bool = True,
    cb: ProgressCb = None,
) -> str:
    found = detect_llama_server(root, config_hint=hint, install_dir=install_dir)
    if found:
        return found
    if not download_if_missing:
        raise FileNotFoundError(
            "llama-server not found — set LLAMA_SERVER_PATH or place a native "
            "binary under tools/llama-server/ (Linux: llama-server, Windows: llama-server.exe)"
        )
    dest = Path(install_dir) if install_dir else Path(default_llama_install_dir(root))
    return download_llama_server_windows(root, install_dir=dest, cb=cb)
