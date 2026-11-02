# Spock Ask AI — 20260831-133404

## You

Please give a detailed breakdown of Spock-Engineering-Maintenance / 1 Maintenance. Describe all options, and usage.

## Computer

Based on the provided codebase corpus, here is a detailed technical breakdown of the **Spock-Engineering-Maintenance** mini-app, focusing specifically on the **1 Maintenance** option.

---

### 1. Architectural Context & Entry Point

The **Spock-Engineering-Maintenance** mini-app is designed to manage wiki ingestion, database maintenance, and system health probes. 

* **Entry Point:** `D:\Spock-Onboarding\spock_maintenance.py`
  This script initializes the Qt application and launches the main window:
  ```python
  from EngineeringDeck.maintenance_app import EngineeringMaintenanceWindow
  from spock_shell.qt_app import create_app

  def main() -> int:
      app = create_app(sys.argv)
      win = EngineeringMaintenanceWindow()
      win.show()
      return app.exec()
  ```
* **Main Window:** `D:\Spock-Onboarding\EngineeringDeck\maintenance_app.py`
  The `EngineeringMaintenanceWindow` inherits from `SuiteShellWindow` and defines the navigation steps:
  ```python
  def nav_steps(self) -> Sequence[NavItem]:
      return [
          ("Home", self.show_home),
          ("1 Maintenance", self._show_maintenance),
          ("2 Ship Computer DB Health", self._show_db_health),
          ("-----", None),
          ("Exit", self.close),
      ]
  ```

When a user clicks **1 Maintenance**, the application calls `self._show_maintenance()`, which displays the center panel widget `self._hub`. This widget is an instance of `WikiMaintenancePanel` imported from `wiki_maintenance.py`.

---

### 2. Detailed Breakdown of "1 Maintenance" (`WikiMaintenancePanel`)

*Note: While `D:\Spock-Onboarding\wiki_maintenance.py` (63,764 characters) is present in the workspace inventory, its full source code was not retrieved in the current context window. However, its options, usage, and underlying mechanics are clearly mapped out by its integration with `maintenance_app.py`, `db_maintenance.py`, `wiki_agent.py`, and the system's database schema.*

The **1 Maintenance** panel serves as the primary administrative console for the local knowledge base. It manages the lifecycle of documents ingested into the ship's computer database (`ship_computer.db`).

#### Core Options & Functionality

1. **Wiki Ingestion & Scan Control**
   * **Purpose:** Controls the background execution of the Wiki Agent (`wiki_agent.py` / `spock_wiki_adapter`).
   * **Usage:** Allows engineers to trigger a manual "Wiki Scan" to crawl configured wiki directories or endpoints, parse Markdown/text files, and queue them for processing.
   * **Visuals:** Typically displays a live log output or progress indicator showing which files are currently being scanned, updated, or skipped.

2. **Database Maintenance & Cleanup (via `db_maintenance.py`)**
   * **Purpose:** Performs low-level SQLite operations on `ship_computer.db` to prevent corruption and optimize query performance.
   * **Usage:**
     * **Vacuum Database:** Reclaims unused space and defragments the SQLite file.
     * **Prune / Purge Documents:** Removes orphaned document chunks, old revisions, or files marked for deletion.
     * **Re-index FTS5:** Rebuilds the Full-Text Search (FTS5) virtual tables to ensure search queries remain fast and accurate.

3. **Agent Queue Management**
   * **Purpose:** Manages the `agent_queue` table in the database, which holds documents waiting to be embedded or processed by the RAG pipeline.
   * **Usage:**
     * **View Queue Status:** Displays the number of pending, processing, and failed items.
     * **Clear / Reset Queue:** Allows engineers to purge stuck tasks or retry failed ingestion jobs.

4. **Re-embedding & Model Migration (aligned with Bringup Step 15)**
   * **Purpose:** Prepares the database when switching embedding models (e.g., changing the model running on the `:8080` llama-server).
   * **Usage:** Clears existing vector embeddings from the database while **preserving the raw text documents**. This avoids having to re-download or re-crawl the entire wiki when changing models; the system simply recalculates the vectors using the new model.

---

### 3. Usage Workflow

An engineer typically uses the **1 Maintenance** panel during the following scenarios:

1. **Initial Onboarding / Ingestion:**
   * After setting up the environment, the engineer navigates to **1 Maintenance** to run the initial Wiki Scan, populating `ship_computer.db` with the raw documentation.
2. **Model Upgrades:**
   * If the embedding model is changed, the engineer uses the **Re-embed** option to wipe old vectors and trigger a clean re-indexing pass against the active embeddings endpoint (typically `http://localhost:8080/embeddings`).
3. **Troubleshooting Search / RAG Failures:**
   * If the "Ask AI" panel or MCP tools return stale or corrupted results, the engineer uses the **Database Maintenance** tools to rebuild search indexes, clear the agent queue, or vacuum the database.

---

### 4. Contrast: "1 Maintenance" vs. "2 Ship Computer DB Health"

To avoid confusion, it is important to understand how **1 Maintenance** differs from its sister tab, **2 Ship Computer DB Health** (`ShipComputerHealthPanel`):

| Feature | **1 Maintenance** (`WikiMaintenancePanel`) | **2 Ship Computer DB Health** (`ShipComputerHealthPanel`) |
| :--- | :--- | :--- |
| **Primary Focus** | Document ingestion, wiki scanning, and database modification/cleanup. | Live system diagnostics, hardware planning, and read-only statistics. |
| **Key Actions** | Run Wiki Scan, Clear Queue, Re-embed, Vacuum DB. | Run `spock_health`, Run `spock_status`, Check `llmfit` GPU compatibility. |
| **Underlying Engine** | `wiki_agent.py`, `db_maintenance.py`. | MCP tools (`mcp_spock_server.py`), `psutil` process discovery. |
