"""Bringup menu step definitions (aligned with Spock-Menu 1–16)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import List, Literal, Optional, Sequence


StepKind = Literal["cli", "spawn", "panel", "exit"]


@dataclass(frozen=True)
class BringupStep:
    id: int
    label: str
    kind: StepKind
    # Short nav button text
    nav_label: str


STEPS: Sequence[BringupStep] = (
    BringupStep(1, "Phase A — Python / venv / PyQt6 deps", "cli", "1 Phase A"),
    BringupStep(
        2,
        "Phase B — full deps (ingest / extractors / WebEngine)",
        "cli",
        "2 Phase B",
    ),
    BringupStep(3, "Acquire runtime + models (llama-server + GGUFs)", "cli", "3 Acquire"),
    BringupStep(4, "Bring up servers (:8080 embed + :8081 chat)", "cli", "4 Bring up servers"),
    BringupStep(5, "Status / probe (write spock_ready_last.json)", "cli", "5 Status / probe"),
    BringupStep(6, "MCP Adapter (stdio + HTTP tools)", "spawn", "6 MCP Adapter"),
    BringupStep(7, "Embedding Profile / RAG API", "spawn", "7 Embedding / RAG"),
    BringupStep(8, "Open Live Monitor (Ship Status GUI)", "spawn", "8 Live Monitor"),
    BringupStep(9, "Run Wiki Scan (wiki_agent.py + live log)", "spawn", "9 Wiki Scan"),
    BringupStep(
        10, "Ask AI / Deep Dive (same as Navigation Station)", "panel", "10 Ask AI"
    ),
    BringupStep(
        11, "Spock Navigation Station (full left-nav GUI)", "spawn", "11 Navigation"
    ),
    BringupStep(
        12, "Spock Engineering Maintenance (wiki / DB console)", "spawn", "12 Maintenance"
    ),
    BringupStep(
        13, "Spock UIEG KnowledgeBase (external capture)", "spawn", "13 UIEG"
    ),
    BringupStep(
        14, "Stop servers / kill all processes", "cli", "14 Stop / kill all"
    ),
    BringupStep(
        15,
        "Re-embed / switch embedding model (clear vectors, keep docs)",
        "cli",
        "15 Re-embed",
    ),
    BringupStep(16, "Exit", "exit", "16 Exit"),
)


def venv_python(root: Path) -> str:
    """Prefer the platform-native venv interpreter."""
    win = root / ".venv" / "Scripts" / "python.exe"
    nix = root / ".venv" / "bin" / "python"
    if os.name == "nt":
        if win.is_file():
            return str(win)
        if nix.is_file():
            return str(nix)
    else:
        if nix.is_file():
            return str(nix)
        if win.is_file():
            return str(win)
    import sys

    return sys.executable


def powershell_exe() -> str:
    windir = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
    candidate = Path(windir) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if candidate.is_file():
        return str(candidate)
    return "powershell.exe"


def build_cli_command(
    step_id: int, root: Path, extra_args: Optional[List[str]] = None
) -> Optional[List[str]]:
    """Return argv for a cli step, or None if not applicable.

    ``extra_args`` appends step-specific flags — step 3 uses it to pass the
    models the user chose from the fit shortlist.

    Phase A/B use ``bootstrap.ps1`` on Windows and ``bootstrap.sh`` on Linux/WSL.
    """
    py = venv_python(root)

    if step_id == 1:
        if os.name == "nt":
            return [
                powershell_exe(),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(root / "bootstrap.ps1"),
                "-NonInteractive",
                "-EmitEvents",
                "-NoHandOffGui",
                "-InstallRoot",
                str(root),
            ]
        return [
            "bash",
            str(root / "bootstrap.sh"),
            "--phase-a",
            "--install-root",
            str(root),
        ]
    if step_id == 2:
        if os.name == "nt":
            return [
                powershell_exe(),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(root / "bootstrap_phase_b_job.ps1"),
                "-InstallRoot",
                str(root),
                "-FullDeps",
                "-Validate",
            ]
        return [
            "bash",
            str(root / "bootstrap.sh"),
            "--phase-b",
            "--install-root",
            str(root),
        ]
    if step_id == 3:
        return [
            py,
            "-u",
            "-m",
            "spock_bringup",
            "--root",
            str(root),
            "acquire",
            *(extra_args or []),
        ]
    if step_id == 4:
        return [py, "-u", "-m", "spock_bringup", "--root", str(root), "up"]
    if step_id == 5:
        return [py, "-u", "-m", "spock_bringup", "--root", str(root), "status"]
    if step_id == 14:
        return [py, "-u", "-m", "spock_bringup", "--root", str(root), "down"]
    if step_id == 15:
        return [
            py,
            "-u",
            "-m",
            "spock_bringup",
            "--root",
            str(root),
            "reembed",
            "--yes",
        ]
    return None


def build_spawn_command(step_id: int, root: Path) -> Optional[List[str]]:
    py = venv_python(root)
    if step_id == 6:
        return [py, "-m", "spock_mcp_adapter", "--root", str(root)]
    if step_id == 7:
        return [py, "-m", "spock_rag_adapter", "--root", str(root)]
    if step_id == 8:
        return [py, "-m", "spock_live_monitor", "--root", str(root)]
    if step_id == 9:
        return [py, "-m", "spock_wiki_adapter", "--root", str(root)]
    if step_id == 11:
        return [py, str(root / "spock_navigation.py")]
    if step_id == 12:
        return [py, str(root / "spock_maintenance.py")]
    if step_id == 13:
        return [py, str(root / "spock_UIEG_KnowledgeBase.py")]
    return None


def step_by_id(step_id: int) -> Optional[BringupStep]:
    for s in STEPS:
        if s.id == step_id:
            return s
    return None
