# Phase 1 — Gitignore Enumeration Mode

## Purpose

Use this when a project should be enumerated by a supplied `.gitignore` file instead of SQL-ManyThing's built-in `SKIP_DIRS` list or `git ls-files`.

This is useful for source trees that are not clean Git worktrees, projects on Windows drives from WSL, and large game-engine projects where the project-local `.gitignore` already encodes the correct skip policy.

## Command

```bash
python3 scripts/phase1/manything_build_db.py <project_root> \
  --gitignore <project_root>/.gitignore \
  --ext .h,.cpp,.cs,.py,.ts,.tsx,.js,.jsx,.rs,.java,.json,.md
```

## Behavior

`--gitignore <file>` switches enumeration to:

1. `os.walk(<project_root>)`
2. Load ignore rules from the specified `.gitignore`
3. Filter directories and files with those rules
4. Do not apply built-in `SKIP_DIRS`
5. Apply extension filtering only after enumeration, during DB build

This means directory and filename filtering are owned by the supplied `.gitignore`; SQL-ManyThing only applies the requested `--ext` list.

## Supported Pattern Subset

The current implementation supports the common source-indexing subset:

- blank lines and comments
- `!` negation
- rooted patterns such as `/Build`
- directory patterns such as `Saved/`
- basename globs such as `*.obj`
- nested path globs such as `Plugins/*/Intermediate/`

It is intentionally lightweight and dependency-free. If exact Git parity is required, compare against `git check-ignore` or `git ls-files --exclude-standard` in a real Git worktree.

## WSL/Windows Validation

Validated against a Windows-hosted Unreal project path from WSL:

```text
/mnt/d/Path/To/Project/.gitignore
```

Smoke checks:

```text
.vs/foo.suo                         -> ignored
Binaries/Win64/x.dll                -> ignored
Intermediate/Build/tmp.obj          -> ignored
Saved/Logs/a.log                    -> ignored
Source/LyraGame/Foo.cpp             -> kept
Config/DefaultGame.ini              -> kept
```

Full enumeration smoke:

```text
enumerated files: 9669
bad ignored prefix count: 0
```

DrvFs traversal on large Windows projects can still be slow. The validation run took about 90 seconds for enumeration only. That is a filesystem traversal cost, not a matching-rule failure.

## Pitfalls

1. Do not combine mental skip lists with `--gitignore`. The point of this mode is to let the specified file own directory and filename filtering.
2. `--gitignore` does not mean `--git`; it works without relying on Git metadata.
3. Extension filtering still happens later through `--ext`. A file can pass `.gitignore` filtering and still be skipped if its extension is absent from `--ext`.
4. This mode is not full Git semantics. Keep the implementation dependency-free unless a future requirement needs exact Git parity.
