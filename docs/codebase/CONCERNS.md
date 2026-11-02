# Concerns

## Concerns (deterministic)

- No `TODO`, `FIXME`, or `HACK` markers were detected in the filtered scan.

### High-churn files (git, filtered)

```text
3 EngineeringDeck/ask_panel.py
   3 ScienceStation/wiki_run.py
   3 spock_wiki_adapter/wiki_run.py
   3 AIHelperDocuments/Spock-Navigation-Station-HELPER.md
   3 NavigationStation/app.py
   3 model_selector/launch_panel.py
   3 starfleet_universal_extractor.py
   2 spock_bringup_menu/acquire_dialog.py
   2 spock_progress_log/panel.py
   2 spock_shell/busy_ui.py
   2 AIHelperDocuments/How does Ask AI and Deep Dive work in Spock  How can I tune the context size.md
   2 ScienceStation/app.py
   2 ScienceStation/ships_logs.py
   2 db_maintenance.py
   2 deep_dive.py
```

## Filter note

TODO markers within excluded directories (`data/`, `models/`, etc., as defined by `.gitignore` and `scan.skip_dirs`) are omitted to prevent large `llama.cpp` model binaries and cached artifacts from skewing the results.

### Raw scan excerpt

```text
spock_codebase_knowledge\populate.py:140: rows.append((rel, purpose.get(item.name, "[TODO]"), f"`{item.name}`"))
...
```

## Evidence

- `D:\Spock-Universal-AI-Wiki\docs\codebase\.codebase-scan.txt`
- Filters: `.gitignore` + `scan.skip_dirs` + built-in extras

## Terminology notes

- **Deterministic**: This section was produced by a repeatable scanning process. Given the same repository state, scanner version, and filter configuration, it will consistently produce the same concerns list rather than relying on nondeterministic model generation or sampling.
- **High-churn files**: Files that have been modified frequently in Git history. High churn can indicate active development, instability, or areas where behavior changes often; it serves as a heuristic for prioritizing review, not as proof of defects.
- **Filtered scan**: The scanner excluded directories listed by `.gitignore`, `scan.skip_dirs`, and built-in extras before reporting `TODO`/`FIXME` hits or file statistics. This prevents generated artifacts, caches, dependencies, and large model/data blobs from dominating the results.
- **Raw scan excerpt**: A short, unprocessed sample of what the scanner observed in a source file. It is shown as evidence that the scanner can detect `TODO`-like markers, but it does not imply that every line in the excerpt represents an unresolved concern.
- **llama.cpp blobs**: Large binary or model-related files associated with `llama.cpp`. They are skipped because they often contain repeated strings and would artificially inflate `TODO`/`FIXME` counts.

## Concerns (deterministic)

> **What “deterministic” means here:** This section was generated automatically by the `acquire_codebase_knowledge` script using a fixed, reproducible rule set (“deterministic fill”). No manual curation was applied; given the same scan input and configuration, it will always produce the same output.

- The filtered concern list reports no actionable `TODO`, `FIXME`, or `HACK` markers in the reviewed source set.

> **What “filtered scan” means:** The scanner walks the repository but excludes directories listed in `.gitignore`, the `scan.skip_dirs` configuration, and a set of built-in extras (for example, `.cache`, `node_modules`, and `__pycache__`). Only files outside those excluded trees are searched for marker comments.

### Summary versus raw evidence

The filtered concern list is intended to highlight actionable review targets in first-party source code. The later “Raw scan excerpt” preserves unprocessed scanner output and may therefore still contain `[TODO]` placeholder strings, scanner internals, or diagnostic text that is not treated as an actionable concern.

### High-churn files (git, filtered)

> **What “high-churn” means:** Churn is a software-engineering metric that describes how frequently a file is modified in version control. The number shown before each path is the count of commits that touched that file during the scan window. Higher churn can indicate active development, instability, or frequent refactoring, making those files useful review targets.

```text
3 EngineeringDeck/ask_panel.py
   3 ScienceStation/wiki_run.py
   3 spock_wiki_adapter/wiki_run.py
   3 AIHelperDocuments/Spock-Navigation-Station-HELPER.md
   3 NavigationStation/app.py
   3 model_selector/launch_panel.py
   3 starfleet_universal_extractor.py
   2 spock_bringup_menu/acquire_dialog.py
   2 spock_progress_log/panel.py
   2 spock_shell/busy_ui.py
   2 AIHelperDocuments/How does Ask AI and Deep Dive work in Spock  How can I tune the context size.md
   2 ScienceStation/app.py
   2 ScienceStation/ships_logs.py
   2 db_maintenance.py
   2 deep_dive.py
```

## SQLite 3 `ship_computer.db`

`ship_computer.db` is the local SQLite 3 database used by the Spock application as its primary structured state store. It provides persistent, transactional storage for application metadata, user sessions, configuration, research artifacts, and audit trails.

In the context of **Ask AI** and **Deep Dive** inquiries, `ship_computer.db` is not primarily responsible for semantic search. Instead, it acts as the system of record for:

- user questions and assistant responses,
- Deep Dive run state and intermediate steps,
- retrieved evidence references,
- model and prompt configuration,
- document and chunk metadata,
- application logs and maintenance events,
- resumable workflow state.

The vector database, by contrast, is optimized for similarity search over embedded text. `ship_computer.db` stores the structured facts about what was asked, what was retrieved, what was generated, and how the process progressed.

### Role in Ask AI

Ask AI is the interactive question-and-answer surface of Spock. When a user submits an inquiry, the application typically performs the following steps:

1. **Normalize the request**
   - Trim and validate the user question.
   - Resolve the active workspace, project, or document scope.
   - Apply any user-selected filters, such as source type, date range, or document category.

2. **Load configuration**
   - Read model settings, context limits, retrieval settings, and prompt templates from `ship_computer.db` or related configuration tables.

3. **Retrieve relevant context**
   - Convert the user question into an embedding using the embedding model.
   - Query the vector database for the most relevant chunks.
   - Optionally rerank or filter results using metadata stored in `ship_computer.db`.

4. **Generate the answer**
   - Assemble a prompt from the user question, retrieved context, and system instructions.
   - Send the prompt to the selected language model.
   - Return the generated answer to the user.

5. **Persist the interaction**
   - Store the user question, assistant response, model used, prompt metadata, retrieved chunk identifiers, and timestamps in `ship_computer.db`.

This persistence allows Spock to support conversation history, answer auditing, debugging, and later review of why a particular answer was produced.

### Role in Deep Dive

Deep Dive is a more extensive research workflow than a single Ask AI question. It is designed for multi-step investigation, where Spock may need to:

- break a broad question into subquestions,
- retrieve evidence from multiple sources,
- summarize intermediate findings,
- identify gaps,
- refine the search,
- produce a final structured report.

`ship_computer.db` supports this workflow by storing the state of each Deep Dive run. A typical Deep Dive record may include:

- the original user request,
- the generated research plan,
- each step executed,
- the subquestions asked,
- the chunks or documents retrieved at each step,
- intermediate summaries,
- final report content,
- model and prompt versions,
- timing and status information.

This makes Deep Dive resumable and inspectable. If a run is interrupted, Spock can reload the last completed step from `ship_computer.db` and continue without losing prior work.

### Representative tables

The exact schema may vary by implementation, but a typical `ship_computer.db` used by Spock may contain tables such as the following:

- `ask_ai_sessions`
  - Stores one row per Ask AI conversation.
  - Tracks session start time, active workspace, model, and status.

- `ask_ai_messages`
  - Stores individual user and assistant messages.
  - Includes message role, content, model, token counts, and timestamps.

- `retrieval_events`
  - Records each retrieval operation.
  - Stores query text, embedding model, vector database query parameters, and retrieved chunk identifiers.

- `deep_dive_runs`
  - Stores one row per Deep Dive investigation.
  - Tracks the original question, status, start time, completion time, and final report location.

- `deep_dive_steps`
  - Stores each step in a Deep Dive workflow.
  - Includes step order, subquestion, retrieved evidence, summary, and status.

- `document_registry`
  - Tracks documents known to Spock.
  - Stores source path, document type, hash, last modified time, and ingestion status.

- `chunk_registry`
  - Tracks text chunks derived from documents.
  - Stores chunk text or chunk hash, source document, chunk index, and vector identifier.

- `model_settings`
  - Stores selected models, embedding model, context size, temperature, and prompt settings.

- `application_logs`
  - Stores operational logs, warnings, and maintenance events.

### Typical Ask AI data flow

A simplified Ask AI flow using `ship_computer.db` and the vector database is:

```text
User question
    |
    v
Spock application
    |
    |-- Load settings from ship_computer.db
    |-- Embed question using embedding model
    |-- Query vector database for similar chunks
    |-- Retrieve chunk metadata from ship_computer.db
    |-- Assemble prompt
    |-- Generate answer with language model
    |-- Store question, answer, and retrieval trace in ship_computer.db
    v
Answer returned to user
```

### Typical Deep Dive data flow

A simplified Deep Dive flow is:

```text
User research request
    |
    v
Spock application
    |
    |-- Create deep_dive_runs row in ship_computer.db
    |-- Generate research plan
    |-- For each step:
    |       |-- Create deep_dive_steps row
    |       |-- Embed subquestion
    |       |-- Query vector database
    |       |-- Store retrieved chunk references
    |       |-- Generate intermediate summary
    |       |-- Update step status
    |-- Generate final report
    |-- Mark run complete in ship_computer.db
    v
Deep Dive report returned to user
```

### Operational notes

Because `ship_computer.db` is a SQLite 3 database, it is well suited to local, file-based, low-overhead persistence. Spock can use it without requiring a separate database server.

Common operational practices include:

- enabling WAL mode for better concurrent read/write behavior,
- using transactions when writing multi-step Deep Dive state,
- storing content hashes to detect changed documents,
- using foreign keys to keep sessions, messages, and retrieval events consistent,
- periodically running integrity checks and maintenance tasks,
- retaining enough metadata to reproduce or audit an Ask AI or Deep Dive result.

## Embedding LLM and vector database

Spock uses an embedding model, often referred to in this context as the **embedding LLM**, to convert text into numerical vectors. These vectors are stored in a **vector database**, which enables fast similarity search over large collections of text.

This mechanism is central to both Ask AI and Deep Dive. It allows Spock to find relevant passages, code excerpts, wiki entries, logs, or research notes without requiring the user to know the exact wording of the source material.

### What the embedding LLM does

An embedding model maps text into a high-dimensional numerical space. Similar meanings tend to produce vectors that are close together, while unrelated meanings tend to produce vectors that are farther apart.

For example:

- “How do I tune the context size?”
- “What settings control prompt length?”
- “How can I increase the amount of context passed to the model?”

These phrases may not share many exact words, but their embeddings may be close enough for the vector database to retrieve them as related.

The embedding model is different from the generative language model used to produce answers. The embedding model is primarily used for:

- indexing text,
- representing semantic meaning numerically,
- enabling similarity search.

The generative model is used for:

- answering questions,
- summarizing evidence,
- producing Deep Dive reports.

### What the vector database stores

The vector database stores the numerical embeddings and the metadata needed to retrieve and cite the original text. A typical vector record may include:

- vector identifier,
- embedded text or chunk text,
- source document path,
- document type,
- chunk index,
- content hash,
- timestamp,
- workspace or project identifier,
- embedding model name,
- embedding dimension,
- optional metadata such as tags, author, or category.

The vector database is optimized for approximate nearest-neighbor search. Given a query vector, it can quickly return the most similar stored vectors.

### How Spock uses the embedding LLM and vector database

The overall process has two main phases: **indexing** and **retrieval**.

#### Indexing phase

When Spock ingests a document, wiki page, code file, log, or research artifact, it may perform the following steps:

1. **Read the source content**
   - Spock reads the file or content source.
   - It records the source path, type, and modification time.

2. **Chunk the content**
   - Long documents are split into smaller chunks.
   - Chunking may be based on character count, token count, headings, paragraphs, or semantic boundaries.

3. **Embed each chunk**
   - Each chunk is passed to the embedding model.
   - The model produces a vector representation of the chunk.

4. **Store the vector and metadata**
   - The vector is written to the vector database.
   - The chunk text, source metadata, and identifiers are stored in `ship_computer.db` or associated metadata tables.

5. **Track ingestion state**
   - Spock records whether the document was successfully indexed.
   - It may store content hashes so unchanged documents are not re-embedded unnecessarily.

#### Retrieval phase

When a user asks a question through Ask AI or initiates a Deep Dive, Spock performs the following steps:

1. **Embed the query**
   - The user question or subquestion is converted into a vector using the same embedding model used during indexing.

2. **Search the vector database**
   - Spock queries the vector database for the nearest neighbors.
   - It may request a configurable number of results, such as top 5, top 10, or top 20.

3. **Apply filters**
   - Results may be filtered by workspace, document type, date, source path, or other metadata.

4. **Rerank or score results**
   - Spock may use similarity scores, metadata relevance, or a reranking model to improve result quality.

5. **Assemble context**
   - The selected chunks are combined into a prompt context.
   - Spock must respect the context window limit of the selected language model.

6. **Generate a response**
   - The generative language model uses the retrieved context to answer the question or produce a Deep Dive section.

7. **Record the retrieval trace**
   - The query, retrieved chunk identifiers, scores, and model settings are stored in `ship_computer.db` for auditability.

### Ask AI usage pattern

Ask AI is optimized for fast, direct answers. Its retrieval strategy usually favors:

- low latency,
- a small number of highly relevant chunks,
- strict context limits,
- clear citations or source references.

A typical Ask AI retrieval configuration may include:

- top-k retrieval size,
- maximum context tokens,
- minimum similarity threshold,
- source filters,
- prompt template,
- model temperature,
- maximum response length.

Ask AI may use a single retrieval pass. For example:

```text
User: How can I tune the context size in Spock?

Spock:
1. Embed the question.
2. Retrieve the five most relevant chunks.
3. Filter chunks to documentation and configuration files.
4. Build a prompt with the question and retrieved chunks.
5. Generate an answer.
6. Store the question, answer, and retrieved chunk IDs.
```

### Deep Dive usage pattern

Deep Dive is optimized for thoroughness rather than speed. It may use multiple retrieval passes, each focused on a different aspect of the research question.

A Deep Dive workflow may include:

- initial broad retrieval,
- extraction of key themes,
- generation of follow-up subquestions,
- targeted retrieval for each subquestion,
- comparison of evidence,
- identification of contradictions or gaps,
- synthesis of a final report.

For example:

```text
User: Explain how Ask AI and Deep Dive work in Spock and how context size can be tuned.

Deep Dive:
1. Retrieve general documentation about Ask AI.
2. Retrieve documentation about Deep Dive.
3. Retrieve configuration files related to context size.
4. Retrieve code files that assemble prompts.
5. Summarize each area.
6. Identify where context limits are enforced.
7. Produce a structured report with citations.
```

Because Deep Dive may retrieve many chunks, it must manage context carefully. It may summarize intermediate results before passing them to the final answer model, reducing the amount of raw text that must fit into the final prompt.

### Relationship between `ship_computer.db` and the vector database

The two storage systems have different responsibilities.

| Component | Primary responsibility | Typical contents |
|---|---|---|
| `ship_computer.db` | Structured application state | sessions, messages, runs, steps, settings, logs, metadata |
| Vector database | Semantic similarity search | embeddings, chunk text, vector metadata |

In practice, they work together:

- The vector database finds relevant text.
- `ship_computer.db` records what was found, why it was found, and how it was used.
- The generative language model produces the final answer or report.
- The embedding model supports both indexing and query-time retrieval.

### Context size and retrieval tuning

Context size is one of the most important tuning areas for Ask AI and Deep Dive. It affects answer quality, latency, cost, and reliability.

Key tuning parameters include:

- **Chunk size**
  - Smaller chunks can be more precise but may lack surrounding context.
  - Larger chunks provide more context but may include irrelevant material.

- **Top-k retrieval count**
  - A higher top-k value retrieves more candidates.
  - A lower top-k value reduces noise and prompt size.

- **Similarity threshold**
  - A higher threshold returns only very similar chunks.
  - A lower threshold may include more diverse but less relevant results.

- **Maximum context tokens**
  - This limits how much retrieved text can be included in the prompt.
  - It must remain within the selected model’s context window.

- **Reranking**
  - Reranking can improve precision by reordering retrieved chunks before prompt assembly.

- **Source filters**
  - Restricting retrieval to specific document types or workspaces can improve relevance.

- **Summarization depth**
  - Deep Dive may summarize intermediate evidence to keep the final prompt manageable.

### Embedding model consistency

For reliable retrieval, Spock should use the same embedding model for indexing and querying. If the embedding model changes, previously stored vectors may no longer be comparable to new query vectors. In that case, Spock may need to re-embed indexed content or maintain separate vector collections for different embedding models.

### Local and offline operation

Because Spock is described as a Python and SQLite application, it is likely designed to operate locally. This means:

- `ship_computer.db` can be a local file,
- the vector database can be local or embedded,
- the embedding model can run locally,
- the generative model can run locally or through a configured endpoint.

This local architecture supports privacy, reproducibility, and offline use, while still allowing Spock to perform semantic search and AI-assisted research.
## ship_computer.db Architecture and Query Routing

`ship_computer.db` is a SQLite 3 database that serves as the persistent state layer for the Spock application. It is configured to run in Write-Ahead Logging (WAL) mode to support concurrent read/write operations without locking the entire database during active AI inference or document indexing.

The database stores relational metadata, query history, session state, configuration, and references to vector artifacts. It is not the primary vector index itself; instead, it provides durable, transactional context around vector search, LLM workflows, and Deep Dive research state.

### Core Schema Components
- **`queries`**: Stores user prompts, timestamps, routing flags (`ask_ai` vs `deep_dive`), and associated session IDs.
- **`documents`**: Contains metadata for ingested wiki pages, ship logs, and research artifacts, including file paths, chunk boundaries, and content hashes.
- **`embeddings_index`**: Maps document chunks to their corresponding vector identifiers and stores dimensionality, model version, and index metadata.
- **`session_state`**: Tracks multi-turn conversation context, intermediate research steps, and cached LLM responses for Deep Dive workflows.
- **`config`**: Holds runtime parameters such as context window limits, temperature settings, and active model paths.

### SQLite 3 Storage and Concurrency Model

SQLite 3 is used as a lightweight, file-based relational store that can run locally without a separate database server. This makes it well suited for Spock’s local or embedded deployment model.

Key storage characteristics include:

- **WAL mode**: Allows readers to continue accessing the database while a writer commits changes. This is important when Spock is indexing documents, updating session state, or writing query logs while another request is being processed.
- **Single-writer model**: SQLite permits one writer at a time, but multiple readers can operate concurrently. Spock should serialize write-heavy operations such as document ingestion, embedding updates, and Deep Dive checkpoint commits.
- **Transactions**: Multi-step operations, especially Deep Dive state updates, should be wrapped in transactions so that partial failures do not leave inconsistent session state.
- **Foreign-key relationships**: The schema should enforce relationships between `queries`, `documents`, `embeddings_index`, and `session_state` to preserve referential integrity.
- **Indexes**: Frequently queried fields such as `session_id`, `query_type`, `document_id`, `chunk_id`, and `created_at` should be indexed to keep lookup latency low.

### Interaction with Ask AI

When a user initiates an **Ask AI** inquiry, the application performs a lightweight, stateless lookup:

1. The prompt is logged to the `queries` table with a `type='ask_ai'` flag.
2. The system checks the `session_state` table for recent context to maintain conversational continuity.
3. If a cached response exists for a semantically similar query, it is returned immediately to reduce latency. Exact-match caching may use a content hash, while approximate caching may use vector proximity.
4. Otherwise, the query is routed to the embedding pipeline, and the resulting context is assembled for the generative LLM.

Ask AI is optimized for fast, single-turn or lightly contextual responses. It may use recent conversation history, but it does not require the durable multi-step state machine used by Deep Dive.

### Interaction with Deep Dive

**Deep Dive** inquiries require stateful, multi-step research tracking:

1. The initial prompt creates a new `session_id` in `session_state`.
2. As the AI iterates through sub-queries, each intermediate finding, source citation, and reasoning step is persisted to `ship_computer.db`.
3. The database acts as a checkpoint system: if the application restarts or a step fails, Deep Dive resumes from the last committed state rather than re-executing completed research branches.
4. Final synthesized reports are linked back to the original `queries` record, enabling auditability and reproducibility.

Deep Dive treats `ship_computer.db` as a durable workflow store. It records not only the final answer, but also the research path that produced the answer.

### Ask AI vs Deep Dive State Management

| Workflow | State Model | Persistence Focus | Recovery Behavior |
|---|---|---|---|
| **Ask AI** | Stateless or lightly stateful | Query log, optional cache, recent context | Re-executes the request if needed |
| **Deep Dive** | Stateful and resumable | Session state, sub-queries, citations, checkpoints, final report | Resumes from last committed step |

Ask AI prioritizes low latency and simple retrieval. Deep Dive prioritizes completeness, traceability, and fault tolerance.

## Embedding LLM and Vector Database Workflow

Spock separates text representation from text generation by utilizing a dedicated embedding model alongside a vector storage layer. This architecture enables efficient semantic retrieval before any generative processing occurs.

### Embedding Model Role

The embedding LLM, more precisely an embedding model, converts unstructured text into fixed-length numerical vectors. Unlike generative models, it does not produce natural language output. Its sole responsibility is to map documents, logs, and user queries into a shared mathematical space where semantic similarity correlates with geometric proximity.

In Spock, the embedding model is used for two main purposes:

- **Document embedding**: Converts ingested wiki pages, ship logs, and research artifacts into searchable vector representations.
- **Query embedding**: Converts user prompts into vectors that can be compared against stored document vectors.

The embedding model should be stable and versioned. If the model changes, existing vectors may no longer be comparable to newly generated vectors, so Spock should track model version in `embeddings_index` and re-embed affected content when necessary.

### Vector Database Integration

Spock leverages a vector database to store and query embeddings. This may be implemented through a SQLite extension such as `sqlite-vec`, or through a lightweight standalone vector index that is referenced from `ship_computer.db`.

- **Indexing Strategy**: Vectors are organized using Approximate Nearest Neighbor (ANN) algorithms such as HNSW (Hierarchical Navigable Small World) or IVF (Inverted File Index). This allows low-latency retrieval across large chunk collections without exhaustive linear scans.
- **Distance Metric**: Cosine similarity or L2 Euclidean distance is used to rank relevance. Higher scores indicate stronger semantic alignment between the user query and stored knowledge.
- **Chunking & Metadata Filtering**: Before embedding, documents are split into logical chunks, such as paragraphs, code blocks, or log entries. Each chunk retains metadata tags that allow the vector DB to apply hybrid filtering, such as restricting results to a specific ship log date range or wiki category.

### Embedding LLM and Vector Database Relationship

The embedding model and vector database work together as a semantic retrieval layer.

1. **Ingestion**: Spock reads a document, splits it into chunks, and sends each chunk to the embedding model.
2. **Vector storage**: The resulting vectors are stored in the vector database, while chunk metadata is stored in `ship_computer.db`.
3. **Query time**: Spock embeds the user’s question using the same embedding model.
4. **Semantic search**: The vector database finds the nearest stored vectors.
5. **Metadata join**: Spock uses `ship_computer.db` to resolve vector identifiers back to document chunks, sources, citations, and metadata.

This separation allows Spock to keep relational data, session state, and vector search in distinct but coordinated layers.

### Retrieval-Augmented Generation (RAG) Pipeline

1. **Query Embedding**: The user’s prompt is passed through the embedding model to generate a query vector.
2. **Vector Search**: The vector DB retrieves the top-K most relevant document chunks based on similarity scoring.
3. **Context Assembly**: Retrieved chunks are concatenated with system prompts, conversation history, and routing instructions.
4. **Generative Inference**: The assembled context is fed to the primary LLM, which synthesizes a response grounded in the retrieved data.
5. **Caching & Feedback**: Successful retrievals and responses are optionally logged back to `ship_computer.db` to improve future latency and enable query optimization.

### Ingestion and Query Path

The full Spock retrieval path can be summarized as follows:

**Ingestion path**

1. Source document is registered in `documents`.
2. Document is chunked into logical units.
3. Each chunk is embedded by the embedding model.
4. Vector identifiers, dimensions, and model version are recorded in `embeddings_index`.
5. Chunk metadata, such as source path, date range, category, and content hash, is stored in SQLite.

**Query path**

1. User prompt is recorded in `queries`.
2. Prompt is embedded using the same embedding model used for ingestion.
3. Vector database performs ANN search over stored chunk vectors.
4. Results are filtered using metadata from `ship_computer.db`.
5. Relevant chunks are assembled into a prompt context.
6. Generative LLM produces the final answer.
7. For Deep Dive, intermediate steps and final report are persisted for auditability and resumability.

This separation of concerns ensures that Spock maintains low memory overhead, scales efficiently with growing knowledge bases, and provides traceable, source-grounded answers for both quick inquiries and complex research tasks.
## Filter note

Markers under skipped trees (`data/`, `models/`, … from `.gitignore` / `scan.skip_dirs`) are omitted so large vendored artifacts—such as llama.cpp model blobs—do not dominate the report.

> **Why the filter matters:** Large binary or generated directories (for example, `data/` and `models/`, which may contain llama.cpp files) can produce many false-positive marker hits from embedded, generated, or third-party code. Excluding them keeps the concerns list focused on first-party source code.

### Raw scan excerpt

> **What this excerpt shows:** The lines below are unprocessed scanner output listing places where `TODO`, `FIXME`, or `HACK` appear. Many hits are inside the `spock_codebase_knowledge` package itself, where `[TODO]` is used as a placeholder string in template code rather than as an actionable developer note.

```text
spock_codebase_knowledge\populate.py:140: rows.append((rel, purpose.get(item.name, "[TODO]"), f"`{item.name}`"))
spock_codebase_knowledge\populate.py:202: return "[TODO] No README/ROADMAP/SPEC found at project root."
spock_codebase_knowledge\populate.py:226: framework = "pytest" if files or (root / "pytest.ini").is_file() or (root / "pyproject.toml").is_file() else "[TODO]"
spock_codebase_knowledge\populate.py:267: bits.append("- [TODO] No root ruff/black/flake8 config detected by scan.")
spock_codebase_knowledge\populate.py:273: todos = _section(sections, "TODO", "FIXME")
spock_codebase_knowledge\populate.py:286: lines.append("### Sample TODO/FIXME (filtered)\n")
spock_codebase_knowledge\populate.py:289: lines.append("- No production TODOs after skip_dirs filter.")
spock_codebase_knowledge\populate.py:291: lines.append("- No TODO/FIXME hits in filtered scan.")
spock_codebase_knowledge\populate.py:354: stack += "[TODO] No requirements*.txt parsed.\n"
spock_codebase_knowledge\populate.py:371: _table(top, ("Path", "Purpose", "Evidence")) if top else "[TODO]\n"
spock_codebase_knowledge\populate.py:377: struct += "- [TODO] No entry points detected\n"
spock_codebase_knowledge\populate.py:386: struct += "[TODO] No packages with `__init__.py` found.\n"
spock_codebase_knowledge\populate.py:430: testing += "- [TODO] No `tests/test_*.py` found\n"
spock_codebase_knowledge\populate.py:438: "TODOs under skipped trees (`data/`, `models/`, … from `.gitignore` / "
spock_codebase_knowledge\populate.py:441: concerns += "\n" + _evidence_block(sections, "TODO", "CHURN", "LARGEST")
spock_codebase_knowledge\__init__.py:4: v1 fills docs from scan evidence; narrative gaps stay as ``[TODO]``.
spock_codebase_knowledge\scripts\scan.py:28: TODO_LIMIT = 60
spock_codebase_knowledge\scripts\scan.py:312: """Search for TODO/FIXME/HACK comments."""
spock_codebase_knowledge\scripts\scan.py:314: patterns = ["TODO", "FIXME", "HACK"]
spock_codebase_knowledge\scripts\scan.py:343: return todos[:TODO_LIMIT]
spock_codebase_knowledge\scripts\scan.py:649: # TODOs
spock_codebase_knowledge\scripts\scan.py:652: print_section("TODO / FIXME / HACK (production code only, test dirs excluded)", todos, output_file)
spock_codebase_knowledge\scripts\scan.py:654: print_section("TODO / FIXME / HACK (production code only, test dirs excluded)", ["None found."], output_file)
```

### Reading notes for the raw excerpt

- Paths use Windows-style backslashes because they were captured on that platform; they are equivalent to forward-slash repository paths.
- `[TODO]` strings inside `spock_codebase_knowledge` may be template placeholders, not real work items.
- Duplicate lines can appear when the scanner reports multiple matching patterns or repeated section output; treat them as evidence of a reporting artifact unless confirmed in source.
- The final line in the original excerpt appears truncated and should not be interpreted as a complete marker hit.

## SQLite 3 `ship_computer.db`

`ship_computer.db` is the SQLite 3 database used by the Spock application to store structured, queryable application state. It is the relational backbone for the knowledge base, scan results, user queries, and response metadata. It works alongside the vector database, which stores high-dimensional embeddings for semantic search.

### Purpose

The database provides a durable, local, transactional store for data that must be filtered, joined, audited, or cited. It is especially useful for:

- Storing source-file metadata and scan evidence.
- Tracking `TODO`, `FIXME`, and `HACK` markers.
- Recording Ask AI and Deep Dive sessions.
- Linking generated answers back to specific chunks, files, and scan runs.
- Preserving citation and provenance information.

### Relationship to the vector database

The vector database stores embeddings, while `ship_computer.db` stores the relational context around those embeddings.

For example:

- The vector database can return a vector ID or chunk ID for a semantically similar passage.
- Spock then uses that ID to query `ship_computer.db` for the file path, line range, document title, scan run, and related markers.
- This allows Spock to combine semantic relevance with precise, citable source information.

### Typical data stored in `ship_computer.db`

A representative schema may include tables such as:

| Table | Purpose |
|---|---|
| `documents` | Stores one row per scanned file or document. |
| `chunks` | Stores text chunks derived from documents. |
| `markers` | Stores `TODO`, `FIXME`, `HACK`, and other code markers. |
| `scan_runs` | Stores metadata about each scan execution. |
| `ask_ai_queries` | Stores user questions submitted through Ask AI. |
| `deep_dive_sessions` | Stores Deep Dive investigation sessions. |
| `deep_dive_steps` | Stores intermediate retrieval and reasoning steps. |
| `citations` | Stores evidence used to support an answer. |
| `embeddings_meta` | Stores metadata linking chunks to vector records. |

### Ask AI interaction

When a user submits an Ask AI question, Spock uses `ship_computer.db` in several ways:

1. **Query recording**
   - Spock stores the user’s question, timestamp, and session context.

2. **Filter extraction**
   - Spock may extract filters such as file path, package name, marker type, or scan run.

3. **Candidate retrieval**
   - Spock queries the database for relevant documents, chunks, and markers.

4. **Vector search coordination**
   - Spock sends the question to the embedding model and searches the vector database.
   - The vector database returns candidate chunk IDs or vector IDs.

5. **Context enrichment**
   - Spock joins the returned IDs back to `ship_computer.db` to retrieve:
     - File path
     - Line numbers
     - Chunk text
     - Related markers
     - Scan metadata

6. **Answer generation**
   - Spock builds a prompt using the retrieved context.
   - The language model generates the answer.

7. **Citation storage**
   - Spock stores the answer and the evidence used to produce it.

### Deep Dive interaction

Deep Dive is a more investigative mode. It may require multiple retrieval passes and broader context than a single Ask AI response.

`ship_computer.db` supports Deep Dive by:

- Creating a session record for the investigation.
- Storing each sub-question or retrieval step.
- Tracking which chunks, files, and markers were considered.
- Preserving the order of evidence discovery.
- Linking final conclusions back to specific source records.

A typical Deep Dive flow is:

1. User asks a complex question.
2. Spock creates a Deep Dive session.
3. Spock decomposes the question into sub-questions.
4. For each sub-question:
   - Spock performs relational queries against `ship_computer.db`.
   - Spock performs semantic search using the vector database.
   - Spock merges and reranks results.
5. Spock accumulates evidence across steps.
6. Spock generates a detailed answer with citations.
7. Spock stores the final session, steps, and citations.

### Why SQLite 3 is used

SQLite 3 is well suited to this role because it is:

- Local and file-based.
- Easy to deploy without a separate database server.
- Transactional.
- Well suited to metadata, audit logs, and citation tracking.
- Compatible with Python’s standard `sqlite3` module.

It is not intended to replace the vector database. Instead, it provides the structured context needed to make vector search results useful, traceable, and citable.

## Embedding LLM and vector database

The Spock application uses an embedding model—referred to in this architecture as the embedding LLM—to convert text into numerical vectors. These vectors are stored in a vector database and used to find semantically similar content.

### What the embedding LLM does

The embedding LLM does not generate natural-language answers. Its role is to encode text into a fixed-size numerical representation.

For example:

- A source-code chunk is converted into a vector.
- A user question is converted into a vector.
- Similar meanings produce vectors that are close together in vector space.

This allows Spock to search for relevant content even when the user’s wording does not exactly match the source text.

### How embeddings are created

During indexing, Spock typically:

1. Reads source files or documents.
2. Splits them into chunks.
3. Sends each chunk to the embedding model.
4. Receives a vector for each chunk.
5. Stores the vector in the vector database.
6. Stores metadata about the chunk in `ship_computer.db`.

The metadata may include:

- Chunk ID
- File path
- Line range
- Document title
- Scan run ID
- Embedding model name
- Vector dimension

### How the vector database is used

The vector database stores embeddings and supports similarity search. It may be implemented using a dedicated vector store or a SQLite-compatible vector extension.

When Spock needs to answer a question, it:

1. Embeds the user’s question using the same embedding model used during indexing.
2. Searches the vector database for the closest vectors.
3. Retrieves the top matching chunks.
4. Uses those chunks as context for answer generation.

### Ask AI using the embedding LLM and vector database

For Ask AI, the flow is:

1. User submits a question.
2. Spock embeds the question.
3. Spock queries the vector database for similar chunks.
4. Spock retrieves the corresponding records from `ship_computer.db`.
5. Spock builds a prompt containing:
   - The user’s question
   - Relevant source chunks
   - File and line metadata
   - Related markers, if present
6. The language model generates an answer.
7. Spock stores the answer and citations.

This allows Ask AI to answer questions using both semantic relevance and precise source context.

### Deep Dive using the embedding LLM and vector database

Deep Dive uses the same embedding and vector search mechanism, but over multiple steps.

For each Deep Dive step:

1. Spock generates or refines a sub-question.
2. Spock embeds the sub-question.
3. Spock searches the vector database.
4. Spock retrieves related records from `ship_computer.db`.
5. Spock may expand the search using:
   - Related files
   - Related chunks
   - Related markers
   - Nearby code sections
6. Spock reranks the evidence.
7. Spock continues until enough context is gathered.
8. Spock produces a detailed, cited answer.

### Why both stores are needed

The vector database provides semantic search, while `ship_computer.db` provides structured context.

Together they allow Spock to:

- Find relevant content by meaning.
- Retrieve exact file and line information.
- Preserve citations.
- Support multi-step Deep Dive investigations.
- Keep answers grounded in the scanned codebase.
## SQLite 3 Database (`ship_computer.db`) Integration

The `ship_computer.db` file is a SQLite 3 relational database that serves as the structured knowledge backbone for the Spock application. It stores normalized metadata, scan artifacts, codebase topology, and cached inference results. Unlike raw file scans, this database provides fast, indexed, and transaction-safe access to project intelligence, enabling Spock to route queries efficiently based on intent.

### Database Schema and Responsibilities

The database is organized around stable identifiers and normalized relationships. A typical schema includes:

| Table | Purpose |
|---|---|
| `files` | Stores file-level metadata such as path, hash, language, size, last modified time, branch, and commit. |
| `modules` | Stores logical module or package information, including name, path, owner, description, and dependency relationships. |
| `dependencies` | Stores directed relationships between files, modules, functions, or packages, including dependency type and confidence. |
| `scan_results` | Stores security, quality, or architecture scan findings, including severity, rule, line range, commit, and timestamp. |
| `query_cache` | Stores cached Ask AI responses, query hashes, context snapshots, model identifiers, and expiration metadata. |
| `sessions` | Stores Deep Dive session state, including user, mode, creation time, and last active time. |
| `annotations` | Stores user-created notes, highlights, and navigation state tied to files, line ranges, or modules. |
| `embeddings_metadata` | Stores chunk identifiers, file paths, line ranges, embedding model, and pointers to the corresponding vector records in the vector database. |

This design keeps `ship_computer.db` focused on exact, queryable facts. The vector database stores high-dimensional embeddings, while SQLite stores the metadata needed to interpret, filter, cite, and cache those results.

### Interaction with "Ask AI" Inquiries

When a user submits an **Ask AI** query, Spock treats the request as a semantic or factual question about the codebase. The workflow leverages `ship_computer.db` as follows:

1. **Context Retrieval:** Spock executes parameterized SQL queries against indexed tables (e.g., `files`, `modules`, `dependencies`, `scan_results`) to fetch relevant documentation, recent changes, and architectural summaries.
2. **Prompt Grounding:** Retrieved rows are serialized into a structured context window. The database ensures that only verified, first-party metadata is injected, reducing hallucination risk.
3. **Response Caching:** Once the LLM generates a response, Spock stores the query hash, context snapshot, and final answer in a `query_cache` table. Subsequent identical or highly similar queries are served directly from SQLite, bypassing redundant LLM calls and reducing latency.

In practice, Ask AI may combine SQLite context with vector search. SQLite provides the authoritative project facts, while the vector database helps Spock find semantically relevant code or documentation when the user's wording does not match exact identifiers.

### Interaction with "Deep Dive" Inquiries

**Deep Dive** requests require granular, relational analysis rather than broad semantic matching. Spock uses `ship_computer.db` to:

1. **Traverse Dependency Graphs:** Complex `JOIN` queries and recursive common table expressions map module relationships, import chains, and function call hierarchies stored in normalized adjacency tables.
2. **Filter by Metadata:** Users can constrain deep dives by commit hash, author, file type, or scan severity. SQLite’s `WHERE` and `GROUP BY` clauses efficiently filter large result sets without loading them into memory.
3. **State Persistence:** Deep Dive sessions maintain temporary working tables that track user navigation paths, highlighted code regions, and custom annotations. These are committed to `ship_computer.db` to preserve session continuity across application restarts.

Because Deep Dive is relationship-heavy, SQLite’s transactional integrity ensures that partial updates do not corrupt the working graph. This makes it suitable for exploratory workflows where users repeatedly refine filters, expand dependency paths, and annotate code regions.

### Ask AI vs. Deep Dive: Retrieval Strategy

- **Ask AI** favors semantic retrieval and cached answers. It may use vector search first, then SQLite for grounding, validation, and citation.
- **Deep Dive** favors relational traversal and exact metadata. It may use SQLite first, then vector search to explain relationships or locate conceptually related code.

## Embedding LLM and Vector Database Workflow

While `ship_computer.db` handles structured, exact-match, and relational queries, the Spock application relies on an **embedding LLM** and a **vector database** to power semantic understanding and fuzzy code retrieval. This hybrid architecture ensures that both precise structural data and conceptual meaning are accessible.

### Role of the Embedding LLM

The embedding LLM is not the same as the primary answer-generating LLM. Its purpose is to convert text, code, comments, documentation, and scan summaries into numerical vectors. Each vector represents the meaning of a chunk in a high-dimensional space. Similar concepts produce vectors that are close together, while unrelated concepts are farther apart.

This allows Spock to answer questions such as "Where is the retry logic for failed API calls?" even when the user's wording does not match the code identifiers exactly. The embedding model provides the semantic bridge between natural language questions and codebase content.

### Embedding Generation Pipeline

1. **Chunking & Preprocessing:** Source files, documentation, and scan outputs are split into semantic chunks (typically 256–512 tokens). Headers, docstrings, and comments are preserved to maintain context.
2. **Vectorization:** The embedding LLM converts each chunk into a high-dimensional vector (e.g., 768 or 1536 dimensions). These vectors capture syntactic patterns, semantic intent, and code semantics.
3. **Indexing:** Vectors are stored in the vector database alongside metadata pointers (file path, line range, chunk ID). The database builds an approximate nearest neighbor (ANN) index (e.g., HNSW or IVF) to enable low-latency similarity searches.

### Vector Database Responsibilities

The vector database is responsible for storing and searching embeddings. It typically stores:

- The embedding vector for each chunk.
- A stable chunk identifier.
- Metadata such as file path, line range, language, commit, and scan severity.
- An ANN index that supports fast similarity search.

During retrieval, Spock embeds the user's question using the same embedding model and asks the vector database for the nearest neighbors. The vector database returns candidate chunks ranked by similarity, often using cosine distance or dot product. Spock then uses `ship_computer.db` to validate metadata, apply filters, deduplicate results, and attach citations.

### Query Routing & Retrieval-Augmented Generation (RAG)

When Spock receives a natural language prompt, it determines whether to route the request through the relational database, the vector store, or both:

- **Semantic Routing:** The query itself is embedded and compared against a lightweight intent classifier. Conceptual questions ("How does authentication work?") trigger vector search, while structural questions ("List all imports in `auth.py`") trigger SQLite queries.
- **Hybrid Retrieval:** For complex prompts, Spock executes parallel lookups. Vector search returns semantically relevant code snippets, while `ship_computer.db` supplies exact file paths, version history, and dependency constraints.
- **Context Assembly:** Retrieved vectors and relational rows are merged, deduplicated, and ranked by relevance score. The final context window is formatted into a system prompt that includes explicit instructions, code boundaries, and citation markers.
- **Inference & Feedback Loop:** The primary LLM generates the response. If the user marks the answer as helpful or requests clarification, Spock logs the interaction in `ship_computer.db` and optionally adjusts retrieval parameters, re-embeds affected chunks, or updates ranking heuristics for improved future retrieval.

This dual-storage approach ensures Spock delivers accurate, traceable, and context-aware responses while maintaining performance at scale.
## Explanation of Terms

- **Deterministic**: The concerns listed above are generated automatically by the `spock_codebase_knowledge` scan pipeline. No manual curation is applied; given an identical repository state, filter configuration, and environment settings, the pipeline produces reproducible output.
- **Filtered scan**: The scan process excludes file paths defined in `.gitignore`, `scan.skip_dirs`, and built-in exclusion patterns (e.g., `.venv`, `node_modules`, `__pycache__`). Only files residing outside these excluded directories are processed for analysis.
- **High-churn files**: Files ranked by the frequency of Git commits that modified them within the scanned history. A higher commit count indicates frequent modification, which may signal active development, architectural instability, or a need for architectural review.
- **`[TODO]` placeholders in the raw excerpt**: These are literal string values emitted by `populate.py` when the scan cannot resolve specific metadata (e.g., missing `README.md` or undetected test frameworks). They serve as template fallbacks for the documentation generator and do not represent actionable `TODO` comments within the source code.
- **`TODO_LIMIT`**: A configuration constant in `scan.py` that caps the number of `TODO`/`FIXME`/`HACK` annotations reported per scan (currently set to 60). This prevents a single noisy file from disproportionately dominating the analysis output.

## SQLite 3 `ship_computer.db` Architecture & Query Routing

The `ship_computer.db` file serves as the primary relational storage layer for the Spock application. Built on SQLite 3, it provides structured, ACID-compliant persistence for scan artifacts, metadata indexes, and query routing logic. Its design complements the unstructured vector storage by handling deterministic lookups, relationship mapping, and state management.

### Schema & Data Organization
The database is partitioned into logical tables that track:
- **File Metadata**: Absolute paths, file types, line counts, and last-modified timestamps.
- **Scan Artifacts**: Parsed AST nodes, dependency graphs, linting results, and architectural concerns.
- **Query History & Caching**: Cached responses, user prompts, and execution timestamps to enable session continuity and reduce redundant LLM calls.
- **Routing Flags**: Boolean and categorical markers that determine whether a query should be routed to the relational engine, the vector engine, or a hybrid pipeline.

### Interaction with "Ask AI" Inquiries
When a user submits an "Ask AI" prompt, Spock first queries `ship_computer.db` to establish baseline context:
1. **Intent Classification**: The prompt is parsed for keywords and structural markers. The database checks routing flags to determine if the query requires code-level precision or high-level architectural reasoning.
2. **Relational Context Retrieval**: If the query references specific modules, functions, or configuration files, Spock executes targeted `SELECT` statements to fetch exact file paths, version history, and associated metadata.
3. **Prompt Assembly**: Retrieved relational data is formatted into a structured context block. This ensures the LLM receives precise, verifiable references rather than relying solely on semantic approximation.

### Interaction with "Deep Dive" Inquiries
"Deep Dive" requests require multi-hop reasoning across codebases, dependencies, and historical changes. `ship_computer.db` facilitates this through:
1. **Graph Traversal**: The database stores adjacency lists for import/export relationships and function call chains. Spock executes recursive CTEs (Common Table Expressions) to map dependency trees up to a configurable depth.
2. **Temporal Analysis**: Commit metadata and churn metrics are joined with file paths to surface historically volatile or frequently refactored components.
3. **Hybrid Routing**: For complex architectural questions, Spock uses the relational layer to filter the vector search space. For example, it may restrict vector retrieval to files modified in the last 30 days or belonging to a specific service tier, drastically reducing noise and improving response accuracy.


## Embedding LLM & Vector Database Integration

While `ship_computer.db` handles structured data, Spock leverages an embedding LLM and a dedicated vector database to process unstructured code, documentation, and natural language queries. This integration powers semantic search and Retrieval-Augmented Generation (RAG) workflows.

### Embedding Generation Pipeline
1. **Chunking Strategy**: Source files and documentation are split into semantic chunks, typically 500–1000 tokens, with overlapping windows to preserve context across function boundaries, class definitions, and Markdown sections. Chunk boundaries, line ranges, and content hashes are recorded in `ship_computer.db` so that retrieval results can be traced back to their source files.
2. **Vectorization**: Each chunk is passed through a code-aware embedding model optimized for source code and technical documentation. The model outputs a fixed-dimensional vector, such as 768 or 1536 dimensions, that captures syntactic and semantic relationships. The same embedding model is used for both corpus chunks and user queries so that similarity comparisons remain consistent.
3. **Metadata Tagging**: Every vector is paired with relational metadata, including file path, language, commit hash, scan timestamp, chunk ID, and vector ID, before ingestion. This metadata enables hybrid filtering, permission checks, and deterministic retrieval constraints during query time.

### Vector Database Storage & Indexing
The vector database stores embeddings in an optimized index structure, such as HNSW or IVF-PQ, that supports approximate nearest-neighbor search with low latency. Key characteristics include:
- **Dynamic Indexing**: New scan results are batched and upserted asynchronously to prevent blocking the main application thread.
- **Namespace Partitioning**: Vectors are partitioned by repository, branch, or service tier to isolate search scopes and prevent cross-context contamination.
- **TTL & Eviction**: Stale embeddings are automatically purged or re-embedded when underlying files are modified, ensuring the vector space reflects the current repository state. `ship_computer.db` tracks file hashes, scan status, and chunk validity to determine when embeddings should be invalidated or refreshed.

### RAG Workflow for Ask AI & Deep Dive
When a query reaches the vector layer, Spock executes the following sequence:
1. **Query Embedding**: The user's prompt is transformed into a vector using the same embedding model applied to the corpus.
2. **Similarity Search**: The vector database performs a cosine similarity or inner-product search against the indexed corpus. Top-K results are returned based on a configurable relevance threshold.
3. **Metadata Filtering & Re-ranking**: Results are cross-referenced with `ship_computer.db` to apply hard filters, such as excluding test files, generated code, secrets, or unauthorized repositories. A lightweight cross-encoder or LLM-based re-ranker may then be applied to refine relevance.
4. **Context Injection**: The highest-scoring chunks are concatenated into a structured prompt template. The embedding LLM is not used for generation; it strictly handles representation. The primary generative LLM receives the enriched context and produces the final response.
5. **Feedback Loop**: User interactions, retrieved chunk IDs, response latency, and accuracy metrics are logged to `ship_computer.db`, enabling continuous tuning of chunking strategies, similarity thresholds, and routing heuristics.

This dual-layer architecture ensures Spock balances deterministic precision, via SQLite, with semantic flexibility, via embeddings, delivering accurate, context-aware responses for both straightforward inquiries and complex architectural deep dives.

### SQLite 3 `ship_computer.db` Integration

`ship_computer.db` is the structured, relational foundation of the Spock application. It is a SQLite 3 database that stores deterministic state, metadata, permissions, scan history, query logs, and feedback data. Unlike the vector database, which is optimized for semantic similarity, `ship_computer.db` is optimized for exact lookups, joins, filtering, transactional consistency, and auditability.

In this architecture, SQLite 3 serves as the system of record for the following concerns:

- **Repository and scan state**: Which repositories have been scanned, which branches were analyzed, and when the last successful scan occurred.
- **File inventory**: File paths, languages, sizes, content hashes, modification timestamps, and classification flags such as test, generated, documentation, or production code.
- **Chunk metadata**: Stable chunk identifiers, line ranges, token counts, content hashes, embedding model versions, and references to the corresponding vector IDs.
- **Query history**: Ask AI and Deep Dive prompts, retrieved chunk IDs, response metadata, latency, and user feedback.
- **Configuration and routing rules**: Thresholds, allowed file types, excluded paths, repository scopes, and feature flags.
- **Maintenance state**: Embedding invalidation, re-embedding queues, failed scans, and data freshness indicators.

A typical `ship_computer.db` schema may include tables such as:

- `repositories`: repository identifiers, remote URLs, default branches, and ownership metadata.
- `scans`: scan runs, commit hashes, start and completion timestamps, status, and error details.
- `files`: file paths, language, size, content hash, classification flags, and last-modified timestamps.
- `chunks`: chunk IDs, file references, line ranges, token counts, content hashes, and vector IDs.
- `query_logs`: session IDs, user IDs, query mode, prompt text, retrieved chunk IDs, response IDs, and latency.
- `feedback`: user ratings, comments, and correction signals tied to specific query logs.
- `settings`: application configuration, retrieval thresholds, and routing preferences.
- `permissions`: repository, branch, or file-level access controls used to constrain retrieval.

#### How `ship_computer.db` Supports Ask AI

Ask AI is designed for fast, scoped, and contextually grounded answers. When a user submits an Ask AI prompt, Spock uses `ship_computer.db` to establish the deterministic boundaries of the search before any semantic retrieval occurs.

The interaction typically follows this flow:

1. **Scope Resolution**  
   Spock resolves the active repository, branch, service tier, and user permissions from `ship_computer.db`. This ensures that the vector search is limited to the correct codebase and that the user cannot retrieve content they are not authorized to access.

2. **Filter Construction**  
   SQLite provides structured filters such as:
   - Include production code and exclude test files.
   - Exclude generated files, vendored dependencies, or secrets.
   - Prioritize recently modified files.
   - Restrict results to a specific module, directory, or language.

3. **Vector Retrieval**  
   The embedding model converts the user prompt into a vector, and the vector database returns semantically similar chunks.

4. **Metadata Joining**  
   Spock joins the returned vector IDs back to `ship_computer.db` to retrieve file paths, chunk line ranges, commit hashes, and classification flags. This step converts raw semantic matches into auditable, repository-aware results.

5. **Context Assembly**  
   Only chunks that pass the SQLite-defined filters are included in the prompt sent to the generative LLM. This prevents the model from answering based on irrelevant, stale, or unauthorized content.

6. **Logging and Feedback**  
   The prompt, retrieved chunk IDs, response metadata, and user feedback are written back to `ship_computer.db`. This creates a durable audit trail and supports future tuning of retrieval behavior.

For Ask AI, SQLite provides precision and control, while the vector database provides semantic recall. The result is a response that is both contextually relevant and constrained to the correct repository state.

#### How `ship_computer.db` Supports Deep Dive

Deep Dive is intended for more complex architectural analysis, such as understanding a subsystem, tracing dependencies, comparing implementation patterns, or explaining how multiple modules interact. In this mode, Spock relies more heavily on `ship_computer.db` because the query often requires structured traversal, not just semantic similarity.

The interaction typically includes:

1. **Initial Semantic Retrieval**  
   Spock begins with an embedding-based search to identify the most relevant chunks, files, and modules.

2. **Structured Expansion**  
   Using `ship_computer.db`, Spock expands the initial result set by following relational relationships, such as:
   - Files that import or reference the matched file.
   - Other chunks in the same module or package.
   - Documentation files associated with the same component.
   - Recent changes to the same file or directory.
   - Related configuration, tests, or interface definitions.

3. **Hybrid Search**  
   For Deep Dive queries that include exact identifiers, function names, class names, or error strings, Spock may combine vector search with SQLite full-text search, such as FTS5. This allows the application to match both semantic intent and exact code symbols.

4. **Iterative Context Building**  
   Deep Dive may perform multiple retrieval passes. Each pass can use the previous results to refine the next query. `ship_computer.db` stores intermediate state, including visited files, candidate chunks, excluded paths, and retrieval steps, so the process remains reproducible and debuggable.

5. **Architecture-Aware Ranking**  
   SQLite metadata can be used to boost or suppress results based on architectural relevance. For example, Spock may prioritize:
   - Public API surfaces.
   - Core service files.
   - Recently changed modules.
   - Files with high coupling or dependency significance.
   - Documentation that explicitly describes the subsystem.

6. **Response Grounding**  
   The final Deep Dive response is grounded in a larger, more structured context than Ask AI. SQLite ensures that the context is not only semantically relevant but also consistent with the repository structure, permissions, and current scan state.

7. **Auditability**  
   Because Deep Dive can involve multiple retrieval steps, `ship_computer.db` records the sequence of queries, retrieved chunks, filters applied, and final response. This is especially useful for debugging why a particular architectural explanation was produced.

#### Relationship Between SQLite and the Vector Database

The SQLite database and vector database are complementary rather than redundant.

| Concern | `ship_computer.db` | Vector Database |
|---|---|---|
| Primary purpose | Structured metadata, permissions, state, and audit logs | Semantic similarity search |
| Query style | Exact matches, joins, filters, and transactions | Approximate nearest-neighbor search |
| Data type | Relational rows, hashes, timestamps, flags | High-dimensional embeddings |
| Strength | Deterministic, auditable, and precise | Flexible, semantic, and cross-language |
| Weakness if used alone | Cannot infer meaning from natural language | Cannot enforce exact repository constraints |

In practice, Spock uses the vector database to find semantically relevant content and `ship_computer.db` to validate, filter, enrich, and log that content. This separation allows the application to answer natural language questions while still respecting the deterministic structure of the codebase.

#### Maintenance and Data Freshness

`ship_computer.db` also plays a central role in keeping the vector index accurate over time.

When Spock detects that a file has changed, it can:

- Compare the new content hash against the stored hash.
- Mark affected chunks as stale.
- Invalidate or delete the corresponding vector IDs.
- Queue the changed file for re-chunking and re-embedding.
- Record the scan result and update the repository state.

This ensures that Ask AI and Deep Dive do not rely on outdated code, documentation, or architecture descriptions. It also allows Spock to maintain a clear history of when each chunk was embedded, which embedding model was used, and whether the underlying source file has changed since the last scan.