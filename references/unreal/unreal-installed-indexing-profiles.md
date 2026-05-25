# Unreal Installed Engine Indexing Profiles

## Why this exists

A full UE installed-engine Phase 1 run can grow much larger than an older `srcidx_build.py` run even when the engine tree looks the same. The usual cause is not SQLite, FTS5, Phase 3 trace, or UHT enrich. It is almost always a changed Phase 1 input set: directory policy plus extension policy.

## Old srcidx baseline behavior

The older UE-oriented script used explicit skip directories:

```python
SKIP_DIRS = {
    ".git", "node_modules", "dist", ".venv", "venv", "__pycache__",
    "ThirdParty", "Intermediate", "Binaries", "Build", "Content",
    "DerivedDataCache", "Saved", "ScriptModules", "Platforms",
}
```

The old rebuild BAT used a narrow extension set:

```bat
python srcidx_build.py . --ext h,cpp,cs,usf,ush,hlsl --no-enrich
```

When comparing against that baseline, the claim "only a few `.py` files were missed" is only valid if both of these remain true:

1. The old explicit `SKIP_DIRS` policy is still applied.
2. The old extension set is still applied, with only `.py` added.

## Engine `.gitignore` is not equivalent to `SKIP_DIRS`

The installed Engine `.gitignore` typically ignores generated/build outputs such as:

- `.vs/`
- `Binaries/*`
- `Build/*`
- `Saved/*`
- `Intermediate/*`
- `DerivedDataCache/*`

It does not necessarily ignore source-heavy directories that the old script skipped, such as:

- `ThirdParty`
- `Content`
- `Platforms`
- `ScriptModules`

Therefore `--gitignore Engine/.gitignore` is a different indexing policy from the old UE baseline. It can include large vendor/source trees under `Source/ThirdParty` and large plugin source trees under `Plugins/*`.

## Profile recommendation

Use named intent profiles rather than a single "Unreal" default.

### Profile: `unreal-installed-lean`

Goal: reproduce old DB scale while adding useful Python coverage.

Directory policy:

```text
.gitignore + skip ThirdParty, Content, Platforms, ScriptModules
```

Extension policy:

```text
.h,.cpp,.cs,.usf,.ush,.hlsl,.py
```

Use this for ordinary agent code search and UHT enrich. UHT enrich only requires headers indexed for its target source files.

### Profile: `unreal-installed-full`

Goal: broadest installed-engine source search.

Directory policy:

```text
.gitignore only, or gitignore plus a minimal generated-output blocklist
```

Extension policy:

```text
.h,.hpp,.cpp,.c,.cc,.cs,.inl,.ipp,.usf,.ush,.ini,.json,.uplugin,.uproject,.py
```

Use this when the user explicitly wants third-party/vendor source, plugin metadata, config, shader, and descriptor files included.

## DB bloat diagnostic query

When a new DB is much larger than an old backup, normalize path separators before comparing. Windows-built old DBs may store `\`, while WSL/Python builds may store `/`.

```sql
ATTACH '<old_db>' AS old;

SELECT 'new', COUNT(*), SUM(size) FROM main.files;
SELECT 'old', COUNT(*), SUM(size) FROM old.files;

SELECT ext, COUNT(*), SUM(size)
FROM main.files
WHERE path NOT IN (SELECT replace(path, '\\', '/') FROM old.files)
GROUP BY ext
ORDER BY SUM(size) DESC;

SELECT
  CASE
    WHEN instr(substr(path, instr(path, '/') + 1), '/') > 0
    THEN substr(path, 1, instr(path, '/') + instr(substr(path, instr(path, '/') + 1), '/') - 1)
    ELSE path
  END AS prefix,
  COUNT(*),
  SUM(size)
FROM main.files
WHERE path NOT IN (SELECT replace(path, '\\', '/') FROM old.files)
GROUP BY prefix
ORDER BY SUM(size) DESC
LIMIT 30;
```

## UE 5.8 observed bloat pattern

A run using `.gitignore` only plus the full extension profile produced a much larger DB than the old backup. Normalized comparison showed the extra content came mainly from:

```text
Source/ThirdParty
Plugins/Experimental
Plugins/Runtime
Plugins/MetaHuman
```

The largest added extensions were:

```text
.h
.hpp
.json
.c
.inl
```

This clarified the assumption: the size jump came from Phase 1 input expansion, not from UHT enrich, trace logging, or SQLite malfunction.

## Practical rule

Before a large UE rebuild, state the intended profile explicitly:

- lean profile: old scale, UHT-friendly, faster, smaller DB
- full profile: broader search, larger DB, vendor/plugin/config coverage

Do not silently replace old `SKIP_DIRS` with `.gitignore` and call the result equivalent.
