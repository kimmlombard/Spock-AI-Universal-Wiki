# Spock AI Helper

Suite-integrated AI chat helper + MkDocs documentation site for Spock-Onboarding.

## Features

1. **AI Chat** — Shared `chat_ai_helper.py` UI (same as the Tools dock). Context comes from the single curated `AIHelperDocuments/` tree at the suite root. Replies stream when the chat provider supports it.
2. **Docs Site** — Pre-built MkDocs HTML served on `http://127.0.0.1:<docs_port>` (default **8000**).

## Prerequisites

- **Python 3.12+** with PyQt6 (suite `.venv` preferred)
- Chat LLM reachable (llama-server or the provider configured in ship_computer settings)

## Quick Start

```bat
Spock-AI-Helper.bat
```

Or PowerShell:

```powershell
.\spock_ai_helper.ps1
```

This will:

1. Start the docs server (port from `docs_port` / `SPOCK_DOCS_PORT`)
2. Open a browser to the docs URL
3. Launch the Chat AI Helper GUI

## Standalone Usage

```bat
python helper_main.py
```

## Build Docs

```bat
SetupMkDocs.bat
mkdocs build
```

## Ports and context (config)

Service ports and completion budgets live in **ship_computer.db** app settings (defaults in `WarpCore/config_defaults.py`), resolved by `WarpCore/service_endpoints.py`:

| Role | Default | Config / env |
|------|---------|--------------|
| Embeddings | 8080 | `embed_port` / `embedding_profile.embeddings_url` / `SPOCK_EMBED_PORT` |
| Chat llama-server | 8081 | `llama_port` / `SPOCK_CHAT_PORT` |
| llama WebUI proxy | 8082 | `mcp.webui_port` / `SPOCK_MCP_WEBUI_PORT` |
| RAG API | 8090 | `rag_api.port` / `SPOCK_RAG_PORT` |
| MCP HTTP | 8765 | `mcp.http_port` / `SPOCK_MCP_PORT` |
| AI Helper docs | 8000 | `docs_port` / `SPOCK_DOCS_PORT` |

Also configurable (Configure Spock AI → llamaccp tab):

- `embed_n_ctx` / `chat_n_ctx` — preferred llama-server `-c` when launching
- `chat_max_tokens` — local / AI Helper stream completion length

Spock always passes an explicit `--port` to llama-server; llama.cpp’s future default `:9931` does not change Spock’s ports.

### Second clone / multi-install

If you run two checkouts at once (e.g. `D:\Spock-Onboarding` and `C:\Dev\Spock`), they share the same default ports and will collide (health may report foreign MCP PIDs). Change `mcp.http_port`, `rag_api.port`, and llama ports in the second install (or stop the first).

## Clone / relocate checklist

Core paths resolve from this tree (`Path(__file__)` / `SPOCK_ROOT`). To run from e.g. `C:\Dev\Spock`:

1. Clone or copy the suite to the new root; run bootstrap / create `.venv` **there**.
2. Set `LLAMA_SERVER_PATH` if llama-server is not under `tools/llama-server/` (app-relative).
3. Optional: `set SPOCK_ROOT=C:\Dev\Spock` (must contain a `WarpCore\` folder).
4. Re-point absolute paths already saved in `ship_computer.db` / profiles (`model_path`, `scan_roots`) if you moved models or data.
5. Regenerate Cursor MCP snippets from Configure → MCP (do not reuse old absolute paths from another drive).

## Layout (suite root)

```
Spock-Onboarding/   (or any clone root)
├── helper_main.py
├── Spock-AI-Helper.bat
├── spock_ai_helper.ps1
├── chat_ai_helper.py
├── docs_server.py
├── AIHelperDocuments/
├── docs/
├── site/
├── mkdocs.yml
├── WarpCore/service_endpoints.py
└── Spock-AI-Helper.md
```

There is **no** separate nested `Spock-AI-Helper/` package and **no** second copy of `AIHelperDocuments/`.
