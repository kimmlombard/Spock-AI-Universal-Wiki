# Spock Ask AI — 20260831-132557

## You

Please give a detailed breakdown of Spock-Navigation-Station / Exit. Describe all options, and usage.

## Computer

A detailed breakdown of the **Spock-Navigation-Station** application, its architecture, its 8-step workflow, and the mechanics of its **Exit** functionality is provided below.

---

### 1. Architectural Overview & Launch Flow

The **Spock-Navigation-Station** is a PyQt6-based desktop application designed as a comprehensive control console for managing local hardware scanning, Hugging Face model acquisition, server orchestration, and RAG (Retrieval-Augmented Generation) interactions.

#### File-Level Entry Points
* **Standalone Entry Point:** `D:\Spock-Onboarding\spock_navigation.py`
  This script bootstraps the environment, ensures the shared `WarpCore` library is on the path, and starts the Qt application loop:
  ```python
  def main() -> int:
      app = create_app(sys.argv)
      win = NavigationStationWindow()
      win.show()
      return app.exec()
  ```
* **Main Window Implementation:** `D:\Spock-Onboarding\NavigationStation\app.py`
  Defines the `NavigationStationWindow` class, which inherits from `SuiteShellWindow` (the shared base shell window providing the left-nav layout, right-hand tools dock, and theme support).

---

### 2. The 8-Step Workflow (Left-Nav Options)

The left navigation panel defines a sequential, structured pipeline for onboarding and running the local AI assistant. The steps are defined in `NavigationStationWindow.nav_steps()`:

```python
def nav_steps(self) -> Sequence[NavItem]:
    return [
        ("Home", self.show_home),
        ("1 Hardware", self._show_hardware),
        ("2 HF Models", self._show_models),
        ("3 Launch", self._show_launch),
        ("4 Configure Spock AI", self._show_configure),
        ("5 Spock Status", self._show_status),
        ("6 Run Wiki Scan", self._show_run),
        ("7 Ship's Logs", self._show_ships_logs),
        ("8 Run Ask AI", self._show_ask_ai),
        ("-----", None),
        ("Exit", self.close),
    ]
```

#### Step-by-Step Breakdown:
1. **Home:** Displays the markdown-rendered helper documentation loaded from `AIHelperDocuments/Spock-Navigation-Station-HELPER.md`.
2. **1 Hardware:** Triggers an automatic hardware scan (CPU, RAM, GPU detection) via `QTimer.singleShot` to populate the system's hardware specifications.
3. **2 HF Models:** Allows querying the Hugging Face Hub for compatible GGUF models based on the scanned hardware profile.
4. **3 Launch:** Manages the execution of local `llama-server` instances (typically port `:8080` for embeddings and `:8081` for chat) using the `LlamaServerManager`.
5. **4 Configure Spock AI:** A tabbed configuration panel (`ConfigureAiPanel` from `spock_shell.configure_ai`) to manage embedding profiles, MCP (Model Context Protocol) settings, and the RAG API server.
6. **5 Spock Status:** Probes active endpoints (RAG API, MCP adapter, and `llama-server` instances) to verify system readiness.
7. **6 Run Wiki Scan:** Launches the `wiki_agent.py` background worker to ingest local documentation and update the vector database.
8. **7 Ship's Logs:** Displays a tabbed view of the SQLite database (`ship_computer.db`), including Captain's Logs, Agent Queues, and Document tables.
9. **8 Run Ask AI:** Opens the local chat interface (`AskAiPanel`) to query the ingested knowledge base using hybrid search.

---

### 3. The "Exit" Option & Lifecycle Management

Exiting the **Spock-Navigation-Station** involves multiple layers of cleanup to ensure that background processes (such as local LLM servers, RAG APIs, and MCP adapters) do not become orphaned.

#### Triggering the Exit
The exit routine can be initiated in three ways:
1. Clicking the **"Exit"** item at the bottom of the left-nav panel (which calls `self.close()`).
2. Clicking the standard OS window close button (**X** in the top-right corner).
3. Being terminated by a parent orchestrator (e.g., `Spock-UIE-Wiki-KB` or `Spock Bringup Menu`).

#### Exit Mechanics & Cleanup Sequence

When `self.close()` is called, the Qt runtime triggers a `closeEvent`. The application performs the following lifecycle operations:

##### A. Profile Preservation & Save Prompts
During initialization, the window registers a single-shot timer to offer profile loading:
```python
QTimer.singleShot(0, self._offer_profile_load)
```
Upon exit, if the user has modified active configurations (such as switching embedding models, changing ports, or toggling MCP tools), the application prompts the user to save these settings to a named profile in `ship_computer.db` using `prompt_save_profile` or `save_profile_interactive`.

##### B. Server & Process Termination
The Navigation Station manages background processes through its `server_manager` (`LlamaServerManager`) and `rag_api_server` (`RagApiServer`). 
* **In-Process Servers:** If the RAG API was hosted in-process, it is stopped directly.
* **Spawned Subprocesses:** If background servers were spawned as independent processes (e.g., via `_start_rag_api.py` or `llama-server`), the application attempts to terminate them.

##### C. Orchestrated Process Reaping (Parent-Child Cleanup)
If the Navigation Station was launched from the **Lite Orchestrator** (`Orchestrator\app.py`) or the **Bringup Menu** (`spock_bringup_menu\app.py`), the parent window monitors the Navigation Station's process. 

When the parent window is closed, it executes a recursive process tree termination to ensure no `llama-server` or Python subprocesses remain active:

```python
def _terminate_process_tree(pid: int, timeout: float = 8.0) -> None:
    """Terminate pid and descendants (llama-server children of a suite script)."""
    if psutil is None:
        try:
            os.kill(pid, 15)
        except OSError:
            pass
        return
    try:
        parent = psutil.Process(pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return
    kids = parent.children(recursive=True)
    for child in kids:
        try:
            child.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    try:
        parent.terminate()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    _, alive = psutil.wait_procs(kids + [parent], timeout=timeout)
    for proc in alive:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
```

This ensures that exiting the suite cleanly tears down:
1. The PyQt6 GUI process.
2. The local embedding server (`:8080`).
3. The local chat server (`:8081`).
4. The Spock RAG API server (`:8090`).
5. The Spock MCP HTTP adapter (`:8765`).

---

### 4. Usage Scenarios

| Execution Mode | Launch Command | Exit Behavior |
| :--- | :--- | :--- |
| **Standalone** | `python spock_navigation.py` | Closes the GUI; prompts to save the active profile; shuts down in-process servers. |
| **Orchestrated (Suite)** | `python Spock-UIE-Wiki-KB.py` | Launched as a subprocess. Closing the main orchestrator window automatically reaps the Navigation Station and all its child LLM processes. |
| **Onboarding Menu** | `python -m spock_bringup_menu` | Launched via Step 11 ("Navigation"). Step 14 ("Stop / kill all") or Step 16 ("Exit") in the menu will forcefully terminate the station and its servers. |
