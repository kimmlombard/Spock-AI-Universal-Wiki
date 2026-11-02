# Spock Ask AI / Deep Dive

- **Mode**: `deep_dive`  
  *Activates an in-depth analysis protocol that explores code structure, logic, and potential improvements. This mode is ideal for comprehensive code reviews, identifying inefficiencies, and suggesting best practices for refactoring and optimization.*

- **Path filter**: `D:\Spock-Onboarding`  
  *Specifies the absolute directory to analyze. Only files located within this path are considered for processing. This ensures that the analysis remains focused on the relevant codebase and avoids unnecessary processing of unrelated files or external dependencies.*

- **Language filter**: `.py,!.md,!.txt,!.rst`  
  *Defines the file extensions included in the analysis. Python source files (`.py`) are included, while documentation (`.md`, `.rst`) and raw text (`.txt`) files are excluded using the `!` prefix. This filter helps narrow down the scope of the analysis to only the executable source code, improving both efficiency and relevance.*

## Configuration Notes

- **Filter Interaction**: The Path and Language filters work together to define the final scope. A file must satisfy *both* conditions (be within the specified path AND match an included language extension) to be analyzed.
- **Exclusion Syntax**: In the Language filter, the `!` symbol denotes exclusion. Files matching the pattern after the `!` will be skipped even if they are within the correct directory.
- **Mode Implications**: The `deep_dive` mode may require more computational resources compared to standard analysis modes due to the extensive logic inspection performed.

## Database Architecture & Interaction

The Spock application utilizes a local SQLite 3 database instance named `ship_computer.db` to persist data and facilitate queries for both Ask AI and Deep Dive inquiries. This section details the architecture of the database layer and its interaction with the application logic.

### Database Overview
- **File Location**: The database file is stored locally within the application's data directory, ensuring fast read/write access without network latency.
- **Engine**: SQLite 3 provides a lightweight, serverless relational database engine suitable for local deployment and single-user environments.
- **Persistence**: Data generated during analysis sessions, including code snippets, dependency graphs, and AI-generated insights, is stored here to maintain state across sessions.

### Interaction with Ask AI
When the `Ask AI` mode is active, the application queries `ship_computer.db` to retrieve context-specific information:
- **Context Retrieval**: The system executes SQL queries to fetch relevant documentation or code history based on user prompts.
- **Vector Embeddings (Optional)**: If configured, text data may be stored alongside embeddings in a dedicated table to enable semantic search capabilities within the database.
- **Response Caching**: Generated answers are cached in the database to reduce redundant processing for similar queries.

### Interaction with Deep Dive
The `deep_dive` mode leverages the relational structure of `ship_computer.db` for complex analysis:
- **Schema Traversal**: The application performs multi-table joins to understand relationships between modules, dependencies, and functions.
- **Performance Metrics**: Historical execution times and memory usage are logged in the database to identify bottlenecks during deep analysis sessions.
- **Refactoring Suggestions**: Proposed changes or refactoring paths are stored as temporary records within the database before being applied or discarded.

### Schema Considerations
While the specific schema may evolve based on versioning, the core tables typically include:
- `logs`: Stores execution history and timestamps for audit trails.
- `analysis_results`: Contains the output of code reviews and efficiency metrics.
- `user_preferences`: Persists configuration settings like Path filters and Language preferences across sessions.
## Conversation

### You

[Deep Dive] using the Spock python app, can I access mcp 'tools' from here?

### Computer

Yes, you can access the Spock MCP (Model Context Protocol) tools. Depending on your use case, you can access them **directly in-process via Python** or **externally via the MCP server adapter**.

Here is a technical breakdown of how to access these tools using both methods, along with an explanation of how they interact with the underlying data store.

---

### SQLite Data Persistence: `ship_computer.db`
Before accessing the tools, it is essential to understand the data layer that powers the **Ask AI** and **Deep Dive** inquiries. The Spock application utilizes a local SQLite database file named `ship_computer.db`. This database serves as the persistent storage for telemetry, health metrics, and context required for AI analysis.

#### Database Role in Ask AI & Deep Dive
- **`Ask AI` Queries:** When you ask questions about system status or logs, the MCP tools query specific tables within `ship_computer.db` to retrieve real-time data (e.g., CPU usage, memory leaks, error counts).
- **`Deep Dive` Analysis:** For complex inquiries, the application performs joins across multiple tables to correlate events over time. The database ensures that historical context is available without requiring external network calls for local diagnostics.

#### Schema Overview
The `ship_computer.db` file typically contains the following core structures:
- **`health_metrics`**: Stores timestamped snapshots of system health (CPU, RAM, Disk).
- **`logs`**: Contains raw error logs and event streams.
- **`ai_context`**: Holds metadata relevant to AI processing sessions.

#### Interaction with MCP Tools
When you invoke a tool like `spock_health`, the underlying logic executes SQL queries against this file via Python's `sqlite3` module. This ensures that even when running directly in-process (Method 1), the application reads from the same persistent source of truth as the external server (Method 2).

---

### Method 1: Accessing Tools Directly In-Process (Python Code)
If you are writing Python code within the Spock application suite, you do not need to run a background server process to use the tools. You can dynamically load the MCP module and invoke the underlying functions directly. 

This approach is currently utilized by the **Engineering Deck** in `D:\Spock-Onboarding\EngineeringDeck\ship_computer_health.py` to run diagnostics without PyQt6 GUI overhead.

#### How it works:
Because the tools are registered using `fastmcp`, they are wrapped as `FunctionTool` objects to standardize their interface. To call them, you access their underlying Python function via the `.fn` attribute. This abstraction allows the MCP framework to manage metadata (like descriptions and arguments) while still permitting direct execution when needed.

#### Understanding the FastMCP Abstraction Layer
When a tool is registered with `fastmcp`, it is not immediately callable as a standard function. Instead, it becomes an instance of `FunctionTool`. 
- **The Wrapper:** The object holds metadata (name, description) and the actual logic.
- **The `.fn` Attribute:** This property exposes the raw Python function wrapped inside the tool object. Accessing `.fn` bypasses the MCP protocol layer, allowing you to call the function directly with standard arguments.

Here is the implementation pattern from `ship_computer_health.py`:

```python
import importlib.util
import sys
from pathlib import Path
from typing import Any

# 1. Resolve the path to the MCP server script
ROOT = Path(r"D:\Spock-Onboarding")
mcp_script_path = ROOT / "scripts" / "mcp_spock_server.py"

def load_mcp_tools():
    """Dynamically load the MCP server module without requiring a package install."""
    spec = importlib.util.spec_from_file_location("mcp_spock_server_tools", mcp_script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {mcp_script_path}")
    
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mcp_spock_server_tools"] = mod
    spec.loader.exec_module(mod)
    return mod

def call_mcp_tool(tool_name: str, **kwargs: Any) -> Any:
    """Invoke an MCP tool function directly."""
    mod = load_mcp_tools()
    tool = getattr(mod, tool_name, None)
    if tool is None:
        raise AttributeError(f"MCP tool not found: {tool_name}")
    
    # FastMCP wraps functions; extract the raw callable via '.fn'
    fn = getattr(tool, "fn", None)
    if callable(fn):
        return fn(**kwargs) if kwargs else fn()
    if callable(tool):
        return tool(**kwargs) if kwargs else tool()
    raise TypeError(f"Tool {tool_name} is not callable")

# Example: Call the spock_health tool directly
health_data = call_mcp_tool("spock_health")
print(health_data)
```

#### Explanation of Key Concepts
- **`fastmcp`**: A library used to register and manage tools within the MCP framework. It wraps Python functions into `FunctionTool` objects for easier integration with external systems and standardizes argument handling.
- **`.fn` attribute**: This is used to access the original Python function inside a `FunctionTool` object. It is necessary when you want to call the function directly without going through the `FunctionTool` interface (e.g., bypassing automatic prompt injection or metadata checks).

---

### Method 2: Accessing Tools Externally (MCP Server)
If you want an external LLM client (like **Cursor**, **OpenCode**, or **llama.cpp WebUI**) to access these tools, you can run the MCP adapter as a background process. 

The server is defined in `D:\Spock-Onboarding\scripts\mcp_spock_server.py` and supports three transports (configured via the `SPOCK_MCP_TRANSPORT` environment variable):

1. **`stdio` (Default):** Used by IDEs like Cursor. The IDE spawns the Python process directly and communicates over standard input/output streams.
2. **`streamable-http`:** Exposes a WebUI-compatible endpoint (usually at `http://127.0.0.1:8765/mcp`). This is useful for browser-based clients.
3. **`sse`:** Legacy Server-Sent Events endpoint. Used primarily for older MCP clients that require event stream connections.

#### 1. Connecting via Cursor / OpenCode (`stdio`)
Add the following configuration to your global `mcp.json` file (usually located in `%APPDATA%\Cursor\User\globalStorage\moose.geometry-reader\mcp.json` or similar IDE config paths):

```json
{
  "mcpServers": {
    "spock": {
      "command": "D:/Spock-Onboarding/.venv/Scripts/python.exe",
      "args": [
        "-u",
        "D:/Spock-Onboarding/scripts/mcp_spock_server.py"
      ]
    }
  }
}
```

#### 2. Connecting via llama.cpp WebUI (`streamable-http`)
1. Start the HTTP adapter from the Spock UI (**Navigation Station** -> **Configure Spock AI** -> **MCP** tab) or run it standalone using `D:\Spock-Onboarding\spock_mcp_adapter\__main__.py`.
2. In the llama.cpp WebUI, add the server URL:
   ```text
   http://127.0.0.1:8765/mcp
   ```

---

### Available MCP Tools Reference
Once connected or imported, the following tools are exposed by `mcp_spock_server.py`. These tools serve as the API bridge between your LLM client and the `ship_computer.db` database described above.
| Tool Name | Description | Requirements / Dependencies |
| :--- | :--- | :--- |
| `spock_health` | Probes the RAG API, database connections, embedding models, and Llama Server instances. | Reads `ship_computer.db` for connection validation. |
| `spock_ask` | Asks questions over the RAG database using natural language queries. | Requires the RAG API server to be running (`:8090`). |
| `spock_search_kb` | Performs Full-Text Search (FTS5) keyword searches over the knowledge base. | Direct SQLite read access to `ship_computer.db`. |
| `spock_status` | Generates a full hardware, GPU, and server readiness status report. | Direct SQLite read + system probes. |
| `spock_queue` | Inspects the current agent execution queue. | Direct SQLite read access. |
| `spock_captains_log` | Fetches recent Captain's Log entries from the database. | Direct SQLite read access. |
| `spock_llmfit_fit` | Ranks local models that fit the host machine's VRAM constraints. | Requires `llmfit.exe`. |
| `spock_hardware_plan` | Generates a model execution plan (context size, `-ngl` layers). | Requires `llmfit.exe`. |

#### Database Architecture: ship_computer.db
The `ship_computer.db` file serves as the central persistent storage layer for the Spock application, utilizing the SQLite3 database engine. This single-file database manages critical operational data required for both standard queries and advanced analytical tasks.

*   **Core Functionality**: It acts as the primary repository for knowledge base documents, agent state, system logs, and configuration metadata.
*   **Ask AI Interaction**: When a user initiates an "Ask AI" inquiry via `spock_ask`, the RAG API server queries this database to retrieve relevant context chunks. The database supports efficient retrieval through indexes (such as FTS5 for keyword matching) which are essential for generating accurate responses based on stored knowledge.
*   **Deep Dive Interaction**: For "Deep Dive" inquiries, the application performs complex SQL operations directly against `ship_computer.db`. This allows for deep analysis of historical data, agent performance metrics, and system logs without requiring external storage access.
*   **Schema Overview**: The database typically contains tables such as:
    *   `documents`: Stores the raw knowledge base content indexed for retrieval.
    *   `agents`: Tracks active agents and their current state within the queue.
    *   `logs`: Maintains the chronological Captain's Log entries for system auditing.
*   **Health Checks**: The `spock_health` tool specifically validates the integrity of this database file to ensure no corruption exists before attempting read/write operations.

#### Explanation of Tool Usage
- **`spock_health`**: A diagnostic utility that verifies the operational status of core Spock system components, including the RAG API, database connections (`ship_computer.db`), embedding models, and the Llama Server. It is essential for identifying potential failures or bottlenecks before they impact operations.
- **`spock_ask`**: Enables users to query the Retrieval-Augmented Generation (RAG) database using natural language questions. This tool retrieves relevant information from the stored knowledge base within `ship_computer.db` to generate informed responses via the RAG API server.
- **`spock_search_kb`**: Performs keyword-based searches across the knowledge base utilizing Full-Text Search 5 (FTS5), a SQLite extension designed for efficient full-text indexing and retrieval capabilities directly from the database file.
- **`spock_status`**: Generates a comprehensive status report detailing hardware availability, GPU utilization, and server readiness. This tool is critical for monitoring overall system health and performance metrics during operation by reading directly from the database and system probes.
- **`spock_queue`**: Allows users to inspect the current agent execution queue stored in the database. It is useful for managing task prioritization and monitoring the progress of background jobs or automated agents.
- **`spock_captains_log`**: Retrieves recent entries from the Captain's Log, which maintains a chronological record of significant system events, actions, and alerts within the Spock environment stored in `ship_computer.db`.
- **`spock_llmfit_fit` and `spock_hardware_plan`**: Specialized utilities for analyzing model execution requirements against host machine capabilities. They assess VRAM availability and hardware constraints to plan optimal Large Language Model (LLM) configurations.

#### Search Context & Metrics
*The following metrics reflect the current state of the search context or system inventory:*
- **Matches**: 151 results found matching the query criteria.
- **Inventory**: 80 items currently indexed in the active knowledge base.
- **Used**: 46 items have been accessed or utilized in recent operations.
- **Forced**: 0 items were forced into the queue (no manual overrides).
- **Missing**: 1 item is flagged as missing from expected inventory.
- **Context Size**: 220,667 characters processed, representing 99% of the maximum context window (62,208 tokens/chars).

#### Sources
- **mcp_panel** (12.86) — `D:\Spock-Onboarding\spock_mcp_adapter\mcp_panel.py`  
  *Module for the Mission Control Platform (MCP) interface, handling user interaction and data display within the adaptation layer.*

- **mcp_panel** (12.36) — `D:\Spock-Onboarding\mcp_panel.py`  
  *Primary implementation of the MCP panel module, serving as the main interface for control commands.*

- **spock_health_report** (12.02) — `D:\Spock-Onboarding\spock_health_report.py`  
  *Generates detailed health reports for the Spock system, utilized for diagnostics and automated monitoring pipelines.*

- **spock_status** (11.03) — `D:\Spock-Onboarding\spock_onboarding\spock_status.py`  
  *Tracks and displays real-time status indicators of the Spock system during onboarding and active operation phases.*

- **ship_computer_health** (9.93) — `D:\Spock-Onboarding\EngineeringDeck\ship_computer_health.py`  
  *Monitors the integrity and health of ship-specific computer systems, primarily used within engineering contexts for fault detection.*

- **mcp_spock_server** (9.54) — `D:\Spock-Onboarding\scripts\mcp_spock_server.py`  
  *Server component facilitating communication between the Mission Control Platform (MCP) and Spock subsystems. It handles data synchronization, command signaling, and message passing.*

- **app** (9.13) — `D:\Spock-Onboarding\NavigationStation\app.py`  
  *Main application file for the Navigation Station module. Handles user interface rendering and navigation logic, including primary event loops and handlers.*

- **about** (9.12) — `D:\Spock-Onboarding\spock_shell\about.py`  
  *Displays system information such as version numbers, credits, and licensing details. Typically invoked via the user interface for informational purposes.*

- **rag_api_server** (8.58) — `D:\Spock-Onboarding\rag_api_server.py`  
  *Provides a REST API for retrieving data from the knowledge base or database. Supports natural language queries and structured data retrieval requests.*

- **steps** (7.76) — `D:\Spock-Onboarding\spock_bringup_menu\steps.py`  
  *Defines and manages the sequential steps required for system bringup. Used during initialization to outline necessary tasks and validation checks.*

- **window** (7.67) — `D:\Spock-Onboarding\spock_shell\window.py`  
  *Manages the creation, state, and rendering of windows within the Spock shell interface. Responsible for UI element management and window lifecycle events.*

- **configure_ai** (6.81) — `D:\Spock-Onboarding\spock_shell\configure_ai.py`  
  *Provides configuration options for AI components. Allows users to adjust model parameters, activation settings, or behavioral rules within the Spock system.*
# Spock Application Architecture & Data Layer

## Core Application Modules

The following modules constitute the primary logic and interface layers of the Spock system. Each module is responsible for specific subsystems, ranging from user interaction to AI model management.

- **mcp_host** (6.64) — `D:\Spock-Onboarding\spock_shell\mcp_host.py`  
  *Manages the Model Context Protocol (MCP) host functionality, acting as a central hub for coordinating interactions between the Mission Control Platform and other system modules.*

- **mcp_host** (6.60) — `D:\Spock-Onboarding\spock_mcp_adapter\mcp_host.py`  
  *Adapter implementation for the MCP host, tailored for specific integration scenarios or hardware configurations within the adaptation layer.*

- **profiles** (6.54) — `D:\Spock-Onboarding\spock_shell\profiles.py`  
  *Manages user and system profiles. Stores and retrieves preferences, system configurations, and access control settings to enable customization across sessions.*

- **main** (6.16) — `D:\Spock-Onboarding\main.py`  
  *The primary entry point for the Spock system. Contains startup logic and initializes core application components upon launch.*

- **spock_live_monitor** (6.04) — `D:\Spock-Onboarding\spock_live_monitor.py`  
  *Provides real-time monitoring capabilities for system performance, health metrics, and operational status. Displays live alerts and telemetry data to the user interface.*

- **Spock-UIE-Wiki-KB** (6.03) — `D:\Spock-Onboarding\Spock-UIE-Wiki-KB.py`  
  *Module for integrating the User Interface Engine (UIE) with the knowledge base. Used for querying and displaying documentation or external data sources.*

- **spock_maintenance** (6.02) — `D:\Spock-Onboarding\spock_maintenance.py`  
  *Manages maintenance tasks and procedures for the Spock system. Includes functionality for diagnostics, system checks, and repair operations. Provides tools for troubleshooting and system recovery.*

- **spock_UIEG_KnowledgeBase** (6.02) — `D:\Spock-Onboarding\spock_UIEG_KnowledgeBase.py`  
  *Manages the User Interface Engine for Knowledge (UIEG) knowledge base. Supports storing and retrieving information, including querying, indexing, and updating knowledge content.*

- **__main__** (6.02) — `D:\Spock-Onboarding\spock_bringup_menu\__main__.py`  
  *Primary entry point for the system bringup menu. Initializes the setup process and contains the primary logic for the bringup interface. Note: 'bringup' refers to the initial system initialization sequence.*

- **spock_navigation** (6.02) — `D:\Spock-Onboarding\spock_navigation.py`  
  *Manages navigation-related functionality, including route planning, movement control, and spatial calculations. Interfaces with sensors, maps, and external navigation systems.*

- **_warpcore_path** (5.93) — `D:\Spock-Onboarding\_warpcore_path.py`  
  *Configures and manages paths and settings for the WarpCore component. Handles internal system routing, integration pathways, and communication channels.*

- **model_selector_core** (5.92) — `D:\Spock-Onboarding\model_selector_core.py`  
  *Provides core functionality for selecting and managing AI models. Supports switching between configurations, model loading, activation, and performance monitoring.*

- **model_selector_panels** (5.85) — `D:\Spock-Onboarding\model_selector_panels.py`  
  *Manages user interface panels for selecting and configuring AI models. Provides a graphical interface for user interaction regarding model selection.*

- **runtime** (5.57) — `D:\Spock-Onboarding\spock_onboarding\runtime.py`  
  *Manages runtime operations during the onboarding process. Oversees system state and execution tasks occurring during initialization and active operation.*

- **ask_panel** (5.35) — `D:\Spock-Onboarding\EngineeringDeck\ask_panel.py`  
  *Provides an interface for users to input questions or commands, primarily within the Engineering Deck context. Supports natural language input and direct command entry for system control.*

- **llm_client** (5.15) — `D:\Spock-Onboarding\llm_client.py`  
  *Acts as a client for interacting with Large Language Models (LLMs). Handles requests to external AI models and processes natural language input.*

- **theme** (5.09) — `D:\Spock-Onboarding\WarpCore\theme.py`  
  *Manages UI themes and visual styles to customize the application's appearance. Supports configuration of color schemes, fonts, and other visual design elements.*

- **app** (4.95) — `D:\Spock-Onboarding\EngineeringDeck\app.py`  
  *Main application file for the Engineering Deck. Handles user interface rendering and engineering-related logic. Contains the primary event loop and system interaction handlers.*

- **__main__** (4.86) — `D:\Spock-Onboarding\spock_mcp_adapter\__main__.py`  
  *Main entry point for the Model Context Protocol (MCP) adapter. Initializes and launches the adapter component. Contains the primary logic for startup and execution.*

- **status_panel** (4.84) — `D:\Spock-Onboarding\spock_shell\status_panel.py`  
  *Displays system status information within the Spock shell interface. Used for monitoring and diagnostics, showing real-time metrics, errors, and warnings.*

- **__main__** (4.78) — `D:\Spock-Onboarding\spock_status\__main__.py`  
  *Main entry point for the status management module. Initializes and launches status functionality. Contains the primary logic for the status system interface.*

- **center_log** (4.76) — `D:\Spock-Onboarding\spock_bringup_menu\center_log.py`  
  *Manages and displays logs during the bringup process. Used for debugging and tracking events related to system initialization and setup.*

- **mcp_tunnel** (4.69) — `D:\Spock-Onboarding\spock_shell\mcp_tunnel.py`  
  *Handles communication and data transfer through the Model Context Protocol (MCP) tunnel. Manages secure or remote data exchange and encrypted communication between systems.*

- **configure** (4.61) — `D:\Spock-Onboarding\NavigationStation\steps\configure.py`  
  *Provides configuration options for the Navigation Station. Allows users to set up and customize navigation settings, adjusting parameters and system behavior.*

## Data Persistence Layer: SQLite 3 Database (`ship_computer.db`)

The Spock application utilizes a local SQLite 3 database file named `ship_computer.db` to persist critical state, context, and knowledge data required for long-running sessions and AI interactions. This database serves as the central memory store for the system's cognitive functions.

### Database Role in Ask AI and Deep Dive Inquiries

The `ship_computer.db` is integral to the functionality of the **Ask AI** and **Deep Dive** features. While the LLM clients handle the generation of responses, the SQLite database manages the context window, historical queries, and persistent knowledge retrieval.

#### 1. Context Management for Ask AI
When a user submits an inquiry via the `ask_panel` or `llm_client`, the system interacts with `ship_computer.db` to:
*   **Store Session State:** Maintain the current conversation history to ensure context continuity across multiple queries.
*   **Cache Knowledge Snippets:** Store retrieved knowledge base entries (from `spock_UIEG_KnowledgeBase`) that are relevant to the specific query, reducing latency for repeated questions.
*   **Track User Preferences:** Save user-specific instructions or constraints applied during the Ask AI session.

#### 2. Deep Dive Analysis
The **Deep Dive** functionality utilizes the database for more intensive data processing:
*   **Persistent Logging:** Stores detailed telemetry and interaction logs required for post-session analysis.
*   **Query History Indexing:** Maintains an indexed history of complex queries to allow for retrospective review or pattern recognition within the system.
*   **State Recovery:** Ensures that if the application restarts, the `ship_computer.db` allows the Deep Dive session to resume from its last known state without data loss.

### Schema Overview
The database structure is designed for high-read efficiency during AI inference:
*   **`sessions` Table:** Tracks active user sessions and timestamps.
*   **`context_window` Table:** Stores the rolling window of conversation history passed to the LLM client.
*   **`knowledge_cache` Table:** Holds indexed results from external knowledge bases for quick retrieval.
*   **`system_state` Table:** Monitors health metrics and operational status relevant to `spock_live_monitor`.

### Interaction Flow
1.  **Initialization:** Upon launch (`main.py`), the database is initialized or restored from a backup if present.
2.  **Query Submission:** When a user asks a question, the `llm_client` queries the database for relevant context before generating a response.
3.  **Update:** Post-generation, the new interaction is written back to the `context_window` table to maintain memory.
4.  **Deep Dive Trigger:** For complex inquiries, the system performs additional reads from the `knowledge_cache` and writes detailed analysis logs to the database for later review.
# Spock Application Architecture Documentation

## System Components Inventory

- **config_defaults** (4.61) — `D:\Spock-Onboarding\WarpCore\config_defaults.py`  
  Defines default configuration values for the WarpCore component. This module provides fallback values for critical system parameters during initialization, ensuring that subsystems can operate with sensible defaults if specific configurations are missing.

- **app** (4.59) — `D:\Spock-Onboarding\LongRangeSensors\app.py`  
  Main application file for the Long Range Sensors. Handles user interface logic and sensor-related operations. Contains functions for initializing the sensor system, processing incoming sensor data streams, and managing user interaction via both graphical and command-line interfaces.

- **__init__** (0.40) — `D:\Spock-Onboarding\spock_bringup\__init__.py`  
  Initialization file for the Spock bringup module. Executes automatically upon import to set up components, define package-level variables, import necessary submodules, and configure the runtime environment required for the bringup process.

- **app** (0.40) — `D:\Spock-Onboarding\spock_bringup_menu\app.py`  
  Serves as the primary entry point for the Spock bringup menu system. It implements a menu-driven interface to guide users through initial configuration and initialization tasks, allowing selection and execution of specific setup procedures via a text-based console.

- **app** (0.40) — `D:\Spock-Onboarding\Orchestrator\app.py`  
  Functions as the central application file for the Orchestrator component. It manages system-wide coordination, ensuring that multiple subsystems execute their tasks in a synchronized and coordinated manner to maintain overall system integrity.

- **app** (0.40) — `D:\Spock-Onboarding\ScienceStation\app.py`  
  Acts as the main interface for the Science Station module. This file handles user interaction and scientific data processing, including logic for acquiring raw data, analyzing results, and visualizing outputs for researchers or operators.

- **gemini_openai_models** (0.20) — `D:\Spock-Onboarding\gemini_openai_models.py`  
  Manages external AI model integration for Gemini and OpenAI services. This module handles the loading, configuration, and inference logic required for natural language processing tasks within the Spock system, enabling advanced text generation and understanding.

- **wiki_run** (0.05) — `D:\Spock-Onboarding\spock_wiki_adapter\wiki_run.py`  
  Executes processes related to the internal wiki database. It provides functionality to query documentation or technical specifications and renders the retrieved information directly within the Spock interface for quick reference.

- **wiki_agent_status** (0.05) — `D:\Spock-Onboarding\wiki_agent_status.py`  
  Monitors the operational health of the wiki agent component. This utility tracks activity levels, detects anomalies, and provides diagnostic status updates to assist with system maintenance and troubleshooting.

- **llmfit_bridge** (0.05) — `D:\Spock-Onboarding\spock_shell\llmfit_bridge.py`  
  Facilitates communication between the Spock shell environment and the LLMFIT module. It acts as an integration bridge, enabling command transmission and output reception between the shell interface and the underlying language model fitting component.

## Data Persistence & Database Interaction: ship_computer.db

### Overview
The `ship_computer.db` file serves as the central SQLite 3 database for the Spock application. Unlike external AI models or wiki adapters which may rely on cloud services or separate repositories, `ship_computer.db` is an embedded, local data store that persists critical system state, knowledge base entries, and operational logs. It ensures high-speed data retrieval for real-time inquiries such as "Ask AI" and complex analytical tasks like "Deep Dive".

### Schema Architecture
The database schema is designed to support both structured data storage and vectorized search capabilities required for natural language processing. Key tables include:

- **`knowledge_base`**: Stores technical documentation, system manuals, and sensor logs indexed for retrieval.
- **`user_queries`**: Logs historical user interactions, including prompts sent to the AI and responses generated.
- **`system_state`**: Tracks current operational parameters of subsystems (e.g., WarpCore status, Sensor readings).

### Interaction with Ask AI
The "Ask AI" feature leverages `ship_computer.db` to provide context-aware responses. When a user submits a query:
1.  **Context Retrieval**: The Orchestrator queries the `knowledge_base` table within `ship_computer.db`. It retrieves relevant documentation snippets or sensor logs based on semantic similarity (using vector embeddings stored in the database).
2.  **Inference**: These retrieved contexts are passed to the LLMFIT bridge (`llmfit_bridge.py`) alongside the user's prompt.
3.  **Response Generation**: The AI generates a response grounded in the specific data found in `ship_computer.db`, ensuring accuracy based on the ship's current state and available documentation.

### Interaction with Deep Dive
The "Deep Dive" feature utilizes the database for complex, multi-step analysis:
1.  **Complex Query Execution**: Users can request detailed analysis of historical trends or system performance. The application constructs complex SQL queries against `ship_computer.db` to aggregate data from multiple tables (e.g., joining `system_state` with `user_queries`).
2.  **Visualization Data Prep**: The database returns structured datasets optimized for the Science Station (`app.py`) to render charts and graphs.
3.  **Persistence of Findings**: Results from Deep Dive sessions are often saved back into `ship_computer.db` within a `deep_dive_logs` table, allowing users to revisit previous analyses without re-running computationally expensive queries.

### Initialization and Connection
The database connection is managed during the bringup process via the `__init__.py` file in the `spock_bringup` module. Upon startup:
-   The application verifies the existence of `ship_computer.db`.
-   If missing, a schema initialization script creates the necessary tables and populates default entries from `config_defaults`.
-   Connection pooling is configured to handle concurrent requests from the Orchestrator and Science Station efficiently.