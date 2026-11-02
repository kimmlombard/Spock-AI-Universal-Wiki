# Spock Ask AI — 20260831-124903

## You

Please give a detailed breakdown of Spock-Navigation-Station / 3 Launch . Describe all options, and usage.

## Computer

Based on the codebase corpus, here is a detailed technical breakdown of **Step 3: Launch** in the **Spock-Navigation-Station** suite.

---

### 1. Architectural Overview
The **"3 Launch"** step is the bridge between model acquisition (Step 2) and AI configuration/ingestion (Step 4+). It is responsible for starting, managing, and attaching to local `llama-server` instances that power the Spock AI suite.

*   **Primary GUI Component**: `LaunchPanel` (defined in `model_selector_panels.py` and instantiated in `NavigationStation\app.py` [Doc 4]).
*   **Process Manager**: `LlamaServerManager` (defined in `llama_server_manager.py` [Doc 4]) which coordinates with the headless process manager `LlamaProcessManager` (defined in `spock_onboarding\llama_process.py` [Doc 15]).
*   **State Management**: `ModelSelectorState` (defined in `model_selector_panels.py` [Doc 4]) tracks selected models, hardware specs, and active ports.

---

### 2. UI Options & Configuration Parameters

When a user navigates to **3 Launch**, the panel dynamically populates options based on the hardware scan from Step 1 and the models selected in Step 2.

#### A. GPU Selection & Allocation
*   **GPU Dropdown / Selector**: Populated via `panel._populate_gpus()` [Doc 4]. It reads the hardware specifications scanned in Step 1 (using NVML or `nvidia-smi` [Doc 31]).
*   **VRAM Allocation Planning**: Displays available VRAM. If a single GPU is shared between the embedding and chat servers, the system calculates a "sibling size" budget so that launching one model does not starve the other of VRAM [Doc 31].

#### B. Embedding Server Configuration (Default Port: `:8080`)
*   **Model Path**: The GGUF file selected for text embeddings (e.g., `nomic-embed-text` or similar).
*   **Port**: Defaults to `8080` (configurable via `SPOCK_EMBED_PORT` or `app_config.json` [Doc 16]).
*   **Context Size (`n_ctx`)**: Defaults to `8192` [Doc 16]. It can be auto-recommended based on VRAM. For embeddings, batch size is prioritized over massive context, so the system typically clamps this to `1024` or `2048` on lower-end cards to save VRAM [Doc 31].
*   **GPU Offload (`-ngl` / Number of GPU Layers)**: Calculated dynamically via `llmfit_bridge.resolve_ngl()` [Doc 15] to offload as many layers as possible to the GPU without causing an Out-Of-Memory (OOM) error.

#### C. Chat Server Configuration (Default Port: `:8081`)
*   **Model Path**: The GGUF file selected for chat/generation (e.g., `Llama-3` or `Qwen` variants).
*   **Port**: Defaults to `8081` (configurable via `SPOCK_CHAT_PORT` [Doc 16]).
*   **Context Size (`n_ctx`)**: Defaults to `8192` [Doc 16]. Calculated using a heuristic "context ladder" (`CTX_LADDER` [Doc 31]) that estimates KV cache size based on remaining VRAM headroom after subtracting the model weights and the embedding sibling model's size [Doc 31].
*   **GPU Offload (`-ngl`)**: Dynamically resolved based on model size and remaining VRAM.

---

### 2b. Persisting the Launch flags

Nothing typed into the Launch row used to survive a restart: the panel re-seeded every control from the host recipe on open. The flags now have two homes, split by whether the value describes the *user's preference* or the *machine*.

| Flag | Stored in | Applies |
|------|-----------|---------|
| `-ngl` (GPU Layers) | `app.launch.ngl` (`Spock_Console`) | Every launch, any machine |
| embed `-np` | `app.launch.embed_np` | Embedding server only |
| GPU policy, tensor-split, split-mode, `-c` | `spock_host_recipe` (versioned) | This machine, until the hardware changes |
| `-b` / `-ub` | `app.embedding_profile.llama_batch` / `llama_ubatch` (unchanged) | Embedding profile |

*   **SAVE DEFAULTS** writes the two `app.launch.*` rows via `settings_store.set_many`. `-1` is stored as "ask llmfit at launch"; a number pins `-ngl` and bypasses `resolve_ngl()` entirely, so `99` offloads every layer whether or not it fits. Values outside `-1..999` are rejected before they can reach `llama-server`.
*   **SAVE TO RECIPE** appends a host recipe version through `host_recipe.update_recipe`, so the change carries a reason and shows up in `Maintenance → Recipe` history.
*   `host_recipe.launch_plan_for_role()` is what merges the two: the recipe (or its live proposal, when the hardware drifted) supplies the base, then the pins override `-ngl` and embed `-np`. All three launch paths call it — the panel, `spock_shell.profiles` on profile restore, and `spock_bringup` step 5 — so a pin is honoured no matter which one starts the server.
*   `ngl_source` rides along so the launch log can say `-ngl 99 (pinned in app.launch.ngl)` instead of crediting llmfit for a number it did not choose.
*   The pins reach `app_config.json` through the settings export rather than by editing the file; `settings_store` replaced the root-level config files with the `Spock_Console` table, and `export_to_json` writes them back as a `"launch"` block for backup.

---

### 3. Under-the-Hood Mechanics

#### A. Dynamic NGL and Context Planning
The launch panel relies on `spock_scanner_core.py` [Doc 31] to run heuristics before spawning processes:
```python
# Heuristic calculation from spock_scanner_core.py
headroom = max(0.0, budget - weights * 1.10 - sibling * 1.10)
# Remaining headroom is used to fund the KV cache size (n_ctx)
```
This prevents system crashes by ensuring that both the embedding model and the chat model can comfortably fit into the available VRAM.

#### B. Launching vs. Attaching
For both the embedding and chat servers, the panel offers two modes of operation:
1.  **Launch**: Spawns a new background `llama-server` process.
    *   On Windows, it is spawned with `subprocess.CREATE_NEW_CONSOLE` to run visibly or in a separate job tree [Doc 22].
    *   Command-line arguments passed include: `--model <path>`, `--port <port>`, `--ctx-size <n_ctx>`, and `--n-gpu-layers <ngl>`.
2.  **Attach**: If a server is already running on port `:8080` or `:8081` (e.g., started externally or by another tool), the panel probes the endpoint using `/health` [Doc 35]. If reachable, it "attaches" to the existing instance, reading its active model path and context size via `/props` or `/slots` [Doc 35], avoiding redundant process creation.

#### C. Health Probing & Readiness
Once a launch command is issued, the system enters a wait loop (`wait_until_healthy` [Doc 15]) and queries the server's HTTP endpoints:
*   **`/health`**: Verifies the HTTP server is responding with a `200 OK` [Doc 35].
*   **`/props`**: Retrieves the active model path and default generation settings (including `n_ctx`) [Doc 35].
*   **`/slots`**: Fallback endpoint to determine active context slots if `/props` is unavailable [Doc 35].

Once healthy, the status is written to `spock_ready_last.json` [Doc 2, Doc 34], which unlocks downstream features like the **AI Helper** and **Ask AI** panels.

---

### 4. Usage Workflow

1.  **Open Step 3**: Click **"3 Launch"** on the left navigation panel of the Spock-Navigation-Station [Doc 4].
2.  **Verify GPU**: Ensure your target NVIDIA or system GPU is selected in the dropdown.
3.  **Review Recommendations**:
    *   The panel displays recommended `-c` (context) and `-ngl` (GPU layers) values calculated by the hardware planner.
    *   Adjust these values manually if you want to reserve VRAM for other applications.
4.  **Start Embedding Server**:
    *   Click **"Launch Embedding Server"** (or **"Attach"** if already running).
    *   The status indicator will turn yellow (loading/probing) and then green (OK) once `:8080/health` responds [Doc 6].
5.  **Start Chat Server**:
    *   Click **"Launch Chat Server"**.
    *   The system will spawn the chat `llama-server` on `:8081`.
6.  **Proceed**: Once both indicators are green, the system is ready. You can proceed to **"4 Configure Spock AI"** to bind these active endpoints to the RAG pipeline [Doc 4, Doc 14].
