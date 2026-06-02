# Old-format cleanup (pre-v5.4.0)

## Background

Before v5.4.0, the enrichment pipeline used a different table schema:
`file_enrich`, `file_enrich_blocks`, `file_enrich_xref`. These were created
by a buggy version of the Phase 2 scripts that has since been replaced by the
current `enrich_depth_segments` + `enrich_file_refs` + `enrich_file_deps` +
`v_enriched` schema.

The new scripts create tables with different names, so old remnants do NOT
interfere with the new pipeline running correctly. However, they:
- Waste disk space (the old tables can be hundreds of MB)
- Confuse `sqlite_master` inspection ("which tables should I query?")
- Can mislead an agent into thinking the old format's data is current

## Detection

```bash
sqlite3 /manything/<project>/source.db "
SELECT name, type, sql FROM sqlite_master
WHERE type='table' AND name LIKE 'file_enrich%';"
```

If this returns rows, old-format tables exist.

## Cleanup

```bash
sqlite3 /manything/<project>/source.db "
DROP TABLE IF EXISTS file_enrich;
DROP TABLE IF EXISTS file_enrich_blocks;
DROP TABLE IF EXISTS file_enrich_xref;"
```

## Re-run Phase 2

After cleanup, run Phase 2 normally:

```bash
python3 scripts/phase2/enrich_depth_segments.py /path/to/project --batch 500
python3 scripts/phase2/enrich_file_refs.py       /path/to/project --batch 500
python3 scripts/phase2/flatten_file_deps.py      /path/to/project
python3 scripts/phase2/create_enriched_view.py   /path/to/project
```

## Verification

After re-run, confirm only the new tables exist:

```bash
sqlite3 /manything/<project>/source.db "
SELECT name FROM sqlite_master
WHERE type IN ('table','view') AND name IN
  ('files','files_fts','v_enriched',
   'enrich_file_deps','enrich_file_refs','enrich_depth_segments')
ORDER BY name;"
```

Expected output — no `file_enrich`-prefixed tables:

```
enrich_depth_segments
enrich_file_deps
enrich_file_refs
files
files_fts
v_enriched
```

## Real-world example

This was discovered on the hermes-agent codebase (3,979 files, ~428 MB DB).
The old `file_enrich` tables were ~160 MB combined and went unnoticed until a
Phase 2 re-run was triggered by a script update. Cleanup and re-run took
under 2 minutes total.
