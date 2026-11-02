#!/usr/bin/env bash
set -uo pipefail
cd "${SPOCK_WSL_DST:-$HOME/src/Spock-AI-Universal-Wiki}"
PY=.venv/bin/python

echo "--- exact bootstrap check ---"
"$PY" -c 'import PyQt6; print("PyQt6 OK", PyQt6.QtCore.PYQT_VERSION_STR)'
echo "exit=$?"

echo "--- fixed check ---"
"$PY" -c 'from PyQt6.QtCore import PYQT_VERSION_STR; print("PyQt6 OK", PYQT_VERSION_STR)'
echo "exit=$?"

echo "--- PyQt6 __init__ head ---"
head -80 .venv/lib/python3.12/site-packages/PyQt6/__init__.py
