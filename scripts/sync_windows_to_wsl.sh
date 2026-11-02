#!/usr/bin/env bash
# Sync D:\Spock-AI-Universal-Wiki → ~/src/Spock-AI-Universal-Wiki (keep WSL venv/DB/models).
set -euo pipefail

SRC="${SPOCK_WIN_SRC:-/mnt/d/Spock-AI-Universal-Wiki}"
DST="${SPOCK_WSL_DST:-$HOME/src/Spock-AI-Universal-Wiki}"

if [[ ! -d "$SRC" ]]; then
  echo "Missing Windows mount source: $SRC" >&2
  exit 1
fi
mkdir -p "$DST"

rsync -a \
  --exclude ".venv" \
  --exclude ".venv/**" \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  --exclude ".pytest_cache/" \
  --exclude "ship_computer.db*" \
  --exclude "uieg_capture.db*" \
  --exclude ".env" \
  --exclude "models/" \
  --exclude "data/" \
  --exclude "logs/" \
  --exclude "captured_files/" \
  --exclude ".git/" \
  --exclude "*.gguf" \
  --exclude "first_models_last.json" \
  --exclude "spock_ready_last.json" \
  --exclude "tools/llama-server/*.exe" \
  --exclude "tools/llama-server/*.dll" \
  --exclude "tools/llama-server/*.zip" \
  "$SRC/" "$DST/"

chmod +x \
  "$DST/Spock-Menu.sh" \
  "$DST/Spock-Menu-Console.sh" \
  "$DST/spock_menu.sh" \
  "$DST/bootstrap.sh" \
  "$DST/scripts/sync_windows_to_wsl.sh" 2>/dev/null || true

echo "Synced $SRC → $DST"
ls -la "$DST/Spock-Menu.sh" "$DST/Spock-Menu-Console.sh" "$DST/spock_bringup_menu/steps.py"
