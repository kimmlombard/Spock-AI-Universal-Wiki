# Spock-AI-Universal-Wiki

**Spock** is a local-first agentic software-engineering workstation: hardware-aware bring-up, hybrid RAG over your codebase/wiki, MCP tools for IDE agents, and first-class connectors for **Google / Gemma / Gemini** (local GGUF + cloud) on consumer GPUs.

> Offline-capable agents need more than weights — they need ops + retrieval substrate. Spock is that open resource.

## Live docs & screenshots

| Resource | URL |
|----------|-----|
| Docs (MkDocs) | https://kimmlombard.github.io/Spock-AI-Universal-Wiki/ |
| Screenshot gallery | https://kimmlombard.github.io/Spock-AI-Universal-Wiki/gallery/ |
| Source | https://github.com/kimmlombard/Spock-AI-Universal-Wiki |

*(Pages may be unavailable while the repo is private on a free GitHub plan — use Actions artifacts or local `mkdocs serve` until visibility is public.)*

## Why Spock (Best New Resource framing)

- **Hardware-aware acquire** — llmfit + Hub shortlists sized to VRAM; provider allow-list (e.g. Google-only) in Maintenance → Provider.
- **Hybrid RAG** — SQLite FTS5 + embeddings (`ship_computer.db`) for grounded Ask AI / Deep Dive.
- **MCP surface** — Cursor and other clients get Spock tools over HTTP.
- **Google-forward** — Gemma GGUF catalogs, EmbeddingGemma profiles, Gemini / Vertex connectors, in-app Google Search + Gemini panel.

## Quick start (Windows)

```bat
Setup-Spock.bat
Spock.bat
```

Or console menu:

```bat
Spock-Menu.bat
```

Linux / WSL peer:

```bash
chmod +x spock_menu.sh bootstrap.sh
./spock_menu.sh
```

## Local docs / gallery preview

```bash
# Main docs (needs docs deps in .venv)
pip install -r requirements-docs.txt
mkdocs serve -a 127.0.0.1:8000

# Screenshot gallery (JPEG captions from LM Studio prescan)
cd gallery
python -m mkdocs serve -a 127.0.0.1:8001
```

Pre-scan ShareX PNGs from `assets/` (not committed; regenerated into `gallery/docs/images/`):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\prescan-screenshots.ps1
```

## Google / Gemma / Gemini support

- **Acquire / HF / Launch** — filter by provider (`google`, …); empty list = all providers.
- **Configure AI** — LM Studio, Ollama, llama.cpp, OpenAI-compatible, Vertex / Gemini paths.
- **Tools panel** — Google Search and Gemini beside the station workflows.
- **Gallery** — captioned UI evidence for HF Gemma lists, provider panels, Search/Gemini, EmbeddingGemma, MCP, Ask AI.

## What stays local (never commit)

- `.env`, `app_config.json`, HF/API tokens, Vertex project IDs
- `*.db`, `models/**`, GGUF weights, `tools/**` binaries
- Raw ShareX `assets/*.png` (published shots live under `gallery/docs/images/`)

## License

Apache License 2.0 — see [LICENSE](LICENSE).
