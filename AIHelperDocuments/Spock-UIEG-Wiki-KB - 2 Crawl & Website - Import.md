# Spock Ask AI — 20260831-134705

## You

Please give a detailed breakdown of Spock-UIEG-Wiki-KB / 2 Crawl -- Website / Import. Describe all options, and usage.  Define the tabs and option buttons for each.

## Computer

In the **Spock-UIEG-KnowledgeBase** application (launched via `spock_UIEG_KnowledgeBase.py` or as Step 13 in the bringup menu), **Step 2: Crawl — Website / Import** is the primary workspace for capturing external web documentation, saving it to disk, importing it into a local staging database, and preparing it for promotion to the ship's computer.

This workspace is implemented in `D:\Spock-Onboarding\LongRangeSensors\uieg_capture_panel.py` via the `UiegCapturePanel` class initialized in `crawl` mode.

---

### 1. Architectural Overview & Workflow
The crawl and import pipeline follows a strict **disk-first, staging-second, promotion-third** architecture:
1. **Crawl to Disk**: The crawler (`uieg_crawler.py`) downloads HTML pages and associated code files directly to a local directory (`capture_folder/captured_files/crawl/`).
2. **Import to Staging DB**: The import utility (`uieg_import.py`) parses these files and writes them into the local UIEG SQLite database (`uieg_capture.db`).
3. **Browse & Preview**: The user inspects the staging database using a table view and an embedded HTML previewer.
4. **Promote**: The staging records are promoted (`uieg_promote.py`) to the main ship's computer database (`ship_computer.db`), making them searchable by the RAG API.

---

### 2. Detailed Tab & Panel Breakdown

The `UiegCapturePanel` in `crawl` mode is styled with a custom Spock-themed dark stylesheet (`_panel_stylesheet`) and is organized into a tabbed interface (`QTabWidget`) and control panels.

#### Tab 1: Crawl / Capture Workspace
This tab contains the configuration inputs and execution controls for the web crawler.

*   **Option Fields & Inputs:**
    *   **Target URL (`QLineEdit`):** The starting URL for the crawl (e.g., `https://docs.example.com`). It supports standard `http://` and `https://` protocols, as well as local `file://` paths.
    *   **Crawl Levels / Depth (`QSpinBox`):** Sets the Breadth-First Search (BFS) depth.
        *   *Level 1:* Fetches only the starting URL.
        *   *Level 2:* Fetches the starting URL plus any same-host links found on that page (1 hop).
        *   *Level 3+:* Continues hopping recursively.
    *   **Link Limit (`QSpinBox`):** Caps the maximum number of HTML pages saved to disk to prevent runaway crawls on large sites.
    *   **Timeout (`QSpinBox`):** Network timeout in seconds per request (default is `15`).
    *   **Fetch Code Links (`QCheckBox`):** If enabled, the crawler will also download non-HTML assets linked on the pages that match code extensions.
    *   **Code Extensions (`QLineEdit`):** A comma-separated list of file extensions to target (defaults to `.py, .md, .txt, .rst`).

*   **Action Buttons:**
    *   **`Start Crawl` / `Run Crawl` (`QPushButton`):** Spawns a background `_Worker(QThread)` that executes `crawl_url_to_disk` without freezing the PyQt6 GUI.
    *   **`Stop Crawl` (`QPushButton`):** Aborts the active crawl thread.
    *   **`Log Output` (`QTextEdit`):** A read-only console area that displays real-time crawl progress, HTTP status codes, and file-saving events emitted by the worker thread.

---

#### Tab 2: Import & Database Staging
Once files are saved to disk, they must be parsed and staged in the local database.

*   **Option Fields & Inputs:**
    *   **Source Folder Path (`QLineEdit`):** Displays the path to the directory containing the crawled files (defaults to `capture_folder/captured_files/crawl/`).
    *   **Clean Import Checkbox (`QCheckBox`):** If checked, clears existing staged crawl captures before importing new ones.

*   **Action Buttons:**
    *   **`Import to DB` (`QPushButton`):** Executes `import_captured_files`. It reads the files from disk, extracts metadata (title, URL, file size), and writes them into the local SQLite staging database.
    *   **`Clear Local DB` (`QPushButton`):** Calls `clear_database` for the crawl channel, wiping all staged crawl records.

---

#### Tab 3: Browse & Preview
This tab allows the user to inspect the staged documents before they are promoted to the active ship's computer.

*   **UI Components:**
    *   **Staged Files Table (`QTableWidget`):** Displays all imported records for the crawl channel.
        *   *Columns:* Title/Path, Source URL, File Size, and Import Date.
        *   *Sorting:* Uses a custom `_SizeTableItem` class to ensure that sorting by the "File Size" column sorts by raw byte count rather than alphabetical string value.
    *   **Preview Pane (`QStackedWidget`):**
        *   If `PyQt6.QtWebEngineWidgets` is installed, it uses an embedded `QWebEngineView` with a custom `_QuietWebPage` (which silences JavaScript console noise) to render the crawled HTML offline.
        *   If `QtWebEngine` is missing, it falls back to a standard `QTextEdit` displaying raw HTML or plain text.

*   **Action Buttons:**
    *   **`Preview in Browser` (`QPushButton`):** Starts a lightweight local HTTP server (`start_preview_server`) on an ephemeral port, writes a temporary file, and opens the page in the system's default web browser via `QDesktopServices.openUrl`.
    *   **`Delete Selected` (`QPushButton`):** Removes the highlighted row's record from the staging database.

---

#### Tab 4: Promote to Ship's Computer
The final step in the ingestion pipeline.

*   **Action Buttons:**
    *   **`Promote to Ship's Computer` (`QPushButton`):** Calls `promote_captures`. This copies the staged documents from the local staging database directly into the active `ship_computer.db`. Once promoted, the files are picked up by the RAG API server (`rag_api_server.py`) and become searchable via the **Ask AI** or **Deep Dive** interfaces.

---

### 3. Under-the-Hood Mechanics (`uieg_crawler.py`)

The crawler uses standard Python libraries (`requests` and `BeautifulSoup` from `bs4`) to perform its work:

```python
def crawl_url_to_disk(
    url: str,
    capture_folder: str,
    *,
    link_limit: int = 10,
    crawl_levels: int = 2,
    timeout_sec: int = 15,
    fetch_code_links: bool = True,
    code_exts: Optional[Set[str]] = None,
    log: Optional[LogFn] = None,
) -> List[str]:
```

*   **SingleFile-Spirit Touch:** When saving HTML pages, the crawler checks if a `<meta charset="...">` tag is present in the first 800 characters. If missing, it prepends or injects `<meta charset="utf-8">` into the `<head>` block. This ensures that offline rendering in the preview pane or external browsers displays special characters correctly.
*   **Same-Host Filtering:** The crawler extracts links using `BeautifulSoup` but filters out external domains using `_same_host(base_url, full_url)` to prevent the crawl from escaping the target documentation site. It also strips URL fragments (e.g., `#section-name`) to avoid downloading duplicate pages.
