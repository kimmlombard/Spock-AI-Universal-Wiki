# Spock Ask AI — 20260831-133956

## You

Please give a detailed breakdown of Spock-Engineering-Maintenance / 2 Ships Computer DB Health. Describe all options, and usage.  Define the 7 tabs and option buttons.

## Computer

The **Spock-Engineering-Maintenance** application (launched via `spock_maintenance.py`) is a PyQt6-based console maintenance suite. Its second navigation step, **"2 Ship Computer DB Health"**, is managed by the `ShipComputerHealthPanel` class defined in `D:\Spock-Onboarding\EngineeringDeck\ship_computer_health.py`. 

This panel serves as a diagnostic and administrative hub for the ship's primary database (`ship_computer.db`) and provides a graphical interface to execute and inspect the output of the suite's **Model Context Protocol (MCP)** tools.

---

### 1. Core Architecture & Execution Flow

Rather than spawning external processes or requiring a formal package installation, the `ShipComputerHealthPanel` executes MCP tools **in-process** by dynamically loading the server script:

1. **Dynamic Module Loading (`_load_mcp_module`)**:
   It locates the MCP server script at `D:\Spock-Onboarding\scripts\mcp_spock_server.py`. It loads it using Python's `importlib.util` and registers it under `sys.modules["mcp_spock_server_tools"]`. This caching prevents re-running FastMCP registration side effects on subsequent tab refreshes.
2. **Direct Tool Invocation (`_call_mcp_tool`)**:
   FastMCP wraps Python functions as `FunctionTool` objects. The panel bypasses network overhead by extracting the underlying callable function (via the `.fn` attribute or calling the tool directly) and executing it with the required keyword arguments:
   ```python
   fn = getattr(tool, "fn", None)
   return fn(**kwargs) if kwargs else fn()
   ```

---

### 2. Detailed Breakdown of the 7 Tabs

The panel organizes its diagnostics into a `QTabWidget` containing exactly **7 tabs**. Each tab targets a specific aspect of database health, system readiness, or hardware-model compatibility.

#### Tab 1: Overview
* **Purpose**: Provides a high-level summary of the SQLite database (`ship_computer.db`) structure and row counts.
* **Displayed Information**:
  * **Database Name & Path**: Points to `SHIP_COMPUTER_DB`.
  * **Size**: Total database size on disk in Megabytes (MB).
  * **Documents Count**: Total rows in the `documents` table, along with the subset of documents that have generated vector embeddings (`embedding IS NOT NULL`).
  * **Captains Log Count**: Total rows in the `captains_log` table.
  * **Agent Queue Count**: Total rows in the `agent_queue` table.
  * **Quarantine Count**: Total rows in the `quarantine` table.
* **Option Buttons**:
  * **"Refresh Stats"**: Re-queries the database using SQLite `COUNT(*)` statements and updates the read-only `QTextEdit` display.

#### Tab 2: spock_health
* **Purpose**: Probes the active status of all Spock-related network endpoints and local servers.
* **Displayed Information**:
  * Status of the Spock RAG API `/health` endpoint (typically port `:8090`).
  * Status of the embedding `llama-server` (typically port `:8080`).
  * Status of the chat `llama-server` (typically port `:8081`).
  * Status of the local MCP adapter (typically port `:8765`).
  * Status of the `--ui-mcp-proxy` (typically port `:8082`).
  * Embedding health verification (runs `test_embeddings.py` against the configured endpoint).
* **Option Buttons**:
  * **"Run Spock Health"**: Invokes the `spock_health` MCP tool in-process and prints the formatted JSON/text output.

#### Tab 3: spock_status
* **Purpose**: Generates a comprehensive system readiness and hardware status report.
* **Displayed Information**:
  * Installation root directory.
  * UI and server readiness flags (`ui_ready`, `servers_ready`, `full_deps_ok`).
  * Detailed blocks for the `:8080` (embedding) and `:8081` (chat) `llama-server` instances (including model name, context window `n_ctx`, and reachability).
  * Discovered active `llama-server` process IDs (PIDs), roles, and ports.
  * Summary of RAG API, embedding, chat, and MCP adapter reachability.
* **Option Buttons**:
  * **"Run Spock Status"**: Executes the `spock_status` MCP tool (which calls `probe_spock_status` in `D:\Spock-Onboarding\spock_onboarding\spock_status.py`) and displays the formatted report.

#### Tab 4: spock_queue
* **Purpose**: Monitors the background ingestion queue used by the Wiki Agent.
* **Displayed Information**:
  * A list of pending, processing, or failed tasks inside the `agent_queue` table.
  * Details on document paths currently queued for scanning, extraction, or embedding.
* **Option Buttons**:
  * **"Refresh Queue"** / **"Run Spock Queue"**: Invokes the `spock_queue` MCP tool to fetch a sample of the active queue.

#### Tab 5: spock_captains_log
* **Purpose**: Audits recent system events, agent actions, and user queries.
* **Displayed Information**:
  * Chronological rows from the `captains_log` table.
  * Event types, timestamps, target document IDs, and status messages.
* **Option Buttons**:
  * **"Refresh Log"** / **"Run Captains Log"**: Invokes the `spock_captains_log` MCP tool to pull the latest log entries.

#### Tab 6: spock_llmfit_fit
* **Purpose**: Evaluates local hardware capabilities and ranks GGUF models based on estimated performance.
* **Displayed Information**:
  * Local GPU/CPU hardware specifications.
  * Fit level (e.g., "Full VRAM", "Partial VRAM", "System RAM Only") for various model sizes.
  * Estimated tokens-per-second (tok/s) throughput.
* **Option Buttons**:
  * **"Run LLMFit Fit"**: Invokes the `spock_llmfit_fit` MCP tool to run local hardware benchmarks and display model recommendations.

#### Tab 7: spock_hardware_plan
* **Purpose**: Generates an optimized execution plan for a specific model and context size.
* **Displayed Information**:
  * Recommended number of layers to offload to the GPU (`-ngl` or `--n-gpu-layers`).
  * Estimated VRAM and system memory consumption for the requested context size (`n_ctx`).
  * Warning flags if the model exceeds available VRAM.
* **Option Buttons**:
  * **"Generate Plan"**: Executes the `spock_hardware_plan` MCP tool, allowing engineers to input a target model and context limit to receive a tailored launch configuration.

---

### 3. Option Buttons & Styling

The panel utilizes a standardized button creation helper (`_make_btn`) that applies custom properties for stylesheet-driven theme integration:

```python
def _make_btn(self, text: str, callback, *, kind: str = "run") -> QPushButton:
    btn = QPushButton(text)
    btn.setMinimumHeight(32)
    btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    btn.setProperty("maint_kind", "run" if kind == "run" else "accent")
    btn.clicked.connect(callback)
    return btn
```

* **`maint_kind = "run"`**: Styled as a standard action button (typically used for executing heavy diagnostic tools like `Run Spock Status` or `Run Spock Health`).
* **`maint_kind = "accent"`**: Styled with the theme's accent color (typically used for non-destructive UI updates like `Refresh Stats`).

---

### 4. Typical Usage & Maintenance Workflows

1. **Database Verification**:
   An engineer opens the **Overview** tab and clicks **Refresh Stats** to verify that the database size is non-zero and that the number of documents with embeddings matches the total document count. If there is a mismatch, they know they need to trigger a re-embed operation.
2. **Connectivity Troubleshooting**:
   If the Ask AI panel or Wiki Agent fails, the engineer switches to the **spock_health** or **spock_status** tabs and clicks their respective **Run** buttons. This immediately reveals if a `llama-server` instance has crashed, if there is a port collision, or if the RAG API is unreachable.
3. **Hardware Optimization**:
   Before launching a new model, the engineer uses the **spock_llmfit_fit** and **spock_hardware_plan** tabs to determine the maximum safe context window (`n_ctx`) and the exact number of GPU layers (`-ngl`) to offload, preventing out-of-memory (OOM) crashes on the ship's computer.
