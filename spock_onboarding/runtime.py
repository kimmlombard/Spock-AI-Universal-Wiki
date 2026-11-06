"""Detect / download llama-server (Windows + Linux/WSL + macOS Metal) — headless."""

from __future__ import annotations

import json
import os
import platform
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from urllib.request import Request, urlopen

# llama.cpp marks almost every build as prerelease; /releases/latest often
# points at an ancient non-prerelease with no current OS assets.
LLAMA_RELEASES_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=15"
ProgressCb = Optional[Callable[[str], None]]


def _say(cb: ProgressCb, msg: str) -> None:
    if cb:
        cb(msg)


def _latest_release_with_assets() -> dict:
    """Return the newest release that has downloadable assets."""
    data = _http_json(LLAMA_RELEASES_API)
    if isinstance(data, dict):
        # Back-compat if a single-release URL is ever restored.
        return data
    if not isinstance(data, list):
        raise RuntimeError("Unexpected llama.cpp releases API payload.")
    for release in data:
        if release.get("assets"):
            return release
    raise RuntimeError("No llama.cpp releases with assets found.")


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


def _download_file(
    url: str,
    dest: Path,
    cb: ProgressCb = None,
    *,
    expected_size: Optional[int] = None,
) -> None:
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
    got = dest.stat().st_size if dest.is_file() else 0
    if expected_size and int(expected_size) > 0 and got != int(expected_size):
        raise RuntimeError(
            f"Download size mismatch for {dest.name}: got {got} bytes, "
            f"expected {int(expected_size)} (incomplete or corrupt transfer)"
        )
    _say(cb, f"Saved {dest.name} ({got // (1024 * 1024)} MB)")


def _verify_zip(archive: Path) -> None:
    """Raise if the zip is truncated or has a Bad CRC member."""
    with zipfile.ZipFile(archive, "r") as zf:
        bad = zf.testzip()
        if bad is not None:
            raise zipfile.BadZipFile(f"Bad CRC-32 for file '{bad}' in {archive.name}")


def _download_asset(
    asset: dict,
    dest: Path,
    cb: ProgressCb = None,
    *,
    attempts: int = 3,
) -> Path:
    """Download a GitHub release asset; verify size and zip CRC; retry on failure."""
    url = str(asset.get("browser_download_url") or "")
    if not url:
        raise RuntimeError(f"Asset missing browser_download_url: {asset.get('name')}")
    expected = asset.get("size")
    try:
        expected_n = int(expected) if expected is not None else None
    except (TypeError, ValueError):
        expected_n = None
    last_err: Optional[BaseException] = None
    for n in range(1, max(1, attempts) + 1):
        try:
            if dest.exists():
                dest.unlink()
            _download_file(url, dest, cb, expected_size=expected_n)
            if dest.name.lower().endswith(".zip"):
                _say(cb, f"Verifying zip CRC: {dest.name}")
                _verify_zip(dest)
            return dest
        except (OSError, RuntimeError, zipfile.BadZipFile) as e:
            last_err = e
            _say(cb, f"Download/verify failed (attempt {n}/{attempts}): {e}")
            try:
                if dest.exists():
                    dest.unlink()
            except OSError:
                pass
    raise RuntimeError(
        f"Failed to download {asset.get('name')} after {attempts} attempts: {last_err}"
    )


def _asset_name(asset: dict) -> str:
    return str(asset.get("name", "")).lower()


def _match_cudart(assets: list, bin_asset: dict) -> Optional[dict]:
    low = _asset_name(bin_asset)
    want: Tuple[str, ...]
    if "cuda-12.8" in low:
        want = ("cuda-12.8",)
    elif "cuda-12.4" in low:
        want = ("cuda-12.4",)
    elif "cuda-13" in low:
        want = ("cuda-13",)
    elif "cuda-12" in low:
        want = ("cuda-12",)
    else:
        return None
    for a in assets:
        name = _asset_name(a)
        if "cudart" not in name:
            continue
        if all(p in name for p in want):
            return a
    return None


def _pick_windows_assets(assets: list) -> Tuple[Optional[dict], Optional[dict]]:
    zips = [
        a
        for a in assets
        if a.get("browser_download_url") and _asset_name(a).endswith(".zip")
    ]

    def find_llama(*parts: str) -> Optional[dict]:
        for a in zips:
            low = _asset_name(a)
            if "cudart" in low:
                continue
            if not low.startswith("llama-"):
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
    cudart = _match_cudart(zips, bin_asset) if bin_asset else None
    return bin_asset, cudart


def _pick_linux_assets(assets: list) -> Tuple[Optional[dict], Optional[dict]]:
    tars = [
        a
        for a in assets
        if a.get("browser_download_url")
        and (
            _asset_name(a).endswith(".tar.gz")
            or _asset_name(a).endswith(".tgz")
        )
    ]

    def find_llama(*parts: str) -> Optional[dict]:
        for a in tars:
            low = _asset_name(a)
            if "cudart" in low:
                continue
            if not low.startswith("llama-"):
                continue
            if all(p in low for p in parts):
                return a
        return None

    bin_asset = (
        find_llama("bin-ubuntu-cuda-12.8", "x64")
        or find_llama("bin-ubuntu-cuda-12.4", "x64")
        or find_llama("bin-ubuntu-cuda-12", "x64")
        or find_llama("bin-ubuntu-cuda-13", "x64")
        or find_llama("bin-ubuntu-vulkan", "x64")
        or find_llama("bin-ubuntu-cpu", "x64")
        or find_llama("bin-linux-cuda-12", "x64")
        or find_llama("bin-linux-cpu", "x64")
    )
    cudart = _match_cudart(tars, bin_asset) if bin_asset else None
    return bin_asset, cudart


def _pick_macos_assets(assets: list) -> Optional[dict]:
    """Pick Metal-capable macOS llama.cpp release (arm64 preferred on Apple Silicon)."""
    archives = [
        a
        for a in assets
        if a.get("browser_download_url")
        and (
            _asset_name(a).endswith(".tar.gz")
            or _asset_name(a).endswith(".tgz")
            or _asset_name(a).endswith(".zip")
        )
    ]

    def find_llama(*parts: str) -> Optional[dict]:
        for a in archives:
            low = _asset_name(a)
            if "cudart" in low or "xcframework" in low or "kleidiai" in low:
                continue
            if not low.startswith("llama-"):
                continue
            if all(p in low for p in parts):
                return a
        return None

    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        return find_llama("bin-macos-arm64") or find_llama("bin-macos", "arm64")
    return (
        find_llama("bin-macos-x64")
        or find_llama("bin-macos-x86_64")
        or find_llama("bin-macos", "x64")
    )


def _extract_zip(archive: Path, dest_dir: Path) -> None:
    _verify_zip(archive)
    with zipfile.ZipFile(archive, "r") as zf:
        zf.extractall(dest_dir)


def _safe_tar_relpath(member_name: str, *, strip: bool) -> Optional[Path]:
    """Map a tar member name to a dest-relative path, rejecting traversal."""
    parts = Path(member_name).parts
    if not parts:
        return None
    if strip:
        if len(parts) == 1:
            return None
        rel = Path(*parts[1:])
    else:
        rel = Path(*parts)
    if rel.is_absolute() or ".." in rel.parts:
        return None
    return rel


def _extract_tar_flat(archive: Path, dest_dir: Path) -> None:
    """Extract a release tarball, stripping a single shared top-level folder.

    Preserves relative symlinks (required for macOS ``libfoo.0.dylib`` soname
    aliases next to ``llama-server``).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as tf:
        members = [m for m in tf.getmembers() if m.name and m.name != "."]
        tops = {Path(m.name).parts[0] for m in members if Path(m.name).parts}
        strip = len(tops) == 1
        # Files first, then symlinks (targets must exist for some tools).
        ordered = sorted(members, key=lambda m: (m.issym() or m.islnk(), m.name))
        for member in ordered:
            rel = _safe_tar_relpath(member.name, strip=strip)
            if rel is None:
                continue
            target = dest_dir / rel
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if member.issym():
                link_target = member.linkname
                if not link_target or Path(link_target).is_absolute() or ".." in Path(link_target).parts:
                    continue
                try:
                    if target.exists() or target.is_symlink():
                        target.unlink()
                except OSError:
                    pass
                try:
                    os.symlink(link_target, target)
                except OSError:
                    pass
                continue
            if member.islnk():
                # Hard links: copy from already-extracted peer when possible.
                link_rel = _safe_tar_relpath(member.linkname, strip=strip)
                if link_rel is None:
                    continue
                src_path = dest_dir / link_rel
                if src_path.is_file():
                    shutil.copy2(src_path, target)
                continue
            src = tf.extractfile(member)
            if src is None:
                continue
            with src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            if member.mode:
                try:
                    os.chmod(target, member.mode & 0o777)
                except OSError:
                    pass


def _write_llama_path_tips(root: Path, dest_dir: Path, exe: str) -> None:
    tip = dest_dir / "SPOCK_LLAMA_PATH.txt"
    tip.write_text(exe + "\n", encoding="utf-8")
    root_tip = root / "tools" / "llama-server"
    root_tip.mkdir(parents=True, exist_ok=True)
    (root_tip / "SPOCK_LLAMA_PATH.txt").write_text(exe + "\n", encoding="utf-8")


def _prepare_llama_dest(root: Path, install_dir: Optional[Path]) -> Path:
    dest_dir = Path(install_dir) if install_dir else (root / "tools" / "llama-server")
    dest_dir = Path(normalize_fs_path(str(dest_dir)))
    # Caller may pass the binary path; install into its parent directory.
    if dest_dir.suffix.lower() == ".exe" or (
        dest_dir.name == "llama-server" and not dest_dir.is_dir()
    ):
        dest_dir = dest_dir.parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / "models").mkdir(parents=True, exist_ok=True)
    return dest_dir


def download_llama_server_windows(
    root: Path,
    install_dir: Optional[Path] = None,
    cb: ProgressCb = None,
) -> str:
    if os.name != "nt":
        raise RuntimeError("download_llama_server_windows requires Windows.")
    dest_dir = _prepare_llama_dest(root, install_dir)
    _say(cb, f"Install folder: {dest_dir}")
    _say(cb, "Fetching latest llama.cpp release metadata…")
    data = _latest_release_with_assets()
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
    _download_asset(bin_asset, bin_zip, cb)
    _extract_zip(bin_zip, dest_dir)

    if cudart and cudart.get("name") != bin_asset.get("name"):
        crt_zip = staging / cudart["name"]
        _download_asset(cudart, crt_zip, cb)
        _extract_zip(crt_zip, dest_dir)

    exe = detect_llama_server(root, install_dir=str(dest_dir))
    if not exe:
        raise RuntimeError(
            f"Downloaded release {tag} but llama-server.exe not found under {dest_dir}"
        )
    _write_llama_path_tips(root, dest_dir, exe)
    _say(cb, f"llama-server ready: {exe}")
    shutil.rmtree(staging, ignore_errors=True)
    return exe


def download_llama_server_linux(
    root: Path,
    install_dir: Optional[Path] = None,
    cb: ProgressCb = None,
) -> str:
    if os.name == "nt":
        raise RuntimeError("download_llama_server_linux requires Linux/WSL.")
    if sys_platform_is_darwin():
        raise RuntimeError("download_llama_server_linux does not run on macOS.")
    dest_dir = _prepare_llama_dest(root, install_dir)
    _say(cb, f"Install folder: {dest_dir}")
    _say(cb, "Fetching latest llama.cpp release metadata…")
    data = _latest_release_with_assets()
    tag = data.get("tag_name", "?")
    assets = data.get("assets") or []
    bin_asset, cudart = _pick_linux_assets(assets)
    if not bin_asset:
        raise RuntimeError(
            f"No Linux/Ubuntu llama-*.tar.gz found in release {tag}. "
            "Place a native llama-server under tools/llama-server/ manually."
        )
    _say(cb, f"Release {tag}: binary={bin_asset.get('name')}")

    staging = dest_dir / "_download"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    bin_tar = staging / bin_asset["name"]
    _download_asset(bin_asset, bin_tar, cb)
    _extract_tar_flat(bin_tar, dest_dir)

    if cudart and cudart.get("name") != bin_asset.get("name"):
        crt_tar = staging / cudart["name"]
        _download_asset(cudart, crt_tar, cb)
        _extract_tar_flat(crt_tar, dest_dir)

    _chmod_llama_server(dest_dir)

    exe = detect_llama_server(root, install_dir=str(dest_dir))
    if not exe:
        raise RuntimeError(
            f"Downloaded release {tag} but llama-server not found under {dest_dir}"
        )
    _write_llama_path_tips(root, dest_dir, exe)
    _say(cb, f"llama-server ready: {exe}")
    shutil.rmtree(staging, ignore_errors=True)
    return exe


def sys_platform_is_darwin() -> bool:
    return platform.system() == "Darwin"


def _chmod_llama_server(dest_dir: Path) -> None:
    exe_path = dest_dir / "llama-server"
    if exe_path.is_file():
        try:
            os.chmod(exe_path, exe_path.stat().st_mode | 0o111)
        except OSError:
            pass


def _extract_archive(archive: Path, dest_dir: Path) -> None:
    name = archive.name.lower()
    if name.endswith(".zip"):
        _extract_zip(archive, dest_dir)
        return
    _extract_tar_flat(archive, dest_dir)


def download_llama_server_macos(
    root: Path,
    install_dir: Optional[Path] = None,
    cb: ProgressCb = None,
) -> str:
    if not sys_platform_is_darwin():
        raise RuntimeError("download_llama_server_macos requires macOS.")
    dest_dir = _prepare_llama_dest(root, install_dir)
    _say(cb, f"Install folder: {dest_dir}")
    _say(cb, "Fetching latest llama.cpp release metadata…")
    data = _latest_release_with_assets()
    tag = data.get("tag_name", "?")
    assets = data.get("assets") or []
    bin_asset = _pick_macos_assets(assets)
    if not bin_asset:
        raise RuntimeError(
            f"No macOS llama-*-bin-macos-*.tar.gz/zip found in release {tag}. "
            "Place a native Metal llama-server under tools/llama-server/ manually."
        )
    _say(cb, f"Release {tag}: binary={bin_asset.get('name')} (Metal)")

    staging = dest_dir / "_download"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    bin_archive = staging / bin_asset["name"]
    _download_asset(bin_asset, bin_archive, cb)
    _extract_archive(bin_archive, dest_dir)
    _chmod_llama_server(dest_dir)

    exe = detect_llama_server(root, install_dir=str(dest_dir))
    if not exe:
        raise RuntimeError(
            f"Downloaded release {tag} but llama-server not found under {dest_dir}"
        )
    _write_llama_path_tips(root, dest_dir, exe)
    _say(cb, f"llama-server ready: {exe}")
    shutil.rmtree(staging, ignore_errors=True)
    return exe


def download_llama_server(
    root: Path,
    install_dir: Optional[Path] = None,
    cb: ProgressCb = None,
) -> str:
    """Download the host-native llama-server into ``tools/llama-server``."""
    if os.name == "nt":
        return download_llama_server_windows(root, install_dir=install_dir, cb=cb)
    if sys_platform_is_darwin():
        return download_llama_server_macos(root, install_dir=install_dir, cb=cb)
    return download_llama_server_linux(root, install_dir=install_dir, cb=cb)


def _windows_cuda_bundle_incomplete(dest_dir: Path) -> bool:
    """True when a CUDA build is present but cuBLAS runtime looks broken.

    A failed cudart zip extract leaves ``llama-server.exe`` + ``ggml-cuda.dll``
    while ``cublasLt64_*.dll`` is missing, tiny, or paired with a still-staged
    zip that fails CRC verification.
    """
    if os.name != "nt":
        return False
    if not (dest_dir / "ggml-cuda.dll").is_file():
        return False
    staging = dest_dir / "_download"
    if staging.is_dir():
        for zpath in staging.glob("cudart*.zip"):
            try:
                _verify_zip(zpath)
            except (OSError, zipfile.BadZipFile):
                return True
    candidates = sorted(dest_dir.glob("cublasLt64_*.dll"))
    if not candidates:
        return True
    # Full cublasLt is hundreds of MB; a few MB means a truncated extract.
    return max(p.stat().st_size for p in candidates) < 50 * 1024 * 1024


def ensure_llama_server(
    root: Path,
    *,
    hint: str = "",
    install_dir: str = "",
    download_if_missing: bool = True,
    cb: ProgressCb = None,
) -> str:
    dest = Path(install_dir) if install_dir else Path(default_llama_install_dir(root))
    found = detect_llama_server(root, config_hint=hint, install_dir=install_dir or str(dest))
    if found and not _windows_cuda_bundle_incomplete(Path(found).parent):
        return found
    if found and _windows_cuda_bundle_incomplete(Path(found).parent):
        _say(
            cb,
            "llama-server.exe is present but CUDA runtime DLLs look incomplete "
            "(likely a corrupt cudart zip). Re-downloading…",
        )
    if not download_if_missing:
        raise FileNotFoundError(
            "llama-server not found — set LLAMA_SERVER_PATH or place a native "
            "binary under tools/llama-server/ "
            "(macOS/Linux: llama-server, Windows: llama-server.exe)"
        )
    return download_llama_server(root, install_dir=dest, cb=cb)
