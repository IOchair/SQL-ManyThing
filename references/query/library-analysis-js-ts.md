# JS/TS Library Analysis via SQL-ManyThing

Pattern for exploring JavaScript/TypeScript library projects using SQL-ManyThing operators. Demonstrated on `@chenglou/pretext` v0.0.5 (text measurement & layout library).

## Discovery Sequence

### Step 1 — Entry point discovery (package.json)

Before probing source files, extract the library's public API shape from its metadata:

```sql
SELECT substr(content, 1, 2000) FROM files WHERE path = 'package.json';
```

Target fields: `main`, `exports`, `types`, `files`. Exports dict reveals subpath entry points:

```
@chenglou/pretext          → ./dist/layout.js
@chenglou/pretext/rich-inline → ./dist/rich-inline.js
@chenglou/pretext/demos/*  → ./pages/demos/*
```

### Step 2 — Module inventory (files table)

Map all source modules:

```sql
SELECT path FROM files WHERE path LIKE 'src/%' ORDER BY path;
```

This reveals the module graph — core modules vs tests vs generated code vs type declarations.

### Step 3 — Symbol enumeration per module (symbol enrichment)

List every exported/internal symbol in each core module:

```sql
SELECT json_extract(s.value, '$.name') AS name,
       json_extract(s.value, '$.kind') AS kind,
       json_extract(s.value, '$.start_line') AS start_line
FROM file_enrich e
JOIN files f ON f.id = e.file_id,
     json_each(e.symbols) AS s
WHERE f.path = 'src/layout.ts'
ORDER BY start_line;
```

Repeat for each key module. This gives:
- Public API surface (exported functions/types)
- Internal helper functions
- Module boundaries and responsibility splits

### Step 4 — Doc-header extraction (bounded)

Extract only the file header comment for purpose and design notes:

```sql
SELECT substr(content, 1, 2000) FROM files WHERE path = 'src/layout.ts';
```

JS/TS libraries often embed architecture notes, problem statements, and limitations in a block comment at the top of the main entry file.

### Step 5 — Deep field probe via instr anchor

For specific function signatures not captured by symbol enrichment (e.g. complex type defs):

```sql
SELECT instr(content, 'export function prepare') AS offset FROM files WHERE path = 'src/layout.ts';
```

Then extract bounded window around the anchor.

## Layer Mapping for Library Analysis

| Layer | Evidence source | Query operator |
|---|---|---|
| Public API surface | package.json exports | FTS5 on path='package.json' |
| Core algorithm | Main module header comment | Bounded substr (1, 2000) |
| Module split | src/ file list | files table path LIKE 'src/%' |
| Function inventory per file | Symbol enrichment | json_each file_enrich.symbols |
| Type definitions | Symbol enrichment (kind='type','interface') | json_each filter by kind |
| Internal call chains | Graph enrichment | enrich_graphify_edges (when available) |
| Use cases / demos | pages/demos/ file list | files table path LIKE 'pages/demos/%' |

## Concrete Example: Pretext

The Pretext session demonstrated this sequence:

1. **Entry points**: main=`./dist/layout.js`, subpath `./rich-inline`, demos at `./pages/demos/*`
2. **Modules**: 11 src files: layout.ts, measurement.ts, analysis.ts, line-break.ts, line-text.ts, bidi.ts, rich-inline.ts, text-modules.d.ts, test-data.ts, layout.test.ts, generated/bidi-data.ts
3. **Symbols**: layout.ts exports 7 functions (prepare, layout, prepareWithSegments, layoutWithLines, measureNaturalWidth, clearCache, setLocale) + 11 type aliases. measurement.ts exports 4 functions + 3 types. analysis.ts exports 25+ segment/merge functions.
4. **Architecture header**: Two-phase design — prepare() segments + measures via canvas (one-time), layout() pure arithmetic on cached widths (~0.0002ms per call). Emoji correction, Intl.Segmenter for i18n, simplified bidi metadata.
5. **Accuracy methodology**: corpus sweeps across Chrome/Firefox/Safari, automated accuracy checks, benchmarks vs DOM baseline.

## Pitfalls

- **Generated files**: `src/generated/bidi-data.ts` is build output, not hand-written. Skip for algorithm analysis; the raw bidi type ranges live in `src/bidi.ts`.
- **Type-only files**: `src/text-modules.d.ts` is ambient declarations, no runtime exports.
- **Test files**: `src/layout.test.ts` and `src/test-data.ts` are excluded from the npm package (see package.json `files` field). Distinguish test from production code by checking the `files` field or the file path pattern.
- **Multiple entry points**: A library may expose both low-level (layout.ts) and convenience (rich-inline.ts) layers. The rich-inline module wraps layout.ts primitives — probe the low-level module first to understand the core, then the wrapper.
