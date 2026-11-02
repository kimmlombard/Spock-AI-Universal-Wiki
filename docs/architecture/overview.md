# Architecture Overview

Spock-Onboarding follows a modular, station-based architecture that separates user-facing interfaces from core infrastructure services. This separation improves maintainability and scalability while keeping presentation logic distinct from backend operations.

## High-Level Layout

```text
┌─────────────────────────────────────────────┐
│              Spock Menu / Shell             │
├───────────┬───────────┬──────────────┬──────┤
│ Navigation│Engineering│Long Range    │Science│
│ Station   │ Deck      │ Sensors      │Station│
├───────────┴───────────┴──────────────┴──────┤
│                 WarpCore                    │
│  (DB, Profiles, Settings, Secrets, Search)  │
├─────────────────────────────────────────────┤
│              Orchestrator                   │
└─────────────────────────────────────────────┘
```

### Reading the Diagram

The diagram represents a logical view of component responsibilities rather than a strict process map. The top layer contains the user-facing shell and functional stations. `WarpCore` provides shared services utilized across multiple components, while the `Orchestrator` coordinates application flow between the UI layer and core services.

## Module Categories

Module names follow two conventions: thematic *Star Trek* names for user-facing or coordination packages, and `spock_`-prefixed snake_case names for backend services, CLI tools, and adapters. The naming convention indicates category; the descriptions below define each package's technical responsibility.

### Star Trek-Named Packages (UI/Stations)
These packages use *Star Trek* naming to represent user-facing components or functional entry points. They are typically where users begin an interaction with the system.

- `Orchestrator` — Central coordinator managing the application lifecycle and data flow between UI layers and core services. It functions as a routing bridge rather than a direct user station.
- `NavigationStation` — Initialization wizard for first-time setup, configuration, and guided onboarding.
- `EngineeringDeck` — Maintenance and diagnostic tools for system health, troubleshooting, and operational validation.
- `LongRangeSensors` — External data capture and monitoring utilities for observing remote or upstream sources.
- `ScienceStation` — Interface for querying knowledge bases, executing research tasks, and reviewing retrieved information.
- `WarpCore` — Shared kernel utilities providing foundational services, including SQLite-backed database access, profile management, settings persistence, secrets handling, and search infrastructure.

### `spock_`-Prefixed Packages (Services)
These packages use a snake_case naming convention (`spock_`) to denote backend services, CLI tools, or adapters. They handle infrastructure tasks and may be invoked by users, scripts, or other components without requiring direct interaction.

- `spock_bringup` — Phase A bring-up CLI used during initial deployment to provision and initialize required system components.
- `spock_probe` — Health probe CLI that validates system readiness and contract compliance before normal operation.
- `spock_shell` — PyQt6 GUI shell providing the primary user interface; corresponds to "Spock Menu / Shell" in the layout.
- `spock_rag_adapter` — RAG (Retrieval-Augmented Generation) pipeline adapter that integrates external knowledge sources into retrieval and generation workflows.
- `spock_mcp_adapter` — MCP (Model Context Protocol) adapter enabling standardized communication with external tools, systems, or context providers.
- `spock_wiki_adapter` — Wiki crawler adapter that extracts, parses, and processes information from wiki-style documentation sources.
- `spock_onboarding` — Core onboarding logic containing reusable setup and configuration workflows accessible to UIs, CLIs, or automation scripts.
- `spock_live_monitor` — Continuous monitoring service that tracks the health and status of running servers or local dependencies.

## Data Flow

1. **Bootstrap** → PowerShell scripts configure the initial environment and install prerequisites.
2. **Bring-up** → `spock_bringup` provisions necessary resources and starts required servers or local services.
3. **Probe** → `spock_probe` verifies that the system meets the readiness contract.
4. **Monitor** → `spock_live_monitor` continuously observes the health and status of running servers or local services.
5. **Use** → Stations provide the user interface for interacting with LLMs, RAG systems, and knowledge bases.

#### Lifecycle vs Runtime Operations

It is important to distinguish between deployment lifecycle operations and runtime usage:

- **Lifecycle phases (1–4):** Steps 1 through 4 (`Bootstrap` through `Monitor`) are primarily administrative. They execute during installation, initial setup, or maintenance windows to ensure the system is healthy and compliant before user interaction.
- **Runtime phase (5):** Step 5 (`Use`) represents the active operational state where end-users engage with the application via the Stations to perform tasks such as research, diagnostics, or configuration changes.

Monitoring continues in the background during runtime, but its purpose remains health observation rather than direct task execution.


## `ship_computer.db` (SQLite 3) Architecture

The `ship_computer.db` file serves as the primary relational data store for the Spock application. Built on SQLite 3, it provides lightweight, serverless persistence for user sessions, configuration state, conversation history, and metadata required by the `WarpCore` and station modules.

It is important to distinguish `ship_computer.db` from the vector database. The SQLite database stores relational application state, audit records, user preferences, and workflow checkpoints. The vector database stores high-dimensional embeddings used for semantic search and retrieval. Together, they allow Spock to maintain durable user context while retrieving relevant knowledge for AI responses.

### Core Data Models

The database is structured around several key tables that support application state and AI interaction:

- **`profiles` & `settings`** — Stores user preferences, theme configurations, API endpoints, and security credentials. Sensitive values are stored as references or encrypted payloads managed by the secrets manager, not as plaintext.
- **`conversations`** — Logs session metadata, timestamps, active station context, and workflow mode for each user interaction.
- **`messages`** — Records individual prompt-response pairs, including role (`user`, `assistant`, `system`, or `tool`), content, token usage, and latency metrics.
- **`artifacts` & `references`** — Tracks retrieved documents, source URLs, chunk identifiers, and citation metadata generated during retrieval-augmented generation operations.
- **`cache`** — Stores frequently accessed embeddings, query results, rate-limit tokens, and intermediate retrieval payloads to reduce redundant API calls and improve response times.

#### Representative Schema

The following schema illustrates the core relational structure used by the Spock application. The exact column names may vary by implementation, but the relationships and responsibilities remain consistent.

```sql
CREATE TABLE profiles (
    profile_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    display_name TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE settings (
    setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id TEXT NOT NULL REFERENCES profiles(profile_id),
    key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    is_secret INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(profile_id, key)
);

CREATE TABLE conversations (
    conversation_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES profiles(profile_id),
    station TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('ask_ai', 'deep_dive')),
    status TEXT NOT NULL DEFAULT 'active',
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE messages (
    message_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,
    model TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    latency_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE artifacts (
    artifact_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
    message_id TEXT REFERENCES messages(message_id),
    source_type TEXT,
    source_uri TEXT,
    title TEXT,
    content_hash TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE references (
    reference_id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    chunk_id TEXT,
    citation TEXT,
    score REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE cache (
    cache_key TEXT PRIMARY KEY,
    cache_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    expires_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE deep_dive_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
    step_index INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    tool_name TEXT,
    tool_input_json TEXT,
    tool_output_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_messages_conversation_created
    ON messages(conversation_id, created_at);

CREATE INDEX idx_conversations_profile_updated
    ON conversations(profile_id, updated_at);

CREATE INDEX idx_artifacts_conversation
    ON artifacts(conversation_id);

CREATE INDEX idx_references_artifact
    ON references(artifact_id);

CREATE INDEX idx_cache_expires
    ON cache(expires_at);

CREATE INDEX idx_deep_dive_checkpoints_conversation
    ON deep_dive_checkpoints(conversation_id, step_index);
```

#### Relationship Model

The tables are organized around a user profile and a conversation lifecycle:

1. A **profile** represents a user or authenticated identity.
2. **Settings** are associated with a profile and store preferences such as model selection, temperature, safety filters, and API configuration.
3. A **conversation** represents a single user session or thread within a station, such as Science Station or Engineering Deck.
4. **Messages** belong to a conversation and preserve the ordered exchange between the user, assistant, system, and tools.
5. **Artifacts** represent retrieved or generated knowledge items, such as wiki pages, documents, tool outputs, or source records.
6. **References** link artifacts to specific chunks, citations, or source locations used in an AI response.
7. **Cache** entries are keyed by workflow-specific identifiers and may store embeddings, retrieval results, or rate-limit state.
8. **Deep Dive checkpoints** preserve intermediate reasoning state so long-running workflows can be resumed or audited.

### Interaction with "Ask AI" Inquiries

When a user submits a query through the Science Station or Engineering Deck, the `Orchestrator` routes the request to the LLM pipeline. Before generation, the system checks `ship_computer.db` for:

1. **Session Context** — Recent conversation history is retrieved to maintain continuity and enforce context window limits.
2. **User Preferences** — Model selection, temperature settings, safety filters, and system prompts are loaded from the `settings` table.
3. **Response Logging** — Upon completion, the prompt, generated response, and performance metrics are written to the `messages` table for auditability, analytics, and future reference.

#### Detailed Ask AI Data Flow

An "Ask AI" inquiry follows a short, deterministic workflow:

1. **Conversation Resolution**  
   The `Orchestrator` determines whether the request belongs to an existing conversation or requires a new one. If a new conversation is created, a record is inserted into the `conversations` table with the active station, workflow mode, and timestamp.

2. **Preference Loading**  
   The system loads the user's profile and settings. These settings may include the preferred LLM, retrieval depth, citation style, safety filters, and API endpoint configuration.

3. **Context Assembly**  
   Recent messages are retrieved from the `messages` table. The application trims or summarizes older context as needed to fit the model's context window while preserving the most relevant recent turns.

4. **Retrieval Preparation**  
   The user's prompt is prepared for semantic search. The embedding model converts the prompt into a vector, and the vector database returns the most relevant knowledge chunks.

5. **Artifact and Reference Persistence**  
   Retrieved chunks are recorded as `artifacts` and `references`. This allows the application to display citations, trace claims to sources, and audit which knowledge was used for the response.

6. **LLM Generation**  
   The assembled context, system prompt, retrieved knowledge, and user question are sent to the generative LLM. The model produces the assistant response.

7. **Response Persistence**  
   The assistant response is written to the `messages` table. Token usage, latency, model name, and error state are recorded when available.

8. **Cache Update**  
   If the query or retrieval result is likely to be reused, the application may store the embedding, retrieval payload, or rate-limit state in the `cache` table.

The final write is typically performed within a transaction so that the assistant message, its references, and related metadata are persisted together. This prevents partial states where a response exists but its citations or metrics are missing.

### Interaction with "Deep Dive" Inquiries

"Deep Dive" workflows require multi-step reasoning, extended context windows, and persistent state tracking. The database supports this by:

- **Checkpointing** — Saving intermediate reasoning steps, tool outputs, and branch decisions to prevent data loss during long-running queries.
- **Source Attribution** — Linking retrieved documents to specific `artifacts` records, enabling users to trace AI claims back to original sources.
- **State Restoration** — Allowing users to resume interrupted Deep Dive sessions by reloading the exact conversation state, tool execution history, and retrieval pointers from the database.

#### Detailed Deep Dive Data Flow

A "Deep Dive" inquiry is treated as a stateful workflow rather than a single prompt-response exchange.

1. **Workflow Initialization**  
   The `Orchestrator` creates or loads a conversation with `mode = 'deep_dive'`. The initial user goal, station context, and active profile are recorded.

2. **Planning**  
   The application may generate a reasoning plan, such as identifying subquestions, selecting knowledge domains, or determining which tools should be invoked. The plan can be stored as a message or checkpoint record.

3. **Iterative Retrieval**  
   For each reasoning step, the system embeds the current subquery and searches the vector database. Retrieved chunks are stored as `artifacts` and `references` so that every claim can later be traced to a source.

4. **Tool Execution**  
   If the workflow requires external tools, such as wiki lookup, code analysis, or station-specific data access, the tool input and output are recorded. This creates an auditable execution trail.

5. **Checkpointing**  
   After each significant step, the application writes a checkpoint to `deep_dive_checkpoints`. The checkpoint may include:
   - The current step index.
   - The reasoning state.
   - Tool names and inputs.
   - Tool outputs.
   - Retrieval pointers.
   - Intermediate conclusions.

6. **Synthesis**  
   Once sufficient evidence has been gathered, the LLM synthesizes the findings into a final response. The final response is written to `messages`.

7. **Resume Support**  
   If the workflow is interrupted, the application can reload the latest checkpoint and continue from the last completed step. This avoids repeating expensive retrieval or tool calls.

8. **Auditability**  
   Because each step is persisted, users and operators can inspect how the Deep Dive reached its conclusion, including which sources were consulted and which tools were executed.

### Query Optimization & Integrity

SQLite's ACID compliance ensures data consistency across concurrent station operations. Indexes are applied to `conversation_id`, `timestamp`, and `user_id` fields to accelerate retrieval. The `WarpCore` module handles connection management and transaction boundaries, reducing lock contention during high-frequency AI interactions.

#### Concurrency and Locking

SQLite is optimized for single-writer workloads. In the Spock application, this means that multiple stations may read from `ship_computer.db` concurrently, but writes are serialized to preserve integrity.

To improve concurrency, the application may use:

- **WAL mode** — Allows readers to continue while a writer is active, reducing read/write blocking.
- **Short transactions** — Keeps write locks held for as little time as possible.
- **Retry logic** — Handles transient `SQLITE_BUSY` errors by retrying with backoff.
- **Batched writes** — Groups related inserts, such as a message and its references, into a single transaction.

The `cache` table is designed for frequent reads and writes. Cache entries should include expiration metadata so stale embeddings, retrieval results, or rate-limit tokens can be removed or refreshed safely.

## Embedding LLM and Vector Database Integration

Spock leverages a dedicated embedding model and a vector database to power semantic search, context retrieval, and knowledge grounding. This architecture enables the application to understand natural language queries and match them against structured and unstructured knowledge bases.

The embedding model is not the same as the generative LLM. The embedding model converts text into numerical vectors. The generative LLM uses those retrieved vectors, along with the associated text chunks, to produce natural language responses.

### Embedding Generation Pipeline

When documents, wiki pages, or user prompts are ingested, the `spock_rag_adapter` and `spock_wiki_adapter` pass the text through a lightweight embedding LLM. The model converts raw text into high-dimensional numerical vectors that capture semantic meaning, syntax, and contextual relationships. These vectors are normalized and stored alongside metadata, including source, chunk ID, timestamp, and access permissions.

#### Embedding Model Contract

For retrieval to work correctly, the embedding model must satisfy a consistent contract:

- **Same model for indexing and querying** — The model used to embed knowledge base documents must also be used to embed user queries.
- **Stable vector dimensions** — The vector database must know the expected dimensionality of the model's output.
- **Normalization** — Vectors are typically normalized so that cosine similarity behaves predictably.
- **Deterministic behavior** — The same input text should produce the same or nearly the same vector under the same model version.
- **Versioning** — If the embedding model changes, the vector index may need to be rebuilt to avoid mixing incompatible vector spaces.

#### Chunking and Metadata

Large documents are split into smaller chunks before embedding. Chunking is important because:

- Smaller chunks produce more focused semantic representations.
- Retrieval can return precise passages rather than entire documents.
- Citations can point to specific sections of a source.
- Context windows can be filled with the most relevant text.

Each chunk is stored with metadata such as:

- Source identifier.
- Source URL or document path.
- Chunk index.
- Content hash.
- Timestamp.
- Access permissions.
- Confidence or relevance score, when available.

### Vector Database Architecture

The vector store operates as a specialized index optimized for similarity search. It supports:

- **Chunking & Indexing** — Large documents are split into manageable segments, each assigned a unique vector representation.
- **Distance Metrics** — Cosine similarity or Euclidean distance calculations determine how closely a query vector matches stored knowledge vectors.
- **Metadata Filtering** — Queries can be constrained by source type, confidence thresholds, or user access levels before similarity scoring occurs.

#### Index and Storage Model

The vector database stores two related pieces of information:

1. **Vector data** — The numerical embedding for each chunk.
2. **Payload data** — The original text chunk and associated metadata.

During retrieval, the vector database compares the query vector against stored vectors and returns the closest matches. The payload is then used to build the LLM context and generate citations.

The vector database may be local, embedded, or remote. In either case, it is separate from `ship_computer.db`. The SQLite database stores workflow state and audit records, while the vector database stores semantic search indexes.

### Similarity Search & Retrieval

During an AI interaction, the user's prompt is embedded using the same model that processed the knowledge base. The resulting query vector is passed to the vector database, which returns the top-k most relevant chunks. This retrieval step ensures that the LLM generates responses grounded in verified, up-to-date information rather than relying solely on pre-training data.

#### Retrieval Scoring

The vector database ranks chunks based on similarity. Common scoring approaches include:

- **Cosine similarity** — Measures the angle between vectors and is commonly used for normalized embeddings.
- **Euclidean distance** — Measures the straight-line distance between vectors.
- **Inner product** — Measures vector alignment and is often used with normalized embeddings.

The application may also apply post-retrieval filtering or reranking to improve result quality. For example, it may prioritize chunks from trusted sources, remove duplicates, or enforce access permissions before passing results to the LLM.

### Integration with Ask AI and Deep Dive Workflows

- **Ask AI** — For standard inquiries, the vector database performs a single-pass similarity search. Retrieved chunks are injected into the LLM's context window alongside system prompts, enabling fast, accurate answers with inline citations.
- **Deep Dive** — Complex queries trigger iterative retrieval. The system performs multiple vector searches across different knowledge domains, aggregates results, and uses the LLM to synthesize findings. Intermediate retrieval states are cached in `ship_computer.db` to avoid redundant vector lookups and maintain reasoning continuity.

#### Ask AI Retrieval Pattern

For "Ask AI" inquiries, retrieval is optimized for speed and relevance:

1. The user prompt is embedded.
2. The vector database returns the top-k most relevant chunks.
3. Chunks are filtered by permissions and source trust.
4. Retrieved text is inserted into the LLM prompt.
5. The LLM generates a response.
6. Citations are derived from the retrieved chunks.
7. The response, citations, and metrics are persisted in `ship_computer.db`.

This pattern is suitable for direct questions where a single retrieval pass is sufficient.

#### Deep Dive Retrieval Pattern

For "Deep Dive" inquiries, retrieval is iterative and stateful:

1. The initial query is decomposed into subquestions or reasoning steps.
2. Each subquestion is embedded and searched against the vector database.
3. Retrieved chunks are evaluated for relevance and completeness.
4. Additional searches may be issued if the evidence is insufficient.
5. Tool outputs and intermediate conclusions are checkpointed in `ship_computer.db`.
6. The LLM synthesizes the accumulated evidence into a final answer.
7. All sources, tool calls, and reasoning steps remain available for audit.

This pattern supports complex investigations where the application must gather evidence from multiple sources before producing a final response.

#### Caching and Consistency

The embedding pipeline and vector store are decoupled from the core LLM generation process, allowing independent scaling, model swapping, and knowledge base updates without disrupting active user sessions.

Caching is used to improve performance, but it must be managed carefully:

- **Embedding cache** — Avoids re-embedding identical text.
- **Retrieval cache** — Avoids repeated vector searches for the same query and knowledge base version.
- **Rate-limit cache** — Tracks API usage and prevents exceeding provider limits.
- **Checkpoint cache** — Preserves Deep Dive state for resumability.

Cache entries should include versioning or expiration metadata. If the embedding model, chunking strategy, or knowledge base changes, stale cache entries should be invalidated to prevent retrieval from outdated vector data.
## Database Architecture

### SQLite3 Implementation (`ship_computer.db`)
The `WarpCore` module relies on a single-file SQLite 3 database named `ship_computer.db` to manage persistent state for the Spock application. This architecture keeps all critical data—user profiles, system configurations, credential references, knowledge-base content, sensor telemetry, and search indices—localized to the host machine, eliminating the need for an external database server or networked data layer.

**Key Characteristics:**
- **Portability:** The entire database state is encapsulated within a single file, enabling straightforward backup, migration, and restoration using standard file system operations.
- **Concurrency & Performance:** SQLite is optimized for read-heavy workloads, supporting multiple concurrent readers while serializing write operations. This aligns with Spock's primary usage pattern of frequent knowledge-base queries and sensor-data retrieval. To maximize throughput, the database operates in Write-Ahead Logging (WAL) mode, which allows readers to proceed without blocking writers. For write-intensive operations, the application batches updates into short, explicit transactions and uses connection management to minimize lock contention.
- **Schema Management:** Table structures are programmatically managed by `WarpCore` utilities. Rather than relying on manual migration scripts, the application executes versioned schema updates at runtime. This allows new features—such as additional sensor telemetry tables or research log schemas—to be deployed seamlessly while preserving historical data integrity.

#### Core Data Model
The `ship_computer.db` database is organized around several logical domains that support both conversational AI responses and structured analytical queries.

- **Identity and Configuration:** Stores user profiles, station preferences, authentication references, and application settings.
- **Knowledge Base:** Stores document metadata, document chunks, source references, and content used by Ask AI.
- **Vector Search Support:** Stores embedding vectors and associated metadata for semantic retrieval.
- **Sensor and Operational Telemetry:** Stores time-series data such as warp core efficiency, power distribution, navigation state, and subsystem diagnostics.
- **Research and Audit Logs:** Stores user inquiries, generated responses, diagnostic requests, and system events for traceability.
- **Indexes and Caches:** Stores B-tree indexes, full-text search indexes, materialized views, and query caches used to accelerate repeated operations.

#### Storage and Indexing Strategy
Spock uses SQLite as both a relational store and a lightweight vector-enabled data layer.

- **B-tree indexes** are used for timestamp, component, user, and status filtering in Deep Dive queries.
- **Full-text search indexes**, such as SQLite FTS5, may be used for keyword-based retrieval and phrase matching.
- **Vector indexes**, such as those provided by `sqlite-vec` or an in-process vector index, are used for semantic similarity search in Ask AI.
- **Materialized views or cached aggregates** may be used for frequently requested analytics, such as rolling averages, threshold breaches, and subsystem summaries.

### Interaction with Ask AI and Deep Dive Inquiries
The database serves as the central memory layer for two distinct operational modes within the Spock application: **Ask AI** and **Deep Dive**. These modes leverage different subsets of `ship_computer.db` and distinct query strategies to deliver tailored responses to user inquiries.

#### Ask AI (Science Station)
- **Function:** Delivers immediate, context-aware answers to user questions regarding system status, external knowledge, or research queries.
- **Database Interaction:** The `ScienceStation` interfaces with the `WarpCore` search index and knowledge-base tables stored in `ship_computer.db`. When a user submits a query, such as *"What is the current warp core efficiency?"*, the application triggers a Retrieval-Augmented Generation (RAG) pipeline. The pipeline first performs a semantic similarity search against locally indexed content, retrieves the most relevant document chunks, and formats them as context for the language model.
- **Workflow:**
  1. User submits a natural language query via the `ScienceStation` interface.
  2. `WarpCore` converts the query into a vector embedding and executes a similarity search against the local index in `ship_computer.db`.
  3. Top-ranked results are extracted, deduplicated, and formatted into a structured context window.
  4. The context is passed to the generation layer, and the final synthesized response is returned to the user interface.

#### Deep Dive (Engineering & Navigation Stations)
- **Function:** Enables complex analytical queries, historical trend tracking, and diagnostic investigations into system logs, sensor history, and operational metrics.
- **Database Interaction:** The `EngineeringDeck` and `NavigationStation` execute structured SQL queries that perform aggregations, window functions, and multi-table joins across `ship_computer.db`. For example, analyzing long-range sensor telemetry requires querying the `sensor_logs` table with time-based filters, grouping by subsystem, and calculating statistical metrics such as moving averages, variance, or threshold breaches. These operations rely heavily on B-tree indexes and precomputed materialized views to maintain sub-second response times.
- **Workflow:**
  1. User initiates a diagnostic request, such as *"Show me warp core fluctuations over the last cycle."*
  2. `WarpCore` constructs and executes parameterized SQL queries against `ship_computer.db`, leveraging indexed columns for timestamp and component filtering.
  3. Aggregated results are serialized, visualized through station-specific dashboards, or exported for offline analysis.

#### Ask AI Data Flow in Detail
Ask AI is designed for natural-language interaction and semantic retrieval. The database supports this mode by storing both the source knowledge and the numerical representations used for similarity search.

1. **Query Intake:** The `ScienceStation` receives the user's question and normalizes it for processing.
2. **Embedding Generation:** The query text is passed to the embedding model, producing a vector representation of the question's meaning.
3. **Semantic Retrieval:** The vector is compared against stored embeddings in `ship_computer.db` to identify the most relevant knowledge chunks.
4. **Metadata Filtering:** Results may be filtered by source type, station context, time range, access level, or document status.
5. **Context Assembly:** The selected chunks are ordered, deduplicated, and formatted into a bounded context window suitable for the language model.
6. **Response Generation:** The language model uses the retrieved context to produce a grounded answer.
7. **Persistence:** The question, retrieved sources, generated answer, and confidence metadata may be stored for audit, feedback, or future retrieval.

#### Deep Dive Data Flow in Detail
Deep Dive is designed for structured analysis of operational data. The database supports this mode by storing time-series telemetry, event logs, and derived analytics in relational tables.

1. **Diagnostic Request:** The `EngineeringDeck` or `NavigationStation` receives a structured or semi-structured analytical request.
2. **Query Planning:** `WarpCore` determines the relevant tables, time range, subsystem filters, and aggregation requirements.
3. **SQL Execution:** Parameterized SQL queries are executed against `ship_computer.db`, using indexes to accelerate filtering and joins.
4. **Aggregation:** The database computes metrics such as averages, maxima, minima, variance, trend deltas, and threshold violations.
5. **Result Presentation:** Results are returned to the station interface for visualization, export, or further analysis.
6. **Caching:** Frequently requested aggregates may be cached or materialized to reduce repeated computation.

### Vector Database & Embedding LLM Integration
While `ship_computer.db` functions as a traditional relational store, Spock extends its capabilities by integrating vector search and embedding models directly into the data layer. This hybrid approach enables semantic understanding without requiring a separate vector database service.

**Embedding Generation:**
When new documents, sensor reports, or system logs are ingested, Spock passes the raw text through a lightweight embedding model, often described as an embedding LLM. More precisely, this is a text-embedding model that converts text into high-dimensional numerical vectors. These vectors capture semantic meaning rather than exact keyword matches. The resulting vectors are stored alongside the original metadata in `ship_computer.db`, typically as BLOBs, fixed-size binary vectors, or JSON-encoded arrays.

**Vector Indexing & Retrieval:**
To enable fast similarity searches, the application maintains a vector index within SQLite using extensions such as `sqlite-vec` or an in-process vector index. When a user submits an Ask AI query, the same embedding model processes the prompt to generate a query vector. The database then performs a cosine similarity or Euclidean distance calculation against the stored vectors, returning the top-k most semantically relevant chunks. Full-text search may also be used alongside vector search to improve recall for exact terms, identifiers, and technical phrases.

#### How Spock Uses the Embedding LLM
Spock uses the embedding model as the semantic bridge between natural language and database retrieval.

- **Ingestion:** When documents or logs are added, Spock splits the content into manageable chunks and generates an embedding vector for each chunk.
- **Query Encoding:** When a user asks a question, Spock encodes the question into a vector using the same embedding model used during ingestion.
- **Semantic Matching:** The query vector is compared against stored vectors to find content that is meaningfully related, even if the wording differs.
- **Consistency:** Using the same model for both ingestion and querying ensures that the vector space remains consistent.
- **Local Operation:** The embedding model can run locally, preserving the offline, single-file architecture of `ship_computer.db`.

#### How Spock Uses the Vector Database
Spock uses the vector database layer to perform semantic retrieval without requiring an external vector database service.

- **Storage:** Embedding vectors are stored in `ship_computer.db` alongside metadata such as document ID, chunk ID, source type, timestamp, and access level.
- **Indexing:** A vector index accelerates nearest-neighbor search over the stored embeddings.
- **Retrieval:** Ask AI queries are converted into vectors and matched against the index to retrieve relevant context.
- **Filtering:** Vector results can be constrained by metadata, allowing Spock to limit retrieval to specific stations, document types, or time ranges.
- **Hybrid Search:** Vector search may be combined with full-text search to balance semantic relevance with exact keyword matching.

#### Hybrid Search and Ranking
For Ask AI, Spock may use a hybrid retrieval strategy rather than relying solely on vector similarity.

- **Semantic Search:** Finds conceptually related content using embedding vectors.
- **Keyword Search:** Finds exact terms, identifiers, error codes, and technical phrases using full-text search.
- **Scoring and Ranking:** Results from both methods are combined, deduplicated, and ranked using relevance scores, recency, source authority, and station context.
- **Context Selection:** Only the highest-ranked chunks are included in the language model context to reduce noise and improve response quality.

#### Model and Index Versioning
Because embedding models can change over time, Spock tracks the model version used to generate each stored vector.

- **Version Tracking:** Each embedding record includes the model name, version, and dimensionality.
- **Re-embedding:** When a new embedding model is deployed, Spock can re-embed existing content to maintain compatibility.
- **Index Compatibility:** Vector indexes are rebuilt or migrated when the embedding dimensionality or model changes.
- **Fallback Behavior:** If a query vector is incompatible with the stored index, Spock can fall back to keyword search or prompt the user to rebuild the index.
**RAG Pipeline Integration:**  
The retrieved vector matches are not returned directly to the user. Instead, they are injected into the LLM's context window as grounding evidence. This ensures that generated responses are factually anchored to the ship's local data, reducing hallucination and maintaining operational accuracy. The embedding LLM and vector DB thus work in tandem: the embedding model translates natural language into searchable mathematical representations, while the vector index within `ship_computer.db` provides low-latency, semantically aware retrieval that powers the Spock application's intelligent query resolution.

## SQLite 3 `ship_computer.db` and Spock Application Interaction

`ship_computer.db` is the local SQLite 3 database that supports the Spock application's retrieval-augmented generation pipeline. It stores the structured data needed to answer user questions from the ship's local knowledge base, including document chunks, metadata, embedding vectors, and query history.

The database acts as the persistent memory layer for Spock. When a user submits an inquiry through **Ask AI** or **Deep Dive**, the Spock application does not rely solely on the LLM's internal knowledge. Instead, it first queries `ship_computer.db` to find relevant local evidence. That evidence is then used to ground the LLM's response.

### Role of `ship_computer.db`

The database typically contains the following types of information:

- **Text chunks**: Small, meaningful segments of source documents, logs, manuals, or operational records.
- **Metadata**: Information such as source file, document title, section, timestamp, author, classification, or operational context.
- **Embedding vectors**: Numerical representations of each text chunk, generated by the embedding LLM.
- **Similarity scores**: Calculated during retrieval to rank how closely a user query matches stored content.
- **Query and response records**: Optional audit data that records user questions, retrieved evidence, and generated answers.

By keeping this data in a local SQLite 3 file, Spock can operate with low latency, reduced network dependency, and strong control over which data is used to generate answers.

### Ask AI Inquiries

**Ask AI** is intended for direct, conversational questions. When a user asks a question, Spock performs the following steps:

1. **Query normalization**  
   The user's question is cleaned and prepared for embedding. This may include trimming whitespace, removing ambiguous phrasing, or extracting key terms.

2. **Query embedding**  
   The embedding LLM converts the question into a vector representation. This vector captures the semantic meaning of the question rather than relying only on keyword matching.

3. **Vector search**  
   Spock compares the query vector against the stored embedding vectors in `ship_computer.db`. The database returns the most semantically similar text chunks.

4. **Evidence ranking**  
   Retrieved chunks are ranked by similarity score. Spock may also apply filters based on metadata, such as document type, time range, or operational relevance.

5. **Context assembly**  
   The top-ranked chunks are formatted into a structured prompt. Each chunk is usually labeled with its source and relevance information so the LLM can cite or reference the evidence.

6. **LLM response generation**  
   The LLM receives the user question together with the retrieved evidence. It is instructed to answer using the provided context and to avoid inventing information that is not present in the local data.

7. **Response delivery**  
   The final answer is returned to the user, often with references to the underlying source material.

This workflow allows **Ask AI** to provide concise, context-aware answers while remaining grounded in the ship's local records.

### Deep Dive Inquiries

**Deep Dive** is designed for more complex, analytical, or multi-part questions. Unlike a simple Ask AI query, a Deep Dive request may require broader context, comparison across multiple sources, or step-by-step reasoning.

When a user initiates a Deep Dive inquiry, Spock may perform the following:

1. **Query decomposition**  
   The original question is broken into smaller sub-questions or search themes. For example, a question about system performance may be split into queries related to logs, maintenance records, configuration changes, and operational notes.

2. **Multiple retrieval passes**  
   Spock may run several vector searches against `ship_computer.db` to gather a wider set of relevant evidence. This helps ensure that the final answer is not limited to a single document or narrow context.

3. **Cross-source synthesis**  
   Retrieved chunks from different sources are compared and synthesized. Spock can identify contradictions, trends, recurring issues, or supporting evidence across the local data set.

4. **Structured reasoning**  
   The LLM is prompted to reason through the evidence in a structured way. It may summarize findings, list supporting references, identify gaps, and provide recommendations.

5. **Expanded response**  
   The final output is more detailed than a standard Ask AI response. It may include sections such as summary, evidence, analysis, limitations, and suggested next steps.

Deep Dive uses the same core RAG mechanism as Ask AI, but it applies it more extensively. The result is a more thorough, evidence-based analysis that remains anchored to the local data stored in `ship_computer.db`.

## How Spock Uses the Embedding LLM and Vector DB

The embedding LLM and vector DB are central to Spock's ability to understand natural language questions and retrieve relevant local information.

### Embedding LLM

The embedding LLM is responsible for converting text into numerical vectors. These vectors represent the semantic meaning of the text in a high-dimensional space.

For example, the phrases:

- "What is the current status of the navigation system?"
- "How is the nav system performing right now?"

may not share many exact keywords, but their embeddings will be close together because they express similar meaning.

Spock uses the embedding LLM in two main ways:

1. **During ingestion**  
   When documents or records are added to the local knowledge base, Spock splits them into chunks and generates an embedding vector for each chunk. These vectors are stored in `ship_computer.db`.

2. **During query time**  
   When a user asks a question, Spock generates an embedding vector for the question. This vector is then compared against the stored vectors to find the most relevant chunks.

Because both the stored content and the user query are represented in the same embedding space, Spock can perform semantic search rather than simple keyword matching.

### Vector DB

The vector DB is the retrieval layer that stores and searches embedding vectors. In this architecture, the vector index is maintained within `ship_computer.db`, allowing Spock to keep retrieval local, fast, and tightly coupled to the application's data.

The vector DB supports the following operations:

- **Vector storage**  
  Each text chunk is stored alongside its embedding vector and associated metadata.

- **Similarity search**  
  When a query vector is generated, Spock searches for stored vectors that are closest to the query vector. Similarity may be measured using cosine similarity, dot product, or another vector distance metric.

- **Ranked retrieval**  
  The database returns the most relevant chunks, usually ordered by similarity score.

- **Metadata filtering**  
  Spock can restrict retrieval to specific document types, time periods, sources, or operational categories before or after vector matching.

### Combined Workflow

The full workflow is as follows:

1. Source documents are processed and split into meaningful chunks.
2. The embedding LLM converts each chunk into a vector.
3. The vectors and metadata are stored in `ship_computer.db`.
4. A user submits an Ask AI or Deep Dive inquiry.
5. Spock converts the user's question into a query vector using the same embedding LLM.
6. The vector DB searches `ship_computer.db` for the most similar stored vectors.
7. The corresponding text chunks are retrieved and ranked.
8. The retrieved evidence is injected into the LLM's context window.
9. The LLM generates a grounded response based on the local evidence.
10. The response is returned to the user, optionally with source references.

This design allows Spock to combine the reasoning ability of an LLM with the precision of local semantic search. The embedding LLM provides meaning-based understanding, while the vector DB provides fast, structured retrieval from the ship's local data. Together, they enable Spock to answer questions accurately, reduce hallucination, and maintain operational relevance.
## Additional Explanation

### Understanding the `spock_`-Prefixed Packages
These packages encapsulate core backend services that support the functionality of the UI stations. Each `spock_`-prefixed package typically functions as a command-line interface (CLI), system adapter, or background daemon that bridges the application with external APIs, local file systems, or infrastructure components. These services are essential for initializing environments, monitoring system health, and maintaining operational continuity. They operate behind the scenes, exposing reusable capabilities and standardized interfaces rather than direct user-facing screens.

In practice, a `spock_` package may provide:

- **CLI commands** for setup, diagnostics, or maintenance tasks.
- **Service adapters** that normalize external API responses into internal data models.
- **Background workers** that monitor system state, refresh caches, or process queued jobs.
- **Shared utilities** for logging, configuration, authentication, or data transformation.

Because these packages are not primarily user-facing, they are designed to be invoked by other components, such as stations, the orchestrator, or scheduled tasks.

### Understanding the Star Trek-Named Packages
These packages are named after elements from the *Star Trek* universe and represent the user-facing components of the application. Each "station" provides a dedicated interface and workflow for interacting with specific functional domains, streamlining tasks such as system setup, diagnostics, real-time monitoring, and research. The station names map directly to their operational purpose: for example, the Science Station facilitates knowledge retrieval and Ask AI workflows, while the Engineering Deck and Navigation Station support deeper operational analysis, system diagnostics, and historical data review.

Stations are the primary surfaces where users interact with the application. They translate user intent into structured requests, coordinate with backend services, and present results in a domain-appropriate format. A station may render forms, dashboards, chat interfaces, diagnostic panels, or analytical reports depending on its purpose.

### Architectural Roles
The architecture distinguishes between **Presentation Layers** (Stations) and **Infrastructure Layers** (Services/Core).

- **Stations** serve as primary entry points for user interaction and domain-specific workflows. The `Orchestrator` is also categorized here; it acts as the central routing hub that coordinates traffic between UI stations and the underlying infrastructure (`WarpCore`). It manages request distribution, aggregates results from multiple backend services, and ensures consistent, structured responses are returned to the user.
- **Services** (prefixed with `spock_`) handle backend logic, external integrations, data transformation, and system health checks without exposing a primary user interface. They are invoked programmatically by stations or the orchestrator rather than accessed directly by end users.
- **WarpCore** functions as the shared kernel, providing persistent storage, configuration management, search indexing, and standardized data access patterns. All other layers depend on WarpCore for state management, query execution, and cross-component data sharing.

This separation allows the application to maintain a clear boundary between user experience, business logic, and data infrastructure. Stations remain focused on interaction, services remain focused on capability, and WarpCore remains focused on consistency, persistence, and shared state.

### Clarifying Terms
This section defines recurring terms used throughout the architecture description.

- **Station:** A user-facing component or workflow surface where users interact with a specific functional domain of the application.
- **Service:** A backend package that provides infrastructure, integration, monitoring, or operational capabilities without directly presenting a primary user interface.
- **WarpCore:** The shared core module responsible for persistent data access, configuration management, search indexing, and common runtime behavior used by all other components.
- **RAG Pipeline:** A retrieval-augmented generation workflow in which the system first retrieves relevant local content from an index, then supplies that evidence as context to a language model to generate accurate, grounded responses.
- **Deep Dive:** An analytical mode optimized for historical data exploration, trend analysis, system diagnostics, and complex multi-table relational queries rather than immediate conversational question answering.
- **Embedding Model:** A machine-learning model that converts text into numerical vectors, enabling semantic similarity search.
- **Vector Database:** A storage system optimized for storing and querying high-dimensional numerical vectors, typically used for semantic search and retrieval.
- **Generative LLM:** A large language model that produces natural-language responses, often using retrieved context to ground its output.

### SQLite 3 `ship_computer.db` Architecture and Data Flow
The `ship_computer.db` file is a serverless SQLite 3 database that serves as the relational backbone of the Spock application. Managed by `WarpCore`, it stores structured metadata, configuration states, query logs, document registries, and relational mappings that complement the unstructured data handled by the vector database. Its lightweight, file-based nature ensures zero-configuration deployment while maintaining ACID compliance for critical application state.

The database is intentionally separate from the vector database. SQLite 3 stores **structured, relational, and auditable data**, while the vector database stores **semantic representations of content**. This separation allows Spock to enforce governance, permissions, and analytical queries in SQLite 3 while performing high-dimensional semantic retrieval in the vector store.

#### Core Responsibilities of `ship_computer.db`
The `ship_computer.db` database is responsible for maintaining the application’s authoritative structured state. Typical responsibilities include:

- **Document Registry:** Tracking which documents exist, their identifiers, sources, versions, and lifecycle status.
- **Metadata Storage:** Storing classification tags, creation dates, ownership, sensitivity levels, and other searchable attributes.
- **Permission and Access Control:** Recording user roles, allowed scopes, and authorization rules that constrain which content can be retrieved.
- **Query Logging:** Capturing user requests, retrieval results, response metadata, and performance data for auditing and diagnostics.
- **Configuration State:** Storing application settings, feature flags, station preferences, and integration parameters.
- **System Event History:** Recording operational events, health checks, errors, and maintenance actions.
- **Relational Mappings:** Linking documents to users, projects, systems, tags, or other entities for analytical queries.

#### Typical Table Categories
While the exact schema may vary by deployment, `ship_computer.db` commonly contains table categories such as:

- **Documents:** Core records representing indexed content items.
- **Document Metadata:** Extended attributes associated with each document.
- **Users and Roles:** Identity and authorization information.
- **Permissions:** Access rules that constrain retrieval and query execution.
- **Query Logs:** Historical records of user requests and system responses.
- **System Events:** Operational and diagnostic events.
- **Configuration:** Application-level settings and runtime state.
- **Index Metadata:** Information about vector index versions, rebuild status, or synchronization state.

These tables provide the structured context needed to govern, audit, and analyze the semantic search system.

#### Interaction with Ask AI Inquiries
When a user submits an Ask AI query, the orchestrator first routes the request through `WarpCore`, which queries `ship_computer.db` to validate permissions, retrieve user-specific context, and fetch metadata filters (e.g., document source, creation date, or classification tags). The database does not store the raw text or embeddings; instead, it maintains a registry of document IDs and their associated metadata. This relational lookup ensures that only authorized and contextually relevant documents are passed to the vector search stage, preventing hallucination and enforcing data governance.

The Ask AI flow typically follows this sequence:

1. **User submits a natural-language question.**
2. **The station forwards the request to the Orchestrator.**
3. **The Orchestrator invokes WarpCore to resolve the request context.**
4. **WarpCore queries `ship_computer.db` to:**
   - Validate the user’s identity and permissions.
   - Determine which document collections are accessible.
   - Apply metadata filters such as tags, source, date range, or classification.
   - Retrieve the set of candidate document identifiers.
5. **The filtered document identifiers are used to constrain vector search.**
6. **The vector database returns semantically similar content.**
7. **The retrieved context is passed to the generative LLM.**
8. **The LLM produces a grounded response.**
9. **The response, along with metadata and citations, is returned to the station.**

In this model, SQLite 3 acts as the **governance and filtering layer**, while the vector database acts as the **semantic retrieval layer**. This ensures that Ask AI responses are not only semantically relevant but also authorized, auditable, and contextually constrained.

#### Interaction with Deep Dive Inquiries
Deep Dive workflows rely heavily on `ship_computer.db` for complex analytical operations. Unlike Ask AI, which prioritizes semantic similarity, Deep Dive executes parameterized SQL queries across multiple tables to aggregate historical metrics, track system events, or correlate logs with configuration changes. The database supports JOIN operations, window functions, and indexed lookups to efficiently process time-series data and relational dependencies. Results are formatted into structured datasets that stations render as charts, tables, or diagnostic reports. Because SQLite 3 handles these queries locally, Deep Dive operations maintain low latency and high throughput without requiring external database servers.

The Deep Dive flow typically follows this sequence:

1. **User selects an analytical task or diagnostic view.**
2. **The station constructs a structured query request.**
3. **The Orchestrator routes the request to WarpCore.**
4. **WarpCore translates the request into parameterized SQL.**
5. **SQLite 3 executes relational queries across multiple tables.**
6. **Results are aggregated, filtered, or transformed as needed.**
7. **The station renders the output as tables, charts, timelines, or diagnostic summaries.**

Deep Dive is best suited for questions that require precise relational logic, such as:

- “Show all system events from the last 30 days grouped by severity.”
- “List documents modified by a specific user within a date range.”
- “Correlate configuration changes with error events.”
- “Identify query patterns that produced the highest latency.”

Because these queries are deterministic and structured, SQLite 3 provides a reliable foundation for analytical workflows without requiring a separate database server.

#### Why SQLite 3 Is Used
SQLite 3 is well suited to the Spock application because it provides:

- **Zero-configuration deployment:** No separate database server is required.
- **File-based portability:** The database can be copied, backed up, or migrated easily.
- **ACID compliance:** Critical application state remains consistent even during concurrent access.
- **Low operational overhead:** Ideal for local, embedded, or edge deployments.
- **Strong relational querying:** Supports joins, indexes, transactions, and analytical SQL features.
- **Complementarity with vector search:** Structured data and semantic data can be managed separately while remaining coordinated through document identifiers.

### Embedding LLM and Vector Database Integration
The Spock application leverages a dedicated embedding model (often referred to as the embedding LLM) and a vector database to power semantic search and context retrieval. It is important to distinguish between the **embedding model**, which converts text into numerical vectors, and the **generative LLM**, which synthesizes final responses.

The embedding model does not generate natural-language answers. Instead, it transforms text into a numerical representation that captures semantic meaning. The vector database stores these numerical representations and enables efficient similarity search. The generative LLM uses the retrieved content as context to produce a coherent, grounded response.

#### Embedding Model Responsibilities
The embedding model is responsible for converting textual content into high-dimensional vectors. These vectors represent the semantic meaning of the text in a way that allows mathematically similar concepts to be close together in vector space.

Its primary responsibilities include:

- **Text Vectorization:** Converting documents, chunks, or query strings into numerical embeddings.
- **Semantic Representation:** Capturing meaning rather than exact keyword matches.
- **Consistency:** Producing embeddings that remain comparable across documents and queries.
- **Dimensionality:** Generating vectors of a fixed size suitable for the vector database.
- **Language and Domain Adaptation:** Supporting the languages and terminology used by the application.

For example, the phrases “system failure” and “critical error” may not share exact keywords, but their embeddings may be close enough to be retrieved as semantically related.

#### Vector Database Responsibilities
The vector database is responsible for storing embeddings and performing fast similarity searches. It is optimized for high-dimensional numerical data and typically supports distance metrics such as cosine similarity, Euclidean distance, or dot product.

Its primary responsibilities include:

- **Embedding Storage:** Persisting vectors associated with document identifiers or content chunks.
- **Similarity Search:** Finding the most semantically relevant vectors for a given query embedding.
- **Scalable Retrieval:** Returning top-k results efficiently, even as the corpus grows.
- **Metadata Association:** Linking vectors to document IDs, metadata, or access-control attributes.
- **Index Management:** Maintaining search indexes that support fast approximate or exact nearest-neighbor queries.

The vector database does not replace SQLite 3. Instead, it complements it by handling semantic retrieval while SQLite 3 handles structured governance, permissions, and analytical queries.

#### Ask AI Retrieval Flow
In Ask AI workflows, the embedding model and vector database work together to retrieve relevant context before the generative LLM produces an answer.

The process typically follows these steps:

1. **The user asks a natural-language question.**
2. **The station sends the question to the Orchestrator.**
3. **WarpCore validates the request and retrieves permission and metadata constraints from `ship_computer.db`.**
4. **The query text is converted into an embedding using the embedding model.**
5. **The vector database searches for the most similar document embeddings.**
6. **The search is constrained by document identifiers or metadata filters obtained from SQLite 3.**
7. **The top relevant content chunks are retrieved.**
8. **The retrieved context is formatted into a prompt for the generative LLM.**
9. **The generative LLM produces a response grounded in the retrieved evidence.**
10. **The station displays the answer, often with citations or source references.**

This approach reduces hallucination because the generative LLM is not expected to answer from parametric memory alone. Instead, it uses locally retrieved, authorized content as evidence.

#### Deep Dive Retrieval Flow
Deep Dive workflows may also use the embedding model and vector database, but they place greater emphasis on structured analysis.

In Deep Dive, the system may:

- Use SQLite 3 to identify relevant time ranges, entities, or event categories.
- Use the vector database to find semantically related documents or logs.
- Combine relational results with semantic results to produce a richer analytical view.
- Use the generative LLM to summarize or explain the combined findings.

For example, a Deep Dive request such as “Explain recent performance degradation in the navigation subsystem” may involve:

1. Querying `ship_computer.db` for recent performance events.
2. Filtering events by subsystem, severity, and time range.
3. Embedding the query and related event descriptions.
4. Searching the vector database for semantically related documentation or logs.
5. Correlating structured events with retrieved context.
6. Generating a diagnostic summary using the generative LLM.

This hybrid approach allows Spock to combine precise relational analysis with semantic understanding.

#### Hybrid Search and Reranking
In many Spock workflows, retrieval is not purely semantic or purely structured. The system may combine multiple signals:

- **Keyword or metadata filters** from SQLite 3.
- **Semantic similarity scores** from the vector database.
- **Recency, relevance, or authority weights** from structured metadata.
- **Reranking** of candidate results before they are passed to the generative LLM.

This hybrid strategy improves accuracy by ensuring that results are both semantically relevant and operationally appropriate.

#### Consistency Between SQLite 3 and the Vector Database
Because the two storage systems serve different purposes, Spock must maintain consistency between them.

Typical consistency mechanisms include:

- **Shared Document Identifiers:** SQLite 3 and the vector database reference the same document IDs.
- **Index Metadata:** SQLite 3 tracks vector index versions, rebuild status, or synchronization state.
- **Permission Enforcement:** SQLite 3 determines which documents are allowed to be searched.
- **Audit Logging:** Query results and retrieval metadata are recorded for diagnostics.
- **Reindexing Workflows:** When documents are added, updated, or deleted, both systems are updated or invalidated as needed.

This coordination ensures that semantic search remains aligned with the application’s authoritative structured state.

#### Failure Handling and Resilience
The embedding and vector search components are designed to degrade gracefully when possible.

Common failure scenarios include:

- **Embedding model unavailable:** The system may fall back to keyword search, metadata filtering, or a limited Deep Dive mode.
- **Vector database unavailable:** The system may return structured results from SQLite 3 or indicate that semantic search is unavailable.
- **Stale index:** The system may warn that results may be outdated or trigger a reindexing task.
- **Permission mismatch:** The system may exclude unauthorized documents before retrieval or after retrieval, depending on the security model.

By separating structured state, semantic retrieval, and generative response, Spock can maintain reliability, auditability, and explainability across both Ask AI and Deep Dive workflows.
**Embedding Process:**
During data ingestion, raw documents, logs, and knowledge-base entries are chunked into semantically coherent segments and passed through the embedding model. The model maps each text segment into a high-dimensional vector space in which semantic similarity corresponds to geometric proximity. The resulting vectors, together with their associated document identifiers, chunk identifiers, and metadata pointers, are stored in the vector database. This process is handled asynchronously by Spock background services so that ingestion and indexing do not block user workflows.

**Vector Database Role:**
The vector database indexes these embeddings using approximate nearest neighbor (ANN) algorithms, enabling low-latency similarity searches across large collections of records. When an Ask AI request arrives, the user's query is embedded using the same embedding model, and the vector database performs a cosine similarity or inner-product search to retrieve the top-k most relevant chunks. These chunks are then ranked, deduplicated, and formatted into a context window for the generative LLM.

**Integration with the RAG Pipeline:**
The retrieved context is injected into the prompt template alongside the original user query and system instructions. The generative LLM then produces a response grounded in the retrieved evidence. `WarpCore` coordinates this handoff, ensuring that vector search results are properly aligned with relational filters from `ship_computer.db`. This hybrid approach combines the precision of relational metadata filtering with the flexibility of semantic search, allowing Spock to deliver accurate, traceable, and context-aware answers while maintaining strict separation between indexing, retrieval, and generation stages.

**SQLite 3 `ship_computer.db` Role:**
`ship_computer.db` is the local SQLite 3 relational database used by the Python-based Spock application to store structured state, metadata, permissions, and audit information. It acts as the system of record for what data exists, who may access it, how data is organized, and what actions have been taken. Unlike the vector database, which optimizes semantic similarity search, `ship_computer.db` provides deterministic queries, joins, constraints, and transactional consistency.

Typical data stored in `ship_computer.db` includes:
- Documents, logs, and knowledge-base entries
- Chunk identifiers and metadata pointers used by the vector database
- User, role, and permission records
- Ask AI request and response records
- Deep Dive session state, steps, evidence, and generated artifacts
- Citation and provenance records
- System configuration and audit logs

`ship_computer.db` typically does not store the high-dimensional vectors themselves; those remain in the vector database. Instead, it stores the relational identifiers and metadata needed to connect vector search results back to authoritative application state.

**Ask AI Interaction with `ship_computer.db`:**
For Ask AI inquiries, `ship_computer.db` provides the relational context that constrains and enriches semantic retrieval. Before or during vector search, Spock may query the database to resolve the user's identity, validate permissions, apply source filters, and identify relevant document collections. It may also retrieve metadata such as document titles, timestamps, owners, tags, and status to help rank or filter candidate chunks.

After the generative LLM produces an answer, `ship_computer.db` records the request, the retrieved evidence, the final response, and any citations or provenance links. This allows Spock to maintain traceability, support follow-up questions, and provide auditable answers that can be reviewed or replayed.

**Deep Dive Interaction with `ship_computer.db`:**
For Deep Dive inquiries, `ship_computer.db` stores the persistent state of a multi-step investigation. This includes the original question, intermediate prompts, retrieved evidence, generated summaries, hypotheses, task steps, and final deliverables. Because Deep Dive workflows may span multiple turns, tools, or background jobs, the database provides durable storage that survives application restarts and enables resumable sessions.

`ship_computer.db` also coordinates the relationship between Deep Dive artifacts and the underlying evidence. Each generated claim, summary, or report can be linked to specific chunks, documents, or vector search results, allowing Spock to present citations and explain how the answer was derived.

**Embedding LLM and Vector Database Workflow:**
The embedding LLM, or embedding model, is a specialized model that converts text into numerical vectors. It is not used to generate natural-language answers; instead, it creates a mathematical representation of meaning that can be compared efficiently. During ingestion, Spock chunks source material, sends each chunk to the embedding model, and stores the resulting vector in the vector database.

At query time, Spock embeds the user's question using the same model. The vector database then compares the query vector against stored vectors using an ANN index and a similarity metric such as cosine similarity or inner product. The closest vectors represent the chunks that are semantically most relevant to the question.

The retrieved chunks are then passed through a retrieval pipeline that may include filtering, reranking, deduplication, and context assembly. The final context is combined with the user's question and system instructions in a prompt template. The generative LLM uses that prompt to produce an answer. In this design, the embedding LLM enables semantic matching, the vector database enables fast retrieval, and the generative LLM enables natural-language synthesis.