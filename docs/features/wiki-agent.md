# Wiki Agent

The Wiki Agent is a tool designed to crawl, index, and query local or remote wiki content. It provides a single entry point for scanning configured wiki sources, extracting text, storing structured results in SQLite, and supporting application queries such as Ask AI and Deep Dive workflows.

## Components

| Module | Role |
|--------|------|
| `wiki_agent` | Main agent logic; orchestrates crawling, indexing, extraction, and query execution. |
| `wiki_agent_status` | Status tracking; records progress, errors, and completion state for ongoing operations. |
| `wiki_maintenance` | Maintenance operations; handles cleanup, database health checks, vacuuming, and integrity validation. |
| `spock_wiki_adapter.wiki_run` | Wiki runner entry point; starts the agent workflow when the adapter module is executed. |
| `spock_wiki_adapter.scan_roots` | Root directory scanner; discovers configured wiki source roots and prepares them for indexing. |

The components are organized so that scanning, execution, status tracking, and maintenance can be tested or invoked independently while still working together as a single agent workflow.

## Usage

To run the Wiki Agent, use the following command in PowerShell:

```powershell
.venv\Scripts\python.exe -m spock_wiki_adapter
```

This command executes the Wiki Agent using the Python interpreter located in the `.venv\Scripts` directory. The `-m` flag tells Python to run the `spock_wiki_adapter` module as a script. Run this command from the project root or any directory where the `.venv` virtual environment is available.

**Dependency Requirements:**  
Scanning requires the full dependency tier, which is installed during the Bringup process (Step 2, Phase B). If only the Phase A UI tier is installed, the agent will report missing packages and abort the scan rather than proceeding. This behavior prevents partial indexes from being created when required extraction or database dependencies are unavailable.

## Optional: Image OCR

Text embedded within images — including standalone image files, images embedded in PDFs, and images in HTML — is extracted only if Optical Character Recognition (OCR) support is enabled. This feature is opt-in because it requires both a native binary and a Python package:

```powershell
winget install UB-Mannheim.TesseractOCR
.venv\Scripts\python.exe -m pip install -r requirements-ocr.txt
```

**Configuration:**  
By default, the extractor searches for `C:\Program Files\Tesseract-OCR\tesseract.exe`. You can override this path by setting the `TESSERACT_CMD` environment variable to point to a different location. If OCR is not installed or configured, scans will still complete successfully; image text will be skipped, and a log message explaining the omission will appear once per run.


## Database Architecture

The Spock application uses a serverless SQLite 3 database file named `ship_computer.db` to persist structured data required for AI-driven inquiries. This section explains how the database supports features such as Ask AI and Deep Dive, including storage, interaction patterns, embedding-based retrieval, and maintenance.

### Overview of ship_computer.db

**Role:**  
The `ship_computer.db` file serves as the central repository for query metadata, knowledge graph nodes, retrieval results, and vector embeddings. Unlike a client-server relational database, SQLite is embedded directly within the application's local data path, providing low-latency access without requiring a separate database server process or network configuration.

**Technology Stack:**
- **Engine:** SQLite 3 (serverless, ACID-compliant).
- **Storage Format:** Single-file B-tree database structure.
- **Location:** Typically located in the project's local data directory, alongside or referenced by the `spock_wiki_adapter` module.
- **Concurrency Model:** Uses Write-Ahead Logging (WAL) mode to allow concurrent read operations while writes are serialized, optimizing performance for AI query workloads.

### Interaction with Spock Application

The Spock application connects to `ship_computer.db` using lightweight, thread-safe connection management. Because SQLite is file-based, concurrency is handled through SQLite's built-in locking mechanisms and Python-level connection management rather than a network database server. The interaction model differs based on the inquiry type:

#### Ask AI Inquiries

For standard "Ask AI" queries, the application performs fast, read-optimized lookups against pre-indexed tables.
- **Workflow:**
  1. User submits a query via the UI.
  2. The `wiki_agent` module tokenizes the query and retrieves relevant context from the database using full-text search (FTS5) and vector similarity indexes.
  3. Retrieved chunks are cached in memory for immediate response generation.
  4. The LLM synthesizes the final answer using the retrieved context.
- **Database Tables:** Primarily uses read-oriented indexed tables containing wiki content, metadata, chunk boundaries, and retrieval hints. Queries are optimized with `WHERE` clauses and precomputed indexes to minimize disk I/O.

#### Deep Dive Inquiries

For complex "Deep Dive" inquiries, the application executes multi-step, stateful queries that may involve joining multiple tables, traversing knowledge graph relationships, or iteratively expanding search parameters.
- **Workflow:**
  1. User initiates a deep analysis request.
  2. The `spock_wiki_adapter` orchestrates transactions to write intermediate results, query expansions, and reasoning steps back to `ship_computer.db`.
  3. The database returns aggregated data, relationship mappings, and confidence scores for visualization or further processing.
  4. Session state is persisted to allow resumption or rollback if the analysis is interrupted.
- **Database Tables:** Uses write-enabled tables for logging session history, storing vector embeddings, tracking query lineage, and maintaining state for long-running analysis tasks.

Transactions (`BEGIN`/`COMMIT`) ensure that intermediate analysis steps remain consistent and atomic while the operation is in progress. Rollback mechanisms are in place to prevent partial state corruption during unexpected terminations.

### Embedding LLM and Vector Database

The Spock application uses an embedding model—often referred to in this context as the embedding LLM—to convert natural-language text into dense numerical vectors. These vectors enable semantic similarity search, allowing the application to retrieve relevant content even when the user's query does not match exact keywords.

**Embedding Pipeline:**
1. **Chunking:** Wiki pages, documents, or knowledge graph nodes are split into manageable chunks during ingestion.
2. **Embedding Generation:** Each chunk is passed through the embedding model, producing a fixed-length vector that represents its semantic meaning.
3. **Vector Storage:** The resulting vectors are stored in `ship_computer.db`, typically in a vector table that links each embedding to its source chunk, document, node ID, and metadata.
4. **Indexing:** Depending on deployment, the application may use SQLite-based indexes, in-memory ANN structures, or an external vector index to accelerate nearest-neighbor search.

**Query-Time Retrieval:**
- When a user submits an Ask AI or Deep Dive request, the same embedding model converts the user's query into a query vector.
- The application compares the query vector against stored chunk vectors, usually using cosine similarity or another distance metric.
- The top-k most similar chunks are returned as candidate context.
- These candidates may be combined with FTS5 keyword results, reranked, and filtered by metadata before being passed to the LLM.

**Role in Ask AI:**
For Ask AI, the embedding model and vector database provide fast semantic retrieval. The application retrieves a small set of highly relevant chunks, assembles them into a prompt, and asks the LLM to generate a concise answer grounded in that context.

**Role in Deep Dive:**
For Deep Dive, the embedding model supports iterative exploration. The application can embed intermediate questions, retrieved passages, and expanded search terms, then use vector similarity to discover related concepts, entities, or documents. This enables multi-hop reasoning, relationship traversal, and progressive refinement of the analysis.

### Maintenance and Health Checks

The `wiki_maintenance` module monitors the health of `ship_computer.db`.
- **Vacuuming:** Periodic `VACUUM` operations are performed to reclaim disk space after large data deletions or index rebuilds.
- **Integrity Check:** The application runs `PRAGMA integrity_check` during startup to ensure the database file is not corrupted.
- **Backup:** Automated snapshots can be configured to back up `ship_computer.db` before major maintenance windows or index migrations.

These checks reduce the risk of stale files, corruption, or failed recovery after interrupted operations.
## Embedding LLM and Vector Database Integration

The Spock application leverages an embedding Large Language Model (LLM) alongside `ship_computer.db` to enable semantic search and context-aware retrieval. This section details how text is transformed into vector representations, stored, and queried.

In this architecture, the embedding LLM is responsible for converting natural-language text into numerical vectors that capture semantic meaning. `ship_computer.db`, a SQLite 3 database, stores those vectors together with the source text, metadata, full-text search indexes, and Deep Dive run state. This allows Spock to perform semantic retrieval without requiring an external vector database service.

### SQLite 3 `ship_computer.db` and Spock Interaction

`ship_computer.db` is a local, file-based SQLite 3 database used by the Spock application as both a relational store and a lightweight vector store. It provides ACID transactions, foreign-key integrity, full-text search through FTS5, and binary storage for embedding vectors.

Spock interacts with `ship_computer.db` through Python database access layers such as `sqlite3`, SQLAlchemy, or a similar ORM. Depending on the operation, Spock may use:

- **Read-only connections** for Ask AI queries and vector search.
- **Read-write connections** for indexing wiki content, storing embeddings, and recording Deep Dive findings.
- **WAL mode** to improve concurrent read performance while allowing writes.
- **Prepared statements** to safely execute parameterized queries for vector retrieval, chunk lookup, and run-state updates.

The database typically contains the following logical components:

| Table or Index | Purpose |
|---|---|
| `wiki_documents` | Stores source wiki pages, titles, URLs, hashes, and update timestamps. |
| `wiki_chunks` | Stores semantically coherent text chunks extracted from wiki documents. |
| `embeddings` | Stores vector representations of chunks or Deep Dive findings. |
| `chunks_fts` | FTS5 full-text search index over chunk text for keyword retrieval. |
| `deep_dive_runs` | Stores metadata for Deep Dive sessions, including prompts, status, and timestamps. |
| `deep_dive_findings` | Stores intermediate findings generated during Deep Dive analysis. |
| `ask_ai_queries` | Optional audit table for Ask AI prompts, retrieved chunks, and response metadata. |

For **Ask AI**, Spock performs a read-only retrieval path:

1. The user submits a question.
2. Spock sends the question to the configured embedding LLM.
3. The embedding LLM returns a query vector.
4. Spock queries `ship_computer.db` for the most similar stored vectors.
5. Spock joins the matching embeddings back to their source chunks and documents.
6. Spock assembles a prompt containing the retrieved context and sends it to the response-generating LLM.

For **Deep Dive**, Spock performs an iterative read-write path:

1. Spock creates a Deep Dive run record in `ship_computer.db`.
2. Spock embeds the initial analysis prompt.
3. Spock retrieves relevant wiki chunks using vector search and, optionally, FTS5.
4. Spock generates an intermediate finding using the primary LLM.
5. Spock stores the finding and its embedding in `ship_computer.db`.
6. In subsequent iterations, Spock queries both the original wiki index and the newly generated intermediate findings.
7. Spock updates the Deep Dive run with citations, reasoning steps, and final synthesis.

This design allows `ship_computer.db` to serve as a self-contained semantic retrieval layer while preserving relational integrity, auditability, and transactional consistency.

### Embedding Generation Pipeline

1. **Text Chunking:** During the indexing phase, raw wiki content is split into semantically coherent chunks, typically 256–1024 tokens. Chunking may use headings, paragraphs, token windows, or overlapping windows to preserve context while fitting within the embedding model's input limits.

2. **Vectorization:** Each chunk is passed through the configured embedding LLM, such as `text-embedding-3-small`, `all-MiniLM-L6-v2`, or a local equivalent. The model outputs a fixed-dimensional floating-point vector, such as 1536 or 768 dimensions, representing the semantic meaning of the text. Spock may normalize the vector before storage to simplify cosine similarity calculations.

3. **Serialization & Storage:** Vectors are serialized into compact binary formats, such as BLOBs containing float32 or float64 values, or optionally stored as JSON arrays. They are stored in dedicated vector tables within `ship_computer.db`. Each vector record is linked to its source chunk or finding via a foreign key, preserving metadata such as document ID, chunk ID, page number, section, model name, model version, dimension count, and extraction timestamp.

### Vector Search & Retrieval

When a user submits a query, the same embedding LLM processes the prompt to generate a query vector. Spock then performs a similarity search against the stored vectors in `ship_computer.db`.

- **Similarity Metric:** Cosine similarity, dot-product similarity, or Euclidean distance is computed between the query vector and indexed chunk vectors. If vectors are normalized, cosine similarity can be efficiently approximated using dot-product calculations.

- **Indexing Strategy:** For small to medium datasets, Spock can perform exact nearest-neighbor search by evaluating all candidate vectors. For larger indexes, Spock may use approximate nearest-neighbor techniques, in-memory HNSW-like structures, or SQLite extensions such as `sqlite-vec` to maintain responsive query performance.

- **Hybrid Retrieval:** Vector results are often combined with keyword-based FTS5 matches. A re-ranking step fuses semantic relevance and lexical precision, using techniques such as reciprocal rank fusion, weighted scoring, or threshold filtering, to return the most accurate context windows to the primary LLM.

### Integration with Ask AI & Deep Dive

- **Ask AI:** Relies on fast, single-pass vector retrieval. The embedding LLM generates one query vector, Spock retrieves the top-K most similar chunks from `ship_computer.db`, and those chunks are passed directly to the response generator.

- **Deep Dive:** Uses iterative embedding queries. As the analysis progresses, intermediate findings are embedded and stored in `ship_computer.db`. Subsequent steps query both the original wiki index and the newly generated intermediate vectors, enabling recursive knowledge expansion and cross-referencing across disparate wiki sections.

This architecture ensures that `ship_computer.db` functions not only as a traditional relational store but also as a lightweight, self-contained vector database, eliminating the need for external vector services while maintaining high query accuracy and low infrastructure overhead.

### Example `ship_computer.db` Schema

The following schema illustrates a practical structure for storing wiki content, embeddings, full-text indexes, and Deep Dive state.

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS wiki_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    url TEXT,
    source_hash TEXT,
    content_hash TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS wiki_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES wiki_documents(id) ON DELETE CASCADE,
    chunk_order INTEGER NOT NULL,
    section_title TEXT,
    page_number INTEGER,
    token_count INTEGER,
    chunk_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL CHECK (source_type IN ('wiki_chunk', 'deep_dive_finding')),
    chunk_id INTEGER REFERENCES wiki_chunks(id) ON DELETE CASCADE,
    finding_id INTEGER REFERENCES deep_dive_findings(id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    model_version TEXT,
    dimensions INTEGER NOT NULL,
    normalized INTEGER NOT NULL DEFAULT 1,
    vector BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_text,
    content='wiki_chunks',
    content_rowid='id'
);

CREATE TABLE IF NOT EXISTS deep_dive_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    iteration_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS deep_dive_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES deep_dive_runs(id) ON DELETE CASCADE,
    iteration INTEGER NOT NULL,
    finding_text TEXT NOT NULL,
    confidence REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_chunks_document_order
    ON wiki_chunks(document_id, chunk_order);

CREATE INDEX IF NOT EXISTS idx_embeddings_model_dimensions
    ON embeddings(model_name, dimensions);

CREATE INDEX IF NOT EXISTS idx_findings_run_iteration
    ON deep_dive_findings(run_id, iteration);
```

### Ask AI and Deep Dive Query Patterns

For Ask AI, Spock typically executes a vector similarity query against the `embeddings` table and joins the result back to the source chunk and document.

```sql
SELECT
    c.id AS chunk_id,
    c.chunk_text,
    d.title AS document_title,
    d.url AS document_url,
    e.model_name,
    e.dimensions
FROM embeddings e
JOIN wiki_chunks c
    ON c.id = e.chunk_id
JOIN wiki_documents d
    ON d.id = c.document_id
WHERE e.source_type = 'wiki_chunk'
  AND e.model_name = :model_name
  AND e.dimensions = :dimensions
ORDER BY vec_distance_cosine(e.vector, :query_vector)
LIMIT :top_k;
```

If a vector extension is not available, Spock can perform the same search in Python by loading candidate vectors, computing similarity scores, and returning the top-K results.

For Deep Dive, Spock may query both wiki chunks and previously generated findings.

```sql
SELECT
    e.id AS embedding_id,
    e.source_type,
    e.model_name,
    e.dimensions,
    c.chunk_text AS wiki_chunk_text,
    f.finding_text AS deep_dive_finding_text,
    d.title AS document_title,
    d.url AS document_url
FROM embeddings e
LEFT JOIN wiki_chunks c
    ON c.id = e.chunk_id
LEFT JOIN wiki_documents d
    ON d.id = c.document_id
LEFT JOIN deep_dive_findings f
    ON f.id = e.finding_id
WHERE e.model_name = :model_name
  AND e.dimensions = :dimensions
ORDER BY vec_distance_cosine(e.vector, :query_vector)
LIMIT :top_k;
```

This allows Deep Dive to expand its context over time. Early iterations may rely primarily on the original wiki index, while later iterations can retrieve both source material and previously derived insights, enabling more nuanced multi-step analysis.