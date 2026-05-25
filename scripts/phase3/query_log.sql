-- =============================================================================
-- SQL-ManyThing Phase 3 — query_log.db schema
-- =============================================================================
-- query_log     — 原始查询日志（从 pending.jsonl import 后写入）
-- query_notes   — 人工标注（tag, note），关联到 query_log
-- query_trace   — VIEW: query_log LEFT JOIN query_notes（agent 查历史用）
-- =============================================================================

CREATE TABLE IF NOT EXISTS query_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   INTEGER NOT NULL,          -- unix epoch
    project     TEXT NOT NULL,
    db_path     TEXT NOT NULL,              -- virtual path (/srcidx/<p>/source.db)
    sql_text    TEXT NOT NULL,
    rows_hint   INTEGER,                   -- result row count (optional, from wrapper)
    imported_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS query_notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id      INTEGER NOT NULL REFERENCES query_log(id) ON DELETE CASCADE,
    note        TEXT NOT NULL,
    tag         TEXT,                       -- 'fast_path' | 'useful_pattern' | NULL
    created_at  INTEGER NOT NULL            -- unix epoch
);

CREATE VIEW IF NOT EXISTS query_trace AS
SELECT
    ql.id,
    ql.timestamp,
    ql.project,
    ql.sql_text,
    qn.note,
    qn.tag,
    qn.created_at AS noted_at
FROM query_log ql
LEFT JOIN query_notes qn ON qn.log_id = ql.id;

-- Index for common lookups
CREATE INDEX IF NOT EXISTS idx_query_log_project ON query_log(project);
CREATE INDEX IF NOT EXISTS idx_query_log_timestamp ON query_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_query_notes_tag ON query_notes(tag);
