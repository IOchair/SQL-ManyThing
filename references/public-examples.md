# Public Examples

## Real-world: Unreal Engine 5.8 (installed build)

The largest validated target. Shows the complete wow-path.

### 1. Build the index

```bash
# Windows Python (avoids WSL DrvFs write overhead)
py -3 manything_build_db.py "D:\Path\To\Engine" \
  --gitignore .gitignore \
  --profile unreal-installed-core
```

Result:
```text
Files enumerated: 95182
Indexed: 89203 files in 173.2s
DB size: 3079.3 MB
```

### 2. Run the overview query

```bash
sqlite3 /manything/ue58/source.db "
SELECT ext, COUNT(*) AS cnt
FROM files
GROUP BY ext
ORDER BY cnt DESC
LIMIT 10;
"
```

Output:
```text
.h       45381
.cpp     36525
.cs       4185
.usf       851
.ush       789
.uplugin   878
.py        270
.ini       318
.hlsl        6
```

### 3. Find and tag a useful trace

```bash
# Search prior queries for actor-related patterns
sqlite3 :trace "
SELECT id, project, substr(sql_text, 1, 120) AS sql_preview
FROM query_trace
WHERE project='ue58'
  AND lower(sql_text) LIKE '%actor%'
ORDER BY id DESC
LIMIT 5;
"

# Found: a MATCH query locating AActor in Source/Runtime/Engine
sqlite3 :trace "
INSERT INTO query_notes (log_id, note, tag, created_at)
VALUES (12, 'Find Actor subclasses via FTS5', 'useful_pattern', strftime('%s','now'));
"
```

### 4. Next session: reuse the trace

```bash
# Pre-flight imports pending logs + shows tagged traces
SQL-ManyThing-query-log import
sqlite3 :trace "
SELECT id, note, substr(sql_text,1,120)
FROM query_trace
WHERE project='ue58' AND tag='useful_pattern'
ORDER BY id DESC
LIMIT 5;
"
```

## Small project: Any Python/JS repo

### 1. Build

```bash
python3 scripts/phase1/manything_build_db.py /path/to/project \
  --git --ext .py,.ts,.tsx,.js,.jsx,.json,.md
```

Result (typical Python web project, ~500 files):
```text
Files enumerated: 487
Indexed: 487 files in 0.8s
DB size: 4.2 MB
```

### 2. Overview

```bash
sqlite3 /manything/myproject/source.db "
SELECT substr(path, 1, instr(path || '/', '/') - 1) AS top_dir,
       COUNT(*) AS files
FROM files
GROUP BY top_dir
ORDER BY files DESC
LIMIT 10;
"
```

### 3. Symbol lookup + tag

```bash
# Find all function symbols matching 'auth'
sqlite3 /manything/myproject/source.db "
SELECT f.path, json_extract(s.value, '$.name') AS name
FROM file_enrich e
JOIN files f ON f.id = e.file_id,
     json_each(e.symbols) AS s
WHERE json_extract(s.value, '$.name') LIKE '%auth%'
LIMIT 20;
"

# Tag as useful
sqlite3 :trace "
INSERT INTO query_notes (log_id, note, tag, created_at)
VALUES (3, 'Auth-related symbol locations', 'fast_path', strftime('%s','now'));
"
```

### 4. Next session: pre-flight finds the tagged trace

```bash
SQL-ManyThing-query-log import
sqlite3 :trace "
SELECT id, note, substr(sql_text,1,100)
FROM query_trace
WHERE tag='fast_path' OR tag='useful_pattern'
ORDER BY id DESC
LIMIT 5;
"
```

## Key takeaway

The first exploration on any project discovers the query shape.
The second exploration reuses it — zero relearning.
The third is instant.
