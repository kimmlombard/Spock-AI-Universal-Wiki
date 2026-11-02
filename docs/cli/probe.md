# spock_probe

Health probe: verifies that all servers are running and that the readiness contract is satisfied. This module ensures system stability by confirming infrastructure health before accepting external traffic. It provides a deterministic signal to load balancers, orchestrators, or monitoring systems about whether the service should receive requests.

## Usage

```bat
.venv\Scripts\python.exe -m spock_probe
```

> **Note:** This command invokes the Python interpreter inside the `.venv` virtual environment directly. The virtual environment must exist and contain the required dependencies; activation is not required when using this explicit path. If you are not using a virtual environment, replace the path with the full path to your system's Python interpreter or activate your environment first.

## Module Reference

The `spock_probe` module performs automated health checks on server infrastructure. It verifies that all servers are running and that they satisfy the readiness contract: the ability to accept requests, process them correctly, and access required dependencies without errors. This makes it suitable as a gatekeeper for load balancers and orchestration systems such as Kubernetes.

### Key Concepts

- **Readiness Contract**: A set of operational criteria beyond simple uptime. A server must be alive, initialized, configured correctly, connected to required resources, and capable of handling incoming traffic without errors. The probe validates service state, configuration availability, and dependency health before reporting the application as ready for load.
- **Liveness vs. Readiness**: Liveness checks determine whether a process is running or responsive at a basic level. Readiness checks, which this module performs, determine whether the process is functionally prepared to serve traffic. A server can be live but not ready—for example, if its database connection has failed or required configuration has not loaded.

### Functionality

- **Server Status Check**: Verifies that all servers are up and running by checking connectivity (for example, TCP or HTTP reachability) and process health indicators such as exit codes, resource usage, or service state.
- **Readiness Contract Check**: Ensures that servers can handle requests safely. This includes validating configuration loading, confirming availability of downstream dependencies such as databases or caches, and verifying correct service states before marking the server as healthy.

# ship_computer_database

The `ship_computer.db` file serves as the central persistent storage layer for the Spock application. Built on SQLite 3, this lightweight relational database enables the application to maintain state, store inquiry results, and manage context for AI-driven interactions without requiring a complex backend infrastructure. This section describes the database architecture and its interaction with the `Ask AI` and `Deep Dive` inquiry modules.

## Database Architecture

The SQLite 3 instance is configured as a single-file database (`ship_computer.db`) located within the application's data directory. The schema is designed to support frequent read operations for AI responses while preserving write integrity for user inquiries, session history, and contextual data.

### Core Tables

- **`inquiries`**: Stores metadata for every `Ask AI` or `Deep Dive` request, including timestamps, query strings, status flags (for example, completed, processing, failed), and links to generated responses or related context.
- **`knowledge_base`**: Contains structured data retrieved from external sources that feeds into AI responses. This table allows the application to reference specific facts during `Deep Dive` sessions and maintain traceability for generated answers.
- **`sessions`**: Tracks active user sessions to preserve context across multiple inquiries within a single `Deep Dive` session, supporting continuity in multi-step reasoning tasks.

## SQLite 3 Implementation Details

SQLite 3 operates as a serverless, zero-configuration, ACID-compliant relational database engine. Within the Spock application, `ship_computer.db` leverages several SQLite 3-specific optimizations to ensure reliability and performance:

- **Write-Ahead Logging (WAL) Mode**: The database is initialized in WAL mode to allow concurrent read operations while writes are occurring. This prevents read locks during AI response generation or session updates, which is critical for maintaining low latency during active inquiries.
- **Schema Enforcement & Indexing**: The application enables SQLite's foreign-key enforcement so that primary keys and foreign keys are strictly enforced to maintain referential integrity between `inquiries`, `sessions`, and `knowledge_base`. B-tree indexes are applied to frequently queried columns (such as `session_id`, `status`, and `timestamp`) to accelerate retrieval operations.
- **Transaction Management**: All write operations are wrapped in explicit transactions. This ensures that partial failures (for example, network timeouts during external API calls) do not corrupt the database state. Rollback mechanisms automatically revert incomplete writes, preserving data consistency.
- **Storage & Portability**: As a single-file database, `ship_computer.db` simplifies deployment, backup, and migration. The file is stored in a dedicated data directory with restricted OS-level permissions to prevent unauthorized modifications.

## Detailed SQLite 3 `ship_computer.db` and Spock Interaction

The `ship_computer.db` database is the system of record for Spock's inquiry lifecycle. It stores the durable state needed to track user questions, preserve AI responses, maintain session continuity, and provide auditable context for both `Ask AI` and `Deep Dive` workflows.

### Ask AI Inquiry Flow

`Ask AI` is a direct inquiry mode in which the user submits a question and expects a generated response. SQLite 3 supports this workflow by recording the request, preserving the response, and maintaining the metadata needed for auditing, debugging, and context reuse.

1. **Request intake**: When a user submits an `Ask AI` question, the Spock application creates a new row in the `inquiries` table. This row captures the user query, timestamp, request mode, status, and any initial metadata.
2. **Context retrieval**: Before generating an answer, the application may query `knowledge_base` for structured facts and query the vector database for semantically relevant passages. SQLite provides the authoritative record of which knowledge items are available and which items have been previously used.
3. **Response generation**: The application sends the user query, retrieved context, and any session metadata to the language model. The model returns a natural-language answer.
4. **Persistence**: The application updates the `inquiries` row with the final status, generated response, model metadata, token usage, latency, and references to retrieved context. If the request fails, the row is updated with an error state and diagnostic details.
5. **Audit and replay**: Because the inquiry, response, and context references are stored in SQLite, operators can inspect past `Ask AI` interactions, reproduce prompts, and verify that the application behaved consistently.

### Deep Dive Inquiry Flow

`Deep Dive` is a longer, multi-step inquiry mode in which the application maintains a working context across several related questions. SQLite 3 is the system of record for session continuity and intermediate results.

1. **Session creation**: At the start of a `Deep Dive`, the application creates a row in the `sessions` table. This row identifies the session, user, start time, and high-level objective.
2. **Step tracking**: Each follow-up question is stored as an `inquiries` row linked to the session. The application can therefore reconstruct the full sequence of questions, answers, and intermediate findings.
3. **Context accumulation**: As the session progresses, the application stores useful facts, citations, and intermediate conclusions in `knowledge_base` or related context tables. These records allow later steps to reference earlier evidence without relying solely on the language model's short-term context window.
4. **State transitions**: The session status can move through states such as `active`, `paused`, `completed`, or `failed`. SQLite transactions ensure that status changes and related inquiry updates are committed atomically.
5. **Continuity and recovery**: If the application restarts or a request is retried, the session and inquiry records in `ship_computer.db` allow the Spock application to resume the `Deep Dive` with the same context and avoid duplicating completed work.

## Embedding LLM and Vector Database Integration

The Spock application uses an embedding LLM and a vector database to support semantic retrieval. This allows the application to find relevant information based on meaning rather than exact keyword matches.

### Embedding LLM

An embedding LLM is a model that converts text into a numerical vector, also called an embedding. Each vector represents the semantic meaning of the text in a high-dimensional space. Similar texts produce vectors that are close together, while unrelated texts produce vectors that are farther apart.

In the Spock application, the embedding LLM is used to encode:

- **User queries**: The question submitted through `Ask AI` or `Deep Dive` is converted into a query vector.
- **Knowledge items**: Documents, passages, facts, and previously generated context are converted into content vectors.
- **Session context**: Optional summaries or intermediate findings may be embedded so that later steps can retrieve related material semantically.

The embedding model is separate from the generative language model. The embedding model does not produce natural-language answers; it produces numerical representations that can be compared efficiently.

### Vector Database

The vector database stores the embeddings produced by the embedding LLM and supports similarity search. When the Spock application receives a query, it embeds the query and asks the vector database to return the most similar stored vectors. The returned records typically include:

- The original text or passage.
- Metadata such as source, timestamp, session ID, or knowledge-base identifier.
- A similarity score or distance metric.

The vector database is responsible for fast approximate nearest-neighbor search. SQLite 3 is not used as the primary vector search engine because its B-tree indexes are optimized for exact relational queries, not high-dimensional similarity search.

### How the Components Work Together

The Spock application combines SQLite 3, the embedding LLM, and the vector database in a retrieval-augmented workflow:

1. **Indexing**: When new knowledge is added, the application stores the structured record in `ship_computer.db` and sends the text to the embedding LLM. The resulting vector is stored in the vector database with a reference to the SQLite record.
2. **Query embedding**: For an `Ask AI` or `Deep Dive` request, the application embeds the user query using the same embedding model used for indexing.
3. **Semantic search**: The vector database returns the most relevant passages or knowledge items based on vector similarity.
4. **Context assembly**: The application retrieves the full text and metadata for those items from SQLite 3, validates their status, and assembles a prompt for the generative language model.
5. **Answer generation**: The generative model produces the final answer using the retrieved context.
6. **Persistence**: The application records the inquiry, response, retrieved vector IDs, and any new session context in `ship_computer.db`.

### Division of Responsibilities

- **SQLite 3 (`ship_computer.db`)**: Stores authoritative relational data, inquiry history, session state, knowledge-base records, and references to vector items.
- **Embedding LLM**: Converts text into semantic vectors for both indexing and querying.
- **Vector database**: Stores vectors and performs fast similarity search to identify relevant context.
- **Generative language model**: Produces the final natural-language answer using the retrieved context.

This separation allows the Spock application to maintain reliable state in SQLite 3 while using the embedding LLM and vector database to improve the relevance and accuracy of AI responses.
## Inquiry Workflow: Ask AI and Deep Dive

The Spock application routes user requests through two distinct inquiry pathways. Both pathways rely on `ship_computer.db` for state management, auditability, and context preservation.

- **Ask AI**: Designed for quick, standalone questions. When a user submits a query, the application creates a new record in the `inquiries` table with a `processing` status. The query is passed to the AI pipeline, and upon completion, the response is stored alongside the original inquiry. The status is then updated to `completed`, and the record remains available for audit or caching purposes. No long-term session context is retained beyond the immediate request-response cycle.
- **Deep Dive**: Designed for complex, multi-turn investigations. When initiated, the application generates a unique `session_id` and inserts a corresponding row into the `sessions` table. Each subsequent follow-up question is linked to this session via a foreign key. The database maintains a chronological chain of inquiries, intermediate reasoning steps, and retrieved knowledge base entries. This allows the AI to reference prior context, avoid redundant searches, and maintain logical continuity across extended dialogues. Session records are periodically archived or purged based on configurable retention policies to manage database size.

### SQLite 3 `ship_computer.db` Interaction

`ship_computer.db` is the application’s local SQLite 3 database. It stores structured, transactional data that the Spock application needs to track user inquiries, preserve Deep Dive session state, and record the evidence used by the AI pipeline. The database is complementary to the vector database: SQLite provides reliable relational state, while the vector store provides semantic similarity search.

#### Primary Tables and Relationships

| Table | Purpose | Key Relationships |
|---|---|---|
| `sessions` | Stores Deep Dive session metadata, including creation time, last activity, and retention status. | `session_id` is the primary key. |
| `inquiries` | Stores each user question, whether it belongs to an Ask AI request or a Deep Dive session. | `inquiry_id` is the primary key. `session_id` is a nullable foreign key to `sessions`; it is populated for Deep Dive inquiries and left null for Ask AI inquiries. |
| `responses` | Stores AI-generated responses, model metadata, latency, token usage, and completion status. | `response_id` is the primary key. `inquiry_id` is a foreign key to `inquiries`. |
| `retrieved_context` | Stores the vector search results used for a given inquiry, including chunk identifiers, similarity scores, and source metadata. | `context_id` is the primary key. `inquiry_id` is a foreign key to `inquiries`. `chunk_id` references the corresponding vector store entry. |
| `reasoning_steps` | Stores intermediate pipeline steps, such as query rewriting, retrieval decisions, filtering logic, and response planning. | `step_id` is the primary key. `inquiry_id` is a foreign key to `inquiries`. |
| `embedding_cache` | Optionally stores locally cached embeddings or embedding references to reduce repeated calls to the embedding model. | `cache_id` is the primary key. Entries may reference `chunk_id`, `text_hash`, or vector store identifiers. |

The database is typically indexed on high-frequency lookup paths, such as:

- `inquiries(session_id, created_at)`
- `responses(inquiry_id)`
- `retrieved_context(inquiry_id, score)`
- `reasoning_steps(inquiry_id, created_at)`

These indexes support fast retrieval of session history, response auditing, and context reconstruction.

#### Ask AI Database Flow

For an Ask AI request, the Spock application uses `ship_computer.db` primarily as a request log and response store.

1. The application opens a SQLite connection and begins a transaction.
2. It inserts a new row into `inquiries` with a `processing` status.
3. If semantic retrieval is used, the application may store the retrieved vector chunks in `retrieved_context`.
4. The AI pipeline generates a response.
5. The application inserts the response into `responses`.
6. It updates the original `inquiries` row to `completed` and records completion metadata.
7. The transaction is committed.

If the pipeline fails, the application can update the inquiry status to `failed`, store an error message, and preserve enough context to diagnose the issue.

#### Deep Dive Database Flow

For a Deep Dive request, the database becomes the source of conversational continuity.

1. The application creates a new row in `sessions` and assigns a unique `session_id`.
2. Each user question is inserted into `inquiries` with the active `session_id`.
3. The application retrieves prior inquiries, responses, reasoning steps, and retrieved context for that session.
4. It uses that history to build a coherent prompt for the AI pipeline.
5. New retrieved chunks, reasoning steps, and responses are written back to the database.
6. The session’s `last_active_at` timestamp is updated.
7. Retention jobs later archive or purge sessions based on configured policies.

This design allows the Spock application to reconstruct the full investigative context for a Deep Dive session without relying on external session storage.

#### Transactional and Operational Behavior

Because `ship_computer.db` is a SQLite 3 database, the application should use short, well-scoped transactions to avoid writer contention. A typical pattern is:

- Use one transaction per inquiry lifecycle.
- Keep vector database calls outside the SQLite transaction when possible.
- Commit only after the response and supporting context have been successfully written.
- Use WAL mode if concurrent reads and writes are expected.
- Store enough metadata to make each inquiry reproducible or auditable.

This approach keeps the database reliable for state management while allowing the vector database to handle high-dimensional semantic search.

## Embedding LLM and Vector Database Integration

While SQLite 3 handles structured relational data, the Spock application utilizes an embedding model and a vector database to enable semantic search and contextual relevance matching. The integration follows a deterministic pipeline:

1. **Text Tokenization & Chunking**: Incoming user queries and retrieved knowledge base documents are preprocessed into manageable text chunks. This ensures that the embedding model receives inputs within its optimal token window, preserving semantic coherence.
2. **Embedding Generation**: The embedding model converts each text chunk into a high-dimensional vector, typically between 768 and 1536 dimensions. These vectors numerically represent the semantic meaning of the text, where similar concepts occupy closer positions in the vector space regardless of lexical differences.
3. **Vector Storage & Indexing**: Generated vectors are stored in a dedicated vector database or a SQLite-compatible vector extension. The vector store maintains an approximate nearest neighbor index, such as HNSW or IVF-PQ, enabling low-latency similarity searches across large collections of entries.
4. **Semantic Retrieval**: When a `Deep Dive` inquiry is processed, the application generates an embedding for the user’s current question and queries the vector database using cosine similarity or inner product distance. The top-k most relevant knowledge chunks are retrieved and injected into the AI’s context window.
5. **Hybrid Query Resolution**: The application combines vector search results with traditional SQLite relational queries. Structured filters, such as date ranges, source credibility, or session boundaries, are applied via SQL, while semantic relevance is determined by the vector store. This hybrid approach ensures both precision and contextual accuracy.
6. **Caching & Feedback Loop**: Frequently accessed embeddings and their corresponding vector IDs are cached in memory to reduce redundant model calls. User interactions and AI response quality metrics are logged back into `ship_computer.db`, enabling periodic retraining or index optimization to improve retrieval accuracy over time.

### How the Spock Application Uses the Embedding LLM and Vector DB

The Spock application uses the embedding model and vector database as a semantic retrieval layer. The embedding model is not the same as the response-generating LLM; it converts text into numerical vectors that can be compared by similarity. The vector database stores those vectors along with metadata, allowing the application to find conceptually relevant content even when the user’s wording differs from the source material.

#### Ingestion and Indexing

When knowledge base documents are added to the system, the Spock application performs the following steps:

1. It normalizes and chunks the document into semantically coherent passages.
2. It generates an embedding vector for each chunk.
3. It stores the vector in the vector database.
4. It stores associated metadata, such as source identifier, document title, date, credibility score, and chunk identifier.
5. It records the chunk reference in `ship_computer.db` so that retrieval results can be audited and linked to specific inquiries.

This separation allows the vector database to optimize similarity search while SQLite remains the system of record for application state and audit history.

#### Query-Time Retrieval

When a user submits a question, the Spock application uses the embedding model to convert the question into a vector. It then queries the vector database for the most similar stored chunks. The vector database returns candidate chunks ranked by similarity score.

The application may then apply additional filtering and ranking logic, such as:

- Restricting results to a specific source or document type.
- Prioritizing recent or high-credibility content.
- Excluding chunks already used in the current Deep Dive session.
- Reranking candidates using lexical overlap, metadata rules, or a secondary relevance model.

The final set of chunks is injected into the prompt context for the response-generating LLM.

#### Ask AI vs Deep Dive Retrieval

The two inquiry pathways use the embedding and vector database differently.

- **Ask AI** treats each question as independent. The application embeds the current question, retrieves the most relevant chunks, and generates a response without relying on prior conversational state.
- **Deep Dive** treats the question as part of an ongoing investigation. The application embeds the current question, retrieves relevant chunks, and also consults prior session context from `ship_computer.db`. This allows the system to refine the query, avoid repeating previously retrieved material, and maintain continuity across multiple turns.

#### Hybrid SQLite and Vector Search

The Spock application does not rely on vector search alone. It combines semantic retrieval with structured database queries.

For example, the application may:

- Use the vector database to find chunks semantically related to “reactor containment failure.”
- Use SQLite to filter those chunks by date range, source credibility, or session scope.
- Use SQLite to determine whether a chunk has already been retrieved in the current Deep Dive session.
- Use SQLite to store the final ranked context for audit and reproducibility.

This hybrid model gives the application both semantic flexibility and operational control.

#### Caching, Feedback, and Optimization

To improve performance and accuracy, the Spock application maintains a feedback loop.

- Embeddings for frequently used text chunks are cached to avoid repeated model calls.
- Vector search results are logged in `ship_computer.db` with their similarity scores and inquiry context.
- Response quality signals, such as user corrections, follow-up questions, or explicit feedback, are stored for later analysis.
- Periodic jobs can use this data to tune chunking strategies, adjust similarity thresholds, rebuild indexes, or retrain retrieval components.

This allows the system to improve over time while preserving a clear audit trail of how each response was constructed.
## Interaction with Spock Application

The database is accessed from the Python backend through the standard `sqlite3` library or an ORM layer such as SQLAlchemy. The interaction model supports responsive, lightweight operations for health checks, inquiry tracking, and session persistence, while offloading heavier AI computations to dedicated processing pipelines.

### ship_computer.db Schema and Interaction Model

`ship_computer.db` is a SQLite 3 relational database that serves as the persistent state layer for the Spock application. It is optimized for low-latency reads and writes, handling metadata, audit trails, and session state rather than raw AI model weights or large binary payloads. The schema is structured around three core tables:

- **`inquiries`**: Stores metadata for every `Ask AI` request, including a unique identifier, user/session context, timestamp, query text, AI response payload, and processing status (`pending`, `processing`, `completed`, `failed`). Indexed on `status` and `created_at` for efficient filtering and health monitoring.
- **`sessions`**: Manages multi-turn `Deep Dive` interactions. Each record contains a session ID, initialization timestamp, current step index, and a `TEXT` field containing serialized JSON context state. Foreign keys link back to the originating user or system actor.
- **`knowledge_base`**: Acts as a structured cache for retrieved documents, embeddings metadata, and intermediate reasoning artifacts. It stores document IDs, source references, vector database identifiers, and relevance scores. Foreign keys tie entries to specific `inquiries` or `sessions` to maintain traceability.

SQLite 3 is configured with `WAL` (Write-Ahead Logging) mode to allow concurrent reads during writes, and `PRAGMA journal_mode=WAL` is enforced at startup. Indexes are applied to foreign keys and frequently queried columns to prevent full-table scans. The application interacts with `ship_computer.db` using parameterized queries to prevent SQL injection, and all state mutations are wrapped in explicit transactions to guarantee atomicity.

### Relationships and Data Flow

The tables in `ship_computer.db` are designed to preserve a clear audit trail for every AI interaction.

- An `inquiries` row represents a single `Ask AI` request and its lifecycle.
- A `sessions` row represents a multi-step `Deep Dive` interaction and its evolving context.
- A `knowledge_base` row represents a retrieved or generated artifact that supports an inquiry or session.

In practice, the database records what happened, when it happened, and which retrieved evidence was used. The actual semantic search and vector similarity calculations are performed outside SQLite, typically in a dedicated vector database or in-memory ANN index. SQLite stores the resulting references, scores, and response metadata so that the Spock application can reconstruct, audit, and resume interactions reliably.

### Ask AI Inquiry Flow

1. **Ingestion**: When a user submits an `Ask AI` query, the application writes a record to the `inquiries` table with a status of `pending`. The record captures the raw prompt, metadata, and a unique tracking ID.
2. **Retrieval**: The system queries the `knowledge_base` to fetch relevant context needed to answer the prompt. Metadata filters and vector similarity scores are joined to surface the most semantically relevant documents.
3. **Completion**: Once the AI engine generates a response, the result is stored in the `response_payload` column, and the inquiry record is updated to `completed`. Processing duration and token metrics are logged for observability.

### Deep Dive Inquiry Flow

1. **Session Initialization**: A `Deep Dive` session creates a new entry in the `sessions` table, establishing a unique context identifier for the multi-step interaction. Initial parameters, depth limits, and user preferences are serialized and stored.
2. **Contextual Storage**: As the AI explores the topic, intermediate results, retrieved documents, and reasoning traces are appended to the `knowledge_base` or linked via foreign keys to the session ID. Each step updates the session's `current_step` and `state_snapshot` fields.
3. **State Persistence**: Unlike standard queries, `Deep Dive` sessions maintain state across multiple steps. The database uses explicit transactions so that if a step fails, incomplete updates can be rolled back, preserving data integrity for the current session. Checkpointing is performed at logical boundaries to enable recovery without reprocessing.

### Embedding LLM and Vector Database Integration

The Spock application relies on a dedicated embedding LLM and a vector database to power semantic retrieval for both `Ask AI` and `Deep Dive` workflows. The integration follows a decoupled pipeline:

- **Embedding Generation**: Incoming user queries and indexed knowledge documents are passed through a lightweight embedding model (e.g., `text-embedding-3-small` or an open-source equivalent). The model converts text into high-dimensional dense vectors that capture semantic meaning rather than lexical matching.
- **Vector Storage & Indexing**: Generated embeddings are stored in a vector database optimized for approximate nearest neighbor (ANN) search. The vector DB maintains an HNSW or IVF index to enable low-latency similarity lookups across large collections of vectors. Each vector record is linked to a metadata payload containing document IDs, source URLs, and chunk boundaries.
- **Similarity Search & Reranking**: During retrieval, the user's query is embedded in real-time and used to query the vector DB using cosine similarity or inner product distance. Top-k results are returned, optionally passed through a cross-encoder reranker to refine relevance before context injection.
- **Integration with Inquiry Flows**: The vector DB does not store conversational state; it strictly handles semantic lookup. Once relevant chunks are retrieved, their metadata and content are cached in `ship_computer.db`'s `knowledge_base` table for auditability. The AI completion engine then receives the original prompt augmented with the retrieved context, ensuring grounded, traceable responses.

### How the Spock Application Uses the Embedding LLM and Vector DB

The embedding LLM and vector database work together to convert natural-language questions into semantic searches over a knowledge corpus.

1. **Document Preparation**: Source documents are chunked into smaller passages suitable for retrieval. Each chunk is assigned metadata such as document ID, source reference, section, and creation timestamp.
2. **Embedding Indexing**: Each chunk is passed through the embedding LLM to produce a vector representation. These vectors are stored in the vector database alongside their metadata.
3. **Query Embedding**: When a user submits an `Ask AI` or `Deep Dive` prompt, the Spock application sends the prompt to the same embedding model used for indexing. This ensures that queries and documents exist in the same vector space.
4. **Semantic Retrieval**: The query vector is compared against the indexed document vectors using a similarity metric such as cosine similarity. The vector database returns the most relevant chunks.
5. **Context Assembly**: The retrieved chunks are ranked, filtered, and assembled into a context block. This context is appended to the user prompt before it is sent to the generative AI model.
6. **Response Grounding**: The generative model produces an answer using both the user prompt and the retrieved context. The resulting response is stored in `ship_computer.db`, along with references to the evidence used.

This separation allows the Spock application to keep semantic search fast and scalable while using SQLite for durable, transactional state management.

### Technical Considerations

- **Concurrency**: SQLite supports concurrent readers and a single writer. WAL mode improves read/write overlap, but the application should avoid long-running write transactions.
- **Security**: All SQL access should use parameterized queries. Sensitive prompt data should be encrypted at rest where required by policy.
- **Performance**: Frequently accessed columns should be indexed. Large response payloads should be stored efficiently, and heavy vector search work should remain outside SQLite.
- **Observability**: Inquiry status, processing duration, token usage, and retrieval scores should be logged to support debugging and performance monitoring.
- **Recovery**: `Deep Dive` sessions should checkpoint state at logical boundaries so that failed steps can be retried without corrupting prior session data.
- **Backup**: Because `ship_computer.db` contains operational state and audit data, it should be included in regular backup and restore procedures.
- **Connection Management**: The application uses context managers or equivalent connection handling to ensure each SQLite connection is opened, used, and closed within a single operation. This prevents resource leaks in long-running processes. Because SQLite supports one writer at a time, the application avoids connection pooling and instead creates short-lived connections per request or per thread. Each connection sets appropriate `busy_timeout`, `journal_mode`, and `synchronous` pragmas, and connections are not shared across threads unless explicitly configured for safe single-thread use.

- **Transaction Isolation**: Writes to `ship_computer.db` are performed inside transactions so that inquiry history, session state, and Deep Dive step state remain atomic. Read-heavy operations use `DEFERRED` transactions, allowing readers to proceed while a writer waits for locks. Batch state updates use `IMMEDIATE` transactions to acquire the write lock early and reduce lock contention. `EXCLUSIVE` transactions are reserved for rare maintenance operations that must prevent concurrent readers and writers.

- **Readiness Check Integration**: The `spock_probe` module verifies database connectivity as part of its readiness contract. If the connection to `ship_computer.db` fails, the server is marked as "Not Ready," preventing traffic routing until the dependency is restored. Health checks include file-system accessibility, WAL checkpoint status, schema version validation, and basic query execution against a known metadata table.

- **Storage & Maintenance**: Periodic `VACUUM` and `ANALYZE` operations are scheduled during low-traffic windows to reclaim fragmented space and refresh query planner statistics. Automated backups are performed using SQLite's online backup API to create consistent, zero-downtime snapshots without blocking normal application traffic.

## SQLite 3 `ship_computer.db` and Spock Interaction

`ship_computer.db` is the local SQLite 3 database that provides durable, transactional state for the Spock application. It is the system of record for inquiry metadata, session context, response history, Deep Dive execution state, citations, feedback, and maintenance information. It does not replace the vector database; instead, it stores the operational state needed to make Ask AI and Deep Dive requests reproducible, auditable, and resumable.

### Role in Ask AI

For an Ask AI inquiry, Spock uses `ship_computer.db` to:

- Create an inquiry record before calling external services.
- Store the user's question, session identifier, model version, prompt template, and request timestamp.
- Load prior conversation context, user preferences, and previous citations.
- Record the vector database query, retrieved chunk identifiers, and similarity scores.
- Store the final answer, token usage, latency, error state, and user feedback.
- Support replay, audit, and debugging by preserving the exact context used to generate the answer.

### Role in Deep Dive

For a Deep Dive inquiry, Spock uses `ship_computer.db` to persist a multi-step research workflow:

- Create a Deep Dive run with a unique identifier, objective, status, and owner.
- Store the generated research plan and each sub-question as individual steps.
- Record the vector database queries, retrieved evidence, intermediate summaries, and confidence signals for each step.
- Track step completion, retries, timeouts, and partial failures.
- Store the final synthesized report, citations, assumptions, and artifacts.
- Allow the run to be resumed after interruption by reading the last committed step state.

This design keeps long-running Deep Dive work durable even if the process restarts or a downstream service temporarily fails.

## Embedding LLM and Vector Database Integration

Spock uses an embedding LLM and a vector database to perform semantic retrieval for both Ask AI and Deep Dive inquiries. The embedding LLM converts text into dense numerical vectors, and the vector database stores those vectors alongside metadata so that Spock can find semantically relevant evidence quickly.

### Embedding LLM

The embedding LLM is a model that maps text chunks, user questions, and metadata into fixed-size vector representations. Spock uses it to:

- Embed document chunks before storing them in the vector database.
- Embed user questions at query time.
- Embed sub-questions and intermediate findings during Deep Dive execution.
- Compare semantic similarity between the user's intent and candidate evidence.

The embedding model version is recorded in `ship_computer.db` so that Spock can detect when embeddings need to be regenerated after a model upgrade.

### Vector Database

The vector database is the semantic search layer. It stores:

- Vector embeddings for document chunks, notes, reports, and other evidence.
- Metadata such as source identifier, document title, section, timestamp, classification, and Deep Dive run association.
- Indexes that support fast approximate nearest-neighbor search.

Spock uses the vector database to:

- Retrieve the most relevant chunks for an Ask AI question.
- Gather evidence for each Deep Dive sub-question.
- Apply metadata filters to limit results to authorized or contextually relevant sources.
- Support hybrid retrieval by combining vector similarity with keyword or structured filters.

### Retrieval Flow

1. Spock receives an Ask AI or Deep Dive request.
2. Spock validates readiness and loads relevant context from `ship_computer.db`.
3. Spock sends the user question or sub-question to the embedding LLM.
4. The embedding LLM returns a query vector.
5. Spock queries the vector database for the nearest matching evidence vectors.
6. Spock applies metadata filters, reranks candidates, and selects the final context set.
7. Spock stores the retrieved identifiers and scores in `ship_computer.db`.
8. Spock passes the selected context to the answer-generation model.
9. Spock records the final response, citations, and execution metadata.

### Consistency and Failure Handling

`ship_computer.db` remains the authoritative store for inquiry state, while the vector database remains the authoritative store for embeddings and semantic search. If the vector database is unavailable, Spock can mark the request as degraded, fall back to previously stored context when appropriate, or return a readiness error depending on the operation. If the embedding LLM is unavailable, Spock cannot generate new query vectors and should avoid returning stale semantic results unless the operation explicitly permits cached retrieval.

This separation allows Spock to maintain durable request state in SQLite while using the vector database for high-performance semantic search.