#!/usr/bin/env bash
set -uo pipefail
file ~/src/Spock-AI-Universal-Wiki/tools/llama-server/llama-server
file /mnt/e/Spock/llama/llama-b11936/llama-server
ls /mnt/d/Spock-AI-Universal-Wiki/models | head
ls ~/src/Spock-AI-Universal-Wiki/models | head
command -v llmfit; command -v llmfit.exe; command -v uvx; command -v uvx.exe
python3 - <<'PY'
import os
print("PATH mnt/c entries:", sum(1 for p in os.environ.get("PATH","").split(":") if p.startswith("/mnt/c")))
PY
