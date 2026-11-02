# Integrations

## External systems

The following table summarizes the integration records reported in the scan. Values marked `(typical)` are not confirmed fixed values and may vary by deployment.

| Integration | Endpoint / artifact | Evidence |
| --- | --- | --- |
| `llama-server embeddings` | `:8080` | `llama_server_manager` / `Launch` |
| `llama-server chat` | `:8081` | `llama_server_manager` / `Launch` |
| `RAG API` | `:8090` (typical) | `rag_api_server.py` |
| `MCP` | `:8765` (typical) | `spock_mcp_adapter` / `mcp_spock_server` |
| `SQLite ship computer` | `ship_computer.db` | `WarpCore` / `wiki_agent` |
| `Hugging Face Hub` | model download | `model_selector` / `acquire` |
| `MkDocs` | `docs/` | `mkdocs.yml` |

### External systems explanation

- The `Endpoint / artifact` column may reference a network port, local file path, directory, or model download action.
- The `Evidence` column identifies the module, script, or configuration file that indicates the integration within the scanned codebase.
- This section documents static scan evidence only; it does not confirm that services are actively running, bound to the listed ports, or reachable at runtime.
- The `llama-server` entries indicate separate local model services: one for embedding generation and one for chat completion.
- The `RAG API` entry indicates a retrieval-augmented generation service that likely coordinates vector search, context assembly, and prompt construction.
- The `MCP` entry indicates a Model Context Protocol adapter or server that may expose Spock capabilities to external MCP-compatible clients.
- The `SQLite ship computer` entry indicates a local database artifact used for persistent application state and knowledge storage.
- The `Hugging Face Hub` entry indicates model acquisition or download support, likely used to obtain embedding or chat models when they are not already present locally.
- The `MkDocs` entry indicates documentation generation or static site support for the project.

## CI / containers (from scan)

```text
No CI/CD pipelines detected.
```

```text
No containerization configs detected.
```

### Raw scan excerpt

```text
No CI/CD pipelines detected.
```

### CI / containers explanation

- The scan reports no CI/CD pipeline files or containerization configuration files within the scanned paths.
- This result is constrained by the applied scan filters and does not represent a comprehensive deployment or infrastructure audit.
- The absence of detected CI/CD or container files may mean that the project is intended to run locally, that deployment tooling is maintained outside the scanned repository, or that such files were excluded by the scan filters.

## Evidence

- `D:\Spock-Universal-AI-Wiki\docs\codebase\.codebase-scan.txt`
- Filters: `.gitignore` + `scan.skip_dirs` + built-in extras

### Evidence explanation

- The listed scan file serves as the primary source artifact for the integration evidence presented above.
- Filters combine `.gitignore`, `scan.skip_dirs`, and built-in exclusion rules to determine which paths are included in the analysis.
- The reported integrations are strictly limited to files and directories that pass these filter criteria.
- Evidence in this document should be treated as scan-derived architectural indication rather than runtime verification.

## SQLite Ship Computer Database (`ship_computer.db`)

### Database Architecture and Purpose

`ship_computer.db` is a SQLite 3 database that functions as the local knowledge store and state manager for the Spock application. It is designed for low-latency, offline-capable data persistence and is accessed primarily through the `WarpCore` orchestration layer and the `wiki_agent` retrieval module.

The database provides a local-first persistence layer for the application’s knowledge, conversation state, retrieval metadata, and cached results. Because SQLite is embedded in the application process, it avoids the operational complexity of a separate database server while still providing transactional integrity, concurrent read access, and simple deployment.

The database typically contains the following logical components:

- **Knowledge Base Tables:** Store structured wiki entries, documentation fragments, source references, and domain-specific reference material.
- **Query & Session Logs:** Track user prompts, system responses, conversation context, and mode-specific state for Ask AI and Deep Dive interactions.
- **Metadata & Indexing Tables:** Maintain chunk identifiers, source provenance, embedding references, similarity metadata, and access or permission information.
- **Cache Tables:** Store frequently requested responses, precomputed context windows, and retrieval results to reduce redundant LLM calls and improve response time.

SQLite is chosen for its zero-configuration deployment, ACID compliance, and seamless integration with Python’s standard library. These properties make it well suited for local-first AI applications that require reliable data integrity without external database dependencies.

### Representative Data Model

The exact schema may vary by deployment, but a typical `ship_computer.db` design would include tables or table groups for the following concerns:

- **Sources:** Track original documents, wiki pages, files, or external references that are ingested into the knowledge base.
- **Chunks:** Store text fragments derived from sources, including chunk text, chunk order, source identifier, and content hash.
- **Embeddings:** Store or reference vector embeddings for chunks, including embedding model identifier, vector dimension, and creation timestamp.
- **Sessions:** Track user conversations, session identifiers, timestamps, and mode-specific state.
- **Messages:** Store individual user and assistant messages within a session.
- **Retrieval Results:** Record which chunks were retrieved for a given query, along with similarity scores and ranking position.
- **Responses:** Store generated answers, prompt context, model identifiers, and response metadata.
- **Cache Entries:** Store reusable query results, context bundles, or precomputed prompts to improve performance.

This structure allows Spock to separate raw knowledge, derived retrieval artifacts, conversational state, and generated responses while preserving enough metadata to audit and reconstruct prior interactions.

### Interaction with Ask AI and Deep Dive Inquiries

The Spock application routes user requests through two distinct inquiry modes, both of which rely on `ship_computer.db` for context assembly and response generation.

#### Ask AI

Ask AI is optimized for direct, single-turn questions. It is intended for users who want a concise answer based on the available local knowledge base.

A typical Ask AI flow is:

1. The user submits a question through the Spock interface.
2. `WarpCore` normalizes the request and identifies the inquiry mode as Ask AI.
3. The application checks cache tables for an exact or near-match response.
4. If a suitable cached response exists, Spock may return it directly or use it to accelerate response generation.
5. If no cached response is found, the query is sent to the embedding service.
6. The embedding service converts the query into a vector representation.
7. The vector database or SQLite-backed retrieval layer searches for the most relevant chunks.
8. `wiki_agent` or the RAG layer assembles a context window from the retrieved chunks.
9. The chat model generates an answer using the assembled context.
10. The final response, retrieved chunks, similarity scores, timestamps, and source references are stored in `ship_computer.db`.

Ask AI uses the database primarily for fast retrieval, response caching, and auditability. The database allows Spock to remember which sources supported a previous answer and to reuse that context when a similar question is asked again.

#### Deep Dive

Deep Dive is designed for complex, multi-step research or iterative exploration. It is intended for questions that require broader context, multiple retrieval passes, or progressive refinement of the answer.

A typical Deep Dive flow is:

1. The user submits a complex question or research objective.
2. `WarpCore` identifies the inquiry mode as Deep Dive.
3. The application creates or resumes a session record in `ship_computer.db`.
4. `wiki_agent` decomposes the question into subtopics, subqueries, or retrieval goals.
5. Each subquery is embedded and used to retrieve relevant chunks from the vector store.
6. Retrieved chunks are ranked, filtered, and added to a session-specific context window.
7. Intermediate reasoning steps, retrieved sources, and confidence indicators are stored in the database.
8. The application may perform additional retrieval passes based on gaps in the current context.
9. The chat model generates a more detailed answer using the accumulated context.
10. The final response, dependency chain between retrieved chunks, and full research trail are persisted for later review.

Deep Dive relies more heavily on `ship_computer.db` than Ask AI because it must preserve multi-step state. The database tracks which chunks have already been considered, how subqueries relate to one another, and which sources contributed to the final answer. This allows Spock to reconstruct the research trail, cite sources accurately, and maintain coherence across extended conversations.

### Transactional and Operational Behavior

Both Ask AI and Deep Dive benefit from SQLite’s transactional safety. When Spock writes session state, retrieval results, or generated responses, it can use transactions to ensure that partial updates do not corrupt the database.

Typical operational benefits include:

- **Atomic writes:** Session updates and response storage can be committed as a single logical unit.
- **Concurrent reads:** Multiple read operations can access the database while writes are occurring, subject to SQLite locking behavior.
- **Local persistence:** Knowledge and session state remain available even when external model services are temporarily unavailable.
- **Auditability:** Stored metadata supports review of which sources, chunks, and models were used for a given answer.
- **Caching:** Repeated or similar queries can be served faster by reusing stored context or responses.

Connection pooling and prepared statements may be used to optimize throughput during high-frequency retrieval cycles, depending on the application’s database access layer.

## Embedding LLM and Vector Database

### Purpose

The embedding LLM and vector database together provide Spock with semantic retrieval capability. They allow the application to find relevant information based on meaning rather than only exact keyword matching.

In this architecture:

- The **embedding LLM** converts text into numerical vector representations.
- The **vector database** stores those vectors along with metadata.
- The **RAG layer** uses vector similarity search to retrieve relevant context.
- The **chat LLM** generates natural-language answers using the retrieved context.

This combination enables Spock to answer questions from local knowledge, cite sources, and support both simple Ask AI queries and more complex Deep Dive research.

### Components

The scan evidence indicates the following relevant components:

| Component | Role | Evidence |
| --- | --- | --- |
| `llama-server embeddings` | Generates text embeddings | `llama_server_manager` / `Launch` |
| `llama-server chat` | Generates chat responses | `llama_server_manager` / `Launch` |
| `RAG API` | Coordinates retrieval and prompt assembly | `rag_api_server.py` |
| `ship_computer.db` | Stores knowledge, metadata, sessions, and cache | `WarpCore` / `wiki_agent` |

The embedding service is typically exposed on `:8080`, while the chat service is typically exposed on `:8081`. The RAG API is typically exposed on `:8090`. These ports are reported as typical values and may vary by deployment.

### How Spock Uses the Embedding LLM

The embedding LLM is used to transform text into dense vector representations. These vectors capture semantic meaning, allowing similar concepts to be close together in vector space.

Spock uses the embedding LLM in two main scenarios:

#### 1. Ingestion and Indexing

When new knowledge is added to the Spock knowledge base, the application may perform the following steps:

1. Source documents, wiki pages, or reference material are loaded.
2. The content is split into manageable chunks.
3. Each chunk is sent to the embedding LLM.
4. The embedding LLM returns a vector for each chunk.
5. The chunk text, vector, source identifier, and metadata are stored in the vector database or SQLite-backed storage.

This process creates a searchable semantic index of the local knowledge base.

#### 2. Query Embedding

When a user asks a question, Spock uses the embedding LLM to convert the user’s query into a vector. This query vector is then compared against stored chunk vectors to identify the most relevant passages.

This approach allows Spock to retrieve relevant information even when the user’s wording differs from the wording in the source material. For example, a question about “how the ship computer stores session state” can retrieve chunks that discuss “conversation persistence,” “SQLite session tables,” or “Deep Dive context tracking,” even if the exact phrase is not repeated.

### How Spock Uses the Vector Database

The vector database stores the numerical embeddings produced by the embedding LLM, along with the text chunks and metadata needed to retrieve and cite them.

Depending on the deployment, the vector database may be implemented as:

- SQLite tables that store vectors and metadata directly in `ship_computer.db`.
- A separate vector store accessed through the RAG API.
- A hybrid approach where `ship_computer.db` stores application state and the RAG API manages vector search.

The scan evidence identifies `ship_computer.db` as the local persistence layer and `rag_api_server.py` as the retrieval service. This suggests that the vector database may be tightly integrated with the local SQLite store or exposed through the RAG API.

A typical vector database record includes:

- **Chunk identifier:** A unique identifier for the text fragment.
- **Source identifier:** The original document, wiki page, or file.
- **Chunk text:** The actual passage used for retrieval and context assembly.
- **Embedding vector:** The numerical representation produced by the embedding LLM.
- **Embedding model:** The model or version used to generate the vector.
- **Timestamp:** When the chunk was indexed.
- **Metadata:** Additional fields such as section title, access level, content hash, or domain tags.

### Retrieval Process

When Spock needs to answer a question, it uses the vector database to perform semantic search.

A typical retrieval process is:

1. The user query is embedded by the embedding LLM.
2. The query vector is sent to the vector database or RAG API.
3. The system calculates similarity between the query vector and stored chunk vectors.
4. The most similar chunks are returned, usually as a top-k result set.
5. The RAG layer filters, ranks, or reranks the retrieved chunks.
6. The selected chunks are assembled into a prompt context.
7. The chat LLM generates an answer grounded in that context.

The similarity metric may be cosine similarity, dot product, or another vector distance measure, depending on the embedding model and vector store implementation.

### Ask AI Retrieval Pattern

Ask AI uses a relatively direct retrieval pattern:

1. Embed the user’s question.
2. Retrieve the most relevant chunks.
3. Assemble a compact context window.
4. Generate a concise answer.
5. Store the response and retrieval metadata in `ship_computer.db`.

This pattern is optimized for speed and simplicity. It is suitable for questions that can be answered from a small number of highly relevant passages.

### Deep Dive Retrieval Pattern

Deep Dive uses a more iterative retrieval pattern:

1. Embed the initial question.
2. Retrieve an initial set of relevant chunks.
3. Analyze the retrieved context for gaps or unresolved subtopics.
4. Generate additional subqueries when needed.
5. Embed and retrieve additional chunks for each subquery.
6. Merge and deduplicate the accumulated context.
7. Generate a detailed answer using the expanded context.
8. Store the full retrieval trail, intermediate steps, and final response in `ship_computer.db`.

This pattern allows Spock to explore a topic more thoroughly than a single retrieval pass would permit. It is especially useful for questions that require synthesis across multiple sources, sections, or conceptual areas.

### Relationship Between the Embedding LLM, Vector Database, and `ship_computer.db`

The embedding LLM, vector database, and `ship_computer.db` work together as a local retrieval pipeline.

- The **embedding LLM** provides semantic encoding for both stored knowledge and user queries.
- The **vector database** provides similarity search over encoded knowledge.
- The **RAG API** coordinates retrieval, context assembly, and prompt construction.
- The **chat LLM** generates the final answer.
- **`ship_computer.db`** persists knowledge, metadata, sessions, retrieval results, and responses.

This design allows Spock to operate as a local-first AI assistant while retaining enough state to support caching, citation, auditing, and multi-turn research.

### Failure and Fallback Behavior

The exact fallback behavior may depend on configuration and deployment. However, a robust Spock deployment would typically handle the following conditions:

- **Embedding service unavailable:** Spock may return an error, disable semantic search, or fall back to keyword-based retrieval if such a fallback is implemented.
- **Vector database unavailable:** Spock may be unable to retrieve local knowledge and may respond with a degraded or error state.
- **Chat service unavailable:** Spock may be unable to generate natural-language answers even if retrieval succeeds.
- **Stale embeddings:** If the embedding model changes, previously stored vectors may no longer be compatible with new query vectors. A reindexing step may be required.
- **Cache inconsistency:** Cached responses may become stale if the underlying knowledge base changes. Cache entries should include source versioning or invalidation metadata where possible.

These considerations are important because the quality of Spock’s answers depends on the consistency of the embedding model, the freshness of the vector index, and the integrity of the local database state.
## Embedding LLM and Vector Database Integration

### Embedding Generation and Indexing
Spock uses a dedicated embedding LLM, exposed via `llama-server embeddings` on port `:8080`, to convert unstructured text into high-dimensional dense vectors. These vectors represent semantic meaning, syntax, and contextual relationships in a numerical format that can be compared mathematically.

The workflow operates as follows:

1. **Chunking:** Incoming documents, wiki pages, or user prompts are segmented into semantically coherent chunks by the `wiki_agent`. Chunking preserves local meaning while keeping each unit small enough to embed efficiently.
2. **Vectorization:** Each chunk is sent to the embedding LLM, which returns a fixed-length vector representation. The vector captures the chunk’s semantic content in a shared vector space.
3. **Storage:** Vectors are persisted alongside their source metadata in the vector database. In Spock’s architecture, this is typically implemented as a vector-enabled SQLite extension or a tightly coupled local vector store that shares the same filesystem boundary as `ship_computer.db`.
4. **Indexing:** Approximate Nearest Neighbor (ANN) indexes, such as HNSW or IVF, are maintained to enable low-latency similarity searches without scanning the entire corpus.

### Vector Search and Retrieval Workflow
The vector database serves as the semantic backbone for Spock’s Retrieval-Augmented Generation (RAG) pipeline, orchestrated by the `RAG API` on `:8090`:

- **Query Transformation:** User input is embedded using the same model that processed the knowledge base, ensuring vector space alignment between indexed content and incoming queries.
- **Similarity Search:** The system executes a cosine similarity or inner-product search against the vector index, returning the top-k most relevant chunks based on a configurable threshold.
- **Context Assembly:** Retrieved chunks are ranked, deduplicated, and formatted into a structured context window. Source provenance is preserved to enable citation and traceability.
- **LLM Generation:** The assembled context is injected into the chat LLM (`llama-server chat` on `:8081`) alongside the original prompt. The model generates a grounded response, which is then validated, cached, and returned to the user.

This architecture ensures that Spock maintains high factual accuracy, minimizes hallucination, and scales efficiently by offloading semantic matching to the vector layer while keeping the generation layer focused on synthesis and instruction following.

### SQLite 3 `ship_computer.db` and Spock Interaction
`ship_computer.db` is the local SQLite 3 database that stores Spock’s application-level state. It provides durable, transactional storage for conversations, document metadata, retrieval provenance, Deep Dive task progress, caches, and audit records.

The vector database stores the high-dimensional embeddings and ANN index. `ship_computer.db` stores the relational metadata that Spock needs to understand, cite, resume, and audit those vectors. In other words, the vector layer answers “what is semantically similar?”, while `ship_computer.db` answers “what did the user ask, what was retrieved, what was generated, and where did it come from?”

Key responsibilities of `ship_computer.db` include:

- **Conversation persistence:** Stores Ask AI sessions, user prompts, assistant responses, timestamps, and model metadata.
- **Document and chunk metadata:** Tracks source documents, wiki pages, chunk text, chunk order, source location, hashes, and permissions.
- **Retrieval provenance:** Records query embeddings, retrieved chunk IDs, similarity scores, thresholds, and retrieval timestamps.
- **Deep Dive task state:** Stores Deep Dive objectives, subquestions, intermediate retrieval results, generated sections, final reports, and task status.
- **Caching:** Stores reusable embeddings, retrieval results, or generated answers to reduce latency and model load.
- **Audit and replay:** Preserves enough context to reproduce, inspect, or regenerate a previous Ask AI or Deep Dive response.

A representative data model may include the following tables:

| Table | Purpose |
|---|---|
| `sessions` | Stores user sessions, active conversation context, and UI state. |
| `messages` | Stores user prompts, assistant responses, timestamps, and model metadata. |
| `documents` | Stores source documents, wiki pages, or uploaded files. |
| `chunks` | Stores chunk text, chunk order, source location, and content hash. |
| `embeddings` | Stores embedding ID, model, dimension, vector reference, and indexing status. |
| `retrieval_logs` | Stores query embeddings, top-k results, scores, thresholds, and retrieval metadata. |
| `deep_dive_tasks` | Stores Deep Dive objectives, status, final report, and task lifecycle state. |
| `deep_dive_steps` | Stores subquestions, intermediate retrieval results, and generated sections. |
| `citations` | Maps response claims to source chunks and documents. |
| `caches` | Stores reusable answers, embeddings, or retrieval results. |

#### Ask AI Interaction
For an Ask AI inquiry, Spock uses `ship_computer.db` as the durable record of the interaction:

1. Spock receives the user’s question.
2. Spock creates or loads a session and stores the user message in `ship_computer.db`.
3. Spock calls the `RAG API` on `:8090`.
4. The `RAG API` embeds the query using the embedding LLM on `:8080`.
5. The vector database returns the most relevant chunks.
6. Retrieved chunk IDs, scores, and provenance are written to `ship_computer.db`.
7. The chat LLM on `:8081` generates a grounded answer.
8. The final answer, citations, model metadata, and cache entries are stored in `ship_computer.db`.

This allows Spock to display citations, resume the conversation, regenerate the answer, and audit the retrieval path.

#### Deep Dive Interaction
For a Deep Dive inquiry, Spock uses `ship_computer.db` to track a multi-step research task:

1. Spock creates a Deep Dive task and stores the user’s objective.
2. A planning step decomposes the objective into subquestions or research steps.
3. Each step triggers embedding and vector search through the `RAG API`.
4. Intermediate retrieval results, generated sections, and step status are stored in `ship_computer.db`.
5. A synthesis step combines the intermediate results into a final report.
6. The final report, citations, task status, and audit trail are persisted in `ship_computer.db`.

This design allows Deep Dive tasks to be paused, resumed, inspected, regenerated, or audited without losing intermediate work.

### How Spock Uses the Embedding LLM and Vector Database
Spock uses the embedding LLM and vector database in two distinct phases: indexing and retrieval.

#### Indexing Phase
During indexing, Spock converts source content into searchable semantic vectors:

1. Source content is ingested from documents, wiki pages, or other local knowledge sources.
2. The `wiki_agent` chunks the content into meaningful units.
3. Each chunk is sent to the embedding LLM on `:8080`.
4. The embedding LLM returns a dense vector for the chunk.
5. The vector, chunk metadata, and source identifiers are stored in the vector database.
6. The ANN index is updated so future queries can search the corpus efficiently.

The embedding LLM is not the chat LLM. It does not generate natural-language answers. Its role is to produce numerical representations of text that can be compared by similarity.

#### Retrieval Phase
During retrieval, Spock uses the same embedding model to convert the user’s question into a vector:

1. The user submits an Ask AI or Deep Dive query.
2. The query is embedded using the embedding LLM on `:8080`.
3. The query vector is compared against the indexed chunk vectors.
4. The vector database returns the top-k most similar chunks.
5. Spock ranks, deduplicates, and assembles the retrieved chunks into a context window.
6. The context is passed to the chat LLM on `:8081` for answer generation.

Using the same embedding model for indexing and querying is important because it ensures that both the knowledge base and the user query exist in the same vector space. If different models were used, similarity scores would not be meaningful.

#### Deep Dive Retrieval Phase
Deep Dive extends the same retrieval pattern across multiple steps:

1. Spock plans a sequence of subquestions.
2. Each subquestion is embedded and searched independently.
3. Retrieved evidence is stored as intermediate results.
4. Spock may generate follow-up questions based on gaps in the evidence.
5. The final answer is synthesized from the accumulated context.
6. All steps, citations, and intermediate outputs are persisted in `ship_computer.db`.

This allows Deep Dive to behave like a local research assistant rather than a single-shot question-answering system.

#### Consistency and Operational Behavior
Spock relies on several operational guarantees:

- **Model consistency:** The same embedding model, dimensionality, and normalization behavior are used for indexing and querying.
- **Provenance tracking:** Every retrieved chunk can be traced back to a source document, chunk ID, and retrieval log entry.
- **Caching:** Embeddings, retrieval results, or generated answers may be cached to improve latency.
- **Reindexing:** If the embedding model changes, the vector index must be rebuilt or migrated to preserve semantic alignment.
- **Local storage:** Both `ship_computer.db` and the vector store remain within the same local filesystem boundary, supporting offline or air-gapped operation.
- **Auditability:** `ship_computer.db` preserves enough metadata to explain why a particular answer was generated.

### Ask AI and Deep Dive Inquiry Flow
**Ask AI** is a single-question or conversational query flow. The user asks a question, Spock retrieves relevant context, and the chat LLM generates a grounded response.

Typical Ask AI flow:

1. User submits a question in Spock.
2. Spock stores the question in `ship_computer.db`.
3. Spock requests retrieval from the `RAG API` on `:8090`.
4. The `RAG API` embeds the question using the embedding LLM on `:8080`.
5. The vector database returns the most relevant chunks.
6. Spock assembles the context and sends it to the chat LLM on `:8081`.
7. The chat LLM generates an answer.
8. Spock stores the answer, citations, retrieval metadata, and cache entries in `ship_computer.db`.
9. The user receives the answer with source context.

**Deep Dive** is a multi-step research flow. The user provides a broader objective, and Spock performs iterative retrieval, synthesis, and reporting.

Typical Deep Dive flow:

1. User submits a Deep Dive objective.
2. Spock creates a task record in `ship_computer.db`.
3. Spock decomposes the objective into subquestions or research steps.
4. Each step is embedded and searched through the vector database.
5. Intermediate results are stored in `ship_computer.db`.
6. Spock synthesizes the results into a structured report.
7. Citations and provenance are attached to the final report.
8. The completed Deep Dive task is persisted for review, regeneration, or audit.