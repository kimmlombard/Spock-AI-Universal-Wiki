Reasoning

Toggle content

spock_search_kb

Toggle content

ReadingGenerationTools

92 tokens1.6s58.08 t/s

Reasoning

Toggle content
Spock-to-Bridge Python App

--------------------------

Based on the documentation in the Spock knowledge base, **Spock-to-bridge** is a **PyQt6 desktop application** that serves as a **personal Starfleet knowledge base console** — essentially a local AI assistant integrated with your computer's hardware and local AI models.

### What It Is

> **"The bridge console for a personal Starfleet knowledge base."**

It combines four main capabilities in one application:

1. **Hardware Assessment** — Scans your machine to determine if it can run local LLMs
2. **Model Selection & Management** — Finds and downloads GGUF models from Hugging Face, reads model cards, and launches `llama-server`
3. **Ship's Computer / RAG** — SQLite knowledge base with hybrid search (vector + FTS5) and AI chat
4. **Wiki Agent Controls** — Additional agent-related functionality

### Key Features

* **OpenAI-compatible chat interface** (connects to local `llama-server`)
* **RAG functionality** — Ask questions against your local knowledge base
* **Model management** — Download, organize, and run GGUF models locally
* **Hardware scanning** — Check GPU, VRAM, and system capabilities
* **Multi-platform** — Runs on Windows, macOS, and Linux
* **MIT Licensed** — Open source

### How to Launch

powershell
    .\.venv\Scripts\Activate.ps1
    python Spock-to-bridge.py
    # or: python main.py

### Architecture

* **Monolith** — The all-in-one `Spock-to-bridge.py` (7,312+ lines)
* **Refactored Suite** — Being split into focused mini-apps (`Spock-UIE-Wiki-KB.py` + individual modules)
* **Shared data** — Uses the same `.venv`, `ship_computer.db`, and configs

### GitHub

The code is available at:  
**https://github.com/kimmlombard/Spock-UIE-Wiki-KB**

* * *

Would you like me to run a specific feature of Spock-to-bridge (like a hardware scan, model search, or RAG query) using the tools I have access to?

ReadingGeneration

516 tokens9.0s57.60 t/s

mradermacher/Qwen3.59BClaude4.6OpusReasoningDistilledv2

608 tokens10s57.67 t/s

can you describe the major modules it has and usage?

11212 tokens6.2s1822.66 tokens/s

Reasoning

Toggle content

spock_search_kb

Toggle content

ReadingGenerationTools

97 tokens1.7s58.16 t/s

Reasoning

Toggle content

* * *

Major Modules of Spock-to-Bridge
--------------------------------

Based on the codebase analysis and architecture documentation, here are the major modules and their usage:

### **1. Core Monolith (`Spock-to-bridge.py`)**

* **Purpose**: Main PyQt6 application window (~7,312 lines)
* **Function**: Orchestrates the entire UI with tabs for:
  * **Captains Log** — Grid view of recent system events
  * **Agents Queue** — Task management grid
  * **Documents** — File browser grid
  * **Quarantine** — Quarantined files grid
  * **Ask AI** — Chat interface with preview, deep dive modes
  * **AI Helper** — MCP adapter testing, LM Studio validation
  * **Hardware Scan** — System assessment

* * *

### **2. Model Selection Suite**

| Module                         | Purpose                                                                         |
| ------------------------------ | ------------------------------------------------------------------------------- |
| **`model_selector_core.py`**   | Core logic for finding, downloading, and managing GGUF models from Hugging Face |
| **`model_selector_panels.py`** | PyQt6 widgets for model browsing and selection                                  |
| **`llama_server_manager.py`**  | Manages `llama-server` lifecycle (start, stop, status)                          |
| **`lm_studio_api.py`**         | Integration with LM Studio as an alternative LLM backend                        |

* * *

### **3. Hardware Assessment**

| Module                      | Purpose                                                                                              |
| --------------------------- | ---------------------------------------------------------------------------------------------------- |
| **`spock_scanner_core.py`** | Hardware scan logic (GPU, VRAM, RAM checks); recommends optimal context size based on available VRAM |
| **`nvidia_detailed.py`**    | Detailed NVIDIA GPU information (uses pynvml)                                                        |

* * *

### **4. RAG / Ship's Computer**

| Module                        | Purpose                                                           |
| ----------------------------- | ----------------------------------------------------------------- |
| **`db_maintenance.py`**       | SQLite database operations for `ship_computer.db`                 |
| **`rag_api_server.py`**       | Starts OpenAI-compatible RAG API server                           |
| **`gemini_openai_models.py`** | Model discovery and connection testing for various providers      |
| **`deep_dive.py`**            | Budgeted multi-file codebase context retrieval with hybrid search |

* * *

### **5. Onboarding Wizard**

| Module                                  | Purpose                          |
| --------------------------------------- | -------------------------------- |
| **`onboarding_wizard.py`**              | First-time setup wizard          |
| **`onboarding_wizard/config_store.py`** | Wizard configuration persistence |
| **`onboarding_wizard/window.py`**       | Wizard window UI                 |

* * *

### **6. AI Chat Features**

| Module                         | Purpose                                             |
| ------------------------------ | --------------------------------------------------- |
| **`chat_ai_helper.py`**        | AI chat helper functionality                        |
| **`external_search_panel.py`** | External search integration (Brave Search, Ask Leo) |

* * *

### **7. MCP (Model Context Protocol) Integration**

| Module             | Purpose                               |
| ------------------ | ------------------------------------- |
| **`mcp_panel.py`** | MCP adapter testing and configuration |

* * *

### **8. Standalone Tools (Refactored Suite)**

| Module                         | Purpose                           |
| ------------------------------ | --------------------------------- |
| **`Spock-Model-Selector.py`**  | Model selection standalone tool   |
| **`SpockOnboardingWizard.py`** | Standalone onboarding wizard      |
| **`_start_rag_api.py`**        | Standalone RAG API server starter |

* * *

### **9. Enterprise Bridge Facade**

| Module                             | Purpose                                    |
| ---------------------------------- | ------------------------------------------ |
| **`EnterpriseBridge/__init__.py`** | Facade layer for lazy loading the monolith |
| **`EnterpriseBridge/app.py`**      | Application entry point                    |

* * *

### **10. WarpCore (Planned Architecture)**

| Module                           | Purpose                                                           |
| -------------------------------- | ----------------------------------------------------------------- |
| **`WarpCore/settings_store.py`** | Settings persistence (migrating from JSON to `ships_computer.db`) |
| **`WarpCore/`**                  | Pure logic modules (no UI)                                        |

* * *

Typical Usage Flow
------------------

text
    1. Launch → Spock-to-bridge.py (or Spock-UIE-Wiki-KB.py for suite)
       │
    2. Onboarding Wizard (first run)
       │   ├── Hardware scan
       │   ├── LLM setup (LM Studio / llama-server)
       │   ├── Data ingestion configuration
       │   └── RAG/embeddings setup
       │
    3. Main Application
       │   ├── Browse/select models (Model Selection panels)
       │   ├── Start llama-server / LM Studio
       │   ├── Ask questions (RAG chat)
       │   ├── View Captains Log / Agents Queue
       │   └── MCP adapter testing
       │
    4. Refactored Mode
       │   ├── Launch hub (Spock-UIE-Wiki-KB.py)
       │   └── Open focused stations independently

* * *
