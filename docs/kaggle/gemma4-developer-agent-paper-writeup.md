# Spock: A Local-First Agentic Software Engineering Workstation for Gemma and Gemini on Consumer Hardware

**Track:** Google Gemma 4 Developer Agent — Paper Track  
**Prize framing:** Best New Resource  
**Artifact:** [github.com/kimmlombard/Spock-AI-Universal-Wiki](https://github.com/kimmlombard/Spock-AI-Universal-Wiki) · [Docs](https://kimmlombard.github.io/Spock-AI-Universal-Wiki/) · [Screenshot gallery](https://kimmlombard.github.io/Spock-AI-Universal-Wiki/gallery/)

---

## 1. Overview / Abstract

Cloud coding agents are powerful, but many software teams still need **capable agents that run offline or on everyday GPUs**—with grounded answers over *their* repositories, not only generic web knowledge. The Gemma 4 Developer Agent Paper Track asks for resources that make local and hybrid agentic software engineering practical. **Spock** is such a resource: an open, Windows-first (with WSL/Linux console peers) workstation suite that turns a greenfield machine into a bring-up, retrieval, and tool-using agent host.

Spock does not claim a new Gemma 4 post-training recipe. Instead it ships the **ops and retrieval substrate** that agentic SE needs: hardware-aware model acquisition (llmfit + Hub shortlists), dual llama-server roles (embedding + chat), hybrid SQLite FTS5 + vector RAG (`ship_computer.db`), an MCP HTTP adapter for IDE clients such as Cursor, and **first-class Google / Gemma / Gemini paths**—local GGUF catalogs, EmbeddingGemma profiles, OpenAI-compatible and Vertex/Gemini connectors, plus an in-app Google Search / Gemini panel. A Maintenance **Provider** allow-list can restrict Acquire / Hugging Face / Launch lists to `google` (or any orgs); an empty list means all providers.

This paper points judges to a **reproducible public artifact**: source, MkDocs documentation, and a captioned screenshot gallery generated from ShareX captures via LM Studio vision. Reproduce by cloning the repo, running Phase A/B bootstrap, acquiring a Gemma GGUF (or pointing at Gemini), scanning a wiki/repo into the ship computer, and asking grounded questions—without Competition Data.

---

## 2. Novelty

Most open “local LLM” projects stop at a chat UI or a single server binary. Agentic software engineering fails for a different reason: **the model is not the bottleneck—the workstation is**. Novelty in Spock is the integrated insight that offline/consumer-hardware agents need a **composable substrate**:

1. **Hardware recipes before download** — fit selection merges llmfit signals, Hub rows, and catalog policy so Acquire proposes models that fit VRAM, not a random Hub search.
2. **Dual-model co-hosting** — embedding and chat roles are first-class, with ports, profiles, and status probes so RAG and dialogue do not fight over one overloaded process.
3. **Hybrid RAG as the memory contract** — documents become chunks + FTS5 + embeddings; Ask AI / Deep Dive cite the ship computer rather than inventing paths.
4. **MCP as the agent I/O bus** — the same workstation exposes tools to external agents, so Cursor (or peers) can drive Spock without reinventing ingestion.
5. **Provider-shaped evidence for Google models** — Gemma on Hub, EmbeddingGemma in profiles, Gemini/Vertex connectors, and UI filters that can lock the shortlist to Google while remaining provider-agnostic when the allow-list is empty.

That combination is the resource: not a fine-tune checkpoint, but a **shippable SE workstation** that makes Gemma/Gemini usable for agentic workflows on consumer hardware.

### Why “substrate” rather than “another chat app”

A chat wrapper around llama.cpp is useful, but agentic SE repeatedly needs the same missing pieces: (a) choosing a model that fits the machine before wasting bandwidth, (b) keeping an embedding service alive beside chat, (c) ingesting a moving codebase without a cloud index, (d) exposing tools to the IDE agent that is already writing the code. Spock treats those as **product surfaces** (Acquire dialog, Ship Status, Wiki Scan, MCP panel, Provider tab) instead of undocumented scripts. The novelty is therefore **productization of the local agent stack** with Google-model evidence baked into the default path—not a claim that Gemma weights themselves are new.

### Separation from PEFT / RL papers

Judges should score this submission on **resource criteria** (novelty of the tool, generality, relevance, verifiability, clarity). Spock explicitly avoids competing as a training paper: there is no custom Gemma 4 reward model, no private preference dataset, and no leaderboard CSV. Where Gemma 4 appears in catalogs or ID tests, Spock documents **support and operability**. Where this host runs Gemma 2/3 GGUFs for demos, the writeup says so. Honesty is part of verifiability.

---

## 3. Quality / Generality

Spock is intentionally **not** a single-leaderboard harness:

- **Any corpus** — wiki scan and UIEG capture ingest local trees and crawled pages into SQLite; the same Ask/Deep Dive path works for arbitrary repos once indexed.
- **OpenAI-compatible clients** — chat and embeddings speak familiar HTTP APIs; LM Studio, Ollama, llama.cpp, and cloud OpenAI-compatible endpoints plug into Configure AI.
- **MCP for third-party agents** — tools are documented in-app (MCP reference tab) with a typical localhost port layout.
- **Provider-agnostic core, Google-proven paths** — the allow-list can be empty (all orgs) or set to `google` for competition-aligned demos; HF chat filter screenshots show Google-provided Gemma-family rows; gallery captions document Search/Gemini tooling beside Navigation and Engineering stations.

Quality shows up as **operability**: Ship Status / live monitor, embedding health probes, config profiles, and Maintenance (scan roots, DB, timing, recipes) keep the substrate inspectable rather than opaque.

### Station layout as a quality signal

Rather than one mega-window, Spock separates concerns into stations that map to SE phases: Navigation (hardware → models → launch → configure), Engineering (Ask/Deep Dive, maintenance, DB health), Science / Long Range Sensors, and UIEG knowledge capture (GitHub fetch, crawl, DB status). Each station reuses shared Tools (AI Helper, Ship Status, Google Search / Gemini, themes). That reuse reduces “works only if you memorize flags” failure modes and makes screenshots auditable: judges can see the same Search and Suite controls across workflows.

### Failure visibility

Bring-up progress panels, embedding health suites (pass/fail counts), and status consoles that print llama-server endpoints and MCP listen addresses are deliberate. A resource that hides failures cannot be verified. Spock prefers noisy truth—probe output, PID tables, recipe profiles—over a green checkbox with no evidence.

---

## 4. Relevance

The Paper Track thesis emphasizes **local/offline agents on consumer hardware**, code comprehension, and Gemma-related resources. Spock maps onto that thesis end-to-end:

| Track need | Spock answer |
|------------|--------------|
| Everyday GPUs | Hardware scan + VRAM-aware acquire; dual Quadro-class hosts already documented in gallery |
| Code / wiki comprehension | Hybrid RAG over onboarded files; Deep Dive over selected roots |
| Gemma / Gemini | Hub Google chat lists, Gemma GGUF quant pages, EmbeddingGemma, Gemini chat/Search UI |
| Agent tools | MCP adapter + status health |

Impact on SE workflow is a linear story judges can replay: **bring-up → acquire Gemma → start servers → ingest → Ask/Deep Dive → MCP from the IDE**. That is the relevance claim—operationalizing competition themes as a reusable open tool, not a one-off notebook.

### Consumer hardware, not datacenter theater

Gallery captures on this development host show dual NVIDIA Quadro-class GPUs, VRAM-aware Primary AI GPU selection, and GGUF tables sized in gigabytes—not abstract “cloud GPU” claims. Spock’s relevance is that a working engineer can clone, bootstrap, and get a Gemma chat + embedding pair running without an ML platform team. When cloud Gemini is desirable for harder questions, Configure AI and the Gemini panel provide the hybrid path without abandoning the local ship computer.

### Google-forward without vendor lock-in

Relevance to a Google-sponsored track does not require locking users into one API. Spock’s Provider allow-list and OpenAI-compatible connectors mean a team can demo Google models for the competition narrative and still point Acquire at other orgs tomorrow by clearing the filter. That design matches how real SE shops evaluate models: **prove the substrate with the sponsor’s family, keep the exit door**.

---

## 5. Verifiability

### Public artifacts

- Source: https://github.com/kimmlombard/Spock-AI-Universal-Wiki  
- Docs: https://kimmlombard.github.io/Spock-AI-Universal-Wiki/  
- Gallery: https://kimmlombard.github.io/Spock-AI-Universal-Wiki/gallery/  
- License: Apache-2.0  

### Reproduce (smoke path)

1. Clone the repository on Windows 10/11 (or follow `spock_menu.sh` on WSL).
2. Run `Setup-Spock.bat` / Phase A–B bootstrap into `.venv` (PyQt pins documented for WebEngine).
3. In Maintenance → **Provider**, add `google` (or leave empty for all providers).
4. Navigation / Bring-up: Acquire a **Gemma** GGUF that fits host VRAM; configure EmbeddingGemma (or current embedding profile).
5. Optionally configure Gemini / OpenAI-compatible / Vertex via Configure AI (keep keys in local `app_config.json` / `.env` — never commit).
6. Run wiki scan / ingest; confirm embedding health.
7. Ask AI or Deep Dive a repo question; confirm citations/context from the ship computer.
8. Start MCP adapter; connect a client; list tools from the MCP reference panel.

### Gallery figures (Google / Gemma / Gemini citation pack)

| Figure (gallery slug) | What it verifies |
|--------------------|------------------|
| `spock-hf-chat-models-list` | HF Filter Chat listing Google-provided chat models |
| `spock-navigation-station-gemma-quantizations` | Gemma GGUF imatrix quant download table |
| `spock-model-selection-panel` | Local GGUF selection including embeddinggemma files |
| `spock-configure-ai-*` / provider tabs | LM Studio, Ollama, OpenAI-compatible, llama.cpp connectors |
| `spock-google-search-view` / `spock-navigation-station-google-search` | In-app Google Search |
| `spock-navigation-station-ai-chat` | Gemini response pane in-station |
| `spock-mcp-adapter-settings-panel` / `spock-mcp-reference-panel` | MCP listen + tool reference |
| `spock-ask-ai-*` | Grounded Ask / Deep Dive UX |
| `spock-embedding-profile-rag-api-panel` | Embedding / RAG API controls |

### Data note

Verifiability uses **local** `ship_computer.db` schema (documents, chunks, FTS5, embeddings)—no private Competition Data. Secrets (Vertex project URLs, tokens) are gitignored.

### What CI and Pages prove

The GitHub Actions workflow builds main MkDocs and the gallery MkDocs into one Pages artifact (`/` and `/gallery/`). A green Actions run plus resolving doc links is independent evidence that the documentation corpus and screenshot JPEGs are in the tree. Raw ShareX PNGs under `assets/` are intentionally not the published source of truth; LM Studio vision captions land in `gallery/docs/` so judges read human-scale JPEG pages, not multi‑megabyte desktop dumps.

### Negative evidence (what is absent on purpose)

The public tree must **not** contain `.env`, `app_config.json`, `*.db`, GGUF weights, or HF tokens. Absence of those files is itself a verifiability check: if a clone still boots to bootstrap and docs, the resource is not secretly depending on leaked credentials. Absolute Windows paths may appear in local logs and screenshots; treat them as host-specific, not as portable secrets in source.

---

## 6. Clarity

### Architecture (stations / RAG / MCP / providers)

```text
┌─────────────────────────────────────────────────────────────┐
│ Spock stations: Navigation · Engineering · Science · UIEG   │
│ Tools: AI Helper · Ship Status · Google Search / Gemini     │
└───────────────┬─────────────────────────────┬───────────────┘
                │                             │
     ┌──────────▼──────────┐       ┌──────────▼──────────┐
     │ llama-server roles  │       │ MCP HTTP adapter    │
     │ embed :8080 chat:…  │       │ IDE / Cursor tools  │
     └──────────┬──────────┘       └─────────────────────┘
                │
     ┌──────────▼──────────┐
     │ ship_computer.db    │  FTS5 + embeddings + chat logs
     └──────────▲──────────┘
                │ ingest (wiki scan / UIEG)
     ┌──────────┴──────────┐
     │ Providers           │  google/… Gemma GGUF · Gemini/Vertex
     │ allow-list or ALL   │  LM Studio · Ollama · OpenAI-compat
     └─────────────────────┘
```

### Glossary

- **Acquire** — hardware-aware model shortlist + download into local models tree.  
- **Provider allow-list** — HF org prefixes (`google`, …); zero rows = all providers.  
- **Ship computer** — SQLite knowledge backbone for RAG.  
- **MCP** — Model Context Protocol tool surface for external agents.
- **Deep Dive** — Ask AI mode scoped to selected roots with stronger retrieval budget.
- **UIEG** — capture/import path for GitHub repos and website crawls into a side DB, then promote into the ship computer.
- **llmfit** — external fit tool consulted when building Acquire shortlists alongside Hub/catalog rows.

### Numbered “first hour” path (clarity for non-authors)

1. Install / bootstrap (Phase A tools, Phase B Python deps).  
2. Pick Primary AI GPU if multi-GPU.  
3. Set Provider allow-list to `google` for a Gemma-focused demo (optional).  
4. Acquire embedding + chat GGUFs; start servers; confirm Ship Status.  
5. Run wiki scan on this repo (or a sample tree); wait for embeddings.  
6. Ask a grounded question (“How does Spock pick embedding vs chat models?”).  
7. Open Google Search / Gemini from Tools for web context; keep secrets local.  
8. Start MCP; connect Cursor; call a Spock tool.  

If any step fails, the status/probe panels are the debugging surface—clarity includes knowing **where** to look.

---

## 7. Conclusion — Best New Resource checklist

Spock is submitted as a **Best New Resource**: a software suite plus documentation plus a screenshot corpus that lets others stand up Gemma/Gemini-capable agentic SE on consumer hardware.

- [x] Open source (Apache-2.0) with public GitHub URL  
- [x] Live docs + screenshot gallery  
- [x] Hardware-aware local bring-up and dual-model hosting  
- [x] Hybrid RAG + Ask/Deep Dive over local corpora  
- [x] MCP adapter for IDE agents  
- [x] Google/Gemma/Gemini connectors and UI evidence (no fabricated Gemma 4 RL claims)  
- [x] Reproduce steps without Competition Data  

**What we do not claim:** new Gemma 4 post-training, PEFT leaderboard scores, or access to private Vertex projects in the public tree. **What we do claim:** a verifiable, Google-forward workstation resource that operationalizes local agentic software engineering.

---

## Appendix — Kaggle submit checklist

1. Confirm repo is **public** and Pages URLs resolve.  
2. Paste this writeup into Kaggle **New Writeup** (trim if needed to ≤3000 words).  
3. Project Links: GitHub + Docs + Gallery.  
4. Optional: short public notebook that clones and prints `spock_status` / docs links.  
5. Word-count gate (~2800 draft target).  
6. Submit before **2026-11-12 23:59 UTC**; keep ≤2 final selections if required.
