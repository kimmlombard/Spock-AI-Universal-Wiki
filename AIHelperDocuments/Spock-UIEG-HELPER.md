# Spock-UIEG-KnowledgeBase

Standalone UIEG (external capture) console for **Spock-Onboarding**.

Use the left **Navigation** pane for capture and status.
Use the right **Tools** pane for modal helpers (AI Helper, Ship Status, About, Brave Search, Theme).

## Left navigation

| Step | Purpose |
|------|---------|
| **Home** | This overview |
| **1 Repo / GitHub Fetch** | Clone or zip-download a GitHub repo → `captured_files/repos/<owner>_<repo>/` → Import → Browse / Preview |
| **2 Crawl — Website / Import** | Crawl a URL → `captured_files/crawl/` → Import → Browse / Preview |
| **3 UIEG DB Status** | Overview + Database maintenance (backup, restore, reindex, channel reset) |
| **Exit** | Close UIEG KnowledgeBase |

## Disk layout

| Path | Role |
|------|------|
| `captured_files/crawl/` | Website crawl output (flat files) |
| `captured_files/repos/<owner>_<repo>/` | GitHub fetch output |
| `captured_files/_repos/` | Temp git clones (skipped on import) |
| `uieg_capture.db` | Capture SQLite DB (`captures` + `capture_batches`) |
| `promoted_research/` | Files promoted toward `ship_computer.db` |

## Right tools

- **AI Helper** — chat helper modal
- **Ship Status** — live llama / MCP / RAG monitor
- **About** — ports, tools, MCP map
- **Brave Search** — optional web search (needs API key)
- **Theme** — color scheme for the shell

Promote runs `starfleet_universal_extractor.py` against selected capture rows.

## Launch

```text
Spock-UIEG-KnowledgeBase.bat
```

or from the onboarding menu:

```text
14) Spock UIEG KnowledgeBase
```
