---
name: sql-manything
description: A* source-code search over SQL-ManyThing SQLite index. Abstraction Frame + Budget-Annotated PROBE/EXTRACT templates. No substr guessing, no whole-file reads.
version: 4.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [code-search, sqlite, fts5, ast, a-star, source-index]
    related_skills: []
---

# SQL-ManyThing

## Overview

SQL-ManyThing indexes a source tree into a SQLite DB. Query model: an **Abstraction Frame** that decomposes a question into layers, then for each layer runs **PROBE** (find file+block via FTS5 or `block_content LIKE`) then **EXTRACT** (get full body via `block_content_full`). Every SQL query is annotated with its budget cost and intent.

## When to Use

- A project has `.srcidx/source.db`.
- The user asks for code search, tracing, implementation lookup, or architecture inspection.
- Minimize token cost — no whole-file reads. Do not use when no index exists.

## A* Search Model

| A* term | Meaning |
|---|---|
| State space | `files` + `v_enriched` — all source files x their depth segments |
| s0 | user's question |
| Goal g | `v_enriched.block_content` locates; `block_content_full` returns full body (EXTRACT) |
| Operator | one SQL query (PROBE via FTS5 + LIKE / EXTRACT via `block_content_full`) |
| g(n) | SQL queries consumed so far |
| h(n) | BM25(-rank) — FTS5 relevance + `:trace` history reuse |
| f(n) = g(n) + h(n) | minimize |
| Track | `→ [budget] L<N>-P/E: g=<N>` after each query |
| Goal test | `block_content_full` returns complete target evidence; stop. New question = new frame |

## Core Schema

| Table | Purpose |
|---|---|
| `files` | indexed files: path, ext, content |
| `files_fts` | FTS5 trigram index over path and content |
| `v_enriched` | **Primary surface.** VIEW: file_id, file_path, ext, depth_level, start_offset, end_offset, scope_end_offset, block_content, block_content_full, refs_to, refs_from |
| `enrich_file_refs` | cross-file imports: file_id, target_raw, target_file_id, line_num |
| `enrich_file_deps` | transitive deps: (file_id, dep_file_id, direction, depth) |
| `enrich_depth_segments` | brace/indent offset ranges + scope_end_offset |

## block_content vs block_content_full

`v_enriched` has two content columns:

| Column | Scope | When to use |
|---|---|---|
| `block_content` | Immediate depth segment (signature, header, single brace block) | PROBE previews; locating the right depth level |
| `block_content_full` | Full enclosing scope — from this segment's start to the next same-or-shallower depth segment | **EXTRACT — always prefer this over block_content for function/method/class bodies** |

`block_content_full` eliminates the multi-step pattern of finding a header at depth=N then manually stitching depth=N+1, N+2 segments. One query gets the complete function body.  When `length(block_content) < length(block_content_full)`, the body spans multiple depth segments — use `block_content_full`.

The `scope_end_offset` column tells you where the enclosing scope ends (start_offset of next depth≤N segment, or EOF). Use it to detect truncation without extracting: `scope_end_offset - start_offset > end_offset - start_offset` means `block_content_full` has more content than `block_content`.

**Escape hatch** (very rare): when block_content_full has the right offsets but the VIEW's computed TEXT is truncated by a SQLite or transport limit, fall back to:
```sql
SELECT substr(f.content, ve.start_offset + 1, ve.scope_end_offset - ve.start_offset)
FROM v_enriched ve JOIN files f ON f.id = ve.file_id
WHERE ve.file_path = '<file>' AND ve.start_offset = <offset>;
```
This is the only valid reason to leave v_enriched for raw files.content. Do NOT use offset guessing — offsets must come from v_enriched columns.

### Split-signature edge case (multi-line defs / typed params)

When a function signature spans multiple lines (Python multi-line params, TSX generic type annotations), the PROBE may find the **def-line segment** whose `block_content_full` is only the signature, not the body. The actual function body starts in the **adjacent same-depth segment**.

**Pattern**: when PROBE returns a segment with unexpectedly small `block_content_full` (< 200 bytes for a function you know is large), query the next segment at the same `depth_level`:

```sql
-- Step 1: PROBE finds the def line (may have small block_content_full)
SELECT start_offset, length(block_content_full) AS full_len,
       substr(block_content_full, 1, 80) AS head
FROM v_enriched
WHERE file_path = '<file>'
  AND block_content LIKE '%def <func>%'
  AND depth_level = 0
ORDER BY start_offset;

-- Step 2: if full_len is small (< 200 bytes), get the NEXT depth=0 segment
SELECT block_content_full FROM v_enriched
WHERE file_path = '<file>'
  AND depth_level = 0
  AND start_offset = (
    SELECT MIN(start_offset) FROM v_enriched ve2
    WHERE ve2.file_path = v_enriched.file_path
      AND ve2.depth_level = 0
      AND ve2.start_offset > <step1_start_offset>
  );
```

This affects ~10% of functions — those with signatures that the depth segmenter splits from their bodies.  Always check `length(block_content_full)` before treating EXTRACT as terminal.

Two SQL shapes, always used within a PROBE or EXTRACT slot of a layer.

**Probe shape (find files + blocks):**

```sql
-- <intent: what we're looking for>
SELECT f.path, rank
FROM files_fts, files f
WHERE files_fts MATCH '<keyword>'
  AND files_fts.rowid = f.id
  AND f.path NOT LIKE '%test%'
ORDER BY rank LIMIT 15;
```

When path is known or block content is the target:

```sql
SELECT file_path, depth_level, length(block_content) AS bytes,
       substr(block_content, 1, 80) AS preview
FROM v_enriched
WHERE file_path = '<exact_path>'
   OR block_content LIKE '%<keyword>%'
ORDER BY depth_level, start_offset;
```

**Extract shape (get full body via block_content_full — termination):**

```sql
SELECT block_content_full FROM v_enriched
WHERE file_path = '<file>' AND depth_level = <N>
  AND start_offset = <offset>
LIMIT 1;
```

## Abstraction Frame (Mandatory — Write Before SQL)

Write this before any SQL. Frame is the plan; SQL fills in the slots.

```
═══ A* BUDGET FRAME  #<N> ═══
QUERY: <one sentence — what are we looking for>
LAYERS:
  <label>: <role description>
    PROBE:   discover target file+block
    EXTRACT: retrieve exact block content
    NO:      anti-pattern for this layer
```

**Rules:**
1. Every layer = PROBE then EXTRACT. Never skip PROBE.
2. EXTRACT uses `block_content_full` for function/method/class bodies (one query gets the full scope). `block_content` is for PROBE previews only.
3. Total EXTRACT output ≤ 6000 chars per feature. Split into more layers if overflow.
4. Budget annotation on EVERY query — intent above, `[budget]` after.
5. Goal test: `block_content_full` returns complete body. Stop. New question = new frame.

## Full-Stack Example with Annotated SQL

Layer 1 — frontend component:

```sql
-- [intent] find the xterm.js terminal component in the web UI
-- [budget] L1-P: g=1
SELECT f.path, rank
FROM files_fts, files f
WHERE files_fts MATCH 'xterm Terminal ChatPage'
  AND files_fts.rowid = f.id
  AND f.ext IN ('.ts', '.tsx')
  AND f.path NOT LIKE '%test%'
ORDER BY rank LIMIT 15;

-- [budget] L1-E: g=2 — extract ChatPage.tsx full component body
SELECT block_content_full FROM v_enriched
WHERE file_path = 'web/src/pages/ChatPage.tsx'
  AND block_content LIKE '%function ChatPage%'
  AND depth_level = 0
ORDER BY start_offset LIMIT 1;
-- ✓ result: xterm.js Terminal with WebSocket /api/pty + resize handler + clipboard
```

Layer 2 — API endpoint:

```sql
-- [intent] find the /api/pty WebSocket endpoint in web_server.py
-- [budget] L2-P: g=3
SELECT file_path, depth_level, substr(block_content, 1, 80) AS preview
FROM v_enriched
WHERE block_content LIKE '%api/pty%' AND depth_level = 0;

-- [budget] L2-E: g=4 — extract pty_ws() full handler body
SELECT block_content_full FROM v_enriched
WHERE file_path = 'hermes_cli/web_server.py'
  AND block_content LIKE '%async def pty_ws%'
  AND depth_level = 0
ORDER BY start_offset LIMIT 1;
-- ✓ result: pty_ws() — auth check → accept → bridge.spawn → reader/writer loops
```

Layer 3 — backend domain:

```sql
-- [intent] find PtyBridge.spawn in pty_bridge.py
-- [budget] L3-P: g=5
SELECT file_path, depth_level, length(block_content) AS bytes
FROM v_enriched
WHERE block_content LIKE '%class PtyBridge%' AND depth_level <= 1;

-- [budget] L3-E: g=6 — extract spawn() full method body
SELECT block_content_full FROM v_enriched
WHERE file_path = 'hermes_cli/pty_bridge.py'
  AND block_content LIKE '%def spawn%'
  AND depth_level = 1
ORDER BY start_offset LIMIT 1;
-- ✓ result: PtyProcess.spawn() — TERM backfill → dimensions → return PtyBridge (1850 bytes, 1 query)
```

Layer 4 — sidecar transport:

```sql
-- [intent] find tui_gateway WebSocket transport
-- [budget] L4-P: g=7
SELECT f.path, rank
FROM files_fts, files f
WHERE files_fts MATCH 'handle_ws tui_gateway'
  AND files_fts.rowid = f.id
  AND f.path NOT LIKE '%test%'
ORDER BY rank LIMIT 15;

-- [budget] L4-E: g=8 — extract WSTransport full implementation
SELECT block_content_full FROM v_enriched
WHERE file_path = 'tui_gateway/ws.py' AND depth_level = 1
  AND block_content LIKE '%class WSTransport%'
ORDER BY start_offset LIMIT 1;
-- ✓ result: WSTransport — dispatch() → same handlers as Ink stdio
```

## Depth by Language

Indent-based (Python, Ruby, YAML):
- `depth=0` — file-level envelope
- `depth=1` — function/class **signature only** (multi-line params included)
- `depth=2` — function **body**

Brace-based (JS, TS, Go, Rust, Java, C++, C#):
- `depth=0` — file-level envelope
- `depth=1` — complete function/method **body** (sig + body)
- `depth=2+` — nested blocks inside

Python body extraction: always `depth=2`. depth=1 is signature only.

## Mandatory Pre-flight

```bash
SQL-ManyThing-query-log import
sqlite3 :trace "
WITH intent(term) AS (
  VALUES ('<kw1>'), ('<synonym>'), ('<likely_file>')
)
SELECT id, project, tag, note, substr(sql_text, 1, 180) AS sql_preview
FROM query_trace WHERE project='<project>'
  AND (tag IS NOT NULL OR EXISTS (
    SELECT 1 FROM intent WHERE lower(sql_text) LIKE '%' || lower(term) || '%'
  ))
ORDER BY tag IS NULL, id DESC LIMIT 12;"
```

## References

| File | Content |
|---|---|
| `references/dashboard-tui-worked-example.md` | Full 4-layer Abstraction Frame execution trace with annotated SQL |
| `references/query/deps-chain-tracing.md` | Correct deps chain queries (upstream + downstream) with bug alert |

## Project Discovery

If no alias exists: `cat ~/.hermes/manything/aliases.sh` → locate root → check `.srcidx/source.db` → register `MANYTHING_{project}="{root}"` → pre-flight.

## Common Violations

1. **Skipping the frame.** Write the frame before SQL.
2. **No budget annotation.** Every query needs `[budget] L<N>-P/E: g=<N>`.
3. **Using `block_content` for EXTRACT when `block_content_full` is available.** `block_content_full` gives the full function/method body. `block_content` is for PROBE previews only.
4. **Blind `substr(content, N, M)`.** Only offsets from v_enriched columns (`start_offset`, `scope_end_offset`).
5. **`path LIKE` for function names.** Symbols are in `block_content`.
6. **depth=1 for Python bodies.** Use depth=2 for methods; use depth=0 for top-level functions (body in child depth=1 segments via `block_content_full`).
7. **Skip PROBE.** Never go straight to EXTRACT with a guess.
8. **read_file after EXTRACT returned content.** block_content is the answer.
9. **Wrapping SQL in execute_code/Python.** `sqlite3` CLI is the transport.
10. **Stitching depth segments manually.** `block_content_full` already spans multiple depth levels — no need for `substr(f.content, start, end-start)` chaining.
