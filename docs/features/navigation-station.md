# Navigation Station

The Navigation Station serves as Spock's initialization wizard. It automates the hardware bring-up process by detecting connected components, configuring the software environment, and launching necessary servers to ensure the system is ready for operation.

## Components

| Module | Role |
|--------|------|
| `NavigationStation.app` | Main application entry point that coordinates the initialization workflow |
| `NavigationStation.steps.configure` | Configuration step — sets up runtime settings, environment options, and required data structures |
| `NavigationStation.steps.hardware` | Hardware detection step — identifies connected hardware components and validates their availability |
| `NavigationStation.steps.launch` | Server launch step — starts required servers and services needed for operation |
| `NavigationStation.steps.status` | Status verification step — checks the status of launched services, hardware, and overall system readiness |

*Note: These modules represent distinct phases that execute sequentially during the initialization workflow.* The `NavigationApp` class coordinates this sequence, collects results from each phase, and reports whether the system is ready for use.

## Usage

To use the Navigation Station, you can either import and run the `NavigationApp` class in Python or execute it via the command line interface (CLI). Ensure your development environment is configured correctly before proceeding.

### Prerequisites

Before running the Navigation Station, verify that:

1. **Python Environment:** A virtual environment, for example `.venv`, is active or explicitly referenced by the interpreter path.
2. **Dependencies:** All required Python packages are installed within that environment.
3. **OS Compatibility:** Command paths and executable names may vary depending on your operating system. See the CLI usage examples below.

### Python Usage

```python
from NavigationStation.app import NavigationApp

app = NavigationApp()
app.run()
```

This snippet instantiates the `NavigationApp` class and triggers the initialization sequence defined in the components above. Execution typically proceeds through hardware detection, configuration, server launch, and status verification.

### CLI Usage

If you prefer using the command line, you can run the Navigation Station using the following command:

```powershell
.venv\Scripts\python.exe -m spock_bringup_menu
```

This command assumes that a Python virtual environment is located at `.venv`. The `-m` flag tells Python to execute `spock_bringup_menu` as a module entry point, which ultimately invokes the same initialization workflow used by `NavigationApp`.

**Note:** This example uses Windows PowerShell syntax, indicated by the backslash path separator. If you are on Linux or macOS, use the appropriate path separator and interpreter location. For example:

```bash
.venv/bin/python -m spock_bringup_menu
```

You may also activate your virtual environment first if your shell setup requires it.

## SQLite 3 Database: `ship_computer.db`

`ship_computer.db` is the local SQLite 3 database used by the Spock application to persist operational state, configuration data, hardware inventory, and AI-assisted inquiry records. It provides a lightweight, file-based relational store that is well suited to a single-node ship computer deployment where offline operation, low overhead, and transactional integrity are important.

The database is not primarily used to store large vector embeddings. Instead, it stores structured metadata, session history, configuration state, and references to content that may be indexed in a separate vector database.

### Purpose of `ship_computer.db`

The `ship_computer.db` database supports several core responsibilities:

- **System state tracking:** Stores the results of hardware detection, service launch, and readiness checks performed by the Navigation Station.
- **Configuration persistence:** Preserves runtime settings, environment options, and user-selected preferences.
- **Ask AI support:** Records user questions, assistant responses, retrieved context, citations, and session history.
- **Deep Dive support:** Stores multi-step investigation records, evidence items, intermediate findings, and final generated reports.
- **Auditability:** Provides a durable record of what the system detected, launched, queried, and generated.

### Relationship to the Spock Application

The Spock application interacts with `ship_computer.db` through Python’s SQLite support, either directly using the `sqlite3` module or through an ORM or data-access layer. The database acts as the system of record for structured application data.

For example:

- The Navigation Station may write hardware detection results and service status into the database.
- Ask AI may read configuration and document metadata, then write the user’s question and the generated answer.
- Deep Dive may create a session record, store each investigation step, and persist the final report.

This separation allows Spock to keep structured data in SQLite while using a vector database for semantic search over unstructured text.

### Representative Schema

The exact schema may vary by deployment, but a representative `ship_computer.db` schema includes the following data domains:

| Table | Purpose |
|-------|---------|
| `system_info` | Stores system identification, version, build, and deployment metadata |
| `hardware_components` | Stores detected hardware components, status, and validation results |
| `configuration` | Stores runtime settings, environment options, and user preferences |
| `services` | Stores launched services, expected state, and observed state |
| `documents` | Stores metadata for documents available to Ask AI and Deep Dive |
| `document_chunks` | Stores chunk-level metadata and references to vector database records |
| `ask_ai_sessions` | Stores Ask AI conversation sessions |
| `ask_ai_messages` | Stores individual user and assistant messages within an Ask AI session |
| `ask_ai_citations` | Stores source references used to support an Ask AI answer |
| `deep_dive_sessions` | Stores Deep Dive investigation sessions |
| `deep_dive_steps` | Stores individual steps, queries, findings, and evidence within a Deep Dive session |
| `deep_dive_reports` | Stores final generated Deep Dive reports and summaries |

### How `ship_computer.db` Supports Ask AI

Ask AI is the conversational query interface where a user asks a natural-language question and Spock returns an answer grounded in available system data, documents, or operational context.

The database supports Ask AI in the following ways:

1. **Session management**
   - Each Ask AI conversation is associated with a session record.
   - The session may store the user, timestamp, model settings, and active context.

2. **Message persistence**
   - User questions and assistant responses are stored as messages.
   - This allows Spock to maintain conversational context and support follow-up questions.

3. **Retrieval metadata**
   - When Ask AI retrieves relevant content, the database can store which documents or chunks were considered.
   - This supports transparency and debugging.

4. **Citation tracking**
   - If the answer is grounded in specific sources, the database can store citation records.
   - Citations may include document identifiers, chunk identifiers, page numbers, or vector database record identifiers.

5. **Configuration lookup**
   - Ask AI may read configuration values from the database, such as enabled data sources, retrieval limits, or model preferences.

A typical Ask AI data flow is:

1. The user submits a question.
2. Spock creates or updates an Ask AI session record.
3. Spock stores the user message.
4. Spock retrieves relevant context from the vector database and/or structured data.
5. Spock generates an answer using the retrieved context.
6. Spock stores the assistant response.
7. Spock stores citations, retrieval metadata, and any relevant provenance information.

### How `ship_computer.db` Supports Deep Dive

Deep Dive is a more investigative workflow than Ask AI. Instead of returning a single answer, Deep Dive may perform multiple retrieval steps, analyze related evidence, compare findings, and produce a structured report.

The database supports Deep Dive by storing the full investigation lifecycle:

1. **Session creation**
   - A Deep Dive session is created when the user starts an investigation.
   - The session stores the initial objective, scope, and relevant constraints.

2. **Step tracking**
   - Each Deep Dive step is stored as a separate record.
   - A step may represent a sub-question, a retrieval action, an analysis action, or a synthesis action.

3. **Evidence collection**
   - Relevant documents, chunks, logs, or structured records are associated with the session.
   - The database stores references to the evidence rather than duplicating large content.

4. **Finding persistence**
   - Intermediate findings, hypotheses, or summaries can be stored for later review.
   - This allows the application to resume or continue an investigation.

5. **Report generation**
   - The final Deep Dive report is stored in the database.
   - The report may include an executive summary, supporting evidence, citations, and confidence notes.

A typical Deep Dive data flow is:

1. The user defines an investigation objective.
2. Spock creates a Deep Dive session.
3. Spock breaks the objective into sub-questions or analysis steps.
4. For each step, Spock retrieves relevant content using the vector database and/or structured queries.
5. Spock stores the step, retrieved evidence, and intermediate findings.
6. Spock synthesizes the findings into a final report.
7. Spock stores the final report and associated citations.

### Division of Responsibility Between SQLite and the Vector Database

The SQLite database and the vector database serve different purposes.

| Concern | `ship_computer.db` | Vector Database |
|---------|--------------------|-----------------|
| Data type | Structured relational data | High-dimensional semantic vectors |
| Primary use | State, sessions, configuration, citations, reports | Semantic similarity search |
| Query style | SQL queries | Vector similarity queries |
| Content stored | Metadata and references | Embeddings and associated text chunks |
| Typical operations | Insert, update, select, join | Index, search, filter, rank |

In practice, Spock may use SQLite to store the identity of a document chunk and the vector database to store the embedding for that chunk. When a user asks a question, Spock can search the vector database for semantically similar chunks and then use SQLite to retrieve metadata, citations, and session context.

## Embedding LLM and Vector Database

Spock uses an embedding LLM and a vector database to enable semantic search over natural-language content. This allows Ask AI and Deep Dive to find relevant information based on meaning rather than only exact keyword matches.

### Role of the Embedding LLM

An embedding LLM is a language model that converts text into a numerical vector, also called an embedding. Each vector represents the semantic meaning of the text in a high-dimensional space.

For example:

- “What is the status of the navigation system?”
- “Is the nav system operational?”
- “Check navigation readiness.”

These phrases may not share many exact keywords, but an embedding model can represent them as vectors that are close to one another because they express a similar intent.

The embedding LLM is not the same as the answer-generation LLM. Its role is to produce vectors for search, not to generate natural-language responses.

### How Embeddings Are Created

The embedding process generally follows these steps:

1. **Text preparation**
   - Documents, logs, or other content are split into manageable chunks.
   - Chunking helps preserve context while keeping embeddings focused.

2. **Embedding generation**
   - Each chunk is passed to the embedding LLM.
   - The model returns a fixed-length vector.

3. **Normalization**
   - The vector may be normalized to improve similarity calculations.

4. **Storage**
   - The vector is stored in the vector database.
   - Metadata, such as document ID, chunk ID, source, and timestamp, is stored alongside the vector.

### Role of the Vector Database

The vector database stores embeddings and supports similarity search. It allows Spock to answer questions such as:

- “Which content is most relevant to this user question?”
- “Which chunks are semantically closest to this Deep Dive sub-question?”
- “Which evidence items support this finding?”

The vector database typically supports:

- **Cosine similarity**
- **Dot product similarity**
- **Euclidean distance**
- **Metadata filtering**
- **Top-k retrieval**
- **Batch indexing**

### Ask AI Retrieval Pipeline

When a user submits an Ask AI question, Spock uses the embedding LLM and vector database as part of the retrieval pipeline.

1. **Query embedding**
   - The user’s question is converted into a vector using the same embedding model used for the indexed content.

2. **Vector search**
   - Spock queries the vector database for the most similar content chunks.
   - The search may return the top-k results, where k is a configurable number.

3. **Metadata filtering**
   - Spock may filter results by document type, source, time range, access level, or other metadata.

4. **Reranking**
   - The retrieved chunks may be reranked using additional signals, such as keyword overlap, recency, or relevance scores.

5. **Context assembly**
   - The selected chunks are assembled into a prompt context for the answer-generation model.

6. **Answer generation**
   - The answer-generation LLM produces a response grounded in the retrieved context.

7. **Persistence**
   - The question, answer, retrieved chunks, and citations are stored in `ship_computer.db`.

### Deep Dive Retrieval Pipeline

Deep Dive uses the same embedding and vector search capabilities, but applies them iteratively across multiple investigation steps.

1. **Objective decomposition**
   - Spock breaks the user’s investigation objective into sub-questions or analysis tasks.

2. **Step-specific embedding**
   - Each sub-question is converted into an embedding vector.

3. **Targeted retrieval**
   - Spock searches the vector database for content relevant to that specific step.

4. **Evidence accumulation**
   - Retrieved chunks are stored as evidence in the Deep Dive session.

5. **Cross-step synthesis**
   - Spock compares findings across steps and identifies patterns, conflicts, or gaps.

6. **Report generation**
   - Spock generates a structured report using the accumulated evidence.

7. **Session persistence**
   - The full Deep Dive session, including steps, evidence, and final report, is stored in `ship_computer.db`.

### Why Both SQLite and a Vector Database Are Needed

SQLite provides reliable structured storage for application state and inquiry history. The vector database provides semantic search over unstructured text.

Together, they allow Spock to:

- Maintain durable session and configuration data.
- Search content by meaning rather than only keywords.
- Ground Ask AI answers in relevant evidence.
- Support Deep Dive investigations with multi-step retrieval and synthesis.
- Preserve citations and provenance for generated responses.
## Database Architecture and Data Interaction

The Spock application relies on a persistent data layer to maintain state between sessions and support advanced analytical features. This architecture is centered around the SQLite 3 database engine, specifically utilizing the `ship_computer.db` file for local storage.

### SQLite 3 Overview

* **Engine:** SQLite 3 serves as the primary relational database management system (RDBMS). It is a serverless, zero-configuration, transactional SQL database engine that operates directly on a single file.
* **Storage Location:** The database resides in a single file named `ship_computer.db`, typically located within the application's data directory or another path defined by deployment configuration.
* **Initialization:** The schema for this database is created and initialized during the `NavigationStation.steps.configure` phase of the initialization workflow. This process includes table creation, index generation, and insertion of any required seed data needed by subsequent operational steps.
* **Concurrency & Safety:** SQLite handles concurrent read operations efficiently and can be configured to use write-ahead logging (WAL) mode to improve data integrity and reduce lock contention during frequent application updates.

### `ship_computer.db` Schema and Operational Role

While the exact table definitions are managed dynamically during configuration, `ship_computer.db` logically organizes data into three primary domains:

1. **Session & Context Management:** Tracks active user sessions, conversation history, prompt templates, and AI response metadata. This enables stateful interactions without relying on external session stores.
2. **Knowledge & Reference Data:** Stores curated documents, system prompts, user preferences, and configuration overrides that the AI references during generation.
3. **Analytics & Task State:** Maintains records for long-running computational jobs, intermediate results, data lineage, and execution logs.

The application layer interacts with `ship_computer.db` through parameterized SQL queries and an ORM/DAO abstraction layer. All write operations are wrapped in transactions to guarantee ACID compliance, while read-heavy operations leverage indexed columns for fast retrieval.

In practice, `ship_computer.db` acts as the system of record for structured application state. It stores the information Spock needs to understand *what* the user is asking, *where* the relevant data came from, *which* session the request belongs to, and *how* previous operations were executed. This makes the database essential for both conversational continuity and reproducible analytical workflows.

### Interaction with Ask AI

The "Ask AI" feature utilizes `ship_computer.db` as a critical component of a Retrieval-Augmented Generation (RAG) workflow. The application layer queries relevant context from the database, then supplies that context to the LLM prompt. This ensures responses reflect stored preferences, prior interactions, and curated knowledge snippets without requiring the model itself to maintain persistent memory.

* **Context Storage:** The database stores user preferences, historical query logs, and indexed knowledge-base snippets. When a user submits a prompt, the application retrieves the most relevant historical context and system guidelines to construct a structured prompt.
* **Session Management:** Active sessions are tracked within the database using unique session identifiers. Follow-up questions automatically reference earlier context, maintaining conversational continuity and reducing redundant prompt engineering.
* **Asynchronous Logging & State Updates:** While the LLM generates responses in real time, the application updates `ship_computer.db` asynchronously. This logs interactions, updates session state, and preserves conversation history for future reference without blocking the user interface.
* **Prompt Assembly Pipeline:** Retrieved relational data is merged with vector search results and formatted into a structured prompt template before being sent to the inference engine.

For Ask AI, `ship_computer.db` provides the structured foundation for the request. It determines which session the prompt belongs to, which user preferences should influence the answer, which documents or knowledge entries are eligible for retrieval, and which prior messages should be included in the context window. The database does not generate the answer itself; instead, it supplies the trusted, queryable context that makes the generated response more accurate, personalized, and consistent.

### Interaction with Deep Dive

The "Deep Dive" feature leverages the database for complex data analysis, result caching, lineage tracking, and long-running task recovery.

* **Analytical Result Caching:** Intermediate results from computationally intensive queries are serialized and cached in the database. When similar analytical work is requested, the system checks for valid cached results before re-executing pipelines, significantly reducing latency and resource consumption.
* **Metadata & Lineage Tracking:** The schema includes tables that record query parameters, data transformation steps, model versions, and result provenance. This supports full reproducibility and auditability of "Deep Dive" sessions.
* **State Persistence & Recovery:** Unlike ephemeral server memory, critical state for long-running Deep Dive tasks is persisted in `ship_computer.db`. If the application restarts or encounters a transient failure, the system can resume analysis from the last checkpoint without data loss.
* **Query Optimization:** Frequently accessed analytical datasets are materialized as views or indexed tables, allowing the application to execute complex joins and aggregations efficiently.

In Deep Dive workflows, `ship_computer.db` is especially important because analytical tasks are often multi-step, resource-intensive, and time-sensitive. The database allows Spock to track the lifecycle of each analysis, preserve intermediate outputs, and reconstruct the exact sequence of operations that produced a result. This is critical for debugging, auditing, and resuming work after interruptions.

### Embedding LLM and Vector Database Integration

While `ship_computer.db` handles relational data, session state, and metadata, Spock employs a dedicated Embedding LLM and Vector Database to power semantic search and high-dimensional similarity matching. This hybrid architecture ensures both precise relational filtering and contextual semantic retrieval.

The Embedding LLM and Vector Database are separate from the generative LLM that produces natural-language answers. Their purpose is not to answer questions directly, but to transform text into numerical representations that can be compared by meaning rather than exact keyword match.

#### Embedding LLM Responsibilities

The Embedding LLM converts textual content into dense vector representations, commonly called embeddings. These vectors capture semantic meaning, allowing Spock to identify related concepts even when the wording differs.

For example, the phrases:

* "show me recent anomalies"
* "find unusual behavior from the last week"
* "what looked abnormal recently?"

may not share many exact keywords, but their embeddings can be close in vector space because they express similar intent.

Spock uses the Embedding LLM in several ways:

* **Query Embedding:** When a user submits an Ask AI or Deep Dive request, the application converts the user's prompt into an embedding vector.
* **Document Embedding:** Knowledge-base entries, reference documents, system notes, and analytical summaries are embedded during ingestion or indexing.
* **Semantic Matching:** The application compares the query embedding against stored embeddings to find the most semantically relevant content.
* **Context Selection:** The most relevant embedded items are retrieved and used to enrich the prompt sent to the generative LLM.

This allows Spock to understand intent, topic, and context more effectively than keyword-only search.

#### Vector Database Responsibilities

The Vector Database stores the high-dimensional embeddings produced by the Embedding LLM. It is optimized for similarity search, meaning it can quickly identify which stored vectors are closest to a given query vector.

The Vector Database typically stores:

* **Embedding Vectors:** Numeric representations of text content.
* **Document Metadata:** Identifiers, source references, timestamps, permissions, and content type.
* **Chunk References:** Pointers to the specific text segment that was embedded.
* **Index Structures:** Approximate nearest neighbor indexes that enable fast similarity search over large collections.

The Vector Database is not a replacement for `ship_computer.db`. Instead, it complements it. The relational database stores structured facts, session state, and operational metadata, while the vector database stores semantic representations used for meaning-based retrieval.

#### How Spock Uses the Embedding LLM and Vector Database in Ask AI

In Ask AI, the Embedding LLM and Vector Database support semantic retrieval of relevant context before the generative LLM produces a response.

A typical Ask AI flow works as follows:

1. **Prompt Intake:** The user submits a question or request.
2. **Session Lookup:** Spock identifies the active session in `ship_computer.db` and retrieves prior conversation context.
3. **Query Embedding:** The Embedding LLM converts the user's prompt into a vector representation.
4. **Vector Search:** Spock queries the Vector Database for the most semantically similar knowledge entries, documents, or prior responses.
5. **Relational Filtering:** Spock uses `ship_computer.db` to filter results based on session ownership, permissions, recency, document status, and user preferences.
6. **Context Ranking:** The application combines vector similarity scores with relational metadata to rank the most useful context.
7. **Prompt Assembly:** The selected context is inserted into a structured prompt template.
8. **Generation:** The generative LLM produces the final answer using the assembled context.
9. **Persistence:** The question, retrieved context, generated answer, and metadata are stored back in `ship_computer.db`.

This approach allows Ask AI to answer questions using both semantic understanding and structured application state. The vector database helps Spock find relevant meaning, while the relational database ensures the response is grounded in the correct session, permissions, and historical context.

#### How Spock Uses the Embedding LLM and Vector Database in Deep Dive

In Deep Dive, the Embedding LLM and Vector Database help Spock locate relevant analytical context, prior results, and related data sources before executing or resuming complex analysis.

A typical Deep Dive flow works as follows:

1. **Analysis Request:** The user requests a detailed investigation or analytical task.
2. **Task Initialization:** Spock creates or resumes a task record in `ship_computer.db`.
3. **Semantic Discovery:** The Embedding LLM converts the analysis request into a vector.
4. **Vector Retrieval:** The Vector Database returns related analytical summaries, prior Deep Dive results, reference documents, or data descriptions.
5. **Structured Validation:** Spock checks `ship_computer.db` to confirm that the retrieved items are valid, accessible, and relevant to the current task.
6. **Pipeline Planning:** The application uses the retrieved context to determine which datasets, transformations, or cached results should be used.
7. **Execution & Checkpointing:** As the analysis progresses, intermediate results and checkpoints are written to `ship_computer.db`.
8. **Result Enrichment:** Final results may be summarized, indexed, and embedded so future Deep Dive requests can retrieve them semantically.

This makes Deep Dive more efficient because Spock can reuse prior analytical work, discover related data sources, and avoid repeating expensive computations when semantically similar results already exist.

#### Hybrid Search and Ranking

Spock does not rely on vector search alone. Instead, it uses a hybrid retrieval strategy that combines semantic similarity with structured relational constraints.

The application may combine:

* **Vector Similarity:** Measures how closely the meaning of the query matches stored content.
* **Keyword Matching:** Captures exact terms, identifiers, or technical names that may be important.
* **SQL Filters:** Enforces session, permission, recency, status, and source constraints.
* **Metadata Scoring:** Prioritizes results based on document type, confidence, freshness, or user preference.

This hybrid approach improves accuracy because semantic search can find conceptually related content, while relational filtering ensures that only valid and authorized data is used.

#### Indexing and Synchronization

For the Embedding LLM and Vector Database to be useful, Spock must maintain an indexing pipeline that keeps semantic content synchronized with relational metadata.

The pipeline generally includes:

1. **Ingestion:** New documents, summaries, preferences, or analytical results are received.
2. **Chunking:** Long content is divided into meaningful segments suitable for embedding.
3. **Embedding:** Each chunk is converted into a vector by the Embedding LLM.
4. **Storage:** The vector and associated metadata are written to the Vector Database.
5. **Relational Sync:** The corresponding metadata, source identifiers, and access controls are stored in `ship_computer.db`.
6. **Invalidation:** When content is deleted, updated, or deauthorized, Spock removes or marks the corresponding vector entries as stale.

This synchronization is important because the Vector Database may contain semantically relevant content that is no longer valid, accessible, or current. `ship_computer.db` provides the authoritative relational state used to validate and filter vector search results.

#### Failure Handling and Fallback Behavior

Because the Embedding LLM and Vector Database are external dependencies, Spock should be designed to degrade gracefully if they are unavailable.

Possible fallback behaviors include:

* **Keyword-Only Search:** If vector search is unavailable, Spock can fall back to SQL-based keyword search over indexed text fields.
* **Cached Context:** Previously retrieved context may be reused if it is still valid according to `ship_computer.db`.
* **Reduced Personalization:** If session or preference data cannot be retrieved, Spock can still answer using general knowledge, but with less contextual accuracy.
* **Task Delay:** For Deep Dive workflows, semantic discovery may be deferred until the vector service is available, while structured task state remains recoverable from `ship_computer.db`.

This layered design ensures that the core application remains functional even when semantic retrieval is temporarily degraded.

#### Security and Privacy Considerations

Embeddings are numerical representations of text and are not directly human-readable, but they can still reveal semantic relationships if accessed improperly. For this reason, Spock should treat vector data with the same care as the source text.

Security controls may include:

* **Access Control:** Vector search results are filtered using permissions stored in `ship_computer.db`.
* **Session Isolation:** User-specific context is not exposed across sessions.
* **Metadata Protection:** Sensitive metadata is not embedded unnecessarily.
* **Audit Logging:** Retrieval and generation events are recorded in the relational database for review.
* **Data Lifecycle Management:** Stale, deleted, or unauthorized content is removed from both the vector index and relational stores.

#### Summary of the Hybrid Data Architecture

The Spock data architecture is intentionally hybrid:

* **`ship_computer.db`** provides structured, transactional, and authoritative application state.
* **The Embedding LLM** converts text into semantic vector representations.
* **The Vector Database** enables fast meaning-based retrieval over large collections of content.
* **The Generative LLM** produces natural-language responses using the retrieved context.

Together, these components allow Spock to support Ask AI and Deep Dive with both conversational continuity and analytical depth. The relational database ensures correctness, state, and auditability, while the embedding and vector layers enable semantic understanding and intelligent context discovery.
## Retrieval-Augmented Generation Architecture

* **Embedding Generation:** When documents, knowledge snippets, or user queries are ingested, the application passes them through a lightweight Embedding LLM, such as a fine-tuned transformer model. This model converts text into fixed-dimensional numerical vectors that capture semantic meaning, tone, and contextual relationships.

* **Vector Storage & Indexing:** Generated embeddings are stored in a specialized Vector Database optimized for high-dimensional data. The vector DB maintains an approximate nearest neighbor, or ANN, index, such as HNSW or IVF-PQ, to enable millisecond-scale similarity searches across large collections of vectors.

* **Hybrid Retrieval Workflow:**
  1. A user query is first embedded using the same embedding model used for document ingestion.
  2. The vector DB performs a similarity search to retrieve the top-K semantically relevant chunks.
  3. These results are cross-referenced with `ship_computer.db` to apply relational filters, such as user permissions, session context, document metadata, or recency constraints.
  4. The filtered and ranked results are injected into the LLM prompt alongside system instructions.

* **Synchronization & Consistency:** The application maintains a mapping table in `ship_computer.db` that links relational record IDs to their corresponding vector embeddings. This ensures that updates, deletions, or version changes in the relational database are accurately reflected in the vector index, preventing stale or orphaned embeddings.

* **Performance Optimization:** Embedding generation is batched and cached to avoid redundant model inference. The vector DB operates in memory for low-latency similarity queries, while `ship_computer.db` handles durable storage and transactional integrity. This separation of concerns allows Spock to scale efficiently under concurrent Ask AI and Deep Dive workloads.

## SQLite 3 `ship_computer.db`

`ship_computer.db` is the durable relational database used by the Spock application. It is implemented with SQLite 3 and serves as the system of record for structured application state, user context, permissions, document metadata, retrieval mappings, and audit information.

Unlike the vector database, `ship_computer.db` is not primarily used for semantic similarity search. Instead, it provides the relational context needed to make retrieval results safe, accurate, and relevant to the current user, session, and application mode.

### Primary Responsibilities

`ship_computer.db` is responsible for:

* Storing user accounts, roles, and permission scopes.
* Tracking active sessions and conversation state.
* Managing document, chunk, and knowledge-base metadata.
* Linking relational records to vector embeddings.
* Supporting Ask AI and Deep Dive workflows.
* Enforcing access control before content is sent to the LLM.
* Recording query history, citations, and audit events.
* Maintaining consistency between relational data and vector data.

### Core Table Concepts

The database may include tables such as:

* `users`
  * Stores user identity, role, and access level.
* `sessions`
  * Tracks active Ask AI or Deep Dive sessions.
* `documents`
  * Stores source documents, file paths, titles, owners, and status.
* `chunks`
  * Stores text fragments derived from documents.
* `embeddings_map`
  * Maps chunk or document IDs to vector IDs in the vector database.
* `permissions`
  * Defines which users or roles can access specific documents or knowledge areas.
* `query_log`
  * Records user queries, retrieval results, and response metadata.
* `deep_dive_state`
  * Stores intermediate context, selected sources, and investigation state for Deep Dive.
* `audit_events`
  * Records access, deletion, permission changes, and other sensitive operations.

### Relationship to the Vector Database

The vector database stores numerical embeddings and performs semantic similarity search. `ship_computer.db` stores the meaning, ownership, and lifecycle of the content behind those embeddings.

For example, a vector search may return a chunk that is semantically similar to a user query. Before that chunk is used in an LLM prompt, Spock checks `ship_computer.db` to confirm that:

* The user is allowed to access the chunk.
* The chunk belongs to an active document.
* The document has not been deleted or revoked.
* The chunk is not marked as deprecated.
* The chunk is relevant to the current session or Deep Dive context.
* The chunk should be included based on recency, priority, or source type.

This hybrid approach combines semantic relevance from the vector database with business rules and access control from SQLite.

## Ask AI Interaction

Ask AI is the conversational question-answering mode in Spock. It is designed for direct user questions that require grounded answers from available knowledge sources.

### Ask AI Workflow

1. The user submits a question through the Spock interface.
2. The application records the session and query in `ship_computer.db`.
3. The query is sent to the Embedding LLM to generate a query vector.
4. The vector database searches for the most semantically similar chunks.
5. Spock retrieves the corresponding relational metadata from `ship_computer.db`.
6. The application filters results based on permissions, document status, and session context.
7. The remaining chunks are ranked and formatted into a prompt.
8. The LLM generates an answer using the retrieved context.
9. The answer, citations, and query metadata are stored back in `ship_computer.db`.

### Why `ship_computer.db` Is Required for Ask AI

Ask AI cannot rely on vector similarity alone. A semantically relevant chunk may still be inaccessible, outdated, or inappropriate for the current user.

`ship_computer.db` ensures that Ask AI answers are:

* Permission-aware.
* Session-aware.
* Source-aware.
* Audit-ready.
* Consistent with the current state of the knowledge base.

## Deep Dive Interaction

Deep Dive is the investigative mode in Spock. It is designed for multi-step exploration, where the application may perform repeated retrieval, compare sources, build context, and maintain a working investigation state.

### Deep Dive Workflow

1. The user starts a Deep Dive session.
2. Spock creates or resumes a session record in `ship_computer.db`.
3. The user provides a topic, question, or investigation goal.
4. The application performs one or more vector similarity searches.
5. Each retrieval result is validated against relational metadata in `ship_computer.db`.
6. Relevant chunks are added to the Deep Dive context.
7. The application may perform follow-up searches based on newly discovered concepts.
8. The LLM synthesizes findings, identifies gaps, and proposes next steps.
9. The session state, selected sources, and intermediate conclusions are persisted in `ship_computer.db`.

### Deep Dive State Management

Deep Dive requires more persistent state than Ask AI. `ship_computer.db` may store:

* The original investigation goal.
* Previously retrieved chunks.
* Chunks selected for the current context.
* Chunks excluded due to permissions or low relevance.
* Intermediate summaries.
* Follow-up questions generated by the application.
* Source citations.
* User feedback on retrieved results.

This allows Deep Dive to resume later, continue from a previous point, or branch into related investigations without losing context.

## Embedding LLM and Vector Database Workflow

The Embedding LLM and vector database work together to enable semantic retrieval. The Embedding LLM converts text into numerical vectors, while the vector database stores those vectors and finds the most similar ones to a query.

### Embedding LLM Role

The Embedding LLM is responsible for transforming natural language into a numerical representation that can be compared mathematically.

It is used for:

* Document chunks.
* Knowledge snippets.
* User queries.
* Deep Dive follow-up prompts.
* Cached or precomputed semantic representations.

A good embedding model should preserve semantic relationships so that similar concepts produce vectors that are close together in vector space.

### Vector Database Role

The vector database is responsible for:

* Storing embeddings.
* Maintaining an ANN index.
* Performing fast similarity search.
* Returning the top-K most relevant vectors.
* Supporting metadata filtering where applicable.

The vector database is optimized for speed and scale. It is not the primary source of truth for permissions, document lifecycle, or application state.

### Hybrid Retrieval in Spock

Spock uses a hybrid retrieval model because neither semantic search nor relational filtering alone is sufficient.

The vector database answers the question:

> What content is semantically similar to the user's request?

`ship_computer.db` answers the question:

> Is this content allowed, current, relevant, and appropriate for this user and session?

Together, they produce retrieval results that are both semantically relevant and operationally safe.

## Consistency and Data Lifecycle

Because Spock uses both a relational database and a vector database, the application must keep the two stores consistent.

### Embedding Mapping

Each chunk or document in `ship_computer.db` should have a corresponding vector ID in the vector database. This mapping allows Spock to:

* Locate the vector for a given chunk.
* Delete the vector when a chunk is removed.
* Replace the vector when a chunk is updated.
* Rebuild indexes after bulk changes.
* Audit which vector records belong to which relational records.

### Update Handling

When a document or chunk is updated, Spock should:

1. Update the relational record in `ship_computer.db`.
2. Generate a new embedding for the updated text.
3. Replace or insert the new vector in the vector database.
4. Update the mapping table.
5. Record the change in the audit log.

### Deletion Handling

When a document or chunk is deleted, Spock should:

1. Mark or remove the relational record in `ship_computer.db`.
2. Remove or tombstone the corresponding vector in the vector database.
3. Update the mapping table.
4. Ensure the deleted content is no longer returned in Ask AI or Deep Dive results.

### Permission Changes

When permissions change, Spock does not necessarily need to regenerate embeddings. Instead, it updates the relational permission records in `ship_computer.db`. Future retrieval results are filtered using the updated permissions before being sent to the LLM.

## Performance and Scalability

The architecture separates semantic search from relational governance.

* The vector database provides fast similarity search.
* The Embedding LLM provides semantic encoding.
* `ship_computer.db` provides durable, transactional, and permission-aware state.
* The Python application coordinates retrieval, filtering, prompt construction, and persistence.

This design allows Spock to handle concurrent Ask AI and Deep Dive workloads while maintaining accurate, auditable, and permission-safe responses.