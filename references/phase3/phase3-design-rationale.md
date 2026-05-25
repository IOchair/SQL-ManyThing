# Phase 3 — Design Rationale

Why query_log + :trace works the way it does. Captures architectural decisions and the reasoning behind each, so future sessions understand constraints without rediscovering them.

## Current Script Status

The `scripts/phase3/` directory exists and was smoke-tested on WSL against a Windows-hosted project. It is usable for the basic path, but should still be treated as an early implementation rather than a polished installer.

Validated:

- `manything_query_log.py init` creates `~/.hermes/manything/query_log.db`, `aliases.sh`, and `pending.jsonl`.
- `sqlite3_wrapper.sh` works when copied to `~/.local/bin/sqlite3` and `~/.local/bin` is before `/usr/bin` in PATH.
- `/manything/<project>/source.db` resolves through `aliases.sh`.
- `/manything/<project>/source.db` is not a real file path. `ls /manything/<project>/source.db` is not a valid health check; use `sqlite3 /manything/<project>/source.db "SELECT COUNT(*) FROM files"`.
- `query_trace` lives in `sqlite3 :trace`, not in any project `.srcidx/source.db`. Seeing no `query_trace` in project `.tables` is expected.
- wrapper logging appends to `pending.jsonl`.
- `manything_query_log.py import` moves pending records into `query_log.db`.
- `sqlite3 :trace "SELECT ..."` reads from the global query log.

Known rough edges:

- No installer script yet; setup currently needs manual `cp`, `chmod`, PATH ordering, and alias insertion.
- The documented command `SQL-ManyThing-query-log` is provided as `scripts/phase3/SQL-ManyThing-query-log`, but it still must be copied or symlinked into a PATH directory such as `~/.local/bin`.
- `aliases.sh` variable naming must match the wrapper. The wrapper expects `MANYTHING_<project>`.
- The wrapper implementation is usable, but this document may still describe ideal transparency rules stricter than current behavior.

## Architecture

```
LLM: sqlite3 /manything/<project>/source.db "SELECT ..."
  │
  ▼
[~/.local/bin/sqlite3 wrapper]   ← PATH-intercept the system binary
  │
  ├─ DB_PATH == ":trace"     → route to global query_log.db
  ├─ DB_PATH =~ /manything/*/   → resolve via aliases.sh → append jsonl → real exec
  └─ anything else           → exec real sqlite3 transparently
```

## Decisions (ordered by impact level)

### 🔴 1. `echo >> pending.jsonl` instead of SQL INSERT

**Problem discovered:** Agent SQL contains single quotes, newlines, nested quotes, even `---` separators. Shell string interpolation into an INSERT reliably breaks on `WHERE path LIKE '%it''s%'`.

**Solution:** Wrapper appends raw text to `pending.jsonl` using `echo >>`. No escaping, no parsing, no SQL in the critical path.

**Why not parameterized query:** `sqlite3` CLI parameter support is weak (`.parameter` with named params or heredoc). Adding complexity to the wrapper increases failure surface, violating the "transparent passthrough" constraint.

**Failure mode:** Even if `echo >>` fails (disk full, permissions), the wrapper continues to `exec` the real sqlite3 — the main query path is never blocked by logging.

### 🔴 2. Global query_log.db instead of per-project

**Problem considered:** Each project has its own `.srcidx/source.db`. Should query_log follow the same split?

**Decision:** Single global `~/.hermes/manything/query_log.db`.

**Why:** Agent most valuable query is cross-project: "how did I query that pattern last time on any project?" Per-project logs make this a multi-DB ATTACH complexity. Global DB with `project` column is one SELECT. Also, traces are about **the agent**, not about each project.

### 🟡 3. :trace is read-write, not read-only

**Problem considered:** If :trace is read-only, agent can view history but cannot annotate.

**Decision:** :trace maps to query_log.db directly (same file read-write). `query_notes` table allows INSERT FROM agent. This turns query_log from a passive log into an evolvable knowledge base.

**Pattern:** Agent discovers a useful query pattern → `sqlite3 :trace "INSERT INTO query_notes (log_id, note, tag) VALUES (42, 'this finds UHT headers', 'fast_path')"` → next session queries `SELECT sql_text FROM query_trace WHERE tag='fast_path'`.

### 🟡 4. Wrapper implemented as single script (not staged)

**Anti-pattern:** Building wrapper without logging first, then adding logging later. Two deploys, two verification cycles, no stable intermediate state.

**Approach:** Build full wrapper in one shot: path resolution + jsonl append + :trace routing + transparent passthrough. Each commit is independently deployable and testable.

### 🟢 5. Aliases in `.sh` source format (not TOML)

**Problem avoided:** Shell parsing TOML is fragile (multi-line values, escape rules, comment handling). 

**Solution:** `~/.hermes/manything/aliases.sh` is pure shell variable assignments:

```bash
SQLMANYTHING_neo4j="/path/to/neo4j"
SQLMANYTHING_llvm="/path/to/llvm-project"
```

Wrapper does one `source` call — zero parsing, zero dependency.

### 🟢 6. PATH hijack over symlinks or config

**Alternative rejected:** Symlink farm in `/manything/` → every new project needs `ln -s`, LLM must learn real paths.

**Chosen:** Wrapper at `~/.local/bin/sqlite3` (first in PATH). LLM always calls `sqlite3 /manything/<project>/source.db` — the virtual path is stable. Aliases.sh maps `<project>` → real root. Zero maintenance per new project beyond one `echo >> aliases.sh`.

### 🟢 7. :trace extends :memory: protocol

`sqlite3 :memory:` is a native reserved path. `:trace` follows the same convention — a special word that maps to a different database. LLM knows `:memory:` already, so `:trace` has zero learning curve.

## Constraints (non-negotiable)

1. **Token position stability** — The LLM-sourced string `sqlite3 /manything/neo4j/source.db "...SELECT..."` must be identical before and after Phase 3 installation. Any character change shifts transformer positional encoding. Wrapper is a pre-exec binary intercept, not a source transformation.
2. **Exit code transparency** — Wrapper must never block, rewrite, or suppress the real sqlite3 exit code.
3. **Error passthrough** — If `source.db` doesn't exist, wrapper emits the exact same `Error: unable to open database` as bare sqlite3. No extra lines, no wrapper error interleaved.
4. **Logging must not block query** — jsonl append on a separate path, failure `|| true` guarded.

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| No alias for project | Fall back to literal path `/manything/<p>/source.db` (fails same as bare sqlite3) |
| No aliases.sh file | Skip source, use literal path |
| pending.jsonl missing | `echo >>` creates it |
| pending.jsonl corrupt | `echo >>` appends; importer skips unparseable entries |
| Race condition (parallel wrapper calls) | `echo >>` is append-mode, atomic per line on POSIX. Multi-line entries (3 lines per record) may interleave under extreme concurrency — acceptable for async logging |
