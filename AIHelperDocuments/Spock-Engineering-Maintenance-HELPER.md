# Spock Engineering — Deck & Maintenance

Shared Home overview for:

| Launch | What you get |
|--------|----------------|
| **Bringup → 10 Ask AI / Deep Dive (Engineering Deck)** | `python -m EngineeringDeck` — in-app Ask AI + Deep Dive |
| **Bringup → 12 Engineering Maintenance** | `spock_maintenance.py` / `Spock-Maintenance.bat` — wiki/DB console |
| **Windows** | `Spock-Maintenance.bat` |

## Engineering Deck (Ask AI / Deep Dive)

Left nav:

| Step | Purpose |
|------|---------|
| **Home** | This overview |
| **1 Ask AI** | Hybrid search + chat / Deep Dive over `ship_computer.db` |
| **2 Configure Spock AI** | Providers, embedding :8080, chat :8081, RAG/MCP |

Needs embed + chat servers up (Bringup step 4) and a Wiki Scan (step 9) for useful retrieval.

## Engineering Maintenance

Left nav:

| Step | Purpose |
|------|---------|
| **Home** | This overview |
| **1 Maintenance** | Scan roots, database ops, settings, **Provider** allow-list, Timing, **Recipe**, Spock Config Profiles |
| **2 Ship Computer DB Health** | Overview + MCP probes + Embedding Health |

### 1 Maintenance tabs

| Tab | Contents |
|-----|----------|
| **Scan Roots** | Update / List / Delete scan roots |
| **Database** | Backup, Restore, Reindex, Purge Missing, **Clear Embeddings (re-embed)**, Reset (auto-backup first) |
| **Settings** | Full console settings + Scan Settings filter |
| **Provider** | HF / Acquire / Launch allow-list (empty = ALL; e.g. Google only excludes Qwen/Nvidia). Clear filter on HF Models / Launch also clears this. |
| **Timing** | Ask AI / Deep Dive stage timings (`ask_timing_history`) |
| **Recipe** | Host recipe Create / Update (GPU policy, tensor-split, `-c`, embed `-np`); audited versions; hardware drift banner (never auto-applies). Kept across content DB reset. |
| **Spock Config Profiles** | List / load / delete session profiles; Load Selected Profile restores Spock_Console and starts only needed llama / RAG / MCP / WebUI processes |

### 2 Ship Computer DB Health tabs

Overview · spock_health (**Run Spock Health** + **Embedding Health**) · spock_status · spock_queue · spock_captains_log · spock_llmfit_fit · spock_hardware_plan

## Right tools (both apps)

AI Helper · Ship Status · About · Google Search · Theme

## Switching embedding models

Use **Maintenance → Database → Clear Embeddings (re-embed)** to null vectors and clear `kb_embedding_corpus` without deleting documents. Then launch the new GGUF on `:8080` and run Wiki Scan — the scan re-queues every document whose embedding is NULL, and the extractor re-embeds those rows even when the file hash is unchanged. Prefer this over **Reset Database (content)** when you only need a model swap.

```text
python -m spock_bringup reembed --yes
```
