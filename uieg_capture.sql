-- ============================================================
-- uieg_capture.db — Full Schema
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
