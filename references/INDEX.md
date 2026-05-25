# References Index

References are grouped by indexing phase or platform/domain specialization.

```text
references/
├── INDEX.md
├── phase1/
│   ├── phase1-setup.md
│   ├── phase1-rebuild-add-tsx.md
│   └── gitignore-enumeration.md
├── phase2/
│   ├── enrich-cymbal.md
│   ├── enrich-graphify.md
│   ├── enrich-java-build.md
│   ├── enrich-covercheck-workflow.md
│   ├── debug-cymbal-outline-empty.md
│   ├── graphify-enrich.md          # deprecated compatibility note
│   └── ue-uht-generated-files.md
├── phase3/
│   ├── phase3-design-rationale.md
│   ├── trace-preflight-debugging.md
│   └── importer-parsing.md
├── platforms/
│   └── wsl-windows-phase123-smoke.md
├── query/
│   ├── library-analysis-js-ts.md          # JS/TS library discovery pattern
│   └── ue-gas-attribute-analysis.md       # UE GAS AttributeSet BP init diagnosis
├── design/
│   └── sql-is-many-things.md             # Design rationale: A*, SQLite, bounded extraction
├── third-party-attribution.md           # Open-source audit record
└── unreal/
    ├── installed-build-indexing.md
    ├── unreal-installed-indexing-profiles.md
    ├── ue5-installed-engine.gitignore
    └── ue58-full-phase123-run.md
```

## Organization Rules

- Phase references document build-time indexing and enrichment stages.
- Platform references document environment-specific validation and pitfalls.
- Unreal references document installed-build indexing policy, UHT enrichment, and full-run results.
- Query references document query-time domain analysis patterns (JS/TS libraries, UE GAS, etc.).
- Scripts live under `scripts/phaseN/` or `scripts/verify/`; do not leave executable helpers at `scripts/` root unless they are an index file.
- Deprecated notes may stay when they preserve migration context, but canonical docs should point to the replacement.
