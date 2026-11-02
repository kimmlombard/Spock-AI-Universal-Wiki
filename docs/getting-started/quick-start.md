# Quick Start

Use this quick start guide to initialize the Spock Onboarding environment and verify that the user interface (UI) and backend servers are operational. The final sections detail the SQLite 3 database architecture and the integration of the embedding LLM with the vector database.

## 1. Bootstrap

Execute `bootstrap.ps1` to initiate Phase A bootstrap.

Phase A is the foundational setup stage that configures the runtime environment, installs dependencies, and prepares system resources prior to application launch and verification.

## 2. Launch

Start the onboarding workflow by executing `Spock-Menu.bat`. This script launches the `spock_bringup_menu` interface, which provides a centralized dashboard for managing and monitoring Spock bring-up tasks.

## 3. Verify

Run `spock_probe` and `spock_status` to validate system readiness. Verify that `spock_ready_last.json` contains `"ui_ready": true` and `"servers_ready": true`. These boolean flags confirm that the frontend interface and all required backend services have successfully initialized and are accepting requests.

## 4. Database Architecture

Spock relies on SQLite 3 for persistent local storage via the `ship_computer.db` file. This database serves as the central repository for application state, user context, and analytical outputs. It is optimized for low-latency reads and writes, making it ideal for local AI-driven workflows.

### 4.1. `ship_computer.db` Schema and Interaction Model

The database is structured to support two primary operational modes: **Ask AI** and **Deep Dive**. Each mode interacts with specific tables and indexes to maintain data integrity and query performance.

* **Ask AI Context Retrieval:** When a user submits a query, the application first checks `ship_computer.db` for relevant historical context, session metadata, and cached knowledge. The database stores structured JSON blobs and relational mappings that allow the AI engine to ground its responses in verified application state rather than relying solely on generative inference.
* **Deep Dive Result Persistence:** During analytical workflows, intermediate processing steps, raw data extracts, and final synthesized reports are serialized and written to dedicated tables. This ensures that complex multi-step inquiries can be paused, resumed, or audited later without recomputation.

### 4.2. Data Flow and Transaction Management

All interactions with `ship_computer.db` are handled through Python's `sqlite3` module with ACID-compliant transaction management. Read operations for Ask AI are optimized using indexed lookups, while Deep Dive writes utilize batched inserts to minimize I/O overhead. Connection pooling and WAL (Write-Ahead Logging) mode are enabled to support concurrent read/write operations without locking the UI.

### 4.3. Representative Schema and Query Patterns

The `ship_computer.db` schema is organized around the logical entities required for session tracking, AI query handling, analytical workflow persistence, and vector metadata management. A typical implementation includes the following table categories:

| Table Category | Purpose |
|---|---|
| `sessions` | Tracks active and historical user sessions, UI state, server readiness state, and session lifecycle metadata. |
| `ask_ai_queries` | Stores each Ask AI request, including the user prompt, response status, model output, latency, and context snapshot references. |
| `ask_ai_context` | Stores the context chunks retrieved for an Ask AI request, including source identifiers, relevance scores, and serialized payload data. |
| `deep_dive_runs` | Stores the top-level Deep Dive workflow, including objective, status, configuration, start/end timestamps, and final result summary. |
| `deep_dive_steps` | Stores individual processing steps within a Deep Dive run, including step order, input/output payloads, status, and error details. |
| `deep_dive_artifacts` | Stores generated artifacts such as reports, data extracts, summaries, or intermediate files produced during a Deep Dive workflow. |
| `vector_metadata` | Stores metadata linking vector database entries back to source documents, session IDs, Ask AI queries, or Deep Dive artifacts. |
| `audit_log` | Stores operational events, state transitions, and diagnostic information for troubleshooting and auditability. |

Indexes are typically maintained on high-frequency lookup fields such as `session_id`, `query_id`, `run_id`, `step_id`, `status`, and `created_at` to support fast retrieval of recent context and workflow state.

### 4.4. Ask AI Interaction Details

The Ask AI workflow uses `ship_computer.db` as the source of truth for structured application context. The interaction generally follows this pattern:

1. **Session Resolution:** Spock identifies the active session and retrieves session metadata from the `sessions` table.
2. **Query Registration:** A new Ask AI request is inserted into `ask_ai_queries` with a pending or processing status.
3. **Context Lookup:** Spock queries structured tables for relevant session data, cached responses, prior Ask AI context, and Deep Dive artifacts that may be relevant to the user's prompt.
4. **Vector Context Retrieval:** Spock also queries the vector database for semantically similar content. The resulting vector matches are mapped back to structured records using metadata stored in `vector_metadata`.
5. **Context Snapshot:** The retrieved context chunks are stored in `ask_ai_context` so the exact context used for the response can be inspected later.
6. **Response Persistence:** After the model generates a response, Spock updates the `ask_ai_queries` row with the final response, status, latency, token usage, and any error information.

This approach allows Ask AI to combine semantic relevance from the vector database with deterministic, structured state from SQLite.

### 4.5. Deep Dive Interaction Details

The Deep Dive workflow uses `ship_computer.db` to persist multi-step analytical work. The interaction generally follows this pattern:

1. **Run Creation:** Spock creates a new record in `deep_dive_runs` representing the overall analytical objective.
2. **Step Planning:** The workflow planner creates or updates rows in `deep_dive_steps` for each planned processing step.
3. **Step Execution:** As each step executes, Spock writes input payloads, output payloads, status changes, and error details back to `deep_dive_steps`.
4. **Artifact Storage:** Generated reports, summaries, data extracts, or intermediate files are recorded in `deep_dive_artifacts`.
5. **Result Finalization:** When the workflow completes, Spock updates the `deep_dive_runs` row with the final status, result summary, and completion timestamp.
6. **Resumability:** If a Deep Dive workflow is interrupted, Spock can inspect the run and step records to determine which steps completed successfully and which steps require re-execution.

This persistence model supports auditability, debugging, and recovery without requiring the user to restart the entire analytical process.

### 4.6. Concurrency, Integrity, and Recovery

Because Spock is a local application, `ship_computer.db` is designed to provide reliable single-node persistence with minimal operational overhead.

* **WAL Mode:** Write-Ahead Logging allows readers to continue accessing the database while a writer commits changes, reducing UI stalls during Deep Dive writes.
* **ACID Transactions:** Each logical operation is wrapped in a transaction so that partial writes do not corrupt application state.
* **Batched Writes:** Deep Dive workflows batch related inserts and updates to reduce disk I/O and improve throughput.
* **Indexed Reads:** Ask AI context retrieval relies on indexed lookups to keep response latency low.
* **Foreign Key Relationships:** Where appropriate, foreign key constraints preserve referential integrity between sessions, queries, runs, steps, and artifacts.
* **Recovery Behavior:** If a process exits unexpectedly, SQLite's journaling and WAL mechanisms help ensure that committed transactions remain durable and uncommitted changes are rolled back.

## 5. Embedding LLM and Vector Database Integration

Spock leverages a dual-layer architecture combining an embedding Large Language Model (LLM) with a local vector database to enable semantic search and context-aware reasoning.

### 5.1. Embedding Generation

When a user initiates an Ask AI or Deep Dive request, the input text is first processed by the embedding LLM. This model transforms unstructured text into high-dimensional numerical vectors (embeddings) that capture semantic meaning, intent, and contextual relationships. Unlike keyword-based search, embeddings allow Spock to match queries with conceptually similar data, even when exact terminology differs.

### 5.2. Vector Database Storage and Retrieval

The generated embeddings are stored in a lightweight, local vector database. Each vector is paired with metadata tags that link it back to source documents, session IDs, or Deep Dive artifacts. When a query is submitted, Spock:

1. Generates an embedding for the user's prompt.
2. Performs a nearest-neighbor search (e.g., cosine similarity or Euclidean distance) against the vector index.
3. Retrieves the top-k most relevant context chunks.
4. Injects these chunks into the LLM's context window to generate a grounded, accurate response.

### 5.3. Synergy with `ship_computer.db`

The vector database and `ship_computer.db` operate in tandem. While the vector store handles semantic matching and high-dimensional similarity searches, `ship_computer.db` manages structured state, transaction logs, and relational metadata. Cross-referencing between the two systems ensures that AI responses are both semantically relevant and structurally consistent with the application's persistent data model.

### 5.4. Embedding Pipeline Details

The embedding pipeline is responsible for converting raw text into searchable vector representations. The pipeline typically includes the following stages:

1. **Text Normalization:** Whitespace, line endings, and formatting artifacts are normalized to produce consistent input.
2. **Chunking:** Long documents, reports, or session transcripts are split into smaller context chunks that are suitable for embedding.
3. **Metadata Attachment:** Each chunk is associated with metadata such as source type, source ID, session ID, query ID, Deep Dive run ID, and creation timestamp.
4. **Embedding Inference:** The embedding model generates a vector for each chunk.
5. **Vector Indexing:** The vector and metadata are written to the local vector database.
6. **Cache Update:** If the same text or chunk is embedded again, Spock can reuse the cached vector to avoid redundant computation.

Embedding models are versioned so that Spock can distinguish between vectors generated by different model versions. This prevents incompatible vectors from being compared during similarity search.

### 5.5. Vector Database Responsibilities

The local vector database is responsible for semantic retrieval rather than transactional application state. Its primary responsibilities include:

* Storing high-dimensional embeddings for documents, prompts, responses, and Deep Dive artifacts.
* Maintaining a similarity index for fast nearest-neighbor search.
* Supporting metadata filters so Spock can restrict search to a specific session, run, document type, or time range.
* Returning ranked context chunks based on similarity score.
* Providing deterministic retrieval behavior for the same query embedding and index state.

The vector database complements SQLite by handling approximate semantic matching, while SQLite handles exact relational queries, workflow state, and durable application records.

### 5.6. End-to-End Ask AI Flow

The Ask AI flow combines structured database access with semantic vector retrieval.

1. The user submits a natural-language question through the Spock UI.
2. Spock resolves the active session from `ship_computer.db`.
3. Spock inserts a new Ask AI query record with a pending status.
4. Spock generates an embedding for the user's prompt using the embedding LLM.
5. Spock queries the vector database for the most semantically similar context chunks.
6. Spock uses metadata from the vector results to retrieve related structured records from `ship_computer.db`.
7. Spock stores the selected context chunks in `ask_ai_context`.
8. Spock assembles a prompt for the generative LLM using the retrieved context and the user's question.
9. The generative LLM produces a response.
10. Spock updates the Ask AI query record with the response, status, latency, and any diagnostic information.

This flow allows Ask AI to answer questions using both semantic context and verified application state.

### 5.7. End-to-End Deep Dive Flow

The Deep Dive flow uses embeddings to discover relevant material and SQLite to persist the analytical workflow.

1. The user defines a Deep Dive objective.
2. Spock creates a `deep_dive_runs` record in `ship_computer.db`.
3. Spock generates an embedding for the objective and related planning prompts.
4. Spock searches the vector database for relevant documents, prior runs, artifacts, or context chunks.
5. Spock retrieves structured metadata from `ship_computer.db` for the matched vector entries.
6. Spock plans a sequence of analytical steps and stores them in `deep_dive_steps`.
7. As each step executes, Spock writes intermediate outputs, status changes, and errors back to SQLite.
8. Generated artifacts are recorded in `deep_dive_artifacts`.
9. New artifacts, summaries, or reports may be embedded and added to the vector database for future retrieval.
10. When the workflow completes, Spock updates the run record with the final result and status.

This design allows Deep Dive workflows to be both analytically rich and fully auditable.

### 5.8. Caching, Refresh, and Failure Handling

Spock uses caching and fallback strategies to maintain responsiveness and reliability.

* **Embedding Cache:** Frequently used prompts, documents, and context chunks are cached to avoid repeated embedding inference.
* **Vector Index Refresh:** When new documents or Deep Dive artifacts are added, Spock embeds and indexes them so future queries can retrieve the new content.
* **Structured Fallback:** If vector search is unavailable or returns insufficient results, Spock can fall back to structured SQLite queries based on session, run, status, or timestamp filters.
* **Error Isolation:** Failures in one Deep Dive step are recorded in `deep_dive_steps` without corrupting the overall run state.
* **Auditability:** Both Ask AI and Deep Dive operations leave persistent records in `ship_computer.db`, enabling later inspection of what context was used and what results were produced.