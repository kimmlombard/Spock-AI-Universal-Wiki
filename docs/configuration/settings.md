# Settings

Global and per-profile settings are managed by `WarpCore.settings_store`, which persists data in `ship_computer.db`. This database acts as the persistent state store for user preferences, runtime configurations, and session metadata. Canonical **port mappings**, **documentation URLs**, and **context / max_tokens** defaults are defined in `WarpCore/service_endpoints.py` and seeded via `WarpCore/config_defaults.py`.

Per-profile settings allow different model or embedding profiles to use distinct endpoints and context limits, while global settings provide shared fallback values when a profile-specific value is not defined.

## Service ports (defaults)

| Role | Default | App config / env |
|------|---------|------------------|
| Embeddings | 8080 | `embed_port`, `embedding_profile.embeddings_url`, `SPOCK_EMBED_PORT` |
| Chat | 8081 | `llama_port`, `SPOCK_CHAT_PORT` |
| Llama WebUI proxy | 8082 | `mcp.webui_port`, `SPOCK_MCP_WEBUI_PORT` |
| RAG API | 8090 | `rag_api.port`, `SPOCK_RAG_PORT` |
| MCP HTTP | 8765 | `mcp.http_port`, `SPOCK_MCP_PORT` |
| AI Helper docs | 8000 | `docs_port`, `SPOCK_DOCS_PORT` |

The values in the **App config / env** column represent alternative sources for the same logical endpoint. A full URL setting, such as `embedding_profile.embeddings_url`, may include a port and can be used to specify the complete endpoint address.

**Context Settings:** `embed_n_ctx`, `chat_n_ctx`, and `chat_max_tokens` control the model's context window size and maximum output length. These are configured via **Configure Spock AI → Llama.cpp**.

- `embed_n_ctx`: Maximum number of tokens that can be processed for embedding-related context.
- `chat_n_ctx`: Maximum number of tokens available to the chat model during inference.
- `chat_max_tokens`: Maximum number of tokens allowed in a generated response.

These settings can be edited in the **Configure Spock AI** interface, or set using `SPOCK_*` environment variables before launching the application. If installing a second instance on the same machine, ensure that different ports are used or stop the first instance to avoid binding conflicts.

## SQLite 3 `ship_computer.db`

`ship_computer.db` is a local SQLite 3 database used by the Spock application as its primary persistent state store. It is embedded in the application, meaning it does not require a separate database server. The database stores configuration, session state, document metadata, retrieval results, and other data needed to support **Ask AI** and **Deep Dive** inquiries.

In practice, `ship_computer.db` may contain logical data groups such as:

- **Settings**: global and per-profile configuration values.
- **Profiles**: model, embedding, endpoint, and context-window settings.
- **Sessions**: conversation state, user prompts, assistant responses, and follow-up context.
- **Documents**: metadata for uploaded or indexed documents, including source, title, owner, and status.
- **Chunks**: document fragments used for retrieval, including chunk text, position, and associated document.
- **Embeddings**: vector representations of chunks or queries, either stored directly in SQLite or referenced from an external vector database.
- **Retrieval results**: cached or logged search results, similarity scores, and selected context for a given inquiry.
- **Usage or audit data**: timestamps, profile selections, model endpoints, and request metadata.

The exact table names and schema may vary by deployment, but the database serves as the durable record of what the user configured, what content was indexed, and how the application answered previous questions.

### How Ask AI uses `ship_computer.db`

**Ask AI** is a direct question-and-answer mode. When a user submits an Ask AI request, Spock uses `ship_computer.db` to resolve the active configuration and to preserve the resulting conversation.

A typical Ask AI flow is:

1. **Resolve the active profile**  
   Spock reads the selected or default profile from the database. This profile determines which embedding endpoint, chat endpoint, context limits, and model settings should be used.

2. **Load context settings**  
   Values such as `embed_n_ctx`, `chat_n_ctx`, and `chat_max_tokens` are read from the profile or global settings. These values control how much context can be sent to the embedding model and how much output the chat model may generate.

3. **Prepare the user query**  
   The user's question is normalized and prepared for retrieval. Depending on the implementation, Spock may also include recent conversation context from the session stored in the database.

4. **Retrieve relevant content**  
   The query is converted into an embedding and used to search the vector database. The retrieved chunks, their scores, and their source metadata are used to build the prompt for the chat model.

5. **Generate the answer**  
   The chat model receives the user question, retrieved context, and any system instructions. It returns a natural-language answer.

6. **Persist the interaction**  
   Spock stores the user question, assistant answer, selected profile, retrieved chunk references, and timestamps in `ship_computer.db`. This allows the conversation to continue, be reviewed later, or be used for follow-up questions.

### How Deep Dive uses `ship_computer.db`

**Deep Dive** is a more thorough inquiry mode. Instead of answering from a single retrieval pass, Deep Dive may perform multiple retrieval steps, expand the search, compare sources, and synthesize a longer response.

`ship_computer.db` supports Deep Dive by storing both the final answer and the intermediate state of the investigation.

A typical Deep Dive flow is:

1. **Create or resume a Deep Dive session**  
   Spock creates a session record in the database. This record tracks the user's original request, the active profile, and the current stage of the analysis.

2. **Perform initial retrieval**  
   The user's request is embedded and used to search the vector database. The most relevant chunks are selected.

3. **Generate follow-up queries**  
   The chat model may identify gaps in the retrieved context and generate additional search queries. These queries are embedded and used to retrieve more content.

4. **Accumulate evidence**  
   Retrieved chunks, similarity scores, source documents, and intermediate summaries are stored or referenced in the database. This allows Spock to avoid repeating work and to maintain a consistent evidence set.

5. **Synthesize the final response**  
   The chat model combines the accumulated context into a detailed answer, report, or analysis.

6. **Persist the Deep Dive result**  
   The final response, supporting citations, retrieved chunk references, and session state are written to `ship_computer.db`. This enables the user to return to the Deep Dive later, ask follow-up questions, or review the sources used.

## Embedding LLM and vector database

Spock uses an **embedding LLM** and a **vector database** to support retrieval-augmented generation, or RAG. The embedding LLM converts text into numerical vectors, and the vector database stores and searches those vectors to find content that is semantically similar to the user's question.

### Embedding LLM

The embedding LLM is a model that produces dense vector representations of text. Unlike the chat model, it does not generate natural-language answers. Instead, it maps text into a fixed-size numerical vector that captures semantic meaning.

In Spock, the embedding LLM is typically exposed through the embeddings endpoint, commonly on port `8080`. The active embedding profile determines which endpoint, model, and context settings are used.

The embedding LLM is used for:

- **Document chunking and indexing**  
  When documents are added to Spock, they are split into chunks. Each chunk is sent to the embedding LLM and converted into a vector.

- **Query embedding**  
  When a user asks a question in Ask AI or Deep Dive, the question is sent to the embedding LLM and converted into a query vector.

- **Semantic matching**  
  The query vector is compared against stored chunk vectors to find the most relevant content.

The `embed_n_ctx` setting controls how much text the embedding model can process at once. If a chunk or query exceeds this limit, Spock must truncate, split, or otherwise manage the input before sending it to the embedding endpoint.

### Vector database

The vector database stores the embeddings produced by the embedding LLM. Each vector is associated with metadata, such as the source document, chunk identifier, profile, timestamp, and relevance score.

The vector database may be implemented in one of two ways:

- **SQLite-backed vector storage**  
  Vectors are stored directly in `ship_computer.db`, often as binary `BLOB` values. This keeps the system self-contained and simple to deploy.

- **External vector database**  
  Vectors are stored in a dedicated vector database, while `ship_computer.db` stores metadata, session state, and references to the external vectors.

In either case, the vector database enables similarity search. When Spock receives a query vector, it searches for the closest stored vectors, usually using cosine similarity or another distance metric. The top matching chunks are returned with their scores and metadata.

### Typical Ask AI and Deep Dive retrieval flow

The following flow describes how Spock uses the embedding LLM and vector database for both Ask AI and Deep Dive:

1. **User submits a question**  
   The question is received by the Spock application.

2. **Active profile is resolved**  
   Spock reads the selected profile from `ship_computer.db` and determines the embedding endpoint, chat endpoint, and context limits.

3. **Question is embedded**  
   The question is sent to the embedding LLM endpoint. The model returns a vector representation of the question.

4. **Vector search is performed**  
   The query vector is compared against stored chunk vectors in the vector database. The most similar chunks are selected.

5. **Retrieved context is assembled**  
   Spock combines the selected chunks, their metadata, and any session context into a prompt for the chat model.

6. **Chat model generates a response**  
   The chat model uses the retrieved context to answer the user's question.

7. **Result is persisted**  
   The question, answer, profile, retrieved chunk references, and session state are stored in `ship_computer.db`.

For **Ask AI**, this process is usually a single retrieval-and-answer cycle. For **Deep Dive**, the process may repeat with additional queries, broader retrieval, and intermediate summaries until the application has enough context to produce a detailed response.
## Configuration Hierarchy

Settings follow a strict precedence order where higher-priority sources override lower-priority ones:

1.  **Hardcoded Defaults:** Values defined in `WarpCore/config_defaults.py` and `WarpCore/service_endpoints.py`.
2.  **Environment Variables:** `SPOCK_*` variables (e.g., `SPOCK_CHAT_PORT`) override defaults if set before startup.
3.  **Database/UI Config:** Persistent settings saved to `ship_computer.db` or modified via the **Configure Spock AI** UI take precedence over environment variables for runtime behavior.

In practice, a fresh installation uses hardcoded defaults unless `SPOCK_*` environment variables are present at startup. Once a value is saved in the database through the application UI, that stored value becomes the active setting until it is explicitly changed again.

### SQLite Database Architecture & Interaction

The `ship_computer.db` file is a local SQLite 3 database that serves as the central repository for application state. It interacts with the Spock application to manage persistent data required for both Ask AI and Deep Dive inquiries.

`ship_computer.db` is responsible for storing the information Spock needs to preserve continuity across sessions, restore user preferences, resume interrupted work, and coordinate with external or embedded model services. It is not primarily used to store large model weights or raw vector indexes, but it does store the metadata, configuration, session state, and indexing status needed to locate, validate, and reuse those resources.

**Database Management:**
*   **Storage Engine:** Uses SQLite 3 for lightweight, serverless storage optimized for desktop applications. The database operates in WAL (Write-Ahead Logging) mode to allow concurrent reads while writes are occurring, preventing lock contention during active AI sessions.
*   **Access Layer:** The `WarpCore.settings_store` module abstracts direct database access, providing a clean, type-safe API for reading and writing configuration values, session metadata, and analysis checkpoints.
*   **Initialization:** The database schema is auto-generated on first launch using the structure and seed values defined in `WarpCore/config_defaults.py`. Subsequent launches validate the schema version and apply incremental migrations if necessary.

**Interaction with Ask AI:**
For Ask AI inquiries, the database stores and retrieves:
*   **User Preferences:** Specific context window sizes (`embed_n_ctx`, `chat_n_ctx`) and token limits (`chat_max_tokens`) that dictate how much input context the model can process and how long a generated response may be.
*   **Session State:** Metadata regarding active chat sessions, including conversation history pointers, selected model profiles, and prompt templates. This ensures continuity between user interactions without reloading the entire context into memory.
*   **Configuration Overrides:** Any UI modifications made in **Configure Spock AI** are written here, ensuring that Ask AI uses the most recent settings rather than static environment variables or hardcoded defaults.

**Interaction with Deep Dive:**
For Deep Dive inquiries (long-context analysis), the database supports:
*   **Session Persistence:** Maintains state for long-running analysis tasks, including document ingestion progress, chunking strategies, and intermediate reasoning steps. This prevents data loss if the application restarts unexpectedly.
*   **Analysis Logs & Checkpoints:** Stores configuration snapshots and vector indexing status associated with specific deep dive sessions, allowing users to resume, branch, or review past analyses without reprocessing source documents.
*   **Resource Management:** Tracks active connections, embedding cache status, and memory allocation limits to optimize performance during heavy computational tasks. The database also logs rate-limiting states and fallback routing decisions when primary endpoints are unavailable.

**Loading Configuration:**
To retrieve the current application state from the database, use the following import:

```python
from WarpCore.settings_store import load_app_config

# Load persisted configuration from the database
cfg = load_app_config("ship_computer.db")
```

The path should point to the actual `ship_computer.db` file. If the application uses a default storage location, pass that resolved path instead of a relative filename. The `settings_store` automatically handles connection pooling, schema validation, and graceful fallback to defaults if the database is corrupted or missing.

### Embedding LLM and Vector Database Workflow

Spock uses an embedding LLM and a vector database to turn unstructured text into searchable, semantically meaningful representations. This allows the application to retrieve relevant context for Ask AI and to analyze large document sets during Deep Dive without relying solely on keyword matching or manual indexing.

An **embedding LLM** is a model that converts text into a fixed-length numeric vector, also called an embedding. Each vector represents the semantic meaning of the text in a high-dimensional space. Text with similar meaning produces vectors that are close together, while unrelated text produces vectors that are farther apart.

A **vector database** stores these embeddings along with metadata such as source document, chunk ID, timestamp, model version, and content hash. During a query, Spock embeds the user's question or analysis prompt, searches the vector database for the most similar stored vectors, and then uses the associated text chunks as context for the chat or reasoning model.

#### How Spock Uses the Embedding LLM

1.  **Text Preparation:**
    Spock normalizes and chunks incoming text. For Ask AI, this may include the user's question, recent conversation context, and selected reference material. For Deep Dive, this includes source documents, reports, logs, or other long-form content.

2.  **Embedding Generation:**
    The embedding LLM converts each text chunk into a vector. The model profile, context length, batch size, and endpoint selection are read from `ship_computer.db` or the active configuration hierarchy.

3.  **Cache Validation:**
    Before generating new embeddings, Spock checks whether an equivalent embedding already exists. The cache key is typically derived from the text content, embedding model identifier, model version, dimensionality, and relevant settings. If a valid cached embedding exists, Spock reuses it to reduce latency and cost.

4.  **Vector Storage:**
    New embeddings are written to the vector database. `ship_computer.db` stores the metadata needed to locate and validate those vectors, including vector store path, index name, schema version, embedding model fingerprint, and ingestion status.

5.  **Query Embedding:**
    When the user submits an Ask AI question or starts a Deep Dive analysis, Spock embeds the query using the same embedding model used for the stored content. This ensures that query vectors and document vectors exist in the same semantic space.

6.  **Similarity Search:**
    Spock performs a nearest-neighbor search against the vector database. The most relevant chunks are returned based on similarity score, metadata filters, and any active session constraints.

7.  **Context Assembly:**
    The retrieved chunks are ranked, deduplicated, and assembled into a prompt context. Token limits from `ship_computer.db` determine how much context can be included in the final model request.

8.  **Model Response:**
    The chat or reasoning LLM generates a response using the assembled context. For Ask AI, this produces a conversational answer. For Deep Dive, this may produce summaries, comparisons, extracted insights, or multi-step analysis.

#### How the Vector Database Supports Ask AI

For Ask AI, the vector database enables fast retrieval of relevant context from previously indexed material. Instead of sending the entire conversation history or all available documents to the model, Spock retrieves only the most relevant chunks.

This improves:
*   **Response relevance:** The model receives context that is semantically related to the user's question.
*   **Latency:** Smaller prompts reduce inference time.
*   **Cost:** Fewer tokens are sent to the model.
*   **Consistency:** Session metadata in `ship_computer.db` ensures the same model profile, context limits, and retrieval settings are used across interactions.

#### How the Vector Database Supports Deep Dive

For Deep Dive, the vector database supports long-context analysis by breaking large documents into manageable chunks and indexing them for semantic search.

During a Deep Dive session, Spock may:
*   Ingest multiple source documents.
*   Chunk documents using a strategy stored in `ship_computer.db`.
*   Generate embeddings for each chunk.
*   Store vectors and metadata in the vector database.
*   Record ingestion progress and checkpoints in `ship_computer.db`.
*   Resume interrupted indexing if the application restarts.
*   Reuse existing embeddings when documents or model settings have not changed.

This allows Deep Dive to analyze large corpora incrementally and to recover from failures without reprocessing every document from scratch.

#### Relationship Between `ship_computer.db` and the Vector Database

`ship_computer.db` and the vector database serve different but complementary roles.

| Component | Primary Responsibility |
|---|---|
| `ship_computer.db` | Stores configuration, session state, user preferences, checkpoints, model settings, and vector index metadata. |
| Vector database | Stores embeddings and performs similarity search over semantic content. |
| Embedding LLM | Converts text into vectors for storage and query matching. |
| Chat/Reasoning LLM | Generates answers or analysis using retrieved context. |

In a typical Spock workflow, `ship_computer.db` tells the application which embedding model to use, where the vector database is located, which chunks have already been indexed, and how to reconstruct the active session. The vector database then provides the semantic search capability needed to retrieve relevant content for the model.

#### Failure Handling and Fallback Behavior

If the embedding endpoint is unavailable, rate-limited, or misconfigured, Spock can fall back to a secondary endpoint or cached embeddings, depending on the active configuration. `ship_computer.db` records the fallback decision, rate-limit state, and last successful model version so the application can resume consistently.

If the vector database is missing or corrupted, Spock can rebuild the index from source documents when available. The rebuild process uses the chunking strategy and embedding settings stored in `ship_computer.db`, ensuring that the regenerated index matches the user's intended configuration.
## Embedding LLM & Vector Database Integration

The Spock application relies on a coordinated pipeline between an embedding LLM, a vector database, and the primary chat LLM to power retrieval-augmented generation (RAG) for both Ask AI and Deep Dive workflows.

**Embedding LLM Role:**
The embedding model (typically running on port `8080`) converts unstructured text into high-dimensional dense vectors. Unlike the chat LLM, which generates human-readable text, the embedding model is optimized for semantic similarity. When a user submits a query or uploads a document, Spock routes the text through the embedding endpoint to generate fixed-length vector representations that capture contextual meaning rather than exact keyword matches.

**Vector Database Role:**
The vector database stores these embeddings alongside metadata (source document, chunk ID, timestamp, and profile tags). It maintains an optimized index (e.g., HNSW or IVF) that enables sub-millisecond similarity searches. When Spock needs to retrieve relevant context, it queries the vector database using cosine similarity or inner product distance metrics to find the most semantically related chunks.

**Ask AI Retrieval Flow:**
1.  **Query Embedding:** The user's prompt is sent to the embedding LLM and converted into a query vector.
2.  **Similarity Search:** The vector database retrieves the top-k most relevant document chunks based on the query vector.
3.  **Context Assembly:** Retrieved chunks are concatenated with the user's prompt and system instructions, respecting the `chat_n_ctx` limit stored in `ship_computer.db`.
4.  **LLM Inference:** The augmented prompt is sent to the chat LLM (port `8081`), which generates a grounded response.
5.  **State Persistence:** Session metadata and retrieval statistics are logged to `ship_computer.db` for continuity and debugging.

**Deep Dive Analysis Flow:**
1.  **Document Ingestion & Chunking:** Large documents are split into manageable segments using configurable token limits and overlap strategies.
2.  **Batch Embedding:** Chunks are processed in parallel batches through the embedding LLM to maximize throughput.
3.  **Vector Indexing:** Embeddings are written to the vector database with deep-dive-specific metadata tags.
4.  **Iterative Retrieval & Reasoning:** The chat LLM performs multi-step analysis, querying the vector database at each reasoning step to gather evidence, cross-reference findings, and maintain logical consistency.
5.  **Checkpointing:** Intermediate analysis states, vector cache status, and resource utilization metrics are persisted to `ship_computer.db`, enabling seamless session resumption and audit trails.

**Coordination with `ship_computer.db`:**
The SQLite database acts as the control plane for the embedding and vector pipeline. It stores:
*   Embedding model profiles and endpoint configurations.
*   Vector index metadata, cache invalidation flags, and synchronization timestamps.
*   Rate-limit counters and fallback routing rules when the primary embedding service is overloaded.
*   Session-specific vector query logs for Deep Dive traceability.

## Usage

The following example shows how to resolve effective endpoint and context values from an already loaded configuration object.

```python
from WarpCore.service_endpoints import resolve_ports, resolve_ctx, docs_base_url

# Resolve ports from the current app configuration object
ports = resolve_ports(app_config)   # dict: embed, chat, rag, mcp_http, docs, …
ctx = resolve_ctx(app_config)       # embed_n_ctx, chat_n_ctx, chat_max_tokens
print(docs_base_url(app_config))    # Base URL for documentation endpoints
```