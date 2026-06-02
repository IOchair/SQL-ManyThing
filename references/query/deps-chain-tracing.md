# Deps Chain Tracing — Correct Query Patterns

The `enrich_file_deps` table has both upstream and downstream directions.
Schema checkpoint: `(file_id, dep_file_id, direction, depth) WITH direction='upstream'|'downstream'`

- `direction='upstream'`: file_id = importer, dep_file_id = imported
- `direction='downstream'`: file_id = imported, dep_file_id = importer

## Upstream: what does a file import, transitively?

```sql
SELECT f.path, d.depth
FROM enrich_file_deps d JOIN files f ON f.id = d.dep_file_id
WHERE d.file_id = (SELECT id FROM files WHERE path = '<target>')
  AND d.direction = 'upstream'
ORDER BY d.depth, f.path;
```

## Downstream: who imports this file, transitively?

```sql
SELECT f.path AS importer, d.depth
FROM enrich_file_deps d JOIN files f ON f.id = d.dep_file_id
WHERE d.file_id = (SELECT id FROM files WHERE path = '<target>')
  AND d.direction = 'downstream'
ORDER BY d.depth, f.path;
```

**Bug alert (older versions)**: the downstream query was `JOIN files f ON f.id = d.file_id` and `WHERE d.dep_file_id = target`. Both are wrong — `file_id` is the imported file, `dep_file_id` is the importer. Use the pattern above.
