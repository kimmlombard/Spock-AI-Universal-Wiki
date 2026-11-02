# Database Schema


## Ship's Computer

The primary SQLite database schema is defined in `ship_computer_schema.sql`, located in the project root directory. This file contains the complete Data Definition Language (DDL) required to initialize the database structure. It serves as the single source of truth for all table definitions, constraints, and relationships within the system. Upon initialization, this schema generates the `ship_computer.db` file, which acts as the persistent storage layer for the Spock application.

### Core Tables

| Table | Purpose |
|-------|---------|
| `profiles` | Stores workstation profile configurations. Each row defines a specific set of settings for a user or system workstation. Profiles can be activated or deactivated dynamically based on operational requirements, typically managed via an `active` status flag. |
| `uieg_captures` | Contains Universal Extractor capture records. This table logs data extracted by the Universal Extractor module for downstream analysis or processing. Each record includes timestamps, source identifiers, and the raw captured payload. |
| `kb_entries` | Holds knowledge-base document entries. This table stores informational content such as documentation, system logs, or learning artifacts. Entries are used for reference, troubleshooting, and system knowledge acquisition. |
| `health_snapshots` | Records historical system health-check data. Each entry captures a snapshot of system metrics at a specific point in time, including CPU usage, memory utilization, and overall system status for monitoring and diagnostics. |

The tables are designed to work together across operational context and diagnostic analysis:

- `profiles` provides the active workstation or user context that scopes other data.
- `kb_entries` stores reference material used by AI-assisted responses and troubleshooting workflows.
- `health_snapshots` records point-in-time performance metrics for trend analysis.
- `uieg_captures` preserves raw extracted payloads for forensic inspection when anomalies occur.

Where the DDL defines foreign keys, these tables are linked through identifiers such as profile IDs, source IDs, timestamps, or entry references. Even when explicit constraints are not present, application queries should treat them as logically related datasets for filtering and correlation.

### Schema File

```sql
-- ship_computer_schema.sql
-- See project root for full DDL
```

This SQL file is executed during the database initialization process to create all necessary tables, indexes, views, triggers, or constraints defined in the DDL. Apply this file before running any application logic that depends on the schema. If using a migration tool, ensure the same definitions are represented in migration scripts or seed files so new and existing databases remain consistent.

Initialization guidance:

- Run the DDL against an empty database unless the statements are explicitly idempotent.
- If the schema uses foreign keys, enable SQLite foreign-key enforcement with `PRAGMA foreign_keys = ON;` before executing dependent queries.
- Verify that expected tables exist by querying `sqlite_master` or using a database inspection tool after initialization.

### Spock Application Integration

The `ship_computer.db` database serves as the persistent backend for the Spock application, specifically powering the **Ask AI** and **Deep Dive** inquiry modules. The interaction between the database and these features is structured as follows:

#### Ask AI Module
The **Ask AI** feature utilizes the `kb_entries` table to provide context-aware responses. When a user submits an inquiry, the system performs semantic search or keyword-based retrieval against the `kb_entries` table. Semantic ranking is handled in application code, while SQLite stores the text and metadata used for filtering.

*   **Data Flow**: The application queries `kb_entries` to retrieve relevant documentation snippets or logs that match the user's intent. Queries are scoped by the active `profiles` record to ensure context alignment.
*   **Context Injection**: Retrieved data is formatted into a structured context window and passed to the AI engine. This grounding mechanism ensures responses are accurate, traceable, and constrained to the ship's verified knowledge base.
*   **Metadata Filtering**: Queries include profile-based filters, timestamp ranges, and document type tags to ensure the AI response adheres to the current operational context, security clearance, and relevance thresholds of the requesting user.
*   **Caching & State**: Frequently accessed knowledge entries are cached in memory to reduce SQLite I/O latency. The application tracks query history and user feedback to refine future retrieval scoring.

#### Deep Dive Module
The **Deep Dive** feature leverages historical data stored in `health_snapshots` and `uieg_captures` for trend analysis and root-cause investigation.

*   **Trend Analysis**: The application aggregates metrics from `health_snapshots` using time-windowed SQL queries. Aggregation functions (`AVG`, `MAX`, `COUNT`) are applied to visualize system performance over time, identifying patterns such as CPU spikes, memory leaks, or network latency degradation.
*   **Forensic Logging**: When an anomaly is detected or manually triggered, the system retrieves corresponding records from `uieg_captures`. Raw payloads are decoded and presented alongside metadata for deeper inspection.
*   **Correlation**: SQL joins are executed to correlate health metrics with specific knowledge-base entries in `kb_entries` that may explain the observed behavior. This cross-referencing enables automated hypothesis generation for troubleshooting workflows.
*   **Query Optimization**: To maintain responsiveness, the application uses indexed lookups on `timestamp`, `profile_id`, and `status` columns. Large result sets are paginated, and heavy aggregations are offloaded to background workers when real-time latency is not required.
Query considerations for these modules include:

- Index frequently filtered columns, such as timestamps, profile or context identifiers, status flags, and source IDs.
- Use bounded queries with time windows, limits, or pagination to avoid scanning large tables unnecessarily.
- Enforce access controls at the query level by including the appropriate `profiles` or security filters in every request.
- For large payloads stored in `uieg_captures`, retrieve only required fields and consider streaming or paginated reads.

### SQLite 3 `ship_computer.db` and Spock Interaction

`ship_computer.db` is the SQLite 3 database that serves as the relational system of record for the Spock application. It stores structured operational data, user and profile context, knowledge-base metadata, captured payloads, and audit information. The Spock application uses SQLite for deterministic, transactional access to data that must be filtered, joined, and governed by explicit access-control rules.

In production, the database is commonly run in WAL mode with a busy timeout to allow concurrent readers while writes are serialized. This supports the read-heavy patterns typical of **Ask AI** and **Deep Dive** workflows, where multiple requests may query the same knowledge-base records, captures, or profile metadata at the same time.

For **Ask AI** and **Deep Dive** inquiries, Spock treats `ship_computer.db` as the authoritative source for:

- **Identity and context**: active profile, session context, role, clearance level, and allowed data scopes.
- **Knowledge-base metadata**: `kb_entries` records, document type, source, timestamp, status, and security attributes.
- **Retrieval constraints**: time windows, profile filters, status flags, and source restrictions applied before or after semantic search.
- **Large captured data**: `uieg_captures` payloads that may be streamed or paginated when a response requires raw evidence.
- **Auditability**: request logs, response citations, feedback, and access decisions.

The typical interaction flow is:

1. Spock receives an **Ask AI** or **Deep Dive** request.
2. It validates the request against the active profile and security policy.
3. It constructs a bounded SQLite query that includes the required `profiles`, clearance, timestamp, and status filters.
4. It retrieves candidate relational records from `kb_entries`, `uieg_captures`, or related tables.
5. It uses the embedding and vector layer to rank or expand the candidate set semantically.
6. It returns only the fields needed for the response, preserving citations and access-control metadata.

This design keeps SQLite responsible for exact filtering, authorization, and transactional consistency, while the vector layer provides semantic ranking over unstructured text.

#### Ask AI and Deep Dive Inquiries

**Ask AI** is a focused, single-turn semantic question. Spock typically retrieves a small number of highly relevant chunks, applies strict profile and clearance filters, and generates a concise, citation-backed answer.

**Deep Dive** is a broader, iterative investigation. Spock may perform multiple retrieval passes, retrieve more context, inspect related `uieg_captures` payloads, compare sources, and assemble a longer analytical response. Deep Dive requests should use pagination, streaming, and explicit limits to avoid loading excessive data into memory.

### Embedding LLM and Vector Database Integration

The Spock application bridges traditional relational storage with modern AI retrieval through an integrated embedding pipeline and vector database layer. This architecture enables semantic understanding of unstructured text stored in `ship_computer.db`.

#### Overview

Spock uses two distinct AI components:

- **Embedding LLM**: Converts text into numerical vectors that represent semantic meaning.
- **Vector database**: Stores those vectors and performs fast similarity search.
- **Generative LLM**: Uses the retrieved context to produce the final natural-language answer.

The embedding LLM is not the same as the answer-generating LLM. Its role is to create comparable vector representations for both stored knowledge and user questions. The vector database then finds the most semantically relevant chunks, and the generative LLM uses those chunks as grounded context.

#### Embedding Generation Process

When new documents, logs, or knowledge articles are ingested into the `kb_entries` table, the application triggers an asynchronous embedding workflow:

1. **Text Extraction & Chunking**: Raw text is parsed, cleaned, and split into semantically coherent chunks (typically 250–500 tokens) to preserve context while fitting within model constraints.
2. **Vectorization**: Each chunk is passed to the configured embedding LLM (e.g., a fine-tuned transformer model optimized for technical documentation). The model converts the text into a high-dimensional numerical vector (embedding) that captures semantic meaning, syntax, and domain-specific terminology.
3. **Metadata Attachment**: Each vector is paired with metadata extracted from the original `kb_entries` record, including `entry_id`, `profile_id`, `timestamp`, `document_type`, and `security_clearance`.

The embedding model is used for both indexing and query time. Using the same model for documents and user questions ensures that the resulting vectors are comparable in the same semantic space.

#### Vector Storage & Indexing

The generated vectors are stored in a dedicated vector database layer that operates alongside `ship_computer.db`. Depending on deployment configuration, this may be:

- A SQLite extension (e.g., `sqlite-vec` or `vecs`) that stores vectors directly within the relational database using specialized indexes.
- A companion vector store (e.g., FAISS, Chroma, or Qdrant) synchronized via application-level event listeners.

The vector index is optimized for approximate nearest neighbor (ANN) search, enabling sub-millisecond similarity lookups across thousands of knowledge entries. Index parameters (e.g., HNSW `M` and `ef_construction`) are tuned to balance recall accuracy against query latency.

The vector store should retain stable identifiers that map back to `ship_computer.db`, such as `entry_id` and `chunk_id`. This allows Spock to perform semantic search first and then apply exact relational filters, authorization checks, and citation tracking.

#### Retrieval-Augmented Generation (RAG) Workflow

When a user initiates an **Ask AI** or **Deep Dive** inquiry, the following pipeline executes:

1. **Query Embedding**: The user's natural language question is vectorized using the same embedding model applied to the knowledge base.
2. **Similarity Search**: The query vector is compared against the vector index using cosine similarity or inner product distance. The top-K most relevant chunks are retrieved.
3. **Hybrid Filtering**: Retrieved vectors are cross-referenced with `ship_computer.db` to apply relational filters (e.g., active profile, clearance level, time range). This ensures semantic relevance is constrained by operational policy.
4. **Context Assembly**: Filtered chunks are ranked, deduplicated, and assembled into a structured prompt context. Source citations are attached to each chunk for traceability.
5. **LLM Response Generation**: The assembled context is injected into the primary generative LLM, which produces a grounded, citation-backed response. The response is logged, and user feedback may trigger re-ranking or index updates.

For **Ask AI**, Spock usually selects a small top-K set and prioritizes precision. For **Deep Dive**, Spock may increase K, perform iterative retrieval, retrieve related captures, and include broader context while still enforcing the same access-control rules.

#### Synchronization & Maintenance

- **Incremental Updates**: New or modified `kb_entries` trigger delta embeddings. Deleted entries are marked as inactive in the vector index to prevent stale retrievals.
- **Index Refresh**: Periodic background jobs rebuild or optimize the vector index to account for drift, new terminology, or schema changes.
- **Fallback Mechanism**: If the embedding service or vector index is unavailable, the application gracefully degrades to keyword-based SQLite `LIKE`/`FTS5` searches, ensuring continuous operation during maintenance or network partitions.
## Access Pattern

The following example demonstrates how to interact with the database using the `ShipComputer` class provided by the `WarpCore.db` module. This class acts as an abstraction layer that manages the database connection and provides query methods for accessing data.

```python
from WarpCore.db import ShipComputer

db = ShipComputer()
entries = db.query("SELECT * FROM profiles WHERE active = 1")
```

In this snippet:

1. **Initialization**: `ShipComputer()` instantiates a connection manager that establishes a link to the SQLite database file (`ship_computer.db`), initializing it according to the predefined application schema.
2. **Query Execution**: The `query` method executes SQL statements against the active connection. For production security, parameterized queries should always be used instead of string concatenation to prevent SQL injection vulnerabilities.
3. **Data Retrieval**: The results are stored in the `entries` variable, which typically contains a list of dictionaries or data objects representing the rows returned from the `profiles` table.

This pattern enables direct SQL access while maintaining centralized connection management across the application.

When dynamic values are involved, use parameter binding if supported by the `ShipComputer.query` method. A typical parameterized implementation looks like this:

```python
from WarpCore.db import ShipComputer

db = ShipComputer()
active_flag = 1
entries = db.query("SELECT * FROM profiles WHERE active = ?", [active_flag])
```

Parameter binding separates SQL logic from data values, mitigating SQL injection risks and allowing SQLite to optimize prepared statement execution. If the API does not expose a parameters argument, utilize a higher-level repository method or rigorously validate and sanitize inputs before constructing queries.

### Connection Lifecycle

When using the `ShipComputer` class, manage the database connection lifecycle appropriately. SQLite connections consume system resources; therefore, close instances when they are no longer needed to prevent resource leaks. If the class implements the context-manager protocol, scoped access can be written as:

```python
with ShipComputer() as db:
    entries = db.query("SELECT * FROM profiles WHERE active = 1")
```

For production environments, consider implementing a session-management strategy that reuses connections efficiently rather than instantiating new objects for every operation. Additionally, adhere to the following best practices:

- Maintain one connection per thread unless the SQLite driver is explicitly configured for cross-thread sharing.
- For concurrent access, configure a `busy_timeout` and enable Write-Ahead Logging (WAL) mode to mitigate write contention.
- Explicitly close or release long-lived connections after batch operations when they are no longer required.

## ship_computer.db Schema & Spock Application Integration

The `ship_computer.db` file is a SQLite 3 database that serves as the persistent storage layer for the Spock application. It is structured to support both traditional relational queries and AI-driven retrieval workflows. The database primarily manages user profiles, session states, inquiry logs, and metadata required for the "Ask AI" and "Deep Dive" features.

### Database Schema Overview

The schema is optimized for read-heavy workloads with occasional writes. Key tables include:

- `profiles`: Stores user configurations, active status flags, and preference settings.
- `inquiries`: Logs all user prompts, timestamps, and associated metadata for audit and context tracking.
- `knowledge_base`: Contains structured reference data, documentation snippets, and system prompts.
- `vector_metadata`: Maps vector identifiers to source documents, enabling traceability for AI-generated responses.

### Ask AI Inquiry Flow

When a user initiates an "Ask AI" request, the Spock application follows a streamlined retrieval-augmented generation (RAG) pipeline:

1. **Intent Parsing**: The application routes the query through the `ShipComputer` instance to validate user permissions and retrieve relevant profile settings.
2. **Context Retrieval**: The system queries `ship_computer.db` for recent conversation history and domain-specific knowledge entries.
3. **Response Generation**: Retrieved context is formatted into a system prompt and sent to the primary LLM. The final response is cached in the `inquiries` table for future reference and analytics.

### Deep Dive Inquiry Flow

"Deep Dive" requests require comprehensive, multi-step analysis. The interaction with `ship_computer.db` expands to support iterative querying:

1. **Query Decomposition**: The initial prompt is broken down into sub-queries. Each sub-query triggers targeted SQL statements against `ship_computer.db` to fetch granular data points.
2. **State Management**: Intermediate results and reasoning steps are persisted in temporary tables or session-specific records to maintain context across multiple LLM calls.
3. **Synthesis & Logging**: Once all data points are gathered, the application synthesizes the findings. The complete trace, including database query logs and LLM reasoning steps, is archived in `ship_computer.db` for reproducibility and debugging.

### Reference Schema

The following schema illustrates the core relational structure of `ship_computer.db`. It is designed to support profile management, inquiry auditing, knowledge storage, vector traceability, and Deep Dive session tracking.

```sql
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL UNIQUE,
    display_name TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    preferences_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS inquiries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    mode TEXT NOT NULL CHECK (mode IN ('ask_ai', 'deep_dive')),
    prompt TEXT NOT NULL,
    response TEXT,
    status TEXT NOT NULL DEFAULT 'completed',
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS knowledge_base (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    title TEXT,
    body TEXT NOT NULL,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (source_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS vector_metadata (
    vector_id TEXT PRIMARY KEY,
    knowledge_id INTEGER NOT NULL REFERENCES knowledge_base(id),
    embedding_model TEXT NOT NULL,
    embedding_version TEXT,
    dimension INTEGER,
    source_uri TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS deep_dive_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    inquiry_id INTEGER REFERENCES inquiries(id),
    objective TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS deep_dive_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES deep_dive_sessions(id),
    step_order INTEGER NOT NULL,
    subquery TEXT NOT NULL,
    vector_ids_json TEXT,
    sql_result_json TEXT,
    reasoning TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### Embedding LLM and Vector Database Integration

The Spock application uses an embedding LLM, or embedding model, to convert natural-language text into numerical vector representations. These vectors allow the application to perform semantic similarity searches across a vector database. The vector database stores the high-dimensional vectors and supports fast nearest-neighbor retrieval, while `ship_computer.db` stores the relational metadata needed to trace, validate, and contextualize the retrieved content.

In this architecture, the embedding LLM and the vector database serve different but complementary roles:

- **Embedding LLM**: Converts text chunks, user prompts, and sub-queries into fixed-size vector embeddings.
- **Vector Database**: Stores embeddings and returns the most semantically similar records for a given query vector.
- **`ship_computer.db`**: Stores profiles, inquiry logs, knowledge-base content, vector metadata, and Deep Dive session state.

This separation allows Spock to combine semantic retrieval with structured data access. For example, the vector database can identify relevant documentation chunks, while `ship_computer.db` can provide the source document, user permissions, conversation history, and audit trail.

#### Ingestion Workflow

When new knowledge is added to the Spock application, the following workflow is typically used:

1. **Chunking**: Source documents are split into manageable chunks, such as paragraphs, sections, or API reference entries.
2. **Embedding**: Each chunk is passed to the embedding LLM, producing a vector representation.
3. **Vector Storage**: The vector is stored in the vector database with a unique `vector_id`.
4. **Metadata Storage**: A corresponding row is inserted into `vector_metadata`, linking the `vector_id` to the `knowledge_base` record.
5. **Knowledge Storage**: The original text chunk is stored in `knowledge_base` for retrieval, citation, and context assembly.

This design ensures that AI-generated responses can be traced back to specific source material.

#### Retrieval Workflow

During an "Ask AI" or "Deep Dive" request, Spock uses the embedding LLM and vector database as follows:

1. **Prompt Embedding**: The user prompt, or a decomposed sub-query, is converted into a vector using the same embedding model used during ingestion.
2. **Vector Search**: The vector database searches for the most similar stored vectors.
3. **Metadata Resolution**: The returned `vector_id` values are used to query `vector_metadata` and resolve the associated `knowledge_base` records.
4. **Context Assembly**: The retrieved text chunks are combined with profile settings, recent inquiry history, and any structured data required by the request.
5. **Generation**: The assembled context is provided to the primary LLM, which generates the final response.
6. **Persistence**: The prompt, response, retrieved vector IDs, and relevant metadata are stored in `ship_computer.db` for auditing and future context.

#### Example Retrieval Pattern

The following example illustrates how Spock may combine vector search results with relational data from `ship_computer.db`:

```python
from WarpCore.db import ShipComputer

db = ShipComputer()

# Assume `vector_db.search` returns the top matching vector IDs.
top_vector_ids = vector_db.search(prompt_embedding, k=5)

rows = db.query(
    """
    SELECT
        kb.id,
        kb.title,
        kb.body,
        vm.vector_id,
        vm.embedding_model
    FROM vector_metadata AS vm
    JOIN knowledge_base AS kb
        ON kb.id = vm.knowledge_id
    WHERE vm.vector_id IN (?, ?, ?, ?, ?)
    """,
    top_vector_ids
)
```

In this pattern, the vector database identifies semantically relevant content, while `ship_computer.db` provides the authoritative text and metadata needed to build a reliable prompt for the primary LLM.

### Ask AI and Deep Dive Interaction Details

The "Ask AI" and "Deep Dive" features both rely on `ship_computer.db`, but they use the database in different ways.

#### Ask AI Interaction

For "Ask AI" requests, the database is used primarily for:

- Validating the active user profile.
- Retrieving user preferences and permission settings.
- Loading recent inquiry history for conversational context.
- Resolving vector search results to source knowledge records.
- Storing the final prompt, response, and retrieval metadata.

A typical "Ask AI" sequence is:

1. Spock receives the user prompt.
2. `ShipComputer` validates the profile and loads relevant settings.
3. The prompt is embedded using the embedding LLM.
4. The vector database returns the most relevant vector IDs.
5. `ship_computer.db` maps those vector IDs to `knowledge_base` records.
6. The application assembles a context window from the retrieved records.
7. The primary LLM generates the answer.
8. The completed inquiry is written to the `inquiries` table.

#### Deep Dive Interaction

For "Deep Dive" requests, the database is used more extensively because the workflow is iterative and stateful.

The database supports:

- Creating a Deep Dive session.
- Storing the original objective.
- Persisting each decomposed sub-query.
- Recording vector search results for each step.
- Storing intermediate SQL results.
- Preserving LLM reasoning steps.
- Maintaining a complete audit trail for reproducibility.

A typical "Deep Dive" sequence is:

1. Spock creates a `deep_dive_sessions` record.
2. The initial prompt is decomposed into sub-queries.
3. Each sub-query is embedded using the embedding LLM.
4. The vector database performs similarity searches for each sub-query.
5. `ship_computer.db` resolves vector IDs to knowledge-base content.
6. Additional SQL queries may be executed to retrieve structured data.
7. Intermediate results are stored in `deep_dive_steps`.
8. The application iterates until sufficient evidence has been gathered.
9. The final synthesis is generated by the primary LLM.
10. The complete session trace is archived in `ship_computer.db`.

This approach allows Spock to perform complex, multi-step analysis while preserving enough context to explain, debug, and reproduce the final result.
## Embedding LLM & Vector Database Architecture

The Spock application leverages an embedding LLM and a vector database to transform unstructured text into searchable, high-dimensional representations. This architecture enables semantic search capabilities that go beyond traditional keyword matching. It supports both quick "Ask AI" questions and multi-step "Deep Dive" investigations by retrieving the most relevant context from the application's knowledge base.

### Embedding Generation Process
1. **Text Ingestion**: Raw documents, user prompts, and system knowledge bases are preprocessed to remove noise and segmented into manageable chunks.
2. **Vectorization**: The embedding LLM processes each text chunk and generates a fixed-length numerical vector, also called an embedding. These vectors capture semantic meaning, contextual relationships, and syntactic structure in a way that allows similar concepts to be close together in vector space.
3. **Storage**: The generated embeddings are stored in the vector database alongside their corresponding metadata, such as source ID, chunk index, content type, model version, and creation timestamp. In this architecture, the vector database is tightly integrated with `ship_computer.db`, allowing unified transactional control and simplified deployment.

### Semantic Search & Retrieval
When a user submits a query, the Spock application executes the following workflow:
- **Query Embedding**: The user's prompt is passed through the same embedding LLM used during ingestion to generate a query vector.
- **Similarity Search**: The vector database performs a nearest-neighbor search, typically using cosine similarity or Euclidean distance, to identify the most relevant document chunks.
- **Context Assembly**: The top-k retrieved chunks are ranked, filtered by relevance thresholds, and assembled into a structured context window.
- **LLM Prompt Construction**: The context window is injected into the primary LLM's prompt template, enabling the model to generate accurate, source-grounded responses.

### Performance & Optimization
To maintain low latency during "Ask AI" and "Deep Dive" operations, the vector database employs indexing strategies such as HNSW (Hierarchical Navigable Small World) or IVF (Inverted File Index). Additionally, the embedding LLM is cached for frequently accessed documents, and vector search results are periodically refreshed to ensure data consistency with the underlying `ship_computer.db` records.

### SQLite 3 `ship_computer.db` and Spock Interaction
`ship_computer.db` is the SQLite 3 database that stores the application's structured data, document content, chunk metadata, embedding records, and interaction history. It acts as the source of truth for the knowledge base and the operational state of Spock.

The database typically contains the following logical areas:

| Area | Purpose |
|---|---|
| Documents | Stores source records, titles, content, hashes, and lifecycle status. |
| Chunks | Stores segmented text pieces that are embedded and retrieved. |
| Embeddings | Stores vector representations, model version, dimensions, and vector payload. |
| Vector Index | Provides fast similarity search, either through a SQLite vector extension such as `sqlite-vec` or through an application-managed index. |
| Sessions and Messages | Stores Ask AI conversations and user/assistant turns. |
| Deep Dive Runs | Stores multi-step investigation plans, subqueries, intermediate results, and final synthesis. |
| Retrieval Logs | Stores query vectors, top-k results, thresholds, latency, and diagnostics. |

A representative schema might include:

```sql
CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    source TEXT,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE chunks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE (document_id, chunk_index)
);

CREATE TABLE embeddings (
    id INTEGER PRIMARY KEY,
    chunk_id INTEGER NOT NULL REFERENCES chunks(id),
    model TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    vector BLOB NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (chunk_id, model)
);

CREATE TABLE ai_sessions (
    id INTEGER PRIMARY KEY,
    mode TEXT NOT NULL CHECK (mode IN ('ask_ai', 'deep_dive')),
    created_at TEXT NOT NULL
);

CREATE TABLE ai_messages (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES ai_sessions(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE deep_dive_runs (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES ai_sessions(id),
    question TEXT NOT NULL,
    status TEXT NOT NULL,
    plan_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE deep_dive_steps (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES deep_dive_runs(id),
    step_index INTEGER NOT NULL,
    subquery TEXT NOT NULL,
    retrieved_chunk_ids TEXT,
    result_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE retrieval_logs (
    id INTEGER PRIMARY KEY,
    query TEXT NOT NULL,
    query_vector BLOB,
    top_k INTEGER NOT NULL,
    threshold REAL,
    latency_ms INTEGER,
    created_at TEXT NOT NULL
);
```

The vector database may be implemented as a SQLite virtual table, for example:

```sql
CREATE VIRTUAL TABLE vec_chunks USING vec0(
    embedding float[768]
);
```

In that case, Spock can query both relational metadata and vector similarity in the same database process. If a separate vector store is used instead, Spock must synchronize it with `ship_computer.db` using the same chunk identifiers and model versions.

### Ask AI and Deep Dive Inquiry Flow
For **Ask AI**, Spock treats the user's question as a single-turn semantic search problem. The application embeds the question, searches the vector index, retrieves the best-matching chunks from `ship_computer.db`, and passes those chunks to the primary LLM. The response is then stored in the session and message tables.

For **Deep Dive**, Spock treats the question as a multi-step investigation. The application may:
1. Embed the initial question and retrieve a broad set of candidate chunks.
2. Use the primary LLM to generate a plan or a set of subqueries.
3. Embed each subquery and perform additional vector searches.
4. Store each step, retrieved chunk IDs, and intermediate reasoning in `deep_dive_runs` and `deep_dive_steps`.
5. Synthesize the final answer from the accumulated context.
6. Persist the final response, citations, and diagnostics for auditability.

This design allows Deep Dive to explore related concepts that a single Ask AI query might miss, while still using the same embedding and retrieval foundation.

### Full Explanation: How Spock Uses the Embedding LLM and Vector Database
The embedding LLM is a specialized model that converts text into a fixed-size vector. Unlike the primary generative LLM, it does not produce natural-language answers. Instead, it produces a numerical representation that can be compared mathematically. Text with similar meaning produces vectors that are close together, while unrelated text produces vectors that are farther apart.

Spock uses this capability in two main phases:

1. **Indexing Phase**
   - Spock reads source records from `ship_computer.db`.
   - It chunks the text into stable, searchable units.
   - It sends each chunk to the embedding LLM.
   - It stores the resulting vector in the vector database or SQLite vector table.
   - It records the model name, vector dimensions, and chunk metadata so that future searches can verify compatibility.

2. **Retrieval Phase**
   - Spock receives an Ask AI or Deep Dive prompt.
   - It embeds the prompt using the same embedding model.
   - It asks the vector database for the nearest vectors.
   - It joins the retrieved vector IDs back to `chunks`, `documents`, and other metadata in `ship_computer.db`.
   - It filters results by relevance score, recency, permissions, or content status.
   - It assembles a context window for the primary LLM.

The vector database is therefore not a replacement for the relational database. It is a search accelerator. `ship_computer.db` remains the authoritative store for content, metadata, sessions, and Deep Dive state. The vector database provides fast similarity ranking, while SQLite provides transactional integrity, joins, filtering, and persistence.

This separation gives Spock three important properties:
- **Semantic relevance**: Queries can match meaning, not just exact words.
- **Traceability**: Every retrieved chunk can be traced back to a document and chunk ID.
- **Operational consistency**: Updates, deletions, and re-embeddings can be managed within the same application data layer.