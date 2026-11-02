# Spock Ask AI — 20260831-132125

## You

Please give a detailed breakdown of Spock-Navigation-Station / 8 Run Ask AI. Describe all options, and usage.

## Computer

Based on the provided codebase corpus, here is a detailed technical breakdown of **Step 8: Run Ask AI** within the **Spock-Navigation-Station** suite.

---

### 1. Overview
**"8 Run Ask AI"** is the primary user-facing interface for interacting with the Spock AI assistant. It provides a local, PyQt-based chat interface that allows developers to query the codebase indexed inside the SQLite database (`ship_computer.db`). 

It supports two primary modes of operation:
1. **Ask Mode**: Standard Retrieval-Augmented Generation (RAG) using hybrid search.
2. **Deep Dive Mode**: A budgeted, multi-file context-packing engine designed for deep codebase analysis.

---

### 2. Architecture & Call Flow

When a user selects **"8 Run Ask AI"** from the left navigation panel in the `NavigationStationWindow`, the following call flow is executed:

1. **Navigation Trigger**:
   In `D:\Spock-Onboarding\NavigationStation\app.py` [Doc 10], the navigation item is mapped to `self._show_ask_ai`:
   ```python
   def _show_ask_ai(self) -> None:
       if self._ask is None:
           from EngineeringDeck.ask_panel import AskAiPanel
           from WarpCore.search import hybrid_search

           self._ask = AskAiPanel(
               self.theme,
               get_llm=lambda: make_llm_client(self.config),
               hybrid_search_fn=hybrid_search,
               get_emb_url=lambda: merge_embedding_profile(
                   self.config.get("embedding_profile")
               ).get("embeddings_url", "http://localhost:8080/embeddings"),
           )
           self.stack.addWidget(self._ask)
       self.show_center(self._ask)
   ```

2. **Dependency Injection**:
   * **`AskAiPanel`**: Imported from `D:\Spock-Onboarding\EngineeringDeck\ask_panel.py`. This is the PyQt widget that renders the chat interface.
   * **`make_llm_client`**: Resolves the active LLM provider (e.g., local `llama-server` on port `8081`, or cloud providers like OpenAI/Gemini) based on the application configuration.
   * **`hybrid_search`**: The search algorithm from `WarpCore.search` that combines vector embeddings with BM25/keyword matching.
   * **`get_emb_url`**: Resolves the active embedding server URL (defaulting to `http://localhost:8080/embeddings`).

---

### 3. Core Modes of Operation

The interface allows toggling between two distinct modes, which dictate how context is gathered from `ship_computer.db`:

#### A. Ask Mode (`ask`)
* **Purpose**: Quick, targeted questions about specific functions, concepts, or files.
* **Mechanism**: 
  * Performs a standard hybrid search over the database.
  * Retrieves the top $K$ most relevant document chunks (paragraphs/sections).
  * Feeds these chunks into the LLM context window alongside the user's prompt.

#### B. Deep Dive Mode (`deep_dive`)
* **Purpose**: Comprehensive codebase analysis, refactoring requests, or multi-file debugging.
* **Mechanism** (defined in `D:\Spock-Onboarding\deep_dive.py` [Doc 25]):
  * **Forced Path Extraction**: The engine parses the user's question using regular expressions to detect explicit file paths (e.g., `"Review spock_scanner_core.py"`). If a file is mentioned, it is marked as **Forced** and its entire content (up to `FORCED_EXCERPT_CHARS = 24_000` characters) is pulled directly from `documents.content_plain` in the database.
  * **Context Budgeting**: It calculates a strict character budget (defaulting to `DEFAULT_CONTEXT_BUDGET = 96_000` characters, which is roughly 43,000 tokens at a conservative code-heavy ratio of `CHARS_PER_TOKEN = 2.2`).
  * **Budget Filling**: After loading forced files, it fills the remaining character budget with relevant files retrieved via hybrid search (up to `FILL_TOP_K = 48` candidates).
  * **No Disk I/O**: Because it reads directly from the SQLite database's `content_plain` column, it is extremely fast and does not touch the physical disk during retrieval.

---

### 4. UI Options & Configuration

The options available in the PyQt `AskAiPanel` (and mirrored in the Web UI equivalent `D:\Spock-Onboarding\templates\webui\app.js` [Doc 29]) allow users to fine-tune their queries:

| Option / Control | Description |
| :--- | :--- |
| **Mode Selector** | Toggle buttons between **Ask** (standard RAG) and **Deep Dive** (budgeted codebase context). |
| **Path Filter** | A text input field allowing users to restrict queries to specific directories or file paths (e.g., `lower(path) LIKE '%spock_shell%'`). |
| **Include Extensions** | Buttons to filter the search to specific programming languages (e.g., `.py`, `.ts`, `.tsx`, `.js`, `.jsx`, `.rs`, `.go`). |
| **Exclude Extensions** | Excludes specific file types. By default, documentation files (`.md`, `.txt`, `.rst`) are excluded from code-heavy deep dives to prevent non-code files from consuming the token budget. |
| **Chat Search** | A search bar to find and highlight specific strings or hits within the active chat transcript. |
| **Clear Chat** | Wipes the current conversation history and resets the LLM context. |
| **Save MD** | Exports the entire conversation log, including retrieved sources and generation statistics, to a local Markdown file. |

---

### 5. Usage Guide

#### Scenario A: General Codebase Q&A (Ask Mode)
1. Select **Ask** mode.
2. Type a conceptual question: 
   > *"How does the Spock MCP host handle streamable-http connections?"*
3. **Result**: The system performs a hybrid search, retrieves relevant chunks from `D:\Spock-Onboarding\spock_shell\mcp_host.py` and `spock_onboarding\spock_status.py`, and explains the connection flow.

#### Scenario B: Targeted Code Review (Deep Dive Mode)
1. Select **Deep Dive** mode.
2. (Optional) Set the **Include Extensions** filter to `.py`.
3. Type a prompt referencing a specific file:
   > *"Review D:\Spock-Onboarding\spock_scanner_core.py and explain how it calculates recommended n_ctx based on VRAM."*
4. **Result**: 
   * The engine identifies `spock_scanner_core.py` as a forced path.
   * It loads the entire file into the context window.
   * It fills the remaining budget with related files (such as `model_pick_policy.py`).
   * The LLM provides a highly accurate, context-aware review of the `recommend_n_ctx` function, explaining how it subtracts model weights and sibling sizes from the usable VRAM budget to recommend context sizes.
