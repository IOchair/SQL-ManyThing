# SQL-ManyThing Agent Guide

This file is for coding agents working inside this repository. Human-facing positioning lives in `README.md`. Agent-facing priority is installation, repeatable runs, and not breaking query-trace semantics.

## Mental Model

SQL-ManyThing has three phases:

```text
Phase 1: build .srcidx/source.db with files + files_fts
Phase 2: add enrichment into the same DB
Phase 3: install sqlite wrapper + query log so agent queries are recorded and reused
```

Agents should keep query-time work in SQL. Do not switch between generic shell search and SQL unless setup is broken.

## Repository Layout

```text
scripts/
├── phase1/manything_build_db.py
├── phase2/enrich_depth_segments.py     # universal: brace/indent segments
├── phase2/enrich_file_refs.py          # universal: import/require/include extraction
├── phase2/flatten_file_deps.py         # universal: transitive dependency tree
├── phase2/create_enriched_view.py      # universal: v_enriched wide VIEW
├── phase2/enrich_cymbal.py             # optional: cymbal symbol enrich
├── phase2/enrich_graphify.py           # optional: graphify AST + doc enrich
├── phase2/enrich_java_build.py         # optional: Java build enrich
├── phase2/uht_enrich.py                # optional: Unreal UHT enrich
├── phase3/install.py                    # cross-platform wrapper installer
├── phase3/sqlite3_wrapper.py            # the wrapper itself
├── phase3/manything_query_log.py        # query log init + import
└── verify/verify_ue_uht_sql.py

references/
├── phase1/
├── phase2/
├── phase3/
├── platforms/
└── unreal/
```

## Install Phase 3 Locally

```bash
python3 scripts/phase3/install.py
```

This places a `sqlite3` wrapper in `~/.local/bin/` that intercepts `/manything/<project>/source.db` and `:trace`. Verify with `which sqlite3` — it should point to `~/.local/bin/sqlite3`. Ensure `~/.local/bin` is before `/usr/bin` in `PATH`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Register project aliases in exactly this format:

```bash
echo 'MANYTHING_myproject="/path/to/project"' >> ~/.hermes/manything/aliases.sh
```

The wrapper expects `MANYTHING_<project>`, not `SQLMANYTHING_<project>`.

## Verify Phase 3

Do not use `ls /manything/<project>/source.db`. `/manything/...` is not a filesystem path. It is a sqlite wrapper virtual path.

Correct verification:

```bash
sqlite3 /manything/myproject/source.db "SELECT COUNT(*) FROM files"
sqlite3 :trace "SELECT COUNT(*) FROM query_trace"
sqlite3 :trace ".tables"
```

Expected trace tables:

```text
query_log query_notes query_trace
```

`query_trace` does not belong inside any project `.srcidx/source.db`.

## Build Phase 1

General git repo:

```bash
python3 scripts/phase1/manything_build_db.py /path/to/project --git --ext .ts,.tsx,.js,.jsx,.json,.md
```

Directory with explicit `.gitignore`:

```bash
python3 scripts/phase1/manything_build_db.py /path/to/project --gitignore /path/to/project/.gitignore
```

Installed Unreal Engine core profile:

```bash
python3 scripts/phase1/manything_build_db.py /path/to/Engine \
  --gitignore /path/to/Engine/.gitignore \
  --profile unreal-installed-core
```

Profile behavior:

```text
unreal-installed-core:
  keep .h,.cpp,.cs,.usf,.ush,.hlsl,.py,.ini,.uplugin
  skip ThirdParty/Content/Platforms/ScriptModules high-noise paths

unreal-installed-full:
  keep broad source/data extensions
  intended only for deep ThirdParty/data exploration
```

## Windows / WSL Guidance

When indexing a large Windows-hosted tree, prefer Windows Python for Phase 1. WSL DrvFs writes are slow.

Template:

```text
templates/run_phase1_unreal_windows.bat
```

Copy these into a Windows-side run directory:

```text
run_phase1_unreal_windows.bat
manything_build_db.py
.gitignore
```

Then run the BAT from Windows.

WSL can still query the resulting DB:

```bash
sqlite3 /mnt/d/Path/To/Engine/.srcidx/source.db "SELECT COUNT(*) FROM files"
```

## Phase 2 Enrichment

### Universal Phase 2 (language-agnostic, no external tool deps)

Depth/indent segments — pre-index brace-depth or indent-level blocks:

```bash
python3 scripts/phase2/enrich_depth_segments.py /path/to/project --batch 500
```

File-level import refs — extract import/require/include across 10 languages:

```bash
python3 scripts/phase2/enrich_file_refs.py /path/to/project --batch 500
```

Transitive dependency flattening — upstream + downstream trees:

```bash
python3 scripts/phase2/flatten_file_deps.py /path/to/project
```

v_enriched wide VIEW — denormalized query surface:

```bash
python3 scripts/phase2/create_enriched_view.py /path/to/project
```

Run order: depth_segments → file_refs → flatten_deps → view. The VIEW LEFT JOINs all three — missing refs or segments produce rows with NULL columns rather than errors.

### Optional enrichment (tool-specific)

cymbal symbols:

```bash
python3 scripts/phase2/enrich_cymbal.py /path/to/project
```

graph/document enrichment:

```bash
python3 scripts/phase2/enrich_graphify.py /path/to/project
```

Java build enrichment:

```bash
python3 scripts/phase2/enrich_java_build.py /path/to/project
```

Unreal Installed Build UHT enrichment:

```bash
python3 scripts/phase2/uht_enrich.py \
  --db /path/to/Engine/.srcidx/source.db \
  --uht-dir /path/to/Engine/Intermediate/Build/Win64/UnrealEditor/Inc \
  --source-prefix Engine/ \
  --batch 500
```

For installed Unreal Engine, run UHT enrich as the primary optional Phase 2 path. Do not use cymbal/graphify as the main Unreal reflection strategy.

## Query-Time Rules for Agents

Before first query, check if any useful patterns are already tagged:

```bash
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

Expand natural-language intent into SQL-facing terms using world knowledge. For example, "implementation overview" should search terms like:

```text
files, ext, path, symbols, file_enrich, graph, README, package, src, layout, prepare, measure, benchmark
```

If a trace row is useful, tag it with SQL, not a separate CLI command:

```bash
sqlite3 :trace "
INSERT INTO query_notes (log_id, note, tag, created_at)
VALUES (<id>, '<reuse note>', 'useful_pattern', strftime('%s','now'));
"
```

Keep query-time reads on the virtual path after alias works:

```bash
sqlite3 /manything/<project>/source.db "SELECT ..."
```

Use direct `.srcidx/source.db` only for setup/debug.

## Overview Query Pattern

For a broad implementation overview:

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

Then choose a small set of anchors and bounded slices. Do not list every file.

Anti-patterns:

```text
grep -r "manything" ~/.hermes/
ls /manything/<project>/source.db
SELECT path FROM files WHERE path LIKE 'src/%' ORDER BY path; -- no LIMIT
whole-file substr(content, 1, length(content))
direct .srcidx/source.db query-time reads after virtual path is known
```

## Validation Commands

Syntax check:

```bash
python3 -m py_compile \
  scripts/phase1/manything_build_db.py \
  scripts/phase2/enrich_depth_segments.py \
  scripts/phase2/enrich_file_refs.py \
  scripts/phase2/flatten_file_deps.py \
  scripts/phase2/create_enriched_view.py \
  scripts/phase2/enrich_cymbal.py \
  scripts/phase2/enrich_graphify.py \
  scripts/phase2/enrich_java_build.py \
  scripts/phase2/uht_enrich.py \
  scripts/phase3/install.py \
  scripts/phase3/manything_query_log.py \
  scripts/verify/verify_ue_uht_sql.py
```

Reference path sanity:

```bash
python3 - <<'PY'
from pathlib import Path
root = Path('.')
for p in ['README.md', 'AGENTS.md', 'SKILL.md', 'references/INDEX.md', 'scripts/INDEX.md']:
    assert (root / p).exists(), p
print('ok')
PY
```

Unreal verification:

```bash
python3 scripts/verify/verify_ue_uht_sql.py /path/to/Engine/.srcidx/source.db
```

## Editing Rules

- Keep `README.md` human-facing and ambitious.
- Keep `AGENTS.md` procedural and installation-focused.
- Keep `SKILL.md` concise and query-time focused.
- Put phase details in `references/phaseN/`.
- Put platform notes in `references/platforms/`.
- Put Unreal notes in `references/unreal/`.
- Put executable helpers under `scripts/phaseN/` or `scripts/verify/`.
- After moving files, update `references/INDEX.md`, `scripts/INDEX.md`, and `SKILL.md` references.
