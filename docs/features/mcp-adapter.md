# MCP Adapter

The MCP (Model Context Protocol) adapter bridges the Spock framework with external AI agents. It exposes Spock tools and resources through the Model Context Protocol, enabling agents to discover capabilities, invoke operations, and receive structured responses. The adapter also facilitates bidirectional communication between external agents and the Spock ecosystem.

## Components

| Module | Role |
|--------|------|
| `spock_mcp_adapter.mcp_host` | **MCP Server Host** — Manages the MCP server endpoint and bidirectional message exchange with AI agents. It handles request/response serialization, protocol framing, tool-call dispatch, and result transmission. |
| `spock_mcp_adapter.mcp_panel` | **MCP Status Panel** — Provides a user interface for monitoring adapter status, including real-time metrics, logs, connection health, and recent activity. |
| `spock_mcp_adapter.paths` | **Path Configuration** — Centralizes filesystem path resolution for configuration files, log directories, data stores, and tool definition schemas used by the adapter. |
| `spock_mcp_adapter.proc_guard` | **Process Lifecycle Management** — Supervises adapter-managed background processes, including startup, shutdown, health monitoring, error handling, and recovery where supported. |

## Prerequisites

Before running the MCP adapter, ensure the following environment requirements are met:

1.  **Python Environment**: A compatible Python interpreter must be available, and a virtual environment (`.venv`) should be initialized in the project directory. On Windows, execute via `.venv\Scripts\python.exe`; on Linux or macOS, use `.venv/bin/python`.
2.  **Dependencies**: All required Python packages for the `spock_mcp_adapter` module must be installed within the virtual environment. If the project provides a dependency manifest (e.g., `requirements.txt` or `pyproject.toml`), install the declared dependencies before starting the adapter.
3.  **Permissions**: The executing user must have read and execute access to the Python interpreter and adapter files, as well as write access to the log and data directories defined in `paths`.

## Usage

To start the MCP adapter, use the following command in PowerShell:

```powershell
.venv\Scripts\python.exe -m spock_mcp_adapter
```

This command runs the `spock_mcp_adapter` package as a module using the Python interpreter located inside the `.venv` virtual environment. The adapter remains active until it is stopped with `Ctrl+C`, receives a termination signal, or encounters a fatal error. Restart the adapter after making configuration changes so that updated tool definitions and settings are loaded.

## Configuration

MCP tools are registered in `WarpCore.skills` and served through the adapter. This configuration object acts as the central registry for Spock capabilities exposed to AI agents. It defines which tools are available, how they are described to external clients, and which internal operations they may invoke.

*   **Tool Registration**: Tools must be explicitly defined within `WarpCore.skills` to be discoverable by external agents. Each tool entry should include the metadata required by MCP, such as a name, description, parameter schema, and the Spock operation or resource it invokes.
*   **Exposure Settings**: Configure only the intended tools for agent access. This practice maintains security boundaries, prevents accidental exposure of internal functions, and keeps the agent-facing API predictable.
*   **Validation**: After modifying tool definitions, restart the adapter and verify that the new configuration loads without runtime errors. Test representative calls to confirm that serialization, permissions, and response formats behave as expected.

## SQLite 3 Database: `ship_computer.db`

The `ship_computer.db` file serves as the primary relational data store for the Spock application, leveraging SQLite 3's serverless, ACID-compliant architecture. It persists structured metadata, operational logs, user preferences, cached contexts, and inquiry histories. The database is optimized for concurrent read-heavy workloads and utilizes Write-Ahead Logging (WAL) mode to ensure data integrity without blocking read operations during active agent sessions.

### Purpose and Design

`ship_computer.db` provides the durable, queryable foundation for Spock's AI workflows. It stores relational facts and operational state that the MCP adapter, Ask AI, and Deep Dive can inspect, filter, cache, and audit. The database is not a substitute for the vector database; rather, it complements semantic retrieval by supplying authoritative metadata, permissions, session state, and historical records.

Key design goals include:

*   **Low-latency reads**: Ask AI and Deep Dive frequently need fast access to session context, tool metadata, and cached results.
*   **Safe writes**: Deep Dive operations may generate reports, audit records, and state changes that must be committed atomically.
*   **Auditability**: Spock records who requested what, which tools were invoked, and what data was returned.
*   **Cache efficiency**: Frequently used prompts, responses, and retrieval results can be cached to reduce LLM token consumption and latency.
*   **Background processing**: Long-running Deep Dive jobs can be tracked, resumed, or monitored through `proc_guard`.

### Typical Logical Tables

The exact table names may vary by deployment, but the logical model commonly includes the following entities:

| Logical table | Purpose |
|---------------|---------|
| `sessions` | Tracks active and historical agent sessions, including session identifiers, timestamps, and user context. |
| `messages` | Stores conversation turns, user prompts, assistant responses, and tool-call context. |
| `tool_calls` | Records MCP tool invocations, parameters, results, errors, and execution duration. |
| `resources` | Stores metadata about Spock resources, documents, files, or external references available to agents. |
| `preferences` | Persists user-specific settings, prompt preferences, and access scopes. |
| `cache` | Stores cached prompts, responses, retrieval results, and embedding metadata for reuse. |
| `audit` | Records security-relevant events, permission checks, and data-access decisions. |
| `deep_dive_jobs` | Tracks Deep Dive operations, including status, progress, resource usage, and completion state. |
| `vector_index_metadata` | Stores links between relational records and vector database entries, including source identifiers, chunk identifiers, and index versions. |

### Interaction with Ask AI Inquiries

The **Ask AI** workflow relies on `ship_computer.db` for rapid, lightweight context retrieval. When an agent initiates an Ask AI request, the adapter queries the database for:

*   **Recent Session Context**: Cached conversation history and user-specific preferences to maintain continuity.
*   **Metadata Indexes**: Lightweight lookups for tool availability, resource tags, and permission scopes.
*   **Response Caching**: Frequently requested answers or system prompts are stored to reduce latency and LLM token consumption.

These queries are designed to be non-blocking and execute within strict timeout thresholds to ensure real-time responsiveness. Ask AI typically uses short-lived read transactions, prepared statements, and indexed lookups to minimize database contention.

### Interaction with Deep Dive Inquiries

The **Deep Dive** workflow triggers complex, transactional operations against `ship_computer.db`. Unlike Ask AI, Deep Dive requests require comprehensive data aggregation and historical analysis. The adapter performs:

*   **Multi-Table Joins**: Correlating logs, user activity, system events, and external resource references to build a complete analytical picture.
*   **Historical Data Retrieval**: Fetching extended time-series data or archived inquiry records for trend analysis and pattern recognition.
*   **State Persistence**: Writing detailed analysis results, generated reports, and audit trails back to the database for future reference.

Deep Dive operations are wrapped in explicit transactions to guarantee consistency. If a query exceeds resource thresholds, the adapter gracefully degrades to a partial response or queues the operation for background processing via `proc_guard`.

## Embedding LLM and Vector Database Integration

Spock uses an embedding LLM and a vector database to support semantic retrieval for Ask AI and Deep Dive inquiries. The embedding LLM converts text into numerical vectors that represent meaning. The vector database stores those vectors and supports fast similarity search. SQLite stores relational metadata, permissions, session state, and links to vector records.

### Role of the Embedding LLM

The embedding LLM is responsible for transforming natural-language content into dense vector representations. These vectors capture semantic similarity, allowing Spock to retrieve relevant information even when the user's wording differs from the source material.

Spock may embed:

*   User questions and follow-up prompts.
*   Documents, notes, resources, and tool descriptions.
*   Session summaries and conversation history.
*   Deep Dive reports, analysis artifacts, and generated insights.
*   Cached retrieval results and prompt fragments.

The embedding model may be local or remote. In either case, Spock treats it as a deterministic text-to-vector service that produces fixed-size vectors suitable for similarity comparison.

### Role of the Vector Database

The vector database stores embeddings and associated metadata. It enables Spock to perform approximate nearest-neighbor search, cosine similarity search, dot-product search, or other vector similarity operations depending on the configured index.

The vector database is used to:

*   Find semantically relevant context for Ask AI responses.
*   Retrieve related documents, resources, and prior Deep Dive results.
*   Support multi-hop retrieval by following related concepts across multiple sources.
*   Filter results by metadata such as source, timestamp, user scope, permission level, or resource type.
*   Reduce the amount of raw text sent to the generative LLM, improving latency and token efficiency.

The vector database may be embedded within the application or deployed as a separate service. Spock abstracts this implementation behind a retrieval interface so that Ask AI and Deep Dive can request semantic context without depending on a specific vector store.

### Ingestion and Indexing

Before content can be retrieved, Spock prepares it for vector search:

1.  **Source Selection**: Spock identifies eligible documents, resources, session history, or tool metadata.
2.  **Chunking**: Large content is divided into manageable chunks to improve retrieval precision.
3.  **Embedding**: Each chunk is converted into a vector using the embedding LLM.
4.  **Metadata Attachment**: Each vector is associated with metadata such as source identifier, chunk identifier, timestamp, user scope, and permission level.
5.  **Indexing**: The vector and metadata are stored in the vector database.
6.  **Relational Linking**: `ship_computer.db` stores the relational metadata and links to the vector record, enabling audit, filtering, and cache management.

### Ask AI Retrieval Path

Ask AI is optimized for fast, conversational responses. Its retrieval path is typically shallow and latency-sensitive.

When an Ask AI request is received:

1.  The MCP adapter validates the request and checks permissions.
2.  `ship_computer.db` is queried for session context, user preferences, and cached results.
3.  The user question is embedded using the embedding LLM.
4.  The vector database performs a similarity search over eligible embeddings.
5.  Results are filtered using SQLite metadata, such as user scope, resource permissions, and freshness.
6.  The most relevant context is assembled into a prompt.
7.  The generative LLM produces a response.
8.  The response, retrieval metadata, and any cache entries are written back to `ship_computer.db`.

Ask AI may use cached embeddings or cached retrieval results when available. This reduces repeated embedding work and lowers response latency.

### Deep Dive Retrieval Path

Deep Dive is optimized for comprehensive analysis. It may perform multiple retrieval passes, aggregate results from many sources, and persist detailed findings.

When a Deep Dive request is received:

1.  The MCP adapter creates or resumes a Deep Dive job in `ship_computer.db`.
2.  The request is decomposed into sub-questions or analysis objectives.
3.  Each sub-question is embedded and searched against the vector database.
4.  SQLite is used to filter results by permissions, source reliability, time range, and resource type.
5.  Retrieved context is reranked, deduplicated, and correlated across sources.
6.  Additional retrieval passes may be performed to resolve gaps or follow related concepts.
7.  The generative LLM synthesizes a detailed response or report.
8.  The final result, intermediate findings, audit records, and job status are persisted to `ship_computer.db`.

Deep Dive may run in the foreground or be delegated to a background process through `proc_guard`. In either case, the database provides the durable state needed to track progress, recover from failures, and audit the operation.

### Coordination Between SQLite and the Vector Database

SQLite and the vector database serve complementary roles:

| Concern | SQLite 3 `ship_computer.db` | Vector Database |
|---------|-----------------------------|-----------------|
| Primary data type | Relational records, logs, preferences, audit data | Dense vectors and semantic metadata |
| Query style | SQL, indexed lookups, joins, transactions | Similarity search, approximate nearest-neighbor search |
| Strength | Authoritative state, permissions, history, audit | Semantic relevance, fuzzy matching, concept retrieval |
| Ask AI use | Session context, caching, permission checks | Fast retrieval of relevant context |
| Deep Dive use | Job tracking, aggregation, persistence, audit | Multi-pass semantic retrieval and correlation |

Spock uses SQLite to decide *what is allowed, what is cached, and what has happened*, while the vector database helps determine *what is semantically relevant*.

### Caching, Permissions, and Failure Handling

Spock applies several safeguards when using embeddings and vector search:

*   **Permission Filtering**: Vector search results are filtered against SQLite-stored permissions before being included in a prompt.
*   **Cache Invalidation**: Cached embeddings and retrieval results are invalidated when source content, permissions, or index versions change.
*   **Timeouts**: Ask AI retrieval is bounded by latency thresholds to preserve responsiveness.
*   **Graceful Degradation**: If vector search is unavailable, Spock may fall back to SQLite-based keyword or metadata retrieval where appropriate.
*   **Audit Logging**: Retrieval decisions, permission checks, and cache hits are recorded in `ship_computer.db`.
*   **Background Recovery**: Long-running Deep Dive retrieval jobs can be monitored and resumed through `proc_guard`.
## Embedding LLM and Vector Database Integration

The Spock application employs a Retrieval-Augmented Generation (RAG) architecture powered by an embedding model and a dedicated vector database. This pipeline enables semantic understanding, context-aware retrieval, and precise information synthesis for both **Ask AI** and **Deep Dive** workflows.

In this architecture, the term **embedding LLM** refers to a model that converts text into numerical vector representations. It is not primarily a generative language model; its role is to encode meaning so that semantically similar text can be compared mathematically.

### Embedding Pipeline

When a user or agent submits a query, the raw text is first processed by the embedding model. This model converts unstructured text into high-dimensional numerical vectors, called **embeddings**, that capture semantic meaning, intent, and contextual relationships.

Unlike keyword-based search, embeddings allow the system to understand:

*   Paraphrased questions
*   Domain-specific terminology
*   Synonyms and related concepts
*   Implicit user intent
*   Questions expressed in different wording but with similar meaning

For example, a query such as “What is the current status of the navigation subsystem?” can be matched to a document that says “The nav system is operational,” even if the exact words do not overlap.

### Vector Database Operations

The generated embeddings are indexed and stored in a vector database optimized for similarity search. Key operations include:

*   **Indexing**: Embeddings are organized using approximate nearest neighbor (ANN) algorithms, such as HNSW or IVF, to enable fast retrieval across large collections of documents, chunks, or metadata records.
*   **Similarity Search**: Incoming query embeddings are compared against the stored index using distance metrics such as cosine similarity, Euclidean distance, or inner product. The vector database returns the most semantically relevant chunks, documents, or metadata records.
*   **Metadata Filtering**: Vector searches can be constrained by structured filters, such as date ranges, user roles, data sources, document types, or access permissions, to ensure precise and secure retrieval.

The vector database is responsible for answering questions such as:

*   “Which passages are most relevant to this question?”
*   “Which documents discuss this concept?”
*   “Which records are semantically similar to this user intent?”

### SQLite 3 `ship_computer.db` Integration

The Spock application also uses a local SQLite 3 database file named `ship_computer.db` as the system of record for structured, transactional, and audit-related data. SQLite 3 is an embedded, file-based relational database that provides ACID transactions, SQL querying, indexing, and lightweight concurrency without requiring a separate database server.

`ship_computer.db` complements the vector database by storing data that is best represented relationally, such as users, sessions, permissions, prompts, responses, citations, configuration, audit logs, and references to external records.

#### Core Responsibilities

`ship_computer.db` is used for:

*   **Structured application state**: Storing users, roles, sessions, preferences, and workflow state.
*   **Transactional records**: Recording prompts, responses, tool calls, and agent actions in a durable and auditable way.
*   **Access control**: Enforcing permissions, data ownership, and role-based visibility before retrieval or response generation.
*   **Caching**: Storing frequently used context, summaries, or precomputed results to reduce repeated vector searches or LLM calls.
*   **Citation tracking**: Linking generated answers to specific documents, chunks, tables, or records used as evidence.
*   **Audit logging**: Capturing who asked what, when, what context was retrieved, and what response was returned.
*   **Workflow coordination**: Supporting multi-step **Deep Dive** workflows by persisting intermediate results, task state, and follow-up queries.

#### Typical Data Stored in `ship_computer.db`

The exact schema may vary by deployment, but a typical `ship_computer.db` may contain tables such as:

| Table | Purpose |
|---|---|
| `users` | Stores user identities, roles, and access permissions. |
| `sessions` | Tracks active or historical user and agent sessions. |
| `prompts` | Stores user questions, agent queries, and prompt metadata. |
| `responses` | Stores generated answers, confidence scores, and response metadata. |
| `citations` | Links responses to source documents, chunks, or database records. |
| `vector_references` | Stores identifiers or metadata pointing to records in the vector database. |
| `audit_logs` | Records access, retrieval, generation, and administrative actions. |
| `workflow_state` | Persists intermediate state for multi-step **Deep Dive** workflows. |
| `cache_entries` | Stores reusable summaries, embeddings metadata, or precomputed context. |

SQLite 3 may also be used to store lightweight keyword indexes, such as FTS5 full-text search tables, when exact phrase matching or lexical search is useful alongside semantic vector search.

#### Ask AI Interaction

For an **Ask AI** request, `ship_computer.db` and the vector database work together in a coordinated sequence.

1.  **Request intake**: The user submits a question through the Spock interface.
2.  **Permission check**: Spock queries `ship_computer.db` to verify the user’s identity, role, and access rights.
3.  **Context lookup**: Spock may retrieve structured context from `ship_computer.db`, such as recent session data, cached summaries, or known entity records.
4.  **Semantic retrieval**: The query is embedded and sent to the vector database to retrieve relevant unstructured or semi-structured content.
5.  **Result filtering**: Retrieved vector results are filtered using metadata stored in or referenced by `ship_computer.db`, such as permissions, source type, or date range.
6.  **Prompt assembly**: Spock combines structured SQLite data, vector-retrieved context, and the user’s question into a grounded prompt.
7.  **Response generation**: The generative LLM produces an answer using the assembled context.
8.  **Persistence**: The prompt, response, citations, and audit information are written back to `ship_computer.db`.

In this workflow, `ship_computer.db` provides authoritative structured context and governance, while the vector database provides semantic recall over larger text collections.

#### Deep Dive Interaction

For a **Deep Dive** inquiry, the interaction becomes iterative and more complex. A Deep Dive request usually requires multiple retrieval passes, cross-referencing, and synthesis across several sources.

1.  **Task decomposition**: Spock breaks the user’s question into sub-questions or research objectives.
2.  **Initial structured scan**: `ship_computer.db` is queried for known entities, prior results, permissions, and workflow state.
3.  **First vector search**: The embedding model encodes the initial sub-question, and the vector database returns the most relevant semantic matches.
4.  **Entity extraction**: Spock extracts key entities, concepts, or identifiers from the retrieved content.
5.  **Relational cross-reference**: Those entities are used to query `ship_computer.db` for related records, such as linked documents, user notes, status records, or historical answers.
6.  **Follow-up vector searches**: New sub-queries are generated from the combined structured and semantic context, and additional vector searches are performed.
7.  **Aggregation**: Results from multiple semantic clusters are merged, deduplicated, and ranked.
8.  **Validation**: Spock checks consistency between vector-retrieved claims and structured records in `ship_computer.db`.
9.  **Synthesis**: The generative LLM produces a comprehensive answer with citations and evidence links.
10. **Persistence**: The full workflow, intermediate results, citations, and final answer are stored in `ship_computer.db` for auditability and future reuse.

In this workflow, `ship_computer.db` acts as the coordination and verification layer, while the vector database acts as the semantic discovery layer.

#### Consistency and Security

Because `ship_computer.db` is transactional, it can safely record state changes even when vector searches or LLM calls are non-deterministic. This is important for:

*   Maintaining a reliable audit trail
*   Preventing unauthorized access to retrieved content
*   Preserving intermediate Deep Dive state
*   Reusing cached context safely
*   Linking generated answers to verifiable sources

The vector database may store embeddings and metadata, but `ship_computer.db` remains the authoritative store for application-level records, permissions, and workflow history.

### Full Explanation: How Spock Uses the Embedding LLM and Vector Database

The Spock application uses the embedding model and vector database as the semantic retrieval backbone of its RAG pipeline. The goal is to allow the generative LLM to answer questions using relevant, up-to-date, and permissioned context rather than relying only on its internal training knowledge.

#### 1. Query Understanding

When a user asks a question, Spock first normalizes the input. This may include:

*   Trimming whitespace
*   Detecting language or domain
*   Identifying entities
*   Classifying the request as **Ask AI** or **Deep Dive**
*   Applying user-specific context

This step helps determine how much retrieval is needed and which data sources should be consulted.

#### 2. Embedding Generation

The query, and sometimes candidate context chunks, are passed to the embedding model. The embedding model produces a vector for each text item.

A vector is a list of numbers, for example:

```text
[0.12, -0.45, 0.87, 0.03, ...]
```

The exact dimensions depend on the model, but the important property is that semantically similar texts produce vectors that are closer together in vector space.

#### 3. Vector Index Search

The query vector is sent to the vector database. The vector database compares it against stored vectors using a similarity metric.

Common similarity metrics include:

*   **Cosine similarity**: Measures the angle between vectors and is often used for text embeddings.
*   **Inner product**: Measures directional alignment and is common when vectors are normalized.
*   **Euclidean distance**: Measures straight-line distance between vectors.

The vector database returns the top matching records, such as document chunks, notes, logs, or metadata entries.

#### 4. Metadata Filtering

Raw semantic similarity is not always enough. Spock applies metadata filters to ensure that only appropriate records are returned.

Examples include:

*   Only documents the user is allowed to access
*   Only records from a specific time window
*   Only content from a specific data source
*   Only records associated with a particular project, ship, system, or role

This prevents the system from retrieving irrelevant or unauthorized content.

#### 5. Reranking and Selection

The initial vector search may return many candidates. Spock may then rerank them using:

*   Similarity score
*   Recency
*   Source authority
*   User role
*   Keyword overlap
*   Prior relevance
*   Structured matches from `ship_computer.db`

The best candidates are selected for prompt assembly.

#### 6. Prompt Assembly

Spock builds a prompt for the generative LLM that includes:

*   The user’s original question
*   Retrieved semantic context
*   Structured context from `ship_computer.db`
*   Citation identifiers
*   Instructions to answer only from the provided context when appropriate

This grounded prompt reduces hallucination and improves traceability.

#### 7. Response Generation

The generative LLM produces the final answer. For **Ask AI**, this is usually a concise response. For **Deep Dive**, the response may include:

*   A summary of findings
*   Supporting evidence
*   Conflicting information
*   Follow-up questions
*   Citations to source records

#### 8. Caching and Persistence

After the response is generated, Spock may store useful results in `ship_computer.db`, such as:

*   The final answer
*   The prompt used
*   Retrieved vector IDs
*   Citation metadata
*   Confidence or relevance scores
*   Audit information

This allows future requests to reuse context, improve consistency, and support audit or debugging.

### Integration with Spock Workflows

The vector database complements `ship_computer.db` by handling unstructured and semi-structured data, while SQLite manages relational and transactional records.

During an **Ask AI** request, the embedding pipeline quickly retrieves relevant context snippets, which are injected into the LLM prompt alongside cached or structured SQLite data. The result is a fast, grounded answer that combines semantic relevance with authoritative application state.

For **Deep Dive** inquiries, the system performs iterative vector searches, aggregates results across multiple semantic clusters, and cross-references findings with relational data in `ship_computer.db` to produce comprehensive, fact-grounded responses. This allows Spock to move beyond a single lookup and instead conduct a multi-step investigation.

The MCP adapter exposes vector search capabilities as structured tools, allowing external agents to trigger semantic queries, update embeddings, or manage index partitions directly through the protocol. This makes the embedding and vector database layer available not only to the Spock user interface, but also to automated agents and external systems that need controlled access to semantic retrieval.
## Database Architecture: ship_computer.db

The `ship_computer.db` file serves as the persistent data store for the Spock application. It leverages SQLite 3 as an embedded, serverless database engine. This component maintains application state, stores knowledge contexts, session metadata, and analysis logs utilized by AI agents. Because SQLite is file-based rather than a separate network service, all access occurs through local connections managed directly by the application or its adapter layer.

### Overview

Located within the application's designated data directory, `ship_computer.db` handles read/write operations for the Spock core. It interacts directly with the MCP adapter to provide context-aware responses during "Ask AI" and "Deep Dive" inquiries. The database should be accessed with robust connection handling: SQLite supports concurrent readers but serializes write operations. To prevent `SQLITE_BUSY` errors, transactions should remain short-lived, and connections should be closed promptly after use. Enabling Write-Ahead Logging (WAL) mode is strongly recommended to improve concurrency, reduce lock contention, and allow readers to proceed without blocking writers.

### Schema Structure

The database schema is organized into logical tables that support distinct interaction types:

*   **Knowledge Base**: Stores data used for retrieval-augmented generation (RAG). This includes text chunks, associated metadata (source, timestamp, category, confidence scores), and either precomputed embedding vectors or references to external vector storage.
*   **User Sessions**: Tracks active inquiry sessions, including timestamps, user identifiers, session status, conversation history, and contextual state required for multi-turn interactions.
*   **Analysis Logs**: Records the results of "Deep Dive" operations, capturing query complexity metrics, execution times, token usage, intermediate reasoning steps, and diagnostic information essential for performance monitoring and troubleshooting.

### Reference Schema

The following conceptual schema illustrates how the core tables may be organized. The exact column names and constraints may vary depending on the Spock implementation, but the logical structure should remain consistent.

```sql
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    source_name TEXT,
    category TEXT,
    content TEXT NOT NULL,
    token_count INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS user_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_message_at TEXT,
    context_json TEXT,
    token_usage_json TEXT
);

CREATE TABLE IF NOT EXISTS analysis_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    inquiry_type TEXT NOT NULL,
    query_text TEXT,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    duration_ms INTEGER,
    token_usage_json TEXT,
    reasoning_steps_json TEXT,
    result_summary TEXT,
    error_message TEXT,
    FOREIGN KEY (session_id) REFERENCES user_sessions(session_id)
);
```

If the application uses `sqlite-vec` or a similar vector extension, the embedding data may be stored in a separate virtual table or linked table:

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_vectors USING vec0(
    chunk_id INTEGER PRIMARY KEY,
    embedding FLOAT[384]
);
```

The vector dimension, such as `384`, must match the output dimension of the selected embedding model.

### Interaction with Spock Application

The database is accessed through a centralized connection manager within the `spock_mcp_adapter` or the broader application layer. Centralizing connections ensures consistent resource release, explicit transaction boundaries, and minimized locking issues during concurrent activity. The adapter abstracts raw SQL operations into structured data access methods, ensuring that schema changes or query optimizations do not require widespread refactoring across the application.

#### Ask AI Inquiries

For "Ask AI" requests, the system performs rapid, context-aware retrieval operations:

1.  **Query Parsing & Embedding**: The incoming user prompt is tokenized and passed to the embedding LLM, which converts it into a high-dimensional vector representation.
2.  **Vector Similarity Search**: The database queries the `Knowledge Base` table to identify relevant text chunks based on cosine similarity or dot product distance against the query vector. Metadata filters may be applied to scope results to specific domains or timeframes.
3.  **Context Assembly & Response Generation**: Retrieved chunks are ranked, truncated to fit context window limits, and injected into the prompt template. The primary LLM generates a response, which is returned through the MCP protocol. Session state is optionally updated to maintain conversation continuity and track token consumption.

#### Deep Dive Inquiries

For "Deep Dive" requests, the system executes complex, multi-step analytical workflows:

1.  **Cross-Table Correlation**: The database performs multi-table joins to correlate data across domains, such as linking user session history with analysis logs, system metrics, or external data sources. This enables the agent to trace decision paths and validate findings against historical patterns.
2.  **Aggregation & State Persistence**: SQL aggregations summarize historical data, calculate trends, and produce derived metrics. Intermediate results and final analysis outputs are persisted to the `Analysis Logs` and `User Sessions` tables, ensuring auditability and enabling incremental reasoning across multiple turns.
3.  **Transaction Management**: All write operations during a Deep Dive session are wrapped in explicit transactions. This ensures atomicity, allowing the system to roll back changes if the analysis fails, encounters validation errors, or exceeds resource thresholds. Read-heavy analytical queries are optimized to avoid holding write locks unnecessarily, preserving system responsiveness.

### Embedding LLM and Vector Database Integration

The Spock application relies on a tightly coupled architecture for semantic search: an embedding model for vectorization and SQLite as a lightweight, embedded vector database. When a document or knowledge artifact is ingested, it is chunked and passed through the embedding LLM (e.g., `text-embedding-3-small`, `nomic-embed-text`, or a local equivalent). The resulting vectors are stored directly in the `Knowledge Base` table using SQLite's `BLOB` or `REAL` array types, often accelerated by extensions like `sqlite-vec` or application-level vector libraries.

During inference, the same embedding model processes user queries to ensure vector space consistency. SQLite then performs approximate nearest neighbor (ANN) or exact nearest neighbor (NN) searches using distance metrics configured in the schema. This integrated approach eliminates the need for external vector databases like Pinecone, Weaviate, or Milvus, reducing infrastructure complexity, network latency, and operational overhead. By co-locating relational metadata and vector embeddings within a single file, Spock achieves low-latency retrieval, simplified backup procedures, and deterministic state management suitable for conversational AI workflows.

#### Embedding Model Responsibilities

The embedding model is responsible for converting natural language text into numerical vectors that represent semantic meaning. In Spock, this model is used in two critical phases:

*   **Ingestion**: Knowledge documents, help articles, system notes, or user-provided context are split into manageable chunks. Each chunk is converted into a vector and stored alongside its metadata.
*   **Query Time**: The user's "Ask AI" or "Deep Dive" prompt is converted into a vector using the same embedding model. This allows the system to compare the query vector against stored knowledge vectors and retrieve semantically relevant content.

Using the same embedding model for both ingestion and querying is essential. If different models are used, their vector spaces may not be compatible, causing poor retrieval quality or meaningless similarity scores.

#### Vector Storage and Search

SQLite does not provide a native vector data type in the core database engine. Therefore, Spock can store embeddings in one of several ways:

*   **BLOB Storage**: The vector is serialized into a binary blob and stored in a column. The application deserializes the vector and performs similarity calculations in Python or another host language.
*   **REAL Array Storage**: The vector is stored as a fixed-length sequence of `REAL` values. This is simpler to inspect but can be less efficient for large-scale search.
*   **sqlite-vec or Similar Extension**: A vector extension provides optimized storage and nearest-neighbor search directly inside SQLite. This is the preferred approach when the knowledge base grows beyond a few thousand chunks.

For small knowledge bases, exact nearest-neighbor search is acceptable. For larger collections, approximate nearest-neighbor search or hybrid search using full-text search plus vector similarity may improve performance and relevance.

#### Model Consistency and Versioning

Because embedding models can change over time, Spock should record the embedding model name, version, and vector dimension alongside each stored vector. This allows the application to detect when a model upgrade requires re-embedding the knowledge base. Without this metadata, the system may silently compare vectors from incompatible models, producing degraded retrieval results.

### Maintenance and Health

Regular maintenance is required to keep `ship_computer.db` performant and reliable. Recommended practices include:

*   **Enable WAL Mode**: Use `PRAGMA journal_mode=WAL;` to improve concurrent read/write behavior.
*   **Set Busy Timeout**: Use `PRAGMA busy_timeout=5000;` or a similar value to reduce transient `SQLITE_BUSY` errors.
*   **Monitor File Growth**: Track database size, especially if embeddings are stored locally.
*   **Vacuum and Analyze**: Periodically run `VACUUM` and `ANALYZE` to reclaim space and improve query planning.
*   **Validate Integrity**: Use `PRAGMA integrity_check;` during maintenance windows to detect corruption.
*   **Back Up the Database File**: Because SQLite is file-based, consistent backups can be performed by copying the database file while the application is idle or by using SQLite's online backup API.
## Database Maintenance

* **Vacuuming**: Schedule periodic `VACUUM` operations during low-activity windows to reclaim unused space from deleted or updated records. On large databases, this operation can be resource-intensive and should not run concurrently with critical write operations.
* **Backup Strategy**: Maintain regular backups of `ship_computer.db`. Use a consistent backup method, such as SQLite's Online Backup API or an application-provided export utility, rather than copying the file directly while the application is running, which risks data corruption or incomplete transactions.
* **Integrity Checks**: Periodically run integrity checks using `PRAGMA integrity_check` during maintenance windows to detect file corruption early and validate recovery procedures. Additionally, monitor `PRAGMA page_count` and `PRAGMA freelist_count` to track database growth, fragmentation, and storage efficiency over time.

## SQLite 3 `ship_computer.db`

`ship_computer.db` is the local SQLite 3 database used by the Spock application. It serves as the primary structured data store for application state, user data, conversation history, document metadata, retrieval results, and operational logs.

SQLite 3 is an embedded, file-based relational database engine. In the Spock application, it provides:

* **Local persistence**: Data is stored in a single database file, making deployment, backup, and recovery straightforward.
* **ACID behavior**: Transactions are atomic, consistent, isolated, and durable, which helps protect application state during writes.
* **Multi-reader, single-writer access**: Multiple readers can access the database concurrently, while writes are serialized to maintain consistency.
* **Low operational overhead**: SQLite does not require a separate database server process, which is useful for local or edge deployments.
* **Structured metadata storage**: It stores the canonical text, metadata, relationships, and audit information that support Ask AI and Deep Dive workflows.

The database is not intended to be the primary semantic search index. Semantic search is handled by the vector database, while `ship_computer.db` remains the source of truth for application data, document content, conversation history, and retrieval metadata.

### Responsibilities of `ship_computer.db`

`ship_computer.db` stores the data required for the Spock application to operate reliably and reproducibly. Typical responsibilities include:

* **Application metadata**: schema version, application settings, feature flags, and local configuration.
* **User and session data**: user profiles, preferences, permissions, and active session state.
* **Document management**: source documents, titles, authors, sources, hashes, timestamps, and content.
* **Chunk management**: text chunks derived from documents, chunk ordering, token counts, and metadata.
* **Conversation history**: Ask AI and Deep Dive sessions, messages, prompts, responses, and model metadata.
* **Retrieval tracking**: which chunks were retrieved for a query, their scores, ranks, and associated vector identifiers.
* **Feedback and evaluation**: user ratings, corrections, follow-up questions, and quality metrics.
* **Operational logs**: indexing events, embedding model changes, vector database synchronization events, and maintenance actions.

### Typical Data Model

The exact schema may vary by deployment, but a typical `ship_computer.db` design includes tables such as the following:

| Table | Purpose |
|---|---|
| `documents` | Stores source documents, titles, sources, hashes, and timestamps. |
| `chunks` | Stores text chunks derived from documents, including chunk order and metadata. |
| `conversations` | Stores Ask AI and Deep Dive session metadata. |
| `messages` | Stores user questions, assistant responses, model names, token usage, and latency. |
| `retrieval_results` | Stores retrieved chunks, similarity scores, ranks, and vector database identifiers. |
| `feedback` | Stores user ratings, corrections, and qualitative feedback. |
| `embedding_jobs` | Tracks embedding generation, model version, status, and completion time. |
| `vector_sync_log` | Tracks synchronization between SQLite and the vector database. |
| `settings` | Stores application-level and user-level configuration. |
| `audit_log` | Records significant application events for troubleshooting and compliance. |

This separation allows Spock to keep human-readable content and application state in SQLite while using the vector database for fast semantic similarity search.

## Interaction with Spock: Ask AI and Deep Dive

The Spock application uses `ship_computer.db` as the coordination layer for both Ask AI and Deep Dive inquiries. The vector database provides semantic retrieval, while SQLite provides durable context, history, and traceability.

### Ask AI Workflow

Ask AI is a direct question-and-answer workflow. A user submits a question, and Spock returns a concise, context-aware answer.

The typical Ask AI flow is:

1. **Receive the user question**  
   Spock receives the question from the user interface and validates the request.

2. **Create or load the conversation**  
   Spock checks whether the question belongs to an existing conversation or starts a new one. It stores the conversation and message metadata in `ship_computer.db`.

3. **Load relevant context**  
   Spock may retrieve recent messages, user preferences, document permissions, and prior retrieval results from SQLite to shape the prompt.

4. **Generate a query embedding**  
   Spock sends the question to the embedding model. The embedding model converts the question into a numerical vector that represents its semantic meaning.

5. **Search the vector database**  
   Spock queries the vector database for the most similar text chunks. The vector database returns candidate chunks along with similarity scores and metadata.

6. **Filter and rank results**  
   Spock applies metadata filters, permission checks, recency rules, and optional reranking to produce a final set of context chunks.

7. **Build the prompt**  
   Spock combines the user question, retrieved chunks, metadata, and system instructions into a prompt for the answer-generating model.

8. **Generate the answer**  
   The answer-generating model produces a response using the retrieved context.

9. **Store the result**  
   Spock writes the answer, retrieved chunks, scores, model metadata, token usage, and latency back to `ship_computer.db`.

10. **Return the answer**  
   Spock returns the answer to the user, optionally including citations or source references.

In this workflow, SQLite is responsible for durable application state, while the vector database is responsible for semantic retrieval.

### Deep Dive Workflow

Deep Dive is a more complex inquiry workflow. Instead of answering a single question directly, Spock performs iterative research, retrieves multiple sources, compares evidence, and synthesizes a more detailed response.

The typical Deep Dive flow is:

1. **Receive the research request**  
   The user submits a broad or complex question that requires deeper analysis.

2. **Create a Deep Dive session**  
   Spock creates a session record in `ship_computer.db` to track the research process.

3. **Decompose the question**  
   Spock breaks the request into subquestions, themes, or search intents. For example, a question about system reliability may be decomposed into failure modes, historical incidents, mitigation strategies, and operational recommendations.

4. **Generate embeddings for each subquery**  
   Each subquestion is converted into a vector using the embedding model.

5. **Perform multiple vector searches**  
   Spock queries the vector database for each subquery, retrieving candidate chunks from the knowledge base.

6. **Deduplicate and merge results**  
   Spock removes duplicate chunks, merges overlapping results, and ranks the combined evidence.

7. **Iterate as needed**  
   If the initial results are insufficient, Spock may generate follow-up subqueries, refine filters, or search for additional context.

8. **Synthesize the response**  
   Spock uses the answer-generating model to produce a structured Deep Dive response, such as a summary, comparison, timeline, or recommendation.

9. **Record the research trail**  
   Spock stores the subqueries, retrieved chunks, scores, intermediate reasoning, final answer, and citations in `ship_computer.db`.

10. **Present the result**  
   Spock returns the Deep Dive response to the user, with references to the supporting chunks and sources.

Deep Dive relies more heavily on SQLite because it must preserve the full research trail, including intermediate queries, retrieved evidence, and final synthesis.

## Embedding LLM and Vector Database

The Spock application uses an embedding model, sometimes referred to as an embedding LLM, together with a vector database to support semantic search.

### What the Embedding Model Does

The embedding model converts text into a numerical vector. Each vector represents the semantic meaning of the text in a high-dimensional space. Text with similar meaning produces vectors that are close together, while unrelated text produces vectors that are farther apart.

For example:

* A document chunk about “database backup procedures” and a user question about “how to back up the database” should produce similar vectors.
* A document chunk about “user authentication” and a question about “database backups” should produce less similar vectors.

The embedding model is typically a transformer-based encoder model. It is different from the answer-generating model:

* **Embedding model**: converts text into vectors for search and similarity comparison.
* **Answer-generating model**: uses retrieved context to produce natural-language responses.

Both models may be local or remote, depending on the deployment. If the embedding model is remote, the text being embedded may leave the local environment. If the model is local, embedding remains on-device.

### Why Spock Uses Embeddings

Spock uses embeddings because keyword search alone is not sufficient for natural-language questions. Embeddings allow Spock to understand semantic intent, synonyms, paraphrases, and related concepts.

For example, a user may ask:

* “How do I back up the database?”
* “What is the recommended backup process?”
* “Can you explain the database recovery procedure?”

These questions use different wording but have similar intent. Embeddings allow Spock to retrieve relevant chunks even when the exact keywords do not match.

### How Spock Uses the Embedding Model

Spock uses the embedding model in two main phases:

1. **Indexing phase**  
   When documents are added or updated, Spock splits them into chunks, sends each chunk to the embedding model, and stores the resulting vector in the vector database.

2. **Query phase**  
   When a user asks a question, Spock sends the question to the same embedding model and uses the resulting vector to search the vector database for similar chunks.

Using the same embedding model for indexing and querying is important. If the model changes, the vector space changes, and previously stored embeddings may no longer be compatible with new query embeddings. In that case, Spock should re-embed the indexed content.

### Vector Database Role

The vector database stores embeddings and supports fast similarity search. It is optimized for operations such as:

* Nearest-neighbor search
* Approximate nearest-neighbor search
* Cosine similarity, dot product, or Euclidean distance calculations
* Metadata filtering
* Batch upserts and deletions
* Index rebuilding

The vector database is not the primary store for document text or application state. Instead, it stores:

* The embedding vector
* A reference to the corresponding chunk or document
* Metadata used for filtering and ranking
* Indexing information required for fast search

SQLite remains the source of truth for the actual text, document metadata, conversation history, and retrieval logs.

### Indexing Pipeline

The indexing pipeline prepares content for semantic search.

1. **Ingest source content**  
   Spock receives documents, notes, logs, or other text sources.

2. **Normalize and store content**  
   Spock stores the canonical text and metadata in `ship_computer.db`.

3. **Chunk the content**  
   Spock splits the text into manageable chunks. Chunking balances context size, retrieval precision, and model input limits.

4. **Generate embeddings**  
   Spock sends each chunk to the embedding model and receives a vector.

5. **Store vector metadata**  
   Spock stores the vector in the vector database along with a reference to the chunk ID and relevant metadata.

6. **Record indexing state**  
   Spock records the embedding model name, version, dimension, timestamp, and status in `ship_computer.db`.

This pipeline allows Spock to keep the human-readable content in SQLite while using the vector database for efficient semantic retrieval.

### Query Pipeline

The query pipeline supports Ask AI and Deep Dive.

1. **Receive the user query**  
   Spock receives the question or research request.

2. **Prepare the query**  
   Spock may clean, expand, or decompose the query depending on the workflow.

3. **Embed the query**  
   Spock sends the query to the embedding model.

4. **Search the vector database**  
   Spock requests the most similar vectors from the vector database.

5. **Apply filters**  
   Spock filters results by permissions, document type, date range, source, or other metadata.

6. **Rerank results**  
   Spock may use a reranker or scoring heuristic to improve result quality.

7. **Assemble context**  
   Spock selects the best chunks and formats them for the answer-generating model.

8. **Generate the response**  
   Spock produces the final answer or Deep Dive synthesis.

9. **Persist the result**  
   Spock stores the query, retrieved chunks, scores, answer, and metadata in `ship_computer.db`.

### Consistency Between SQLite and the Vector Database

Because Spock uses two storage systems, it must keep them consistent.

* **SQLite is the source of truth** for document text, chunk text, metadata, conversations, and retrieval history.
* **The vector database is a search index** for embeddings and similarity lookup.

When content changes, Spock should:

* Update the canonical text in `ship_computer.db`.
* Update or delete the corresponding vector in the vector database.
* Record the synchronization event in `ship_computer.db`.
* Re-embed content if the embedding model changes.

If the vector database becomes unavailable, Spock can fall back to SQLite-based search, such as full-text search or exact matching, if available. This fallback may be less semantically accurate but can preserve basic functionality.

### Embedding Model Versioning

Embedding models should be versioned because different models produce different vector spaces.

Spock should track:

* Model name
* Model version
* Vector dimension
* Embedding timestamp
* Chunk ID
* Document ID
* Index status

If Spock upgrades the embedding model, it should rebuild the vector index or maintain separate indexes for different model versions. Mixing embeddings from incompatible models can reduce retrieval quality.

### Security and Privacy Considerations

Because `ship_computer.db` may contain sensitive application data, Spock should protect it with appropriate file permissions, encryption at rest, and controlled access.

If the embedding model or vector database is remote, Spock should clearly indicate which data is sent externally. If the deployment requires local-only processing, Spock should use local embedding models and a local vector database.

### Monitoring and Maintenance

Spock should monitor both SQLite and the vector database to maintain search quality and operational health.

Useful metrics include:

* `ship_computer.db` file size
* SQLite page count and freelist count
* Number of documents, chunks, and conversations
* Embedding job success and failure rates
* Vector database index size
* Query latency
* Retrieval hit rate
* User feedback scores
* Stale or orphaned vector records

Regular maintenance should include:

* Backups of `ship_computer.db`
* Integrity checks
* Vacuuming during low-activity windows
* Reindexing after embedding model changes
* Cleanup of orphaned vectors
* Validation of synchronization between SQLite and the vector database