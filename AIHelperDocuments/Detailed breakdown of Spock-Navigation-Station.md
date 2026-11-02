# Spock Ask AI — 20260831-124250

## You

Please give a detailed breakdown of Spock-Navigation-Station. Describe all options, and usage.

## Computer

### Overview of Spock-Navigation-Station

**Spock-Navigation-Station** is the primary, full-featured desktop GUI orchestrator for the Spock-Onboarding suite. Built on **PyQt6**, it guides users through a structured, multi-step pipeline—from hardware discovery and local model execution to knowledge ingestion (Wiki scanning) and local RAG-enabled chat (Ask AI). 

It consolidates several standalone tools into a single left-navigation interface, managing background processes like `llama-server` instances, the Spock RAG API, and the Model Context Protocol (MCP) adapter.

---

### 1. Architecture & Entry Point

The application is launched via a thin entry script:

* **File Path:** `D:\Spock-Onboarding\spock_navigation.py`

* **Mechanism:** It ensures the core library path (`WarpCore`) is on `sys.path` via `_warpcore_path.ensure()`, initializes the Qt application using `spock_shell.qt_app.create_app`, and instantiates the main window:
  
  ```python
  from NavigationStation.app import NavigationStationWindow
  from spock_shell.qt_app import create_app
  
  def main() -> int:
      app = create_app(sys.argv)
      win = NavigationStationWindow()
      win.show()
      return app.exec()
  ```

The main window class, `NavigationStationWindow`, is defined in:

* **File Path:** `D:\Spock-Onboarding\NavigationStation\app.py`
* **Inheritance:** It inherits from `SuiteShellWindow` (defined in `spock_shell.window`), which provides the standard layout: a left-hand navigation panel, a central stacked widget for steps, and a right-hand dock for utility tools.

---

### 2. Detailed Breakdown of Navigation Steps

The left-hand navigation panel exposes a sequential workflow (Steps 1–8) designed to take a user from a clean slate to a fully operational local AI assistant.

```
[Home] ──> [1 Hardware] ──> [2 HF Models] ──> [3 Launch] ──> [4 Configure Spock AI] ──> [5 Spock Status] ──> [6 Run Wiki Scan] ──> [7 Ship's Logs] ──> [8 Run Ask AI]
```

#### Step 1: Hardware Scan

* **Action:** `_show_hardware()`
* **Implementation:** Built via `build_hardware_step(self.theme, self.state)` from `NavigationStation.steps.hardware`.
* **Usage & Options:** 
  * Automatically triggers a hardware scan (`_start_scan`) the first time the pane is displayed.
  * Detects system CPU, RAM, and available GPUs (VRAM, compute capability).
  * Saves specs to `self.state.hardware_specs` (a `ModelSelectorState` instance), which is required to unlock subsequent Hugging Face model queries.

#### Step 2: HF Models (Hugging Face Hub)

* **Action:** `_show_models()`
* **Implementation:** Uses `ModelsPanel` from `model_selector_panels.py`.
* **Usage & Options:**
  * Allows users to query the Hugging Face Hub for GGUF format models.
  * Features dedicated buttons: **Query Chat Models** and **Query Embedding Models**.
  * Filters and recommends models based on the hardware specs gathered in Step 1.

#### Step 3: Launch (Local Llama Servers)

* **Action:** `_show_launch()`
* **Implementation:** Uses `LaunchPanel` from `model_selector_panels.py` backed by `LlamaServerManager` from `llama_server_manager.py`.
* **Usage & Options:**
  * Manages starting and stopping local `llama-server` instances.
  * **Dual-Server Layout:** Typically runs two separate servers:
    1. **Embedding Server** (default port `:8080`): Dedicated strictly to generating vector embeddings.
    2. **Chat Server** (default port `:8081`): Dedicated to instruct/chat generation.
  * **Options:** Allows selecting which GPU to target, configuring context size (`n_ctx`), and setting GPU offload layers (`-ngl` / `--n-gpu-layers`).

#### Step 4: Configure Spock AI

* **Action:** `_show_configure()`
* **Implementation:** Built via `build_configure_step` in `D:\Spock-Onboarding\NavigationStation\steps\configure.py`, which instantiates `ConfigureAiPanel` from `D:\Spock-Onboarding\spock_shell\configure_ai.py`.
* **Usage & Options:**
  A tabbed configuration panel that unifies all backend connections:
  * **LM Studio Tab:** Connects to an external LM Studio instance (Host, Port, Model ID, Load Context, API Key).
  * **MCP Tab:** Configures the Spock MCP Adapter (transport type, host, port).
  * **Embedding Profile / RAG API Tab:** Manages the local Spock RAG API server (port `:8090`). Users can start/stop the RAG server directly from this tab.

#### Step 5: Spock Status

* **Action:** `_show_status()`
* **Implementation:** Built via `build_status_step` from `NavigationStation.steps.status`.
* **Usage & Options:**
  * Probes the active status of all system components.
  * Runs HTTP and socket checks against:
    * RAG API (`:8090/health`)
    * MCP Adapter (`:8765/mcp`)
    * Embedding `llama-server` (`:8080`)
    * Chat `llama-server` (`:8081`)
  * Writes the status report to `spock_ready_last.json`.

#### Step 6: Run Wiki Scan

* **Action:** `_show_run()`
* **Implementation:** Built via `build_wiki_agent_run_panel` from `spock_wiki_adapter.wiki_run`.
* **Usage & Options:**
  * Ingests local or remote markdown/wiki documentation.
  * Chunks the text, generates vector embeddings using the active embedding server, and writes the resulting documents and vectors into the central SQLite database (`ship_computer.db`).
  * Displays a live log of the ingestion agent's progress.

#### Step 7: Ship's Logs

* **Action:** `_show_ships_logs()`
* **Implementation:** Built via `build_ships_logs_panel` from `ScienceStation.ships_logs` targeting `SHIP_COMPUTER_DB`.
* **Usage & Options:**
  * A database browser displaying tables inside `ship_computer.db`.
  * **Tabs:**
    * **Captain's Log:** General system and user-logged events.
    * **Agent's Queue:** Tasks pending or completed by background agents.
    * **Documents:** Ingested files, paths, and metadata.
    * **Quarantine:** Files flagged or failed during ingestion.

#### Step 8: Run Ask AI

* **Action:** `_show_ask_ai()`
* **Implementation:** Uses `AskAiPanel` from `EngineeringDeck.ask_panel`.
* **Usage & Options:**
  * The primary user-facing chat interface.
  * Integrates **Hybrid Search** (combining SQLite FTS5 keyword search and vector similarity search via `WarpCore.search.hybrid_search`).
  * **Options:** Users can toggle RAG on/off, adjust the number of retrieved context documents, and chat directly with the configured LLM provider.

---

### 3. Configuration & Profile Management

The Navigation Station features robust profile management to save and restore complex multi-server configurations.

* **Profile Storage:** Profiles are stored in `ship_computer.db` and managed via `WarpCore.profile_store` (re-exported by `spock_profile_store.py`).
* **Startup Behavior:** On startup, `NavigationStationWindow` triggers `_offer_profile_load` via a single-shot timer:
  
  ```python
  QTimer.singleShot(0, self._offer_profile_load)
  ```
  
  This prompts the user to load an existing profile (e.g., "RTX 6000 Default", "MacBook Local").
* **Profile Saving:** Users can save their active configuration (including selected models, ports, context lengths, and active providers) into a named profile using `save_profile_interactive` from `spock_shell.profiles`.

---

### 4. Service Endpoints & Port Layout

Network ports and endpoints are resolved centrally through `D:\Spock-Onboarding\WarpCore\service_endpoints.py` to prevent hardcoding. The typical port layout managed by the Navigation Station is:

| Port        | Service                  | Description                                                             |
|:----------- |:------------------------ |:----------------------------------------------------------------------- |
| **`:8080`** | Embedding `llama-server` | Generates vector embeddings for RAG and Wiki scanning.                  |
| **`:8081`** | Chat `llama-server`      | Handles conversational LLM generation.                                  |
| **`:8082`** | `llama-server` MCP Proxy | WebUI proxy for the Engineering Deck.                                   |
| **`:8090`** | Spock RAG API            | OpenAI-compatible gateway serving the database context.                 |
| **`:8765`** | Spock MCP HTTP           | Streamable-HTTP adapter for MCP clients (e.g., Cursor, Claude Desktop). |
| **`:8000`** | Docs Server              | Serves the local MkDocs documentation site.                             |

---

### 5. Typical Usage Workflow

To utilize the Spock-Navigation-Station from start to finish:

1. **Launch the App:** Run `python spock_navigation.py`.
2. **Scan Hardware (Step 1):** Let the automatic scan complete to identify your CPU/GPU capabilities.
3. **Acquire Models (Step 2):** Search Hugging Face and download a recommended GGUF pair (one embedding model, one chat model).
4. **Launch Servers (Step 3):** Start the embedding server on `:8080` and the chat server on `:8081`.
5. **Configure & Start RAG (Step 4):** Navigate to the *Embedding Profile / RAG API* tab and click **Start RAG Server** to spin up the API on `:8090`.
6. **Verify Health (Step 5):** Run the status probe to ensure all green checkmarks are received.
7. **Ingest Knowledge (Step 6):** Run a Wiki Scan to chunk and embed your documentation into `ship_computer.db`.
8. **Chat with Context (Step 8):** Open *Run Ask AI*, type a query, and watch Spock retrieve relevant documents from your newly ingested wiki to answer your questions.

## 
