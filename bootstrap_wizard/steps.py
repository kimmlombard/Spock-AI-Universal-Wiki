"""Named bootstrap steps shared by the control wizard UI."""

from __future__ import annotations

from typing import List, Tuple

# (id, title) — ids must match bootstrap.ps1 $STEP_ORDER where applicable
PHASE_A_STEPS: List[Tuple[str, str]] = [
    ("python", "Python 3.12"),
    ("install_root", "Resolve install root"),
    ("acquire", "Acquire app source"),
    ("folders", "Create folder tree"),
    ("database", "Empty database check"),
    ("venv", "Create Python venv"),
    ("pip_wizard", "Install wizard dependencies"),
]

# Order matters in the UI: full pip before health / Onboarding handoff
PHASE_B_STEPS: List[Tuple[str, str]] = [
    ("pip_full", "Install full requirements.txt (torch — required)"),
    ("validate", "Spock health check"),
    ("onboarding", "Launch Onboarding Wizard"),
]

ALL_STEPS: List[Tuple[str, str]] = PHASE_A_STEPS + PHASE_B_STEPS

# Written when detached Phase B (HeavyDeps) completes successfully
FULL_DEPS_MARKER = "bootstrap_full_deps.ok"
