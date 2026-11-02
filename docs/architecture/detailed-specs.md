# Detailed Specs

## Server Configuration

### Embed Server (Port 8080)
- **Function:** Handles vector embedding generation for document chunks and user queries.
- **Usage:** Integrated into the Retrieval-Augmented Generation (RAG) pipeline to produce dense, fixed-dimensional numerical representations for indexing, retrieval, and semantic similarity comparison.
- **Note:** This server transforms unstructured text into high-dimensional vectors that are persisted in or referenced by the knowledge base. Applications must use a consistent embedding model and vector dimensionality across both ingestion and query phases to ensure mathematical comparability and retrieval accuracy.

### Chat Server (Port 8081)
- **Function:** Provides LLM chat completion endpoints for natural language interaction.
- **Usage:** Implements an OpenAI-compatible API schema, enabling seamless integration with standard clients, SDKs, and agent frameworks that expect `chat/completions`-style requests.
- **Note:** This server manages text generation inference. In a RAG workflow, it does not perform data retrieval; instead, it receives a structured prompt that has been enriched with context retrieved from the knowledge base, allowing the model to ground its responses in verified source material.

### MCP Server
- **Function:** Acts as a Model Context Protocol (MCP) adapter layer.
- **Usage:** Exposes application tools, data resources, and execution capabilities to AI agents, enabling dynamic tool invocation and structured resource access over supported MCP transports.
- **Note:** This component bridges core application logic with external agent frameworks adhering to the MCP standard. It allows compatible clients to discover, authenticate, and invoke Spock capabilities programmatically without hardcoding integration logic.

### Workflow Integration
The servers operate as a coordinated RAG pipeline:

1. **Ingestion:** The Embed Server converts document chunks into vector embeddings. The resulting vectors, chunk metadata, and source references are persisted in the local knowledge base for indexing.
2. **Retrieval:** When a user submits a query, the system generates an embedding for the prompt and searches the knowledge base to locate semantically relevant context.
3. **Generation:** The Chat Server receives the retrieved context, formatted alongside the original prompt, and generates a grounded LLM response.
4. **Agent Access:** The MCP Server exposes selected application capabilities to external AI agents as callable tools or queryable resources.

This architectural separation keeps embedding generation, text inference, and tool exposure decoupled while enabling interoperability through shared data stores and well-defined API contracts.

### Embedding LLM and Vector Database Usage in Spock
Spock uses the Embed Server as its embedding model endpoint and `ship_computer.db` as its local vector database. Together, these components allow Spock to convert natural language input into numerical representations, retrieve semantically relevant content, and assemble grounded context for the Chat Server.

- **Embedding generation:** Spock sends normalized text to the Embed Server during both ingestion and query time. For ingestion, the text is usually a document chunk. For queries, the text is the user’s question or instruction.
- **Vector storage:** The Embed Server returns a fixed-length vector. Spock stores that vector in `ship_computer.db` alongside the chunk text, source identifier, metadata, and any relevant session or citation information.
- **Semantic retrieval:** When a user asks a question, Spock embeds the query using the same embedding model used during ingestion. It then compares the query vector against stored vectors to identify the most semantically similar chunks.
- **Similarity calculation:** Spock may compute similarity in Python using cosine similarity, dot product, or another compatible metric. If a SQLite vector extension is available, Spock may delegate similarity ranking to the database layer.
- **Context assembly:** After retrieval, Spock ranks, filters, and formats the selected chunks into a prompt. This prompt is then sent to the Chat Server for natural language generation.
- **Consistency requirement:** The embedding model, vector dimensionality, normalization method, and similarity metric must remain consistent between ingestion and retrieval. If these values change, previously stored vectors may no longer be comparable to newly generated query vectors.

## SQLite 3 Database (`ship_computer.db`) and Spock Interaction

The `ship_computer.db` file serves as the primary persistent storage layer for the Spock application. Built on SQLite 3, it functions as a hybrid relational and vector database, managing document chunks, metadata, embedding vectors, session state, and query history. Spock interacts with this database through Python's `sqlite3` (or `aiosqlite` for asynchronous operations) to orchestrate data flow for both **Ask AI** and **Deep Dive** inquiry modes.

### Database Structure and Role
- **Chunk Storage:** Raw text segments, source identifiers, and hierarchical metadata are stored in relational tables.
- **Vector Persistence:** Embedding vectors are serialized (typically as BLOBs or JSON arrays) and stored alongside their corresponding chunk IDs.
- **Session & Context Tracking:** Conversation history, user preferences, and retrieval logs are maintained to enable stateful interactions and auditability.
- **Indexing:** SQLite handles primary key lookups and metadata filtering, while vector similarity operations are either computed in-memory by Spock's Python layer or executed via SQLite's vector search extensions.

### Core Tables and Responsibilities
The following table layout is conceptual and may vary depending on the exact Spock implementation.

| Table | Purpose |
|---|---|
| `chunks` | Stores document text, source references, chunk ordering, and metadata. |
| `embeddings` | Stores serialized vector embeddings and links them to chunk identifiers. |
| `sources` | Tracks document or resource provenance, such as file path, URL, author, or classification. |
| `sessions` | Preserves conversation state, user preferences, and active inquiry mode. |
| `query_logs` | Records user queries, retrieval parameters, selected chunks, and response metadata. |
| `citations` | Maps generated response claims or passages to source chunks for traceability. |

A typical ingestion record would include:

- Chunk text
- Source identifier
- Chunk index or position
- Metadata tags
- Embedding vector
- Embedding model identifier
- Vector dimensionality
- Creation timestamp

A typical query record would include:

- Session identifier
- User query text
- Inquiry mode (`Ask AI` or `Deep Dive`)
- Query embedding
- Retrieval threshold
- Retrieved chunk identifiers
- Re-ranking score, if applicable
- Final prompt context
- Chat Server response metadata

### Ask AI Inquiry Flow
**Ask AI** is optimized for fast, conversational responses. It prioritizes low latency and concise context over exhaustive source coverage.

1. **Query intake:** Spock receives the user’s question and identifies the inquiry mode as **Ask AI**.
2. **Query embedding:** Spock sends the question to the Embed Server and receives a query vector.
3. **Metadata filtering:** Spock applies lightweight filters, such as source type, access level, recency, or session scope, to reduce the candidate set.
4. **Vector search:** Spock searches `ship_computer.db` for the most similar chunks, typically using a small top-k threshold such as top-3 to top-5.
5. **Context assembly:** Spock formats the selected chunks into a compact prompt, preserving source identifiers for citation.
6. **Generation:** Spock sends the prompt to the Chat Server and receives a grounded response.
7. **Logging:** Spock records the query, retrieved chunks, and response metadata in the session and query logs.

This mode is suitable for quick factual questions, status checks, short explanations, and conversational follow-ups where broad analysis is not required.

### Deep Dive Inquiry Flow
**Deep Dive** is optimized for comprehensive, multi-source analysis. It prioritizes coverage, cross-referencing, and traceability over minimal response time.

1. **Query intake:** Spock receives the user’s request and identifies the inquiry mode as **Deep Dive**.
2. **Query embedding:** Spock sends the request to the Embed Server and receives a query vector.
3. **Broad retrieval:** Spock queries `ship_computer.db` with a larger top-k threshold, such as top-20 to top-50, to capture a wider set of potentially relevant chunks.
4. **Metadata expansion:** Spock applies additional metadata filters and may expand the search to related sources, tags, or linked documents.
5. **Re-ranking:** Spock re-ranks candidates using semantic similarity, lexical overlap, source authority, recency, and relevance to the session context.
6. **Cross-referencing:** Spock groups related chunks by source, topic, or metadata cluster to support multi-source reasoning.
7. **Context assembly:** Spock builds a larger, structured prompt that includes prioritized context, source citations, and any necessary reasoning constraints.
8. **Generation:** Spock sends the enriched prompt to the Chat Server and receives a detailed, grounded response.
9. **State persistence:** Spock stores the expanded session state, retrieval results, citation mappings, and reasoning trace to support follow-up questions and auditability.

This mode is suitable for complex investigations, comparative analysis, multi-document synthesis, and questions that require detailed source attribution.

### Transactional and Operational Behavior
In both modes, Spock manages transaction boundaries, handles connection pooling, and ensures data consistency by synchronizing retrieval results with the Chat Server's prompt assembly stage.

- **Read consistency:** Retrieval operations are typically read-only and should not modify chunk, embedding, or source data.
- **Write isolation:** Session updates, query logs, and citation records are written after successful retrieval and, where applicable, after response generation.
- **Error handling:** If embedding generation fails, Spock should avoid falling back to ungrounded generation and should surface a clear error or degraded-mode warning.
- **Model versioning:** Spock should record the embedding model identifier and vector dimensionality with each stored vector to prevent incompatible similarity comparisons.
- **Citation integrity:** Every chunk included in the final prompt should retain a stable identifier so that generated claims can be traced back to their source material.
## Embedding LLM and Vector Database Architecture

The Spock application relies on a tightly coupled embedding LLM and vector database architecture to transform unstructured information into queryable semantic representations. This architecture enables accurate context retrieval, which is the foundation of the RAG pipeline.

### Embedding LLM Functionality
The embedding LLM is a specialized neural network trained to map text into a high-dimensional vector space. Unlike generative LLMs, it does not produce human-readable text; instead, it outputs fixed-length numerical arrays, called embeddings, where semantic similarity corresponds to geometric proximity. Spock routes both document chunks and user queries to the Embed Server on port 8080, which returns these vectors. Consistency in model versioning, tokenizer behavior, and vector dimensionality is strictly enforced to prevent drift between ingestion and retrieval phases.

### Vector Database Operations
The vector database, implemented as the SQLite 3 file `ship_computer.db`, stores embeddings and enables efficient similarity search. When a query arrives, Spock:
1. **Embeds the query:** Sends the user prompt to the Embed Server to generate a query vector.
2. **Executes similarity search:** Computes a distance or similarity metric, typically cosine similarity or Euclidean distance, between the query vector and stored chunk vectors. For moderate-sized corpora, Spock can perform exact search; if a vector extension or external ANN index is available, approximate nearest neighbor search may be used to reduce latency.
3. **Retrieves and ranks results:** Returns the top-k matching chunks, sorted by relevance score. Metadata filters, such as source type, timestamp, access level, document family, and inquiry mode, are applied at the database layer to constrain the search space.
4. **Assembles context:** Formats the retrieved chunks into a structured context block, preserving source citations, chunk boundaries, and ordering information for the generative Chat Server.

### SQLite 3 `ship_computer.db` as the Vector Store
`ship_computer.db` is an embedded SQLite 3 database used by Spock as a lightweight, file-based vector store. It is not a standalone vector database service; instead, Spock uses Python's `sqlite3` interface to manage transactions, metadata, and vector payloads within a single portable database file.

Core SQLite 3 does not provide a native vector index. Spock therefore treats `ship_computer.db` as a metadata store plus vector payload store. Similarity scoring is performed either in Python or through an optional vector extension such as `sqlite-vec`, depending on deployment requirements.

The database typically contains the following logical components:

- **Documents:** Source records such as manuals, logs, tickets, or knowledge-base entries.
- **Chunks:** Text segments derived from documents, including chunk index, token count, content hash, and parent/child relationships for hierarchical retrieval.
- **Embeddings:** Fixed-length vectors generated by the embedding LLM, stored as binary `BLOB` values or JSON arrays, with the model name, model version, and dimension recorded for compatibility checks.
- **Metadata:** Queryable attributes such as source type, access level, timestamp, language, document family, and inquiry-mode eligibility.
- **Audit and query state:** Optional tables for query logs, retrieval scores, and Deep Dive session state.

A typical retrieval query is constrained by model version and dimension before any vector comparison is performed. This prevents Spock from comparing vectors produced by incompatible embedding models. When a vector extension is enabled, Spock can use vector virtual tables and distance functions directly in SQL. Otherwise, Spock loads candidate rows using SQL filters and computes similarity in Python.

Example conceptual query:

```sql
SELECT
    c.id,
    c.content,
    c.source,
    c.chunk_index,
    c.access_level,
    c.updated_at
FROM chunks AS c
JOIN embeddings AS e ON e.chunk_id = c.id
WHERE c.model_version = ?
  AND c.dimension = ?
  AND c.access_level IN (?)
  AND c.source_type IN (?)
ORDER BY vec_distance_cosine(e.embedding, ?) ASC
LIMIT ?;
```

In this flow, SQLite 3 provides transactional storage, filtering, and persistence, while Spock provides the semantic search logic, ranking, and context assembly.

### Ask AI and Deep Dive Inquiry Flows
Spock uses the same embedding LLM and `ship_computer.db` for both Ask AI and Deep Dive inquiries, but it applies different retrieval strategies.

**Ask AI** is optimized for fast, conversational responses. Spock typically:
- Uses the current user prompt and, when available, recent session context.
- Applies stricter metadata filters to reduce noise.
- Retrieves a smaller top-k set of chunks.
- Prefers cached query embeddings and recently accessed chunks when safe to do so.
- Assembles a concise context block for the Chat Server to generate a direct answer.

**Deep Dive** is optimized for analytical, multi-step investigation. Spock typically:
- Expands the user inquiry into multiple subqueries or retrieval facets.
- Retrieves a larger candidate set from `ship_computer.db`.
- Uses hierarchical chunk relationships to include parent context, related sections, or supporting evidence.
- Applies reranking, score thresholds, and citation aggregation.
- May perform iterative retrieval, where early results inform additional queries or filters.
- Produces a richer context block with multiple sources, confidence indicators, and traceable citations.

In both modes, the embedding LLM converts text into comparable vectors, while `ship_computer.db` stores those vectors and the metadata needed to retrieve, filter, and cite the correct context.

### Spock's Orchestration Role
Spock acts as the central orchestrator between the embedding LLM, the vector database, and the generative Chat Server. It manages the chunking strategy, including token limits, overlap, and hierarchical splitting; handles embedding request batching; executes vector similarity computations; and dynamically adjusts retrieval parameters based on the inquiry mode. By decoupling embedding generation from storage and inference, Spock ensures scalability, maintains retrieval accuracy, and provides a reliable foundation for both conversational AI and deep analytical workflows.
## Database

The SQLite-based "ship's computer" local storage manages:
- Profile configurations for user environments.
- UIEG (Universal Extractor) capture data used for content processing, metadata extraction, and knowledge-base preparation.
- Knowledge-base metadata required for retrieval indexing, including chunk identifiers, source references, timestamps, vector IDs, and embedding model information where applicable.
- System health snapshots that record performance metrics, stability indicators, error logs, and diagnostic state.

See [Database Schema](database-schema.md) for detailed table definitions.

### Data Categories
The database is organized into four primary categories to support efficient data management and logical isolation:
- **User Profiles:** Stores configuration settings specific to each workstation, user session, or local environment.
- **Content Extraction:** Retains raw and processed data from the UIEG capture process, including extracted text, metadata tags, source identifiers, and processing status.
- **Knowledge Base:** Contains structured metadata required for vector indexing, search operations, provenance tracking, and retrieval scoring.
- **System Diagnostics:** Logs health metrics, stability indicators, error reports, and maintenance-relevant events.

### SQLite 3 Storage & Interaction
The primary persistent storage for the Spock application is the SQLite 3 database file named `ship_computer.db`. This local database acts as the central persistence layer for data that must survive server restarts, bridging ephemeral server processes with long-term knowledge retention. It serves as the single source of truth for shared application state across the Embed, Chat, and MCP servers when those components need to read or write application data.

#### SQLite 3 Interaction Details
`ship_computer.db` is used as the durable relational store for application state, while the vector database is used as an optimized similarity-search index. In this model, the vector database may return vector IDs, chunk IDs, or similarity scores, but `ship_computer.db` provides the authoritative metadata needed to interpret those results.

The database supports the following interaction patterns:
- **Read operations:** Ask AI and Deep Dive flows read knowledge-base metadata, chunk text references, source provenance, session state, and diagnostic context.
- **Write operations:** UIEG capture, knowledge-base preparation, inquiry processing, and health monitoring write new records, update processing status, and append diagnostic events.
- **Lookup operations:** Vector search results are resolved against SQLite records to retrieve readable content, source references, timestamps, permissions, and embedding model details.
- **Audit operations:** Deep Dive workflows may write reasoning traces, analysis artifacts, and provenance updates so that later sessions can reconstruct how a result was produced.

This separation allows Spock to keep fast vector search separate from durable application state, while still maintaining a single local database for configuration, content metadata, session continuity, and diagnostics.

#### Embedding LLM and Vector Database Integration
Spock uses an embedding LLM, or embedding model, to convert natural-language text into numerical vector representations. These vectors allow the application to compare semantic similarity rather than exact keyword matches. The integration works as follows:

1. **Content Chunking:** Source content from UIEG capture or knowledge-base preparation is divided into manageable chunks. Each chunk is assigned a stable chunk identifier and associated metadata in `ship_computer.db`.
2. **Embedding Generation:** The Embed Server sends each chunk, or a user query, to the configured embedding model. The model returns a high-dimensional vector that represents the meaning of the text.
3. **Vector Storage or Indexing:** The resulting vector is stored in the vector database or vector index. If the deployment uses a separate vector store, `ship_computer.db` stores the vector ID, embedding model name, model version, dimensionality, and the relational metadata needed to resolve the vector back to source content. If the deployment uses a SQLite-backed vector index, the vector payload may also be stored locally while the same metadata tables remain the authoritative source for provenance and retrieval context.
4. **Similarity Search:** When a user asks a question, the same embedding model converts the query into a vector. The vector database searches for the most similar stored vectors and returns candidate vector IDs or chunk identifiers.
5. **Metadata Resolution:** Spock uses `ship_computer.db` to map those vector IDs or chunk identifiers back to readable text, source references, timestamps, permissions, and other provenance data. This step is essential because the vector database identifies semantically similar content, while the SQLite database provides the context needed to build a trustworthy prompt.
6. **Prompt Assembly:** The resolved context is ranked, filtered, and assembled into the prompt sent to the Chat Server for response generation.

This design keeps the vector database optimized for fast similarity search and keeps `ship_computer.db` responsible for durable, queryable application state.

#### Interaction with Ask AI Inquiries
**Ask AI** inquiries are primarily retrieval-focused operations. When a user submits a query through the Spock interface:
1. **Query Preparation:** The application routes the user's question to the Embed Server, which converts the text into a high-dimensional vector representation using the configured embedding model.
2. **Context Fetching:** The application queries `ship_computer.db` to retrieve relevant knowledge-base metadata, chunk identifiers, source references, and any stored semantic context associated with matching content. The database acts as the index-to-content bridge, mapping vector search results back to readable text and provenance data.
3. **Prompt Construction:** Retrieved context is assembled into the prompt sent to the Chat Server for response generation.
4. **Session State:** Temporary session tokens or conversation state may be stored in the database to maintain continuity across multiple turns without requiring external state management.

#### Interaction with Deep Dive Inquiries
**Deep Dive** inquiries involve complex analysis, extended reasoning, or multi-step investigation tasks that require deeper interaction with the data store:
1. **Reasoning Trace Storage:** Intermediate steps, analytical artifacts, and optional chain-of-thought logs generated during complex queries can be persisted for later review or audit.
2. **Extended Context Management:** The database helps manage larger context windows by storing historical conversation segments, prior analysis results, and references to relevant knowledge-base content needed to maintain coherence over long sessions.
3. **Metadata Enrichment:** Deep Dive operations may trigger additional metadata extraction, re-indexing, or provenance updates. These actions are logged and managed within the SQLite schema to preserve data integrity and traceability.

#### Persistence Strategy
The `ship_computer.db` file is designed for local persistence, ensuring that critical configuration, knowledge state, session context, and diagnostic records survive server restarts. It relies on SQLite's ACID-compliant transaction support to reduce the risk of data corruption during write operations from UIEG capture, health monitoring, or inquiry processing. Because multiple components may access the database, application-level coordination should be used for concurrent writes to maintain consistency.
### Embedding LLM & Vector Database Integration

The Spock application uses a dedicated embedding LLM and a vector database to provide semantic search and context-aware retrieval. This allows the system to understand the meaning of user questions and document content rather than relying only on exact keyword matches.

The workflow operates as follows:

- **Embedding Generation:** When new content is ingested through the UIEG pipeline, the Embed Server processes the text chunks and sends them to the configured embedding LLM. The embedding model converts each chunk into a fixed-length numerical vector, also called an embedding. This vector represents the semantic meaning of the chunk, so similar concepts are placed close together in vector space even if they use different wording.

- **Vector Storage & Indexing:** The generated vectors are stored in a local vector database optimized for fast approximate nearest neighbor, or ANN, searches. The vector database maintains an index that enables high-performance similarity matching. This allows the application to quickly identify semantically relevant content without scanning every stored vector.

- **Metadata Synchronization:** `ship_computer.db` maintains a synchronized relational mapping between vector IDs and their corresponding metadata. This metadata can include source files, chunk boundaries, timestamps, processing status, document identifiers, and embedding model versions. When a vector search returns a set of matching vector IDs, the application queries `ship_computer.db` to resolve those IDs into actual text content, provenance information, and related document context.

- **Query Resolution:** During an Ask AI or Deep Dive session, the user's prompt is embedded using the same embedding model used for document ingestion. The resulting query vector is compared against the stored vectors in the vector database. The top-k most similar vectors are retrieved, their metadata is fetched from `ship_computer.db`, and the combined context is injected into the LLM prompt. This decoupled architecture ensures that the vector store handles similarity computation, while SQLite manages relational metadata, session state, and system configuration.

#### SQLite 3 `ship_computer.db` Integration

`ship_computer.db` is a SQLite 3 database that serves as the relational backbone for the Spock application. It stores structured application data that is not well suited to a vector database, including document metadata, chunk records, session history, user settings, processing state, and references to embedded content.

The database is used in several key ways:

- **Document and Chunk Tracking:** `ship_computer.db` records the source of each ingested document, the text chunks derived from that document, and the relationship between each chunk and its corresponding vector ID. This allows the application to retrieve the exact text associated with a vector search result.

- **Provenance and Context:** When the vector database returns relevant chunks, `ship_computer.db` provides the surrounding context needed for a useful LLM response. This can include the original file name, document title, section or page information, chunk order, ingestion timestamp, and processing status.

- **Ask AI Session State:** For Ask AI inquiries, the database stores conversation metadata, user prompts, assistant responses, retrieved context references, and model configuration used for the session. This enables the application to maintain continuity, audit responses, and reconstruct the context that influenced a given answer.

- **Deep Dive Session State:** For Deep Dive inquiries, the database tracks deeper analytical sessions, including the questions asked, the documents or chunks examined, intermediate findings, and the sequence of retrieval steps. This supports more extended, multi-turn investigations where the application must remember what has already been analyzed.

- **Embedding Version Control:** Because embedding models can change over time, `ship_computer.db` stores the embedding model version associated with each vector. This allows the application to detect when stored vectors were generated with an older model and to re-embed content if necessary to maintain search quality.

- **Processing and Synchronization:** The database also tracks ingestion and embedding status, such as whether a document has been parsed, chunked, embedded, indexed, or failed processing. This helps the application avoid duplicate work, recover from interrupted pipelines, and keep the vector database and relational metadata consistent.

In practice, the vector database answers the question, “Which content is semantically similar to this query?” while `ship_computer.db` answers the question, “What is that content, where did it come from, and what application state is associated with it?”

#### How the Spock Application Uses the Embedding LLM and Vector Database

The Spock application uses the embedding LLM and vector database as a retrieval layer that prepares context for the main LLM. The embedding LLM does not generate natural-language answers. Instead, it converts text into numerical vectors that can be compared mathematically.

The process works in two main phases: ingestion and query time.

During ingestion, the application breaks source documents into manageable chunks. Each chunk is sent to the embedding LLM, which produces a vector representation of that chunk. The vector is then stored in the vector database, while the chunk text, source information, and vector ID are stored in `ship_computer.db`. This creates a linked system where semantic similarity is handled by the vector database and structured application data is handled by SQLite.

During query time, the user submits an Ask AI or Deep Dive request. The application embeds the user's prompt using the same embedding model. The resulting query vector is then searched against the vector database. The vector database returns the most similar stored vectors, typically the top-k results. The application then uses those vector IDs to query `ship_computer.db` and retrieve the corresponding text chunks and metadata.

The retrieved chunks are assembled into a context block and provided to the main LLM along with the user's question. The main LLM can then generate a grounded response based on the retrieved content. This approach improves relevance because the system can find conceptually related material even when the user's wording differs from the wording in the source documents.

The separation between the embedding LLM, vector database, and SQLite database is important. The embedding LLM provides semantic representation, the vector database provides fast similarity search, and `ship_computer.db` provides durable relational state, provenance, and application context. Together, they allow Spock to perform accurate, explainable, and context-aware AI interactions.
## Profile System

Profiles define per-workstation configurations to isolate environments:
- **LLM Model Selections:** Specifies which model weights or endpoints are active for inference.
- **Server Port Assignments:** Allocates unique ports to prevent conflicts between multiple instances running on the same machine.
- **Knowledge-Base Paths:** Defines local directories for vector stores and document storage specific to that profile.
- **Theme Preferences:** Sets UI styling options for the dashboard interface to match user or organizational standards.

Managed by `WarpCore.profile_store` and `spock_profile_store`.

### Explanation of Profile System

A profile is a named configuration bundle that captures the settings required for one workstation or deployment context. It allows different users, teams, or environments to run separate instances with distinct LLM models, server ports, knowledge-base locations, and UI themes without interfering with each other. This supports flexibility, personalization, and safe multi-instance operation on shared machines or networks.

By encapsulating these settings in a single profile object, the system reduces configuration drift, simplifies deployment, and helps maintain data isolation and security across workstations. Changes made to one profile do not affect profiles used by other users or environments.

### Profile Stores

`WarpCore.profile_store` and `spock_profile_store` manage persistence and retrieval of profile configurations. They provide a consistent way to create, read, update, and delete profiles so that each workstation can load the correct settings at startup and preserve user-specific preferences across sessions.

### SQLite 3 `ship_computer.db` and Spock Integration

`ship_computer.db` is the local SQLite 3 database used by the Spock application to store structured application state. It provides a lightweight, file-based relational store for data that must be queried, filtered, and audited using SQL.

In the Spock architecture, `ship_computer.db` typically stores:
- **Profile metadata:** active profile names, selected LLM endpoints, ports, knowledge-base paths, and theme settings.
- **Document registry:** source documents, file paths, ingestion timestamps, profile ownership, and content hashes.
- **Chunk metadata:** chunk identifiers, parent document references, character or token offsets, and retrieval filters.
- **Query and session records:** Ask AI and Deep Dive prompts, retrieved context identifiers, generated response metadata, and citation references.
- **Embedding references:** identifiers that link SQLite rows to vectors stored in the vector database.

When a user submits an **Ask AI** inquiry, Spock uses `ship_computer.db` to resolve the active profile, locate the relevant knowledge base, and retrieve metadata for candidate documents or chunks. The application then performs vector similarity search against the vector database. The matching chunk identifiers are joined back to `ship_computer.db` to obtain source information, permissions, and citation details. The final answer is generated by the selected LLM using the retrieved context, and the interaction may be recorded in the database for auditability.

For **Deep Dive** inquiries, Spock uses the same database to maintain a richer context window. Deep Dive can perform multiple retrieval passes, follow references between chunks, filter by document type or profile, and preserve intermediate results. `ship_computer.db` supports this workflow by storing the session state, retrieved chunk sets, and source lineage, allowing the application to reconstruct the evidence trail behind a detailed response.

### Embedding LLM and Vector Database

The Spock application uses an embedding LLM to convert natural-language text into numerical vectors. These vectors represent semantic meaning in a high-dimensional space, where similar concepts are located close together.

The typical workflow is:
1. **Ingestion:** Documents are read from the profile-specific knowledge-base path, split into manageable chunks, and registered in `ship_computer.db`.
2. **Embedding:** Each chunk is passed to the embedding LLM, which produces a vector representation.
3. **Vector storage:** The vector and its associated chunk identifier are stored in the vector database.
4. **Query embedding:** When a user asks a question, the question is embedded using the same embedding model.
5. **Similarity search:** The vector database returns the most semantically similar chunks.
6. **Context assembly:** Spock retrieves the corresponding text and metadata from `ship_computer.db`, then supplies the context to the answer-generating LLM.

The vector database is responsible for fast approximate nearest-neighbor search over embeddings. It is optimized for semantic retrieval, while SQLite provides reliable relational storage for metadata, profiles, documents, and audit records. Together, they allow Spock to answer Ask AI questions with relevant context and support Deep Dive workflows that require repeated, filtered, and traceable retrieval.