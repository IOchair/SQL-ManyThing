# Unreal Installed-Build Indexing

Use this reference when indexing a released/installed Unreal Engine tree, especially on Windows drives from WSL.

## Core lesson

A project `.gitignore` is necessary but not sufficient for SQL-ManyThing indexing. It filters generated outputs and binaries, but it does not express query value. Installed Unreal trees contain many source-like files that are searchable but low-value for engine architecture questions.

Use a profile that combines three filters:

1. `.gitignore` patterns
2. Unreal-specific path policy
3. extension allowlist

## Recommended profile

`unreal-installed-core`

Keep extensions:

```text
.h,.cpp,.cs,.usf,.ush,.hlsl,.py,.ini,.uplugin
```

Skip high-noise paths:

```text
Source/ThirdParty/
Plugins/*/Source/ThirdParty/
Content/
Plugins/*/Content/
Platforms/
ScriptModules/
```

Rationale:

- `.h/.cpp/.cs` carry engine code and UHT source targets.
- `.usf/.ush/.hlsl` carry shader code.
- `.py` captures Unreal Python tooling that older engine indexes often missed.
- `.ini` and `.uplugin` are small and useful for config/module/dependency questions.
- `.hpp/.c/.inl/.ipp/.json` can be valuable for deep dives but are high-noise in installed builds; keep them for a separate full profile.

## Why not gitignore-only

A gitignore-only full extension run on UE 5.8 indexed many large, low-query-value files:

```text
Source/ThirdParty        ~363 MB new content
Plugins/Experimental     ~248 MB new content
large vegetation JSONs   20 MB each range
Flite voice C tables      8-16 MB each range
large generated/vendor headers
```

Those files inflated the SQLite/FTS5 database without improving UHT enrichment. UHT overlap from the new full-extension set was zero in the UE 5.8 validation run.

## Rebuild rule

For full Phase 1 rebuilds, delete the old database before rebuilding instead of relying on `DROP TABLE` to shrink the file.

SQLite `DROP TABLE` releases pages into the freelist but does not shrink the database file. A profile rebuild can correctly reduce row count while leaving the old file size unchanged until `VACUUM` or deletion.

Preferred full rebuild sequence:

```bash
rm -f Engine/.srcidx/source.db Engine/.srcidx/source.db-journal Engine/.srcidx/source.db-wal Engine/.srcidx/source.db-shm
# then run the Windows-side BAT or Phase 1 script
```

Verify shrinkage with:

```sql
PRAGMA page_count;
PRAGMA freelist_count;
SELECT COUNT(*) FROM files;
SELECT ext, COUNT(*), SUM(size) FROM files GROUP BY ext ORDER BY SUM(size) DESC;
```

`freelist_count` should be `0` after delete-and-rebuild.

## Windows-side run pack

For a Windows-hosted installed engine tree, prefer Windows Python via BAT over WSL Python to avoid DrvFs write overhead.

Run pack contents:

```text
.gitignore
manything_build_db.py
run_phase1_unreal_windows.bat
```

The BAT should call:

```bat
py -3 "%SCRIPT%" "%ENGINE_ROOT%" --gitignore "%GITIGNORE%" --profile "unreal-installed-core"
```

## Phase 2 for installed builds

For installed Unreal Engine builds, run UHT enrichment as the primary Phase 2 strategy. Do not treat cymbal/graphify as the main Unreal enrichment path.

UHT-specific parser pitfalls:

- `CURRENT_FILE_ID` encodes both separators and literal underscores as `_`; exact decoded paths can fail. Resolve against the `files` table by trying exact path first, then progressively joining trailing components with underscores.
- UE 5.8 UINTERFACE generated headers can contain `DECLARE_FUNCTION(...)`; capture thunks for both class and interface blocks.

## Expected validation shape

A healthy installed-build core run should have:

- database size near the old focused index, not a full gitignore-only index
- `freelist_count = 0` after delete-and-rebuild
- UHT enrich count matching parsed generated headers that map to indexed `.h` sources
- `AActor` query resolves to `Source/Runtime/Engine/Classes/GameFramework/Actor.h`
