# Phase 2 — Java Build Output Enrich (.class files)

## Purpose

Extract fully-resolved type information from compiled Java bytecode. .class files are the **primary enrich target** for Java — they contain resolved generics, annotation values, access flags, and complete method signatures that source-code AST cannot provide.

Pom.xml module hierarchy is a secondary supplement (build structure, not type info).

## Two levels (priority order)

- **Level 1 (primary):** Parse `.class` files via `javap` → resolved generic type signatures, annotation info, access flags
- **Level 2 (supplement):** Parse `pom.xml` files → module dependency tree (Maven project structure)

**Philosophy:** For Java, build output IS the best AST. The compiler already resolved generics, computed type bounds, and validated the code. Source-code AST (tree-sitter) is a fallback for when the project hasn't been built.

## Script

`scripts/phase2/enrich_java_build.py`

## Usage

```bash
# Both levels (requires JDK + built project)
python3 scripts/phase2/enrich_java_build.py /path/to/project

# pom.xml only (no JDK, no .class files)
python3 scripts/phase2/enrich_java_build.py /path/to/project --skip-classes
```

## Prerequisites

- `.srcidx/source.db` from Phase 1
- **Level 1 (.class):** JDK installed (`javap` in PATH) + project must have been built (target/ dirs with .class files)
- **Level 2 (pom.xml):** Python stdlib only

## Output

```
enrich_java_classfiles — (Level 1, primary)
  class_id         TEXT  PRIMARY KEY
  file_id          INT   REFERENCES files(id)
  class_name       TEXT  full class declaration (access flags, extends, implements)
  super_class      TEXT
  interfaces       TEXT  JSON list
  method_signatures TEXT full javap -p output
  field_types      TEXT
  access_flags     TEXT
  source           TEXT  .class file path

enrich_java_modules — (Level 2, supplement)
  module_id    TEXT  PRIMARY KEY  "group:artifact"
  artifact_id  TEXT
  group_id     TEXT
  parent_id    TEXT               references enrich_java_modules.module_id
  packaging    TEXT               "pom" | "jar" | etc.
  rel_path     TEXT               relative pom.xml path
```

## Comparison of all Java enrich strategies

| Aspect | graphify (`enrich_graphify.py`) | .class files (Level 1) | pom.xml (Level 2) |
|--------|-------------------------------|----------------------|-------------------|
| What | tree-sitter AST of .java | javap from .class | Maven module tree |
| Gives | class/method names, extends, calls imports | resolved generics, annotations, access flags, full signatures | module hierarchy, artifact coordinates, parent-child |
| Requires | tree-sitter-java pip | JDK + built project | Python stdlib |
| Status | Works now, no JDK needed | Blocked: no JDK available | Works now |
| Value for analysis | Structural edges (calls, inherits) | Type-level info (erased generics, annotation values) | Build structure (which module→which jar) |

The three are complementary. When JDK is available, Level 1 (.class) should be the primary Java enrich path.

## Query examples

### Level 1: .class files (requires JDK)

```sql
-- All classfiles by module
SELECT m.artifact_id, COUNT(*) AS classes
FROM enrich_java_classfiles c
JOIN enrich_java_modules m ON m.module_id LIKE '%' || SUBSTR(c.source, 1, INSTR(c.source, '/')-1)
GROUP BY m.artifact_id
ORDER BY classes DESC;

-- Classes with resolved superclass info
SELECT class_name, super_class
FROM enrich_java_classfiles
WHERE super_class IS NOT NULL
LIMIT 20;

-- Method signatures search
SELECT class_name, method_signatures
FROM enrich_java_classfiles
WHERE method_signatures LIKE '%@Override%'
LIMIT 10;
```

### Level 2: Module hierarchy

```sql
-- Top-level modules
SELECT module_id, packaging FROM enrich_java_modules
WHERE parent_id IS NULL
ORDER BY module_id;

-- Sub-modules of a given parent
SELECT m.module_id, m.packaging, m.rel_path
FROM enrich_java_modules m
WHERE m.parent_id = 'org.neo4j:parent'
ORDER BY m.module_id;

-- Module tree depth
WITH RECURSIVE mod_tree(id, lvl) AS (
  SELECT module_id, 0 FROM enrich_java_modules WHERE parent_id IS NULL
  UNION ALL
  SELECT m.module_id, t.lvl + 1
  FROM enrich_java_modules m JOIN mod_tree t ON m.parent_id = t.id
)
SELECT MAX(lvl) AS max_depth, COUNT(*) AS total FROM mod_tree;
```

## Known Fixes & Pitfalls

### Fix: docstring order consistent with reference doc
Script docstring previously labeled pom.xml as Level 1 and .class as Level 2, inverted from reference doc priority. Fixed so docstring matches: Level 1=.class (primary), Level 2=pom.xml (supplement).

### Fix: classfiles table DROP moved to classfiles function
`enrich_modules()` previously had `DROP TABLE IF EXISTS enrich_java_classfiles;` in its createscript. When Level 2 ran but Level 1 was skipped (no JDK), the classfiles table from a prior run was destroyed. Fix: move DROP into `enrich_classfiles()` createscript so it only fires when Level 1 actually executes.

### Fix: javap classpath must point to Maven output dir
Line `javap -p -cp <project_root> <classfile>` resolved types incorrectly because `-cp` pointed to project root, not the Maven output directory (typically `target/classes`). Fix: walk up from .class file path to find `target` dir, then use `<module>/target/classes` as classpath. Falls back to .class file's own directory when no `target/classes` exists.

### Pitfall: no JDK means no Level 1
Script degrades gracefully when `javap` is absent — Level 1 silently skipped. Do not interpret absence of `enrich_java_classfiles` table as script failure; check JDK availability first.

### Pitfall: unbuilt project = no .class files
Level 1 requires Maven `mvn compile` to have run. If project download has `target/` dirs but no .class files, the build step was skipped. The script correctly reports "no .class files found".

## Future work

- **.jar parsing**: unpack jar → parse contained .class files (for third-party dependency analysis)
- **Gradle**: `enrich_gradle_build.py` for build.gradle / build.gradle.kts
- This script is currently Maven-specific
