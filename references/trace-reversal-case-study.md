# :trace Reversal Case Study — Why Violation #16 Was Wrong

Session 2026-06-02: while patching the sql-manything SKILL.md, the agent
added a `⚠ Never query :trace` warning to §1.3. This was based on the
original violation #16: "Querying `:trace` as a database. No such DB exists."

The user pushed back: `:trace` was designed to work — the whole Phase 3
architecture depends on it. Investigation revealed the truth.

## What Actually Exists

```bash
# The sqlite3 wrapper (scripts/phase3/sqlite3_wrapper.sh) has always handled :trace:
if [[ "$DB_PATH" == ":trace" ]]; then
    exec "$REAL_SQLITE3" "$QUERY_LOG_DB" "${ARGS[@]}"
fi
```

`:trace` resolves to `~/.hermes/manything/query_log.db` — a real SQLite
database with 816 queries logged across 3 projects, 10 tagged patterns.

```bash
sqlite3 :trace ".tables"
# → query_log  query_notes  query_trace

sqlite3 :trace "SELECT project, count(*) FROM query_log GROUP BY project;"
# → graphify_8|68  hermes_agent|414  ue58|334

sqlite3 :trace "SELECT id, tag FROM query_trace WHERE tag IS NOT NULL;"
# → useful_pattern, three_axis_join, dashboard_tui_architecture, reused
```

## Why the Original Prohibition Existed

The original SKILL.md author likely:

1. Saw `:trace` used as a bare SQLite filename → tried `sqlite3 :trace ".tables"`
   with the system sqlite3 (not the wrapper) → got an empty file or error
2. Concluded "no such DB exists" without checking whether the wrapper handled it
3. Added violation #16 to prevent agents from hitting the same error

The wrapper was never consulted. The prohibition was based on testing with
the WRONG sqlite3 binary.

## The Damage

For the entire lifetime of v5.3.1:

- 816 queries were auto-logged to `query_log.db` via the wrapper
- 10 patterns were manually tagged in `query_notes`
- ZERO agents ever searched `:trace` because the SKILL.md told them not to
- The trace-acceleration design (agent finds past queries → tags patterns →
  future agents discover them) was completely non-functional — not because
  the infrastructure was broken, but because the documentation forbade it

## Lesson

**Assertions in skill documentation about tool/feature availability must be
verified against the actual implementation.** The wrapper script is the
source of truth for what paths `sqlite3` supports. The SKILL.md is downstream
documentation that can drift.

When an agent encounters a SKILL.md claim of the form "X is not supported" or
"Y does not exist," and that claim is blocking a useful workflow, the correct
response is:

1. Read the implementation (wrapper script, install.py, config) — does it
   actually support X?
2. If yes → the SKILL.md claim is stale. Update it.
3. If no → document the correct alternative path in the SKILL.md.

Never blindly trust a prohibition without checking the implementation first.
