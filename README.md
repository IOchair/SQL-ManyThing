# SQL-ManyThing

**Turn any source tree into a local SQLite database. Full-text search 89,000 files in seconds. One file. No server. No network.**

SQL-ManyThing builds a FTS5 trigram index of your entire codebase, adds optional symbol/graph enrichment, and records every query so agents get smarter with each session.

> 🇨🇳 [中文版](README.zh-CN.md)

---

## The Shock Test

A full Unreal Engine 5.8 install — indexed locally, queried locally:

```
89,203 files indexed
~3.0 GB single SQLite database
Full-text search: seconds
UHT reflection symbols: 4,455 classes · 3,247 structs · 1,590 enums · 8,902 functions
```

This is the stress test. The framework works on anything with files: JS/TS libraries, Python tools, Java projects, monorepos, generated code, build outputs — whatever you point it at.

---

## Why This Exists

Most AI agent code search is still grep + cat: linear scan, whole-file reads, repeated loading, exploding token budgets. Every alternative has friction:

| | grep | LSP | Cloud RAG | **SQL-ManyThing** |
|---|---|---|---|---|
| **Offline** | ✅ | ✅ | ❌ needs network | **✅** |
| **Query speed** | O(n) scan | O(1) jump | ms + network | **ms local FTS5** |
| **Token cost** | whole-file reads | precise but narrow | retrieval + stitching | **bounded `substr()`** |
| **Auditable** | ✅ | ❌ black box | ❌ black box | **✅ pure SQL** |
| **Language-agnostic** | ✅ | ❌ language-locked | ✅ | **✅ any file** |
| **Self-built index** | ❌ | ✅ auto | ❌ external service | **✅ local SQLite** |

Any index beats grep. SQLite FTS5 is the simplest one that works at scale.

---

## Core Idea

Model code search as A* search:

```
state space = files + rows + symbols + graph nodes + trace history
g(n)        = queries / tool calls / tokens already spent
h(n)        = remaining cost estimated by rank, symbol precision, graph coverage, trace reuse
operator    = one SQL query or one bounded source extract
goal        = evidence-rich answer with minimal source text
```

**Narrow first. Extract second. Answer from evidence.**

This is nearly inverted from mainstream RAG: instead of retrieving chunks and stuffing context, FTS5 locates targets, `substr()` extracts proof, and full files never enter the context window.

---

## Quick Start

### Phase 1 — Build the FTS5 Index

```bash
# Any project
python3 scripts/phase1/manything_build_db.py /path/to/project \
  --git --ext .ts,.tsx,.js,.jsx,.json,.md

# Plain directory with .gitignore
python3 scripts/phase1/manything_build_db.py /path/to/project \
  --gitignore /path/to/project/.gitignore

# Unreal Engine installed build
python3 scripts/phase1/manything_build_db.py /path/to/Engine \
  --gitignore /path/to/Engine/.gitignore \
  --profile unreal-installed-core
```

Output: `<project>/.srcidx/source.db`

### Phase 2 — Enrich (Optional)

```bash
# Symbol enrichment
python3 scripts/phase2/enrich_cymbal.py /path/to/project

# Graph/document enrichment
python3 scripts/phase2/enrich_graphify.py /path/to/project

# Unreal UHT reflection metadata
python3 scripts/phase2/uht_enrich.py \
  --db /path/to/Engine/.srcidx/source.db \
  --uht-dir /path/to/Engine/Intermediate/Build/Win64/UnrealEditor/Inc \
  --source-prefix Engine/ --batch 500
```

### Phase 3 — Query Tracing

```bash
# Initialize trace database
python3 scripts/phase3/manything_query_log.py init

# Install the sqlite3 wrapper
mkdir -p ~/.local/bin
cp scripts/phase3/sqlite3_wrapper.sh ~/.local/bin/sqlite3
cp scripts/phase3/SQL-ManyThing-query-log ~/.local/bin/SQL-ManyThing-query-log
chmod +x ~/.local/bin/sqlite3 ~/.local/bin/SQL-ManyThing-query-log
```

Ensure `~/.local/bin` precedes `/usr/bin` in `PATH`.

```bash
# Register a project
echo 'MANYTHING_myproject="/path/to/project"' >> ~/.hermes/manything/aliases.sh

# Query through the virtual path
sqlite3 /manything/myproject/source.db "SELECT COUNT(*) FROM files"

# Review trace history
SQL-ManyThing-query-log import
sqlite3 :trace "SELECT id, project, tag, substr(sql_text,1,120) FROM query_trace ORDER BY id DESC LIMIT 10"
```

---

## What Gets Built

**Per project:**
```
<project>/.srcidx/source.db
```

**Schema:**
```
files                   — file metadata + full text
files_fts               — FTS5 trigram index over path + content
file_enrich             — symbol/domain enrich JSON per file
enrich_graphify_nodes   — AST/document nodes
enrich_graphify_edges   — graph/document edges
```

**Global (Phase 3):**
```
~/.hermes/manything/query_log.db    — query trace database
~/.hermes/manything/aliases.sh      — project aliases
~/.hermes/manything/pending.jsonl   — pending query log buffer
```

---

## Query Examples

**Find files by content:**
```sql
SELECT path, rank FROM files_fts
WHERE files_fts MATCH 'layout prepare'
ORDER BY rank LIMIT 20;
```

**Project shape at a glance:**
```sql
SELECT ext, COUNT(*) FROM files
GROUP BY ext ORDER BY COUNT(*) DESC;
```

**Bounded source extraction** (never read the whole file):
```sql
SELECT instr(content, 'export function layout') FROM files WHERE path='src/layout.ts';
SELECT substr(content, 1200, 1600) FROM files WHERE path='src/layout.ts';
```

**Symbol search across enrichment:**
```sql
SELECT f.path,
       json_extract(s.value, '$.name') AS name,
       json_extract(s.value, '$.kind') AS kind
FROM file_enrich e
JOIN files f ON f.id = e.file_id,
     json_each(e.symbols) AS s
WHERE json_extract(s.value, '$.name') LIKE '%layout%'
LIMIT 50;
```

**Reuse past queries as agent memory:**
```sql
WITH intent(term) AS (
  VALUES ('files'), ('symbols'), ('graph'), ('README'), ('package'), ('src')
)
SELECT id, project, tag, note, substr(sql_text, 1, 180)
FROM query_trace
WHERE project = 'myproject'
  AND (tag IS NOT NULL OR EXISTS (
    SELECT 1 FROM intent WHERE lower(sql_text) LIKE '%' || lower(term) || '%'
  ))
ORDER BY tag IS NULL, id DESC LIMIT 12;
```

**Tag a useful query for future sessions:**
```sql
INSERT INTO query_notes (log_id, note, tag, created_at)
VALUES (42, 'overview entrypoint query', 'useful_pattern', strftime('%s','now'));
```

---

## Meta-Strategy (Reproduction Guide)

You can reproduce this project with three prompts executed in sequence:

1. **FTS5 + trigram full-text index** the target project; design your own filter rules
2. **Interactively query the DB**, discover enrichment table designs, write batch enrichment scripts
3. **Auto-ingest SQL queries** into the trace database, enabling historical query exploration before running new searches

---

## Design Principles

- **SQLite first.** Query everything with SQL. One file, fully inspectable.
- **Build once, reuse forever.** Index cost is paid once; queries are free.
- **Trace behavior, not just answers.** Every session leaves navigable breadcrumbs for the next.
- **Never read whole files.** Bounded `substr()` proves the answer without blowing context.
- **Profile policies over `.gitignore` assumptions.** Control what gets indexed explicitly.
- **Project-agnostic by default.** Unreal-specific and other project lessons live in `references/`, not the core.

---

## Why Raw Scripts, Not a Unified CLI

Every script is a stable entrypoint: `python3 scripts/phase1/manything_build_db.py ...`

A unified `manything build` wrapper would shift every token position in every command string. Transformer positional encoding is sensitive to displacement; even small shifts introduce noise in agent reasoning. By keeping raw scripts:

- Token positions across phases stay predictable
- Agent-issued commands in query traces are reproducible verbatim
- Zero cost forcing an agent to learn wrapper conventions

Same principle drives the Phase 3 sqlite3 wrapper: intercept at the binary level, never modify the query string reaching the LLM context.

---

## Windows / WSL Notes

For Windows-hosted repositories, run Phase 1 indexing with Windows Python when possible — DrvFs writes from WSL are slower. WSL can query the resulting database fine.

Template included: `templates/run_phase1_unreal_windows.bat`

---

## References

Start here:
```
.hermes/                — Hermes Agent project context
references/INDEX.md
scripts/INDEX.md
```

Key references:
```
references/phase1/phase1-setup.md
references/phase1/gitignore-enumeration.md
references/phase2/enrich-cymbal.md
references/phase2/enrich-graphify.md
references/phase2/ue-uht-generated-files.md
references/phase3/phase3-design-rationale.md
references/unreal/unreal-installed-indexing-profiles.md
references/unreal/ue58-full-phase123-run.md
```

---

## License

MIT
