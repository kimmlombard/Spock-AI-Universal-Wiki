# Apple Silicon (macOS) setup — Spock-AI-Universal-Wiki

This is the bring-up path for **macOS on Apple Silicon** (M1 / M2 / M3 / M4 …). It covers Phase A/B, **Metal llama-server**, **llmfit**, and step **3 Acquire**.

Peer docs: [`Linux-Ubuntu-Setup-README.md`](Linux-Ubuntu-Setup-README.md) (CUDA) · [`tools/README.md`](tools/README.md).

## What you need

| Requirement | Notes |
|-------------|--------|
| macOS on Apple Silicon | `uname -m` → `arm64` |
| Python 3.10+ | Homebrew `python@3.12` preferred; system / brew `python3` also works |
| Metal GPU | Built into Apple Silicon (no NVIDIA / CUDA) |
| Display for GUI | Native Cocoa — no `DISPLAY` / X11 / WSLg |
| Optional HF token | Gated GGUFs / anonymous rate limits |

Example host that completed this flow: **Apple M4**, Metal OK, ~12 GiB unified memory reported to llama.cpp, macOS 26.x.

```bash
# Optional but recommended (needs a writable Homebrew prefix)
brew install python@3.12
python3.12 --version

# Confirm Metal is available
system_profiler SPDisplaysDataType | grep -E 'Chipset|Metal'
```

If `brew install` fails with **Cellar is not writable**, fix ownership once:

```bash
sudo chown -R "$(whoami)" /opt/homebrew/Cellar /opt/homebrew/var/homebrew
```

Or skip brew Python and use whatever `python3` is already on `PATH` (3.10+). Phase A creates a project-local `.venv`.

## 1. Get the tree

```bash
cd ~/Developer   # or your preferred location
git clone https://github.com/kimmlombard/Spock-AI-Universal-Wiki.git
cd Spock-AI-Universal-Wiki
chmod +x bootstrap.sh Spock-Menu.sh Spock-Menu-Console.sh spock_menu.sh
```

Portable tool dirs (created empty by Phase A):

```text
tools/llama-server/   → native Metal llama-server (+ dylibs / soname symlinks)
tools/llmfit/         → native llmfit CLI (aarch64-apple-darwin)
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

Qt uses the **cocoa** platform plugin on macOS — you do **not** need `DISPLAY` or WSLg.

## 3. Phase B — full deps

Phase B installs ingest / extractors / WebEngine (`requirements-full.txt`) and writes `bootstrap_full_deps.ok`.

```bash
./bootstrap.sh --phase-b
# or menu option 2
```

```bash
.venv/bin/python -c 'import watchdog, pymupdf, PIL, bs4, lxml, docx, openpyxl, pandas; print("ingest OK")'
.venv/bin/python -c 'from PyQt6.QtWebEngineWidgets import QWebEngineView; print("WebEngine OK")'
```

## 4. Install llmfit (hardware fit shortlists)

Spock uses **llmfit** during Acquire / Launch to score models against available memory and suggest `-ngl`. A **native macOS binary** is required — a Windows `llmfit.exe` is ignored.

Preferred layout:

```text
tools/llmfit/llmfit
```

### Option A — Homebrew

```bash
brew install llmfit
# or tap formula:
# brew install AlexsJones/llmfit/llmfit

mkdir -p tools/llmfit
cp "$(command -v llmfit)" tools/llmfit/llmfit
chmod +x tools/llmfit/llmfit
tools/llmfit/llmfit --version
```

### Option B — GitHub release into `tools/llmfit`

```bash
mkdir -p tools/llmfit
TAG=$(curl -fsSI https://github.com/AlexsJones/llmfit/releases/latest \
  | awk 'tolower($1)=="location:"{print $2}' | tr -d '\r' | sed 's|.*/tag/||')
curl -fsSL \
  "https://github.com/AlexsJones/llmfit/releases/download/${TAG}/llmfit-${TAG}-aarch64-apple-darwin.tar.gz" \
  -o /tmp/llmfit-mac.tar.gz
tar -xzf /tmp/llmfit-mac.tar.gz -C /tmp
cp /tmp/llmfit-*/llmfit tools/llmfit/llmfit
chmod +x tools/llmfit/llmfit
tools/llmfit/llmfit --version
```

### Option C — leave on PATH / uvx

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

## 5. Install llama-server (Metal build)

Spock expects the macOS binary at:

```text
tools/llama-server/llama-server
```

plus the matching **dylibs and soname symlinks** (`libllama-common.0.dylib` → `libllama-common.0.9.0.dylib`, `libggml-metal.*`, …) in the **same directory**.

### Option A — automatic (recommended): step 3 Acquire

Acquire fetches the latest **macOS Apple Silicon** release asset from [llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases):

- `llama-*-bin-macos-arm64.tar.gz` (Intel Macs: `…-bin-macos-x64…`)

Archives are flattened into `tools/llama-server/` (symlinks preserved) and `SPOCK_LLAMA_PATH.txt` is written.

```bash
# GUI: Spock-Menu.sh → 3 Acquire
# or console:
./spock_menu.sh          # option 3
# or headless:
.venv/bin/python -m spock_bringup acquire
```

### Option B — manual extract

```bash
DEST=tools/llama-server
mkdir -p "$DEST/_download"
# Download from the latest llama.cpp GitHub release, e.g.:
#   llama-bNNNN-bin-macos-arm64.tar.gz
# into $DEST/_download/

# Prefer Spock's extractor (keeps dylib symlinks):
.venv/bin/python -c '
from pathlib import Path
from spock_onboarding.runtime import download_llama_server_macos
print(download_llama_server_macos(Path("."), cb=print))
'

# Or extract yourself — do NOT drop a Windows .exe or Ubuntu CUDA tarball here:
# tar -xzf "$DEST/_download"/llama-*-bin-macos-arm64.tar.gz -C "$DEST" --strip-components=1
# chmod +x "$DEST/llama-server"
# printf '%s\n' "$(pwd)/$DEST/llama-server" > "$DEST/SPOCK_LLAMA_PATH.txt"
```

Do **not** use `llama-*-bin-ubuntu-cuda-*` or `llama-*-bin-win-cuda-*` on macOS.

### Smoke-test llama-server

```bash
tools/llama-server/llama-server --version
tools/llama-server/llama-server --list-devices
# Expect MTL0: Apple M… — not "(none)" / CUDA-only empty
```

Example healthy output:

```text
Available devices:
  MTL0: Apple M4 (12124 MiB, … free)
  BLAS: Accelerate (0 MiB, 0 MiB free)
```

Overrides:

```bash
export LLAMA_SERVER_PATH=/path/to/llama-server   # file or directory
```

Probe what Spock will resolve:

```bash
.venv/bin/python -c '
from pathlib import Path
from spock_onboarding.runtime import detect_llama_server
print(detect_llama_server(Path(".")))
'
```

## 6. Step 3 — Acquire runtime + models

Acquire does three things:

1. Resolve **llmfit** (optional but recommended)
2. Ensure **llama-server** under `tools/llama-server/`
3. Pick / download embed + chat **GGUFs** into `models/`, write `first_models_last.json`

```bash
# Interactive shortlist (GUI Acquire dialog) or:
.venv/bin/python -m spock_bringup acquire

# Reuse models already on disk:
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
| Full GUI station | `./Spock-Menu.sh` / Navigation Station |

```bash
.venv/bin/python -m spock_bringup up
.venv/bin/python -m spock_bringup status
```

## Dual-boot / copy: path healing

When you copy the Spock tree (and `ship_computer.db`) between macOS, Ubuntu, and Windows, absolute paths in `Spock_Console` used to stay on the old OS. On first suite / wiki-agent / extractor load, Spock remaps Spock-rooted paths to the current install root and stamps `settings.spock_root` + `settings.host_os`. Host-recipe GPU drift (CUDA ↔ Metal) is still handled separately in Maintenance → Recipe.

## Failure notes from Apple Silicon bring-up

1. **Phase A/B OK, Acquire fails with `NEED_LLAMA_SERVER`**  
   Older trees only auto-downloaded Windows / Ubuntu CUDA packages. Current trees download `bin-macos-arm64` (or `macos-x64`). Leaving archives under `tools/llama-server/_download/` without extracting is **not** enough.

2. **`dyld: Library not loaded: @rpath/libllama-common.0.dylib`**  
   The release tarball relies on **soname symlinks**. A flat copy that skips symlinks breaks the binary. Re-run Acquire / `download_llama_server_macos`, or extract with a tool that preserves links (`tar -xzf …`).

3. **`--list-devices` shows no `MTL0`**  
   Wrong binary (Linux/Windows build), quarantine / Gatekeeper blocking dylibs, or a CPU-only custom build. Use the official `bin-macos-arm64` asset and run outside restricted sandboxes.

4. **Homebrew cannot install Python / llmfit**  
   Prefix owned by another user (`Cellar is not writable`). Fix with `chown` (see above), or install llmfit from the GitHub `aarch64-apple-darwin` tarball into `tools/llmfit/` and use any existing `python3` ≥ 3.10 for Phase A.

5. **Acquire `NEED_MODELS` / HF errors**  
   Set `HF_TOKEN` / `.HF_TOKEN`, or pass `--embed-repo` / `--chat-repo` that already exist under `models/<repo-name>/*.gguf`.

6. **Unified memory sizing**  
   Apple Silicon shares RAM between CPU and GPU. llmfit / llama.cpp report a Metal pool (often most of system RAM); leave headroom for macOS and the Spock GUI when picking GGUF quants / `-ngl`.

## Quick checklist

- [ ] `uname -m` → `arm64`  
- [ ] `./bootstrap.sh --phase-a` → PyQt6 OK  
- [ ] `./bootstrap.sh --phase-b` → `bootstrap_full_deps.ok`  
- [ ] `tools/llmfit/llmfit --version`  
- [ ] `tools/llama-server/llama-server --list-devices` shows **MTL0**  
- [ ] `python -m spock_bringup acquire` → `ok: true`  
- [ ] `python -m spock_bringup up` → `:8080` + `:8081` healthy  

See also: [`tools/README.md`](tools/README.md), [`bootstrap.sh`](bootstrap.sh), [`spock_menu.sh`](spock_menu.sh), [`Spock-Menu.sh`](Spock-Menu.sh).
