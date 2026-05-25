# UE 5.8 Installed Engine Full Run — WSL + Windows Python

## Target

Windows engine root:

```text
D:\Path\To\Engine
```

WSL path:

```text
/mnt/d/Path/To/Engine
```

## Run Pack

A Windows-side Phase 1 run pack was copied to:

```text
D:\Path\To\Engine\.srcidx\sql_manything_run
```

Contents:

```text
.gitignore
manything_build_db.py
run_phase1_unreal_windows.bat
```

The engine `.gitignore` was also archived for reuse with installed Unreal Engine trees:

```text
references/unreal/ue5-installed-engine.gitignore
```

## Phase 1

Command path:

```bat
D:\Path\To\Engine\.srcidx\sql_manything_run\run_phase1_unreal_windows.bat
```

The BAT runs Windows Python instead of WSL Python to avoid DrvFs write overhead:

```bat
py -3 "%SCRIPT%" "%ENGINE_ROOT%" --gitignore "%GITIGNORE%" --ext "%EXTS%"
```

Profile used:

```text
unreal-installed-core
```

The profile combines `.gitignore` with Unreal-specific path policy and a focused extension allowlist.

Extensions used by the core profile:

```text
.h,.cpp,.cs,.usf,.ush,.hlsl,.py,.ini,.uplugin
```

Core profile skips high-noise paths such as `Source/ThirdParty/`, `Plugins/*/Source/ThirdParty/`, `Content/`, `Plugins/*/Content/`, `Platforms/`, and `ScriptModules/`.

Result:

```text
Files enumerated: 95182
Indexed: 89203 files in 173.2s
DB size: 3228901376 bytes (3079.3 MB)
```

Verification:

```sql
SELECT COUNT(*) FROM files;       -- 89203
SELECT COUNT(*) FROM files_fts;   -- 89203
```

Top extensions:

```text
.h       45381
.cpp     36525
.cs       4185
.usf       851
.ush       789
.py        270
.ini       318
.uplugin   878
.hlsl        6
```

## Phase 2 — UHT Only

For installed Unreal Engine builds, run only UHT enrich for Phase 2. Do not run cymbal/graphify as the primary enrich path for Unreal.

UHT input:

```text
/mnt/d/Path/To/Engine/Intermediate/Build/Win64/UnrealEditor/Inc
```

Command:

```bash
python3 scripts/phase2/uht_enrich.py \
  --db /mnt/d/Path/To/Engine/.srcidx/source.db \
  --uht-dir /mnt/d/Path/To/Engine/Intermediate/Build/Win64/UnrealEditor/Inc \
  --source-prefix Engine/ \
  --batch 500
```

Result after adapting path resolution:

```text
UHT files: 4748
Parsed: 4742 files with symbols
Unique source files: 4742
Enriched: 4742 files
Total: 43.4s
```

Symbol counts in `file_enrich.symbols`:

```text
function   8902
class      4455
struct     3247
enum       1590
interface   226
```

Important fix:

UHT `CURRENT_FILE_ID` uses underscores for both path separators and literal underscores. The initial decoder produced paths such as:

```text
Source/Editor/AnimGraph/Internal/AnimBlueprintExtension/Base.h
```

while the real indexed file was:

```text
Source/Editor/AnimGraph/Internal/AnimBlueprintExtension_Base.h
```

`uht_enrich.py` now resolves this by trying exact path first, then progressively joining trailing path components with underscores.

Interface UFUNCTION fix:

UE 5.8 UINTERFACE generated headers can contain `DECLARE_FUNCTION(...)` thunks. `uht_enrich.py` now captures functions for both `class` and `interface` blocks.

## Phase 3

Alias:

```bash
MANYTHING_ue58="/mnt/d/Path/To/Engine"
```

Virtual DB smoke:

```bash
sqlite3 /manything/ue58/source.db "SELECT COUNT(*) FROM files;"
# 126055
```

Trace smoke:

```bash
sqlite3 /manything/ue58/source.db "SELECT ..."
SQL-ManyThing-query-log import
sqlite3 :trace "SELECT project, substr(sql_text,1,120) FROM query_log WHERE project='ue58' ORDER BY id DESC LIMIT 3;"
```

Verified `ue58` query records appear in `:trace`.

## Query Examples

FTS5:

```sql
SELECT path, rank
FROM files_fts
WHERE files_fts MATCH 'UCLASS Actor'
  AND path LIKE 'Source/%'
ORDER BY rank
LIMIT 5;
```

UHT enrich:

```sql
SELECT files.path,
       json_extract(value,'$.name') AS name,
       json_extract(value,'$.kind') AS kind,
       json_array_length(json_extract(value,'$.uht_functions')) AS fn_count
FROM files
JOIN file_enrich ON files.id=file_enrich.file_id,
     json_each(file_enrich.symbols)
WHERE json_extract(value,'$.name')='AActor';
```

Observed:

```text
Source/Runtime/Engine/Classes/GameFramework/Actor.h | AActor | class | 136
```
