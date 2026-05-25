# DB Maintenance

## Incremental updates: NOT supported

SQL-ManyThing builds a fresh index on every Phase 1 run (`DROP + CREATE`).
There is no incremental update mode. The pipeline is designed for full rebuilds
because:

- Source trees change unpredictably (files added, deleted, renamed, moved).
- FTS5 content index cannot efficiently patch individual rows at scale.
Incremental logic would add complexity with no practical benefit for agent-driven
workflows (rebuild is fast enough for most projects; Unreal Engine scale takes
under 20 min on SSD with Windows BAT for all phases).

## Recommended approach: delete or backup, then rebuild

```bash
# Option A: Delete old DB, rebuild from scratch
rm -rf /path/to/project/.srcidx
python3 scripts/phase1/manything_build_db.py /path/to/project --git --ext .ts,.tsx,.js,.jsx,.json,.md

# Option B: Backup, rebuild, compare
cp /path/to/project/.srcidx/source.db /path/to/project/.srcidx/source.db.bak
python3 scripts/phase1/manything_build_db.py /path/to/project --git --ext .ts,.tsx,.js,.jsx,.json,.md
```

Option B is safest when you have existing enrichments or query traces tied to
specific DB states — you can restore the backup if something goes wrong.

## In-place modification: slow, not recommended

SQLite `UPDATE` / `DELETE` on the `files` table works in theory but is slow
at scale because:

- FTS5 content tables must be rebuilt after row mutations.
- `DELETE` does not reclaim disk space (SQLite marks pages as free but does
  not shrink the file).
- Dropping and recreating the FTS5 table is equivalent to a full rebuild anyway.

```sql
-- These work but are NOT recommended:
DELETE FROM files WHERE ext NOT IN ('.py', '.md');
INSERT INTO files_fts(files_fts) VALUES('rebuild');

-- Better: just rebuild
```

## VACUUM

`VACUUM` reclaims disk space after large deletes but is a full-database copy
and takes time proportional to DB size. Use it only when you've deleted a
significant fraction of rows and need the space back. For routine maintenance,
delete-and-rebuild is simpler and gives the same result.

## `--replace` mode

Phase 1 `manything_build_db.py` already drops and recreates all tables on
every run. This is the default behavior — no `--replace` flag needed.
Enrichment tables created by Phase 2 scripts are independent; they are not
touched by a Phase 1 rebuild. If you need to re-run Phase 2 enrichment after
a Phase 1 rebuild, the enrich scripts check file `size:mtime` keys and skip
unchanged files automatically.
