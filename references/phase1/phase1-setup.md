# Phase 1 — FTS5 Trigram Content Index

## Purpose

Store all file contents in SQLite FTS5 with trigram tokenizer. Base layer that all Phase 2 enrich strategies build on.

## Script

`scripts/phase1/manything_build_db.py`

## Usage

```bash
# Default extensions (h,cpp,cs,py,ts,tsx,js,jsx,rs,java)
python3 scripts/phase1/manything_build_db.py /path/to/project

# Custom extensions
python3 scripts/phase1/manything_build_db.py /path/to/project --ext rs,md,toml

# Include .java
python3 scripts/phase1/manything_build_db.py /path/to/project --ext java,kt,scala
```

## Output

Creates `.srcidx/source.db` at project root with schema:

```
files         — id, path (UNIQUE), ext, size, mtime, content
files_fts     — FTS5 virtual, tokenize='trigram' (path, content)
file_enrich   — file_id→files, file_key (cache key), symbols (JSON)
```

## Incremental

Re-run to update changed files. Matches by `path` UNIQUE, replaces on conflict.

## Adding new file types

Pass `--ext` with additional extensions. No script changes needed.

## Dependencies

- `sqlite3 >= 3.34.0` (for trigram tokenizer)
- Python stdlib only (`sqlite3`, `os`, `sys`, `argparse`, `fnmatch`, `subprocess`, `json`)

## Quick-start template

After building a Phase 1 index, run these to orient yourself:

```bash
cd /path/to/project

# 1. File overview
sqlite3 .srcidx/source.db "
SELECT ext, COUNT(*) AS cnt
FROM files
GROUP BY ext
ORDER BY cnt DESC
LIMIT 10;
"

# 2. Top-level directory structure
sqlite3 .srcidx/source.db "
SELECT substr(path, 1, instr(path || '/', '/') - 1) AS top,
       COUNT(*) AS files
FROM files
GROUP BY top
ORDER BY files DESC
LIMIT 10;
"

# 3. FTS5 probe for a known identifier
sqlite3 .srcidx/source.db "
SELECT path, rank
FROM files_fts
WHERE files_fts MATCH 'YourFunctionName'
ORDER BY rank
LIMIT 10;
"

# 4. Bounded source extraction from a specific file
sqlite3 .srcidx/source.db "
SELECT substr(content, 1, 200)
FROM files
WHERE path = 'src/main.ts';
"
```
