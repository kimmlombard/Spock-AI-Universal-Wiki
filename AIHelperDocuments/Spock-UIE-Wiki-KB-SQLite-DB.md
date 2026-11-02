
Would you like me to expand on any specific aspect of this plan, such as detailed API designs, database schema changes, or specific implementation strategies for any module?

Redesign of Sqlite3 DBs for database optimization

6440 tokens3.9s1636.04 tokens/s

Reasoning

Toggle content
Spock-to-Bridge: Optimized SQLite3 Database Redesign
====================================================
Executive Summary

-----------------

A comprehensive database architecture redesign that eliminates schema duplication, centralizes configuration, optimizes query performance, and provides a unified knowledge base for the Spock application.

* * *

📊 Current vs. Proposed Architecture
------------------------------------

### Current Schema Problems

| Issue                                 | Impact                            |
| ------------------------------------- | --------------------------------- |
| Multiple `ship_computer.db` instances | Data fragmentation, sync issues   |
| JSON configs stored externally        | No ACID compliance, version drift |
| No foreign keys                       | Referential integrity violations  |
| Unindexed text columns                | Slow searches on large datasets   |
| Mixed data types                      | Inefficient storage, query issues |

* * *

🏗️ Optimized Database Schema
-----------------------------

### **1. Centralized Console Database**

sql
    -- ============================================================
    -- ship_computer.db (Primary Knowledge Base + Console)
    -- ============================================================
    -- ──────────────────────────────────────────────────────────────
    -- 1.1 Console Configuration (replaces JSON configs)
    -- ──────────────────────────────────────────────────────────────
    CREATE TABLE Spock_Console (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        version TEXT DEFAULT '1.0.0',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        -- Backend Configuration
        llama_host TEXT DEFAULT 'localhost',
        llama_port INTEGER DEFAULT 8081,
        lm_studio_host TEXT DEFAULT 'localhost',
        lm_studio_port INTEGER DEFAULT 1234,
        openai_compat_base_url TEXT DEFAULT '',

        -- RAG Configuration
        embedding_profile TEXT DEFAULT 'default',
        rag_api_enabled INTEGER DEFAULT 1,
        rag_api_host TEXT DEFAULT 'localhost',
        rag_api_port INTEGER DEFAULT 8080,

        -- Search Preferences
        default_search_mode TEXT DEFAULT 'hybrid',
        default_top_k INTEGER DEFAULT 24,
        default_context_budget INTEGER DEFAULT 96000,

        -- File Management
        documents_root TEXT DEFAULT '',
        models_root TEXT DEFAULT '',
        quarantine_root TEXT DEFAULT '',

        -- UI Preferences
        theme TEXT DEFAULT 'dark',
        sidebar_width INTEGER DEFAULT 250,
        font_size INTEGER DEFAULT 12,

        -- System Flags
        auto_scan INTEGER DEFAULT 1,
        auto_index INTEGER DEFAULT 1,
        enable_mcp INTEGER DEFAULT 1,
        last_scan TIMESTAMP,

        PRIMARY KEY (id),
        UNIQUE(name)
    );

    -- ──────────────────────────────────────────────────────────────
    -- 1.2 Settings Categories (Hierarchical Configuration)
    -- ──────────────────────────────────────────────────────────────

    CREATE TABLE Settings_Categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        parent_id INTEGER REFERENCES Settings_Categories(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        description TEXT,
        order_index INTEGER DEFAULT 0,
        is_expanded INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(parent_id, name)
    );

    -- ──────────────────────────────────────────────────────────────
    -- 1.3 Individual Settings (Typed Storage)
    -- ──────────────────────────────────────────────────────────────

    CREATE TABLE Settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id INTEGER NOT NULL REFERENCES Settings_Categories(id),
        key TEXT NOT NULL,
        value_type TEXT NOT NULL CHECK (value_type IN ('string', 'integer', 'boolean', 'json')),
        value TEXT NOT NULL,
        description TEXT,
        default_value TEXT,
        sensitive INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(category_id, key)
    );

    -- ──────────────────────────────────────────────────────────────
    -- 1.4 Secret Values (Encrypted Storage)
    -- ──────────────────────────────────────────────────────────────

    CREATE TABLE Secrets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT NOT NULL UNIQUE,
        value TEXT NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- ──────────────────────────────────────────────────────────────
    -- 1.5 Embedding Profile Management
    -- ──────────────────────────────────────────────────────────────

    CREATE TABLE Embedding_Profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT,
        model TEXT,
        model_path TEXT,
        dimensions INTEGER,
        quantized INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        active INTEGER DEFAULT 0
    );

    -- ──────────────────────────────────────────────────────────────
    -- 1.6 Model Registry (Centralized Model Metadata)
    -- ──────────────────────────────────────────────────────────────

    CREATE TABLE Models (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        provider TEXT NOT NULL,
        model_type TEXT NOT NULL,  -- chat, embedding, r1, etc.
        provider_name TEXT NOT NULL,  -- huggingface, ollama, local
        model_id TEXT NOT NULL,
        file_path TEXT,
        file_size INTEGER DEFAULT 0,  -- bytes
        sha256 TEXT,
        downloaded_at TIMESTAMP,
        last_used TIMESTAMP,
        is_active INTEGER DEFAULT 0,
        context_size INTEGER,
        context_window INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(name, provider, model_id)
    );

    -- ──────────────────────────────────────────────────────────────
    -- 1.7 Model Cache Index
    -- ──────────────────────────────────────────────────────────────

    CREATE INDEX idx_models_path ON Models(file_path);
    CREATE INDEX idx_models_type ON Models(model_type);
    CREATE INDEX idx_models_active ON Models(is_active);
    CREATE INDEX idx_models_downloaded_at ON Models(downloaded_at);

    -- ──────────────────────────────────────────────────────────────
    -- 1.8 Inference Sessions (Performance Tracking)
    -- ──────────────────────────────────────────────────────────────

    CREATE TABLE Inference_Sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_id INTEGER NOT NULL REFERENCES Models(id),
        session_type TEXT NOT NULL,  -- chat, completion, embedding
        tokens_input INTEGER DEFAULT 0,
        tokens_output INTEGER DEFAULT 0,
        latency_ms INTEGER DEFAULT 0,
        status TEXT DEFAULT 'completed',
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP
    );

    CREATE INDEX idx_sessions_model ON Inference_Sessions(model_id);
    CREATE INDEX idx_sessions_status ON Inference_Sessions(status);

    -- ──────────────────────────────────────────────────────────────
    -- 1.9 MCP Adapter Configuration
    -- ──────────────────────────────────────────────────────────────

    CREATE TABLE MCP_Adapters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        adapter_name TEXT NOT NULL,
        host TEXT,
        port INTEGER,
        path TEXT,
        enabled INTEGER DEFAULT 1,
        version TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- ──────────────────────────────────────────────────────────────
    -- 1.10 System Diagnostics Cache
    -- ──────────────────────────────────────────────────────────────

    CREATE TABLE Diagnostics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_type TEXT NOT NULL,  -- hardware, optimization, health
        results TEXT NOT NULL,  -- JSON blob
        recommendations TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expired_at TIMESTAMP
    );

    CREATE INDEX idx_diagnostics_type ON Diagnostics(scan_type);

* * *

### **2. Knowledge Base Database**

sql
    -- ============================================================
    -- knowledge_base.db (Optimized for RAG Operations)
    -- ============================================================
    -- ──────────────────────────────────────────────────────────────
    -- 2.1 Documents (Core Content)
    -- ──────────────────────────────────────────────────────────────
    CREATE TABLE Documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        path TEXT NOT NULL,
        file_size INTEGER DEFAULT 0,
        mime_type TEXT,
        parent_id INTEGER,
        folder_path TEXT,
        content_hash TEXT,  -- For change detection
        content_plain TEXT,  -- Extracted plain text
        content_html TEXT,   -- Extracted HTML (optional)
        content_vector TEXT,  -- Vector embedding (stored as text)
        embeddings_url TEXT,  -- URL to embedding service
        embedding_dimensions INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        indexed INTEGER DEFAULT 0,

        -- Hybrid Search Optimization
        searchable_text TEXT,  -- FTS5-compatible text
        searchable_tags TEXT,  -- Comma-separated tags
        category TEXT,
        language TEXT,

        FOREIGN KEY (parent_id) REFERENCES Documents(id)
    );

    -- ──────────────────────────────────────────────────────────────
    -- 2.2 FTS5 Full-Text Search Index
    -- ──────────────────────────────────────────────────────────────

    CREATE VIRTUAL TABLE documents_fts USING fts5(
        searchable_text,
        searchable_tags,
        title,
        content,
        content_rowid=id
    );

    -- ──────────────────────────────────────────────────────────────
    -- 2.3 Embedding Results (Vector Cache)
    -- ──────────────────────────────────────────────────────────────

    CREATE TABLE Embedding_Results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER NOT NULL REFERENCES Documents(id),
        query_text TEXT NOT NULL,
        embedding_vector TEXT NOT NULL,  -- Stored as JSON array or serialized
        model TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(document_id, query_text)
    );

    CREATE INDEX idx_embeddings_document ON Embedding_Results(document_id);
    CREATE INDEX idx_embeddings_model ON Embedding_Results(model);

    -- ──────────────────────────────────────────────────────────────
    -- 2.4 Document Relationships (Knowledge Graph)
    -- ──────────────────────────────────────────────────────────────

    CREATE TABLE Document_Relationships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id_1 INTEGER NOT NULL REFERENCES Documents(id),
        document_id_2 INTEGER NOT NULL REFERENCES Documents(id),
        relationship_type TEXT NOT NULL,  -- cites, references, duplicates, similar
        confidence REAL DEFAULT 1.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(document_id_1, document_id_2, relationship_type)
    );

    CREATE INDEX idx_relationships_doc1 ON Document_Relationships(document_id_1);
    CREATE INDEX idx_relationships_doc2 ON Document_Relationships(document_id_2);

    -- ──────────────────────────────────────────────────────────────
    -- 2.5 Document Tags (Many-to-Many)
    -- ──────────────────────────────────────────────────────────────

    CREATE TABLE Document_Tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER NOT NULL REFERENCES Documents(id) ON DELETE CASCADE,
        tag TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(document_id, tag)
    );

    CREATE INDEX idx_tags_document ON Document_Tags(document_id);
    CREATE INDEX idx_tags_name ON Document_Tags(tag);

    -- ──────────────────────────────────────────────────────────────
    -- 2.6 Search Logs (Analytics)
    -- ──────────────────────────────────────────────────────────────

    CREATE TABLE Search_Logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        query TEXT NOT NULL,
        top_k INTEGER DEFAULT 24,
        results_found INTEGER DEFAULT 0,
        query_time_ms INTEGER DEFAULT 0,
        filter_applied TEXT,
        user_session TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX idx_search_query ON Search_Logs(query);
    CREATE INDEX idx_search_time ON Search_Logs(created_at);

    -- ──────────────────────────────────────────────────────────────
    -- 2.7 User Notes (Personal Annotations)
    -- ──────────────────────────────────────────────────────────────

    CREATE TABLE Document_Notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER NOT NULL REFERENCES Documents(id) ON DELETE CASCADE,
        note TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(document_id, note)
    );

    CREATE INDEX idx_notes_document ON Document_Notes(document_id);

* * *

### **3. System Event Database**

sql
    -- ============================================================
    -- captains_log.db (System Events & Audit Trail)
    -- ============================================================
    CREATE TABLE Events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        source TEXT,
        message TEXT NOT NULL,
        level TEXT DEFAULT 'INFO',  -- DEBUG, INFO, WARNING, ERROR, CRITICAL
        metadata TEXT,  -- JSON
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        processed INTEGER DEFAULT 0,
        UNIQUE(event_type, source, message, created_at)
    );
    CREATE INDEX idx_events_type ON Events(event_type);
    CREATE INDEX idx_events_level ON Events(level);
    CREATE INDEX idx_events_time ON Events(created_at);
    CREATE INDEX idx_events_processed ON Events(processed);

    -- Partitions for performance (optional, can be managed via views)
    CREATE TABLE Events_Current (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        source TEXT,
        message TEXT NOT NULL,
        level TEXT DEFAULT 'INFO',
        metadata TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(event_type, source, message, created_at)
    );

    CREATE TABLE Events_Archive (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        source TEXT,
        message TEXT NOT NULL,
        level TEXT DEFAULT 'INFO',
        metadata TEXT,
        archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(event_type, source, message, archived_at)
    );

* * *

### **4. Task Queue Database**

sql
    -- ============================================================
    -- agents_queue.db (Background Task Processing)
    -- ============================================================
    CREATE TABLE Agents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_name TEXT NOT NULL,
        agent_type TEXT NOT NULL,
        skill TEXT,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        active INTEGER DEFAULT 1
    );
    CREATE TABLE Tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id INTEGER NOT NULL REFERENCES Agents(id),
        task_type TEXT NOT NULL,
        task_name TEXT NOT NULL,
        description TEXT,
        status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'success', 'failed')),
        priority INTEGER DEFAULT 5,
        payload TEXT,  -- JSON payload
        result TEXT,  -- JSON result
        error_message TEXT,
        retries INTEGER DEFAULT 0,
        max_retries INTEGER DEFAULT 3,
        scheduled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(task_type, task_name, status)
    );

    CREATE INDEX idx_tasks_agent ON Tasks(agent_id);
    CREATE INDEX idx_tasks_status ON Tasks(status);
    CREATE INDEX idx_tasks_priority ON Tasks(priority);
    CREATE INDEX idx_tasks_scheduled ON Tasks(scheduled_at);
    CREATE INDEX idx_tasks_type ON Tasks(task_type);

    -- Task History (for debugging)
    CREATE TABLE Task_History (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER NOT NULL REFERENCES Tasks(id) ON DELETE CASCADE,
        log_entry TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX idx_history_task ON Task_History(task_id);

* * *

### **5. Quarantine Database**

sql
    -- ============================================================
    -- quarantine.db (Suspicious Files)
    -- ============================================================
    CREATE TABLE Quarantine_Items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        original_path TEXT NOT NULL,
        quarantined_path TEXT NOT NULL,
        file_size INTEGER DEFAULT 0,
        detection_method TEXT,
        confidence REAL DEFAULT 1.0,
        reason TEXT NOT NULL,
        flagged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        reviewed_at TIMESTAMP,
        action TEXT DEFAULT 'pending' CHECK (action IN ('pending', 'reviewed', 'deleted', 'restored')),
        reviewer TEXT,
        notes TEXT,
        UNIQUE(original_path)
    );
    CREATE INDEX idx_quarantine_path ON Quarantine_Items(original_path);
    CREATE INDEX idx_quarantine_flagged ON Quarantine_Items(flagged_at);
    CREATE INDEX idx_quarantine_action ON Quarantine_Items(action);

* * *

📈 Performance Optimization Indexes
-----------------------------------

sql
    -- ============================================================
    -- COMPREHENSIVE INDEX STRATEGY
    -- ============================================================
    -- ──────────────────────────────────────────────────────────────
    -- Knowledge Base Optimizations
    -- ──────────────────────────────────────────────────────────────
    -- Document lookups by path
    CREATE INDEX idx_documents_path ON Documents(path);
    CREATE INDEX idx_documents_folder ON Documents(folder_path);

    -- Document content for filtering
    CREATE INDEX idx_documents_category ON Documents(category);
    CREATE INDEX idx_documents_language ON Documents(language);

    -- FTS5 already handles full-text search efficiently

    -- ──────────────────────────────────────────────────────────────
    -- Console Configuration Optimizations
    -- ──────────────────────────────────────────────────────────────

    -- Settings lookups by category
    CREATE INDEX idx_settings_category ON Settings(category_id);
    CREATE INDEX idx_settings_key ON Settings(key);

    -- ──────────────────────────────────────────────────────────────
    -- Model Optimizations
    -- ──────────────────────────────────────────────────────────────

    -- Model discovery
    CREATE INDEX idx_models_provider ON Models(provider);
    CREATE INDEX idx_models_model_id ON Models(model_id);
    CREATE INDEX idx_models_type ON Models(model_type);

    -- ──────────────────────────────────────────────────────────────
    -- Event Log Optimizations
    -- ──────────────────────────────────────────────────────────────

    -- Event filtering
    CREATE INDEX idx_events_type_level ON Events(event_type, level);
    CREATE INDEX idx_events_time_range ON Events(created_at);
    CREATE INDEX idx_events_processed ON Events(processed);

    -- ──────────────────────────────────────────────────────────────
    -- Search Log Optimizations
    -- ──────────────────────────────────────────────────────────────

    -- Query analysis
    CREATE INDEX idx_search_query_length ON Search_Logs((length(query)));
    CREATE INDEX idx_search_results ON Search_Logs(results_found);
    CREATE INDEX idx_search_query_time ON Search_Logs(query_time_ms);

    -- ──────────────────────────────────────────────────────────────
    -- Materialized Views for Common Queries
    -- ──────────────────────────────────────────────────────────────

    -- Most used models
    CREATE VIEW v_models_usage AS
    SELECT 
        id,
        name,
        model_id,
        provider,
        last_used,
        COUNT(*) as usage_count
    FROM Inference_Sessions
    WHERE status = 'completed'
    GROUP BY model_id
    ORDER BY usage_count DESC;

    -- Recent documents
    CREATE VIEW v_documents_recent AS
    SELECT 
        id,
        title,
        path,
        file_size,
        indexed,
        created_at
    FROM Documents
    WHERE indexed = 1
    ORDER BY updated_at DESC
    LIMIT 1000;

    -- Active settings
    CREATE VIEW v_settings_active AS
    SELECT 
        s.id,
        s.key,
        s.value,
        s.description,
        c.name as category_name
    FROM Settings s
    JOIN Settings_Categories c ON s.category_id = c.id
    WHERE s.value_type != 'json';

    -- ──────────────────────────────────────────────────────────────
    -- Triggers for Maintained Fields
    -- ──────────────────────────────────────────────────────────────

    -- Auto-update timestamps
    CREATE TRIGGER trg_documents_updated
    AFTER UPDATE ON Documents
    BEGIN
        UPDATE Documents SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
    END;

    CREATE TRIGGER trg_tasks_status_updated
    AFTER UPDATE ON Tasks
    BEGIN
        UPDATE Tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
    END;

-- ============================================================
-- uie_capture.db — Full Schema
-- Search + Save captures (research blobs) and Spock profiles
-- ============================================================

-- TABLE: captures
CREATE TABLE captures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    filepath TEXT,
    filetype TEXT,
    captured_at TEXT,
    content BLOB,
    source_url TEXT,
    source_kind TEXT,
    promoted_at TEXT,
    promoted_path TEXT,
    file_size INTEGER
);

-- TABLE: spock_profile
CREATE TABLE spock_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    stardate TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

-- INDEX: idx_captures_captured_at
CREATE INDEX idx_captures_captured_at ON captures(captured_at);

-- INDEX: idx_captures_filename
CREATE INDEX idx_captures_filename ON captures(filename);

