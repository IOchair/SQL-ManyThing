# Phase 3 Trace Pre-flight Debugging

Use this when an agent claims SQL-ManyThing trace is unavailable or when a query run produces no `:trace` history.

## Core rule

`/manything/<project>/source.db` is a sqlite wrapper virtual path, not a filesystem path. `ls /manything/<project>/source.db` is not a valid check and may fail even when the wrapper works.

`query_trace` lives in the global `:trace` database, not in the project `.srcidx/source.db`. Project DB `.tables` should not contain `query_trace`.

## Correct health checks

```bash
export PATH="$HOME/.local/bin:$PATH"
SQL-ManyThing-query-log import
sqlite3 :trace ".tables"
sqlite3 :trace "SELECT id, project, substr(sql_text,1,80), tag FROM query_trace WHERE project='<project>' ORDER BY id DESC LIMIT 5"
sqlite3 /manything/<project>/source.db "SELECT COUNT(*) FROM files"
```

Expected:

- `sqlite3 :trace ".tables"` lists `query_log`, `query_notes`, and `query_trace`.
- `sqlite3 /manything/<project>/source.db ...` returns project data.
- The project `.srcidx/source.db` does not need trace tables.

## Common false diagnosis

Wrong sequence:

```bash
ls /manything/<project>/source.db
sqlite3 /path/to/project/.srcidx/source.db ".tables"
```

Why wrong:

- `ls` bypasses the sqlite wrapper, so it cannot prove virtual path availability.
- Opening `.srcidx/source.db` directly bypasses wrapper logging.
- Checking `.tables` on the project DB for `query_trace` checks the wrong database.

## Query logging requirement

Once alias and wrapper are configured, query-time SQL should use:

```bash
sqlite3 /manything/<project>/source.db "SELECT ..."
```

## Pre-flight template

Use this sequence at the start of every agent session:

```bash
# 1. Import any pending traces from previous sessions
SQL-ManyThing-query-log import

# 2. Check trace tables exist
sqlite3 :trace ".tables"
# Expected: query_log  query_notes  query_trace

# 3. Find tagged traces for this project
sqlite3 :trace "
SELECT id, tag, note, substr(sql_text, 1, 120)
FROM query_trace
WHERE project='<project>' AND tag IS NOT NULL
ORDER BY id DESC
LIMIT 10;
"

# 4. Find untagged but relevant traces
sqlite3 :trace "
SELECT id, project, substr(sql_text, 1, 120)
FROM query_trace
WHERE project='<project>' AND tag IS NULL
  AND (sql_text LIKE '%files%' OR sql_text LIKE '%symbol%' OR sql_text LIKE '%ext%')
ORDER BY id DESC
LIMIT 5;
"

# 5. Verify project index is accessible
sqlite3 /manything/<project>/source.db "SELECT COUNT(*) FROM files;"
```

Direct project DB queries are acceptable for setup/debugging only. They do not append to `pending.jsonl`, so they will not appear in `:trace` after import.

## Evaluation of broad overview runs

For implementation overviews, metadata probes are acceptable:

```sql
SELECT COUNT(*) FROM files;
SELECT ext, COUNT(*) FROM files GROUP BY ext;
SELECT COUNT(*) FROM file_enrich;
SELECT DISTINCT relation FROM enrich_graphify_edges;
```

But keep path listings bounded with `LIMIT` or grouped by directory. For source extraction, prefer symbol/FTS5/instr probes before `substr`, unless reading small root documents such as `package.json` or `README.md` for project overview context.
