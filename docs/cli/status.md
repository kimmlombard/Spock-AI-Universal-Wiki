# spock_status

Displays the current system status, including server health, resource usage, and readiness flags.

## Usage

```cmd
.venv\Scripts\python.exe -m spock_status
```

> **Note:** The command above calls the Python interpreter inside a Windows virtual environment directly, so activation is not required. If you activate the virtual environment first, run `python -m spock_status` instead. On Linux/macOS, use `./venv/bin/python -m spock_status`, or activate the environment with `source venv/bin/activate` and then run `python -m spock_status`.

## SQLite 3 `ship_computer.db` and Spock integration

`ship_computer.db` is the local SQLite 3 database used by the Spock application as the structured source of truth for operational state and inquiry metadata. It stores data that is deterministic, queryable, and suitable for relational access, such as:

- server health and readiness flags
- resource usage snapshots
- service status and dependency checks
- Ask AI request metadata
- Deep Dive investigation records
- evidence references, citations, and result summaries
- embedding metadata, such as chunk identifiers, source paths, timestamps, and vector store references

The database is not used to store large vector embeddings directly. Instead, it stores the relational context needed to explain, audit, and retrieve the data that the vector database returns.

### Ask AI interaction

When a user submits an Ask AI inquiry, Spock uses `ship_computer.db` to:

1. Validate that the system is ready to answer.
2. Load relevant status, configuration, and recent operational context.
3. Record the user question, timestamp, model version, and retrieval parameters.
4. Store the final answer, confidence indicators, and source references.
5. Provide citations that can be traced back to structured records in the database.

For Ask AI, the database provides the factual and operational context, while the vector database provides semantic similarity over unstructured text.

### Deep Dive interaction

Deep Dive inquiries are more investigative and may require multiple retrieval and reasoning steps. Spock uses `ship_computer.db` to:

- create a Deep Dive session record
- track each step of the investigation
- store structured queries and their results
- link vector search results to source documents and database records
- preserve intermediate findings, hypotheses, and evidence
- produce a final report with auditable references

This separation allows Deep Dive to combine precise SQL queries with semantic search. For example, Spock can query `ship_computer.db` for all failed readiness checks in the last hour, then use the vector database to find related logs, runbooks, or explanatory text that match the failure context.

## Embedding LLM and vector database usage

The Spock application uses an embedding LLM to convert text into numerical vectors. These vectors represent semantic meaning, allowing the application to find related content even when the wording differs from the user's question.

### Embedding process

1. Spock receives a user question or a document chunk.
2. The text is normalized and split into manageable chunks if necessary.
3. The embedding LLM converts each chunk into a vector.
4. The vector is stored in the vector database along with metadata, such as source, timestamp, chunk ID, and content type.
5. `ship_computer.db` stores the relational metadata needed to reference, audit, and display that content.

### Retrieval process

When Spock needs to answer an Ask AI or Deep Dive inquiry:

1. The user question is embedded using the same embedding LLM.
2. The vector database searches for the nearest vectors to the question vector.
3. Spock retrieves the associated text chunks and metadata.
4. Results are filtered, ranked, and combined with structured data from `ship_computer.db`.
5. The final context is passed to the language model that generates the response.

### Why both SQLite and a vector database are used

SQLite 3 provides exact, relational access to structured operational data. The vector database provides approximate semantic search over unstructured text. Together, they allow Spock to answer questions that require both precise status data and contextual understanding.

For example:

- **Ask AI:** "Why is the server not ready?" Spock queries `ship_computer.db` for readiness flags and resource usage, then searches the vector database for related logs or documentation.
- **Deep Dive:** "Investigate the recent readiness failures." Spock creates a session in `ship_computer.db`, retrieves structured failure records, searches semantically for possible causes, and stores the evidence trail for review.
## Module Reference

### Overview

The `spock_status` module provides a command-line interface (CLI) for monitoring system health and status. It is intended for development and operations environments, allowing teams to quickly assess the state of a server or application without performing detailed manual inspection.

The module can also serve as a source of operational context for the Spock application. When status metrics, service checks, or readiness signals are persisted or exposed through the Spock data layer, they can be used to support "Ask AI" and "Deep Dive" inquiries that require current or historical system state.

### Functionality

- **Server Health**: Verifies the operational status of critical running services, validates network connectivity, and monitors active system processes where available.
- **Resource Usage**: Reports real-time statistics for CPU load, memory consumption, and disk space availability. The exact metrics may vary by operating system and permissions.
- **Readiness Flags**: Returns boolean indicators or exit codes that indicate whether the system meets the criteria required for deployment, testing, or production use. Exit codes are useful for scripts, CI/CD pipelines, and automated monitoring tools.

### Technical Details

The module is implemented in Python and should be run from a virtual environment that contains its dependencies. It relies on system-level metrics and may require appropriate permissions to access certain resources, such as network sockets, process lists, or protected files. On Windows, Linux, and macOS, the available data can differ depending on user privileges and OS APIs.

### Prerequisites

- **Python Environment**: A compatible Python version must be installed in the virtual environment, along with any required third-party packages.
- **Permissions**: The user executing the module may need elevated privileges to read system logs, inspect processes, or access protected network interfaces.

### Database Architecture

The Spock application uses a SQLite 3 database file named `ship_computer.db` to persist data and manage state for advanced inquiry features. This section explains how the database supports "Ask AI" and "Deep Dive" inquiries, and how it can provide context for status-related reporting when applicable.

#### SQLite 3 Storage Layer

The `ship_computer.db` file serves as the local relational database engine for the Spock application. It is implemented using Python's built-in `sqlite3` library, so no external database server or additional installation step is required.

- **File-Based Persistence**: Unlike server-based databases such as PostgreSQL or MySQL, SQLite stores all data in a single disk file. This makes it well suited to portable applications and environments where network overhead should be minimized.
- **ACID Compliance**: Despite its lightweight design, the database follows ACID principles (Atomicity, Consistency, Isolation, Durability). This helps preserve data integrity even if the application crashes during a write operation.
- **Schema Management**: The application manages the schema for `ship_computer.db`. Required tables are created during initialization or when a feature first needs them, rather than requiring manual database setup.
- **Write-Ahead Logging (WAL)**: The application configures the database to operate in WAL mode where supported to optimize concurrent read/write operations. This helps ensure that status checks and AI query routing do not unnecessarily block each other, maintaining low latency during high-throughput periods.
- **Local Transaction Control**: SQLite transactions are managed by the application process. This allows Spock to group related writes, such as storing a user query, retrieved context, and generated response, into a single consistent operation.
- **Portability and Simplicity**: Because the database is file-based, it can be copied, backed up, or restored as part of the application data directory. This is useful for local development, edge deployments, and environments where a separate database service is not desired.

#### Ask AI and Deep Dive Integration

The database plays an important role in powering the intelligent features of the Spock application, specifically "Ask AI" and "Deep Dive". These features rely on structured data retrieval from `ship_computer.db`.

- **Ask AI Queries**: When a user initiates an "Ask AI" inquiry, the system parses natural-language requests into constrained SQL queries, query plans, or semantic retrieval requests. The database stores historical context, logs, metadata, and prior interactions needed to generate accurate responses. Frequently accessed tables are indexed to reduce latency for AI inference pipelines.
- **Deep Dive Inquiries**: For complex analytical tasks labeled as "Deep Dive", the application performs multi-table joins and aggregations within `ship_computer.db`. This enables detailed analysis of system logs, performance metrics, user activity, and status history without transferring large datasets to external servers. Results can be summarized or returned as structured data for display.
- **Data Isolation**: To maintain security and stability, database access is restricted to the application process. Direct modification by external scripts or users should be avoided; file permissions, OS-level controls, and parameterized queries help prevent unauthorized changes to the data store.
- **Context Persistence**: The database records the inputs, outputs, and intermediate context used by AI features. This supports auditability, debugging, response consistency, and the ability to reconstruct why a particular answer was generated.
- **Status Context**: When `spock_status` metrics are stored in `ship_computer.db`, Ask AI and Deep Dive can reference recent health checks, resource usage, service states, and readiness flags as part of their response context.

#### Schema Design and Query Routing

To support both conversational and analytical workloads, `ship_computer.db` utilizes a normalized schema with dedicated indexing strategies:

- **Core Tables**: The database maintains tables for `sessions`, `queries`, `responses`, `system_metrics`, and `context_logs`. Each record includes timestamps, user/session identifiers, and status flags to enable precise filtering.
- **Indexing Strategy**: Primary keys are indexed by SQLite's rowid mechanism. Foreign keys are not automatically indexed, so the application creates indexes on commonly joined columns. Additional B-tree indexes are applied to frequently filtered columns such as `query_type`, `status_code`, and `timestamp` to accelerate `WHERE` and `ORDER BY` clauses during Deep Dive aggregations.
- **Query Routing**: The application's query router evaluates incoming requests and directs them to the appropriate execution path. Simple status checks use lightweight `SELECT` statements with `LIMIT` clauses, while Deep Dive operations trigger batched reads and bounded result sets to prevent memory exhaustion.
- **Read-Only Enforcement**: AI and Deep Dive query paths should use read-only connections or transaction modes where possible. This reduces the risk of accidental writes during analytical operations.
- **Query Limits**: The application enforces timeouts, row limits, and resource caps on generated SQL to protect the local database and the host system from expensive or runaway queries.

#### Detailed Inquiry Data Flow

The following flow describes how `ship_computer.db` participates in Spock's inquiry features:

1. **Intake**: The user submits an "Ask AI" or "Deep Dive" request through the Spock interface.
2. **Session Tracking**: The application creates or updates a session record in `ship_computer.db`, capturing the user, timestamp, request type, and environment context.
3. **Intent Classification**: The request is classified as a simple status question, a conversational AI question, or a complex analytical Deep Dive request.
4. **Context Retrieval**: The application retrieves relevant structured data from `ship_computer.db`, such as recent metrics, prior queries, service states, or status flags.
5. **Semantic Retrieval**: If the request requires conceptual matching, the application also queries the vector database for relevant text chunks, logs, or documentation.
6. **Query Execution**: For Deep Dive requests, the application may generate constrained SQL, execute joins and aggregations, and apply limits to keep the operation safe and efficient.
7. **Response Generation**: The retrieved context is assembled into a prompt or structured report. An LLM or summarization engine may generate the final user-facing answer.
8. **Persistence**: The final response, retrieved context, query plan, and execution metadata are stored back into `ship_computer.db` for audit and future reference.

#### Operational Considerations

- **Backups**: Because `ship_computer.db` is a single file, it can be backed up using file-level copy, snapshot, or application-managed export mechanisms.
- **Migrations**: Schema changes should be applied through controlled migration steps to avoid corrupting existing inquiry history.
- **Retention**: Large tables such as `context_logs` and `system_metrics` may require retention policies to prevent unbounded growth.
- **Monitoring**: The application should track query latency, failed queries, database size, and WAL file growth to detect performance or storage issues.
- **Concurrency**: SQLite is best suited to single-writer workloads. The application should serialize writes and use short transactions to avoid lock contention.

### Embedding LLM and Vector Database Integration

While `ship_computer.db` handles structured relational data, the Spock application leverages an embedding LLM and a companion vector database to enable semantic understanding and context-aware retrieval. This hybrid architecture ensures that both precise data lookups and conceptual matching are supported.

#### Embedding Generation and Semantic Search

The embedding LLM, or embedding model, converts text into numerical vector representations. These vectors capture semantic meaning, allowing the application to find related content even when the exact wording differs from the user's question.

- **Text Normalization**: Before embedding, the application normalizes text by trimming whitespace, removing unnecessary markup, and standardizing timestamps or identifiers where appropriate.
- **Chunking**: Long documents, logs, or responses are split into smaller chunks. Each chunk is embedded separately so that retrieval can return the most relevant portion of a larger text source.
- **Embedding Generation**: The embedding model maps each chunk into a fixed-length vector. Similar concepts produce vectors that are closer together in vector space, while unrelated concepts produce vectors that are farther apart.
- **Semantic Search**: When a user asks a question, the application embeds the question and searches the vector database for the most similar stored chunks. Similarity is typically measured using cosine distance, dot product, or another vector distance metric.
- **Hybrid Search**: In addition to semantic search, the application may combine keyword search, metadata filters, and structured SQLite queries. This hybrid approach improves recall for technical terms, identifiers, and exact values that pure semantic search may miss.

#### Vector Database Storage and Retrieval

The vector database stores embeddings alongside metadata that describes the source and context of each vector.

- **Vector Records**: Each record contains an embedding vector, a unique identifier, a text chunk or reference, and metadata such as source type, timestamp, session ID, document ID, and content category.
- **Metadata Filtering**: The application can restrict vector searches to specific sessions, time ranges, document types, or status categories. This prevents irrelevant results from being returned.
- **Similarity Ranking**: The vector database returns the top-k most similar records based on the embedded query. The application can then rerank these results using recency, relevance score, source authority, or business rules.
- **Local or Embedded Deployment**: The vector database may be implemented as an embedded local store or a lightweight companion service. In either case, it is designed to work alongside `ship_computer.db` without requiring a large external infrastructure stack.
- **Indexing**: Vector indexes are used to accelerate similarity search. The application may rebuild or refresh indexes when new content is added or when the underlying text corpus changes significantly.

#### Hybrid Retrieval and Context Assembly

Spock combines structured and semantic retrieval to build a complete context for each inquiry.

- **Structured Retrieval**: `ship_computer.db` provides precise data such as metric values, query history, response records, status flags, and session metadata.
- **Semantic Retrieval**: The vector database provides conceptually related text, such as similar past questions, relevant log excerpts, documentation snippets, or explanatory notes.
- **Context Assembly**: The application merges these results into a bounded context window. It prioritizes the most relevant and recent items, removes duplicates, and enforces token or size limits before sending the context to the response generator.
- **Answer Grounding**: The final answer should be grounded in the retrieved context. If the context is insufficient, the application should indicate uncertainty rather than fabricating details.
- **Explainability**: Because both structured and semantic sources are recorded, the application can explain which data contributed to a response, improving debugging and user trust.

#### End-to-End Inquiry Flow

The following flow describes how the embedding LLM and vector database work with `ship_computer.db`:

1. **User Request**: The user submits an "Ask AI" or "Deep Dive" question.
2. **Query Embedding**: The application converts the user's question into an embedding vector.
3. **Vector Search**: The vector database returns the most semantically similar stored chunks.
4. **Structured Search**: The application queries `ship_computer.db` for relevant sessions, metrics, logs, responses, or status records.
5. **Result Fusion**: The application combines vector search results with structured database results, applying filters, rankings, and deduplication.
6. **Context Construction**: The application builds a concise context package that includes the most relevant facts, examples, and historical references.
7. **Response Generation**: An LLM or summarization engine uses the context to generate a natural-language answer or structured report.
8. **Result Storage**: The final answer, retrieved context, vector search metadata, and database query results are stored for audit and future retrieval.

#### Caching, Consistency, and Failure Handling

- **Embedding Cache**: Frequently used text chunks may have cached embeddings to reduce repeated model inference costs.
- **Vector Index Refresh**: New or updated content should be embedded and added to the vector index in a controlled manner to avoid serving stale or inconsistent results.
- **Database Consistency**: `ship_computer.db` remains the source of truth for structured records. The vector database is treated as a derived index that can be rebuilt if necessary.
- **Graceful Degradation**: If the vector database is unavailable, the application can fall back to structured SQLite queries and keyword search, though semantic matching will be reduced.
- **Timeouts and Limits**: Vector searches and embedding generation should have timeouts and result limits to prevent slow or expensive operations from blocking the user interface.

#### Security and Privacy

- **Data Minimization**: Only content necessary for inquiry support should be embedded and stored in the vector database.
- **Access Control**: Both `ship_computer.db` and the vector database should be protected by file permissions, application authentication, and OS-level controls.
- **Sensitive Data Handling**: Logs, prompts, and responses may contain sensitive information. The application should apply redaction, retention limits, and encryption where appropriate.
- **Audit Logging**: Access to inquiry context, vector search results, and generated responses should be logged to support accountability and troubleshooting.
- **Isolation**: AI retrieval paths should not expose raw database internals or vector store internals to end users. Only approved, summarized, or structured results should be returned.
- **Text-to-Vector Conversion**: The embedding LLM converts natural language inputs, system logs, and documentation snippets into high-dimensional dense vectors. These vectors capture semantic meaning rather than relying on exact keyword matches.
- **Dimensionality and Model Selection**: The application uses a lightweight, locally hosted embedding model optimized for technical and operational text. Vectors are typically 384 to 1536 dimensions, balancing accuracy with memory efficiency.
- **Similarity Scoring**: Retrieved vectors are scored using cosine similarity or dot product metrics. Thresholds are dynamically adjusted based on query confidence to filter out irrelevant context before passing data to the generative LLM.

#### Vector Database Architecture

- **Storage and Indexing**: The vector database stores embeddings alongside metadata pointers that link back to records in `ship_computer.db`. It utilizes Approximate Nearest Neighbor (ANN) indexing (e.g., HNSW or IVF) to enable sub-millisecond search times across millions of vectors.
- **Synchronization**: A background sync process ensures that new logs, metrics, and user queries are embedded and indexed incrementally. This prevents search latency from degrading during peak usage.
- **Hybrid Retrieval**: When a query arrives, the system performs a dual lookup: exact matches are pulled from SQLite, while semantic matches are retrieved from the vector store. Results are fused using a weighted ranking algorithm before context assembly.

#### Integration with Ask AI and Deep Dive Workflows

- **Ask AI Context Assembly**: For conversational inquiries, the embedding LLM first generates a query vector. The vector database retrieves the top-k semantically relevant documents or log entries. These are combined with relational metadata from `ship_computer.db` to construct a precise prompt context, reducing hallucination and improving response accuracy.
- **Deep Dive Analytical Enhancement**: During complex investigations, the vector store identifies conceptually related events that may not share explicit identifiers. For example, a spike in memory usage can be correlated with deployment logs or error traces that mention similar subsystems, even if they lack direct foreign key relationships.
- **Fallback and Caching**: If the embedding pipeline experiences latency or temporary unavailability, the application gracefully falls back to keyword-based SQLite queries. Frequently used vector results are cached in memory to minimize redundant embedding computations and database round trips.