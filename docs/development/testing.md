# Testing

## Running Tests

`pytest` is included in the optional development dependency set defined in `requirements-dev.txt`. Install these dependencies before running tests for the first time:

```bat
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest tests -q
```

**Note:** These commands assume a Windows environment with a virtual environment located at `.venv`. On Unix-like systems, use the corresponding Python executable path (for example, `./venv/bin/python`). If your virtual environment has a different name or location, adjust the paths accordingly.

The first command installs the development dependencies required for testing. The second command executes all tests discovered in the `tests/` directory. The `-q` flag reduces output verbosity by suppressing detailed logging and displaying primarily the final test results and summary.

## Test Suite

| Test File | Focus Area |
|-----------|------------|
| `test_bringup.py` | Phase A bring-up logic, including initial startup behavior |
| `test_health.py` | Health check functions |
| `test_llama_process.py` | llama.cpp process management |
| `test_llmfit_bridge.py` | LLM fit bridge logic |

Each test file targets a specific component or behavior in the project. Together, these tests verify that core modules behave as expected under normal and edge-case conditions, helping prevent regressions during development.

## Writing Tests

Tests are written using `pytest`. New test files should be placed in the `tests/` directory and named with the `test_` prefix so that `pytest` can discover them automatically without additional configuration. Test functions inside those modules should also begin with `test_`, because `pytest` discovers callable objects by name as well.

```python
def test_readiness_contract():
    from spock_onboarding.readiness import ReadinessContract
    contract = ReadinessContract(ui_ready=True, servers_ready=True)
    assert contract.is_ready
```

This example demonstrates a simple unit test for the `ReadinessContract` class. It creates a contract with both UI and server readiness flags set to `True`, then asserts that the `is_ready` property evaluates to `True`. This confirms that the readiness logic correctly combines its inputs according to the documented behavior.


## Database Architecture

The Spock application uses a persistent SQLite 3 database file named `ship_computer.db` to store stateful data required for AI interactions. This section explains how the database supports the Spock application, particularly **Ask AI** and **Deep Dive** inquiries.

### Overview of `ship_computer.db`

The `ship_computer.db` file is the central repository for durable runtime data that must survive application restarts. It is initialized on first use and persists across sessions. SQLite 3 is used because it provides a lightweight, single-file database with sufficient query capability for local application state without requiring a separate database server.

The database operates in Write-Ahead Logging (WAL) mode to optimize concurrent read/write operations and improve data integrity during active AI workflows. WAL mode allows readers to continue accessing the database while a writer is committing changes, which is useful when Spock is simultaneously retrieving context, persisting messages, and updating session state.

Typical initialization includes:

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
```

This configuration helps Spock maintain a responsive local experience while preserving a reliable record of conversations, retrieved context, embeddings, and operational events.

### Schema and Data Flow

The database is structured around several core tables that manage conversation history, document context, session state, and system telemetry:

*   **`sessions`**: Tracks unique interaction sessions, including timestamps, user identifiers, session mode, and session metadata.
*   **`messages`**: Stores individual turns in a conversation, capturing user prompts, assistant responses, tool outputs, and associated metadata such as token counts, model names, and latency.
*   **`documents`**: Holds ingested reference materials, system prompts, uploaded files, and contextual knowledge bases.
*   **`embeddings`**: Stores high-dimensional vector representations of text chunks alongside their source document references, chunk indices, and metadata.
*   **`audit_logs`**: Records system events, configuration changes, retrieval operations, and error states for debugging, observability, and compliance.

Data flows through a centralized database abstraction layer that manages connection handling, transaction boundaries, schema migrations, and safe access from multiple application components. This layer ensures that read/write operations are coordinated, that concurrent access is handled safely, and that schema updates are applied automatically when the application version advances.

#### Core Table Definitions

The following schema illustrates the primary tables used by `ship_computer.db`. The exact implementation may vary by Spock version, but the logical structure remains centered on sessions, messages, documents, embeddings, and audit records.

```sql
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT,
    mode TEXT NOT NULL CHECK (mode IN ('ask_ai', 'deep_dive', 'system')),
    status TEXT NOT NULL DEFAULT 'active',
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,
    model TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    latency_ms INTEGER,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    title TEXT,
    source_path TEXT,
    content TEXT,
    content_hash TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS embeddings (
    embedding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    vector BLOB NOT NULL,
    dimension INTEGER NOT NULL,
    embedding_model TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (document_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    session_id TEXT,
    payload_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_session_created
    ON messages(session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_embeddings_document_chunk
    ON embeddings(document_id, chunk_index);

CREATE INDEX IF NOT EXISTS idx_audit_created
    ON audit_logs(created_at);
```

The `vector` column stores the embedding as a binary blob, commonly a sequence of 32-bit or 64-bit floating-point values. The `dimension` column records the vector size so the application can validate compatibility between stored embeddings and the active embedding model.

#### Data Flow Through the Abstraction Layer

The database abstraction layer provides a consistent interface for the rest of the Spock application. Higher-level features do not issue raw SQL directly; instead, they call repository or service methods that translate business operations into database transactions.

This layer is responsible for:

*   Opening and closing SQLite connections safely.
*   Enforcing foreign-key constraints and transaction boundaries.
*   Applying schema migrations when the application starts.
*   Serializing writes to avoid corruption from concurrent access.
*   Providing query helpers for sessions, messages, documents, embeddings, and audit events.
*   Recording operational metadata for debugging and observability.

Because SQLite is a single-file database, the abstraction layer is especially important for ensuring that multiple Spock components, such as the Ask AI responder, Deep Dive planner, ingestion pipeline, and telemetry logger, do not interfere with one another.

### Interaction with Spock Application

The Spock application accesses `ship_computer.db` through a dedicated database abstraction layer. This layer centralizes connection handling, schema access, and data operations so that higher-level features can read and write persistent state consistently.

#### Ask AI Inquiries

For **Ask AI** functionality, the database provides the contextual grounding needed to answer user questions accurately. Ask AI is primarily a retrieval-augmented generation workflow: Spock retrieves relevant local context, enriches the prompt, and then asks the language model to produce a grounded answer.

When a user submits a query:

1.  **Session Resolution:** Spock identifies or creates the active session in the `sessions` table. This allows the response to be associated with the correct conversation and user context.
2.  **Query Parsing & Embedding:** The application normalizes the natural-language request and passes it through the embedding model to generate a semantic vector.
3.  **Context Retrieval:** The system performs a similarity search against the `embeddings` table to identify the most relevant document chunks, prior messages, or reference materials.
4.  **Prompt Construction:** Retrieved context is formatted into a structured prompt template, preserving source attribution, chunk order, and relevance scores where available.
5.  **Response Generation:** The enriched prompt is sent to the LLM engine, which generates a grounded response.
6.  **Persistence:** The user query, retrieved context metadata, assistant response, model information, token counts, and latency are persisted to the `messages` table.
7.  **Audit Logging:** Key events, such as retrieval success, embedding generation, prompt construction, and response completion, are recorded in `audit_logs`.

This flow allows Ask AI to answer questions using both the model’s general knowledge and the specific local context stored in `ship_computer.db`.

#### Ask AI Persistence Details

The following data is typically persisted for each Ask AI exchange:

*   Session identifier and timestamp.
*   User prompt.
*   Assistant response.
*   Model name and version, if available.
*   Prompt and completion token counts.
*   Retrieval metadata, such as document IDs, chunk indices, and similarity scores.
*   Latency measurements for embedding, retrieval, and generation stages.
*   Error states or fallback behavior, if the response could not be generated normally.

This persistence enables Spock to reconstruct prior conversations, improve follow-up questions, and provide an auditable record of how each answer was produced.

#### Deep Dive Inquiries

For **Deep Dive** inquiries, which involve complex analysis, multi-step reasoning, or extended research tasks, the database supports advanced state management and traceability. Unlike a simple Ask AI exchange, a Deep Dive session may span multiple steps, tools, documents, and intermediate conclusions.

The database supports Deep Dive in the following ways:

1.  **Session State Management:** `ship_computer.db` stores intermediate reasoning steps, tool outputs, and branching decision paths. This allows users to pause, resume, or backtrack within a Deep Dive session without losing progress.
2.  **Semantic Search & Indexing:** Vector embeddings are continuously updated as new documents or research artifacts are ingested. The database maintains optimized indexes to support rapid semantic retrieval across large knowledge bases.
3.  **Step Tracking:** Each Deep Dive step can be recorded with its input, output, status, parent step, and timestamp. This creates a navigable execution graph rather than a flat message list.
4.  **Audit & Reproducibility:** Detailed records of Deep Dive operations, including model parameters, retrieval sources, tool calls, and execution timestamps, are logged to the `audit_logs` table. This enables full reproducibility, debugging, and compliance tracking.

#### Deep Dive State Tables

In addition to the core tables, Deep Dive workflows may use supplemental tables to represent structured reasoning state. These tables are optional in simple deployments but are useful when Spock needs to preserve complex multi-step work.

```sql
CREATE TABLE IF NOT EXISTS deep_dive_steps (
    step_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    parent_step_id INTEGER REFERENCES deep_dive_steps(step_id),
    step_type TEXT NOT NULL,
    title TEXT,
    input_json TEXT,
    output_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tool_calls (
    tool_call_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    step_id INTEGER REFERENCES deep_dive_steps(step_id),
    tool_name TEXT NOT NULL,
    arguments_json TEXT,
    result_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_deep_dive_steps_session
    ON deep_dive_steps(session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_tool_calls_session
    ON tool_calls(session_id, created_at);
```

These tables allow Spock to represent Deep Dive work as a directed graph of steps and tool calls. A step may depend on a previous step, branch into parallel investigations, or be retried after a failure. The database preserves enough detail for the application to reconstruct the user’s reasoning path.

### Embedding LLM and Vector Database Integration

The Spock application relies on a dedicated embedding model to transform unstructured text into numerical vectors that capture semantic meaning. This process bridges natural language and machine-readable data structures.

Although the product may refer to this component as the “embedding LLM,” it is more precise to describe it as an embedding model. Unlike a generative language model, an embedding model does not produce prose. Instead, it maps text into a fixed-size numerical vector that can be compared mathematically with other vectors.

#### Embedding Pipeline

The embedding pipeline has four main stages:

1.  **Ingestion:** Spock receives text from user messages, uploaded documents, system prompts, or research artifacts.
2.  **Chunking:** The text is split into manageable chunks, commonly 256 to 1024 tokens, depending on the model and use case. Overlapping windows may be used to preserve context across chunk boundaries.
3.  **Embedding:** Each chunk is passed through the embedding model. The model outputs a fixed-dimensional vector, commonly 384, 768, or 1536 dimensions, representing the semantic content of the text.
4.  **Storage:** The vector, chunk text, source document reference, chunk index, model name, and dimension are stored in the `embeddings` table.

This pipeline allows Spock to convert large amounts of local text into a form that can be searched by meaning rather than exact keyword match.

#### Vector Storage in SQLite

In Spock, the vector database is implemented primarily as a SQLite table rather than as a separate external vector database service. The `embeddings` table stores each vector as a binary blob, along with metadata needed to retrieve and interpret the vector.

For example, a 768-dimensional embedding may be stored as 768 floating-point values serialized into a `BLOB`. The application can deserialize this blob into a numeric array when performing similarity calculations.

This approach keeps the architecture self-contained. Spock does not require a separate vector database server, which simplifies deployment and reduces operational complexity.

#### Similarity Search Mechanics

When a user asks a question, Spock embeds the query using the same embedding model used for document chunks. The resulting query vector is then compared against stored vectors in the `embeddings` table.

Common similarity metrics include:

*   **Cosine similarity:** Measures the angle between two vectors and is useful when vector magnitude is less important than direction.
*   **Dot product:** Efficient when vectors are normalized; equivalent to cosine similarity for unit-length vectors.
*   **Euclidean distance, or L2 distance:** Measures the straight-line distance between two vectors in vector space.

A typical retrieval query returns the top-k most relevant chunks, where k is a configurable number such as 3, 5, or 10. Spock may also apply a minimum similarity threshold to avoid including weakly relevant context.

SQLite 3 does not provide a native vector index in the core database engine. Therefore, Spock may use one of the following approaches:

*   Application-level similarity search, where vectors are loaded and compared in Python.
*   A SQLite vector extension, such as `sqlite-vec`, if available in the deployment environment.
*   A companion in-memory index that is rebuilt or refreshed from the `embeddings` table.

The logical result is the same: Spock can retrieve semantically relevant chunks from `ship_computer.db` without requiring a separate vector database product.

#### Retrieval-Augmented Generation Flow

The embedding model and vector storage work together to support retrieval-augmented generation:

1.  Spock receives a user question.
2.  The question is embedded into a vector.
3.  The vector is compared against stored document and message embeddings.
4.  The most relevant chunks are selected.
5.  The selected chunks are inserted into a prompt template.
6.  The language model generates an answer using the retrieved context.
7.  The final answer and retrieval metadata are stored back in the database.

This integration allows Spock to perform fast, semantically aware retrieval while keeping the architecture local, self-contained, and performant.

### Conceptual Explanation

Conceptually, `ship_computer.db` acts as Spock’s persistent memory. It stores the facts, conversations, documents, and operational traces that allow the application to behave consistently across restarts.

The database can be understood in three layers:

*   **Conversation memory:** The `sessions` and `messages` tables preserve what the user asked, what Spock answered, and when those events occurred.
*   **Semantic memory:** The `documents` and `embeddings` tables preserve reference material and its vector representations, enabling meaning-based retrieval.
*   **Operational memory:** The `audit_logs` table, and optionally Deep Dive step tables, preserve the system’s internal actions, errors, tool calls, and reasoning state.

Ask AI uses this memory to answer questions by retrieving relevant context and grounding the language model’s response. Deep Dive uses the same memory more extensively, preserving intermediate steps, tool outputs, and branching decisions so that complex investigations can be resumed, inspected, and reproduced.

The embedding model is the bridge between human language and database retrieval. It converts text into numerical coordinates in a semantic space. The vector database, implemented through SQLite, stores those coordinates and enables Spock to find the most relevant text for a given query. Together, they allow Spock to combine local knowledge, conversational context, and language-model reasoning into a coherent AI experience.
*   **Persistence:** Unlike in-memory variables that are lost when the application restarts, `ship_computer.db` retains data until it is explicitly updated or deleted. This supports long-running AI sessions, repeated use of prior context, and seamless recovery after crashes or updates.
*   **Schema Evolution:** As features such as Ask AI and Deep Dive expand, the database schema may need to change. The application manages schema initialization and migrations in a controlled way using versioned migration scripts. This ensures that older databases remain compatible with newer application versions while preserving historical data integrity.
*   **Durable Storage:** Storing state in a file-backed SQLite database separates persistent data from transient Python objects. This helps preserve important context across process restarts while keeping the core application logic focused on behavior rather than storage details. The abstraction layer also enforces data validation and transaction safety, reducing the risk of corruption during concurrent AI operations.

## SQLite 3 `ship_computer.db`

`ship_computer.db` is the durable state store for the Spock application. It is a SQLite 3 database file that provides reliable, file-backed storage for application state, user context, AI session history, and metadata related to Ask AI and Deep Dive inquiries.

The database is designed to support the following responsibilities:

*   **Session continuity:** It preserves conversation context, user preferences, and prior AI interactions so that Spock can resume work after a restart.
*   **Auditability:** It records meaningful events, such as user questions, retrieved context, generated answers, and Deep Dive progress.
*   **Recovery:** It allows the application to recover from crashes, updates, or interrupted operations without losing important state.
*   **Schema control:** It supports versioned migrations so that the database can evolve as new features are introduced.
*   **Separation of concerns:** It stores durable application state while transient computation, model calls, and in-memory processing remain separate.

In this architecture, `ship_computer.db` is not primarily responsible for storing large-scale vector embeddings. Instead, it stores the durable records that describe what happened, what was requested, what was retrieved, and how the application should continue. The vector database is used for similarity search over embedded content, while SQLite stores the operational and historical state needed to make those interactions reproducible and resumable.

### Ask AI interaction

For Ask AI inquiries, `ship_computer.db` supports the full lifecycle of a user question and the system’s response.

A typical Ask AI flow works as follows:

1.  **Receive the question:** Spock receives an Ask AI request from the user.
2.  **Load context:** The application reads relevant session state from `ship_computer.db`, such as prior conversation turns, user preferences, and previously retrieved context.
3.  **Prepare the query:** Spock constructs a prompt or retrieval query using the user’s question and any available context.
4.  **Retrieve relevant information:** The application uses the embedding LLM and vector database to find relevant content.
5.  **Generate the answer:** Spock sends the retrieved context and user question to the AI model to produce a response.
6.  **Persist the result:** The question, retrieved references, generated answer, model metadata, and any relevant session updates are written back to `ship_computer.db`.

This persistence model allows Ask AI to behave consistently across restarts. If the application is restarted after a question has been asked, Spock can reload the prior context and continue the conversation without requiring the user to repeat themselves.

### Deep Dive interaction

Deep Dive inquiries are more complex than single-turn Ask AI requests. They may involve multiple retrieval steps, intermediate analysis, follow-up questions, and a final synthesized result.

For Deep Dive operations, `ship_computer.db` stores the durable state needed to track and resume the process. This may include:

*   The original Deep Dive request.
*   Intermediate subquestions or analysis steps.
*   Retrieved sources or context fragments.
*   Partial findings or working notes.
*   The final Deep Dive output.
*   Status information, such as whether the Deep Dive is pending, in progress, completed, or failed.

A typical Deep Dive flow works as follows:

1.  **Create a Deep Dive record:** Spock creates a durable record in `ship_computer.db` representing the new Deep Dive request.
2.  **Break the request into steps:** The application may decompose the request into subquestions, research tasks, or analysis stages.
3.  **Retrieve evidence:** For each step, Spock uses the embedding LLM and vector database to retrieve relevant content.
4.  **Accumulate findings:** Intermediate results, citations, and reasoning steps are stored in `ship_computer.db`.
5.  **Iterate if needed:** Spock may perform additional retrieval or analysis based on the evidence gathered so far.
6.  **Produce the final result:** Once enough context has been collected, Spock generates the final Deep Dive response.
7.  **Persist the completed result:** The final answer, supporting evidence, and completion status are written back to the database.

This design allows Deep Dive operations to be interrupted and resumed. If the application crashes or is restarted during a Deep Dive, Spock can reload the saved state and continue from the last completed step rather than starting over.

## Embedding LLM and Vector DB

The Spock application uses an embedding LLM and a vector database to retrieve relevant information for Ask AI and Deep Dive inquiries.

An **embedding LLM** is a model that converts text into a numerical vector representation. This vector captures the semantic meaning of the text in a way that can be compared mathematically. Similar meanings produce vectors that are close together in vector space, while unrelated meanings produce vectors that are farther apart.

A **vector database** stores these numerical vectors and supports efficient similarity search. When Spock needs to find relevant content, it does not rely only on keyword matching. Instead, it can search for content that is semantically similar to the user’s question or current analysis step.

### How Spock uses the embedding LLM

When a user submits an Ask AI or Deep Dive request, Spock uses the embedding LLM to transform the relevant text into a vector. This may include:

*   The user’s original question.
*   A reformulated search query.
*   A subquestion generated during a Deep Dive.
*   A summary of prior context.
*   A candidate passage that needs to be compared against other content.

The embedding LLM produces a dense vector that represents the meaning of that text. Spock then uses that vector to query the vector database.

### How Spock uses the vector database

The vector database stores embeddings for the content that Spock can search. This content may include documents, notes, prior answers, reference material, or other structured or unstructured data relevant to the application.

When Spock receives a vector from the embedding LLM, it sends it to the vector database for similarity search. The vector database returns the most similar stored vectors, along with their associated content or metadata.

This allows Spock to retrieve context that is semantically related to the user’s request, even if the exact words do not match.

### Ask AI retrieval flow

For Ask AI, the embedding and vector database workflow is typically straightforward:

1.  Spock receives the user’s question.
2.  Spock prepares the question for retrieval.
3.  The embedding LLM converts the question into a vector.
4.  Spock queries the vector database with that vector.
5.  The vector database returns the most relevant content.
6.  Spock combines the retrieved content with the user’s question.
7.  Spock sends the combined context to the AI model to generate an answer.
8.  Spock stores the question, retrieved context, and answer in `ship_computer.db`.

This approach improves answer quality by grounding the AI response in relevant retrieved information rather than relying only on the model’s internal knowledge.

### Deep Dive retrieval flow

For Deep Dive, the embedding and vector database workflow is iterative.

1.  Spock creates a Deep Dive task in `ship_computer.db`.
2.  Spock analyzes the request and identifies the information needed.
3.  Spock generates one or more retrieval queries.
4.  The embedding LLM converts each query into a vector.
5.  Spock queries the vector database for relevant content.
6.  Spock reviews the retrieved content and determines whether more information is needed.
7.  If needed, Spock generates additional queries and repeats the retrieval process.
8.  Spock accumulates evidence, findings, and intermediate results in `ship_computer.db`.
9.  Once sufficient context has been gathered, Spock generates the final Deep Dive response.
10. Spock persists the final result and supporting evidence.

This iterative process allows Deep Dive to handle complex questions that require multiple searches, comparisons, and synthesis steps.

### Relationship between `ship_computer.db`, the embedding LLM, and the vector database

The three components work together as follows:

*   **`ship_computer.db`** stores durable application state, session history, Deep Dive progress, and retrieval metadata.
*   **The embedding LLM** converts text into semantic vectors that can be used for similarity search.
*   **The vector database** stores those vectors and returns the most relevant content for a given query.

In simple terms:

*   The embedding LLM helps Spock understand what the user is asking for.
*   The vector database helps Spock find relevant content.
*   `ship_computer.db` helps Spock remember what happened and continue the work reliably.