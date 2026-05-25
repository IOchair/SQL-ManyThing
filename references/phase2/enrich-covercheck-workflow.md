# Enrich Coverage Check — Field Lessons (2026-05-24)

## Scenario

Investigate the Hermes Dashboard Skills management tab implementation. User required "pure SQL".

## Wrong Path (what happened)

1. Only used FTS5 MATCH searching `'skill tab dashboard'` → landed on web_server.py + docs
2. Searched `path LIKE '%skill%'` → 0 results (skills_tool.py lacks `skill` in path name)
3. Did not check `.tables` → assumed enrich_graphify absent
4. Fell back to code_search/read_file for frontend + backend code
5. User asked "was that pure SQL?" → admitted mixing 5 code_search + 5 read_file calls
6. User asked "no enrich_graphify?" → actual `.tables` check showed it existed

## Correct Path

```bash
# 1. pre-flight
SQL-ManyThing-query-log import
sqlite3 :trace "..."  # has useful_pattern records

# 2. Check enrich schema
sqlite3 /manything/hermes/source.db ".tables"
# → enrich_graphify_nodes, enrich_graphify_edges both exist!

# 3. Confirm coverage (critical! — graphify does not cover all extensions)
sqlite3 /manything/hermes/source.db "
SELECT n.file_type, f.ext, COUNT(*) as cnt
FROM enrich_graphify_nodes n
JOIN files f ON f.id = n.file_id
GROUP BY n.file_type, f.ext
ORDER BY cnt DESC
"
# → only .py (43379) + .md (33227), missing .tsx/.ts

# 4. Use graphify for backend routing (pure SQL)
sqlite3 /manything/hermes/source.db "
SELECT n.label, n.source_location, f.path
FROM enrich_graphify_nodes n
JOIN files f ON f.id = n.file_id
WHERE n.label IN ('get_skills()', 'toggle_skill()')
"
# → get_skills()   L2890  hermes_cli/web_server.py
# → toggle_skill() L2902  hermes_cli/web_server.py

# 5. Frontend .tsx has no graphify → use FTS5 to locate file paths
sqlite3 /manything/hermes/source.db "
SELECT path FROM files WHERE ext='tsx'
"
# → web/src/pages/SkillsPage.tsx

# 6. Pure SQL can locate file names and function names,
#    reading full component implementation requires read_file (when no ts parser available)
```

## Key Lessons

| Lesson | Root Cause |
|--------|-----------|
| **Check `.tables` first** — do not assume enrich tables exist or not | Without checking you don't know what indexes are available |
| **Graphify coverage is not universal** — verify extension scope | Hermes graphify only covers .py+.md; frontend .tsx is a blind spot |
| **FTS5 file-name location is enough** — don't force pure SQL to read full function bodies | No AST parser means no index; read_file is a legitimate fallback |
| **Graphify node names include paren suffix** — `get_skills()` not `get_skills` | `n.label LIKE '%()'` matches function nodes |
| **Call edges may be empty** — dynamic imports inside function bodies produce no edges | `from tools.skills_tool import _find_all_skills` not in call graph |
