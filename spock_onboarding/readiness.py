"""Readiness artifact for menu + future PyQt UI contract."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


READY_FILENAME = "spock_ready_last.json"  # frozen schema for future PyQt UI


def ready_path(root: Path) -> Path:
    return root / READY_FILENAME


def check_ui_ready(root: Path) -> Dict[str, Any]:
    venv_py = root / ".venv" / "Scripts" / "python.exe"
    if not venv_py.is_file():
        venv_py = root / ".venv" / "bin" / "python"
    detail = {
        "venv_python": str(venv_py) if venv_py.is_file() else "",
        "pyqt6_importable": False,
        "ui_ready": False,
        "detail": "",
    }
    if not venv_py.is_file():
        detail["detail"] = "missing .venv"
        return detail
    import subprocess

    try:
        proc = subprocess.run(
            [str(venv_py), "-c", "import PyQt6"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        ok = proc.returncode == 0
        detail["pyqt6_importable"] = ok
        detail["ui_ready"] = ok
        detail["detail"] = "ok" if ok else (proc.stderr or proc.stdout or "import failed")[:200]
    except Exception as e:
        detail["detail"] = str(e)[:200]
    return detail


def collect_next_ui_prompts(root: Path, *, hf_token_present: bool) -> List[str]:
    prompts: List[str] = []
    if not hf_token_present:
        prompts.append("hf_token")
    env_path = root / ".env"
    if not env_path.is_file():
        prompts.append("api_keys")
    else:
        try:
            text = env_path.read_text(encoding="utf-8")
            if "API_KEY" not in text.upper() and "OPENAI" not in text.upper():
                prompts.append("api_keys")
        except OSError:
            prompts.append("api_keys")
    # Ingest paths are always a future UI concern until configured
    cfg = root / "app_config.json"
    if not cfg.is_file():
        prompts.append("ingest_paths")
    return prompts


def write_readiness(
    root: Path,
    *,
    ui_ready: bool,
    servers_ready: bool,
    full_deps_ok: bool = False,
    venv_python: str = "",
    embed: Optional[Dict[str, Any]] = None,
    chat: Optional[Dict[str, Any]] = None,
    reasons: Optional[List[str]] = None,
    next_ui_prompts: Optional[List[str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Path:
    payload: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "install_root": str(root.resolve()),
        "ui_ready": bool(ui_ready),
        "servers_ready": bool(servers_ready),
        "full_deps_ok": bool(full_deps_ok),
        "venv_python": venv_python,
        "embed": embed or {},
        "chat": chat or {},
        "reasons": reasons or [],
        "next_ui_prompts": next_ui_prompts or [],
        "schema_version": 1,
    }
    if extra:
        payload.update(extra)
    path = ready_path(root)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_readiness(root: Path) -> Optional[Dict[str, Any]]:
    path = ready_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def full_deps_marker(root: Path) -> bool:
    return (root / "bootstrap_full_deps.ok").is_file()


def format_status_text(data: Dict[str, Any]) -> str:
    lines = [
        f"install_root: {data.get('install_root')}",
        f"ui_ready:      {data.get('ui_ready')}",
        f"servers_ready:{data.get('servers_ready')}",
        f"full_deps_ok: {data.get('full_deps_ok')}",
    ]
    reasons = data.get("reasons") or []
    if reasons:
        lines.append("reasons: " + ", ".join(str(r) for r in reasons))
    prompts = data.get("next_ui_prompts") or []
    if prompts:
        lines.append("next_ui_prompts: " + ", ".join(str(p) for p in prompts))
    emb = data.get("embed") or {}
    chat = data.get("chat") or {}
    lines.append(
        f"embed :{emb.get('port', 8080)} reachable={emb.get('reachable')} "
        f"model={emb.get('model_name') or emb.get('model_path') or '-'}"
    )
    lines.append(
        f"chat  :{chat.get('port', 8081)} reachable={chat.get('reachable')} "
        f"model={chat.get('model_name') or chat.get('model_path') or '-'}"
    )
    return "\n".join(lines)
