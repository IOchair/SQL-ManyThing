# Scripts Index

```text
scripts/
├── phase1/
│   └── manything_build_db.py           # FTS5 trigram content index
├── phase2/
│   ├── enrich_depth_segments.py        # universal: brace/indent segment pre-index
│   ├── enrich_file_refs.py             # universal: import/require/include extraction
│   ├── flatten_file_deps.py            # universal: transitive dependency flattening
│   ├── create_enriched_view.py         # universal: denormalized v_enriched VIEW
│   ├── enrich_cymbal.py                # optional: cymbal symbol enrich
│   ├── enrich_graphify.py              # optional: graphify AST + document enrich
│   ├── enrich_java_build.py            # optional: Java build-output enrich
│   └── uht_enrich.py                   # optional: Unreal UHT .generated.h enrich
├── phase3/
│   ├── SQL-ManyThing-query-log         # installable query-log command shim
│   ├── aliases.sh                      # MANYTHING_<project> path aliases
│   ├── manything_query_log.py          # query-log CLI implementation
│   ├── query_log.sql                   # query_log.db schema
│   └── sqlite3_wrapper.sh             # sqlite3 PATH wrapper
└── verify/
    └── verify_ue_uht_sql.py            # Unreal UHT DB verification
```

Universal Phase 2 scripts (depth_segments, file_refs, flatten_deps, view) run on any indexed project with zero external tool dependencies. Optional enrichment scripts (cymbal, graphify, java, uht) complement universal Phase 2 for project-specific needs.
