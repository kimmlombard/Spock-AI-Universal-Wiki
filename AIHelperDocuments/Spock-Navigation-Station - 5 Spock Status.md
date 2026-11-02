# Spock Ask AI — 20260831-130836

## You

Please give a detailed breakdown of Spock-Navigation-Station / 5 Spock Status . Describe all options, and usage.

## Computer

In the **Spock-Navigation-Station** (the primary control GUI for the Spock-UIE-Wiki-KB suite), **"5 Spock Status"** is a critical diagnostic step. It provides a comprehensive, real-time health and readiness assessment of the entire local AI stack. 

This step aggregates probes across multiple distributed services (embedding servers, chat servers, RAG APIs, and Model Context Protocol adapters) to ensure the system is fully operational before executing document ingestion or running queries.

---

### 1. Architectural Overview of the Status Probe
The status check is driven by the backend module `D:\Spock-Onboarding\spock_onboarding\spock_status.py` (Doc 1) and its CLI wrapper `D:\Spock-Onboarding\spock_status\__main__.py` (Doc 16). 

When a user navigates to **"5 Spock Status"** in the Navigation Station, the application executes `probe_spock_status()`, which queries five distinct layers of the system:

```
                     [ Navigation Station GUI ]
                                 │
                     ┌───────────┴───────────┐
                     ▼                       ▼
           [ probe_spock_status() ]  [ spock_ready_last.json ]
                     │
     ┌───────────────┼───────────────┬───────────────┐
     ▼               ▼               ▼               ▼
[RAG API]      [MCP Adapter]   [Embed Server]  [Chat Server]
 (:8090)          (:8765)         (:8080)         (:8081)
```

1. **Embedding `llama-server` (`:8080`)**: Probes the local `llama.cpp` instance dedicated to generating vector embeddings.
2. **Chat `llama-server` (`:8081`)**: Probes the local `llama.cpp` instance dedicated to text generation and instruction-following.
3. **RAG API Server (`:8090`)**: Probes the FastAPI/web server that coordinates document chunking, vector database storage, and hybrid search.
4. **MCP Adapter (`:8765`)**: Probes the Model Context Protocol server that exposes database tools to LLM clients (like Cursor or the llama.cpp WebUI).
5. **Process Discovery**: Scans active system processes to locate running `llama-server` instances and verify their PIDs, ports, and loaded models.

---

### 2. Detailed Breakdown of Probed Components

#### A. The RAG API Probe
* **Target**: `http://127.0.0.1:8090/health` (configurable).
* **Mechanism**: Performs a standard HTTP `GET` request.
* **Verification**: Checks for a `200 OK` response and attempts to parse the returned JSON payload to verify database connectivity.

#### B. The MCP Adapter Probe
* **Target**: `http://127.0.0.1:8765/mcp` (configurable).
* **Mechanism**: Performs an HTTP `OPTIONS` request (CORS preflight check) with specific headers:
  ```python
  headers={
      "Origin": "http://127.0.0.1:8082",
      "Access-Control-Request-Method": "POST",
      "Access-Control-Request-Headers": "content-type,accept",
  }
  ```
* **Verification**: Verifies if the adapter is listening and checks for the presence of the `Access-Control-Allow-Origin` header to ensure cross-origin requests from the llama.cpp WebUI (`:8082`) are permitted.

#### C. The Llama-Server Probes
* **Targets**: `:8080` (Embed) and `:8081` (Chat).
* **Mechanism**: Queries three endpoints on each server:
  1. `/health`: Verifies the server is up and responding.
  2. `/props`: Extracts the loaded model path and the context budget (`n_ctx`) from `default_generation_settings`.
  3. `/slots` or `/v1/models`: Fallback endpoints to extract context size and model names if `/props` is unavailable.

#### D. Process Discovery
* **Mechanism**: Uses `psutil` (if available) to scan active processes.
* **Verification**: Identifies processes running `llama-server` or `mcp_spock_server.py`, matching their command-line arguments to determine their active roles (e.g., identifying which PID is hosting the embedding model vs. the chat model).

#### E. Readiness State File
* **Target**: `spock_ready_last.json` in the installation root.
* **Verification**: Reads the JSON file written by the bringup sequence to check high-level flags:
  * `ui_ready`: Whether the user interface dependencies are satisfied.
  * `full_deps_ok`: Whether the Phase B full dependency tier (extractors, ingest, WebEngine, MCP) is installed.

---

### 3. The Spock Status Report Format
The output of the probe is formatted into a clean, human-readable text block via `format_spock_status_report()` (Doc 1):

```text
Spock Status (spock-status)

API / readiness
  Install root     : D:\Spock-Onboarding
  ui_ready         : True
  servers_ready    : True
  full_deps_ok     : True

RAG API
  URL              : http://127.0.0.1:8090/health
  Reachable        : True (ok)

MCP adapter
  URL              : http://127.0.0.1:8765/mcp
  Reachable        : True (listening (HTTP 204, CORS *))

Llama-server endpoints
  :8080 embed
    Status         : OK
    Port           : 8080
    Model          : bge-large-en-v1.5-q8_0.gguf
    n_ctx          : 8192
    Detail         : ok
  :8081 chat
    Status         : OK
    Port           : 8081
    Model          : Llama-3-8B-Instruct-Q4_K_M.gguf
    n_ctx          : 8192
    Detail         : ok

Discovered llama-server processes
  PID 14204  role=embedding  port=8080  model=bge-large-en-v1.5-q8_0.gguf
  PID 18940  role=chat       port=8081  model=Llama-3-8B-Instruct-Q4_K_M.gguf

Summary
  OK RAG API responding
  OK embedding llama-server :8080
  OK chat llama-server :8081
  OK MCP adapter responding
```

---

### 4. Usage and Execution Options

The status probe can be executed in three ways: through the GUI, via the CLI, or as an automated MCP tool.

#### Option A: GUI Usage (Navigation Station)
1. Launch the Navigation Station: `python spock_navigation.py` (Doc 15).
2. Click **"5 Spock Status"** in the left-hand navigation panel.
3. The center pane displays the formatted status report.
4. *Note:* The GUI automatically resolves ports using `WarpCore.service_endpoints` (Doc 17), which respects environment overrides (like `SPOCK_RAG_PORT` or `SPOCK_EMBED_PORT`) and database configurations.

#### Option B: CLI Usage (`spock_status` & `spock_probe`)
You can run the status probe directly from a terminal. This is useful for headless environments or automated startup scripts.

##### 1. Standard Status Report (`spock_status`)
```bash
python -m spock_status [options]
```
* **Available Options**:
  * `--root <path>`: The installation root directory (defaults to current working directory).
  * `--embed-port <int>`: Port of the embedding `llama-server` (default: `8080`).
  * `--chat-port <int>`: Port of the chat `llama-server` (default: `8081`).
  * `--rag-url <url>`: Full URL to the RAG API health endpoint (default: `http://127.0.0.1:8090/health`).
  * `--mcp-host <ip>`: Host IP of the MCP adapter (default: `127.0.0.1`).
  * `--mcp-port <int>`: Port of the MCP adapter (default: `8765`).
* **Exit Codes**: Returns `0` if all servers are ready; returns `1` if any core service is unreachable.

##### 2. Readiness Probe (`spock_probe`)
A lightweight alternative designed for orchestration scripts (Doc 21):
```bash
python -m spock_probe [--root <path>] [--embed-port <port>] [--chat-port <port>] [--json]
```
* **`--json` flag**: Outputs the raw readiness state as a JSON object instead of formatted text.
* **Exit Codes**:
  * `0`: Both UI and servers are fully ready.
  * `1`: Either UI or servers are ready, but not both.
  * `2`: Neither is ready.

#### Option C: MCP Tool Integration
The status probe is also exposed as an MCP tool named `spock_status` inside `scripts/mcp_spock_server.py` (Doc 23, Doc 28). 
* **Usage**: Any connected MCP client (such as Cursor, VS Code, or the llama.cpp WebUI) can invoke the `spock_status` tool.
* **Execution**: The tool executes the underlying `probe_spock_status()` function and returns the formatted diagnostic report directly to the LLM context or client console.
