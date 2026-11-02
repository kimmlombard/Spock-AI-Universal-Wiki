"""CPU / memory / GPU snapshot for Live Monitor (no Qt)."""

from __future__ import annotations

import shutil
import subprocess
from typing import Dict


def _nvidia_smi_gpus() -> Dict[str, Dict[str, str]]:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return {}
    try:
        proc = subprocess.run(
            [
                smi,
                "--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.free,power.draw",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    out: Dict[str, Dict[str, str]] = {}
    for i, line in enumerate((proc.stdout or "").splitlines()):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue
        name, util, temp, used, free, power = parts[:6]
        short = name if len(name) <= 28 else name[:25] + "..."
        try:
            used_gb = f"{float(used) / 1024:.2f} GB"
        except ValueError:
            used_gb = f"{used} MiB"
        try:
            free_gb = f"{float(free) / 1024:.2f} GB"
        except ValueError:
            free_gb = f"{free} MiB"
        out[f"GPU {i}"] = {
            "Name": short,
            "Utilization": f"{util}%",
            "Temperature": f"{temp} C",
            "VRAM Used": used_gb,
            "VRAM Free": free_gb,
            "Power": f"{power} W",
        }
    return out


def get_live_monitor_snapshot() -> Dict[str, Dict[str, str]]:
    """Return sections matching Ship Status Live Monitor boxes."""
    snap: Dict[str, Dict[str, str]] = {
        "CPU": {"Usage": "--", "Threads": "--", "Cores": "--", "Frequency": "--"},
        "Memory": {
            "Total": "--",
            "Used": "--",
            "Available": "--",
            "Percent": "--",
        },
    }
    try:
        import psutil
    except ImportError:
        snap["GPU 0"] = {
            "Name": "--",
            "Utilization": "--",
            "Temperature": "--",
            "VRAM Used": "--",
            "VRAM Free": "--",
            "Power": "--",
        }
        return snap

    cpu = psutil.cpu_percent(interval=0)
    cores = psutil.cpu_count(logical=False) or psutil.cpu_count() or 0
    threads = psutil.cpu_count(logical=True) or cores
    freq = psutil.cpu_freq()
    freq_s = f"{freq.current:.0f} MHz" if freq else "N/A"
    mem = psutil.virtual_memory()
    snap["CPU"] = {
        "Usage": f"{cpu:.1f}%",
        "Threads": str(threads),
        "Cores": str(cores),
        "Frequency": freq_s,
    }
    snap["Memory"] = {
        "Total": f"{mem.total / (1024**3):.1f} GB",
        "Used": f"{mem.used / (1024**3):.1f} GB",
        "Available": f"{mem.available / (1024**3):.1f} GB",
        "Percent": f"{mem.percent:.1f}%",
    }

    gpus = _nvidia_smi_gpus()
    if gpus:
        snap.update(gpus)
    else:
        snap["GPU 0"] = {
            "Name": "N/A",
            "Utilization": "--",
            "Temperature": "--",
            "VRAM Used": "--",
            "VRAM Free": "--",
            "Power": "--",
        }
    return snap
