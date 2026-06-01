---
name: sql-manything
description: Use when a project has a SQL-ManyThing SQLite source index. Query code structure with A* search over FTS5, symbol enrichment, depth segments, file dependencies, graph edges, v_enriched VIEW, and bounded source extraction before falling back to slower tools.
version: 1.2.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [code-search, sqlite, fts5, ast, a-star, source-index]
    related_skills: []
---

# SQL-ManyThing

## Overview

SQL-ManyThing indexes a source tree into a SQLite DB. Query with A* discipline: FTS5 probe → `v_enriched` block extract → stop at evidence. Build-time details: `AGENTS.md`, `scripts/`, `references/`. Design philosophy: `README.md`.

## When to Use

- A project has `.srcidx/source.db`.
- The user asks for code search, tracing, implementation lookup, or architecture inspection.
- Minimize token cost — no whole-file reads.

Do not use when: no index exists, task is non-code, or index is stale.

## A* Search Model

| A* term | Meaning |
|---|---|
| State space | `files` + `v_enriched` + `enrich_file_refs` + `enrich_file_deps` |
| Goal state | bounded `block_content` that directly answers the question |
| g(n) | cost paid: SQL queries, tool calls, tokens |
| h(n) | remaining-cost estimate from FTS5 rank, trace reuse, depth precision |
| Operator | one SQL query, one v_enriched extract |
| Goal test | exact evidence obtained; stop

## Primary Query Chain

```
-- A*: g=1 (FTS5 probe) → h=rank → extract
SELECT f.path, f.ext, rank               -- 1. FTS5 finds candidate
FROM files_fts JOIN files f ON f.rowid = files_fts.rowid
WHERE files_fts MATCH '<keyword>'
ORDER BY rank LIMIT 5;

-- A*: g=2 (v_enriched) → h=0 (exact block) → goal
SELECT file_path, depth_level, block_content  -- 2. v_enriched extracts block
FROM v_enriched
WHERE block_content LIKE '%<keyword>%'
ORDER BY depth_level, start_offset;

-- A*: g=2 (who imports?) → h=0 (raw strings cover all langs)
SELECT f.path, r.target_raw, r.line_num      -- 3. enrich_file_refs for imports
FROM enrich_file_refs r JOIN files f ON f.id = r.file_id
WHERE r.target_raw LIKE '%<ClassName>%';
```

Never fall back to `instr(content,...)` + `substr(content,offset,len)` when `v_enriched.block_content` exists.

## Mandatory Pre-flight

Before the first query against a project in a session:

```bash
SQL-ManyThing-query-log import
sqlite3 :trace "
WITH intent(term) AS (
  VALUES
    ('<intent-keyword-1>'),
    ('<intent-keyword-2>'),
    ('<domain-synonym-1>'),
    ('<likely-sql-anchor-1>')
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

Expand intent with world knowledge — e.g. "implementation overview" → `files`, `ext`, `path`, `v_enriched`, `file_refs`, `src`, `layout`.

Tag useful traces:

```bash
sqlite3 :trace "
INSERT INTO query_notes (log_id, note, tag, created_at)
VALUES (<id>, '<when to reuse>', 'useful_pattern', strftime('%s','now'));
"
```

Use `/manything/<project>/source.db` (virtual path, wrapper-logs queries). Verify: `sqlite3 /manything/<project>/source.db "SELECT COUNT(*) FROM files"`. `query_trace` lives in `:trace`, not in project DBs.

Rules:
- Import before querying `:trace`.
- Reuse tagged traces when intent overlaps.
- Fall back to FTS5 only when no useful trace exists.
- Use virtual paths for query-time SQL; `.srcidx/...` for setup/debug only.
- Find aliases in `~/.hermes/manything/aliases.sh` — never recursive grep.
- At the end of a query session, run `SQL-ManyThing-query-log import` once more if you need the just-run virtual-path queries to appear in `:trace` immediately.

**query_trace table absent**: Phase 3 query logging may not be set up. This diagnosis is valid only when the `:trace` command itself fails with `no such table: query_trace`:

```bash
sqlite3 :trace ".tables"
```

When this happens:
  1. Treat it as "no useful trace exists" — skip straight to FTS5 or symbol probe.
  2. Do not conclude the project index is broken. Phase 1 (FTS5) and Phase 2 (enrichment) are independent of Phase 3.
  3. Proceed normally without repeating the trace query.

Do **not** infer Phase 3 failure from `.tables` on `/path/to/.srcidx/source.db`; project databases are not supposed to contain `query_trace`.

## Project Discovery

If the user names a project but no alias exists, do not conclude the project is missing. Discover and register it.

Recommended sequence:

1. Inspect SQL-ManyThing aliases.
2. Locate the project root using configured mount points or common repository directories.
3. Confirm the root contains source files.
4. Check for `.srcidx/source.db`.
5. If no index exists, ask before building unless the user already authorized indexing.
6. Register the alias.
7. Run the mandatory pre-flight.

Registration shape:

```bash
MANYTHING_<project>="<absolute_project_root>"
```

Verification shape:

```bash
sqlite3 /manything/<project>/source.db "SELECT COUNT(*) FROM files"
```

## Operator 1: FTS5 Probe

FTS5 is the broad entry point — use it to discover candidate files.

```sql
SELECT f.path, f.ext, rank
FROM files_fts
JOIN files f ON f.rowid = files_fts.rowid
WHERE files_fts MATCH '<keyword>'
ORDER BY rank
LIMIT 20;
```

Narrow with AND, fallback with OR:

```sql
SELECT f.path, f.ext, rank
FROM files_fts JOIN files f ON f.rowid = files_fts.rowid
WHERE files_fts MATCH '<kw1> <kw2>'
ORDER BY rank LIMIT 20;
```

Extension-filtered:

```sql
SELECT f.path, rank
FROM files_fts JOIN files f ON f.rowid = files_fts.rowid
WHERE files_fts MATCH '<keyword>'
  AND f.ext IN ('.py', '.ts', '.tsx')
ORDER BY rank LIMIT 20;
```

Rank heuristic:

| rank | meaning | next step |
|---|---|---|
| strongly negative | likely target | extract via v_enriched (Operator 2) |
| moderately negative | plausible | add keywords or filter extension/path |
| weak | noisy | change query terms or inspect coverage |
| empty | no term match | try OR, synonym, or report absence |

## Stay In SQL

SQL-ManyThing is a **closed-loop query system**. Once you have established that the index covers a project (pre-flight confirms `files` count > 0, `v_enriched` has blocks), every subsequent question about that project must start with SQL. Do not switch to Hermes's generic code-search tools (code_search, code_extract, search_files, read_file) for needs the index already satisfies. FTS5 finds files by keyword, v_enriched extracts block content, enrich_file_refs traces imports. The only valid reason to leave SQL is evidence the index does not have (untracked files, stale index, cross-repo references, binary blobs).

When you catch yourself reaching for code_search / code_extract / grep after a SQL query, stop and ask: "does the SQL index have this data?" If yes, the answer is FTS5 + v_enriched. If no, then — and only then — fall back.

## Operator 2: v_enriched Block Extraction

`v_enriched` is the default universal Phase 2 interface. Every row = one depth segment with pre-extracted `block_content` — no need for `instr` anchor hunting or `substr` offset guessing. FTS5 narrows the file, `v_enriched` gives the exact block.

**Find blocks by keyword (replaces old anchor+substr):**

```sql
SELECT file_path, depth_level, start_offset, end_offset,
       block_content
FROM v_enriched
WHERE block_content LIKE '%<keyword>%'
  AND ext = '.tsx'
LIMIT 20;
```

**Browse file structure by depth (depth=0 = file-level, depth=1 = top-level blocks):**

```sql
SELECT depth_level, start_offset, end_offset,
       substr(block_content, 1, 120) AS preview
FROM v_enriched
WHERE file_path = '<target_path>'
ORDER BY start_offset;
```

**Zoom into a function/method body via FTS5 → v_enriched chain:**

```sql
-- Step 1: FTS5 finds the file
SELECT f.path FROM files_fts JOIN files f ON f.rowid = files_fts.rowid
WHERE files_fts MATCH 'function AppLayout' AND f.path LIKE 'ui-tui/%';

-- Step 2: v_enriched extracts the block at the right depth
SELECT depth_level, block_content
FROM v_enriched
WHERE file_path = 'ui-tui/src/components/appLayout.tsx'
  AND block_content LIKE '%function AppLayout%';
```

**Check coverage:**

```sql
SELECT COUNT(*) AS total_rows,
       SUM(CASE WHEN block_content = '' THEN 1 ELSE 0 END) AS empty_blocks,
       SUM(CASE WHEN refs_to IS NOT NULL THEN 1 ELSE 0 END) AS has_refs_to,
       SUM(CASE WHEN refs_from IS NOT NULL THEN 1 ELSE 0 END) AS has_refs_from
FROM v_enriched;
```

v_enriched is a VIEW computed from `files` + `enrich_depth_segments` + `enrich_file_refs`. LEFT JOIN means rows exist even without refs. Run `enrich_depth_segments.py` + `enrich_file_refs.py` + `create_enriched_view.py` to populate.

**Key rule**: v_enriched gives `block_content` for free — do NOT fall back to `instr(content, ...)` + `substr(content, offset, length)` when v_enriched is available. The VIEW already has exact boundaries. Manual anchor hunting is only acceptable when v_enriched is not built.

**block_content truncation escape hatch (very large blocks)**: v_enriched's `block_content` may be truncated when function bodies exceed its column width. Detect this: if `length(block_content)` is suspiciously short for the (end_offset - start_offset) range, or if a function clearly extends beyond what `block_content` returned, retrieve the full body from `files.content` using v_enriched's exact offsets — never instr-based guessing:

```sql
SELECT substr(f.content, ve.start_offset, ve.end_offset - ve.start_offset) AS full_body
FROM v_enriched ve
JOIN files f ON f.id = ve.file_id
WHERE ve.file_path = '<target_path>'
  AND ve.depth_level = 1
  AND ve.block_content LIKE '%<anchor_keyword>%';
```

This is NOT a violation of the anchor-hunting rule. The difference: v_enriched provides verified `start_offset`/`end_offset` from the depth-segment indexing pass; instr requires scanning content for a text anchor at query-time. Offset-based extraction from v_enriched boundaries is the correct A* g=1 escape hatch for oversized blocks.

**Zoom out for broader context (don't guess offsets):** When a single block is too narrow, expand by lowering `depth_level` — v_enriched already knows the nesting hierarchy. Never fall back to blind `substr(content, <magic_number>, N)`:

```sql
-- Step 1: browse the file's block map (depth=0 = file-level envelope)
SELECT depth_level, start_offset, end_offset,
       substr(block_content, 1, 120) AS preview
FROM v_enriched
WHERE file_path = '<path>'
ORDER BY start_offset;

-- Step 2: get the enclosing scope (e.g. class body around a method)
SELECT block_content FROM v_enriched
WHERE file_path = '<path>'
  AND depth_level = <target_depth - 1>
  AND start_offset <= <target_start_offset>
  AND end_offset >= <target_end_offset>;

-- Step 3 (rare): if you genuinely need raw bytes between blocks,
-- use v_enriched offsets — never guess:
SELECT substr(f.content, ve.start_offset, ve.end_offset - ve.start_offset)
FROM v_enriched ve JOIN files f ON f.id = ve.file_id
WHERE ve.file_path = '<path>'
  AND ve.depth_level = <depth>
  AND ve.start_offset = <known_offset>;
```

Key principle: the file is fully covered by depth segments — every byte belongs to some block. If `block_content` feels too small, the fix is lowering `depth_level`, not abandoning v_enriched for manual offset guessing. Manual `substr(content, 36637, 4000)` is an anti-pattern: the number 36637 appears nowhere in the query plan and was arrived at by guesswork.

## Operator 3: Import & Dependency Probe

Use for "who imports X" or "what does X depend on" questions.

**Raw imports (cross-language, no resolution needed):**

```sql
-- Find all files importing any variant of a class name
SELECT f.path, r.target_raw, r.line_num
FROM enrich_file_refs r JOIN files f ON f.id = r.file_id
WHERE r.target_raw LIKE '%<ClassName>%'
ORDER BY f.path, r.line_num;
```

This works for all languages — Java `import org.neo4j.graphdb.Node`, Python `from foo.bar import Baz`, JS `import { X } from './module'`. Resolution to `target_file_id` is a bonus for languages with path-matching resolvers (Python, JS/TS, Go). Java and other languages with package→filesystem gaps fall back to fuzzy `target_raw` matching — by design.

**Transitive dependency tree (upstream + downstream):**

```sql
-- Upstream: what files does this file import, transitively?
SELECT f.path, d.depth
FROM enrich_file_deps d JOIN files f ON f.id = d.dep_file_id
WHERE d.file_id = (SELECT id FROM files WHERE path = '<target_path>')
  AND d.direction = 'upstream'
ORDER BY d.depth, f.path;

-- Downstream: what files import this file, transitively?
SELECT f.path, d.depth
FROM enrich_file_deps d JOIN files f ON f.id = d.file_id
WHERE d.dep_file_id = (SELECT id FROM files WHERE path = '<target_path>')
  AND d.direction = 'downstream'
ORDER BY d.depth, f.path;
```

Coverage: deps only exist when `enrich_file_refs` has resolved refs. If empty, run `enrich_file_refs.py` then `flatten_file_deps.py`.

## Optional Enrichment: Symbols & Graphs

Tool-specific enrichment (cymbal symbols, graphify edges, UHT reflection, Java modules) coexists with universal Phase 2. These tables are optional and project-specific — query them when present, fall back to FTS5 + v_enriched when absent.

Symbol probe (cymbal, `file_enrich.symbols`): `references/phase2/enrich-cymbal.md`

Graph probe (graphify, `enrich_graphify_*`): `references/phase2/enrich-graphify.md`

UE UHT: `scripts/phase2/uht_enrich.py`

Java modules: `scripts/phase2/enrich_java_build.py`

## Query-Time References

| Pattern | Reference |
|---|---|
| JS/TS library exploration | `references/query/library-analysis-js-ts.md` |
| UE GAS AttributeSet BP init diagnosis | `references/query/ue-gas-attribute-analysis.md` |

## Build-Time References

| Topic | Reference |
|---|---|---|
| Phase 1 base FTS5 index | `scripts/phase1/manything_build_db.py` |
| Phase 1 setup reference | `references/phase1/phase1-setup.md` |
| Phase 1 extension rebuild | `references/phase1/phase1-rebuild-add-tsx.md` |
| Phase 1 gitignore enumeration | `references/phase1/gitignore-enumeration.md` |
| Universal Phase 2: depth/indent segments | `scripts/phase2/enrich_depth_segments.py` |
| Universal Phase 2: file-level import refs | `scripts/phase2/enrich_file_refs.py` |
| Universal Phase 2: transitive dep flattening | `scripts/phase2/flatten_file_deps.py` |
| Universal Phase 2: v_enriched wide VIEW | `scripts/phase2/create_enriched_view.py` |
| Universal Phase 2: Windows BAT template | `scripts/phase2/run_phase2_universal_windows.bat` |
| Phase 2 performance patterns | `references/phase2/perf-optimization.md` |
| Symbol enrichment (cymbal) | `references/phase2/enrich-cymbal.md` |
| Graph enrichment (graphify) | `references/phase2/enrich-graphify.md` |
| Java build enrichment | `references/phase2/enrich-java-build.md` |
| UE UHT enrichment | `scripts/phase2/uht_enrich.py` |
| Coverage checking | `references/phase2/enrich-covercheck-workflow.md` |
| Debugging empty symbol output | `references/phase2/debug-cymbal-outline-empty.md` |
| Unreal UHT generated files | `references/phase2/ue-uht-generated-files.md` |
| Query log design | `references/phase3/phase3-design-rationale.md` |
| Trace pre-flight debugging | `references/phase3/trace-preflight-debugging.md` |
| Query log importer parsing | `references/phase3/importer-parsing.md` |
| WSL-Windows Phase 1/2/3 smoke | `references/platforms/wsl-windows-phase123-smoke.md` |
| Unreal installed-build indexing | `references/unreal/installed-build-indexing.md` |
| Unreal indexing profiles | `references/unreal/unreal-installed-indexing-profiles.md` |
| UE 5.8 full run | `references/unreal/ue58-full-phase123-run.md` |
| Phase 2 overload test (UE) | `references/unreal/phase2-overload-test.md` |
| Unreal UHT DB verification | `scripts/verify/verify_ue_uht_sql.py` |
| Third-party licensing audit | `references/third-party-attribution.md` |
| Open-source attribution notices | `THIRD_PARTY_NOTICES.md` |
| Agent query-loop lessons | `references/agent-query-loop-lessons.md` |
| Reference index | `references/INDEX.md` |
| Design rationale | `references/design/sql-is-many-things.md` |
| Contributing guide | `CONTRIBUTING.md` |
| Changelog | `CHANGELOG.md` |
| Security / privacy | `SECURITY.md` |
| DB maintenance | `references/db-maintenance.md` |
| Public examples | `references/public-examples.md` |

## Core Schema

| Table | Purpose |
|---|---|
| `files` | one row per indexed file: path, ext, size, mtime, content |
| `files_fts` | FTS5 trigram index over path and content |
| `v_enriched` | **Primary query surface.** VIEW: files + depth_segments → block_content + refs_to + refs_from. Columns: file_id, file_path, ext, depth_level, start_offset, end_offset, block_content, refs_to, refs_from |
| `enrich_file_refs` | cross-file imports: file_id, target_raw, target_file_id, line_num |
| `enrich_file_deps` | flattened transitive deps: (file_id, dep_file_id, direction, depth) |
| `enrich_depth_segments` | brace/indent offset ranges: (file_id, depth_level, start_offset, end_offset) |
| `file_enrich` | per-file enrichment cache, usually cymbal symbols as JSON |
| `enrich_graphify_nodes` / `_edges` | optional: graphify AST/document nodes and edges |

Constraints: `files.ext` includes leading dot (`.py`). Enrichment coverage bounded by Phase 1 extensions. VIEW LEFT JOINs — rows exist without refs.

## Query-Time Decision Tree

1. Run pre-flight.
2. Reuse a tagged trace if available and relevant.
3. FTS5 probe to discover candidate files (Operator 1).
4. v_enriched to extract block content — `block_content LIKE '%<keyword>%'` or `file_path = '<target>'` ORDER BY `start_offset` (Operator 2).
5. If the question is about imports/dependencies, use `enrich_file_refs` + `enrich_file_deps` (Operator 3).
6. If optional enrichment exists (symbols, graph, UHT), probe it as a complement — fall back to FTS5 + v_enriched when absent.
7. Stop after the extracted evidence answers the question. If a follow-up question arises, **stay in SQL** — convert it to another FTS5 + v_enriched round. Only leave SQL when the index provably lacks the needed data (untracked file types, stale index, cross-repo references).
8. If evidence is absent, state what was queried and what coverage was checked.
9. Never fall back from v_enriched to `instr`+`substr` guessing when the VIEW is built.

## Implementation Overview Recipe

For a broad implementation overview, do not enumerate every file. Use a bounded sequence:

```bash
SQL-ManyThing-query-log import
sqlite3 :trace "
WITH intent(term) AS (
  VALUES ('files'), ('ext'), ('path'),
         ('v_enriched'), ('depth_segments'), ('file_refs'),
         ('file_enrich'), ('graph'), ('README'), ('src')
)
SELECT id, project, tag, note, substr(sql_text, 1, 180) AS sql_preview
FROM query_trace
WHERE project='<project>'
  AND (tag IS NOT NULL OR EXISTS (
    SELECT 1 FROM intent WHERE lower(sql_text) LIKE '%' || lower(term) || '%'
  ))
ORDER BY tag IS NULL, id DESC
LIMIT 12;"
sqlite3 /manything/<project>/source.db "SELECT COUNT(*) FROM files; SELECT ext, COUNT(*) FROM files GROUP BY ext ORDER BY COUNT(*) DESC;"
sqlite3 /manything/<project>/source.db "SELECT substr(path,1,instr(path||'/', '/')-1) AS top, COUNT(*) FROM files GROUP BY top ORDER BY COUNT(*) DESC LIMIT 20;"
sqlite3 /manything/<project>/source.db "SELECT COUNT(*) AS segments, MIN(depth_level), MAX(depth_level) FROM enrich_depth_segments;"
sqlite3 /manything/<project>/source.db "SELECT COUNT(*) AS total, SUM(CASE WHEN block_content='' THEN 1 ELSE 0 END) AS empty, SUM(CASE WHEN refs_to IS NOT NULL THEN 1 ELSE 0 END) AS has_refs_to FROM v_enriched;"
sqlite3 /manything/<project>/source.db "SELECT direction, COUNT(*) FROM enrich_file_deps GROUP BY direction;"
sqlite3 /manything/<project>/source.db "SELECT COUNT(*) FROM file_enrich WHERE symbols IS NOT NULL AND symbols != '[]';"
sqlite3 /manything/<project>/source.db "SELECT COUNT(*) FROM enrich_graphify_nodes; SELECT DISTINCT relation FROM enrich_graphify_edges LIMIT 20;"
```

Then choose at most 3-5 representative anchors and extract via v_enriched. Prefer manifests, README-style docs, and main entrypoints found via FTS5.


Anti-patterns:

- `grep -r` or recursive config search.
- `SELECT path ... ORDER BY path` without `LIMIT` or grouping.
- Direct `.srcidx/source.db` reads after virtual path is known.
- Whole-file reads or `substr(content, 1, length(content))`.
- Falling back from v_enriched to manual `instr`+`substr` anchor hunting.
- Switching from SQL to code_search/code_extract/read_file after SQL has answered the first question. Follow-up questions stay in SQL.

## Common Pitfalls

1. Skipping pre-flight. Import pending logs and inspect tagged traces before new exploration.
2. Querying `:trace` without import. Pending logs stay invisible.
3. Reading whole files. Bounded extraction is mandatory.
4. Forgetting the dot in `files.ext`. Use `.py`, not `py`.
5. Falling back from `v_enriched.block_content` to `instr`+`substr` anchor hunting. The VIEW has exact boundaries — use it.
6. Assuming `enrich_file_refs.target_file_id` must be non-NULL. Query `target_raw LIKE '%ClassName%'` for cross-language import discovery.
7. Recursively grepping Hermes home to find project aliases. Use `~/.hermes/manything/aliases.sh`.
8. Listing every source path for an overview. Group by top-level path first, drill into a subset.
9. Switching from SQL to code_search/code_extract mid-session. The index has FTS5 + v_enriched for everything provenance the project needs. Reaching for generic search tools is a signal you forgot SQL covers it — rephrase the question as a FTS5 MATCH and a v_enriched block look-up.
10. Writing `.bat` files from WSL with LF line endings or non-ASCII characters (em dashes, Unicode). Windows `cmd.exe` requires CRLF + pure ASCII. Always run `unix2dos` on `.bat` files authored in WSL. Avoid `%s` in inline Python strings inside `.bat` — `cmd.exe` interprets `%s` as variable expansion; use `%%s` or keep verification in separate sqlite3 calls.
11. Falling back to blind `substr(content, <magic_number>, <magic_number>)` when v_enriched found the target but you want «more context». The file is fully depth-segmented — every byte belongs to some block. If a single block feels too narrow, query `depth_level - 1` for the enclosing scope, or browse adjacent blocks by `start_offset`. Never fabricate a byte offset from thin air; always derive it from a v_enriched `start_offset`/`end_offset` column.

## Verification Checklist

Before answering:

- [ ] Pre-flight ran or was explicitly impossible.
- [ ] Query trace reuse was considered.
- [ ] FTS5 probe ran with appropriate keyword expansion.
- [ ] v_enriched used for block extraction — not `instr`+`substr` anchoring.
- [ ] No whole-file `substr` was used.
- [ ] Coverage checked: depth_segments, v_enriched, file_deps, optional enrichment.
- [ ] Missing results include the query and coverage checked.
- [ ] Final answer separates evidence from inference.

Before editing this skill:

- [ ] Keep `SKILL.md` generic and English-only.
- [ ] Move build-time or project-specific detail into `references/`.
- [ ] Preserve mandatory pre-flight, bounded extraction, and coverage-check rules.
- [ ] Validate frontmatter and file size.
