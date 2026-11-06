#!/usr/bin/env bash
# Spock Bringup Menu (PyQt6). Peer of Spock-Menu.bat for Linux / WSL / macOS.
# If PyQt6 / .venv is missing, runs Phase A (bootstrap.sh) then opens the GUI.

set -uo pipefail

# Qt sizing: native Ubuntu defaults (1.0 / 96). Early WSL smoke tests used
# 1.25 / 144 — override only when WSLg/HiDPI text is still too small, e.g.:
#   QT_SCALE_FACTOR=1.25 QT_FONT_DPI=144 ./Spock-Menu.sh
export QT_SCALE_FACTOR="${QT_SCALE_FACTOR:-1.0}"
export QT_FONT_DPI="${QT_FONT_DPI:-96}"
# WSLg: gio/xdg-open often fails for http:// — prefer Firefox (or set BROWSER=…)
# macOS: open(1) / system default; leave BROWSER unset unless overridden.
if [[ "$(uname -s)" != "Darwin" ]]; then
  export BROWSER="${BROWSER:-firefox}"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${SPOCK_INSTALL_ROOT:-$SCRIPT_DIR}"
ROOT="$(cd "$ROOT" && pwd)"
cd "$ROOT"

VENV_PY="$ROOT/.venv/bin/python"
BOOTSTRAP="$ROOT/bootstrap.sh"

c_cyan()  { printf '\033[36m%s\033[0m\n' "$*"; }
c_red()   { printf '\033[31m%s\033[0m\n' "$*"; }
c_yellow(){ printf '\033[33m%s\033[0m\n' "$*"; }

pyqt6_ready() {
  [[ -x "$VENV_PY" ]] || return 1
  "$VENV_PY" -c 'import PyQt6' >/dev/null 2>&1
}

launch_gui() {
  c_cyan "Opening Spock Bringup Menu..."
  export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
  if [[ "$(uname -s)" != "Darwin" && -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
    c_yellow "No DISPLAY/WAYLAND_DISPLAY — WSLg or an X server is required for the GUI."
    c_yellow "Fallback: ./spock_menu.sh   or   ./Spock-Menu-Console.sh"
  fi
  set +e
  "$VENV_PY" -m spock_bringup_menu "$@"
  local code=$?
  set -e
  if [[ "$code" -ne 0 ]]; then
    echo ""
    c_red "Bringup Menu exited with an error ($code)."
    return "$code"
  fi
  return 0
}

need_phase_a() {
  c_yellow "PyQt6 / venv not ready — running Phase A (bootstrap)..."
  echo ""
  if [[ ! -f "$BOOTSTRAP" ]]; then
    c_red "Missing $BOOTSTRAP"
    exit 1
  fi
  bash "$BOOTSTRAP" --phase-a --install-root "$ROOT"
  local code=$?
  if [[ "$code" -ne 0 ]]; then
    echo ""
    c_red "Phase A failed. Fix errors above, then run ./Spock-Menu.sh again."
    c_yellow "Or use ./Spock-Menu-Console.sh / ./spock_menu.sh for the text menu."
    exit "$code"
  fi
  if [[ ! -x "$VENV_PY" ]]; then
    c_red "Phase A finished but .venv/bin/python is still missing."
    exit 1
  fi
  if ! pyqt6_ready; then
    c_red "Phase A finished but PyQt6 still not importable."
    exit 1
  fi
}

if ! pyqt6_ready; then
  need_phase_a
fi

launch_gui "$@"
exit $?
