# WSL/Windows Full Phase Smoke

Use this reference when validating SQL-ManyThing against a small repository stored on a Windows drive from WSL. The goal is to prove Phase 1, Phase 2, and Phase 3 together: index build, enrichment, alias resolution, sqlite wrapper logging, and `:trace` import.

## Scope

This is a portability smoke workflow, not a benchmark. Pick a small repository on `/mnt/<drive>/...` and run the full pipeline before changing scripts for Windows/WSL compatibility.

## A* Budget Shape

- S1 discover inputs: repository exists, `.git` exists if using `--git`, `.srcidx/source.db` state, portable tool archives, Python/sqlite availability.
- S2 Phase 1: build FTS5 DB, verify file count, extension distribution, and one FTS query.
- S3 Phase 2: run symbol enrichment and graph enrichment, then verify row counts and sample symbols/nodes.
- S4 Phase 3: initialize query log, install/verify sqlite wrapper path precedence, register alias, run `/manything/<project>/source.db`, import pending logs, query `:trace`.
- S5 archive local tool binaries only if they were used; store checksums.
- S6 final smoke: one combined query that proves files, FTS, symbol rows, graph rows, and trace rows.

## Generic Commands

```bash
ROOT=/mnt/d/path/to/repo
PROJECT=myproject
SKILL=/path/to/sql-manything

python3 "$SKILL/scripts/phase1/manything_build_db.py" "$ROOT" --git --ext .ts,.tsx,.js,.jsx,.json,.md
sqlite3 "$ROOT/.srcidx/source.db" "SELECT COUNT(*) FROM files; SELECT ext, COUNT(*) FROM files GROUP BY ext ORDER BY ext;"

python3 "$SKILL/scripts/phase2/enrich_cymbal.py" "$ROOT" --batch 25
python3 "$SKILL/scripts/phase2/enrich_graphify.py" "$ROOT"
sqlite3 "$ROOT/.srcidx/source.db" "SELECT COUNT(*) FROM file_enrich WHERE symbols IS NOT NULL AND symbols != '[]'; SELECT COUNT(*) FROM enrich_graphify_nodes; SELECT COUNT(*) FROM enrich_graphify_edges;"

python3 "$SKILL/scripts/phase3/manything_query_log.py" init
mkdir -p "$HOME/.local/bin" "$HOME/.hermes/manything"
cp "$SKILL/scripts/phase3/sqlite3_wrapper.sh" "$HOME/.local/bin/sqlite3"
chmod +x "$HOME/.local/bin/sqlite3"
printf 'MANYTHING_%s="%s"\n' "$PROJECT" "$ROOT" >> "$HOME/.hermes/manything/aliases.sh"
export PATH="$HOME/.local/bin:$PATH"
sqlite3 "/manything/$PROJECT/source.db" "SELECT COUNT(*) FROM files;"
SQL-ManyThing-query-log import || python3 "$SKILL/scripts/phase3/manything_query_log.py" import
sqlite3 :trace "SELECT project, sql_text FROM query_log WHERE project='$PROJECT' ORDER BY id DESC LIMIT 3;"
```

## Portable Tool Archive Pattern

If a user supplies a portable binary archive for the smoke, archive it under the skill only when it is actually used or explicitly requested:

```bash
mkdir -p "$SKILL/assets/bin/<tool>_<version>"
cp <tool-archive> "$SKILL/assets/bin/<tool>_<version>/"
sha256sum "$SKILL/assets/bin/<tool>_<version>/"* > "$SKILL/assets/bin/<tool>_<version>/SHA256SUMS"
```

Prefer the normal PATH tool first. Use the archived binary as a reproducibility asset, not as a permanent global override, unless a follow-up task asks for that policy.

## Durable Fix Patterns

- Do not encode a single workstation path into scripts. Accept project roots as arguments and resolve paths at runtime.
- WSL paths under `/mnt/<drive>` should be tested through real Phase 1/2/3 execution, not only by checking that files exist.
- If graph enrichment depends on an optional checkout, make the script degrade gracefully with a small built-in fallback or produce a clear setup instruction. Verify node counts after fallback.
- For Phase 3, the sqlite wrapper only intercepts `/manything/<project>/source.db` when `~/.local/bin` precedes `/usr/bin` in PATH.
- Provide a command shim for helper commands if docs mention a command name; otherwise show the Python script fallback next to the command.

## Final Smoke Query

```bash
sqlite3 "/manything/$PROJECT/source.db" "
SELECT 'files', COUNT(*) FROM files;
SELECT 'symbols', COUNT(*) FROM file_enrich WHERE symbols IS NOT NULL AND symbols != '[]';
SELECT 'graph_nodes', COUNT(*) FROM enrich_graphify_nodes;
SELECT 'graph_edges', COUNT(*) FROM enrich_graphify_edges;
SELECT 'fts', path FROM files_fts WHERE files_fts MATCH 'layout' ORDER BY rank LIMIT 3;
"
SQL-ManyThing-query-log import || python3 "$SKILL/scripts/phase3/manything_query_log.py" import
sqlite3 :trace "SELECT 'trace_count', COUNT(*) FROM query_log WHERE project='$PROJECT';"
```

## Prior Run Note

A previous smoke note lived at `references/platforms/wsl-windows-phase123-smoke.md`; it was consolidated here so platform-specific smoke tests live under `references/platforms/`.
