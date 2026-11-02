# Root Scripts

Inventory of the entry-point style Python scripts at the repository root. Each is described by its documentation and structural summary extracted from source (not executed).

| Script | Lines | Classes | Functions | Main guard | Purpose |
|--------|-------|---------|-----------|------------|---------|
| `_start_rag_api.py` | 159 | 0 | 2 | yes | Start the Spock OpenAI-compatible RAG API + browser Web UI. |
| `chat_ai_helper.py` | 742 | 3 | 9 | no | Chat AI Helper — suite how-to Q&A from AIHelperDocuments (chat LLM only). |
| `db_browser.py` | 863 | 4 | 0 | no | SQLite grid browsing for ship_computer.db, with a file preview dialog. |
| `db_maintenance.py` | 1024 | 0 | 34 | yes | ship_computer.db — Database Maintenance Utility |
| `deep_dive.py` | 1365 | 1 | 28 | no | Ask AI Deep Dive — budgeted multi-file codebase context from ship_computer.db. |
| `docs_server.py` | 123 | 2 | 1 | yes | Pre-built mkdocs site server — serves ./site (port from config / SPOCK_DOCS_PORT). |
| `enhance_docs.py` | 51 | 0 | 2 | yes | Enhance docs/*.md sources in place using the LLM hook pipeline. |
| `gemini_openai_models.py` | 206 | 0 | 6 | no | Gemini / Vertex OpenAI-compatible model catalog and listing helpers. |
| `helper_main.py` | 72 | 0 | 2 | yes | Spock AI Helper — suite entry point. |
| `llama_server_manager.py` | 687 | 2 | 3 | no | Qt-friendly llama-server process manager (max one embedding + one chat). |
| `llm_client.py` | 1039 | 1 | 9 | no | Unified chat LLM client for the Spock suite. |
| `lm_studio_api.py` | 446 | 0 | 15 | no | LM Studio native + OpenAI-compatible helpers for Spock-to-bridge. |
| `main.py` | 34 | 0 | 1 | yes | Spock-UIE-Wiki-KB v2 orchestrator. |
| `mcp_panel.py` | 844 | 2 | 8 | no | Center-panel MCP controls (stdio + HTTP) and the llama.cpp WebUI launcher. |
| `model_pick_policy.py` | 1000 | 0 | 37 | no | VRAM-aware Hugging Face GGUF picks for Spock embed :8080 + chat :8081. |
| `model_selector_core.py` | 1259 | 0 | 39 | no | Pure logic for Spock Model Selector (hardware, HF Hub, GGUF scan, PDF). |
| `model_selector_panels.py` | 45 | 0 | 0 | no | Compatibility facade — implementation lives in the ``model_selector`` package. |
| `rag_api_server.py` | 638 | 1 | 5 | no | OpenAI-compatible RAG HTTP API + browser Ask AI / Deep Dive Web UI (stdlib only). |
| `reset.py` | 277 | 0 | 5 | yes | Reset ship_computer.db for a fresh wiki-scan run. |
| `reset_ship_computer.py` | 54 | 0 | 0 | no | Reset ship_computer.db and logs for a fresh run. |
| `reset_uieg.py` | 48 | 0 | 0 | no | Reset uieg_capture.db for a fresh run. |
| `Spock-UIE-Wiki-KB.py` | 29 | 0 | 1 | yes | Spock-UIE-Wiki-KB — main orchestrator for suite mini-apps. |
| `spock_health_report.py` | 707 | 0 | 17 | no | RAG API + llama-server health probe / report (no Qt). |
| `spock_live_monitor.py` | 28 | 0 | 1 | yes | Entry: spock_live_monitor mini-app. |
| `spock_maintenance.py` | 28 | 0 | 1 | yes | Entry: Spock-Engineering-Maintenance mini-app. |
| `spock_navigation.py` | 30 | 0 | 1 | yes | Entry: Spock-Navigation-Station mini-app. |
| `spock_profile_store.py` | 33 | 0 | 0 | no | Spock configuration profiles — re-export WarpCore.profile_store. |
| `spock_scanner_core.py` | 1432 | 0 | 25 | no | Spock-Scanner assessment logic for Spock-to-bridge Hardware Scan. |
| `spock_uieg.py` | 8 | 0 | 0 | yes | Entry alias: Spock-UIEG-KnowledgeBase (lite hub button: spock_uieg). |
| `spock_UIEG_KnowledgeBase.py` | 28 | 0 | 1 | yes | Entry: Spock-UIEG-KnowledgeBase mini-app. |
| `SpockBootstrapWizard.py` | 87 | 0 | 1 | yes | _no module docstring_ |
| `starfleet_universal_extractor.py` | 1067 | 0 | 35 | yes | Starfleet Universal Extractor |
| `wiki_agent.py` | 1271 | 3 | 21 | yes | Wiki Agent - Starfleet Ship's Computer |
| `wiki_agent_status.py` | 611 | 0 | 11 | yes | Ship Computer / Wiki Agent progress report. |
| `wiki_maintenance.py` | 2159 | 7 | 0 | no | Console maintenance for ship_computer.db: scan roots, settings, profiles. |