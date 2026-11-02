# Spock-to-bridge Model Guide

How to pick **chat** vs **embedding** models for this console (Launch, Ask AI, Wiki Agent, RAG API).

---

## 1. Two different jobs (do not mix on one port)

| Role | What it is | How you run it | Typical port |
|------|------------|----------------|--------------|
| **Chat / instruct** | Answers questions (Ask AI, RAG API backend) | LM Studio **or** Launch GGUF **without** “Use as embedding server” | LM Studio `:1234` · Launch chat e.g. `:8080` |
| **Embeddings** | Vectors for wiki ingest + hybrid RAG | Launch GGUF **with** “Use as embedding server” + Config URL | Often `:8080` or `:8081` — **must match Config → Embeddings URL** |
| **RAG API** (optional) | OpenAI-compatible front door over the DB | Config → **START RAG API** | `:8090` (`/v1`) — **not** a browser chat page |

**Rule:** Chat LLM and embedding model are both “local LLMs,” but they are **not** interchangeable. An embedding GGUF on `/chat` produces garbage / runaway tokens. A chat GGUF on `/embeddings` returns 501 or useless vectors.

---

## 2. Embedding model selection (Spock / RAG)

Use a dedicated **embedding** GGUF (name usually contains `Embedding` / `embed`).

### Recommended for this project

| Model (examples) | Notes |
|------------------|--------|
| `Qwen3-VL-Embedding-8B-…gguf` | Common in Spock configs; dim often **4096** — set **Expected dim** in Config to match |
| Other `*Embedding*/*.gguf` from LM Studio or Spock `models/` | After Launch, **Apply** Config so Wiki Agent / Ask AI use the same URL |

### Launch checklist (embeddings)

1. Left nav → **Launch** → source **All sources** (or LM Studio / Spock Models) → **SCAN MODELS**
2. Select an **embedding** `.gguf`
3. Check **Use as embedding server**
4. Port e.g. **8080** or **8081** (don’t collide with a chat server)
5. **LAUNCH** → Status should show role **embedding**
6. **App Tools → Config** → Embeddings URL `http://localhost:PORT/embeddings` → **APPLY / SAVE**
7. Optional: **START RAG API** on `:8090` for external tools

Dim mismatch (Config says 4096, server/DB differ) breaks vector search — probe/Apply when changing models.

---

## 3. Chat model selection

### Option A — LM Studio (often easiest for Ask AI)

1. Load an **instruct** model in LM Studio, start server (default **1234**)
2. Right dock → **Ask AI — LM Studio** → Save
3. Keep embeddings on Launch / Config (separate)

### Option B — Spock Launch (llamaccp / llama-server)

1. **Launch** → select an **instruct** GGUF (not Embedding)
2. Uncheck **Use as embedding server**
3. Use a **different port** than the embedding server
4. Right dock → **Connect to llamaccp** → that chat port → Save

RAG quality is similar either way: the DB + embeddings do retrieval; the chat host only writes the answer.

---

## 4. Hardware tips (this machine class)

| VRAM (NVIDIA) | Comfortable chat | Embeddings |
|---------------|------------------|------------|
| ~6–8 GB | ~3B–7B Q4 | Small / quantized embed |
| ~12–16 GB | ~7B–13B | 8B embed OK if chat elsewhere |
| ~22–24 GB (e.g. RTX 6000) | 27B-class quantized chat **or** large embed | Prefer **second GPU** or second port for the other role |

CPU-only is fine for learning RAG concepts; GPU makes Ask AI / ingest usable.

---

## 5. Classic Ollama size ladder (optional / students)

Still useful if you also run Ollama — RAM-bound more than disk.

| Size | Min RAM | CPU-only? | Notes |
|------|---------|-----------|--------|
| Tiny ~1B | 2 GB | Yes | Concepts only |
| Small ~3–4B | 4–8 GB | Yes, slow | Learning RAG |
| ~8B | 16 GB | Barely | Prefer GPU |
| 70B-class | 64 GB+ | No | Needs serious GPU |

---

## 6. Quick troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| Ask AI “no documents” | Documents **path filter** matches 0 rows, or empty search |
| Gibberish on `:8080` web UI | That port is an **embedding** server — use Ask AI / instruct chat |
| Vector RAG dead | Embeddings URL points at chat model, or embed server not running |
| `:8090` Chromium “Server unavailable” | RAG API not started yet — Embedding / RAG → **START RAG API**, then open **http://127.0.0.1:8090/** (not `/v1`) |
| `:8090` shows JSON only | You opened `/v1` — use **http://127.0.0.1:8090/** for the Ask AI / Deep Dive Web UI |

---

*Live long and learn. For scripts and -ngl suggestions, see the **llama.cpp Config** tab.*
