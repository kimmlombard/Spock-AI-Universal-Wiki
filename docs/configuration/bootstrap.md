# Bootstrap

The bootstrap process initializes the Spock environment from a clean state. To ensure the desktop menu launches quickly without waiting for all dependencies, the process is divided into two phases: Phase A (approximately 280 MB) and Phase B (bringing the total size to approximately 990 MB). These sizes are approximate and may vary depending on the platform, package versions, and existing system components.

## Phases

### Phase A — Environment setup and the UI tier

```powershell
.\bootstrap.ps1 -NonInteractive -EmitEvents -NoHandOffGui
```

Phase A prepares only the dependencies required for the Bringup menu and lightweight bringup operations:

1.  Locates or installs Python 3.14
2.  Creates the virtual environment (`.venv`) and the required folder structure
3.  Installs `requirements-ui.txt` — PyQt6, requests, psutil, huggingface_hub
4.  Validates the UI gate (`import PyQt6`)

Phase A intentionally halts at the point required for `python -m spock_bringup_menu` to open the desktop interface. This prevents file-locking conflicts during Phase B, as the Bringup menu may keep Python and PyQt files in use while running. Subsequent bringup steps (3–5: acquire, bring up servers, status) operate on this tier as well, because they only require lightweight packages such as `requests` and `huggingface_hub`.

### Phase B — Full dependency tier

```powershell
.\bootstrap_phase_b_job.ps1 -InstallRoot . -FullDeps -Validate
```

Run from Bringup step 2 (or the console menu). It re-enters `bootstrap.ps1 -FromStep pip_full` and installs only the full dependency tier. It does **not** reinstall the UI packages, because the Bringup menu is typically still holding that virtual environment open, and Windows may lock loaded files (`WinError 32`).

Phase B assumes Phase A has already completed successfully. If the virtual environment or UI-tier packages are missing, run Phase A first before attempting Phase B.

1.  Installs `requirements-full.txt` — extractors (PyMuPDF, python-docx, openpyxl, pandas, beautifulsoup4, lxml, Pillow), `watchdog`, `PyQt6-WebEngine`, keyring, reportlab, google-auth, nvidia-ml-py
2.  Pulls in `requirements-mcp.txt` (fastmcp, authlib, starlette)
3.  Retries `pip` a few times if a file is briefly locked by Defender, Explorer, or another Spock window
4.  Writes `bootstrap_full_deps.ok`, the marker file read by `spock_onboarding.readiness`, `spock_bringup`, and `spock_status`

If Phase B still fails with **Windows Error 32** on a `site-packages` path, close every other Spock or Python window that uses this `.venv`, then re-run step 2. As a last resort, exit Bringup and run the Phase B script from a plain PowerShell prompt. Do not delete or recreate the virtual environment unless absolutely necessary; if you do, rerun Phase A before Phase B.

Phase B is required before Wiki Scan and the UIEG crawler; both validate their imports first and redirect to step 2 when packages are missing. `-HeavyDeps` / `-SkipHeavyDeps` still function as aliases for `-FullDeps` / `-SkipFullDeps`. Use skip flags only in constrained environments, because features that depend on the full tier will remain unavailable until Phase B completes successfully.

Server launch is **not** part of Phase B — that is handled in Bringup step 4 (`spock_bringup up`).

## Step order

The `bootstrap.ps1` script executes a logical sequence of internal functions: `python`, `install_root`, `folders`, `venv`, `pip_wizard`, `pip_full`, `validate`. Use `-FromStep` or `-OnlyStep` to re-enter partway through the process; note that `pip_full` performs no operations unless the `-FullDeps` flag is passed.

Typical usage:

-   Phase A runs the initial steps and stops after UI validation, leaving a usable Bringup environment.
-   Phase B re-enters at `pip_full` with `-FullDeps`, installs the remaining packages, and then validates readiness.

## Script Reference

| Script | Purpose |
|--------|---------|
| `bootstrap.ps1` | Main bootstrap orchestrator for both tiers; can be run directly or re-entered from later steps |
| `bootstrap_phase_b_job.ps1` | Phase B full-tier install, intended to run outside the GUI when possible |
| `spock_menu.ps1` | Interactive menu wrapper for common Spock operations |

# Database Architecture

The Spock application uses a local SQLite 3 database file named `ship_computer.db` to persist state between sessions. This database serves as the central repository for user context, conversation history, document metadata, retrieval results, and analysis metadata required by the Ask AI and Deep Dive modules. Unlike the virtual environment managed during bootstrap, which can be rebuilt from package requirements, the database is designed to be durable and supports the read-heavy access patterns typical of LLM-assisted workflows.

## Database Location and Lifecycle

The `ship_computer.db` file resides in Spock's resolved data directory. Depending on the installation layout and OS conventions, this may be under the application root, a user-specific application-data folder, or a dedicated `data/` subdirectory. It is not part of the Python virtual environment and should not be moved into `.venv`.

-   **Initialization:** The database is created automatically upon first run if it does not exist. Spock initializes the required tables and indexes for Ask AI and Deep Dive during startup.
-   **Persistence:** Data persists across restarts of the Spock application and bootstrap phases unless explicitly deleted or reset by a user action.
-   **Locking:** SQLite uses file-level locking to coordinate access. Although package installation does not normally modify the database, open Spock processes may hold connections that can cause `SQLITE_BUSY` errors during concurrent writes or schema changes. Close idle Bringup, Ask AI, or Deep Dive windows before running maintenance operations when possible.

## ship_computer.db and Ask AI / Deep Dive Interaction

`ship_computer.db` is the durable local state store for Spock's conversational and analytical features. It is not the primary vector index, but it is the source of truth for the metadata that makes Ask AI and Deep Dive responses reproducible, auditable, and resumable.

### Role in Ask AI

Ask AI is a conversational interface that answers user questions using local context, retrieved documents, and prior conversation state. `ship_computer.db` supports this workflow by storing:

-   **Session state:** The active Ask AI conversation, including session identifiers, timestamps, and user context.
-   **Message history:** User prompts, assistant responses, system prompts, and intermediate context used to generate each answer.
-   **Retrieval context:** The document chunks, sources, and metadata that were selected for a given question.
-   **Citations and provenance:** References to the files, pages, sections, or records that contributed to an answer.
-   **Feedback and corrections:** Optional user feedback, such as accepted, rejected, or corrected responses, which can be used to improve future retrieval or prompting.

A typical Ask AI interaction follows this pattern:

1.  The user submits a question in the Ask AI interface.
2.  Spock loads the active session and recent conversation history from `ship_computer.db`.
3.  The query is embedded using the configured embedding LLM.
4.  The vector database is searched for semantically similar chunks.
5.  Candidate chunks are filtered, ranked, and combined into a prompt context.
6.  The LLM generates an answer.
7.  Spock writes the question, answer, retrieved chunks, citations, and metadata back to `ship_computer.db`.

This design allows Ask AI to maintain continuity across restarts, show users where an answer came from, and support follow-up questions without reprocessing the entire corpus.

### Role in Deep Dive

Deep Dive is a more structured analytical workflow. It is designed for questions that require multiple retrieval passes, evidence comparison, and step-by-step reasoning. `ship_computer.db` supports Deep Dive by storing:

-   **Run metadata:** The Deep Dive run identifier, start time, completion status, and user intent.
-   **Decomposed subquestions:** The individual questions or hypotheses generated during the analysis.
-   **Retrieval steps:** Each search performed, including query text, embedding vector reference, top-k results, and filters applied.
-   **Evidence records:** The chunks, documents, and metadata selected as supporting evidence.
-   **Intermediate conclusions:** Partial findings produced during the analysis.
-   **Final report data:** The synthesized answer, citations, confidence notes, and unresolved gaps.

A typical Deep Dive interaction follows this pattern:

1.  The user starts a Deep Dive with a broad analytical question.
2.  Spock creates a new run record in `ship_computer.db`.
3.  The application decomposes the question into subquestions or evidence requirements.
4.  For each subquestion, Spock embeds the query and searches the vector database.
5.  Retrieved chunks are stored as evidence records with provenance.
6.  The LLM compares evidence, identifies contradictions, and builds intermediate conclusions.
7.  The final answer is generated with citations to the stored evidence.
8.  The complete run, including intermediate steps, is persisted in `ship_computer.db` so the user can review, resume, or export the analysis.

This makes Deep Dive more transparent than a single-turn Ask AI response because the database preserves the reasoning path, not just the final answer.

## Embedding LLM and Vector Database Integration

Spock uses an embedding LLM and a vector database to convert natural-language questions and document content into a form that can be compared semantically. This is the core mechanism behind Ask AI and Deep Dive retrieval.

### Embedding LLM

The embedding LLM is a model that converts text into a fixed-size numerical vector, also called an embedding. Unlike a generative LLM, which produces text, an embedding LLM produces a representation of meaning.

For example:

-   A document chunk about “network latency during peak load” is converted into a vector.
-   A user question about “why the system slows down at busy times” is converted into another vector.
-   If the two concepts are semantically related, their vectors will be close together in vector space.

Spock uses the embedding LLM in two main ways:

1.  **Indexing:** When documents are ingested, their text is split into chunks and each chunk is embedded.
2.  **Querying:** When a user asks a question, the question is embedded and compared against the stored chunk embeddings.

The embedding model should be deterministic for a given input so that repeated queries produce consistent retrieval results. If the model changes, existing embeddings may no longer be comparable to new ones, and the vector index may need to be rebuilt.

### Vector Database

The vector database stores embeddings and the metadata needed to retrieve them. It may be implemented as a SQLite-backed vector store or as a separate vector database service, depending on the deployment. In either case, Spock abstracts the vector store behind a retrieval interface.

The vector database typically stores:

-   **Vector ID:** A unique identifier for the embedding.
-   **Embedding vector:** The numerical representation of the text chunk.
-   **Chunk text:** The original text that was embedded.
-   **Document reference:** The source file, record, or page.
-   **Metadata:** Section, author, timestamp, classification, language, or other filters.
-   **Index version:** The embedding model or index generation used to create the vector.

The vector database supports similarity search, allowing Spock to find the most relevant chunks for a query. Depending on the implementation, this may use exact nearest-neighbor search, approximate nearest-neighbor search, or a hybrid search that combines vector similarity with keyword matching.

### How Spock Uses the Embedding LLM and Vector Database Together

The full retrieval pipeline works as follows:

1.  **Document ingestion**
    -   Spock reads documents from local files, wikis, or other sources.
    -   Documents are parsed into text using the appropriate extractor.
    -   Text is split into chunks of a suitable size for retrieval.
    -   Each chunk is embedded using the embedding LLM.
    -   The chunk, metadata, and vector are stored in the vector database.
    -   A reference to the chunk and vector is stored in `ship_computer.db`.

2.  **Query preparation**
    -   The user submits a question through Ask AI or Deep Dive.
    -   Spock normalizes the query and may add context from the active session.
    -   The query is embedded using the same embedding LLM used for indexing.

3.  **Vector search**
    -   Spock searches the vector database for the closest matching chunk embeddings.
    -   Filters may be applied based on document type, date, user permissions, or metadata.
    -   The top-k results are returned.

4.  **Reranking and context assembly**
    -   Spock may rerank the retrieved chunks using metadata, recency, source reliability, or keyword overlap.
    -   The selected chunks are assembled into a prompt context for the generative LLM.

5.  **Answer generation**
    -   The generative LLM produces an answer using the retrieved context.
    -   Citations are generated from the metadata associated with the retrieved chunks.

6.  **Persistence**
    -   The query, retrieved chunks, citations, answer, and run metadata are written to `ship_computer.db`.
    -   This allows the user to inspect the evidence, resume a Deep Dive, or audit an Ask AI response.

### Relationship Between ship_computer.db and the Vector Database

`ship_computer.db` and the vector database serve different but complementary roles.

| Component | Primary Responsibility |
|-----------|------------------------|
| `ship_computer.db` | Durable application state, conversation history, run metadata, citations, provenance, and user context |
| Vector database | High-performance semantic search over embedded text chunks |
| Embedding LLM | Converts text into numerical vectors for semantic comparison |

In a standard Spock deployment, `ship_computer.db` stores the human-readable and application-level records, while the vector database stores the numerical embeddings used for retrieval. If the vector database is rebuilt, Spock can often re-embed the source chunks and restore search capability. If `ship_computer.db` is deleted, however, conversation history, Deep Dive runs, citations, and user context may be lost.

### Failure Modes and Recovery

Several failure modes can affect the embedding and retrieval pipeline:

-   **Missing embedding model:** Spock cannot embed new queries or documents. Ask AI and Deep Dive may be unavailable until the model is restored.
-   **Stale embeddings:** If the embedding model changes, old vectors may no longer match new query vectors. Reindexing is required.
-   **Vector database unavailable:** Retrieval fails, but `ship_computer.db` may still contain prior answers and metadata.
-   **Corrupted or missing chunks:** If the source text is unavailable, citations may be incomplete even if the vector index exists.
-   **Concurrent writes:** Multiple Spock processes writing to `ship_computer.db` may cause `SQLITE_BUSY` errors. Closing idle windows or using a single active process reduces this risk.

For recovery, Spock should prefer rebuilding the vector index from the stored source chunks before deleting `ship_computer.db`. The vector index is derived data; `ship_computer.db` contains the durable application state.
## ship_computer.db Schema and Core Tables

The `ship_computer.db` file is the local SQLite 3 database used by the Spock application. It is optimized for high-concurrency reads and structured writes using SQLite 3's Write-Ahead Logging (WAL) mode. The schema is partitioned into logical domains to isolate conversation state, document metadata, analysis results, and vector embeddings.

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `conversations` | Tracks individual Ask AI sessions | `id`, `title`, `created_at`, `updated_at`, `user_id` |
| `messages` | Stores prompt/response pairs and system instructions | `id`, `conversation_id`, `role`, `content`, `token_count`, `timestamp` |
| `documents` | Catalogs ingested files for Deep Dive analysis | `id`, `file_path`, `hash`, `mime_type`, `ingestion_status`, `metadata_json` |
| `analysis_results` | Caches Deep Dive extraction outputs and summaries | `id`, `document_id`, `query_hash`, `result_json`, `confidence_score` |
| `vector_store` | Holds dense embeddings for semantic retrieval | `id`, `document_id`, `chunk_id`, `embedding_vector`, `metadata` |

All tables utilize B-tree indexes on foreign keys and timestamp columns to accelerate JOIN operations and chronological queries. Transaction isolation is set to `DEFERRED` for reads and `IMMEDIATE` for batch writes, ensuring consistency without blocking concurrent UI threads.

### Schema Design Notes

The schema is designed to keep Spock's interactive and analytical workflows separate while still allowing them to share a single local database.

- **`conversations`** represents a user-facing Ask AI session. Each conversation has a stable identifier, a human-readable title, and timestamps that support history browsing, sorting, and session restoration.
- **`messages`** stores the ordered exchange of user prompts, assistant responses, system instructions, and tool-related messages. The `role` column distinguishes message types, while `token_count` supports context-window management, cost tracking, and rate-limiting.
- **`documents`** tracks files that have been ingested for Deep Dive analysis. The `hash` column enables change detection, while `ingestion_status` allows Spock to distinguish between pending, processing, completed, and failed documents.
- **`analysis_results`** stores structured outputs produced by Deep Dive pipelines. Caching these results prevents repeated extraction work and allows Spock to reuse previously computed summaries, entities, tables, or other structured findings.
- **`vector_store`** stores dense vector embeddings for document chunks. These embeddings are used for semantic retrieval in both Ask AI and Deep Dive workflows.

### SQLite 3 Operational Details

Spock relies on SQLite 3 as an embedded, file-based database engine. This gives the application local persistence, low operational overhead, and strong ACID behavior without requiring a separate database server.

- **WAL mode** allows readers to continue accessing the database while a writer is committing changes. This is important for Spock because the UI may read conversation history or document metadata while background ingestion or embedding jobs are writing new data.
- **`PRAGMA synchronous=NORMAL`** reduces fsync overhead compared with the default `FULL` setting while still providing a practical durability level for local application data.
- **Deferred reads** allow multiple read transactions to proceed without immediately acquiring exclusive locks.
- **Immediate writes** are used for batch operations so that writers can acquire the necessary lock before modifying multiple rows, reducing the chance of write conflicts.
- **B-tree indexes** on foreign keys, timestamps, and frequently filtered columns improve query performance for common operations such as loading recent messages, finding documents by status, or retrieving analysis results by document.

## Ask AI and Deep Dive Integration

The `ship_computer.db` acts as the state backbone for both interactive and analytical workflows:

- **Ask AI:** When a user initiates a query, Spock retrieves the relevant `conversation_id` and fetches the last N messages from the `messages` table to reconstruct the context window. System prompts, tool-use instructions, and user preferences are merged at query time. Responses are written back to `messages` with token usage metrics, enabling cost tracking and rate-limiting logic.
- **Deep Dive:** This module performs structured document analysis. Upon ingestion, files are registered in `documents` and processed through extraction pipelines. Results are cached in `analysis_results` to avoid redundant processing. When a user requests a Deep Dive inquiry, Spock queries `analysis_results` using semantic and metadata filters, then assembles a structured context payload that is injected into the LLM prompt. The database ensures that analysis state survives application restarts and can be versioned or rolled back if needed.

Both modules leverage SQLite's `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL` settings to balance durability with performance. Read queries are heavily cached at the application layer, while writes are batched to minimize I/O latency.

### Ask AI Interaction

Ask AI uses `ship_computer.db` as the persistent store for conversational state.

1. **Session lookup:** Spock identifies the active conversation using the `conversations` table.
2. **Context reconstruction:** Spock reads recent rows from `messages` in chronological order to build the prompt context.
3. **Prompt assembly:** System instructions, user preferences, tool definitions, and retrieved semantic context are combined into the final LLM prompt.
4. **Response persistence:** The assistant response is inserted into `messages` with metadata such as token count, model identifier, and timestamp.
5. **State updates:** The conversation's `updated_at` timestamp is refreshed so that the UI can display the most recently active sessions first.

This design allows Ask AI to resume conversations after application restarts, support multiple simultaneous sessions, and maintain a durable audit trail of prompts and responses.

### Deep Dive Interaction

Deep Dive uses `ship_computer.db` to manage document ingestion, analysis caching, and structured retrieval.

1. **Document registration:** When a file is added, Spock inserts a row into `documents` with the file path, hash, MIME type, and initial ingestion status.
2. **Ingestion tracking:** As the file is parsed, chunked, embedded, and analyzed, Spock updates the `ingestion_status` and related metadata.
3. **Analysis caching:** Structured extraction outputs are stored in `analysis_results`, keyed by document and query hash where applicable.
4. **Semantic retrieval:** When a Deep Dive question is asked, Spock may retrieve relevant chunks from `vector_store` and combine them with cached analysis results.
5. **Result assembly:** The retrieved context is formatted into a structured payload for the LLM, allowing the model to answer with grounding in the ingested document.

By persisting both raw document metadata and derived analysis results, Spock can avoid repeating expensive extraction work while still supporting incremental updates when source documents change.

### Shared Database Behavior

Ask AI and Deep Dive share the same database file, but they operate on different logical domains.

- Ask AI primarily reads and writes `conversations` and `messages`.
- Deep Dive primarily reads and writes `documents`, `analysis_results`, and `vector_store`.
- Both workflows may use `vector_store` for semantic retrieval.
- Both workflows benefit from WAL mode because UI reads and background writes can occur concurrently.
- Both workflows rely on transactional writes to ensure that partially completed operations do not corrupt user-visible state.

## Embedding LLM and Vector Database Workflow

Spock integrates a local embedding LLM and a vector database to enable semantic search and context-aware retrieval. The workflow operates as follows:

1. **Text Chunking & Preprocessing:** Ingested documents are split into overlapping text chunks (typically 512–1024 tokens) with metadata preservation (source, page, section headers).
2. **Embedding Generation:** Each chunk is passed through the embedding LLM (e.g., a lightweight transformer model optimized for dense vector representation). The model outputs a fixed-dimensional vector (e.g., 768 or 1536 dimensions) that captures semantic meaning.
3. **Vector Storage:** Embeddings are stored in the `vector_store` table within `ship_computer.db`. SQLite's vector extension (or a compatible in-process vector index) enables approximate nearest neighbor (ANN) search without requiring external services.
4. **Semantic Retrieval:** When Ask AI or Deep Dive requires contextual grounding, the user query is embedded using the same model. Spock executes a vector similarity search (cosine or dot product) against the `vector_store` index, retrieving the top-K most relevant chunks.
5. **Context Assembly & Reranking:** Retrieved chunks are filtered by metadata constraints, deduplicated, and optionally reranked using a lightweight cross-encoder or heuristic scoring. The final context window is assembled and injected into the primary LLM prompt.
6. **Caching & Incremental Updates:** Embeddings are cached to prevent redundant model inference. When documents are updated or deleted, Spock invalidates the corresponding vector entries and triggers incremental re-embedding only for affected chunks.

This architecture ensures low-latency retrieval, offline capability, and strict data locality. The embedding LLM runs in a dedicated inference thread with memory pooling, while the vector database leverages SQLite's ACID guarantees to maintain consistency between document state and semantic indexes.

### Embedding LLM Role

The embedding LLM is responsible for converting text into numerical vector representations that can be compared mathematically.

- It does not generate natural-language answers.
- It produces fixed-size dense vectors for text chunks and user queries.
- It enables Spock to measure semantic similarity between a question and document content.
- It runs locally or in a controlled inference environment, preserving data locality and reducing dependence on external services.
- It is used during ingestion to embed document chunks and during retrieval to embed user queries.

Because the same embedding model is used for both document chunks and queries, Spock can compare vectors in the same semantic space.

### Vector Database Role

The vector database provides the storage and search layer for embeddings.

- It stores each chunk's embedding vector in the `vector_store` table.
- It preserves metadata needed for filtering, such as document ID, chunk ID, source file, page, section, and ingestion timestamp.
- It supports similarity search using cosine similarity, dot product, or another configured distance metric.
- It allows Spock to retrieve the most relevant chunks for a query without scanning the entire document corpus.
- It can be implemented using a SQLite vector extension or an in-process vector index that integrates with the local database.

The vector database is not a replacement for relational storage. It complements the relational tables by enabling semantic matching, while `documents`, `analysis_results`, and `messages` continue to provide structured state and auditability.

### Retrieval and Context Assembly

When Spock needs grounded context, it follows a retrieval pipeline.

1. **Query embedding:** The user's question or Deep Dive prompt is converted into an embedding vector.
2. **Similarity search:** Spock searches `vector_store` for the closest matching chunk embeddings.
3. **Metadata filtering:** Results are filtered by document status, user scope, file type, date range, or other constraints.
4. **Deduplication:** Near-duplicate chunks are removed to avoid redundant context.
5. **Reranking:** Optional reranking improves precision by scoring the relationship between the query and each candidate chunk.
6. **Prompt injection:** The selected chunks are formatted into the LLM prompt with source attribution where appropriate.

This process allows Spock to answer questions using relevant document evidence rather than relying solely on the model's prior knowledge.

### Consistency, Caching, and Updates

Spock maintains consistency between document state and vector state.

- If a document is deleted, its associated chunks and embeddings are removed or marked inactive.
- If a document is modified, Spock compares the new file hash with the stored hash.
- Only changed chunks are re-embedded when possible.
- Embedding results are cached to avoid repeated inference for unchanged content.
- Analysis results are cached in `analysis_results` so that repeated Deep Dive queries can reuse prior work.
- SQLite transactions ensure that partial updates do not leave the database in an inconsistent state.

This combination of local persistence, semantic retrieval, and incremental updates allows Spock to provide responsive Ask AI and Deep Dive experiences while maintaining a durable, inspectable, and locally controlled data store.
## Interaction with Ask AI

The Ask AI module leverages `ship_computer.db` to support Retrieval-Augmented Generation (RAG) and session management. The database provides the persistent context needed to retrieve relevant source material, maintain conversation continuity across application restarts, and correctly attribute responses to specific user inquiries.

1.  **Conversation History:** Stores user prompts and model responses in the `conversations` table. This enables multi-turn sessions to preserve contextual memory, allowing the generative LLM to reference prior exchanges without requiring the user to repeat information.
2.  **Knowledge Base Indexing:** Stores metadata for document chunks alongside serialized embedding vectors or pointers to an external vector index. During query processing, Ask AI uses this data to efficiently locate and retrieve the most relevant document fragments.
3.  **Session State:** Tracks the active session identifier, turn ordering, and attribution metadata. This ensures that responses are correctly linked to the originating user prompt and that conversation threads remain isolated and traceable.

**Schema Overview (Ask AI):**
-   `conversations`: Stores chat history (`id`, `user_query`, `model_response`, `timestamp`) along with session identifiers and message metadata required for contextual continuity.
-   `knowledge_chunks`: Stores retrieved document fragments (`chunk_id`, `content`, `source_url`, `embedding_vector`). Depending on the deployment configuration, embeddings may be stored directly in the database or represented as foreign keys/references to an external vector store.

The fields above represent the core data structures utilized by Ask AI. Additional columns may be present for version control, relevance scoring, source provenance, or token usage accounting.

## Interaction with Deep Dive

The Deep Dive module performs intensive, multi-step analysis on user-provided inputs and requires structured storage for complex intermediate states and final outputs. The database supports full auditability, streamlined debugging, and the reuse of computationally expensive operations.

1.  **Analysis Logs:** Records each step executed during a deep dive (e.g., text extraction, parsing, cross-referencing, validation) in job and log tables such as `analysis_jobs`. This enables operators to monitor progress, inspect intermediate outputs, and diagnose failures without re-running the entire pipeline.
2.  **Entity Extraction:** Persists identified entities, attributes, and relationships extracted from source documents. Depending on the analysis type, this data is stored as structured relational rows or serialized within result metadata for flexible querying.
3.  **Result Caching:** Stores the outputs of heavy computations keyed to input hashes or identifiers. When equivalent inputs are submitted, Spock checks the cache first, allowing it to return prior results instantly instead of reprocessing identical source material.

**Schema Overview (Deep Dive):**
-   `analysis_jobs`: Tracks active, queued, and completed analysis tasks (`job_id`, `input_file`, `status`, `completion_time`) along with lifecycle metadata such as error codes and resource consumption.
-   `extraction_results`: Stores parsed data from specific files (`file_path`, `extracted_text`, `metadata_json`). Entity graphs, relationship mappings, or cache flags may be embedded within the JSON payload or normalized into adjacent tables for optimized querying.

The fields above describe the foundational Deep Dive records. Additional columns may exist for input hashing, detailed error tracing, execution timing, or result versioning.

## Connection Management

The Python application connects to the SQLite database using the standard `sqlite3` module. The helper function below establishes a new connection for each request or operation, which is appropriate for local development and single-process deployments. If the application scales to multiple worker processes or threads, prefer short-lived connections per unit of work or introduce a managed connection pooling layer. Never share a raw SQLite connection across threads without explicit synchronization.

```python
import sqlite3

# Standard connection pattern for Spock
def get_db_connection():
    conn = sqlite3.connect("ship_computer.db")
    conn.row_factory = sqlite3.Row  # Enable dictionary-like access
    return conn
```

Setting `conn.row_factory` to `sqlite3.Row` allows query results to be accessed by column name rather than positional index. This improves code readability, reduces indexing errors, and simplifies schema evolution.

**Best Practices:**
-   **Transactions:** All write operations (e.g., persisting conversation history or caching analysis results) should be wrapped in transactions to guarantee atomicity. In Python, a `with conn:` context manager automatically commits on success and rolls back if an unhandled exception occurs.
-   **Connection Lifecycle:** Close connections promptly after use. Prefer explicit `try/finally` blocks, or a custom context manager that closes the connection, to release file handles and prevent resource leaks. The built-in `with conn:` context manager manages transactions, not connection closure.
-   **Write-Ahead Logging (WAL):** Enable WAL mode (`PRAGMA journal_mode=WAL;`) to improve concurrent read performance and reduce lock contention during frequent writes.
-   **Vacuuming & Maintenance:** Periodic maintenance (e.g., `VACUUM`, `ANALYZE`) may be required if the database grows significantly or experiences heavy fragmentation. If Spock includes automated idle-time maintenance, rely on that; otherwise, schedule manual vacuuming during low-traffic windows.

## SQLite 3 `ship_computer.db` and Spock Interaction

`ship_computer.db` is a local SQLite 3 database file that serves as Spock's relational store of record. It is used for durable application state, audit trails, session continuity, and lightweight retrieval metadata. In most Spock deployments, it does not replace the vector database; instead, it coordinates the data that the vector database indexes and the results that Spock returns to the user.

### Role in the Spock Application

-   **Durable state:** Persists conversations, analysis jobs, extraction results, and cache entries so that Spock can resume work after restarts.
-   **Auditability:** Records who asked what, when, which sources were used, and which pipeline steps succeeded or failed.
-   **Retrieval coordination:** Stores chunk identifiers, source metadata, and optional embedding references that allow Spock to connect vector search results back to readable content.
-   **Caching and reuse:** Stores hashes, job outputs, and intermediate artifacts so expensive Deep Dive operations can be repeated without recomputation.
-   **Local deployment:** Because SQLite is embedded, Spock can run with minimal infrastructure while still providing transactional consistency for local or single-node deployments.

### Ask AI Inquiry Flow

When a user submits an Ask AI inquiry, Spock typically uses `ship_computer.db` in the following sequence:

1.  **Resolve the session:** Spock reads or creates a session identifier and loads prior conversation turns from `conversations`.
2.  **Prepare retrieval context:** Spock determines which knowledge base, source filters, or user permissions apply to the inquiry.
3.  **Retrieve relevant chunks:** Spock uses the vector database to find semantically similar chunks, then uses `knowledge_chunks` to load the chunk text, source URL, and provenance metadata.
4.  **Build the prompt:** Spock combines the user's current question, relevant conversation history, and retrieved source material into a prompt for the generative LLM.
5.  **Store the response:** After the LLM returns an answer, Spock writes the user prompt, model response, retrieved chunk references, relevance scores, and token usage to `conversations` or related metadata tables.
6.  **Maintain continuity:** The stored turn becomes part of the session history for future Ask AI inquiries.

This design keeps the vector database focused on similarity search while SQLite remains the source of truth for conversation history, source attribution, and operational metadata.

### Deep Dive Inquiry Flow

When a user submits a Deep Dive inquiry, Spock uses `ship_computer.db` to manage the full lifecycle of the analysis:

1.  **Create the job:** Spock inserts a row into `analysis_jobs` with the input identifier, status, timestamps, and any user or session context.
2.  **Execute pipeline steps:** As Spock extracts text, identifies entities, cross-references sources, and validates results, it writes step logs and intermediate artifacts to the database.
3.  **Use semantic search:** If the Deep Dive pipeline needs to compare new material against existing knowledge, Spock embeds the extracted text and queries the vector database for related chunks or entities.
4.  **Persist results:** Final or intermediate outputs are stored in `extraction_results` or adjacent tables, often with JSON payloads for flexible structures such as entity graphs.
5.  **Cache expensive work:** Spock stores result hashes and cached outputs so that equivalent Deep Dive inputs can be served from the database instead of re-running the pipeline.
6.  **Support debugging:** Operators can inspect job status, step logs, extracted entities, and cached results without relying on transient in-memory state.

### Typical Data Responsibilities

| Concern | Stored in `ship_computer.db` | Stored in vector DB |
|---|---|---|
| Conversation history | Yes | No |
| Session identifiers | Yes | No |
| Document chunk text | Yes, or referenced by ID | No, unless duplicated for search |
| Chunk metadata | Yes | Yes, as searchable metadata |
| Embedding vectors | Optional for small deployments | Primary store |
| Similarity search | No, or limited | Yes |
| Analysis job state | Yes | No |
| Extraction results | Yes | No |
| Result cache | Yes | No |

## Embedding LLM and Vector Database

Spock uses an embedding LLM and a vector database to support semantic retrieval for both Ask AI and Deep Dive. The embedding LLM converts text into numerical vectors, and the vector database stores those vectors and finds the most similar ones to a user's inquiry.

### Embedding LLM

An embedding LLM is a model that maps text into a fixed-length vector of floating-point numbers. For example, a document chunk such as "The reactor coolant loop uses a closed-loop heat exchange design" may be converted into a vector with hundreds or thousands of dimensions. Texts with similar meaning produce vectors that are geometrically close, while unrelated texts produce vectors that are farther apart.

Spock uses the embedding LLM in two main ways:

-   **Indexing:** When source documents are added to the knowledge base, Spock splits them into chunks, embeds each chunk, and stores the resulting vector in the vector database.
-   **Querying:** When a user asks an Ask AI question or submits a Deep Dive input, Spock embeds the query or extracted text and uses that vector to search for semantically related content.

The embedding LLM is distinct from the generative LLM that writes natural-language answers. The embedding model is responsible for understanding meaning for retrieval, while the generative model is responsible for composing the final response.

### Vector Database

The vector database is the component that stores embedding vectors and performs fast similarity search. It may be a local library such as FAISS or Chroma, or a managed service such as Qdrant, Milvus, or pgvector. The exact implementation is deployment-specific, but its role in Spock is consistent:

1.  **Store vectors:** Each vector is associated with a chunk identifier, source metadata, and optional filters such as document type, date, or user scope.
2.  **Build an index:** The vector database creates an index that enables approximate nearest-neighbor search, allowing Spock to find relevant chunks quickly even when the knowledge base is large.
3.  **Return candidates:** Given a query vector, the vector database returns the top-k most similar chunks, often ranked by cosine similarity, dot product, or another distance metric.
4.  **Support filtering:** Spock can restrict search to specific sources, sessions, document categories, or permission scopes before or during vector search.

### How Spock Uses Them Together

For Ask AI, Spock typically follows this RAG pattern:

1.  The user submits a question.
2.  Spock embeds the question using the embedding LLM.
3.  Spock queries the vector database with that embedding.
4.  The vector database returns the most relevant chunk identifiers.
5.  Spock uses those identifiers to retrieve chunk text and metadata from `ship_computer.db`.
6.  Spock constructs a prompt that includes the question, conversation history, and retrieved context.
7.  The generative LLM produces an answer grounded in the retrieved material.
8.  Spock stores the answer and retrieval metadata in `ship_computer.db`.

For Deep Dive, Spock may use the same embedding and vector search capabilities in a more analytical way:

1.  Spock extracts text, entities, or claims from the user's input.
2.  Spock embeds those extracted items.
3.  Spock searches the vector database for related documents, prior analyses, or known entities.
4.  Spock compares, clusters, or cross-references the results as part of the Deep Dive pipeline.
5.  Spock stores the semantic matches, extracted entities, and final report in `ship_computer.db`.

### Relationship Between SQLite and the Vector Database

SQLite and the vector database serve different purposes:

-   **SQLite** is the relational, transactional store for Spock's durable state: conversations, jobs, logs, extraction results, cache entries, and chunk metadata.
-   **Vector database** is the semantic search engine for embeddings: it stores vectors and returns the most similar chunks or entities.
-   **Spock** is the orchestrator: it decides what to embed, what to search, how to combine results, and what to persist.

In a small deployment, Spock may store embedding vectors directly in `ship_computer.db` as BLOBs or use a SQLite vector extension. In a larger deployment, Spock usually stores only chunk identifiers and metadata in SQLite while the vector database holds the high-dimensional vectors and search index. This separation keeps SQLite lightweight and transactional while allowing the vector database to scale with the size of the knowledge base.
## ship_computer.db Interaction Architecture

`ship_computer.db` is the SQLite 3 persistence layer for the Spock application. It stores application state, conversation history, document chunks, analysis job metadata, cached extraction results, and operational telemetry. In a Python deployment, Spock typically accesses this database through the standard `sqlite3` module or a thin data-access layer that enforces parameterized queries, transaction boundaries, and connection lifecycle management.

The database is designed to support two primary workloads:

- **Ask AI:** A conversational, retrieval-augmented generation workflow where the user asks natural-language questions and Spock returns grounded answers using relevant document context.
- **Deep Dive:** A structured analysis workflow where Spock processes one or more sources, extracts entities, relationships, summaries, or other analytical artifacts, and stores the results for later review.

The interaction follows a consistent request-response lifecycle:

1. **Request Ingestion**

   When a user submits a query or file, Spock generates a unique session or job identifier and writes an initial record to the appropriate table:

   - `conversations` for Ask AI requests.
   - `analysis_jobs` for Deep Dive requests.

   This establishes an audit trail, enables crash recovery, and anchors subsequent operations to a stable identifier.

2. **Context Retrieval and Routing**

   - For **Ask AI**, Spock retrieves relevant document fragments from `knowledge_chunks` using semantic similarity. The retrieved chunks, together with recent conversation history from `conversations`, are assembled into a prompt context window for the generative LLM.
   - For **Deep Dive**, Spock first checks `extraction_results` for a cached output. If a valid cache hit exists, the pipeline short-circuits and returns the stored result. Otherwise, Spock executes the analysis pipeline and logs each stage back to the database.

3. **LLM or Processing Execution**

   The assembled context is passed to the generative LLM or analysis engine. Intermediate states, such as streaming tokens, partial entity graphs, extraction progress, or pipeline stage status, may be written to staging or event tables to support real-time UI updates and recovery from interruptions.

4. **Response Persistence**

   Once processing completes, the final output, metadata, and performance metrics are committed to the database.

   - For Ask AI, Spock updates the `conversations` table with the model response, token usage, latency, model identifier, and any retrieval metadata.
   - For Deep Dive, Spock populates `extraction_results`, updates the job status to `completed`, and records completion timestamps, confidence scores, and processing metrics.

5. **Cleanup and Indexing**

   Background tasks periodically prune expired sessions, archive stale jobs, update relevance or access metadata, and maintain database indexes. This helps query performance remain predictable as the database grows.

This architecture ensures that every interaction is traceable, stateful, and resilient to interruptions while maintaining a clear separation between conversational data and analytical workloads.

### Detailed SQLite 3 `ship_computer.db` Model

`ship_computer.db` is a single-file SQLite 3 database. It is well suited to Spock because it provides ACID transactions, JSON support, full-text search, and low operational overhead without requiring a separate database server.

The database is organized around several core concerns:

| Concern | Purpose |
|---|---|
| Conversations | Stores Ask AI user prompts, assistant responses, session context, and model metadata. |
| Documents and chunks | Stores ingested source material and the text fragments used for retrieval. |
| Embeddings | Stores vector representations of chunks and, where applicable, query vectors. |
| Analysis jobs | Tracks Deep Dive request lifecycle, configuration, status, and progress. |
| Extraction results | Stores cached Deep Dive outputs, including entities, relationships, summaries, and confidence data. |
| Operational metadata | Stores model versions, pipeline stages, errors, timing, and maintenance state. |

A typical logical schema includes the following tables or table groups:

#### `conversations`

Stores Ask AI interaction records. Depending on implementation, this table may represent one row per conversation or one row per message.

Representative fields:

- `id`: Primary key.
- `session_id`: Groups related messages into a single conversation.
- `user_id`: Identifies the user or tenant.
- `role`: `user`, `assistant`, `system`, or `tool`.
- `content`: Prompt or response text.
- `model`: Generative model identifier.
- `retrieval_metadata`: JSON payload describing retrieved chunks, scores, and filters.
- `token_count`: Input and output token usage.
- `latency_ms`: Processing time.
- `created_at`: Timestamp.
- `updated_at`: Timestamp.

This table supports conversation continuity, prompt assembly, audit logging, and response replay.

#### `documents`

Stores source documents that have been ingested into Spock.

Representative fields:

- `id`: Primary key.
- `title`: Human-readable document name.
- `source_type`: File, URL, API, or manual entry.
- `source_uri`: Original location or identifier.
- `content_hash`: Hash used for deduplication and cache validation.
- `status`: `pending`, `processed`, `failed`, or `archived`.
- `created_at`: Timestamp.
- `updated_at`: Timestamp.

This table provides the source of truth for document identity and lifecycle.

#### `knowledge_chunks`

Stores the text fragments used for retrieval and context assembly.

Representative fields:

- `id`: Primary key.
- `document_id`: Foreign key to `documents`.
- `chunk_index`: Position of the chunk within the source document.
- `content`: Chunk text.
- `token_count`: Approximate token length.
- `metadata_json`: Source, permissions, language, section, or other filters.
- `embedding_model`: Identifier of the embedding model used.
- `embedding_version`: Version or hash of the embedding model.
- `embedding_blob`: Binary vector representation, when stored locally.
- `created_at`: Timestamp.

This table is central to Ask AI retrieval and Deep Dive evidence gathering.

#### `analysis_jobs`

Stores Deep Dive job state.

Representative fields:

- `id`: Primary key.
- `job_id`: Public or external job identifier.
- `user_id`: Requesting user or tenant.
- `source_id`: Related document or source identifier.
- `status`: `queued`, `running`, `completed`, `failed`, or `cancelled`.
- `request_json`: Original user request and configuration.
- `config_json`: Pipeline settings, extraction targets, and model parameters.
- `progress`: Percentage or stage indicator.
- `error_message`: Failure details, if present.
- `started_at`: Timestamp.
- `completed_at`: Timestamp.

This table allows Spock to track long-running analytical work and resume or inspect it later.

#### `extraction_results`

Stores completed Deep Dive outputs.

Representative fields:

- `id`: Primary key.
- `job_id`: Foreign key to `analysis_jobs`.
- `result_json`: Final structured output.
- `entities_json`: Extracted entities.
- `relations_json`: Extracted relationships or graph edges.
- `summary`: Natural-language summary.
- `confidence`: Overall confidence or quality score.
- `model`: Analysis model identifier.
- `created_at`: Timestamp.

This table enables cache hits, result comparison, and historical review.

#### `pipeline_events`

Stores intermediate processing events for Deep Dive and, where useful, Ask AI.

Representative fields:

- `id`: Primary key.
- `job_id`: Related job or conversation identifier.
- `stage`: Pipeline stage name.
- `status`: `started`, `completed`, `failed`, or `skipped`.
- `payload_json`: Stage-specific data.
- `created_at`: Timestamp.

This table supports debugging, progress reporting, and crash recovery.

#### `sessions`

Stores active user or application sessions.

Representative fields:

- `id`: Primary key.
- `user_id`: User or tenant identifier.
- `created_at`: Timestamp.
- `expires_at`: Expiration timestamp.
- `metadata_json`: Client, device, or feature flags.

This table supports session pruning and access control.

### Ask AI Data Flow in `ship_computer.db`

Ask AI is a retrieval-augmented conversational workflow. The database participates at every stage.

1. **Session and message creation**

   Spock creates or reuses a session identifier and writes the user prompt to `conversations`.

2. **History retrieval**

   Spock loads recent messages for the session to provide conversational context. The number of messages included is controlled by token budget, latency requirements, and product policy.

3. **Query embedding**

   The user prompt, optionally combined with recent context, is converted into an embedding vector using the configured embedding model.

4. **Vector or full-text retrieval**

   Spock searches the vector store or local SQLite vector index for the most similar `knowledge_chunks`. If semantic search is unavailable, it may fall back to SQLite FTS5 or keyword search.

5. **Metadata filtering**

   Retrieved chunks are filtered by permissions, source type, recency, language, or other metadata before being included in the prompt.

6. **Prompt assembly**

   Spock combines the filtered chunks, conversation history, system instructions, and user question into a structured prompt.

7. **Generative LLM call**

   The prompt is sent to the generative LLM. Streaming tokens may be displayed in the UI while the final response is being generated.

8. **Response persistence**

   The assistant response, retrieval metadata, model identifier, token usage, and latency are written back to `conversations`.

9. **Post-processing**

   Spock may update access counts, relevance scores, or session metadata. It may also log retrieval quality signals for later evaluation.

### Deep Dive Data Flow in `ship_computer.db`

Deep Dive is a structured analytical workflow. The database is used to track job state, cache results, and preserve intermediate artifacts.

1. **Job creation**

   Spock creates an `analysis_jobs` record with status `queued` or `running`. The request payload, source identifiers, and configuration are stored in JSON fields.

2. **Cache check**

   Spock checks `extraction_results` for a valid cached result. A cache is considered valid when the source content hash, extraction configuration, model version, and schema version match the current request.

3. **Source preparation**

   If no cache hit exists, Spock loads the relevant document or chunks from `documents` and `knowledge_chunks`.

4. **Retrieval and evidence selection**

   For complex Deep Dive requests, Spock may use semantic search to identify the most relevant chunks before passing them to the analysis model.

5. **Analysis execution**

   The analysis engine extracts entities, relationships, summaries, or other requested artifacts. Stage transitions are recorded in `pipeline_events`.

6. **Result validation**

   Spock validates the output against the expected schema, applies confidence scoring, and normalizes the result.

7. **Result persistence**

   The final result is written to `extraction_results`, and the corresponding `analysis_jobs` record is updated to `completed`.

8. **Failure handling**

   If processing fails, Spock records the error in `analysis_jobs` and `pipeline_events`. The job may be retried, depending on configuration.

### Transactions, Concurrency, and Recovery

Because Spock is a Python application using SQLite 3, transaction management is important for consistency.

- **Parameterized queries** prevent SQL injection.
- **Short transactions** reduce lock contention.
- **WAL mode** can improve concurrent read performance while writes are in progress.
- **Foreign keys** help maintain referential integrity between documents, chunks, jobs, and results.
- **Idempotent job processing** allows Spock to safely retry failed stages without duplicating results.
- **Event logging** enables reconstruction of pipeline state after an interruption.

For long-running Deep Dive jobs, Spock should avoid holding database locks during LLM calls. Instead, it should persist job state before external processing, update progress in small transactions, and commit final results only after validation.

## Embedding LLM and Vector Database Integration

Spock uses an embedding model and a vector database to power semantic search and context retrieval. The embedding model converts text into numerical vectors, while the vector database stores those vectors and supports efficient similarity search.

Together, they allow Spock to retrieve contextually relevant information rather than relying only on exact keyword matching.

### Embedding Model Role

The embedding model is a non-generative language model that maps text into a fixed-dimensional vector space. In Spock, it is used for two purposes:

1. **Document embedding**

   During ingestion, document chunks are converted into vectors and stored with their metadata.

2. **Query embedding**

   During Ask AI or Deep Dive requests, the user prompt is converted into a vector using the same embedding model.

Using the same model for both documents and queries is essential because similarity is only meaningful when both sides of the comparison exist in the same vector space.

The embedding model captures semantic meaning, syntax, and contextual relationships. As a result, queries such as “What risks are mentioned in the contract?” can retrieve chunks containing “liability,” “indemnification,” or “breach,” even if the exact words do not match.

### Vector Database Role

The vector database stores embeddings and supports nearest-neighbor search. It may be:

- An external vector database such as Chroma, Qdrant, Milvus, or Weaviate.
- A local vector index such as FAISS.
- A SQLite-based vector extension such as `sqlite-vec`, when the deployment is small or self-contained.

The vector database is responsible for:

- Storing high-dimensional vectors.
- Maintaining an approximate nearest-neighbor index.
- Returning the top-K most similar chunks for a query vector.
- Supporting metadata filters, such as permissions, source type, or recency.
- Enabling fast search without scanning every stored vector.

### Ingestion Pipeline

When a document is added to Spock, the following steps occur:

1. **Document normalization**

   Spock extracts text from the source format, removes unnecessary markup, and normalizes encoding.

2. **Chunking**

   The document is split into overlapping or non-overlapping chunks. Chunk size is chosen to balance retrieval precision with context completeness.

3. **Metadata extraction**

   Spock records source, title, section, permissions, language, and other attributes.

4. **Embedding generation**

   Each chunk is passed through the embedding model to produce a vector.

5. **Persistence**

   The chunk text, metadata, embedding model identifier, and vector are stored in `ship_computer.db` or an external vector database.

6. **Index update**

   The vector index is updated so the new chunk can be retrieved immediately.

### Query-Time Retrieval Pipeline

During an Ask AI or Deep Dive request, Spock performs the following steps:

1. **Query preparation**

   Spock may rewrite, expand, or decompose the user prompt to improve retrieval quality.

2. **Query embedding**

   The prepared query is converted into a vector using the same embedding model used for document chunks.

3. **Vector search**

   Spock queries the vector database for the top-K most similar chunks. Similarity is typically measured using cosine similarity or inner product distance.

4. **Metadata filtering**

   Results are filtered by access permissions, source type, recency, language, or other business rules.

5. **Reranking**

   Optional reranking may reorder candidates using a cross-encoder, keyword score, or business-specific relevance heuristic.

6. **Context assembly**

   The final chunks are formatted into the LLM prompt with citations or source identifiers.

7. **Response generation**

   The generative LLM produces an answer grounded in the retrieved context.

### Local SQLite Vector Storage

For small or self-contained deployments, Spock can store embeddings directly in `ship_computer.db`.

In this mode:

- Embeddings are stored as `BLOB` values in `knowledge_chunks` or a dedicated vector table.
- The embedding model name and version are stored alongside each vector.
- Similarity search may use brute-force comparison for small datasets or a SQLite vector extension for larger datasets.
- FTS5 can provide keyword-based fallback search.

This approach keeps the deployment simple and portable, but it is best suited to moderate data volumes.

### External Vector Database

For larger deployments, Spock can use an external vector database.

In this mode:

- `ship_computer.db` remains the system of record for conversations, jobs, documents, and metadata.
- The external vector database stores embeddings and provides high-performance ANN search.
- Spock synchronizes chunk metadata between SQLite and the vector store.
- Deletions, updates, and re-indexing are coordinated to prevent stale vectors.

This separation allows Spock to scale retrieval independently from transactional application state.

### Fallback, Versioning, and Re-indexing

Spock should treat embedding search as a preferred path, not the only path.

- If the embedding service is unavailable, Spock can fall back to SQLite FTS5 or keyword search.
- If the vector database is unavailable, Spock can return cached results, limited context, or a degraded response with a clear notice.
- Embedding vectors are versioned with the model identifier and model version.
- If the embedding model changes, Spock triggers a background re-indexing job so that new queries are compared against vectors generated by the current model.
- Old vectors may be retained temporarily for rollback or comparison, then pruned after validation.

This integration ensures that Spock retrieves contextually relevant information, improves response accuracy, reduces hallucination, and supports efficient handling of complex, multi-document inquiries.