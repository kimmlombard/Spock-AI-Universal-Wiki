# Spock Bringup Menu

Novice-friendly PyQt6 console for Spock-Onboarding steps **1–16**.

## Launch

```text
Spock-Menu.bat
```

- If `.venv` + PyQt6 are ready → opens this GUI.
- Otherwise runs Phase A (`bootstrap.ps1`), then opens the GUI.

Console fallback (power users):

```text
Spock-Menu-Console.bat
```

## Layout

| Pane | Role |
|------|------|
| **Left** | Steps 1–16 |
| **Center** | Checklist + live progress / launch log (or Ask AI panel) |
| **Right Tools** | **Profiles** (Save / Load / Manage), AI Helper (after step 4), Ship Status, About, Theme |

Spock Status has no left-nav step — the same report is in **Right Tools → Ship Status**.

## Steps

1. Phase A — Python / venv / PyQt6 deps (UI tier only: `requirements-ui.txt`)  
2. Phase B — full deps (`requirements-full.txt`: ingest, extractors, WebEngine, MCP) — **required** before step 9 Wiki Scan. Safe to run from the menu; if Windows reports `WinError 32` / `WinError 5` on a `site-packages` file, close other Spock windows and re-run (pip retries automatically). PyQt6 is capped `<6.12` so it stays aligned with `PyQt6-WebEngine` (a 6.12/6.11 skew shows up as Brave Search “DLL load failed … QtWebEngineWidgets”). 
3. Acquire runtime + models — opens a fit shortlist first (see **Step 3 model selection**)  
4. Bring up servers (`:8080` embed + `:8081` chat) — unlocks **AI Helper**  
5. Status / probe → `spock_ready_last.json`  
6. MCP Adapter  
7. Embedding Profile / RAG API — **Model path** / **Model id** pre-fill from step 3 Acquire (`first_models_last.json`); **USE ACQUIRE RESULT** adopts that pick **and** writes Acquire's embed/chat `-c` onto the host recipe (capped to what this machine can hold), then **APPLY / SAVE** persists the GGUF path. Re-launch both llama-servers afterward — a running server keeps its old `-c` / GPU pin. 
8. Open Live Monitor  
9. Run Wiki Scan — includes **Embedding Health** (`test_embeddings.py`: coverage, dimensions, vector/FTS5 search, corpus vs live `:8080`)  
10. **Ask AI / Deep Dive** — in-app panel (same as Navigation Station → 8 Run Ask AI)  
11. Spock Navigation Station  
12. Spock Engineering Maintenance  
13. Spock UIEG KnowledgeBase  
14. Stop servers / kill suite children started from this menu  
15. **Re-embed / switch embedding model** — asks **Skip** or **Re-embed**, then a second warning that prior embeddings will be lost; clears document vectors + `kb_embedding_corpus` only (keeps docs/settings); then use step 4 + 9  
16. Exit  

CLI steps (1–5, 14–15) stream into the center log. Step 10 opens Ask AI in the center pane. Suite apps (6–9, 11–13) open in separate windows.

### Dependency tiers

Phase A installs only what the menu itself needs (~280 MB) so the GUI opens fast; Phase B installs the rest (~990 MB total).

| Tier | File | Installed by |
|------|------|--------------|
| UI | `requirements-ui.txt` | Step 1 Phase A |
| Full (ingest / extractors / WebEngine / MCP) | `requirements-full.txt` | Step 2 Phase B |
| OCR | `requirements-ocr.txt` | Opt-in — also needs `winget install UB-Mannheim.TesseractOCR` |
| Dev | `requirements-dev.txt` | Opt-in (`pytest`) |
| Docs | `requirements-docs.txt` | Opt-in (system Python 3.12 mkdocs toolchain) |

Steps 3–5 run on the UI tier alone. Step 9 Wiki Scan and the UIEG crawler check for their packages first and tell you to run step 2 if they are missing. Ask AI renders plain text instead of HTML until Phase B installs `PyQt6-WebEngine`. Without the OCR tier, scans skip text inside images and note it once in the log.

### Step 3 model selection (fit shortlist)

Step 3 no longer downloads a fixed pair off a VRAM ladder. It reads the **host recipe** — creating one from a live probe if the machine has none, and planning from the live probe when the saved recipe belongs to other hardware — then offers the three best-fitting GGUF repos per role: one radio group for the embedding model (`:8080`), one for chat (`:8081`).

- **Budget** per role comes from the recipe, not raw VRAM: `pin_per_role` gives each role its own card, `tensor_split_chat` pools cards for chat, and a shared card reserves room for the embedding model before sizing chat. `-c` comes from `embed_n_ctx` / `chat_n_ctx`.
- **Fit** uses llmfit's vocabulary — *perfect*, *good*, *tight*. When the llmfit CLI is installed its verdict and tok/s estimate win; otherwise Spock computes the same labels locally from weights + KV cache (`model_pick_policy.local_fit_level`), so the shortlist works offline. Models that cannot fit are dropped, and the hover text names the source of each verdict.
- **Candidates** come from Hugging Face (the searches "2 HF Models" uses) and fall back to the built-in catalog when the Hub is unreachable. Re-uploads of one model collapse to a single row, so three options mean three real choices; among equal fits, chat prefers the larger model and embedding prefers the better-scored one.
- Picking an embedding model whose dimension differs from vectors already in `ship_computer.db` is flagged — that switch needs step 15 Re-embed.

Selections are passed to the CLI, so the run is reproducible:

```text
python -m spock_bringup acquire --embed-repo Qwen/Qwen3-Embedding-4B-GGUF --embed-quant Q8_0 \
  --embed-n-ctx 4096 --chat-repo Qwen/Qwen3-14B-GGUF --chat-quant Q4_K_M --chat-n-ctx 16384
```

Omit the repo flags and headless Acquire matches the recipe itself (`pick_from_recipe`), falling back to the static catalog only when no recipe can be read.

### Configuration profiles (`spock_profile` in `ship_computer.db`)

Same store Navigation Station uses on start/stop:

- On launch: optional **Load from a previous configuration profile?**
- On exit: offer save only when no profiles exist yet (first launch); later saves happen from Navigation Station exit or Profiles → Save
- Right Tools → **Profiles**: Save / Load / Manage at any time
- Profiles record embed GGUF (`:8080`) and chat GGUF (`:8081`) from live llama-server or `spock_ready_last.json`
- Save/load compares the embedding model to the last Wiki Scan (`kb_embedding_corpus`) and warns on mismatch

### Host recipe (`spock_host_recipe`)

Machine Launch defaults (GPU policy, tensor-split, `-c`, embed `-np`), separate from session profiles:

- On Bringup start: if none exists → offer **Create host recipe** from a live probe
- Navigation Launch reads the current recipe for defaults / chat `--tensor-split`
- Step 3 Acquire and Navigation Station's launch probe both call `host_recipe.ensure_recipe`, which creates version 1 when none exists and otherwise reports drift without rewriting anything — an existing recipe still changes only through Maintenance or the prompts below, always with a reason

### Moving ship_computer.db to another machine

A recipe stores the hardware snapshot it was created from, so a database copied to a second box carries the first box's GPUs and RAM. Nothing plans from that snapshot: `host_recipe.effective_recipe` always measures against a live probe (cached per session), and when the two disagree it plans from a proposal derived from the live hardware — a `single_gpu` policy cannot describe two cards, and a `-c` sized for 22 GB will not load on 12 GB.

- **Bringup start** names the drift and offers to save a new recipe version for this host. Declining is fine; selection and Launch still follow the live probe, they just say the saved recipe is for other hardware.
- **Step 3 Acquire** sizes the shortlist to the live probe and shows the saved-vs-live policy. Its checkbox saves the new version so Launch inherits it.
- **Launch** falls back to the live proposal and labels the recipe line accordingly; `spock_shell.profiles` does the same when it fills `--tensor-split` / GPU pinning for llama-server.
- Saving always appends a version with the drift in the reason — the previous machine's recipe stays in **Maintenance → Recipe** history.

### Ask AI / Deep Dive context (`app.ctx.*`)

Tunable packing knobs live in **Spock_Console** only (not JSON). Edit via Engineering Maintenance → **Settings** → **Ctx - Context**. Run history is under the **Timing** tab (`ask_timing_history`, wiped by content reset). Set `app.ctx.stream_response` to `true` for opt-in token streaming (LLM phase only; retrieve/pack still finish first).

`app.ctx.ask_top_k` (default 20, clamped 1–50) sets how many snippets plain Ask AI retrieves; Deep Dive uses `deep_top_k` instead. Ask trims the packed snippets to what the live chat window can hold, so raising the knob cannot overflow the prompt.

Both modes answer strictly from what they retrieve — Ask sends `ASK_SYSTEM_PROMPT` from `llm_client.py`, which forbids outside knowledge even when a scanned project shares a name with a public package. When the snippets are too thin, the answer says so and closes with a `Next step:` line recommending Deep Dive, since Deep Dive packs whole files. Pair either mode with the repo root as the path filter and extension include/exclude to steer retrieval.

The **Path** filter takes several roots separated by `;` — `Spock-Universal-AI-Wiki; LLMFIT` researches both repos in one question. Absolute pieces anchor to their subtree, bare names match anywhere in the path.

### Switching embedding models

Prefer **step 15** (or Maintenance → Database → **Clear Embeddings**) over a full DB content reset. Then launch the new GGUF on `:8080` and run Wiki Scan — documents with a NULL embedding are re-queued even when the file hash is unchanged.

```text
python -m spock_bringup reembed --yes
python -m spock_rag_adapter.reembed status
```

## Related

- Post-ready lite hub: `Spock.bat` → Spock-UIE-Wiki-KB orchestrator  
- Progress modal used by the console menu: `python -m spock_progress_log …`
