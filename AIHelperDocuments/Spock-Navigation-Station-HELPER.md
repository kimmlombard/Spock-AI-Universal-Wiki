# Spock-Navigation-Station

Standalone Navigation Station for **Spock-Onboarding**.

Use the left **Navigation** pane to move through bring-up and day-to-day ops.
Use the right **Tools** pane for modal helpers (AI Helper, Ship Status, About, Brave Search, Theme).

## Left navigation

| Step | Purpose |
|------|---------|
| **Home** | This overview |
| **1 Hardware** | Review the launch hardware probe; re-scan on demand |
| **2 HF Models** | Browse / download GGUFs from Hugging Face |
| **3 Launch** | Start llama-server (embed + chat) |
| **4 Configure Spock AI** | LLM connectors, Embedding / RAG, MCP, WebUI |
| **5 Spock Status** | Probe RAG / llama / MCP health |
| **6 Run Wiki Scan** | Start `wiki_agent.py` (bootstrap + watcher + queue) |
| **7 Ship's Logs** | Browse captains_log / DB tables |
| **8 Run Ask AI** | In-app Ask / Deep Dive over `ship_computer.db` |
| **Exit** | Close Navigation Station |

## Launch flags — what persists, and where

The Launch row splits into flags that travel with you and flags that describe the machine, because a layer count means the same thing everywhere while a tensor-split names cards a different box may not have.

- **SAVE DEFAULTS** stores **GPU Layers** and **embed -np** as `app.launch.ngl` / `app.launch.embed_np` in `Spock_Console`. They are re-applied on every launch, on any machine, and reach `app_config.json` through the settings export (`Maintenance → Settings`), not by editing the file — the root `app_config.json` was retired in favour of the table.
- **SAVE TO RECIPE** stores **GPU policy**, **tensor-split**, **split-mode** and **Context (-c)** as a new host recipe version, with the reason recorded in `Maintenance → Recipe` history. The `-c` you save lands in the slot for the role of the current selection (`embed_n_ctx` or `chat_n_ctx`).
- **USE ACQUIRE RESULT** (Configure → Embedding / RAG, or Bringup step 7) copies the Acquire GGUF into the embedding profile **and** writes Acquire's embed/chat `-c` onto the host recipe, capped to what this machine's hardware proposes. If `ship_computer.db` still carries another machine's recipe, that click also saves the live dual-GPU (or single-GPU) proposal so Launch stops pinning both roles to CUDA 0. A running llama-server keeps its old flags — re-launch embed (:8080) and chat (:8081) after adopting.
- `-ngl -1` means "ask llmfit at launch for a VRAM-safe count", which is the default. Any number pins it and skips that check, so `99` offloads every layer whether or not it fits. The launch log distinguishes them: `-ngl 99 (pinned in app.launch.ngl)` versus llmfit's own reason.
- Pins apply to all three launch paths — the panel, a profile restore, and step 4/5 of the Bringup Menu — so a pinned value is not something only the GUI honours.
- After a machine move, the pinned `-ngl` still applies (it is a cap, not a topology) while the drifted recipe's tensor-split and GPU indexes do not; SAVE TO RECIPE then asks before saving a version for the live host, and never carries the old machine's GPU indexes forward.

## Hardware probe — once per session

The station probes hardware once, right after the window opens, and every panel reads that result from the shared `ModelSelectorState`. A probe is three `nvidia-smi` spawns plus an NVML pass, so visiting **1 Hardware** or **2 HF Models** no longer re-runs it; the panel header shows when the cached probe ran (`STATUS: SCAN COMPLETE (probed 08:31:02)`).

- **SCAN HARDWARE** on 1 Hardware is the only re-probe, and it refuses to start a second scan while one is running.
- The same probe calls `host_recipe.ensure_recipe`: it creates version 1 if the machine has no recipe, and otherwise reports drift for **Engineering Maintenance → Recipe** to apply. An existing recipe is never rewritten automatically.
- Drift means `ship_computer.db` came from another machine. Model sizing and Launch defaults then follow this probe instead of the recipe's stored snapshot (`host_recipe.effective_recipe`), and the Launch recipe line says so until the recipe is saved for this host.
- If the probe fails, 2 HF Models says so and keeps the Hub query buttons disabled instead of rescanning on each visit.
- llmfit's own `--json system` fingerprint (used to attach tok/s and fit badges to Hub rows) is cached for the session too, so repeated Hub queries no longer re-shell out to it.

## Path filter — several repos at once

The **Path** box on 8 Run Ask AI and 7 Ship's Logs accepts semicolon-separated roots. `Spock-Universal-AI-Wiki; LLMFIT` retrieves from both `D:\Spock-Universal-AI-Wiki` and `C:\DEV\llmfit`: each piece becomes its own `path LIKE` group, the groups are OR'd, and include/exclude extensions still apply to the whole set. A piece that looks absolute (`D:\…`, `\\host\share`, `/srv`) anchors to that subtree; anything else is a substring match.

Opening **8 Run Ask AI** after Ship's Logs has a non-empty Path that matches documents may offer to **copy that Path into Ask AI**. Keep a llama.cpp-only Path when you want upstream-only answers; clear Path (or add Spock) when asking how *this app* tunes context.

## Ask AI / Deep Dive — good results (less trial-and-error)

1. Launch chat with **Suggest Context** so `-c` fits the GPU; heed **Fit warning** if the GGUF is too large (CPU spill → timeouts).
2. Use **Deep Dive** for architecture; watch the footer `used N · X% of budget` — near 100% means raise `-c` or narrow Path.
3. Follow italic **Tip:** lines under answers (pack saturation, Path vs Spock question, timeout cause).
4. Details: `AIHelperDocuments/How does Ask AI and Deep Dive work in Spock  How can I tune the context size.md`.

## Right tools

- **AI Helper** — chat helper modal
- **Ship Status** — live llama / MCP / RAG monitor
- **About** — ports, tools, MCP map
- **Brave Search** — optional web search (needs API key)
- **Theme** — color scheme for the shell

## Prerequisites

1. Phase A venv + deps (`spock_menu.ps1` → 1)
2. Acquire runtime + models (menu → 3) if needed
3. Bring up servers on `:8080` embed + `:8081` chat (menu → 4) before Wiki Scan / Ask AI

## Launch

```text
Spock-Navigation.bat
```

or from the onboarding menu:

```text
12) Spock Navigation Station
```
