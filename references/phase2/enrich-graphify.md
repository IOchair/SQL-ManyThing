# Phase 2 — graphify AST + Document Enrich

## Purpose

Extract AST nodes + document structure using graphify's hand-written tree-sitter extractors. Fills cymbal blind spots:

- **Markdown documents** → heading tree + code block nodes
- **Rust** → functions, structs, enums, traits, impl methods, `use` declarations, `calls`/`method` edges
- **Java** → classes, interfaces, constructors, methods, `imports`/`extends`/`implements`/`calls` edges
- **Non-code files** (.json, .yaml, .toml via graphify extractors)
- **Docstrings/comments** (`_extract_python_rationale` for module/class/function docstrings + `# NOTE:` markers)

## Script

`scripts/phase2/enrich_graphify.py`

## Usage

```bash
python3 scripts/phase2/enrich_graphify.py /path/to/project
```

## Prerequisites

- `.srcidx/source.db` from Phase 1
- graphify project at `~/graphify` (or adjust `sys.path` in script)
- Tree-sitter parsers for target languages:
  ```bash
  pip3 install tree-sitter tree-sitter-rust tree-sitter-python tree-sitter-javascript tree-sitter-typescript tree-sitter-java tree-sitter-c tree-sitter-bash tree-sitter-json
  ```

## Output

Two dedicated enrich tables (separate from cymbal's `file_enrich`):

```
enrich_graphify_nodes  — file_id, node_id, label, file_type, source_location
enrich_graphify_edges  — file_id, source_node_id, target_node_id, relation, weight
```

### `file_type` values

| file_type | source | extractor |
|-----------|--------|-----------|
| `code`    | Code AST walk | `extract_rust`, `extract_java`, `extract_python`, etc. |
| `document`| Markdown parsing | `extract_markdown` (pure line-by-line, no tree-sitter) |
| `rationale`| Docstrings/comments | `_extract_python_rationale` (post-pass) |

### Edge `relation` values

| relation | meaning | source languages |
|----------|---------|----------|
| `contains` | parent→child (file→function, heading→subheading) | all |
| `calls` | function→function call | Rust, Java |
| `method` | impl block→method, class→constructor | Rust, Java |
| `imports` | file→import reference | Java (`import`) |
| `extends` | class→superclass | Java |
| `implements` | class→interface | Java |
| `imports_from` | file→module reference | Rust (`use`), Python (`import`) |
| `inherits` | class→base class | Python |

## Query examples

```sql
-- All Rust functions in a file
SELECT n.label, n.source_location
FROM enrich_graphify_nodes n
JOIN files f ON f.id = n.file_id
WHERE f.path = 'src/main.rs'
  AND n.label LIKE '%()'
ORDER BY n.source_location;

-- Call graph from main()
SELECT e.target_node_id
FROM enrich_graphify_edges e
JOIN enrich_graphify_nodes n ON n.node_id = e.source_node_id AND n.file_id = e.file_id
JOIN files f ON f.id = n.file_id
WHERE f.path = 'src/main.rs'
  AND n.label = 'main()'
  AND e.relation = 'calls';

-- Markdown heading tree for a doc
SELECT n.label, n.source_location
FROM enrich_graphify_nodes n
JOIN files f ON f.id = n.file_id
WHERE f.path = 'README.md'
  AND n.file_type = 'document'
  AND n.label NOT LIKE 'code:%'
ORDER BY n.source_location;
```

### Java-specific queries

```sql
-- Find all classes/interfaces and methods in a file
SELECT n.label, n.source_location
FROM enrich_graphify_nodes n
JOIN files f ON f.id = n.file_id
WHERE f.path LIKE '%BoltServer.java'
  AND n.source_location != ''
ORDER BY n.source_location;

-- Inheritance chain (extends edges)
SELECT e.source_node_id AS class, e.target_node_id AS superclass
FROM enrich_graphify_edges e
JOIN files f ON f.id = e.file_id
WHERE e.relation = 'extends' AND f.ext = '.java'
LIMIT 10;

-- Interface implementation relations
SELECT e.source_node_id AS class, e.target_node_id AS iface
FROM enrich_graphify_edges e
JOIN files f ON f.id = e.file_id
WHERE e.relation = 'implements' AND f.ext = '.java'
LIMIT 10;

-- Count classes by module (joined with enrich_java_modules)
SELECT m.artifact_id, COUNT(DISTINCT n.label) AS classes
FROM enrich_java_modules m
JOIN files f ON f.path LIKE (SUBSTR(m.rel_path, 1, LENGTH(m.rel_path)-7) || '%')
  AND f.ext='.java'
JOIN enrich_graphify_nodes n ON n.file_id = f.id
WHERE n.source_location != ''
  AND n.label NOT LIKE '.%'
  AND n.label NOT LIKE '%()'
  AND m.packaging = 'jar'
GROUP BY m.artifact_id
ORDER BY classes DESC
LIMIT 10;
```

## Performance (benchmarked)

| Project | Files | Languages | Nodes | Edges | Time |
|---------|-------|-----------|-------|-------|------|
| probe (Rust code search) | 395 .rs, 129 .md | Rust, Markdown | 12,115 | 20,606 | 1.3s |
| neo4j (graph database) | 7,962 .java | Java | 98,604 | 242,810 | 44.9s |

## Adding new languages

1. Import the graphify extractor function (e.g. `from graphify.extract import extract_rust`)
2. Add to `EXTRACTORS` dict in `enrich_graphify.py`: `".ext": extract_fn`
3. No other script changes needed — sibling enrich scripts untouched

## License

graphify extractors are MIT (Copyright 2026 Safi Shamsi). Full license in `~/graphify/LICENSE`.
