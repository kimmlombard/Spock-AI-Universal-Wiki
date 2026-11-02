# Codebase Structure

## Overview

This repository contains the **Spock Universal AI Wiki** codebase, a Python and SQLite application organized around specialized "stations" and supporting adapter packages. The architecture follows a hub-and-spoke model:

- **WarpCore** serves as the shared foundation, providing the SQLite database layer, application settings, and standardized skill interfaces that all other packages depend on.
- **Stations** (`NavigationStation`, `ScienceStation`, `EngineeringDeck`) are the primary operator-facing GUIs, each responsible for a distinct operational domain.
- **`spock_*` adapter packages** bridge external systems (MCP, RAG, wiki scanning, live monitoring) into the core application.
- **Bringup and onboarding packages** handle initial system configuration, model selection, and operator profile selection.
- **Bootstrap scripts** automate environment setup and dependency installation on Windows (PowerShell).

The project uses a multi-entry-point design: each major subsystem can be launched independently via its own `__main__.py` or through `python -m <package>`.

## Top-level map

| Path | Purpose | Evidence |
| --- | --- | --- |
| AIHelperDocuments/ | Helper / Ask AI source markdown | `AIHelperDocuments` |
| bootstrap_wizard/ | Pending classification | `bootstrap_wizard` |
| docs/ | MkDocs + generated structure docs | `docs` |
| EngineeringDeck/ | Ask AI + Engineering Maintenance | `EngineeringDeck` |
| LongRangeSensors/ | Pending classification | `LongRangeSensors` |
| model_selector/ | Model launch / status | `model_selector` |
| NavigationStation/ | Primary operator GUI | `NavigationStation` |
| Orchestrator/ | Pending classification | `Orchestrator` |
| ScienceStation/ | Science / wiki / ships logs GUI | `ScienceStation` |
| scripts/ | Pending classification | `scripts` |
| spock_bringup/ | CLI bringup steps | `spock_bringup` |
| spock_bringup_menu/ | Bringup GUI | `spock_bringup_menu` |
| spock_codebase_knowledge/ | Acquire codebase knowledge skill | `spock_codebase_knowledge` |
| spock_live_monitor/ | Pending classification | `spock_live_monitor` |
| spock_mcp_adapter/ | MCP adapter | `spock_mcp_adapter` |
| spock_onboarding/ | Bringup / acquire / fit select | `spock_onboarding` |
| spock_probe/ | Pending classification | `spock_probe` |
| spock_progress_log/ | Pending classification | `spock_progress_log` |
| spock_rag_adapter/ | RAG / embeddings bridge | `spock_rag_adapter` |
| spock_shell/ | Shared shell widgets / busy UI / paths | `spock_shell` |
| spock_status/ | Pending classification | `spock_status` |
| spock_wiki_adapter/ | Wiki Scan panel | `spock_wiki_adapter` |
| templates/ | Pending classification | `templates` |
| tests/ | Pytest suite | `tests` |
| WarpCore/ | Shared DB / settings / skill contracts | `WarpCore` |
| _rag_api_pid.txt | Runtime artifact: RAG API PID file (see Notes) | `_rag_api_pid.txt` |
| _start_rag_api.py | Runtime launcher for the RAG API subprocess (see Notes) | `_start_rag_api.py` |
| _warpcore_path.py | Path-resolution helper that locates `WarpCore` at runtime | `_warpcore_path.py` |
| app_config.json | Application-level configuration values | `app_config.json` |
| bootstrap.log | Bootstrap installation log | `bootstrap.log` |
| bootstrap.ps1 | Bootstrap installer | `bootstrap.ps1` |
| bootstrap_full_deps.ok | Bootstrap completion marker | `bootstrap_full_deps.ok` |
| bootstrap_phase_b_job.ps1 | Phase B bootstrap job script | `bootstrap_phase_b_job.ps1` |
| bootstrap_phase_b_result.txt | Phase B bootstrap result output | `bootstrap_phase_b_result.txt` |
| captains_log.md | Narrative or operational log file (Star Trek-themed naming) | `captains_log.md` |

### Notes on top-level entries

- **Pending classification** entries indicate paths whose purpose has not yet been confirmed by the knowledge-acquisition scan. They are present in the repository but lack a verified role description.
- The **Evidence** column shows the repository path observed during the scan that supports the listed classification.
- **`_rag_api_pid.txt`** stores the process ID for a running RAG API subprocess, enabling later status checks or graceful shutdown.
- **`_start_rag_api.py`** is a launcher script that initializes the RAG API subprocess.
- **`_warpcore_path.py`** is a path-resolution helper that dynamically locates the `WarpCore` package at runtime.
- **`app_config.json`** holds application-level configuration values.
- **Bootstrap artifacts** such as `bootstrap.log`, `bootstrap_full_deps.ok`, `bootstrap_phase_b_job.ps1`, and `bootstrap_phase_b_result.txt` are produced or consumed during the two-phase bootstrap installation process.
- **`captains_log.md`** is a narrative or operational log file, following the project's Star Trek-themed naming convention.


## SQLite 3 Database Architecture (`ship_computer.db`)

`ship_computer.db` is the central persistent storage layer for the Spock application. Built on SQLite 3, it provides a unified, file-based relational database that manages metadata, conversation history, configuration state, retrieval logs, and vector embeddings. The database is abstracted through `WarpCore`, which exposes standardized query interfaces to all stations and adapters.

In practical terms, `ship_computer.db` acts as the single source of truth for Spock’s knowledge base, session state, and retrieval behavior. It allows the application to maintain a local, portable, and low-dependency storage model while still supporting structured queries, full-text search, vector similarity search, and audit logging.

### Core Schema Concepts

While the exact table definitions are managed dynamically by `WarpCore`, the database logically partitions data into the following domains:

- **Document & Metadata Tables:** Store raw wiki content, codebase artifacts, logs, and associated metadata such as source, timestamp, tags, classification, access scope, and content hash.
- **Embedding & Vector Tables:** Hold high-dimensional vector representations of text chunks, along with model version, dimensionality, normalization state, and search metadata.
- **Conversation & Context Tables:** Track user sessions, prompt history, AI responses, retrieved context, feedback loops, and model routing decisions to maintain conversational continuity.
- **Configuration & State Tables:** Persist application settings, model selections, operator profiles, feature flags, cache policies, and runtime state.
- **Audit & Progress Tables:** Record retrieval steps, query filters, similarity scores, fallback events, and Deep Dive reasoning traces for debugging and auditability.

### Schema Domain Details

The following table summarizes the primary responsibilities of each logical schema domain.

| Domain | Primary Purpose | Typical Data Stored |
|---|---|---|
| Document & Metadata | Preserve source content and provenance | Document ID, source URI, title, chunk text, content hash, tags, classification, timestamps |
| Embedding & Vector | Enable semantic similarity search | Chunk ID, embedding model, vector dimension, vector payload, normalization flag, index metadata |
| Conversation & Context | Maintain session continuity and response history | Session ID, turn ID, user prompt, AI response, retrieved chunk IDs, model used, latency, feedback |
| Configuration & State | Store operator and application settings | Model routing, feature flags, operator profile, cache policy, runtime mode |
| Audit & Progress | Support observability and debugging | Retrieval step, filter applied, candidate count, similarity score, fallback reason, execution time |

This separation allows Spock to treat raw knowledge, semantic search, conversational state, and operational configuration as distinct but related concerns.

### Interaction with Ask AI and Deep Dive Inquiries

The Spock application routes user queries through two distinct retrieval pathways, both leveraging `ship_computer.db`:

1. **Ask AI (Standard Inquiry)**
   - Optimized for speed and conversational context.
   - Queries the conversation history table to inject relevant prior turns into the prompt.
   - Performs a lightweight vector similarity search against the embedding table, retrieving the top-k most relevant chunks.
   - Uses SQLite’s full-text search (FTS5) or indexed metadata filters to quickly narrow results before vector matching.
   - Returns a concise, context-aware response with minimal latency.

2. **Deep Dive (Advanced Inquiry)**
   - Designed for complex, multi-hop, or highly specific technical questions.
   - Triggers iterative retrieval loops: initial vector search → metadata filtering → secondary cross-reference queries → refined vector search.
   - Joins multiple tables to apply strict constraints such as date ranges, document types, classification levels, and confidence thresholds.
   - Retrieves larger context windows and may cache intermediate results in temporary SQLite tables to avoid redundant computation.
   - Supports chain-of-thought reasoning by logging each retrieval step to the progress log, enabling auditability and debugging.

`WarpCore` ensures transactional integrity, connection management, and graceful fallbacks if the database is locked, busy, or temporarily unavailable. All stations interact with `ship_computer.db` through asynchronous query builders, preventing UI thread blocking during heavy retrieval operations.

### Ask AI and Deep Dive Data Flow

The following table compares how the two inquiry modes use the database.

| Stage | Ask AI | Deep Dive |
|---|---|---|
| Query intake | Normalizes prompt and loads recent session context | Normalizes prompt and identifies multi-part or multi-hop intent |
| Initial retrieval | Lightweight vector search plus optional FTS5 keyword matching | Broader vector search with metadata pre-filtering |
| Context selection | Selects a small top-k set of chunks | Selects larger candidate sets and performs iterative refinement |
| Filtering | Basic access and relevance filters | Strict classification, date, source, and confidence filters |
| Reasoning support | Minimal intermediate logging | Logs each retrieval and refinement step for auditability |
| Response style | Concise, conversational, low-latency | Detailed, source-grounded, and traceable |
| Caching | Caches frequent query embeddings and top results | Caches intermediate candidate sets and cross-reference results |

In both modes, the database serves as the coordination point between semantic search, metadata filtering, session state, and response generation.

### Example Retrieval Pattern

A simplified retrieval pattern for both Ask AI and Deep Dive may resemble the following conceptual query:

```sql
SELECT
    c.chunk_id,
    c.chunk_text,
    d.title,
    d.source_uri,
    d.classification,
    d.updated_at,
    vec_distance_cosine(e.vector, :query_vector) AS similarity_score
FROM chunks c
JOIN documents d ON d.doc_id = c.doc_id
JOIN embeddings e ON e.chunk_id = c.chunk_id
WHERE d.classification = :allowed_classification
  AND d.updated_at >= :minimum_timestamp
ORDER BY similarity_score
LIMIT :top_k;
```

In Ask AI, `:top_k` is typically small and the query is optimized for fast response. In Deep Dive, the same pattern may be executed multiple times with different filters, expanded candidate sets, and cross-reference joins to build a more complete answer.

## Embedding LLM and Vector Database Integration

The Spock application relies on a Retrieval-Augmented Generation (RAG) pipeline that separates text encoding from response generation. This architecture ensures accurate, source-grounded answers while maintaining flexibility in model selection.

The pipeline has two distinct model roles:

- **Embedding model:** Converts text into numerical vectors for semantic search.
- **Generative LLM:** Produces the final natural-language response using retrieved context.

Keeping these roles separate allows Spock to optimize retrieval accuracy independently from response quality.

### Embedding LLM Role

The embedding model is a specialized neural network trained to convert unstructured text into fixed-dimensional numerical vectors. Unlike generative LLMs, it does not produce human-readable text. Instead, it maps semantically similar content to nearby points in a high-dimensional vector space.

Spock uses this model to:

- Ingest and chunk incoming wiki documents, code files, and logs.
- Generate vector representations for each chunk.
- Encode user queries into the same vector space for comparison.
- Support semantic matching between questions and knowledge-base content.
- Enable retrieval of relevant context before the generative LLM produces an answer.

The embedding model is therefore not responsible for answering the user directly. Its job is to make relevant information discoverable.

### Embedding Model Contract

For reliable retrieval, Spock treats the embedding model as a versioned component with a stable contract.

| Contract Element | Description |
|---|---|
| Model identifier | Unique name used for routing, logging, and cache invalidation |
| Vector dimension | Fixed number of dimensions produced for every text input |
| Normalization behavior | Whether vectors are normalized before storage or search |
| Similarity metric | Cosine, dot product, or Euclidean distance used during retrieval |
| Versioning | Allows Spock to distinguish old embeddings from new ones after model upgrades |
| Fallback behavior | Defines how Spock responds if the embedding service is unavailable |

This contract is important because changing the embedding model can change vector geometry. Spock therefore stores model metadata alongside each vector so that incompatible embeddings are not mixed during search.

### Vector Database Integration

The vector database stores and indexes these embeddings, enabling low-latency similarity searches. In Spock’s architecture, the vector store is tightly coupled with `ship_computer.db`, either through SQLite vector extensions such as `sqlite-vec` or a synchronized external vector backend.

The integration workflow operates as follows:

1. **Ingestion & Indexing:** Raw documents are parsed, chunked, and passed to the embedding model. Resulting vectors are stored alongside metadata in the vector table. Depending on the backend, an exact or approximate nearest-neighbor index may be built to accelerate search.
2. **Query Processing:** When a user submits a prompt, the query is embedded using the same model. The vector database performs a similarity search, typically using cosine similarity or dot-product distance, to retrieve the most relevant chunks.
3. **Context Assembly:** Retrieved chunks are ranked, deduplicated, and formatted into a structured context window. Metadata filters applied through SQLite ensure only authorized or relevant documents are included.
4. **RAG Generation:** The assembled context is injected into the prompt template and sent to the generative LLM. The model produces a final response grounded in the retrieved data.
5. **Caching & Optimization:** Frequently queried vectors and their results are cached in memory or SQLite to reduce redundant embedding calls. The `spock_rag_adapter` manages fallback strategies if the embedding service is unavailable.

### Vector Storage Options

Spock can operate with two broad vector storage strategies.

| Strategy | Description | Trade-offs |
|---|---|---|
| SQLite-native vector storage | Vectors are stored directly in `ship_computer.db`, often using a vector extension | Simpler deployment, local persistence, lower infrastructure overhead, suitable for moderate-scale knowledge bases |
| External vector backend | Vectors are stored in a dedicated vector database and synchronized with `ship_computer.db` | Better for very large corpora or high-throughput search, but requires additional synchronization and operational management |

In both cases, `ship_computer.db` remains the authoritative store for metadata, conversation state, configuration, and audit logs.

### Similarity Metrics

Vector search depends on the distance or similarity metric used to compare query embeddings with stored embeddings.

| Metric | Common Use | Notes |
|---|---|---|
| Cosine similarity | Semantic text matching | Measures angle between vectors; often preferred when vector magnitude is less important than direction |
| Dot product | Normalized vector search | Efficient and effective when vectors are normalized |
| Euclidean distance | Geometric distance comparison | Useful when vector magnitude and spatial distance are meaningful |

Spock records the metric and normalization state in the embedding metadata so that retrieval behavior remains consistent and auditable.

### Retrieval Quality Controls

To improve answer quality, Spock applies several controls after raw vector search:

- **Metadata filtering:** Restricts results to allowed classifications, sources, date ranges, and document types.
- **Deduplication:** Removes near-identical chunks that may appear from overlapping document sections.
- **Re-ranking:** Optionally reorders candidates using keyword overlap, recency, source authority, or user feedback.
- **Confidence thresholds:** Discards low-similarity results that are unlikely to be useful.
- **Context budgeting:** Limits the number of chunks injected into the generative prompt to avoid context overflow.
- **Fallback handling:** If vector search returns weak results, Spock may fall back to full-text search, broader metadata queries, or a clarification request.

These controls help ensure that the generative LLM receives relevant, authorized, and sufficiently specific context.

### Architecture Benefits

- **Decoupled Model Swapping:** Operators can change the embedding model or generative LLM independently without re-architecting the retrieval pipeline.
- **Deterministic Retrieval:** Vector search is reproducible and auditable, with every retrieval step logged to `ship_computer.db`.
- **Scalable Context Management:** The hybrid SQLite + vector approach allows Spock to handle large knowledge bases while maintaining low memory overhead and fast cold-start times.
- **Local Persistence:** The file-based database model reduces external dependencies and supports portable deployment.
- **Operational Observability:** Conversation, retrieval, and configuration state are stored together, making debugging and audit trails easier to reconstruct.

The `spock_rag_adapter` package orchestrates this entire flow, exposing clean APIs to the stations while handling model routing, vector dimension alignment, cache management, and error recovery.
## Entry points

- `main.py`
- `EngineeringDeck/__main__.py`
- `spock_bringup/__main__.py`
- `spock_bringup_menu/__main__.py`
- `spock_live_monitor/__main__.py`
- `spock_mcp_adapter/__main__.py`
- `spock_probe/__main__.py`
- `spock_progress_log/__main__.py`
- `spock_rag_adapter/__main__.py`
- `spock_shell/__main__.py`
- `spock_status/__main__.py`
- `spock_wiki_adapter/__main__.py`
- `python -m EngineeringDeck` — resolves to `EngineeringDeck/__main__.py`.
- `python -m spock_bringup` — resolves to `spock_bringup/__main__.py`.
- `python -m spock_bringup_menu` — resolves to `spock_bringup_menu/__main__.py`.
- `python -m spock_live_monitor` — resolves to `spock_live_monitor/__main__.py`.
- `python -m spock_mcp_adapter` — resolves to `spock_mcp_adapter/__main__.py`.
- `python -m spock_probe` — resolves to `spock_probe/__main__.py`.
- `python -m spock_progress_log` — resolves to `spock_progress_log/__main__.py`.
- `python -m spock_rag_adapter` — resolves to `spock_rag_adapter/__main__.py`.
- `python -m spock_shell` — resolves to `spock_shell/__main__.py`.
- `python -m spock_status` — resolves to `spock_status/__main__.py`.
- `python -m spock_wiki_adapter` — resolves to `spock_wiki_adapter/__main__.py`.

### How to read the entry-point list

Most subsystems expose two equivalent launch mechanisms:

1. **File-based entry point** — the specific `__main__.py` file listed in the first group. This identifies the executable module on disk.
2. **Module invocation** — the `python -m <package>` command listed in the second group, which resolves to the same package-level `__main__.py`.

The two groups are redundant by design: the first group names the file, while the second group shows the canonical command-line form. The module invocation form is generally preferred because it relies on Python's standard package resolution rather than a relative script path. `main.py` appears only in the file list because it serves as a standalone top-level application entry point, not a per-package `__main__.py`.

## Module boundaries (packages)

| Package | Path | Notes |
| --- | --- | --- |
| bootstrap_wizard | `bootstrap_wizard/` | Importable Python package |
| EngineeringDeck | `EngineeringDeck/` | Importable Python package |
| LongRangeSensors | `LongRangeSensors/` | Importable Python package |
| model_selector | `model_selector/` | Importable Python package |
| NavigationStation | `NavigationStation/` | Importable Python package |
| Orchestrator | `Orchestrator/` | Importable Python package |
| ScienceStation | `ScienceStation/` | Importable Python package |
| spock_bringup | `spock_bringup/` | Importable Python package |
| spock_bringup_menu | `spock_bringup_menu/` | Importable Python package |
| spock_codebase_knowledge | `spock_codebase_knowledge/` | Importable Python package |
| spock_live_monitor | `spock_live_monitor/` | Importable Python package |
| spock_mcp_adapter | `spock_mcp_adapter/` | Importable Python package |
| spock_onboarding | `spock_onboarding/` | Importable Python package |
| spock_probe | `spock_probe/` | Importable Python package |
| spock_progress_log | `spock_progress_log/` | Importable Python package |
| spock_rag_adapter | `spock_rag_adapter/` | Importable Python package |
| spock_shell | `spock_shell/` | Importable Python package |
| spock_status | `spock_status/` | Importable Python package |
| spock_wiki_adapter | `spock_wiki_adapter/` | Importable Python package |
| tests | `tests/` | Importable test package |
| WarpCore | `WarpCore/` | Importable Python package |

The `tests/` package is included in the boundary table because it can be imported by test runners and development tooling; it does not represent a production subsystem.

### Package grouping

The 20 non-test importable packages fall into four functional groups:

| Group | Packages | Role |
| --- | --- | --- |
| **Stations (operator GUIs)** | NavigationStation, ScienceStation, EngineeringDeck | Primary user-facing interfaces for navigation, science/wiki, and engineering operations. |
| **Core infrastructure** | WarpCore, spock_shell, model_selector | Shared database access, settings, skill contracts, UI widgets, shell behavior, and model management. |
| **Adapters (external bridges)** | spock_mcp_adapter, spock_rag_adapter, spock_wiki_adapter, spock_live_monitor, spock_probe, spock_status | Connect the application to external services or operational concerns: MCP integration, RAG/embeddings, wiki scanning, live monitoring, probing, and status reporting. |
| **Bringup / onboarding** | spock_bringup, spock_bringup_menu, spock_onboarding, bootstrap_wizard, spock_codebase_knowledge, spock_progress_log, Orchestrator, LongRangeSensors | Initial system setup, operator onboarding, codebase knowledge acquisition, progress tracking, orchestration, and related operational support. |

> **Note:** Several packages — including `Orchestrator`, `LongRangeSensors`, `spock_probe`, `spock_progress_log`, `spock_status`, and `spock_live_monitor` — are marked `[TODO]` in the top-level map, meaning their detailed purpose has not yet been fully documented by the knowledge-acquisition scan. Their placement in the grouping above is therefore inferred from naming conventions and the known roles of adjacent packages.

## SQLite 3 `ship_computer.db`

`ship_computer.db` is the local SQLite 3 database used by the Spock application to persist operational state, AI interaction history, retrieval metadata, and system configuration. It acts as the local system of record for the application, especially for features such as **Ask AI** and **Deep Dive**.

The database is expected to be accessed through shared infrastructure packages such as `WarpCore`, `spock_shell`, and adapter packages such as `spock_rag_adapter`, `spock_wiki_adapter`, and `spock_codebase_knowledge`. This keeps database access consistent across stations, adapters, and background processes.

### Purpose of `ship_computer.db`

The database provides a durable, local store for data that must survive application restarts. It is used to:

- Preserve operator settings and application configuration.
- Record Ask AI questions, retrieved context, model responses, and feedback.
- Track Deep Dive investigations, including plans, steps, evidence, and progress.
- Store metadata for codebase and wiki content used by retrieval-augmented generation.
- Maintain mappings between local records and external vector database entries.
- Support auditability by recording when data was indexed, queried, or updated.
- Enable resumable workflows for long-running Deep Dive operations.

### Relationship to the Spock application

The Spock application uses `ship_computer.db` as a coordination layer between user-facing stations, background adapters, and AI services.

For example:

- A station such as `ScienceStation`, `EngineeringDeck`, or `NavigationStation` may present an Ask AI or Deep Dive interface.
- `spock_shell` may provide the conversational or command-driven surface for user inquiries.
- `spock_rag_adapter` may use the database to store retrieval metadata and coordinate embedding operations.
- `spock_codebase_knowledge` and `spock_wiki_adapter` may register source documents, chunks, and freshness metadata.
- `spock_progress_log` may record the progress of Deep Dive investigations.
- `WarpCore` may provide shared database access, connection handling, and schema utilities.

In this model, `ship_computer.db` is not merely a settings file. It is the persistent backbone that allows the Spock application to remember what it has seen, what it has retrieved, what it has answered, and how far a Deep Dive investigation has progressed.

### Ask AI interaction with `ship_computer.db`

**Ask AI** is a short-form inquiry workflow. The operator asks a question, and the application returns an answer using available local knowledge, retrieved context, and a language model.

A typical Ask AI flow is:

1. The operator submits a question through a station, shell, or other user interface.
2. The application records the request in `ship_computer.db`, including the user, timestamp, station, and question text.
3. The question is normalized and prepared for retrieval.
4. The application generates or retrieves an embedding for the question.
5. The vector database is searched for semantically similar chunks from the codebase, wiki, or other indexed sources.
6. The retrieved chunks, along with their metadata, are stored or referenced in `ship_computer.db`.
7. A prompt is assembled using the question and retrieved context.
8. The language model generates an answer.
9. The answer, citations, confidence indicators, and model metadata are stored in `ship_computer.db`.
10. Optional operator feedback, such as acceptance, correction, or rejection, is recorded for future improvement.

The database therefore supports both the immediate response and the longer-term audit trail. It allows the application to answer:

- What did the operator ask?
- Which context was used?
- Which model produced the answer?
- Which sources were cited?
- Was the answer accepted or corrected?
- Can the same question be answered more consistently in the future?

### Deep Dive interaction with `ship_computer.db`

**Deep Dive** is a longer-form investigation workflow. Unlike Ask AI, which is optimized for a single answer, Deep Dive is designed to explore a topic across multiple sources, perform iterative retrieval, and produce a more detailed result.

A Deep Dive may involve:

- Multiple retrieval passes.
- Cross-referencing code, wiki pages, configuration, and operational logs.
- Tracking intermediate findings.
- Maintaining a plan or investigation state.
- Resuming after interruption.
- Producing a structured report rather than a single chat response.

`ship_computer.db` supports Deep Dive by storing:

- The original investigation request.
- The investigation plan or task breakdown.
- Each retrieval step and the sources consulted.
- Intermediate findings and evidence.
- Citations and source references.
- Progress state for resumability.
- Final report or summary.
- Operator annotations and follow-up questions.

This makes Deep Dive a stateful workflow rather than a one-shot prompt. The database allows the Spock application to pause, resume, audit, and refine the investigation over time.

### Logical data model

The exact schema may vary by deployment, but `ship_computer.db` is expected to contain logical entities such as the following:

| Entity | Purpose |
| --- | --- |
| Application settings | Stores operator preferences, model selections, and feature toggles. |
| Sessions | Tracks user sessions, active stations, and interaction context. |
| Ask AI requests | Stores each Ask AI question and its metadata. |
| Ask AI responses | Stores generated answers, model information, and response status. |
| Retrieved context | Stores or references the chunks used to answer a question. |
| Source documents | Tracks codebase files, wiki pages, and other indexed sources. |
| Document chunks | Stores chunk identifiers, source locations, and freshness metadata. |
| Embedding records | Maps chunks or queries to vector database entries. |
| Deep Dive investigations | Stores the top-level investigation request and state. |
| Deep Dive steps | Tracks individual investigation tasks or retrieval passes. |
| Evidence records | Stores findings, citations, and supporting context. |
| Progress log | Records workflow progress for resumable operations. |
| Audit events | Records important system and user actions for traceability. |

### Relationship to the vector database

`ship_computer.db` and the vector database serve different but complementary roles.

- `ship_computer.db` stores structured application state, interaction history, and metadata.
- The vector database stores high-dimensional embeddings and supports semantic similarity search.

In many deployments, `ship_computer.db` stores the local identifiers, source metadata, and mapping information, while the vector database stores the actual numeric vectors. This separation allows the application to maintain a durable local record even if the vector index is rebuilt, migrated, or hosted externally.

## Embedding LLM and vector database usage

The Spock application uses an **embedding LLM** and a **vector database** to support retrieval-augmented generation, or RAG. This allows the application to answer questions using relevant local knowledge rather than relying only on the language model's general training data.

### What is an embedding LLM?

An embedding LLM is a model that converts text into a numeric vector, also called an embedding. Each vector represents the semantic meaning of the text in a high-dimensional space.

For example:

- A question about database migration may be close to chunks discussing schema changes.
- A question about UI behavior may be close to chunks describing station interfaces.
- A question about model selection may be close to chunks describing `model_selector` behavior.

The embedding model is not the same as the generative language model that produces the final answer. Its role is to make text searchable by meaning rather than by exact keyword match.

### Why embeddings are needed

Keyword search can fail when the user's wording differs from the source text. For example, an operator may ask:

> "How does the app remember previous AI answers?"

The relevant documentation may say:

> "Ask AI responses are persisted in the local database for auditability."

A keyword search may miss this because the wording is different. An embedding-based search can still identify the relationship because both texts are semantically related.

### How the Spock application uses embeddings

The Spock application uses embeddings in two main ways:

1. **Indexing source content**
   - Codebase files, wiki pages, and other knowledge sources are split into chunks.
   - Each chunk is converted into an embedding vector.
   - The vector is stored in the vector database along with metadata.

2. **Searching for relevant context**
   - The user's Ask AI or Deep Dive question is converted into an embedding vector.
   - The vector database finds the most similar stored vectors.
   - The corresponding text chunks are returned as context for the language model.

### Chunking and indexing

Before text can be embedded, it is usually divided into smaller chunks. Chunking is important because:

- Large documents are too broad to embed as a single unit.
- Smaller chunks produce more precise retrieval.
- Metadata can be attached to each chunk, such as file path, line range, source type, and update time.

A typical indexing flow is:

1. A source document is discovered by `spock_codebase_knowledge`, `spock_wiki_adapter`, or another adapter.
2. The document is split into meaningful chunks.
3. Each chunk is sent to the embedding LLM.
4. The resulting vector is stored in the vector database.
5. Metadata about the chunk is stored in `ship_computer.db` or associated with the vector record.
6. The index is marked as current for that source.

### Vector database role

The vector database is responsible for storing embeddings and performing similarity search. It allows the application to ask:

> "Which stored chunks are most similar to this user question?"

The vector database may be:

- A dedicated external vector database.
- A SQLite-backed vector store.
- An in-process vector index.
- A hybrid store that combines vector search with structured metadata.

Regardless of implementation, the vector database provides the semantic search capability that makes Ask AI and Deep Dive useful.

### Ask AI retrieval flow

For an Ask AI inquiry, the application typically follows this flow:

1. The operator asks a question.
2. The question is embedded using the embedding LLM.
3. The vector database searches for the most similar chunks.
4. The top matching chunks are retrieved.
5. The chunks are filtered or reranked using metadata, permissions, freshness, or relevance scores.
6. The question and selected context are combined into a prompt.
7. The generative language model produces an answer.
8. The answer and supporting context are stored in `ship_computer.db`.

This flow allows the application to answer with evidence rather than relying only on the model's internal knowledge.

### Deep Dive retrieval flow

For a Deep Dive inquiry, the retrieval process is more iterative.

A typical Deep Dive flow is:

1. The operator requests an investigation.
2. The application creates an investigation record in `ship_computer.db`.
3. The initial question is embedded and searched.
4. The application reviews the retrieved context.
5. It may generate follow-up subquestions.
6. Each subquestion is embedded and searched.
7. Results are cross-referenced across code, wiki, configuration, and operational sources.
8. Intermediate findings are stored in the database.
9. The application continues until it has enough evidence or reaches a stopping condition.
10. A final summary or report is generated.
11. The investigation state, evidence, and citations are persisted.

This makes Deep Dive suitable for complex questions that require multiple retrieval passes and source reconciliation.

### Embedding lifecycle

Embeddings are not static. They must be maintained as source content changes.

The application should handle:

- **New content** — newly added files or wiki pages are chunked and embedded.
- **Changed content** — modified chunks are re-embedded and replaced.
- **Deleted content** — removed chunks are invalidated or deleted from the vector index.
- **Stale content** — old embeddings may be refreshed if the embedding model changes.
- **Model changes** — switching embedding models may require rebuilding the vector index.

`ship_computer.db` can store versioning and freshness metadata so the application knows whether an embedding is current.

### Why this matters for Spock

The combination of `ship_computer.db`, the embedding LLM, and the vector database gives the Spock application three important capabilities:

1. **Grounded answers**
   - Ask AI responses can be based on retrieved local knowledge.

2. **Traceability**
   - The application can record which sources supported an answer.

3. **Scalable investigation**
   - Deep Dive can perform repeated, evidence-based retrieval across multiple sources.

In short, the embedding LLM makes semantic search possible, the vector database makes that search efficient, and `ship_computer.db` makes the whole process persistent, auditable, and resumable.
## Data Persistence: `ship_computer.db` (SQLite 3)

The Spock application relies on a centralized SQLite 3 database named `ship_computer.db` for persistent storage, configuration management, and structured query routing. This database serves as the primary data backbone for both **Ask AI** and **Deep Dive** inquiry workflows, ensuring fast, reliable, and transaction-safe data access.

Because SQLite is an embedded, file-based database engine, Spock can store and query critical application data locally without requiring a separate database server. This makes `ship_computer.db` well suited for low-latency reads, durable writes, and portable deployment across environments.

### Interaction with Ask AI and Deep Dive

- **Ask AI Inquiries:** When a user submits a general question, the Spock application first queries `ship_computer.db` to retrieve relevant system state, user preferences, cached context, and recent interaction history. The database acts as a fast, structured lookup layer that filters out irrelevant data before passing a refined context window to the generative LLM. This ensures responses are grounded in the current operational state of the application without unnecessary token overhead.

- **Deep Dive Inquiries:** For complex, multi-step analytical requests, the application executes parameterized SQL queries against `ship_computer.db` to extract historical logs, sensor readings, configuration snapshots, and cross-referenced knowledge entries. The results are aggregated, normalized, and fed into the reasoning pipeline. The database's ACID compliance guarantees data integrity during these intensive read/write cycles, while application-level connection management and prepared statements optimize performance for high-frequency queries.

### Schema & Access Patterns

The database is accessed through a standardized data access layer that abstracts raw SQL operations. Key logical tables typically include:

- `system_state`: Tracks real-time operational metrics, subsystem statuses, and health indicators.
- `knowledge_cache`: Stores pre-processed documentation, wiki entries, and codebase metadata.
- `query_history`: Logs past Ask AI and Deep Dive interactions for auditability, context chaining, and performance analytics.
- `user_preferences`: Manages model selections, UI themes, inquiry thresholds, and routing rules.

All interactions are transactional, ensuring that concurrent inquiries do not corrupt state or return stale data. The SQLite journaling mode is configured for durability, and periodic vacuuming maintains optimal file size and query performance.

### SQLite 3 Operational Details

`ship_computer.db` is designed to function as a local, self-contained data store for the Spock application. Its SQLite 3 foundation provides several operational advantages:

- **Single-file storage:** The database is stored as a single file, which simplifies backup, migration, and deployment.
- **ACID transactions:** Reads and writes are committed atomically, reducing the risk of partial updates or corrupted state.
- **Concurrent access:** SQLite supports multiple concurrent readers and a single writer at a time. When configured with WAL mode, this improves read/write concurrency for interactive applications.
- **Prepared statements:** Repeated queries are compiled once and reused, reducing parsing overhead and improving query consistency.
- **Application-level connection management:** Spock manages database connections through its data access layer, allowing safe reuse of connections and controlled transaction boundaries.
- **Maintenance operations:** Periodic `VACUUM` and `ANALYZE` operations help control file growth and keep query planning efficient.

### Ask AI and Deep Dive Data Flow

The Spock application uses `ship_computer.db` differently depending on the inquiry type.

1. **Inquiry intake:** The user submits a question or analytical request through the Spock interface.
2. **Routing decision:** The application determines whether the request is best handled as an **Ask AI** inquiry or a **Deep Dive** inquiry.
3. **Structured context retrieval:** The data access layer queries `ship_computer.db` for relevant rows, such as current system state, user preferences, cached knowledge, and prior interaction context.
4. **Context assembly:** Retrieved records are normalized into a compact, structured context payload suitable for the generative LLM.
5. **Response generation or analysis:** For Ask AI, the model produces a concise answer. For Deep Dive, the application may perform additional SQL queries, semantic retrieval, and multi-step reasoning before producing a detailed result.
6. **Persistence:** The final interaction, retrieved context, and any derived analytical results are written back to `ship_computer.db` for auditability and future context reuse.

## Semantic Search & Context Retrieval: Embedding LLM and Vector Database

To handle unstructured data and enable semantic understanding, the Spock application integrates a dedicated embedding LLM alongside a vector database. This architecture powers the retrieval-augmented generation (RAG) pipeline that underpins both Ask AI and Deep Dive capabilities.

### Role of the Embedding LLM

The embedding LLM is a specialized model optimized for converting text into high-dimensional numerical vectors, also known as embeddings. Unlike generative LLMs, it does not produce conversational responses. Instead, it maps semantic meaning into a mathematical space where conceptually similar texts are positioned closer together.

In Spock, the embedding model is invoked during two distinct phases:

1. **Indexing:** When new documentation, codebase files, or wiki entries are ingested, the embedding LLM processes the content and generates fixed-length vectors.
2. **Query Encoding:** When a user submits an inquiry, the prompt is passed through the same embedding model to generate a query vector.

This shared embedding space allows Spock to compare a user's question against stored content using semantic similarity rather than exact keyword matching. As a result, the system can retrieve relevant information even when the user's wording differs from the source material.

### Vector Database Integration

The generated vectors are stored in a dedicated vector database optimized for similarity search. This database maintains an index, such as HNSW or IVF, that enables fast nearest-neighbor lookups. During an inquiry:

- The query vector is compared against the indexed corpus using distance metrics, typically cosine similarity or Euclidean distance.
- The top-k most relevant chunks are retrieved and ranked by relevance score.
- These chunks are filtered, deduplicated, and formatted into a structured context payload.
- The payload is injected into the prompt template for the generative LLM, ensuring that responses are factually grounded and context-aware.

### Workflow Synergy

The embedding LLM and vector database operate independently of the generative model to reduce latency and token consumption. By offloading semantic retrieval to this specialized pipeline, Spock ensures that Ask AI delivers concise, accurate answers while Deep Dive leverages the same retrieval mechanism to assemble comprehensive, multi-source evidence before initiating complex reasoning chains. This separation of concerns also allows the system to scale indexing operations independently of inference workloads.

### Embedding and Vector Search Details

The semantic search pipeline is designed to convert unstructured content into a form that can be efficiently retrieved and used by the generative LLM.

- **Chunking:** Large documents, code files, and wiki entries are split into smaller, meaningful chunks before embedding. This improves retrieval precision and reduces the amount of context sent to the generative model.
- **Metadata association:** Each vector is stored with metadata, such as source type, document title, timestamp, access level, and relevance tags. This allows Spock to filter results by context before ranking them.
- **Similarity scoring:** Retrieved chunks are scored based on vector distance. Cosine similarity is commonly used because it is effective for comparing semantic direction in high-dimensional spaces.
- **Top-k retrieval:** The vector database returns the most relevant chunks for a query, balancing recall and precision.
- **Deduplication and filtering:** Near-duplicate chunks are removed, and low-relevance or out-of-scope results are discarded before context assembly.
- **Hybrid retrieval:** In some workflows, Spock may combine vector similarity with structured database filters from `ship_computer.db`, allowing semantic search to be constrained by operational state, user preferences, or document type.

### Ask AI and Deep Dive Retrieval Flow

The same embedding and vector search infrastructure supports both inquiry types, but the retrieval strategy differs.

- **Ask AI:** The system performs a focused retrieval pass, selecting a small number of highly relevant chunks and structured records. The goal is to provide a concise, accurate answer with minimal context overhead.
- **Deep Dive:** The system performs broader retrieval across multiple sources, including structured database rows, cached knowledge, and semantic chunks. The retrieved evidence is then organized into a larger context set that supports multi-step reasoning, comparison, and synthesis.

This layered approach allows Spock to use `ship_computer.db` for precise, structured data access while using the embedding LLM and vector database for flexible, semantic understanding of unstructured content.
## Naming

Python module files consistently use `snake_case` (for example, `llm_client.py`). Package directories function as importable Python packages and follow two primary naming conventions in this project:

- `TitleCase` for station-style application packages (for example, `EngineeringDeck`, `NavigationStation`, `Orchestrator`, and `ScienceStation`).
- `snake_case` prefixed with `spock_` for auxiliary Spock-specific components.

This convention allows developers to quickly distinguish between core station modules and auxiliary Spock utilities without inspecting file contents or extensions.

### Raw scan excerpt

```
.env
.gitignore
_rag_api_pid.txt
_start_rag_api.py
_warpcore_path.py
AIHelperDocuments
app_config.json
bootstrap.log
bootstrap.ps1
bootstrap_full_deps.ok
bootstrap_phase_b_job.ps1
bootstrap_phase_b_result.txt
bootstrap_wizard
bootstrap_wizard\__init__.py
bootstrap_wizard\panel.py
bootstrap_wizard\steps.py
bootstrap_wizard\window.py
bootstrap_wizard\worker.py
captains_log.md
chat_ai_helper.py
config.json
db_browser.py
db_maintenance.py
deep_dive.py
docs
docs\.logic_cache.json
docs\architecture
docs\cli
docs\codebase
docs\codebase\.codebase-scan.txt
docs\codebase\ARCHITECTURE.md
docs\codebase\CONCERNS.md
docs\codebase\CONVENTIONS.md
docs\codebase\INTEGRATIONS.md
docs\codebase\STACK.md
docs\codebase\STRUCTURE.md
docs\codebase\TESTING.md
docs\configuration
docs\development
docs\features
docs\gen_logic.py
docs\gen_pages.py
docs\gen_schema.py
docs\gen_structure.py
docs\getting-started
docs\reference
docs\structure
docs\structure\bootstrap_wizard
docs\structure\EngineeringDeck
docs\structure\logic
docs\structure\LongRangeSensors
docs\structure\model_selector
docs\structure\NavigationStation
docs\structure\Orchestrator
docs\structure\ScienceStation
docs\structure\spock_bringup
docs\structure\spock_bringup_menu
docs\structure\spock_live_monitor
docs\structure\spock_mcp_adapter
docs\structure\spock_onboarding
docs\structure\spock_probe
docs\structure\spock_progress_log
docs\structure\spock_rag_adapter
docs\structure\spock_shell
docs\structure\spock_status
docs\structure\spock_wiki_adapter
docs\structure\WarpCore
docs_server.py
EngineeringDeck
EngineeringDeck\__init__.py
EngineeringDeck\__main__.py
EngineeringDeck\app.py
EngineeringDeck\ask_panel.py
EngineeringDeck\maintenance_app.py
EngineeringDeck\ship_computer_health.py
enhance.log
enhance_docs.py
first_models_last.json
gcloud-install.ps1
gemini_openai_models.py
helper_main.py
index.md
llama_server_manager.py
llm_client.py
llm_enhance.py
llm_enhance_sav.py
lm_studio_api.py
LongRangeSensors
LongRangeSensors\__init__.py
LongRangeSensors\app.py
LongRangeSensors\external_search_panel.py
LongRangeSensors\uieg_capture_panel.py
LongRangeSensors\uieg_crawler.py
LongRangeSensors\uieg_database.py
LongRangeSensors\uieg_import.py
LongRangeSensors\uieg_maintenance.py
LongRangeSensors\uieg_paths.py
LongRangeSensors\uieg_preview.py
LongRangeSensors\uieg_promote.py
LongRangeSensors\uieg_repo_fetch.py
LongRangeSensors\uieg_status.py
LongRangeSensors\web_search_clients.py
main.py
mcp_panel.py
mkdocs.yml
mkdocs.yml.sav
model_pick_policy.py
model_selector
model_selector\__init__.py
model_selector\embedding_panel.py
model_selector\hardware_panel.py
model_selector\launch_panel.py
model_selector\model_card.py
model_selector\models_panel.py
model_selector\state.py
model_selector\status_window.py
model_selector\widgets.py
model_selector\workers.py
model_selector_core.py
model_selector_panels.py
NavigationStation
NavigationStation\__init__.py
NavigationStation\app.py
NavigationStation\steps
NavigationStation\steps\__init__.py
NavigationStation\steps\configure.py
NavigationStation\steps\hardware.py
NavigationStation\steps\launch.py
NavigationStation\steps\status.py
Orchestrator
Orchestrator\__init__.py
Orchestrator\app.py
rag_api_server.py
requirements-dev.txt
requirements-docs.txt
requirements-full.txt
requirements-mcp.txt
requirements-ocr.txt
requirements-ui.txt
requirements.txt
reset.py
reset_ship_computer.py
reset_uieg.py
scan_config.json
ScienceStation
ScienceStation\__init__.py
ScienceStation\app.py
ScienceStation\
```

This excerpt represents a partial directory scan rather than a complete inventory. Directories containing `__init__.py` denote importable Python packages, whereas files ending in `.py` are standalone modules. Backslashes reflect the Windows-style path separator used by the scanning environment and do not alter the underlying naming conventions.

## Evidence

- Source: `D:\Spock-Universal-AI-Wiki\docs\codebase\.codebase-scan.txt`
- Filters applied: `.gitignore`, `scan.skip_dirs`, and built-in exclusion rules.
- The scan output validates the observed naming patterns. It should be interpreted as a snapshot of the scanned directory tree rather than a strict guarantee that every module or package adheres to a single uniform style.

## Data and Retrieval Architecture

The Spock application combines a local SQLite 3 database, an embedding LLM, and a vector database to support both Ask AI and Deep Dive workflows. The SQLite database provides durable, queryable state for documents, sessions, retrieval results, model state, and maintenance records. The embedding LLM converts text into numerical vectors, and the vector database uses those vectors to find semantically relevant content. Together, these components allow Spock to answer questions using local knowledge, preserve context, and support more complex multi-step research tasks.

### SQLite 3 `ship_computer.db`

`ship_computer.db` is the local SQLite 3 database used by the Spock application. It acts as the system of record for non-vector application state. In other words, it stores the structured information that the application needs to track, query, audit, and recover over time.

The database is embedded in the application environment. It does not require a separate database server, which makes it suitable for local, desktop, or ship-computer-style deployments. SQLite 3 provides transactional storage, relational queries, and file-based persistence, allowing Spock to maintain consistent state even when the application is restarted or when multiple local components need to read and write data.

#### Purpose

The primary purposes of `ship_computer.db` are to:

- Store document and chunk metadata used by retrieval workflows.
- Preserve Ask AI conversation history, prompts, responses, citations, and model metadata.
- Track Deep Dive runs, subtasks, evidence, intermediate results, and final reports.
- Record model selection, embedding model state, and local inference status.
- Support maintenance, health monitoring, reset, and diagnostic workflows.
- Provide a queryable source of truth for UI panels, maintenance tools, and debugging.

The vector database stores high-dimensional embeddings for semantic search. SQLite 3 stores the relational and operational data that surrounds those embeddings. This separation allows Spock to use vector similarity for recall while using SQL for filtering, auditing, session management, and application state.

#### Data domains

The scan does not expose the exact table definitions, but the module names indicate that the database supports several distinct data domains.

| Data domain | Representative modules | Stored information | Role in Spock |
|---|---|---|---|
| Documents and chunks | `spock_rag_adapter`, `spock_wiki_adapter`, `AIHelperDocuments` | Source documents, chunk text, chunk identifiers, source paths, hashes, status, and metadata | Provides the content that can be embedded, retrieved, and cited. |
| Ask AI sessions | `EngineeringDeck/ask_panel.py`, `llm_client.py` | User questions, generated answers, model used, prompt context, citations, timestamps, and status | Preserves the Ask AI interaction history and supports context-aware follow-up questions. |
| Deep Dive runs | `deep_dive.py`, `Orchestrator` | Run identifiers, subquestions, retrieval steps, evidence, intermediate summaries, final reports, and execution status | Enables complex, multi-step research workflows and allows the application to resume or audit a Deep Dive. |
| Model state | `model_selector`, `model_selector_core.py`, `llm_client.py`, `llama_server_manager.py` | Selected models, embedding model, generative model, local server status, and model availability | Tracks which models are active and supports model switching or recovery. |
| Health and maintenance | `EngineeringDeck/ship_computer_health.py`, `db_maintenance.py`, `reset_ship_computer.py` | Health events, maintenance jobs, reset actions, and diagnostic state | Supports local observability, cleanup, and recovery of the Spock environment. |

#### Ask AI interaction

Ask AI is the interactive question-and-answer workflow in which a user asks a question and Spock returns an answer grounded in available local knowledge. The SQLite database participates in this workflow at several stages.

1. **Question intake**  
   The user submits a question through the Ask AI interface, such as the panel represented by `EngineeringDeck/ask_panel.py`. The application records the question, user context, timestamp, and any active session identifier.

2. **Context preparation**  
   Before generating an answer, Spock may load prior conversation context, active document filters, or user preferences from `ship_computer.db`. This allows follow-up questions to remain connected to the previous exchange.

3. **Retrieval support**  
   The embedding LLM encodes the user question into a vector. The vector database returns candidate chunks that are semantically similar to the question. SQLite then supplies the structured metadata needed to validate, filter, and display those candidates, such as source document, chunk identifier, title, path, status, and citation information.

4. **Prompt construction**  
   The application builds a prompt for the generative LLM using the retrieved chunks, session context, and any system instructions. The prompt may include citations or source labels so that the model can reference the evidence it is using.

5. **Answer generation**  
   The generative LLM produces the answer. The application records the response, the model used, token or latency metadata where available, and the retrieval results that informed the answer.

6. **Persistence**  
   The completed Ask AI exchange is stored in `ship_computer.db`. This allows the user to review previous questions, inspect citations, restore context, or debug an answer later.

7. **Citation and auditability**  
   Because the database stores the relationship between an answer and the chunks used to generate it, Spock can show which local documents supported the response. This is important for trust, verification, and maintenance.

#### Deep Dive interaction

Deep Dive is a more complex research workflow. Instead of answering a single question directly, Spock breaks the request into multiple steps, retrieves evidence across several subtopics, and synthesizes a more detailed result.

The SQLite database is central to this process because Deep Dive requires durable state across multiple retrieval and generation steps.

1. **Run creation**  
   When a user starts a Deep Dive, the application creates a run record in `ship_computer.db`. This record identifies the request, the user, the timestamp, the selected models, and the initial status.

2. **Task decomposition**  
   The application may decompose the user request into subquestions or research steps. These steps are stored so that the workflow can be resumed, inspected, or debugged.

3. **Iterative retrieval**  
   For each subquestion, Spock uses the embedding LLM and vector database to retrieve relevant chunks. The retrieved chunk identifiers, similarity scores, and source metadata are stored in the database.

4. **Evidence accumulation**  
   As the Deep Dive progresses, the application accumulates evidence from multiple retrieval passes. SQLite stores the evidence rows, including which subquestion produced them, which chunks were selected, and how they were used.

5. **Intermediate synthesis**  
   The generative LLM may summarize or analyze intermediate evidence. These intermediate results are stored so that the final report can be reconstructed or audited.

6. **Final report generation**  
   After the research steps are complete, Spock generates a final Deep Dive report. The report, its supporting evidence, and the execution history are persisted in `ship_computer.db`.

7. **Review and maintenance**  
   Users can later inspect Deep Dive runs, compare evidence, review model choices, or reset state. Modules such as `db_browser.py`, `db_maintenance.py`, and `reset_ship_computer.py` support these operational workflows.

#### Maintenance and observability

Because `ship_computer.db` stores operational state, it also supports maintenance and health monitoring.

- `db_maintenance.py` can be used to inspect, clean, or optimize the local database.
- `db_browser.py` provides a way to view database contents for debugging or verification.
- `EngineeringDeck/ship_computer_health.py` can record or display the health of the local Spock environment.
- `reset_ship_computer.py` supports controlled reset workflows when the local state needs to be cleared or rebuilt.

These capabilities are important for a local AI system because the database may accumulate sessions, retrieval results, model state, and maintenance records over time.

### Embedding LLM and vector database

The embedding LLM and vector database are the semantic retrieval layer of the Spock application. They allow Spock to find relevant information based on meaning rather than only exact keyword matches.

#### Role of the embedding LLM

An embedding LLM is a model that converts text into a numerical vector. Each vector represents the semantic meaning of the text in a high-dimensional space. Text with similar meaning produces vectors that are close together, while text with different meaning produces vectors that are farther apart.

In Spock, the embedding LLM is used for two main purposes:

1. **Document embedding**  
   When documents or chunks are added to the knowledge base, the embedding LLM converts each chunk into a vector. That vector is stored in the vector database alongside metadata such as chunk identifier, source document, title, path, and status.

2. **Query embedding**  
   When a user asks a question through Ask AI or Deep Dive, the embedding LLM converts the question into a vector. The vector database then searches for stored vectors that are closest to the query vector.

The embedding LLM is distinct from the generative LLM. The embedding model is responsible for understanding meaning and producing vectors. The generative model is responsible for producing natural-language answers, summaries, or reports.

#### Role of the vector database

The vector database stores the embeddings produced by the embedding LLM. It is optimized for similarity search, meaning it can quickly find the stored vectors that are most similar to a query vector.

The vector database typically stores:

- The vector itself.
- A reference to the source chunk or document.
- Metadata used for filtering and display.
- Similarity or distance scores during search.

The vector database is not the primary store for conversation history, run state, or application metadata. Those responsibilities belong to `ship_computer.db`. Instead, the vector database is specialized for semantic recall.

#### Ingestion pipeline

The ingestion pipeline prepares local knowledge for retrieval.

1. **Source collection**  
   Spock gathers content from local documents, wiki adapters, AI helper documents, or other configured sources.

2. **Chunking**  
   Large documents are divided into smaller chunks. Chunking improves retrieval precision because the application can retrieve only the most relevant portions of a document rather than the entire file.

3. **Embedding**  
   Each chunk is passed to the embedding LLM. The model produces a vector representation of the chunk.

4. **Vector storage**  
   The vector is stored in the vector database. The chunk identifier and related metadata are also stored so that the vector can be mapped back to the original text.

5. **Metadata registration**  
   The corresponding chunk, document, and status information is recorded in `ship_computer.db`. This allows the application to filter, audit, and display the retrieved content.

#### Query pipeline

The query pipeline is used during Ask AI and Deep Dive.

1. **Question normalization**  
   The user question is cleaned, contextualized, and prepared for retrieval.

2. **Query embedding**  
   The embedding LLM converts the question into a vector.

3. **Vector search**  
   The vector database searches for the most similar stored vectors.

4. **Metadata filtering**  
   Spock uses `ship_computer.db` to filter results by document status, source type, user permissions, active workspace, or other metadata.

5. **Candidate ranking**  
   The application may rank candidates using similarity score, metadata relevance, recency, or other configured signals.

6. **Prompt assembly**  
   The selected chunks are inserted into a prompt for the generative LLM.

7. **Answer generation**  
   The generative LLM produces the final answer or Deep Dive synthesis.

8. **Result persistence**  
   The question, retrieved chunks, answer, model metadata, and citations are stored in `ship_computer.db`.

#### Use in Ask AI

In Ask AI, the embedding LLM and vector database provide fast, semantic retrieval for a single user question.

The workflow is generally:

- User asks a question.
- The question is embedded.
- The vector database retrieves relevant chunks.
- SQLite supplies metadata and session context.
- The generative LLM answers using the retrieved evidence.
- The answer and citations are stored.

This allows Ask AI to respond using local knowledge while preserving enough context for follow-up questions.

#### Use in Deep Dive

In Deep Dive, the embedding LLM and vector database are used repeatedly across multiple research steps.

The workflow is generally:

- User requests a detailed investigation.
- Spock decomposes the request into subquestions.
- Each subquestion is embedded and searched against the vector database.
- Evidence is collected and stored in SQLite.
- Intermediate summaries are generated.
- The final report is synthesized from the accumulated evidence.
- The full run history is persisted for review.

This makes Deep Dive more powerful than a single Ask AI query because it can explore multiple angles, gather broader evidence, and produce a more structured result.

#### Model management and local inference

The scan includes modules that indicate Spock supports local model management and inference.

- `model_selector` and `model_selector_core.py` likely support selecting and managing available models.
- `model_selector/embedding_panel.py` likely provides a UI for selecting or inspecting the embedding model.
- `llama_server_manager.py` and `lm_studio_api.py` suggest support for local LLM servers.
- `llm_client.py` likely provides the client used to call generative models.
- `rag_api_server.py` and `spock_rag_adapter` suggest a retrieval-augmented generation layer that connects the vector database, embedding model, and generative model.

This architecture allows Spock to operate with local models where possible, reducing dependence on external services and supporting the local ship-computer deployment model.

#### Failure and fallback behavior

Because the retrieval system depends on both the embedding LLM and the vector database, Spock must handle cases where one component is unavailable or degraded.

Possible failure conditions include:

- The embedding model is not loaded.
- The local inference server is unavailable.
- The vector database is empty or corrupted.
- A document has not been embedded yet.
- The generative model fails to produce a response.
- The SQLite database is locked or requires maintenance.

In such cases, Spock can rely on the state stored in `ship_computer.db` to report the problem, preserve partial results, retry the operation, or fall back to a simpler retrieval mode if configured. The exact fallback behavior depends on the application configuration, but the separation between SQLite state, vector storage, and model inference makes it possible to diagnose and recover from individual component failures.
## SQLite 3 `ship_computer.db` Architecture

The Spock application relies on a local SQLite 3 database named `ship_computer.db` as its primary persistence layer for state management, audit logging, and contextual memory. SQLite was selected for its zero-configuration deployment, ACID compliance, and efficient single-file architecture, which aligns with Spock's design as a self-contained, locally executable AI workstation.

### Schema & Data Organization

The database is structured around several core relational tables that support Spock's operational workflows:

- **`conversations` & `messages`**: Store session identifiers, timestamps, user prompts, AI responses, and metadata such as model used, token counts, latency, and response status.
- **`deep_dive_queries` & `analysis_results`**: Log structured research requests, intermediate reasoning steps, source citations, retrieval parameters, and final synthesized reports.
- **`system_state` & `config_cache`**: Persist runtime configurations, hardware profiles, model selection policies, and RAG pipeline settings.
- **`embedding_metadata`**: Maps document chunks to their corresponding vector identifiers, enabling traceability between the vector database and source files.

### Interaction with Ask AI

During **Ask AI** sessions, `ship_computer.db` functions as a conversational memory store and performance cache:

1. **Context Injection**: Before a prompt is sent to the generative LLM, the application queries the `messages` table to retrieve the most recent conversation history. This history is formatted into a system prompt to maintain continuity across turns.
2. **Response Persistence**: Once the LLM returns a response, it is immediately written to the database using parameterized queries to prevent SQL injection. This ensures that chat history survives application restarts.
3. **Caching & Deduplication**: Identical or highly similar user prompts are checked against a hash index. If a match exists, the cached response is served directly, reducing redundant LLM calls and lowering latency.

### Interaction with Deep Dive

The **Deep Dive** feature leverages the database for structured research tracking and reproducible analysis:

1. **Query Logging**: Each Deep Dive request is recorded with a unique trace ID, capturing the original question, search parameters, and execution timestamps.
2. **Source Attribution**: As the RAG pipeline retrieves documents, their metadata (file path, chunk index, confidence score) is stored in `embedding_metadata`. This allows the UI to render clickable citations and verify AI claims.
3. **State Rollback & Maintenance**: The `db_maintenance.py` and `reset_ship_computer.py` modules provide administrative routines to vacuum the database, rebuild indexes, or purge expired sessions without corrupting active inference pipelines.

The application maintains a persistent connection pool with Write-Ahead Logging (WAL) enabled, allowing concurrent read operations (e.g., UI polling for status updates) while write operations (e.g., logging new messages) occur in the background.

### Embedding LLM and Vector Database Integration

Spock uses an embedding model, often referred to in the application as the **embedding LLM**, together with a local vector database to provide semantic retrieval. This system complements `ship_computer.db` rather than replacing it. SQLite stores durable relational state, while the vector database stores high-dimensional numerical representations of text.

The embedding LLM converts text into dense vector embeddings. These embeddings capture semantic meaning rather than exact keyword matches. For example, the phrases “how does the RAG pipeline work?” and “explain the retrieval-augmented generation flow” can produce similar vectors even if they share few words.

#### Ingestion and Chunking

When Spock indexes documents, it performs the following steps:

1. **Document Parsing**: Files are read and converted into plain text or structured content.
2. **Chunking**: Long documents are split into smaller, semantically coherent chunks. Chunking improves retrieval precision because smaller passages are easier to rank and cite.
3. **Embedding Generation**: Each chunk is passed through the embedding LLM to produce a vector.
4. **Vector Storage**: The vector is stored in the vector database.
5. **Metadata Recording**: SQLite records the relationship between the chunk and its vector identifier, including file path, chunk index, content hash, timestamp, and source metadata.

This separation allows Spock to query vectors efficiently while preserving human-readable metadata in SQLite.

#### Embedding Generation

The embedding LLM produces a fixed-size vector for each input text. The same embedding model is used for both document chunks and user queries so that both exist in the same vector space.

Spock may batch embedding requests to improve throughput and cache embeddings for unchanged content. If a document chunk has not changed, its existing vector can be reused instead of regenerating it.

#### Vector Storage and Metadata Mapping

The vector database stores the numerical vectors and may also store lightweight payload data. SQLite stores the authoritative relational metadata needed for auditing, citations, and maintenance.

A typical mapping includes:

- `vector_id`: Identifier used by the vector database.
- `chunk_id`: Identifier for the source text chunk.
- `file_path`: Location of the original document.
- `chunk_index`: Position of the chunk within the document.
- `content_hash`: Hash used to detect unchanged content.
- `created_at`: Timestamp for when the embedding was generated.
- `confidence_score`: Optional score recorded during retrieval or reranking.

This mapping allows Spock to retrieve a vector match and then resolve it back to a concrete source passage.

#### Query-Time Retrieval

When a user submits an Ask AI or Deep Dive request, Spock uses the embedding LLM and vector database as follows:

1. **Query Embedding**: The user prompt is converted into a vector using the same embedding model used for indexed content.
2. **Similarity Search**: The vector database searches for the most semantically similar chunks.
3. **Metadata Filtering**: SQLite metadata may be used to filter results by file type, date, source, or session context.
4. **Reranking**: Retrieved chunks may be reranked using relevance scores, keyword overlap, or a secondary ranking model.
5. **Context Assembly**: The top-ranked chunks are formatted into a prompt context for the generative LLM.
6. **Response Generation**: The generative LLM produces an answer grounded in the retrieved context.
7. **Citation Recording**: The source chunks used to generate the response are recorded in SQLite for auditability.

#### Ask AI Use of Embeddings

In **Ask AI**, the embedding system supports conversational grounding. The application may combine recent conversation history from SQLite with semantically relevant chunks from the vector database.

For example, if a user asks, “What did the previous analysis say about model latency?”, Spock can:

- Retrieve recent messages from `messages`.
- Embed the current question.
- Search the vector database for relevant prior analysis chunks.
- Record the retrieved sources in `embedding_metadata`.
- Generate a response that references both conversation context and indexed evidence.

This allows Ask AI to behave like a memory-aware assistant rather than a stateless chat interface.

#### Deep Dive Use of Embeddings

In **Deep Dive**, the embedding system supports broader, multi-step research. Instead of relying on a single retrieval pass, Spock may generate multiple subqueries, retrieve candidate chunks, refine the search, and synthesize a structured report.

The workflow typically includes:

1. **Question Decomposition**: The original Deep Dive question is broken into smaller research subquestions.
2. **Iterative Retrieval**: Each subquestion is embedded and used to query the vector database.
3. **Source Aggregation**: Retrieved chunks are grouped by source, topic, or confidence.
4. **Evidence Ranking**: The most relevant and trustworthy chunks are selected for synthesis.
5. **Report Generation**: The generative LLM produces a structured analysis with citations.
6. **Persistence**: The query trace, retrieved sources, and final report are stored in `deep_dive_queries` and `analysis_results`.

This makes Deep Dive reproducible because the application can later inspect which chunks influenced the final answer.

### Consistency, Caching, and Maintenance

Spock treats `ship_computer.db` as the source of truth for relational state and audit data. The vector database is treated as a retrieval index that can be rebuilt if necessary.

Key operational behaviors include:

- **WAL Mode**: Enables concurrent reads while writes are committed safely.
- **Parameterized Queries**: Prevents SQL injection when persisting prompts, responses, and metadata.
- **Hash-Based Caching**: Reduces repeated embedding or LLM calls for unchanged content.
- **Trace IDs**: Link Ask AI and Deep Dive operations to their underlying retrieval and generation steps.
- **Maintenance Routines**: Allow Spock to vacuum the database, rebuild indexes, and remove expired sessions without disrupting active workloads.

Together, SQLite, the embedding LLM, and the vector database form a local retrieval-augmented generation stack. SQLite provides durable state and auditability, the embedding LLM provides semantic understanding, and the vector database provides fast similarity search over indexed knowledge.
## Embedding LLM and Vector Database Integration

Spock implements a Retrieval-Augmented Generation (RAG) architecture to ground AI responses in verified, locally stored knowledge. This pipeline decouples semantic search from text generation by using a dedicated embedding model and a vector database.

### The Embedding LLM

Unlike the primary generative LLM, the embedding model is optimized for high-dimensional vectorization rather than natural language generation. It converts unstructured text—such as wiki pages, technical documentation, user queries, and crawled repositories—into dense numerical vectors that capture semantic meaning.

Key characteristics include:

- **Fixed Output Dimensionality**: The embedding model produces vectors of a fixed size, commonly 384, 768, or 1536 dimensions, depending on the selected model. Examples include `nomic-embed-text`, `all-MiniLM-L6-v2`, or custom fine-tuned variants.
- **Resource Efficiency**: The embedding model can run on CPU or low-tier GPU hardware. This allows Spock to perform continuous background indexing without competing for VRAM with the generative model.
- **Semantic Query Transformation**: When a user submits an Ask AI or Deep Dive prompt, the embedding LLM first vectorizes the query. This allows Spock to search for semantically related content rather than relying on exact keyword matching.
- **Deterministic Representation**: For a given input and model version, the embedding model produces a consistent vector. Spock stores the model name and version in `ship_computer.db` so that retrieval results can be audited and reproduced.

### The Vector Database

The vector database serves as the high-performance index for all embedded knowledge. It stores vectors alongside metadata filters such as source type, creation date, access permissions, chunk boundaries, document identifiers, and content hashes.

Spock's integration follows this workflow:

1. **Ingestion and Chunking**  
   Documents are parsed, split into overlapping semantic chunks, and passed through the embedding LLM. The resulting vectors are upserted into the vector database via `spock_rag_adapter`.

2. **Similarity Search**  
   During inference, the vectorized user query is compared against the index using Approximate Nearest Neighbor (ANN) algorithms such as HNSW or IVF-PQ. The top-k most relevant chunks are retrieved based on cosine similarity or dot-product distance.

3. **Context Assembly**  
   Retrieved chunks are ranked, deduplicated, and formatted into a structured context window. Metadata filters ensure that only authorized or relevant documents are injected into the prompt.

4. **Generative Handoff**  
   The assembled context, combined with the original user query and system instructions, is passed to `llm_client.py`. The generative LLM then produces a grounded, citation-ready response.

### Operational Synergy

The separation of embedding and generative workloads provides Spock with significant architectural advantages:

- **Latency Optimization**: Vector search completes in milliseconds, allowing the UI to display “searching” states before the heavier generative model begins processing.
- **Scalability**: New documents can be indexed asynchronously without interrupting active Ask AI or Deep Dive sessions.
- **Traceability**: Every vector retrieval is logged in `ship_computer.db`, enabling full audit trails for compliance, debugging, and prompt-engineering refinement.
- **Local Control**: Because both the vector index and relational state are managed locally, Spock can operate with strict data locality and reduced dependence on external services.

This dual-model RAG pipeline ensures that Spock delivers accurate, context-aware responses while maintaining strict control over data locality and computational resource allocation.

### SQLite 3 `ship_computer.db` Integration

`ship_computer.db` is Spock’s local SQLite 3 database. It provides durable, transactional, relational state for the application. While the vector database is optimized for semantic similarity search, `ship_computer.db` is optimized for structured queries, joins, permissions, audit logging, and workflow state.

In other words, the vector database answers the question:

> “Which chunks are semantically similar to this query?”

`ship_computer.db` answers the questions:

> “Who asked the question?”  
> “Which documents were allowed to be searched?”  
> “Which chunks were retrieved?”  
> “What was the final answer?”  
> “What evidence supported a Deep Dive?”  
> “Can this result be reproduced or audited?”

This separation gives Spock a clean boundary between semantic retrieval and application state.

#### Relationship Between the Vector Database and `ship_computer.db`

The vector database and `ship_computer.db` are complementary stores:

| Concern | Vector Database | `ship_computer.db` |
|---|---|---|
| Primary purpose | Semantic similarity search | Relational state, audit, and workflow tracking |
| Main data type | Dense vectors and lightweight metadata | Structured rows, foreign keys, timestamps, permissions |
| Query style | ANN search, cosine similarity, dot product | SQL queries, joins, filters, transactions |
| Typical use | Retrieve top-k relevant chunks | Record requests, citations, Deep Dive steps, and audit events |
| Strength | Fast semantic ranking | Durable, inspectable, reproducible state |
| Weakness if used alone | Poor fit for complex relational workflows | Poor fit for high-dimensional semantic search |

Spock uses `spock_rag_adapter` to coordinate writes and reads across both stores. The adapter ensures that vector retrieval results are linked to the correct request, user, permission scope, document version, and Deep Dive step.

#### Key Data Domains in `ship_computer.db`

The database is organized around the following logical data domains:

| Table or Domain | Purpose |
|---|---|
| `ai_requests` | Stores Ask AI prompts, model configuration, permission scope, status, and final response metadata. |
| `rag_queries` | Stores the vectorized search query, embedding model version, search parameters, and top-k settings. |
| `retrieved_chunks` | Stores the chunks returned by the vector database, including chunk IDs, scores, source references, and retrieval rank. |
| `citations` | Stores citation metadata linking generated answer sections to retrieved chunks and source documents. |
| `documents` | Stores document-level metadata such as title, source URI, content hash, creation date, and access permissions. |
| `chunks` | Stores chunk-level metadata such as chunk boundaries, parent document, content hash, and vector database object reference. |
| `deep_dive_runs` | Stores the top-level Deep Dive research task, including objective, status, and final report reference. |
| `deep_dive_steps` | Stores individual research steps, subquestions, intermediate findings, and step status. |
| `evidence_items` | Stores evidence collected during a Deep Dive, including source, relevance, confidence, and supporting text. |
| `audit_logs` | Stores immutable or append-only records of user actions, model calls, retrieval events, and permission checks. |

These domains allow Spock to reconstruct the full lifecycle of an Ask AI or Deep Dive request.

#### How Ask AI Uses `ship_computer.db`

Ask AI is Spock’s grounded question-answering mode. It is designed for single-turn or short multi-turn questions where the user expects a direct answer supported by local knowledge.

The Ask AI workflow interacts with `ship_computer.db` as follows:

1. **Request Creation**  
   When the user submits an Ask AI prompt, Spock creates an `ai_requests` record. This record captures the user, timestamp, prompt text, model configuration, permission scope, and request status.

2. **Permission and Scope Resolution**  
   Before search begins, Spock resolves the user’s access permissions and document scope. This ensures that the vector database query is constrained to documents the user is allowed to see.

3. **Query Embedding**  
   The embedding LLM converts the user prompt into a vector. Spock records the embedding model name, model version, and query vector metadata in `rag_queries`.

4. **Vector Search**  
   `spock_rag_adapter` sends the query vector to the vector database. The vector database returns the top-k most relevant chunks, along with similarity scores and chunk identifiers.

5. **Retrieval Logging**  
   Spock writes the retrieved chunks into `retrieved_chunks`. This includes the chunk ID, source document, similarity score, rank, and retrieval timestamp.

6. **Context Assembly**  
   Spock uses `ship_computer.db` metadata to deduplicate chunks, enforce permissions, and assemble the final context window. The database may also provide chunk boundaries, source titles, and document metadata for citation formatting.

7. **Generative Response**  
   The assembled context is passed to `llm_client.py`. The generative LLM produces the final answer.

8. **Citation and Response Storage**  
   Spock stores the final response metadata in `ai_requests` and writes citation records to `citations`. Each citation links a portion of the answer to the supporting chunk and source document.

9. **Audit and Feedback**  
   The request, retrieval results, model versions, and user feedback are recorded in `audit_logs` or related tables. This allows Spock to debug poor answers, improve prompts, and verify that only authorized content was used.

This workflow makes Ask AI reproducible. If a response is disputed, Spock can inspect the exact query, the exact retrieved chunks, the exact permission scope, and the exact model versions used.

#### How Deep Dive Uses `ship_computer.db`

Deep Dive is Spock’s multi-step research mode. Unlike Ask AI, which is optimized for a single grounded answer, Deep Dive is designed for iterative investigation, source discovery, evidence collection, and synthesis.

`ship_computer.db` is central to Deep Dive because Deep Dive requires durable state across many steps.

The Deep Dive workflow interacts with `ship_computer.db` as follows:

1. **Run Creation**  
   When the user starts a Deep Dive, Spock creates a `deep_dive_runs` record. This record stores the research objective, user, permission scope, status, and final report reference.

2. **Research Planning**  
   Spock decomposes the research objective into subquestions or investigation steps. Each step is stored in `deep_dive_steps`.

3. **Semantic Discovery**  
   For each step, the embedding LLM vectorizes the subquestion. The vector database is then queried for relevant chunks, documents, or source candidates.

4. **Source Tracking**  
   Spock records discovered sources in `documents` and `chunks`. This prevents duplicate crawling, duplicate retrieval, and redundant processing.

5. **Evidence Collection**  
   Relevant passages are stored as `evidence_items`. Each evidence item links to a source, a chunk, a Deep Dive step, and a relevance or confidence score.

6. **Intermediate Synthesis**  
   As the Deep Dive progresses, Spock may generate intermediate summaries for each step. These summaries are stored in `deep_dive_steps` or related synthesis tables.

7. **Cross-Step Reasoning**  
   Because all evidence is stored relationally, Spock can query across steps to identify contradictions, gaps, recurring themes, or missing sources.

8. **Final Report Generation**  
   The final Deep Dive report is generated by the generative LLM using the accumulated evidence. The report reference is stored in `deep_dive_runs`.

9. **Provenance and Audit**  
   Every claim in the final report can be traced back to evidence items, chunks, documents, and retrieval events. This provenance chain is stored in `ship_computer.db`.

This makes Deep Dive more than a long Ask AI prompt. It is a structured research workflow with persistent state, evidence tracking, and auditability.

#### Consistency, Audit, and Local Control

`ship_computer.db` gives Spock several operational guarantees:

- **Transactional Integrity**: SQLite transactions allow Spock to write request state, retrieval results, and response metadata atomically.
- **Reproducibility**: Model versions, query parameters, retrieved chunks, and permission scopes are stored, allowing Spock to reconstruct past answers.
- **Auditability**: `audit_logs` and related tables provide a durable record of what was searched, what was retrieved, and what was generated.
- **Permission Enforcement**: Access scopes are resolved before vector search and enforced during context assembly.
- **Local Persistence**: Because the database is local, Spock can maintain full control over sensitive research data and user history.
- **Debuggability**: Developers can inspect the exact relationship between a user prompt, retrieved evidence, and final response.

Together, the embedding LLM, vector database, and `ship_computer.db` form a coherent RAG system. The embedding LLM converts language into searchable meaning, the vector database retrieves semantically relevant knowledge, and `ship_computer.db` preserves the application state, permissions, citations, and audit trail required for reliable Ask AI and Deep Dive experiences.
## Naming

- Python modules: use `snake_case` file names, such as `llm_client.py`, `db_maintenance.py`, and `rag_api_server.py`.
- Packages: in this codebase, use `TitleCase` for station packages, such as `EngineeringDeck`, `NavigationStation`, `ScienceStation`, `Orchestrator`, `WarpCore`, and `LongRangeSensors`, or use `snake_case` for `spock_*` packages.

### Naming guidance

- Station packages are named after the application’s themed subsystems. They represent major functional areas of the ship-computer experience, such as engineering operations, navigation setup, science workflows, orchestration, warp-core management, and long-range sensing.
- `spock_*` names identify Spock-specific helper, adapter, or integration modules. The common prefix groups related support code that assists the broader Spock workflow without being a primary station package.
- Leading-underscore files, such as `_start_rag_api.py` and `_warpcore_path.py`, are internal helper scripts. They typically perform local startup, path resolution, maintenance, or environment setup tasks and should be treated as implementation details rather than public entry points.

### Raw scan excerpt

```
.env
.gitignore
_rag_api_pid.txt
_start_rag_api.py
_warpcore_path.py
AIHelperDocuments
app_config.json
bootstrap.log
bootstrap.ps1
bootstrap_full_deps.ok
bootstrap_phase_b_job.ps1
bootstrap_phase_b_result.txt
bootstrap_wizard
bootstrap_wizard\__init__.py
bootstrap_wizard\panel.py
bootstrap_wizard\steps.py
bootstrap_wizard\window.py
bootstrap_wizard\worker.py
captains_log.md
chat_ai_helper.py
config.json
db_browser.py
db_maintenance.py
deep_dive.py
docs
docs\.logic_cache.json
docs\architecture
docs\cli
docs\codebase
docs\codebase\.codebase-scan.txt
docs\codebase\ARCHITECTURE.md
docs\codebase\CONCERNS.md
docs\codebase\CONVENTIONS.md
docs\codebase\INTEGRATIONS.md
docs\codebase\STACK.md
docs\codebase\STRUCTURE.md
docs\codebase\TESTING.md
docs\configuration
docs\development
docs\features
docs\gen_logic.py
docs\gen_pages.py
docs\gen_schema.py
docs\gen_structure.py
docs\getting-started
docs\reference
docs\structure
docs\structure\bootstrap_wizard
docs\structure\EngineeringDeck
docs\structure\logic
docs\structure\LongRangeSensors
docs\structure\model_selector
docs\structure\NavigationStation
docs\structure\Orchestrator
docs\structure\ScienceStation
docs\structure\spock_bringup
docs\structure\spock_bringup_menu
docs\structure\spock_live_monitor
docs\structure\spock_mcp_adapter
docs\structure\spock_onboarding
docs\structure\spock_probe
docs\structure\spock_progress_log
docs\structure\spock_rag_adapter
docs\structure\spock_shell
docs\structure\spock_status
docs\structure\spock_wiki_adapter
docs\structure\WarpCore
docs_server.py
EngineeringDeck
EngineeringDeck\__init__.py
EngineeringDeck\__main__.py
EngineeringDeck\app.py
EngineeringDeck\ask_panel.py
EngineeringDeck\maintenance_app.py
EngineeringDeck\ship_computer_health.py
enhance.log
enhance_docs.py
first_models_last.json
gcloud-install.ps1
gemini_openai_models.py
helper_main.py
index.md
llama_server_manager.py
llm_client.py
llm_enhance.py
llm_enhance_sav.py
lm_studio_api.py
LongRangeSensors
LongRangeSensors\__init__.py
LongRangeSensors\app.py
LongRangeSensors\external_search_panel.py
LongRangeSensors\uieg_capture_panel.py
LongRangeSensors\uieg_crawler.py
LongRangeSensors\uieg_database.py
LongRangeSensors\uieg_import.py
LongRangeSensors\uieg_maintenance.py
LongRangeSensors\uieg_paths.py
LongRangeSensors\uieg_preview.py
LongRangeSensors\uieg_promote.py
LongRangeSensors\uieg_repo_fetch.py
LongRangeSensors\uieg_status.py
LongRangeSensors\web_search_clients.py
main.py
mcp_panel.py
mkdocs.yml
mkdocs.yml.sav
model_pick_policy.py
model_selector
model_selector\__init__.py
model_selector\embedding_panel.py
model_selector\hardware_panel.py
model_selector\launch_panel.py
model_selector\model_card.py
model_selector\models_panel.py
model_selector\state.py
model_selector\status_window.py
model_selector\widgets.py
model_selector\workers.py
model_selector_core.py
model_selector_panels.py
NavigationStation
NavigationStation\__init__.py
NavigationStation\app.py
NavigationStation\steps
NavigationStation\steps\__init__.py
NavigationStation\steps\configure.py
NavigationStation\steps\hardware.py
NavigationStation\steps\launch.py
NavigationStation\steps\status.py
Orchestrator
Orchestrator\__init__.py
Orchestrator\app.py
rag_api_server.py
requirements-dev.txt
requirements-docs.txt
requirements-full.txt
requirements-mcp.txt
requirements-ocr.txt
requirements-ui.txt
requirements.txt
reset.py
reset_ship_computer.py
reset_uieg.py
scan_config.json
ScienceStation
ScienceStation\__init__.py
ScienceStation\app.py
ScienceStation\
```

### Scan excerpt notes

- The excerpt is a raw directory listing from the scan.
- Backslashes are Windows path separators.
- Entries ending in `.py` are Python modules; entries without extensions may be directories/packages or data files.
- A directory that contains `__init__.py`, such as `EngineeringDeck\__init__.py`, indicates a Python package.

## Evidence

- `D:\Spock-Universal-AI-Wiki\docs\codebase\.codebase-scan.txt`
- Filters: `.gitignore` + `scan.skip_dirs` + built-in extras

### Evidence notes

- The scan file is the source of the raw excerpt.
- The listed filters reduce the scan to relevant project files and exclude ignored, skipped, or built-in extra paths.


## SQLite 3 Database Architecture: `ship_computer.db`

The `ship_computer.db` file serves as the central relational database for the Spock application, leveraging SQLite 3 for lightweight, serverless, and zero-configuration data persistence. It acts as the authoritative source of truth for application state, user configurations, session tracking, audit logging, and metadata indexing.

Unlike the vector database, which is optimized for semantic similarity and approximate nearest-neighbor search, `ship_computer.db` manages structured relational data required for deterministic operations, workflow orchestration, and reproducible application behavior. In practice, the two storage layers are complementary:

- **SQLite 3 (`ship_computer.db`)** stores exact records, timestamps, identifiers, task states, configuration values, and audit trails.
- **The vector database** stores high-dimensional embeddings and supports semantic retrieval over text content.

This separation allows Spock to combine deterministic state management with flexible semantic search.

### Core Schema & Functional Domains

- **Configuration & State Management:**  
  Stores persistent user preferences, model selection policies (`first_models_last.json` mappings), hardware profiles, and runtime environment variables. This ensures settings survive application restarts without requiring external configuration services.

- **Health & Maintenance Tracking:**  
  Modules such as `db_maintenance.py` and `EngineeringDeck/ship_computer_health.py` write diagnostic metrics, uptime logs, and system integrity checks to dedicated tables. This enables proactive monitoring, troubleshooting, and automated recovery routines.

- **Session & Workflow Metadata:**  
  Tracks active and historical sessions for both interactive and background processes, including progress markers, error states, resource allocation records, and workflow checkpoints.

- **Audit & Traceability:**  
  Records user actions, AI query submissions, Deep Dive task execution, document ingestion events, and maintenance operations. This provides a durable audit trail for debugging, compliance, and reproducibility.

### Interaction with "Ask AI" Inquiries

When a user initiates an "Ask AI" query via `chat_ai_helper.py` or `EngineeringDeck/ask_panel.py`, the application performs the following relational operations:

1. **Context Retrieval & Caching:**  
   The database stores recent conversation history, prompt templates, cached LLM responses, and retrieval metadata. This reduces redundant API calls, maintains conversational continuity, and allows the application to reconstruct prior context after restarts.

2. **Rate Limiting & Cost Tracking:**  
   Each query is logged with timestamps, token usage estimates, model identifiers, latency measurements, and response status. This data is used to enforce usage policies, detect anomalies, and provide transparent cost and performance reporting.

3. **Response Validation:**  
   Before delivering an AI-generated response, the system cross-references the output against stored safety filters, domain-specific constraints, and user-defined guardrails stored in the relational schema.

4. **Retrieval Coordination:**  
   For questions that require external knowledge, `ship_computer.db` stores references to relevant documents, chunks, source identifiers, and vector database search results. This allows the application to combine semantic retrieval with deterministic citation and provenance tracking.

### Interaction with "Deep Dive" Inquiries

The "Deep Dive" feature, orchestrated by `deep_dive.py`, relies heavily on `ship_computer.db` for stateful, long-running analytical workflows:

1. **Task Queue & Progress Logging:**  
   Deep Dive operations are broken into discrete steps such as crawling, parsing, chunking, embedding, analysis, and reporting. Each step's status, completion percentage, timestamps, and intermediate artifacts are recorded in the database, allowing users to pause, resume, or inspect progress without losing context.

2. **Document & Source Indexing:**  
   When `LongRangeSensors` or `spock_wiki_adapter` ingest external documents, the database stores source URLs, file hashes, ingestion timestamps, processing flags, and content fingerprints. This prevents duplicate processing and ensures traceability for every piece of retrieved information.

3. **Result Aggregation:**  
   Final analysis outputs, extracted entities, cross-referenced findings, and generated summaries are stored in structured tables. This enables the UI to render detailed reports, generate citations, and allow users to export or archive Deep Dive sessions.

4. **Embedding Pipeline State:**  
   The database tracks which documents and chunks have been embedded, which embedding model version was used, and whether re-embedding is required after model or chunking changes. This prevents inconsistent semantic indexes and supports safe upgrades.

### Embedding LLM & Vector Database Integration

The Spock application uses an embedding LLM and a vector database to support semantic understanding, retrieval, and knowledge synthesis. This layer is especially important for "Ask AI" and "Deep Dive" workflows, where the application must locate relevant information from large or unstructured text sources.

#### 1. Text Chunking

Before embedding, Spock breaks source content into manageable chunks. Chunking may be based on:

- Paragraph boundaries
- Section headings
- Token limits
- Document structure
- Semantic boundaries

Each chunk is assigned a stable identifier and associated metadata, such as:

- Source document ID
- Source URL or file path
- Chunk index
- Content hash
- Ingestion timestamp
- Processing status
- Embedding model version

This metadata is stored in `ship_computer.db`, while the resulting vector is stored in the vector database.

#### 2. Embedding Generation

The embedding LLM converts each text chunk into a dense numerical vector. This vector represents the semantic meaning of the chunk in a high-dimensional space. Similar concepts are placed closer together, while unrelated concepts are placed farther apart.

The embedding process is deterministic for a given model version and input text, but the resulting vectors are not human-readable. They are optimized for mathematical similarity comparison.

Spock records the following information in the relational database:

- Which embedding model was used
- When the embedding was generated
- Which chunk was embedded
- Whether the embedding succeeded
- Whether the chunk requires re-embedding

This allows the application to maintain consistency when models, prompts, or chunking strategies change.

#### 3. Vector Database Storage

The vector database stores the generated embeddings alongside lightweight metadata required for retrieval. Unlike SQLite, the vector database is optimized for approximate nearest-neighbor search, allowing Spock to quickly find semantically similar chunks even when the user's query does not match the source text exactly.

For example, a user may ask:

> "What are the risks associated with autonomous navigation failures?"

The vector database can retrieve relevant chunks containing related concepts such as:

- "sensor degradation"
- "decision latency"
- "failover procedures"
- "navigation uncertainty"

even if those exact phrases do not appear in the user's question.

#### 4. Semantic Retrieval for "Ask AI"

During an "Ask AI" inquiry, Spock may use the vector database to retrieve context relevant to the user's question. The typical flow is:

1. The user submits a question.
2. The question is embedded using the same or a compatible embedding model.
3. The vector database searches for the most semantically similar chunks.
4. Retrieved chunks are ranked by similarity score.
5. Relevant metadata is joined from `ship_computer.db`.
6. The retrieved context is included in the prompt sent to the generative LLM.
7. The final response is validated, logged, and returned to the user.

This approach allows Spock to answer questions using grounded, source-backed context rather than relying solely on the LLM's internal knowledge.

#### 5. Semantic Retrieval for "Deep Dive"

For "Deep Dive" workflows, the embedding and vector database layers support deeper analysis over large document sets. The process typically includes:

1. Ingesting documents from external sources.
2. Parsing and normalizing content.
3. Chunking documents into semantic units.
4. Generating embeddings for each chunk.
5. Storing vectors in the vector database.
6. Recording chunk metadata in `ship_computer.db`.
7. Performing similarity searches, clustering, or cross-document comparison.
8. Aggregating findings into structured reports.

This enables Spock to identify related concepts across multiple sources, detect recurring themes, and produce citations that trace back to the original documents.

#### 6. Relationship Between SQLite and the Vector Database

The relational database and vector database work together as follows:

- **SQLite stores exact, queryable state:**  
  It records what was ingested, when it was processed, which model was used, what the task status is, and what the final results were.

- **The vector database stores semantic representations:**  
  It stores embeddings and supports similarity search over text content.

- **SQLite provides provenance:**  
  It links vector search results back to source documents, chunks, users, sessions, and workflows.

- **The vector database provides flexibility:**  
  It allows Spock to retrieve relevant information even when the user's wording differs from the source material.

This hybrid architecture gives Spock both deterministic reliability and semantic adaptability.

### Database Lifecycle & Maintenance

Database lifecycle operations are managed through `db_maintenance.py` and `reset_ship_computer.py`.

- **`db_maintenance.py`:**  
  Handles schema migrations, integrity checks, vacuuming, index optimization, and cleanup of stale records.

- **`reset_ship_computer.py`:**  
  Provides safe state clearing for troubleshooting, development, or recovery scenarios.

The relational layer ensures deterministic consistency, while the vector layer handles semantic flexibility. Together, they allow Spock to manage complex AI workflows with traceability, resumability, and semantic retrieval.
## Embedding LLM and Vector Database Integration

The Spock application implements a Retrieval-Augmented Generation (RAG) pipeline that separates semantic retrieval from generative reasoning. This architecture relies on two distinct AI components: an **Embedding LLM** for vectorization and a **Vector Database** for similarity retrieval. Together, they enable context-aware, grounded responses for both **Ask AI** and **Deep Dive** workflows.

### The Embedding LLM: Semantic Translation

The embedding model is a specialized neural network trained to map unstructured text into high-dimensional numerical vectors, commonly called embeddings. Unlike a generative LLM, it does not produce conversational text. Instead, it captures semantic meaning, context, and relationships between words, phrases, and documents.

- **Chunking Strategy:** Raw documents, wiki pages, logs, and external search results are split into manageable chunks, typically 250–500 tokens, to preserve contextual boundaries while fitting within the model’s context window.
- **Vectorization:** Each chunk is passed through the configured embedding LLM, managed via `llm_client.py` and `model_selector/embedding_panel.py`. The model outputs a fixed-length vector where geometric proximity correlates with semantic similarity.
- **Metadata Attachment:** Each vector is paired with structured metadata, such as source ID, document type, timestamp, confidence score, and retrieval context, before storage. This enables precise filtering, attribution, and traceability during retrieval.

### The Vector Database: High-Dimensional Indexing

The vector database, exposed via `rag_api_server.py` and `spock_rag_adapter`, stores embeddings in an optimized index structure, such as HNSW or IVF, designed for fast approximate nearest neighbor, or ANN, search.

- **Storage & Indexing:** Vectors are persisted alongside their metadata. The index is periodically rebuilt or updated as new documents are ingested by `LongRangeSensors` or `spock_wiki_adapter`.
- **Similarity Search:** When a query arrives, the same embedding LLM converts the user’s prompt into a vector. The vector database then performs a cosine similarity, dot product, or Euclidean distance calculation to identify the most relevant document chunks.
- **Hybrid Filtering:** Results are filtered using metadata constraints, such as “only return engineering logs from the last 30 days,” before being passed to the generative LLM. This improves relevance, reduces hallucination, and respects domain boundaries.

### SQLite 3 `ship_computer.db` Integration

The SQLite 3 database `ship_computer.db` is Spock’s local relational store for application state, user interactions, retrieval metadata, and workflow checkpoints. It does not replace the vector database; instead, it coordinates the surrounding Spock application and provides durable, queryable context for both **Ask AI** and **Deep Dive** inquiries.

- **Persistent Application State:** `ship_computer.db` stores sessions, prompts, responses, model selections, retrieval results, citations, and workflow status. This allows Spock to resume conversations, audit AI behavior, and maintain continuity across restarts.
- **Ask AI Support:** During an Ask AI inquiry, `chat_ai_helper.py` can use `ship_computer.db` to load prior conversation context, record the user’s prompt, store retrieved chunk references, and persist the final generated response. This creates a traceable chain from user question to retrieved evidence to AI answer.
- **Deep Dive Support:** During a Deep Dive inquiry, `deep_dive.py` can use `ship_computer.db` to track research phases, intermediate findings, evidence links, and completion status. This allows the workflow to checkpoint progress, recover from interruptions, and cross-reference earlier findings in later phases.
- **Relationship to the Vector Database:** The vector database is optimized for fast semantic similarity search, while `ship_computer.db` is optimized for structured queries, transactions, and application state. A typical design stores vector references, chunk IDs, scores, and metadata in SQLite, while the actual high-dimensional vectors remain in the vector database.
- **Typical Data Domains:** Common tables or data domains include sessions, messages, documents, chunks, embeddings, retrieval results, Deep Dive runs, findings, model configuration, and audit logs.
- **Operational Benefits:** Because SQLite is embedded, local, and transactional, `ship_computer.db` supports offline operation, low-latency state access, and reliable persistence without requiring a separate database server.

### How Spock Uses the Embedding LLM and Vector Database

Spock uses the embedding LLM and vector database as a semantic retrieval layer that grounds generative AI responses in relevant local and external knowledge.

1. **Ingestion:** Documents, wiki pages, logs, and sensor-derived data are chunked, embedded, and stored in the vector database with metadata.
2. **Query Embedding:** When a user submits an Ask AI or Deep Dive prompt, Spock sends the prompt to the configured embedding LLM to produce a query vector.
3. **Similarity Retrieval:** `spock_rag_adapter` queries the vector database for the most semantically similar chunks, using ANN search and metadata filters.
4. **Context Assembly:** The retrieved chunks, along with their metadata and scores, are assembled into a context window for the generative LLM.
5. **Grounded Generation:** The generative LLM produces a response using the retrieved context, reducing reliance on ungrounded parametric knowledge.
6. **Persistence:** `ship_computer.db` records the prompt, retrieved evidence, response, model used, and workflow state for auditability and continuity.
7. **Deep Dive Iteration:** In Deep Dive mode, intermediate findings are embedded and stored so later phases can retrieve and cross-reference earlier analysis.
8. **Model Management:** `model_selector` can swap embedding models or generative models, while the vector database and SQLite metadata track model versions to prevent incompatible vector mixing.

### Integration with Spock Workflows

- **Ask AI Pipeline:** User prompts are embedded, matched against the vector store, and the top-k relevant chunks are injected into the generative LLM’s context window. The LLM synthesizes a response grounded in the retrieved data, while `chat_ai_helper.py` manages turn-taking and context window optimization.
- **Deep Dive Pipeline:** For complex, multi-step analysis, the vector database acts as a dynamic knowledge base. As `deep_dive.py` iterates through research phases, intermediate findings are embedded and stored. Subsequent steps query the vector store to cross-reference new data with previously analyzed material, enabling recursive reasoning and comprehensive synthesis.
- **Model Flexibility:** The `model_selector` subsystem allows users to swap embedding models based on hardware constraints or accuracy requirements. The vector database abstracts the underlying model version, ensuring backward compatibility and supporting migration by re-embedding or maintaining versioned indexes.

This separation of concerns ensures that Spock maintains high retrieval accuracy, scales efficiently with growing document corpora, and delivers auditable, traceable AI interactions.