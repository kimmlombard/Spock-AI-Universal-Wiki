# Architecture

## Layers

The application is organized into functional layers that separate user interaction, content ingestion, retrieval-augmented generation, model/hardware management, and persistence.

| Layer | Components | Evidence |
| --- | --- | --- |
| UI / Stations | `NavigationStation`, `EngineeringDeck`, `ScienceStation`, Bringup Menu | PyQt6-based desktop applications or panels |
| Wiki agent / ingest | `wiki_agent`, `starfleet_universal_extractor`, onboarding skills | Pipeline from `agent_queue` to extracted `documents` and embeddings |
| RAG / Ask AI | `deep_dive`, `llm_client`, `spock_rag_adapter`, `AskAiPanel` | Hybrid search over local knowledge, context packing, and chat LLM calls |
| Hardware / models | `spock_scanner_core`, `model_selector`, `host_recipe`, `llmfit` | VRAM-aware model selection and launch configuration |
| Persistence | `WarpCore.settings_store`, `ship_computer.db` | SQLite database with FTS5 full-text search and embedding storage |
| Python packages present | `bootstrap_wizard`, `EngineeringDeck`, `LongRangeSensors`, `model_selector`, `NavigationStation`, `Orchestrator`, `ScienceStation`, `spock_bringup`, `spock_bringup_menu`, `spock_codebase_knowledge`, `spock_live_monitor`, `spock_mcp_adapter`, `spock_onboarding`, `spock_probe`, `spock_progress_log`, `spock_rag_adapter`, `spock_shell`, `spock_status`, `spock_wiki_adapter`, `tests` | Filesystem scan of Python packages and modules |

### Layer notes

- **UI / Stations:** The user-facing layer consists of a desktop UI built with PyQt6. "Stations" represent distinct operational views or workspaces, including navigation, engineering, science, and bringup/onboarding interfaces.
- **Wiki agent / ingest:** This layer transforms raw wiki content into structured knowledge. It enqueues onboarding items, extracts text and metadata, persists documents, and generates embeddings for semantic search.
- **RAG / Ask AI:** This layer answers user questions by combining local retrieval with an LLM. Hybrid search indicates that the system uses both keyword/full-text matching and vector/embedding similarity before assembling prompt context.
- **Hardware / models:** This layer manages model availability and launch behavior, particularly regarding GPU memory or VRAM constraints. It selects appropriate model sizes, quantizations, ports, and runtime settings tailored to the host machine.
- **Persistence:** The system stores configuration, documents, search indexes, embeddings, and operational state in SQLite. FTS5 provides full-text search capability, while stored embeddings support semantic retrieval.

## SQLite 3 Persistence: ship_computer.db

`ship_computer.db` serves as the centralized persistence layer for the Spock application. Built on SQLite 3, it combines relational storage, full-text indexing, and vector data management into a single, lightweight database file.

### Schema and Storage Strategy

- **Document & Metadata Tables:** Store raw and processed wiki content, codebase artifacts, and associated metadata such as source paths, timestamps, authorship, and classification tags. These tables provide the authoritative record of what has been ingested and how each item should be interpreted.
- **FTS5 Virtual Table:** An integrated Full-Text Search 5 index enables high-performance keyword matching, phrase queries, and boolean filtering across all ingested text. This supports exact-term retrieval, which is especially useful for technical identifiers, error messages, configuration keys, and domain-specific terminology.
- **Embedding Storage:** High-dimensional vectors generated during ingestion are serialized, typically as BLOBs or JSON arrays, and stored alongside their corresponding document or chunk identifiers. This eliminates the need for an external vector database while still enabling semantic similarity search.
- **Configuration & State:** `WarpCore.settings_store` maps to dedicated tables that track user preferences, hardware recipes, model launch parameters, and runtime telemetry. This allows the application to restore prior state and maintain consistent behavior across sessions.

### Embedding LLM and Vector Database

Spock uses an embedding model, often described in this architecture as the embedding LLM, to convert text into dense numerical vectors. These vectors represent the semantic meaning of a passage rather than its exact wording. For example, a question about "how to configure the model port" can be matched to a document that says "set the launch port in the host recipe," even if the two texts share few keywords.

The vector database is not a separate server or external service. It is implemented inside `ship_computer.db` as one or more SQLite tables that store embedding vectors together with metadata such as document ID, chunk ID, embedding model name, vector dimension, and creation timestamp. This design keeps the entire knowledge base local, portable, and easy to back up.

During ingestion, Spock processes source content in the following way:

1. Raw wiki pages, codebase artifacts, or onboarding items are extracted and normalized.
2. The content is split into manageable chunks so that retrieval can return relevant passages rather than entire documents.
3. Each chunk is passed through the embedding model to produce a vector.
4. The vector is serialized and stored in the embedding table.
5. The same chunk is also indexed in the FTS5 table for keyword-based retrieval.

During query time, Spock uses the same embedding model to convert the user's question into a query vector. It then compares that vector against stored embeddings to find semantically similar passages. Because SQLite does not natively provide a universal vector index, similarity scoring is typically performed by the application layer, often using cosine similarity or dot-product scoring over candidate vectors. The result is a ranked set of semantically relevant documents or chunks.

This embedding-based retrieval complements FTS5. FTS5 excels at exact keyword matching, while the embedding vector store excels at conceptual matching. Together, they allow Spock to answer questions that require both precise terminology and broader semantic understanding.

### Interaction with Ask AI and Deep Dive

- **Ask AI:** When a user submits a conversational query, the RAG adapter executes a hybrid search against `ship_computer.db`. It first runs an FTS5 query to capture exact keyword matches and domain-specific terminology. Simultaneously, it retrieves the top-K semantically similar documents using stored embeddings. Results are ranked, deduplicated, and packed into a structured context window before being forwarded to the chat LLM. This allows Ask AI to produce grounded answers that are based on local knowledge rather than relying solely on the model's general training data.
- **Deep Dive:** This mode triggers a more granular, multi-hop retrieval strategy. Instead of a single query pass, Deep Dive iteratively expands context by following metadata relationships, traversing codebase dependencies, or recursively querying related wiki nodes. The database supports this through indexed foreign keys, transactional read consistency, and optimized batch retrieval queries that minimize I/O latency during complex explorations. Deep Dive can therefore move from an initial answer to a broader investigation, pulling in related configuration files, code references, wiki pages, and operational notes as needed.

### Ask AI and Deep Dive Query Flow

The following flow describes how `ship_computer.db` participates in both Ask AI and Deep Dive inquiries.

1. **Query intake:** The user submits a question through the Ask AI panel or initiates a Deep Dive request.
2. **Query preparation:** Spock normalizes the question, extracts key terms, and prepares it for both lexical and semantic retrieval.
3. **Keyword retrieval:** An FTS5 query is executed against the full-text index to find documents containing exact terms, phrases, or technical identifiers.
4. **Semantic retrieval:** The question is embedded using the same embedding model used during ingestion. The resulting query vector is compared against stored embeddings to find conceptually similar passages.
5. **Result fusion:** Keyword and vector results are combined, ranked, and deduplicated. This hybrid approach reduces the risk of missing relevant content that is either semantically similar but lexically different, or lexically exact but contextually weak.
6. **Context assembly:** The highest-ranked passages are packed into a prompt context window. Metadata such as source, title, and classification may be included to help the LLM interpret the evidence.
7. **Answer generation:** The chat LLM receives the assembled context and generates a response. For Ask AI, this is typically a direct answer. For Deep Dive, the response may include follow-up retrieval targets.
8. **Iterative expansion:** In Deep Dive mode, Spock may inspect the retrieved documents for related links, code references, configuration keys, or metadata relationships. It then issues additional queries against `ship_computer.db` to expand the evidence base.
9. **State persistence:** Query results, session state, and operational telemetry may be written back to SQLite so that the application can resume, audit, or refine the investigation later.

This flow allows Spock to treat `ship_computer.db` as both a knowledge store and a retrieval engine. FTS5 provides fast lexical search, the embedding tables provide semantic search, and the relational schema provides the structure needed to connect documents, metadata, configuration, and application state.
## Data flow (ingest → Ask AI)

1. **Wiki scan / watcher enqueues onboarding work**  
   A scanner or file watcher detects new wiki content and places it into an `onboarding` queue in `ship_computer.db`. The extractor processes queued items, producing structured `documents`, metadata, and associated embeddings.

2. **Ask AI / Deep Dive retrieves relevant context**  
   When a user asks a question, the RAG layer queries `ship_computer.db`. It combines SQLite FTS5 full-text search with embedding similarity to identify the most relevant documents, metadata, or codebase knowledge. The selected context is then packed into an LLM prompt.

3. **Settings and host recipes control runtime behavior**  
   `WarpCore.settings_store` and related recipe/configuration data dictate how the application launches models, which ports are utilized, where scan roots are located, and what hardware constraints must be respected.

> **[ASK USER] Confirm intended production topology (single host vs dual-GPU).**  
> This matters because it affects model placement, VRAM allocation, port configuration, scan-root discovery, and whether components run locally on one machine or across multiple GPUs/hosts.

### SQLite 3 `ship_computer.db`

`ship_computer.db` is the local SQLite 3 database that acts as the operational state store for the Spock application. It is not merely a passive file; it is the shared source of truth for onboarding work, extracted knowledge, embeddings, retrieval indexes, and runtime configuration.

#### Core responsibilities

- **Onboarding queue:** stores pending wiki pages, files, or code artifacts that need extraction, chunking, embedding, and indexing.
- **Document store:** stores normalized documents, chunks, source paths, titles, timestamps, content hashes, and metadata needed for citation and filtering.
- **Embedding store:** stores vector representations for each document chunk or query-relevant unit, typically as `BLOB` values with dimensionality and model identifier.
- **Full-text index:** uses SQLite FTS5 to provide keyword search over document text, titles, and selected metadata.
- **Settings and recipes:** stores `WarpCore.settings_store` values and host recipes that control model endpoints, ports, scan roots, GPU/CPU placement, and hardware constraints.

#### Expected table relationships

A practical schema would include tables such as:

- `onboarding(id, source_path, content_hash, status, created_at, updated_at, error)`
- `documents(id, source_id, title, path, content, content_hash, created_at, updated_at)`
- `chunks(id, document_id, ordinal, text, token_count, metadata_json)`
- `embeddings(id, chunk_id, model, dimension, vector_blob, created_at)`
- `documents_fts` as an FTS5 virtual table linked to `chunks` or `documents`
- `settings(key, value_json, updated_at)`
- `recipes(id, name, host, gpu, ports_json, scan_roots_json, constraints_json)`

These tables allow the application to perform atomic updates: a new wiki page can be queued, extracted, chunked, embedded, and indexed in a single transaction, reducing the risk of partial state.

#### How Ask AI uses the database

For an Ask AI request, the application:

1. Normalizes the user question.
2. Queries FTS5 for exact or near-exact keyword matches.
3. Encodes the question with the embedding LLM.
4. Compares the query vector against stored chunk embeddings.
5. Ranks the combined results using keyword relevance, semantic similarity, recency, source type, and access constraints.
6. Selects the highest-scoring chunks and formats them into a prompt for the generative LLM.

#### How Deep Dive uses the database

Deep Dive extends the same retrieval path with a more exhaustive strategy:

- It may issue multiple retrieval passes, using the initial answer or intermediate findings to generate follow-up queries.
- It can traverse related documents through shared metadata, source paths, or linked references.
- It may retrieve codebase knowledge, configuration recipes, and settings context in addition to wiki content.
- It assembles a larger, more structured context block while still respecting token limits and relevance thresholds.

This makes `ship_computer.db` the central coordination point between ingestion, semantic search, configuration, and answer generation.

### Raw scan excerpt

```text
No monorepo signals detected.
```

This indicates that the scanner did not detect typical monorepo markers in the scanned tree. The project may still contain many Python packages or modules, but it does not appear to be structured as a multi-project workspace with explicit monorepo tooling signals.

## Embedding LLM and Vector Database Integration

The Spock application relies on a dedicated embedding LLM and an integrated vector storage mechanism to power semantic retrieval. This pipeline bridges raw text ingestion with intelligent, context-aware querying.

### Embedding LLM Workflow

- **Ingestion Phase:** As documents are extracted by the wiki agent, the embedding LLM processes each text chunk independently. It converts unstructured content into fixed-dimensional numerical vectors that capture semantic meaning, syntactic structure, and domain-specific relationships.
- **Query Phase:** When a user submits a prompt via Ask AI or Deep Dive, the same embedding LLM encodes the query into a vector of identical dimensionality. This ensures mathematical compatibility for similarity comparison.
- **Model Selection & Optimization:** The embedding model is typically smaller and faster than generative chat models, allowing it to run efficiently on CPU or low-VRAM GPU configurations. Quantization and batching are applied during ingestion to maintain throughput without sacrificing vector fidelity.

### Vector Database Operations

- **Storage Architecture:** Rather than relying on a standalone vector database, Spock leverages `ship_computer.db` as a unified vector store. Embeddings are persisted alongside document metadata, enabling atomic transactions and simplified backup/recovery procedures.
- **Similarity Search:** During retrieval, the application computes cosine similarity or dot product distances between the query vector and stored document vectors. Indexing strategies, such as approximate nearest neighbor algorithms or SQLite vector extensions, can accelerate search operations and target sub-second response times even across large knowledge bases.
- **Hybrid Ranking:** Raw similarity scores are combined with FTS5 keyword relevance metrics using a weighted ranking algorithm. This hybrid approach mitigates the limitations of pure vector search, such as poor handling of exact identifiers or rare technical terms, while preserving semantic flexibility.
- **Context Assembly:** Top-ranked results are filtered by metadata constraints, such as recency, source type, or access level, truncated to fit token limits, and formatted into a structured context block. This block is injected into the system prompt before the generative LLM produces the final response.

### End-to-end embedding and retrieval flow

1. **Chunking:** The extractor splits source content into manageable chunks that preserve meaning while remaining small enough for efficient embedding and prompt inclusion.
2. **Embedding:** Each chunk is passed through the embedding LLM to produce a dense vector representation.
3. **Persistence:** The vector, chunk text, document metadata, and source information are written to `ship_computer.db`.
4. **Query encoding:** The user’s Ask AI or Deep Dive prompt is encoded with the same embedding model.
5. **Candidate retrieval:** The system retrieves candidates using both FTS5 keyword search and vector similarity search.
6. **Reranking:** Candidates are scored using semantic similarity, keyword relevance, metadata filters, and freshness or access constraints.
7. **Prompt construction:** The highest-scoring context is assembled into a structured prompt for the generative LLM.

### Why SQLite is used as the vector store

- **Simplicity:** SQLite provides a single-file database that is easy to deploy, inspect, and back up.
- **Atomicity:** Document, chunk, embedding, and index updates can be committed together, reducing inconsistent state.
- **Portability:** The database can be copied, restored, or migrated without requiring a separate vector database service.
- **Hybrid search:** SQLite FTS5 and vector storage can coexist in the same database, enabling combined keyword and semantic retrieval.
- **Operational constraints:** For local or single-host deployments, SQLite avoids the complexity of running a separate vector database cluster.

## Evidence

- `D:\Spock-Universal-AI-Wiki\docs\codebase\.codebase-scan.txt`
- Filters: `.gitignore`, `scan.skip_dirs`, and built-in exclusion extras

### Interpretation

The evidence is based on a deterministic codebase scan of the repository. The scan excluded common generated, dependency, cache, build, and environment directories to reduce noise. The resulting architecture view should therefore be treated as an inferred map of the active Python application rather than a complete inventory of every file in the workspace.