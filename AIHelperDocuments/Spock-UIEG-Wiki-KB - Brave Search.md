# Spock Ask AI — 20260831-140722

## You

Please give a detailed breakdown of Spock-UIEG-Wiki-KB / Brave Search. Discuss both 'Search' and 'Ask Leo' options.  Give examples for each.

## Computer

Based on the provided codebase corpus, **Brave Search** is integrated into the **Spock-UIEG-Wiki-KB** suite (and its standalone mini-apps like `Spock-UIEG-KnowledgeBase` and `Spock-Science-Station`) in two distinct ways:

1. **An Interactive Web UI Panel (`spock_shell/brave_search.py`)**: A center-panel interface that embeds Brave Search directly into the PyQt6 application using `QWebEngineView`. This panel features the **"Search"** and **"Ask Leo"** options.
2. **A Programmatic API Client (`LongRangeSensors/web_search_clients.py` & `external_search_panel.py`)**: A backend client that uses a `BRAVE_API_KEY` to fetch search results programmatically, allowing users to crawl and ingest external web pages into the Ship's Computer database (`ship_computer.db`).

---

### 1. The Interactive Brave Search Panel (`spock_shell/brave_search.py`)

The interactive panel is built inside `spock_shell/brave_search.py` using an embedded HTML landing page (`BRAVE_SEARCH_HTML`). 

#### Technical Implementation
The panel attempts to load a PyQt6 `QWebEngineView` to render the HTML. If `PyQt6.QtWebEngineWidgets` is not installed on the system, it gracefully falls back to a standard `QLabel` displaying a warning and a manual link:

```python
# D:\Spock-Onboarding\spock_shell\brave_search.py
def build_brave_search_panel(theme: Optional[Dict[str, str]] = None) -> QWidget:
    """Center panel with Brave Search + Ask Leo (QWebEngineView when available)."""
    ...
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        view = QWebEngineView()
        view.setHtml(BRAVE_SEARCH_HTML)
        lay.addWidget(view)
    except Exception as e:
        err = QLabel("Brave Search needs Qt WebEngine...\nOpen https://search.brave.com/ in a browser instead.")
        lay.addWidget(err)
```

The embedded HTML contains a text input (`#searchInput`) and two primary buttons that trigger JavaScript redirections.

---

### 2. The "Search" Option

The **"Search"** option performs a standard, privacy-focused web search using Brave's search engine. 

#### How It Works (JavaScript)
When the user types a query and clicks "Search" (or presses Enter), the JavaScript function redirects the embedded browser to Brave's standard search endpoint:

```javascript
function search() {
    const query = document.getElementById('searchInput').value.trim();
    if (query) {
        window.location.href = 'https://search.brave.com/search?q=' + encodeURIComponent(query);
    }
}
```

#### Example Use Case
* **Scenario**: An engineer needs to find the official GitHub repository for a utility like `SingleFile` to fetch its source code.
* **Query**: `SingleFile CLI github`
* **Execution**: The user types the query and clicks **Search**. The embedded browser redirects to:
  `https://search.brave.com/search?q=SingleFile%20CLI%20github`
* **Result**: The user is presented with standard search results listing the repository `gildas-lormeau/singlefile-cli` and can navigate directly to it within the application.

---

### 3. The "Ask Leo" Option

The **"Ask Leo"** option leverages Brave's free, built-in AI assistant (**Leo**), which performs real-time web-synthesized Q&A. This allows the user to get direct answers to natural language questions without leaving the Spock application interface.

#### How It Works (JavaScript)
When the user clicks "Ask Leo", the JavaScript function redirects the embedded browser to Brave's AI-specific `/ask` endpoint:

```javascript
function askLeo() {
    const query = document.getElementById('searchInput').value.trim();
    if (query) {
        window.location.href = 'https://search.brave.com/ask?q=' + encodeURIComponent(query);
    }
}
```

#### Example Use Case
* **Scenario**: An engineer wants a quick summary of how to run `SingleFile` via the command line without reading through pages of documentation.
* **Query**: `How do I use SingleFile CLI to save a page?`
* **Execution**: The user types the query and clicks **Ask Leo**. The embedded browser redirects to:
  `https://search.brave.com/ask?q=How%20do%20I%20use%20SingleFile%20CLI%20to%20save%20a%20page%3F`
* **Result**: Brave's Leo AI processes the query, searches the web, and generates a concise, step-by-step markdown response (e.g., showing `npx single-file <url> <output-file>`) directly inside the embedded view.

---

### 4. Programmatic API Search & Ingestion (UIEG Workflow)

Beyond the interactive web panel, Brave Search is integrated into the **UIEG (Universal Ingestion Engine Gateway)** workflow via `LongRangeSensors/external_search_panel.py` and `LongRangeSensors/web_search_clients.py`.

If a `BRAVE_API_KEY` is provided (either in `app_config.json` or as an environment variable), users can run programmatic searches. The results are displayed in a `QTableWidget` where the user can select a URL and trigger a background crawl:

```python
# D:\Spock-Onboarding\LongRangeSensors\external_search_panel.py
# Inside ExternalSearchPanel UI:
self.capture_btn = QPushButton("Capture URL")
self.capture_btn.clicked.connect(self._on_capture)
```

* **Programmatic Example**: 
  1. The user searches for `Starfleet warp core specifications` via the programmatic search bar.
  2. The backend queries `https://api.search.brave.com/res/v1/web/search` and returns a list of structured JSON results.
  3. The user selects a high-quality wiki page from the results table and clicks **Capture URL**.
  4. The system calls `crawl_url_to_disk()` (using `uieg_crawler.py`) to download the page as a clean document, which can then be promoted to `ship_computer.db` for Spock's local **Ask AI / Deep Dive** to reference.
