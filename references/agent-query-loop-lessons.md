# Agent Query Loop Lessons

Condensed lessons from iterative SQL-ManyThing dogfooding. Use this when improving the skill prompt, README/AGENTS docs, or Phase 3 trace workflow.

## Phase 3 is a SQL context, not a CLI context

Agents stay more reliable when trace search and trace tagging are expressed as SQL over `sqlite3 :trace`. A separate CLI command for `search` or `tag` makes the agent switch mental modes and is easy to skip.

Preferred pre-flight shape:

```bash
SQL-ManyThing-query-log import
sqlite3 :trace "
WITH intent(term) AS (
  VALUES ('files'), ('ext'), ('path'), ('symbols'), ('file_enrich'),
         ('graph'), ('README'), ('package'), ('src')
)
SELECT id, project, tag, note, substr(sql_text, 1, 180) AS sql_preview
FROM query_trace
WHERE project='<project>'
  AND (tag IS NOT NULL OR EXISTS (
    SELECT 1 FROM intent WHERE lower(sql_text) LIKE '%' || lower(term) || '%'
  ))
ORDER BY tag IS NULL, id DESC
LIMIT 12;"
```

Preferred tagging shape:

```bash
sqlite3 :trace "
INSERT INTO query_notes (log_id, note, tag, created_at)
VALUES (<id>, '<reuse note>', 'useful_pattern', strftime('%s','now'));
"
```

## Expand user intent into SQL-facing terms

Do not search trace history only with the user's natural words. Expand with world knowledge into terms likely to appear inside SQL:

- implementation overview: `files`, `ext`, `path`, `symbols`, `file_enrich`, `graph`, `README`, `package`, `src`
- library layout: `entry`, `exports`, `package`, `README`, `src`, `test`, `benchmark`
- Unreal reflection: `UCLASS`, `USTRUCT`, `UENUM`, `UFUNCTION`, `file_enrich`, `uht_functions`

## Virtual path discipline

`/manything/<project>/source.db` is a sqlite wrapper virtual path, not a filesystem path. Do not verify it with `ls` or `test -f`. Verify it by opening it with sqlite:

```bash
sqlite3 /manything/<project>/source.db "SELECT COUNT(*) FROM files"
```

Once the virtual path works, use it for query-time SQL so wrapper logging captures the session. Direct `.srcidx/source.db` is setup/debug only.

## Overview query discipline

For broad overviews, group before listing. Avoid dumping all files.

Good first probes:

```sql
SELECT COUNT(*) FROM files;
SELECT ext, COUNT(*) FROM files GROUP BY ext ORDER BY COUNT(*) DESC;
SELECT substr(path,1,instr(path||'/', '/')-1) AS top, COUNT(*)
FROM files GROUP BY top ORDER BY COUNT(*) DESC LIMIT 20;
SELECT COUNT(*) FROM file_enrich WHERE symbols IS NOT NULL AND symbols != '[]';
SELECT COUNT(*) FROM enrich_graphify_nodes;
SELECT COUNT(*) FROM enrich_graphify_edges;
SELECT DISTINCT relation FROM enrich_graphify_edges LIMIT 20;
```

Avoid:

```sql
SELECT path FROM files WHERE path LIKE 'src/%' ORDER BY path;
```

unless paired with `LIMIT`, grouping, or a narrowed predicate.

## Large DB maintenance

SQLite `DROP TABLE` does not shrink a database file. Full rebuild scripts should delete the old DB first when the goal is a compact replacement. VACUUM can work, but on Windows-hosted DBs it may be slower or hit file-handle/permission issues; delete-and-rebuild matches SQL-ManyThing's full rebuild model.

## Unreal profile lesson

`.gitignore` is not an indexing-value policy. Unreal installed builds need both `.gitignore` and a profile:

- ext allowlist for query value
- path policy for high-noise directories
- UHT enrich remains the main Phase 2 path

`unreal-installed-core` keeps DB size near the earlier baseline while preserving UHT coverage.

## Depth segmentation causes redundant substr queries (→ scope_end_offset fix)

**Problem (2026-06-02):** Agent was making 2-3x more queries than necessary when extracting function bodies. Root cause: `v_enriched.block_content` returns ONE depth segment at a time, but functions span multiple depth levels (signature at depth=N, body at N+1, N+2...). Agent saw only the header, then manually stitched deeper segments via `substr(f.content, start, end-start)` — 3-4 queries per function.

Example: `PtyBridge.spawn()` — 4 queries (FTS5 → block_content header → depth verification → substr stitch). `_make_tui_argv()` — 3 queries. `_resolve_chat_argv()` — 2 queries (truncated first, continuation second).

**Fix:** Added `scope_end_offset` to `enrich_depth_segments` (computed once via SQL UPDATE after segment insertion) and `block_content_full` to `v_enriched` VIEW. `scope_end_offset` = start of next segment at same-or-shallower depth (or EOF). One `block_content_full` query now returns the complete function body.

Result: 10 queries → 4 queries (60% reduction). See `SKILL.md` "block_content vs block_content_full" section and the split-signature edge case.

**Implementation:**
- `scripts/phase2/enrich_depth_segments.py`: `ensure_schema()` adds `scope_end_offset` column; `compute_scope_end_offsets()` runs one UPDATE after all segments inserted
- `scripts/phase2/create_enriched_view.py`: VIEW adds `scope_end_offset` + `block_content_full` columns
- 25万 segments computed in ~1s for hermes-agent (3979 files)

**Key SQL:**
```sql
UPDATE enrich_depth_segments SET scope_end_offset = (
    SELECT COALESCE(
        MIN(ds2.start_offset),
        (SELECT length(f.content) FROM files f WHERE f.id = enrich_depth_segments.file_id)
    )
    FROM enrich_depth_segments ds2
    WHERE ds2.file_id = enrich_depth_segments.file_id
      AND ds2.start_offset > enrich_depth_segments.start_offset
      AND ds2.depth_level <= enrich_depth_segments.depth_level
);
```

**Known limitation:** Python/TSX functions with multi-line signatures may split across two depth=0 segments. The PROBE finds the def-line segment (small block_content_full); the body is in the adjacent same-depth segment. Query the next depth=0 row via `start_offset > <def_line_offset>`. Affects ~10% of top-level functions.
