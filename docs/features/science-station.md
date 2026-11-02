The Science Station serves as the central interface for wiki querying and ship's log access, enabling efficient data retrieval and historical record review within the system.

| Module | Role |
|---|---|
| `ScienceStation.app` | Main science panel. Manages the primary user interface and core application logic. |
| `ScienceStation.ships_logs` | Ship's log viewer. Dedicated component for browsing, filtering, and displaying historical ship logs. |
| `ScienceStation.wiki_run` | Wiki agent runner. Agent module responsible for executing queries against external wiki databases. |

The Science Station relies on a local SQLite 3 database file named `ship_computer.db` to persist critical data and facilitate high-speed retrieval.

### SQLite 3 Database Architecture (`ship_computer.db`)

The `ship_computer.db` file functions as the persistent data layer for the Spock application, ensuring fast, reliable access to structured records and AI interaction metadata.

- **Schema & Data Storage:** The database contains normalized tables for ship logs, wiki query caches, session history, and embedding metadata. Primary keys and foreign keys enforce referential integrity, while indexed columns (e.g., timestamps, query hashes, log IDs) optimize read performance.
- **Ask AI Interaction:** When a user initiates an "Ask AI" request, the application first queries `ship_computer.db` for cached responses or relevant contextual snippets. If a cache miss occurs, the request is routed to the external LLM. Upon completion, the response, along with metadata (timestamp, confidence score, and associated vector IDs), is written to the database. This caching layer reduces redundant API calls and accelerates repeat queries.
- **Deep Dive Interaction:** The "Deep Dive" feature leverages the database to perform cross-referential analysis. It executes parameterized SQL queries against the ship's log tables to extract historical entries matching specific keywords, dates, or event types. These results are then joined with cached wiki data and stored as structured analysis reports. The database's ACID compliance guarantees that concurrent Deep Dive operations do not corrupt log integrity or produce inconsistent reads.
- **Maintenance & Performance:** The database is configured with WAL (Write-Ahead Logging) mode to support concurrent read/write operations without locking. Periodic vacuuming and index rebuilding are handled automatically by the application to prevent fragmentation and maintain sub-second query latency.

### Embedding LLM and Vector Database Workflow

The Spock application employs a hybrid AI architecture that separates semantic retrieval from content generation. This is achieved through a dedicated embedding model, a local vector database, and a generative LLM.

- **Text Embedding Process:** Unstructured data (ship logs, wiki articles, and user queries) is passed through a lightweight embedding model. This model converts text into high-dimensional numerical vectors that mathematically represent semantic meaning, rather than relying on exact keyword matches.
- **Vector Database Indexing:** Generated vectors are stored in a local vector database optimized for approximate nearest neighbor (ANN) search. The vector DB maintains an index that allows the application to rapidly compare incoming query vectors against thousands of stored document vectors, retrieving the most semantically relevant chunks in milliseconds.
- **Query Resolution Pipeline:**
  1. **Ingestion & Embedding:** User input is transformed into a query vector.
  2. **Similarity Search:** The vector DB performs a cosine similarity or dot-product search, returning the top-k most relevant log entries and wiki excerpts.
  3. **Context Assembly:** Retrieved chunks are formatted into a structured prompt context, preserving source attribution and metadata.
  4. **LLM Generation:** The generative LLM receives the original query alongside the assembled context and produces a synthesized, fact-grounded response.
- **State & Traceability:** While the vector database handles semantic matching, `ship_computer.db` tracks query history, user preferences, and embedding versioning. This separation ensures that AI interactions remain auditable, reproducible, and independent of external network dependencies.

On Windows PowerShell, use the local `.venv` Python environment to run the following command:

```powershell
.venv\Scripts\python.exe -m spock_wiki_adapter
```

## Prerequisites

Before running the Science Station, confirm that the following environment requirements are met:

1. **Python Environment:** Create and activate a Python virtual environment (`.venv`). This isolates project dependencies from the system Python installation and helps prevent dependency conflicts.
2. **Path Configuration:** The command paths shown below are specific to Windows PowerShell environments. Run the script from a terminal that matches the documented file structure, for example `.venv\Scripts\python.exe`.

### Virtual environment setup (Windows)

If you need to create or refresh the virtual environment in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Then install project dependencies if a requirements file is present:

```powershell
pip install -r requirements.txt
```

This step ensures that `spock_wiki_adapter` and its required packages are available inside the isolated environment.

### Path notes

- On Windows PowerShell, use backslashes (`\`) in relative paths.
- The interpreter path `.venv\Scripts\python.exe` points to the Python executable inside the project virtual environment.
- If you activate the virtual environment first, you can usually run `python -m spock_wiki_adapter` instead of using the full interpreter path.


## Usage

To start the Science Station, run the following command in PowerShell:

```powershell
.venv\Scripts\python.exe -m spock_wiki_adapter
```

This command invokes the `spock_wiki_adapter` module, which serves as the entry point for initializing the Science Station application. The `-m` flag tells Python to execute a package or module by name rather than running a standalone script file.

Ensure that the Python virtual environment (`.venv`) is properly set up and activated before running this command to avoid dependency errors. If you are not using an activated shell, use the full path shown above so PowerShell resolves the correct interpreter.

### Cross-platform note

On macOS or Linux shells, the equivalent command typically uses forward slashes:

```bash
.venv/bin/python -m spock_wiki_adapter
```

Use this form only if your project structure and virtual environment layout match that platform convention.

## SQLite 3 `ship_computer.db`

`ship_computer.db` is the local SQLite 3 database used by the Spock application as the primary structured store for Science Station content. It is a single-file database, which makes it easy to bundle, inspect, and version alongside the application without requiring a separate database server.

### Purpose

The database provides durable, queryable storage for the information that Ask AI and Deep Dive need to ground their responses. It typically stores:

- Wiki or article records, including titles, slugs, source URLs, and revision metadata.
- Chunked text segments that can be retrieved as context for language-model prompts.
- Metadata used for filtering, such as tags, categories, dates, authorship, and content type.
- Conversation history, user questions, generated answers, and citation references.
- Retrieval caches or query logs that help improve performance and auditability.
- Foreign-key relationships that allow Deep Dive to traverse related records.

### Typical contents

A representative schema may include tables such as:

```sql
CREATE TABLE wiki_pages (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    source_url TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE wiki_chunks (
    id INTEGER PRIMARY KEY,
    page_id INTEGER NOT NULL REFERENCES wiki_pages(id),
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER,
    embedding_id TEXT
);

CREATE TABLE conversations (
    id INTEGER PRIMARY KEY,
    user_id TEXT,
    created_at TEXT,
    mode TEXT CHECK (mode IN ('ask_ai', 'deep_dive'))
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT
);

CREATE TABLE citations (
    id INTEGER PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES messages(id),
    chunk_id INTEGER NOT NULL REFERENCES wiki_chunks(id),
    relevance_score REAL
);
```

The exact schema may vary, but the important architectural point is that SQLite holds the authoritative text, metadata, and relational links, while the vector database holds the numeric embeddings used for semantic search.

### How Spock interacts with the database

The `spock_wiki_adapter` module acts as the bridge between the Spock application and `ship_computer.db`. During startup, it typically:

1. Opens the SQLite database file.
2. Validates or migrates the schema.
3. Loads configuration for Ask AI and Deep Dive.
4. Exposes repository functions for reading pages, chunks, conversations, and citations.
5. Coordinates with the embedding service and vector database when semantic retrieval is required.

For Ask AI, Spock uses the database mainly to fetch precise context after semantic search has identified relevant chunks. For Deep Dive, Spock uses the database more extensively to filter, join, paginate, and trace relationships across multiple records.

### Ask AI interaction

Ask AI is a retrieval-augmented question-answering feature. A typical flow is:

1. The user submits a question.
2. Spock stores the question in the conversations and messages tables.
3. The embedding model converts the question into a vector.
4. The vector database returns the most semantically similar chunks.
5. Spock uses the returned chunk identifiers to load the full text and metadata from `ship_computer.db`.
6. The prompt builder combines the question, retrieved context, and citation metadata.
7. The answer-generating language model produces a response.
8. Spock stores the answer and the citations used to support it.

This design keeps the answer grounded in the local wiki content and makes it possible to show users which records informed the response.

### Deep Dive interaction

Deep Dive is a longer, multi-step investigation mode. It uses the same core components as Ask AI, but with a broader and more structured retrieval strategy.

Compared with Ask AI, Deep Dive may:

- Run multiple embedding queries to cover different aspects of the user's request.
- Apply structured filters from SQLite, such as date range, category, source type, or tag.
- Follow foreign-key relationships to find related pages, chunks, or entities.
- Build an evidence set from several retrieval passes.
- Store intermediate steps, plans, and citations so the user can review the reasoning path.
- Use cached results from `ship_computer.db` to avoid repeated expensive retrieval or embedding calls.

In this mode, SQLite is not merely a lookup table. It is the relational backbone that lets Spock move from "find similar text" to "assemble a coherent, citable investigation."

## Embedding LLM and vector database

### What the embedding LLM does

The embedding LLM, or embedding model, converts text into a numeric vector. Each vector represents the semantic meaning of the text in a high-dimensional space. Text with similar meaning is placed closer together in that space.

This is different from the answer-generating language model. The embedding model does not write the final response. Its job is to make text searchable by meaning rather than by exact keyword match.

### How Spock uses the embedding model

Spock uses the embedding model in two main phases.

#### Indexing phase

When wiki content is added or updated:

1. Spock splits the content into manageable chunks.
2. Each chunk is stored in `ship_computer.db`.
3. The embedding model converts each chunk into a vector.
4. The vector is stored in the vector database.
5. A link between the chunk and its vector is maintained, often through an `embedding_id` or similar identifier.

#### Query phase

When a user asks a question:

1. Spock embeds the user's question using the same embedding model.
2. The vector database searches for the nearest vectors.
3. The top matching chunk identifiers are returned.
4. Spock retrieves the corresponding text and metadata from `ship_computer.db`.
5. The retrieved context is used to build the prompt for the answer-generating model.

Using the same embedding model for indexing and querying is important because it ensures that both content and questions are represented in the same semantic space.

### Role of the vector database

The vector database stores the numeric embeddings and provides fast similarity search. It is optimized for approximate nearest-neighbor queries, which are well suited to semantic search over large text collections.

The vector database complements SQLite:

| Component | Primary responsibility |
|---|---|
| SQLite `ship_computer.db` | Authoritative text, metadata, relationships, conversation history, and citations |
| Vector database | Semantic similarity search over embedded text chunks |
| Embedding model | Converts text into vectors for both indexing and querying |
| Answer-generating model | Produces the final user-facing response from the retrieved context |

### Ask AI versus Deep Dive

Ask AI typically performs a single semantic search pass. It embeds the question, retrieves a small number of relevant chunks, and asks the language model to answer directly from that context.

Deep Dive performs a more complex retrieval process. It may combine semantic search with structured database queries, repeated retrieval, relationship traversal, and evidence aggregation. The result is a more detailed response that can cite multiple sources and explain how the evidence was assembled.

### Why both SQLite and a vector database are needed

Keyword search and semantic search solve different problems. SQLite can answer questions such as:

- Which chunks belong to a specific page?
- Which records were updated within a date range?
- Which chunks are tagged with a particular category?
- Which previous messages cited a given source?

The vector database can answer questions such as:

- Which chunks are semantically similar to this question?
- Which passages discuss a concept even if they do not use the exact same words?
- Which content is conceptually related to the user's request?

By combining both, Spock can retrieve relevant content efficiently while preserving the structured context needed for accurate, citable, and auditable responses.