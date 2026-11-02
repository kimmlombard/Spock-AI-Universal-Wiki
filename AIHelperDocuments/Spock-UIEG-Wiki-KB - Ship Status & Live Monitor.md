# Spock Ask AI — 20260831-140245

## You

Please give a detailed breakdown of Spock-UIEG-Wiki-KB / Ship Status / Live Monitor. Describe Live Monitor options, and usage.  Define the llama-server instances and option buttons plus the running instances list (grid).

## Computer

An analysis of the codebase reveals that the **Live Monitor** (also referred to as the **Ship Status** window) is a standalone PyQt6-based graphical utility. It provides real-time visibility into the health of the local AI stack, specifically tracking `llama-server` instances, the RAG API, and the Model Context Protocol (MCP) adapter.

Below is a detailed technical breakdown of its architecture, options, usage, and underlying mechanics.

---

### 1. Architectural Context & Entry Points

The Live Monitor is integrated into the `Spock-UIEG-Wiki-KB` suite and can be launched in several ways:
* **Direct CLI Entry**: Run via `python -m spock_live_monitor` or through its alias script `D:\Spock-Onboarding\spock_live_monitor.py`.
* **Bringup Menu**: Triggered as **Step 8 ("Open Live Monitor (Ship Status GUI)")** in the terminal-based bringup menu defined in `D:\Spock-Onboarding\spock_bringup_menu\steps.py`.
* **Orchestration**: Spawned as a separate process by the main suite orchestrator (`D:\Spock-Onboarding\Orchestrator\app.py`).

---

### 2. Live Monitor Options & Usage

The user interface is defined in `D:\Spock-Onboarding\spock_live_monitor\__main__.py` under the `LiveMonitorWindow` class. It features several interactive controls:

* **Stop Monitor / Start Monitor Button**: 
  * Toggles the active state of the background polling timer (`self._timer`).
  * **Visual States**: When running, it displays as green (`#6D9E5A`) with the text "Stop Monitor". When stopped, it turns blue/indigo (`#5C6BC0`) with the text "Start Monitor".
* **Interval Spinbox (`QSpinBox`)**:
  * Configures the polling frequency of the status loop.
  * **Range**: `500 ms` to `5000 ms` (adjustable in steps of `500 ms`).
  * **Default**: `1000 ms`.
* **Run Spock Status Button**:
  * Manually triggers a comprehensive diagnostic probe across the entire system.
  * It executes `run_spock_status_text` (imported from `spock_onboarding.spock_status`) and prints the formatted report directly to the **Live Output** log.
* **Refresh Button**:
  * Instantly forces a refresh of the active `llama-server` instances table without waiting for the next timer tick.

---

### 3. llama-server Instances & Port Layout

The Spock architecture relies on splitting LLM workloads across two distinct local `llama-server` instances to prevent context collision and performance degradation:

1. **Embedding Server (`:8080`)**:
   * **Role**: Dedicated exclusively to generating vector embeddings via the `/embeddings` endpoint.
   * **Warning Hint**: As noted in the UI's hint label: *"Embedding servers are for /embeddings only - chat on that port will be garbled."*
2. **Chat Server (`:8081`)**:
   * **Role**: Dedicated to instruct-based chat and conversational RAG.

---

### 4. The Running Instances List (Grid & Table)

The window displays active processes and system health using two primary visual components:

#### A. The Dynamic Status Grid (`self.monitor_grid`)
The grid is dynamically rebuilt inside `_rebuild_boxes(self, snap)` using a snapshot dictionary retrieved from `get_live_monitor_snapshot()`. 
* It clears out old widgets and generates styled `QFrame` panels (`#24303a`) representing key system sections (e.g., RAG API, MCP, and Llama endpoints).
* Each section displays key-value pairs of status metrics (such as reachability, latency, or loaded models).

#### B. The Active Instances Table (`self.table`)
A `QTableWidget` with 4 columns that lists active `llama-server` processes discovered on the host machine:
* **Role**: Identifies whether the process is acting as an `embedding` or `chat` server. This is determined by inspecting the loaded model path (e.g., checking if it matches known embedding GGUF patterns via `is_embedding_gguf_path`).
* **Model**: Displays the filename of the GGUF model currently loaded into VRAM.
* **Port**: The port the process is listening on (typically `8080` or `8081`).
* **PID**: The operating system Process ID, allowing administrators to track down orphaned processes.

#### C. Live Output Log (`self.log`)
A read-only `QTextEdit` terminal view (`#0f1419`) at the bottom of the window that captures stdout, probe logs, and detailed error messages when endpoints become unreachable.

---

### 5. Code Flow & Polling Loop

The window's lifecycle and update loop operate as follows:

```
[LiveMonitorWindow.__init__]
       │
       ├──> Starts QTimer (Default: 1000ms)
       │
       └──> [_update_monitor()]
                 │
                 ├──> Calls get_live_monitor_snapshot()
                 │
                 ├──> Calls _rebuild_boxes(snap) to redraw Grid
                 │
                 └──> [_refresh_instances()]
                           │
                           ├──> Calls discover_llama_servers()
                           │
                           └──> Populates QTableWidget (Role, Model, Port, PID)
```

1. **Initialization**: The window sets up its dark theme stylesheet, starts the `QTimer`, and immediately triggers the first update.
2. **Polling**: Every timer timeout calls `_update_monitor()`, which fetches a live snapshot of the system.
3. **Process Discovery**: `_refresh_instances()` uses `discover_llama_servers()` (which leverages `psutil` under the hood) to scan the operating system's process tree for active `llama-server` executables, extracting their command-line arguments to determine their ports, loaded models, and PIDs.
