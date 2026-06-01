# Java Import Resolver Limitation

`enrich_file_refs.py` resolves imports by matching candidate file paths against the `files` table using exact path equality. This works for languages where imports map directly to filesystem paths (Python `from x import y`, JS/TS `import './foo'`, C/C++ `#include "header.h"`).

Java imports use package-qualified class names (`org.neo4j.graphdb.Node`) that do NOT directly map to filesystem paths. The file path includes the source-root prefix (e.g., `community/kernel/src/main/java/org/neo4j/graphdb/Node.java`), but the resolver only converts dots to slashes without matching against suffix.

## Behavior

- `enrich_file_refs` extracts Java import strings via `RE_JAVA_IMPORT`
- `target_raw` is populated (e.g., `org.neo4j.graphdb.Node`)
- `target_file_id` remains NULL — resolved count is 0 for all Java imports

## Impact

- `enrich_file_deps` (flattened dependency tree) has 0 deps on Java-only codebases
- `v_enriched` `refs_to` / `refs_from` columns are NULL for Java projects
- `enrich_depth_segments` and block extraction are unaffected

## Fix Sketch

`suffix-match` approach — when resolving Java imports:

1. Convert `org.neo4j.graphdb.Node` → `org/neo4j/graphdb/Node.java`
2. Match against any `files.path` whose suffix matches the candidate
3. If exactly one file matches, resolve; if multiple (e.g., different source roots), pick the shortest path

Implementation note: suffix matching requires scanning all known paths per import, which is O(N) without an index. A reverse-suffix index (FTS5 on reversed path) or a pre-built suffix→id map would avoid the O(N) scan.

## Current Workaround

For Java codebases, use `enrich_java_build.py` for module-level dependency data, and use FTS5 + depth segments for code-level exploration. File-level import tracing requires the suffix-match fix.
