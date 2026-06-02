# SQL-ManyThing

**Give your AI agent a searchable memory of any codebase. One file. Zero servers. Instant recall.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.9+](https://img.shields.io/badge/Python-3.9%2B-green.svg)](https://www.python.org/)
[![SQLite: 3.35+](https://img.shields.io/badge/SQLite-3.35%2B-orange.svg)](https://www.sqlite.org/) · [🇨🇳 中文](README.zh-CN.md)

```bash
# Index 89K files
python3 scripts/phase1/manything_build_db.py /path/to/project

# Query in milliseconds
sqlite3 /manything/myproject/source.db \
  "SELECT f.path, rank FROM files_fts, files f
   WHERE files_fts MATCH 'layout prepare'
     AND files_fts.rowid = f.id
   ORDER BY rank LIMIT 10;"
```

---

## 🤖 Zero-Setup Agent Prompts (if in a hurry)

No installation needed. Copy these three prompts, feed them to **any fresh AI coding agent** one by one, and watch it reproduce the entire setup automatically:

**Prompt 1: Index the codebase**
```text
FTS5 + trigram full-text index the target project; design your own filter rules
```

**Prompt 2: Enrich & explore**
```text
Interactively query the DB, discover enrichment table designs, write batch enrichment scripts
```

**Prompt 3: Enable query memory**
```text
Auto-ingest SQL queries into the trace database, enabling historical query exploration before running new searches
```

Now you know the recipe. Come back for the details when you're ready.

---

## Quick Start

### Let your agent install it

SQL-ManyThing ships as self-contained scripts with zero external dependencies. Copy this to your agent:

> **Requires:** An agent with web access and shell execution (Claude, Cursor, Codex, etc.). For air-gapped environments, use the manual steps below.

> Read AGENTS.md from https://github.com/IOchair/SQL-ManyThing/tree/master and install it for this project. Index the project with Phase 1, run Phase 2 universal enrichment, set up Phase 3 query tracing, then invoke the `sql-manything` skill to index the target directory.

No pip install, no config files. The agent reads `SKILL.md`, finds the scripts, and runs them.

### Or do it yourself

```bash
git clone https://github.com/IOchair/SQL-ManyThing.git
cd SQL-ManyThing

# 1. Index (Phase 1)
python3 scripts/phase1/manything_build_db.py /path/to/project
# → creates .srcidx/source.db

# 2. Enrich (Phase 2 — universal, all languages)
python3 scripts/phase2/enrich_depth_segments.py /path/to/project --batch 500
python3 scripts/phase2/enrich_file_refs.py       /path/to/project --batch 500
python3 scripts/phase2/flatten_file_deps.py      /path/to/project
python3 scripts/phase2/create_enriched_view.py   /path/to/project

# 3. Tracing wrapper (Phase 3)
python3 scripts/phase3/install.py
echo 'MANYTHING_myproject="/path/to/project"' >> ~/.hermes/manything/aliases.sh
```

Default extensions for Phase 1: `.h,.cpp,.cs,.py,.ts,.tsx,.js,.jsx,.rs,.java`. Add `--ext .md,.toml` for docs/config, or `--profile unreal-installed-core` for an Unreal Engine build tree.

### Verify

```bash
sqlite3 /manything/myproject/source.db "SELECT COUNT(*) FROM files;"
sqlite3 /manything/myproject/source.db \
  "SELECT f.path, rank FROM files_fts, files f
   WHERE files_fts MATCH 'layout prepare'
     AND files_fts.rowid = f.id
   ORDER BY rank LIMIT 10;"
```

---

## Features

**89,203 files · 3 GB · millisecond search · one SQLite file.**

- 🔍 **FTS5 trigram full-text search** — find any symbol across your entire codebase in milliseconds
- 📦 **Single SQLite file** — no server, no daemon, no network. `scp` it anywhere.
- ✂️ **Bounded extraction** — `block_content_full` returns only the function body. Full files never enter context.
- 🧠 **Query memory** — every query logged, tagged, reusable. The index gets smarter with use.
- 👁️ **Pure SQL, fully auditable** — no black-box retrieval. Every result traceable to a `SELECT`.
- 🌐 **Language-agnostic** — C++, Python, JS, Rust, GLSL, generated code — if it's text, it's indexable.
- 🤖 **Agent-native** — stable entrypoints, canonical SQL templates, `:trace` for query reuse.

---

## Requirements

- **Python 3.9+** (stdlib only for Phase 1–2; no pip install needed)
- **SQLite 3.35+** with FTS5 trigram tokenizer enabled (included by default on most systems)
- **Bash** (Linux/macOS/WSL) or **PowerShell** (Windows) for the Phase 3 wrapper
- Phase 2 enrichment scripts use only Python stdlib; optional `cymbal` enrichment needs the `cymbal` CLI binary

---

## What Gets Built

**Per project — `.srcidx/source.db`:**

| Table | What it holds |
|---|---|
| `files` | File metadata + full text content |
| `files_fts` | FTS5 trigram index over `path` + `content` |
| `v_enriched` | Unified view: depth-segmented blocks with `block_content_full` |
| `enrich_depth_segments` | Raw depth-segmented block data |
| `enrich_file_deps` | Resolved import/include dependency graph |
| `enrich_file_refs` | Raw `#include` / `import` strings with line numbers |

Optional enrichment adds: `enrich_cymbal` (symbol definitions), `enrich_graphify_nodes` / `_edges` (AST/document graph), `file_enrich` (UHT reflection JSON).

**Global (Phase 3):**

| Path | Purpose |
|---|---|
| `~/.hermes/manything/query_log.db` | Query trace database |
| `~/.hermes/manything/aliases.sh` | Project alias registry |
| `~/.hermes/manything/pending.jsonl` | Pending query log buffer |

---

## Usage Examples

These are the canonical SQL templates. Every query follows this shape.

### DISCOVER — find candidate files

```sql
SELECT f.path, rank FROM files_fts, files f
WHERE files_fts MATCH 'layout prepare'
  AND files_fts.rowid = f.id
  AND f.path NOT LIKE '%test%'
ORDER BY rank LIMIT 15;
```

### EXTRACT — probe file structure

```sql
SELECT depth_level, start_offset,
       length(block_content) AS bytes,
       length(block_content_full) AS full_bytes,
       substr(block_content, 1, 100) AS preview
FROM v_enriched
WHERE file_path = 'src/layout.ts'
  AND depth_level <= 1
ORDER BY depth_level, start_offset;
```

### EXTRACT_BLOCK — terminal extraction

```sql
SELECT block_content_full FROM v_enriched
WHERE file_path = 'src/layout.ts'
  AND block_content LIKE '%function layout%'
  AND depth_level = 1
ORDER BY start_offset LIMIT 1;
```

> **Depth by language:** Brace-based (JS, TS, Go, Rust, Java, C++, C#) — bodies at `depth=1`. Indent-based (Python, Ruby, YAML) — signatures at `depth=1`, bodies at `depth=2`.

### Utility — project shape at a glance

```sql
SELECT ext, COUNT(*) AS n FROM files
GROUP BY ext ORDER BY n DESC;
```

For advanced patterns (dependency tracing, trace reuse, symbol search), see [Enrichment](#enrichment) and [Query Tracing](#query-tracing).

---

## Enrichment

Phase 1 gives you FTS5 search. Phase 2 adds structure — depth-segmented blocks, resolved dependencies, and raw reference strings — enabling bounded extraction without whole-file reads.

### Universal Workflow (all languages)

```bash
python3 scripts/phase2/enrich_depth_segments.py /path/to/project --batch 500
python3 scripts/phase2/enrich_file_refs.py       /path/to/project --batch 500
python3 scripts/phase2/flatten_file_deps.py      /path/to/project
python3 scripts/phase2/create_enriched_view.py   /path/to/project
```

This adds `v_enriched`, `enrich_file_deps`, `enrich_file_refs`, and `enrich_depth_segments`. The `v_enriched` view provides depth-aware block extraction:

```sql
-- Extract a function body at depth=1 (brace-based languages)
SELECT block_content_full FROM v_enriched
WHERE file_path = 'src/parser.ts'
  AND block_content LIKE '%function parseExpr%'
  AND depth_level = 1
ORDER BY start_offset LIMIT 1;
```

### Additional Enrichment Scripts

| Script | What it adds | Scope |
|---|---|---|
| `enrich_cymbal.py` | Symbol definitions (classes, functions, methods) | Python, Go, JS via `cymbal` CLI |
| `enrich_graphify.py` | AST/document graph nodes + edges | Python + Markdown only |
| `uht_enrich.py` | Unreal Header Tool reflection metadata | UE builds with UHT output |
| `enrich_java_build.py` | Java import resolution | Java projects |

On Windows, `scripts/phase2/run_phase2_universal_windows.bat` runs all 4 universal steps. On Linux/WSL/macOS, run the Python scripts directly.

Full details: [Phase 2 Enrichment Guide](references/phase2/enrich-covercheck-workflow.md)

---

## Query Tracing

The Phase 3 wrapper intercepts every `sqlite3` call to a `/manything/` database and logs it. Past queries become discoverable — agents can search what queries were run before and reuse proven patterns.

### Install the wrapper

```bash
python3 scripts/phase3/install.py
```

This places a `sqlite3` wrapper in `~/.local/bin/` that intercepts `/manything/<project>/source.db` and `:trace`. Verify with `which sqlite3` — it should point to `~/.local/bin/sqlite3`. Ensure `~/.local/bin` is before `/usr/bin` in `PATH`.

### Register a project

```bash
echo 'MANYTHING_myproject="/path/to/project"' >> ~/.hermes/manything/aliases.sh
```

### Query through the virtual path

```bash
sqlite3 /manything/myproject/source.db "SELECT COUNT(*) FROM files;"
```

### Search past queries

```bash
# :trace is a virtual path intercepted by the Phase 3 wrapper
sqlite3 :trace "
SELECT id, project, tag, substr(sql_text, 1, 120) FROM query_trace
WHERE project = 'myproject'
ORDER BY id DESC LIMIT 10;"
```

### Tag useful query patterns

```sql
INSERT INTO query_notes (log_id, note, tag, created_at)
VALUES (42, 'overview entrypoint query', 'useful_pattern', strftime('%s','now'));
```

Tagged queries accumulate over time — future sessions can `SELECT * FROM query_trace WHERE tag IS NOT NULL` to discover proven patterns without repeating discovery work.

Full architecture: [Phase 3 Design Rationale](references/phase3/phase3-design-rationale.md)

---

## How It Works

Instead of throwing whole files at the LLM, SQL-ManyThing treats code search as an A\* exploration: find the right file, extract only the proof, and answer from minimal evidence.

### The Search Loop

```
Mainstream RAG:          SQL-ManyThing:
─────────────────        ──────────────────────
embed whole files   →    FTS5 rank candidates
retrieve chunks     →    substr() extract proof
stuff context       →    answer from evidence
hope for the best   →    verify with SQL
```

Under the hood this is A\* search over an information state-space tree (`g(n)` = cost spent, `h(n)` = estimated remaining cost, `operator` = one SQL query, `goal` = evidence-rich answer). The four canonical templates — DISCOVER → EXTRACT → EXTRACT_BLOCK — encode this loop as reusable SQL patterns.

**Narrow first. Extract second. Answer from evidence.**

### Design Principles

- **SQLite first.** Query everything with SQL. One file, fully inspectable.
- **Build once, reuse forever.** Index cost is paid once; queries are free.
- **Trace behavior, not just answers.** Every session leaves navigable breadcrumbs for the next.
- **Never read whole files.** Bounded `substr()` proves the answer without blowing context.
- **Profile policies over `.gitignore` assumptions.** Control what gets indexed explicitly.
- **Project-agnostic by default.** Domain-specific lessons live in `references/`, not the core.

### Why Scripts, Not a Unified CLI

Every script is a stable entrypoint: `python3 scripts/phase1/manything_build_db.py ...` keeps token positions predictable across sessions — important for agent-driven workflows where command strings are reproduced verbatim from query traces. See [Phase 3 Design Rationale](references/phase3/phase3-design-rationale.md) for the full argument.

---

## Performance

A full Unreal Engine 5.8 install — indexed locally, queried locally:

```
89,203 files indexed
~3.0 GB single SQLite database
Full-text search: sub-second
UHT reflection symbols: 4,455 classes · 3,247 structs · 1,590 enums · 8,902 functions
```

This is the stress test. The framework works on anything with files: JS/TS libraries, Python tools, Java projects, monorepos, generated code, build outputs — whatever you point it at.

> **WSL note:** DrvFS queries on Windows-hosted repos can be 30× slower than ext4. Copy the DB to `~/.hermes/manything/` for sub-second performance. See [DrvFS Performance](references/drvfs-performance.md).

---

## Comparison

|  | grep | LSP | Cloud RAG | **SQL-ManyThing** |
|---|---|---|---|---|
| **Offline** | ✅ | ✅ | ❌ cloud dependency | **✅** |
| **Sub-second search** | ❌ O(n) | ✅ narrow | ✅ + latency | **✅ FTS5** |
| **Bounded extraction** | ❌ full lines | ❌ | ❌ chunks | **✅ substr()** |
| **Query memory** | ❌ | ❌ | ❌ | **✅ trace log** |
| **Auditable results** | ✅ | ❌ | ❌ | **✅ pure SQL** |
| **Self-hosted index** | N/A | ✅ auto | ❌ | **✅ local SQLite** |

---

## Unreal Engine

UE is the project's primary stress-test target. The workflow is the same universal Phase 1 + Phase 2 — UE is just large, so batch files are provided to run on the Windows side (avoids WSL DrvFS write overhead).

### Phase 1 — Index with UE profile

```bash
# Or use templates/run_phase1_unreal_windows.bat on Windows
python3 scripts/phase1/manything_build_db.py /path/to/Engine \
  --gitignore /path/to/Engine/.gitignore \
  --profile unreal-installed-core
```

The `unreal-installed-core` profile filters extensions (`.h,.cpp,.cs,.usf,.ush,.hlsl,.py,.ini,.uplugin`) and skips high-noise paths (`Source/ThirdParty/`, `Content/`, `Platforms/`, `ScriptModules/`). Result: ~89K files, ~3 GB.

### Phase 2 — Universal enrichment (overload-tested on 89K files)

```bash
# Or use scripts/phase2/run_phase2_universal_windows.bat on Windows
python3 scripts/phase2/enrich_depth_segments.py /path/to/Engine --batch 500
python3 scripts/phase2/enrich_file_refs.py       /path/to/Engine --batch 500
python3 scripts/phase2/flatten_file_deps.py      /path/to/Engine
python3 scripts/phase2/create_enriched_view.py   /path/to/Engine
```

UE shader files (`.usf`, `.ush`, `.hlsl`) are C-style brace languages and work with the universal depth-segment parser. The full run produces 5.2M segments at +394 MB DB growth.

### Phase 2 — UHT enrichment (optional)

Only for installed builds with generated UHT headers available:

```bash
python3 scripts/phase2/uht_enrich.py \
  --db /path/to/Engine/.srcidx/source.db \
  --uht-dir /path/to/Engine/Intermediate/Build/Win64/UnrealEditor/Inc \
  --source-prefix Engine/ --batch 500
```

UE-specific documentation:

- [Installed Build Indexing](references/unreal/installed-build-indexing.md) — indexing policy and filter profiles
- [UE58 Full Run](references/unreal/ue58-full-phase123-run.md) — end-to-end Phase 1–3 results with timing
- [UHT Generated Files](references/phase2/ue-uht-generated-files.md) — reflection metadata structure

---

## Windows / WSL Notes

- **Phase 1 indexing:** Run with Windows Python when possible — DrvFS writes from WSL are slower. WSL can query the resulting database fine.
- **Query performance:** Copy `.srcidx/source.db` to a native ext4 filesystem for sub-second queries. See [DrvFS Performance](references/drvfs-performance.md).
- **Wrapper:** `scripts/phase3/install.py` works cross-platform (Windows `.cmd` wrapper, Linux/WSL shell wrapper).
- **Template:** `templates/run_phase1_unreal_windows.bat` — quick-start batch file for UE indexing on Windows.

---

## References

Reference docs are organized by phase and domain:

| Area | Key Docs |
|---|---|
| **Phase 1** | ⭐ [Phase 1 Setup](references/phase1/phase1-setup.md) · [Gitignore Enumeration](references/phase1/gitignore-enumeration.md) |
| **Phase 2** | ⭐ [Enrich Coverage Workflow](references/phase2/enrich-covercheck-workflow.md) · [Cymbal](references/phase2/enrich-cymbal.md) · [Graphify](references/phase2/enrich-graphify.md) · [Java](references/phase2/enrich-java-build.md) · [UHT](references/phase2/ue-uht-generated-files.md) |
| **Phase 3** | ⭐ [Design Rationale](references/phase3/phase3-design-rationale.md) · [Importer Parsing](references/phase3/importer-parsing.md) |
| **Unreal** | [Installed Build Indexing](references/unreal/installed-build-indexing.md) · [UE58 Full Run](references/unreal/ue58-full-phase123-run.md) · [Indexing Profiles](references/unreal/unreal-installed-indexing-profiles.md) |
| **Platforms** | [WSL/Windows Smoke Test](references/platforms/wsl-windows-phase123-smoke.md) |
| **Design** | [SQL Is Many Things](references/design/sql-is-many-things.md) · [DB Maintenance](references/db-maintenance.md) |
| **Meta** | [Agent Query Loop Lessons](references/agent-query-loop-lessons.md) · [Public Examples](references/public-examples.md) · [Third-Party Attribution](references/third-party-attribution.md) |

Full catalog: [references/INDEX.md](references/INDEX.md)

---

## License

MIT
