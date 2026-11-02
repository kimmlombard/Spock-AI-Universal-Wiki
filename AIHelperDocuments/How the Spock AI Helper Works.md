ℹ️ Scoped to D:\Spock-Onboarding\AIHelperDocuments (*-HELPER.md). Chat LLM required; embeddings optional. Ask how the Spock suite works. For outside topics use Brave Search / Ask Leo.

👤 You:  
How does Spock AI Helper work?

ℹ️ Embeddings reachable (http://localhost:8080/embeddings) — optional RAG bonus.

ℹ️ Streaming answer…

🤖 Spock:  
Based on the provided documentation, here is a detailed explanation of how the **Spock AI Helper** and the broader **Spock-Onboarding** suite work, including their components, ports, databases, and interoperability.



---



### 1. How the Spock AI Helper Works

The **Spock AI Helper** (also referred to as the "Spock-UIEG-KnowledgeBase" assistant) is a standalone, lightweight PyQt6 application designed to run with zero external dependencies. It is launched via `helper_main.py` or its entry alias `spock_uieg.py`.



* **Background Docs Server:** It starts a background documentation server (`DocsServer`) serving a pre-built site (from the `site/` directory built using `mkdocs build`) and automatically opens a web browser to the documentation URL.

* **PyQt6 GUI:** It launches a desktop GUI window (`ChatAIHelperWindow` / `AIHelperDialog`) using PyQt6.

* **LLM Integration & RAG-lite:** It connects to a Chat LLM client (such as a configured provider or a local `llama-server` running on port **8081**). It retrieves local Markdown documentation, constructs a context-rich prompt, and executes an asynchronous HTTP request to the server.

* **Search & Embeddings:** It utilizes hybrid search (`hybrid_search`) and embeddings validation (`embeddings_endpoint_ok`) from the `WarpCore.search` module, querying against the ship's computer database (`SHIP_COMPUTER_DB`).
  
  

---



### 2. Suite Components & Workflow



#### **Bootstrap & Onboarding**

The **Spock Onboarding** application is a Retrieval-Augmented Generation (RAG) and hardware assessment tool.

* **RAG API Server (`rag_api_server.py`):** An OpenAI-compatible RAG HTTP API built using only the Python standard library. It serves the Web UI and handles AI requests using a model identified as `"spock-ships-computer"`.

* **Web UI Frontend (`index.html` & `app.js`):** A browser-based interface ("Spock — Ask AI") that allows users to interact with the AI, filter files by path/extension, and save transcripts as Markdown.

* **Spock Scanner Core (`spock_scanner_core.py`):** Performs hardware scans and assessments.
  
  

#### **Orchestrator & Navigation (Spock-Navigation-Station)**

Launched via `spock_navigation.py`, this is the primary desktop GUI orchestrator built on PyQt6. It guides users through an 8-step pipeline:

1. **Home:** Displays markdown-rendered helper documentation.

2. **1 Hardware:** Automatically triggers a hardware scan (CPU, RAM, GPU detection) to populate specifications.

3. **2 HF Models:** Queries the Hugging Face Hub for compatible GGUF models based on the hardware profile.

4. **3 Launch:** Manages local `llama-server` instances (embeddings and chat).

5. **4 Configure Spock AI:** A tabbed configuration panel (`ConfigureAiPanel`) to manage embedding profiles, MCP settings, and the RAG API server.

6. **5 Spock Status:** Probes active endpoints to verify system readiness.

7. **6 Run Wiki Scan:** Launches the `wiki_agent.py` background worker to ingest local documentation and update the vector database.

8. **7 Ship's Logs:** Displays a tabbed view of the SQLite database tables.

9. **8 Run Ask AI:** Opens the local chat interface (`AskAiPanel`) to query the ingested knowledge base using hybrid search.
   
   

#### **Engineering & Maintenance**

Launched via `spock_maintenance.py`, this PyQt6-based console maintenance suite manages wiki ingestion, database maintenance, and system health probes.

* **1 Maintenance (`WikiMaintenancePanel`):** Serves as the administrative console for the local knowledge base. It controls the Wiki Agent (`wiki_agent.py`), performs SQLite database maintenance (Vacuum, Prune, Re-index FTS5 via `db_maintenance.py`), and manages the agent queue.

* **2 Ship Computer DB Health (`ShipComputerHealthPanel`):** Serves as a diagnostic hub for the database. It executes Model Context Protocol (MCP) tools *in-process* by dynamically loading the server script (`mcp_spock_server.py`) to bypass network overhead. It features 7 diagnostic tabs (including Overview and `spock_health`).
  
  

#### **Science & Enterprise**

* **Insufficient Context:** The provided documentation does not contain details regarding "Science" or "Enterprise" components. For information on these modules, please use the in-app **Brave Search** or **Ask Leo** for outside help.
  
  

#### **UIEG**

* **UIEG** refers to the entry point alias `spock_uieg.py` and the **Spock-UIEG-KnowledgeBase** which provides the shared Chat AI Helper GUI interface over the `AIHelperDocuments/` directory.
  
  

---



### 3. Ports & SQLite Databases



#### **Network Ports**

* **Port `8080`:** Dedicated strictly to the local embedding `llama-server`.

* **Port `8081`:** Dedicated to the local chat `llama-server`.

* **Port `8090`:** The Spock RAG API `/health` endpoint.

* **Port `8765`:** The local MCP adapter.

* **Port `8082`:** The `--ui-mcp-proxy` port.
  
  

#### **SQLite Databases**

* **`SHIP_COMPUTER_DB` (`ship_computer.db`):** The central database of the suite. Settings are persisted here via `WarpCore.settings_store`. It contains several key tables:

* `documents`: Stores ingested files and their generated vector embeddings.

* `captains_log`: Stores system events and logs.

* `agent_queue`: Holds tasks and documents waiting to be processed.

* `quarantine`: Holds quarantined files.
  
  

---



### 4. Interoperability

The suite achieves interoperability through several shared mechanisms:

* **Shared Database:** All mini-apps (`spock_navigation.py`, `spock_maintenance.py`, `helper_main.py`) read and write to the same SQLite database (`ship_computer.db`).

* **Shared Library (`WarpCore`):** The core library path is ensured on `sys.path` during bootstrap, allowing all components to share search, settings, and database utilities.

* **Standardized APIs:** The frontend, backend, and desktop panels communicate using OpenAI-compatible HTTP APIs and standard JSON payloads.

* **In-Process MCP Execution:** To avoid network overhead, diagnostic tools dynamically load and execute MCP tools directly within the running Python process rather than spawning external network requests.
