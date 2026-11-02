# Project Layout

```text
spock-onboarding/
├── spock_onboarding/          # Core onboarding logic
├── spock_bringup/             # Phase A bring-up CLI
├── spock_bringup_menu/        # Bring-up menu GUI
├── spock_probe/               # Health probe CLI
├── spock_status/              # Status display CLI
├── spock_live_monitor/        # Live monitor CLI
├── spock_shell/               # PyQt6 GUI shell (24 modules)
├── spock_mcp_adapter/         # MCP protocol adapter
├── spock_rag_adapter/         # RAG pipeline adapter
├── spock_wiki_adapter/        # Wiki crawler adapter
├── spock_progress_log/        # Progress logging panel
├── Orchestrator/              # Top-level app shell
├── NavigationStation/         # Bring-up wizard
├── EngineeringDeck/           # Maintenance tools
├── LongRangeSensors/          # External data capture
├── ScienceStation/            # Wiki & knowledge queries
├── WarpCore/                  # Shared kernel (DB, profiles, search)
├── scripts/                   # Standalone scripts
├── tests/                     # Test suite
├── docs/                      # MkDocs documentation source
├── templates/                 # Document templates
├── mkdocs.yml                 # MkDocs configuration
├── requirements.txt           # Python dependencies
├── ship_computer_schema.sql   # Database DDL
└── gen_ref_pages.py           # API reference generator
```

## Reading the layout

The top-level entries are organized by functional responsibility:

- **Reusable Python packages**: Directories prefixed with `spock_` encapsulate modular capabilities, including core logic, CLI utilities, GUI components, and protocol adapters.
- **Application groupings**: PascalCase directories represent user-facing workstations, maintenance interfaces, external data ingestion pipelines, knowledge query modules, and shared kernel services.
- **Shared infrastructure**: `scripts/`, `tests/`, `docs/`, and `templates/` provide cross-cutting support for automation, quality assurance, documentation generation, and content templating.
- **Root configuration files**: `mkdocs.yml`, `requirements.txt`, `ship_computer_schema.sql`, and `gen_ref_pages.py` manage project configuration, dependency resolution, database schema definition, and API reference generation.

## Naming conventions

The repository uses two distinct naming patterns to distinguish architectural layers:

- `snake_case` (e.g., `spock_onboarding/`, `spock_rag_adapter/`) identifies reusable Python packages and modular components.
- `PascalCase` (e.g., `Orchestrator/`, `NavigationStation/`, `WarpCore/`) denotes application-level groupings, user-facing stations, and shared functional domains.

# Spock Onboarding Architecture Blueprint

## Overview

The `spock-onboarding` repository implements a Python and SQLite-based application designed to streamline system onboarding, phased bring-up procedures, continuous monitoring, knowledge integration, and workflow orchestration. The architecture deliberately separates reusable core logic from user-facing CLI tools, GUI shells, protocol adapters, and shared services. This modular design enables independent scaling, simplified testing, and clear separation of concerns across development, documentation, and deployment pipelines.

## Directory Structure

```text
spock-onboarding/
├── spock_onboarding/          # Core onboarding logic
├── spock_bringup/             # Phase A bring-up CLI
├── spock_bringup_menu/        # Bring-up menu GUI
├── spock_probe/               # Health probe CLI
├── spock_status/              # Status display CLI
├── spock_live_monitor/        # Live monitor CLI
├── spock_shell/               # PyQt6 GUI shell (24 modules)
├── spock_mcp_adapter/         # MCP protocol adapter
├── spock_rag_adapter/         # RAG pipeline adapter
├── spock_wiki_adapter/        # Wiki crawler adapter
├── spock_progress_log/        # Progress logging panel
├── Orchestrator/              # Top-level app shell
├── NavigationStation/         # Bring-up wizard
├── EngineeringDeck/           # Maintenance tools
├── LongRangeSensors/          # External data capture
├── ScienceStation/            # Wiki & knowledge queries
├── WarpCore/                  # Shared kernel (DB, profiles, search)
├── scripts/                   # Standalone scripts
├── tests/                     # Test suite
├── docs/                      # MkDocs documentation source
├── templates/                 # Document templates
├── mkdocs.yml                 # MkDocs configuration
├── requirements.txt           # Python dependencies
├── ship_computer_schema.sql   # Database DDL
└── gen_ref_pages.py           # API reference generator
```

## SQLite 3 `ship_computer.db` and Spock Interactions

`ship_computer.db` is the local SQLite 3 database that provides persistent state for the Spock application. It is created and maintained from `ship_computer_schema.sql` and is used by `WarpCore/`, `spock_onboarding/`, `spock_bringup/`, `spock_probe/`, `spock_status/`, `spock_live_monitor/`, `spock_rag_adapter/`, and the user-facing stations.

The exact table names and columns are defined in `ship_computer_schema.sql`. Functionally, the database serves as the system of record for:

- **Onboarding state**: current onboarding phase, completed steps, pending actions, operator profiles, and configuration choices.
- **Bring-up execution**: Phase A bring-up runs, step results, timestamps, pass/fail status, and retry history.
- **Health and monitoring**: probe results, status snapshots, live-monitor events, thresholds, and alert history.
- **Knowledge management**: document ingestion metadata, source identifiers, chunk references, processing status, and citation data.
- **Ask AI and Deep Dive inquiries**: user questions, retrieved context identifiers, generated answers, investigation plans, evidence links, and audit trails.

For **Ask AI** inquiries, the Spock application uses `ship_computer.db` to preserve the conversational and operational context needed to answer safely. When a user asks a question, the application can:

1. Load the active session, operator profile, and relevant onboarding or bring-up state.
2. Record the question, timestamp, and request metadata.
3. Retrieve candidate knowledge chunks from the vector database or local search index.
4. Store the selected chunk identifiers, source documents, confidence scores, and citations.
5. Persist the generated answer and any follow-up context for later review.

For **Deep Dive** inquiries, the database provides a durable investigation workspace. A Deep Dive request is not treated as a single lookup; it is a multi-step analysis that may include query decomposition, repeated retrieval, evidence comparison, and synthesis. `ship_computer.db` stores:

- The original Deep Dive question and any refined sub-questions.
- The sequence of retrieval operations and the chunks considered at each step.
- Evidence items, including source documents, chunk IDs, relevance scores, and supporting excerpts.
- Intermediate findings, contradictions, unresolved gaps, and final conclusions.
- Audit information that allows an operator to trace how the final answer was derived.

In this design, SQLite is not primarily used to store large raw vector embeddings. Instead, it stores structured metadata, references, and operational history. The vector database stores high-dimensional embeddings for similarity search, while `ship_computer.db` stores the durable, queryable context that makes Ask AI and Deep Dive results reproducible and auditable.

## Ask AI and Deep Dive Inquiry Flow

The Spock application supports two related but distinct inquiry modes:

- **Ask AI**: a direct question-answering mode that retrieves relevant context and returns a concise, cited answer.
- **Deep Dive**: an investigative mode that performs broader retrieval, compares multiple sources, and produces a structured analysis.

Both modes rely on the same underlying knowledge pipeline, but they differ in depth, retrieval strategy, and output format.

### Ask AI Flow

1. The user submits a question through the Spock interface.
2. The application normalizes the question and applies any active filters, such as document type, onboarding phase, or source scope.
3. The question is converted into an embedding using the configured embedding model.
4. The vector database performs similarity search and returns the most relevant chunks.
5. The application may rerank candidates using metadata, recency, source authority, or keyword overlap.
6. The selected chunks are assembled into a prompt context.
7. The language model generates an answer grounded in the retrieved context.
8. Citations, chunk IDs, and source references are stored in `ship_computer.db`.

### Deep Dive Flow

1. The user submits a broader investigative question.
2. The application decomposes the question into sub-questions or analysis dimensions.
3. Each sub-question is embedded and searched against the vector database.
4. The application iterates retrieval, expanding or refining queries when initial evidence is insufficient.
5. Retrieved chunks are grouped by source, topic, phase, or confidence.
6. The application identifies supporting evidence, contradictions, and gaps.
7. A structured Deep Dive report is generated, including findings, evidence, limitations, and recommended next steps.
8. The full investigation trail is persisted in `ship_computer.db` for audit and follow-up.

## Embedding LLM and Vector Database Usage

The Spock application uses an embedding LLM, or embedding model, to convert text into numerical vectors that can be compared by semantic similarity. This is the foundation of its retrieval-augmented generation (RAG) capability.

### Embedding Process

When documents, wiki pages, onboarding guides, probe reports, or other knowledge sources are ingested, the application:

1. Splits the content into manageable chunks.
2. Adds metadata to each chunk, such as source, title, section, timestamp, document type, and onboarding phase.
3. Sends each chunk to the configured embedding model.
4. Receives a fixed-length vector representation of the chunk.
5. Stores the vector in the vector database along with the chunk text and metadata.

The embedding model is typically a dedicated encoder model rather than a generative language model. Its role is to produce dense vector representations that capture semantic meaning. The generative language model is used later to answer questions using the retrieved context.

### Vector Database Role

The vector database stores embeddings and supports fast similarity search. When a user asks a question, the application:

1. Embeds the user question using the same embedding model used for the knowledge base.
2. Queries the vector database for the nearest or most similar chunk vectors.
3. Applies metadata filters to restrict results to relevant sources or phases.
4. Returns a ranked set of candidate chunks for prompt construction.

This approach allows Spock to answer questions using current, domain-specific knowledge rather than relying only on the language model's pretraining data.

### Ask AI and Deep Dive Differences in Retrieval

For **Ask AI**, retrieval is usually optimized for speed and precision. The application typically performs one or a small number of similarity searches and selects the highest-confidence chunks.

For **Deep Dive**, retrieval is optimized for coverage and evidence quality. The application may perform multiple searches, use query expansion, retrieve from different document categories, and compare results across sources. The goal is to build a defensible evidence base before generating the final analysis.

### Relationship Between SQLite and the Vector Database

The two storage systems have complementary roles:

- **Vector database**: stores embeddings and supports semantic similarity search.
- **SQLite `ship_computer.db`**: stores structured application state, inquiry history, citations, evidence references, and audit data.

This separation keeps high-dimensional vector data in a storage system optimized for similarity search, while keeping operational and analytical data in a relational database optimized for structured queries, transactions, and persistence.
## SQLite 3 Database (`ship_computer.db`) Architecture & Interaction

The `ship_computer.db` file serves as the centralized relational datastore for the Spock application. Defined by `ship_computer_schema.sql`, it leverages SQLite 3's ACID compliance, zero-configuration deployment, and efficient read-heavy performance to manage application state, user profiles, query history, session checkpoints, and cached AI responses.

`ship_computer.db` is intentionally separate from the vector database. It stores relational records that describe application behavior, user context, cached results, and audit trails. The vector database stores embeddings and performs semantic similarity search. This separation allows Spock to keep durable operational state in a lightweight local database while using a specialized vector index for retrieval.

### Core Schema Domains
- **System State & Profiles**: Stores onboarding progress, user preferences, bring-up phase checkpoints, and configuration overrides.
- **Query & Session Logs**: Tracks all user interactions, including timestamps, input prompts, selected inquiry modes, and response metadata.
- **Knowledge Index Metadata**: Maintains references to crawled wiki pages, external data sources, and document versioning without storing raw payloads.
- **Response Cache**: Holds serialized LLM outputs and retrieval results to reduce latency and API costs for repeated or similar queries.

### SQLite 3 Operational Characteristics
SQLite 3 is used as an embedded, file-based database engine. This means Spock does not require a separate database server process. The database is accessed through Python's `sqlite3` module, which provides a simple, synchronous interface suitable for local application state management.

Key operational characteristics include:

- **Single-File Storage**: The entire relational database is stored in `ship_computer.db`, making backup, restore, and local inspection straightforward.
- **ACID Transactions**: Writes are committed atomically. If a transaction fails, the database remains in a consistent state.
- **WAL Mode**: Write-ahead logging allows concurrent readers while a single writer commits changes. This is useful when the GUI reads session state while the RAG adapter writes logs or cache entries.
- **Local Concurrency Model**: SQLite supports multiple readers and one writer at a time. Spock should serialize write operations through `WarpCore` or a dedicated persistence layer to avoid lock contention.
- **Schema Versioning**: The schema is defined in `ship_computer_schema.sql`. Application startup should verify the schema version and apply migrations if necessary.
- **Cache and Log Growth**: Query logs, response caches, and Deep Dive checkpoints can grow over time. Spock should implement retention policies, pruning rules, or archival strategies to keep the database manageable.

### Interaction with "Ask AI" Inquiries
"Ask AI" is optimized for rapid, context-light responses. When a user submits a query:

1. The `spock_shell` or CLI interface routes the request to `WarpCore`, which normalizes the prompt and checks the response cache in `ship_computer.db`.
2. If a cached match exists, based on prompt hash, session context, inquiry mode, source filters, and model version, the application returns the stored response immediately.
3. If no cached match exists, the query is forwarded to the RAG pipeline. The database logs the request, tracks token usage, stores retrieval metadata, and stores the final generated response for future cache hits.
4. Transaction isolation ensures that concurrent "Ask AI" requests do not corrupt session state or overwrite active cache entries.

### Ask AI Data Flow
The "Ask AI" flow is designed for low-latency responses while preserving enough context to make the answer reproducible and auditable.

1. **Request Normalization**  
   `WarpCore` receives the user prompt and normalizes it. Normalization may include trimming whitespace, resolving user-specific aliases, applying default source filters, and determining the active inquiry mode.

2. **Cache Lookup**  
   The application computes a cache key from the normalized prompt, user context, inquiry mode, source filters, model version, embedding model version, and retrieval parameters. It then queries `ship_computer.db` for a matching cached response.

3. **Cached Response Path**  
   If a valid cache entry exists, Spock returns the stored response. The cache entry may include the generated answer, retrieved evidence identifiers, confidence score, token usage, and timestamp.

4. **RAG Retrieval Path**  
   If no valid cache entry exists, Spock sends the prompt to the embedding LLM to create a query vector. The vector database returns the most relevant document chunks. The retrieved chunks are ranked, filtered, and assembled into a context payload.

5. **Response Generation**  
   The generative LLM receives the user prompt and retrieved context. It produces a natural-language answer. The response is validated, formatted, and prepared for display.

6. **Persistence**  
   Spock writes the request, retrieval results, response, token usage, confidence score, and timing metrics to `ship_computer.db`. If the response is eligible for caching, it is stored with a cache key and expiration policy.

7. **Concurrency Control**  
   Write operations are committed within SQLite transactions. If two "Ask AI" requests attempt to write related state, Spock serializes the writes to prevent partial updates or cache corruption.

### Interaction with "Deep Dive" Inquiries
"Deep Dive" mode triggers iterative, multi-step research workflows. The database interaction differs significantly from "Ask AI" because Deep Dive sessions require durable state, resumability, and detailed auditability.

1. **Step Tracking**: Each reasoning step, retrieved document chunk, and intermediate LLM output is recorded as a distinct row in a `deep_dive_sessions` table, enabling full auditability and step-by-step UI rendering.
2. **Context Assembly**: The application queries `ship_computer.db` to retrieve previously resolved entities, user-defined constraints, and historical research paths to maintain continuity across long sessions.
3. **State Persistence**: Because Deep Dive sessions may span minutes or hours, the database periodically checkpoints progress. If the application restarts or encounters an interruption, `WarpCore` reconstructs the session state from the last committed checkpoint.
4. **Resource Management**: SQLite's write-ahead logging (WAL) mode is enabled to allow concurrent reads from the GUI while the RAG adapter performs heavy write operations during document ingestion and session logging.

### Deep Dive Data Flow
Deep Dive is a stateful workflow. Unlike a single "Ask AI" request, a Deep Dive session may involve multiple retrieval passes, intermediate reasoning steps, user constraints, and evidence accumulation.

1. **Session Initialization**  
   When a user starts a Deep Dive inquiry, Spock creates a session record in `ship_computer.db`. The record includes the session identifier, user identifier, initial prompt, selected constraints, source filters, token budget, and creation timestamp.

2. **Planning and Step Creation**  
   `WarpCore` breaks the research task into steps. Each step may represent a sub-question, retrieval action, reasoning action, or validation action. Step records are stored with status, sequence number, input context, and expected output.

3. **Retrieval and Evidence Capture**  
   For each retrieval step, Spock queries the vector database. The retrieved chunks, similarity scores, source identifiers, and metadata are stored in the session's evidence log. This allows the GUI to display which sources supported each reasoning step.

4. **Intermediate Reasoning**  
   Intermediate LLM outputs are stored as step artifacts. These may include hypotheses, contradictions, unresolved questions, and proposed next actions. Storing these artifacts enables the user to inspect the reasoning path rather than only seeing the final answer.

5. **Checkpointing**  
   After each committed step, Spock writes a checkpoint to `ship_computer.db`. The checkpoint captures the current session state, completed steps, pending steps, resolved entities, accumulated evidence, and token usage.

6. **Resume and Recovery**  
   If the application restarts, the user closes the session, or an error occurs, `WarpCore` can reload the last committed checkpoint. The session can then resume from the next pending step without repeating completed work.

7. **Completion and Audit**  
   When the Deep Dive session completes, Spock stores the final answer, final evidence set, total token usage, duration, and confidence metrics. The complete session history remains available for review, debugging, or future context reuse.

### Cache Invalidation and Data Integrity
The response cache in `ship_computer.db` improves performance, but it must be invalidated when the underlying knowledge or configuration changes.

Cache entries should be invalidated or bypassed when any of the following change:

- The user prompt or normalized query.
- The inquiry mode, such as "Ask AI" versus "Deep Dive".
- The source filters or permission scope.
- The generative LLM model or prompt template.
- The embedding model or embedding dimension.
- The vector database index version.
- The document version or crawl timestamp.
- The user's access permissions.

Spock should store cache metadata alongside each cached response so that stale entries can be detected and discarded. This prevents the application from returning an answer that was valid under a previous knowledge base state but is no longer accurate.

## Embedding LLM & Vector Database Integration

The Spock application employs a Retrieval-Augmented Generation (RAG) architecture powered by an embedding model and a vector database. This pipeline transforms unstructured knowledge into semantically searchable representations, enabling accurate, context-aware AI responses.

The embedding LLM is not the same as the generative LLM. The embedding model converts text into numerical vectors that represent semantic meaning. The generative LLM uses those retrieved vectors' associated text chunks as context when producing a natural-language answer.

### Embedding LLM Workflow
1. **Text Ingestion**: Raw documents, wiki pages, and external data captured by `spock_wiki_adapter` and `LongRangeSensors` are chunked using configurable token limits and overlap strategies.
2. **Vectorization**: Each chunk is passed through the embedding LLM, such as `text-embedding-3-small` or a local equivalent. The model outputs a high-dimensional vector that captures semantic meaning, syntax, and contextual relationships.
3. **Metadata Attachment**: Before storage, each vector is paired with metadata, including source URL, document title, chunk index, timestamp, and access permissions, to enable precise attribution and filtering during retrieval.

### Embedding Consistency Requirements
For retrieval to work correctly, the embedding model used during ingestion and the embedding model used during query time must be compatible.

Spock should enforce the following consistency rules:

- **Same Model Family**: The query vector and document vectors should be generated by the same embedding model or a compatible model with the same vector space.
- **Same Dimensionality**: The vector database index must match the embedding dimension. A model change that changes vector dimension requires a new index or re-embedding of the knowledge base.
- **Same Normalization**: If vectors are normalized for cosine similarity, both ingestion and query vectors should use the same normalization strategy.
- **Same Chunking Strategy**: Document chunk size, overlap, and text preprocessing should be stable for a given knowledge base version. Changing chunking may require re-indexing.
- **Version Tracking**: The embedding model name, version, and dimension should be stored in `ship_computer.db` and in vector metadata so that Spock can detect incompatible retrieval requests.

### Vector Database Operations
The vector store, integrated via `spock_rag_adapter`, handles similarity search and index management:

- **Indexing**: Vectors are stored in an optimized index structure, such as HNSW or IVF, that balances query speed with memory usage. The index is periodically rebuilt or updated incrementally as new knowledge is onboarded.
- **Query Transformation**: When a user submits a prompt, the same embedding LLM converts the query into a vector using identical parameters as the ingestion pipeline.
- **Similarity Search**: The vector database computes distance metrics, such as cosine similarity or Euclidean distance, to retrieve the top-K most relevant chunks. Hybrid search capabilities may combine vector similarity with keyword filtering for precision.
- **Context Window Assembly**: Retrieved chunks are ranked, deduplicated, and formatted into a structured context payload. This payload is injected into the LLM's system prompt alongside the original user query.

### Retrieval Pipeline
The retrieval pipeline is the bridge between the user's question and the generative LLM. It determines which knowledge chunks are relevant enough to include in the model's context window.

1. **Query Embedding**  
   The user prompt is converted into a vector using the embedding LLM. The resulting query vector represents the semantic intent of the question.

2. **Metadata Filtering**  
   Before or during similarity search, Spock applies filters based on user permissions, source type, document version, time range, and inquiry mode. This prevents the model from retrieving content the user should not access.

3. **Similarity Search**  
   The vector database searches for the nearest neighbors to the query vector. It returns the top-K chunks, where K is configurable based on the inquiry mode. "Ask AI" may use a smaller K for speed, while "Deep Dive" may use a larger K for broader evidence collection.

4. **Scoring and Thresholding**  
   Each retrieved chunk has a similarity score. Spock can discard chunks below a confidence threshold to avoid injecting weakly relevant context into the LLM prompt.

5. **Reranking**  
   If available, a reranking model or heuristic can reorder the retrieved chunks. Reranking improves precision by prioritizing chunks that are most directly useful to the user's question.

6. **Deduplication**  
   Overlapping chunks from the same document may be merged or deduplicated to reduce redundancy and conserve context window space.

7. **Context Assembly**  
   The final chunks are formatted into a structured context payload. The payload includes source attribution, chunk identifiers, and enough surrounding text for the generative LLM to reason accurately.

8. **Prompt Injection**  
   The assembled context is inserted into the generative LLM's prompt template. The LLM then generates an answer grounded in the retrieved evidence.

### Integration with Spock Modules
- **`spock_rag_adapter`**: Orchestrates the end-to-end RAG flow, managing vector store connections, chunking strategies, retrieval thresholds, and LLM prompt templating.
- **`spock_mcp_adapter`**: Exposes the RAG pipeline and vector search capabilities via the Model Context Protocol, allowing external tools or AI agents to query the knowledge base programmatically.
- **`ScienceStation`**: Provides the GUI interface for users to initiate queries, adjust retrieval parameters, such as depth and source filtering, and visualize retrieved evidence alongside AI-generated answers.
- **Caching & Fallbacks**: If the vector database returns low-confidence matches, the application falls back to keyword search or prompts the user to refine the query. All retrieval metrics and confidence scores are logged to `ship_computer.db` for performance monitoring and continuous tuning.

### End-to-End RAG Sequence
The following sequence describes how Spock uses the embedding LLM and vector database for both "Ask AI" and "Deep Dive" inquiries.

1. **User Submits a Query**  
   The user enters a prompt through `spock_shell`, the CLI, or `ScienceStation`.

2. **WarpCore Routes the Request**  
   `WarpCore` determines the inquiry mode, applies user context, and checks whether a cached response is available in `ship_computer.db`.

3. **Embedding LLM Creates a Query Vector**  
   If retrieval is required, the embedding LLM converts the user prompt into a vector.

4. **Vector Database Performs Similarity Search**  
   The vector database returns the most relevant document chunks, along with similarity scores and metadata.

5. **Spock Filters and Ranks Evidence**  
   `spock_rag_adapter` applies permission filters, source filters, confidence thresholds, and reranking logic.

6. **Context Payload Is Assembled**  
   The selected chunks are formatted into a structured context payload suitable for the generative LLM.

7. **Generative LLM Produces an Answer**  
   The generative LLM receives the user prompt and context payload, then generates a response.

8. **Response Is Returned and Persisted**  
   The answer is returned to the user. Spock stores the request, retrieval results, response, token usage, and confidence metrics in `ship_computer.db`.

9. **Deep Dive Continues Iteratively**  
   In Deep Dive mode, the process repeats across multiple steps. Each step may refine the query, retrieve additional evidence, update hypotheses, and checkpoint progress.

### Failure Modes and Fallbacks
Spock should handle retrieval and generation failures gracefully.

- **Embedding Failure**: If the embedding LLM is unavailable, Spock can fall back to keyword search, return a degraded response, or ask the user to retry.
- **Vector Database Unavailable**: If the vector store cannot be reached, Spock can use cached responses, keyword search, or a local fallback index if one exists.
- **Low-Confidence Retrieval**: If similarity scores are below threshold, Spock should avoid forcing weak evidence into the prompt. It can ask the user to refine the query or present the best available sources with a confidence warning.
- **Stale Knowledge**: If document versions or permissions have changed, Spock should invalidate cached responses and re-retrieve from the current knowledge base.
- **Token Budget Exceeded**: If retrieved context exceeds the LLM's context window, Spock should truncate, summarize, or prioritize the highest-scoring chunks.
- **Session Interruption**: For Deep Dive sessions, Spock should rely on SQLite checkpoints to resume from the last committed state rather than restarting the entire workflow.
## Component Reference

### Core Onboarding and Bring-Up Tools

- **`spock_onboarding/`**  
  Contains the core onboarding logic shared across CLI tools, GUI shells, adapters, and application components. This module standardizes initialization routines, configuration validation, and environment provisioning.

- **`spock_bringup/`**  
  Provides the Phase A bring-up command-line interface for initial system setup, dependency validation, and guided preparation workflows.

- **`spock_bringup_menu/`**  
  Provides a graphical menu interface for bring-up operations, offering an interactive alternative to the CLI-based workflow with visual progress tracking and step-by-step navigation.

- **`spock_probe/`**  
  Provides a health probe command-line interface used to verify the availability, connectivity, and operational state of internal services and external dependencies.

- **`spock_status/`**  
  Provides a status display command-line interface for viewing current application state, service health, onboarding progress, and runtime metrics.

- **`spock_live_monitor/`**  
  Provides a live monitoring command-line interface for observing real-time activity, task execution progress, system logs, and runtime behavior.

### GUI Shells and Panels

- **`spock_shell/`**  
  A PyQt6-based graphical user interface shell comprising 24 modules. It serves as the primary interactive desktop application surface, hosting navigation, configuration, and operational controls.

- **`spock_progress_log/`**  
  Provides a dedicated progress logging panel for displaying operational activity, task execution status, diagnostic output, and system events within the GUI context.

### Protocol and Knowledge Adapters

- **`spock_mcp_adapter/`**  
  Adapts the application to the Model Context Protocol (MCP), enabling standardized integration with external tools, services, and AI model workflows that support MCP communication patterns.

- **`spock_rag_adapter/`**  
  Provides a retrieval-augmented generation (RAG) pipeline adapter. It orchestrates knowledge retrieval, context assembly, and generation workflows by connecting core data sources to the LLM inference layer.

- **`spock_wiki_adapter/`**  
  Provides a wiki crawler and content processor adapter responsible for retrieving, parsing, chunking, and indexing wiki documentation for use in knowledge query features.

### Application Shells and Stations

- **`Orchestrator/`**  
  The top-level application shell responsible for coordinating high-level workflows, managing component lifecycles, and routing requests between subsystems.

- **`NavigationStation/`**  
  Provides a structured bring-up wizard experience, guiding users through configuration, validation, and onboarding steps with contextual feedback and error handling.

- **`EngineeringDeck/`**  
  Contains maintenance and diagnostic tools intended for operational troubleshooting, system tuning, and engineering-level configuration management.

- **`LongRangeSensors/`**  
  Handles external data ingestion, capturing remote feeds, API responses, and third-party system outputs, then normalizing and routing them into the application data pipeline.

- **`ScienceStation/`**  
  Provides wiki and knowledge query capabilities, serving as the user-facing interface for searching, exploring, and interacting with indexed documentation and AI-assisted knowledge retrieval.

### Shared Kernel

- **`WarpCore/`**  
  The shared application kernel providing foundational services, including database access abstraction, user profile management, search indexing, configuration handling, and reusable utility functions consumed by all components.

### Project Support Files

- **`scripts/`**  
  Contains standalone utility scripts for maintenance tasks, synthetic data generation, environment provisioning, and one-off operational procedures.

- **`tests/`**  
  Contains the comprehensive test suite used to validate application behavior, component integration, and regression stability across all packages.

- **`docs/`**  
  Contains the MkDocs documentation source files, including architecture guides, API references, and operational manuals.

- **`templates/`**  
  Contains document and report templates used for structured content generation, export formatting, and standardized output rendering.

- **`mkdocs.yml`**  
  The MkDocs configuration file that controls documentation site structure, navigation hierarchy, plugin integration, and rendering behavior.

- **`requirements.txt`**  
  Lists the Python dependencies, version constraints, and environment specifications required to install and run the application.

- **`ship_computer_schema.sql`**  
  Contains the SQLite database DDL statements defining the schema for the “ship computer” data model, including tables, indexes, constraints, and initialization routines.

- **`gen_ref_pages.py`**  
  A utility script that auto-generates API reference documentation pages by parsing code docstrings, type hints, and package metadata.

## SQLite 3 `ship_computer.db`

`ship_computer.db` is the local SQLite 3 database used by the Spock application to persist application state, user data, knowledge artifacts, AI interaction history, and operational metadata. It is created and maintained from the DDL statements in `ship_computer_schema.sql`, which define the tables, indexes, constraints, and initialization routines required for the “ship computer” data model.

The database is embedded and file-based, meaning it does not require a separate database server. This makes it well suited for local desktop operation, offline workflows, and controlled environments. The Spock application accesses the database through the shared `WarpCore/` kernel, which provides a consistent database access abstraction for all components. This prevents individual tools, GUI panels, adapters, and stations from managing raw SQLite connections independently.

### Purpose and Role

The `ship_computer.db` database serves as the persistent source of truth for the Spock application. It stores the information needed to support onboarding, configuration, knowledge ingestion, AI-assisted querying, and operational monitoring.

Its primary responsibilities include:

- Storing user profiles, preferences, and onboarding state.
- Storing configuration values and environment-specific settings.
- Storing ingested knowledge sources, such as wiki pages, documents, and external data.
- Storing processed text chunks and metadata used for retrieval.
- Storing references to embeddings or vector records used for semantic search.
- Storing Ask AI sessions, prompts, responses, citations, and model metadata.
- Storing Deep Dive sessions, retrieval steps, selected sources, and generated artifacts.
- Storing operational logs, task state, probe results, and status information.

The exact table names and column definitions are authoritative in `ship_computer_schema.sql`. Conceptually, the database contains the following record families:

| Record Family | Examples | Purpose |
|---|---|---|
| User and session data | profiles, settings, sessions | Tracks user identity, preferences, and active application state. |
| Knowledge sources | sources, documents, wiki pages | Stores the origin and metadata of ingested content. |
| Processed content | chunks, passages, excerpts | Stores text fragments suitable for retrieval and context assembly. |
| Retrieval data | queries, candidates, citations | Records what was searched, what was retrieved, and what was cited. |
| AI interaction data | prompts, responses, model metadata | Preserves Ask AI and Deep Dive outputs for auditability and follow-up. |
| Deep Dive state | sessions, steps, selected sources | Tracks multi-step investigations and the evidence used at each stage. |
| Operational data | logs, tasks, probe results | Supports monitoring, diagnostics, and maintenance workflows. |

### Relationship to the Spock Application

The Spock application uses `ship_computer.db` as its local persistence layer. Different components interact with the database through `WarpCore/`, which provides shared services for database access, configuration handling, user profile management, and search indexing.

This design has several benefits:

- **Consistency:** All components use the same data access patterns and schema conventions.
- **Maintainability:** Database logic is centralized rather than duplicated across tools and adapters.
- **Auditability:** User actions, AI responses, and retrieval results can be traced back to stored records.
- **Reusability:** GUI shells, CLI tools, adapters, and stations can share the same persistent state.
- **Local operation:** The database supports local, file-based storage without requiring an external database service.

### Ask AI Interaction

Ask AI is the Spock application’s question-answering capability. It allows users to ask natural-language questions and receive AI-generated answers grounded in indexed knowledge sources.

The `ship_computer.db` database supports Ask AI in the following ways:

1. **Session and profile context**  
   The database stores the active user profile, session state, and relevant configuration. This allows the application to personalize retrieval, enforce preferences, and maintain continuity across interactions.

2. **Knowledge source metadata**  
   When a question is asked, the application can use stored source metadata to filter or prioritize relevant documents, wiki pages, or external content.

3. **Retrieval context**  
   The database stores processed chunks and metadata associated with indexed content. These records help the RAG adapter assemble a coherent context for the LLM.

4. **Query history**  
   Ask AI queries, timestamps, and associated metadata are stored so users can review previous questions and answers.

5. **Response persistence**  
   Generated answers, model metadata, retrieval scores, and citations are stored for later inspection, export, or follow-up.

6. **Citation tracking**  
   The database can store the source identifiers, chunk identifiers, and retrieval scores used to support each answer. This improves transparency and traceability.

A typical Ask AI flow is:

1. The user submits a question through `ScienceStation/`, `spock_shell/`, or another supported interface.
2. `Orchestrator/` routes the request to the appropriate workflow.
3. `WarpCore/` loads the user profile, session state, and configuration.
4. `spock_rag_adapter/` prepares the query for retrieval.
5. The query is embedded using the configured embedding LLM.
6. The vector database returns the most relevant text chunks.
7. `ship_computer.db` supplies metadata, source records, and prior context.
8. The RAG adapter assembles a prompt containing the user question and retrieved context.
9. The generation LLM produces an answer.
10. The answer, query, citations, and session state are written back to `ship_computer.db`.

### Deep Dive Interaction

Deep Dive is an extended inquiry mode designed for more complex questions that require broader context, multiple sources, and iterative retrieval. Unlike a single Ask AI response, a Deep Dive may involve several retrieval passes, source expansion, and structured analysis.

The `ship_computer.db` database supports Deep Dive by storing the state needed to track a multi-step investigation.

Its role includes:

- Storing the Deep Dive session identifier and user intent.
- Recording each retrieval step and the query used for that step.
- Tracking which sources and chunks were selected, reviewed, or excluded.
- Preserving intermediate findings or generated sections.
- Maintaining citation data for each part of the final answer.
- Supporting follow-up questions by reusing prior context.
- Enabling export or review of the complete investigation trail.

A typical Deep Dive flow is:

1. The user starts a Deep Dive with a topic, question, or investigation goal.
2. The application performs an initial retrieval pass using the embedding LLM and vector database.
3. The RAG adapter evaluates the retrieved chunks and identifies relevant sources.
4. The application may generate refined subqueries to fill gaps or explore related concepts.
5. Additional retrieval passes are performed against the vector database.
6. `ship_computer.db` records each step, selected source, retrieved chunk, and retrieval score.
7. The application assembles a broader context window from the accumulated evidence.
8. The generation LLM produces a more detailed, structured answer.
9. The final Deep Dive artifact, including citations and step history, is stored in `ship_computer.db`.

### Ask AI and Deep Dive Comparison

| Aspect | Ask AI | Deep Dive |
|---|---|---|
| Scope | Single question or short exchange | Extended investigation |
| Retrieval | Usually one or a few retrieval passes | Multiple iterative retrieval passes |
| Context | Focused on the immediate question | Broader, source-expanded context |
| Output | Concise answer | Structured, detailed analysis |
| Citation use | Supports answer grounding | Tracks evidence across multiple steps |
| Database role | Stores query, answer, and citations | Stores session, steps, sources, and artifacts |
| Follow-up | May use prior session context | Reuses accumulated investigation state |

### Data Integrity and Operational Notes

Because `ship_computer.db` is a SQLite 3 database, it provides local ACID transaction behavior, which helps maintain consistency during writes. The schema in `ship_computer_schema.sql` defines the constraints and indexes that support reliable access patterns.

The database is especially important for:

- Preserving user work across application restarts.
- Maintaining a history of AI-assisted interactions.
- Supporting reproducible retrieval and citation workflows.
- Enabling diagnostics through stored logs and status data.
- Allowing Deep Dive sessions to be resumed or reviewed later.

The database does not replace the vector database. Instead, it stores relational state and metadata, while the vector database stores high-dimensional embeddings used for semantic similarity search.

## Embedding LLM and Vector Database

The Spock application uses an embedding LLM and a vector database to support semantic knowledge retrieval. Together, they allow the application to understand the meaning of user questions and find relevant passages from indexed documentation, wiki content, or other knowledge sources.

This capability is central to both Ask AI and Deep Dive. The embedding LLM converts text into numerical vectors, and the vector database stores and searches those vectors to find semantically similar content.

### Purpose of the Embedding LLM

An embedding LLM is a model that maps text into a fixed-size numerical vector, also called an embedding. Each vector represents the semantic meaning of the text in a high-dimensional space.

The embedding LLM is not the same as the generation LLM that produces final answers. Its role is retrieval-oriented:

- It encodes documents, chunks, and user queries into comparable vectors.
- It enables semantic similarity search rather than exact keyword matching.
- It allows the application to find relevant content even when the wording differs from the user’s question.
- It supports RAG workflows by helping the application assemble relevant context before generation.

For example, a user may ask:

> “How do I configure the bring-up workflow?”

The indexed documentation may contain a passage that says:

> “Phase A setup requires validating dependencies before starting the guided preparation process.”

A keyword search might miss this if the exact words do not match. An embedding-based search can still identify the passage because the semantic meaning is related.

### Purpose of the Vector Database

The vector database stores embeddings and the metadata needed to retrieve and interpret them. It is optimized for similarity search, allowing the application to find the most relevant vectors for a given query vector.

The vector database may be implemented in different ways:

- As a SQLite-backed vector store, possibly using a vector extension or vector table.
- As a separate local vector database.
- As an external vector service, with metadata and references stored in `ship_computer.db`.

Regardless of implementation, the vector database provides the following capabilities:

- Storing high-dimensional vectors.
- Associating each vector with metadata such as source, chunk ID, document ID, timestamp, and model version.
- Performing similarity search using metrics such as cosine similarity, dot product, or Euclidean distance.
- Returning the top-k most relevant vectors for a query.
- Supporting filtering by source, date, type, or other metadata.

### Indexing Workflow

Before Ask AI or Deep Dive can use semantic retrieval, knowledge sources must be indexed.

The indexing workflow generally follows these steps:

1. **Ingestion**  
   Content is collected from sources such as wiki pages, documents, external feeds, or local files. Components such as `spock_wiki_adapter/` and `LongRangeSensors/` may participate in this process.

2. **Parsing and normalization**  
   Raw content is parsed into structured text. Formatting, markup, and source-specific artifacts are cleaned or normalized.

3. **Chunking**  
   The content is divided into smaller passages or chunks. Chunking is important because LLM context windows are limited and retrieval works best with focused passages rather than entire documents.

4. **Metadata extraction**  
   Each chunk is associated with metadata such as:
   - Source identifier
   - Document identifier
   - Page or section
   - Title
   - Timestamp
   - Content type
   - User or profile scope
   - Processing version

5. **Embedding generation**  
   The embedding LLM converts each chunk into a vector. The vector dimension and model version are important because embeddings from different models or versions are not directly comparable.

6. **Vector storage**  
   The generated vectors are stored in the vector database.

7. **Metadata persistence**  
   The corresponding chunk records, source records, and references are stored in `ship_computer.db`.

This separation allows the vector database to focus on similarity search while SQLite stores the relational context needed for citations, permissions, history, and application state.

### Query Workflow

When a user submits an Ask AI or Deep Dive inquiry, the application uses the embedding LLM and vector database to retrieve relevant context.

The query workflow is:

1. **Query normalization**  
   The user’s question is cleaned, expanded, or reformulated as needed.

2. **Query embedding**  
   The embedding LLM converts the question into a query vector.

3. **Vector search**  
   The vector database compares the query vector against stored embeddings and returns the most similar chunks.

4. **Metadata filtering**  
   The application may filter results based on user profile, source type, date, permissions, or session context.

5. **Ranking and reranking**  
   Retrieved chunks may be ranked by similarity score, recency, source authority, or other relevance signals.

6. **Context assembly**  
   `spock_rag_adapter/` assembles the retrieved chunks into a prompt context for the generation LLM.

7. **Generation**  
   The generation LLM produces an answer using the user question and retrieved context.

8. **Persistence**  
   The query, retrieved chunks, citations, answer, and session state are stored in `ship_computer.db`.

### How Ask AI Uses the Embedding LLM and Vector Database

Ask AI uses the embedding LLM and vector database to ground a single answer in relevant indexed content.

The process is:

1. The user asks a question.
2. The question is embedded.
3. The vector database retrieves the most relevant chunks.
4. The application assembles a prompt with the question and retrieved context.
5. The generation LLM answers the question.
6. The answer and supporting citations are stored.

Ask AI is best suited for questions that can be answered from a focused set of relevant passages. The database and vector store work together to ensure the answer is based on indexed knowledge rather than only the LLM’s general training.

### How Deep Dive Uses the Embedding LLM and Vector Database

Deep Dive uses the same retrieval foundation but applies it iteratively and more broadly.

The process is:

1. The user defines a Deep Dive topic or question.
2. The application performs an initial semantic search.
3. It evaluates the retrieved chunks for relevance and completeness.
4. It identifies gaps, related concepts, or additional sources worth exploring.
5. It generates refined subqueries.
6. It performs additional vector searches.
7. It accumulates evidence from multiple retrieval passes.
8. It produces a structured, detailed answer with citations.
9. It stores the full investigation trail in `ship_computer.db`.

Deep Dive benefits from the vector database because it can repeatedly search for semantically related content without requiring the user to know exact keywords. It benefits from SQLite because it can track the multi-step process, preserve citations, and support follow-up analysis.

### Relationship Between SQLite and the Vector Database

The SQLite database and vector database serve different but complementary roles.

| Component | Stores | Primary Use |
|---|---|---|
| `ship_computer.db` | Relational records, metadata, session state, history | Application state, citations, user data, audit trail |
| Vector database | High-dimensional embeddings and vector metadata | Semantic similarity search |
| Embedding LLM | Converts text into vectors | Enables semantic comparison between queries and content |

The two systems are linked through shared identifiers, such as chunk IDs, document IDs, or source IDs. For example:

- A chunk record in `ship_computer.db` may reference a vector ID in the vector database.
- A citation in an Ask AI response may reference both a chunk record and a source record.
- A Deep Dive step may reference multiple retrieved chunks and their associated vector search scores.

This design keeps semantic search efficient while preserving the relational context needed for the Spock application.

### Operational Considerations

Several operational factors affect the embedding and vector retrieval system:

- **Model versioning**  
  Embeddings generated by different models or versions may not be compatible. The application should store the embedding model name and version with each vector or chunk.

- **Vector dimension**  
  The dimension of the embedding vector must match the vector database configuration.

- **Chunk size**  
  Chunk size affects retrieval quality. Chunks that are too large may dilute relevance, while chunks that are too small may lack context.

- **Similarity threshold**  
  The application may use a minimum similarity score to avoid retrieving weakly related content.

- **Top-k selection**  
  The number of retrieved chunks affects both answer quality and prompt length.

- **Reindexing**  
  When source content changes, affected chunks and embeddings may need to be regenerated.

- **Fallback behavior**  
  If the embedding service or vector database is unavailable, the application may report degraded retrieval capability or fall back to another search method, depending on configuration.

### Summary

The Spock application uses the embedding LLM to convert text into semantic vectors and uses the vector database to find relevant content for Ask AI and Deep Dive inquiries. The SQLite 3 `ship_computer.db` database stores the relational state, metadata, session history, citations, and operational data that make these AI-assisted workflows persistent, traceable, and usable across the application.
## Naming Conventions

The repository uses two distinct naming patterns to communicate architectural intent:

| Pattern | Examples | Purpose |
|---|---|---|
| `spock_*` (snake_case) | `spock_bringup`, `spock_probe`, `spock_shell` | Reusable Python packages, each encapsulating a single capability such as a CLI tool, GUI component, or protocol adapter |
| PascalCase themed directories | `Orchestrator`, `NavigationStation`, `WarpCore` | Application-level groupings that compose one or more `spock_*` packages into a user-facing station, workflow, or shared kernel |

In practice, the naming convention signals architectural boundaries:

- Use **snake_case `spock_*` names** for standalone Python packages that can be imported, unit-tested, and reused independently across the codebase.
- Use **PascalCase themed directories** for higher-level application areas that orchestrate multiple capabilities into a coherent user experience or shared subsystem.

This distinction enforces separation of concerns, ensuring reusable building blocks remain decoupled from the larger application contexts in which they are deployed.

## SQLite 3 Database: `ship_computer.db`

The `ship_computer.db` file serves as the relational backbone of the Spock application. It stores structured metadata, configuration state, user profiles, permissions, and query history. Built on SQLite 3, it provides lightweight, serverless persistence that integrates seamlessly with the `WarpCore` shared kernel.

### Schema Design and Data Organization

The database schema, defined in `ship_computer_schema.sql`, is organized into logical domains:

- **System & Configuration Tables**: Store application settings, onboarding state, environment variables, and component health flags.
- **Knowledge & Document Metadata**: Track source documents, wiki pages, ingestion timestamps, chunk boundaries, content hashes, and permission flags. This metadata is cross-referenced with the vector database to maintain traceability.
- **User & Session Management**: Persist user profiles, authentication tokens, preference settings, and active session contexts.
- **Query & Interaction Logs**: Record historical prompts, AI responses, retrieval metrics, and user feedback to enable audit trails, analytics, and future retrieval optimization.

### Interaction with Ask AI and Deep Dive Inquiries

When a user initiates an **Ask AI** or **Deep Dive** inquiry, the application follows a coordinated data flow:

1. **Query Routing**: The `Orchestrator` intercepts the user prompt and routes it to the `spock_rag_adapter`.
2. **Metadata Resolution**: Before vector search, the adapter queries `ship_computer.db` to resolve document permissions, content freshness, source credibility flags, and user-specific access rules. This ensures only authorized and up-to-date knowledge is considered.
3. **Context Assembly**: For **Deep Dive** requests, the database retrieves extended metadata chains, including related documents, citation graphs, and historical query patterns. This relational context is merged with vector search results to construct a comprehensive prompt context.
4. **Response Logging**: After the LLM generates a response, the interaction is logged to `ship_computer.db` with timestamps, retrieval confidence scores, and user ratings. This data feeds analytics, monitoring, and future retrieval optimization.

SQLite’s ACID compliance and file-based architecture ensure reliable state management without requiring external database services, making it ideal for portable, self-contained AI workstations.

### Embedding LLM and Vector Database Integration

The Spock application uses an embedding model—referred to in the architecture as the embedding LLM—to convert natural-language text into dense numerical vectors. These vectors capture semantic meaning, allowing the application to find conceptually similar content even when the exact wording differs. The vector database stores these embeddings and performs approximate nearest-neighbor search, while `ship_computer.db` stores the relational metadata needed to filter, rank, trace, and audit the results.

#### Embedding Generation and Storage

During ingestion, the application processes source documents, wiki pages, and other knowledge artifacts through the following pipeline:

1. **Chunking**: Large documents are split into manageable chunks, such as paragraphs, sections, or semantic units.
2. **Embedding**: Each chunk is passed to the embedding model, producing a high-dimensional vector representation.
3. **Vector Storage**: The vector is stored in the vector database with a stable identifier, such as a chunk ID or document ID.
4. **Metadata Registration**: `ship_computer.db` records the corresponding metadata, including source location, content hash, ingestion timestamp, permissions, and relationships to other documents.

This separation allows the vector database to optimize semantic similarity search while SQLite preserves the authoritative, queryable context needed for governance and application logic.

#### Vector Search and Metadata Filtering

When a user submits a query, the Spock application embeds the prompt using the same embedding model used during ingestion. The resulting query vector is then used to search the vector database for the most semantically similar chunks.

The raw vector search results are not returned directly. Instead, the application enriches them with metadata from `ship_computer.db`:

- **Permission filtering**: Removes chunks the user is not authorized to access.
- **Freshness filtering**: Excludes stale or superseded content when newer versions exist.
- **Credibility weighting**: Applies source reliability scores or document status flags.
- **Context expansion**: Retrieves related chunks, parent documents, or citation-linked content for deeper reasoning.

This hybrid approach combines semantic relevance with relational constraints, producing a more accurate and auditable retrieval result than vector search alone.

#### Ask AI and Deep Dive Retrieval Strategies

**Ask AI** is optimized for concise, direct answers. It typically uses a smaller retrieval set, applies stricter permission and freshness filters, and prioritizes the most relevant chunks. The goal is to answer the user’s immediate question with minimal context and low latency.

**Deep Dive** is optimized for exploratory, multi-step analysis. It may retrieve a broader set of semantically related chunks, follow citation or relationship links stored in `ship_computer.db`, and incorporate historical query patterns to build a richer context. This allows the application to synthesize information across multiple sources, compare perspectives, and provide more detailed explanations.

#### Feedback and Continuous Improvement

After each response, the application records the query, retrieved chunk IDs, vector similarity scores, metadata filters applied, and user feedback in `ship_computer.db`. This feedback loop supports:

- Retrieval tuning, such as adjusting chunk sizes or similarity thresholds.
- Source quality monitoring, by identifying documents that frequently produce low-rated answers.
- Auditability, by preserving a traceable record of which knowledge artifacts influenced each response.
- Future model improvement, by providing labeled interaction data for evaluation or fine-tuning.

In summary, `ship_computer.db` and the vector database work together as complementary systems: the vector database finds semantically relevant content, while SQLite provides the structured context, permissions, history, and audit trail required for reliable Spock application behavior.
## Embedding LLM and Vector Database Integration

The Spock application leverages an embedding LLM and a vector database to power semantic search, context retrieval, and intelligent knowledge synthesis. This architecture forms the core of the Retrieval-Augmented Generation (RAG) pipeline.

### Embedding Generation Pipeline
1. **Text Ingestion**: Raw documents, wiki pages, and external data feeds are parsed and chunked by the `spock_wiki_adapter` and `LongRangeSensors` modules.
2. **Vectorization**: Each text chunk is passed through the embedding LLM, which transforms unstructured text into high-dimensional numerical vectors (embeddings). These vectors capture semantic meaning, contextual relationships, and topical similarity.
3. **Indexing**: Generated embeddings are stored in the vector database alongside metadata pointers (document ID, chunk index, source URL, and timestamp). The vector index is optimized for fast approximate nearest neighbor (ANN) search using algorithms such as HNSW or IVF.

### Query Resolution and Semantic Retrieval
When a user submits a query:
1. **Prompt Embedding**: The user’s natural language question is embedded using the same embedding model used during indexing to ensure vector space consistency.
2. **Similarity Search**: The vector database performs a cosine similarity or dot-product search against the indexed embeddings, returning the most semantically relevant chunks.
3. **Re-ranking & Filtering**: Results are filtered by metadata constraints (e.g., access control, recency, source type) and optionally re-ranked using cross-encoders or LLM-based scoring to improve precision.
4. **Context Injection**: The top-ranked chunks are formatted into a structured context window and injected into the generative LLM prompt alongside system instructions and user intent markers.

### Integration with Spock Architecture
- **`spock_rag_adapter`** orchestrates the end-to-end flow, managing embedding requests, vector queries, and context assembly.
- **`WarpCore`** provides caching layers to reduce redundant embedding computations and vector lookups for repeated queries.
- **Hybrid Search**: For complex **Deep Dive** inquiries, the system combines vector semantic search with keyword-based SQLite metadata queries, ensuring both conceptual relevance and exact factual matching.
- **Continuous Learning**: User feedback and interaction logs stored in `ship_computer.db` are periodically used to adjust retrieval thresholds, refresh cached embeddings, and optimize chunking strategies.

### Detailed Explanation of the Embedding LLM and Vector Database
An **embedding LLM** is a language model specialized for converting text into dense numerical vectors. In Spock, this model is used for two related but distinct tasks:
- **Indexing**: converting source documents, wiki pages, and retrieved data into embeddings that can be stored and searched.
- **Querying**: converting user questions into embeddings that can be compared against the indexed document embeddings.

Because both documents and queries are transformed by the same model, they exist in the same vector space. This allows Spock to measure semantic similarity rather than relying only on exact keyword matches.

A **vector database** is a storage and indexing system optimized for high-dimensional vectors. It stores each embedding with associated metadata and provides fast similarity search operations. In Spock, the vector database is responsible for answering questions such as:
- Which chunks are semantically closest to the user's question?
- Which sources are most relevant to a particular concept, entity, or intent?
- Which passages should be included in the context window for the generative LLM?

The vector database does not replace `ship_computer.db`. Instead, it complements it. The vector database handles semantic similarity, while `ship_computer.db` handles structured application state, permissions, user context, provenance, feedback, and audit data.

## SQLite 3 `ship_computer.db` and Spock Inquiry Integration

`ship_computer.db` is the local SQLite 3 database that stores Spock's operational state, user profiles, interaction history, retrieval metadata, and audit information. It is the system of record for non-vector data and provides deterministic, transactional access to the information needed to answer **Ask AI** and **Deep Dive** inquiries.

The database schema is defined in `ship_computer_schema.sql`, which contains the definitive DDL statements for tables, indexes, foreign key constraints, and triggers. This schema ensures data integrity, query performance, and consistent behavior across Spock's station modules and adapter packages.

### Database Responsibilities
- **Application state**: stores session identifiers, active profiles, feature flags, and configuration snapshots.
- **User context**: records user preferences, access scopes, and interaction history used to personalize and constrain retrieval.
- **Retrieval metadata**: maintains document identifiers, source URLs, chunk indexes, timestamps, permissions, and provenance links used by the vector database and RAG pipeline.
- **Feedback and evaluation**: captures user ratings, corrections, accepted or rejected answers, and Deep Dive follow-up questions to support retrieval tuning and auditability.
- **Audit and traceability**: logs query text, retrieved chunk IDs, embedding model versions, vector database versions, and response metadata for reproducibility.

### Ask AI Inquiry Flow
For **Ask AI** requests, Spock uses `ship_computer.db` to prepare a fast, scoped, and personalized query:
1. **Session and profile lookup**: `WarpCore` reads the active user profile, permissions, and recent context from SQLite.
2. **Query normalization**: The raw question is normalized, tokenized, and enriched with user-specific constraints such as preferred sources, language, or access level.
3. **Metadata pre-filtering**: SQLite queries identify eligible documents, recent updates, and excluded sources before vector search is executed.
4. **Vector search handoff**: The filtered metadata set is passed to `spock_rag_adapter`, which embeds the query and searches the vector database.
5. **Response assembly**: Retrieved chunks, SQLite metadata, and user context are combined into the final prompt for the generative LLM.
6. **Persistence**: The question, retrieved chunk IDs, response summary, and user feedback are written back to `ship_computer.db`.

### Deep Dive Inquiry Flow
For **Deep Dive** requests, Spock performs a more exhaustive investigation that combines semantic retrieval with structured database analysis:
1. **Intent decomposition**: The request is broken into sub-questions, entities, time ranges, and evidence requirements.
2. **Hybrid retrieval**: `spock_rag_adapter` issues vector similarity searches for conceptual relevance and SQLite queries for exact matches, relationships, timestamps, and permissions.
3. **Evidence graph construction**: Results from both sources are joined using shared identifiers such as document ID, chunk index, source URL, and entity keys.
4. **Cross-validation**: Conflicting or duplicate evidence is ranked using metadata freshness, source authority, user feedback, and retrieval scores.
5. **Synthesis**: The validated context is injected into the generative LLM prompt, with citations and provenance preserved.
6. **Learning loop**: The completed Deep Dive session, including user follow-ups and corrections, is stored in `ship_computer.db` for future retrieval tuning and audit review.

### Relationship Between SQLite and the Vector Database
The vector database and `ship_computer.db` are complementary rather than redundant:
- The **vector database** stores high-dimensional embeddings and optimizes semantic similarity search.
- **`ship_computer.db`** stores structured metadata, permissions, user context, feedback, and audit records.
- `spock_rag_adapter` coordinates both systems, using SQLite to constrain, enrich, and validate vector search results.
- `WarpCore` provides the shared database abstraction layer, ensuring consistent transactions, caching, and access control across both storage systems.

## Key Relationships

- **`WarpCore/`** serves as the shared application kernel. It encapsulates the database abstraction layer, profile management, and search utilities that all station modules and `spock_*` packages depend upon. Effectively, it provides the foundational data models and service interfaces for the entire system.
- **`Orchestrator/`** functions as the top-level application shell. It instantiates, hosts, and manages the lifecycle of individual station components (`NavigationStation`, `EngineeringDeck`, `LongRangeSensors`, `ScienceStation`). It acts as the primary runtime container, handling initialization, inter-component communication, and graceful shutdown sequences.
- **`spock_shell/`** is a PyQt6-based graphical interface framework comprising 24 modular components. It supplies reusable presentation-layer widgets and layout managers that other packages can integrate when a native GUI is required.
- **Adapter packages** (`spock_mcp_adapter`, `spock_rag_adapter`, `spock_wiki_adapter`) act as protocol bridges. They translate external data streams, API calls, and retrieval pipelines into standardized interfaces, enabling third-party systems and internal modules to interact with the onboarding and query systems seamlessly.
- **`ship_computer_schema.sql`** contains the definitive SQLite DDL statements. It defines all runtime tables, indexes, foreign key constraints, and triggers required to maintain data integrity and optimize query performance.
- **`gen_ref_pages.py`** is an automation script that dynamically generates API reference documentation. It synchronizes the MkDocs site in `docs/` with the current codebase, ensuring that developer documentation remains accurate across releases.
## SQLite 3 Database Architecture (`ship_computer.db`)

The `ship_computer.db` file is the persistent relational storage layer instantiated at runtime from `ship_computer_schema.sql`. It acts as the central state manager for the Spock application, handling user sessions, conversation history, document metadata, and query routing logic. The database is accessed exclusively through the `WarpCore/` database abstraction layer, which enforces connection pooling, transaction isolation, and parameterized query execution to prevent SQL injection and ensure thread safety.

### Interaction with "Ask AI" Inquiries
When a user initiates an **Ask AI** request, the Spock application leverages `ship_computer.db` for context assembly and session persistence:
- **Conversation History & Context Windows:** Each query and response is logged in a structured conversation table, indexed by session ID and user profile. The database retrieves the most recent interaction history to maintain conversational continuity and enforce token limits.
- **Prompt Template Resolution:** Dynamic prompt templates are stored in the database alongside variable mappings. The application fetches the appropriate template, injects user-specific context (role, preferences, security clearance), and prepares the final payload for the LLM.
- **Response Caching & Deduplication:** Identical or near-identical queries are checked against a hash-indexed cache table. If a match exists, the application serves the cached response directly, reducing latency and external API costs.
- **Audit & Telemetry:** Query timestamps, latency metrics, and model routing decisions are recorded for performance monitoring and compliance logging.

### Interaction with "Deep Dive" Inquiries
**Deep Dive** operations require structured, multi-step research workflows. The database supports this through specialized tables and relational joins:
- **Research Trail Persistence:** Each Deep Dive session generates a directed acyclic graph (DAG) of sub-queries, retrieved documents, and intermediate analysis steps. These are stored as relational records with parent-child foreign keys, enabling the UI to render interactive research trees.
- **Document Metadata & Source Attribution:** Retrieved documents are indexed with source URLs, extraction timestamps, confidence scores, and chunk boundaries. The database ensures that every AI-generated claim can be traced back to its originating data slice.
- **State Management & Checkpointing:** Long-running Deep Dive processes are checkpointed to the database. If the application restarts or a network interruption occurs, the orchestrator restores the exact query state, pending tasks, and partial results without data loss.
- **Cross-Reference Indexing:** The database maintains a full-text search index (via SQLite FTS5) over ingested documents, enabling rapid keyword fallbacks when semantic search returns low-confidence matches.

## Embedding LLM and Vector Database Integration

The Spock application employs a dual-model architecture to power semantic retrieval and response generation. This pipeline separates **semantic representation** (embedding LLM) from **content synthesis** (generative LLM), with the vector database acting as the high-dimensional index layer.

### Embedding LLM Role & Pipeline
The embedding model is a specialized, fixed-output neural network optimized for converting unstructured text into dense vector representations (typically 768–1536 dimensions). Its responsibilities include:
- **Ingestion Chunking:** Raw documents are split into semantically coherent chunks. Each chunk is passed through the embedding model to generate a fixed-length vector.
- **Query Transformation:** User prompts are embedded using the same model to ensure query and document vectors exist in the same mathematical space.
- **Similarity Scoring:** The application computes cosine similarity or inner-product distances between the query vector and stored document vectors to rank relevance.

### Vector Database Architecture
While `ship_computer.db` handles relational metadata and session state, the vector database (integrated via `spock_rag_adapter`) stores the high-dimensional embeddings. The integration follows these principles:
- **Hybrid Storage Strategy:** Vectors are stored in a dedicated vector index optimized for approximate nearest neighbor (ANN) search. Metadata pointers (document ID, chunk offset, source URI) are synchronized with `ship_computer.db` to maintain referential integrity.
- **Index Maintenance:** The vector index supports incremental updates. New documents are embedded and inserted asynchronously, while stale or deprecated chunks are marked for lazy deletion to preserve index performance.
- **Query Routing:** The Spock orchestrator routes semantic queries to the vector DB, applies hybrid filtering (metadata constraints + vector similarity), and returns a ranked context window to the generative LLM.

### Orchestration & Fallback Logic
The Spock application manages the end-to-end RAG pipeline through deterministic state machines:
1. **Context Assembly:** Retrieved vectors are decoded back into text chunks, deduplicated, and sorted by relevance score.
2. **Prompt Construction:** The ranked context is injected into the system prompt alongside instructions, formatting rules, and citation requirements.
3. **Generative LLM Invocation:** The final prompt is sent to the primary LLM. Streaming responses are parsed in real-time, with markdown and code blocks rendered by `spock_shell/`.
4. **Fallback & Error Handling:** If the vector DB returns insufficient context or the embedding model fails, the application gracefully degrades to keyword-based FTS5 search or direct LLM generation with explicit uncertainty disclaimers. All fallback events are logged to `ship_computer.db` for pipeline tuning.

## Module Counts

| Category | Packages | Files |
|----------|----------|-------|
| Star Trek–named | 6 | ~50 |
| `spock_`-prefixed | 11 | ~45 |
| Top-level modules | — | ~33 |
| **Total** | **17** | **~115** |

The package count excludes top-level modules because they are standalone Python files rather than package directories. The file total is approximate because some packages may contain generated, auxiliary, or environment-specific files.

### Explanation of Categories

- **Star Trek–named modules** refer to packages whose directory names use terminology inspired by *Star Trek* (e.g., `NavigationStation`, `WarpCore`). These modules may serve different architectural roles; for example, some act as user-facing stations or workflows, while others provide shared infrastructure.
- **`spock_`-prefixed modules** are lower-level components that implement specific functionality (e.g., `spock_onboarding`, `spock_probe`). They often contain internal utilities, adapters, probes, or operational tools used by higher-level application components.
- **Top-level modules** are standalone Python files at the project root that serve as entry points, orchestrators, or high-level coordinators for the system (e.g., `Orchestrator`, `ScienceStation`). They are counted by file count rather than package count because they are not organized as multi-file packages.

#### Functional vs. Naming Distinction

It is important to distinguish between naming conventions and architectural roles within this project:

- **Naming Conventions:** The "Star Trek–named" and "`spock_`-prefixed" categories describe the *naming style* of directories or files. This helps developers quickly identify thematic components (e.g., `WarpCore`) versus functional utilities (e.g., `spock_probe`).
- **Architectural Roles:** The "Top-level modules" category describes the *functional role* of a component, regardless of its naming convention. For example, `Orchestrator` is considered top-level because it coordinates system behavior, even if it does not follow the `spock_` or Star Trek naming conventions strictly.
- **Overlap and Counting Rules:** Some modules may be described both thematically and functionally (e.g., `WarpCore` has a Star Trek–inspired name but acts as shared infrastructure). The counts above use primary categorization to avoid double-counting while preserving useful documentation groupings.

> **Note on Primary Categorization:** When a module fits more than one category, it is assigned to the category that best reflects its dominant architectural responsibility. For example, `WarpCore` is counted under "Star Trek–named" because its directory name follows the thematic convention, even though its role is that of a shared infrastructure kernel. This keeps package counts mutually exclusive for tracking and documentation purposes.

### Architectural Overview

The project structure follows a layered architecture designed to separate concerns:

- **Infrastructure Layer:** Components like `WarpCore` provide shared services such as database access, profile management, search support, and other cross-cutting capabilities that other modules depend on.
- **Functional Layer:** Modules prefixed with `spock_` handle specific operational tasks such as health checks, status reporting, probing, data adaptation, or RAG-related processing. They consume infrastructure services and expose focused behavior to higher layers.
- **Interface Layer:** Star Trek–named modules (e.g., `NavigationStation`, `EngineeringDeck`) typically represent high-level user-facing stations, wizards, or workflows that coordinate functional components for end users.

#### Dependency Direction

Dependencies flow strictly downward through the layers: the Interface Layer depends on the Functional Layer, and the Functional Layer depends on the Infrastructure Layer. No module in a lower layer may import from a higher layer. This unidirectional dependency ensures that shared services remain decoupled from presentation logic and that specific functional tools can be tested or replaced without affecting user-facing components.

### Database Architecture: ship_computer.db

The persistent storage for the Spock application is managed via a SQLite 3 database file named `ship_computer.db`. This database serves as the central repository for system state, user profiles, knowledge graphs, and historical logs. It is orchestrated by the `WarpCore` module, which acts as the shared kernel responsible for managing connections, schema integrity, and data access patterns across the application stack.

> **Why SQLite?** A single-file SQLite 3 database was chosen to keep the application self-contained and portable. No external database server is required, which simplifies deployment and reduces configuration drift between environments. All modules access the database through `WarpCore` rather than opening direct connections, ensuring that connection lifecycle management, transaction handling, and schema checks are centralized.

#### SQLite 3 Operational Characteristics

- **Single-file storage:** `ship_computer.db` is a self-contained file that can be copied, backed up, or mounted in a local workspace.
- **Connection management:** `WarpCore` opens and closes connections as needed, applies pragmas, and enforces a consistent transaction policy.
- **Concurrency:** SQLite 3 supports concurrent readers and a single writer. In production-like deployments, WAL mode can be enabled to improve read/write concurrency while preserving file-based simplicity.
- **Data integrity:** Foreign keys, unique constraints, and check constraints help prevent orphaned sessions, duplicate inquiry logs, or invalid profile references.
- **Migrations:** Schema changes are applied through controlled migrations so that older database files can be upgraded without manual intervention.
- **Portability:** Because the database is file-based, the Spock application can run in local, containerized, or edge environments without requiring a separate database service.

#### Schema Definition

The structure of the database is defined in `ship_computer_schema.sql`. This DDL file ensures that all modules accessing the database adhere to a consistent set of tables, indexes, and constraints. Key entities typically include:

- **Profiles:** User-specific configurations, session states, and persistent user context.
- **Knowledge Graphs:** Nodes and edges representing relationships between data points for RAG (Retrieval-Augmented Generation) operations; related tables may also store text chunks, metadata, or retrieval indexes used during inquiry processing.
- **Logs:** Audit trails for system events, inquiry history, and diagnostic information.
- **Inquiry Sessions:** State for Ask AI and Deep Dive inquiries, including session identifiers, user context, step checkpoints, retrieved evidence, and final results.
- **Embeddings and Vector Indexes:** Numerical vector representations of text chunks and queries, along with metadata needed for similarity search, filtering, and citation.
- **Permissions and Access Control:** Rules that determine which profiles, stations, or inquiry modes may read or write specific knowledge, sessions, or logs.
- **Schema Versioning:** Migration records that allow `WarpCore` to validate, upgrade, or repair the database safely.

#### Interaction with Ask AI Inquiries

Ask AI is a lightweight inquiry mode in which a user submits a natural-language question and the Spock application returns a grounded answer. `ship_computer.db` participates in every stage of this flow, from resolving user context to persisting the final response.

1. **Session and profile resolution:** `WarpCore` loads the active profile, permissions, and any existing Ask AI session from `ship_computer.db`. This determines what knowledge the user may access and what context should be included in the prompt.
2. **Query normalization:** The application may rewrite, expand, or classify the question. If the question references prior context, the relevant session rows are read from the database.
3. **Retrieval preparation:** The query is converted into an embedding by the embedding LLM. The resulting vector is used to search the vector DB for semantically similar text chunks, knowledge-graph nodes, or related evidence.
4. **Evidence assembly:** `WarpCore` retrieves the top-ranked chunks and their metadata, such as source document, section, timestamp, permissions, and related graph edges. This evidence is assembled into a structured prompt for the generation LLM.
5. **Answer generation:** The generation LLM produces the answer using the retrieved evidence. The database is not used to generate the answer directly, but it supplies the context that makes the answer grounded and auditable.
6. **Persistence:** After the answer is produced, the application writes an inquiry log entry containing the question, answer, retrieved chunk identifiers, prompt version, model identifiers, token usage, latency, and any user feedback.
7. **Response delivery:** The user receives the answer, optionally with citations or source references that can be traced back to rows in `ship_computer.db`.

Because Ask AI is usually short-lived, the database operations are optimized for low latency: reads are performed in a read-only transaction, while writes are committed after the answer is available. If the retrieval step fails, the application can return a controlled error or fallback response without corrupting session state.

#### Interaction with Deep Dive Inquiries

Deep Dive is a stateful, multi-step inquiry mode used for more complex investigations. Unlike Ask AI, Deep Dive may decompose a question into subquestions, perform multiple retrieval passes, maintain hypotheses, and synthesize a longer report. `ship_computer.db` stores the durable state that allows Deep Dive to be resumable, auditable, and safe to retry.

1. **Session creation:** When a Deep Dive inquiry starts, `WarpCore` creates a session row with a unique identifier, profile reference, initial question, mode, and timestamp.
2. **Task decomposition:** The application may create step or subquestion rows that represent the investigation plan. Each step is linked to the parent session and may include status, priority, and dependencies.
3. **Iterative retrieval:** For each step, the embedding LLM converts the step text into a vector. The vector DB returns relevant chunks, graph nodes, or related evidence. The application may perform multiple searches with different filters, such as document type, time range, or knowledge domain.
4. **Evidence tracking:** Retrieved evidence is stored or referenced in session-specific tables. This allows the application to avoid duplicate retrieval, track which evidence supported which hypothesis, and provide citations in the final report.
5. **Hypothesis and synthesis state:** Intermediate conclusions, confidence levels, contradictions, and unresolved questions may be persisted so that a later synthesis step can reason over the full investigation history.
6. **Final report generation:** The generation LLM uses the accumulated evidence and session state to produce a structured Deep Dive report. The report may include summary, findings, evidence citations, limitations, and recommended follow-up actions.
7. **Finalization and audit:** The session is marked complete, and the final report, token usage, retrieval statistics, and user feedback are written to the logs. If the user cancels or the process times out, the session state remains in the database so it can be resumed or inspected.

Deep Dive therefore relies on `ship_computer.db` as a checkpoint store. This design prevents loss of work during long-running LLM calls and enables operational tools to diagnose failed or slow inquiries.

#### Embedding LLM and Vector Database

The Spock application uses an embedding LLM and a vector DB to support semantic retrieval for both Ask AI and Deep Dive. These components work together to turn natural-language questions into relevant evidence before the generation LLM produces an answer.

- **Embedding LLM:** An embedding LLM is a model that converts text into a fixed-size numerical vector, also called an embedding. The vector captures semantic meaning, so similar concepts produce vectors that are close together in vector space. The embedding LLM is used at two times: during indexing, when source text is converted into searchable vectors, and during inquiry, when the user's question is converted into a query vector.
- **Vector DB:** The vector DB stores embeddings together with metadata such as chunk identifier, source document, section, profile permissions, timestamp, and knowledge-graph relationships. It supports similarity search, typically using cosine similarity or another distance metric, to find the most relevant chunks for a query vector.
- **Indexing pipeline:** When knowledge is added or updated, the application chunks the text, generates an embedding for each chunk using the embedding LLM, and stores the vector and metadata in the vector DB. The chunking strategy, embedding model version, and vector dimension are recorded so that retrieval remains consistent and reproducible.
- **Query pipeline:** During an inquiry, the user's question is embedded using the same embedding model family and dimensionality. The vector DB searches for the nearest or most similar vectors, applies metadata filters, and returns a ranked set of candidate chunks. The application may then rerank candidates using lexical signals, graph relationships, recency, or user-specific relevance.
- **Relationship to `ship_computer.db`:** In this architecture, the vector DB may be implemented as tables inside `ship_computer.db`, as an adjacent vector store, or as an external service exposed through `WarpCore`. Regardless of the physical implementation, `WarpCore` provides a consistent data-access contract so that higher-level modules do not need to know whether vectors are stored in SQLite, a vector extension, or another backend.
- **Consistency and versioning:** Embeddings are versioned with the model that produced them. If the embedding model changes, the application can reindex affected chunks or maintain multiple vector indexes. This prevents incompatible vectors from being compared during search.
- **Security and privacy:** Because embeddings can reveal semantic information about the underlying text, access to the vector DB is governed by the same permissions and audit controls as the rest of `ship_computer.db`. Queries are filtered by profile and station permissions, and retrieval results are logged for accountability.

Together, the embedding LLM and vector DB enable the Spock application to perform grounded RAG: the system retrieves relevant evidence from the knowledge base, uses that evidence to constrain the generation LLM, and records the retrieval path in `ship_computer.db` for transparency and debugging.

#### Retrieval Quality and Operational Considerations

- **Top-k selection:** The application selects a configurable number of candidate chunks, balancing recall against prompt size and latency.
- **Reranking:** Initial vector search results may be refined using additional signals such as keyword overlap, graph proximity, document authority, or user-specific relevance.
- **Citations:** Retrieved chunks are linked to the final answer so users can inspect the source material and verify claims.
- **Failure handling:** If the embedding service, vector DB, or generation LLM is unavailable, the application can degrade gracefully, return a partial answer, or surface a clear operational error.
- **Performance:** Indexing, query embedding, vector search, and prompt assembly are measured and logged to support tuning and capacity planning.
- **Auditability:** Every Ask AI and Deep Dive inquiry can be traced from user question to retrieved evidence to final answer, supporting debugging, compliance, and continuous improvement.
The "Ask AI" functionality leverages the `spock_rag_adapter` module to query the database for relevant information. When a user submits an inquiry, the following workflow occurs:

1. **Context Assembly:** `WarpCore` retrieves the active user profile and recent session logs from `ship_computer.db` to establish baseline context. This context may include user preferences, active session state, previously accepted answers, and permission scope.
2. **Semantic Retrieval:** The inquiry text is passed to the embedding pipeline, which generates a vector representation. This vector is used to query the vector database for semantically similar documents, chunks, or knowledge graph nodes.
3. **Relational Filtering:** Retrieved candidates are cross-referenced with SQLite metadata tables to apply access controls, relevance scoring, and temporal filters. This step ensures that semantically similar results are also valid, current, and permitted for the requesting user.
4. **Response Generation:** The filtered context is injected into the LLM prompt. Once the response is generated, the complete inquiry-response pair, along with metadata such as latency, token usage, and retrieval sources, is written back to `ship_computer.db` for audit and future context windowing.

#### Interaction with Deep Dive Inquiries

"Deep Dive" inquiries follow a more intensive, multi-stage retrieval pattern optimized for complex, multi-hop reasoning:

1. **Query Decomposition:** The orchestrator breaks the user's prompt into sub-queries to target specific domains within the knowledge graph.
2. **Graph Traversal & Vector Expansion:** Instead of a single similarity search, the system performs iterative vector queries combined with SQLite-backed graph traversal. This allows the application to follow relational edges such as `depends_on`, `contradicts`, and `references` while maintaining semantic relevance.
3. **State Persistence:** Intermediate retrieval results, confidence scores, and traversal paths are temporarily cached in dedicated SQLite tables. This enables the system to resume interrupted deep dives or allow users to inspect the reasoning chain.
4. **Synthesis & Logging:** After gathering sufficient evidence, the LLM synthesizes a comprehensive response. The full execution trace, including all sub-queries, retrieved nodes, and final synthesis, is archived in `ship_computer.db` to support debugging, model fine-tuning, and user transparency.

### Embedding LLM and Vector Database Integration

The Spock application relies on a tightly coupled pipeline between an embedding language model (LLM) and a vector database to power semantic search and RAG capabilities. This integration operates independently of the relational SQLite store but coordinates with it through `WarpCore` and the `spock_rag_adapter`.

In this architecture, the embedding model and the generative LLM serve different purposes. The embedding model converts text into numerical vectors for similarity search. The generative LLM uses the retrieved context to produce a natural-language answer. The vector database stores and indexes the vectors, while SQLite stores the authoritative metadata, permissions, graph relationships, and audit records.

#### Embedding Generation Process

When raw text (documents, logs, or user queries) enters the system, it is first chunked into manageable segments using configurable token limits and overlap strategies. Each chunk is passed to the embedding LLM, which transforms the text into a high-dimensional numerical vector. These vectors capture semantic meaning, allowing similar concepts to cluster together regardless of lexical differences.

The embedding pipeline records the model name, model version, vector dimensionality, and content hash in `ship_computer.db`. This metadata allows the system to detect when a chunk has changed, when an embedding was generated by an outdated model, and when a vector must be regenerated.

#### Vector Storage and Indexing

The generated vectors are stored in a dedicated vector database optimized for high-dimensional similarity search. Unlike SQLite, which excels at structured, relational queries, the vector DB uses approximate nearest neighbor (ANN) algorithms (e.g., HNSW or IVF) to index embeddings. This enables fast retrieval of the most semantically relevant documents even across millions of entries. Metadata associated with each vector (source file, timestamp, author, access level) is stored alongside the embedding to enable hybrid filtering.

The vector database is optimized for similarity ranking, but it is not the system of record for permissions or document lifecycle. SQLite remains the authoritative source for which users may access a document, whether a chunk is current, and how chunks relate to knowledge graph nodes.

#### Retrieval and Context Assembly

During an inquiry, the user's prompt undergoes the same embedding process. The resulting query vector is compared against the indexed corpus using cosine similarity or inner product distance. The vector DB returns a ranked list of candidate chunks. Before these candidates are passed to the generative LLM, `spock_rag_adapter` performs a reconciliation step:

- **Metadata Validation:** SQLite is queried to verify that the retrieved chunks comply with user permissions and data freshness policies.
- **Deduplication & Re-ranking:** Overlapping or redundant chunks are filtered out, and remaining results are re-scored based on recency, source authority, and graph connectivity.
- **Prompt Construction:** The validated context is formatted into a structured prompt template, preserving citations and source references for transparency.

#### Lifecycle Management

Embeddings are not static. As new data is ingested or existing documents are updated, the system triggers incremental re-embedding jobs. `WarpCore` tracks embedding versions in `ship_computer.db`, ensuring that stale vectors are purged and that the vector index remains synchronized with the authoritative relational state. This hybrid architecture combines the speed and semantic intelligence of vector search with the reliability, auditability, and relational integrity of SQLite.

#### Request Processing Summary

1. **Retrieval:** The request is routed through `WarpCore`, which queries stored embeddings, keyword indexes, or knowledge-graph records in `ship_computer.db`.
2. **Context Assembly:** Relevant data chunks are retrieved from the knowledge graph tables and assembled into context for the AI model.
3. **Response Generation:** The AI generates a response based on this retrieved context, ensuring answers are grounded in the application's internal data rather than ungrounded external knowledge.

#### SQLite 3 `ship_computer.db` Architecture and Interaction

`ship_computer.db` is a centralized SQLite 3 database that serves as the persistent storage layer for the Spock application. It is engineered to balance relational integrity with flexible document-like storage, enabling both lightweight AI retrieval and heavy analytical workloads.

##### Purpose and Design Principles

`ship_computer.db` is the authoritative relational store for Spock. It provides ACID transactions, foreign-key integrity, auditability, and structured access control. It is not intended to replace the vector database; instead, it supplies the relational context that makes vector search safe, explainable, and permission-aware.

The database is designed around three principles:

- **Authoritative metadata:** SQLite stores the canonical identity, ownership, permissions, and lifecycle state of documents, chunks, graph nodes, and AI interactions.
- **Retrieval support:** SQLite stores the metadata needed to filter, rank, and explain vector search results.
- **Operational transparency:** SQLite records session state, deep-dive execution traces, model versions, token usage, and audit events.

Depending on deployment, SQLite features such as WAL mode, FTS5, and JSON1 may be enabled to improve concurrency, keyword search, and structured payload storage.

##### Core Table Groups

The following table groups describe the primary data structures used by Ask AI and Deep Dive workflows.

| Table group | Representative tables | Purpose |
|---|---|---|
| Identity and context | `users`, `user_profiles`, `sessions`, `session_logs` | Stores user identity, preferences, active session state, and recent interaction history. |
| Document and chunk metadata | `documents`, `chunks`, `chunk_versions` | Tracks source documents, chunk boundaries, content hashes, token counts, and update history. |
| Embedding metadata | `embedding_records`, `embedding_versions`, `vector_index_sync` | Maps chunks to vector database entries, records embedding model versions, and tracks synchronization status. |
| Knowledge graph | `knowledge_graph_nodes`, `knowledge_graph_edges` | Stores entities, concepts, and relationships such as `depends_on`, `contradicts`, and `references`. |
| Access control | `permissions`, `access_policies`, `resource_scopes` | Enforces user-level, role-level, and document-level access rules during retrieval. |
| AI interaction audit | `ai_inquiries`, `ai_responses`, `retrieval_candidates`, `audit_logs` | Records prompts, responses, retrieved sources, scores, latency, token usage, and system actions. |
| Deep Dive state | `deep_dive_runs`, `deep_dive_steps`, `traversal_paths` | Persists multi-stage reasoning state, sub-queries, intermediate evidence, and traversal paths. |

##### Ask AI Interaction

For Ask AI inquiries, `ship_computer.db` participates in every stage of the workflow:

1. **Session and permission lookup:** `WarpCore` reads the active user profile, session state, and permission scope from SQLite before any retrieval occurs.
2. **Candidate validation:** After the vector database returns candidate chunks, `spock_rag_adapter` joins those candidates against `embedding_records`, `chunks`, `documents`, and `permissions` to remove unauthorized, stale, or duplicate results.
3. **Context enrichment:** SQLite supplies metadata such as document title, author, timestamp, access level, and related graph nodes. This metadata is included in the prompt so the generative LLM can cite sources and respect context constraints.
4. **Audit persistence:** The inquiry, response, retrieved candidates, scores, model name, token counts, latency, and final prompt context are written to SQLite. This creates a durable record for debugging, compliance, and future context windowing.

A simplified Ask AI retrieval pattern is:

```sql
SELECT c.chunk_id,
       d.title,
       d.author,
       d.updated_at,
       er.model_version,
       er.vector_id
FROM embedding_records er
JOIN chunks c ON c.chunk_id = er.chunk_id
JOIN documents d ON d.doc_id = c.doc_id
WHERE er.vector_id IN (:candidate_vector_ids)
  AND d.access_level <= :user_access_level
  AND d.updated_at >= :minimum_freshness;
```

##### Deep Dive Interaction

For Deep Dive inquiries, `ship_computer.db` provides the relational backbone for multi-hop reasoning:

1. **Run initialization:** The orchestrator creates a `deep_dive_runs` record and stores the original prompt, user scope, and execution status.
2. **Sub-query tracking:** Each decomposed sub-query is stored in `deep_dive_steps`, allowing the system to resume, replay, or inspect individual reasoning stages.
3. **Graph traversal:** SQLite stores knowledge graph nodes and edges. The application can traverse relationships such as `depends_on`, `contradicts`, and `references` while using vector search to discover semantically related nodes.
4. **Intermediate evidence caching:** Retrieved nodes, candidate chunks, confidence scores, and traversal paths are persisted in SQLite. This makes the reasoning chain inspectable and supports recovery from interruptions.
5. **Final trace archival:** The completed Deep Dive trace, including sub-queries, retrieved evidence, rejected candidates, and final synthesis, is archived in SQLite for transparency, debugging, and model improvement.

A simplified Deep Dive traversal pattern is:

```sql
SELECT n.node_id,
       n.label,
       e.relation,
       e.confidence
FROM knowledge_graph_edges e
JOIN knowledge_graph_nodes n ON n.node_id = e.target_node_id
WHERE e.source_node_id = :current_node_id
  AND e.relation IN ('depends_on', 'references', 'contradicts')
ORDER BY e.confidence DESC;
```

##### Consistency, Permissions, and Audit

`ship_computer.db` enforces consistency between the vector index and the application's authoritative data. When a document is updated, deleted, or re-permissioned, `WarpCore` updates the relevant metadata tables and marks affected embeddings for re-embedding or removal. The vector database may temporarily contain stale vectors, but SQLite determines whether those vectors are eligible for retrieval.

This separation gives Spock a practical hybrid architecture:

- The vector database provides fast semantic discovery.
- SQLite provides permission enforcement, relational context, graph traversal, and durable auditability.
- `WarpCore` and `spock_rag_adapter` coordinate the two systems so that Ask AI and Deep Dive responses are both semantically relevant and operationally trustworthy.
#### SQLite 3 `ship_computer.db` Overview

The Spock application uses SQLite 3 as its embedded persistence and retrieval layer. `ship_computer.db` is a single-file database that stores structured application state, inquiry history, system logs, profile data, and vector embeddings. This design allows the application to run locally with minimal operational overhead while still supporting relational queries, full-text search, and semantic similarity search.

- **Schema Design:** The database utilizes a normalized relational structure for core entities such as user profiles, system logs, inquiry history, and sensor or state records. JSON columns are used for semi-structured metadata, such as device attributes, event payloads, or model-specific fields. This hybrid approach enforces strict schema constraints where data is stable while allowing dynamic fields to evolve without frequent migrations.
- **Indexing Strategy:** B-tree indexes accelerate primary key, foreign key, and common filter lookups. Full-Text Search (FTS5) virtual tables support keyword-based retrieval over logs, documents, and inquiry text. Vector similarity search is supported through SQLite vector extensions such as `sqlite-vec` or `VSS`, or through BLOB storage with application-level distance calculations when an extension is unavailable.
- **Interaction with Ask AI:** For standard inquiries, `WarpCore` executes lightweight, read-optimized queries. It retrieves top-K vector matches and keyword hits, then joins them with metadata tables to assemble a concise context window. Queries are strictly read-only during inference to prevent write contention and to keep response latency predictable.
- **Interaction with Deep Dive:** Complex analytical requests trigger multi-table JOINs, window functions, and aggregate calculations. `WarpCore` dynamically constructs parameterized SQL statements that correlate historical logs, profile states, and sensor data. The database returns consolidated datasets rather than raw rows, reducing payload size and simplifying downstream Python processing.
- **Concurrency & Performance:** SQLite operates in Write-Ahead Logging (WAL) mode, allowing multiple concurrent readers while maintaining a single writer. Connection pooling and statement caching minimize overhead, ensuring stable latency even under sustained analytical loads.

#### Core Tables and Relationships

The following table groups describe the primary data domains stored in `ship_computer.db`.

- **Identity and profile tables:** Store user or operator profiles, access levels, preferences, and device associations.
- **Inquiry tables:** Store Ask AI and Deep Dive requests, prompts, retrieved context, generated responses, and confidence scores.
- **Log and event tables:** Store system events, sensor readings, state transitions, and diagnostic messages.
- **Document and chunk tables:** Store source text, chunk boundaries, content hashes, and metadata needed for retrieval.
- **Vector tables:** Store embedding vectors, dimensions, model identifiers, and foreign keys to source chunks or records.
- **Full-text search tables:** FTS5 virtual tables mirror searchable text from logs, documents, and inquiry history to support keyword retrieval.

#### Ask AI Inquiry Flow

"Ask AI" is the retrieval-oriented path used for direct questions, status checks, and short-form assistance. The goal is to return a fast, grounded answer using the most relevant local context.

1. **Input normalization:** The user's question is cleaned, tokenized, and optionally expanded with known aliases or domain terms.
2. **Hybrid retrieval:** `WarpCore` issues parallel read-only queries against FTS5 tables and the vector store. Keyword results capture exact terms, while vector results capture semantic intent.
3. **Ranking and filtering:** Results are scored by relevance, recency, access permissions, and source confidence. Low-quality or unauthorized records are removed.
4. **Context assembly:** The selected records are joined with metadata tables to produce a compact context window for the LLM.
5. **Answer generation:** The LLM generates a concise response using only the assembled context. The final answer is logged to the inquiry history table for audit and future retrieval.

#### Embedding LLM and Vector Database Integration

The Spock application integrates an embedding LLM and a vector storage layer directly within the `ship_computer.db` ecosystem, eliminating the need for an external vector database while maintaining high-performance semantic search.

- **Embedding Generation:** When new documents, logs, or profile updates are ingested, the embedding LLM converts textual content into high-dimensional numerical vectors. These vectors capture semantic meaning, enabling similarity matching beyond exact keyword matches.
- **Vector Storage & Indexing:** Embeddings are stored as BLOBs or structured arrays within dedicated SQLite tables, paired with metadata pointers such as source ID, timestamp, content type, and access level. A vector index is maintained using approximate nearest neighbor (ANN) algorithms available through SQLite vector extensions, or through optimized application-level search for smaller datasets.
- **Query Pipeline:** 
  1. User input is passed to the embedding LLM to generate a query vector.
  2. `WarpCore` executes a cosine similarity or L2 distance search against the vector index.
  3. The top-K most relevant records are retrieved, filtered by access permissions and recency thresholds.
  4. Retrieved vectors are discarded; only the associated text chunks and metadata are passed to the context assembly stage.
- **Context Window Management:** To prevent token overflow, the system applies dynamic chunking and relevance scoring. Low-confidence matches are pruned, and overlapping segments are deduplicated before the final context is injected into the LLM prompt.
- **Update & Synchronization:** Embeddings are regenerated incrementally. When source data changes, only affected records are re-embedded and re-indexed, ensuring the vector store remains synchronized with the relational schema without full database rebuilds.

#### How the Spock Application Uses the Embedding LLM and Vector Database

The embedding LLM and vector database work together to provide semantic understanding of local data. The embedding LLM is not used to generate the final answer directly; instead, it converts text into numerical representations that can be compared efficiently. The vector database stores those representations and retrieves the closest matches to a user's question.

- **Ingestion:** When a log entry, profile update, document, or inquiry record is created, the application extracts the relevant text, chunks it if necessary, and sends it to the embedding LLM.
- **Storage:** The resulting vector is stored in a vector table alongside a foreign key to the source record. This keeps the vector store synchronized with the relational schema and allows permission checks to be applied during retrieval.
- **Retrieval:** For an Ask AI request, the user's question is embedded using the same model used during ingestion. The query vector is compared against stored vectors to find semantically similar records.
- **Hybrid ranking:** Vector similarity is combined with FTS5 keyword scores, recency, and metadata filters. This improves accuracy for both natural-language questions and exact technical terms.
- **Model consistency:** The embedding model name, version, and vector dimension are stored with each vector. If the embedding model changes, affected records are re-embedded to maintain compatibility.
- **Fallback:** If a vector extension is unavailable, the application can fall back to BLOB-based storage and compute distances in Python. This fallback is slower but preserves functionality for small or medium-sized datasets.

#### Interaction with Deep Dive Inquiries

"Deep Dive" inquiries represent complex analytical requests that require deeper access to system history and detailed profiles. These interactions involve:

- **Context loading:** `WarpCore` retrieves relevant profile records, prior inquiry logs, and related state from the database.
- **Analysis:** `spock_` modules perform targeted checks, comparisons, or aggregation over the retrieved data.
- **Synthesis:** The results are combined into a detailed explanation, diagnostic summary, or recommendation for the user.

1. **Complex Querying:** The `WarpCore` kernel executes multi-step SQL queries against the SQLite database to aggregate data from multiple tables—for example, joining profile records with sensor log entries. These queries are designed to return consolidated results rather than raw rows from a single table.

2. **State Analysis:** Unlike "Ask AI," which is primarily retrieval-oriented, "Deep Dive" performs analytical work over stored state. It may examine trends, correlations, or historical patterns in the database to support higher-level reasoning about system behavior.

3. **Resource Management:** Because analytical queries can be resource-intensive, `WarpCore` may apply targeted indexing strategies and query-planning controls within `ship_computer.db`. This helps keep response times stable during heavy read workloads while avoiding unnecessary write amplification.

#### Data Persistence and Integrity

- **Atomicity:** Write operations are wrapped in SQLite transactions so that a change is either fully committed or fully rolled back. This prevents partial updates if the process crashes, loses power, or restarts unexpectedly.
- **Isolation:** The database files are kept separate from the application shell's working file system and GUI-managed directories. This reduces the risk of accidental deletion, overwriting, or corruption by non-database components.
- **Backup Strategy:** `WarpCore` monitors `ship_computer_schema.sql` for schema changes. When a change is detected, it can create a backup and apply migrations automatically before updating the live database structure.