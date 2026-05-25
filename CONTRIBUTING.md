# Contributing to SQL-ManyThing

SQL-ManyThing is a community project. Contributions of all kinds are welcome.

## How to contribute

1. **Report issues** — open a GitHub issue with a clear description of the problem, including the command and output.
2. **Suggest enhancements** — open an issue with the "enhancement" label.
3. **Submit code** — see the PR workflow below.

## Adding a new enrich strategy

Phase 2 enrichment scripts follow a consistent pattern:

1. Create `scripts/phase2/enrich_<name>.py` that reads from `.srcidx/source.db` and writes into one or more `enrich_<name>_*` tables.
2. Add matching reference documentation at `references/phase2/enrich-<name>.md`.
3. Add a reference entry in `references/INDEX.md`.
4. Add tiny fixture data and tests under `tests/` (see existing fixtures for examples).
5. Ensure the script degrades gracefully when its external dependency is absent (no hard crashes, clear error messages).

## PR workflow

```bash
# Format and lint
# (add lint configuration as needed)

# Run tests
bash scripts/run_tests.sh

# Verify reference paths are valid
python3 -c "
from pathlib import Path
root = Path('.')
for p in ['README.md', 'AGENTS.md', 'SKILL.md', 'references/INDEX.md', 'scripts/INDEX.md']:
    assert (root / p).exists(), p
print('Reference check: OK')
"
```

## Guidelines

- Keep `README.md` human-facing and ambitious.
- Keep `AGENTS.md` procedural and installation-focused.
- Keep `SKILL.md` concise and query-time focused.
- Put phase details in `references/phaseN/`.
- Put Unreal notes in `references/unreal/`.
- Do not commit personal paths. Use `/path/to/project` placeholders.
- Do not commit binary artifacts. Document install steps instead.
- Add small fixture data for every new enrich script, not just production-size examples.
