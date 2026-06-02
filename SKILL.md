---
name: sql-manything
description: A* source-code search over SQL-ManyThing SQLite index. Four canonical SQL templates (DISCOVER→TRACE_DEPS→EXTRACT→EXTRACT_BLOCK) + Abstraction Frame with budget tracking. No substr guessing, no whole-file reads.
version: 5.4.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [code-search, sqlite, fts5, ast, a-star, source-index]
    related_skills: []
---

# SQL-ManyThing

Indexes a source tree into a SQLite DB. Query model: Abstraction Frame → DISCOVER → EXTRACT → EXTRACT_BLOCK, with optional TRACE_DEPS for candidate disambiguation.

**Reading order is execution order.** Start at §0, follow steps in sequence. Do not jump to SQL templates before writing a Frame.

## §0 When to Use

**Use when:**
- A project has `.srcidx/source.db` (if not, see §1.3 to create one). Query via `/manything/<project>/source.db`.
- The user asks for code search, tracing, implementation lookup, or architecture inspection.
- You need precise, offset-based extraction without whole-file reads.

**Do NOT use when:**
- No index exists for the project.
- You're looking at <100 files total — `code_search` / `code_extract` is faster.
- The target is logs, config, markdown, or non-code text — use `search_files` / `read_file`.
- You need a single function from a known file — `code_extract` is 1 call.

## §1 Pre-flight — Know Your DB Before You Query

Before ANY query, check what tables are available. Not every project is fully enriched.

### 1.1 Schema check

```bash
sqlite3 /manything/<project>/source.db "
SELECT name FROM sqlite_master
WHERE type='table' AND name IN ('files','files_fts','v_enriched','enrich_file_deps','enrich_file_refs','enrich_depth_segments')
ORDER BY name;"
```

| Tables present | Capabilities |
|---|---|
| `files` + `files_fts` only | FTS5 search only. No v_enriched — skip EXTRACT/EXTRACT_BLOCK. Use `files.content` or fall back to `read_file`. |
| + `v_enriched` | Full DISCOVER → EXTRACT → EXTRACT_BLOCK chain. |
| + `enrich_file_deps` | TRACE_DEPS available. |
| + `enrich_depth_segments` | `block_content_full` + `scope_end_offset` for complete body extraction. |
| + `enrich_file_refs` (no deps) | Raw #include/import strings — query refs table directly. |

### 1.2 File count

```bash
sqlite3 /manything/<project>/source.db "SELECT count(*) AS file_count FROM files;"
```

| File count | Strategy |
|---|---|
| <10K | Fast LIKE scans OK |
| 10K–50K | Prefer FTS5 for discovery; narrow LIKE with `file_path` |
| >50K | FTS5 only for discovery; NEVER run unfiltered `block_content LIKE '%X%'` without `file_path` |

### 1.3 Setup: Phase 1 → 2 → 3

A fully enriched project goes through three phases. After Phase 1 each phase is optional — stop when you have the tables you need (§1.1).

**Phase 1 — Create the index** (`references/phase1/phase1-setup.md`):
```bash
python3 scripts/phase1/manything_build_db.py /path/to/project
```
This creates `.srcidx/source.db` with `files` + `files_fts`. Enough for FTS5-only search.

**Phase 2 — Enrich with structure + dependencies** (`references/phase2/enrich-covercheck-workflow.md`):
```bash
# Universal workflow (all languages, always applicable):
python3 scripts/phase2/enrich_depth_segments.py /path/to/project --batch 500
python3 scripts/phase2/enrich_file_refs.py       /path/to/project --batch 500
python3 scripts/phase2/flatten_file_deps.py      /path/to/project
python3 scripts/phase2/create_enriched_view.py   /path/to/project
```
This adds `v_enriched`, `enrich_file_deps`, `enrich_file_refs`, `enrich_depth_segments` — the full DISCOVER→EXTRACT→EXTRACT_BLOCK chain. If re-running on a previously enriched DB, see `references/old-format-cleanup.md`.

Optional enrichments (not needed for most queries):
- `enrich_cymbal.py` — symbol definitions via cymbal CLI (Python/Go/JS only; needs `cymbal` binary)
- `enrich_graphify.py` — AST graph for Python + Markdown (does not cover TSX/JSX)
- `enrich_java_build.py` — Java-specific

On Windows, `scripts/phase2/run_phase2_universal_windows.bat` runs all 4 steps. On Linux/WSL/macOS, run the Python scripts directly as shown above.

**Phase 3 — Install the sqlite3 wrapper** (enables `/manything/` paths + `:trace`):
```bash
# Cross-platform (Windows/Linux/macOS):
python3 scripts/phase3/install.py

# Or bash-only (Linux/WSL/macOS):
./install.sh
```
This places a `sqlite3` wrapper in `~/.local/bin/` that intercepts `/manything/<project>/source.db` and `:trace`. On Windows, `install.py` also copies `sqlite3-real.exe` and creates a `.cmd` wrapper. Ensure `~/.local/bin` is before `/usr/bin` in PATH.

After Phase 3, register the project:
```bash
echo 'MANYTHING_<project>="/path/to/project"' >> ~/.hermes/manything/aliases.sh
```
Then proceed with §1.1 schema check.

See `references/phase3/phase3-design-rationale.md` for architecture details.

### 1.4 Trace — search past queries (`:trace`)

The sqlite3 wrapper logs every `/manything/` query to `~/.hermes/manything/query_log.db`. Use `:trace` as a virtual database name to search past queries — it resolves to the global query log automatically.

**Search by project + keyword:**
```bash
sqlite3 :trace "
SELECT id, sql_text, tag FROM query_trace
WHERE project = '<project>'
  AND sql_text LIKE '%<keyword>%'
ORDER BY id DESC LIMIT 10;"
```

**Tag a useful query pattern** (agent discovers a reusable SQL shape):
```sql
INSERT INTO query_notes(log_id, note, tag, created_at)
VALUES (<id>, 'brief description of the pattern', '<short_tag>', strftime('%s','now'));
```

Tagged queries accumulate over time — future agents can `SELECT * FROM query_trace WHERE tag IS NOT NULL` to discover proven patterns without repeating discovery work. This is how the system gets faster and deeper with use.

## §2 Quick Start — Minimal Path (4 queries)

Goal: find and extract `SubstrateToonBSDF` in UE 5.8.

**Step 0 — Pre-flight** (already done: ue58 has all tables, 89K files, >50K → FTS5 only).

**Step 1 — Write the Frame:**

```
═══ A* BUDGET FRAME  #1 ═══
QUERY: UE5.8 Substrate Toon BSDF — shader implementation entry point

LAYERS:
  shader:     SubstrateToonBSDF.ush — BSDF eval + integrate functions
    DISCOVER:      FTS5 MATCH 'SubstrateToonBSDF'
    EXTRACT:       v_enriched depth≤1 structure map
    EXTRACT_BLOCK: SubstrateEvaluateToon body → TERMINAL
```

**Step 2 — DISCOVER:**

```sql
-- [intent] find Substrate toon BSDF shader file
-- [budget] L1-P: g=1
SELECT f.path, rank FROM files_fts, files f
WHERE files_fts MATCH 'SubstrateToonBSDF'
  AND files_fts.rowid = f.id AND f.path NOT LIKE '%test%'
ORDER BY rank LIMIT 10;
-- → Shaders/Private/Substrate/SubstrateToonBSDF.ush (rank -9.2)
```

**Step 3 — EXTRACT (probe structure):**

```sql
-- [intent] structure map of SubstrateToonBSDF.ush
-- [budget] L1-P: g=2
SELECT depth_level, start_offset,
       length(block_content) AS bytes,
       length(block_content_full) AS full_bytes,
       substr(block_content, 1, 100) AS preview
FROM v_enriched
WHERE file_path = 'Shaders/Private/Substrate/SubstrateToonBSDF.ush'
  AND depth_level <= 1
ORDER BY depth_level, start_offset;
-- → depth=0: file envelope (includes, macros)
-- → depth=1: UnpackToonCustomData, SubstrateIntegrateToon, SubstrateEvaluateToon, ...
```

**Step 4 — EXTRACT_BLOCK (terminal):**

```sql
-- [intent] extract SubstrateEvaluateToon full body
-- [budget] L1-E: g=3
SELECT length(block_content_full) AS full_len FROM v_enriched
WHERE file_path = 'Shaders/Private/Substrate/SubstrateToonBSDF.ush'
  AND block_content LIKE '%SubstrateEvaluateToon%'
  AND depth_level = 1;
-- If full_len ≥ 200 → extract. If <200 → split-signature, query next same-depth segment.

SELECT block_content_full FROM v_enriched
WHERE file_path = 'Shaders/Private/Substrate/SubstrateToonBSDF.ush'
  AND depth_level = 1 AND start_offset = <from_EXTRACT>;
-- ✓ goal: block_content_full returned complete function body. Stop.
```

That's it. 1 Frame + 3 queries (2 probes + 1 terminal) = 4 queries total for a single-file question. Multi-layer investigations scale linearly: ~3-4 queries per layer.

## §3 Abstraction Frame — Write Before ANY SQL

**The Frame is mandatory. Skipping it is the #1 cause of budget waste.** Going straight to DISCOVER without a Frame fragments attention and collapses layers.

### 3.1 Template

```
═══ A* BUDGET FRAME  #<N> ═══
QUERY: <one sentence — what are we looking for>

LAYERS:
  <label>: <role description>
    DISCOVER:      candidate files via FTS5 MATCH
    TRACE_DEPS:    [optional] validate candidates via deps
    EXTRACT:       read file structure map via v_enriched
    EXTRACT_BLOCK: retrieve block_content_full → TERMINAL
    NO:            anti-pattern (e.g. "no whole-file read")
```

### 3.2 Rules

1. Every layer = DISCOVER → (TRACE_DEPS when helpful) → EXTRACT → EXTRACT_BLOCK. **Never skip to EXTRACT_BLOCK without a PROBE first.**
2. EXTRACT_BLOCK always uses `block_content_full`. `block_content` is for EXTRACT previews only.
3. Total EXTRACT_BLOCK output ≤ 6000 chars per feature.
4. **Budget annotation on EVERY query** — `[budget] L<N>-P/D/E: g=<N>` above each SQL. Use `-P` for probes (DISCOVER/EXTRACT), `-D` for TRACE_DEPS, `-E` for EXTRACT_BLOCK.
5. Goal test: `block_content_full` returns complete target → stop. New question = new frame.
6. **Pruning**: if h(n) too high (FTS5 rank >10, no LIKE hits) → downgrade (OR synonyms) or switch intent. Layer exceeds 12 queries → report unsearchable, move to next layer. Multi-layer investigations have independent budgets per layer; 40+ queries total is normal for full subsystem exploration.
7. **TRACE_DEPS is a search accelerator**, not just a call-chain tool. Use when DISCOVER returns 2+ candidates. Skip only when deps table is empty or DISCOVER returned a single unambiguous hit.

### 3.3 Budget tracking format

```
→ [budget] L1-P: g=1 — FTS5 MATCH 'SubstrateToonBSDF' → SubstrateToonBSDF.ush (rank -9.2)
→ [budget] L1-E: g=2 — block_content_full depth=1 → 4821 bytes ✓
```

## §4 Four Canonical Templates

Four templates. Variants exist for edge cases — keep the canonical shape as default.

### 4.1 DISCOVER — find candidate files via FTS5

```sql
-- [intent] <what we're hunting>
-- [budget] L<N>-P: g=<N>
SELECT f.path, rank
FROM files_fts, files f
WHERE files_fts MATCH '{QUERY}'
  AND files_fts.rowid = f.id
  AND f.path NOT LIKE '%test%'
ORDER BY rank LIMIT 15;
```

`{QUERY}` = FTS5 terms (space-separated, boolean operators OK).

### 4.2 TRACE_DEPS — disambiguate candidates via dependency graph

Deps are a **search accelerator**: use when DISCOVER returns 2+ candidates, or when you need to validate which file is the core target.

**TRACE_DEPS is NOT a call-chain tracing tool.** If the user asks "trace how X calls Y," write a Frame with DISCOVER→EXTRACT→EXTRACT_BLOCK per layer. TRACE_DEPS answers "which of these 3 files is the real implementation?" — not "what is the full call chain." For deep cross-file tracing, use §6 Dependency Chain Tracing as a reference, not as your primary search strategy.

```sql
-- [intent] validate candidate via deps
-- [budget] L<N>-D: g=<N>
-- Upstream: what does this file import?
SELECT f.path AS imported_file, d.depth
FROM enrich_file_deps d JOIN files f ON f.id = d.dep_file_id
WHERE d.file_id = (SELECT id FROM files WHERE path = '{FILE}')
  AND d.direction = 'upstream'
ORDER BY d.depth;

-- Downstream: who imports this file?
SELECT f.path AS importer, d.depth
FROM enrich_file_deps d JOIN files f ON f.id = d.file_id
WHERE d.dep_file_id = (SELECT id FROM files WHERE path = '{FILE}')
  AND d.direction = 'downstream'
ORDER BY d.depth;
```

`{FILE}` = candidate path from DISCOVER.

**Heuristic interpretation:**

| Signal | Meaning | Action |
|---|---|---|
| Many downstream deps (depth=1) | Core module, likely correct target | Proceed to EXTRACT |
| Few deps + high FTS5 rank | Leaf file; check upstream for real implementation | Switch to imported file |
| Upstream deps match your intent | Target is the dependency, not this file | Switch layer to that file |
| No deps (empty table) | Deps not enriched | Skip TRACE_DEPS, EXTRACT on top candidate |

**Budget**: TRACE_DEPS costs g=+1 per step (upstream + downstream). Limit to `depth <= 2` — beyond that fan-out explodes.

**Raw refs** (use when resolved deps are sparse, common on C/C++):

```sql
-- [intent] raw #include strings — full coverage
-- [budget] L<N>-D: g=<N>
SELECT target_raw, line_num
FROM enrich_file_refs
WHERE file_id = (SELECT id FROM files WHERE path = '{FILE}')
ORDER BY line_num;
```

### 4.3 EXTRACT — file structure map (PROBE before extraction)

```sql
-- [intent] <what layer this serves>
-- [budget] L<N>-P: g=<N>
SELECT depth_level, start_offset,
       length(block_content) AS bytes,
       length(block_content_full) AS full_bytes,
       substr(block_content, 1, 100) AS preview
FROM v_enriched
WHERE file_path = '{FILE}'
  AND depth_level <= {N}
ORDER BY depth_level, start_offset;
```

`{FILE}` = relative path from DISCOVER. `{N}` = max depth. Use `bytes` and `preview` to pick the right depth level and offset for EXTRACT_BLOCK.

**Depth by language — check this before EXTRACT_BLOCK:**

| Language family | depth=0 | depth=1 | depth=2 |
|---|---|---|---|
| Brace-based (JS,TS,Go,Rust,Java,C++,C#) | File envelope | **Full function body** | Nested blocks |
| Indent-based (Python,Ruby,YAML) | File envelope | Signature only | **Function body** |

- Brace: extract bodies at `depth=1`.
- Python: extract bodies at `depth=2`. depth=1 is signatures only.
- C++ `.ush` / `.usf` shader files: brace-based, depth=1 for function bodies.

**Variant — find symbol across all files (EXPENSIVE, use only when FTS5 fails):**

```sql
-- [intent] find where <symbol> is defined (narrow with file_path when possible)
SELECT file_path, depth_level, start_offset,
       length(block_content_full) AS full_bytes,
       substr(block_content, 1, 100) AS preview
FROM v_enriched
WHERE block_content LIKE '%{SYMBOL}%'
  AND depth_level <= {N}
ORDER BY depth_level, start_offset;
```

**⚠️ On >50K-file indexes, NEVER run this without a `file_path` filter — it scans the entire VIEW and can time out.**

### 4.4 EXTRACT_BLOCK — terminal extraction

```sql
-- [intent] <extract body of function/method/class>
-- [budget] L<N>-E: g=<N>
SELECT block_content_full FROM v_enriched
WHERE file_path = '{FILE}'
  AND depth_level = {N}
  AND start_offset = {OFFSET}
LIMIT 1;
```

`{FILE}`, `{N}`, `{OFFSET}` all from EXTRACT probe. **Never guess offset.**

**Variant — extract by symbol name (when offset unknown):**

```sql
-- [intent] <extract via name match>
-- [budget] L<N>-E: g=<N>
SELECT block_content_full FROM v_enriched
WHERE file_path = '{FILE}'
  AND block_content LIKE '%{SYMBOL}%'
  AND depth_level = {N}
ORDER BY start_offset LIMIT 1;
```

**After extraction, ALWAYS check `length(block_content_full)`.** If <200 bytes for a function you know is large → split-signature edge case.

#### block_content vs block_content_full

| Column | Scope | Use for |
|---|---|---|
| `block_content` | Immediate depth segment | EXTRACT previews only |
| `block_content_full` | Full enclosing scope (to next same-or-shallower segment) | **EXTRACT_BLOCK — always** |

`block_content_full` eliminates manual stitching. One query gets the complete body.

Detect truncation without extracting: `scope_end_offset - start_offset > end_offset - start_offset` → `block_content_full` has more content.

#### Split-signature edge case (~15% of large functions)

**Two causes:**
1. **Multi-line signatures** (Python params, TSX generics) — the def-line segment's `block_content_full` is only the signature.
2. **Nested-brace split on large functions** — a function body with 4000+ bytes may span multiple depth=1 segments because inner brace-blocks also get indexed. `block_content_full` from the first depth=1 segment only reaches the next same-depth boundary.

**Detection**: `full_bytes` from EXTRACT probe looks plausible (1000-3000 bytes) but the function should be larger — check if the depth=0 parent has much larger `full_bytes`, or if multiple adjacent depth=1 segments share the same function name prefix in their previews.

**Workaround for nested-brace split**: use the depth=0 parent segment instead:
```sql
SELECT block_content_full FROM v_enriched
WHERE file_path = '{FILE}'
  AND depth_level = 0 AND start_offset = {PARENT_OFFSET};
```

**For multi-line signatures**:

```sql
-- Step 1: find the def line
SELECT start_offset, length(block_content_full) AS full_len,
       substr(block_content_full, 1, 80) AS head
FROM v_enriched
WHERE file_path = '{FILE}'
  AND block_content LIKE '%def {FUNC}%'
  AND depth_level = {N}
ORDER BY start_offset;

-- Step 2: if full_len < 200, get the NEXT same-depth segment
SELECT block_content_full FROM v_enriched
WHERE file_path = '{FILE}'
  AND depth_level = {N}
  AND start_offset = (
    SELECT MIN(start_offset) FROM v_enriched ve2
    WHERE ve2.file_path = v_enriched.file_path
      AND ve2.depth_level = {N}
      AND ve2.start_offset > {STEP1_OFFSET}
  );
```

#### Escape hatch (very rare)

When `block_content_full` is truncated by SQLite/transport limits despite correct offsets:

```sql
SELECT substr(f.content, ve.start_offset + 1, ve.scope_end_offset - ve.start_offset)
FROM v_enriched ve JOIN files f ON f.id = ve.file_id
WHERE ve.file_path = '{FILE}' AND ve.start_offset = {OFFSET};
```

**This is the ONLY valid reason to leave v_enriched for raw files.content.** Offsets MUST come from v_enriched columns — never guess.

## §5 Full-Stack Example (4 layers, 8 queries)

```
═══ A* BUDGET FRAME  #1 ═══
QUERY: Dashboard TUI — how does the browser connect to the agent?

LAYERS:
  frontend:    xterm.js terminal + WebSocket client (ChatPage.tsx)
  api:         /api/pty WebSocket endpoint (web_server.py)
  backend:     PtyBridge PTY spawn (pty_bridge.py)
  transport:   tui_gateway WSTransport (ws.py)
```

Layer 1 — frontend:

```sql
-- [intent] find xterm.js terminal component
-- [budget] L1-P: g=1
SELECT f.path, rank FROM files_fts, files f
WHERE files_fts MATCH 'xterm Terminal ChatPage'
  AND files_fts.rowid = f.id AND f.ext IN ('.ts','.tsx')
  AND f.path NOT LIKE '%test%'
ORDER BY rank LIMIT 15;

-- [intent] extract ChatPage.tsx full component body
-- [budget] L1-E: g=2
SELECT block_content_full FROM v_enriched
WHERE file_path = 'web/src/pages/ChatPage.tsx'
  AND block_content LIKE '%function ChatPage%'
  AND depth_level = 0
ORDER BY start_offset LIMIT 1;
-- ✓ result: xterm.js Terminal + WebSocket /api/pty + resize + clipboard (29441 bytes)
```

Layer 2 — API endpoint:

```sql
-- [intent] find /api/pty WebSocket handler
-- [budget] L2-P: g=3
SELECT file_path, depth_level, length(block_content) AS bytes,
       substr(block_content, 1, 80) AS preview
FROM v_enriched
WHERE block_content LIKE '%async def pty_ws%'
  AND depth_level = 0;

-- [intent] extract pty_ws() full handler
-- [budget] L2-E: g=4
SELECT block_content_full FROM v_enriched
WHERE file_path = 'hermes_cli/web_server.py'
  AND block_content LIKE '%async def pty_ws%'
  AND depth_level = 0
ORDER BY start_offset LIMIT 1;
-- ✓ result: pty_ws() — auth → accept → bridge.spawn → reader/writer loops (4303 bytes)
```

Layer 3 — backend:

```sql
-- [intent] find PtyBridge.spawn in pty_bridge.py
-- [budget] L3-P: g=5
SELECT file_path, depth_level, length(block_content) AS bytes
FROM v_enriched
WHERE block_content LIKE '%class PtyBridge%'
  AND depth_level <= 1;

-- [intent] extract spawn() full method body
-- [budget] L3-E: g=6
SELECT block_content_full FROM v_enriched
WHERE file_path = 'hermes_cli/pty_bridge.py'
  AND block_content LIKE '%def spawn%'
  AND depth_level = 1
ORDER BY start_offset LIMIT 1;
-- ✓ result: PtyProcess.spawn() — TERM backfill → dimensions → return PtyBridge (1850 bytes)
```

Layer 4 — transport:

```sql
-- [intent] find tui_gateway WebSocket transport
-- [budget] L4-P: g=7
SELECT f.path, rank FROM files_fts, files f
WHERE files_fts MATCH 'handle_ws tui_gateway'
  AND files_fts.rowid = f.id AND f.path NOT LIKE '%test%'
ORDER BY rank LIMIT 15;

-- [intent] extract WSTransport full implementation
-- [budget] L4-E: g=8
SELECT block_content_full FROM v_enriched
WHERE file_path = 'tui_gateway/ws.py'
  AND block_content LIKE '%class WSTransport%'
  AND depth_level = 1
ORDER BY start_offset LIMIT 1;
-- ✓ result: WSTransport — dispatch() → same handlers as Ink stdio
```

→ ✓ goal: block_content_full returns complete body for all 4 layers (8 queries total).

## §6 Dependency Chain Tracing (Reference)

For deep cross-file tracing, use `enrich_file_deps` and `enrich_file_refs`. For routine candidate disambiguation, use §4.2 TRACE_DEPS — this section is for complex multi-hop tracing.

### Upstream deps (what does this file import?)

```sql
SELECT d.dep_file_id, f.path AS imported_file, d.depth
FROM enrich_file_deps d
JOIN files f ON f.id = d.dep_file_id
WHERE d.file_id = (SELECT id FROM files WHERE path = '{FILE}')
  AND d.direction = 'upstream'
ORDER BY d.depth;
```

### Downstream deps (what imports this file?)

```sql
SELECT d.file_id, f.path AS importer, d.depth
FROM enrich_file_deps d
JOIN files f ON f.id = d.file_id
WHERE d.dep_file_id = (SELECT id FROM files WHERE path = '{FILE}')
  AND d.direction = 'downstream'
ORDER BY d.depth;
```

### Cross-file references (symbol-level)

```sql
SELECT f.path, r.line_num, r.target_raw
FROM enrich_file_refs r
JOIN files f ON f.id = r.file_id
WHERE r.target_file_id = (SELECT id FROM files WHERE path = '{FILE}')
ORDER BY f.path, r.line_num;
```

**BUG ALERT — JOIN direction**: upstream joins `files f ON f.id = d.dep_file_id` with `WHERE d.file_id = target`. Downstream joins `files f ON f.id = d.file_id` with `WHERE d.dep_file_id = target`. Swapping these gives empty results.

**Coverage note**: On C/C++ projects, bare `#include "file.h"` patterns often fail path resolution. Basename fallback exists but resolved deps are always sparser than raw refs. `enrich_file_refs.target_raw` has full coverage; use it when resolved deps come up empty.

## §7 Domain Knowledge Banks (references/)

Pre-indexed architectural summaries built from A* traversal. Load with `skill_view(name="sql-manything", file_path="references/<name>.md")` before querying a known domain — they cut discovery cost to near-zero.

Key references:
- `references/fresh-agent-failure-transcripts.md` — two real sessions where pre-v5.4.0 document structure caused Frame-skipping and budget waste (43 queries, 23 queries). Evidence for why reading order = execution order.
- `references/trace-reversal-case-study.md` — how the original `:trace` prohibition was wrong: the wrapper supported it all along, but the SKILL.md was tested against the wrong sqlite3 binary. Lesson: verify doc claims against implementation.
- See `references/INDEX.md` for full catalog.

## §8 Common Violations (Checklist)

If something goes wrong, scan this list before debugging:

1. **Skipping the Frame.** Write the Abstraction Frame before any SQL.
2. **No budget annotation.** Every query needs `[budget] L<N>-P/D/E: g=<N>`.
3. **Using `block_content` for EXTRACT_BLOCK.** Use `block_content_full`.
4. **Blind `substr(content, N, M)`.** Offsets only from v_enriched columns.
5. **`path LIKE` for function names.** Symbols live in `block_content`.
6. **depth=1 for Python bodies.** Use depth=2; depth=1 is signature only.
7. **Skip PROBE → straight to EXTRACT_BLOCK.** Always DISCOVER/EXTRACT first.
8. **`read_file` after EXTRACT_BLOCK returned content.** block_content is the answer.
9. **Wrapping SQL in execute_code/Python.** `sqlite3` CLI is the transport.
10. **Stitching depth segments manually.** `block_content_full` spans levels.
11. **Confusing layer budget with investigation budget.** >12 queries per layer = unsearchable. Multi-layer investigations have independent budgets per layer.
12. **Not checking `length(block_content_full)`.** <200 bytes = classic split-signature. But **also** watch for 1000-3000 bytes on a known-large function — nested-brace split means the depth=0 parent may have 2×+ the content. Always cross-check `full_bytes` against the EXTRACT preview's expected scope.
13. **Accepting degraded `block_content_full` silently.** Check `scope_end_offset IS NULL` if consistently truncated.
14. **Only checking deps for call chains.** TRACE_DEPS is a search accelerator — use whenever DISCOVER returns 2+ candidates.
15. **Broad `block_content LIKE` without `file_path` filter on large indexes.** >50K files: always narrow with file_path from DISCOVER.
16. **FTS5 query with dots or special chars.** FTS5 syntax errors on `.` in search terms (e.g. `MATCH '"file" query.ush'`). Drop dots or use LIKE on pre-filtered files instead.
17. **Old table remnants from previous buggy versions.** Before re-running Phase 2, check `sqlite_master` for `file_enrich`, `file_enrich_blocks`, `file_enrich_xref` — these are old-format tables that won't be cleaned up by the new scripts and will clutter inspection output. Drop them first (see §1.0).
