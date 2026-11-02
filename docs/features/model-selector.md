# Model Selector

The Model Selector facilitates the selection of appropriate Large Language Models (LLMs) for specific tasks by evaluating hardware constraints and model specifications. It ensures that chosen models are compatible with the target environment while optimizing for performance, task accuracy, and resource efficiency.

## Components

| Module | Role |
|--------|------|
| `model_selector_core` | Contains the core logic for selecting models based on selection criteria, including filtering algorithms, compatibility checks, and resource estimation. |
| `model_selector_panels` | Provides UI panels for interacting with and selecting models from the registry via a graphical interface. |
| `model_pick_policy` | Defines the policy or ranking mechanism used during model selection to prioritize specific attributes, such as speed versus quality. |
| `gemini_openai_models` | Maintains a registry of available models, including their specifications, capabilities, supported inference engines, and resource requirements. |

### How the Modules Work Together

The Model Selector uses these modules in a coordinated workflow:

1. **Model Discovery** — `gemini_openai_models` provides the catalog of candidate models and their metadata.
2. **Compatibility Filtering** — `model_selector_core` removes models that do not meet hard requirements, such as available VRAM, context length, or inference engine support.
3. **Ranking and Selection** — `model_pick_policy` ranks the remaining candidates according to the desired trade-off between speed, quality, task fit, and resource usage.
4. **User Interaction** — `model_selector_panels` presents the available options and allows users to review or override the selected model when appropriate.

## Selection Criteria

1. **GPU VRAM** — The model must fit within the available VRAM of the target hardware. This ensures that the model can be loaded and run without causing memory-related errors or performance degradation.
   * *Note:* Memory requirements include both model weights and active context, such as the KV cache. Quantization may reduce this footprint.

2. **Task Match** — The model's capabilities should align with the specific requirements of the task. For example, a model designed for language translation may not be suitable for code generation.
   * *Note:* Verify capability tags or fine-tuning history to ensure domain-specific proficiency.

3. **Speed** — Preference is given to models with lower inference latency when appropriate for the use case. This is particularly important for real-time or interactive applications where response time is critical.
   * *Note:* Consider tokens-per-second (TPS), batch size efficiency, and prompt processing overhead when evaluating speed.

4. **Quality** — Models are ranked based on their benchmark scores, reflecting overall performance and accuracy. Higher benchmark scores typically indicate better performance on standard evaluation tasks.
   * *Note:* Scores may vary based on the specific benchmark suite used, such as MMLU or HumanEval.

### How Criteria Are Combined

The selector treats some criteria as hard constraints and others as ranking factors:

* **Hard Constraints** — Models that fail VRAM, context window, task compatibility, or inference engine requirements are excluded before ranking.
* **Soft Ranking Factors** — Remaining models are scored using the active `model_pick_policy`. Depending on the selected mode, the policy may prioritize lower latency, higher benchmark quality, better task alignment, or a balanced combination of these attributes.

## Technical Considerations

When using the Model Selector, consider the following technical nuances that affect selection outcomes:

* **Quantization:** Models can be loaded in lower precision formats, such as FP8 or INT4, to reduce VRAM usage without significant quality loss. The selector should account for quantized model sizes when checking VRAM limits.
* **Context Window:** Ensure the model's maximum context window supports the input length required by the task. Exceeding this limit will result in truncation or errors.
* **Inference Engine Compatibility:** Verify that the selected model is compatible with specific hardware accelerators, such as CUDA or ROCm, and software libraries supported by the registry.

## SQLite 3 `ship_computer.db` Integration

The `ship_computer.db` file is a local SQLite 3 database used by the Spock application to store structured ship-computer data and to support Ask AI and Deep Dive inquiries. It acts as the system of record for metadata, documents, telemetry, user context, and retrieval results.

### Purpose

The database provides a durable, queryable foundation for the Spock application. It stores the information that Ask AI and Deep Dive need to answer questions, retrieve relevant context, and maintain auditability.

The database is especially useful for:

* Storing structured records about the ship computer, including configuration, status, logs, and operational data.
* Maintaining references to documents, knowledge-base entries, and user-generated content.
* Supporting metadata filtering, such as time range, subsystem, severity, user role, or document type.
* Providing stable identifiers that can be linked to embeddings in the vector database.
* Enabling deterministic retrieval, auditing, and debugging of AI responses.

### Typical Contents

The exact schema may vary by deployment, but a typical `ship_computer.db` database may include the following categories of data:

| Area | Description |
|------|-------------|
| `documents` | Stores source documents, notes, manuals, logs, or knowledge-base entries that can be retrieved by Ask AI or Deep Dive. |
| `metadata` | Stores attributes used for filtering, such as subsystem, timestamp, severity, source, owner, or classification. |
| `queries` | Records user questions, prompts, and request context for auditing and reproducibility. |
| `retrieval_results` | Stores the records returned for a given query, including relevance scores and retrieval metadata. |
| `embeddings_index` | May store local references to vector IDs, embedding model versions, and chunk identifiers. |
| `audit_log` | Tracks model selections, retrieval actions, user overrides, and system events. |

### Relationship to the Vector Database

The SQLite database and the vector database serve complementary roles.

* **SQLite 3 `ship_computer.db`** stores the authoritative structured data, metadata, and references.
* **Vector database** stores numerical embeddings and supports semantic similarity search.

A common pattern is to store a stable identifier in both systems. For example, a document chunk in `ship_computer.db` may have an ID such as `doc_1042_chunk_7`. The vector database stores the embedding for that chunk and references the same ID. When Spock retrieves a vector match, it can use the ID to load the full text and metadata from SQLite.

This separation allows the system to benefit from:

* Fast semantic search through the vector database.
* Reliable structured filtering through SQLite.
* Easy auditing and debugging because the source records remain in a standard relational database.
* Independent scaling of vector search and relational data access.

### Interaction with Spock: Ask AI

Ask AI is intended for direct, focused questions. The Spock application uses `ship_computer.db` to ground the answer in relevant local data.

A typical Ask AI flow is:

1. The user submits a question through the Spock interface.
2. Spock records the question and request context in the database.
3. The question is converted into an embedding using the selected embedding LLM.
4. The vector database returns the most semantically similar records.
5. Spock uses the returned identifiers to load full text and metadata from `ship_computer.db`.
6. Optional metadata filters are applied, such as time range, subsystem, document type, or access level.
7. The retrieved context is assembled into a prompt for the answer LLM.
8. The LLM generates a response.
9. Spock stores the response, retrieved sources, model used, and confidence or scoring metadata for auditability.

This approach allows Ask AI to provide concise, evidence-based answers while preserving traceability back to the original records in `ship_computer.db`.

### Interaction with Spock: Deep Dive

Deep Dive is intended for broader investigation, where the user needs a more comprehensive understanding of a topic, incident, subsystem, or operational pattern.

Compared with Ask AI, Deep Dive typically uses the database in a more iterative and analytical way:

* It may retrieve a larger set of related records.
* It may apply multiple metadata filters.
* It may group results by subsystem, time, severity, or document type.
* It may perform follow-up semantic searches based on intermediate findings.
* It may summarize clusters of related records before generating a final explanation.
* It may preserve a richer audit trail of the investigation steps.

A typical Deep Dive flow is:

1. The user requests a detailed analysis or investigation.
2. Spock creates a Deep Dive session in `ship_computer.db`.
3. The initial query is embedded and searched in the vector database.
4. Spock retrieves candidate records and loads their metadata from SQLite.
5. The records are grouped, filtered, or ranked using structured criteria.
6. Spock may issue additional semantic queries to explore related concepts.
7. The accumulated context is summarized or condensed to fit the answer model's context window.
8. The LLM produces a structured Deep Dive response.
9. Spock stores the session, intermediate results, final answer, and source references.

This makes Deep Dive suitable for complex questions that require multiple retrieval passes and structured reasoning over the contents of `ship_computer.db`.

### Data Flow

The overall data flow between Spock, SQLite, the embedding LLM, and the vector database is:

1. **Ingestion** — Source data is written to `ship_computer.db`.
2. **Chunking** — Long documents or logs are divided into manageable chunks.
3. **Embedding** — Each chunk is converted into a vector by the embedding LLM.
4. **Indexing** — The vector and its reference ID are stored in the vector database.
5. **Querying** — A user question is embedded and searched against the vector index.
6. **Retrieval** — Matching IDs are used to load full records from SQLite.
7. **Generation** — The answer LLM uses the retrieved context to produce a response.
8. **Audit** — The query, retrieved records, model used, and response are stored for review.

### Consistency and Performance

Because `ship_computer.db` is a local SQLite 3 database, it is well suited for single-node or embedded deployments. To maintain reliable behavior, the Spock application should consider:

* **WAL mode** — Use SQLite Write-Ahead Logging to improve concurrent read performance.
* **Foreign keys** — Enforce relationships between documents, metadata, queries, and retrieval results.
* **Indexing** — Add indexes on commonly filtered fields, such as timestamp, subsystem, severity, and document type.
* **Versioning** — Track embedding model versions so that stale vectors can be detected and rebuilt.
* **Access control** — Apply user-level or role-based filtering before records are included in an AI prompt.
* **Backup** — Treat `ship_computer.db` as a critical data store and include it in backup and recovery procedures.

## Spock Application: Embedding LLM and Vector Database

The Spock application uses an embedding LLM and a vector database to convert natural-language questions and stored content into comparable numerical representations. This enables semantic retrieval, allowing the system to find relevant information even when the user's wording does not exactly match the stored text.

### Role of the Embedding LLM

The embedding LLM is a specialized model that converts text into a fixed-length numerical vector, also called an embedding.

For example:

* A user question such as "Why did the navigation subsystem report a fault?" is converted into a vector.
* A stored log entry such as "Navigation fault detected during attitude correction" is also converted into a vector.
* If the two concepts are semantically related, their vectors will be closer together in vector space.

The embedding LLM does not generate the final answer. Its role is to create a mathematical representation of meaning that can be compared efficiently.

Key responsibilities of the embedding LLM include:

* Converting user queries into query vectors.
* Converting documents, logs, notes, and knowledge-base entries into content vectors.
* Supporting semantic similarity search.
* Enabling retrieval of relevant context for the answer LLM.

### Role of the Vector Database

The vector database stores embeddings and supports fast similarity search. It is optimized for answering questions such as:

* "Which stored records are most similar to this query?"
* "Which records are closest to this vector?"
* "Which records match this query within a given similarity threshold?"

The vector database typically stores:

* The embedding vector.
* A reference ID linking back to `ship_computer.db`.
* Optional metadata for filtering.
* Index metadata, such as embedding model version and creation timestamp.

The vector database is not a replacement for SQLite. Instead, it provides semantic search, while SQLite provides structured storage, metadata, and authoritative record access.

### Embedding Pipeline

The embedding pipeline is the process by which text becomes searchable vector data.

A typical pipeline is:

1. **Source Selection** — Spock identifies documents, logs, or records that should be indexed.
2. **Chunking** — Long text is divided into smaller chunks to improve retrieval precision.
3. **Normalization** — Text is cleaned or normalized as needed.
4. **Embedding** — The selected embedding LLM converts each chunk into a vector.
5. **Storage** — The vector and its reference ID are stored in the vector database.
6. **Metadata Linking** — The reference ID is associated with the corresponding record in `ship_computer.db`.
7. **Version Tracking** — The embedding model name and version are recorded so that the index can be rebuilt if the model changes.

### Ask AI Query Flow

For Ask AI, Spock uses the embedding LLM and vector database to retrieve a small, highly relevant set of context.

The flow is:

1. The user asks a question.
2. Spock sends the question to the embedding LLM.
3. The embedding LLM returns a query vector.
4. Spock searches the vector database for the closest matching vectors.
5. The vector database returns a ranked list of reference IDs and similarity scores.
6. Spock loads the corresponding records from `ship_computer.db`.
7. Spock applies metadata filters and access controls.
8. Spock selects the top records for the answer prompt.
9. The answer LLM generates a concise response using the retrieved context.
10. Spock stores the question, retrieved sources, model used, and response.

This flow is optimized for speed and precision. Ask AI typically retrieves a limited number of records to keep the response focused and the prompt size manageable.

### Deep Dive Query Flow

For Deep Dive, Spock uses the same embedding and vector search foundation but applies a broader retrieval strategy.

The flow is:

1. The user requests a detailed investigation.
2. Spock creates a Deep Dive session in `ship_computer.db`.
3. The initial query is embedded and searched in the vector database.
4. Spock retrieves a larger candidate set than it would for Ask AI.
5. Spock loads metadata from SQLite and applies structured filters.
6. Spock groups or clusters related records by subsystem, time, severity, or topic.
7. Spock may generate follow-up queries based on the initial results.
8. Additional vector searches are performed to expand coverage.
9. The accumulated context is summarized or condensed.
10. The answer LLM produces a structured, detailed response.
11. Spock stores the full investigation trail, including intermediate queries and retrieved records.

This flow is optimized for completeness and context. Deep Dive may perform multiple retrieval passes and use more of the available context window than Ask AI.

### Indexing and Refresh

The vector index must be maintained over time.

Common maintenance operations include:

* **Initial indexing** — Embedding all eligible records when the system is first deployed.
* **Incremental indexing** — Embedding new records as they are added to `ship_computer.db`.
* **Reindexing** — Rebuilding the vector index when the embedding model changes.
* **Pruning** — Removing vectors for records that have been deleted or declassified.
* **Validation** — Checking that vector reference IDs still resolve to valid SQLite records.

Because embeddings are model-specific, Spock should track the embedding model version. If a new embedding model is selected, the system should either rebuild the index or maintain separate indexes for different model versions.

### Failure Handling and Fallbacks

The Spock application should handle failures gracefully.

Possible failure scenarios include:

* The embedding LLM is unavailable.
* The vector database is unreachable.
* A retrieved reference ID no longer exists in `ship_computer.db`.
* The answer LLM exceeds its context window.
* The selected model does not fit the available hardware.

Recommended fallback behavior includes:

* Falling back to keyword search or SQLite full-text search if vector search is unavailable.
* Reducing the number of retrieved records if the prompt is too large.
* Selecting a smaller or more efficient model through the Model Selector.
* Logging the failure and presenting a clear status message to the user.
* Preserving the user's query and partial results for later review.

### Relationship to Model Selector

The Model Selector supports the Spock application by choosing appropriate models for both embedding and answer generation.

For embedding, the selector may prioritize:

* Low latency.
* Small memory footprint.
* Compatibility with the local inference engine.
* Sufficient semantic quality for retrieval.

For answer generation, the selector may prioritize:

* Higher reasoning quality.
* Larger context window.
* Better instruction following.
* Task-specific capability.

This allows Spock to use different models for different stages of the pipeline. For example, a lightweight embedding model may be used for fast vector search, while a larger answer model may be used for generating the final response.
## SQLite 3 Database (`ship_computer.db`) Integration

The `ship_computer.db` file serves as the primary relational storage layer for the Spock application, built on SQLite 3. It manages persistent state, user configurations, conversation history, and metadata required for AI-driven features. In Python, the application interfaces with this database using the built-in `sqlite3` module, ensuring thread-safe, ACID-compliant operations without requiring a separate database server.

### Interaction with Ask AI and Deep Dive Inquiries
The database plays a critical role in routing, contextualizing, and persisting user requests:

* **Query Routing & State Management:** When a user initiates an "Ask AI" or "Deep Dive" request, the application first queries `ship_computer.db` for active session states, user preferences, and previously resolved intents. This ensures continuity across multi-turn conversations and prevents redundant processing.
* **Context Caching:** For "Ask AI" queries, frequently accessed knowledge snippets, resolved prompts, and system instructions are cached in dedicated tables. This reduces redundant LLM calls, lowers API latency, and accelerates response times for repeated or similar questions.
* **Deep Dive Orchestration:** "Deep Dive" inquiries require iterative research, synthesis, and source verification. The database tracks each research step, storing intermediate findings, source URLs, confidence scores, and reasoning chains in structured logs. This allows the application to reconstruct the full inquiry path, support rollback functionality, and maintain audit trails for complex, multi-step queries.
* **Schema Optimization & Concurrency:** The database uses indexed foreign keys, prepared statements, and WAL (Write-Ahead Logging) mode to minimize I/O latency. Connection pooling and read-replica routing (where applicable) support concurrent read/write operations during intensive AI processing, preventing database locks during high-throughput inference cycles.

## Embedding LLM and Vector Database Architecture

Spock leverages a dedicated embedding model and a vector database to enable semantic search and context-aware reasoning. This architecture bridges the gap between raw data and the generative LLM, ensuring that responses are grounded in relevant, up-to-date information rather than relying solely on parametric memory.

### Workflow Overview
1. **Text Embedding Generation:** When a user submits a query or when new documents are ingested, the application routes the text through a lightweight embedding LLM (e.g., `nomic-embed-text`, `all-MiniLM-L6-v2`, or a domain-specific fine-tuned model). This model converts unstructured text into high-dimensional numerical vectors (embeddings) that capture semantic meaning, intent, and contextual relationships rather than exact keyword matches.
2. **Vector Storage & Indexing:** The generated embeddings are stored in a vector database (such as ChromaDB, FAISS, or SQLite-VSS). Each vector is paired with metadata (source, timestamp, relevance tags, and chunk boundaries) and indexed using approximate nearest neighbor (ANN) algorithms like HNSW or IVF. This enables sub-millisecond similarity searches even across large, dynamically updating datasets.
3. **Semantic Retrieval for Ask AI:** During an "Ask AI" interaction, the user's prompt is embedded and queried against the vector index. The system retrieves the top-k most semantically similar chunks, which are then formatted into a structured context window. This retrieved context is injected into the system prompt before being passed to the primary generative LLM, grounding the response in verified data.
4. **Deep Dive Context Expansion:** For "Deep Dive" requests, the vector database performs iterative similarity searches. Initial results seed follow-up queries, allowing the system to traverse related concepts, cross-reference sources, and build a comprehensive knowledge graph. The vector store also supports hybrid search (combining semantic embeddings with keyword/BM25 filtering) to improve precision for technical, code-heavy, or domain-specific terminology.
5. **Feedback Loop & Re-ranking:** Retrieved vectors are optionally passed through a cross-encoder re-ranker to refine relevance before context injection. This reduces hallucination risk, filters out low-quality or outdated chunks, and ensures the generative LLM operates on the most accurate and task-aligned information. The re-ranked results are then logged back to `ship_computer.db` for future caching and audit purposes.

## Database Architecture

The application utilizes a SQLite 3 database file named `ship_computer.db` to persist critical state information, query history, and model metadata. This lightweight, serverless database ensures portability and low-latency access for the Spock application's core AI functions, specifically Ask AI and Deep Dive inquiries.

### Design Goals

The database design prioritizes:

*   **Local Persistence** — Data remains available offline without requiring an external database service or continuous network connectivity.
*   **Low-Latency Reads** — Frequent lookups of model metadata and session state are optimized for speed through strategic indexing and query caching.
*   **Transactional Integrity** — Query logs, session updates, and knowledge-base writes are managed within consistent ACID-compliant transaction boundaries to prevent data corruption.
*   **Recoverability** — Active Deep Dive contexts and intermediate analytical states can be reliably restored after application restarts or unexpected closures.

### Schema Overview

The `ship_computer.db` schema is structured to support high-frequency read operations while maintaining strict data integrity for analysis logs. Key tables include:

*   **`models`**: Stores registry metadata for available AI models, including configuration paths, quantization profiles, VRAM requirements, context window limits, and inference engine compatibility flags. *(Note: Actual model weights are stored externally on disk and referenced by identifier or path.)*
*   **`sessions`**: Tracks active user sessions, initialization timestamps, expiration policies, and the specific model configurations bound to each session.
*   **`queries`**: Logs all Ask AI and Deep Dive inquiries. Records include input prompts, generated responses, associated model identifiers, token counts, and latency metrics for performance monitoring.
*   **`knowledge_base`**: Contains structured data, extracted insights, and intermediate reasoning steps generated during Deep Dive sessions to maintain persistent context.

### Interaction with Spock Application

The Spock application interacts with `ship_computer.db` through a dedicated ORM layer to ensure type safety, connection pooling, and robust transaction management. The interaction patterns are specifically optimized for the AI inquiry modules:

1.  **Ask AI Inquiries**:
    *   When a user submits an Ask AI query, the system first queries the `models` table to identify available resources compatible with current hardware constraints and user preferences.
    *   Upon completion, the prompt, response, and associated metadata are atomically written to the `queries` table. This historical log enables the application to track usage patterns, monitor inference latency, and dynamically optimize model selection policies over time.

2.  **Deep Dive Inquiries**:
    *   Deep Dive sessions require multi-step, persistent context. The system writes intermediate analysis results, extracted entities, and reasoning chains to the `knowledge_base` table to maintain state across iterative steps.
    *   Query logs in the `queries` table are enriched with session identifiers and "Deep Dive" status tags. This allows the application to perform specialized retrieval, filter historical context, and reconstruct the analytical thread during subsequent interactions.

3.  **Persistence and Recovery**:
    *   The database is engineered to survive application restarts and system interruptions. Upon initialization, Spock scans the `sessions` and `knowledge_base` tables to reconstruct active contexts. This ensures users can resume Deep Dive sessions seamlessly without re-executing initial analysis steps or losing intermediate findings.

### Detailed Database Interaction Workflow

To ensure reliability during intensive AI operations, Spock implements a structured data access lifecycle for `ship_computer.db`:

*   **Connection & Concurrency Management**: Spock initializes a single, thread-safe SQLite connection at startup. Write-Ahead Logging (WAL) mode is enabled to allow concurrent read operations during heavy write cycles, effectively eliminating database lock contention during active inference.
*   **Ask AI Data Flow**: User prompts are validated and routed to the selected model. Once the LLM generates a response, the ORM constructs a transaction that inserts the query record, updates session metrics, and commits the transaction. If the inference pipeline fails or times out, the transaction is rolled back to maintain log consistency and prevent orphaned records.
*   **Deep Dive Data Flow**: Deep Dive operations utilize a state-machine pattern. Each analytical step triggers a database transaction that appends new findings to the `knowledge_base` table while updating the `sessions` table with the current step index and checkpoint hash. This granular logging enables precise state reconstruction and allows users to backtrack through the analysis without data loss.
*   **Indexing Strategy**: Primary keys and foreign keys are strictly enforced. Additional indexes are applied to `session_id`, `model_id`, and `timestamp` columns to accelerate filtering and sorting operations during session recovery and performance analytics.

### Embedding LLM and Vector Database Integration

To enable semantic understanding and context-aware retrieval, Spock integrates an embedding LLM alongside a vector database layer. This architecture powers the retrieval-augmented generation (RAG) pipeline for both Ask AI and Deep Dive inquiries.

The embedding LLM and vector database work together to allow Spock to retrieve relevant information based on meaning rather than exact keyword matching. This is especially important for Ask AI questions that require concise, grounded answers and for Deep Dive sessions that require iterative exploration of related concepts, entities, and prior findings.

#### How Spock Uses the Embedding LLM

The embedding LLM is a specialized model that converts text into numerical vector representations, also called embeddings. Each embedding captures the semantic meaning of the text in a high-dimensional numerical space. Texts with similar meanings produce vectors that are closer together, while unrelated texts produce vectors that are farther apart.

Spock uses the embedding LLM in the following ways:

*   **Query Encoding**: When a user submits an Ask AI or Deep Dive prompt, Spock sends the prompt to the embedding LLM to generate a query vector.
*   **Context Encoding**: Relevant documents, knowledge-base entries, extracted insights, and prior Deep Dive findings are also converted into vectors and stored in the vector database.
*   **Semantic Matching**: Spock compares the query vector against stored vectors to identify the most semantically relevant context.
*   **Prompt Augmentation**: The retrieved context is inserted into the prompt provided to the generative LLM, improving answer accuracy, relevance, and traceability.
*   **Deep Dive Continuity**: During Deep Dive sessions, newly generated insights, extracted entities, and intermediate reasoning steps are embedded and stored so that later steps can retrieve earlier context efficiently.

The embedding LLM is distinct from the generative LLM. The generative LLM produces natural-language responses, while the embedding LLM produces numerical representations used for retrieval and similarity search.

#### How Spock Uses the Vector Database

The vector database stores the embeddings produced by the embedding LLM and supports fast similarity search. It allows Spock to retrieve relevant context from large or growing knowledge bases without scanning every record using traditional keyword search.

Spock uses the vector database to:

*   Store embeddings for user documents, knowledge-base entries, Deep Dive findings, and prior query context.
*   Perform similarity searches using metrics such as cosine similarity, dot product, or Euclidean distance.
*   Retrieve the most relevant passages, entities, and reasoning steps for a given prompt.
*   Filter results by session, knowledge-base scope, timestamp, or Deep Dive step.
*   Support iterative retrieval during Deep Dive sessions, where each new question may require access to both original source material and previously generated insights.

The vector database complements `ship_computer.db` rather than replacing it. SQLite stores relational state, session metadata, query history, and structured knowledge-base records. The vector database stores high-dimensional embeddings and provides semantic search capabilities.

#### Ask AI Semantic Retrieval Workflow

For Ask AI inquiries, Spock uses the embedding LLM and vector database to ground the response in relevant context.

1.  **Prompt Reception**: The user submits a question or request.
2.  **Model Selection**: Spock selects an appropriate generative LLM and embedding LLM based on the `models` table, hardware constraints, and user preferences.
3.  **Query Embedding**: The prompt is converted into a vector using the embedding LLM.
4.  **Vector Search**: Spock queries the vector database for the most relevant stored context.
5.  **Context Filtering**: Results are filtered by session scope, knowledge-base permissions, recency, and relevance score.
6.  **Prompt Construction**: The retrieved context is combined with the user prompt to form an augmented prompt.
7.  **Response Generation**: The generative LLM produces the final answer.
8.  **Persistence**: The prompt, response, retrieved context identifiers, embedding model identifier, vector scores, latency, and token usage are written to the `queries` table.

This workflow allows Ask AI to provide more accurate and context-aware answers while preserving a complete audit trail of the information used to generate each response.

#### Deep Dive Semantic Retrieval Workflow

Deep Dive inquiries are iterative and stateful. Spock uses the embedding LLM and vector database to maintain semantic continuity across multiple analysis steps.

1.  **Session Initialization**: Spock creates or resumes a Deep Dive session and records the session state in the `sessions` table.
2.  **Initial Context Retrieval**: The initial prompt is embedded, and the vector database is searched for relevant source material and prior findings.
3.  **Analysis Step Execution**: The generative LLM produces an intermediate analysis, such as extracted entities, hypotheses, comparisons, or reasoning steps.
4.  **Insight Embedding**: New insights are embedded and stored in the vector database.
5.  **Knowledge-Base Update**: Structured findings are written to the `knowledge_base` table, including session identifiers, step indices, and checkpoint hashes.
6.  **Iterative Retrieval**: For each subsequent Deep Dive step, Spock embeds the new prompt and retrieves both original context and previously generated insights.
7.  **State Reconstruction**: If the application restarts, Spock uses the `sessions`, `queries`, and `knowledge_base` tables to reconstruct the Deep Dive state and continue the analysis.

This approach allows Deep Dive sessions to build on prior reasoning without requiring the user to repeat earlier steps or manually re-supply context.

#### Embedding and Vector Metadata in `ship_computer.db`

Although the vector database stores the actual embeddings, `ship_computer.db` stores the relational metadata needed to manage, trace, and recover semantic retrieval operations.

This metadata may include:

*   **Embedding Model Identifiers**: The specific embedding LLM used to generate each vector.
*   **Vector Store References**: Identifiers linking SQLite records to corresponding vectors in the vector database.
*   **Retrieval Scores**: Similarity scores associated with retrieved context.
*   **Session Scope**: The session or Deep Dive context to which a vector or retrieved result belongs.
*   **Knowledge-Base Links**: Relationships between vector records and structured entries in the `knowledge_base` table.
*   **Timestamps**: Creation and update times for embeddings and retrieval events.
*   **Versioning Information**: Model versions, embedding dimensions, and index configurations used to generate or search vectors.

By storing this metadata in `ship_computer.db`, Spock can maintain a consistent, queryable record of how semantic retrieval was performed, which context influenced each response, and how Deep Dive sessions evolved over time.
*   **Embedding Generation**: When a query, document chunk, or knowledge-base entry is processed, the embedding LLM converts textual data into high-dimensional numerical vectors. These vectors capture semantic meaning, allowing the system to match conceptual relevance rather than relying solely on exact keyword matching. In Spock, this step is used for both user prompts and stored knowledge so that Ask AI and Deep Dive requests can be compared against the same semantic space.
*   **Vector Storage & Indexing**: Generated embeddings are stored in a dedicated vector database optimized for fast similarity search. Each vector is linked to its source metadata via stable identifiers that reference the `knowledge_base` and `queries` tables in `ship_computer.db`. This hybrid relational-vector approach ensures that semantic search results can be instantly correlated with structured session data, citations, and audit logs.
*   **Semantic Retrieval Workflow**:
    1.  **Query Encoding**: The user's prompt is passed through the embedding LLM to generate a query vector.
    2.  **Similarity Search**: The vector database performs an Approximate Nearest Neighbor (ANN) search to retrieve the most contextually relevant embeddings from the knowledge base.
    3.  **Context Assembly**: Retrieved vectors are mapped back to their original text chunks, ranked by cosine similarity or dot-product scores, and injected into the primary LLM's context window alongside the original prompt.
    4.  **Inference & Logging**: The LLM generates a response grounded in the retrieved context. The final output, along with the retrieved source references and similarity scores, is logged to `ship_computer.db` for transparency and future session recovery.
*   **Performance Optimization**: To minimize latency, Spock caches frequently accessed embeddings and utilizes batched vector operations. The embedding model runs on the same hardware acceleration stack as the primary inference engine, ensuring efficient resource utilization without requiring external API calls or additional network overhead.

## SQLite 3 `ship_computer.db` and Spock Interaction

`ship_computer.db` is the local SQLite 3 database used by the Spock application to persist application state, user interactions, knowledge-base metadata, and audit information. It is not the primary vector store; instead, it provides the relational context that makes semantic search results traceable, recoverable, and auditable.

Because Spock is a Python and SQLite application, `ship_computer.db` is typically accessed through Python’s built-in `sqlite3` module. SQLite 3 provides a lightweight, file-based, ACID-compliant database that is well suited for local application state, session tracking, and structured logging.

### Core Tables and Responsibilities

A typical `ship_computer.db` schema may include tables such as:

| Table | Purpose |
|---|---|
| `sessions` | Tracks user conversations, session identifiers, timestamps, and conversation state. |
| `queries` | Stores individual user prompts, request type, model settings, and execution metadata. |
| `knowledge_base` | Stores metadata for documents, notes, or knowledge entries available to Spock. |
| `chunks` | Stores text chunks derived from knowledge-base entries, including chunk identifiers and source references. |
| `retrieval_results` | Records which chunks were retrieved for a query, along with similarity scores and ranking information. |
| `responses` | Stores generated answers, response type, model output, and associated citations. |
| `deep_dive_runs` | Tracks multi-step Deep Dive tasks, including objective, status, and intermediate progress. |
| `citations` | Links generated answers to specific source chunks, documents, or knowledge-base entries. |
| `audit_logs` | Records system actions, retrieval events, model calls, and error states for transparency. |

These tables allow Spock to maintain a durable record of what the user asked, what information was retrieved, how the answer was generated, and which sources supported the final response.

### Ask AI Inquiries

For an Ask AI request, Spock uses `ship_computer.db` to manage a conversational or single-question workflow. The database supports the following steps:

1. **Session Creation or Update**  
   Spock creates or updates a session record so that the Ask AI request can be associated with a broader conversation.

2. **Query Recording**  
   The user prompt is inserted into the `queries` table with metadata such as timestamp, request type, model configuration, and any user-provided context.

3. **Knowledge Resolution**  
   Spock identifies the relevant knowledge-base entries and text chunks that may be useful for answering the question.

4. **Retrieval Logging**  
   The retrieved chunks, similarity scores, and source identifiers are stored in `retrieval_results` or a similar table.

5. **Response Storage**  
   The generated answer is stored in `responses`, along with citations, confidence indicators, and any follow-up suggestions.

6. **Audit Trail**  
   Relevant events are written to `audit_logs`, allowing Spock to reconstruct the request, verify the sources used, and support future debugging or session recovery.

This workflow allows Spock to answer a question, explain which sources influenced the answer, and restore the conversation later without re-running the full retrieval pipeline.

### Deep Dive Inquiries

For a Deep Dive request, Spock treats the inquiry as a multi-step research task rather than a single prompt-and-answer exchange. The database supports this workflow by:

1. **Creating a Deep Dive Run**  
   A `deep_dive_runs` record captures the objective, scope, status, and lifecycle of the research task.

2. **Tracking Intermediate Questions**  
   Spock may break the Deep Dive into sub-questions, hypotheses, or research steps. Each step can be recorded with its own query metadata.

3. **Storing Evidence**  
   Retrieved chunks, documents, and supporting evidence are linked to the Deep Dive run so that the final report can be traced back to specific sources.

4. **Recording Citations**  
   Citations are stored in a structured way, allowing Spock to show which sources support each claim or section of the final output.

5. **Persisting the Final Report**  
   The synthesized Deep Dive report, assumptions, limitations, and follow-up recommendations are stored for later review.

6. **Supporting Resumability**  
   Because the state is persisted in SQLite 3, a long-running Deep Dive can be paused, resumed, or audited after completion.

In both Ask AI and Deep Dive modes, `ship_computer.db` acts as the source of truth for what the user asked, what Spock retrieved, what it answered, and how the answer can be verified.

## How Spock Uses the Embedding LLM and Vector Database

Spock uses the embedding LLM to translate natural-language content into numerical vectors. These vectors are then stored in a vector database that supports fast similarity search. The primary LLM is responsible for generating natural-language answers, while the embedding LLM is responsible for making content searchable by meaning.

### Embedding LLM Role

The embedding LLM is used in three main cases:

* **Knowledge Ingestion**: When documents, notes, or knowledge-base entries are added, Spock splits them into chunks and generates an embedding for each chunk.
* **Query Processing**: When a user submits an Ask AI or Deep Dive prompt, Spock generates an embedding for the prompt.
* **Re-ranking or Filtering**: In some workflows, Spock may generate additional embeddings for sub-questions, candidate summaries, or evidence fragments to improve retrieval precision.

The embedding model does not generate the final user-facing answer. It produces vectors that allow Spock to find semantically related content before the primary LLM composes a response.

### Vector Database Role

The vector database stores the generated embeddings and provides similarity search. For each vector, Spock stores or references metadata such as:

* Source document or knowledge-base entry identifier
* Chunk identifier
* Session or query identifier
* Timestamp
* Content type
* Access permissions or scope, if applicable

When Spock needs context, it sends the query vector to the vector database and requests the nearest neighbors. The vector database returns the most relevant vectors and their associated metadata. Spock then uses those metadata identifiers to retrieve the original text chunks from `ship_computer.db` or the local document store.

### End-to-End Retrieval and Answering

1. The user submits an Ask AI or Deep Dive request.
2. Spock records the request in `ship_computer.db`.
3. The embedding LLM converts the request into a vector.
4. The vector database searches for similar knowledge-base vectors.
5. Spock retrieves the corresponding text chunks and metadata.
6. The primary LLM receives the user prompt plus the retrieved context.
7. The primary LLM generates a grounded answer.
8. Spock stores the answer, citations, similarity scores, and execution metadata in `ship_computer.db`.

This design separates semantic search from answer generation. The embedding LLM and vector database make it possible to find relevant information by meaning, while SQLite 3 provides durable, queryable records of the conversation, sources, and audit trail.