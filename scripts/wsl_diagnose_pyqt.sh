#!/usr/bin/env bash
set -uo pipefail
DST="${SPOCK_WSL_DST:-$HOME/src/Spock-AI-Universal-Wiki}"
cd "$DST"
PY="$DST/.venv/bin/python"
echo "DST=$DST"
echo "PY=$PY"
if [[ ! -x "$PY" ]]; then
  echo "missing venv python"
  exit 1
fi

echo "=== python ==="
"$PY" -c 'import sys; print(sys.executable); print(sys.version)'

echo "=== PyQt6 import ==="
"$PY" - <<'PY'
import PyQt6
print("module", PyQt6)
print("file", getattr(PyQt6, "__file__", None))
print("path", list(getattr(PyQt6, "__path__", [])))
print("dir sample", [x for x in dir(PyQt6) if not x.startswith("_")][:40])
try:
    from PyQt6 import QtCore
    print("QtCore OK", QtCore.PYQT_VERSION_STR)
except Exception as e:
    print("QtCore FAIL", type(e).__name__, e)
try:
    import PyQt6.QtCore as qc
    print("PyQt6.QtCore OK", qc.PYQT_VERSION_STR)
except Exception as e:
    print("PyQt6.QtCore FAIL", type(e).__name__, e)
PY

echo "=== pip show ==="
"$PY" -m pip show PyQt6 PyQt6-Qt6 PyQt6-sip 2>&1 || true

echo "=== site-packages/PyQt6 ==="
ls -la .venv/lib/python*/site-packages/PyQt6 2>&1 | head -50

echo "=== QtCore binary ==="
ls -la .venv/lib/python*/site-packages/PyQt6/QtCore* 2>&1 | head
ls -la .venv/lib/python*/site-packages/PyQt6/Qt6/lib/libQt6Core* 2>&1 | head

echo "=== shadow PyQt6 outside venv ==="
find . -maxdepth 3 \( -iname 'PyQt6.py' -o -iname 'PyQt6' \) ! -path './.venv/*' 2>/dev/null || true

echo "=== ldd QtCore (if .so) ==="
so=$(ls .venv/lib/python*/site-packages/PyQt6/QtCore*.so 2>/dev/null | head -1 || true)
if [[ -n "${so:-}" ]]; then
  echo "so=$so"
  ldd "$so" 2>&1 | head -40
else
  echo "no QtCore*.so found"
fi
