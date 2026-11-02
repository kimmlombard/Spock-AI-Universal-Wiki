# Spock Ask AI — 20260831-134403

## You

Please give a detailed breakdown of Spock-UIEG-Wiki-KB / 1 Repo / GitHub Fetch. Describe all options, and usage.  Define the tabs and option buttons for each.

## Computer

Based on the codebase corpus, here is a detailed technical breakdown of the **Spock-UIEG-KnowledgeBase** application, specifically focusing on the **"1 Repo / GitHub Fetch"** station.

---

### 1. Architectural Overview
The **Spock-UIEG-KnowledgeBase** application (launched via `spock_uieg.py` or Step 13 of the Spock Bringup Menu) is designed to capture external knowledge from GitHub repositories and websites, stage them locally on disk, and promote them to the Ship's Computer database (`ship_computer.db`).

The entry point is defined in:
* **Path:** `D:\Spock-Onboarding\LongRangeSensors\app.py`

The application uses a multi-step navigation layout managed by `SuiteShellWindow`. The first active step is **"1 Repo / GitHub Fetch"**, which instantiates a specialized capture panel:
```python
self._steps["repo"] = UiegCapturePanel(self.theme, uieg_cfg=uieg, mode="repo")
```

---

### 2. UI Layout & Navigation Tabs
The left-hand navigation panel of the `UiegKnowledgeBaseWindow` exposes the following steps:
1. **Home:** Displays the markdown-rendered helper document (`AIHelperDocuments/Spock-UIEG-HELPER.md`).
2. **1 Repo / GitHub Fetch:** The primary interface for cloning or downloading GitHub repositories (powered by `UiegCapturePanel` in `"repo"` mode).
3. **2 Crawl — Website / Import:** The interface for crawling web URLs (powered by `UiegCapturePanel` in `"crawl"` mode).
4. **3 UIEG DB Status:** Displays the database status and allows promoting staged files to the Ship's Computer.

---

### 3. "1 Repo / GitHub Fetch" Panel Breakdown
The interface is driven by `UiegCapturePanel` (configured with `mode="repo"`). It coordinates with the backend module `D:\Spock-Onboarding\LongRangeSensors\uieg_repo_fetch.py` to fetch, filter, and store repository contents.

#### Input Fields & Configuration Options
* **Repository URL or Slug:** 
  * Accepts full GitHub URLs (e.g., `https://github.com/owner/repo`) or shorthand slugs (e.g., `owner/repo`).
  * Supports explicit branch/tag/commit references using the `@` delimiter (e.g., `owner/repo@dev` or `owner/repo@v1.0.0`).
* **Fetch Method Selection:**
  * **`auto` (Default):** Attempts a shallow Git clone first. If `git` is not installed on the system or the clone fails, it automatically falls back to downloading a ZIP archive.
  * **`git`:** Forces a local command-line Git clone.
  * **`zip`:** Bypasses Git entirely and downloads a compressed ZIP archive directly from GitHub's servers.
* **File Extension Allowlist:**
  * Restricts the files copied into the staging area to prevent database bloat.
  * Default allowlisted extensions: `.md`, `.py`, `.txt`, `.rst`, `.json`, `.toml`, `.yml`, `.yaml`.

#### Action Buttons
* **Fetch / Clone:** Initiates the download process. It spawns a background worker thread to prevent freezing the PyQt6 GUI.
* **Clear / Reset:** Clears the input fields and resets the status log.
* **Refresh DB View:** Refreshes the local staging view to show newly fetched files.

---

### 4. Backend Mechanics (`uieg_repo_fetch.py`)
When a fetch is triggered, the backend executes the following pipeline:

#### A. Parsing (`parse_github_repo`)
The input string is parsed to extract the owner, repository name, and target reference (defaulting to `main` if not specified):
```python
def parse_github_repo(url_or_slug: str) -> Optional[Tuple[str, str, str]]:
    # Parses owner, repo, and ref (e.g., "owner/repo@ref")
```

#### B. Git Fetching (`_fetch_via_git`)
If Git is selected or auto-detected, it attempts a shallow clone (`--depth 1`) of the specified branch:
```python
subprocess.run(
    ["git", "clone", "--depth", "1", "--branch", ref, url, clone_dir],
    check=True, capture_output=True, text=True, timeout=timeout_sec
)
```
If the branch clone fails (e.g., if the branch does not exist), it retries cloning the default `HEAD`.

#### C. ZIP Fetching (`_fetch_via_zip`)
If Git is unavailable or fails, it sequentially queries GitHub's archive endpoints to download the repository as a ZIP file:
1. `https://github.com/{owner}/{repo}/archive/refs/heads/{ref}.zip`
2. `https://github.com/{owner}/{repo}/archive/refs/tags/{ref}.zip`
3. `https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{ref}`

#### D. Filtering & Staging (`_copy_allowlisted`)
Once downloaded, the files are extracted to a temporary directory. The system walks the directory tree, ignores blacklisted folders (such as `.git`, `__pycache__`, `node_modules`, `.venv`), and copies only allowlisted files to the target capture folder:
```python
dest_root = os.path.join(capture_folder, f"{owner}_{repo}")
```

---

### 5. Integration with Right-Dock "External Search"
The application features a right-dock search panel that integrates directly with the GitHub Fetch workflow:
* **Path:** `D:\Spock-Onboarding\LongRangeSensors\external_search_panel.py`
* **Path:** `D:\Spock-Onboarding\LongRangeSensors\web_search_clients.py`

#### How it Works:
1. The user clicks **"Brave Search"** in the right-dock tools panel.
2. They enter a query. If the query targets GitHub, `web_search_clients.py` rewrites natural language into structured GitHub search operators (sorting by stars).
3. Results are displayed in an `ExternalSearchPanel` table.
4. **Option Buttons in the Search Panel:**
   * **Open:** Opens the repository URL in the default web browser.
   * **Clone / Zip repo:** Instantly triggers `fetch_repo_to_capture` using the selected search result's URL, automatically staging the repository files without requiring the user to manually copy-paste the URL into the main "1 Repo / GitHub Fetch" tab.
