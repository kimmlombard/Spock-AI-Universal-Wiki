#!/usr/bin/env bash
set -euo pipefail
DST="${SPOCK_WSL_DST:-$HOME/src/Spock-AI-Universal-Wiki}"
cd "$DST"
PY="$DST/.venv/bin/python"
[[ -x "$PY" ]] || PY=python3

"$PY" <<'PY'
from pathlib import Path
from spock_bringup_menu.steps import build_cli_command, build_spawn_command
root = Path(".").resolve()
c = build_cli_command(1, root)
print("phase_a", c)
assert c and c[0] == "bash" and c[1].endswith("bootstrap.sh")
c2 = build_cli_command(2, root)
print("phase_b", c2)
assert c2 and "--phase-b" in c2
print("spawn9", build_spawn_command(9, root))
from PyQt6.QtCore import PYQT_VERSION_STR
print("PyQt6", PYQT_VERSION_STR)
import spock_bringup_menu
print("bringup_menu ok")
PY

echo "DISPLAY=${DISPLAY:-} WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-}"
ls -la Spock-Menu.sh Spock-Menu-Console.sh spock_bringup_menu/steps.py
# Non-interactive import of GUI entry (no show)
"$PY" -c "import spock_bringup_menu.__main__ as m; print('entry', m.main)"
echo "smoke ok"
