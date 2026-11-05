# Linux / Ubuntu setup — Spock-AI-Universal-Wiki

This is the bring-up path used on native Ubuntu (also applies to WSL2 Ubuntu with NVIDIA + WSLg). It covers Phase A/B, **llama-server**, **llmfit**, and step **3 Acquire**.

## What you need

| Requirement | Notes |
|-------------|--------|
| Ubuntu 22.04+ (tested on 26.04) | x86_64 |
| Python 3.10+ | `python3`, `python3-venv`, `python3-pip` |
| NVIDIA GPU + driver | `nvidia-smi` must list your GPUs |
| Display for GUI | Wayland/X11, or WSLg under WSL |
| Optional HF token | Gated GGUFs / anonymous rate limits |

Example host that completed this flow: dual **RTX 3060 12GB**, driver **595.x**, ~60 GB RAM.

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip curl git
# GUI / WebEngine extras (Phase B Brave Search / Qt WebEngine):
sudo apt install -y libnspr4 libnss3
nvidia-smi   # must succeed before CUDA llama-server is useful
```

## 1. Get the tree

```bash
cd ~/src   # or your preferred location (prefer a Linux filesystem, not /mnt/d/…)
git clone https://github.com/kimmlombard/Spock-AI-Universal-Wiki.git
cd Spock-AI-Universal-Wiki
chmod +x bootstrap.sh Spock-Menu.sh Spock-Menu-Console.sh spock_menu.sh
```

Portable tool dirs (created empty by Phase A):

```text
tools/llama-server/   → native llama-server (+ CUDA libs)
tools/llmfit/         → native llmfit CLI
models/               → GGUF weights (gitignored)
```

## 2. Phase A — Python / venv / PyQt6

Phase A installs `.venv` and UI deps (`requirements-ui.txt`).

```bash
./bootstrap.sh --phase-a
# equivalent from the console menu: option 1
./spock_menu.sh
```

Or open the PyQt bring-up GUI (it runs Phase A automatically if PyQt6 is missing):

```bash
./Spock-Menu.sh
```

Success marker: `.venv/bin/python` imports PyQt6.

```bash
.venv/bin/python -c 'from PyQt6.QtCore import PYQT_VERSION_STR; print(PYQT_VERSION_STR)'
```

## 3. Phase B — full deps

Phase B installs ingest / extractors / WebEngine (`requirements-full.txt`) and writes `bootstrap_full_deps.ok`.

```bash
./bootstrap.sh --phase-b
# or menu option 2
```

```bash
.venv/bin/python -c 'import watchdog, pymupdf, PIL, bs4, lxml, docx, openpyxl, pandas; print("ingest OK")'
```

## 4. Install llmfit (hardware fit shortlists)

Spock uses **llmfit** during Acquire / Launch to score models against VRAM and suggest `-ngl`. A **native Linux binary** is required — a Windows `llmfit.exe` on `/mnt/c/...` is ignored.

Preferred layout:

```text
tools/llmfit/llmfit
```

### Option A — copy / install a release binary

```bash
mkdir -p tools/llmfit
# Place the Linux llmfit binary here (from an llmfit release or your ~/.local/bin copy):
cp "$(command -v llmfit)" tools/llmfit/llmfit   # if already on PATH
chmod +x tools/llmfit/llmfit
tools/llmfit/llmfit --version
```

### Option B — leave on PATH / uvx

If `tools/llmfit/llmfit` is missing, Spock also accepts:

- `~/.local/bin/llmfit` or anything on `PATH`
- `uvx llmfit` when [`uv`](https://github.com/astral-sh/uv) is installed
- overrides: `SPOCK_LLMFIT_EXE` / `LLMFIT_EXE`

```bash
# optional: skip llmfit and use catalog / host-recipe only
export SPOCK_LLMFIT=0
```

Verify Spock can see it:

```bash
.venv/bin/python -c 'from spock_onboarding import llmfit_bridge as b; print(b.find_llmfit_exe(), b.available())'
```

## 5. Install llama-server (CUDA build)

Spock expects the Linux binary at:

```text
tools/llama-server/llama-server
```

plus the matching shared libraries (`libggml*.so`, `libcudart.so.12`, …) in the **same directory**.

### Option A — automatic (recommended): step 3 Acquire

After the Linux download support in `spock_onboarding/runtime.py`, Acquire fetches the latest **Ubuntu CUDA** release assets from [llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases):

- `llama-*-bin-ubuntu-cuda-12.8-x64.tar.gz` (falls back through 12.4 / 12 / Vulkan / CPU)
- matching `cudart-llama-*-bin-ubuntu-cuda-*.tar.gz`

Archives are flattened into `tools/llama-server/` and `SPOCK_LLAMA_PATH.txt` is written.

```bash
# GUI: Spock-Menu.sh → 3 Acquire
# or console:
./spock_menu.sh          # option 3
# or headless:
.venv/bin/python -m spock_bringup acquire
```

### Option B — manual extract (what we did when tarballs were already downloaded)

```bash
DEST=tools/llama-server
mkdir -p "$DEST/_download"
# Download from the latest llama.cpp GitHub release, e.g.:
#   llama-bNNNN-bin-ubuntu-cuda-12.8-x64.tar.gz
#   cudart-llama-bNNNN-bin-ubuntu-cuda-12.8-x64.tar.gz
# into $DEST/_download/

tar -xzf "$DEST/_download"/llama-*-bin-ubuntu-cuda-*.tar.gz -C "$DEST" --strip-components=1
tar -xzf "$DEST/_download"/cudart-llama-*-bin-ubuntu-cuda-*.tar.gz -C "$DEST" --strip-components=1
chmod +x "$DEST/llama-server"
printf '%s\n' "$(pwd)/$DEST/llama-server" > "$DEST/SPOCK_LLAMA_PATH.txt"
rm -rf "$DEST/_download"   # optional; frees ~0.7 GB
```

Do **not** drop a Windows `llama-server.exe` here and expect it to run under Linux.

### Smoke-test llama-server

```bash
tools/llama-server/llama-server --version
tools/llama-server/llama-server --list-devices
# Expect CUDA0 / CUDA1 (etc.) — not "(none)"
```

Overrides:

```bash
export LLAMA_SERVER_PATH=/path/to/llama-server   # file or directory
```

Probe what Spock will resolve:

```bash
.venv/bin/python scripts/wsl_probe_bringup_paths.py
```

## 6. Step 3 — Acquire runtime + models

Acquire does three things:

1. Resolve **llmfit** (optional but recommended)
2. Ensure **llama-server** under `tools/llama-server/`
3. Pick / download embed + chat **GGUFs** into `models/`, write `first_models_last.json`

```bash
# Interactive shortlist (GUI Acquire dialog) or:
.venv/bin/python -m spock_bringup acquire

# Reuse models already on disk (example from this host):
.venv/bin/python -m spock_bringup acquire \
  --embed-repo ggml-org/embeddinggemma-2-GGUF \
  --chat-repo google/gemma-4-E4B-it-qat-q4_0-gguf \
  --embed-quant Q8_0 \
  --chat-quant Q4_0 \
  --embed-n-ctx 4096 \
  --chat-n-ctx 8192

# Ensure llama only; skip Hub downloads:
.venv/bin/python -m spock_bringup acquire --no-download-models
```

Hugging Face token (for gated repos / higher rate limits):

```bash
# either:
echo 'hf_…' > .HF_TOKEN
# or:
export HF_TOKEN=hf_…
```

Success looks like:

```json
{ "ok": true, "reasons": [], "summary_path": "…/first_models_last.json" }
```

`llama_server_path` in that file should point at `…/tools/llama-server/llama-server`.

## 7. Next steps after Acquire

| Step | Command / menu |
|------|----------------|
| Bring up embed `:8080` + chat `:8081` | menu **4** / `python -m spock_bringup up` |
| Status / readiness JSON | menu **5** / `python -m spock_bringup status` |
| MCP adapter | menu **6** |
| Full GUI station | `./Spock-Menu.sh` |

```bash
.venv/bin/python -m spock_bringup up
.venv/bin/python -m spock_bringup status
```

## Dual-boot / copy: Spock_Console path healing

When you copy the Spock tree (and `ship_computer.db`) between Ubuntu and Windows,
absolute paths in `Spock_Console` (`app.*.path`, `scan.scan_roots`, UIEG folders,
`onboarding.first_models`, …) used to stay on the old OS. On first suite /
wiki-agent / extractor load, Spock now remaps Spock-rooted paths to the current
install root and stamps `settings.spock_root` + `settings.host_os`. External
tools (e.g. `cloudflared` under Program Files) are left alone. Host-recipe GPU
drift is still handled separately in Maintenance → Recipe.

## Failure notes from this Ubuntu bring-up

1. **Phase A/B OK, Acquire fails with `NEED_LLAMA_SERVER`**  
   Older trees only auto-downloaded Windows zips. Linux now downloads Ubuntu CUDA tarballs; or extract manually as in §5 Option B. Leaving archives under `tools/llama-server/_download/` without extracting is **not** enough — Spock needs the flattened `llama-server` binary.

2. **`nvidia-smi` works but `--list-devices` shows `(none)`**  
   Usually a sandbox / missing `/dev/nvidia*` access, or a CPU-only build. Use the **ubuntu-cuda** release, not a CPU tarball, and run outside restricted environments.

3. **llmfit “available” but no shortlist quality**  
   Confirm a **Linux** ELF at `tools/llmfit/llmfit` (not a source clone only, not a `.exe`). `llmfit --version` should print something like `1.1.x`.

4. **Acquire `NEED_MODELS` / HF errors**  
   Set `HF_TOKEN` / `.HF_TOKEN`, or pass `--embed-repo` / `--chat-repo` that already exist under `models/<repo-name>/*.gguf`.

## Quick checklist

- [ ] `nvidia-smi` lists GPUs  
- [ ] `./bootstrap.sh --phase-a` → PyQt6 OK  
- [ ] `./bootstrap.sh --phase-b` → `bootstrap_full_deps.ok`  
- [ ] `tools/llmfit/llmfit --version`  
- [ ] `tools/llama-server/llama-server --list-devices` shows CUDA  
- [ ] `python -m spock_bringup acquire` → `ok: true`  
- [ ] `python -m spock_bringup up` → `:8080` + `:8081` healthy  

See also: [`tools/README.md`](tools/README.md), [`bootstrap.sh`](bootstrap.sh), [`spock_menu.sh`](spock_menu.sh).
