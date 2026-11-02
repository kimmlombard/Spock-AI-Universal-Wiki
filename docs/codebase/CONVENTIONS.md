# Conventions

## Observed conventions

- Python packages use PascalCase or snake_case directory names and include an `__init__.py` file.
- Wiki agent skills are implemented as methods on the `Skills` class and validated through `WarpCore.skills`.
- Prefer `spock_shell.paths` for resolving ROOT and database paths rather than hard-coding path values.
- [TODO] The scan did not detect a root-level `ruff`, `black`, or `flake8` configuration file.

### Conventions explained

- A Python package directory is an explicit directory that contains `__init__.py`; the observed convention allows either PascalCase or snake_case naming for such directories.
- The `Skills` / `WarpCore.skills` convention describes how agent capabilities are exposed as callable methods and validated through the `WarpCore.skills` registry.
- Using `spock_shell.paths` centralizes path resolution, which helps keep ROOT and database path handling consistent across environments and prevents path-related runtime errors.
- The TODO item records a scan finding about missing linting/formatting configuration; it is not itself a confirmed project rule.

## Error handling

- Skills return `SkillResult(ok, evidence, log_lines)` instead of raising exceptions into the queue loop.
- GUI long-running work uses a wait cursor and a busy `QProgressBar` via `spock_shell.busy_ui`.

### Error handling explained

- `SkillResult` is a structured result object that reports whether a skill succeeded (`ok`), provides supporting evidence, and includes relevant log lines. By returning this value instead of raising exceptions, the queue loop can record failures, continue processing subsequent items, and avoid unhandled exception crashes.
- The GUI pattern communicates that long operations are in progress by showing a wait cursor or busy progress indicator. `spock_shell.busy_ui` centralizes this behavior so user-facing code does not need to manage Qt cursor and progress-bar state manually.

### Raw scan excerpt

```
No linting or formatting config files found in project root.
```

## Evidence

- `D:\Spock-Universal-AI-Wiki\docs\codebase\.codebase-scan.txt`
- Filters: `.gitignore` + `scan.skip_dirs` + built-in extras

### Evidence explained

- The evidence file is the scan output that supports the observations above.
- The filters describe exclusion rules used during scanning: entries from `.gitignore`, configured `scan.skip_dirs`, and additional built-in exclusions.

## SQLite 3 Database: `ship_computer.db`

### Database Overview and Schema

`ship_computer.db` is the SQLite 3 database that provides persistent state for the Spock application. It is the system of record for application metadata, query history, session context, skill state, and references to external knowledge assets such as document chunks and vector-store identifiers.

The database is optimized for read-heavy workloads and uses SQLite's ACID behavior to keep state consistent while multiple skills or background jobs may read and write data. It does not replace the vector database; instead, it stores the metadata needed to locate, validate, cache, and audit the data used by Ask AI and Deep Dive.

Core tables include:

- `documents`: Stores metadata about ingested files, including file path, content hash, source type, ingestion timestamp, and processing status.
- `embeddings_index`: Maps document chunks to vector-store identifiers, chunk text or chunk references, embedding model version, and retrieval metadata.
- `query_log`: Records user prompts, skill invocations, routing decisions, response summaries, latency, token usage, and retrieval metrics for auditing and analytics.
- `sessions`: Tracks active conversation contexts, user preferences, temporary state, and multi-turn interaction history.
- `skills_registry`: Maintains skill configuration, availability status, dependency information, and version metadata for agent skills.

### Interaction with Ask AI Inquiries

When a user submits an "Ask AI" inquiry, the Spock application treats the request as a lightweight retrieval-augmented generation task. The skill first resolves the database path through `spock_shell.paths`, then checks `ship_computer.db` for cached responses, recent session context, or previously resolved intents.

If a sufficiently similar cached response exists, the application may return the cached result to reduce latency and avoid unnecessary LLM calls. If no cache exists, the application embeds the user prompt using the embedding LLM, searches the vector database for relevant chunks, and retrieves the associated document metadata from `ship_computer.db`.

The raw prompt, timestamp, routing decision, retrieved chunk identifiers, and final response summary are written to `query_log`. If the request is part of a multi-turn conversation, the relevant context is also stored in `sessions`. The final answer and supporting citations are returned to the user through a `SkillResult`, with evidence and log lines available for inspection.

### Interaction with Deep Dive Inquiries

"Deep Dive" requests trigger a more intensive retrieval-augmented generation workflow. The application uses `ship_computer.db` to identify high-relevance document clusters and to apply metadata filters such as date ranges, source credibility, topic tags, document type, and ingestion status.

The database returns structured pointers to the vector store, including chunk identifiers, vector-store IDs, and metadata needed to fetch dense vector representations or precomputed chunk text. The Spock application then performs one or more vector searches, reranks candidates, and may issue follow-up embeddings to explore related concepts.

Throughout the Deep Dive process, intermediate reasoning steps, retrieved context chunks, confidence scores, filter selections, and final evidence chains are persisted in `ship_computer.db`. This allows the application to produce transparent, traceable outputs and lets users review the evidence that supported the final answer. Because Deep Dive can be long-running, the GUI uses `spock_shell.busy_ui` to show a wait cursor or busy progress indicator while the skill executes.

### Ask AI and Deep Dive Data Flow

1. The user submits an Ask AI or Deep Dive request through the Spock GUI or shell.
2. The request is routed to the appropriate skill method on the `Skills` class.
3. The skill validates its configuration through `WarpCore.skills` and resolves the database and vector-store paths using `spock_shell.paths`.
4. The skill reads `sessions` and `query_log` to determine whether cached context or prior results are available.
5. The user prompt is converted into an embedding by the embedding LLM.
6. The vector database is searched for the most relevant chunks.
7. `ship_computer.db` is used to resolve chunk metadata, document provenance, and citation information.
8. The generative LLM produces an answer using the retrieved context.
9. The response, evidence, metrics, and log lines are written back to `ship_computer.db`.
10. The skill returns a `SkillResult` containing success status, evidence, and diagnostic log lines.

## Embedding LLM and Vector Database

### Purpose

The embedding LLM and vector database provide semantic search for the Spock application. The embedding LLM converts text into numerical vectors that represent meaning. The vector database stores those vectors and supports similarity search, allowing the application to find relevant document chunks even when the user's wording differs from the source text.

This layer is separate from the generative LLM that writes the final answer. The embedding LLM is used for retrieval; the generative LLM is used for synthesis.

### Ingestion Pipeline

When documents are added to the Spock knowledge base, the application processes them through an ingestion pipeline:

1. The source file is read and validated.
2. The document is split into manageable chunks, such as paragraphs, sections, or token-limited blocks.
3. Each chunk is embedded using the embedding LLM.
4. The resulting vector is stored in the vector database.
5. Metadata about the document, chunk, embedding model, and vector-store identifier is written to `ship_computer.db`.
6. The `documents` table records the source file, hash, ingestion timestamp, and processing status.
7. The `embeddings_index` table records the mapping between the chunk and its vector-store identifier.

This design keeps the vector database focused on high-dimensional similarity search while `ship_computer.db` remains the authoritative source for application state, provenance, and audit information.

### Query Pipeline

When the application needs to answer a question, it uses the following query pipeline:

1. The user prompt is normalized and embedded using the same embedding LLM used during ingestion.
2. The query vector is sent to the vector database.
3. The vector database returns the nearest neighbor chunks, usually a configurable top-k set.
4. The application retrieves metadata for those chunks from `ship_computer.db`.
5. Optional reranking, filtering, or scoring is applied to improve relevance.
6. The selected chunks are passed to the generative LLM as context.
7. The generative LLM produces an answer grounded in the retrieved evidence.
8. The final answer, citations, retrieval metrics, and log lines are returned to the user and recorded in `ship_computer.db`.

### How Ask AI Uses the Embedding LLM and Vector Database

Ask AI uses the embedding LLM and vector database for fast, single-pass retrieval. The user prompt is embedded once, the vector database is searched once, and the most relevant chunks are used to generate a concise answer.

Ask AI is optimized for low latency. It may use cached embeddings, cached responses, or session context from `ship_computer.db` when available. If the vector database returns weak matches, the skill may return a lower-confidence answer, request clarification, or fall back to a generic response depending on the configured policy.

### How Deep Dive Uses the Embedding LLM and Vector Database

Deep Dive uses the embedding LLM and vector database more aggressively. It may perform multiple retrieval passes, expand the search with related terms, retrieve document clusters, and apply metadata filters from `ship_computer.db`.

Deep Dive is optimized for completeness and traceability. It may retrieve more chunks than Ask AI, compare confidence scores, and preserve intermediate retrieval results in `ship_computer.db`. This allows the final answer to include an evidence chain showing which documents, chunks, and metadata filters contributed to the response.

### Relationship to `ship_computer.db`

The vector database stores the high-dimensional vectors used for similarity search. `ship_computer.db` stores the application-level state needed to use those vectors safely and transparently.

In practice, the two systems work together as follows:

- The vector database answers: "Which chunks are semantically similar to this prompt?"
- `ship_computer.db` answers: "What document did this chunk come from, when was it ingested, which embedding model created it, what metadata applies, and what was the user's prior context?"
- The Spock application combines both results to produce grounded, auditable answers for Ask AI and Deep Dive.

### Failure and Fallback Behavior

If the embedding LLM is unavailable, the skill should return a `SkillResult` with `ok=False`, evidence explaining the failure, and log lines describing the missing dependency or error.

If the vector database is unavailable or returns no results, the application may fall back to cached responses, session context, or a clearly labeled non-grounded answer, depending on the configured policy. In all cases, the failure or fallback is recorded in `query_log` so the behavior can be audited.
## Embedding LLM and Vector Database Integration

### Embedding Model Workflow
Spock uses a dedicated embedding model, separate from the generative LLM, to convert unstructured text into high-dimensional numerical vectors. When new documents or user queries are processed, the text is first chunked, cleaned, and normalized. The embedding model then generates fixed-length vectors that capture semantic meaning rather than simple lexical overlap. These vectors are optimized for cosine similarity or inner-product distance metrics, enabling efficient semantic search across large knowledge bases.

### Vector Database Retrieval and RAG Pipeline
The generated vectors are stored in a vector database optimized for approximate nearest neighbor (ANN) search. When an Ask AI or Deep Dive request is initiated, Spock embeds the user's prompt using the same embedding model and queries the vector database for the most contextually relevant document chunks. The retrieved chunks are ranked, filtered by metadata constraints, and supplied to the generative LLM as context. This retrieval-augmented generation pipeline grounds responses in verified, up-to-date information rather than relying solely on the model's pre-training data.

### Separation of Concerns: Embedding vs. Generative LLM
The architecture strictly separates the embedding model from the generative LLM to optimize performance, cost, and accuracy. The embedding model is lightweight, fast, and designed exclusively for vectorization and similarity matching; it does not generate natural language. The generative LLM is responsible for synthesizing coherent, context-aware responses using the retrieved chunks and associated metadata. This division allows Spock to scale retrieval operations independently, update embedding models without disrupting response generation, and maintain clear audit trails for both semantic search and language synthesis stages.

### SQLite 3 `ship_computer.db` and Spock Integration
SQLite 3 `ship_computer.db` serves as Spock's local relational store for operational state, document metadata, retrieval context, and audit information. It is the system of record for what Spock is allowed to use, what has been retrieved, and how each Ask AI or Deep Dive response was produced. The vector database stores high-dimensional vectors for fast semantic search, while `ship_computer.db` stores the durable, queryable facts that make those search results meaningful and traceable.

Typical responsibilities of `ship_computer.db` include:
- Storing document and chunk records, including source, title, owner, permissions, status, and content hash.
- Mapping each chunk to its vector database identifier, embedding model version, and vector status.
- Recording user sessions, prompts, retrieved chunk IDs, generated responses, citations, and confidence signals.
- Maintaining Deep Dive state, such as active constraints, explored chunks, follow-up questions, and intermediate findings.
- Providing transactional consistency, so a chunk is not considered available for retrieval until its metadata and vector reference are committed.
- Supporting audit and compliance by preserving the exact context used for each generated answer.

In practice, Spock uses SQLite 3 for deterministic filtering and state management, while it uses the vector database for probabilistic semantic ranking. This combination allows Spock to answer questions with both relevance and accountability.

### Ask AI and Deep Dive Interaction with `ship_computer.db`
For Ask AI inquiries, Spock treats the request as a bounded question that should be answered from the most relevant available context. The application first loads the user's session, permissions, and allowed source scope from `ship_computer.db`. It then embeds the prompt, searches the vector database, and retrieves candidate chunks. Before passing those chunks to the generative LLM, Spock validates them against SQLite-stored metadata, such as document status, access rights, freshness, and source reliability. The final answer, retrieved chunk IDs, citations, and response metadata are written back to `ship_computer.db` so the interaction can be reviewed, replayed, or audited.

For Deep Dive inquiries, Spock treats the request as a multi-step investigation rather than a single lookup. `ship_computer.db` stores the Deep Dive session state, including the original objective, refined sub-questions, applied filters, previously retrieved chunks, and intermediate conclusions. As the investigation progresses, Spock may issue multiple embedding searches, compare results, eliminate duplicates, and request additional context. SQLite 3 ensures that the application does not lose track of what has already been examined, prevents redundant retrieval, and preserves a clear chain of evidence from the initial question to the final synthesized answer.

### How Spock Uses the Embedding LLM and Vector Database
Spock uses the embedding model and vector database as a semantic retrieval layer that connects user intent to the most relevant stored knowledge. The embedding model converts both stored content and incoming questions into the same numerical vector space. Because both sides of the search use the same model, a user question such as "what are the risks in this deployment plan?" can match a document chunk that does not contain the exact phrase "risks" but still discusses failure modes, rollback constraints, or operational exposure.

During ingestion, Spock processes source material into manageable chunks, normalizes the text, and generates a vector for each chunk. The vector is stored in the vector database alongside a stable identifier and metadata. The corresponding chunk record, permissions, and vector identifier are stored in `ship_computer.db`. This dual storage model gives Spock fast semantic search while preserving durable, inspectable context.

During retrieval, Spock embeds the user's prompt and asks the vector database for the nearest vectors. The vector database returns candidate chunks based on semantic proximity. Spock then applies business rules from `ship_computer.db`, such as access control, document status, source priority, and freshness. The surviving chunks are ranked, deduplicated, and assembled into a context window for the generative LLM. The generative LLM uses that context to produce an answer, while the embedding model and vector database remain responsible only for finding the right material.

This design gives Spock three important properties:
- **Relevance:** semantic search finds conceptually related content, not just keyword matches.
- **Grounding:** generated answers are constrained by retrieved, citable evidence.
- **Traceability:** SQLite 3 preserves the exact chunks, metadata, and session state used to produce each response.