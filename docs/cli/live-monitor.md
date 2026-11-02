# spock_live_monitor

Real-time monitoring dashboard for server health and resource usage.

## Usage

### Prerequisites

Ensure that you have created a virtual environment named `.venv` and installed the `spock_live_monitor` package within it. While activating the virtual environment is recommended, it is not strictly required if you invoke the Python interpreter directly using the path below.

```console
.venv\Scripts\python.exe -m spock_live_monitor
```

**Note:** The command above is specific to Windows environments. On macOS or Linux, use the corresponding interpreter path:

```console
.venv/bin/python -m spock_live_monitor
```

When execution starts successfully, the dashboard automatically opens in your default web browser. If you are using a differently named virtual environment, replace `.venv` with the actual path to that environment.

Running the command launches `spock_live_monitor` as a Python module. The `-m` flag instructs Python to execute the package's entry point, which initializes the monitoring dashboard, establishes connections to the local database, and begins real-time data polling.

## Local Database: `ship_computer.db`

`ship_computer.db` is a SQLite 3 database that serves as the local persistence layer for `spock_live_monitor` and the broader Spock application. It stores monitoring data, system events, user interactions, and metadata required for AI-assisted analysis.

Because SQLite is embedded and file-based, the database can be accessed directly by the Python application without requiring a separate database server. This makes it well suited for local dashboards, lightweight analytics, and offline or semi-offline AI workflows.

### Purpose

The `ship_computer.db` database is used to:

- Store real-time and historical server health metrics.
- Record system events, alerts, and diagnostic messages.
- Preserve context for Ask AI and Deep Dive inquiries.
- Support semantic search by linking text content to vector embeddings.
- Maintain session history for AI-generated responses.
- Provide a consistent source of truth for dashboard visualizations and analysis.

### Expected Data Model

The exact schema may vary by deployment, but a typical `ship_computer.db` database includes tables such as the following:

| Table | Purpose |
|---|---|
| `hosts` | Stores monitored server or device identities, such as hostname, IP address, OS, and status. |
| `metrics` | Stores time-series measurements such as CPU usage, memory usage, disk usage, network throughput, and temperature. |
| `events` | Stores alerts, warnings, errors, and operational events. |
| `ai_sessions` | Tracks Ask AI and Deep Dive conversation sessions. |
| `ai_messages` | Stores user questions, system prompts, and AI responses. |
| `documents` | Stores text content that can be embedded, such as logs, runbooks, metric descriptions, or diagnostic notes. |
| `embeddings` | Stores vector embeddings or references to vectors used for semantic search. |

A simplified example of the core tables is shown below.

```sql
CREATE TABLE hosts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    ip_address TEXT,
    os TEXT,
    status TEXT,
    last_seen_at TEXT
);

CREATE TABLE metrics (
    id INTEGER PRIMARY KEY,
    host_id INTEGER NOT NULL,
    metric_name TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT,
    collected_at TEXT NOT NULL,
    FOREIGN KEY (host_id) REFERENCES hosts(id)
);

CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    host_id INTEGER,
    severity TEXT,
    message TEXT,
    created_at TEXT,
    FOREIGN KEY (host_id) REFERENCES hosts(id)
);

CREATE TABLE ai_sessions (
    id INTEGER PRIMARY KEY,
    mode TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE ai_messages (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES ai_sessions(id)
);

CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    source_type TEXT,
    source_id INTEGER,
    title TEXT,
    body TEXT,
    created_at TEXT
);

CREATE TABLE embeddings (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL,
    model_name TEXT,
    vector BLOB,
    created_at TEXT,
    FOREIGN KEY (document_id) REFERENCES documents(id)
);
```

### SQLite 3 Characteristics

The application relies on several SQLite 3 features:

- **Embedded storage:** The database is stored as a local file, reducing deployment complexity.
- **ACID transactions:** Writes remain consistent even if the application crashes or a query fails.
- **Read concurrency:** Multiple dashboard readers can query the database while a writer updates new metrics.
- **WAL mode:** If enabled, Write-Ahead Logging improves read/write concurrency and reduces locking contention.
- **Simple querying:** SQL queries allow the dashboard and AI features to retrieve filtered, aggregated, and time-bounded data.

### Interaction with the Spock Application

The Spock application uses `ship_computer.db` as the primary local data source for both dashboard rendering and AI-assisted analysis.

For the live dashboard, the application typically:

1. Opens a SQLite connection to `ship_computer.db`.
2. Queries recent metrics and events.
3. Aggregates data for charts, tables, and status indicators.
4. Polls for new rows or changed values at a configured interval.
5. Updates the browser dashboard with the latest information.

For Ask AI and Deep Dive, the application uses the same database to build context. Instead of asking the LLM to answer from general knowledge alone, Spock retrieves relevant local records from `ship_computer.db` and includes them in the prompt. This grounds the AI response in actual system data.

## Ask AI and Deep Dive Inquiries

Ask AI and Deep Dive are two related but distinct AI-assisted analysis modes in the Spock application.

### Ask AI

Ask AI is intended for quick, conversational questions about the monitored environment.

Examples include:

- “Which host has the highest CPU usage right now?”
- “Are there any recent disk warnings?”
- “Summarize the last hour of memory usage.”
- “What changed on this server in the last 15 minutes?”

When a user submits an Ask AI question, the Spock application generally performs the following steps:

1. **Receive the user question.**
   The question is captured from the dashboard UI and associated with an AI session.

2. **Identify relevant data scope.**
   The application determines which hosts, time ranges, metric types, or event severities are likely relevant.

3. **Query `ship_computer.db`.**
   SQL queries retrieve recent metrics, events, host metadata, or related documents.

4. **Retrieve semantic context.**
   The question is embedded and compared against stored embeddings to find semantically relevant text, such as logs, runbooks, metric descriptions, or previous diagnostics.

5. **Build the LLM prompt.**
   The application combines:
   - The user question.
   - Retrieved SQL results.
   - Retrieved semantic context.
   - System instructions for tone, safety, and formatting.

6. **Generate the response.**
   The LLM returns a concise answer based on the provided context.

7. **Store the interaction.**
   The question, retrieved context, and response are saved to `ai_sessions` and `ai_messages` for auditability and future reference.

Ask AI is optimized for speed and simplicity. It usually retrieves a limited amount of context and produces a direct answer.

### Deep Dive

Deep Dive is intended for more detailed, multi-step analysis.

Examples include:

- “Investigate why host A degraded over the last two hours.”
- “Compare CPU, memory, and disk behavior across all hosts during the incident window.”
- “Identify possible root causes for repeated network timeouts.”
- “Generate a diagnostic report for the last 24 hours.”

Deep Dive uses the same local database but performs broader analysis.

The typical Deep Dive workflow is:

1. **Parse the analysis request.**
   The application interprets the user’s goal, such as root-cause analysis, trend comparison, or incident summary.

2. **Determine the analysis window.**
   The application selects a relevant time range, such as the last hour, last 24 hours, or a user-specified period.

3. **Retrieve structured data.**
   It queries `ship_computer.db` for:
   - Host metadata.
   - Metric trends.
   - Event sequences.
   - Threshold breaches.
   - Correlated changes across hosts or services.

4. **Retrieve unstructured context.**
   It uses semantic search to find relevant logs, notes, runbooks, or previous AI responses.

5. **Perform intermediate analysis.**
   The application may calculate:
   - Averages.
   - Percentiles.
   - Rate of change.
   - Correlation between metrics.
   - Time alignment between events and metric spikes.

6. **Compose a structured prompt.**
   The prompt includes the analysis goal, retrieved data, intermediate findings, and instructions for producing a detailed report.

7. **Generate the Deep Dive report.**
   The LLM produces a structured explanation, often including:
   - Summary.
   - Observed symptoms.
   - Likely contributing factors.
   - Recommended next steps.
   - Confidence notes or limitations.

8. **Persist the result.**
   The full Deep Dive session, including intermediate data and final report, is stored in the database.

Deep Dive is more computationally intensive than Ask AI because it may retrieve more data, perform more analysis, and generate a longer response.

## Embedding LLM and Vector Database

The Spock application uses an embedding LLM and a vector database to support semantic search. This allows the application to find relevant information based on meaning rather than exact keyword matching.

### What Is an Embedding LLM?

An embedding LLM is a model that converts text into a numerical vector, also called an embedding.

For example:

```text
"CPU usage spiked during the backup window"
```

may be converted into a vector such as:

```text
[0.12, -0.45, 0.87, 0.03, ...]
```

The vector represents the semantic meaning of the text in a high-dimensional space. Text with similar meaning produces vectors that are close to each other, while unrelated text produces vectors that are farther apart.

Embeddings are useful because they allow the application to answer questions such as:

- Which logs are semantically related to this user question?
- Which runbook entries match this incident pattern?
- Which previous AI responses are similar to the current request?
- Which metric descriptions are relevant to this diagnostic query?

### What Is a Vector Database?

A vector database stores embeddings and their associated metadata. It is optimized for similarity search, meaning it can quickly find the most relevant vectors for a given query vector.

In the Spock application, the vector database may be:

- A separate vector database service.
- A local vector store.
- A SQLite extension such as `sqlite-vec`.
- A file-based vector index maintained by the application.

The exact implementation may vary, but the role is the same: store embeddings and retrieve the most semantically similar records.

### How Embeddings Are Created

The Spock application creates embeddings for text content that may be useful during Ask AI or Deep Dive.

Typical sources include:

- Server logs.
- Event messages.
- Metric descriptions.
- Runbooks.
- Diagnostic notes.
- Previous AI responses.
- User questions.

The process is:

1. **Select text content.**
   The application identifies text that should be searchable.

2. **Chunk the text.**
   Long documents are split into smaller passages so that retrieval is more precise.

3. **Generate embeddings.**
   Each chunk is passed to the embedding LLM, producing a vector.

4. **Store the vector and metadata.**
   The vector is stored in the vector database along with metadata such as:
   - Source type.
   - Source ID.
   - Host ID.
   - Timestamp.
   - Title.
   - Original text.

5. **Index for similarity search.**
   The vector database indexes the embeddings so future queries can be answered quickly.

### How the Spock Application Uses the Vector Database

When a user asks a question, the Spock application uses the vector database to retrieve relevant context.

The workflow is:

1. **Embed the user question.**
   The question is converted into a vector using the same embedding model used for stored content.

2. **Search for similar vectors.**
   The vector database finds the closest matching embeddings.

3. **Retrieve associated text.**
   The application loads the original text chunks and metadata linked to those vectors.

4. **Rank and filter results.**
   Results may be filtered by:
   - Host.
   - Time range.
   - Severity.
   - Source type.
   - Relevance score.

5. **Include context in the LLM prompt.**
   The retrieved text is added to the prompt so the LLM can answer using relevant local information.

### Why Semantic Search Is Needed

SQL queries are excellent for structured data, such as:

```sql
SELECT value
FROM metrics
WHERE host_id = 1
  AND metric_name = 'cpu_percent'
  AND collected_at >= '2026-06-15 10:00:00';
```

However, many useful pieces of information are unstructured, such as:

- Free-form log messages.
- Incident notes.
- Runbook instructions.
- Previous diagnostic explanations.

Keyword search may miss relevant text if the wording differs. For example, a user may ask:

```text
Why did the server slow down?
```

while the relevant log says:

```text
High I/O wait observed during database checkpoint.
```

Semantic search can connect these concepts because their embeddings are closer in meaning than a simple keyword match would suggest.

### Relationship Between `ship_computer.db` and the Vector Database

The SQLite database and vector database work together:

| Component | Responsibility |
|---|---|
| `ship_computer.db` | Stores structured monitoring data, events, sessions, messages, and source text. |
| Embedding LLM | Converts text into numerical vectors. |
| Vector database | Stores vectors and performs similarity search. |
| Spock application | Coordinates retrieval, prompt construction, and response generation. |

In some deployments, the vector embeddings may be stored directly inside `ship_computer.db` using a SQLite vector extension. In other deployments, the vectors may be stored in a separate vector database while `ship_computer.db` remains the source of truth for structured data and text content.

### Example Ask AI Flow with Embeddings

Suppose the user asks:

```text
Why is host-01 using so much memory?
```

The Spock application may:

1. Query `ship_computer.db` for recent memory metrics on `host-01`.
2. Query recent events related to `host-01`.
3. Embed the user question.
4. Search the vector database for similar text, such as:
   - Memory leak warnings.
   - Process growth logs.
   - Swap usage notes.
   - Previous AI explanations.
5. Combine the structured metrics and semantic context into a prompt.
6. Ask the LLM to explain the likely cause.
7. Store the question and answer in `ai_sessions` and `ai_messages`.

### Example Deep Dive Flow with Embeddings

Suppose the user asks:

```text
Investigate the performance degradation on host-01 over the last six hours.
```

The Spock application may:

1. Retrieve CPU, memory, disk, and network metrics for the last six hours.
2. Retrieve all events for `host-01` in that window.
3. Calculate trends and identify spikes.
4. Embed the request and retrieve semantically related logs or notes.
5. Compare metric changes with event timestamps.
6. Generate a structured diagnostic report.
7. Save the full analysis to the database.

## Summary

`spock_live_monitor` provides a real-time dashboard for server health and resource usage. It uses a local SQLite 3 database, `ship_computer.db`, to store monitoring data, events, AI sessions, and searchable text content.

The Spock application extends this local data with AI-assisted features:

- **Ask AI** provides quick, context-aware answers.
- **Deep Dive** provides detailed, multi-step analysis.
- The **embedding LLM** converts text into semantic vectors.
- The **vector database** enables similarity search over logs, notes, runbooks, and previous AI context.

Together, these components allow the Spock application to combine structured monitoring data with semantic understanding, producing more accurate and useful AI responses.
## Database Architecture

### SQLite 3 Integration (`ship_computer.db`)

The Spock application uses a local SQLite 3 database file named `ship_computer.db` to persist critical data required for AI-driven interactions. SQLite 3 is a lightweight, embedded, file-based relational database engine that stores all data in a single cross-platform file. This architecture eliminates the need for external database servers, making it ideal for local deployments, development environments, and self-contained monitoring agents.

The database serves as the central repository for system telemetry, interaction logs, and contextual metadata used by the **Ask AI** and **Deep Dive** modules. It is initialized automatically on first run, with the Spock backend handling schema creation, versioning, and migration without manual intervention. If `ship_computer.db` already exists, the application opens the existing file and preserves historical state.

#### Schema Overview & Data Lifecycle
The database is organized into logical tables that track system performance and AI interaction history:
- **`system_metrics`**: Stores time-series data for CPU, memory, disk I/O, network throughput, and process states. Records are inserted at configurable intervals and indexed by timestamp for efficient range queries.
- **`interaction_logs`**: Captures user prompts, AI responses, session IDs, latency metrics, and retrieval metadata. This table enables audit trails, conversation continuity, and post-hoc analysis of AI behavior.
- **`context_cache`**: Holds precomputed system snapshots, recent event summaries, and frequently used prompt context to reduce redundant database scans during AI generation.
- **`vector_metadata`**: Maps embedding vectors to their source documents, timestamps, semantic tags, and source identifiers in `ship_computer.db` (used in conjunction with the vector database).

SQLite operates in Write-Ahead Logging (WAL) mode by default within Spock, allowing concurrent read operations from the dashboard and AI modules while writes are safely queued. Data retention policies automatically archive or prune records older than a configurable threshold to prevent unbounded file growth.

#### Interaction Flow
1. **Ask AI Inquiries:** When a user submits a natural language question via the dashboard or REST API, Spock executes targeted `SELECT` queries against `ship_computer.db` to retrieve recent system states, active alerts, and relevant conversation history. This contextual payload is injected into the AI prompt, enabling precise, environment-aware responses rather than generic documentation outputs.
2. **Deep Dive Analysis:** For complex diagnostic requests, the application triggers analytical queries that aggregate historical metrics using window functions and time-bucketing. Spock joins `system_metrics` with `interaction_logs` to correlate performance degradation with specific events or configuration changes. Results are formatted into structured reports and visualizations before being returned to the user.

Because `ship_computer.db` contains persistent application state and diagnostic history, it should be treated as critical local data. Regular backups are recommended when long-term retention or disaster recovery is required.

#### Ask AI Data Access Patterns
Ask AI is optimized for low-latency, context-aware answers. Spock typically performs the following database operations:
- Retrieve the most recent system metrics for the current host or selected time window.
- Load active alerts, recent errors, and notable process changes.
- Fetch the current session's conversation history to preserve context.
- Query `context_cache` for precomputed summaries that can be reused without recalculating expensive aggregations.
- Record the user prompt, retrieved context identifiers, generated response, and latency in `interaction_logs`.

These queries are intentionally narrow and index-friendly. They provide the generative LLM with a concise, factual snapshot of the environment while avoiding large, unfiltered result sets.

#### Deep Dive Data Access Patterns
Deep Dive is optimized for analytical investigation. Spock may execute longer-running queries that:
- Aggregate CPU, memory, disk, and network metrics over minutes, hours, or days.
- Identify anomalies using rolling averages, percentiles, or threshold comparisons.
- Correlate metric changes with application events, configuration changes, or user-reported issues.
- Join `system_metrics`, `interaction_logs`, and `context_cache` to build a chronological diagnostic narrative.
- Store intermediate summaries in `context_cache` so repeated Deep Dive requests can reuse computed results.

The output is not limited to a single answer. It may include ranked findings, time-series summaries, affected components, and recommended follow-up questions.

#### Concurrency, Integrity, and Operational Considerations
SQLite 3 provides transactional integrity for local writes, but Spock still enforces application-level safeguards:
- Read-heavy dashboard queries use short-lived connections and prepared statements.
- Write operations are batched where possible to reduce file contention.
- Schema migrations are applied inside transactions when supported, with fallback to safe incremental steps.
- Retention jobs run outside the main request path to avoid blocking user interactions.
- The database file is treated as a local artifact; it is not designed for multi-host concurrent writes unless an external synchronization or replication strategy is added.

### Embedding LLM and Vector Database Integration

To enable semantic understanding and rapid retrieval of unstructured data, Spock integrates an embedding model (often referred to as an embedding LLM) with a dedicated vector database. This pipeline powers the retrieval-augmented generation (RAG) workflow used by both Ask AI and Deep Dive modules.

#### Embedding Generation Process
1. **Text Chunking:** Raw logs, system documentation, metric descriptions, and historical AI responses are normalized and split into semantically coherent chunks. Chunk boundaries are optimized to preserve context while staying within the embedding model's token limits.
2. **Vectorization:** Each chunk is passed through the embedding model, which converts the text into a high-dimensional dense vector (typically 768–1536 dimensions). These vectors numerically represent the semantic meaning of the source text, independent of exact keyword matching.
3. **Indexing & Storage:** The generated vectors are stored in the vector database alongside metadata pointers back to `ship_computer.db`. The vector store maintains an approximate nearest neighbor (ANN) index (e.g., HNSW or IVF-PQ) to enable fast similarity searches across large collections of records.

#### Query Resolution & Context Retrieval
When a user initiates an inquiry, Spock follows a deterministic retrieval pipeline:
1. **Prompt Embedding:** The user's natural language question is processed by the same embedding model to generate a query vector.
2. **Similarity Search:** The vector database computes cosine similarity or inner product distances between the query vector and stored document vectors. It returns the top-*k* most relevant chunks based on a configurable similarity threshold.
3. **Context Assembly:** Retrieved chunks are ranked, deduplicated, and filtered by recency and relevance. The resulting context window is formatted into a structured prompt template.
4. **AI Generation:** The enriched prompt is sent to the generative LLM, which synthesizes a response grounded in the retrieved system data. For **Deep Dive** requests, the pipeline may execute multiple parallel vector searches across different semantic domains (e.g., network logs, CPU throttling events, disk latency spikes) and merge the results before generation.

This architecture ensures that AI responses are dynamically grounded in real-time and historical system data, reducing hallucination and improving diagnostic accuracy. The vector database operates independently of SQLite's relational engine but synchronizes metadata references to maintain data consistency across the Spock ecosystem.

#### Embedding Model Responsibilities
The embedding model is not responsible for generating natural language answers. Its role is to transform text into numerical representations that can be compared by similarity. In Spock, it is used for:
- Converting system logs, documentation, metric descriptions, and prior interactions into searchable vectors.
- Converting user questions into query vectors.
- Enabling semantic matching between a user's intent and stored technical context.

Because the embedding model and the generative LLM are separate components, Spock can use a smaller, faster embedding model for retrieval while using a larger generative model for answer synthesis.

#### Vector Database Responsibilities
The vector database is responsible for storing, indexing, and retrieving high-dimensional vectors at scale. In Spock, it provides:
- Persistent storage for embedding vectors and associated metadata.
- Fast approximate nearest neighbor search using ANN indexes.
- Filtering by metadata such as timestamp, source type, host, session, or semantic tag.
- Support for hybrid retrieval, where vector similarity can be combined with keyword or structured filters.
- Isolation from SQLite's relational storage, allowing vector workloads to scale independently.

The vector database does not replace `ship_computer.db`. Instead, it complements it by making unstructured and semi-structured content searchable by meaning rather than by exact table columns or SQL predicates.

#### RAG Pipeline Sequence
A typical Spock RAG request proceeds as follows:
1. The user submits a question through Ask AI or Deep Dive.
2. Spock normalizes the prompt and extracts any explicit filters, such as time range, host, or component.
3. The embedding model converts the prompt into a query vector.
4. The vector database searches for the most relevant stored chunks.
5. Spock retrieves the corresponding source records from `ship_computer.db` using metadata pointers.
6. The retrieved context is ranked, deduplicated, and trimmed to fit the generative model's context window.
7. The generative LLM produces an answer grounded in the assembled context.
8. The final response, retrieved context identifiers, and performance metrics are written back to `interaction_logs`.

This sequence allows Spock to combine structured telemetry from SQLite with semantic retrieval from the vector database.

#### Consistency, Caching, and Failure Handling
Spock treats the SQLite database and vector database as complementary stores with different consistency requirements:
- `ship_computer.db` is the source of truth for structured telemetry, interaction history, and application state.
- The vector database is a derived index over selected content and may be rebuilt or refreshed when source data changes.
- If a vector search fails, Spock can fall back to structured SQL queries against `ship_computer.db` to provide a degraded but still useful response.
- If the generative LLM is unavailable, Spock can return the retrieved context, diagnostic summary, or structured report directly.
- Metadata synchronization ensures that deleted or expired records in SQLite are not surfaced as stale context by the vector database.
## Module Reference

::: spock_live_monitor

The `spock_live_monitor` module provides functionality for real-time monitoring of server health and resource usage. It includes components for data collection, visualization, and user interface rendering. The directive above generates an API reference from the package's public documentation strings. That reference lists exposed classes, functions, parameters, return values, and examples where available.

## SQLite 3 Database: `ship_computer.db`

`ship_computer.db` is the local SQLite 3 database used by the Spock application to store operational state, telemetry, event history, and AI-assisted inquiry context. It is designed to be lightweight, portable, and suitable for embedded or edge deployments where a full database server is not required.

### Role in the Spock Application

The Spock application uses `ship_computer.db` as its primary local persistence layer. The database supports three main responsibilities:

1. **Telemetry storage**  
   The application writes normalized server health and resource usage data into the database so that historical trends can be analyzed.

2. **Event and alert tracking**  
   Significant operational events, such as threshold breaches, service restarts, or configuration changes, are recorded for later review and AI-assisted analysis.

3. **AI inquiry context**  
   When a user submits an **Ask AI** or **Deep Dive** request, the Spock application queries the database to retrieve relevant records, historical patterns, and previously generated insights.

### Core Tables

The following tables represent the primary data structures used by the Spock application.

| Table | Purpose |
|---|---|
| `hosts` | Stores monitored server or node identifiers, metadata, and status. |
| `metrics` | Stores time-series resource usage data such as CPU, memory, disk, and network utilization. |
| `events` | Stores discrete operational events, alerts, and state changes. |
| `ai_queries` | Stores user questions submitted through the Ask AI feature. |
| `ai_responses` | Stores generated answers, confidence metadata, and retrieval context. |
| `deep_dive_sessions` | Stores multi-step Deep Dive investigations and their lifecycle state. |
| `deep_dive_steps` | Stores individual analysis steps, retrieved evidence, and intermediate conclusions. |
| `embeddings` | Stores vector embeddings generated by the embedding LLM for semantic search. |

### Data Flow

The interaction between the Spock application and `ship_computer.db` follows a consistent read/write pattern:

1. **Collection**  
   The `spock_live_monitor` module collects server health and resource usage data.

2. **Normalization**  
   Raw telemetry is normalized into a consistent schema before being written to the database.

3. **Persistence**  
   Normalized records are inserted into `metrics`, `events`, or related tables.

4. **Retrieval**  
   The user interface and AI features query the database to display current state, historical trends, and relevant context.

5. **AI Context Assembly**  
   For Ask AI and Deep Dive requests, the application combines structured database records with semantic search results to build a prompt for the language model.

## Ask AI and Deep Dive Inquiries

The Spock application provides two AI-assisted inquiry modes: **Ask AI** and **Deep Dive**. Both modes use `ship_computer.db`, the embedding LLM, and the vector database, but they differ in scope and depth.

### Ask AI

**Ask AI** is intended for direct, single-turn questions about the current or recent state of the monitored system.

Example questions include:

- “Why is CPU usage high on host A?”
- “What changed in the last hour?”
- “Which service is consuming the most memory?”

The Ask AI workflow is as follows:

1. The user submits a natural-language question.
2. The Spock application records the question in `ai_queries`.
3. The embedding LLM converts the question into a vector embedding.
4. The vector database searches for semantically similar records, such as past questions, events, metrics summaries, or documented issues.
5. The application retrieves structured context from `ship_computer.db`, including relevant hosts, metrics, and events.
6. The retrieved context is assembled into a prompt for the generative LLM.
7. The LLM produces a concise answer.
8. The answer, along with retrieval metadata, is stored in `ai_responses`.

Ask AI is optimized for speed and relevance. It typically performs one retrieval pass and returns a focused answer.

### Deep Dive

**Deep Dive** is intended for complex investigations that require multiple retrieval steps, correlation across data sources, and iterative reasoning.

Example requests include:

- “Investigate the performance degradation on host B over the last 24 hours.”
- “Correlate memory pressure, disk I/O, and service restarts.”
- “Identify likely root causes for repeated timeout events.”

The Deep Dive workflow is as follows:

1. The user submits an investigation request.
2. The Spock application creates a record in `deep_dive_sessions`.
3. The application breaks the request into analysis steps and stores them in `deep_dive_steps`.
4. For each step, the application:
   - embeds the step description using the embedding LLM,
   - searches the vector database for relevant historical context,
   - queries `ship_computer.db` for structured evidence,
   - records the retrieved evidence and intermediate conclusion.
5. The application iterates through additional steps as needed, refining the investigation based on previously retrieved evidence.
6. The final response synthesizes the collected evidence into a structured explanation.
7. The session, steps, evidence, and final answer are persisted for auditability and future reuse.

Deep Dive is optimized for thoroughness. It may perform multiple vector searches, SQL aggregations, and correlation analyses before producing a final answer.

## Embedding LLM and Vector Database

The Spock application uses an **embedding LLM** and a **vector database** to enable semantic search over operational data, user questions, and previously generated insights.

### Embedding LLM

The embedding LLM converts natural-language text into numerical vector representations. These vectors capture semantic meaning, allowing the application to compare questions, events, and documentation based on meaning rather than exact keyword matching.

The embedding LLM is used for:

- user questions submitted through Ask AI,
- Deep Dive investigation steps,
- event descriptions,
- metric summaries,
- previously generated AI responses,
- operational notes or runbooks, if present.

The resulting embeddings are stored in the `embeddings` table or in a dedicated vector index, depending on the deployment configuration.

### Vector Database

The vector database stores embeddings and supports similarity search. It allows the Spock application to retrieve records that are semantically related to the current user request.

The vector database may be implemented as:

- a SQLite vector extension,
- an embedded vector store,
- or an external vector database service.

In this architecture, `ship_computer.db` remains the source of truth for structured operational data, while the vector database provides semantic retrieval over text-based content.

### Retrieval Pipeline

The retrieval pipeline combines semantic search with structured database queries.

1. **Embed the request**  
   The user question or Deep Dive step is converted into a vector by the embedding LLM.

2. **Search the vector database**  
   The vector database returns the most semantically similar records.

3. **Resolve structured context**  
   The application uses identifiers from the retrieved records to query `ship_computer.db` for precise data such as host names, metric values, event timestamps, and alert states.

4. **Rank and filter**  
   Results are ranked by similarity score, recency, relevance, and confidence.

5. **Assemble prompt context**  
   The application constructs a prompt that includes:
   - the user request,
   - relevant structured data,
   - semantically similar historical examples,
   - constraints or known operational context.

6. **Generate response**  
   The generative LLM produces the final answer using the assembled context.

7. **Persist results**  
   The question, answer, retrieved context, and confidence metadata are stored in `ship_computer.db` for future reference.

### Why Semantic Search Is Needed

Structured SQL queries are effective for exact filtering, such as retrieving CPU usage for a specific host during a specific time window. However, they are less effective for natural-language questions that require interpretation.

For example, a user may ask:

- “Why did the system slow down?”
- “What looks abnormal today?”
- “Is this similar to the incident last week?”

These questions require semantic understanding. The embedding LLM and vector database allow the Spock application to map such questions to relevant operational records, historical incidents, and prior AI responses.

### Relationship Between `ship_computer.db` and the Vector Database

The two storage systems serve complementary roles:

| System | Responsibility |
|---|---|
| `ship_computer.db` | Stores structured, queryable operational data and AI session history. |
| Vector database | Stores embeddings and supports semantic similarity search. |

The Spock application uses `ship_computer.db` for precise data retrieval and auditability, and it uses the vector database for meaning-based discovery. Together, they enable both accurate monitoring and intelligent, context-aware AI responses.