"""Cloudflare quick tunnel for the Spock MCP HTTP adapter.

Uses ``cloudflared tunnel --url http://127.0.0.1:<port>`` (no account required).
Named/account tunnels can be added later; this module focuses on the quick tunnel
flow that yields a ``*.trycloudflare.com`` URL for llama.cpp / browser MCP clients.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from spock_shell.paths import ROOT

_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.I)
_DEFAULT_CLOUDFLARED = Path(r"C:\Program Files (x86)\cloudflared\cloudflared.exe")


def find_cloudflared(explicit: str | Path | None = None) -> Optional[Path]:
    """Resolve cloudflared.exe — explicit path, PATH, then common install dir."""
    if explicit:
        p = Path(str(explicit).strip())
        if p.is_file():
            return p
    found = shutil.which("cloudflared")
    if found:
        return Path(found)
    if _DEFAULT_CLOUDFLARED.is_file():
        return _DEFAULT_CLOUDFLARED
    return None


def _log_path() -> Path:
    path = ROOT / "logs" / "cloudflared-mcp.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def discover_tunnel_pids() -> List[int]:
    """PIDs running cloudflared that mention our MCP port or log file."""
    marker = str(_log_path()).replace("\\", "/").lower()
    pids: List[int] = []
    try:
        import psutil
    except ImportError:
        return pids
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = str(proc.info.get("name") or "").lower()
            if "cloudflared" not in name:
                continue
            cmdline = " ".join(str(c) for c in (proc.info.get("cmdline") or []))
            folded = cmdline.replace("\\", "/").lower()
            if "8765" in folded or marker in folded or "trycloudflare" in folded:
                pids.append(int(proc.info["pid"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError, ValueError):
            continue
    return sorted(set(pids))


def read_public_url(log_file: Path | None = None) -> str:
    """Parse the most recent trycloudflare.com URL from cloudflared log output."""
    path = log_file or _log_path()
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    matches = _URL_RE.findall(text)
    return matches[-1] if matches else ""


def start_quick_tunnel(
    local_port: int = 8765,
    local_host: str = "127.0.0.1",
    cloudflared: str | Path | None = None,
    timeout: float = 45.0,
) -> Tuple[bool, str, Optional[subprocess.Popen], str]:
    """Start cloudflared quick tunnel → local MCP HTTP adapter.

    Returns (ok, detail, proc, public_base_url).
    """
    exe = find_cloudflared(cloudflared)
    if exe is None:
        return False, "cloudflared not found (install from Cloudflare or add to PATH)", None, ""

    from spock_shell.proc_guard import tcp_open

    if not tcp_open(str(local_host), int(local_port)):
        return (
            False,
            f"MCP HTTP adapter is not listening on {local_host}:{local_port}. "
            "Start streamable-http adapter first, then start the tunnel.",
            None,
            "",
        )

    existing = discover_tunnel_pids()
    if existing:
        url = read_public_url()
        if url:
            return True, f"Tunnel already running (PID {existing[0]})", None, url
        return True, f"cloudflared already running (PID {existing[0]})", None, ""

    log_path = _log_path()
    try:
        log_path.write_text("", encoding="utf-8")
    except OSError:
        pass

    target = f"http://{local_host}:{int(local_port)}"
    cmd = [str(exe), "tunnel", "--no-autoupdate", "--url", target]
    try:
        fh = open(log_path, "a", encoding="utf-8", errors="replace")
    except OSError as e:
        return False, f"Cannot write tunnel log: {e}", None, ""

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=fh,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as e:
        fh.close()
        return False, f"Failed to launch cloudflared: {e}", None, ""

    deadline = time.time() + max(5.0, float(timeout))
    public_url = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        public_url = read_public_url(log_path)
        if public_url:
            break
        time.sleep(0.35)

    fh.close()

    if proc.poll() is not None and not public_url:
        tail = ""
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = "\n".join(lines[-12:])
        except OSError:
            pass
        return False, f"cloudflared exited early.\n{tail}".strip(), None, ""

    if not public_url:
        return (
            False,
            "cloudflared started but no public URL appeared yet. "
            f"Check {log_path}",
            proc,
            "",
        )

    mcp_url = f"{public_url.rstrip('/')}/mcp"
    return (
        True,
        f"Tunnel up (PID {proc.pid})\nPublic MCP URL:\n  {mcp_url}",
        proc,
        public_url,
    )


def stop_tunnel(proc: subprocess.Popen | None = None) -> Tuple[bool, str]:
    """Stop our cloudflared spawn and any discovered tunnel PIDs."""
    stopped: List[str] = []
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=3)
            stopped.append(str(proc.pid))
        except Exception:
            try:
                proc.kill()
                stopped.append(str(proc.pid))
            except Exception:
                pass

    if os.name == "nt":
        for pid in discover_tunnel_pids():
            if str(pid) in stopped:
                continue
            try:
                p = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if p.returncode == 0:
                    stopped.append(str(pid))
            except Exception:
                continue

    if stopped:
        return True, f"Stopped cloudflared PID(s): {', '.join(stopped)}"
    return True, "No cloudflared tunnel was running"


def tunnel_status(local_port: int = 8765) -> Dict[str, Any]:
    """Snapshot for health / UI panels."""
    pids = discover_tunnel_pids()
    url = read_public_url()
    return {
        "pids": pids,
        "public_url": url,
        "mcp_url": f"{url.rstrip('/')}/mcp" if url else "",
        "running": bool(pids or url),
        "log_path": str(_log_path()),
        "local_port": int(local_port),
    }
