# Prerequisites

## System Requirements

- **OS**: Windows 10/11 (PowerShell 5.1+)
- **Python**: 3.10+ (provided through the project virtual environment, `.venv`)
- **RAM**: 8 GB minimum, 16 GB recommended
- **GPU**: NVIDIA GPU with CUDA support (optional; improves local LLM inference performance)

> **Note on Python Installation:** You do not need to install Python globally. The application uses a project-local virtual environment (`.venv`) that contains the required Python runtime and packages. A GPU is optional; if unavailable, local LLM inference will fall back to CPU-only backends using smaller models or reduced batch sizes, which may impact response latency. If you install system-level dependencies such as Tesseract, run your terminal with Administrator privileges when prompted by the installer or package manager.

## SQLite 3 Database: `ship_computer.db`

`ship_computer.db` is the local SQLite 3 database used by the Spock application to store structured application data, user context, and operational state. It acts as the persistent, queryable foundation for both **Ask AI** and **Deep Dive** workflows.

SQLite is used because it provides:

- **Local persistence**: Data remains available without requiring a separate database server.
- **Structured querying**: Spock can use SQL to filter, join, and retrieve records by metadata.
- **Low overhead**: The database is embedded in the application and does not require external administration.
- **Auditability**: Sessions, prompts, results, and user actions can be recorded for traceability.

### Purpose of `ship_computer.db`

The database stores information that supports the Spock application’s ability to answer questions and perform deeper investigations. Typical data includes:

- **Documents and records**: Source materials, notes, reports, logs, or other ship-computer content.
- **Metadata**: Titles, authors, dates, categories, tags, source identifiers, and access permissions.
- **Chunks**: Smaller text segments derived from larger documents, used for retrieval and context assembly.
- **Entities and relationships**: People, systems, locations, events, or other concepts extracted from the data.
- **Ask AI sessions**: User questions, retrieved context, generated answers, and model metadata.
- **Deep Dive sessions**: Multi-step investigation state, selected scope, intermediate findings, and final summaries.
- **Query logs**: Records of user requests, retrieval results, and application behavior for debugging and auditing.

### How Spock Uses `ship_computer.db`

Spock treats `ship_computer.db` as the authoritative local store for structured data and session state.

For **Ask AI**, Spock uses the database to:

1. Validate that the requested data exists.
2. Retrieve relevant records based on keywords, metadata, or entity filters.
3. Load text chunks that will be embedded or passed to the language model.
4. Store the user’s question, retrieved context, and generated answer.
5. Preserve conversation history for follow-up questions.

For **Deep Dive**, Spock uses the database to:

1. Create a persistent investigation session.
2. Track the user’s selected scope, such as a system, time range, person, or topic.
3. Store intermediate results, such as related records, extracted entities, and candidate explanations.
4. Maintain provenance by linking conclusions back to source records.
5. Save the final Deep Dive summary, recommendations, and evidence trail.

### Relationship Between SQLite and the Vector Database

`ship_computer.db` and the vector database serve complementary roles.

- **SQLite** stores structured, relational, and metadata-rich data.
- **The vector database** stores numerical embeddings used for semantic similarity search.

In practice, Spock may use SQLite to filter candidates by exact metadata, such as date, category, or source, and then use the vector database to rank those candidates by semantic relevance. This hybrid approach improves both precision and recall.

## How Spock Supports Ask AI and Deep Dive Inquiries

### Ask AI

**Ask AI** is the conversational question-answering mode of the Spock application. It allows users to ask natural-language questions about the ship computer’s stored information.

A typical Ask AI flow is:

1. The user submits a question.
2. Spock normalizes the question and extracts relevant terms or entities.
3. Spock queries `ship_computer.db` for candidate records and metadata.
4. Spock retrieves or generates embeddings for the question and relevant text chunks.
5. Spock searches the vector database for semantically similar content.
6. Spock combines structured filters from SQLite with semantic results from the vector database.
7. Spock assembles a context window from the most relevant records.
8. The language model generates an answer grounded in that context.
9. Spock stores the question, context, answer, and metadata in `ship_computer.db`.

Ask AI is best suited for direct questions, such as:

- “What is the current status of the navigation system?”
- “Which logs mention the reactor anomaly?”
- “Summarize the recent communications from the bridge.”

### Deep Dive

**Deep Dive** is the investigative mode of the Spock application. It is designed for more complex, multi-step analysis where the user wants to explore relationships, trace evidence, and build a reasoned explanation.

A typical Deep Dive flow is:

1. The user selects a topic, entity, time range, or set of records.
2. Spock creates a Deep Dive session in `ship_computer.db`.
3. Spock retrieves related records, entities, and semantic matches.
4. Spock identifies connections, contradictions, and supporting evidence.
5. The user can refine the investigation by adding filters or asking follow-up questions.
6. Spock updates the session state as new evidence is discovered.
7. Spock generates a structured summary with findings, confidence notes, and source references.
8. The final Deep Dive report is stored in `ship_computer.db` for later review.

Deep Dive is best suited for questions such as:

- “Trace all events related to the power fluctuation over the last 48 hours.”
- “Compare the sensor readings, crew reports, and system logs for the anomaly.”
- “Build a timeline of what happened before the navigation failure.”

## Embedding LLM and Vector Database

### What Is an Embedding LLM?

An **embedding LLM** is a model that converts text into a numerical vector, also called an embedding. Each vector represents the semantic meaning of the text in a high-dimensional space.

For example, the phrases:

- “reactor temperature warning”
- “core heat anomaly”
- “power system overheating”

may produce vectors that are close to one another because they are semantically related, even if they do not share many exact words.

Spock uses embeddings to enable semantic search. Instead of relying only on keyword matching, Spock can find records that are conceptually similar to the user’s question.

### What Is a Vector Database?

A **vector database** is a specialized storage system optimized for storing and searching numerical embeddings. It supports similarity search operations, such as finding the nearest vectors to a query vector.

Spock uses the vector database to answer questions like:

- “Which records are most relevant to this question?”
- “Which passages are semantically similar to this event?”
- “Which documents contain related concepts even if they use different wording?”

### How Spock Uses the Embedding LLM

Spock uses the embedding LLM in two main ways:

1. **During ingestion**
   - Spock breaks source documents into smaller chunks.
   - Each chunk is converted into an embedding.
   - The embedding is stored in the vector database along with metadata.

2. **During query time**
   - Spock converts the user’s question into an embedding.
   - Spock searches the vector database for similar embeddings.
   - The most relevant chunks are returned for context assembly.

### How Spock Uses the Vector Database

The vector database stores:

- **Embeddings**: Numerical vectors representing text chunks.
- **Chunk text**: The original text associated with each vector.
- **Metadata**: References to source documents, record IDs, timestamps, categories, and other SQLite-linked fields.

When a user asks a question, Spock performs a similarity search against the vector database. The database returns the closest matching vectors, which Spock then maps back to the original text and metadata.

### Combining SQLite, Embeddings, and the Language Model

The full retrieval and generation process works as follows:

1. **Question intake**
   - Spock receives the user’s Ask AI or Deep Dive request.

2. **Structured filtering**
   - Spock queries `ship_computer.db` to narrow the search space using metadata, such as date, source, category, or entity.

3. **Semantic retrieval**
   - Spock embeds the question using the embedding LLM.
   - Spock searches the vector database for semantically similar chunks.

4. **Result fusion**
   - Spock combines structured results from SQLite with semantic results from the vector database.
   - Results may be reranked based on relevance, recency, authority, or user preferences.

5. **Context assembly**
   - Spock selects the most relevant chunks and formats them into a context window.

6. **Answer generation**
   - The language model uses the assembled context to generate a grounded response.

7. **Persistence**
   - Spock stores the question, retrieved context, generated answer, and session metadata in `ship_computer.db`.

### Why This Architecture Is Effective

This design separates concerns in a way that improves both accuracy and maintainability:

- **SQLite** provides reliable structured storage and session tracking.
- **The vector database** enables semantic understanding and flexible retrieval.
- **The embedding LLM** bridges natural language and numerical similarity search.
- **The language model** generates human-readable answers from retrieved evidence.

Together, these components allow Spock to answer direct questions through **Ask AI** and perform deeper, evidence-based investigations through **Deep Dive**.
## Software Dependencies

| Component | Purpose |
|-----------|---------|
| Python 3.10+ | Runtime for all Spock modules |
| PyQt6 | GUI framework (installed via `requirements-ui.txt` in Phase A) |
| SQLite3 | Ship's computer database |
| llama.cpp / LM Studio | Local LLM inference backends |
| Tesseract OCR | Optional — only needed to read text inside images |

### Explanation of Software Dependencies

- **PyQt6**: Python bindings for the Qt libraries, used to build cross-platform graphical user interfaces. In Spock, PyQt6 provides the main application window, menus, settings panels, and other interactive UI elements.
- **SQLite3**: A lightweight, file-based relational database that does not require a separate server process. Spock uses it to store ship logs, telemetry, and historical records locally, ensuring data persists without relying on an external network or database service.
- **llama.cpp / LM Studio**: Tools for running large language models (LLMs) locally. They provide the inference backend used for natural-language tasks such as summarization, question answering, text generation, and chatbot-style interaction. `llama.cpp` is a performance-focused runtime with CPU/GPU optimization options, while `LM Studio` provides a more user-friendly interface for downloading, managing, and serving models.
- **Tesseract OCR**: An open-source optical character recognition (OCR) engine. It allows Spock to extract text from images or scanned documents when the source is not already available as selectable text.

### Ship Computer Database (SQLite3)

The core data persistence layer for the Spock application is a single-file SQLite database named `ship_computer.db`. This database acts as the central repository for ship logs, system telemetry, and historical records that the AI uses when generating responses. It is configured to run in Write-Ahead Logging (WAL) mode to optimize concurrent read/write operations and ensure data integrity during high-throughput logging events.

#### Interaction with Ask AI
When a user initiates an **Ask AI** inquiry, Spock queries `ship_computer.db` to retrieve relevant context before asking the LLM to generate a response. The interaction follows this flow:
1.  **Context Retrieval**: The system executes parameterized SQL queries to fetch recent logs, sensor readings, or specific data points related to the user's question (for example, `"What was the engine status at 0800?"`). Indexes on timestamp and system-ID columns ensure sub-second query performance.
2.  **Prompt Construction**: Retrieved structured data is serialized into a clean context string and injected into the LLM's system prompt. This grounds the AI's response in actual ship records rather than relying solely on pre-trained general knowledge.
3.  **State Updates & Audit Logging**: After the inquiry, the AI's response, the user's query, and any newly confirmed observations are written back to dedicated audit tables. This maintains a complete conversational history and ensures the historical record remains accurate and traceable.

#### Interaction with Deep Dive
For **Deep Dive** inquiries, which involve complex analysis, root-cause investigation, or long-term pattern recognition, Spock accesses `ship_computer.db` using advanced query patterns:
1.  **Aggregation & Window Functions**: The system performs SQL aggregations (`GROUP BY`, `SUM`, `AVG`) and window functions to analyze trends over time, such as power-consumption spikes, thermal drift, or maintenance intervals across multiple shifts.
2.  **Deep Context Window Management**: The application retrieves larger, time-bounded datasets to populate the LLM's context window. Data is chunked and prioritized by relevance scores to avoid exceeding token limits while preserving critical historical continuity.
3.  **Iterative Refinement**: Deep Dive queries often trigger multi-step retrieval. Initial broad queries narrow down to specific subsystem logs, allowing the LLM to perform step-by-step reasoning grounded in verified operational data.

#### Embedding LLM & Vector Database Integration
To enable semantic understanding beyond keyword matching, Spock integrates an embedding LLM with a vector-capable SQLite extension (such as `sqlite-vec`). This architecture powers intelligent retrieval for both Ask AI and Deep Dive workflows:

1.  **Text Chunking & Embedding Generation**: Incoming logs, reports, and user-uploaded documents are parsed and split into manageable text chunks. A lightweight embedding model (e.g., `all-MiniLM-L6-v2` or a domain-tuned alternative) converts each chunk into a high-dimensional vector that captures semantic meaning.
2.  **Vector Storage in SQLite**: These vectors are stored alongside their source metadata in dedicated vector tables within `ship_computer.db`. The database indexes these vectors using Approximate Nearest Neighbor (ANN) algorithms, enabling fast similarity searches without external vector databases.
3.  **Semantic Retrieval**: When a user submits a query, the same embedding model converts the prompt into a vector. Spock then executes a cosine similarity or Euclidean distance search against the stored vectors to retrieve the most contextually relevant chunks, even if they lack exact keyword matches.
4.  **Retrieval-Augmented Generation (RAG)**: The retrieved semantic chunks are merged with structured SQL results and formatted into a unified context payload. This enriched prompt is passed to the primary inference LLM, ensuring responses are both factually grounded and semantically aware.


## Python Packages

Packages are tiered, and the bootstrap installer manages them in two passes: Phase A installs `requirements-ui.txt` (just enough for the menu to open), and Phase B installs `requirements-full.txt` (extractors, ingest, WebEngine, MCP). OCR, test, and docs packages are opt-in. See [Requirements](../reference/requirements.md) for the full breakdown.

Text inside images requires the native Tesseract binary alongside `requirements-ocr.txt`. This installation step should be performed with Administrator privileges so system binaries can be registered correctly.

```powershell
winget install UB-Mannheim.TesseractOCR
.venv\Scripts\python.exe -m pip install -r requirements-ocr.txt
```

> **Installation Tip:** If you encounter permission errors during the `winget` command, run PowerShell as Administrator and retry. If `winget` is unavailable or blocked by policy, install Tesseract using an approved installer, then run the pip command above.

## SQLite 3 `ship_computer.db`

`ship_computer.db` is the local SQLite 3 database used by the Spock application to persist application state, document metadata, retrieval context, and user interaction history. It is the structured data layer behind both **Ask AI** and **Deep Dive** workflows.

### Role in the Spock application

Spock uses `ship_computer.db` to:

- Store document and chunk metadata after ingestion.
- Track which content has been embedded and indexed.
- Preserve Ask AI and Deep Dive sessions, prompts, retrieved sources, and generated responses.
- Support filtering, ranking, and citation of retrieved content.
- Provide a durable local record for audit, replay, and follow-up questions.

The database does not replace the vector database. Instead, it stores the relational metadata that Spock needs to understand what each vector represents, where it came from, and how it should be presented to the user.

### Typical data model

A typical `ship_computer.db` schema includes tables such as:

| Table | Purpose |
|---|---|
| `documents` | One row per ingested document, including source path, title, MIME type, hash, and ingestion timestamp. |
| `chunks` | One row per text chunk, including document reference, chunk index, character offsets, and content hash. |
| `embeddings` | One row per embedded chunk, including vector store reference, embedding model, dimensionality, and status. |
| `queries` | One row per user question or Deep Dive request, including mode, prompt, filters, and timestamp. |
| `retrievals` | One row per retrieved chunk or source used for a query, including score, rank, and citation metadata. |
| `responses` | One row per generated answer, including model, prompt version, token usage, and feedback. |

This separation allows Spock to keep the vector database optimized for similarity search while using SQLite for reliable joins, filtering, and history.

### Ask AI interaction

When a user submits an **Ask AI** request, Spock typically follows this flow:

1. **Normalize the request.** Spock records the question in `queries` and applies any active filters, such as document type, date range, or project scope.
2. **Embed the question.** The question is converted into a vector using the configured embedding LLM.
3. **Search the vector database.** Spock performs a nearest-neighbor search to find the most semantically relevant chunks.
4. **Resolve metadata.** Spock joins the retrieved vector IDs back to `ship_computer.db` to obtain document titles, chunk text, source locations, and permissions.
5. **Generate the answer.** The retrieved context is sent to the answer LLM, which produces a response grounded in the retrieved material.
6. **Persist the result.** Spock stores the query, retrieved sources, scores, and final response in `ship_computer.db` for citation, audit, and follow-up.

For Ask AI, the goal is a fast, focused answer. The database provides the context needed to make the answer traceable and repeatable.

### Deep Dive interaction

**Deep Dive** is a more investigative mode. Instead of returning a single best answer, Spock may perform multiple retrieval passes, broaden or narrow the search, and assemble a larger evidence set.

During a Deep Dive, `ship_computer.db` is used to:

- Track the original request and each intermediate retrieval step.
- Store candidate chunks, scores, and ranking decisions.
- Preserve filters and scope changes made by the user.
- Record which sources were included in the final synthesis.
- Support follow-up questions by reusing the same session context.

This makes Deep Dive suitable for complex questions that require comparing multiple documents, tracing claims to sources, or building a structured summary from many chunks.

## Embedding LLM and Vector Database

Spock uses an **embedding LLM** and a **vector database** to turn unstructured text into searchable semantic representations.

### What an embedding LLM does

An embedding LLM converts text into a numerical vector, also called an embedding. Each vector represents the meaning of the text in a high-dimensional space. Text with similar meaning produces vectors that are close together, while unrelated text produces vectors that are farther apart.

For example:

- "How do I reset the ship computer?" and "What is the procedure for restarting the ship computer?" produce similar vectors.
- "How do I reset the ship computer?" and "What is the weather forecast?" produce dissimilar vectors.

Spock uses embeddings for both indexing and querying:

- During ingestion, document chunks are embedded and stored in the vector database.
- During Ask AI or Deep Dive, the user's question is embedded and compared against stored embeddings.

### How the vector database is used

The vector database stores the embeddings and supports fast similarity search. When Spock receives a question, it:

1. Embeds the question using the same embedding model used for indexing.
2. Queries the vector database for the nearest vectors.
3. Retrieves the associated chunk IDs or document references.
4. Uses `ship_computer.db` to load the full chunk text and metadata.
5. Ranks, filters, and formats the results for the answer LLM.

Using the same embedding model for indexing and querying is important because the vector space must be consistent. If the model changes, Spock should re-embed existing content or maintain a separate index for the new model.

### How Ask AI and Deep Dive use embeddings differently

**Ask AI** uses embeddings for direct semantic retrieval. It typically asks for a small number of highly relevant chunks and generates a concise answer.

**Deep Dive** uses embeddings more extensively. It may:

- Run multiple queries with different phrasings.
- Retrieve a larger candidate set.
- Re-rank results using metadata, recency, or user preferences.
- Expand context by finding related chunks from the same document.
- Store the full retrieval trail in `ship_computer.db`.

This allows Deep Dive to move beyond a single best match and build a more complete, source-backed explanation.