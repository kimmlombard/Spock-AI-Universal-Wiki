# Testing

## Framework

- Detected: **pytest**

### Framework explanation

`pytest` is a mature, feature-rich Python testing framework used to discover, execute, and report on test files and functions. The codebase scan confirms that `pytest` is the primary testing infrastructure for this project. It provides built-in fixtures, parameterization, assertion introspection, and detailed failure reporting.

## Test files (sample)

- `tests/test_acquire_codebase_knowledge.py`
- `tests/test_acquire_launch_handoff.py`
- `tests/test_ask_grounding.py`
- `tests/test_bringup.py`
- `tests/test_db_browser_grid.py`
- `tests/test_fit_match.py`
- `tests/test_good_results_coach.py`
- `tests/test_health.py`
- `tests/test_host_recipe_drift.py`
- `tests/test_launch_settings.py`
- `tests/test_llama_process.py`
- `tests/test_llmfit_bridge.py`
- `tests/test_path_filter.py`

### Sample explanation

The list above is a sample of test file paths discovered during the scan, not an exhaustive inventory. These files follow the standard `tests/test_*.py` naming convention, which allows `pytest` to discover and run them automatically without explicit configuration.

## How to run

```bash
python -m pytest
```

### Run command explanation

Running `python -m pytest` invokes the testing framework as a Python module from the project root. The command triggers automatic test discovery, executes all matching test files, and produces a consolidated execution report. Additional flags can be appended as needed, such as `-v` for verbose output or `-k` for keyword filtering.

### Raw scan excerpt

```
No performance testing configs detected.
```

### Raw scan excerpt explanation

This observation indicates that the static analysis scan did not identify configuration files or dependencies associated with performance or load testing, such as `pytest-benchmark`, `locust`, or `k6`. Functional and unit tests remain the primary validation mechanism within the scanned scope.

## Evidence

- `D:\Spock-Universal-AI-Wiki\docs\codebase\.codebase-scan.txt`
- Filters: `.gitignore` + `scan.skip_dirs` + built-in extras

### Evidence explanation

The scan output file at the specified path is the authoritative source for the findings in this section. The scan applied a layered filtering strategy to determine inclusion and exclusion boundaries, ensuring that only relevant source files were analyzed.

### Filter details

- `.gitignore`: Enforces repository-level ignore rules to exclude version-controlled artifacts, temporary files, and environment-specific configurations.
- `scan.skip_dirs`: Applies project-specific directory exclusions defined in the scan configuration to bypass non-essential or generated folders.
- `built-in extras`: Applies the scanner's default exclusion rules for common build artifacts, caches, virtual environments, and dependency directories.

## SQLite 3 Database (`ship_computer.db`) Architecture

The Spock application relies on a local SQLite 3 database named `ship_computer.db` to persist structured metadata, query history, configuration states, and cached inference results. SQLite is selected for its zero-configuration deployment, ACID compliance, and efficient read/write performance for single-user or low-concurrency workloads typical of local AI assistant applications.

### Interaction with Spock: Ask AI and Deep Dive Inquiries

When a user initiates an **Ask AI** or **Deep Dive** inquiry, the Spock application orchestrates a multi-step interaction with `ship_computer.db`:

1. **Context Retrieval & Grounding**: Before routing the prompt to the LLM, Spock queries the database for relevant historical context, user preferences, and previously resolved entities. This ensures responses are grounded in the user's specific project state and conversation history.
2. **Query Logging & State Management**: Each inquiry is logged with timestamps, session IDs, and metadata tags. For **Deep Dive** requests, which typically involve multi-turn reasoning or extensive codebase traversal, the database tracks intermediate reasoning steps, cached embeddings, and dependency graphs to prevent redundant computation and maintain traceability.
3. **Result Caching & Deduplication**: To optimize latency and reduce token consumption, Spock checks `ship_computer.db` for semantically similar past queries. If a match exceeds a configured similarity threshold, the cached response is returned or used as a prefix for incremental generation.
4. **Transaction Safety**: All write operations during inquiry processing are wrapped in SQLite transactions. This guarantees data integrity and prevents partial writes even if the application encounters interruptions during long-running Deep Dive operations.
5. **Schema Versioning**: The database includes a version-tracking table that allows Spock to apply incremental schema migrations safely, ensuring backward compatibility as new inquiry features are introduced.

### Database responsibilities

`ship_computer.db` is the system of record for structured application state. It is responsible for:

- Preserving user sessions, inquiry history, and conversation context.
- Storing configuration, preferences, and feature flags.
- Tracking codebase chunks, content hashes, and version metadata.
- Recording embedding metadata, vector index references, and retrieval provenance.
- Caching normalized prompts, responses, and intermediate Deep Dive results.
- Providing auditability for Ask AI and Deep Dive outputs.
- Supporting safe schema migrations and local backups.

### Core tables and their roles

The exact table names may vary by implementation, but the logical schema typically includes the following categories:

| Table or table group | Purpose |
|---|---|
| `schema_version` | Tracks database schema version and applied migrations. |
| `sessions` | Stores user or application session identifiers, start/end times, and session-level settings. |
| `inquiries` | Records each Ask AI or Deep Dive request, including type, status, timestamps, and parent/child relationships. |
| `messages` | Stores user prompts, assistant responses, system prompts, and message metadata. |
| `entities` | Tracks named entities, files, functions, classes, documents, or concepts referenced during an inquiry. |
| `codebase_chunks` | Stores chunk identifiers, source paths, content hashes, line ranges, and version information. |
| `embeddings_metadata` | Stores embedding model, vector dimension, content hash, vector store reference, and creation time. |
| `response_cache` | Caches normalized prompts, similarity scores, response payloads, and cache validity metadata. |
| `preferences` | Stores user or workspace preferences that influence retrieval, grounding, and response style. |
| `audit_log` | Records significant events, errors, fallbacks, and permission or policy decisions. |

### Ask AI detailed flow

An **Ask AI** inquiry is a grounded, usually single-turn question that Spock answers using local context, conversation history, and semantic retrieval.

1. **Intake and session binding**  
   Spock creates or reuses a session and records the inquiry in `ship_computer.db`. The record includes the prompt, user context, timestamp, and inquiry type.

2. **Structured context lookup**  
   Before calling the model, Spock queries the database for relevant session state, recent messages, user preferences, and previously resolved entities. This helps the response reflect the user's current project and conversation.

3. **Semantic retrieval**  
   Spock embeds the user prompt using the embedding model and queries the vector database for semantically similar code chunks, documents, or conversation summaries. SQLite stores the metadata needed to retrieve, filter, and cite those results.

4. **Prompt assembly**  
   Spock combines the user prompt, retrieved context, preferences, and any cached or previously resolved information into a structured prompt for the answer-generation model.

5. **Response generation and persistence**  
   After the model returns an answer, Spock stores the response, citations, token usage, latency, and confidence or grounding metadata in `ship_computer.db`.

6. **Caching and deduplication**  
   Spock may store a normalized prompt hash and embedding reference in the response cache. If a later Ask AI request is sufficiently similar, Spock can return the cached answer or use it as a grounding prefix, reducing latency and token usage.

### Deep Dive detailed flow

A **Deep Dive** inquiry is a longer, multi-step investigation. It may involve repeated retrieval, code traversal, dependency analysis, and synthesis of a detailed report.

1. **Run creation**  
   Spock creates a Deep Dive run record in `ship_computer.db`, including the objective, scope, constraints, and initial context.

2. **Planning and decomposition**  
   Spock breaks the objective into subquestions or investigation steps. Each step is stored as a child inquiry or task record so the process can be inspected, resumed, or replayed.

3. **Iterative retrieval**  
   For each step, Spock embeds the subquestion, queries the vector database, and retrieves relevant chunks. It may also use SQLite to filter by file path, entity, version, or session scope.

4. **Evidence accumulation**  
   Retrieved chunks, code symbols, dependency relationships, and intermediate conclusions are stored with provenance metadata. This allows Spock to cite sources and avoid repeating work.

5. **Checkpointing**  
   Because Deep Dive operations can be long-running, Spock commits intermediate state to SQLite at safe points. If the process is interrupted, Spock can resume from the last committed checkpoint.

6. **Synthesis and final report**  
   Spock synthesizes the accumulated evidence into a final answer or report. The final output, citations, reasoning steps, and performance metrics are persisted for auditability.

### Transaction safety and consistency

All write operations during Ask AI and Deep Dive processing are wrapped in SQLite transactions. This ensures that partial writes are not committed if an error occurs. For long-running Deep Dive operations, Spock uses incremental commits and checkpoints to preserve progress while maintaining data integrity.

### Schema versioning and migrations

The database includes a version-tracking mechanism that allows Spock to apply incremental schema migrations safely. This supports backward compatibility and controlled introduction of new inquiry features, retrieval fields, or caching columns.

## Embedding LLM and Vector DB

Spock uses an embedding model, often referred to in this architecture as the embedding LLM, together with a vector database, or vector DB, to provide semantic retrieval. The embedding model converts text into numerical vectors, and the vector DB indexes those vectors for fast similarity search. This allows Spock to find relevant code, documentation, conversation history, or project knowledge even when the wording of the user's question differs from the wording of the stored content.

### Purpose of the embedding and vector layer

The embedding and vector layer provides semantic grounding for Spock's AI responses. It complements `ship_computer.db` by handling approximate similarity search, while SQLite handles exact structured state, metadata, history, and provenance.

Together, they enable Spock to:

- Retrieve relevant context for Ask AI questions.
- Support iterative evidence gathering during Deep Dive investigations.
- Reduce reliance on brittle keyword matching.
- Improve answer relevance, citation quality, and consistency.
- Cache and reuse embeddings for repeated or similar content.

### How Spock uses the embedding LLM

The embedding LLM is a model that produces fixed-size vector representations of text. It is separate from the answer-generation model that produces natural-language responses.

Spock uses the embedding model in the following ways:

1. **Chunk embedding**  
   Code files, documentation, conversation summaries, and other knowledge sources are split into chunks. Each chunk is embedded into a vector.

2. **Prompt embedding**  
   When a user submits an Ask AI or Deep Dive request, Spock embeds the prompt or subquestion to create a query vector.

3. **Similarity comparison**  
   The query vector is compared against stored vectors using a similarity metric, commonly cosine similarity.

4. **Caching**  
   Embeddings are cached by content hash. If a chunk has not changed, Spock reuses the existing vector instead of re-embedding it.

5. **Re-embedding on change**  
   When code, documentation, or conversation context changes, Spock re-embeds affected chunks and updates the vector database.

### How Spock uses the vector DB

The vector DB stores embeddings and supports approximate nearest-neighbor search. It may be implemented as a local vector store or a SQLite-backed vector index, depending on the deployment. In either case, Spock abstracts the storage behind a retrieval interface.

The vector DB is used to:

- Store embeddings for code chunks, documents, entities, and conversation summaries.
- Index vectors for fast similarity search.
- Return the most relevant chunks for a given query vector.
- Support metadata filtering, such as file path, session, project, version, or content type.
- Enable reranking or hybrid retrieval when combined with keyword search.

### Ask AI usage pattern

For an Ask AI inquiry, Spock typically follows this pattern:

1. Receive the user's question.
2. Embed the question using the embedding model.
3. Query the vector DB for the most relevant chunks.
4. Use SQLite to retrieve metadata, preferences, session context, and citation information.
5. Assemble a grounded prompt for the answer-generation model.
6. Store the response, retrieved context, and provenance in `ship_computer.db`.

This pattern allows Spock to answer questions with context that is semantically related to the user's request, rather than relying only on exact keyword matches.

### Deep Dive usage pattern

For a Deep Dive inquiry, Spock uses the embedding and vector layer repeatedly:

1. Decompose the investigation into subquestions.
2. Embed each subquestion.
3. Retrieve relevant chunks for each subquestion.
4. Store retrieved evidence and intermediate conclusions in SQLite.
5. Use the accumulated evidence to generate follow-up subquestions.
6. Continue until the investigation reaches a stopping condition.
7. Synthesize the final report and persist the full reasoning trail.

This iterative use of embeddings and vector search allows Deep Dive to explore a codebase or knowledge base more thoroughly than a single retrieval pass.

### Caching, invalidation, and consistency

Spock uses caching to improve performance and reduce repeated embedding work.

- **Embedding cache**: Stored by content hash, model name, and vector dimension.
- **Response cache**: Stored by normalized prompt, context version, and similarity threshold.
- **Invalidation**: Triggered when source content, schema version, embedding model, or retrieval policy changes.
- **Consistency**: SQLite remains the source of truth for metadata and provenance, while the vector DB is treated as a derived index that can be rebuilt if necessary.

### Failure handling and fallback

If the embedding model or vector DB is unavailable, Spock can degrade gracefully by:

- Falling back to SQLite-based keyword or metadata search.
- Returning a limited answer with a warning that semantic retrieval is unavailable.
- Logging the failure in the audit log.
- Retrying embedding or vector search operations when appropriate.

This design keeps the core application functional while preserving transparency about the level of grounding available for each response.
## Embedding LLM and Vector Database Integration

Spock leverages a dedicated embedding model (typically a lightweight, locally-hosted transformer or distilled LLM) to convert unstructured text, code snippets, and documentation into high-dimensional numerical vectors. These vectors are stored in a vector database (or a vector-capable SQLite extension) to enable fast semantic similarity search and retrieval-augmented generation.

### How Spock Utilizes Embeddings and Vector Search

The embedding and vector search pipeline operates as follows:

- **Ingestion & Chunking**: Raw documents, code files, and wiki entries are parsed and split into semantic chunks. Each chunk is passed through the embedding LLM to generate a fixed-length vector representation that captures contextual meaning rather than exact keyword matches.
- **Vector Indexing**: The generated vectors are indexed using approximate nearest neighbor (ANN) algorithms (e.g., HNSW or IVF) to enable sub-millisecond retrieval. Metadata such as file paths, line numbers, chunk IDs, and source types are attached to each vector for traceability and filtering.
- **Semantic Query Routing**: When a user submits a query, Spock first embeds the prompt using the same model. The resulting query vector is compared against the indexed corpus to retrieve the most contextually relevant chunks based on cosine similarity or inner product distance.
- **Retrieval-Augmented Generation (RAG)**: The top-k retrieved chunks are injected into the LLM's context window alongside the original prompt. This grounding mechanism significantly reduces hallucination and ensures that **Ask AI** and **Deep Dive** responses are directly tied to verified project data.
- **Dynamic Re-embedding & Index Maintenance**: As the codebase or documentation evolves, Spock triggers incremental re-embedding jobs. The vector index is updated asynchronously to maintain search accuracy without blocking user interactions, and stale vectors are automatically pruned based on file modification timestamps.