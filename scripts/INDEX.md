# Scripts Index

```text
scripts/
├── phase1/
│   └── manything_build_db.py          # FTS5 trigram content index
├── phase2/
│   ├── enrich_cymbal.py               # cymbal symbol enrich
│   ├── enrich_graphify.py             # graphify/fallback AST + document enrich
│   ├── enrich_java_build.py           # Java build-output enrich
│   └── uht_enrich.py                  # Unreal UHT .generated.h enrich
├── phase3/
│   ├── SQL-ManyThing-query-log        # installable query-log command shim
│   ├── aliases.sh                     # MANYTHING_<project> path aliases
│   ├── manything_query_log.py         # query-log CLI implementation
│   ├── query_log.sql                  # query_log.db schema
│   └── sqlite3_wrapper.sh             # sqlite3 PATH wrapper
└── verify/
    └── verify_ue_uht_sql.py           # Unreal UHT DB verification
```

Each phase script should have a matching reference under `references/phaseN/` or a domain-specific reference under `references/unreal/` / `references/platforms/`.
