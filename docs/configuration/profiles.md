# Profiles

Profiles store per-workstation configurations, such as model selections, ports, paths, and preferences. They allow settings to be customized for a particular workstation without altering the configuration of other workstations.

## Storage

Profiles are managed by `WarpCore.profile_store` and persisted to SQLite 3. The central database file is `ship_computer.db`, which stores profile configurations alongside core operational data required by the Spock application. This includes structured records for **Ask AI** inquiries, which are focused on information retrieval, and **Deep Dive** inquiries, which are focused on complex analysis and multi-step reasoning. Key tables include `profiles`, `inquiries`, and `results`.

Database interactions are wrapped in explicit transactions, with automatic rollback available when an operation fails. This ensures that configuration and inquiry data remain consistent across both successful and failed updates.

## Usage

```python
from WarpCore.profile_store import ProfileStore

store = ProfileStore()
profile = store.get_active()
print(profile.model_name)
```

This example retrieves the currently active profile using `ProfileStore.get_active()` and prints its model name, assuming the returned profile object exposes a `model_name` attribute. Callers should verify that `get_active()` returns a valid profile instance before accessing its attributes to prevent `NoneType` errors.

## Creating a Profile

```python
store = ProfileStore()
store.create(name="workstation-1", model="llama-3-8b", port=8081)
```

This creates a new profile named `workstation-1` with the specified model and port, then persists it to SQLite. Once created, the profile can be reused in subsequent sessions or operations that require workstation-specific settings. Profiles may also store additional configuration values, such as file paths, API keys, or UI preferences, depending on the application's schema design.

### Lifecycle Management

Profiles are managed as persistent records within the store: they can be created, retrieved, updated, and deleted when no longer needed. Removing unused profiles prevents stale configurations from accumulating in the database. For example, a profile can be removed with `store.delete(name="workstation-1")`. The store automatically handles foreign key constraints to ensure related inquiry and result records are archived or cleaned up according to the defined retention policy.

## Database Core: ship_computer.db and Spock Integration

The `ship_computer.db` file serves as the central SQLite 3 database for the application, managing both profile configurations and core operational data required by the Spock application. This database is structured to support reliable, auditable queries for AI-driven tasks, specifically handling **Ask AI** inquiries and **Deep Dive** inquiries.

### Schema Overview

The database schema normalizes data while maintaining strict transactional safety. Normalization reduces redundant storage of profile settings, inquiry metadata, and results, making updates easier to maintain. Transactional safety ensures that related changes are committed together or not at all. Key tables include:

*   **`profiles`**: Stores configuration details for each workstation, including model paths, API ports, preference flags, and active status indicators.
*   **`inquiries`**: Logs metadata for every Ask AI or Deep Dive request, including timestamps, user identifiers, query hashes, session IDs, and inquiry type flags.
*   **`results`**: Stores the output of AI processing, linked to specific inquiry IDs for retrieval, auditing, and caching. Deep Dive inquiries may contain multiple result rows representing intermediate reasoning steps.

Depending on the deployment, additional tables or external stores may also be used for `inquiry_steps`, `embeddings`, `vector_chunks`, or checkpoint data. In such cases, `ship_computer.db` remains the authoritative relational store for profiles, inquiry metadata, and final or intermediate results, while the vector database stores semantic representations used for retrieval.

### Embedding LLM and Vector Database

Spock uses an embedding LLM, or a dedicated embedding model, to convert text into numerical vector representations. These vectors capture semantic meaning, allowing Spock to compare the similarity between a user query and stored content without relying only on keyword matching.

The embedding process works as follows:

1.  **Text preparation**: Spock receives a user query, document chunk, intermediate reasoning artifact, or other text item.
2.  **Embedding generation**: The embedding LLM converts the text into a fixed-size vector.
3.  **Vector storage**: The vector, along with associated metadata, is stored in the vector database.
4.  **Semantic search**: When a new query is submitted, Spock embeds the query and searches the vector database for the most similar stored vectors.
5.  **Context assembly**: The retrieved chunks or artifacts are ranked, filtered, and assembled into a context window for the generative model or analysis engine.

The vector database is responsible for storing and querying these embeddings efficiently. It may be implemented as a separate vector database service or as a SQLite-backed vector extension, depending on the deployment. In either case, Spock treats it as a semantic index that supports fast approximate nearest-neighbor search.

For **Ask AI** inquiries, the embedding LLM and vector database are used primarily for retrieval. Spock embeds the user's question, searches the vector database for relevant documents, notes, or prior results, and then provides the most relevant context to the generative model. This allows the model to answer from grounded, workstation-specific information rather than relying solely on its internal knowledge.

For **Deep Dive** inquiries, the embedding LLM and vector database support multi-step reasoning. Spock may embed the initial question, intermediate hypotheses, retrieved evidence, and generated analysis steps. During each reasoning step, Spock can query the vector database to find relevant prior context, compare new findings against earlier artifacts, and retrieve supporting evidence. This helps the application maintain continuity across long-running analyses and reduces the risk of losing important context between steps.

The vector database does not replace `ship_computer.db`. Instead, it complements it. `ship_computer.db` stores structured, transactional records such as profiles, inquiry metadata, result payloads, and audit information. The vector database stores semantic representations used for similarity search and context retrieval. Together, they allow Spock to combine reliable relational persistence with flexible semantic search.

### Spock Application Interaction

The Spock application interacts with `ship_computer.db` through a managed database layer that controls connection pooling, query optimization, and write ordering. This interaction ensures that:

1.  **Ask AI Inquiries**: When a user submits an Ask AI query, the system logs the request in `inquiries`, retrieves relevant context via semantic search, and stores the final response in `results`. This supports historical tracking of knowledge retrieval while minimizing direct exposure of sensitive raw data to the generative model.
2.  **Deep Dive Inquiries**: For complex tasks requiring multi-step reasoning, the database persists intermediate states, checkpoint tokens, and final outputs. This allows an interrupted Deep Dive session to resume from the last committed transaction in `ship_computer.db` without losing computational progress.

### Ask AI and Deep Dive Inquiry Processing

Spock treats **Ask AI** and **Deep Dive** as distinct inquiry types because they have different processing requirements.

**Ask AI** is optimized for fast, grounded information retrieval. A typical Ask AI flow is:

1.  The user submits a question.
2.  Spock creates an inquiry record in `inquiries`.
3.  Spock loads the active profile to determine the model, retrieval settings, and workstation-specific preferences.
4.  Spock embeds the question using the embedding LLM.
5.  Spock queries the vector database for the most relevant chunks, documents, or prior results.
6.  Spock ranks and filters the retrieved context.
7.  Spock sends the question and selected context to the generative model.
8.  Spock stores the final answer in `results`.
9.  The inquiry, result, and related metadata remain available for auditing, replay, or follow-up questions.

**Deep Dive** is optimized for complex, multi-step analysis. A typical Deep Dive flow is:

1.  The user submits a complex task or research question.
2.  Spock creates an inquiry record in `inquiries` and marks it as a Deep Dive inquiry.
3.  Spock breaks the task into reasoning steps, sub-questions, or analysis checkpoints.
4.  For each step, Spock may embed the step's context and query the vector database for relevant evidence.
5.  Spock generates intermediate reasoning artifacts, such as hypotheses, summaries, comparisons, or partial conclusions.
6.  Spock persists intermediate results and checkpoints in `results` or related step tables.
7.  If the session is interrupted, Spock can resume from the last committed checkpoint.
8.  When the analysis is complete, Spock stores the final output in `results` and links it back to the original inquiry.

This separation allows Spock to provide quick answers for simple retrieval tasks while preserving enough state to support long-running, iterative analysis.

### Data Flow and Audit Trail

Each AI-driven request follows a consistent lifecycle:

1.  Spock creates or identifies an inquiry record in `inquiries`.
2.  The application retrieves profile settings and any relevant context needed for the task.
3.  The model or analysis engine produces a response or intermediate result.
4.  The final output is written to `results` and linked back to the original inquiry via foreign keys.

This flow provides an auditable trail that connects user intent, system configuration, and generated output without requiring raw sensitive data to be retained in every result record. Indexes on `inquiry_id`, `timestamp`, and `user_id` ensure rapid retrieval for logging and debugging.

### Transactional Integrity

All interactions between Spock and the SQLite database are wrapped in explicit transactions. This prevents partial writes, such as an incomplete Deep Dive analysis, from leaving orphaned data in the database. If a query fails or a timeout occurs, the transaction is rolled back automatically, maintaining the consistency of the `ship_computer.db` file across all sessions. SQLite's Write-Ahead Logging (WAL) mode is enabled to allow concurrent reads during heavy write operations, ensuring the application remains responsive during intensive AI workloads.
## Embedding LLM and Vector Database Integration

The Spock application uses a dedicated embedding LLM and a vector database to provide semantic search and context retrieval. This design separates raw document storage from AI reasoning, allowing fast, relevance-driven retrieval for both Ask AI and Deep Dive workflows.

The embedding LLM converts text into numerical vectors that represent meaning. The vector database stores those vectors and supports similarity search. SQLite 3, through `ship_computer.db`, stores relational metadata, permissions, session state, audit records, and synchronization information. Together, these components allow Spock to retrieve relevant context, enforce access control, and maintain a reliable record of AI-assisted analysis.

### Embedding Pipeline Architecture

When a user submits a query or when new documents are ingested, Spock routes the text through the embedding LLM. The model transforms unstructured text into high-dimensional dense vectors, also called embeddings. These vectors capture semantic similarity rather than exact keyword matches.

The resulting vectors are stored in a vector database optimized for Approximate Nearest Neighbor (ANN) search. ANN search allows Spock to find the most similar vectors quickly, even when the index contains a large number of document chunks.

The vector database operates alongside `ship_computer.db`. The vector store holds the numerical embeddings and lightweight payload references, while SQLite 3 holds the authoritative relational metadata needed for permissions, citations, session tracking, and auditability.

### Semantic Retrieval for Ask AI

For Ask AI inquiries, the embedding pipeline enables rapid context assembly:

1. The user's question is converted into an embedding vector.
2. The vector database performs a similarity search against indexed document chunks and returns the most semantically relevant passages.
3. Spock uses `ship_computer.db` to resolve vector IDs to document chunks, verify access permissions, retrieve source metadata, and rank or filter candidates.
4. The selected chunks are formatted into a context window.
5. The generative LLM receives the original query and the retrieved context, producing a grounded, citation-ready response.

This retrieval-augmented generation (RAG) approach reduces hallucination and ensures Ask AI responses are tied to verified source material.

### Context Management for Deep Dive

Deep Dive inquiries require sustained context across multiple reasoning steps. The embedding LLM and vector database support this by:

* **Chunking and Indexing**: Long documents, reports, or conversation histories are split into manageable segments, embedded, and indexed for fast lookup.
* **Dynamic Context Refreshing**: As the Deep Dive session progresses, intermediate outputs, hypotheses, and analysis notes are embedded and stored. The vector database re-ranks relevant context based on the evolving query trajectory, helping the generative model focus on the most pertinent information.
* **State Checkpointing**: Vector metadata is synchronized with `ship_computer.db` at each reasoning step. If a session is interrupted, Spock can reconstruct the semantic context from stored checkpoints and resume analysis without reprocessing previously evaluated data.

### Vector-Relational Synchronization

To maintain data integrity, Spock synchronizes vector database operations with the relational schema:

* Every vector insertion or update generates a corresponding metadata record in `ship_computer.db`, linking vector IDs to inquiry sessions, user profiles, document sources, and access permissions.
* Batch operations are coordinated with database transactions where possible. Because the vector database and SQLite 3 are separate stores, Spock uses idempotent writes, reconciliation logs, and periodic verification to prevent drift.
* Periodic reconciliation jobs verify that vector embeddings correspond to their source documents, flagging or re-embedding corrupted, stale, or permission-mismatched entries.

This hybrid architecture combines the speed and semantic accuracy of vector search with the reliability and auditability of SQLite 3, providing a robust foundation for Spock's AI-driven workflows.

### SQLite 3 `ship_computer.db` Integration

`ship_computer.db` is the local SQLite 3 database used by Spock to manage relational state. It is not the primary store for large-scale vector search. Instead, it provides the structured, transactional, and auditable layer that surrounds the vector database.

#### Core Responsibilities

`ship_computer.db` is responsible for:

* **Document and chunk metadata**: source file, title, author, version, ingestion timestamp, content hash, and chunk boundaries.
* **Vector linkage**: mapping vector IDs to document chunks, embedding model versions, and index identifiers.
* **Access control**: user roles, document permissions, session-scoped permissions, and audit-relevant access decisions.
* **Ask AI state**: inquiry records, query text, retrieved context, generated responses, citations, and feedback.
* **Deep Dive state**: session records, reasoning steps, checkpoints, intermediate artifacts, status, and resume information.
* **Synchronization and reconciliation**: logs of vector insertions, updates, deletions, failed operations, and consistency checks.

#### Conceptual Schema

A simplified schema might include the following tables:

```sql
CREATE TABLE documents (
    document_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_uri TEXT,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE vector_metadata (
    vector_id TEXT PRIMARY KEY,
    chunk_id TEXT NOT NULL REFERENCES chunks(chunk_id),
    embedding_model TEXT NOT NULL,
    embedding_version TEXT NOT NULL,
    index_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('ask_ai', 'deep_dive')),
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE inquiry_events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    step_index INTEGER,
    event_type TEXT NOT NULL,
    payload_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE permissions (
    permission_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    document_id TEXT REFERENCES documents(document_id),
    access_level TEXT NOT NULL,
    granted_at TEXT NOT NULL
);

CREATE TABLE sync_state (
    sync_id TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    vector_id TEXT,
    chunk_id TEXT,
    status TEXT NOT NULL,
    error_message TEXT,
    created_at TEXT NOT NULL
);
```

The exact schema may vary by deployment, but the important architectural point is that SQLite 3 stores the relational facts needed to interpret, secure, and audit vector search results.

#### Ask AI Interaction

During an Ask AI inquiry, `ship_computer.db` participates in the following sequence:

1. **Inquiry creation**: Spock records the user, session, timestamp, and original question.
2. **Permission resolution**: Spock checks which documents and chunks the user may access.
3. **Vector search**: The embedding LLM converts the question into a vector, and the vector database returns candidate vector IDs.
4. **Metadata resolution**: Spock joins vector IDs to `vector_metadata`, `chunks`, and `documents` to retrieve readable text, source information, and citation data.
5. **Context filtering**: Chunks that fail permission checks, are stale, or are outside the requested scope are removed.
6. **Response storage**: The final answer, retrieved context, citations, model version, and user feedback are stored for audit and follow-up.

This allows Ask AI to be both semantically flexible and operationally accountable.

#### Deep Dive Interaction

For Deep Dive, `ship_computer.db` provides durable session state. Each reasoning step can be recorded as an event or checkpoint, including:

* the current question or hypothesis,
* the vector IDs used to retrieve context,
* the chunks selected for the generative LLM,
* the intermediate output produced,
* the status of the step,
* and any errors or reconciliation flags.

When a Deep Dive session resumes, Spock reads the latest checkpoint from `ship_computer.db`, reconstructs the semantic context from the referenced vector IDs, and continues from the recorded state. This prevents loss of analytical progress and supports reproducible review of how a conclusion was reached.

### How Spock Uses the Embedding LLM and Vector Database

Spock uses the embedding LLM and vector database as a semantic retrieval layer. The embedding LLM is responsible for converting text into a numerical representation that can be compared by similarity. The vector database is responsible for storing those representations and returning the closest matches to a query vector.

#### Embedding LLM Responsibilities

The embedding LLM:

* Converts user questions, document chunks, and Deep Dive intermediate outputs into dense vectors.
* Preserves semantic relationships so that conceptually similar text produces nearby vectors.
* Enables retrieval by meaning rather than exact phrase matching.
* Supports consistent indexing and querying when the same model version is used for both ingestion and search.

The embedding LLM does not generate the final user-facing answer. Its role is to create searchable representations of text.

#### Vector Database Responsibilities

The vector database:

* Stores embeddings for indexed document chunks and, where appropriate, intermediate Deep Dive artifacts.
* Supports ANN search to find the most similar vectors to a query embedding.
* Returns vector IDs and optional payload data, such as chunk references or source identifiers.
* Enables fast retrieval over large corpora without requiring full-text keyword matching.

The vector database does not replace relational storage. It does not own permissions, audit logs, session state, or document lifecycle metadata. Those responsibilities remain in `ship_computer.db`.

#### Ingestion Flow

When Spock ingests a document:

1. The document is validated and stored as a relational record in `ship_computer.db`.
2. The document is split into chunks suitable for embedding and retrieval.
3. Each chunk is sent to the embedding LLM.
4. The resulting vector is stored in the vector database.
5. A metadata record is written to `ship_computer.db`, linking the vector ID to the chunk, document, embedding model, and index.
6. Permissions and audit metadata are associated with the document and chunk.

#### Query Flow

When Spock answers a question:

1. The user query is embedded using the same embedding LLM used during ingestion.
2. The vector database searches for the nearest vectors.
3. Candidate vector IDs are returned to Spock.
4. Spock resolves those IDs against `ship_computer.db` to obtain chunk text, document metadata, and access permissions.
5. The context is filtered, ranked, and formatted.
6. The generative LLM produces the final response using the query and retrieved context.
7. The response and retrieval metadata are recorded in `ship_computer.db`.

#### Why This Separation Matters

Separating the embedding LLM, vector database, and SQLite 3 database gives Spock three distinct capabilities:

* **Semantic retrieval** through embeddings and ANN search.
* **Relational integrity** through SQLite 3 transactions, foreign keys, and audit records.
* **Operational control** through permissions, session checkpoints, and reconciliation.

This separation allows Spock to scale vector search independently while preserving a reliable, inspectable record of every Ask AI and Deep Dive interaction.