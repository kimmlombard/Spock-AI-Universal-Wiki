# Spock Ask AI — 2026-08-25T14-44-18

- **Mode**: deep_dive
- **Path filter**: `D:\Spock-Onboarding`
- **Language filter**: `!.md,!.txt,!.rst`

## Conversation

### You

What are the major components of the Spock Onboarding python application?  How do they interact?  What is the usage for an app like this?

### Computer

Based on the provided context, the **Spock Onboarding** application is a Retrieval-Augmented Generation (RAG) and hardware assessment tool. Here are its major components, how they interact, and its primary use cases:

### 1. Major Components

*   **RAG API Server (`rag_api_server.py`):** 
    The backend of the application. It is an OpenAI-compatible RAG HTTP API built using only the Python standard library. It serves the Web UI and handles AI requests using a model identified as `"spock-ships-computer"`.
*   **Web UI Frontend (`index.html` & `app.js`):** 
    A browser-based interface ("Spock — Ask AI") that allows users to interact with the AI. It includes features like "Ask", "Deep Dive", and "Search Chat", and provides UI controls to filter files by path or extension (e.g., including `*.py`, `*.ts`, `*.go` and excluding `!.md`, `!.txt`). It also allows users to save transcripts as Markdown (`.md`).
*   **Model Selector Panels (`model_selector_panels.py`):** 
    PyQt-based desktop UI panels used for selecting AI models within a broader "Spock-to-bridge" system.
*   **Spock Scanner Core (`spock_scanner_core.py`):** 
    The core logic for performing a "Spock-to-bridge Hardware Scan" and assessment.

---

### 2. How the Components Interact

*   **Web UI to Backend:** The frontend JavaScript (`app.js`) captures user inputs, file path filters, and commands (like "Ask" or "Deep Dive") from the HTML interface (`index.html`). It sends these requests to the backend HTTP API hosted by `rag_api_server.py`.
*   **RAG Processing:** The `rag_api_server.py` processes these requests, likely scanning the specified code files (filtered by the extensions defined in the UI) to perform Retrieval-Augmented Generation (RAG) and returns the AI's response back to the Web UI.
*   **Desktop Integration:** The PyQt panels (`model_selector_panels.py`) and the hardware scanner (`spock_scanner_core.py`) interact as part of a "Spock-to-bridge" system, allowing users to run hardware assessments and select models from a desktop interface.

---

### 3. Usage of the Application

This application is designed as a local developer assistant and system assessment tool. Its primary use cases include:

*   **Codebase Q&A (RAG):** Developers can use the "Ask AI" or "Deep Dive" features to query their local codebase. By filtering for specific file types (like Python, JavaScript, Go, C++), the AI can retrieve relevant code snippets and answer highly specific questions about the project.
*   **Hardware Diagnostics:** Using the `spock_scanner_core.py`, users can perform hardware scans and assessments of their system.
*   **Local AI Playground:** Because the server is OpenAI-compatible and uses standard libraries, it serves as a lightweight, self-contained local AI assistant (a "Ship's Computer") that doesn't require heavy external dependencies to run its API and web interface.

#### Sources

- **Spock — Ask AI** (0.59) — `D:\Spock-Onboarding\templates\webui\index.html`
- **rag_api_server** (0.53) — `D:\Spock-Onboarding\rag_api_server.py`
- **app** (0.51) — `D:\Spock-Onboarding\templates\webui\app.js`
- **model_selector_panels** (0.48) — `D:\Spock-Onboarding\model_selector_panels.py`
- **spock_scanner_core** (11.80) — `D:\Spock-Onboarding\spock_scanner_core.py`

### You

[Deep Dive] Please write a detailed spec of the Spock system for ingestion to the 'AI Helper' - the spec will be used as a foundation for new users during and after the onboarding process.  Be as detailed as possible.

### Computer

# SYSTEM SPECIFICATION: SPOCK-TO-BRIDGE ONBOARDING & RAG SYSTEM
**Document ID:** `01-Spock-System-Spec-HELPER.md`  
**Classification:** Starfleet Ship's Computer Core Documentation  
**Target Audience:** Engineering Officers, Developers, and Onboarding Personnel  

---

## 1. System Overview & Philosophy

The **Spock System** is a local-first, Retrieval-Augmented Generation (RAG) and hardware-orchestration platform designed to act as the "Ship's Computer." It provides developers with an intelligent assistant capable of scanning local codebases, managing local Large Language Model (LLM) servers, and exposing context-aware AI capabilities to both desktop interfaces and external IDEs (such as Cursor, Codex, and OpenCode).

### Core Design Principles
1. **Local-First & Air-Gapped:** All model execution, vector embeddings, and database storage occur locally on the host workstation.
2. **Hardware-Aware Orchestration:** Dynamically assesses host CPU, RAM, and GPU (VRAM) resources to optimize model selection and context window allocations.
3. **Agentic Ingestion:** Employs a background file-watching agent ("Wiki Agent") to continuously parse, extract, and index workspace files.
4. **Standardized Interoperability:** Exposes an OpenAI-compatible RAG API and a Model Context Protocol (MCP) server to integrate seamlessly with modern developer tools.

---

## 2. System Architecture & Component Topology

The Spock system is composed of several decoupled layers interacting via local loopback APIs, SQLite databases, and IPC (Inter-Process Communication) channels.

```
                     +--------------------------------------------------+
                     |               User Interfaces                    |
                     |  - Spock Bringup Menu (PyQt6 Onboarding)         |
                     |  - Spock Navigation Station (PyQt6 Control)      |
                     |  - Chat AI Helper (PyQt6 Q&A Panel)              |
                     +------------------------+-------------------------+
                                              |
                                              v
+---------------------------------------------+---------------------------------------------+
|                                  Orchestration Layer                                      |
|                                                                                           |
|  +-------------------------+  +-------------------------+  +---------------------------+  |
|  |  LlamaServerManager     |  |  RagApiServer           |  |  Wiki Agent (Watchdog)    |  |
|  |  - Port 8080 (Embed)    |  |  - Port 8090            |  |  - File Watcher           |  |
|  |  - Port 8081 (Chat)     |  |  - OpenAI-Compatible    |  |  - Universal Extractor    |  |
|  +------------+------------+  +------------+------------+  +-------------+-------------+  |
+---------------|----------------------------|-----------------------------|----------------+
                |                            |                             |
                v                            v                             v
+---------------+----------------------------+-----------------------------+----------------+
|                                     Data & Model Layer                                    |
|                                                                                           |
|  +-----------------------------------------+  +----------------------------------------+  |
|  |  Local Models (GGUF)                    |  |  ship_computer.db (SQLite WAL)         |  |
|  |  - Chat: spock-ships-computer           |  |  - Config, Scan Roots, Logs,           |  |
|  |  - Embeddings: Local / HuggingFace      |  |    Document Chunks & Embeddings        |  |
|  +-----------------------------------------+  +----------------------------------------+  |
+--------------------------------------------+----------------------------------------------+
                                             ^
                                             | (Queries / Tools)
                               +-------------+-------------+
                               |  MCP Spock Server (8765)  |
                               |  - stdio / http / sse     |
                               +-------------+-------------+
                                             ^
                                             |
                               +-------------+-------------+
                               |  External IDEs (Cursor)   |
                               +---------------------------+
```

### Key Network Ports & Protocols
*   **Port 8080:** Local Embedding Server (`llama-server` / `llamaccp`).
*   **Port 8081:** Local Chat LLM Server (`llama-server` / `llamaccp`).
*   **Port 8090:** Spock RAG API Server (OpenAI-compatible HTTP endpoint).
*   **Port 8765:** Model Context Protocol (MCP) Server (supports `stdio`, `streamable-http`, and `sse` transports).
*   **Port 8082:** WebUI Server (optional browser-based interface).

---

## 3. Subsystem Deep Dives

### 3.1. Hardware Assessment & Model Selection (`spock_scanner_core.py`)
Before launching any models, the system runs a hardware diagnostic to prevent Out-Of-Memory (OOM) crashes on the GPU.
*   **Resource Detection:** Queries system RAM, CPU cores, and GPU VRAM (via `nvidia-smi` or `pynvml`).
*   **Context Size Heuristics (`recommend_n_ctx`):**
    *   Calculates available VRAM headroom after subtracting model weight sizes.
    *   Applies a context ladder (`CTX_LADDER`) to find the maximum safe context window (`n_ctx`) for the chat model.
    *   Ensures the embedding model context is at least `1024` (or `2048` if VRAM $\ge$ 8GB) to prevent chunk truncation during ingestion.
    *   Accounts for "sibling" models when both chat and embedding servers share a single GPU.

### 3.2. Server Management & Orchestration (`llama_server_manager.py`)
Manages the lifecycles of the underlying `llama-server` processes.
*   **Process Guarding:** Uses process guards (`proc_guard.py`) to ensure orphaned server processes are reaped when the main UI closes.
*   **State Tracking:** Writes server readiness states to `spock_ready_last.json` to coordinate UI unlocks (e.g., unlocking the AI Helper only after servers are verified online).

### 3.3. Wiki Agent & Ingestion Pipeline (`wiki_agent.py`)
A background daemon that implements the "Agent-Skill loop" to keep the RAG database synchronized with local files.
*   **File Watching:** Uses the `watchdog` library to monitor configured "scan roots" (`scan_config.json` or database-defined paths).
*   **Filtering:** Respects allowed extensions (e.g., `.py`, `.ts`, `.go`, `.md`) and skips blacklisted directories (e.g., `.git`, `node_modules`, `venv`).
*   **Extraction:** Invokes `starfleet_universal_extractor.py` to parse files into clean text chunks.
*   **Database Storage:** Writes document metadata, chunks, and vector embeddings into `ship_computer.db` using SQLite Write-Ahead Logging (WAL) to prevent database locks during concurrent read/write operations.

### 3.4. Model Context Protocol (MCP) Adapter (`mcp_spock_server.py`)
Exposes Spock's internal capabilities to external developer environments.
*   **FastMCP Integration:** Built on the FastMCP framework.
*   **Exposed Tools:**
    *   `spock_health`: Probes the status of the RAG API, embedding/chat servers, and database.
    *   `spock_ask`: Allows external agents to query the local RAG pipeline directly.
*   **Logging:** Writes to `logs/spock-mcp.log` to allow debugging of background execution when spawned by IDEs like Cursor.

### 3.5. Chat AI Helper (`chat_ai_helper.py`)
A specialized Q&A interface designed to assist users with system operations.
*   **Curated Context:** Scans the `AIHelperDocuments/` directory for markdown files (specifically prioritizing `00-Background-HELPER.md`).
*   **Keyword Ranking:** Implements a lightweight, dependency-free TF-IDF style keyword scoring algorithm (`score_markdown_files`) to retrieve relevant helper documentation based on user queries.

---

## 4. Data Flow & Lifecycle

### 4.1. The Onboarding Phase (Steps 1–16)
New users navigate the onboarding process via the **Spock Bringup Menu** (`spock_bringup_menu/app.py`), which executes a sequential 16-step bootstrap sequence:
1.  **Phase A (Steps 1–2):** Virtual environment and the PyQt6 UI tier, then the full dependency tier (extractors, ingest, WebEngine, MCP).
2.  **Phase B (Steps 3–5):** Model acquisition (GGUF pair from Hugging Face), launching the dual `llama-server` instances, and probing readiness.
3.  **Phase C (Steps 6–9):** MCP adapter, Embedding Profile / RAG API, Live Monitor, and the initial Wiki Agent scan.
4.  **Phase D (Steps 10–16):** Ask AI, the suite GUIs, shutdown, and re-embedding when the embedding model changes.

### 4.2. The Ingestion Flow
```
[Local File Modified] 
       │
       ▼
[Wiki Agent (Watchdog Event)]
       │
       ▼
[Filter Check (Allowed Extensions / Skip Dirs)]
       │
       ▼
[Starfleet Universal Extractor] ───► [Text Chunks]
                                           │
                                           ▼
[Embedding Server (Port 8080)] ◄─── [Vector Generation]
       │
       ▼
[ship_computer.db (SQLite WAL)]
```

### 4.3. The Query Flow (RAG)
```
[User Query / IDE Tool Call]
       │
       ▼
[Spock RAG API (Port 8090) / MCP (Port 8765)]
       │
       ▼
[Vector Search in ship_computer.db] ───► [Retrieve Relevant Chunks]
                                                    │
                                                    ▼
[Construct System Prompt with Context Chunks] ◄─────┘
       │
       ▼
[Chat LLM Server (Port 8081)]
       │
       ▼
[Streaming Response to User / IDE]
```

---

## 5. Configuration & Environment Variables

The system is configured via a combination of `ship_computer.db` settings, `app_config.json`, and environment variables.

| Environment Variable | Default Value | Description |
| :--- | :--- | :--- |
| `LLAMA_SERVER_PATH` | `{SPOCK_ROOT}/tools/llama-server` | Path to `llama-server` / `llama-server.exe` (or its install dir). |
| `SPOCK_API_BASE_URL` | `http://127.0.0.1:8090` | Base URL for the Spock RAG API. |
| `SPOCK_DB_PATH` | `ROOT/ship_computer.db` | Path to the primary SQLite database. |
| `SPOCK_MCP_TRANSPORT` | `stdio` | MCP transport protocol (`stdio`, `streamable-http`, `sse`). |
| `WIKI_AGENT_EXTENSIONS`| `all` | Comma-separated extensions to scan (e.g., `.py,.ts,.md`). |
| `SPOCK_MCP_LOG_PATH` | `ROOT/logs/spock-mcp.log` | File path for MCP server logging. |

---

## 6. Troubleshooting & Diagnostics

When troubleshooting the Spock system, verify the following diagnostic checkpoints:

1.  **Database Locks:** If the UI or Wiki Agent reports database locks, ensure WAL mode is active by running:
    ```sql
    PRAGMA journal_mode;
    ```
    *(Should return `wal`)*.
2.  **Server Connectivity:** Use the built-in `spock_health` tool (via the MCP adapter or Navigation Station) to verify that ports `8080`, `8081`, and `8090` are listening and responding to HTTP requests.
3.  **Process Orphans:** If servers fail to bind to ports, check for orphaned background processes using:
    *   *Windows:* `tasklist | findstr llama`
    *   *Linux/macOS:* `ps aux | grep llama`
4.  **Ingestion Failures:** Check `wiki_agent_session.json` to verify the active PID, current stardate, and active scan roots of the background file watcher.

*Deep Dive: 155 match(es) · inventory 80 · used 6 · forced 0 · 42,331 chars (97% of 12,613)*

#### Sources

- **spock_scanner_core** (28.17) — `D:\Spock-Onboarding\spock_scanner_core.py`
- **mcp_spock_server** (26.09) — `D:\Spock-Onboarding\scripts\mcp_spock_server.py`
- **wiki_agent** (25.53) — `D:\Spock-Onboarding\wiki_agent.py`
- **app** (21.55) — `D:\Spock-Onboarding\spock_bringup_menu\app.py`
- **chat_ai_helper** (20.24) — `D:\Spock-Onboarding\chat_ai_helper.py`
- **app** (19.87) — `D:\Spock-Onboarding\NavigationStation\app.py`

### You

[Deep Dive] Please provide a comprehensive Spock-Onboarding-HELPER.md based on each of the modules called from spock_menu.ps1.

### Computer

# Spock Onboarding Helper Specification (`Spock-Onboarding-HELPER.md`)

This document serves as the comprehensive system specification and onboarding guide for the **Spock-to-Bridge Onboarding & RAG System**. It details the 16-step lifecycle orchestrated by the Spock Bringup Menu (`spock_menu.ps1` / `spock_bringup_menu\app.py`), mapping each phase to its underlying Python modules, database schemas, and network topologies.

---

## 1. System Architecture & Network Topology

The Spock system is a local-first, hardware-aware Retrieval-Augmented Generation (RAG) and Model Context Protocol (MCP) platform. It transforms a local workstation into an intelligent "Ship's Computer" capable of indexing codebases, running local LLMs, and serving developer tools.

```
                     +--------------------------------------------------+
                     |               User Interfaces                    |
                     |  - Spock Bringup Menu (PyQt6 Onboarding)         |
                     |  - Spock Navigation Station (PyQt6 Control)      |
                     |  - Chat AI Helper (PyQt6 Q&A Panel)              |
                     +------------------------+-------------------------+
                                              |
                                              v
+---------------------------------------------+---------------------------------------------+
|                                  Orchestration Layer                                      |
|                                                                                           |
|  +-------------------------+  +-------------------------+  +---------------------------+  |
|  |  LlamaServerManager     |  |  RagApiServer           |  |  Wiki Agent (Watchdog)    |  |
|  |  - Port 8080 (Embed)    |  |  - Port 8090            |  |  - File Watcher           |  |
|  |  - Port 8081 (Chat)     |  |  - OpenAI-Compatible    |  |  - Universal Extractor    |  |
|  +------------+------------+  +------------+------------+  +-------------+-------------+  |
+---------------|----------------------------|-----------------------------|----------------+
                |                            |                             |
                v                            v                             v
+---------------+----------------------------+-----------------------------+----------------+
|                                     Data & Model Layer                                    |
|                                                                                           |
|  +-----------------------------------------+  +----------------------------------------+  |
|  |  Local Models (GGUF)                    |  |  ship_computer.db (SQLite WAL)         |  |
|  |  - Chat: spock-ships-computer           |  |  - Config, Scan Roots, Logs,           |  |
|  |  - Embeddings: Local / HuggingFace      |  |    Document Chunks & Embeddings        |  |
|  +-----------------------------------------+  +----------------------------------------+  |
+--------------------------------------------+----------------------------------------------+
                                             ^
                                             | (Queries / Tools)
                               +-------------+-------------+
                               |  MCP Spock Server (8765)  |
                               |  - stdio / http / sse     |
                               +-------------+-------------+
                                             ^
                                             |
                               +-------------+-------------+
                               |  External IDEs (Cursor)   |
                               +---------------------------+
```

### Port Allocations
*   **Port 8080**: Local Embedding Server (`llama-server` / `llamacpp`).
*   **Port 8081**: Local Chat LLM Server (`llama-server` / `llamacpp`).
*   **Port 8090**: Spock RAG API Server (OpenAI-compatible endpoint).
*   **Port 8765**: Model Context Protocol (MCP) Server.

---

## 2. The 16-Step Onboarding & Bringup Lifecycle

The onboarding process is divided into 16 discrete steps defined in `D:\Spock-Onboarding\spock_bringup_menu\steps.py`. These steps transition the system from a raw environment to a fully operational local RAG and MCP-enabled assistant.

### Step 1: Phase A — Python / venv / PyQt6 Dependencies
*   **Kind**: CLI
*   **Command**: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:\Spock-Onboarding\bootstrap.ps1 -NonInteractive -EmitEvents -NoHandOffGui -InstallRoot D:\Spock-Onboarding`
*   **Description**: Initializes the Python virtual environment (`.venv`) at the project root. It installs core dependencies, including `PyQt6` for the desktop user interfaces, and verifies the base Python interpreter.

### Step 2: Phase B — Full Dependencies (Ingest / Extractors / WebEngine)
*   **Kind**: CLI
*   **Command**: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:\Spock-Onboarding\bootstrap_phase_b_job.ps1 -InstallRoot D:\Spock-Onboarding -FullDeps -Validate` (`-HeavyDeps` remains as an alias)
*   **Description**: Installs `requirements-full.txt` — the document extractors (`PyMuPDF`, `python-docx`, `openpyxl`, `pandas`, `beautifulsoup4`, `lxml`, `Pillow`), the `watchdog` file watcher, `PyQt6-WebEngine`, and the MCP server packages. Required before step 9 Wiki Scan and the UIEG crawler, which both check for these packages and point back here if they are missing. Writes `bootstrap_full_deps.ok` on success.

### Step 3: Acquire Runtime + Models
*   **Kind**: CLI
*   **Command**: `python -u -m spock_bringup --root D:\Spock-Onboarding acquire`
*   **Description**: Downloads the required local execution runtimes (such as `llama-server` binaries) and the default GGUF model files. It places them in the designated local cache directories.

### Step 4: Bring Up Servers (:8080 Embed + :8081 Chat)
*   **Kind**: CLI
*   **Command**: `python -u -m spock_bringup --root D:\Spock-Onboarding up`
*   **Description**: Launches two parallel instances of `llama-server` via `llama_server_manager.py`:
    1.  **Embedding Server**: Bound to port `8080` for vector generation.
    2.  **Chat Server**: Bound to port `8081` for conversational inference.
    It applies hardware-aware context sizing (`n_ctx`) to prevent GPU Out-Of-Memory (OOM) errors.

### Step 5: Status / Probe
*   **Kind**: CLI
*   **Command**: `python -u -m spock_bringup --root D:\Spock-Onboarding status`
*   **Description**: Probes the active ports (`8080` and `8081`) to verify that both servers are responding to health checks. Upon success, it writes a state file (`spock_ready_last.json`) containing the active server configurations and context limits.

### Step 6: MCP Adapter (stdio + HTTP Tools)
*   **Kind**: Spawn
*   **Command**: `python -m spock_mcp_adapter --root D:\Spock-Onboarding`
*   **Description**: Launches the Model Context Protocol (MCP) adapter. This component exposes Spock's internal tools (such as database querying, file reading, and system diagnostics) to external IDEs like Cursor or VS Code over stdio or HTTP.

### Step 7: Embedding Profile / RAG API
*   **Kind**: Spawn
*   **Command**: `python -m spock_rag_adapter --root D:\Spock-Onboarding`
*   **Description**: Starts the RAG API server (`rag_api_server.py`) on port `8090`. This server acts as an OpenAI-compatible gateway, advertising the model ID `spock-ships-computer`. It intercepts chat completion requests and injects relevant context retrieved from the local vector database.
*   **Acquire hand-off**: **Model path** and **Model id** are pre-filled from the step 3 Acquire pick (`first_models_last.json` → `embed_gguf_path` / `embed_model_id`) whenever they are empty or point at a missing file. **USE ACQUIRE RESULT** adopts that pick over whatever is in the fields; **APPLY / SAVE** writes it to `ship_computer.db` + `.env`.

### Step 8: Open Live Monitor (Ship Status GUI)
*   **Kind**: Spawn
*   **Command**: `python -m spock_live_monitor --root D:\Spock-Onboarding`
*   **Description**: Launches a PyQt6-based real-time monitoring dashboard. This GUI displays active process PIDs, CPU/GPU utilization, memory consumption, and the status of the background servers.

### Step 9: Run Wiki Scan
*   **Kind**: Spawn
*   **Command**: `python -m spock_wiki_adapter --root D:\Spock-Onboarding`
*   **Description**: Spawns the background file-watching agent (`wiki_agent.py`). This agent monitors configured workspace directories, extracts text from modified files using the `starfleet_universal_extractor.py`, chunks the content, generates embeddings via the port `8080` server, and updates `ship_computer.db`.
*   **Embedding Health**: Streams `test_embeddings.py` into the panel log — embedding coverage, dimension consistency, deserialization, cosine/FTS5 ranking, nearest-neighbour and batch consistency, plus a corpus-vs-live `:8080` GGUF comparison.

### Step 10: Ask AI / Deep Dive
*   **Kind**: Panel
*   **Module**: `EngineeringDeck.ask_panel.AskAiPanel` (same UI as Navigation Station → 8 Run Ask AI)
*   **Description**: Opens the Ask AI / Deep Dive center panel in-process. Supports path/extension filters, chat transcript search, Save to .MD, Render MD/HTML, Ask AI (hybrid retrieval + LLM), and Deep Dive (packed context). Requires embed + chat servers (step 4) and indexed docs (Wiki Scan) for best results.

### Step 11: Spock Navigation Station
*   **Kind**: Spawn
*   **Command**: `python D:\Spock-Onboarding\spock_navigation.py`
*   **Description**: Launches the primary desktop control panel. The Navigation Station provides a unified left-navigation interface to access chat, search, system settings, and diagnostic logs.

### Step 12: Spock Engineering Maintenance
*   **Kind**: Spawn
*   **Command**: `python D:\Spock-Onboarding\spock_maintenance.py`
*   **Description**: Opens the database and wiki maintenance console (`wiki_maintenance.py` / `db_maintenance.py`). This interface allows administrators to prune orphaned vector records, rebuild search indexes, and inspect raw database tables.

### Step 13: Spock UIEG KnowledgeBase
*   **Kind**: Spawn
*   **Command**: `python D:\Spock-Onboarding\spock_UIEG_KnowledgeBase.py`
*   **Description**: Launches the external knowledge capture system (`uieg_capture_panel.py`). This tool crawls external repositories, fetches documentation, and ingests it into the local Spock database.

### Step 14: Stop Servers / Kill All Processes
*   **Kind**: CLI
*   **Command**: `python -u -m spock_bringup --root D:\Spock-Onboarding down`
*   **Description**: Gracefully terminates all background processes managed by the Spock runtime, including the `llama-server` instances, RAG API, and MCP adapters. It cleans up lock files and process guards.

### Step 15: Re-embed / Switch Embedding Model
*   **Kind**: CLI
*   **Command**: `python -u -m spock_bringup --root D:\Spock-Onboarding reembed --yes`
*   **Description**: Clears all existing vector embeddings from `ship_computer.db` while preserving the raw document text. It then regenerates all embeddings using the currently selected embedding model.

### Step 16: Exit
*   **Kind**: Exit
*   **Description**: Closes the Spock Bringup Menu interface.

> **Spock Status** is no longer a left-nav step. The same report is available from **Right Tools → Ship Status** in every suite window, or on the command line via `python -m spock_status --root D:\Spock-Onboarding`.

---

## 3. Core Subsystem Deep Dives

### 3.1. Unified Chat Client & Collision Prevention (`llm_client.py`)
The `llm_client.py` module provides a unified interface for communicating with various LLM backends (LM Studio, Ollama, local `llama-server`, or cloud providers like Google Vertex AI and OpenAI).

*   **Collision Prevention**: To prevent infinite recursion, the client includes `embeddings_chat_collision(chat_url, embeddings_url)`. This function compares the network locations (`host:port`) of the chat endpoint and the embedding endpoint. If they match, it blocks the request, preventing the chat client from accidentally flooding the embedding server (or vice versa).
*   **Google Vertex AI Integration**: The client automatically repairs and normalizes Google Cloud Vertex AI endpoints. It rewrites regional endpoints to global ones (`vertex_global_base`) to ensure compatibility with newer Gemini models, and handles Application Default Credentials (ADC) token generation via `google_adc_bearer_token()`.

### 3.2. AI Configuration & Connection Management (`spock_shell\configure_ai.py`)
The `configure_ai.py` module provides a tabbed PyQt6 configuration interface for managing AI backends.

*   **Connector Tabs**: Each backend (e.g., LM Studio, Ollama, Local Llama, OpenAI, Gemini) is represented by a dedicated `_ConnectorTab` subclass. Each tab manages its own settings, connection testing (`test_connection`), and saving.
*   **RAG Gateway Protection**: The configuration interface explicitly blocks users from setting the chat completion endpoint to the Spock RAG gateway model (`spock-ships-computer` on port `8090`). Chatting directly with the gateway model would cause an infinite loop, as the gateway itself relies on an underlying chat model to generate responses.

### 3.3. Context Budgeting & Hybrid Retrieval (`deep_dive.py`)
The `deep_dive.py` module manages the context window and retrieval strategy for complex codebase queries ("Deep Dives").

*   **Token Estimation**: Because local models are highly sensitive to context overflows, the system uses a conservative estimation of **2.2 characters per token** (`CHARS_PER_TOKEN = 2.2`) for code-heavy prompts. If a local `llama-server` is active, it attempts to use the server's native `/tokenize` endpoint for exact counts.
*   **Dynamic Context Budgeting**:
    *   The system queries the active chat server's `/props` endpoint to determine the runtime context limit (`n_ctx`).
    *   It allocates a character budget (defaulting to `96,000` characters or a calculated fraction of `n_ctx`) to pack as much relevant code as possible without exceeding the model's limits.
*   **Hybrid Retrieval Strategy**:
    1.  **Forced Paths**: Explicitly requested files (e.g., files specified in the user's query) are prioritized and allocated a larger character budget (`FORCED_EXCERPT_CHARS = 24,000`) to ensure complete or near-complete file ingestion.
    2.  **Semantic Search**: The system queries the vector database for chunks matching the user's query.
    3.  **Budget Filling**: Remaining context budget is filled with adjacent code chunks and high-ranking search results up to the calculated token limit.

---

## 4. Database Schema (`ship_computer_schema.sql`)

The system state, document index, and vector metadata are stored in a local SQLite database (`ship_computer.db`) operating in Write-Ahead Logging (WAL) mode for concurrent read/write performance.

### Core Tables
1.  **`documents`**: Stores the raw text content, file paths, hashes, and metadata of all ingested files.
2.  **`embeddings`**: Stores the high-dimensional vector representations of document chunks, mapped back to the `documents` table.
3.  **`config`**: Key-value store for system settings, active model profiles, and API keys.
4.  **`scan_roots`**: Configured directories that the `wiki_agent.py` monitors for changes.
5.  **`process_logs`**: Audit trail of background process executions, startup times, and errors.

---

## 5. Troubleshooting & Operational Runbooks

### Issue: GPU Out-Of-Memory (OOM) during Step 4
*   **Symptom**: The chat server (`:8081`) or embedding server (`:8080`) crashes immediately after startup, or the system becomes highly unresponsive.
*   **Cause**: The allocated context window (`n_ctx`) or model size exceeds available VRAM.
*   **Resolution**:
    1.  Open the Navigation Station (Step 11) or AI Configuration (Step 12).
    2.  Navigate to the **Model Selector / Hardware** panel.
    3.  Reduce the **Load Context** size (e.g., from `32768` to `16384` or `8192`).
    4.  If sharing a single GPU, ensure the embedding model is lightweight (e.g., a 384-dimensional or 768-dimensional model) to leave headroom for the chat model.

### Issue: Infinite Loop / Chat Hangs
*   **Symptom**: Chat queries spin indefinitely without returning a response.
*   **Cause**: The chat completion endpoint is misconfigured to point to the RAG API gateway (`http://localhost:8090/v1`) instead of the underlying chat server (`http://localhost:8081/v1` or LM Studio).
*   **Resolution**:
    1.  Run Step 14 (Stop / kill all) to terminate hanging processes.
    2.  Launch Step 11 (Navigation Station) and open the **AI Configuration** tab.
    3.  Verify that the active provider is set to **LM Studio** (port `1234`), **Ollama** (port `11434`), or **Local Llama** (port `8081`).
    4.  Ensure the RAG gateway is *only* used by external IDEs, not by the internal chat panels.

*Deep Dive: 155 match(es) · inventory 80 · used 4 · forced 0 · missing 2 · 29,250 chars (79% of 11,294)*

#### Sources

- **deep_dive** (16.80) — `D:\Spock-Onboarding\deep_dive.py`
- **configure_ai** (14.04) — `D:\Spock-Onboarding\spock_shell\configure_ai.py`
- **llm_client** (13.70) — `D:\Spock-Onboarding\llm_client.py`
- **steps** (12.02) — `D:\Spock-Onboarding\spock_bringup_menu\steps.py`
