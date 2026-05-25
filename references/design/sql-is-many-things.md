# SQL-ManyThing Design

For the origin narrative, comparison with grep/LSP/cloud indexing/RAG, and the 3-step meta-strategy to reproduce this project, see `README.md` in the skill root.

SQL-ManyThing turns any source tree into a queryable SQLite database for local code
intelligence. It is designed for AI agents that need to answer questions about unfamiliar
codebases without reading every file.

## A\* Search Framing

The system models code exploration as an A\* search over a finite state space:

- **State space** = files + rows + symbols + graph nodes + trace history
- **g(n)** = queries and tool calls already spent navigating the space
- **h(n)** = remaining cost, estimated by symbol precision, graph coverage, and
  trace reuse potential
- **Operator** = one SQL query or one bounded `substr()` source extraction
- **Goal** = an evidence-rich answer obtained by reading the minimum necessary
  source text

This framing keeps the agent cost-conscious: every operator costs tokens, so the
system is biased toward narrow, targeted queries rather than whole-file scans.

## Why SQLite + FTS5

- **Universal and local** — no server process, no network, no deployment friction
- **Inspectable at every layer** — the database file is an open format; every
  table, index, and query plan is visible
- **FTS5 trigram tokenizer** — handles CJK characters, code identifiers
  (`CamelCase`, `snake_case`), and natural language equally well. No language-specific
  tokenizer tuning needed.

## Bounded `substr()` Extraction

Evidence lives in small regions of large files. Rather than reading an entire 10,000-line
file, the system extracts only the slice containing the match via:

```sql
SELECT substr(content, max(1, ? - 30), ? + 60) FROM files WHERE rowid = ?
```

This is a **token efficiency primitive** — the agent pays for the relevant context
window, not the full file. It mirrors how a human developer scrolls to a specific
line number rather than reading top-to-bottom.

## Query Trace Persistence

Every agent session starts cold. `query_trace` captures query patterns, parameters,
and outcomes so future sessions learn from past ones:

- Agents query `:trace` (a dedicated trace database) to find reusable patterns
- Tagged traces (`useful_pattern`, `schema_intro`, `anchor_query`) act as a
  learned index over SQL strategies
- The system gets faster with use — no training, just replay of working queries

This is the key scaling mechanism: trace-driven learning means N agents querying
M projects collectively converge on efficient patterns without manual tuning.

## Virtual Path + Aliases

The wrapper intercepts `sqlite3` at the binary level and resolves
`/manything/<project>/source.db` to the actual `.srcidx/source.db` via
`MANYTHING_<project>` environment variable aliases:

- **Stable virtual path** — survives project moves, renames, and drive relocations
- **Zero config per project** — set one alias, and every agent in every session
  finds the database
- Registration: `echo 'MANYTHING_myproject="/path/to/project"' >> aliases.sh`

## Profiles Over `.gitignore`

`.gitignore` is lossy for installed SDKs and engines that lack a `.git` directory.
Engine layouts (e.g., Unreal Engine) have deeply nested trees like
`ThirdParty/Content/Platforms/ScriptModules` where the signal-to-noise ratio is
abysmal. Profile policy is explicit and auditable:

- `unreal-installed-core` — keep `.h,.cpp,.cs,.usf,.ush,.hlsl,.py,.ini,.uplugin`;
  skip known high-noise paths
- `unreal-installed-full` — broader extension set for deep ThirdParty or data
  exploration

Profiles are checked into the project configuration and do not require a
`.gitignore` file to exist. This makes them suitable for CI/CD pipelines,
container images, and any environment where `.git` is absent.
