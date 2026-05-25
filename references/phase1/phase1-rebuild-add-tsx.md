# Phase 1 Rebuild: Add Frontend Extensions + cymbal Enrich Walkthrough (2026-05-24)

**Scenario:** Investigating the hermes dashboard Skills tab implementation. Phase 1 originally used `--ext py,md,yaml,yml,toml` — no frontend files included.

## Debug Chain

```
files table has no .tsx → cymbal can't enrich → graphify has no nodes
                   ↓
        Frontend code unreachable via SQL-ManyThing pure SQL queries
                   ↓
        Must fall back to code_search / read_file
```

## Full Pipeline Rebuild (Add Frontend Extensions)

```bash
# 1. Check current extension coverage
sqlite3 /manything/hermes/source.db "SELECT DISTINCT ext FROM files ORDER BY ext"
# → .py .md .yaml .yml .toml  — missing .tsx .ts .js .jsx .css .html

# 2. Rebuild Phase 1 — keep existing extensions + add frontend extensions
python3 ~/.hermes/skills/sql-manything/scripts/phase1/manything_build_db.py \
  /path/to/project \
  --ext py,md,yaml,yml,toml,tsx,ts,js,jsx,css,html

# 3. Run cymbal enrich (includes newly indexed TSX/TS/JS)
python3 ~/.hermes/skills/sql-manything/scripts/phase2/enrich_cymbal.py \
  /path/to/project

# 4. Run graphify enrich (optional)
python3 ~/.hermes/skills/sql-manything/scripts/phase2/enrich_graphify.py \
  /path/to/project
```

## Verify cymbal TSX Support

```bash
# Single-file verification — cymbal v0.13.1+
cymbal outline --json web/src/pages/SkillsPage.tsx

# Output format (multi-file: dict, single-file: list):
# {
#   "name": "handleToggleSkill",
#   "kind": "function",
#   "file": "/abs/path/SkillsPage.tsx",
#   "rel_path": "web/src/pages/SkillsPage.tsx",
#   "start_line": 119,
#   "end_line": 141,
#   "depth": 0,
#   "signature": "(skill: SkillInfo) => Promise<void>",
#   "language": "typescript"
# }
```

## Query Frontend Symbols via Pure SQL After Rebuild

```sql
-- All TSX symbols
SELECT f.path, json_extract(value, '$.name') AS name,
       json_extract(value, '$.kind') AS kind,
       json_extract(value, '$.start_line') AS line
FROM file_enrich e, json_each(e.symbols) AS s
JOIN files f ON f.id = e.file_id
WHERE f.ext = '.tsx'
ORDER BY f.path, line;

-- Specific component
SELECT json_extract(value, '$.name') AS name,
       json_extract(value, '$.kind') AS kind,
       json_extract(value, '$.start_line') AS line,
       json_extract(value, '$.signature') AS sig
FROM file_enrich e, json_each(e.symbols) AS s
JOIN files f ON f.id = e.file_id
WHERE f.path = 'web/src/pages/SkillsPage.tsx'
ORDER BY line;
```

## Lessons Learned

- **Don't assume** — seeing the `enrich_graphify_nodes` table exist doesn't mean frontend code is queryable. First run `SELECT DISTINCT ext FROM files` to confirm the target extension is included in Phase 1.
- **Phase 1 `--ext` is a hard constraint** — all downstream enrich phases can only process files already in the `files` table. Frontend `.tsx`/`.ts`/`.js` files must be included at the Phase 1 stage.
- **cymbal doesn't filter by extension** — `enrich_cymbal.py` runs `cymbal outline --json` on every file in the `files` table regardless of extension. File in `files` table + cymbal can parse it = automatically enriched.
- **Debug workflow**: FTS5 search returns empty → check enrich tables with `.tables` → run `SELECT DISTINCT ext FROM files` to confirm the target extension exists → if extension is missing, Phase 1 must be rebuilt; enrich cannot fix it.
