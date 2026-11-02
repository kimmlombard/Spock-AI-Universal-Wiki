# LLM Client

The LLM client provides a unified interface for communicating with local LLM inference backends and other OpenAI-compatible services. It abstracts the differences between various LLM servers and APIs, allowing developers to interact with different models through a consistent API without implementing custom connection logic for each backend.

## Components

| Module | Role |
|--------|------|
| `llm_client` | Main client library that provides core functionality for interacting with LLMs |
| `lm_studio_api` | Wrapper for the LM Studio API, enabling communication with the LM Studio GUI-based inference tool through its HTTP endpoint |
| `llama_server_manager` | Manages the lifecycle of the llama.cpp server, including starting, stopping, and monitoring server health status |
| `gemini_openai_models` | Registry for Gemini and OpenAI models, facilitating compatibility mapping between different model families to ensure consistent API usage |

## Usage

```python
from llm_client import LLMClient

# Initialize the client with the base URL of the inference server.
client = LLMClient(base_url="<inference-server-url>")

# Send a chat request to the selected backend.
response = client.chat("What is the meaning of life?")
```

### Message Format and Parameters

The example above demonstrates a high-level abstraction where the prompt is passed as a plain string. In production scenarios, requests should be structured using message objects (e.g., `system`, `user`, and `assistant` roles) to support multi-turn conversations, system instructions, and tool calling. The client automatically serializes these message objects into the JSON payload format expected by the underlying OpenAI-compatible backend.

## Supported Backends

- **LM Studio** — A local GUI-based inference tool for running LLMs on a machine. It exposes an OpenAI-compatible API endpoint, allowing developers to manage models and interact with them without requiring detailed knowledge of the underlying server configuration.
- **llama.cpp** — A lightweight C++ inference server optimized for performance and resource efficiency. It is well suited for running large language models on devices with limited computational resources by using quantization techniques (e.g., GGUF format) to reduce memory footprint while maintaining acceptable accuracy.
- **OpenAI-compatible APIs** — Any server that implements the OpenAI chat format, typically over HTTP/REST. This allows integration with a wide range of LLM services, including commercial and open-source models that follow the standard OpenAI API specification.

## SQLite 3 `ship_computer.db`

The `ship_computer.db` file is a SQLite 3 database that stores structured information about the ship’s computer systems, components, operational state, maintenance history, and related technical documentation. It serves as the primary structured data source for the Spock application, especially for **Ask AI** and **Deep Dive** inquiries.

### Purpose

The database provides a reliable, queryable foundation for answering questions about the ship’s computer environment. Unlike unstructured text, the data in `ship_computer.db` is organized into tables and relationships, which allows the Spock application to perform precise lookups, joins, aggregations, and time-based filtering before sending relevant context to the LLM.

Typical data stored in `ship_computer.db` may include:

- Ship and computer identifiers
- Hardware specifications
- Software versions
- Component inventory
- Operational status
- Error logs
- Maintenance records
- Configuration snapshots
- User or system activity records
- Links to related documentation or knowledge-base entries

### Schema Overview

A typical `ship_computer.db` schema may contain tables such as:

| Table | Description |
|-------|-------------|
| `ships` | Core ship records, including ship ID, name, class, and status |
| `computers` | Computer systems associated with each ship |
| `components` | Hardware or software components installed on each computer |
| `status_events` | Time-stamped operational status changes |
| `error_logs` | Captured errors, warnings, and diagnostic messages |
| `maintenance_records` | Maintenance actions, repairs, and inspections |
| `documents` | References to manuals, guides, or technical notes |
| `document_chunks` | Chunked text segments used for retrieval and embedding |
| `embeddings` | Vector representations of document chunks, if stored in SQLite |

The exact schema may vary depending on the deployment, but the key design principle is that `ship_computer.db` stores **structured, relational data** that can be queried deterministically before being used to inform LLM responses.

### Ask AI Interaction

**Ask AI** is intended for direct, conversational questions about the ship’s computer systems. When a user submits an Ask AI request, the Spock application typically follows this flow:

1. **Receive the user question**
   - Example: “What is the current status of the navigation computer?”

2. **Interpret the intent**
   - The application determines whether the question requires structured data, documentation, or both.

3. **Query `ship_computer.db`**
   - The application runs targeted SQL queries to retrieve relevant records.
   - For example, it may query the `computers` and `status_events` tables to find the latest status for a specific computer.

4. **Assemble context**
   - The retrieved rows are formatted into a concise context block.
   - This context may include identifiers, timestamps, status values, and related component information.

5. **Send the prompt to the LLM**
   - The LLM client sends the user question and the structured context to the selected model.
   - The model generates a natural-language answer grounded in the retrieved data.

6. **Return the response**
   - The Spock application presents the answer to the user, optionally including source references or data provenance.

This approach allows Ask AI to answer questions quickly while reducing the risk of hallucination, because the LLM is provided with concrete data from the database rather than relying solely on its internal knowledge.

### Deep Dive Interaction

**Deep Dive** is intended for more complex investigations that require multiple data sources, historical analysis, and cross-referencing. Compared with Ask AI, Deep Dive may involve:

- Multiple database queries
- Joins across several tables
- Time-range filtering
- Aggregation of logs or events
- Retrieval of related documentation
- Vector search over technical text
- Multi-step reasoning by the LLM

A typical Deep Dive flow is:

1. **Receive a complex question**
   - Example: “Why did the navigation computer experience repeated failures during the last 72 hours?”

2. **Break the question into subtasks**
   - Identify the relevant computer
   - Retrieve recent status events
   - Retrieve error logs
   - Retrieve maintenance records
   - Find related documentation or known issues

3. **Query `ship_computer.db`**
   - The application may execute several SQL statements, such as:
     - Find the computer by name or ID
     - Retrieve status events within a time window
     - Retrieve error logs associated with that computer
     - Retrieve recent maintenance actions
     - Join component data to identify affected subsystems

4. **Retrieve unstructured context**
   - If the question requires explanatory context, the application may also search the vector database for relevant documentation chunks.

5. **Combine structured and unstructured evidence**
   - The application merges database results with retrieved text snippets.
   - It may rank or prioritize the most relevant evidence before sending it to the LLM.

6. **Generate a detailed explanation**
   - The LLM produces a structured response that may include:
     - Summary of findings
     - Timeline of events
     - Likely causes
     - Recommended actions
     - References to logs, records, or documentation

Deep Dive is therefore a retrieval-augmented workflow in which `ship_computer.db` provides the factual backbone, while the LLM provides interpretation and synthesis.

### Data Flow

The interaction between `ship_computer.db` and the Spock application can be summarized as follows:

```text
User Question
    ↓
Spock Application
    ↓
Intent Detection / Query Planning
    ↓
SQLite 3 `ship_computer.db`
    ↓
Structured Context
    ↓
Optional Vector Search
    ↓
LLM Client
    ↓
Generated Answer
    ↓
User
```

In this flow, the database is not directly “talking” to the LLM. Instead, the Spock application acts as the orchestrator: it queries the database, formats the results, and supplies them as context to the LLM through the LLM client.

### Example Queries

The following examples illustrate the kinds of queries the Spock application may run against `ship_computer.db`.

#### Find a computer by name

```sql
SELECT id, ship_id, name, status
FROM computers
WHERE name = 'Navigation Computer';
```

#### Retrieve recent status events

```sql
SELECT timestamp, event_type, status, details
FROM status_events
WHERE computer_id = 12
  AND timestamp >= datetime('now', '-72 hours')
ORDER BY timestamp DESC;
```

#### Retrieve recent error logs

```sql
SELECT timestamp, severity, message, component_id
FROM error_logs
WHERE computer_id = 12
  AND timestamp >= datetime('now', '-72 hours')
ORDER BY timestamp DESC;
```

#### Retrieve related maintenance records

```sql
SELECT performed_at, technician, action, notes
FROM maintenance_records
WHERE computer_id = 12
ORDER BY performed_at DESC
LIMIT 10;
```

These queries provide the factual context that the LLM can use to answer user questions accurately.

## Embedding LLM and Vector Database

The Spock application may also use an **embedding LLM** and a **vector database** to support semantic search over unstructured or semi-structured text. This is especially useful for Deep Dive inquiries, where the answer may depend on manuals, troubleshooting guides, incident reports, or other technical documents that are not easily captured by simple SQL queries.

### Purpose

An embedding LLM converts text into numerical vectors, also called embeddings. These vectors represent the semantic meaning of the text in a high-dimensional space. Similar meanings produce similar vectors, which allows the application to find relevant passages by measuring vector similarity rather than relying only on keyword matching.

The vector database stores these embeddings and supports efficient similarity search. Together, the embedding LLM and vector database enable the Spock application to answer questions such as:

- “What are the recommended troubleshooting steps for a navigation computer timeout?”
- “Are there known issues with this component after firmware update 4.2?”
- “What does the maintenance manual say about thermal throttling on this system?”

### Ingestion Pipeline

Before text can be searched semantically, it must be processed and stored. A typical ingestion pipeline includes the following steps:

1. **Collect source documents**
   - Technical manuals
   - Maintenance guides
   - Error reference documents
   - Incident reports
   - Component datasheets
   - Operational procedures

2. **Chunk the text**
   - Long documents are split into smaller, meaningful segments.
   - Chunking helps improve retrieval precision and keeps context within the LLM’s token limits.

3. **Generate embeddings**
   - Each chunk is passed to the embedding LLM.
   - The model returns a vector representation of the chunk.

4. **Store metadata**
   - Alongside each vector, the application stores metadata such as:
     - Document ID
     - Chunk ID
     - Source title
     - Section heading
     - Page or paragraph location
     - Timestamp
     - Related ship or computer ID, if applicable

5. **Index the vectors**
   - The vector database indexes the embeddings for fast similarity search.

### Embedding Model

The embedding LLM is typically a separate model from the chat LLM used for answer generation. It is optimized for producing dense vector representations of text.

Key characteristics of an embedding model include:

- **Deterministic output** — The same input text should produce the same embedding under the same model version.
- **Semantic sensitivity** — Text with similar meaning should produce similar vectors.
- **High-dimensional output** — Embeddings may have hundreds or thousands of dimensions.
- **Model versioning** — Changing the embedding model may require re-embedding existing content.

The Spock application may use a local embedding model, a hosted embedding API, or another OpenAI-compatible embedding endpoint, depending on the deployment environment.

### Vector Storage

The vector database may be implemented in several ways:

- A dedicated vector database such as Chroma, Qdrant, Milvus, or Weaviate
- A SQLite-based vector extension such as `sqlite-vec`
- An in-memory vector index for smaller deployments
- A hybrid store where metadata remains in `ship_computer.db` while vectors are stored separately

If the vector store is separate from `ship_computer.db`, the Spock application must maintain consistent references between the two systems. For example, a vector record may include a `document_id` that maps back to a row in the `documents` table.

### Query Pipeline

When the Spock application needs semantic search, it follows a process similar to the following:

1. **Receive the user question**
   - Example: “What should I check if the navigation computer reports intermittent timeouts?”

2. **Embed the query**
   - The application sends the question to the embedding LLM.
   - The model returns a query vector.

3. **Search the vector database**
   - The vector database finds the most similar stored embeddings.
   - The application retrieves the corresponding text chunks and metadata.

4. **Filter by metadata**
   - The application may filter results by:
     - Ship ID
     - Computer ID
     - Document type
     - Time range
     - Relevance score

5. **Rank and select context**
   - The application selects the most relevant chunks.
   - It may combine vector similarity with keyword matching or metadata filters.

6. **Send context to the chat LLM**
   - The retrieved chunks are included in the prompt.
   - The chat LLM generates an answer grounded in the retrieved evidence.

### Hybrid Search

In many cases, the best results come from combining structured search with semantic search. This is known as **hybrid search**.

For example, the Spock application may:

- Use SQL to find the correct computer and time range
- Use vector search to find relevant troubleshooting documentation
- Combine both result sets into a single context block

This approach is more robust than using either method alone because:

- SQL provides precise, deterministic filtering
- Vector search provides semantic flexibility
- The LLM can synthesize both structured and unstructured evidence

### Context Assembly

Before sending the prompt to the LLM, the Spock application assembles a context block that may include:

- User question
- Relevant database rows
- Retrieved document chunks
- Metadata such as timestamps and source references
- Instructions for the LLM to answer only from the provided context

A simplified prompt structure may look like this:

```text
You are an assistant for the Spock ship computer system.
Answer the user's question using only the provided context.
If the answer is not present in the context, say that the information is unavailable.

Context:
- Computer: Navigation Computer
- Status: Degraded
- Recent Error: Timeout detected in navigation service
- Document Chunk: "If navigation timeouts occur, verify network latency, firmware version, and thermal status."

User Question:
What should I check if the navigation computer reports intermittent timeouts?
```

This structure helps ensure that the LLM remains grounded in the retrieved data and documentation.

### Failure Handling

Because the embedding and vector search pipeline depends on multiple components, the Spock application should handle failures gracefully.

Common failure modes include:

- Embedding model unavailable
- Vector database unreachable
- Missing or stale embeddings
- Low-relevance search results
- Mismatch between document metadata and database records

Recommended handling strategies include:

- Fall back to structured database queries if vector search fails
- Return a clear message if no relevant context is found
- Log retrieval failures for diagnostics
- Re-embed content after model or schema changes
- Validate metadata consistency between `ship_computer.db` and the vector store

### Relationship Between `ship_computer.db` and the Vector Database

The two data stores serve complementary roles:

| Data Store | Role |
|------------|------|
| `ship_computer.db` | Stores structured, relational data about ships, computers, components, status, logs, and maintenance |
| Vector database | Stores semantic embeddings of unstructured or semi-structured text for similarity search |

The Spock application uses both when appropriate:

- Use `ship_computer.db` for precise, factual queries
- Use the vector database for semantic retrieval over documents and guides
- Use the LLM to interpret and synthesize the combined context

This separation allows the application to maintain accurate structured data while still benefiting from flexible, meaning-based search over technical content.
## Database Architecture

The database layer provides persistent storage for LLM interactions. It uses SQLite, with the primary database file named `ship_computer.db`. This enables the Spock application to retain query history, associated context, and generated results for later retrieval, auditing, or review.

### Database Schema Overview

| Table | Purpose |
|-------|---------|
| `queries` | Stores submitted prompts or question text, session information, feature type, and request metadata |
| `context` | Stores contextual material supplied to the LLM for a query, including source identifiers, text snippets, and relevance scores |
| `results` | Stores generated model responses, performance metrics, token usage, model version, and execution status |

### Interaction with Spock Application

The Spock application uses this client as its integration point for AI-assisted features such as Ask AI and Deep Dive. For each request, Spock supplies a user prompt and any relevant context; the LLM client forwards that information to the selected backend and records the interaction in `ship_computer.db`. The stored records include entries in `queries`, `context`, and `results`, which support traceability of what was asked, what context was provided, and what response was returned.

The client exposes lightweight CRUD methods that Spock calls synchronously after each inference cycle. A typical write sequence is:

1. Insert a `queries` record to capture the user prompt and request metadata.
2. Insert one or more `context` records to capture the sources, chunks, and relevance scores used for the request.
3. Insert a `results` record to capture the model response, latency, token usage, and execution status.
4. Commit the transaction. If any step fails, the transaction is rolled back to prevent partial writes.

This design keeps the Spock application responsible for user experience and workflow orchestration, while the database client remains responsible for durable logging and retrieval of AI interactions.

### SQLite 3 Database: `ship_computer.db` Architecture

`ship_computer.db` is a local, file-based SQLite 3 relational database designed for low-latency, zero-configuration persistence. It operates in WAL journal mode to improve data integrity and concurrency during read/write operations from the Spock application. The schema is normalized to separate user intent, retrieved context, and model outputs, enabling efficient querying and historical analysis.

- **`queries` Table**: Acts as the primary ledger for user interactions. Each record contains a unique identifier, timestamp, session ID, raw user prompt, and metadata tags such as feature flag, user role, and request source. This table serves as the anchor for all downstream logging.
- **`context` Table**: Stores the semantic context injected into the LLM prompt. Records include a foreign key linking to the parent `queries` entry, source identifiers such as document ID, URL, or knowledge base path, raw text snippets, chunk identifiers, and relevance scores returned by the vector search engine. This enables developers to audit which documents influenced a specific response.
- **`results` Table**: Captures the LLM's output along with performance metrics. Fields include the generated response text, token usage for input and output, latency, model version, and execution status such as success, timeout, or error. This facilitates cost tracking, performance monitoring, and response caching.

All database operations are wrapped in transactional blocks to prevent partial writes during network timeouts or backend failures. The client exposes lightweight CRUD methods that Spock calls synchronously after each inference cycle.

#### Reference Schema

The following schema illustrates the core relationships and fields used by the Spock application.

```sql
CREATE TABLE queries (
    query_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    feature TEXT NOT NULL CHECK (feature IN ('ask_ai', 'deep_dive', 'other')),
    user_role TEXT,
    prompt TEXT NOT NULL,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE context (
    context_id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id INTEGER NOT NULL REFERENCES queries(query_id) ON DELETE CASCADE,
    source_type TEXT,
    source_id TEXT,
    source_path TEXT,
    chunk_id TEXT,
    text_snippet TEXT,
    relevance_score REAL,
    embedding_id TEXT,
    retrieved_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE results (
    result_id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id INTEGER NOT NULL REFERENCES queries(query_id) ON DELETE CASCADE,
    response_text TEXT,
    model_name TEXT,
    model_version TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    latency_ms INTEGER,
    status TEXT NOT NULL CHECK (status IN ('success', 'timeout', 'error', 'cancelled')),
    error_message TEXT,
    cache_key TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_queries_session ON queries(session_id, created_at);
CREATE INDEX idx_context_query ON context(query_id);
CREATE INDEX idx_results_query ON results(query_id);
```

The `queries` table is the parent record for a single user request. The `context` table may contain multiple rows for one query, especially in Deep Dive workflows where several retrieved chunks are used. The `results` table stores the final response and operational metrics for that query.

### Spock Application Integration: Ask AI and Deep Dive Workflows

The Spock application leverages the LLM client and `ship_computer.db` to power two distinct AI inquiry modes, each with different data flow and logging requirements:

- **Ask AI**: Designed for direct, conversational Q&A. When a user submits a prompt, Spock routes it directly to the LLM client with minimal or no external context. The client forwards the request to the configured backend, receives the response, and logs a single entry across the three database tables. This workflow prioritizes speed and simplicity, making it ideal for general knowledge questions, code snippets, or quick clarifications.
- **Deep Dive**: Engineered for complex, research-oriented inquiries requiring domain-specific knowledge. Spock initiates a Retrieval-Augmented Generation (RAG) pipeline. The user prompt is first processed to extract semantic intent, triggering a vector similarity search. Retrieved documents are chunked, ranked, and injected into the system prompt as structured context. The LLM client then orchestrates the multi-step inference, logging each context chunk in the `context` table and the final synthesized response in the `results` table. This workflow ensures traceability, allowing users to click through source references and verify how the model constructed its answer.

Both workflows share the same underlying client abstraction, but Deep Dive dynamically adjusts timeout thresholds, token limits, and retry logic to accommodate heavier computational loads.

#### Ask AI Logging Pattern

In Ask AI, the database write is typically compact:

- One `queries` row records the user's prompt.
- Zero or more `context` rows record any optional context supplied by the user or application.
- One `results` row records the model response and execution metadata.

Because Ask AI is optimized for low latency, Spock may skip vector search entirely or use a lightweight context source when appropriate.

#### Deep Dive Logging Pattern

In Deep Dive, the database write is more detailed:

- One `queries` row records the original research question.
- Multiple `context` rows record each retrieved chunk, source, relevance score, and embedding identifier.
- One `results` row records the synthesized answer, model version, token usage, latency, and status.

This pattern supports audit trails, source verification, and debugging of retrieval quality.

### Embedding LLM and Vector Database Integration

While the primary LLM client handles generative tasks, the Spock application relies on a separate **embedding LLM** and a **vector database** to power semantic search and context retrieval. These components operate in tandem to bridge the gap between unstructured data and the generative model.

#### Role of the Embedding LLM

The embedding LLM is a specialized model that converts text into dense numerical vectors, also called embeddings. Unlike the primary generative LLM, the embedding LLM does not produce natural-language answers. Instead, it produces fixed-length vector representations that capture semantic meaning. Texts with similar meaning are mapped to nearby points in vector space, enabling similarity search.

Spock uses the embedding LLM in two main phases:

1. **Indexing**: When documents, knowledge-base entries, or other source material are added to Spock, the application chunks the text and sends each chunk to the embedding LLM. The resulting vectors are stored in the vector database along with metadata such as document ID, chunk ID, source path, permissions, and timestamp.
2. **Querying**: When a user submits a Deep Dive request, Spock sends the user prompt to the same embedding LLM to create a query vector. This vector is then compared against stored vectors to find the most semantically relevant chunks.

Using the same embedding model for indexing and querying is important because vectors from different models are not guaranteed to be comparable. If Spock changes the embedding model, it should reindex existing content or maintain versioned embeddings to preserve search accuracy.

#### Role of the Vector Database

The vector database stores embeddings and their associated metadata. It is optimized for high-dimensional nearest-neighbor search, allowing Spock to quickly identify the most relevant chunks from a large corpus.

For each stored vector, the vector database typically retains:

- The embedding vector itself.
- A unique chunk or document identifier.
- Source metadata such as document ID, URL, file path, or knowledge-base location.
- Access-control metadata such as user role, group, or permission scope.
- Timestamps and version information.
- Optional relevance or confidence scores computed during retrieval.

During a Deep Dive request, the vector database performs a similarity search using the query embedding. It returns the top-k most relevant chunks, ranked by similarity score. Spock can then filter these results by permissions, freshness, or source type before injecting them into the LLM prompt.

#### How Spock Uses the Embedding LLM and Vector Database Together

The full retrieval flow for a Deep Dive inquiry is:

1. **Prompt preparation**: Spock receives the user's question and prepares it for semantic search.
2. **Query embedding**: Spock sends the prompt to the embedding LLM and receives a query vector.
3. **Vector search**: Spock queries the vector database for the nearest stored vectors.
4. **Filtering and ranking**: Spock applies metadata filters, permission checks, and relevance ranking to select the best context chunks.
5. **Context assembly**: Spock formats the selected chunks into a structured prompt context, including source references for traceability.
6. **Generation**: Spock sends the prompt and context to the primary LLM through the LLM client.
7. **Logging**: The LLM client records the query, retrieved context, and final response in `ship_computer.db`.

This separation of concerns allows Spock to use the embedding LLM for semantic matching, the vector database for fast retrieval, and the primary LLM for answer synthesis. It also makes the system easier to debug: if a Deep Dive answer is incorrect, developers can inspect the retrieved chunks in the `context` table and determine whether the issue was retrieval, ranking, prompt construction, or model generation.

#### Ask AI vs. Deep Dive Use of Embeddings

Ask AI may not require vector search when the question can be answered from the model's general knowledge or from a small, explicitly supplied context. In that case, Spock may bypass the embedding LLM and vector database entirely, or use them only for optional lightweight retrieval.

Deep Dive relies more heavily on the embedding LLM and vector database because it is designed to answer questions that require access to specific documents, internal knowledge, or domain-specific material. The vector search step is what allows Deep Dive to ground its responses in relevant source content rather than relying solely on the generative model's prior knowledge.
1. **Embedding Generation**: When a user submits a query—particularly in Deep Dive mode—Spock passes the prompt to a dedicated embedding model (for example, `text-embedding-3-small` or a local equivalent). The model converts the text into a high-dimensional numerical vector that captures semantic meaning rather than literal keyword matches. This vector is used as a search key for related content.

2. **Vector Similarity Search**: Spock sends the generated query vector to the vector database, which indexes pre-embedded documents, knowledge-base articles, and system logs. Using similarity measures such as cosine similarity or inner-product distance, the vector database retrieves the top-N most relevant passages. Each result includes a similarity score and metadata pointers that identify the source document, section, timestamp, or log entry.

3. **Context Assembly & Injection**: Spock aggregates the retrieved passages, trims or ranks them to fit the LLM's context window, and formats them into a structured prompt template. The LLM client then appends this context to the system message before forwarding the complete payload to the inference backend. This allows the generative model to answer using grounded, relevant material rather than relying only on its internal knowledge.

4. **Logging & Traceability**: The vector database does not store conversation history. Instead, the LLM client writes the retrieved context snippets, their source IDs, similarity scores, and related metadata into the `context` table in `ship_computer.db`. This decouples real-time vector search from persistent relational logging, ensuring that the application maintains a complete audit trail without bloating the vector index.

This architecture ensures that the generative LLM remains focused on reasoning and synthesis, while the embedding model and vector database handle precise, scalable information retrieval. The separation of concerns also allows Spock to swap embedding models or vector backends independently without disrupting the core inference pipeline.

## SQLite 3 `ship_computer.db`

`ship_computer.db` is a local SQLite 3 database used by the Spock application for durable, transactional storage of application state and inquiry history. It is separate from the vector database: SQLite stores structured records, while the vector database stores high-dimensional embeddings and performs similarity search.

For **Ask AI** inquiries, Spock uses `ship_computer.db` to record the user's question, the selected mode, the model response, the retrieved context, and any relevant metadata. This gives the application a persistent record of what was asked, what context was used, and what answer was produced.

For **Deep Dive** inquiries, Spock uses the same database to store richer audit information, including multiple retrieval steps, source identifiers, similarity scores, timestamps, and the final synthesized answer. This supports traceability, debugging, and later review of how the application arrived at a detailed response.

Typical responsibilities of `ship_computer.db` include:

| Area | Purpose |
|---|---|
| `context` | Stores retrieved passages, source IDs, similarity scores, and context metadata used for an inquiry. |
| Conversation records | Stores user prompts, assistant responses, mode, and timestamps. |
| Settings and state | Stores user preferences, active model configuration, and application state. |
| Audit trail | Provides a durable record of Ask AI and Deep Dive activity for review and debugging. |

The database is not used as the primary vector index. Embeddings and similarity search remain in the vector database, while SQLite provides reliable local persistence and relational querying.

## Embedding LLM and Vector Database

Spock uses an embedding model to translate natural-language text into numerical vectors. These vectors represent semantic meaning, so similar concepts are close together in vector space. The vector database stores these vectors alongside metadata and uses them to find relevant content quickly.

### How Spock uses the embedding LLM

1. Spock receives a user query from Ask AI or Deep Dive.
2. It sends the query to the embedding model.
3. The embedding model returns a vector representation of the query.
4. Spock uses that vector to search the vector database for semantically related passages.

The embedding model is not responsible for generating the final answer. Its role is to create a searchable representation of the query so that Spock can retrieve relevant context.

### How Spock uses the vector database

1. The vector database contains pre-embedded documents, knowledge-base articles, logs, and other indexed content.
2. Spock submits the query vector to the vector database.
3. The vector database compares the query vector against stored vectors using a similarity metric.
4. It returns the top-N most relevant passages, each with a similarity score and metadata.
5. Spock uses those passages to build the context for the generative LLM.

### Ask AI versus Deep Dive

In **Ask AI**, Spock typically performs a focused retrieval step: it embeds the question, retrieves a small set of relevant passages, and asks the generative LLM to answer directly.

In **Deep Dive**, Spock may perform broader or iterative retrieval: it can embed multiple query variants, retrieve more passages, rank or filter results, and assemble a larger context before asking the generative LLM to synthesize a detailed answer. In both cases, the final answer is generated by the LLM, while the embedding model and vector database provide the relevant supporting material.
## Database Architecture

The `ship_computer.db` SQLite 3 database serves as the persistent storage layer for the Spock application, specifically managing data related to AI inquiries such as "Ask AI" and "Deep Dive". This database stores context, query history, and generated insights locally, eliminating reliance on external cloud services for state management and ensuring data sovereignty.

### Database Schema Overview

The `ship_computer.db` file is optimized for the high-frequency read/write operations required by the LLM client and Spock application. Key tables include:

- **`queries`**: Stores incoming prompts and metadata, including timestamps, user/session IDs, request type (`ask_ai` or `deep_dive`), execution status, and correlation identifiers. This table provides a complete audit trail for every AI interaction and enables precise tracking of request lifecycles.
- **`context`**: Maintains session history and retrieval context used for multi-turn conversations. It stores conversation turns, referenced data points, vector search results, and scope boundaries required to reconstruct the prompt environment accurately. Each entry is linked to a specific session ID to prevent context bleeding between independent inquiries.
- **`results`**: Caches generated responses from LLM backends to prevent redundant inference calls. Cached results support response replay, debugging, and a consistent user experience when identical or highly similar requests are repeated. The table also stores token usage metrics and latency data for performance monitoring.
- **`vector_metadata`**: Acts as a relational bridge between the vector database and SQLite. It maps vector IDs to source documents, conversation threads, and access permissions, ensuring that semantic search results can be traced back to their origin within the relational schema.

### Interaction with Spock Application

The Spock application orchestrates the data flow between the user interface, the LLM client, and `ship_computer.db`. When a user initiates an inquiry, the following workflows execute:

1. **Ask AI**: The Spock application first queries the `context` table to retrieve relevant session history and previously resolved references. This enriched context is appended to the user's prompt before transmission to the LLM client. The resulting response is logged in the `results` table, and the updated conversation state is persisted back to `context`. If the query matches a previously cached prompt within a defined similarity threshold, the system bypasses the LLM and serves the cached result directly.
2. **Deep Dive**: For complex, multi-step analysis, the system breaks down the inquiry into discrete reasoning stages. Intermediate steps, tool outputs, and chain-of-thought traces are written to the `queries` and `context` tables with incremental status flags. This granular logging allows users to inspect the AI's decision-making process, verify data sources, and resume interrupted analyses without losing state. Each reasoning step is tagged with a parent-child correlation ID to reconstruct the full analytical tree.

The LLM client interacts with this database exclusively through the Spock application's internal API. This abstraction ensures that all inference requests are logged, stateful sessions survive application restarts, and data integrity is maintained via SQLite's ACID compliance. Connection pooling and WAL (Write-Ahead Logging) mode are enabled to optimize concurrent read/write performance during active sessions.

### Local Storage and Recovery

Because `ship_computer.db` is a local SQLite 3 file, it provides an embedded, low-dependency storage solution ideal for single-user or workstation deployments. The Spock application treats this database as the authoritative source for AI interaction state. While generated model outputs depend on backend availability and caching policies, all session metadata, context windows, and user prompts remain locally accessible and recoverable. Automatic checkpointing and periodic vacuuming are scheduled to prevent database bloat and maintain query performance over extended usage periods.

### Embedding LLM and Vector Database Integration

The Spock application leverages a dedicated embedding LLM and an integrated vector database to enable semantic search and dynamic context retrieval. This subsystem operates alongside `ship_computer.db` to bridge raw user queries with relevant knowledge bases and conversation history.
- **Embedding Generation**: When a user submits a query, uploads a document, or initiates a session, the Spock application routes the text through a lightweight embedding LLM. This model converts natural language into high-dimensional numerical vectors that capture semantic meaning, intent, and contextual relationships rather than relying on exact keyword matches.
- **Vector Storage & Indexing**: Generated vectors are stored in a vector database optimized for similarity search. The index uses approximate nearest neighbor (ANN) algorithms to enable low-latency retrieval even as the corpus scales. Metadata linking each vector to its source document, conversation thread, or context window is persisted in `ship_computer.db` for traceability and access control.
- **Semantic Retrieval Workflow**: During an "Ask AI" or "Deep Dive" request, the user's prompt is first embedded. The vector database performs a similarity search against the indexed corpus, retrieving the most contextually relevant chunks. These retrieved segments are then recorded in the `context` table, ranked by relevance score, and formatted into the final prompt sent to the primary generative LLM.
- **State Management & Separation of Concerns**: The vector database handles high-speed similarity matching and memory-efficient indexing, while `ship_computer.db` maintains the relational mapping between vectors, sessions, and user metadata. This architecture ensures that semantic search remains performant without compromising the durability, query flexibility, and transactional safety of the relational database. Context windows are dynamically assembled by merging vector search results with relational session history, providing the LLM with both semantic relevance and conversational continuity.

## SQLite 3 `ship_computer.db`

`ship_computer.db` is the durable relational database used by the Spock application to manage application state, user context, document metadata, retrieval results, and audit information. It is built on SQLite 3 and is intended to provide ACID transactions, structured querying, and persistent storage for the parts of the system that require relational integrity.

The database does **not** perform vector similarity search. Instead, it stores the relational metadata needed to interpret, authorize, trace, and reuse the results returned by the vector database.

### Core Responsibilities

`ship_computer.db` is responsible for:

- Storing user, session, and conversation state.
- Tracking uploaded documents, source files, and derived text chunks.
- Mapping vector database identifiers back to application-level entities.
- Recording retrieval results for "Ask AI" and "Deep Dive" requests.
- Maintaining the `context` table used to assemble prompts for the generative LLM.
- Enforcing application-level access control and auditability.
- Preserving session history so that later requests can reference prior context.

### Representative Tables

The exact schema may vary by implementation, but a typical `ship_computer.db` design includes tables such as the following:

| Table | Purpose |
|---|---|
| `users` | Stores user identities, roles, and access permissions. |
| `sessions` | Stores conversation sessions, including session ID, user ID, creation time, and status. |
| `messages` | Stores user prompts, assistant responses, and message ordering. |
| `documents` | Stores uploaded or indexed source documents, including title, source, owner, and visibility. |
| `chunks` | Stores text chunks derived from documents, including chunk text, position, and document reference. |
| `vector_refs` | Maps application-level chunks to vector database identifiers and embedding metadata. |
| `context` | Stores retrieval results selected for a specific request, including relevance score and rank. |
| `audit_log` | Records access, retrieval, and generation events for traceability. |

### Key Relationships

The relational model connects the major entities in the system:

- A `user` owns or participates in one or more `sessions`.
- A `session` contains one or more `messages`.
- A `document` is split into one or more `chunks`.
- A `chunk` may have one or more `vector_refs`.
- A `vector_ref` links a chunk to a vector stored in the external vector database.
- A `context` row records that a particular chunk was selected for a particular request.

This structure allows Spock to answer questions such as:

- Which user made this request?
- Which session did this request belong to?
- Which document or chunk was used as context?
- Which vector database identifier represented that chunk?
- What relevance score was returned?
- When was the context assembled?
- Which LLM response was generated from that context?

## Interaction with Ask AI and Deep Dive

### Ask AI Workflow

"Ask AI" is typically a single-turn or lightweight multi-turn semantic retrieval workflow. The Spock application uses `ship_computer.db` to manage the surrounding state while the vector database performs similarity search.

A typical Ask AI sequence is:

1. The user submits a prompt.
2. Spock loads or creates the relevant session in `ship_computer.db`.
3. Spock records the user message in the `messages` table.
4. Spock sends the prompt to the embedding LLM.
5. The embedding LLM returns a query vector.
6. Spock sends the query vector to the vector database.
7. The vector database returns candidate vector identifiers and similarity scores.
8. Spock uses `vector_refs` to resolve those identifiers back to application-level chunks.
9. Spock checks permissions and document visibility using `users`, `documents`, and related tables.
10. Spock inserts the selected chunks into the `context` table with their relevance scores and ranks.
11. Spock assembles the final prompt using the session history and retrieved context.
12. Spock sends the prompt to the primary generative LLM.
13. Spock stores the assistant response in `messages`.
14. Spock records audit information in `audit_log`.

In this workflow, `ship_computer.db` provides the durable record of what was asked, what was retrieved, what was authorized, and what was generated.

### Deep Dive Workflow

"Deep Dive" is a more iterative retrieval and synthesis workflow. It may involve multiple retrieval passes, follow-up subqueries, context expansion, and repeated prompt assembly.

A typical Deep Dive sequence is:

1. The user submits a complex question or research request.
2. Spock creates or loads a Deep Dive session in `ship_computer.db`.
3. Spock records the initial user message.
4. Spock embeds the initial prompt using the embedding LLM.
5. Spock performs an initial similarity search in the vector database.
6. Spock resolves the returned vector identifiers to chunks using `vector_refs`.
7. Spock filters the results using access control and document metadata.
8. Spock stores the first retrieval pass in the `context` table.
9. Spock may generate follow-up subqueries or refinement prompts.
10. Each subquery is embedded and searched again.
11. New retrieval results are merged, deduplicated, and re-ranked.
12. The updated context is persisted in `ship_computer.db`.
13. Spock assembles a richer prompt for the generative LLM.
14. The final answer, intermediate steps, and retrieved context are stored for traceability.

For Deep Dive, `ship_computer.db` is especially important because it preserves the multi-step reasoning path. It allows Spock to reconstruct which chunks were considered, which retrieval passes were performed, and how the final context was assembled.

## Embedding LLM and Vector Database

### Role of the Embedding LLM

The embedding LLM is a specialized model used to convert text into numerical vectors. Unlike the primary generative LLM, the embedding LLM is not expected to produce natural-language answers. Its purpose is to represent text in a mathematical space where semantically similar texts are located near one another.

The embedding LLM is used for:

- User prompts.
- Uploaded documents.
- Document chunks.
- Conversation history, when needed.
- Follow-up subqueries in Deep Dive workflows.

The resulting vectors capture semantic meaning rather than exact keyword overlap. For example, a query about "how to recover a failed deployment" may be semantically close to a document chunk discussing "rollback procedures after a bad release," even if the exact words differ.

### Role of the Vector Database

The vector database stores the numerical vectors produced by the embedding LLM. It is optimized for similarity search, meaning it can quickly find the vectors that are closest to a query vector.

The vector database is responsible for:

- Storing high-dimensional vectors.
- Maintaining an ANN index for fast similarity search.
- Returning the most relevant vector identifiers for a query.
- Providing similarity scores or distance metrics.
- Scaling to large corpora without requiring full linear scans.

The vector database is not the system of record for application state. It stores the searchable vector representation, while `ship_computer.db` stores the relational metadata needed to interpret and govern those vectors.

### How Spock Uses the Embedding LLM and Vector Database Together

Spock acts as the orchestration layer between the embedding LLM, the vector database, the generative LLM, and `ship_computer.db`.

The overall process is:

1. **Chunking**: Spock splits documents into manageable text chunks.
2. **Embedding**: Spock sends each chunk to the embedding LLM.
3. **Indexing**: Spock stores the resulting vectors in the vector database.
4. **Mapping**: Spock stores the relationship between chunks and vector identifiers in `ship_computer.db`.
5. **Query Embedding**: When a user asks a question, Spock embeds the user prompt.
6. **Similarity Search**: Spock queries the vector database with the prompt vector.
7. **Result Resolution**: Spock maps returned vector identifiers back to chunks.
8. **Authorization**: Spock verifies that the user is allowed to access the retrieved chunks.
9. **Context Assembly**: Spock stores and ranks the selected chunks in the `context` table.
10. **Generation**: Spock sends the assembled prompt to the primary generative LLM.
11. **Persistence**: Spock stores the response and retrieval metadata in `ship_computer.db`.

### Why the Embedding LLM and Vector Database Are Separate from SQLite

SQLite 3 is a relational database. It is well suited for structured data, transactions, joins, and durable application state. It is not optimized for high-dimensional vector similarity search.

The embedding LLM and vector database are therefore used for the semantic search layer, while `ship_computer.db` remains the authoritative store for:

- User identity.
- Session state.
- Document ownership.
- Chunk metadata.
- Retrieval history.
- Access control.
- Audit records.
- Prompt and response persistence.

This separation gives Spock a practical architecture: the vector database provides fast semantic retrieval, the embedding LLM provides semantic representation, and `ship_computer.db` provides durable, queryable, transactional application state.