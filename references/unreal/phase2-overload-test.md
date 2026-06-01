# Phase 2 Universal Scripts — UE Overload Test

## Context

Universal Phase 2 scripts (`enrich_depth_segments`, `enrich_file_refs`, `flatten_file_deps`, `create_enriched_view`) were overload-tested against a full UE 5.8 installed-engine index: 89,203 files across 9 extensions, 3.1 GB DB.

## UE Extension Gaps

The base universal scripts don't know about Unreal shader extensions by default. Before running on UE, patch the copies:

### enrich_depth_segments.py — BRACE_EXTS

UE shader files use C-style braces. Add to `BRACE_EXTS` set:

```python
".usf", ".ush", ".hlsl",  # UE shaders (C-style braces)
```

Without this: `.usf` (851 files) + `.ush` (789 files) + `.hlsl` (6 files) fall through to default brace mode, which works but using the explicit list ensures they're tracked correctly.

### enrich_file_refs.py — LANG_PATTERNS

UE shader files use `#include` directives. Add to `LANG_PATTERNS` dict:

```python
'.usf':  [RE_C_INCLUDE],   # UE shader files use #include
'.ush':  [RE_C_INCLUDE],   # UE shader headers use #include
'.hlsl': [RE_C_INCLUDE],   # HLSL uses #include
```

Without this: shader files get no import references extracted (marked "no patterns"), losing cross-shader include relationships.

### Not needed

- `.cs` — already in BRACE_EXTS, no LANG_PATTERNS entry (C# uses `using`, not `#include`). 4,185 files get depth segments but no ref extraction.
- `.ini`, `.uplugin` — no brace structure, no language patterns. Gets empty depth segments with no refs. Harmless.

## Run Pattern

Copy scripts + BAT to a Windows-accessible directory on the same drive as the DB. Run via Windows Python to avoid DrvFs write overhead.

### Directory layout

```
Engine\.srcidx\sql_manything_run\
├── enrich_depth_segments.py    (patched)
├── enrich_file_refs.py         (patched)
├── flatten_file_deps.py
├── create_enriched_view.py
├── run_phase2_universal_windows.bat
├── run_phase1_unreal_windows.bat
├── manything_build_db.py
└── .gitignore
```

### BAT template

```bat
@echo off
setlocal EnableExtensions
setlocal EnableDelayedExpansion

set "RUN_DIR=%~dp0"
set "ENGINE_ROOT=D:\Path\To\Engine"
set "DB=%ENGINE_ROOT%\.srcidx\source.db"
set "BATCH=500"

REM Step 1 — depth segments (brace/indent scanning)
py -3 "%RUN_DIR%enrich_depth_segments.py" "%ENGINE_ROOT%" --batch %BATCH%

REM Step 2 — file refs (import/include extraction)
py -3 "%RUN_DIR%enrich_file_refs.py" "%ENGINE_ROOT%" --batch %BATCH%

REM Step 3 — flatten transitive deps
py -3 "%RUN_DIR%flatten_file_deps.py" "%ENGINE_ROOT%"

REM Step 4 — create v_enriched VIEW
py -3 "%RUN_DIR%create_enriched_view.py" "%ENGINE_ROOT%"

REM Verification
py -3 -c "
import sqlite3
c = sqlite3.connect(r'%DB%').cursor()
c.execute('SELECT COUNT(*) FROM enrich_depth_segments'); print(f'segments: {c.fetchone()[0]}')
c.execute('SELECT COUNT(*) FROM enrich_file_refs'); print(f'refs: {c.fetchone()[0]}')
c.execute('SELECT direction, COUNT(*) FROM enrich_file_deps GROUP BY direction')
for row in c.fetchall(): print(f'deps ({row[0]}): {row[1]}')
c.execute('SELECT COUNT(*), SUM(CASE WHEN block_content=\"\" THEN 1 ELSE 0 END) FROM v_enriched')
row = c.fetchone(); print(f'v_enriched: total={row[0]} empty={row[1]}')
"
```

### Invocation

From WSL:
```bash
cmd.exe /c "D:\Path\To\Engine\.srcidx\sql_manything_run\run_phase2_universal_windows.bat"
```

### Performance notes

- `--batch 500` reduces transaction overhead vs default 50 — critical for 89K-file DBs
- `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;` already set inside scripts
- Expect minutes, not seconds for full UE engine runs
- `flatten_file_deps` is the most variable step — depends on import density (C++ `#include` chains can be deep)

## .bat Encoding Gotcha

When authoring `.bat` files from WSL, `write_file` produces LF line endings and UTF-8. Windows `cmd.exe` requires CRLF + pure ASCII from the system's active code page (GBK on Chinese Windows). Symptoms: garbled mojibake output, every line treated as an unrecognized command.

Fix:
```bash
unix2dos path/to/file.bat
```
And ensure no non-ASCII characters (no em dashes `—`, no Unicode). Use `--` instead. Also: `%s` inside inline Python strings gets interpreted as `cmd.exe` variable expansion — use `%%s` or keep verification queries separate.

## Results — UE 5.8 (89,203 files, 3.0 GB DB)

| Step | Script | Output | Time |
|---|---|---|---|
| 1 | enrich_depth_segments | 5,242,711 segments | ~3m |
| 2 | enrich_file_refs | 550,253 refs | ~2m |
| 3 | flatten_file_deps | 993↑ / 993↓ deps (5 rounds) | 0.1s |
| 4 | create_enriched_view | 5,242,711 rows | ~3s |

DB growth: 3.0 GB → 3.4 GB (+394 MB).

Depth distribution: peak at depth=2 (1,413,300 segments), exponential decay past depth=5 — matches C++ engine expectations.

UE shader extension coverage confirmed:
- `.ush` (789 files): 47,564 depth segments, 1,415 files with #include refs
- `.usf` (851 files): 35,234 depth segments, 3,739 files with #include refs
- `.hlsl` (6 files): 87 depth segments, 4 files with #include refs
