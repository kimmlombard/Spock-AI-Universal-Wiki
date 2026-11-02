# Long Range Sensors

The Long Range Sensors module is responsible for external data capture, web search, and UIEG (Universal Extractor) operations. It provides tools for gathering, processing, and managing external data sources to support knowledge discovery and integration.

## Components

| Module | Role |
|--------|------|
| `LongRangeSensors.app` | Main sensor panel that serves as the central interface for coordinating sensor operations. |
| `LongRangeSensors.external_search_panel` | Web search interface that allows users to perform queries using external search APIs. |
| `LongRangeSensors.uieg_capture_panel` | UIEG capture interface that provides a user-facing control surface for initiating data capture tasks. |
| `LongRangeSensors.uieg_crawler` | Web crawler used by UIEG to automatically gather and scrape content from online sources. |
| `LongRangeSensors.uieg_database` | UIEG persistence layer that stores captured and processed data for later retrieval. |
| `LongRangeSensors.uieg_import` | Module responsible for importing, parsing, and structuring captured content for system ingestion. |
| `LongRangeSensors.uieg_preview` | Preview interface that allows users to review and inspect captured data before promotion. |
| `LongRangeSensors.uieg_promote` | Promotion module that adds approved content to the Knowledge Base for broader access. |
| `LongRangeSensors.uieg_repo_fetch` | Repository fetcher that retrieves data from external repositories and third-party source systems. |
| `LongRangeSensors.uieg_status` | Status service that monitors ongoing UIEG operations and reports their current state. |
| `LongRangeSensors.web_search_clients` | Backend API clients that interface with external search engines and APIs to perform web searches. |

## UIEG Pipeline

1.  **Capture** → Crawl web sources: The UIEG crawler gathers content from online sources, identifies relevant pages or documents, and extracts raw material for downstream processing.
2.  **Import** → Parse and store documents: Captured data is parsed into structured records and stored in the UIEG database so it can be reviewed later.
3.  **Preview** → Review captured content: Users inspect extracted content to verify accuracy, relevance, and suitability before promotion.
4.  **Promote** → Add to knowledge base: Approved content is promoted to the Knowledge Base (KB), making it available for broader retrieval and use by Spock or other consumers.

The pipeline intentionally separates collection from integration so that unverified external data does not directly enter the knowledge graph. This staged approach supports review, correction, and controlled promotion of information before it becomes part of the system's trusted knowledge base.

## Core Concepts

### UIEG (Universal Extractor)
The Universal Extractor (UIEG) is a core component of the Long Range Sensors module designed to handle the extraction and normalization of data from diverse web sources. It acts as an intermediary layer that standardizes incoming information, making it compatible with the internal knowledge base structure. By automating the extraction process, UIEG reduces manual effort in data ingestion while maintaining high fidelity to the original source content.

### Data Lifecycle
The sensor module follows a strict data lifecycle to ensure quality and integrity:

*   **Ingestion:** Raw data is collected via crawlers or APIs.
*   **Normalization:** Data is parsed and structured during the Import phase.
*   **Validation:** Human review occurs during the Preview phase.
*   **Integration:** Verified data is merged into the Knowledge Base during the Promote phase.

This pipeline ensures that only high-quality, relevant, and accurate information contributes to the system's overall knowledge graph.

### UIEG Naming Note
In this documentation, **UIEG** is used as a project-specific label for the Universal Extractor workflow. It does not refer to a separate external service; rather, it describes the set of components that capture, import, preview, and promote extracted web content into the system's knowledge base.

## SQLite 3 `ship_computer.db`

`ship_computer.db` is the SQLite 3 database used by the Spock application as the local system of record for operational state, inquiry history, source metadata, and retrieval context. It supports both **Ask AI** and **Deep Dive** workflows by storing the durable data needed to track conversations, preserve citations, manage UIEG pipeline state, and maintain references to embedded content.

### Purpose

The `ship_computer.db` database provides a persistent, transactional foundation for Spock. It is used to:

*   Store Spock conversations and message history.
*   Record Ask AI inquiries, answers, and retrieved context.
*   Track Deep Dive runs, subqueries, intermediate findings, and final reports.
*   Maintain source metadata for documents, web pages, repositories, and UIEG captures.
*   Store references to chunks, embeddings, and vector DB records.
*   Preserve audit trails for review, debugging, and reproducibility.
*   Support hybrid retrieval by combining relational metadata with lexical search indexes.

In short, `ship_computer.db` is the authoritative store for **what Spock knows about its own operations**, while the vector DB is the authoritative store for **semantic similarity search over embedded text**.

### Relationship to Spock

Spock uses `ship_computer.db` as its primary local database for application state. When a user submits an Ask AI question or initiates a Deep Dive inquiry, Spock reads from and writes to this database to maintain context, traceability, and consistency.

The database is especially important because:

*   It allows Spock to resume conversations after restarts.
*   It preserves the exact context used to generate an answer.
*   It enables citation tracking by linking answers to specific chunks and sources.
*   It supports Deep Dive workflows by storing multi-step research state.
*   It provides a stable metadata layer for the vector DB, even if the vector store is external or SQLite-backed.

### Core Tables

The following table describes the primary table categories used by Spock in `ship_computer.db`.

| Table | Purpose |
|-------|---------|
| `spock_conversations` | Stores top-level conversation records for Ask AI and Deep Dive sessions. |
| `spock_messages` | Stores individual user and assistant messages within a conversation. |
| `ask_ai_inquiries` | Records Ask AI questions, normalized queries, answers, citations, and retrieval metadata. |
| `deep_dive_runs` | Records Deep Dive objectives, status, final reports, and lifecycle timestamps. |
| `deep_dive_steps` | Records individual Deep Dive subqueries, retrieval actions, and intermediate findings. |
| `sources` | Stores source metadata such as URLs, repository identifiers, capture timestamps, and trust levels. |
| `documents` | Stores normalized documents promoted from UIEG or other ingestion paths. |
| `chunks` | Stores text chunks derived from documents for embedding and retrieval. |
| `embeddings` | Stores embedding metadata, model version, dimensionality, and references to vector DB records. |
| `vector_index_metadata` | Tracks vector index names, models, dimensions, metrics, and rebuild state. |
| `ui_eg_captures` | Stores raw capture records from the UIEG pipeline. |
| `ui_eg_imports` | Stores import and parsing results for captured content. |
| `ui_eg_previews` | Stores preview state and review metadata for captured content. |
| `ui_eg_promotions` | Stores promotion records linking approved content to the Knowledge Base. |
| `audit_log` | Stores operational events for debugging, compliance, and traceability. |

### Ask AI Interaction

Ask AI is Spock's direct question-answering mode. It is designed for fast, context-aware responses based on the current conversation and the available knowledge base.

When Spock handles an Ask AI inquiry, it interacts with `ship_computer.db` in the following way:

1.  **Conversation lookup or creation**
    Spock checks whether the current conversation already exists in `spock_conversations`. If not, it creates a new conversation record.

2.  **Message persistence**
    The user's question is stored in `spock_messages` with metadata such as timestamp, role, and conversation ID.

3.  **Query normalization**
    Spock normalizes the question into a canonical form suitable for retrieval. This may include trimming, language normalization, entity extraction, and filter derivation.

4.  **Embedding lookup or generation**
    Spock checks whether an embedding for the normalized query already exists in `embeddings`. If not, it requests the embedding LLM to generate one and stores the resulting metadata in `ship_computer.db`.

5.  **Retrieval context storage**
    After querying the vector DB, Spock stores the retrieved chunk IDs, source IDs, scores, and ranking metadata in `ask_ai_inquiries`.

6.  **Answer generation**
    Spock uses the retrieved context to build a prompt for the answer-generating LLM. The final answer is then stored in `ask_ai_inquiries` and appended to `spock_messages`.

7.  **Citation preservation**
    The sources and chunks used to support the answer are linked to the inquiry record so that Spock can later explain, audit, or regenerate the response.

This design ensures that Ask AI responses are not only generated in real time but also remain inspectable and reproducible.

### Deep Dive Interaction

Deep Dive is Spock's extended research mode. It is used when a question requires multi-step investigation, source comparison, or synthesis across multiple documents.

When Spock executes a Deep Dive inquiry, it uses `ship_computer.db` to maintain a durable research state:

1.  **Run creation**
    Spock creates a record in `deep_dive_runs` containing the objective, status, and lifecycle timestamps.

2.  **Research planning**
    Spock decomposes the objective into subquestions or research steps. Each step is stored in `deep_dive_steps`.

3.  **Subquery embedding**
    For each subquery, Spock generates or retrieves an embedding and stores the associated metadata in `embeddings`.

4.  **Retrieval execution**
    Spock queries the vector DB for relevant chunks and stores the retrieved chunk IDs, source IDs, and scores in the corresponding `deep_dive_steps` record.

5.  **Evidence accumulation**
    As Spock gathers evidence, it records intermediate findings, confidence notes, and source references in `deep_dive_steps`.

6.  **Gap detection and follow-up**
    If Spock identifies missing information, it may generate additional subqueries, trigger Long Range Sensors web search, or request UIEG capture of new sources.

7.  **Synthesis**
    Once sufficient evidence is collected, Spock synthesizes a final report and stores it in `deep_dive_runs`.

8.  **Audit trail**
    The full sequence of steps, queries, retrieved sources, and final output remains available in `ship_computer.db` for review and debugging.

This makes Deep Dive a traceable, stateful workflow rather than a single one-shot query.

### Consistency and Audit

Because Spock depends on both relational state and semantic retrieval, `ship_computer.db` plays a key role in maintaining consistency:

*   **Content hashing** prevents duplicate chunks and duplicate embeddings.
*   **Embedding versioning** ensures that Spock can distinguish vectors generated by different embedding models.
*   **Source linkage** allows every answer to be traced back to a specific document, chunk, and capture event.
*   **Run state tracking** allows Deep Dive workflows to be resumed or replayed.
*   **Audit logging** supports debugging, quality review, and operational monitoring.

If the vector DB is implemented as an external service, `ship_computer.db` stores the stable identifiers and metadata needed to reconcile Spock's local state with the vector store. If the vector DB is implemented as a SQLite-backed vector extension, `ship_computer.db` may also host the vector index itself while still serving as the primary metadata and state store.

## Spock Embedding LLM and Vector DB

Spock uses an **embedding LLM** and a **vector DB** to convert text into searchable semantic representations. The embedding LLM is responsible for producing dense vector representations of text, while the vector DB is responsible for storing those vectors and retrieving the most relevant ones for a given query.

### Embedding LLM

The embedding LLM is a specialized model used to transform text into fixed-dimensional numerical vectors. Unlike the answer-generating LLM, the embedding LLM does not produce natural language output. Instead, it produces a vector that captures the semantic meaning of the input text.

Spock uses the embedding LLM for:

*   Embedding Knowledge Base documents.
*   Embedding UIEG-promoted content.
*   Embedding web search results that have been captured and normalized.
*   Embedding user questions in Ask AI.
*   Embedding subqueries in Deep Dive.
*   Embedding repository content and other structured sources.

The embedding LLM is important because it allows Spock to retrieve content based on **meaning**, not just exact keyword matches.

### Vector DB

The vector DB is the semantic retrieval layer used by Spock. It stores the vectors produced by the embedding LLM along with the metadata needed to filter, rank, and cite results.

The vector DB is used to:

*   Store high-dimensional vectors for chunks, queries, and subqueries.
*   Perform approximate nearest neighbor search.
*   Retrieve the most semantically relevant chunks for a given query.
*   Apply metadata filters such as source type, date, trust level, and document status.
*   Support hybrid retrieval by combining semantic similarity with lexical search.
*   Maintain index metadata such as model version, dimensionality, and similarity metric.

The vector DB may be implemented as a standalone vector database or as a SQLite-backed vector store. In either case, Spock treats it as the semantic search service and uses `ship_computer.db` to preserve the relational context around each retrieval.

### Ask AI Retrieval Flow

The Ask AI flow uses the embedding LLM and vector DB to answer a user question with retrieved context.

1.  **Question intake**
    Spock receives the user's question and associates it with the active conversation.

2.  **Context assembly**
    Spock loads recent conversation context from `ship_computer.db` to preserve continuity.

3.  **Query embedding**
    Spock sends the normalized question to the embedding LLM and receives a query vector.

4.  **Semantic search**
    Spock queries the vector DB for the most similar chunks using the query vector.

5.  **Metadata filtering**
    Spock applies filters based on source type, trust level, document status, and other constraints stored in `ship_computer.db`.

6.  **Hybrid ranking**
    Spock may combine vector similarity with lexical search results from `ship_computer.db` to improve precision.

7.  **Prompt construction**
    Spock builds a prompt containing the user question, conversation context, and retrieved chunks.

8.  **Answer generation**
    The answer-generating LLM produces a response grounded in the retrieved context.

9.  **Result persistence**
    Spock stores the question, answer, retrieved chunks, citations, and retrieval metadata in `ship_computer.db`.

This flow allows Ask AI to provide fast, grounded answers while preserving a complete record of the evidence used.

### Deep Dive Retrieval Flow

The Deep Dive flow uses the same embedding and vector retrieval infrastructure, but in a more iterative and stateful way.

1.  **Objective decomposition**
    Spock breaks the Deep Dive objective into multiple subquestions or research steps.

2.  **Subquery embedding**
    Each subquestion is embedded using the embedding LLM.

3.  **Iterative retrieval**
    Spock queries the vector DB for each subquestion and retrieves relevant chunks and sources.

4.  **Evidence evaluation**
    Spock evaluates the retrieved evidence for relevance, completeness, and conflicts.

5.  **Follow-up retrieval**
    If gaps are detected, Spock generates additional subqueries and performs further vector searches.

6.  **External capture if needed**
    If the existing knowledge base is insufficient, Spock may use Long Range Sensors to perform web search or UIEG capture.

7.  **Synthesis**
    Spock combines the collected evidence into a structured Deep Dive report.

8.  **State persistence**
    The full run, including subqueries, retrieved sources, intermediate findings, and final report, is stored in `ship_computer.db`.

This makes Deep Dive suitable for complex questions that require comparison, synthesis, and multi-source reasoning.

### Hybrid Search and Ranking

Spock does not rely on vector search alone. It combines semantic retrieval with relational and lexical signals to improve result quality.

The hybrid retrieval strategy may include:

*   **Vector similarity** for semantic relevance.
*   **Full-text search** for exact keyword matches.
*   **Metadata filters** for source type, date, trust level, and document status.
*   **Recency weighting** to favor newer content when appropriate.
*   **Source confidence weighting** to prioritize verified or promoted content.
*   **Deduplication** to avoid redundant chunks from the same document.
*   **Citation grouping** to present results by source rather than by isolated fragments.

This approach allows Spock to balance semantic understanding with precise, auditable retrieval.

### Embedding Lifecycle

The embedding lifecycle connects the Long Range Sensors module, the Knowledge Base, and Spock's retrieval system.

1.  **Capture**
    Long Range Sensors captures external content through web search, crawling, or repository fetch.

2.  **Import**
    Captured content is parsed and normalized into structured records.

3.  **Preview**
    Users review the content for accuracy and relevance.

4.  **Promotion**
    Approved content is promoted to the Knowledge Base.

5.  **Chunking**
    Promoted documents are split into retrieval-ready chunks.

6.  **Embedding**
    Each chunk is sent to the embedding LLM and converted into a vector.

7.  **Indexing**
    The vector and associated metadata are stored in the vector DB.

8.  **Retrieval**
    Spock uses the vector DB to retrieve relevant chunks for Ask AI and Deep Dive inquiries.

9.  **Re-embedding**
    If the embedding model changes, Spock can re-embed affected content and rebuild the vector index.

This lifecycle ensures that content moves from external capture to trusted, searchable knowledge in a controlled and auditable way.
## SQLite 3 Database: ship_computer.db

`ship_computer.db` is the primary SQLite 3 relational database that serves as the operational backbone for the Spock application. It manages session state, query metadata, caching, and configuration parameters required for both **Ask AI** and **Deep Dive** inquiry modes.

The database is designed for local, file-based persistence and is optimized for the access patterns of a Python application: frequent small reads, incremental writes, and transactional updates. It does not replace the vector database; instead, it coordinates application state, caches, provenance metadata, and configuration that support the embedding model, vector store, and generative response pipeline.

### Schema and Storage Responsibilities

The database is structured to handle lightweight, high-frequency read/write operations typical of a local Python application. Key tables include:

*   `sessions`: Tracks active user sessions, inquiry types, conversation history, and Deep Dive progress state.
*   `query_logs`: Stores timestamps, user prompts, system responses, retrieval statistics, and performance metrics for audit, debugging, and observability.
*   `cache_embeddings`: Holds recently computed vector embeddings, query hashes, and cache expiration data to avoid redundant embedding-model calls.
*   `knowledge_metadata`: Maintains pointers to promoted UIEG content, including source URLs, extraction timestamps, content identifiers, relevance scores, and provenance information.
*   `config`: Stores application settings, model identifiers, API endpoints, retrieval thresholds, cache policies, and other runtime parameters.

### Data Model and Relationships

The schema is organized around a central session model. A user inquiry creates or reuses a session record, and all subsequent query activity, retrieval results, and intermediate Deep Dive steps are associated with that session.

Typical relationships include:

*   `sessions.id` is the primary key for a user or application session.
*   `query_logs.session_id` references the session that produced the log entry.
*   `cache_embeddings.query_hash` provides a stable identifier for a normalized prompt or content chunk, enabling fast cache lookups.
*   `knowledge_metadata.source_id` links promoted content to its origin, extraction pipeline, and vector-store record.
*   `config.key` stores named configuration values that can be read at runtime without hard-coding parameters.

Indexes are used on frequently queried columns such as session identifiers, timestamps, query hashes, and source identifiers. Embeddings and flexible metadata may be stored as binary blobs, JSON, or serialized structures depending on the application’s serialization strategy. This allows Spock to keep relational data queryable while preserving enough flexibility for evolving retrieval metadata.

### Interaction with Spock: Ask AI vs. Deep Dive

Spock routes user inquiries through `ship_computer.db` to determine context, manage state, and optimize response generation:

*   **Ask AI Inquiries:** Designed for direct, single-turn questions. When a user submits a prompt, Spock queries `ship_computer.db` to check for cached embeddings, recent session context, and relevant knowledge metadata. If a suitable match exists, the system can bypass full re-embedding and retrieve the relevant vector index immediately. The database logs the query, retrieval statistics, and response metadata, enabling quick, low-latency answers without extensive background processing.
*   **Deep Dive Inquiries:** Designed for multi-step, contextual research. Spock initializes a dedicated session record in `ship_computer.db` and breaks the inquiry into sub-queries. Each sub-query’s results, intermediate embeddings, source references, and progress state are stored incrementally. The database acts as a state machine, tracking progress, preventing redundant searches, and maintaining a coherent knowledge trail. Once the Deep Dive completes, Spock consolidates findings, updates the session record, and optionally archives the research path for future reference.

By centralizing state management and caching in `ship_computer.db`, Spock ensures consistent performance, reduces external API calls, and maintains a reliable audit trail for all AI-driven operations.

### Ask AI Data Flow

For an **Ask AI** inquiry, the database participates in a short, deterministic request cycle:

1.  **Prompt Intake:** Spock receives the user prompt and normalizes it for hashing and cache lookup.
2.  **Cache Check:** Spock queries `cache_embeddings` using the normalized prompt hash or a derived semantic key.
3.  **Context Lookup:** If the prompt is new, Spock checks `knowledge_metadata` for relevant promoted content and session context.
4.  **Embedding Decision:** If a valid cached embedding exists, Spock reuses it. Otherwise, it calls the embedding model and stores the result in `cache_embeddings`.
5.  **Vector Retrieval:** Spock sends the query vector to the vector database and retrieves the most relevant content chunks.
6.  **Response Generation:** Spock assembles the retrieved context and generates a response using the generative model.
7.  **Logging:** Spock writes the prompt, response metadata, retrieval score, latency, and cache status to `query_logs`.

This flow keeps Ask AI fast and predictable by minimizing repeated embedding work and preserving enough context to support follow-up questions within the same session.

### Deep Dive Data Flow

For a **Deep Dive** inquiry, the database supports a longer-running, stateful research process:

1.  **Session Initialization:** Spock creates a new session record with the inquiry type, user intent, and initial parameters.
2.  **Inquiry Decomposition:** Spock breaks the request into sub-queries, research branches, or retrieval tasks.
3.  **Incremental Persistence:** Each sub-query’s embedding, vector-search results, source references, and intermediate conclusions are written to the database.
4.  **Deduplication:** Spock checks existing session data and cache entries to avoid repeating identical or highly similar searches.
5.  **Progress Tracking:** The session record is updated as the Deep Dive advances, allowing Spock to resume, pause, or recover from interruptions.
6.  **Consolidation:** After all branches complete, Spock merges the retrieved evidence, ranks sources, and prepares a final synthesized response.
7.  **Archive and Audit:** The completed research path, source citations, and performance metrics are retained in `query_logs` and session metadata for future review.

This stateful approach allows Deep Dive to behave like a local research engine rather than a single prompt-response exchange.

### Concurrency, Transactions, and Local Reliability

Because `ship_computer.db` is a local SQLite database, Spock should use SQLite in a way that matches its single-writer, multi-reader characteristics.

Recommended operational practices include:

*   **WAL Mode:** Write-ahead logging improves read concurrency and reduces lock contention during normal application use.
*   **Short Transactions:** Writes should be scoped narrowly to reduce the chance of database locks.
*   **Parameterized Queries:** All SQL should use parameter binding to prevent injection and improve query planning.
*   **Busy Timeout:** A reasonable busy timeout helps the application handle brief write contention gracefully.
*   **Atomic Updates:** Session state changes, cache writes, and log writes should be grouped into transactions where consistency matters.
*   **Local Backup Strategy:** Because the database is file-based, Spock can support export, backup, or migration workflows without requiring a separate database server.

These practices make `ship_computer.db` suitable for a local Python application while preserving data integrity across Ask AI and Deep Dive operations.

### Audit, Debugging, and Data Retention

The database also supports operational transparency. `query_logs` can record enough detail to reconstruct why Spock selected a particular response, including:

*   The original user prompt.
*   The normalized prompt hash.
*   Whether a cached embedding was used.
*   The vector database query parameters.
*   The top retrieved sources and their similarity scores.
*   The final response identifier or summary.
*   Latency and error information.

Retention policies can be applied to sensitive prompts, cached embeddings, and session history. Where appropriate, Spock can redact, expire, or anonymize data to reduce privacy risk while preserving the metadata needed for debugging and performance analysis.

## Embedding LLM and Vector Database Integration

The Spock application leverages an embedding Large Language Model (LLM) and a vector database to transform unstructured text into searchable, semantically meaningful representations. This integration powers the retrieval-augmented generation (RAG) pipeline that underpins both Ask AI and Deep Dive functionalities.

In this architecture, the embedding model is responsible for converting text into numerical vectors, while the vector database is responsible for storing those vectors and performing efficient similarity search. The generative LLM is a separate component that uses the retrieved context to produce the final user-facing answer.

### Embedding Process

When external content is promoted via the UIEG pipeline, or when a user submits a new query, Spock routes the text through the embedding model. The model converts natural language into high-dimensional numerical vectors, commonly called embeddings, that capture semantic meaning, context, and relationships between words.

Unlike keyword matching, embeddings allow Spock to understand intent, synonyms, paraphrases, and conceptual similarity. For example, a query about “failure modes” can retrieve content that discusses “breakdown patterns” or “error conditions” even if the exact words do not match.

The embedding process typically follows these steps:

1.  **Text Preparation:** Content is cleaned, normalized, and split into appropriately sized chunks.
2.  **Embedding Generation:** Each chunk or prompt is passed to the embedding model.
3.  **Vector Normalization:** Vectors may be normalized to support cosine similarity or dot-product search.
4.  **Metadata Attachment:** Each vector is associated with source, content type, timestamp, and relevance metadata.
5.  **Storage or Caching:** The vector is stored in the vector database and, where useful, cached in `ship_computer.db`.

### Chunking and Text Preparation

Effective retrieval depends on how text is divided before embedding. Spock should chunk content in a way that preserves meaning while keeping each vector focused enough for accurate similarity search.

Good chunking practices include:

*   Splitting by semantic boundaries such as paragraphs, sections, or headings.
*   Keeping chunks small enough to represent a single idea.
*   Adding overlap between adjacent chunks to reduce loss of context at boundaries.
*   Preserving headings, source identifiers, and timestamps as metadata.
*   Avoiding overly large chunks that dilute semantic specificity.

The resulting chunks become the unit of retrieval. When Spock answers a question, it retrieves relevant chunks rather than entire documents, which improves precision and reduces the amount of context passed to the generative model.

### Vector Database Storage and Indexing

Generated embeddings are stored in a dedicated vector database optimized for similarity search. Each vector is paired with metadata, such as source ID, content type, promotion timestamp, relevance tags, and provenance information, and indexed using approximate nearest neighbor (ANN) algorithms.

This indexing strategy enables fast retrieval even as the knowledge base scales to large collections of documents. Common ANN approaches include:

*   **HNSW:** Hierarchical navigable small world graphs, which provide strong recall and low-latency search.
*   **IVF:** Inverted file indexes, which partition vectors into clusters for efficient candidate selection.
*   **Product Quantization:** Compressed vector representations that reduce memory usage while preserving approximate similarity.

The exact algorithm depends on the vector database implementation, but the goal is the same: quickly identify the vectors that are closest to the query vector in semantic space.

### Metadata Filtering and Provenance

Vector similarity alone is not always sufficient. Spock also uses metadata to constrain and prioritize retrieval results.

Metadata filtering allows Spock to:

*   Limit results to a specific source, document, or content type.
*   Prefer recently promoted UIEG content.
*   Exclude deprecated, low-confidence, or unverified material.
*   Apply user-specific or session-specific constraints.
*   Preserve citation information for the final response.

Provenance is especially important for Deep Dive inquiries, where the user may need to understand which sources contributed to a conclusion. By storing source identifiers, extraction timestamps, and relevance scores in both the vector database and `ship_computer.db`, Spock can maintain a traceable path from final answer back to original content.

### Retrieval and Response Generation

1.  **Query Embedding:** Spock passes the user’s prompt through the same embedding model used for content indexing to generate a query vector.
2.  **Similarity Search:** The vector database computes cosine similarity or dot-product distance between the query vector and stored document vectors.
3.  **Metadata Filtering:** Retrieved candidates are filtered by source, freshness, relevance, and session constraints.
4.  **Context Assembly:** The top-k most relevant chunks are retrieved, ranked, and assembled into a context window.
5.  **LLM Synthesis:** Spock feeds the context window and original prompt to the generative LLM, which produces a grounded, citation-backed response.

The generative model does not rely solely on its internal knowledge. Instead, it uses the retrieved context as evidence, which improves factual grounding and reduces hallucination risk.

### Re-ranking and Thresholding

Raw similarity scores are useful, but they are not always the final ranking signal. Spock can apply additional ranking logic to improve answer quality.

Possible re-ranking strategies include:

*   Combining vector similarity with keyword overlap.
*   Boosting results from trusted or recently promoted sources.
*   Penalizing stale or low-confidence content.
*   Using a lightweight cross-encoder or scoring model for candidate refinement.
*   Applying inquiry-specific thresholds for Ask AI and Deep Dive.

Ask AI typically benefits from a tighter retrieval threshold because it prioritizes speed and directness. Deep Dive may use a broader search radius to capture more contextual relationships, alternative perspectives, and supporting evidence.

### Optimization and Caching

To minimize latency and API costs, Spock implements a multi-tier caching strategy managed by `ship_computer.db`. Frequently accessed embeddings are cached locally, and vector search results are temporarily stored for identical or highly similar queries.

The caching strategy can include:

*   **Prompt Hash Caching:** Normalized prompts are hashed to detect repeated or near-identical queries.
*   **Embedding Cache:** Recently computed vectors are stored to avoid repeated embedding-model calls.
*   **Retrieval Cache:** Similar query vectors can reuse previously retrieved candidate sets when metadata constraints have not changed.
*   **Session Cache:** Active Deep Dive sessions can reuse intermediate results across sub-queries.
*   **TTL and Invalidation:** Cache entries expire or are invalidated when source content changes.

The system also dynamically adjusts the top-k retrieval threshold based on inquiry type: Ask AI uses a tighter threshold for speed, while Deep Dive expands the search radius to capture broader contextual relationships.

### Failure Handling and Fallback Behavior

A robust Spock architecture should handle partial failures gracefully.

If the embedding model is unavailable, Spock can:

*   Serve cached embeddings when they exist.
*   Fall back to keyword-based retrieval if supported.
*   Return a clear status message indicating degraded capability.

If the vector database is unavailable, Spock can:

*   Use local metadata search over `knowledge_metadata`.
*   Limit responses to cached or session-local context.
*   Log the failure and avoid presenting incomplete results as authoritative.

If the generative model fails, Spock can still return the retrieved sources and evidence, allowing the user to review the underlying material even when synthesis is unavailable.

### Security and Privacy Considerations

Because Spock stores prompts, embeddings, session state, and source metadata locally, it should apply appropriate safeguards:

*   Encrypt sensitive configuration values and API keys at rest.
*   Avoid storing unnecessary personally identifiable information in `query_logs`.
*   Apply retention and deletion policies to session data and caches.
*   Validate and sanitize external content before embedding or display.
*   Preserve provenance so that users can distinguish verified sources from inferred conclusions.

This architecture ensures that Spock delivers accurate, context-aware responses while maintaining efficient resource utilization, reliable local state management, and strict data provenance.
## Database Architecture and Spock Integration

The `ship_computer.db` file serves as the primary persistent storage layer for the Spock application, utilizing SQLite 3 for efficient local data management. This database is critical for maintaining state, storing query results, and supporting high-level cognitive functions within the system.

### SQLite 3 Database Specifications

The `ship_computer.db` instance is configured with SQLite 3 optimizations tailored for high-concurrency, read-heavy workloads:

* **Write-Ahead Logging (WAL):** WAL mode is enabled to allow concurrent read operations while writes are occurring, significantly reducing lock contention during active Ask AI and Deep Dive sessions. This is especially useful because Spock may need to serve conversational queries while simultaneously persisting new insights, logs, or derived knowledge.
* **Indexing Strategy:** B-tree indexes are applied to primary keys, foreign keys, and frequently filtered columns such as `entity_type`, `timestamp`, `relationship_type`, `session_id`, and `node_id`. Full-Text Search (FTS5) virtual tables are used for rapid natural language matching across unstructured metadata, summaries, and descriptive fields.
* **Transaction Management:** Spock uses `DEFERRED` transactions for read-heavy operations and `IMMEDIATE` transactions for batch writes. This approach preserves ACID compliance while minimizing unnecessary blocking, particularly in a local, file-based database environment.
* **Maintenance:** Automated `VACUUM` and `ANALYZE` routines run during idle periods to reclaim fragmented space and update query planner statistics. This helps preserve long-term performance as the knowledge base grows and query patterns evolve.

### SQLite 3 Query Features Used by Spock

Spock relies on several SQLite 3 capabilities to support both structured retrieval and flexible analytical workloads:

* **Prepared Statements:** Spock uses parameterized SQL statements to prevent injection issues and improve execution efficiency, especially for repeated Ask AI and Deep Dive query patterns.
* **JSON Support:** Structured metadata is stored in JSON columns and queried using SQLite’s JSON functions. This allows Spock to keep flexible, semi-structured data without sacrificing relational integrity.
* **FTS5:** FTS5 provides fast keyword and phrase matching for natural language content, making it useful for retrieving relevant nodes, summaries, or relationship descriptions.
* **Recursive Common Table Expressions (CTEs):** Recursive CTEs support graph traversal over relationship edges, enabling Deep Dive queries to follow multi-hop connections such as `part_of`, `located_in`, or `related_to`.
* **Window Functions:** Where supported, window functions help Spock compute ranked results, moving averages, and temporal comparisons for analytical Deep Dive responses.
* **Read-Only Connections:** Heavy analytical queries are routed through dedicated read connections to isolate them from conversational traffic and reduce contention.

### Interaction with Spock Application

The Spock application interacts directly with `ship_computer.db` to execute complex queries and maintain context across sessions. The interaction model supports two primary inquiry types:

* **Ask AI:** Ask AI uses the database to retrieve factual knowledge, answer natural language questions, and fetch specific data points stored in the knowledge graph. Queries are optimized for low-latency retrieval to support conversational interfaces. Spock constructs parameterized SQL statements that leverage FTS5 indexes and relational filters to return precise, structured JSON payloads. These payloads are injected directly into the LLM context window, grounding responses in verified data.
* **Deep Dive:** Deep Dive performs deeper analysis by querying historical logs, relationship mappings, and aggregated metrics stored within the SQLite schema. This mode supports complex joins and aggregations that require direct database access. Spock executes multi-table joins across knowledge nodes, relationship edges, and temporal logs. Results are paginated and streamed to prevent memory exhaustion, with analytical queries routed through a dedicated read connection to isolate heavy workloads from conversational traffic.

#### Ask AI Retrieval Pattern

Ask AI is optimized for fast, grounded, conversational responses. A typical Ask AI flow works as follows:

1. Spock interprets the user’s question and identifies likely entity types, keywords, and semantic intent.
2. The query is embedded using the embedding LLM and searched against the vector database to retrieve semantically relevant candidate nodes.
3. Candidate node identifiers are passed back to SQLite, where Spock applies exact filters such as entity type, confidence, time range, and relationship constraints.
4. FTS5 may be used to supplement semantic results with strong keyword matches, especially for proper nouns, technical terms, or rare phrases.
5. The resulting records are serialized into a compact JSON context that includes only the fields needed for the answer.
6. The LLM generates a response using that grounded context, allowing Spock to answer with citations or references to stored knowledge.

This pattern keeps Ask AI responsive by limiting the amount of data loaded into the LLM context while still providing enough structured evidence to produce accurate answers.

#### Deep Dive Retrieval Pattern

Deep Dive is optimized for analytical, multi-step reasoning over the knowledge base. A typical Deep Dive flow works as follows:

1. Spock identifies the entities, relationships, and time ranges relevant to the user’s request.
2. Semantic search and keyword search are used to seed the initial set of knowledge nodes.
3. SQLite traverses relationship edges using joins or recursive CTEs to discover connected entities, dependencies, or historical changes.
4. Aggregations are computed over temporal logs, confidence scores, relationship counts, or other metrics.
5. Results are streamed or paginated to avoid excessive memory use during large analytical queries.
6. If the Deep Dive produces new insights, Spock may persist them back into the database as new nodes, edges, summaries, or query log entries.

This pattern allows Spock to move beyond simple fact retrieval and perform structured analysis across the full knowledge graph.

### Data Flow Mechanics

1. **Query Execution:** Spock sends SQL queries or prepared statements to the database engine through a managed SQLite connection pool. Connection lifecycle is handled via context managers to prevent resource leaks. Because SQLite is file-based, Spock typically uses a small number of read connections and serializes writes through a single writer path.
2. **Result Caching:** Frequently accessed data is cached in memory to reduce latency during Ask AI sessions, ensuring responsive user experiences. An LRU (Least Recently Used) cache with configurable TTL (Time-To-Live) expiration balances memory efficiency with data freshness.
3. **Persistence:** New insights generated by Deep Dive inquiries are written back to the database for future reference, allowing knowledge to evolve over time. Writes are batched and committed within atomic transactions to guarantee data consistency and prevent partial updates.

Because SQLite is a file-based database engine, connection management and caching are handled locally rather than through a networked database server. This design supports lightweight deployment while still providing structured access to persistent application data.

#### Connection, Caching, and Write Safety

Spock treats `ship_computer.db` as a local, authoritative data store. Reads are optimized for speed, while writes are carefully controlled to preserve consistency.

* **Read Path:** Ask AI and Deep Dive queries use read connections that can operate concurrently under WAL mode.
* **Write Path:** Updates to knowledge nodes, relationship edges, and query logs are committed atomically to avoid partial state.
* **Cache Invalidation:** When data changes, Spock invalidates or refreshes affected cache entries so that subsequent Ask AI responses reflect the latest stored knowledge.
* **Query Fingerprinting:** Cache keys may include query parameters, schema version, data version, and retrieval filters to reduce the risk of serving stale results.

### Schema Overview

The `ship_computer.db` schema is designed to support both relational data integrity and flexible querying:

* **Knowledge Nodes:** Stores entities extracted from UIEG pipelines. Includes core identifiers (`node_id`), semantic classifications (`entity_type`), structured metadata (`metadata_json`), and foreign key references to vector embeddings.
* **Relationship Edges:** Defines connections between nodes, such as `part_of`, `located_in`, or other semantic relationships. Maintains directional mapping (`source_id`, `target_id`), relationship taxonomy, confidence scoring, and temporal validity ranges to support graph traversal.
* **Query Logs:** Maintains a history of Ask AI and Deep Dive interactions for audit trails, debugging, and potential model training. Records session identifiers, raw prompts, response summaries, execution metrics, and status codes to enable performance monitoring and feedback loops.

This architecture ensures that the Spock application has reliable, structured access to the knowledge base while maintaining the performance required for real-time interaction.

#### Schema Relationships and Constraints

The schema is organized around a graph-like knowledge model with relational integrity:

* **Knowledge Nodes** are the primary entities in the system. Each node represents a concept, object, event, person, location, or other meaningful item extracted from the UIEG pipeline.
* **Relationship Edges** connect nodes and describe how they relate to one another. Edges are directional, typed, and may include confidence and temporal validity information.
* **Query Logs** record how Spock used the knowledge base, providing an audit trail and enabling later analysis of retrieval quality, latency, and user intent.
* **Vector Embeddings** are stored in the vector database but are linked back to knowledge nodes through stable identifiers, allowing Spock to combine semantic search with relational filtering.

This separation allows Spock to use SQLite for authoritative structured data while using the vector database for fast semantic candidate retrieval.

### Embedding LLM and Vector Database Integration

Spock augments relational SQLite queries with semantic search capabilities by integrating an embedding LLM and a dedicated vector database. This hybrid retrieval pipeline bridges the gap between exact keyword matching and contextual understanding:

#### Embedding LLM Responsibilities

The embedding LLM is responsible for converting text into dense vector representations. Spock uses it to encode:

* User questions from Ask AI and Deep Dive requests.
* Knowledge node summaries and descriptive metadata.
* Relationship labels and relationship context.
* Historical log entries and derived insights.
* Candidate passages used for retrieval and reranking.

The embedding LLM does not generate the final user-facing answer. Instead, it produces numerical vectors that capture semantic meaning. These vectors allow Spock to find conceptually similar content even when the exact wording differs from the user’s query.

#### Vector Database Responsibilities

The vector database stores embeddings alongside metadata and supports fast approximate nearest-neighbor search. Its primary responsibilities include:

* Storing high-dimensional vectors for knowledge nodes, relationships, and derived content.
* Supporting similarity search using cosine, dot product, or Euclidean distance, depending on the embedding model.
* Returning the most semantically relevant candidate records for a given query vector.
* Allowing metadata filters to be applied during or after vector search.
* Maintaining stable identifiers that link vector records back to `ship_computer.db`.

The vector database is therefore a retrieval accelerator. It helps Spock quickly identify relevant knowledge, while SQLite remains the authoritative source for structured facts, relationships, timestamps, and confidence data.

#### Hybrid Retrieval Pipeline

Spock uses a hybrid retrieval pipeline that combines semantic search, keyword search, and relational filtering. The pipeline generally follows these steps:

1. **Query Understanding:** Spock interprets the user’s Ask AI or Deep Dive request and extracts likely entities, intent, time constraints, and relationship types.
2. **Semantic Embedding:** The query is converted into a vector using the embedding LLM.
3. **Vector Search:** The vector database returns a set of semantically similar knowledge nodes or related content.
4. **Relational Filtering:** Spock queries `ship_computer.db` to validate and enrich the candidates using exact filters, foreign keys, confidence scores, and temporal constraints.
5. **Keyword Search:** FTS5 is used to capture strong lexical matches, especially for technical terms, names, or phrases that may not be well represented by semantic similarity alone.
6. **Merge and Rerank:** Results from vector search, FTS5, and relational queries are merged and ranked using relevance, confidence, recency, and query-specific weights.
7. **Context Assembly:** Spock builds a compact, structured context for the LLM, including only the most relevant nodes, relationships, and evidence.
8. **Answer Generation:** The LLM produces the final response, grounded in the retrieved database context.

This hybrid approach gives Spock both the flexibility of semantic understanding and the precision of structured database access.

#### Ask AI Semantic Flow

For Ask AI inquiries, Spock favors speed and groundedness. The system typically retrieves a small number of highly relevant records rather than loading large portions of the knowledge base.

* The embedding LLM converts the user’s question into a vector.
* The vector database returns the closest matching knowledge nodes.
* SQLite applies strict filters to ensure the results are valid, current, and relevant.
* FTS5 may be used to reinforce matches for exact terms.
* The final context is kept small enough to fit efficiently into the LLM context window.
* The LLM answers using only the grounded context, reducing hallucination risk.

This makes Ask AI suitable for conversational questions, factual lookups, and quick explanations.

#### Deep Dive Semantic Flow

For Deep Dive inquiries, Spock uses the same semantic foundation but expands the scope of retrieval and analysis.

* Semantic search identifies the initial entities and concepts relevant to the user’s question.
* SQLite traverses relationship edges to discover connected nodes, dependencies, and historical context.
* Temporal logs are queried to analyze changes over time.
* Aggregations are computed to summarize counts, confidence trends, relationship density, or other metrics.
* Results may be streamed to the user or used to generate a structured analytical report.
* New insights may be persisted back into the database for future retrieval.

This makes Deep Dive suitable for complex questions that require multi-hop reasoning, historical analysis, or cross-entity comparison.

#### Consistency, Caching, and Failure Handling

Because Spock combines SQLite, an embedding LLM, and a vector database, consistency is managed carefully.

* **Embedding Versioning:** Spock tracks the embedding model version and vector dimension so that old and new embeddings are not mixed unintentionally.
* **Re-Embedding:** When the embedding model changes, Spock can re-embed affected content and update the vector database.
* **Cache Invalidation:** Changes to knowledge nodes, edges, or metadata invalidate related cache entries to prevent stale Ask AI responses.
* **Fallback Retrieval:** If the vector database is unavailable, Spock can fall back to FTS5 and relational queries, preserving basic functionality.
* **Authoritative Source:** SQLite remains the source of truth for structured facts, relationships, and audit data. The vector database is used for retrieval, not as the final authority.

This design allows Spock to provide fast, semantically aware answers while maintaining the reliability and auditability expected from a structured database-backed system.
*   **Text-to-Vector Transformation:** When a user submits a query or when new documents are ingested, the embedding LLM converts unstructured text into high-dimensional numerical vectors. These vectors capture semantic meaning, synonyms, and contextual relationships that traditional SQL `LIKE` or `MATCH` operators cannot detect.
*   **Vector Storage and Indexing:** Generated embeddings are persisted in a vector database optimized for similarity search. The vector store utilizes Approximate Nearest Neighbor (ANN) indexing algorithms, such as HNSW or IVF-PQ, to enable sub-second retrieval across large collections of data points.
*   **Hybrid Query Resolution:** During an Ask AI or Deep Dive request, Spock first passes the user prompt through the embedding LLM to generate a query vector. The vector database performs a similarity search to retrieve the most semantically relevant knowledge nodes. These results are then cross-referenced with `ship_computer.db` using relational filters, such as access control, temporal constraints, or entity type validation, to ensure precision.
*   **Context Assembly:** The filtered vector results and relational data are merged into a unified context payload. This payload is formatted and injected into the primary LLM’s context window, enabling grounded, fact-based responses that combine semantic relevance with strict data integrity.
*   **Continuous Learning:** Embedding vectors and relationship confidence scores are periodically re-evaluated based on query logs and user feedback, allowing the semantic index to adapt to evolving terminology and domain-specific nuances.

This integration ensures that Spock can handle both precise factual lookups and abstract, concept-driven inquiries without compromising response accuracy or system latency.

## SQLite 3 `ship_computer.db` Integration

`ship_computer.db` is the embedded SQLite 3 database used by the Spock application as the authoritative relational store for structured ship-computer data. It provides deterministic, transactional access to records that require exact matching, auditability, permission enforcement, and temporal validity.

In this architecture, `ship_computer.db` is not primarily responsible for semantic search. Instead, it serves as the system of record for the facts, relationships, metadata, and access controls that Spock must verify before returning an answer. The vector database identifies semantically relevant candidates, while SQLite validates and enriches those candidates with precise relational data.

### Responsibilities of `ship_computer.db`

`ship_computer.db` stores and manages structured data such as:

*   **Document and chunk metadata:** identifiers, titles, sources, ingestion timestamps, and content hashes.
*   **Entity records:** equipment, systems, components, personnel, locations, procedures, and other domain-specific objects.
*   **Relationship data:** associations between entities, such as “component belongs to system,” “procedure applies to equipment,” or “sensor monitors subsystem.”
*   **Access control policies:** user roles, clearance levels, department restrictions, and document classification rules.
*   **Temporal constraints:** effective dates, expiration dates, revision numbers, and validity windows for records.
*   **Query and feedback logs:** user prompts, retrieved candidates, selected context, response metadata, and user feedback.
*   **Audit information:** who accessed what data, when, and under which authorization context.

Because SQLite 3 is an embedded, file-based database, it is well suited to local, edge, or single-node deployments where low operational overhead and strong ACID behavior are required. Spock can access it through Python’s `sqlite3` module using prepared statements and parameterized queries to prevent SQL injection and maintain safe, repeatable access patterns.

### How `ship_computer.db` Supports Ask AI

Ask AI is intended for direct, grounded questions where the user expects a concise answer supported by relevant ship-computer knowledge.

A typical Ask AI flow is:

1.  **Prompt intake:** Spock receives the user’s question and normalizes it for retrieval.
2.  **Semantic retrieval:** The embedding LLM converts the prompt into a query vector, and the vector database returns the most semantically similar knowledge nodes.
3.  **Candidate validation:** Spock uses the identifiers returned by the vector database to query `ship_computer.db`.
4.  **Relational filtering:** SQLite applies deterministic filters, such as:
    *   user access level,
    *   document classification,
    *   entity type,
    *   effective date,
    *   revision status,
    *   system or subsystem scope.
5.  **Context enrichment:** SQLite retrieves exact records, related entities, and supporting metadata needed to ground the response.
6.  **Answer generation:** The primary LLM receives a compact, validated context payload and generates a concise answer with citations or source references where appropriate.

For Ask AI, the goal is to avoid returning semantically similar but operationally invalid information. A vector match may be close in meaning, but SQLite ensures that the result is authorized, current, and correctly scoped.

### How `ship_computer.db` Supports Deep Dive

Deep Dive is intended for broader, multi-step investigations where the user needs a more complete explanation, comparison, or analysis.

A typical Deep Dive flow is:

1.  **Initial semantic search:** Spock retrieves the most relevant concepts, documents, and entities for the user’s question.
2.  **Entity resolution:** `ship_computer.db` maps those semantic results to canonical entity records.
3.  **Relationship traversal:** SQLite follows structured relationships to discover related systems, components, procedures, constraints, and historical records.
4.  **Iterative refinement:** Spock may generate follow-up sub-questions, retrieve additional vector candidates, and validate them against relational data.
5.  **Evidence assembly:** SQLite collects exact facts, timestamps, revision history, and access-controlled details.
6.  **Synthesis:** The primary LLM combines semantic context with relational evidence to produce a deeper, structured response.

Deep Dive relies more heavily on `ship_computer.db` because it must move beyond surface-level similarity and reconstruct a coherent, authorized, and factually consistent picture of the domain.

### SQLite Access Patterns

Spock should access `ship_computer.db` using safe, predictable patterns:

*   **Parameterized queries:** All user-influenced values should be bound as parameters rather than concatenated into SQL strings.
*   **Read-only connections for retrieval:** Most Ask AI and Deep Dive reads can use read-only connections to reduce risk and improve concurrency.
*   **WAL mode where appropriate:** Write-Ahead Logging can improve read concurrency while maintaining durability.
*   **Prepared statements:** Repeated query shapes, such as access checks or entity lookups, can be prepared and reused.
*   **Explicit transaction boundaries:** Writes to logs, feedback, or derived metadata should be committed atomically.
*   **Metadata joins:** Vector results should be joined to relational metadata before context assembly, ensuring that semantic candidates are validated against authoritative records.

## Embedding LLM and Vector Database Workflow

The embedding LLM and vector database together provide Spock with semantic retrieval capability. This allows the application to understand natural-language intent, retrieve conceptually related information, and support both Ask AI and Deep Dive workflows.

### Embedding Generation

An embedding LLM, also referred to as an embedding model, converts text into a fixed-length numerical vector. Each vector represents the semantic position of the text in a high-dimensional space.

For example, the phrases:

*   “hydraulic pressure loss”
*   “drop in hydraulic system pressure”
*   “hydraulic circuit underpressure condition”

may be represented by vectors that are close to one another, even though the exact words differ. This is the key advantage over simple keyword matching.

Spock uses embeddings in two main situations:

1.  **Ingestion:** When new documents, notes, procedures, or knowledge nodes are added, their text is embedded and stored in the vector database.
2.  **Query time:** When a user asks a question, the prompt is embedded and compared against stored vectors.

The quality of the embedding model is critical. A well-chosen model should understand domain terminology, preserve contextual meaning, and produce stable vectors for similar concepts.

### Vector Storage and Indexing

The vector database stores each embedding alongside metadata required for filtering and retrieval. Typical metadata includes:

*   document identifier,
*   chunk identifier,
*   entity identifier,
*   source type,
*   classification level,
*   ingestion timestamp,
*   effective date,
*   revision number,
*   access scope,
*   content hash.

The vector database uses ANN indexing to make similarity search efficient. Exact nearest-neighbor search can be too slow for large collections, so ANN algorithms provide a practical tradeoff between speed and recall.

Common ANN approaches include:

*   **HNSW:** a hierarchical navigable small-world graph that provides fast approximate search with high recall.
*   **IVF-PQ:** inverted file clustering with product quantization, useful for large-scale collections where memory efficiency is important.

The choice of index depends on collection size, latency requirements, memory constraints, and acceptable recall.

### Query Resolution

When Spock receives an Ask AI or Deep Dive request, it performs the following semantic query steps:

1.  **Prompt normalization:** Spock cleans and structures the user prompt.
2.  **Query embedding:** The embedding LLM converts the prompt into a query vector.
3.  **Similarity search:** The vector database finds the closest stored vectors.
4.  **Candidate scoring:** Results are ranked using a similarity metric, such as cosine similarity or dot product.
5.  **Metadata filtering:** Candidates are filtered using access control, entity type, temporal validity, and other relational constraints.
6.  **Relational validation:** `ship_computer.db` confirms that the candidate records are authoritative and permitted.
7.  **Context selection:** The most relevant and valid records are selected for the LLM context window.

This hybrid approach prevents Spock from relying solely on semantic similarity. A vector match may be conceptually close, but SQLite ensures that the result is operationally valid.

### Hybrid Filtering and Context Assembly

After vector search, Spock does not immediately pass raw vector results to the primary LLM. Instead, it performs hybrid filtering and context assembly.

This process includes:

*   **Access control checks:** Ensuring the user is authorized to view the retrieved records.
*   **Temporal validation:** Ensuring the records are current and within their effective date range.
*   **Entity validation:** Ensuring the records match the expected entity type or domain scope.
*   **Deduplication:** Removing redundant chunks or overlapping content.
*   **Relevance ranking:** Combining vector similarity, relational confidence, recency, and source authority.
*   **Context formatting:** Structuring the selected records into a clear prompt for the primary LLM.

The resulting context payload is designed to be compact, grounded, and traceable. This helps the primary LLM produce answers that are both semantically relevant and factually constrained by the authoritative data in `ship_computer.db`.

### Continuous Learning and Index Maintenance

The semantic index is not static. Over time, terminology changes, new documents are added, and user feedback reveals which retrieval patterns are effective.

Spock can improve retrieval quality through:

*   **Re-embedding:** Regenerating vectors when documents are revised or when a better embedding model is deployed.
*   **Index rebuilding:** Reconstructing ANN indexes after large ingestion or model changes.
*   **Feedback weighting:** Using user ratings, corrections, or accepted answers to adjust ranking signals.
*   **Query log analysis:** Identifying frequent failures, ambiguous prompts, or under-retrieved concepts.
*   **Relationship confidence updates:** Adjusting the strength of entity relationships based on observed usage and validation outcomes.

This continuous improvement loop allows Spock to maintain high retrieval quality while adapting to evolving domain language and operational needs.