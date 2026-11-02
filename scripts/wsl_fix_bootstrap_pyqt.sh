#!/usr/bin/env bash
set -euo pipefail
SRC=/mnt/d/Spock-AI-Universal-Wiki
DST=$HOME/src/Spock-AI-Universal-Wiki
sed -i 's/\r$//' "$SRC/bootstrap.sh"
cp -f "$SRC/bootstrap.sh" "$DST/bootstrap.sh"
cp -f "$SRC/bootstrap.sh" /mnt/d/Spock-Universal-AI-Wiki/bootstrap.sh 2>/dev/null || true
cd "$DST"
.venv/bin/python -c 'from PyQt6.QtCore import PYQT_VERSION_STR; print("PyQt6 OK", PYQT_VERSION_STR)'
bash bootstrap.sh --phase-a --install-root "$DST"
echo "PHASE_A done"
