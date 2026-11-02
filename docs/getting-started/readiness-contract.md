# Readiness Contract

Spock uses a JSON-based readiness contract to communicate system health and state transitions between deployment phases. This mechanism allows dependent components to verify the orchestration environment before proceeding.

## Schema

The readiness file is written to `spock_ready_last.json` in the project root.

```json
{
  "ui_ready": true,
  "servers_ready": true,
  "timestamp": "2026-01-01T00:00:00Z",
  "phase": "A"
}
```

### Explanation of Schema Fields

- **`ui_ready`**: Boolean indicating whether Phase A is complete. This confirms that the Python runtime, virtual environment (`.venv`), and `PyQt6` dependencies are correctly configured and importable within the application context.
- **`servers_ready`**: Boolean indicating whether backend services are healthy. Specifically, this verifies that the embedded server on port `8080` and the chat server on port `8081` respond to health checks with an HTTP `200 OK` status.
- **`timestamp`**: ISO 8601 string representing when the readiness contract was last updated. The value is expressed in UTC.
- **`phase`**: String identifying the current lifecycle stage of the system. This value tracks progress through setup or deployment stages, such as `"A"` and `"B"`.

Consumers should treat a missing file, malformed JSON, or an unrecognized `phase` value as "not ready" unless the consuming component has explicit fallback logic for that phase.

## Flags

| Flag | Meaning |
|------|---------|
| `ui_ready` | **Phase A complete:** Confirms the Python environment, virtual environment (`.venv`), and `PyQt6` are correctly set up and importable. |
| `servers_ready` | **Backend healthy:** Confirms that the embedded server on port `8080` and the chat server on port `8081` are both healthy and operational. |

## Usage

```python
from spock_onboarding.readiness import ReadinessContract

try:
    contract = ReadinessContract.load("spock_ready_last.json")
    if contract.ui_ready and contract.servers_ready:
        print("All systems operational")
except FileNotFoundError:
    # Handle the case where the readiness file does not exist yet.
    pass
```

Consumers should also handle malformed JSON or unexpected schema versions by treating the readiness state as unavailable rather than assuming success.

See `READINESS_SCHEMA.md` in the project root for the full JSON schema definition.

## State Transitions

The `phase` field acts as a token that orchestration logic uses to determine which setup steps have completed. Updates to this file should be performed atomically—for example, write to a temporary file first and then rename it—to prevent race conditions during concurrent access. The system typically transitions from Phase A (Environment Setup) to subsequent phases once both `ui_ready` and `servers_ready` are set to `true`.

The readiness file represents the last known state rather than a live status feed. Components that require current health should re-read the contract or perform their own health checks before making critical decisions.


## Database Architecture

The Spock application uses an embedded SQLite 3 database (`ship_computer.db`) located in the project root for persistent data storage. This database serves as the central repository for conversation context, user interactions, analytical results, and semantic search data required by the Ask AI and Deep Dive modules.

Because SQLite is embedded, the database file is local to the application and does not require a separate database server. This makes it well suited to single-user or small-team shipboard workloads where low operational overhead and fast local reads are important. The application should open the database with WAL mode, foreign keys enabled, and a controlled connection strategy to keep reads fast while preserving write consistency.

### Schema Overview

The database is structured to support high-frequency read operations for inference while maintaining write consistency for state updates. Key tables include:

- **`conversations`**: Stores metadata about active sessions, including session identifiers, creation timestamps, user roles, status flags, and optional tags for filtering.
- **`messages`**: Contains individual user prompts, system responses, and AI-generated replies linked to conversation IDs via foreign keys. It also stores message type, model identifiers, token counts, and feedback flags.
- **`context_cache`**: Holds preprocessed context snippets, normalized text, metadata, and optional references to vector records. It is optimized for rapid retrieval during AI inference.
- **`analysis_results`**: Stores outputs from Deep Dive inquiries, including structured data summaries, confidence scores, query parameters, result hashes, and metadata tags.
- **`vector_store`**: A dedicated table for high-dimensional embedding vectors and associated metadata, used for semantic similarity search. Depending on the SQLite extension in use, vectors may be stored as serialized BLOBs or in a vector-capable column.

### Detailed SQLite 3 Database Design

This section provides a more detailed view of how `ship_computer.db` is organized and how its tables support the Spock application.

#### File and Connection Settings

- **Database file**: `ship_computer.db` in the project root.
- **Journal mode**: `WAL` (Write-Ahead Logging) for concurrent readers and a single writer.
- **Foreign keys**: Enabled with `PRAGMA foreign_keys = ON;` to enforce referential integrity between conversations, messages, context, and analysis results.
- **Synchronous mode**: Typically `NORMAL` in WAL mode for a balance of durability and performance.
- **Busy timeout**: Configured to avoid immediate failures when a writer briefly holds the database lock.

#### Core Tables

| Table | Purpose | Key Fields |
|---|---|---|
| `conversations` | Session and conversation metadata | `id`, `user_id`, `created_at`, `updated_at`, `status`, `tags` |
| `messages` | Individual prompt and response records | `id`, `conversation_id`, `role`, `content`, `model`, `token_count`, `feedback`, `created_at` |
| `context_cache` | Reusable context snippets and metadata | `id`, `conversation_id`, `source`, `text`, `normalized_text`, `tags`, `created_at` |
| `analysis_results` | Deep Dive analytical outputs | `id`, `conversation_id`, `query`, `summary`, `confidence`, `tags`, `created_at` |
| `vector_store` | Embedding vectors and metadata | `id`, `source_id`, `source_type`, `text`, `embedding`, `model`, `dimensions`, `created_at` |

#### Indexes and Constraints

- Primary keys on all tables for stable identifiers.
- Foreign key constraints from `messages.conversation_id` to `conversations.id`.
- Foreign key constraints from `context_cache.conversation_id` and `analysis_results.conversation_id` to `conversations.id` where applicable.
- Indexes on `messages.conversation_id`, `messages.created_at`, `context_cache.conversation_id`, `analysis_results.conversation_id`, and `vector_store.source_id`.
- Optional full-text search indexes on `messages.content`, `context_cache.text`, and `analysis_results.summary` using SQLite FTS5 for keyword retrieval.
- Optional vector search support through an extension such as `sqlite-vec` for indexed KNN similarity search.

#### Example DDL

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    status TEXT NOT NULL DEFAULT 'active',
    tags TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    model TEXT,
    token_count INTEGER,
    feedback TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS context_cache (
    id TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    source TEXT NOT NULL,
    text TEXT NOT NULL,
    normalized_text TEXT,
    tags TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS analysis_results (
    id TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    query TEXT NOT NULL,
    summary TEXT NOT NULL,
    confidence REAL,
    tags TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vector_store (
    id TEXT PRIMARY KEY,
    source_id TEXT,
    source_type TEXT NOT NULL,
    text TEXT NOT NULL,
    embedding BLOB NOT NULL,
    model TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_context_conversation ON context_cache(conversation_id);
CREATE INDEX IF NOT EXISTS idx_analysis_conversation ON analysis_results(conversation_id);
CREATE INDEX IF NOT EXISTS idx_vector_source ON vector_store(source_id, source_type);
```

If a vector extension is used, the application may also create a vector table or vector index for KNN search. For example, with `sqlite-vec`, embeddings can be stored in a virtual vector table and queried with nearest-neighbor functions. Without such an extension, similarity search can still be performed by loading vectors into application memory and computing distances in Python, which is practical for small-to-moderate local datasets.

### Interaction with Ask AI

The `Ask AI` module uses the database as a context provider and audit log. It does not rely on the LLM to remember prior turns; instead, it reconstructs a bounded, relevant context from stored data before each request.

1. **Conversation lookup**: The application resolves the active `conversation_id` and loads recent `messages` rows in chronological order.
2. **Semantic retrieval**: The user's question is embedded by the embedding LLM. The resulting query vector is compared against vectors in `vector_store`, optionally filtered by `conversation_id`, `source_type`, `tags`, or time range.
3. **Keyword retrieval**: In parallel, SQLite FTS5 or other SQL text queries may retrieve exact terms, system names, error codes, or user-specified identifiers.
4. **Context assembly**: Retrieved snippets, recent messages, and relevant `analysis_results` are ranked, deduplicated, and truncated to fit the LLM context window.
5. **Prompt construction**: The assembled context is placed into a structured prompt with clear roles: system instructions, conversation history, retrieved context, and the user's current question.
6. **Response generation**: The LLM generates an answer using the supplied context.
7. **Persistence**: The user question, assistant response, model name, token usage, and retrieval metadata are written to `messages` and optionally to `context_cache` for future reuse.

This design keeps sensitive raw logs out of the prompt unless they are explicitly relevant, and it provides a traceable record of what context influenced each answer.

### Interaction with Deep Dive

The `Deep Dive` module performs complex analytical tasks that require structured data access beyond simple text retrieval. The database supports these inquiries through:

1. **Query planning**: The application interprets the user's request and determines which tables are needed, such as `messages`, `context_cache`, `analysis_results`, or `vector_store`.
2. **Structured querying**: Complex SQL queries are executed against the `analysis_results`, `conversations`, and `messages` tables to filter specific system states, historical trends, or anomaly patterns.
3. **Semantic enrichment**: When the request is ambiguous, the module embeds the request and retrieves semantically similar context or prior analyses to guide the SQL query.
4. **Data aggregation**: Results from multiple sources are aggregated within SQLite using window functions and `GROUP BY` clauses before being returned to the UI, reducing latency by minimizing round trips to external data stores.
5. **Result caching**: Completed Deep Dive outputs are stored in `analysis_results` with a query hash, summary, confidence score, and tags. Repeated or similar questions can reuse cached results when appropriate.
6. **State consistency**: Transactions are managed explicitly during Deep Dive operations using `BEGIN IMMEDIATE` or `BEGIN EXCLUSIVE` statements so that partial analysis does not corrupt the state of `ship_computer.db`.

Example Deep Dive query:

```sql
SELECT
    date(created_at) AS day,
    COUNT(*) AS message_count,
    AVG(token_count) AS average_tokens
FROM messages
WHERE conversation_id = ?
  AND role = 'assistant'
GROUP BY day
ORDER BY day;
```

### Maintenance and Integrity

The SQLite database is configured with WAL (Write-Ahead Logging) mode enabled by default to improve concurrent read/write safety and reduce locking contention during AI inference tasks. WAL allows multiple readers to operate while a writer is active, which is useful because Ask AI and Deep Dive often issue read-heavy queries while new messages are being logged.

Maintenance operations such as `VACUUM` and `ANALYZE` are scheduled for low-activity windows or when the database is idle, because they require exclusive access and should not run while high-concurrency workloads are active.

Recommended maintenance practices:

- Run `PRAGMA integrity_check;` during startup or scheduled health checks.
- Run `PRAGMA optimize;` after bulk inserts or deletions.
- Run `ANALYZE` after significant schema or data changes so the query planner has accurate statistics.
- Run `VACUUM` only when the database is idle and when file size reduction is needed.
- Back up `ship_computer.db` using SQLite's online backup API or by copying the file only when no writes are in progress.

### Embedding LLM and Vector Database Integration

Spock leverages a dedicated embedding LLM to transform unstructured text into fixed-dimensional numerical vectors. These vectors enable semantic search capabilities that traditional keyword matching cannot achieve. An embedding model is not a generative chat model; it produces a deterministic numerical representation of text, allowing the application to compare meaning rather than exact wording.

- **Embedding Generation**: When new data enters the system (e.g., system logs, user prompts, or documentation), the embedding LLM processes the text and outputs a high-dimensional vector (typically 384–1536 dimensions depending on the model). This process occurs asynchronously in a background worker to avoid blocking the main UI thread.
- **Vector Storage**: Generated vectors are stored in the `vector_store` table as serialized BLOBs or in a vector-capable column, depending on the SQLite extension in use. Each vector is paired with a unique identifier, source metadata, model name, dimension count, and a timestamp.
- **Similarity Search**: During inference, the user's query is embedded using the same model. The application then executes a vector similarity search against the `vector_store` table using cosine similarity, Euclidean distance, or dot product. When a vector extension such as `sqlite-vec` is used, indexed KNN search can provide fast retrieval; without an extension, the Python application can deserialize vectors from BLOBs and compute distances in memory, which is practical for small-to-moderate local datasets.
- **Hybrid Retrieval**: Spock combines vector search with traditional SQL filtering. For example, a query might first filter by `conversation_id` or `system_tag`, then rank results by semantic similarity. This hybrid approach ensures both precision and relevance.

#### Embedding Workflow

1. **Text preparation**: Raw text is normalized, cleaned, and chunked into meaningful units such as log entries, documentation paragraphs, or message segments.
2. **Embedding**: Each chunk is passed to the embedding LLM, which returns a fixed-size vector.
3. **Normalization**: Vectors may be normalized to unit length when cosine similarity is used, making distance calculations more stable.
4. **Storage**: The vector, chunk text, source identifier, source type, model name, dimensions, and timestamp are inserted into `vector_store`.
5. **Query embedding**: At query time, the user's question is embedded with the same model and version to ensure compatibility with stored vectors.
6. **Similarity scoring**: The query vector is compared against stored vectors to find the most semantically similar chunks.
7. **Ranking and filtering**: Results are filtered by metadata, ranked by similarity score, deduplicated, and truncated to fit the LLM context window.

#### Similarity Metrics

- **Cosine similarity**: Measures the angle between vectors and is commonly used when vector magnitude is less important than direction.
- **Euclidean distance**: Measures straight-line distance between vectors and can be useful when vector magnitude carries meaning.
- **Dot product**: Measures alignment between vectors and is often used with normalized embeddings.

The application should use the same metric consistently for indexing, retrieval, and ranking to avoid inconsistent relevance ordering.

### Query Resolution and Context Assembly

The interaction between `ship_computer.db`, the embedding LLM, and the vector DB follows a deterministic pipeline:

1. **Ingestion**: Raw text is normalized, chunked (if necessary), and passed to the embedding LLM.
2. **Indexing**: Vectors are inserted into the vector index with associated metadata. SQLite's transaction journal ensures atomicity during bulk inserts.
3. **Retrieval**: Ask AI and Deep Dive modules issue concurrent read queries. WAL mode allows multiple readers to access the database simultaneously without blocking writers.
4. **Context Window Management**: Retrieved vectors are ranked, truncated to fit the LLM's context window, and formatted into a structured prompt. Irrelevant or low-confidence matches are filtered out before API submission.
5. **Feedback Loop**: User corrections or explicit feedback are logged back into `messages` and optionally trigger re-embedding of corrected context, ensuring the knowledge base remains accurate over time.

#### Context Assembly Rules

- Prefer recent conversation history for continuity.
- Prefer high-similarity context chunks for factual grounding.
- Prefer structured `analysis_results` when the question asks for trends, counts, or comparisons.
- Exclude low-confidence matches unless the user explicitly requests broad exploration.
- Preserve source identifiers so the UI can display citations or provenance when available.
- Keep the final prompt within the model's token limit by truncating from the least relevant content first.

### Indexing and Performance Optimization

To maintain low-latency responses under load, `ship_computer.db` employs several optimization strategies:

- **WAL mode**: Enables concurrent reads during writes, reducing contention for Ask AI and Deep Dive workloads.
- **Covering indexes**: Indexes on frequently filtered columns such as `conversation_id`, `created_at`, `source_id`, and `tags` reduce full table scans.
- **Batched writes**: Message logging, context caching, and vector inserts are grouped into transactions to reduce commit overhead.
- **Precomputed context**: Frequently used context snippets are stored in `context_cache` to avoid repeated preprocessing.
- **Vector search limits**: Similarity search returns only the top N results, and metadata filters are applied before distance calculations when possible.
- **Query planning**: `ANALYZE` keeps SQLite's query planner informed about table sizes and index usage.
- **Connection management**: The application reuses connections or serializes writes to avoid excessive connection churn and lock contention.
- **Monitoring**: The application can track query latency, write failures, database size, and vector search duration to detect performance degradation early.
# SQLite 3 `ship_computer.db` and Spock Application Integration

`ship_computer.db` is the local SQLite 3 database used by the Spock application to store conversational state, request metadata, retrieval results, and vector search artifacts. It acts as the persistent data layer for both **Ask AI** and **Deep Dive** inquiries, while the embedding LLM and vector database provide semantic search over the application’s knowledge base.

## Ask AI and Deep Dive Inquiries

### Ask AI

**Ask AI** is the lightweight, conversational query mode used for direct questions. When a user submits an Ask AI request, the Spock application typically performs the following steps:

1. **Query Normalization**  
   The user’s question is cleaned, tokenized, and prepared for semantic search.

2. **Embedding Generation**  
   The query is passed to the embedding LLM, which converts it into a dense vector representation.

3. **Vector Search**  
   The vector is compared against stored embeddings in the vector database to retrieve the most semantically relevant records.

4. **Context Assembly**  
   The retrieved records, along with their metadata, are assembled into a compact context window.

5. **Answer Generation**  
   The Spock application uses the retrieved context to generate a concise, grounded response.

Ask AI is optimized for speed and low latency. It usually retrieves a small number of highly relevant results and avoids loading large analytical payloads unless necessary.

### Deep Dive

**Deep Dive** is the more thorough investigation mode used when the user requires detailed analysis, multi-source synthesis, or extended context. Compared with Ask AI, Deep Dive may:

- Retrieve a larger number of candidate records.
- Apply additional filters such as domain, session type, timestamp, or status.
- Perform reranking or secondary scoring to improve result quality.
- Load heavier analytical payloads only when explicitly requested by the UI.
- Store intermediate results in `ship_computer.db` so the user can review, compare, or continue the investigation.

Deep Dive is designed for complex questions where completeness and context matter more than immediate response time.

## Embedding LLM and Vector Database

The Spock application uses an **embedding LLM** to convert natural-language text into numerical vector representations. These vectors capture semantic meaning, allowing the application to search for related content even when the exact wording differs.

### Embedding Process

When content is indexed or a query is submitted, the embedding LLM performs the following:

1. **Text Input**  
   The application provides a text string, such as a user question, document chunk, conversation message, or knowledge-base entry.

2. **Vector Generation**  
   The embedding model produces a fixed-length vector, commonly represented as a list of floating-point numbers.

3. **Vector Storage**  
   The vector is stored in the vector database alongside metadata such as:
   - `conversation_id`
   - `message_id`
   - `timestamp`
   - `status`
   - `domain`
   - `session_type`
   - `source_reference`

4. **Similarity Search**  
   At query time, the user’s question is embedded using the same model. The vector database then compares the query vector against stored vectors using a similarity metric such as cosine similarity, dot product, or Euclidean distance.

### Vector Database Role

The vector database is responsible for fast semantic retrieval. It may be implemented as:

- A SQLite 3 extension such as `sqlite-vec`.
- A separate vector database service.
- A hybrid store where SQLite 3 holds relational metadata and the vector database holds embeddings.

In all cases, the vector database enables the Spock application to find relevant records without requiring exact keyword matches.

### Interaction with `ship_computer.db`

`ship_computer.db` stores the relational and operational data needed to manage Ask AI and Deep Dive workflows. This may include:

- Conversation history.
- User questions and system responses.
- Retrieval metadata.
- Vector search result references.
- Deep Dive session state.
- Lazy-loaded analytical payload references.
- Indexing status and synchronization metadata.

The vector database stores the embeddings used for semantic search, while `ship_computer.db` stores the structured context needed to present, filter, and manage those results within the Spock application.

## Performance and Concurrency

- **Covering Indexes**: Frequently queried columns, such as `conversation_id`, `timestamp`, and `status`, are indexed to avoid full table scans. Covering indexes allow SQLite 3 to satisfy common queries directly from the index, reducing disk I/O and improving response time for both Ask AI and Deep Dive operations.

- **Vector Index Partitioning**: The vector store is partitioned by domain or session type to reduce the search space and improve cache locality. Partitioning allows the Spock application to search only the relevant subset of vectors, which improves latency and reduces unnecessary computation during semantic retrieval.

- **Connection Pooling**: The Python application uses a thread-safe connection pool with `check_same_thread=False` and explicit `PRAGMA journal_mode=WAL` settings to prevent SQLite locking errors during concurrent AI requests. WAL mode allows readers and writers to operate more safely under concurrency, while the connection pool ensures that multiple application threads can access the database without exhausting or corrupting connections.

- **Lazy Loading**: Heavy analytical payloads are fetched only when explicitly requested by the UI, reducing memory overhead and database I/O during standard Ask AI interactions. This keeps lightweight queries fast while still allowing Deep Dive workflows to load detailed data when the user needs it.