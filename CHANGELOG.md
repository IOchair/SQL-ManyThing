# Changelog

All notable changes to SQL-ManyThing are documented here.

## [Unreleased]

### Added
- Universal Phase 2 enrichment — language-agnostic, zero external tool deps:
  - `enrich_depth_segments.py`: brace-depth / indent-level block pre-indexing (C-family, Python, YAML)
  - `enrich_file_refs.py`: import/require/include extraction across 10 languages
  - `flatten_file_deps.py`: transitive upstream/downstream dependency tree flattening
  - `create_enriched_view.py`: denormalized `v_enriched` VIEW (files + segments + refs)
- UE shader extension support in universal scripts (`.usf`, `.ush`, `.hlsl` → brace mode + `#include` extraction)
- `v_enriched` block_content zoom-out query pattern — browse by depth level, never guess byte offsets
- Phase 2 overload test on UE 5.8 (89,203 files, 5.2M segments, 550K refs; 3.0 GB → 3.4 GB DB)
- Windows BAT template for universal Phase 2 runs (`scripts/phase2/run_phase2_universal_windows.bat`)
- Documented Java `target_file_id=NULL` design rationale (`references/phase2/java-import-resolver.md`)
- Performance optimization notes for enrich scripts (`references/phase2/perf-optimization.md`)
- SKILL.md: collapsed 7 operators → 3 (FTS5 / v_enriched / ImportDeps), A*-annotated query templates
- SKILL.md: pitfall #11 — never guess substr offsets when v_enriched has depth-level zoom
- `.gitignore` entry for `.srcidx/` build artifacts

### Changed
- SKILL.md restructured: `## Primary Query Chain` immediately follows A* model; `## Core Schema` moved after references
- SKILL.md prose trimmed ~40%; pitfalls collapsed from 15→11
- `v_enriched.block_content` replaces all legacy `instr`+`substr` anchor-hunting patterns
- Resolved orphan doc files: deleted `universal-phase2.md`, indexed `java-import-resolver.md`, confirmed `perf-optimization.md` in index
- TODO.md orphan section rewritten as resolved status

### Fixed
- `enrich_depth_segments.py`: added `.usf`, `.ush`, `.hlsl` to BRACE_EXTS (UE shaders use C-style braces)
- `enrich_file_refs.py`: added `.usf`, `.ush`, `.hlsl` to LANG_PATTERNS (map to `RE_C_INCLUDE`)
- BAT template: `D:\Path\To\Engine` placeholder (was hardcoded real path)
- Phase 2 run script ordering: `depth_segments` before `file_refs` (not vice versa)

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
