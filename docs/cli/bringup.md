# spock_bringup

Phase A Bring-Up CLI — acquires resources, starts servers, and validates readiness.

## Commands

Run the following commands from the project root directory. The text after `#` is explanatory only; remove it before executing a command in shells that do not treat `#` as a comment.

```text
.venv\Scripts\python.exe -m spock_bringup acquire    # Acquire system resources required for the bring-up process
.venv\Scripts\python.exe -m spock_bringup up         # Start all servers and services necessary for operation
.venv\Scripts\python.exe -m spock_bringup status     # Check the current status and readiness of the system
.venv\Scripts\python.exe -m spock_bringup down       # Stop all servers and release resources
```

### Command Path Variations

The command examples above use Windows-specific paths (`.venv\Scripts\python.exe`). On Unix-like systems (macOS or Linux), replace the path with `.venv/bin/python`. Ensure the virtual environment is located in the project root directory.


## Module Reference

### Overview

The `spock_bringup` module is a Python package that provides command-line tools for managing the bring-up and tear-down of a system during Phase A of a deployment process. **Phase A** refers to the initial infrastructure provisioning stage, where the foundational environment—such as compute instances, networking, and storage—is established before application logic is deployed. The module simplifies resource acquisition, service initialization, system status validation, and resource release when components are no longer needed.

### Key Concepts

- **Acquire**: This command provisions the necessary system resources required for the bring-up process, such as compute instances, storage volumes, or network configurations. It verifies that prerequisites are met before deployment proceeds. Because this step may call external cloud provider APIs and wait for resource availability, it can take several minutes to complete.
- **Up**: This command starts all servers and services required for normal operation. Depending on the environment, this may include launching application containers, initializing databases, and starting background processes. Verify that required ports are available before running this command to avoid binding conflicts.
- **Status**: This command reports the current state of the system in real time. Use it after `up` to validate readiness, verify whether all services are running, inspect errors, or determine whether the system is ready for use. If status indicates "not ready," resolve the reported issues before proceeding with dependent workloads.
- **Down**: This command gracefully shuts down running servers and services and releases allocated resources where appropriate. It helps prevent resource leaks and unnecessary costs. Unless explicitly configured in the teardown script, this command does not delete persistent data.

### Database Architecture and SQLite Integration

The Spock application uses a local SQLite 3 database file named `ship_computer.db` to persist critical state information, query logs, and context data required for intelligent processing. Because SQLite is embedded directly within the Python runtime, no external database server is required for deployment, reducing infrastructure complexity and latency.

`ship_computer.db` serves as the relational source of truth for Spock's operational state, user interactions, session history, and metadata. It works alongside a vector database that stores semantic embeddings used for retrieval-augmented reasoning. The two storage systems are complementary:

- **SQLite 3 (`ship_computer.db`)** stores structured, queryable data such as sessions, prompts, responses, system state, trace IDs, and metadata.
- **Vector database** stores high-dimensional embeddings and chunk-level semantic content used to retrieve relevant context for Ask AI and Deep Dive inquiries.

This separation allows Spock to maintain auditable relational state while still performing fast, semantic retrieval over large bodies of text.

#### ship_computer.db Schema and Operational Mechanics

`ship_computer.db` is a serverless, single-file relational database optimized for concurrent read/write operations during active sessions. The database operates in Write-Ahead Logging (WAL) mode to ensure data integrity while allowing multiple application threads to read historical context without blocking write operations.

The schema is organized around three primary data domains:

- **Query History & Session Logs:** Stores timestamps, user prompts, model responses, and session identifiers. This enables audit trails, conversation continuity, and rollback capabilities.
- **Context & Metadata Registry:** Maintains structured metadata for documents, system configurations, and user preferences. Foreign keys link this metadata to vector representations and intermediate analysis results.
- **System State & Telemetry:** Tracks operational modes (e.g., `active`, `maintenance`, `degraded`), service health metrics, and bring-up checkpoints. This prevents conflicting operations during initialization and enables graceful failover.

All database interactions use parameterized queries and connection pooling to prevent SQL injection, minimize I/O overhead, and ensure thread safety across the Spock application stack.

#### Core Tables and Relationships

A typical `ship_computer.db` implementation includes tables that support session tracking, query auditing, context management, and Deep Dive workflow persistence. The exact table names may vary by implementation, but the logical structure generally includes the following:

| Table | Purpose |
|---|---|
| `sessions` | Tracks user or application sessions, including session ID, start time, end time, user identity, and active mode. |
| `queries` | Stores each user prompt or system-generated inquiry, including timestamp, session ID, prompt text, and request type. |
| `responses` | Stores model responses, response metadata, token usage, latency, and associated query ID. |
| `documents` | Stores metadata for source documents, such as title, source, owner, creation time, and processing status. |
| `chunks` | Stores text chunks derived from documents, including chunk ID, document ID, chunk text, position, and embedding reference. |
| `vector_references` | Maps relational chunk IDs to vector database identifiers, embedding model version, and vector storage location. |
| `deep_dive_traces` | Stores top-level Deep Dive workflows, including trace ID, objective, status, start time, and completion time. |
| `deep_dive_steps` | Stores individual reasoning or retrieval steps within a Deep Dive trace, including step order, input context, output result, and retrieved evidence. |
| `system_state` | Stores current operational state, such as `active`, `maintenance`, `degraded`, or `initializing`. |
| `telemetry` | Stores health metrics, error events, service status, and bring-up checkpoints. |

These tables are linked through stable identifiers. For example, a `query` belongs to a `session`, a `response` references a `query`, a `chunk` belongs to a `document`, and a `deep_dive_step` references both a `deep_dive_trace` and the `chunks` or `vector_references` used during that step.

This design allows Spock to reconstruct the full context of an Ask AI or Deep Dive interaction without relying on the generative model to remember prior state.

#### Concurrency, Safety, and Operational Behavior

SQLite is well suited to Spock's local deployment model because it requires no separate database server, supports file-based persistence, and provides strong transactional guarantees. However, because SQLite allows only one writer at a time, Spock uses a controlled concurrency model.

Key operational behaviors include:

- **WAL mode:** Enables readers to continue accessing the database while a writer commits changes. This is useful when Ask AI or Deep Dive workflows need to read historical context while new responses are being logged.
- **Parameterized queries:** All SQL statements use bound parameters rather than string concatenation, preventing SQL injection and improving query plan reuse.
- **Connection pooling:** Spock maintains a small pool of SQLite connections at the Python level. Each connection is guarded by appropriate locking or thread-affinity rules to avoid unsafe cross-thread access.
- **Busy timeout handling:** If a write lock is temporarily held, SQLite can wait for a configurable period before reporting an error. This reduces transient failures during concurrent session activity.
- **Transaction boundaries:** Multi-step operations, such as logging a query, storing a response, and updating session state, are committed as a single transaction where appropriate. This prevents partial writes and keeps the audit trail consistent.

This model allows Spock to maintain a reliable local database while supporting interactive AI workflows that may involve frequent reads and writes.

#### Ask AI and Deep Dive Interaction Flow

The database acts as the central memory layer for Spock's advanced reasoning features, enabling stateful, context-aware interactions:

- **Ask AI:** When a user submits an inquiry, the application first queries `ship_computer.db` to retrieve relevant historical context, user preferences, and active system configurations. This contextual payload is injected into the prompt template before being sent to the generative model. By grounding responses in persisted data rather than relying solely on model inference, Ask AI delivers more accurate, consistent, and auditable answers.
- **Deep Dive:** For complex, multi-step analysis tasks, the Deep Dive feature writes intermediate results, expanded context windows, and cross-referenced data points back into the database. Each analysis step is logged with a unique trace ID, allowing the application to resume interrupted workflows, backtrack through reasoning chains, and maintain state across long-running sessions without re-fetching raw source data.

#### Ask AI Request Lifecycle

An Ask AI inquiry follows a retrieval-augmented workflow that combines relational context from `ship_computer.db` with semantic retrieval from the vector database.

1. **Receive the user prompt**
   - Spock receives the user's question or instruction.
   - The prompt is associated with an active session ID.

2. **Load session and system context**
   - Spock queries `ship_computer.db` for:
     - Recent conversation history.
     - User preferences.
     - Active system configuration.
     - Relevant document metadata.
     - Prior Ask AI responses related to the current topic.

3. **Prepare the retrieval query**
   - Spock may rewrite or expand the user prompt to improve retrieval quality.
   - The query is passed to the embedding model to generate a dense vector representation.

4. **Retrieve semantically relevant chunks**
   - Spock searches the vector database for chunks whose embeddings are most similar to the query embedding.
   - The search may apply metadata filters, such as document type, session scope, user role, or time range.
   - The top-k results are returned with similarity scores.

5. **Resolve relational metadata**
   - Spock uses the chunk IDs or vector references returned by the vector database to query `ship_computer.db`.
   - This retrieves source document metadata, chunk text, permissions, timestamps, and related context.

6. **Build the prompt**
   - Spock assembles a prompt that includes:
     - The user's original question.
     - Retrieved context chunks.
     - Session history.
     - System instructions.
     - Any relevant configuration or policy constraints.

7. **Generate the response**
   - The assembled prompt is sent to the generative model.
   - The model produces an answer grounded in the retrieved context.

8. **Persist the interaction**
   - Spock writes the query, response, retrieved chunk references, model metadata, and timing information back to `ship_computer.db`.
   - This creates an auditable record and provides context for future Ask AI requests.

This lifecycle ensures that Ask AI responses are not based only on the model's internal knowledge. Instead, they are grounded in Spock's persisted application state and retrieved semantic context.

#### Deep Dive Request Lifecycle

Deep Dive is designed for complex, multi-step analysis tasks that require iterative retrieval, reasoning, and state persistence. Unlike a single Ask AI response, a Deep Dive workflow may span multiple retrieval passes, intermediate analyses, and follow-up questions.

1. **Create a Deep Dive trace**
   - Spock creates a new trace ID in `ship_computer.db`.
   - The trace records the user's objective, session ID, start time, and initial status.

2. **Break the objective into steps**
   - Spock decomposes the task into smaller analytical steps.
   - Each step is stored in the `deep_dive_steps` table with an ordered position and status.

3. **Retrieve context for the first step**
   - Spock generates an embedding for the step's query.
   - It searches the vector database for relevant chunks.
   - It resolves chunk metadata from `ship_computer.db`.

4. **Perform step-level analysis**
   - Spock may call the generative model to summarize, compare, classify, or reason over the retrieved context.
   - The intermediate result is stored in the database with the trace ID and step ID.

5. **Refine the next query**
   - Based on the intermediate result, Spock generates a follow-up query.
   - This allows the workflow to explore related concepts, missing evidence, or conflicting information.

6. **Repeat retrieval and reasoning**
   - Each iteration creates additional vector searches and database writes.
   - Spock records which chunks were used, which were rejected, and why.

7. **Maintain a reasoning chain**
   - The database preserves the sequence of steps, inputs, outputs, and evidence.
   - This allows Spock to backtrack, resume, or explain how a final conclusion was reached.

8. **Produce the final Deep Dive result**
   - After sufficient evidence has been gathered, Spock synthesizes a final answer or report.
   - The final result is linked to the trace ID and all contributing steps.

9. **Persist the completed workflow**
   - Spock updates the trace status to completed, failed, or paused.
   - All intermediate artifacts remain available for audit, debugging, or future continuation.

This design allows Deep Dive to handle long-running analytical tasks without losing context, even if the application is restarted or the user returns later.

#### Embedding LLM and Vector Database Pipeline

Spock separates generative reasoning from semantic retrieval by utilizing a dedicated embedding model alongside a vector database. This architecture enables efficient, high-precision context retrieval before any generative processing occurs.

The embedding model and vector database form the semantic retrieval layer of Spock. They allow the application to find relevant text based on meaning rather than exact keyword matching. This is especially important for Ask AI and Deep Dive, where user questions may be phrased differently from the source material.

#### What the Embedding Model Does

The embedding model converts text into a fixed-size numerical vector, also called an embedding. Each vector represents the semantic meaning of the text in a high-dimensional space. Texts with similar meanings produce vectors that are closer together, while unrelated texts produce vectors that are farther apart.

In Spock, the embedding model is used to encode:

- User questions.
- Document chunks.
- Deep Dive step queries.
- Intermediate analysis summaries.
- Metadata-rich context fragments.

Although it is sometimes referred to as an "embedding LLM," the component is typically an encoder model rather than a generative language model. Its purpose is not to produce natural language output, but to produce dense vector representations that can be compared using similarity metrics such as cosine similarity.

Key characteristics of the embedding pipeline include:

- **Deterministic encoding:** The same input text, model version, and preprocessing rules produce the same embedding.
- **Semantic similarity:** Embeddings capture meaning, allowing Spock to retrieve related content even when exact keywords differ.
- **Chunk-level granularity:** Documents are split into smaller chunks so that retrieval can target specific passages rather than entire files.
- **Metadata association:** Each embedding is linked to relational metadata in `ship_computer.db`, such as document ID, chunk ID, session scope, and permissions.
- **Model versioning:** Spock stores the embedding model version with each vector reference so that retrieval behavior can be tracked and reproduced.

#### What the Vector Database Stores

The vector database stores the numerical embeddings and the minimal information needed to perform similarity search. It is optimized for fast nearest-neighbor queries over high-dimensional vectors.

A typical vector record includes:

| Field | Purpose |
|---|---|
| `vector_id` | Unique identifier for the embedding record. |
| `chunk_id` | Identifier for the text chunk in `ship_computer.db`. |
| `document_id` | Identifier for the source document. |
| `session_id` | Optional session or scope identifier. |
| `embedding` | High-dimensional vector produced by the embedding model. |
| `model_version` | Version of the embedding model used. |
| `created_at` | Timestamp for when the embedding was generated. |
| `metadata` | Additional filters such as document type, owner, language, or classification. |

The vector database does not replace `ship_computer.db`. Instead, it provides fast semantic lookup. After Spock retrieves candidate vector IDs, it uses those IDs to query `ship_computer.db` for authoritative text, permissions, timestamps, and relational context.

#### Retrieval-Augmented Generation Flow

Spock uses the embedding model and vector database as part of a retrieval-augmented generation pipeline. The general flow is as follows:

1. **Chunking**
   - Source documents are split into manageable chunks.
   - Each chunk is stored in `ship_computer.db` with metadata.

2. **Embedding**
   - Each chunk is passed through the embedding model.
   - The resulting vector is stored in the vector database.
   - A reference to the vector is stored in `ship_computer.db`.

3. **Query embedding**
   - When a user asks a question, Spock embeds the query using the same embedding model.

4. **Similarity search**
   - Spock searches the vector database for the most similar chunk embeddings.
   - The search returns a ranked list of candidate chunks.

5. **Metadata filtering**
   - Spock filters results using relational metadata from `ship_computer.db`.
   - This ensures that only authorized, relevant, and appropriately scoped content is used.

6. **Context assembly**
   - Spock retrieves the full text of the selected chunks.
   - It combines them with session history and system instructions.

7. **Generative response**
   - The assembled context is sent to the generative model.
   - The model produces a response grounded in the retrieved evidence.

8. **Persistence**
   - Spock stores the query, response, retrieved chunk IDs, similarity scores, and model metadata in `ship_computer.db`.

This pipeline allows Spock to answer questions using current, relevant, and auditable context rather than relying solely on the generative model's internal knowledge.

#### Relationship Between SQLite and the Vector Database

The SQLite database and vector database are tightly coordinated but serve different purposes.

| Concern | SQLite 3 (`ship_computer.db`) | Vector Database |
|---|---|---|
| Primary role | Relational state, audit logs, session history, system state | Semantic similarity search |
| Data type | Structured rows, foreign keys, timestamps, text | High-dimensional vectors and lightweight metadata |
| Query style | SQL queries, joins, filters, transactions | Nearest-neighbor vector search |
| Strength | Consistency, auditability, transactional writes | Fast semantic retrieval over large text corpora |
| Used for | Ask AI history, Deep Dive traces, permissions, configuration | Finding relevant chunks for user questions and Deep Dive steps |

Spock uses stable identifiers to connect the two systems. For example, a vector record may reference a `chunk_id`, and that `chunk_id` may exist in `ship_computer.db` with the full chunk text, document ownership, permissions, and processing status.

This design provides several benefits:

- **Auditability:** Every Ask AI and Deep Dive interaction can be traced back to the exact chunks and metadata used.
- **Consistency:** Relational state remains authoritative in SQLite, while vector search remains optimized for semantic retrieval.
- **Scalability:** Vector search can be optimized independently of the relational schema.
- **Resumability:** Deep Dive workflows can be paused and resumed because their state is persisted in SQLite.
- **Security:** Permissions and access control can be enforced through relational metadata before context is included in a prompt.

Together, `ship_computer.db`, the embedding model, and the vector database form the foundation of Spock's context-aware Ask AI and Deep Dive capabilities.
## Semantic Retrieval Pipeline

1. **Text Ingestion & Embedding Generation:** Raw documents, logs, and user prompts are passed through a lightweight embedding LLM, such as `text-embedding-3-small` or an open-source equivalent. This model converts unstructured text into high-dimensional numerical vectors that capture semantic meaning rather than exact keyword matches.

2. **Vector Storage & Indexing:** The generated vectors are stored in a vector database, or in a SQLite-vec extension, optimized for similarity search. Each vector is indexed using approximate nearest neighbor, or ANN, algorithms such as HNSW or IVF to enable millisecond-level retrieval even across large datasets.

3. **Semantic Query Resolution:** When a user initiates an Ask AI or Deep Dive request, the same embedding model converts the query into a vector. The vector database performs a similarity search, typically using cosine distance or inner product, to retrieve the most semantically relevant chunks from the knowledge base.

4. **Context Assembly & Generation:** Retrieved chunks are ranked, filtered by relevance thresholds, and assembled into a structured context window. This context is merged with metadata from `ship_computer.db` and passed to the primary generative LLM. The model then synthesizes a response grounded in both real-time vector retrieval and persistent relational state.

This decoupled pipeline ensures that Spock scales efficiently: the embedding model handles semantic matching, the vector database manages high-dimensional search, SQLite maintains relational integrity and session state, and the generative LLM focuses exclusively on reasoning and response formulation.

## SQLite 3 `ship_computer.db`

`ship_computer.db` is the SQLite 3 database used by the Spock application to store persistent relational state. It is the system of record for user sessions, conversation history, document metadata, retrieval results, Deep Dive execution state, and application-level audit information.

While the vector database is responsible for semantic similarity search, `ship_computer.db` is responsible for structured, transactional data. This separation allows Spock to combine fast semantic retrieval with reliable application state management.

### Role in the Spock Application

`ship_computer.db` provides the following capabilities:

- **Session persistence:** Stores user conversations, Ask AI exchanges, and Deep Dive runs.
- **Metadata management:** Tracks documents, sources, chunk identifiers, permissions, and provenance.
- **Retrieval auditing:** Records which chunks were retrieved for a given query and how they were ranked.
- **Deep Dive state tracking:** Stores intermediate steps, subqueries, statuses, and final outputs for multi-stage analysis.
- **Application integrity:** Enforces foreign key relationships, transactional writes, and consistent state across requests.
- **Operational observability:** Captures timestamps, model usage, latency, token counts, and error states.

### Typical Data Areas

A Spock implementation using `ship_computer.db` commonly maintains data in the following areas:

| Area | Purpose |
|---|---|
| Users and identities | Associates sessions and prompts with authenticated users or service identities. |
| Sessions and conversations | Groups related Ask AI messages into persistent conversation threads. |
| Messages | Stores user prompts, assistant responses, timestamps, and model metadata. |
| Documents and sources | Tracks ingested files, logs, reports, or other knowledge sources. |
| Chunks and vector references | Maps semantic chunks to their vector identifiers and source metadata. |
| Retrieval results | Records the chunks returned for each Ask AI or Deep Dive query. |
| Deep Dive runs | Stores the lifecycle of a Deep Dive request, including status and final output. |
| Deep Dive steps | Captures intermediate reasoning, subqueries, retrieval batches, and partial results. |
| Audit and usage logs | Records model calls, token usage, latency, errors, and feature flags. |

### Ask AI Interaction

For an Ask AI request, `ship_computer.db` participates in the request lifecycle as follows:

1. **Session validation:** Spock verifies that the user has an active session and that the request is authorized.
2. **Prompt persistence:** The user prompt is inserted into the messages table with a timestamp, session identifier, and request metadata.
3. **Retrieval context lookup:** After the vector database returns relevant chunks, Spock queries `ship_computer.db` for chunk metadata, source information, permissions, and provenance.
4. **Context assembly:** The retrieved chunks and relational metadata are combined into the prompt context for the generative LLM.
5. **Response persistence:** The assistant response, citations, retrieval identifiers, token usage, and latency are written back to the database.
6. **Audit trail:** The completed exchange is available for later review, debugging, or continuity in the same conversation.

This ensures that Ask AI responses are not only semantically grounded but also traceable to specific sources, sessions, and application state.

### Deep Dive Interaction

Deep Dive is a more complex workflow than a single Ask AI query. It may involve multiple retrieval passes, iterative analysis, and synthesis of a longer-form response.

`ship_computer.db` supports Deep Dive by tracking the full execution lifecycle:

1. **Run creation:** Spock creates a Deep Dive run record with a unique identifier, user, session, initial prompt, and status.
2. **Planning state:** If the application generates a plan or subqueries, those are stored as structured steps.
3. **Intermediate retrieval:** Each subquery or retrieval batch is recorded, including the vector database results and relevance scores.
4. **Step execution:** Intermediate outputs, partial summaries, and reasoning artifacts are persisted as steps.
5. **Final synthesis:** The final Deep Dive response is stored with references to the steps, sources, and retrieval results that contributed to it.
6. **Status management:** The run can transition through states such as `pending`, `running`, `completed`, `failed`, or `cancelled`.

This allows Spock to resume, inspect, or debug Deep Dive workflows after they have been initiated.

### Transactional and Operational Notes

Because `ship_computer.db` is a SQLite 3 database, Spock should use it in a way that preserves consistency and performance:

- Use parameterized SQL queries to prevent SQL injection.
- Enable foreign key constraints to maintain referential integrity.
- Use transactions when writing related records, such as a message, retrieval result, and audit entry.
- Use indexes on session, user, document, chunk, and Deep Dive run identifiers.
- Consider WAL mode for improved concurrent read performance.
- Store large generated responses as text or blob fields, while keeping metadata in structured columns.
- Use soft deletes or status flags where historical auditability is required.

## How Spock Uses the Embedding LLM and Vector Database

The embedding LLM and vector database form the semantic retrieval layer of Spock. Together, they allow the application to find relevant information based on meaning rather than exact string matching.

### Embedding LLM

The embedding LLM is a specialized model that converts text into a fixed-size numerical vector. Unlike a generative LLM, it does not produce natural language output. Instead, it produces a dense representation of the input text.

For example:

- A user prompt such as “Why did the deployment fail?” is converted into a vector.
- A document chunk describing a failed deployment is also converted into a vector.
- If the two concepts are semantically related, their vectors will be close together in vector space.

The embedding LLM is used in two main places:

1. **Ingestion time:** Documents, logs, and knowledge chunks are embedded and stored in the vector database.
2. **Query time:** User prompts from Ask AI or Deep Dive are embedded and used to search the vector database.

Using the same embedding model for both ingestion and querying is important because the vectors must exist in the same semantic space.

### Vector Database

The vector database stores the generated vectors along with associated metadata. It is optimized for similarity search, meaning it can quickly find the vectors that are closest to a query vector.

The vector database may be a dedicated vector store or a SQLite-vec extension. In either case, it provides:

- Vector storage
- Similarity search
- Approximate nearest neighbor indexing
- Metadata filtering
- Relevance scoring
- Efficient retrieval over large collections

### Ingestion Flow

When Spock ingests new knowledge, the process typically follows these steps:

1. **Source acquisition:** Spock receives a document, log file, report, or other text source.
2. **Chunking:** The source is divided into smaller, meaningful chunks suitable for retrieval.
3. **Embedding:** Each chunk is passed to the embedding LLM and converted into a vector.
4. **Vector storage:** The vector is stored in the vector database with a unique chunk identifier.
5. **Metadata linkage:** `ship_computer.db` stores the relationship between the chunk, source document, user permissions, and vector identifier.

This creates a searchable semantic index while preserving relational context in SQLite.

### Query Flow

When a user submits an Ask AI or Deep Dive request, Spock uses the embedding LLM and vector database as follows:

1. **Query embedding:** The user prompt is converted into a vector using the embedding LLM.
2. **Similarity search:** The vector database searches for the most similar stored vectors.
3. **Candidate retrieval:** The top matching chunks are returned with similarity scores.
4. **Metadata enrichment:** Spock queries `ship_computer.db` for source, permission, and context metadata.
5. **Filtering and ranking:** Results are filtered by relevance thresholds, permissions, and freshness.
6. **Context construction:** The selected chunks are assembled into a structured context for the generative LLM.
7. **Response generation:** The generative LLM produces an answer grounded in the retrieved context.
8. **Persistence:** The query, retrieved chunks, response, and usage metadata are stored in `ship_computer.db`.

### Ask AI vs. Deep Dive

Ask AI and Deep Dive use the same semantic retrieval foundation, but they differ in scope.

| Feature | Ask AI | Deep Dive |
|---|---|---|
| Query complexity | Usually a single user question | Often a multi-step analysis request |
| Retrieval pattern | One or a few similarity searches | Multiple iterative searches |
| Context size | Moderate | Larger and more structured |
| Output | Direct answer or short explanation | Detailed report or synthesized analysis |
| State tracking | Message-level persistence | Run-level and step-level persistence |
| Use of `ship_computer.db` | Stores prompt, response, and citations | Stores run, steps, subqueries, and final output |

### Why This Architecture Works

This architecture separates concerns in a way that improves both performance and maintainability:

- The **embedding LLM** handles semantic representation.
- The **vector database** handles fast similarity search.
- **SQLite 3 `ship_computer.db`** handles relational state, permissions, history, and auditability.
- The **generative LLM** handles reasoning and natural language response generation.

As a result, Spock can answer Ask AI questions quickly, perform deeper Deep Dive analyses reliably, and maintain a durable record of every interaction.
## Environment Setup

To ensure the commands function correctly, meet the following prerequisites:

1.  **Virtual environment**: The command examples assume a virtual environment named `.venv` exists in the project root. On macOS or Linux, use the Unix-style interpreter path (for example, `.venv/bin/python`).
2.  **Activation**: Although the commands invoke the Python executable by full path, activating the virtual environment is recommended: `.\.venv\Scripts\activate` on Windows or `source .venv/bin/activate` on Unix-like systems. This simplifies command execution and ensures the correct environment variables are set.
3.  **Permissions**: Ensure you have sufficient permissions to allocate system resources for `acquire` and bind network ports for `up`. Administrative privileges may be required depending on cloud provider policies or local infrastructure constraints.

## SQLite 3 `ship_computer.db`

`ship_computer.db` is the local SQLite 3 database used by the Spock application to persist application state, user interactions, and operational metadata. It provides a durable, transactional store for data that must survive restarts, support auditing, and enable features such as session history, Deep Dive tracking, and Ask AI response management.

The database is intentionally separate from the vector database. SQLite stores structured application data, while the vector database stores high-dimensional embeddings used for semantic search. Together, they allow Spock to combine reliable state management with AI-driven retrieval.

### Purpose of `ship_computer.db`

The `ship_computer.db` database is used for:

- Storing user sessions and conversation history.
- Recording Ask AI questions, answers, model parameters, and response metadata.
- Tracking Deep Dive investigations, including steps, findings, citations, and intermediate results.
- Maintaining references to vector database records, such as collection names, document IDs, chunk IDs, and embedding IDs.
- Preserving audit information, including timestamps, user identifiers, model versions, and retrieval statistics.
- Supporting replay, debugging, and export of AI-assisted workflows.

### Relationship to the Spock Application

The Spock application uses `ship_computer.db` as its primary local persistence layer. When a user submits an Ask AI question or initiates a Deep Dive, Spock writes relevant state to SQLite before, during, and after the AI workflow.

For example:

1. A user submits a question.
2. Spock records the question, session ID, timestamp, and request parameters in SQLite.
3. Spock sends the question to the embedding model and vector database.
4. Spock stores the retrieved context identifiers and search metadata in SQLite.
5. Spock sends the assembled prompt to the generative LLM.
6. Spock stores the final answer, token usage, latency, and any citations in SQLite.

This approach allows Spock to reconstruct what happened during an AI request, even if the vector database or LLM provider is later changed.

### Ask AI Interaction

For Ask AI inquiries, `ship_computer.db` stores the full lifecycle of a question-and-answer exchange.

Typical data includes:

- **Question**: The user’s original prompt.
- **Session ID**: The conversation or workspace context.
- **Timestamp**: When the request was made.
- **Model**: The generative LLM used to produce the answer.
- **Embedding model**: The model used to vectorize the query.
- **Vector database collection**: The collection searched for relevant context.
- **Retrieved chunks**: IDs or references to the vector records used as context.
- **Answer**: The final generated response.
- **Citations**: Sources or chunks referenced by the answer.
- **Feedback**: Optional user ratings or corrections.
- **Performance metrics**: Latency, token counts, and retrieval scores.

This makes Ask AI auditable and repeatable. Spock can later display previous answers, explain which context was used, or replay a request with updated settings.

### Deep Dive Interaction

Deep Dive is a more complex workflow than a single Ask AI question. It may involve multiple searches, subquestions, summaries, comparisons, and iterative reasoning. `ship_computer.db` stores the structured state of that process.

Typical Deep Dive data includes:

- **Deep Dive session**: The overall investigation or research task.
- **Objective**: The user’s high-level goal.
- **Plan**: The sequence of steps Spock intends to perform.
- **Steps**: Individual search, synthesis, or analysis actions.
- **Intermediate findings**: Partial conclusions generated during the workflow.
- **Retrieval records**: Vector database results used at each step.
- **Citations**: Evidence supporting each finding.
- **Final report**: The synthesized Deep Dive output.
- **Status**: Whether the Deep Dive is active, paused, completed, or failed.

By storing Deep Dive state in SQLite, Spock can support resumable investigations, branching analysis, and detailed review of how a conclusion was reached.

### Conceptual Schema

A typical `ship_computer.db` implementation may include tables such as:

| Table | Purpose |
|---|---|
| `sessions` | Stores user or application sessions. |
| `ask_ai_requests` | Stores Ask AI questions and request metadata. |
| `ask_ai_responses` | Stores generated answers and response metadata. |
| `deep_dive_sessions` | Stores top-level Deep Dive investigations. |
| `deep_dive_steps` | Stores individual steps within a Deep Dive. |
| `deep_dive_findings` | Stores intermediate or final findings. |
| `retrieval_events` | Stores vector database search events and results. |
| `citations` | Stores evidence or source references used by answers. |
| `feedback` | Stores user ratings or corrections. |
| `audit_log` | Stores system-level events for debugging and compliance. |

The exact table names may vary, but the database should preserve enough information to reconstruct the AI workflow and explain how Spock produced a given answer.

## Embedding LLM and Vector Database

Spock uses an embedding LLM and a vector database to perform semantic retrieval. The embedding LLM converts text into numerical vectors, and the vector database stores and searches those vectors efficiently.

This is separate from the generative LLM that produces natural-language answers. The embedding model is responsible for understanding meaning and similarity, while the generative model is responsible for composing responses.

### Role of the Embedding LLM

The embedding LLM transforms text into a dense vector representation. Each vector captures semantic meaning in a high-dimensional space. Text with similar meaning produces vectors that are closer together, while unrelated text produces vectors that are farther apart.

Spock uses embeddings for:

- Converting user questions into searchable vectors.
- Converting documents, chunks, notes, or knowledge-base entries into searchable vectors.
- Finding semantically relevant context for Ask AI and Deep Dive.
- Supporting similarity search, clustering, and retrieval-augmented generation.

The embedding model does not generate conversational answers. Its purpose is to make text searchable by meaning rather than by exact keyword match.

### Role of the Vector Database

The vector database stores embeddings along with metadata. It allows Spock to perform fast similarity searches over large collections of text.

Typical vector database records include:

- **Vector**: The numerical embedding produced by the embedding LLM.
- **Text**: The original text chunk or document fragment.
- **Document ID**: The source document or record.
- **Chunk ID**: The specific segment within the document.
- **Collection**: The logical group of related embeddings.
- **Metadata**: Tags, timestamps, user IDs, source type, or access controls.
- **Score**: The similarity score returned during search.

The vector database enables Spock to answer questions such as:

- “Which passages are most relevant to this question?”
- “What prior Deep Dive findings are similar to this new objective?”
- “Which documents support this claim?”
- “What context should be included in the prompt for the generative LLM?”

### Ask AI Workflow

For Ask AI, Spock follows a retrieval-augmented generation workflow:

1. **Receive the user question.**
   - The user submits a natural-language question.
   - Spock records the request in `ship_computer.db`.

2. **Embed the question.**
   - Spock sends the question to the embedding LLM.
   - The embedding LLM returns a vector representation of the question.

3. **Search the vector database.**
   - Spock queries the vector database using the question vector.
   - The vector database returns the most similar text chunks or records.

4. **Filter and rank results.**
   - Spock may apply metadata filters, such as user, session, document type, or time range.
   - Spock may rerank results using similarity scores, recency, or business rules.

5. **Build the prompt.**
   - Spock combines the user question with the retrieved context.
   - The prompt instructs the generative LLM to answer using the provided context.

6. **Generate the answer.**
   - The generative LLM produces a natural-language response.
   - Spock may include citations or references to the retrieved context.

7. **Persist the result.**
   - Spock stores the question, answer, retrieved context, model details, and metadata in `ship_computer.db`.

This workflow allows Spock to answer questions using relevant context rather than relying only on the generative model’s internal knowledge.

### Deep Dive Workflow

Deep Dive uses the same embedding and vector database infrastructure, but in a more iterative and structured way.

A typical Deep Dive workflow includes:

1. **Define the objective.**
   - The user provides a high-level research or analysis goal.
   - Spock stores the objective in `ship_computer.db`.

2. **Break the objective into subquestions.**
   - Spock may generate a plan or list of subquestions.
   - Each subquestion becomes a separate retrieval task.

3. **Embed each subquestion.**
   - Spock sends each subquestion to the embedding LLM.
   - Each subquestion receives its own vector representation.

4. **Search the vector database multiple times.**
   - Spock performs multiple similarity searches.
   - Results may be filtered by collection, metadata, or previous findings.

5. **Synthesize intermediate findings.**
   - Spock uses the generative LLM to summarize or analyze retrieved context.
   - Intermediate findings are stored in `ship_computer.db`.

6. **Iterate as needed.**
   - Spock may generate new subquestions based on earlier findings.
   - It may search again, compare results, or refine the analysis.

7. **Produce the final Deep Dive report.**
   - Spock combines all findings into a structured response.
   - Citations and evidence are preserved for review.

This makes Deep Dive suitable for complex investigations where a single search is not enough.

### Why Spock Uses Both SQLite and a Vector Database

Spock uses two different storage systems because they solve different problems.

| System | Responsibility |
|---|---|
| SQLite 3 `ship_computer.db` | Stores structured application state, sessions, requests, responses, Deep Dive steps, citations, and audit data. |
| Vector database | Stores embeddings and supports fast semantic similarity search. |
| Embedding LLM | Converts text into vectors for semantic search. |
| Generative LLM | Produces natural-language answers and synthesized findings. |

SQLite provides reliability, transactional integrity, and easy local persistence. The vector database provides semantic retrieval over large text collections. The embedding LLM connects text to the vector space, and the generative LLM turns retrieved context into useful answers.

Together, these components allow Spock to support Ask AI and Deep Dive workflows that are auditable, resumable, and grounded in relevant context.