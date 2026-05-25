# Changelog

All notable changes to SQL-ManyThing are documented here.

## [Unreleased]

### Added
- Phase 1: FTS5 trigram content index builder (`manything_build_db.py`)
- Phase 1: `.gitignore` enumeration mode (`--gitignore` flag)
- Phase 1: Profile system for SDK/engine-level indexing (`unreal-installed-core`, `unreal-installed-full`)
- Phase 2: cymbal symbol enrichment (`enrich_cymbal.py`)
- Phase 2: Graphify AST + document enrichment (`enrich_graphify.py`)
- Phase 2: Java build-output enrichment (`enrich_java_build.py`)
- Phase 2: Unreal UHT generated file enrichment (`uht_enrich.py`)
- Phase 3: SQLite wrapper with query tracing (`sqlite3_wrapper.sh`)
- Phase 3: Query log CLI (`manything_query_log.py`, `SQL-ManyThing-query-log`)
- Phase 3: Virtual path resolution (`/manything/<project>/source.db`)
- References: library analysis patterns, UE GAS attribute analysis
- Licensing: MIT License, third-party attribution notices
- Documentation: DESIGN.md, CONTRIBUTING.md, SECURITY.md

### Changed
- Privacy: all personal paths replaced with placeholders
- Localization: all documentation converted to English
- Binaries: cymbal archives excluded from repository (install via GitHub releases)
