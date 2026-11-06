#!/usr/bin/env bash
# bootstrap.sh — Spock Phase A/B for Linux / WSL / macOS (peer of bootstrap.ps1)
#
# Usage:
#   ./bootstrap.sh                  # Phase A: python3 + .venv + requirements-ui.txt
#   ./bootstrap.sh --phase-b        # Phase B: requirements-full.txt (+ validate)
#   ./bootstrap.sh --install-root /path/to/Spock-AI-Universal-Wiki

set -euo pipefail

PHASE="a"
INSTALL_ROOT=""
VALIDATE=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --phase-b|--full-deps) PHASE="b"; shift ;;
    --phase-a) PHASE="a"; shift ;;
    --install-root)
      INSTALL_ROOT="${2:-}"; shift 2 ;;
    --no-validate) VALIDATE=0; shift ;;
    -h|--help)
      sed -n '1,12p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "$INSTALL_ROOT" ]]; then
  INSTALL_ROOT="${SPOCK_INSTALL_ROOT:-$SCRIPT_DIR}"
fi
INSTALL_ROOT="$(cd "$INSTALL_ROOT" && pwd)"
cd "$INSTALL_ROOT"

LOG_FILE="$INSTALL_ROOT/bootstrap.log"
mkdir -p "$INSTALL_ROOT/logs" "$INSTALL_ROOT/models" \
  "$INSTALL_ROOT/tools/llama-server" "$INSTALL_ROOT/tools/llmfit" "$INSTALL_ROOT/data"

log() {
  local level="${2:-INFO}"
  local line
  line="[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $1"
  echo "$line" | tee -a "$LOG_FILE" >/dev/null
  echo "$line"
}

find_python() {
  local c
  for c in python3.12 python3.11 python3.13 python3; do
    if command -v "$c" >/dev/null 2>&1; then
      local ver
      ver="$("$c" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
      local major minor
      major="${ver%%.*}"
      minor="${ver#*.}"
      if [[ "$major" -gt 3 ]] || { [[ "$major" -eq 3 ]] && [[ "$minor" -ge 10 ]]; }; then
        echo "$c"
        return 0
      fi
    fi
  done
  return 1
}

VENV_PY="$INSTALL_ROOT/.venv/bin/python"

phase_a() {
  log "Phase A — install root: $INSTALL_ROOT"
  local py
  if ! py="$(find_python)"; then
    if [[ "$(uname -s)" == "Darwin" ]]; then
      log "Python 3.10+ not found. On macOS: brew install python@3.12" ERROR
    else
      log "Python 3.10+ not found. On Ubuntu: sudo apt install -y python3 python3-venv python3-pip" ERROR
    fi
    exit 1
  fi
  log "Base Python: $py ($("$py" -c 'import sys; print(sys.version.split()[0])'))"

  if [[ -x "$VENV_PY" ]]; then
    if ! "$VENV_PY" -c 'print("ok")' >/dev/null 2>&1; then
      log "Existing .venv is broken; recreating" WARN
      rm -rf "$INSTALL_ROOT/.venv"
    else
      log "Using existing venv: $VENV_PY"
    fi
  fi
  if [[ ! -x "$VENV_PY" ]]; then
    log "Creating .venv"
    "$py" -m venv "$INSTALL_ROOT/.venv"
  fi

  log "Upgrading pip/wheel"
  "$VENV_PY" -m pip install -U pip wheel \
    --disable-pip-version-check --prefer-binary --no-input

  local req_ui="$INSTALL_ROOT/requirements-ui.txt"
  if [[ -f "$req_ui" ]]; then
    log "Installing $req_ui"
    "$VENV_PY" -m pip install -r "$req_ui" \
      --disable-pip-version-check --prefer-binary --no-input
  else
    log "requirements-ui.txt missing; installing wizard deps" WARN
    "$VENV_PY" -m pip install PyQt6 requests psutil huggingface_hub \
      --disable-pip-version-check --prefer-binary --no-input
  fi

  if [[ "$VALIDATE" -eq 1 ]]; then
    # PyQt6 6.11+: QtCore is a submodule, not an attribute of import PyQt6.
    log "Validating PyQt6 import"
    "$VENV_PY" -c 'from PyQt6.QtCore import PYQT_VERSION_STR; print("PyQt6 OK", PYQT_VERSION_STR)'
  fi
  log "PHASE_A_OK"
}

phase_b() {
  if [[ ! -x "$VENV_PY" ]]; then
    log "No .venv — run Phase A first (./bootstrap.sh)" ERROR
    exit 1
  fi
  log "Phase B — full deps at $INSTALL_ROOT"
  local req_full="$INSTALL_ROOT/requirements-full.txt"
  if [[ ! -f "$req_full" ]]; then
    log "Missing $req_full" ERROR
    exit 1
  fi
  "$VENV_PY" -m pip install -r "$req_full" \
    --disable-pip-version-check --prefer-binary --no-input

  if [[ "$VALIDATE" -eq 1 ]]; then
    log "Validating ingest imports"
    "$VENV_PY" -c 'import watchdog, pymupdf, PIL, bs4, lxml, docx, openpyxl, pandas; print("ingest OK")'
    if "$VENV_PY" -c 'from PyQt6.QtWebEngineWidgets import QWebEngineView' >/dev/null 2>&1; then
      log "PyQt6-WebEngine OK"
    else
      log "PyQt6-WebEngine import failed — Brave Search needs it. On Ubuntu/WSL also: sudo apt install -y libnspr4 libnss3" WARN
    fi
  fi
  printf 'ok\nsource=bootstrap.sh\n' >"$INSTALL_ROOT/bootstrap_full_deps.ok"
  log "PHASE_B_OK (wrote bootstrap_full_deps.ok)"
}

case "$PHASE" in
  a) phase_a ;;
  b) phase_b ;;
  *) log "Unknown phase: $PHASE" ERROR; exit 2 ;;
esac
