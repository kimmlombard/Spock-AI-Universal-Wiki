# Technology Stack

## Runtime summary

| Area | Value | Evidence |
| --- | --- | --- |
| Primary language | Python | `requirements*.txt`, `*.py` files |
| Runtime | CPython 3.x, typically run from a virtual environment under `.venv` | `.venv`, bootstrap/installation notes |
| Package manager | pip with tiered `requirements-*.txt` files | `requirements.txt` and related requirement files |
| GUI | PyQt6 desktop interface | `requirements-ui.txt` |
| Local LLM support | `llama-server` exposing an OpenAI-compatible API | `llama_server_manager` references |
| Database | SQLite 3 database named `ship_computer.db` | `ship_computer_schema.sql` |

The project is a local Python desktop application. It uses pip-managed dependencies, a PyQt6 user interface, and a SQLite 3 database for configuration and application state. Local LLM functionality is provided through an external OpenAI-compatible server process rather than by directly embedding the model runtime within the Python package. This architecture decouples model execution from the application UI, enabling independent scaling, hot-swapping of models, and simplified dependency management.

## Stated project intent

No README, ROADMAP, or SPEC document was detected at the project root during the scan. This section is therefore left as a placeholder until formal project documentation is added.

## Production / install dependencies (from requirements*)

The table below lists packages detected across the scanned `requirements-*.txt` files. The dependency set encompasses runtime, GUI, MCP, testing, and documentation tooling, reflecting the tiered structure identified during the scan. `[unpinned]` indicates that no explicit version constraint was found for that package in the scanned requirement file; it does not imply a recommended or installed version.

| Dependency | Version | Role | Evidence |
| --- | --- | --- | --- |
| PyQt6-WebEngine | [unpinned] | Embedded web rendering support for the GUI | `requirements-full.txt` |
| markdown | [unpinned] | Markdown parsing and processing | `requirements-full.txt` |
| Pillow | [unpinned] | Image handling, conversion, and manipulation | `requirements-full.txt` |
| beautifulsoup4 | [unpinned] | HTML/XML document parsing | `requirements-full.txt` |
| lxml | [unpinned] | Fast XML/HTML parsing backend | `requirements-full.txt` |
| python-docx | [unpinned] | Microsoft Word `.docx` file handling | `requirements-full.txt` |
| PyMuPDF | [unpinned] | PDF text, metadata, and page/image extraction | `requirements-full.txt` |
| openpyxl | [unpinned] | Excel workbook reading and writing | `requirements-full.txt` |
| pandas | [unpinned] | Tabular data processing and analysis | `requirements-full.txt` |
| watchdog | [unpinned] | File-system change monitoring, likely for wiki file watching | `requirements-full.txt` |
| keyring | [unpinned] | OS-level credential storage or retrieval | `requirements-full.txt` |
| reportlab | [unpinned] | PDF generation and reporting | `requirements-full.txt` |
| google-auth | [unpinned] | Google authentication flows and credential handling | `requirements-full.txt` |
| nvidia-ml-py | [unpinned] | NVIDIA GPU status, usage, or resource queries | `requirements-full.txt` |
| PyQt6 | >=6.6,<6.12 | Primary desktop GUI framework (capped to match WebEngine) | `requirements-ui.txt` |
| requests | >=2.31 | HTTP client for API and network calls | `requirements-ui.txt` |
| psutil | >=5.9 | Process, CPU, memory, disk, and system metrics | `requirements-ui.txt` |
| huggingface_hub | >=0.23 | Hugging Face model or dataset download and management | `requirements-ui.txt` |
| fastmcp | ==2.11.3 | Model Context Protocol (MCP) server support | `requirements-mcp.txt` |
| authlib | [unpinned] | OAuth/OIDC authentication library | `requirements-mcp.txt` |
| starlette | [unpinned] | ASGI web framework for HTTP endpoints or MCP-related services | `requirements-mcp.txt` |
| pytest | >=8.0 | Automated test execution | `requirements-dev.txt` |
| mkdocs | >=1.6 | Static documentation site generation | `requirements-docs.txt` |
| mkdocs-material | >=9.5 | Material theme for MkDocs sites | `requirements-docs.txt` |
| mkdocstrings | >=0.26 | API reference generation from Python docstrings | `requirements-docs.txt` |
| mkdocs-gen-files | >=0.5 | File generation during MkDocs builds | `requirements-docs.txt` |
| openai | [unpinned] | OpenAI-compatible client for LLM or embedding endpoints | `requirements-docs.txt` |

## Key commands

```bash
python -m spock_bringup_menu
python -m EngineeringDeck   # or NavigationStation / ScienceStation
python -m pytest
pip install -r requirements-ui.txt   # Phase A
pip install -r requirements-full.txt # Phase B
```

Command notes:

- `python -m spock_bringup_menu` starts the bring-up menu entry point.
- `python -m EngineeringDeck`, `NavigationStation`, or `ScienceStation` launches a specific application module or deck; the exact module depends on the intended workflow.
- `python -m pytest` runs the project's automated test suite.
- `pip install -r requirements-ui.txt` installs the minimal Phase A GUI tier.
- `pip install -r requirements-full.txt` installs the fuller Phase B runtime, including extractors, ingest support, WebEngine dependencies, and MCP-related packages.

## SQLite 3 database: `ship_computer.db`

`ship_computer.db` is the local SQLite 3 database used by the Spock application to persist configuration, application state, document metadata, conversation history, retrieval context, and operational diagnostics. It acts as the durable local record for the desktop application, while the LLM and vector database provide the inference and semantic retrieval capabilities.

The database is expected to be managed through the schema defined in `ship_computer_schema.sql`. The exact table names and column definitions should be confirmed against that schema file, but the database generally serves the following architectural roles.

### Purpose

The `ship_computer.db` database provides a local, transactional, file-based store for data that must survive application restarts. It is used for:

- Storing user and application settings.
- Tracking document ingestion and parsing status.
- Recording Ask AI conversations and generated responses.
- Preserving Deep Dive investigation state, including multi-step reasoning and retrieved evidence.
- Maintaining metadata that links application records to vector database entries.
- Supporting auditability, resume-after-restart, and local diagnostics.

Because the application is a local desktop system, SQLite 3 is a suitable choice: it requires no separate database server, supports concurrent read access from the GUI process, and provides sufficient transactional integrity for local application state.

### Core data domains

The following table describes the major data domains that `ship_computer.db` is expected to support.

| Data domain | Stored information | Use in Spock |
| --- | --- | --- |
| Application settings | UI preferences, model endpoints, local server configuration, feature flags, user preferences | Allows the application to restore the user's environment and connect to the correct LLM or embedding endpoint. |
| Document ingestion | Source file paths, file hashes, document types, parse status, chunk counts, ingestion timestamps | Tracks which documents have been processed and whether their content is available for retrieval. |
| Document metadata | Title, author, source, language, page count, extraction method, last modified time | Provides context for citations, filtering, and relevance scoring. |
| Ask AI sessions | User questions, assistant responses, model name, prompt version, timestamp, session ID | Enables conversation history, follow-up questions, and response auditing. |
| Ask AI citations | Retrieved chunk IDs, source documents, similarity scores, cited passages | Allows the application to show evidence for generated answers. |
| Deep Dive investigations | Investigation title, objective, status, step history, generated analysis, user feedback | Supports multi-step research workflows that can be paused, resumed, and reviewed. |
| Deep Dive evidence | Retrieved passages, vector IDs, source documents, confidence scores, step associations | Preserves the evidence trail used to produce a Deep Dive result. |
| Retrieval metadata | Query text, embedding model, vector database ID, top-k results, filters, scores | Provides traceability for semantic search and retrieval quality analysis. |
| Diagnostics | Errors, warnings, LLM request failures, embedding failures, ingestion failures | Helps users and developers troubleshoot local model or database issues. |

### Relationship to the Spock application

The Spock application uses `ship_computer.db` as its local system of record. The GUI layer, ingestion pipeline, LLM client, and retrieval layer all read from or write to this database through a shared data-access layer.

A typical interaction pattern is:

1. The user opens the Spock application.
2. The application reads settings and prior state from `ship_computer.db`.
3. The user selects a document, starts an Ask AI session, or begins a Deep Dive investigation.
4. The application records the request in the database.
5. The application calls the embedding model and vector database to retrieve relevant context.
6. The application calls the LLM to generate a response.
7. The application stores the response, citations, model metadata, and any follow-up state in `ship_computer.db`.

This design keeps the user-facing application state local and persistent, while allowing the LLM and vector database to be replaced, restarted, or upgraded without losing the application's historical records.

### Ask AI interaction

Ask AI is the conversational query mode in which the user asks a question and the application returns a generated answer based on local or connected knowledge sources.

The interaction with `ship_computer.db` typically follows this flow:

1. **Session initialization**  
   The application creates or resumes an Ask AI session record. This record may include a session ID, user ID, timestamp, and active model configuration.

2. **Query capture**  
   The user's question is stored in the database. This allows the application to reconstruct the conversation later and to support follow-up questions.

3. **Context retrieval**  
   The application sends the question to the embedding model and queries the vector database for relevant passages. The retrieved passages, similarity scores, and source metadata are stored or referenced in the database.

4. **Prompt construction**  
   The application builds a prompt using the user's question, prior conversation context, and retrieved evidence.

5. **LLM generation**  
   The application sends the prompt to the LLM endpoint and receives a generated answer.

6. **Response persistence**  
   The generated answer, model name, prompt version, latency, token usage, and citation metadata are written to `ship_computer.db`.

7. **Follow-up support**  
   If the user asks a follow-up question, the application can load the prior session from the database and include relevant prior context in the next prompt.

This makes Ask AI more than a stateless chat window. The database allows the application to maintain continuity, show citations, and preserve a local audit trail of what was asked, what was retrieved, and what was generated.

### Deep Dive interaction

Deep Dive is a more structured, multi-step inquiry mode. Instead of returning a single immediate answer, the application may decompose the user's objective, retrieve evidence across multiple steps, synthesize intermediate findings, and produce a more detailed investigation result.

The database supports Deep Dive by persisting the investigation as a durable object.

A typical Deep Dive workflow is:

1. **Investigation creation**  
   The user defines a Deep Dive objective. The application creates an investigation record with a unique ID, title, status, and creation timestamp.

2. **Planning**  
   The application may generate a plan or sub-questions. These steps are stored in the database so the investigation can be resumed if the application is closed.

3. **Retrieval**  
   For each step, the application embeds the step query and retrieves relevant passages from the vector database. The retrieved evidence is linked to the investigation step.

4. **Synthesis**  
   The application uses the LLM to synthesize findings from the retrieved evidence. Intermediate summaries are stored in the database.

5. **Iteration**  
   If the generated result is incomplete, the application may issue additional retrieval or synthesis steps. Each iteration is recorded.

6. **Final output**  
   The final Deep Dive report, citations, confidence notes, and user feedback are stored in the database.

This persistence model is important because Deep Dive workflows can be long-running. The database allows the application to:

- Resume an interrupted investigation.
- Show the user which evidence supported each conclusion.
- Compare multiple Deep Dive runs.
- Preserve user edits or feedback.
- Audit how the application arrived at a result.

### Example data relationships

The following conceptual relationships are expected in the database design.

```text
application_settings
    stores user and model configuration

documents
    stores ingested source files and metadata

document_chunks
    stores chunk-level metadata and links to vector entries

ask_ai_sessions
    stores conversation sessions

ask_ai_messages
    stores user and assistant messages

ask_ai_citations
    stores evidence used for assistant messages

deep_dive_investigations
    stores multi-step investigation records

deep_dive_steps
    stores individual planning, retrieval, or synthesis steps

deep_dive_evidence
    stores retrieved passages linked to investigation steps

retrieval_logs
    stores query embedding and vector search metadata
```

The exact table names may differ, but the logical model is likely to separate:

- **Configuration data**, which changes infrequently.
- **Document data**, which grows as new sources are ingested.
- **Conversation data**, which grows with user interactions.
- **Investigation data**, which grows with Deep Dive usage.
- **Diagnostics data**, which supports troubleshooting.

### Transactional behavior

Because the application is local and user-facing, `ship_computer.db` should be used with transactional writes to avoid partial state.

For example, when storing an Ask AI response, the application should ideally write the following as a single logical transaction:

- The assistant message.
- The citation records.
- The retrieval metadata.
- The session status update.

This prevents situations where a response is visible in the GUI but its citations are missing, or where a Deep Dive step is marked complete without its evidence being saved.

### Local privacy and portability

Using SQLite 3 keeps sensitive local data on the user's machine. This is important for a desktop application that may process private documents, local notes, or internal knowledge bases.

The database also supports portability:

- The user can back up `ship_computer.db` along with the vector database and document corpus.
- The application can be moved to another machine if the database and vector index are copied.
- The user can inspect or export local records without relying on a remote service.

## Embedding LLM and vector database usage

The Spock application uses an embedding LLM and a vector database to support semantic retrieval for Ask AI and Deep Dive inquiries. The embedding model converts text into numerical vectors, and the vector database stores and searches those vectors efficiently.

This combination allows the application to find relevant passages based on meaning rather than only exact keyword matches.

### Role of the embedding LLM

The embedding LLM is a model that maps text into a high-dimensional vector space. Similar meanings are represented by vectors that are close together, while unrelated meanings are farther apart.

In the Spock application, the embedding LLM is used for two main purposes:

1. **Document embedding**  
   When documents are ingested, their text is split into chunks. Each chunk is converted into an embedding vector and stored in the vector database.

2. **Query embedding**  
   When the user asks a question in Ask AI or Deep Dive, the question is converted into an embedding vector. The application then searches the vector database for stored vectors that are semantically similar to the query vector.

The embedding model may be served locally through an OpenAI-compatible endpoint, such as `llama-server`, or it may be accessed through a remote API. The application likely uses the `openai` Python package or a similar OpenAI-compatible client to call the embedding endpoint.

### Relationship between the embedding LLM and the LLM

The embedding LLM and the generative LLM serve different roles.

| Component | Purpose | Output |
| --- | --- | --- |
| Embedding LLM | Converts text into vectors for similarity search | Numeric vector |
| Generative LLM | Produces natural-language answers or analysis | Text response |

The embedding LLM does not generate the final answer. It helps the application find the most relevant evidence. The generative LLM then uses that evidence to produce the user-facing response.

This separation is important because:

- Embedding models are optimized for semantic similarity.
- Generative models are optimized for language production.
- Retrieval can be performed before generation, reducing hallucination risk.
- The application can show citations for the generated answer.

### Document ingestion and vector indexing

When a document is added to the Spock knowledge base, the application likely performs the following steps:

1. **File discovery**  
   The application identifies a supported file type, such as PDF, Word, Excel, HTML, Markdown, or plain text.

2. **Extraction**  
   The application extracts text using the appropriate library, such as PyMuPDF for PDFs, python-docx for Word files, openpyxl for Excel files, or BeautifulSoup for HTML.

3. **Normalization**  
   The extracted text is cleaned, normalized, and split into manageable chunks.

4. **Chunking**  
   The text is divided into overlapping or non-overlapping chunks. Chunking is necessary because embedding models have input length limits and because smaller chunks produce more precise retrieval results.

5. **Embedding**  
   Each chunk is sent to the embedding LLM and converted into a vector.

6. **Vector storage**  
   The vector, chunk text, and metadata are stored in the vector database.

7. **Metadata persistence**  
   The application stores document and chunk metadata in `ship_computer.db`, including source file, chunk ID, vector ID, ingestion timestamp, and status.

The vector database is the primary store for the embedding vectors. `ship_computer.db` stores the relational metadata that links those vectors back to documents, chunks, sessions, and investigations.

### Vector database role

The vector database is the semantic search index. It stores embedding vectors and supports similarity queries such as:

- Find the top 10 chunks most similar to this question.
- Find chunks from a specific document that match this concept.
- Find passages related to a Deep Dive sub-question.
- Filter results by document type, date, source, or user-defined tags.

The exact vector database implementation is not identified in the scanned requirements. It may be an embedded SQLite vector extension, a local vector database, or an external vector service accessed through an API. From the application's perspective, the vector database is used through a retrieval layer that abstracts the underlying storage.

### Query flow for Ask AI

For an Ask AI question, the application uses the embedding LLM and vector database as follows:

1. The user enters a question.
2. The application sends the question to the embedding LLM.
3. The embedding LLM returns a query vector.
4. The application queries the vector database for the most similar stored vectors.
5. The vector database returns candidate chunks with similarity scores.
6. The application retrieves the corresponding text and metadata from `ship_computer.db` or the vector database.
7. The application ranks or filters the candidates.
8. The application builds a prompt containing the question and relevant evidence.
9. The generative LLM produces an answer.
10. The application stores the question, answer, citations, and retrieval metadata in `ship_computer.db`.

This flow allows Ask AI to answer from the user's local knowledge base rather than relying only on the LLM's general training data.

### Query flow for Deep Dive

For a Deep Dive inquiry, the application uses the same embedding and vector search mechanism, but it applies it across multiple steps.

A typical Deep Dive flow is:

1. The user defines a research objective.
2. The application creates a Deep Dive investigation record in `ship_computer.db`.
3. The application generates sub-questions or analysis steps.
4. For each step:
   - The step text is embedded.
   - The vector database retrieves relevant passages.
   - The retrieved evidence is stored with the step.
   - The generative LLM synthesizes a partial finding.
5. The application may issue additional retrieval steps if the evidence is insufficient.
6. The application produces a final Deep Dive report.
7. The report, evidence trail, and step history are persisted in `ship_computer.db`.

This makes Deep Dive more traceable than a single Ask AI response. The database preserves the sequence of reasoning, retrieval, and synthesis.

### Similarity scoring and ranking

The vector database returns similarity scores, often based on cosine similarity, dot product, or another distance metric. The application may use these scores to:

- Rank retrieved chunks.
- Filter out low-confidence results.
- Limit the number of passages included in the prompt.
- Show confidence indicators to the user.
- Support hybrid retrieval by combining vector similarity with keyword matching.

Hybrid retrieval is useful because semantic search excels at conceptual matching, while keyword search can be effective for exact terms, names, codes, or technical identifiers.

### Context assembly

After retrieval, the application assembles a prompt for the generative LLM. The prompt may include:

- The user's original question.
- Prior conversation context for Ask AI.
- The Deep Dive objective and current step.
- Retrieved passages with source metadata.
- Instructions to cite sources.
- Instructions to state uncertainty when evidence is insufficient.

The quality of the final answer depends heavily on the quality of the retrieved context. Good chunking, accurate embeddings, and effective ranking are therefore central to the application's usefulness.

### Model configuration

The application likely stores embedding and LLM configuration in `ship_computer.db` or in local configuration files. This configuration may include:

- Embedding model name.
- Embedding endpoint URL.
- Generative LLM model name.
- Generative LLM endpoint URL.
- API key references, with actual secrets stored in the OS keyring.
- Maximum context length.
- Top-k retrieval count.
- Similarity threshold.
- Chunk size and overlap settings.

Using `keyring` for credentials is consistent with the dependency list and allows the application to avoid storing sensitive API keys directly in the SQLite database.

### Failure handling and fallbacks

Because the embedding LLM and vector database are external or semi-external components, the application should handle failures gracefully.

Possible failure scenarios include:

- The embedding server is not running.
- The vector database is unavailable.
- A document has not been fully indexed.
- The embedding model returns an error.
- The generative LLM times out.
- The retrieved context is too small or too large.

In these cases, the application may:

- Show a clear error message.
- Fall back to keyword search if available.
- Mark the retrieval step as failed in `ship_computer.db`.
- Allow the user to retry.
- Preserve partial Deep Dive results.
- Log diagnostics for troubleshooting.

### Summary of the retrieval architecture

The overall retrieval architecture can be summarized as follows:

```text
User question
    |
    v
Embedding LLM
    |
    v
Query vector
    |
    v
Vector database
    |
    v
Similar chunks + metadata
    |
    v
Prompt assembly
    |
    v
Generative LLM
    |
    v
Answer / Deep Dive result
    |
    v
ship_computer.db
```

In this model:

- The **embedding LLM** provides semantic understanding.
- The **vector database** provides fast similarity search.
- The **generative LLM** produces the final natural-language output.
- **`ship_computer.db`** preserves the application state, conversation history, citations, and Deep Dive evidence.

Together, these components allow the Spock application to support local, evidence-based Ask AI responses and structured Deep Dive investigations.
## SQLite 3 Database (`ship_computer.db`) Architecture & Interaction

The `ship_computer.db` file serves as the centralized relational backbone for the Spock application. Built on SQLite 3, it provides ACID-compliant storage for application configuration, user preferences, session state, document metadata, query history, and provenance data. Its lightweight, serverless nature aligns with the desktop-first architecture, eliminating the need for external database services while maintaining robust data integrity.

In Spock, `ship_computer.db` is the system of record for application state and document provenance. The vector database handles semantic similarity search, while SQLite handles durable, queryable, relational context such as:

- Which documents exist and where they are stored.
- Which chunks belong to which documents.
- Which vector IDs correspond to which chunks.
- Which conversations, prompts, responses, and citations belong to which session.
- Which Deep Dive research threads are active, paused, or completed.
- Which ingestion jobs have completed, failed, or require retry.

This separation allows Spock to combine fast semantic retrieval with reliable, inspectable, and auditable application state.

### Core Schema Responsibilities

- **Configuration & State Management:** Stores UI layout preferences, API endpoints, model selection parameters, retrieval settings, and local server (`llama-server`) status flags.
- **Document Registry:** Maintains metadata for all ingested files (PDFs, DOCX, XLSX, HTML, etc.), including file paths, ingestion timestamps, chunk counts, processing status, and source identifiers.
- **Chunk Registry:** Tracks individual text chunks, their order, boundaries, token counts, source locations, and associated vector IDs.
- **Query & Session History:** Logs user prompts, AI responses, contextual metadata, and conversation state to enable continuity, audit trails, and prompt refinement.
- **Vector Store Mapping:** Acts as the relational index that links semantic vector IDs to their source documents, chunk boundaries, and citation references.
- **Citation & Provenance Tracking:** Stores the evidence behind AI-generated claims, including document, page, section, table, cell, or paragraph references.
- **Ingestion & Processing State:** Records parsing, chunking, embedding, and indexing progress so that long-running operations can be resumed or retried safely.

### Key Tables and Relationships

A typical `ship_computer.db` schema may include the following logical domains. The exact table names can vary by implementation, but the responsibilities remain consistent.

| Domain | Example Tables | Purpose |
|---|---|---|
| Application settings | `app_settings`, `model_config`, `server_status` | Store user preferences, endpoint URLs, model names, temperature, top-k, and local server health. |
| Documents | `documents`, `document_files` | Track source files, file paths, MIME types, ingestion status, and document-level metadata. |
| Chunks | `chunks`, `chunk_metadata` | Store individual text segments, chunk order, token counts, page/section/cell references, and embedding status. |
| Vectors | `vector_records`, `vector_index_map` | Map vector IDs to chunks, embedding models, vector dimensions, and vector database locations. |
| Sessions | `sessions`, `conversation_threads` | Track Ask AI and Deep Dive conversations, including thread type, status, and timestamps. |
| Messages | `messages`, `prompt_parts` | Store user prompts, assistant responses, system prompts, retrieved context, and token usage. |
| Citations | `citations`, `claim_evidence` | Link generated claims to source chunks, pages, sections, tables, or cells. |
| Ingestion jobs | `ingestion_jobs`, `job_steps` | Track parsing, chunking, embedding, and indexing progress for resumable processing. |
| Research state | `deep_dive_threads`, `deep_dive_steps`, `annotations` | Preserve intermediate findings, user notes, branching research paths, and exportable research state. |
| Metrics | `retrieval_metrics`, `usage_metrics` | Record query latency, retrieval scores, token counts, and model usage for tuning and analytics. |

### SQLite Operational Characteristics

SQLite 3 is well suited to Spock because it is embedded, file-based, and requires no separate database server. This makes it ideal for a local desktop application that must start quickly, operate offline, and maintain reliable state.

Key operational characteristics include:

- **ACID Transactions:** Writes to configuration, session state, document metadata, and citation records can be committed atomically, reducing the risk of partial updates.
- **Single-File Storage:** The entire relational database can be stored in one portable file, simplifying backup, migration, and local inspection.
- **Concurrent Read Access:** Multiple readers can access the database while a writer is active, which is useful when the UI reads session state while background ingestion or embedding jobs are running.
- **WAL Mode:** Write-Ahead Logging can improve concurrency by allowing readers to continue while writes are in progress.
- **Indexed Lookups:** Frequently queried fields such as session ID, document ID, chunk ID, vector ID, and message timestamp can be indexed to reduce latency.
- **Prepared Statements:** Repeated queries for session context, document metadata, and citation lookup can be prepared and reused efficiently.
- **JSON Support:** SQLite’s JSON capabilities can store flexible metadata such as document properties, chunk boundaries, and model parameters without requiring rigid schema changes.
- **Full-Text Search:** SQLite FTS5 can support keyword-based retrieval as part of a hybrid search strategy alongside vector similarity.

### Interaction with "Ask AI" Inquiries

"Ask AI" is designed for rapid, conversational queries. It is optimized for low-latency interaction, short context windows, and immediate user feedback.

When a user submits an "Ask AI" prompt, `ship_computer.db` participates in the following way:

1. **Session Resolution:**  
   The application checks `ship_computer.db` for the active session, conversation thread, and recent message history. This allows the model to understand follow-up questions such as "Why?" or "Expand on that."

2. **Preference Retrieval:**  
   The database supplies user preferences such as selected model, temperature, response style, citation behavior, and allowed document scope.

3. **Context Assembly:**  
   Relevant metadata is retrieved to populate the prompt template. This may include recent messages, active document scope, and optional retrieved chunks if semantic search is enabled.

4. **Prompt Construction:**  
   The application builds a structured prompt containing the user question, conversation context, and any retrieved evidence. The prompt is then forwarded to the local generative LLM via the OpenAI-compatible API.

5. **Response Persistence:**  
   Upon response, the exchange is persisted to the database. This includes the user prompt, assistant response, model name, token counts, latency, and any citations or retrieved chunk references.

6. **Conversation Continuity:**  
   Future "Ask AI" turns can reference prior messages, enabling coherent multi-turn dialogue without requiring the user to repeat context.

7. **Low-Latency Optimization:**  
   Because "Ask AI" prioritizes speed, database operations are optimized with indexed lookups, prepared statements, and disciplined connection management. The goal is to retrieve only the minimum context needed to answer the question quickly.

In "Ask AI," SQLite is primarily responsible for session state, user preferences, prompt history, and lightweight provenance. The vector database may be used to retrieve relevant chunks, but SQLite remains the source of truth for which chunks, documents, and sessions are involved.

### Interaction with "Deep Dive" Inquiries

"Deep Dive" handles complex, multi-document research tasks requiring structured analysis, iterative reasoning, and citation tracking. It is designed for longer-running workflows where the user may pause, refine, branch, or export a research thread.

`ship_computer.db` plays a more extensive role in "Deep Dive" than in "Ask AI."

1. **Ingestion Tracking:**  
   As documents are parsed and chunked, `ship_computer.db` records processing states, enabling resumable ingestion and duplicate detection. If a job fails during embedding or indexing, the database can identify which chunks completed and which require retry.

2. **Document Scope Management:**  
   Deep Dive sessions can be scoped to specific documents, folders, or collections. The database stores the selected scope so that retrieval and citation remain consistent across multiple research steps.

3. **Context Assembly:**  
   The database retrieves chunk-level metadata and vector store pointers relevant to the research query. This relational layer ensures that semantic results can be traced back to exact source locations, such as page numbers, sections, tables, or cell ranges.

4. **Research Thread State:**  
   Long-running Deep Dive sessions maintain intermediate findings, user annotations, and branching research paths within the database. This allows users to pause, resume, or export research threads without losing context.

5. **Citation & Provenance:**  
   Every AI-generated claim in a Deep Dive response is cross-referenced with database-stored source metadata, enabling accurate in-text citations and source verification.

6. **Evidence Graphing:**  
   The database can store relationships between claims, chunks, documents, and research steps. This supports explanations such as "This conclusion was derived from these three sources" or "This claim conflicts with this earlier finding."

7. **Export and Audit:**  
   Because Deep Dive state is persisted relationally, users can export research threads, review citation chains, or audit how a conclusion was reached.

In "Deep Dive," SQLite is the durable backbone for research state, while the vector database supplies candidate evidence. The combination allows Spock to perform semantic retrieval while preserving a clear, inspectable chain of evidence.

## Embedding LLM & Vector Database Integration

The Spock application employs a two-stage retrieval-augmented generation (RAG) pipeline that separates semantic indexing from response generation. This architecture ensures high accuracy, efficient context window utilization, and scalable document handling.

The pipeline has three major components:

1. **Embedding Model:** Converts text into numerical vectors that represent semantic meaning.
2. **Vector Database:** Stores and indexes those vectors for fast similarity search.
3. **Generative LLM:** Uses retrieved context to produce a coherent, grounded response.

This separation allows each component to optimize for its specific role: semantic understanding, fast retrieval, and natural language generation.

### Embedding LLM Role

The embedding model is a specialized neural network trained to convert unstructured text into high-dimensional numerical vectors, commonly called embeddings. Unlike generative LLMs, it does not produce human-readable text. Instead, it maps semantically similar content to proximate coordinates in vector space.

In practical terms, an embedding model allows Spock to answer questions such as:

- Which chunks discuss the same concept as the user's query?
- Which passages are semantically related even if they use different wording?
- Which documents contain evidence relevant to a Deep Dive research question?

In Spock, the embedding model is used during both ingestion and query time.

#### During Ingestion

1. **Document Parsing:**  
   Raw documents are parsed using libraries such as `PyMuPDF`, `python-docx`, `openpyxl`, and `beautifulsoup4`, depending on file type.

2. **Chunking:**  
   Text is split into manageable chunks, typically 256–1024 tokens, to preserve contextual boundaries while remaining small enough for efficient retrieval.

3. **Embedding:**  
   Each chunk is passed through the embedding model, which outputs a fixed-length vector representing its semantic meaning.

4. **Vector Storage:**  
   The resulting vector is stored in the vector database and linked to the corresponding chunk record in `ship_computer.db`.

5. **Metadata Association:**  
   The database records the document, chunk ID, page or section, token count, embedding model, vector dimensions, and creation timestamp.

#### During Query Time

When a user submits a question, the same embedding model converts the prompt into a vector. This ensures that the query and the knowledge base exist in the same semantic space.

Using the same model for both documents and queries is critical. If different embedding models were used, their vector spaces might not be compatible, and similarity scores would be unreliable.

### Vector Database Functionality

The vector database stores and indexes embeddings to enable fast, similarity-based retrieval. It is responsible for answering the question: "Which stored text chunks are most semantically similar to this query?"

Key capabilities include:

- **Semantic Search:**  
  When a user submits a query, the embedding model converts the prompt into a vector. The vector database then performs a nearest-neighbor search to identify the most relevant document chunks.

- **Similarity Scoring:**  
  Retrieved chunks are ranked using similarity metrics such as cosine similarity, dot product, or Euclidean distance. Cosine similarity is commonly used because it measures directional similarity and is less sensitive to vector magnitude.

- **Approximate Nearest Neighbor Search:**  
  For large knowledge bases, the vector database may use approximate indexing structures such as HNSW to reduce search latency while maintaining high recall.

- **Hybrid Retrieval:**  
  Spock can combine vector similarity with keyword filtering or full-text search via SQLite metadata queries. This balances semantic relevance with precise factual matching, such as exact names, dates, IDs, or technical terms.

- **Dynamic Indexing:**  
  As new documents are ingested, vectors are appended to the index without requiring full retraining, enabling real-time knowledge base updates.

- **Vector-to-Chunk Mapping:**  
  The vector database returns vector IDs or chunk IDs. `ship_computer.db` then resolves those IDs into full document metadata, source locations, and citation references.

### How SQLite and the Vector Database Divide Work

The vector database and SQLite serve complementary but distinct roles.

| Responsibility | Vector Database | SQLite 3 |
|---|---|---|
| Semantic similarity search | Primary | Secondary or none |
| Keyword search | Possible | Strong, especially with FTS5 |
| Document metadata | Minimal | Primary |
| Chunk boundaries | Minimal | Primary |
| Citation provenance | Minimal | Primary |
| Session state | None | Primary |
| Conversation history | None | Primary |
| Ingestion job state | None | Primary |
| Deep Dive research state | None | Primary |
| Vector ID to chunk mapping | Stores vectors | Stores relational mapping |
| User preferences | None | Primary |

In short, the vector database finds semantically relevant evidence, while SQLite explains where that evidence came from and how it fits into the user's session.

### Integration Workflow in Spock

1. **Query Vectorization:**  
   The user's prompt is embedded using the same model that processed the knowledge base. This produces a query vector in the same semantic space as the stored document chunks.

2. **Retrieval:**  
   The vector database returns the top-k most relevant chunks, ranked by semantic similarity. Depending on the query, Spock may also apply keyword filters or full-text search to improve precision.

3. **Metadata Resolution:**  
   The retrieved chunk IDs are used to query `ship_computer.db` for document names, file paths, page numbers, sections, tables, cells, and other provenance details.

4. **Context Assembly:**  
   Retrieved chunks are formatted into a structured context window, complete with source metadata pulled from `ship_computer.db`. The context is ordered and trimmed to fit the generative model's context window.

5. **Generation:**  
   The assembled context and original prompt are sent to the generative LLM, such as a local model served by `llama-server`. The model synthesizes an answer grounded in the retrieved evidence.

6. **Citation Attachment:**  
   If the response includes claims derived from retrieved chunks, Spock can attach citations using the source metadata stored in SQLite.

7. **Persistence:**  
   The prompt, response, retrieved chunks, similarity scores, model parameters, and citation references are written back to `ship_computer.db`.

8. **Feedback Loop:**  
   User interactions and retrieval accuracy metrics can be logged to the SQLite database, enabling future tuning of chunk sizes, similarity thresholds, top-k values, and model parameters.

This separation of concerns ensures that the embedding model handles semantic understanding, the vector database manages scalable retrieval, and the generative LLM focuses exclusively on coherent, context-aware response synthesis.
## Environment / config

- Primary configuration is persisted in the SQLite 3 database `ship_computer.db` through the `WarpCore.settings_store` module. Settings are organized into logical namespaces, including `scan.*` (scanning parameters), `app.*` (application behavior), and `secrets` (sensitive credentials).
- Optional configuration overlays can be supplied via `scan_config.json` or `.env` files. These overlay files are automatically excluded from version control via `.gitignore`.
- Key environment variables include the following:

| Variable | Purpose |
| --- | --- |
| `EMBEDDINGS_URL` | Base URL for the embedding endpoint used by the application, such as a local or remote OpenAI-compatible service. |
| `EMBEDDINGS_DIM` | Expected vector dimensionality. This value must match both the selected embedding model and the database schema constraints. |
| `HF_TOKEN` | Hugging Face authentication token required for accessing gated models or private datasets. |
| `SPOCK_EMBED_MODEL_PATH` | Local filesystem path to a pre-downloaded embedding model, used when offline inference or custom model loading is required. |
| `PYTHONUNBUFFERED` | When set, disables Python stdout/stderr buffering so log output is rendered immediately in real time. |

### Raw scan excerpt

The following excerpt demonstrates how the aggregate `requirements.txt` resolves the full runtime tier and documents opt-in dependencies that are not installed by default.

```text
--- requirements.txt ---
# Aggregate of the tiers bootstrap installs. `pip install -r requirements.txt`
# still gives you a complete runtime.
#
#   requirements-ui.txt    Phase A - PyQt6 menu only
#   requirements-full.txt  Phase B - extractors, ingest, WebEngine (+ MCP)
#   requirements-mcp.txt   MCP server, pulled in by the full tier
#
# Opt-in, never auto-installed: requirements-ocr.txt (needs the Tesseract
# binary), requirements-dev.txt (pytest), requirements-docs.txt (system 3.12).
-r requirements-full.txt
```

## Evidence

- `D:\Spock-Universal-AI-Wiki\docs\codebase\.codebase-scan.txt`
- Filters: `.gitignore`, `scan.skip_dirs`, and built-in exclusion extras

The scan excluded common generated, dependency, cache, build, and virtual-environment directories to focus the evidence on source code, configuration, documentation, and requirement files.

## SQLite 3 `ship_computer.db` Architecture & Query Routing

The `ship_computer.db` file serves as the centralized state and configuration repository for the Spock application. It is managed through `WarpCore.settings_store`, which abstracts direct SQL operations into a namespace-aware key-value interface. The database schema typically includes a primary settings table, conversation history logs, scan result caches, and vector metadata indexes.

In this architecture, SQLite is the system of record for application state, while the vector database is the retrieval engine for semantic search. SQLite stores the metadata needed to locate, validate, and reuse vector records, such as chunk identifiers, document hashes, embedding model identifiers, dimensionality, timestamps, and source provenance. This separation allows Spock to keep configuration, audit data, and cache state in a lightweight local database while delegating high-dimensional similarity search to the vector store.

### Interaction with "Ask AI" Inquiries

"Ask AI" operates as a lightweight, conversational interface optimized for speed and context continuity. When a user submits a query:

1. **Configuration Resolution:** `WarpCore` reads the `app.*` and `secrets` namespaces to validate API keys, model endpoints, and safety filters.
2. **Context Retrieval:** The application executes parameterized queries against the conversation history table to fetch recent exchanges, ensuring the LLM receives a coherent prompt window without exceeding token limits.
3. **Semantic Retrieval (when enabled):** If the query requires external knowledge, Spock embeds the user prompt using the configured embedding model and queries the vector database for relevant chunks. SQLite supplies the chunk metadata, source references, and cache status used to assemble the final context.
4. **State Persistence:** Responses and user feedback are written back to the database using ACID-compliant transactions. This guarantees that conversational state remains consistent even if the application restarts or encounters transient network failures.
5. **Overlay Application:** If `scan_config.json` or `.env` files are present, their values override default database entries at runtime, allowing developers to test configurations without modifying the persistent store.

### Interaction with "Deep Dive" Inquiries

"Deep Dive" is a resource-intensive mode designed for comprehensive document analysis, multi-source synthesis, and detailed technical retrieval. Its interaction with `ship_computer.db` differs significantly:

1. **Metadata & Chunk Indexing:** Deep Dive queries leverage indexed tables that store document metadata, extraction timestamps, and content chunk boundaries. The `scan.*` namespace dictates filtering rules, such as date ranges, source types, and confidence thresholds.
2. **Caching & Deduplication:** To prevent redundant processing, the database maintains a hash-based cache of previously analyzed documents. When a Deep Dive is initiated, Spock checks this cache first; if the content is unchanged, it retrieves pre-computed results instead of re-running extractors.
3. **Transaction Isolation:** Heavy read/write operations during Deep Dive sessions use SQLite transaction isolation to reduce lock contention with concurrent "Ask AI" requests. When WAL mode is enabled, readers and writers can operate concurrently, helping keep the UI responsive while background analysis proceeds.
4. **Result Aggregation:** Structured findings, citations, and confidence scores are serialized into JSON blobs within the database, enabling rapid retrieval and rendering in the PyQt6/WebEngine interface.

### Embedding LLM and Vector Database Integration

The Spock application uses an embedding model to convert text into fixed-length numerical vectors. These vectors represent semantic meaning in a high-dimensional space, allowing the application to find similar passages, documents, or chunks by measuring vector distance or similarity.

The embedding workflow is configured through the environment variables described above:

- `EMBEDDINGS_URL` identifies the embedding service endpoint.
- `EMBEDDINGS_DIM` defines the expected vector size.
- `HF_TOKEN` provides authentication when the model or dataset is gated.
- `SPOCK_EMBED_MODEL_PATH` allows Spock to load a local embedding model for offline or custom inference.

When Spock processes content for "Ask AI" or "Deep Dive", it follows this general flow:

1. **Text Preparation:** Raw documents, scan results, or user prompts are normalized, chunked, and filtered according to `scan.*` settings.
2. **Embedding Generation:** Each chunk or query is sent to the configured embedding endpoint or local model. The resulting vector must match `EMBEDDINGS_DIM`; otherwise, Spock should reject or re-embed the content to avoid schema mismatches.
3. **Vector Storage:** The vector is stored in the vector database together with a stable identifier, such as a chunk ID or document hash. The vector database is responsible for efficient similarity search, such as nearest-neighbor or cosine-similarity queries.
4. **Metadata Persistence:** SQLite stores the corresponding metadata, including source path, extraction timestamp, chunk boundaries, embedding model identifier, vector dimensionality, content hash, and cache status. This metadata lets Spock validate that a vector is still relevant, reusable, and compatible with the current configuration.
5. **Query Execution:** For a user question, Spock embeds the question using the same embedding model and queries the vector database for the most similar chunks. The returned chunk IDs are then resolved against SQLite metadata to retrieve citations, source context, and confidence information.
6. **Answer Synthesis:** The retrieved context is assembled into a prompt for the LLM. The LLM generates the final answer, while SQLite records the query, retrieved chunks, response, and any user feedback for auditability and future context.

This design keeps the vector database focused on similarity search and the SQLite database focused on durable application state. It also allows Spock to support both fast conversational queries and deeper analytical workflows without duplicating configuration, cache, or provenance data.
## Embedding LLM & Vector Database Integration

Spock utilizes a hybrid embedding pipeline that bridges natural language understanding with high-dimensional vector storage. This architecture enables semantic search, context retrieval, and intelligent routing for both inquiry modes.

### Embedding Generation Pipeline
1. **Model Selection:** The application dynamically selects an embedding model based on environment configuration. If `SPOCK_EMBED_MODEL_PATH` is defined, Spock loads the model locally using frameworks such as `sentence-transformers` or `ONNX Runtime`. Otherwise, it routes requests to the remote endpoint specified in `EMBEDDINGS_URL`.
2. **Dimensionality Validation:** Before ingestion, the system verifies that the generated vectors match `EMBEDDINGS_DIM`. Mismatches trigger a graceful fallback, re-embedding with a compatible model, or schema migration to prevent vector alignment errors during similarity searches.
3. **Text Chunking & Normalization:** Raw documents and user queries are tokenized, chunked into optimal window sizes, and normalized to preserve semantic meaning while minimizing noise.

### Vector Storage & Retrieval
Spock leverages a SQLite-backed vector database extension, such as `sqlite-vec` or a custom FTS/vector hybrid, to store embeddings alongside metadata. This approach maintains the application's single-database footprint while enabling high-performance semantic operations.

- **Indexing:** Vectors are stored in dedicated tables with approximate nearest neighbor indexes, such as HNSW or IVF, when supported by the selected vector extension. If ANN indexing is unavailable, Spock falls back to exact KNN search over stored vectors.
- **Similarity Search:** When a query is submitted, it is embedded using the same model as the corpus. The vector database executes a cosine similarity or Euclidean distance search to retrieve the top-k most relevant chunks.
- **Context Assembly:** Retrieved chunks are ranked, deduplicated, and assembled into a structured context window. This context is injected into the LLM prompt, enabling accurate, source-grounded responses.

### Integration with Inquiry Modes
- **Ask AI:** Uses a lightweight vector search focused on conversational history and frequently accessed knowledge bases. The retrieval window is narrow, prioritizing low latency and immediate feedback.
- **Deep Dive:** Triggers a multi-stage vector search across the entire indexed corpus. It applies advanced filtering, including metadata constraints, source weighting, and temporal decay, and aggregates results from multiple semantic clusters. The vector database returns a comprehensive context package that the LLM synthesizes into detailed, citation-rich reports.

This tightly coupled architecture ensures that configuration, state, and semantic retrieval operate within a unified, transaction-safe environment, minimizing external dependencies while maximizing analytical depth.

### SQLite 3 `ship_computer.db` Integration

Spock stores all persistent application state in a single SQLite 3 database file named `ship_computer.db`. This file serves as the local system of record for configuration, conversation history, document metadata, embeddings, search logs, and Deep Dive artifacts. By keeping semantic retrieval, user state, and application metadata in one SQLite database, Spock can operate with minimal external infrastructure while preserving transactional consistency.

#### Primary Responsibilities

`ship_computer.db` is responsible for:

- Storing application settings and environment-specific configuration.
- Tracking user conversations and message history for Ask AI and Deep Dive sessions.
- Maintaining document metadata, including source, title, hash, creation time, and update time.
- Storing text chunks that are eligible for semantic search.
- Storing embedding vectors and the model metadata required to validate vector compatibility.
- Supporting full-text search and hybrid retrieval through SQLite FTS or a vector/FTS hybrid.
- Recording search queries, retrieved chunks, latency, and retrieval mode for auditability.
- Persisting Deep Dive reports, citations, and generated analytical artifacts.

#### Representative Schema

The following tables represent the core data structures used by Spock. The exact schema may vary by deployment, but the responsibilities remain consistent.

| Table | Contents | Role in Spock |
|---|---|---|
| `app_settings` | Key-value configuration entries | Stores runtime settings, model paths, retrieval limits, and feature flags. |
| `conversations` | Conversation identifiers, user identifiers, inquiry mode, timestamps | Tracks Ask AI and Deep Dive sessions. |
| `messages` | User and assistant messages, roles, content, timestamps | Preserves conversational context for follow-up questions. |
| `documents` | Source documents, titles, paths, hashes, metadata | Provides provenance and filtering context for retrieved chunks. |
| `chunks` | Text chunks, chunk index, token count, document reference | Stores the searchable units used for semantic retrieval. |
| `embeddings` | Vector data, model name, dimensions, chunk reference | Stores embedding vectors and validates model compatibility. |
| `fts_chunks` | Full-text search index over chunks | Supports keyword search and hybrid retrieval. |
| `search_logs` | Query text, query vector, retrieved chunk IDs, latency, mode | Provides auditability and performance observability. |
| `deep_dive_reports` | Generated report content, conversation reference, timestamps | Persists Deep Dive outputs for review and reuse. |
| `citations` | Report references, chunk IDs, document IDs, relevance score | Links generated claims to source chunks and documents. |

#### Ask AI Interaction

When a user submits an Ask AI inquiry, Spock uses `ship_computer.db` to assemble a fast, context-aware response.

1. **Session Lookup:** Spock reads the active conversation from `conversations` and recent messages from `messages`.
2. **Configuration Load:** Spock retrieves relevant settings from `app_settings`, such as retrieval limits, preferred sources, and model configuration.
3. **Query Embedding:** The user query is converted into an embedding vector using the configured embedding model.
4. **Limited Retrieval:** Spock performs a constrained vector search against `embeddings`, optionally combined with full-text search from `fts_chunks`.
5. **Metadata Join:** Retrieved chunk IDs are joined to `chunks` and `documents` to recover source metadata, titles, and relevance context.
6. **Context Construction:** Spock assembles a compact prompt context from the most relevant chunks and recent conversation history.
7. **Response Persistence:** The assistant response is written back to `messages`, and the retrieval operation is recorded in `search_logs`.

This interaction pattern favors low latency and conversational continuity. Ask AI typically searches a narrower subset of the corpus, such as recent documents, pinned sources, or frequently accessed knowledge bases.

#### Deep Dive Interaction

When a user requests a Deep Dive inquiry, Spock uses `ship_computer.db` to perform a broader, more analytical retrieval process.

1. **Report Initialization:** Spock creates a new record in `deep_dive_reports` to track the inquiry.
2. **Broad Vector Search:** Spock searches the full indexed corpus in `embeddings`, not just recent or frequently accessed chunks.
3. **Hybrid Retrieval:** Spock may combine vector similarity with full-text search from `fts_chunks` to capture both semantic and keyword relevance.
4. **Metadata Filtering:** Results are filtered using `documents` metadata, such as source type, date range, author, classification, or topic.
5. **Ranking and Aggregation:** Spock applies source weighting, temporal decay, and cluster aggregation to produce a coherent evidence set.
6. **Citation Capture:** Relevant chunks and documents are recorded in `citations` so that generated claims can be traced back to source material.
7. **Report Persistence:** The final report, citations, and search metadata are stored in `deep_dive_reports`, `citations`, and `search_logs`.

This interaction pattern favors depth, traceability, and analytical completeness over immediate response speed.

#### Transaction and Concurrency Model

Because Spock is built around SQLite 3, `ship_computer.db` provides a simple, embedded, file-based storage model. Spock typically uses SQLite in WAL mode to allow concurrent reads while writes are serialized. This is important because Ask AI and Deep Dive operations may read conversation history, document metadata, and embeddings while other operations write new messages, reports, or search logs.

The database layer enforces:

- Atomic writes for messages, reports, and search logs.
- Foreign-key relationships between conversations, messages, documents, chunks, and citations.
- Consistent reads during retrieval operations.
- Safe fallback behavior when vector dimensions or model metadata do not match.
- Auditability through `search_logs` and citation records.

### Full Explanation: How Spock Uses the Embedding LLM and Vector Database

Spock uses an embedding model, often referred to in this architecture as the embedding LLM, to convert natural language text into numerical vectors. These vectors represent semantic meaning in a high-dimensional space, allowing Spock to compare user queries against stored document chunks using mathematical similarity rather than exact keyword matching.

The embedding model is not the same as the generative LLM that produces final answers. Its role is to encode text into a consistent numerical representation. The generative LLM then uses the retrieved context to produce a natural language response.

#### Ingestion Workflow

When Spock indexes a document or knowledge source, it performs the following steps:

1. **Document Intake:** The source document is registered in `documents` with metadata such as title, source path, hash, and creation time.
2. **Chunking:** The document is split into smaller chunks that are large enough to preserve meaning but small enough to retrieve efficiently.
3. **Normalization:** Text is cleaned and normalized to reduce noise while preserving semantic content.
4. **Embedding:** Each chunk is passed to the configured embedding model, producing a fixed-size vector.
5. **Validation:** Spock verifies that the vector dimension matches `EMBEDDINGS_DIM` and that the model name is compatible with existing stored vectors.
6. **Storage:** The vector, chunk text, document reference, and model metadata are stored in `ship_computer.db`.
7. **Indexing:** If available, Spock updates vector indexes or full-text indexes to improve retrieval performance.

#### Query Workflow

When a user submits a question, Spock follows a retrieval-augmented generation workflow.

1. **Query Normalization:** The user query is cleaned and prepared for embedding.
2. **Query Embedding:** The query is converted into a vector using the same embedding model used for the corpus.
3. **Similarity Search:** Spock searches the vector database for chunks whose embeddings are closest to the query vector.
4. **Hybrid Scoring:** Spock may combine vector similarity with full-text search scores, metadata relevance, recency, and source trust.
5. **Deduplication:** Similar or overlapping chunks are merged to avoid redundant context.
6. **Context Assembly:** The highest-scoring chunks are ordered and formatted into a prompt context.
7. **LLM Generation:** The generative LLM receives the user query, conversation history, and retrieved context, then produces a grounded response.
8. **Persistence:** The response, retrieved chunks, and search metadata are written back to `ship_computer.db`.

#### Ask AI vs. Deep Dive Retrieval

Ask AI and Deep Dive use the same underlying embedding and vector database infrastructure, but they differ in retrieval scope and optimization goals.

- **Ask AI** optimizes for speed and conversational relevance. It typically searches recent context, pinned sources, and high-frequency knowledge chunks. The goal is to answer quickly with enough context to feel natural and accurate.
- **Deep Dive** optimizes for completeness and analytical depth. It searches the broader corpus, applies stricter metadata filters, aggregates multiple semantic clusters, and preserves citations. The goal is to produce a detailed, source-grounded report.

#### Why SQLite Is Sufficient for This Design

Using SQLite 3 for `ship_computer.db` allows Spock to keep the entire semantic retrieval stack local and self-contained. The same database file can store configuration, conversation state, document metadata, embeddings, full-text indexes, search logs, and generated reports. This reduces operational complexity, avoids external vector database dependencies, and makes the system easier to deploy, back up, and audit.

The key architectural benefit is that Spock can perform semantic search, maintain conversational state, and persist analytical artifacts within one transaction-safe storage layer. This makes the embedding pipeline, vector database, and application state tightly integrated rather than loosely coupled across multiple services.