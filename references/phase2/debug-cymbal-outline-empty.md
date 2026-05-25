# Debugging cymbal outline Returns Empty

Symptoms: `cymbal outline --json <file>` says "No symbols found" or script's enrich phase shows 0/50 per batch despite cymbal having indexed the repo.

## Checklist (in order)

### 1. Is the file git-tracked?

```bash
cd /path/to/repo
git ls-files path/to/File.java
```

If empty, cymbal skips it — it only indexes git-tracked files.

### 2. Is cymbal running from the right CWD?

Cymbal uses CWD to locate its per-repo DB (walks up to find git root). Running from outside the repo:

```
Warning: not inside a git repository — results may be empty.
```

Fix: `cd` into the repo root before calling cymbal, or add `cwd=target` to `subprocess.run()`.

### 3. Does cymbal have the repo indexed?

```bash
cybal ls --repos | grep <repo>
```

Shows per-repo entries with file/symbol counts. Each entry has a `db_path` under `~/Library/Caches/cymbal/repos/<hash>/index.db`.

### 4. Has the DB been fragmented by subdir indexing?

`cybal index <subdir>` creates separate repo entries per path. When outline is called, cymbal picks the wrong entry and returns empty.

Check: look for multiple entries for the same repo:
```
/path/to/neo4j/community    10694 files  212807 symbols
/path/to/neo4j/.srcidx      0 files     0 symbols
```

Fix: re-index root with `--force`:
```bash
cd /path/to/repo && cymbal index . --force
```

### 5. Does single-file outline work?

```bash
cd /path/to/repo
cybal outline --json $(realpath SomeFile.java)
```

If this works but batches don't, the issue is in how paths are constructed (relative vs absolute, symlink resolution).

### 6. Verify outline output format

Single file → JSON list `[{file, name, kind, ...}]`
Multiple files → JSON dict `{"/abs/path": [{...}] or null}`

Null values = files with no parseable symbols (empty/generated files). Normal to see 5-10% null for Java repos.

### 7. Check for stale file_enrich entries

Previous failed runs may have written null entries. Clear them:
```bash
sqlite3 .srcidx/source.db "DELETE FROM file_enrich"
```

### 8. Never pass `--db` to cymbal pointing at `.srcidx/source.db`

```bash
# ❌ DANGER — cymbal overwrites the FTS5 schema with its own:
cybal outline --json file.java --db /path/to/repo/.srcidx/source.db
```

Cymbal's `--db` flag tells it to **use that file as its own database**. It will create its own schema (files, symbols, refs tables) and drop the FTS5 content index. The damage is invisible until you check — the file size stays the same (cymbal writes over the pages).

**Recovery:** delete the corrupted DB and re-run `--phase db`.
```bash
rm -rf .srcidx/
python3 ~/.hermes/skills/sql-manything/scripts/phase1/manything_build_db.py . --ext java --phase db
```

### 9. Multi-language repos: Java does not include Scala

`cymbal ls --stats` shows language breakdown. If a repo has Scala (2754 files in neo4j) but you only indexed `.java`, you miss half the code. Re-run with `--ext java,scala` if cymbal supports the language.
