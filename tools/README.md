# Spock portable tool installs

Keep third-party binaries under this tree so Windows and WSL share the same
relative layout (no fixed `C:\` / `D:\` defaults).

| Tool | Directory | Binary |
|------|-----------|--------|
| llama.cpp | `tools/llama-server/` | `llama-server.exe` (Windows) or `llama-server` (Linux/WSL) |
| llmfit | `tools/llmfit/` | Built CLI: `llmfit` / `llmfit.exe`, or `target/release/llmfit` after `cargo build --release` |

**Acquire (step 3)** installs llama-server automatically when missing:

- Windows — latest `llama-*-bin-win-cuda-*.zip` (+ matching `cudart`) from [llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases)
- Linux / WSL — latest `llama-*-bin-ubuntu-cuda-*.tar.gz` (+ matching `cudart`), flattened into `tools/llama-server/`

Cloning the llmfit **source** into `tools/llmfit` is not enough — Spock needs a
native binary. Under WSL, Windows `*.exe` on PATH (`/mnt/c/...`) is ignored.

Overrides (optional):

- `LLAMA_SERVER_PATH` — file or directory for llama-server
- `SPOCK_LLMFIT_EXE` / `LLMFIT_EXE` — path to the llmfit CLI
- `SPOCK_LLMFIT=0` — skip llmfit entirely (catalog / host-recipe `-ngl` only)

`bootstrap.sh` / Phase A creates these directories empty; Acquire (or a manual
drop of the native binary) fills them.
