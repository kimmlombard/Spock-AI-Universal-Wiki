#!/usr/bin/env bash
set -euo pipefail
SRC=/mnt/d/Spock-AI-Universal-Wiki
DST=$HOME/src/Spock-AI-Universal-Wiki
for f in \
  WarpCore/service_endpoints.py \
  spock_shell/llmfit_bridge.py \
  spock_onboarding/llmfit_bridge.py \
  spock_onboarding/runtime.py \
  spock_bringup/__init__.py \
  tools/README.md \
  scripts/wsl_heal_first_models.py \
  scripts/wsl_probe_bringup_paths.py \
  scripts/sync_windows_to_wsl.sh
do
  sed -i 's/\r$//' "$SRC/$f" 2>/dev/null || true
  mkdir -p "$DST/$(dirname "$f")"
  cp -f "$SRC/$f" "$DST/$f"
done
cd "$DST"
.venv/bin/python scripts/wsl_heal_first_models.py
.venv/bin/python scripts/wsl_probe_bringup_paths.py
echo "--- resolve_ngl without windows llmfit ---"
.venv/bin/python - <<'PY'
from spock_onboarding import llmfit_bridge
print("available", llmfit_bridge.available())
print("exe", llmfit_bridge.find_llmfit_exe())
print("uvx", llmfit_bridge.find_uvx())
print(llmfit_bridge.resolve_ngl("/tmp/x.gguf", n_ctx=4096))
PY
