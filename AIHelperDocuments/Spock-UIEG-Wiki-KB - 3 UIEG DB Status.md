# Spock Ask AI — 20260831-134932

## You

Please give a detailed breakdown of Spock-UIEG-Wiki-KB / 3 UIEG DB Status. Describe all options, and usage.  Define the tabs and option buttons for each.

## Computer

Based on the codebase corpus, the **"3 UIEG DB Status"** panel is the administrative and maintenance hub of the **Spock-UIEG-KnowledgeBase** mini-app (located at `D:\Spock-Onboarding\LongRangeSensors\app.py`). 

This panel is implemented in **`D:\Spock-Onboarding\LongRangeSensors\uieg_status.py`** as the `UiegStatusPanel` class. It provides a dedicated interface to monitor, backup, restore, optimize, and reset the external capture database (**`uieg_capture.db`**), which stores data ingested from GitHub repositories (`CHANNEL_REPO`) and website crawls (`CHANNEL_CRAWL`).

---

### 1. Global Layout & Controls
The panel features a clean, Spock-themed layout with the following global elements:
*   **Title**: `3 UIEG DB Status` (rendered in Segoe UI, 14pt, Bold).
*   **Subtitle/Tip**: A rich-text label explaining that the panel provides an overview of `uieg_capture.db` along with backup, restore, reindex, and channel-specific reset capabilities.
*   **Global "Refresh" Button**: Located at the bottom right of the panel.
    *   **Style**: Styled with a purple background (`#5C6BC0`), white text, and bold font.
    *   **Function**: Triggers the `self.refresh()` method, which updates the status reports and refreshes the active tab's data.

---

### 2. Tab Breakdown

The panel is divided into a two-tab interface (`QTabWidget`): **Overview** and **Database**.

#### Tab A: "Overview" Tab
*   **Purpose**: Provides a read-only, high-level diagnostic report of the current ingestion state.
*   **UI Elements**:
    *   **Heading**: "UIEG CAPTURE — STATUS" (12pt, Bold).
    *   **Description**: A label indicating that this tab displays capture counts by channel (repo vs. crawl), recent import batches, source kinds, and repos promoted to the Ship's Computer.
    *   **Status Display (`self.overview_view`)**: A read-only `QTextEdit` styled with a dark background (`panel_bg`) and light text (`fg`). It uses a monospaced font (`Consolas`, 10pt) to display structured text.
*   **Usage**:
    *   When loaded or refreshed, it calls `format_uieg_status_report` from `LongRangeSensors.uieg_database` to query `uieg_capture.db` and generate a text-based breakdown of:
        *   Total captures.
        *   Captures partitioned by channel (`repo` vs. `crawl`).
        *   Recent import batches and source file types.
        *   Ingested repositories that have been successfully promoted to the primary Ship's Computer database (`ship_computer.db`).

---

#### Tab B: "Database" Tab
*   **Purpose**: Houses destructive and non-destructive database maintenance operations.
*   **UI Elements**:
    *   **Heading**: "Database" (12pt, Bold).
    *   **Description**: Explains that users can backup, restore, reindex, or reset the database, and notes that resets automatically trigger a backup first.
    *   **Action Rows**: Four distinct action blocks, each containing a bold title, a descriptive tip (styled in gray `#aaa`), and an action button.

The four option buttons on this tab are:

| Button Label | Action Description / Tooltip | Underlying Operation & Safety |
| :--- | :--- | :--- |
| **Backup UIEG Database** | "Copy uieg_capture.db into the backups/ folder with a timestamp." | Calls `backup_db` from `LongRangeSensors.uieg_maintenance`. It copies the active SQLite database file to a timestamped backup file inside the `backups/` directory. |
| **Restore UIEG Database** | "Overwrite the current database from a prior backup (destructive)." | Calls `list_backups` to present a selection dialog to the user, then invokes `restore_db` to overwrite `uieg_capture.db` with the chosen backup. *Warning: This is a destructive operation.* |
| **Reindex Database** | "Run ANALYZE, then VACUUM uieg_capture.db." | Calls `reindex_db` from `LongRangeSensors.uieg_maintenance`. It executes SQLite optimization commands (`ANALYZE` to update query planner statistics, followed by `VACUUM` to rebuild the database file and reclaim unused space). |
| **Reset Database** | "Automatic backup, then choose: reset Repo / GitHub, reset Crawl / Website Import, or wipe the entire DB." | Calls `auto_backup_before_reset` to secure current data. It then prompts the user to choose a target: reset only the Repo channel (`CHANNEL_REPO`), reset only the Crawl channel (`CHANNEL_CRAWL`), or wipe the entire database (`reset_all`). |

---

### 3. Integration & Usage Workflow

The "3 UIEG DB Status" panel is tightly integrated with the rest of the ingestion pipeline:

1.  **Data Ingestion**: The user fetches a GitHub repository or crawls a website using the first two steps of the application (handled by `UiegCapturePanel` in `uieg_capture_panel.py`).
2.  **Status Verification**: The user navigates to **3 UIEG DB Status** to verify that the files were successfully imported into `uieg_capture.db` and to check the total capture counts.
3.  **Database Maintenance**: If the database becomes bloated or fragmented after large crawls, the user runs **Reindex Database** to optimize performance.
4.  **State Synchronization**: When a database-altering operation (such as a **Restore** or **Reset**) is executed, the panel invokes the `on_db_changed` callback. As defined in `app.py`:
    ```python
    self._steps["status"] = build_uieg_status_panel(
        self.theme,
        uieg_cfg=uieg,
        on_db_changed=self._refresh_capture_panels,
    )
    ```
    This triggers `_refresh_capture_panels()`, which calls `refresh_db_view()` on both the "Repo" and "Crawl" capture panels, ensuring that the file tables and workspace views immediately reflect the restored or cleared database state.
