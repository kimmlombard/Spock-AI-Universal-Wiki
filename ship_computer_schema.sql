-- ============================================================
-- ship_computer.db — Full Schema Export
-- Generated from existing database
-- ============================================================

-- TABLE: documents
CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    title TEXT NOT NULL,
    content_md TEXT,
    content_html TEXT,
    content_plain TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'kirk' CHECK(role IN ('spock','scotty','bones','kirk')),
    duty_officer TEXT,
    source_url TEXT,
    source_type TEXT DEFAULT 'local' CHECK(source_type IN ('local','web','synthesis')),
    hash_sha256 TEXT NOT NULL,
    file_mtime INTEGER NOT NULL,
    file_size INTEGER NOT NULL,
    lang TEXT,
    mime_type TEXT,
    blob_path TEXT,
    extracted_json TEXT,
    embedding BLOB,
    embedding_model_path TEXT,
    embedding_dim INTEGER,
    created_at INTEGER DEFAULT (strftime('%s','now')),
    updated_at INTEGER DEFAULT (strftime('%s','now'))
);

-- TABLE: tags
CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE
);

-- TABLE: memory_entities
CREATE TABLE memory_entities (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    type TEXT NOT NULL CHECK(type IN ('tech','concept','decision','milestone','person','project')),
    summary TEXT NOT NULL,
    first_seen_doc_id INTEGER REFERENCES documents(id),
    last_updated_doc_id INTEGER REFERENCES documents(id),
    mention_count INTEGER DEFAULT 1,
    created_at INTEGER DEFAULT (strftime('%s','now')),
    updated_at INTEGER DEFAULT (strftime('%s','now'))
);

-- TABLE: config
CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at INTEGER DEFAULT (strftime('%s','now')),
    updated_by TEXT DEFAULT 'kirk'
);

-- TABLE: quarantine
CREATE TABLE quarantine (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    reason TEXT NOT NULL,
    detected_by TEXT NOT NULL DEFAULT 'bones',
    content_snippet TEXT,
    file_hash TEXT,
    created_at INTEGER DEFAULT (strftime('%s','now'))
);

-- TABLE: captains_log
CREATE TABLE captains_log (
    id INTEGER PRIMARY KEY,
    stardate TEXT NOT NULL,
    alert_level TEXT NOT NULL CHECK(alert_level IN ('GREEN','YELLOW','RED')),
    officer TEXT NOT NULL CHECK(officer IN ('spock','scotty','bones','kirk','computer','system','away_team')),
    skill_name TEXT,
    action TEXT NOT NULL,
    target_path TEXT,
    target_doc_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    message TEXT NOT NULL,
    meta_json TEXT,
    created_at INTEGER DEFAULT (strftime('%s','now'))
);

-- TABLE: agent_queue
CREATE TABLE agent_queue (
    id INTEGER PRIMARY KEY,
    skill_name TEXT NOT NULL,
    officer TEXT NOT NULL CHECK(officer IN ('spock','scotty','bones','kirk','computer','away_team')),
    payload_json TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending','running','done','failed')),
    priority INTEGER DEFAULT 5,
    created_at INTEGER DEFAULT (strftime('%s','now')),
    started_at INTEGER,
    finished_at INTEGER,
    error_msg TEXT,
    evidence TEXT
);

-- TABLE: document_attachments
CREATE TABLE document_attachments (
    id INTEGER PRIMARY KEY,
    doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    mime_type TEXT,
    blob_path TEXT,
    extracted_text TEXT,
    sha256 TEXT
);

-- TABLE: document_tags
CREATE TABLE document_tags (
    doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (doc_id, tag_id)
);

-- TABLE: entity_mentions
CREATE TABLE entity_mentions (
    entity_id INTEGER NOT NULL REFERENCES memory_entities(id) ON DELETE CASCADE,
    doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    PRIMARY KEY (entity_id, doc_id)
);

-- TABLE: links
CREATE TABLE links (
    id INTEGER PRIMARY KEY,
    src_doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    dst_path TEXT NOT NULL,
    dst_doc_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    anchor_text TEXT,
    is_external INTEGER DEFAULT 0,
    is_broken INTEGER DEFAULT 0
);

-- FTS: docs_fts
CREATE VIRTUAL TABLE docs_fts USING fts5(
    title, content_plain, role, filename,
    content='documents', content_rowid='id',
    tokenize='porter unicode61 remove_diacritics 1'
);

-- INDEX: idx_documents_role
CREATE INDEX idx_documents_role ON documents(role);

-- INDEX: idx_documents_updated
CREATE INDEX idx_documents_updated ON documents(updated_at);

-- INDEX: idx_documents_embed_model
CREATE INDEX idx_documents_embed_model ON documents(embedding_model_path);

-- TABLE: kb_embedding_corpus (singleton — which GGUF built documents.embedding)
CREATE TABLE kb_embedding_corpus (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    model_path TEXT NOT NULL DEFAULT '',
    model_name TEXT NOT NULL DEFAULT '',
    model_id TEXT NOT NULL DEFAULT '',
    embeddings_url TEXT NOT NULL DEFAULT '',
    embeddings_dim INTEGER,
    recorded_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'wiki_scan'
);

-- TABLE: spock_profile (named suite configs; name is unique)
CREATE TABLE spock_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    stardate TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

-- TABLE: ask_timing_history (Ask AI / Deep Dive stage timings; wiped by content reset)
-- Spock_Console (app.ctx.* knobs) is intentionally NOT in this schema file.
CREATE TABLE ask_timing_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    mode TEXT NOT NULL CHECK(mode IN ('ask','deep_dive')),
    question TEXT NOT NULL,
    response_length INTEGER NOT NULL DEFAULT 0,
    total_ms INTEGER,
    retrieve_ms INTEGER,
    pack_ms INTEGER,
    llm_ms INTEGER,
    n_ctx INTEGER,
    budget INTEGER,
    budget_used INTEGER,
    budget_used_pct REAL,
    docs_used INTEGER,
    match_count INTEGER,
    inventory_shown INTEGER,
    forced_count INTEGER,
    unresolved_count INTEGER,
    max_out INTEGER,
    pack_summary TEXT,
    provider TEXT,
    stage_timings_json TEXT,
    filter_json TEXT,
    meta_json TEXT,
    updated_by TEXT DEFAULT 'ask_panel'
);

CREATE INDEX idx_ask_timing_created ON ask_timing_history(created_at DESC);
CREATE INDEX idx_ask_timing_mode_created ON ask_timing_history(mode, created_at DESC);

-- INDEX: FK child lookups (foreign_keys=ON in WarpCore/db.py) — also scanned by
-- db_maintenance/wiki_maintenance "doc_id IN (...)" count+delete sweeps.
CREATE INDEX IF NOT EXISTS idx_captains_target_doc ON captains_log(target_doc_id);
CREATE INDEX IF NOT EXISTS idx_links_src ON links(src_doc_id);
CREATE INDEX IF NOT EXISTS idx_links_dst ON links(dst_doc_id);
CREATE INDEX IF NOT EXISTS idx_attachments_doc ON document_attachments(doc_id);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_doc ON entity_mentions(doc_id);

-- INDEX: hot query paths
-- RED-alert probe (wiki_agent.ship_status) polls alert_level + created_at window.
CREATE INDEX IF NOT EXISTS idx_captains_alert_created ON captains_log(alert_level, created_at);
-- Queue claim (get_next_task): status filter ordered by priority, created_at.
CREATE INDEX IF NOT EXISTS idx_agent_queue_claim ON agent_queue(status, priority, created_at);
-- Enqueue dedupe (skill_name + active status).
CREATE INDEX IF NOT EXISTS idx_agent_queue_skill_status ON agent_queue(skill_name, status);
-- Note: no index for "WHERE embedding IS NOT NULL" — the predicate matches
-- (nearly) every row and SQLite 3.53 never auto-selects a partial index for it
-- once stats exist; a table scan is the optimal plan (verified via EQP).

-- TRIGGER: documents_ad
CREATE TRIGGER documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO docs_fts(docs_fts, rowid) VALUES ('delete', old.id);
END;

-- TRIGGER: documents_ai
CREATE TRIGGER documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO docs_fts(rowid, title, content_plain, role, filename)
    VALUES (new.id, new.title, new.content_plain, new.role, new.filename);
END;

-- TRIGGER: documents_au
CREATE TRIGGER documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO docs_fts(docs_fts, rowid) VALUES ('delete', old.id);
    INSERT INTO docs_fts(rowid, title, content_plain, role, filename)
    VALUES (new.id, new.title, new.content_plain, new.role, new.filename);
END;
