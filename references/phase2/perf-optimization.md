# Phase 2 Performance Patterns

SQL round-trip elimination patterns proven on 8K-file codebases. Apply to any enrich script.

## Pattern 1: Cursor Reuse

**Before (N+1 cursor alloc per file):**
```python
for fid, path, mode, key in batch:
    c2 = conn.cursor()                    # BAD: new cursor per file
    c2.execute("SELECT content FROM files WHERE id=?", (fid,))
    row = c2.fetchone()
    content = row[0]
```

**After (single cursor):**
```python
for fid, path, mode, key in batch:
    c.execute("SELECT content FROM files WHERE id=?", (fid,))  # GOOD: reuse
    row = c.fetchone()
    content = row[0]
```

SQLite serializes all access through a single connection anyway — separate cursors add Python overhead with zero concurrency benefit.

## Pattern 2: Batch Tracker Check

**Before (N+1 query per file):**
```python
c.execute("SELECT id, path, ext, size, mtime FROM files")
for fid, path, ext, size, mtime in c.fetchall():
    key = f"{size}:{mtime}"
    c.execute("SELECT 1 FROM tracker WHERE file_id=? AND file_key=?", (fid, key))
    if c.fetchone() is None:
        pending.append(...)
```

**After (single LEFT JOIN):**
```python
c.execute("""
    SELECT f.id, f.path, f.ext, f.size, f.mtime
    FROM files f
    LEFT JOIN tracker t ON t.file_id = f.id
        AND t.file_key = (f.size || ':' || f.mtime)
    WHERE t.file_id IS NULL
""")
for fid, path, ext, size, mtime in c.fetchall():
    pending.append(...)
```

Eliminates N SQL round-trips. On 8K files: ~8ms vs ~800ms.

## Pattern 3: Batch UPDATE

**Before (N+1 per-row update):**
```python
for rowid, fid, raw in pending:
    candidates = resolve(raw)
    for cand in candidates:
        tid = path_to_id.get(cand)
        if tid:
            c.execute("UPDATE t SET target_file_id=? WHERE rowid=?", (tid, rowid))
            break
```

**After (executemany):**
```python
updates = []
for rowid, fid, raw in pending:
    candidates = resolve(raw)
    for cand in candidates:
        tid = path_to_id.get(cand)
        if tid:
            updates.append((tid, rowid))
            break

if updates:
    c.executemany("UPDATE t SET target_file_id=? WHERE rowid=?", updates)
```

On 11K resolved refs: ~50ms vs ~3,000ms.

## Pattern 4: Single-Pass Lookup Build

**Before (N+1 per path):**
```python
path_to_id = {}
for p in known_paths:
    c.execute("SELECT id FROM files WHERE path=?", (p,))
    row = c.fetchone()
    if row:
        path_to_id[p] = row[0]
```

**After (single SELECT):**
```python
path_to_id = {}
c.execute("SELECT id, path FROM files")
for fid, path in c.fetchall():
    path_to_id[path] = fid
```

## Pattern 5: WAL + Synchronous

Always add at start of enrich functions:

```python
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
```

Batch-writes on DrvFs: 3-5x speedup vs default journal_mode=DELETE.
