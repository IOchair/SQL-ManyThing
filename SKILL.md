---
name: sql-manything
description: Use when a project has a SQL-ManyThing SQLite source index. Query code structure with A* search over FTS5, symbol enrichment, graph edges, and bounded source extraction before falling back to slower tools.
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [code-search, sqlite, fts5, ast, a-star, source-index]
    related_skills: []
---

# SQL-ManyThing

## Overview

SQL-ManyThing turns a source tree into a local SQLite search space. The agent queries that space with A* discipline: keep the path cost low, improve the remaining-cost estimate, and stop when a bounded source slice proves the answer.

This skill is for query-time behavior. Build-time indexing and enrichment details live in `references/` and `scripts/`. Keep the main skill generic, open-source friendly, and project-agnostic.

For design philosophy, origin narrative, comparison table (grep/LSP/Cloud RAG/SQL-MT), RAG inversion rationale, and the 3-step meta-strategy to reproduce this project, see `README.md` (English) or `README.zh-CN.md` (Chinese) in the skill root.

README narrative flow: 30-Second Pitch → Why Everything Else Breaks at Scale → Core Insight (A*) → Shock Test (UE 5.8) → Meta-Strategy → Query Power → Architecture → Design Principles → CLI Philosophy.

## When to Use

Use this skill when:

- A project has `.srcidx/source.db` built by SQL-ManyThing.
- The user asks for code search, code tracing, implementation lookup, symbol discovery, or architecture inspection.
- A question can be answered by SQLite FTS5, symbol enrichment, graph enrichment, or bounded source slices.
- You need to minimize token cost and avoid reading whole files.

Do not use this skill when:

- No SQL-ManyThing database exists and the task is too small to justify building one.
- The user asks for a non-code task.
- The indexed content is known stale and rebuilding is not allowed.
- A minified single-line bundle makes FTS5 ranking meaningless; use the minified-bundle fallback strategy instead.

## A* Search Model

Map code search onto A*:

| A* term | SQL-ManyThing meaning |
|---|---|
| State space | indexed files, rows, symbols, graph nodes, graph edges |
| Start state | user question and known project context |
| Goal state | bounded source extract or query result that directly answers the question |
| g(n) | cost already paid: SQL queries, source slices, tool calls, tokens |
| h(n) | optimistic remaining cost estimated from rank, symbol precision, graph links, and trace reuse |
| f(n) | g(n) + h(n), minimized at every step |
| Operator | one SQL query, one bounded extract, one enrichment lookup |
| Pruning | empty MATCH, weak rank, missing table, poor coverage, irrelevant path |
| Goal test | exact bounded evidence obtained; no need to read more |

Search rule:

1. Improve h(n) before spending g(n).
2. Prefer high-signal SQL probes over wide source reads.
3. Extract source only after a probe narrows path and offset.
4. Treat "not found" as a valid result after checking index coverage and fallback query forms.
5. Do not invent code paths when the database returns no evidence.

## Mandatory Pre-flight

Before the first query against a project in a session, flush pending logs, then stay in SQL mode for trace search and tagging:

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
  AND (
    tag IS NOT NULL
    OR EXISTS (
      SELECT 1 FROM intent
      WHERE lower(sql_text) LIKE '%' || lower(term) || '%'
    )
  )
ORDER BY tag IS NULL, id DESC
LIMIT 12;"
```

Use world knowledge to expand the intent into multiple SQL-facing descriptions before searching. For example, an "implementation overview" intent may expand to `files`, `ext`, `path`, `symbols`, `file_enrich`, `graph`, `README`, `package`, `src`, `layout`, `prepare`, `measure`, `benchmark`, or project-specific entrypoint names.

If a row is useful, tag it immediately through SQL, not a separate CLI mode:

```bash
sqlite3 :trace "
INSERT INTO query_notes (log_id, note, tag, created_at)
VALUES (<id>, '<when to reuse this query>', 'useful_pattern', strftime('%s','now'));
"
```

`/manything/<project>/source.db` is a wrapper-only virtual path, not a real filesystem path. Do not check it with `ls` or `test -f`; those will normally fail. Verify it by opening it through the sqlite wrapper:

```bash
sqlite3 /manything/<project>/source.db "SELECT COUNT(*) FROM files"
```

`query_trace` also lives only in the global `:trace` database. It is not a table inside each project's `.srcidx/source.db`, and its absence from project `.tables` is expected.

Rules:

- Run import and trace together. Do not query `:trace` without importing pending logs first.
- Use SQL fuzzy pre-flight results as the entry point. Check both tagged rows and SQL-matched untagged rows before new exploration.
- Reuse tagged traces when their intent overlaps the current question.
- If a recent untagged trace proves useful, tag it immediately with an `INSERT INTO query_notes ...` statement in `sqlite3 :trace`; do not switch to a separate CLI command for tagging.
- Only when no useful tagged or SQL-matched trace exists, start with a broad FTS5 probe.
- If `/manything/<project>/source.db` virtual paths are configured, use them so the wrapper can log queries.
- Do not search `~/.hermes/` recursively to find aliases. Alias lookup is a single-file operation: inspect `~/.hermes/manything/aliases.sh`, or just try the known virtual path with sqlite.
- After you start using a virtual `/manything/<project>/source.db` path, keep using it for query-time SQL so Phase 3 can log the session. Direct `.srcidx/source.db` queries are for setup/debug only.
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

## Core Schema

Common tables:

| Table | Purpose |
|---|---|
| `files` | one row per indexed file: path, ext, size, mtime, content |
| `files_fts` | FTS5 trigram index over path and content |
| `file_enrich` | per-file enrichment cache, usually symbols as JSON |
| `enrich_graphify_nodes` | AST or document nodes |
| `enrich_graphify_edges` | graph edges such as calls, containment, references |

Important constraints:

- `files_fts` contains only indexed FTS columns. Join `files` for `ext`, `size`, or metadata filters.
- `files.ext` includes the leading dot, for example `.py`, `.ts`, `.tsx`.
- Enrichment coverage is bounded by Phase 1 indexed extensions.
- Enrichment tables can exist while holding partial or empty coverage. Check table counts and extension coverage before drawing conclusions.

## Operator 1: FTS5 Probe

Use FTS5 for broad-to-narrow discovery.

Broad probe:

```sql
SELECT path, rank
FROM files_fts
WHERE files_fts MATCH '<keyword>'
ORDER BY rank
LIMIT 20;
```

Narrow probe:

```sql
SELECT path, rank
FROM files_fts
WHERE files_fts MATCH '<kw1> <kw2>'
ORDER BY rank
LIMIT 20;
```

OR fallback after empty AND:

```sql
SELECT path, rank
FROM files_fts
WHERE files_fts MATCH '<kw1> OR <kw2>'
ORDER BY rank
LIMIT 20;
```

Extension-filtered probe:

```sql
SELECT f.path, rank
FROM files_fts
JOIN files f ON f.rowid = files_fts.rowid
WHERE files_fts MATCH '<keyword>'
  AND f.ext IN ('.py', '.ts', '.tsx')
ORDER BY rank
LIMIT 20;
```

Rank heuristic:

| rank | meaning | next step |
|---|---|---|
| strongly negative | likely target | probe offsets or extract bounded slice |
| moderately negative | plausible | add keywords or filter extension/path |
| weak | noisy | change query terms or inspect coverage |
| empty | no term match | try OR, synonym, path probe, or report absence with coverage note |

## Operator 2: Symbol Probe

Use symbol enrichment when the question names a function, class, method, type, command, or handler.

```sql
SELECT f.path,
       json_extract(s.value, '$.name') AS name,
       json_extract(s.value, '$.kind') AS kind,
       json_extract(s.value, '$.start_line') AS start_line,
       json_extract(s.value, '$.end_line') AS end_line
FROM file_enrich e
JOIN files f ON f.id = e.file_id,
     json_each(e.symbols) AS s
WHERE json_extract(s.value, '$.name') LIKE '%<symbol>%'
ORDER BY f.path, start_line
LIMIT 50;
```

If symbol results are empty:

1. Check whether `file_enrich` has rows.
2. Check whether the target extension was indexed.
3. Try FTS5 for the symbol text.
4. Do not assume the symbol does not exist until coverage is known.

## Operator 3: Graph Probe

Use graph enrichment when the question is about call flow, containment, dependencies, document structure, or cross-file relationships.

List graph coverage:

```sql
SELECT DISTINCT f.ext
FROM enrich_graphify_nodes n
JOIN files f ON f.id = n.file_id
ORDER BY f.ext;
```

**Pre-check edge relation types before interpreting results.** Run:

```sql
SELECT DISTINCT e.relation FROM enrich_graphify_edges e LIMIT 20;
```

Edge type determines what conclusions graph data supports:

| relation | meaning | use |
|---|---|---|
| `contains` | document hierarchy (markdown sections, JSON nesting) | structure exploration, not call flow |
| `calls` / `references` / `imports` | code-level relationships | dependency tracing, call graph analysis |
| `implements` / `extends` | type hierarchy | OOP structure analysis |

Do not use `contains` edges to answer call-flow questions. If only `contains` relations exist, the graph is a document outline, not a code call graph — fall back to symbol probe (Operator 2) or FTS5 (Operator 1) for code-level relationships.

Find nodes:

```sql
SELECT n.label, n.source_location, f.path
FROM enrich_graphify_nodes n
JOIN files f ON f.id = n.file_id
WHERE n.label LIKE '%<label>%'
ORDER BY f.path, n.source_location
LIMIT 50;
```

Inspect edges from a node:

```sql
SELECT n1.label AS source, e.relation, n2.label AS target
FROM enrich_graphify_edges e
JOIN enrich_graphify_nodes n1 ON n1.file_id = e.file_id AND n1.node_id = e.source_node_id
JOIN enrich_graphify_nodes n2 ON n2.file_id = e.file_id AND n2.node_id = e.target_node_id
WHERE n1.label LIKE '%<label>%'
ORDER BY e.relation, target
LIMIT 100;
```

## Operator 4: Bounded Source Extraction

Source extraction is the A* goal test, not a browsing habit.

Allowed pattern:

```sql
SELECT instr(content, '<anchor>') AS offset
FROM files
WHERE path = '<target_path>';
```

Then extract a bounded window:

```sql
SELECT substr(content, <start_offset>, <length>)
FROM files
WHERE path = '<target_path>';
```

Rules:

- Never use `substr(content, 1, length(content))` to read a whole file.
- For qualitative answers, keep each slice small, usually 500-2000 characters.
- For multi-layer tracing, define the layer first, probe each layer, then extract only the needed windows.
- Prefer symbol line spans or anchors over arbitrary file starts.
- Stop after the extracted evidence answers the question.

## Abstraction Frame

Before tracing a feature, define the layers and expected evidence.

Template:

```text
QUERY: <one-sentence user intent>
LAYERS:
  - <layer_name>: <role in the system>
    PROBE: <SQL probe, symbol lookup, graph lookup, or anchor search>
    EXTRACT: <bounded offsets and lengths only if probe succeeds>
```

Example layers for a full-stack feature:

- UI component: state, rendering, event handlers.
- API client: endpoint names, request payloads, response handling.
- Route handler: HTTP entry point and validation.
- Domain logic: core function or service behavior.
- Persistence layer: database query, file write, cache operation.

Constraints:

- Probe before extract for every layer.
- Do not extract child components or callees unless their behavior is directly in question.
- Keep total extracted text bounded. If the question requires too much text, split into sub-questions.
- If a layer cannot be found, report the missing evidence and the coverage checked.

## Query-Time References

| Pattern | Reference |
|---|---|
| JS/TS library exploration: entry point → module inventory → symbol enumeration → bounded extraction | `references/query/library-analysis-js-ts.md` |
| UE GAS AttributeSet BP init diagnosis: class specifiers, attribute types, replication, Blueprint Editor readiness | `references/query/ue-gas-attribute-analysis.md` |

## Build-Time References

Use references for indexing and enrichment details:

| Topic | Reference |
|---|---|
| Phase 1 base FTS5 index | `references/phase1/phase1-setup.md` |
| Phase 1 extension rebuild | `references/phase1/phase1-rebuild-add-tsx.md` |
| Phase 1 gitignore enumeration | `references/phase1/gitignore-enumeration.md` |
| Symbol enrichment | `references/phase2/enrich-cymbal.md` |
| Graph enrichment | `references/phase2/enrich-graphify.md` |
| Java build enrichment | `references/phase2/enrich-java-build.md` |
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
| Unreal UHT DB verification | `scripts/verify/verify_ue_uht_sql.py` |
| Third-party licensing audit | `references/third-party-attribution.md` |
| Open-source attribution notices | `THIRD_PARTY_NOTICES.md` |
| Agent query-loop dogfooding lessons | `references/agent-query-loop-lessons.md` |
| Reference index | `references/INDEX.md` |
| Design rationale | `references/design/sql-is-many-things.md` |
| Contributing guide | `CONTRIBUTING.md` |
| Changelog | `CHANGELOG.md` |
| Security / privacy | `SECURITY.md` |
| DB maintenance | `references/db-maintenance.md` |
| Public examples (UE5.8 + small project) | `references/public-examples.md` |

## Query-Time Decision Tree

1. Run pre-flight.
2. Reuse a tagged trace if available and relevant.
3. If the question names a symbol, try symbol probe.
4. If the question names behavior, error text, endpoint, command, or UI text, try FTS5.
5. If the question asks relationships, try graph probe after checking graph coverage.
6. If a likely path is found, use `instr` or symbol span to locate offsets.
7. Extract bounded evidence.
8. Answer only from evidence.
9. If evidence is absent, state what was queried and what coverage was checked.

## Implementation Overview Recipe

For a broad implementation overview, do not enumerate every file or recursively grep user config. Use a bounded sequence:

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
sqlite3 /manything/<project>/source.db "SELECT COUNT(*) FROM files; SELECT ext, COUNT(*) FROM files GROUP BY ext ORDER BY COUNT(*) DESC;"
sqlite3 /manything/<project>/source.db "SELECT substr(path,1,instr(path||'/', '/')-1) AS top, COUNT(*) FROM files GROUP BY top ORDER BY COUNT(*) DESC LIMIT 20;"
sqlite3 /manything/<project>/source.db "SELECT COUNT(*) FROM file_enrich WHERE symbols IS NOT NULL AND symbols != '[]';"
sqlite3 /manything/<project>/source.db "SELECT COUNT(*) FROM enrich_graphify_nodes; SELECT COUNT(*) FROM enrich_graphify_edges; SELECT DISTINCT relation FROM enrich_graphify_edges LIMIT 20;"
```

Then choose at most 3-5 representative anchors and extract bounded slices. Prefer manifests, README-style docs, and main library entrypoints found via FTS5 or symbol probes.

Anti-patterns for overview:

- `grep -r "manything" ~/.hermes/` or any recursive config search.
- `SELECT path FROM files WHERE path LIKE 'src/%' ORDER BY path` without `LIMIT` or grouping.
- Repeated `export PATH=...` in every shell command instead of relying on the installed sqlite wrapper.
- Direct `.srcidx/source.db` query-time reads after a virtual path is known.
- Whole-file reads or large unanchored `substr` blocks.

## Minified Bundle Fallback

FTS5 ranking is weak for single-line minified bundles because one record can contain the whole artifact.

Fallback strategy:

1. Use non-minified sources if available.
2. Anchor on stable strings such as endpoint names, action names, route paths, or user-visible labels.
3. Use a bounded regex or string window around each anchor.
4. Infer only local behavior from nearby code. Do not reconstruct the entire bundle.

## Common Pitfalls

1. Skipping pre-flight. Always import pending query logs and inspect tagged traces before new exploration.
2. Querying `:trace` without import. Pending logs stay invisible.
3. Reading whole files. Bounded extraction is mandatory.
4. Forgetting the dot in `files.ext`. Use `.py`, not `py`.
5. Assuming enrichment absence from one empty query. Check tables, row counts, and extension coverage.
6. Rebuilding Phase 1 and forgetting Phase 2. Rebuilds can drop or invalidate enrichment tables.
7. Letting Phase 1 extension choices hide later symbols. Downstream enrichment cannot cover extensions absent from `files`.
8. Passing the source index as a tool-specific database to an enrichment tool. Keep SQL-ManyThing schema separate from tool-private databases.
9. Running subagents without teaching them the virtual `/manything/<project>/source.db` path and pre-flight protocol.
10. Treating project-specific examples as generic rules. Keep public skill text project-agnostic.
11. Assuming build-time helper commands are installed. On a fresh WSL machine, create shims such as `~/.local/bin/SQL-ManyThing-query-log` and ensure `~/.local/bin` precedes `/usr/bin` so the sqlite wrapper can see `/manything/<project>/source.db` queries.
12. Assuming graphify is installed. The Phase 2 graph enrichment script should degrade gracefully when `~/graphify` is absent; verify node counts rather than treating import failure as acceptable.
13. Assuming graph edges represent code call flow. `contains` edges from markdown/document structure look similar to code edges in query results but answer different questions. Pre-check edge relation types before drawing conclusions (see Operator 3 pre-check).
14. Recursively grepping Hermes home to find project aliases. Use `~/.hermes/manything/aliases.sh` directly or test the virtual sqlite path. Recursive grep across `~/.hermes/` is slow, noisy, and outside the SQL-ManyThing query loop.
15. Listing every source path for an overview. Group by top-level or second-level path first, then drill into a small representative subset.

## Verification Checklist

Before answering:

- [ ] Pre-flight ran or was explicitly impossible.
- [ ] Query trace reuse was considered.
- [ ] FTS5, symbol, or graph coverage was checked as appropriate.
- [ ] Every source extract used explicit offset and length.
- [ ] No whole-file `substr` was used.
- [ ] Missing results include the query and coverage checked.
- [ ] Final answer separates evidence from inference.

Before editing this skill:

- [ ] Keep `SKILL.md` generic and English-only.
- [ ] Move build-time or project-specific detail into `references/`.
- [ ] Preserve mandatory pre-flight, bounded extraction, and coverage-check rules.
- [ ] Validate frontmatter and file size.
