# Database Architecture: `ship_computer.db`

This section describes the architecture of the primary data store for the Spock application. The database is implemented with SQLite 3 and stored as a local file named `ship_computer.db`. It provides persistent storage for session state, query history, knowledge-graph data, and user context used by the **Ask AI** and **Deep Dive** modules.

## Overview

`ship_computer.db` is initialized at application startup and remains available while the application runs. Unlike in-memory caches or temporary API responses, this database retains durable information that must survive restarts:

- **Session state:** Active and completed Ask AI and Deep Dive sessions.
- **Query history:** User inputs and model responses used to reconstruct conversation context.
- **Knowledge graph data:** Entities and relationships extracted during Deep Dive analysis.
- **User context:** Profile-specific preferences, including settings such as `WarpCore.theme`.

All database access is routed through a repository layer. This architectural pattern keeps SQL logic separate from application features, makes behavior easier to test, and reduces the risk of inconsistent writes or SQL injection vulnerabilities.

## Schema Design

The schema is optimized for local read-heavy workloads with periodic writes during session creation, response logging, and Deep Dive extraction. The core tables are:

| Table Name | Purpose | Primary Key | Notes |
|------------|---------|-------------|-------|
| `sessions` | Tracks Ask AI and Deep Dive sessions. | `session_id` | Stores timestamps, status, and the associated user profile. |
| `query_logs` | Maintains a history of text inputs and model responses. | `log_id` | Supports retrieval of recent interactions for context reconstruction. |
| `knowledge_graph` | Stores entities and relationships extracted during Deep Dive analysis. | `entity_id` | Enables relationship mapping across analyzed topics. |
| `user_context` | Persists user-specific configuration for AI inquiries. | `profile_id` | Linked to the settings store for theme and preference management, including `WarpCore.theme`. |

The tables are intentionally simple so that common operations—creating a session, appending a query log entry, reading recent context, and persisting extracted entities—remain fast and easy to reason about. Indexes are applied to foreign keys and frequently queried columns, such as `session_id`, `profile_id`, and `timestamp`, to ensure fast lookups during active conversations.

## Interaction with Spock Application

The Spock application interacts with `ship_computer.db` through a dedicated repository layer that abstracts raw SQL queries. This prevents API endpoints or UI components from accessing the database directly, improving security, maintainability, and testability.

### Ask AI Integration

When a user submits an inquiry through the **Ask AI** module, the following data flow occurs:

1. **Session Initialization:** The application checks for an active session tied to the current profile. If none exists, the repository inserts a new record into `sessions` with a unique `session_id`, timestamp, and initial status (`active`).
2. **Context Assembly:** The repository queries `user_context` for profile-specific preferences and fetches the most recent `N` entries from `query_logs` scoped to the current `session_id`. This historical data is serialized into a structured prompt template.
3. **Inference and Logging:** The assembled prompt is sent to the LLM. Upon receiving a response, the repository inserts both the user query and the model response into `query_logs` within a single transaction, preserving chronological order and token usage metadata.
4. **State Synchronization:** The UI updates in real time via WebSocket or polling, reflecting the new message while the database remains the source of truth for session continuity.

### Deep Dive Integration

The **Deep Dive** module performs more intensive, multi-step analysis:

1. **Graph Construction:** As the AI analyzes a topic, it extracts named entities, concepts, and semantic relationships. The repository batches these extractions and writes them to `knowledge_graph`, linking them to the parent `session_id`.
2. **Entity Persistence and Deduplication:** Before insertion, the repository checks for existing entities to prevent duplication. Relationships are stored as directed edges, enabling traversal and visualization across analyzed material.
3. **Context Reuse and Cross-Referencing:** Persisted graph data can be queried by Ask AI or other features when relevant context is needed. For example, if a user asks a follow-up question referencing a previously analyzed entity, the repository retrieves related graph nodes and injects them into the prompt context.
4. **Session Finalization:** Once analysis completes, the `sessions` record status updates to `completed`, and a summary index is generated for faster future retrieval.

## SQLite 3 Runtime Behavior

`ship_computer.db` is an embedded SQLite 3 database file, so it does not require a separate database server process. The Spock application opens the file through the repository layer and uses SQLite 3 for local, file-based persistence.

SQLite 3 is well suited to this use case because it supports concurrent readers and a single writer, which matches the Spock workload: many reads for context reconstruction and UI state, with writes during session creation, response logging, and Deep Dive extraction. The repository layer uses short transactions to keep writes consistent and to reduce the chance of lock contention.

The database file is the durable source of truth for relational data. In-memory caches, WebSocket state, and temporary prompt buffers may improve responsiveness, but they are not relied upon for persistence. If the application restarts, Spock can reconstruct the active conversation, user preferences, and Deep Dive graph from `ship_computer.db`.

## Embedding LLM and Vector Database

Spock uses an embedding LLM and a vector database to add semantic retrieval to the Ask AI and Deep Dive workflows. The embedding LLM is not the same model that generates final answers. Its role is to convert text into dense numeric vectors, also called embeddings, that represent meaning rather than exact keyword matches.

The vector database stores those embeddings together with metadata. It allows Spock to find semantically similar passages, entities, or concepts quickly. `ship_computer.db` remains the primary record store for sessions, query logs, user context, and knowledge-graph metadata, while the vector database acts as a retrieval accelerator for semantic search.

### Embedding LLM Responsibilities

The embedding LLM is used to create vector representations for:

- User questions submitted through Ask AI.
- Recent conversation turns used to preserve context.
- Source passages or documents analyzed during Deep Dive.
- Extracted entities, concepts, and relationship descriptions.
- Candidate summaries or evidence snippets that may be injected into a prompt.

Each embedding is associated with metadata such as `profile_id`, `session_id`, `entity_id`, source location, timestamp, and embedding model version. This metadata allows Spock to scope retrieval to the correct user, session, and analysis context.

### Vector Database Responsibilities

The vector database stores:

- The numeric embedding vector.
- The original text or a reference to the text.
- Metadata used for filtering and tracing.
- Similarity index structures that support fast nearest-neighbor search.

Spock typically uses cosine similarity or another vector similarity metric to rank candidate results. The vector database is not a replacement for `ship_computer.db`; it complements the relational store by enabling semantic matching across large amounts of text and extracted concepts.

### Ask AI Semantic Retrieval Flow

For an Ask AI inquiry, Spock uses the embedding LLM and vector database in the following way:

1. **Query Embedding:** The user's question, and optionally the most recent conversation turns, are sent to the embedding LLM to produce a query vector.
2. **Semantic Retrieval:** Spock searches the vector database for the most similar stored passages, entities, or Deep Dive artifacts. Results are filtered by the current `profile_id` and, when appropriate, the active `session_id`.
3. **Context Assembly:** The repository layer combines the retrieved semantic context with data from `ship_computer.db`, including recent `query_logs`, `user_context` preferences, and relevant `knowledge_graph` nodes.
4. **Prompt Construction:** The combined context is serialized into a structured prompt for the answer-generating LLM.
5. **Response Logging:** After the LLM responds, Spock logs the user query, model response, retrieved vector identifiers, and token usage metadata in `query_logs`. This allows future sessions to trace which semantic evidence influenced the answer.

This approach allows Ask AI to answer questions using both explicit conversation history and semantically related material that may not share exact keywords with the user's question.

### Deep Dive Semantic Analysis Flow

Deep Dive uses the embedding LLM and vector database to make multi-step analysis more coherent:

1. **Passage Chunking:** The input material is divided into meaningful chunks, such as paragraphs, sections, or extracted statements.
2. **Embedding Generation:** Each chunk, entity, and relationship description is converted into an embedding by the embedding LLM.
3. **Semantic Clustering:** Spock uses vector similarity to group related concepts, detect near-duplicate entities, and identify recurring themes.
4. **Relationship Enrichment:** Similarity scores help rank candidate relationships and suggest connections that may not be obvious from keyword matching alone.
5. **Graph Persistence:** The repository layer stores the resulting entities and relationships in `knowledge_graph`, while the vector database retains the embeddings and retrieval metadata.
6. **Cross-Session Reuse:** Future Ask AI or Deep Dive requests can retrieve related vectors and graph nodes, allowing Spock to build on previously analyzed material.

### Coordination Between SQLite and the Vector Store

The repository layer coordinates the two storage systems:

- `ship_computer.db` stores durable relational records, including session identifiers, query history, user preferences, and knowledge-graph edges.
- The vector database stores embeddings and similarity search indexes.
- Vector records reference relational identifiers such as `session_id`, `profile_id`, and `entity_id`, so Spock can trace semantic results back to the authoritative database records.
- If vector retrieval is unavailable, Spock can fall back to SQLite-based context reconstruction, recent query history, and keyword or graph-based lookup.

This separation keeps the relational database simple and reliable while giving Spock the semantic retrieval capability needed for natural-language Ask AI and Deep Dive experiences.
## Embedding LLM and Vector Database Integration

While `ship_computer.db` manages structured relational data, the Spock application leverages an embedding LLM and a vector database to enable semantic search and high-dimensional context retrieval. This integration supports Ask AI and Deep Dive inquiries by allowing Spock to retrieve relevant prior context based on meaning rather than exact keyword matches.

The integration operates as follows:

1. **Text Ingestion & Embedding:** When queries, responses, or extracted knowledge-graph entities are persisted to `ship_computer.db`, a background pipeline simultaneously passes the text through an embedding LLM, such as a sentence-transformer model. The model converts the text into a fixed-dimensional numerical vector that captures semantic meaning.
2. **Vector Storage:** These embeddings are stored in a dedicated vector database optimized for similarity search. Each vector record includes a metadata pointer linking back to the corresponding `log_id` or `entity_id` in `ship_computer.db`, ensuring relational integrity without storing large vector payloads inside the SQLite file.
3. **Semantic Retrieval:** When a user submits a new inquiry, the application generates an embedding for the prompt. The vector database performs a nearest-neighbor search, using cosine similarity or an approximate index such as HNSW, to identify historically relevant queries, responses, or knowledge entities that share semantic context.
4. **Context Fusion:** The repository layer merges the top-k vector search results with the chronological `query_logs` data. This hybrid approach combines temporal conversation history with semantic relevance, improving the LLM's accuracy and reducing hallucination.
5. **Resource Management:** Embedding generation and vector indexing are handled asynchronously to avoid blocking the main application thread. The vector database is periodically compacted, and stale embeddings are purged when the associated SQLite records are archived or deleted.

## SQLite 3 `ship_computer.db` and Spock Application Interaction

`ship_computer.db` is the local SQLite 3 database used by the Spock application to persist structured application state. It serves as the system of record for profile settings, conversation sessions, query history, extracted entities, and relationships. The vector database is a separate derived store used for semantic retrieval; it does not replace `ship_computer.db`, but it references records in it through metadata identifiers.

### Database Responsibilities

- **Profile context:** Stores active profile preferences, theme settings, and other user-specific configuration.
- **Session continuity:** Tracks conversation sessions so Ask AI and Deep Dive can maintain context across multiple turns.
- **Query logging:** Records user prompts, model responses, retrieval metadata, and timestamps for auditing and context assembly.
- **Knowledge extraction:** Persists entities and relationships extracted from conversations or documents, enabling structured reasoning in Deep Dive.
- **Retention and cleanup:** Provides a durable location for data that can be archived, deleted, or restored as a single file.

### Core Logical Schema

The database is organized around the following logical concepts:

| Table or Concept | Purpose | Key Relationships |
|---|---|---|
| `user_context` | Stores profile-specific settings such as theme, preferences, and workspace state. | Identified by profile identifier; read before prompt assembly. |
| `sessions` | Represents a conversation or Deep Dive session. | Belongs to a profile; contains ordered query logs. |
| `query_logs` | Stores individual Ask AI or Deep Dive prompts, responses, and retrieval metadata. | Belongs to a session; referenced by vector records through `log_id`. |
| `knowledge_entities` | Stores extracted entities such as people, systems, concepts, or artifacts. | Belongs to a profile or session; referenced by vector records through `entity_id`. |
| `entity_relations` | Stores relationships between entities, such as dependencies, ownership, or causal links. | Connects two or more `knowledge_entities` records. |
| `audit_events` | Optional table for lifecycle events such as archive, delete, or restore. | References affected profile, session, or entity records. |

This structure allows Spock to combine relational queries, such as "show the last five queries in this session," with semantic queries, such as "find prior context about the same system failure."

### Ask AI Interaction

Ask AI is the conversational inquiry path. Spock uses `ship_computer.db` to ground each response in the active profile's recent context and relevant historical context.

A typical Ask AI flow is:

1. **Resolve profile:** Spock identifies the active profile and loads profile-specific settings from `user_context`.
2. **Load session context:** The repository layer retrieves the current session and recent `query_logs` entries to preserve conversational continuity.
3. **Embed the prompt:** The user's question is converted into an embedding vector.
4. **Semantic search:** The vector database returns the most semantically similar prior queries, responses, or entities.
5. **Relational join:** Spock uses the returned `log_id` or `entity_id` values to fetch the full records from `ship_computer.db`.
6. **Prompt assembly:** The application combines profile context, recent conversation history, and semantically relevant records into the LLM prompt.
7. **Response persistence:** The model response, retrieval metadata, and any newly extracted entities are written back to `ship_computer.db` in a transaction.

This allows Ask AI to answer naturally while remaining anchored to stored application data.

### Deep Dive Interaction

Deep Dive is the analytical inquiry path. It typically requires broader context than a single conversational turn, including related entities, historical sessions, and structured relationships.

A typical Deep Dive flow is:

1. **Scope the inquiry:** Spock resolves the active profile and determines the relevant session, topic, or entity set.
2. **Retrieve structured context:** The repository layer queries `sessions`, `query_logs`, `knowledge_entities`, and `entity_relations` for directly related records.
3. **Retrieve semantic context:** The vector database searches for semantically related entities, responses, or prior Deep Dive findings.
4. **Expand the graph:** If entity relationships are available, Spock may traverse related entities to include dependencies, causes, or associated systems.
5. **Iterate if needed:** Deep Dive may perform multiple retrieval passes, using intermediate results to refine subsequent vector or relational queries.
6. **Persist findings:** New entities, relationships, intermediate conclusions, and the final response are stored in `ship_computer.db` so future inquiries can reuse them.

This makes Deep Dive more than a single prompt-response exchange; it is a context-building process that combines SQLite's relational integrity with the vector database's semantic reach.

## Data Persistence and Security

`ship_computer.db` is a local SQLite 3 file, which makes it suitable for lightweight deployment and simple backup. Because the database may contain user prompts, model responses, extracted entities, and profile preferences, access should be treated as sensitive:

- **Repository-only access:** Application code uses repository methods rather than ad hoc SQL strings from feature layers.
- **Profile-scoped reads:** Queries are constrained to the active profile where possible to reduce cross-profile exposure.
- **Minimal retention:** Only data needed for session continuity, auditing, or analysis is persisted.
- **Backup and restore:** The database file can be copied as a single artifact, but backups should respect the same access controls as the application itself.
- **Derived data protection:** The vector database should be protected with equivalent controls because embeddings and metadata can reveal sensitive information about prompts, responses, or entities.

## Profile Isolation

Profile isolation ensures that one user profile does not accidentally read or modify another profile's data. The `user_context` table stores profile-specific settings, such as `WarpCore.theme`, while session and query records are associated with the active profile.

In practice, this means:

- Repository methods receive an explicit profile identifier rather than relying on global state.
- Context retrieval is scoped to the current profile before prompts are assembled.
- Theme and preference changes update only the selected profile's context record.
- Vector search results are filtered or validated against the active profile before being used in a prompt.

## Transaction Management

SQLite 3 provides transactional guarantees for writes. The repository layer uses transactions to keep related operations atomic:

- **Commit:** A successful operation, such as creating a session and logging its first query, is committed as one unit of work.
- **Rollback:** If any step fails, the transaction is rolled back so partial records are not left behind.
- **Consistency:** Readers see either the complete previous state or the complete new state, reducing the chance of corrupted context data.

This approach is especially important for Ask AI and Deep Dive flows, where a single user action may update multiple tables. SQLite's Write-Ahead Logging (WAL) mode is enabled by default to allow concurrent reads during active writes, ensuring the UI remains responsive while the database persists new data.

## Connection Pooling

Connection pooling reduces the overhead of repeatedly opening and closing SQLite connections. In this application, pooling refers to an application-level connection manager that maintains a small, fixed set of reusable database connections rather than instantiating a new connection for every query. Because SQLite is file-based and relies on database-level locking, the pool size is configured conservatively:

- **Reuse:** Connections are returned to the pool immediately after each repository operation completes.
- **Thread Safety:** The application strictly adheres to SQLite's threading model. Connections are never shared across threads unless explicitly configured with thread-safe pragmas or mutex settings.
- **Concurrency Limits:** SQLite serializes write operations at the database level. Excessive concurrent connections increase lock contention without improving throughput, so the pool caps active connections to match the application's expected concurrency.

This approach maintains database responsiveness while preserving the simplicity and reliability of a local, embedded data store.
## Data Persistence and Security

### Profile Isolation

To protect user privacy and prevent data leakage between crew member profiles, all write operations are strictly scoped by a `profile_id` filter. This row-level scoping ensures that records created, updated, or deleted for one profile never intersect with another profile’s dataset. Profile-specific configurations, including theme preferences defined in the `WarpCore.theme` module, are also persisted here, guaranteeing that user settings survive application restarts and session timeouts.

### Transaction Management

All database interactions are wrapped in explicit SQLite transactions using `BEGIN`, `COMMIT`, and `ROLLBACK` directives. This enforces atomicity for multi-step operations: either all related changes are successfully committed, or the entire transaction is rolled back upon encountering an error. Consequently, partial writes during unexpected session failures or system interruptions cannot corrupt the knowledge graph, query logs, or user metadata.

### Connection Pooling

Within the persistence layer, connection pooling optimizes resource allocation during high-load scenarios. Instead of spawning a new SQLite connection for every repository call, the data access layer checks out available connections from the pool, executes the required operations, and returns them when idle. This minimizes connection overhead on the main application thread, prevents file descriptor exhaustion, and ensures database access remains controlled, predictable, and performant.

### Embedded SQLite Behavior

As an embedded database, `ship_computer.db` is a self-contained local file managed directly by the application process. It operates without a separate database server or daemon, which significantly reduces deployment complexity while delivering durable, ACID-compliant storage. The database file remains entirely under the application’s control, streamlining backup procedures, disaster recovery, and local data lifecycle management.

## ship_computer.db Architecture and Spock Interaction

The `ship_computer.db` file serves as the central relational store for the Spock application, housing user profiles, query histories, AI response caches, session states, and metadata required for both **Ask AI** and **Deep Dive** workflows. The database schema is normalized to support rapid read/write cycles while maintaining referential integrity across related entities.

**Ask AI Workflow:** When a user initiates an Ask AI request, Spock first queries `ship_computer.db` for cached responses or relevant context tied to the user’s `profile_id`. If a cache miss occurs, the application logs the incoming query, triggers the AI generation pipeline, and stores the resulting response alongside metadata such as timestamp, token usage, confidence score, and source references. Subsequent identical or highly similar queries retrieve the cached result directly from the database, reducing latency and minimizing redundant API calls.

**Deep Dive Workflow:** Deep Dive inquiries require iterative context expansion and multi-step reasoning. Spock leverages `ship_computer.db` to maintain a session-specific state machine that tracks conversation turns, intermediate research steps, retrieved documents, and user feedback. Each step in the Deep Dive process is recorded as a structured log entry, allowing the application to backtrack, refine prompts, or resume interrupted sessions seamlessly. The database also indexes citation metadata and source provenance, ensuring that every Deep Dive output can be audited and traced back to its original data points.

Both workflows rely on optimized indexing strategies, such as B-tree indexes on `profile_id`, `query_hash`, and `session_id`, to ensure fast lookups even as the database scales. Write-Ahead Logging (WAL) mode is enabled to allow concurrent reads during heavy write operations, further enhancing responsiveness without compromising data integrity.

### SQLite 3 Schema and Spock Interaction

`ship_computer.db` is a SQLite 3 database file that provides durable, transactional storage for the Spock application. It acts as the system of record for user-specific data, application state, AI interaction history, and provenance metadata. While the database is embedded and local, its schema is designed to support both simple single-turn Ask AI requests and complex multi-step Deep Dive sessions.

A typical `ship_computer.db` schema includes the following logical entities:

- **Profiles:** Stores user or crew member identity records, including `profile_id`, creation timestamps, and last activity metadata.
- **Profile Settings:** Persists user preferences such as theme selection, language settings, and feature toggles.
- **Queries:** Records each user-submitted question or prompt, including normalized text, query hash, profile association, and creation time.
- **Responses:** Stores generated AI answers, model identifiers, token usage, confidence scores, and response metadata.
- **Sessions:** Tracks long-running conversations or Deep Dive workflows, including session status, workflow type, and lifecycle timestamps.
- **Deep Dive Steps:** Captures each intermediate reasoning or research step within a Deep Dive session, enabling replay, debugging, and resumability.
- **Citations:** Stores source references, document identifiers, URLs, snippets, and ranking information associated with generated answers.
- **Embedding Metadata:** Records references to generated embeddings, embedding model versions, vector dimensions, and associated content identifiers.
- **Vector References:** If Spock uses an external vector database, this table stores the mapping between relational records and vector identifiers. If Spock uses a SQLite vector extension, vector data may be stored directly in `ship_computer.db`.

Spock interacts with `ship_computer.db` through a repository or data access layer that enforces profile scoping, transaction boundaries, and consistent query patterns. For Ask AI requests, the database is used to check for cached answers, log new queries, store generated responses, and preserve citation metadata. For Deep Dive requests, the database maintains the session state machine, records each reasoning step, stores intermediate retrieval results, and supports resumption after interruption.

### Detailed Ask AI and Deep Dive Interaction

For **Ask AI**, Spock follows a cache-first, retrieval-augmented pattern:

1. The user submits a question.
2. Spock normalizes the question and computes a stable query hash.
3. Spock checks `ship_computer.db` for an existing response associated with the same `profile_id`, query hash, model version, and context version.
4. If a cached response exists, Spock returns it immediately.
5. If no cached response exists, Spock embeds the query using the embedding LLM.
6. Spock performs a vector similarity search to retrieve semantically relevant context.
7. Spock applies structured SQL filters to enforce profile isolation, permissions, recency, and source validity.
8. Spock assembles a prompt using the retrieved context and sends it to the generation LLM.
9. Spock stores the query, response, citations, token usage, and confidence metadata in `ship_computer.db`.
10. Spock returns the answer to the user.

For **Deep Dive**, Spock uses a more stateful workflow:

1. Spock creates a new session record in `ship_computer.db`.
2. Spock decomposes the user’s request into research or reasoning steps.
3. Each step is persisted with its prompt, retrieved context, intermediate result, and status.
4. Spock embeds each subquery and retrieves relevant documents or knowledge items.
5. Spock records citations and source provenance for every step.
6. Spock may backtrack, refine prompts, or request additional context based on intermediate results.
7. When the workflow completes, Spock stores the final answer, final citations, and session summary.
8. If the session is interrupted, Spock can reload the session state and resume from the last committed step.

This design allows Spock to treat `ship_computer.db` as both a persistence layer and an audit trail. Every Ask AI answer and Deep Dive conclusion can be traced back to the queries, retrieved context, model versions, and user profile that produced it.

### Embedding LLM and Vector Database Integration

Spock uses an embedding LLM to convert natural language text into numerical vector representations. These vectors capture semantic meaning, allowing Spock to compare questions, documents, summaries, and retrieved context based on similarity rather than exact keyword matching.

The embedding LLM is used in several parts of the Spock pipeline:

- **Query Embedding:** When a user asks a question, Spock converts the question into a vector representation.
- **Document Embedding:** Relevant knowledge items, documents, notes, or source excerpts are embedded and stored in the vector database.
- **Context Retrieval:** Spock compares the query vector against stored vectors to find semantically related content.
- **Deep Dive Subqueries:** During Deep Dive, each intermediate question or research step is embedded to retrieve additional context.
- **Caching:** Spock may cache embeddings in `ship_computer.db` or the vector database to avoid repeated embedding API calls for identical content.

The vector database stores high-dimensional vectors and associated metadata. It supports approximate nearest neighbor search, allowing Spock to quickly identify the most relevant items from a large corpus. Depending on the deployment, the vector database may be a separate service or a SQLite vector extension. In either case, `ship_computer.db` remains the authoritative store for relational metadata, session state, user profiles, response history, and citation provenance.

Spock combines vector search with structured SQL queries to produce accurate and secure results. The vector database answers the question, “What content is semantically similar to this query?” while `ship_computer.db` answers the question, “Which content is allowed for this profile, session, and workflow?” This hybrid approach prevents cross-profile leakage, supports permission-aware retrieval, and enables Spock to generate grounded, auditable answers for both Ask AI and Deep Dive inquiries.
## Embedding LLM and Vector Database Workflow

The Spock application integrates an embedding LLM and a vector database to enable semantic understanding and context-aware retrieval. This pipeline operates alongside the relational `ship_computer.db` but synchronizes metadata and query results to maintain a unified, secure user experience.

**Embedding Generation:** When a user submits a query or uploads a document, the application routes the text through a dedicated embedding LLM. This model converts natural language into high-dimensional numerical vectors, called embeddings, that capture semantic meaning, syntax, and contextual relationships. Unlike traditional keyword-based search, embeddings allow Spock to understand intent, recognize synonyms, and identify conceptual similarities across disparate data sources.

**Vector Storage and Indexing:** The generated embeddings are stored in a specialized vector database optimized for approximate nearest neighbor (ANN) search. Each vector is paired with structured metadata, such as source document, profile association, timestamp, and content type, and indexed using efficient algorithms such as HNSW or IVF-PQ. This indexing structure enables rapid similarity searches across large datasets with minimal computational overhead and predictable latency.

**Retrieval-Augmented Generation (RAG) Integration:** During both Ask AI and Deep Dive operations, Spock uses the vector database to perform semantic retrieval. The user’s query is embedded in real time, and the vector database returns the most contextually relevant documents, notes, or historical responses. These retrieved chunks are then injected into the LLM’s context window alongside the original prompt. This RAG architecture ensures that AI responses are grounded in verified, profile-specific data rather than relying solely on the model’s pre-trained knowledge, significantly reducing hallucination and improving factual accuracy.

**Synchronization with ship_computer.db:** While the vector database handles semantic search, `ship_computer.db` maintains the authoritative record of user interactions, access controls, and audit trails. After a vector search completes, Spock logs the retrieval metrics, filters results through the `profile_id` security layer, and caches the final synthesized response in the relational database. This dual-storage approach combines the speed and semantic power of vector search with the reliability, transactional safety, and strict access controls of SQLite.

### SQLite 3 `ship_computer.db` Integration

`ship_computer.db` is the SQLite 3 database that provides the relational foundation for Spock. It stores the authoritative metadata required to identify what data a user may access, how documents and chunks are related, what queries have been executed, and what responses were generated. The vector database is optimized for fast semantic similarity search, while `ship_computer.db` is optimized for structured records, transactions, permissions, and auditability.

**Core Responsibilities:**

- **Profile and identity context:** Stores user profiles, `profile_id` values, roles, and the scope of data each profile can access.
- **Document and chunk registry:** Tracks uploaded documents, extracted chunks, content hashes, source locations, timestamps, and the vector identifiers associated with each chunk.
- **Access control:** Enforces profile-level, role-level, and document-level permissions before and after retrieval.
- **Query lifecycle:** Records Ask AI and Deep Dive requests, parameters, retrieval settings, and response metadata.
- **Audit and compliance:** Captures who accessed what, when, why, and what was returned, supporting traceability and review.
- **Caching and state:** Stores recent responses, intermediate Deep Dive state, citations, and reusable retrieval results to improve performance and consistency.

**Relationship to the Vector Database:**

The vector database stores the numerical embeddings and the ANN index used for similarity search. `ship_computer.db` stores the relational metadata that gives those vectors meaning and control. A typical relationship is:

| SQLite 3 `ship_computer.db` | Vector Database |
|---|---|
| `profile_id`, document ID, chunk ID, permissions, audit fields | Embedding vector, ANN index, similarity score |
| Authoritative record of what exists and who may access it | Fast retrieval of semantically similar content |
| Transactional updates, deletes, and access checks | Approximate nearest neighbor search |
| Query logs, response cache, and compliance data | Candidate chunk retrieval and ranking |

When Spock retrieves a candidate chunk from the vector database, it uses the chunk identifier or metadata pointer to validate the result against `ship_computer.db`. If the chunk is no longer authorized, has been deleted, or belongs to a different profile, Spock discards it before the LLM sees the content.

When documents are updated or deleted, Spock coordinates the change across both stores. The relational database is updated first to reflect the new authoritative state, and the corresponding vector entry is then removed, replaced, or marked invalid in the vector database. This prevents stale or unauthorized content from being returned during future Ask AI or Deep Dive requests.

### Ask AI and Deep Dive Interaction with `ship_computer.db`

**Ask AI Workflow:**

Ask AI is designed for direct, context-aware questions. The workflow is:

1. The user submits a question.
2. Spock resolves the user’s `profile_id` and validates the request.
3. `ship_computer.db` provides the allowed document scope, chunk metadata, and any cached or relevant prior context.
4. The query is sent to the embedding LLM and converted into a vector.
5. The vector database returns the most semantically similar chunks.
6. Spock filters those chunks against SQLite permissions, profile scope, and content validity.
7. The LLM generates an answer using the original question and the validated retrieved context.
8. Spock writes the query, retrieval metrics, response, citations, and audit events to `ship_computer.db`.

This keeps Ask AI fast while ensuring that the answer is grounded in data the user is permitted to access.

**Deep Dive Workflow:**

Deep Dive is designed for more complex, multi-step analysis. It may require broader retrieval, iterative refinement, cross-document comparison, and synthesis of a longer response. The workflow is:

1. The user submits a Deep Dive request.
2. Spock creates or resumes a Deep Dive session in `ship_computer.db`.
3. The application determines the initial retrieval scope, including relevant profiles, documents, notes, and historical responses.
4. The query is embedded, and the vector database returns candidate chunks.
5. Spock filters, ranks, and groups the candidates using SQLite metadata such as source, recency, importance, and permissions.
6. If the initial context is insufficient, Spock may issue follow-up embeddings or refined queries to retrieve additional related content.
7. The LLM synthesizes a detailed answer, report, or analysis using the accumulated context.
8. Spock stores the final response, intermediate retrieval steps, citations, and audit trail in `ship_computer.db`.

Deep Dive therefore uses the vector database for semantic discovery and SQLite for session continuity, permission enforcement, and traceable synthesis.

### Detailed Explanation of the Embedding LLM and Vector Database

**Embedding LLM Role:**

The embedding LLM is a specialized model that converts text into numerical vectors. Each vector represents the meaning of the text in a high-dimensional space. Texts with similar meaning are placed closer together, while unrelated texts are placed farther apart. This allows Spock to compare a user’s question with stored content using mathematical similarity rather than exact keyword matching.

For example, a query such as “What risks are associated with the current deployment?” can retrieve content that mentions “production rollout concerns,” “release safety issues,” or “operational exposure,” even if the exact words do not match.

**Vector Database Role:**

The vector database stores these embeddings and provides fast similarity search. Because Spock may need to search across many documents, notes, and historical responses, exact comparison of every vector would be too slow. The vector database uses ANN indexing, such as HNSW or IVF-PQ, to return the closest matches quickly while maintaining acceptable accuracy.

Each vector is associated with metadata that allows Spock to identify the source chunk, profile, document, timestamp, and content type. This metadata is essential for filtering, citation, and security enforcement.

**How Spock Uses the Pipeline:**

1. **Ingestion:** When content is added, Spock splits it into manageable chunks, stores chunk metadata in `ship_computer.db`, generates embeddings with the embedding LLM, and stores the vectors in the vector database.
2. **Query:** When a user asks a question, Spock embeds the query using the same embedding model used for stored content.
3. **Retrieval:** The vector database returns the most similar chunks based on vector distance or similarity score.
4. **Validation:** Spock validates each candidate against `ship_computer.db` to confirm that the user is authorized to view it.
5. **Generation:** The LLM receives the user’s question and the validated context, then produces an answer grounded in that context.
6. **Recording:** Spock records the request, retrieval results, response, and audit information in `ship_computer.db`.

**Why This Matters:**

This architecture gives Spock three important capabilities:

- **Semantic understanding:** The system can match meaning, not just keywords.
- **Context-aware retrieval:** Ask AI and Deep Dive can pull relevant content from the user’s authorized data.
- **Secure and auditable responses:** SQLite enforces permissions, preserves history, and provides a reliable record of what was accessed and returned.