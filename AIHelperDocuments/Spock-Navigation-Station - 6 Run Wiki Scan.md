# Spock Ask AI — 20260831-131207

## You

Please give a detailed breakdown of Spock-Navigation-Station / 6 Run Wiki Scan. Describe all options, and usage.

## Computer

In the **Spock-Navigation-Station** suite, **"6 Run Wiki Scan"** is the control center for indexing, extracting, and embedding local documents into the ship's computer database (`ship_computer.db`). It acts as a graphical wrapper around the background ingestion engine, `wiki_agent.py`.

Below is a detailed technical breakdown of its architecture, options, preflight checks, and usage.

---

### 1. Architecture & Call Flow

The "6 Run Wiki Scan" step is designed to run the heavy, long-running Python ingestion process asynchronously so that the PyQt6 user interface remains responsive.

```
[NavigationStationWindow]
       │
       ▼ (Shows Step 6)
[Wiki Agent Run Panel] (spock_wiki_adapter/wiki_run.py)
       │
       ├─► [Preflight Check] (Probes :8080, :8081, and RAG API)
       │
       ├─► [Scan Roots Dialog] (spock_wiki_adapter/scan_roots.py) ──► Updates DB / scan_config.json
       │
       ▼ (Spawns Subprocess)
[wiki_agent.py] ◄───(Monitored by)─── [ProcessOutputReader] (QThread)
       │                                      │
       ▼ (Ingests & Embeds)                   ▼ (Strips ANSI & Streams)
[ship_computer.db] ◄─────────────────── [Log Terminal UI]
```

#### Key File Citations:
*   **Entry Point / Navigation Integration:** `D:\Spock-Onboarding\NavigationStation\app.py`
*   **UI Panel Implementation:** `D:\Spock-Onboarding\spock_wiki_adapter\wiki_run.py`
*   **Scan Roots Configuration Dialog:** `D:\Spock-Onboarding\spock_wiki_adapter\scan_roots.py`
*   **Core Ingestion Engine:** `D:\Spock-Onboarding\wiki_agent.py`

---

### 2. Preflight Verification

Before the Wiki Scan subprocess is allowed to launch, the panel executes a strict preflight check via `_preflight_spock_health()` in `wiki_run.py`. This prevents the agent from running and failing silently due to missing backend services.

1.  **Embedding Server Check:** Probes the configured embeddings URL (typically `http://localhost:8080/embeddings`). If unreachable, it halts execution and displays a warning:
    > *"Embedding llama-server is not reachable on :8080. Run menu 4) Bring up servers before Wiki Scan."*
2.  **Chat Server Check:** Probes the chat server port (typically `:8081`). If unreachable, it warns the user.
3.  **RAG API Check:** Probes the Spock RAG API (typically `:8090/health`).
4.  **Log Output:** If successful, the full health report is formatted and printed to the terminal log before the scan begins.

---

### 3. Subprocess Environment Setup

When the scan is started, `wiki_run.py` constructs a clean, isolated environment dictionary using `_embedding_env()` to pass to `subprocess.Popen`. This ensures `wiki_agent.py` has access to the correct embedding models and context limits:

*   **`EMBEDDINGS_URL`**: Resolved from the active embedding profile (e.g., `http://localhost:8080/embeddings`).
*   **`EMBEDDINGS_DIM`**: The vector dimension size (e.g., `4096` for Llama-3-based embedders).
*   **`EMBEDDINGS_TRUNCATE`**: Maximum character limit per chunk (defaults to `1500`).
*   **`EMBEDDINGS_BATCH_CHUNK` & `EMBEDDINGS_BATCH_WORKERS`**: Controls parallel embedding generation (defaults to `32` chunks across `8` workers).
*   **`WIKI_AGENT_EXTENSIONS`**: Set to `"all"` or restricted to specific extensions (e.g., `.py,.ts,.rs`).
*   **`PYTHONUNBUFFERED` & `NO_COLOR`**: Set to `1` to ensure clean, real-time log streaming without ANSI escape sequences.
*   **`PYTHONPATH`**: Prepended with the repository root path so that internal modules (like `WarpCore`) resolve correctly.

---

### 4. UI Options & Controls

The "Run Wiki Scan" panel provides several interactive controls:

#### A. Start / Stop Scan Buttons
*   **Start Scan:** Triggers the preflight check, configures the environment, and spawns `python wiki_agent.py`.
*   **Stop Scan:** Sends a termination signal to the running subprocess. If it does not exit cleanly within a timeout, it kills the process tree to prevent orphaned `llama-server` or python processes.

#### B. Scan Roots Configuration (Modal Dialog)
Clicking the **"Update Scan Roots"** button opens `ScanRootsDialog` (`spock_wiki_adapter/scan_roots.py`).
*   **Add Folder...**: Opens a native directory picker (`QFileDialog.getExistingDirectory`) to add new directories to index.
*   **Delete Selected**: Removes a directory from the indexing list.
*   **Persistence**: Saves the updated list directly to `ship_computer.db` under the key `scan.scan_roots` using the `WarpCore.settings_store`. It also writes a fallback copy to `scan_config.json`.

#### C. Live Log Terminal
*   A read-only `QTextEdit` configured with a monospaced font (`Consolas`).
*   It displays real-time output from `wiki_agent.py` (e.g., file discovery, extraction progress, database writes, and vector embedding generation).
*   **ProcessOutputReader (`QThread`):** Reads the stdout stream of the subprocess line-by-line in a background thread and safely posts updates to the main Qt thread using a `pyqtSignal` (`line_read`).

---

### 5. Usage & Operational Flow

To run a document ingestion scan:

1.  **Launch Backends:** Ensure your local LLM servers are running (Step 3 "Launch" in the Navigation Station, or Step 4 in the Bringup Menu).
2.  **Navigate to Step 6:** Click **"6 Run Wiki Scan"** in the left navigation panel.
3.  **Configure Folders:**
    *   Click **"Update Scan Roots"**.
    *   Add the directories containing the codebases, markdown files, or documentation you want Spock to know about.
    *   Click **Save** (if the agent is already running, you will be prompted to restart it).
4.  **Start Ingestion:** Click **"Start Scan"**.
    *   The preflight check will run.
    *   The terminal will display `Running spock_health preflight...` followed by the status of your servers.
    *   `wiki_agent.py` will begin scanning the roots, checking for modified files, extracting text using `starfleet_universal_extractor.py`, generating vector embeddings, and saving them to `ship_computer.db`.
5.  **Monitor & Query:** Once the log shows that indexing is complete, you can immediately query the newly ingested knowledge base in **"8 Run Ask AI"** or via the RAG API.
