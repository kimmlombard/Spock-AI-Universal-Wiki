# Copy Map

The copy map tracks which files were adapted from the original `Spock-UIE-Wiki-KB-HUB` project during migration to the current codebase. This document provides a high-level summary of architectural changes and file renames. For the complete, low-level file-to-file mapping, see `COPY_MAP.md` in the project root.

## Key Adaptations

| Original | Spock-Onboarding | Changes |
|----------|------------------|---------|
| `UIE-Wiki-KB.py` | `Spock-UIE-Wiki-KB.py` | Refactored for modularity to improve maintainability and scalability. This allows functionality to be updated or extended without affecting unrelated parts of the codebase. |
| `UIEG_KnowledgeBase.py` | `spock_UIEG_KnowledgeBase.py` | Extracted into a standalone module to promote reusability and separation of concerns. The knowledge-base logic can now be used independently and is less tightly coupled to other components. |
| Monolithic UI | `spock_shell/` | Split into 24 focused modules to improve code organization and simplify maintenance. This makes individual user-interface components easier to read, test, and update. |

### Column Notes

*   **Original:** The file or component name in the source `Spock-UIE-Wiki-KB-HUB` project.
*   **Spock-Onboarding:** The corresponding file, module, or directory in the current codebase after migration.
*   **Changes:** The primary architectural reason for the rename, extraction, or refactor.

## Architectural Context

This section explains the architectural terms used above:

*   **Modularity:** The original implementation contained tightly coupled logic within single files. Refactoring into modular units allows specific features to be updated or tested in isolation, reducing the risk of regressions during development.
*   **Separation of Concerns:** Logic previously mixed with data handling—for example, in `UIEG_KnowledgeBase.py`—has been decoupled. This ensures that knowledge-base functionality can operate independently of main application logic, which simplifies unit testing and database management.
*   **Monolithic UI:** Refers to the original implementation where user-interface code was consolidated in one location or tightly coupled structure. The new `spock_shell/` directory distributes this code across specialized modules, allowing developers to target specific UI components without impacting the entire application.


## Database Architecture

The Spock application relies on a persistent data store managed by **SQLite 3**, specifically instantiated as `ship_computer.db`. This database serves as the central repository for knowledge retrieval, state management, and analytical processing required by the application's core features.

### Role of `ship_computer.db`

Unlike client-server relational databases that require separate server processes, SQLite is embedded directly within the application runtime. This design choice minimizes infrastructure overhead while providing ACID-compliant transactional integrity when the application uses appropriate transaction handling, journaling modes such as WAL, and concurrency controls. The database is responsible for:

1.  **Knowledge Persistence:** Storing structured data related to the knowledge base, document metadata, and context windows.
2.  **State Management:** Maintaining session history, user interaction logs, and application configuration states.
3.  **Query Execution:** Providing the underlying data schema for analytical operations, full-text search, and vector similarity retrieval.

### SQLite Operational Model

`ship_computer.db` is a single-file database that is accessed directly by the Spock application. This embedded model provides several operational benefits:

*   **Low Deployment Complexity:** The database does not require a separate database server, service account, or network endpoint.
*   **Data Locality:** Relational data, metadata, and vector embeddings can be stored in the same file, reducing integration overhead.
*   **Transactional Consistency:** SQLite supports atomic transactions, allowing the application to update knowledge entries, session state, and interaction logs consistently.
*   **Concurrency Control:** SQLite uses file-level locking and journaling mechanisms to coordinate access. In read-heavy workloads, WAL mode can improve concurrent read performance while preserving write consistency.
*   **Extension Support:** Optional SQLite extensions, such as FTS5 for full-text search or vector-oriented extensions where available, can extend the database's retrieval capabilities.

### Interaction with Application Features

The database interacts directly with specific high-level features of the Spock application, particularly **Ask AI** and **Deep Dive** inquiries. The data flow is structured as follows:

#### Ask AI Inquiries
*   **Functionality:** Provides immediate, context-aware answers based on retrieved knowledge base content.
*   **Database Interaction:** When a user submits an inquiry, the application first queries `ship_computer.db` to retrieve relevant text chunks, metadata, or cached results associated with the query topic. Semantic search leverages precomputed vector embeddings stored directly in SQLite, while keyword-based fallback retrieval utilizes SQLite's FTS5 extension. The database returns the top-k most relevant documents, which are then formatted into a prompt context window for the generative model.
*   **Read/Write Pattern:** Primarily read-heavy during inference to minimize latency. Write operations occur asynchronously during knowledge ingestion, context window updates, or when query results are cached for future requests.

#### Deep Dive Inquiries
*   **Functionality:** Enables complex analysis, multi-step reasoning, cross-referencing, and historical data exploration.
*   **Database Interaction:** These inquiries trigger more intensive database transactions. The application executes complex SQL queries that join multiple tables to correlate disparate data points, such as user session history, knowledge-base entries, and previous analysis outputs. The database may also store intermediate reasoning steps and chain-of-thought artifacts to support iterative exploration.
*   **Read/Write Pattern:** Balanced read/write workload. The application persists analysis results, intermediate computation states, and audit records to enable reproducibility and longitudinal tracking of user research paths.

### Embedding LLM and Vector Database Integration

Spock utilizes an embedding LLM and a vector storage layer to enable semantic search and context retrieval. Although SQLite is traditionally a relational database, in this architecture it functions as a lightweight vector database through the following pipeline:

1.  **Document Ingestion & Chunking:** Raw documents or knowledge base entries are parsed and split into manageable text chunks. Metadata such as source, timestamp, category, and document identifier is extracted and normalized.
2.  **Embedding Generation:** Each text chunk is passed through an embedding LLM, such as a transformer-based model optimized for dense vector representation. The model outputs a fixed-dimensional floating-point vector that captures the semantic meaning of the text.
3.  **Vector Storage in SQLite:** The generated vectors are stored in `ship_computer.db` as `BLOB` or `REAL` array columns alongside their corresponding text chunks and metadata. Because SQLite does not have a native array type, vectors are commonly stored either as a packed binary `BLOB` or as a fixed number of `REAL` columns. This eliminates the need for a separate vector database service while maintaining data locality.
4.  **Similarity Search & Retrieval:** When a query is submitted, the same embedding LLM converts the user's prompt into a vector. The application then performs a similarity search, typically using cosine similarity or Euclidean distance, against the stored vectors. Depending on the implementation, this computation may occur in application memory or leverage SQLite extensions optimized for vector math.
5.  **Context Assembly:** The top-ranked vectors are mapped back to their original text chunks. These chunks are assembled into a structured context window, which is injected into the prompt for the primary generative LLM to produce the final response.

This integrated approach ensures low-latency retrieval, simplified deployment, and consistent transactional behavior across both relational and vector data operations.

### Embedding LLM Responsibilities

The embedding LLM is a specialized model used to convert text into numerical vector representations. It is distinct from the generative LLM that produces natural-language answers.

*   **Semantic Encoding:** The embedding LLM maps text into a high-dimensional vector space where semantically similar texts are located closer together.
*   **Fixed-Dimension Output:** Each text chunk and user query is represented by a vector of the same dimension, enabling consistent similarity comparison.
*   **Retrieval Support:** The embedding LLM enables the application to find relevant knowledge chunks without relying solely on exact keyword matching.
*   **Query Normalization:** User questions, paraphrases, and natural-language prompts are converted into the same vector space as the stored knowledge base.
*   **Caching Opportunity:** Embeddings for stable knowledge chunks can be precomputed and reused, reducing repeated inference cost during retrieval.

### Vector Search Mechanics

The vector search process is the core mechanism that connects user intent to relevant knowledge base content.

1.  **Query Embedding:** The user's Ask AI or Deep Dive prompt is converted into a vector using the embedding LLM.
2.  **Candidate Retrieval:** The application compares the query vector against stored vectors in `ship_computer.db`.
3.  **Similarity Scoring:** Each stored vector is scored using a similarity metric such as cosine similarity, dot product, or Euclidean distance.
4.  **Top-k Selection:** The highest-scoring vectors are selected, typically the top-k most relevant chunks.
5.  **Reranking or Filtering:** Optional metadata filters, recency rules, category constraints, or reranking models may refine the candidate set.
6.  **Context Construction:** The selected chunks are ordered and formatted into a prompt context for the generative LLM.

For small to medium knowledge bases, this approach can be performed efficiently within the application. For larger corpora, the architecture can be extended with SQLite vector extensions, application-level indexing, or an external vector database while preserving the same logical retrieval workflow.

### Ask AI Data Flow

The Ask AI feature is optimized for fast, context-aware responses.

1.  **User Submission:** The user submits a question or prompt.
2.  **Query Embedding:** The application converts the prompt into a vector using the embedding LLM.
3.  **Semantic Retrieval:** The application searches `ship_computer.db` for the most relevant knowledge chunks.
4.  **Fallback Retrieval:** If semantic results are insufficient, the application may use FTS5 keyword search to recover relevant text.
5.  **Context Assembly:** The retrieved chunks are combined into a structured prompt context.
6.  **Answer Generation:** The generative LLM produces a response using the retrieved context.
7.  **Persistence:** The query, retrieved context, response, latency, and metadata are stored for auditing, caching, and future analysis.

### Deep Dive Data Flow

The Deep Dive feature is optimized for iterative, multi-step analysis.

1.  **Analysis Planning:** The application interprets the user's request and determines which data sources, sessions, knowledge entries, or prior analyses are relevant.
2.  **Multi-Table Retrieval:** The application executes SQL queries that join knowledge base entries, interaction logs, session state, and previous Deep Dive outputs.
3.  **Intermediate State Storage:** Intermediate reasoning steps, retrieved evidence, and computation states are persisted to `ship_computer.db`.
4.  **Iterative Refinement:** The application may perform additional retrieval, filtering, or analysis passes based on intermediate results.
5.  **Synthesis:** The generative LLM synthesizes the accumulated evidence into a detailed response.
6.  **Audit and Reproducibility:** The final analysis, supporting evidence, and execution metadata are stored to support review, comparison, and longitudinal tracking.

### Schema Overview

While specific table structures may evolve with feature requirements, the core schema is intended to reduce data redundancy through normalization. Key logical tables typically include:

*   `knowledge_base`: Stores static knowledge entries, document chunks, and associated metadata.
*   `sessions`: Tracks active user sessions, authentication tokens, and timestamps.
*   `interactions`: Logs specific Ask AI or Deep Dive queries, response payloads, and latency metrics for audit trails and model fine-tuning.
*   `embeddings`: Holds vector representations linked to knowledge base entries, enabling semantic retrieval.

### Schema Verification

The table names above describe expected logical entities rather than guaranteed physical names. For authoritative definitions, inspect the current `ship_computer.db` schema using `.schema` in the SQLite CLI or review the application's database migration scripts that create and update those tables.