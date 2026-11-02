# Ship Computer Database

The `ship_computer.db` SQLite 3 database serves as the persistent storage layer for the Spock application. It stores structured data required by the Ask AI and Deep Dive features, including inquiry metadata, query history, retrieval logs, session state, and audit information. The database integrates with the RAG API Server to ensure that user questions are answered using relevant context from the knowledge base, while maintaining a reliable, queryable record of all requests and system actions.

## Components

| Module | Role |
|--------|------|
| `ship_computer.db` | SQLite 3 database file that stores structured metadata, user inquiries, retrieval logs, session state, and application state required by Ask AI and Deep Dive workflows. |
| `spock_rag_adapter.bridge_host` | Adapter and host layer that connects client or UI requests to the RAG pipeline. It routes incoming requests to the appropriate handler, validates input, and returns responses in a standardized format. |
| `spock_rag_adapter.embedding_corpus` | Manages the document embedding pipeline, converting raw text into numerical representations, or embeddings. These vectors are used for semantic similarity calculations during retrieval. |
| `spock_rag_adapter.rag_host` | Contains the core RAG server logic, including query processing, context retrieval from the indexed corpus, response generation or assembly, and coordination with the SQLite database and vector store. |

## Endpoints

The following endpoints are provided by the RAG API Server. They operate on data managed through `ship_computer.db` and the associated vector store.

| Method | Path | Description |
|--------|-------------|-------------|
| `POST` | `/index` | Indexes documents into the vector store, enabling efficient semantic search. Used to add or update documents in the knowledge base. |
| `POST` | `/query` | Queries the knowledge base using a natural language question. The system retrieves relevant documents and generates an answer based on the retrieved context. |
| `GET` | `/health` | Performs a health check to verify that the API server is running and its core components are functioning correctly. |
| `POST` | `/db/initialize` | Initializes the SQLite database schema, creating the tables required for Ask AI and Deep Dive inquiries. |

## Core Concepts

To fully understand the functionality described above, it is helpful to define the underlying technical terms:

*   **SQLite 3:** A lightweight, serverless, and self-contained relational database engine that stores all data in a single file (`ship_computer.db`). It supports ACID properties—Atomicity, Consistency, Isolation, and Durability—ensuring data integrity during concurrent operations and Ask AI query processing.
*   **Vector Store:** A specialized storage mechanism optimized for storing and retrieving high-dimensional embeddings. It enables fast similarity searches by calculating distances between query vectors and document vectors, identifying contextually relevant content regardless of exact keyword matches.
*   **Semantic Search:** A retrieval methodology that prioritizes meaning over lexical matching. By leveraging embeddings and vector similarity metrics, it identifies documents that are conceptually aligned with a user's query, even when terminology differs.
*   **Ask AI Inquiries:** User requests processed through the RAG pipeline. The `ship_computer.db` database logs metadata for each inquiry, including timestamps, user identifiers, confidence scores, and response status, enabling audit trails, debugging, and performance analytics.
*   **Deep Dive Analysis:** An advanced feature that allows users to explore topics with greater granularity. It triggers iterative database queries to retrieve related documents, cross-reference findings within the knowledge base, and assemble comprehensive, multi-faceted responses.

## Database Architecture & Application Interaction

The `ship_computer.db` file acts as the relational backbone for the Spock application, specifically designed to support the operational and audit requirements of Ask AI and Deep Dive workflows. Unlike the vector store, which handles unstructured semantic data, SQLite 3 manages structured relational data through a normalized schema optimized for fast reads and writes.

For **Ask AI inquiries**, the database records a unique inquiry ID, timestamp, user session context, and the raw query string. As the RAG pipeline processes the request, intermediate results—such as retrieved document IDs, similarity scores, and LLM response tokens—are logged. This creates a complete audit trail that allows administrators to trace how a specific answer was constructed, verify retrieval accuracy, and monitor system latency.

For **Deep Dive inquiries**, the database handles more complex state management. Deep Dive sessions often involve multi-turn interactions and iterative context expansion. The SQLite database stores session state, tracks which documents have already been presented to the user, and logs cross-referencing operations. This prevents redundant retrievals, maintains conversation continuity, and ensures that expanded context is properly versioned and linked back to the original inquiry. All interactions are transactionally safe, leveraging SQLite's journaling mechanisms to prevent data corruption during high-throughput query processing.

## Embedding LLM and Vector Store Workflow

The Spock application uses an embedding LLM and a vector store together to perform semantic retrieval. In this context, the embedding LLM is the model responsible for converting text into numerical vector representations. It is distinct from any answer-generation LLM that may later use the retrieved context to compose a response.

When documents are added to the knowledge base, the Spock application processes them through the embedding pipeline. The document text is split into manageable chunks, and each chunk is passed to the embedding LLM. The embedding LLM produces a high-dimensional vector that represents the semantic meaning of that chunk. These vectors, along with associated metadata such as document ID, chunk ID, source, and timestamp, are stored in the vector store.

When a user submits an Ask AI or Deep Dive question, the Spock application sends the user's query to the embedding LLM. The embedding LLM converts the query into a vector using the same embedding space as the indexed documents. The vector store then performs a similarity search, comparing the query vector against the stored document vectors. The most similar vectors are returned, typically as a ranked set of top-k results.

The vector store is optimized for this type of search. It can quickly identify semantically related content even when the user's wording does not exactly match the wording in the source documents. For example, a query about “power loss during docking” may retrieve documents that discuss “energy interruption during berthing” because their embeddings are close in vector space.

The retrieved chunks are then used by the RAG pipeline as context. The Spock application may pass these chunks to an answer-generation model, or it may assemble a response directly from the retrieved content. In either case, the vector store provides the relevant semantic context, while the SQLite database records the structured details of the request, retrieval, and response.

## SQLite 3 Interaction Details

The `ship_computer.db` database is the authoritative structured record for Spock application activity. It does not replace the vector store; instead, it complements it by storing the relational and audit data needed to understand, debug, and manage Ask AI and Deep Dive behavior.

The database typically tracks the following categories of information:

*   **Inquiry records:** Each Ask AI or Deep Dive request is assigned a unique identifier. The database stores the user or session context, the original question, the request timestamp, and the final response status.
*   **Retrieval logs:** For each query, the database records the documents or chunks returned by the vector store, their similarity scores, and the order in which they were retrieved. This allows administrators to inspect whether the correct context was selected.
*   **Session state:** Deep Dive workflows may span multiple turns. The database stores the current state of the session, including which topics have been explored, which documents have already been shown, and which follow-up questions have been generated.
*   **Response artifacts:** The database may store the final answer, the model or pipeline version used, token counts, confidence indicators, and any errors that occurred during processing.
*   **Audit events:** Important system actions, such as indexing jobs, schema initialization, failed queries, or manual corrections, are recorded to support operational review and compliance.

During an Ask AI request, the Spock application uses SQLite 3 in a transactional workflow. First, it creates or updates an inquiry record. Next, it sends the query to the embedding LLM and vector store. After the vector store returns relevant chunks, the application logs the retrieval results. Finally, it stores the generated or assembled response and commits the transaction. If any step fails, the transaction can be rolled back, preventing partial or inconsistent records from being written.

During a Deep Dive request, the database plays a larger role. The application may create a session record, then perform multiple retrieval passes as the user explores the topic. Each pass is linked to the session and to the original inquiry. The database tracks which documents have already been used, which new documents were retrieved, and how the context expanded over time. This enables the Spock application to avoid repeating the same results, maintain a coherent narrative, and provide users with progressively deeper analysis.

The separation between SQLite 3 and the vector store is intentional. The vector store is optimized for fast semantic similarity search over high-dimensional embeddings. SQLite 3 is optimized for reliable structured queries, joins, filtering, and transactional integrity. Together, they allow Spock to answer questions using meaningful context while preserving a durable, inspectable record of every interaction.
## Embedding LLM & Vector Database Integration

The Spock application relies on a dedicated embedding LLM and a vector database to power its semantic retrieval capabilities. The embedding LLM is a specialized neural network model trained to map text into a high-dimensional vector space. When a document is ingested via the `/index` endpoint, the `spock_rag_adapter.embedding_corpus` module passes the text through this model, generating a fixed-length numerical array (the embedding) that captures the semantic meaning, context, and intent of the content.

These embeddings are stored in the vector database alongside lightweight metadata (for example, document source, chunk ID, and indexing timestamp). When a user submits a query through Ask AI or Deep Dive, the same embedding LLM processes the question to generate a query vector. The vector database then performs a nearest-neighbor search, calculating similarity metrics (such as cosine similarity or Euclidean distance) between the query vector and the stored document vectors.

This integration decouples semantic understanding from keyword matching. The embedding LLM ensures that conceptually related content is retrieved even when the vocabulary differs, while the vector database provides low-latency retrieval at scale. The top-ranked results are returned to the `rag_host`, which formats them into a context window for the generative LLM. This pipeline ensures that responses are grounded in indexed, semantically relevant knowledge-base content rather than relying solely on the LLM's pre-trained parameters.

## Detailed Explanation: How Spock Uses the Embedding LLM and Vector Database

The Spock application uses two distinct AI components for retrieval-augmented generation:

- **Embedding LLM:** Converts text into numerical vectors that represent semantic meaning.
- **Generative LLM:** Produces natural-language answers using the retrieved context.

The vector database is not responsible for generating answers. It is a search index that stores embeddings and supports fast similarity search. The embedding LLM is responsible for turning text into a form that the vector database can compare.

### Indexing Path

When Spock indexes content, it follows a retrieval-oriented workflow:

1. A document or text payload is submitted through the `/index` endpoint.
2. The `spock_rag_adapter.embedding_corpus` module prepares the text for embedding.
3. The text is split into manageable chunks so that retrieval can return precise, relevant passages rather than entire documents.
4. Each chunk is passed through the embedding LLM.
5. The resulting embedding vector is stored in the vector database with metadata such as source, chunk identifier, and timestamp.
6. Indexing activity is recorded in `ship_computer.db` for auditability and operational tracking.

This process creates a searchable semantic index. The vector database stores the numerical representations, while `ship_computer.db` stores the durable operational record of what was indexed and when.

### Query Path

When a user submits an Ask AI or Deep Dive inquiry, Spock uses the same embedding model to convert the user's question into a query vector. The vector database then searches for stored embeddings that are closest to that query vector.

The retrieval process works as follows:

1. The user's question is received by the Spock application.
2. The question is converted into an embedding vector using the embedding LLM.
3. The vector database performs a similarity search against the indexed embeddings.
4. The most relevant document chunks are returned with similarity scores.
5. The `rag_host` selects the strongest results and assembles them into a context window.
6. The generative LLM uses that context to produce a grounded response.
7. The inquiry, retrieval results, response, and audit data are persisted in `ship_computer.db`.

This design allows Spock to answer questions using indexed knowledge rather than relying only on the generative LLM's internal training data.

### Ask AI vs. Deep Dive

Both Ask AI and Deep Dive use the same core embedding and vector-search pipeline, but they differ in depth and audit behavior.

| Mode | Typical Behavior |
|---|---|
| **Ask AI** | Performs a focused retrieval pass and returns a concise, context-grounded answer. |
| **Deep Dive** | Performs a more extensive retrieval and analysis workflow, potentially using multiple retrieval passes, broader context, and more detailed audit logging. |

In both cases, the embedding LLM provides semantic matching, the vector database provides fast retrieval, and `ship_computer.db` provides the durable record of the inquiry and its supporting evidence.

## Data Flow

A typical request moves through the system as follows:

1. A client or user interface sends a request to `spock_rag_adapter.bridge_host`.
2. For indexing operations, raw text is processed by `spock_rag_adapter.embedding_corpus`, converted into embeddings via the embedding LLM, and stored in the vector store. Corresponding metadata and indexing logs are recorded in `ship_computer.db`.
3. For query operations, the user's question is converted into an embedding. The vector store performs a similarity search to retrieve the most relevant document chunks.
4. The retrieved context is passed to the generative LLM to assemble a response. Inquiry details, retrieval results, timestamps, similarity scores, and audit logs are persistently stored in `ship_computer.db` for compliance, debugging, and performance analysis.

## SQLite 3 `ship_computer.db` and Spock Inquiry Integration

`ship_computer.db` is a SQLite 3 database file used as the durable operational store for the Spock application. It is separate from the vector database. The vector database is optimized for high-dimensional similarity search, while SQLite is optimized for durable, transactional, queryable records.

For Ask AI and Deep Dive inquiries, `ship_computer.db` serves as the system of record for:

- Inquiry lifecycle state
- User prompts and system responses
- Retrieval evidence and similarity scores
- Indexing activity
- Audit events
- Performance and debugging data

This separation is important because the vector database is best suited for fast semantic search, while SQLite provides a reliable place to store the business and audit context around each request.

### Role in Ask AI and Deep Dive

When an Ask AI or Deep Dive request is received, the Spock application uses `ship_computer.db` to track the full lifecycle of the inquiry.

For **Ask AI**, the database typically records:

- The user's question
- The inquiry mode
- The retrieval results used to answer the question
- The final generated response
- Timestamps and latency information
- Any errors or status changes

For **Deep Dive**, the database records the same core information but may also capture a more detailed event trail, such as:

- Multiple retrieval passes
- Intermediate analysis steps
- Expanded context selections
- Additional audit events
- More detailed performance metrics

This makes `ship_computer.db` especially useful for compliance, troubleshooting, and post-hoc review of how Spock arrived at a particular answer.

### Representative Schema

The following schema is representative of the data the application needs to persist for Ask AI and Deep Dive workflows:

```sql
CREATE TABLE IF NOT EXISTS inquiries (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL CHECK (mode IN ('ask_ai', 'deep_dive')),
    session_id TEXT,
    user_id TEXT,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    response TEXT,
    model TEXT,
    retrieval_count INTEGER,
    latency_ms INTEGER
);

CREATE TABLE IF NOT EXISTS retrieval_results (
    id TEXT PRIMARY KEY,
    inquiry_id TEXT NOT NULL REFERENCES inquiries(id),
    rank INTEGER NOT NULL,
    chunk_id TEXT,
    source TEXT,
    similarity_score REAL,
    retrieved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inquiry_events (
    id TEXT PRIMARY KEY,
    inquiry_id TEXT NOT NULL REFERENCES inquiries(id),
    event_type TEXT NOT NULL,
    payload TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS index_jobs (
    id TEXT PRIMARY KEY,
    source TEXT,
    status TEXT NOT NULL,
    chunk_count INTEGER,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
```

### Interaction Sequence

The interaction between Spock, the vector database, and `ship_computer.db` typically follows this sequence:

1. `spock_rag_adapter.bridge_host` receives an Ask AI or Deep Dive request.
2. An inquiry record is created in `ship_computer.db`.
3. `spock_rag_adapter.embedding_corpus` converts the user's question into an embedding vector.
4. The vector database performs a similarity search and returns the most relevant chunks.
5. The retrieval results are written to `ship_computer.db`.
6. `rag_host` assembles the retrieved context and calls the generative LLM.
7. The final response is stored in `ship_computer.db`.
8. For Deep Dive, additional events and retrieval passes may be recorded as the workflow progresses.

### Why SQLite Is Used

SQLite is a practical choice for this role because it provides:

- Local, file-based storage with minimal operational overhead
- Strong transactional behavior for reliable writes
- Easy backup and inspection
- SQL-based querying for audit and debugging
- A simple deployment model that fits well with a Python application

## Usage

To start the RAG API server using a Windows PowerShell virtual environment:

```powershell
.venv\Scripts\python.exe -m _start_rag_api
```

Alternatively, you can start the server directly using the following Python code:

```python
from rag_api_server import app
import uvicorn

uvicorn.run(app, host="0.0.0.0", port=8080)
```

This launches the FastAPI server on port `8080`, making the RAG API available for use. The first command assumes that a virtual environment exists at `.venv` in the current directory. The second snippet requires `uvicorn` to be installed in your Python environment. For local development, you may prefer binding to `127.0.0.1` instead of `0.0.0.0` if the server does not need to accept connections from other network interfaces.

### Database Management

To manage `ship_computer.db` directly:

1. **Initialize:** Call the `/db/initialize` endpoint to ensure the database schema matches the application requirements.
2. **Backup:** Copy the `ship_computer.db` file to a secure location before making significant changes. If possible, stop the API server or disable active writes while copying the file to prevent file locking or corruption.
3. **Inspect:** Use SQLite command-line tools to inspect the database structure and contents:

```bash
sqlite3 ship_computer.db ".tables"
sqlite3 ship_computer.db "SELECT * FROM inquiries LIMIT 10;"
```