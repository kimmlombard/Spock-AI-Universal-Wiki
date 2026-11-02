# Engineering Deck

The Engineering Deck is a specialized suite of tools that provides maintenance capabilities, health checks, and ship-computer diagnostics. It helps engineers and maintenance personnel monitor, diagnose, and repair critical systems aboard the ship.

Within the broader Spock application, the Engineering Deck acts as the operational interface for ship-computer intelligence. It combines structured SQLite data, natural-language diagnostics, semantic retrieval, and analytical workflows to support both routine troubleshooting and advanced root-cause analysis.

## Components

| Module | Role |
|--------|------|
| `EngineeringDeck.app` | **Main Engineering Panel** — Serves as the central interface for engineering operations. This module provides a high-level overview of the ship's systems and supports general engineering tasks. |
| `EngineeringDeck.ask_panel` | **Q&A Diagnostic Interface** — Allows users to query specific diagnostics and receive detailed information. This module is useful for troubleshooting issues and retrieving real-time system status reports. It serves as the primary entry point for **Ask AI** inquiries, where natural-language queries are translated into structured database searches and semantic context retrieval. |
| `EngineeringDeck.maintenance_app` | **Maintenance Workflow UI** — Provides a guided interface for performing maintenance tasks. This module walks users through step-by-step procedures for common maintenance operations to help ensure safety and compliance. |
| `EngineeringDeck.ship_computer_health` | **Ship Computer Health Monitor** — Monitors and reports on the status of the ship's computer systems. This module continuously tracks the performance, stability, and integrity of the ship's computing infrastructure and supports deep analytical queries. |

## Database Architecture

The Engineering Deck uses a persistent SQLite 3 database file named `ship_computer.db` to store system telemetry, diagnostic logs, and historical health data. Keeping this data in a local database allows the Spock application to perform read-heavy operations efficiently without requiring constant network connectivity.

The database is designed to support both transactional diagnostic lookups and analytical workloads. It provides a reliable local source of truth for ship-computer state while remaining lightweight enough to run in constrained or offline environments.

### ship_computer.db Schema & Data Model

The `ship_computer.db` file is structured to optimize fast reads, time-series analysis, and diagnostic lookups. The schema is organized into the following core tables:

* **`telemetry_readings`**: Stores high-frequency sensor data, such as temperature, pressure, power draw, CPU utilization, GPU utilization, memory pressure, and network throughput. Includes indexed columns for `timestamp`, `system_id`, and `metric_type` to enable rapid time-window queries and subsystem-specific filtering.
* **`diagnostic_logs`**: Captures structured event logs, error codes, warning messages, and subsystem-generated diagnostics. Uses full-text search indexes, such as SQLite FTS5, to allow keyword-based log retrieval and fast matching of error signatures.
* **`health_metrics`**: Stores aggregated health scores, status flags, and operational state indicators for major ship systems. These records are updated periodically by background polling routines and provide a normalized view of system health for dashboards and AI-assisted diagnostics.
* **`query_cache`**: Stores recent Ask AI and Deep Dive query results along with their execution timestamps, query fingerprints, and result metadata. This reduces redundant database scans and improves response latency for repeated or similar inquiries.
* **`integrity_checksums`**: Maintains cryptographic hashes, such as SHA-256, for critical log batches and telemetry snapshots. This supports detection of data corruption, accidental overwrites, or unauthorized modifications.

SQLite is configured in **WAL (Write-Ahead Logging) mode** to allow concurrent read operations while background telemetry writers append new records. This is important because the Spock application may serve diagnostic queries while telemetry ingestion continues in the background.

The application also uses prepared statements and managed database connections to minimize overhead and reduce the risk of locking during high-throughput diagnostic sessions. In a Python implementation, this may involve a connection pool, per-thread connections, or a lightweight connection manager that enforces safe reuse and proper cleanup.

### Interaction with Ask AI

The **Ask AI** functionality within the `EngineeringDeck.ask_panel` module leverages `ship_computer.db` to ground AI responses in real-time, structured ship data. This prevents the system from relying solely on generic language-model knowledge and instead anchors answers in observable ship-computer evidence.

When a user submits a diagnostic query:

1. **Query Translation:**  
   The natural-language input is parsed by a lightweight intent classifier or query planner. The Spock application maps the request to relevant data sources, such as `diagnostic_logs` for error codes, `telemetry_readings` for current sensor states, or `health_metrics` for subsystem status.

2. **Data Retrieval:**  
   Parameterized SQL queries execute against `ship_computer.db`. These queries return structured datasets such as recent fault events, threshold breaches, subsystem status flags, or recent maintenance-related warnings.

3. **Semantic Context Retrieval:**  
   If the query is ambiguous or requires broader context, the Spock application may also query the vector database for semantically similar logs, maintenance notes, incident reports, or previously resolved issues.

4. **Context Assembly & Response Synthesis:**  
   The retrieved structured data and semantic context are formatted into a context payload. The AI processing pipeline then synthesizes this evidence into a clear, actionable diagnostic answer, citing specific log entries, metric values, timestamps, or subsystem identifiers when applicable.

This hybrid approach allows Ask AI to answer both precise questions, such as “What errors occurred on the navigation subsystem in the last hour?” and broader questions, such as “Why is the ship computer reporting intermittent instability?”

### Interaction with Deep Dive Inquiries

For advanced analysis known as **Deep Dive** inquiries, the `EngineeringDeck.ship_computer_health` module utilizes `ship_computer.db` for complex, multi-dimensional analytical tasks. Deep Dive is intended for engineers who need to investigate trends, correlations, and root causes rather than retrieve a single status value.

1. **Historical Analysis:**  
   Time-series queries leverage SQLite window functions, date/time aggregations, and indexed timestamp ranges to identify degradation trends, cyclical failures, or performance drift across days, weeks, or months.

2. **Correlation Checks:**  
   Engineers can execute multi-table joins that correlate hardware telemetry with software event logs. For example, a query might cross-reference `telemetry_readings` power spikes with `diagnostic_logs` kernel warnings to isolate possible root causes.

3. **Integrity Verification:**  
   The `integrity_checksums` table enables automated validation routines that verify data fidelity. If a checksum mismatch is detected, the system flags the affected records for quarantine and triggers a diagnostic alert.

4. **Evidence-Based Reporting:**  
   Deep Dive results are not limited to raw query output. The Spock application can summarize findings, rank likely causes, and present supporting evidence from both structured SQLite data and semantically related historical records.

## Spock Application Integration

The Spock application is the orchestration layer that connects the Engineering Deck modules, the SQLite database, the embedding pipeline, the vector database, and the AI response pipeline. It is responsible for coordinating user requests, retrieving relevant evidence, and presenting coherent diagnostic results.

### Ask AI Flow in Spock

When a user submits an Ask AI request through the Spock application:

1. The request is received by `EngineeringDeck.ask_panel`.
2. Spock normalizes the input and identifies the likely intent, such as error lookup, status check, trend question, or maintenance guidance.
3. Spock generates or selects parameterized SQL queries against `ship_computer.db`.
4. If semantic context is needed, Spock embeds the user query and searches the vector database for related logs, documents, or past incidents.
5. Spock merges structured SQLite results with vector-search results.
6. The combined context is passed to the AI response pipeline.
7. The final answer is returned to the user with citations or references to the underlying data where appropriate.

This flow allows Spock to answer questions that require both exact data and contextual understanding.

### Deep Dive Flow in Spock

When a user initiates a Deep Dive inquiry:

1. The request is routed to `EngineeringDeck.ship_computer_health`.
2. Spock identifies the relevant time range, subsystems, metrics, and log categories.
3. Spock executes analytical SQLite queries, including aggregations, window functions, and multi-table joins.
4. Spock may query the vector database for historically similar incidents, maintenance procedures, or known failure patterns.
5. Spock evaluates data integrity using `integrity_checksums` where applicable.
6. The application synthesizes the results into an analytical summary, possible root causes, recommended actions, and supporting evidence.

This makes Deep Dive useful for complex investigations where a single query is insufficient and the engineer needs a broader diagnostic narrative.

## Embedding LLM and Vector Database Integration

The Spock application uses an embedding LLM and a vector database to support semantic understanding of ship-computer data. This capability complements the structured SQLite database by allowing the system to retrieve information based on meaning rather than exact keyword matches alone.

### Purpose

Structured SQLite queries are excellent for precise lookups, such as finding logs with a specific error code or telemetry values within a time window. However, many diagnostic questions are ambiguous, descriptive, or historical. For example:

* “The ship computer has been acting unstable after power fluctuations.”
* “Find similar incidents where the navigation subsystem degraded after a firmware update.”
* “What maintenance actions were taken when memory pressure spiked during long-duration operations?”

An embedding LLM and vector database allow Spock to interpret these kinds of requests and retrieve relevant context from logs, maintenance notes, incident reports, and previously resolved issues.

### Embedding LLM

The embedding LLM, or embedding model, converts text into numerical vector representations. These vectors capture semantic meaning, so similar concepts are represented by nearby values in vector space.

In the Spock application, the embedding model may be used to:

* Convert user questions into query vectors.
* Convert diagnostic logs into searchable vectors.
* Convert maintenance documentation into searchable vectors.
* Convert historical incident summaries into searchable vectors.
* Convert telemetry descriptions or anomaly summaries into searchable vectors.

The model does not need to generate the final answer. Its role is to create a mathematical representation of meaning that can be compared efficiently against a large collection of stored text.

### Vector Database

The vector database stores the generated embeddings along with metadata. Each vector record typically includes:

* The original text or summary.
* The source type, such as log, maintenance note, incident report, or telemetry annotation.
* The subsystem or system identifier.
* The timestamp or time range.
* The severity or status, if available.
* The associated SQLite record identifier, when applicable.
* The embedding vector itself.

The vector database supports similarity search, commonly using cosine similarity or another distance metric. When Spock receives a query, it can retrieve the most semantically relevant records without requiring the user to know exact keywords or error codes.

### How Spock Uses the Embedding LLM and Vector DB

The Spock application uses the embedding LLM and vector database as part of a hybrid retrieval pipeline.

1. **Query Embedding:**  
   The user’s natural-language question is converted into a vector by the embedding LLM.

2. **Vector Search:**  
   Spock searches the vector database for the closest matching records. These may include similar logs, past incidents, maintenance procedures, or system annotations.

3. **Metadata Filtering:**  
   The vector search results are filtered by relevant metadata, such as subsystem, time range, severity, or data source.

4. **Structured Data Retrieval:**  
   Spock also queries `ship_computer.db` for exact, structured evidence, such as current telemetry, recent error codes, or health flags.

5. **Result Fusion:**  
   The vector-search results and SQLite results are combined into a single context payload.

6. **Response Generation:**  
   The AI pipeline uses the fused context to produce a grounded, evidence-based answer.

This hybrid approach improves accuracy because the system can use exact data when precision is required and semantic retrieval when the question is descriptive or ambiguous.

### Ask AI Usage

For Ask AI inquiries, the embedding LLM and vector database help Spock understand the intent behind the user’s question and retrieve relevant context that may not be directly expressible as a simple SQL predicate.

For example, if a user asks, “Why did the ship computer become unstable after the last power event?”, Spock can:

* Query `telemetry_readings` for power-related metrics around the event.
* Query `diagnostic_logs` for errors near the same time window.
* Search the vector database for past incidents involving power events and instability.
* Retrieve maintenance notes describing similar conditions.
* Combine all evidence into a diagnostic answer.

This makes Ask AI more useful than a simple keyword search because it can reason over both structured data and semantically related historical context.

### Deep Dive Usage

For Deep Dive inquiries, the embedding LLM and vector database support broader investigative workflows.

Spock can use semantic retrieval to:

* Find historically similar failure patterns.
* Identify maintenance actions that were effective in comparable situations.
* Surface related logs that do not contain the exact keywords used by the engineer.
* Connect telemetry anomalies with documented incidents or known subsystem behaviors.
* Provide context for anomalies that are not immediately obvious from raw metrics.

For example, a Deep Dive investigation into repeated navigation subsystem degradation may combine:

* Time-series telemetry from `telemetry_readings`.
* Error events from `diagnostic_logs`.
* Health scores from `health_metrics`.
* Semantically similar past incidents from the vector database.
* Maintenance procedures or known workarounds from stored documentation.

The result is a more complete diagnostic picture than either structured queries or semantic search could provide alone.

### Data Lifecycle

The embedding and vector database pipeline typically follows this lifecycle:

1. **Ingestion:**  
   Logs, telemetry summaries, maintenance notes, and incident reports are collected from the ship-computer environment.

2. **Chunking:**  
   Large documents or log batches are divided into meaningful segments suitable for embedding.

3. **Embedding:**  
   Each segment is converted into a vector by the embedding LLM.

4. **Storage:**  
   The vector and associated metadata are stored in the vector database.

5. **Indexing:**  
   The vector database maintains an index to support fast similarity search.

6. **Retrieval:**  
   Spock queries the vector database during Ask AI and Deep Dive workflows.

7. **Refresh and Maintenance:**  
   New data is periodically embedded and added, while stale or low-value records may be archived or removed.

This lifecycle ensures that the semantic search layer remains current and useful as the ship-computer environment changes over time.
## Embedding LLM & Vector Database Integration

While `ship_computer.db` handles structured telemetry and logs, the Spock application employs an **Embedding LLM** and a **Vector Database** to manage unstructured and semi-structured knowledge, enabling semantic search and context-rich reasoning.

### Embedding Pipeline
1. **Query Embedding:** When a user submits a natural-language question, the Spock application passes the text through a dedicated embedding model, such as a fine-tuned sentence transformer. This model converts the query into a high-dimensional vector that captures semantic meaning rather than exact keyword matches.
2. **Knowledge Base Indexing:** Technical manuals, historical incident reports, maintenance procedures, and system architecture documents are pre-processed, chunked, and embedded during system initialization. These vectors are stored in the vector database with metadata tags, such as `system: propulsion`, `severity: critical`, and `doc_type: manual`.

### Vector Retrieval & RAG Workflow
3. **Similarity Search:** The query vector is compared against the indexed knowledge base using approximate nearest neighbor, or ANN, algorithms, such as HNSW or IVF. The vector database returns the top-k most semantically relevant document chunks.
4. **Hybrid Context Fusion:** Retrieved vector results are merged with structured data pulled from `ship_computer.db`. This hybrid approach ensures the AI has both historical and semantic context from the vector database and real-time operational state from SQLite.
5. **LLM Synthesis:** The combined context is injected into the prompt template for the primary LLM. The model generates a comprehensive response, grounding its recommendations in verified documentation and live system data. Citations and source references are automatically appended to maintain transparency and traceability.

### How the Spock Application Uses the Embedding LLM and Vector Database

The Spock application uses the embedding LLM and vector database as a semantic retrieval layer for Ask AI and Deep Dive inquiries. The embedding model is not used to generate the final answer directly. Instead, it converts text into numerical vectors that can be compared by meaning.

The vector database stores those vectors alongside the original text chunks and metadata. When a user asks a question, the application embeds the question, searches the vector database for semantically similar content, and retrieves the most relevant documentation, procedures, incident notes, or architecture references.

For **Ask AI**, this process supports quick, natural-language answers. The application can combine the retrieved semantic context with live structured data from `ship_computer.db`, allowing the LLM to answer questions that require both current system state and documented guidance.

For **Deep Dive**, the application can use the vector database to gather broader context across multiple documents and historical records. It can then correlate that context with telemetry, logs, maintenance history, and incident data from SQLite to support multi-step troubleshooting, root-cause analysis, and procedural recommendations.

This architecture ensures that Ask AI and Deep Dive inquiries benefit from precise, real-time telemetry while leveraging semantic understanding for complex troubleshooting, procedural guidance, and cross-system analysis.

## SQLite 3 `ship_computer.db` Integration

`ship_computer.db` is the local SQLite 3 database used by the Spock application as the structured source of truth for operational, diagnostic, and maintenance data. It complements the vector database by storing data that can be queried with precise filters, timestamps, numeric thresholds, and relational joins.

### Purpose and Scope

The SQLite 3 database is used for data that requires exact matching, time-based filtering, aggregation, and deterministic querying. This includes telemetry readings, system alerts, maintenance records, incident history, diagnostic results, and operational state information.

Unlike the vector database, which is optimized for semantic similarity, `ship_computer.db` is optimized for structured queries. It allows the Spock application to answer questions such as:

* What is the current temperature of the propulsion system?
* Which alerts were active in the last 24 hours?
* What maintenance tasks were completed for the life support system last month?
* Which incidents are associated with a specific subsystem?
* What is the latest status of a known fault code?

### Data Model Overview

The exact schema may vary by deployment, but `ship_computer.db` typically contains structured tables or views representing the following data areas:

| Data Area | Example Content | Use in Spock |
|---|---|---|
| Telemetry | Sensor readings, timestamps, units, thresholds | Provides current and historical operational state |
| Alerts and Events | Fault codes, severity, active/cleared status | Supports troubleshooting and incident awareness |
| Maintenance Records | Tasks, completion status, technicians, notes | Provides procedural and historical maintenance context |
| Incident Reports | Incident ID, affected systems, root cause, resolution | Supports Deep Dive analysis and pattern recognition |
| System Metadata | Subsystems, components, versions, configuration | Enables filtering and cross-system correlation |
| Audit Logs | User actions, system changes, access events | Supports traceability and operational accountability |

The database is typically accessed through Python’s `sqlite3` module using parameterized SQL queries. This allows the Spock application to retrieve only the relevant rows needed for a given Ask AI or Deep Dive request.

### How Ask AI Uses `ship_computer.db`

For Ask AI inquiries, the Spock application uses `ship_computer.db` to obtain precise, current, or recent structured facts. This is especially useful when the user asks about live system state, recent alerts, thresholds, or completed maintenance actions.

A typical Ask AI flow is:

1. The user asks a natural-language question.
2. The Spock application interprets the intent of the question.
3. It queries `ship_computer.db` for relevant structured data, such as current telemetry, active alerts, or recent maintenance records.
4. It may also query the vector database for relevant documentation or procedural guidance.
5. The structured and semantic context is combined into a prompt for the primary LLM.
6. The LLM generates a concise, grounded answer with citations to the relevant data sources.

For example, if a user asks, “What is the current status of the propulsion system?”, the application can query `ship_computer.db` for the latest propulsion telemetry, active alerts, and recent maintenance notes. It can then use the vector database to retrieve relevant operational procedures or known fault guidance. The final answer can include both the current state and the recommended next steps.

### How Deep Dive Uses `ship_computer.db`

For Deep Dive inquiries, the Spock application uses `ship_computer.db` as the primary structured evidence store. Deep Dive is intended for more complex investigations that require correlation across time, systems, incidents, maintenance actions, and operational logs.

A typical Deep Dive flow is:

1. The user requests an in-depth analysis of a system, incident, or anomaly.
2. The Spock application identifies the relevant subsystems, time range, and data sources.
3. It queries `ship_computer.db` for telemetry trends, alert history, maintenance records, incident reports, and related system events.
4. It queries the vector database for semantic context, such as troubleshooting guides, historical incident summaries, architecture notes, and procedural documentation.
5. The application correlates structured evidence with semantic context.
6. The primary LLM synthesizes a detailed report, including likely causes, supporting evidence, recommended actions, and source references.

For example, if a user asks for a Deep Dive into repeated propulsion anomalies, the application may query `ship_computer.db` for temperature spikes, pressure deviations, fault codes, maintenance history, and related alerts. It may then retrieve vector database content describing known propulsion failure modes, diagnostic procedures, and historical incident resolutions. The final output can present a timeline, probable root causes, and recommended maintenance or diagnostic actions.

### Query and Context Patterns

The Spock application typically converts SQLite query results into prompt-friendly context. This may include:

* Timestamps and time ranges
* Sensor values and units
* Alert severity and status
* Maintenance task completion details
* Incident IDs and resolution notes
* System or subsystem identifiers
* Row identifiers or record keys for citation

This context is then combined with vector database results, which may include:

* Document title or source name
* Section or chunk identifier
* Metadata tags
* Semantic relevance score
* Original text excerpt

The combined context is used to ground the LLM response and reduce the likelihood of unsupported or hallucinated recommendations.

### Relationship to the Embedding and Vector Layers

The SQLite 3 database and the vector database serve different but complementary roles.

| Layer | Best For | Example Question |
|---|---|---|
| `ship_computer.db` | Exact values, timestamps, thresholds, alerts, maintenance records | “What was the propulsion temperature at 14:32?” |
| Vector database | Semantic meaning, procedures, historical context, documentation | “What should be checked when propulsion temperature spikes?” |
| Primary LLM | Synthesis, explanation, recommendation, report generation | “What is the likely cause and what should we do next?” |

The Spock application uses `ship_computer.db` for factual, structured evidence and the vector database for semantic, document-based context. The primary LLM then combines both to produce a coherent, traceable, and operationally useful response.

## Prerequisites

Before running the Engineering Deck, ensure the following environment requirements are met:

* **Python Environment:** A Python virtual environment, such as `.venv`, must be created and configured for the project.
* **Dependencies:** All required Python packages must be installed within the virtual environment before execution.
* **Operating System / Shell:** The provided usage commands are optimized for Windows PowerShell. Run them in a PowerShell terminal, or adapt the syntax if using another shell such as WSL, Bash, or Zsh.

## Usage

To run the Engineering Deck, execute the following command from the project root directory:

**Windows (PowerShell):**
```powershell
.venv\Scripts\python.exe -m spock_maintenance
```

**Linux / macOS / WSL:**
```bash
./.venv/bin/python -m spock_maintenance
```

*(If your virtual environment directory is named `venv` instead of `.venv`, adjust the path accordingly: `./venv/bin/python -m spock_maintenance`)*

This command starts the application using the Python interpreter located in the virtual environment. The `-m` flag instructs Python to execute the `spock_maintenance` package as a module. Ensure the virtual environment exists and contains all required dependencies. Explicitly invoking the virtual environment’s interpreter bypasses the need to activate the environment first, though activation remains an option if preferred.