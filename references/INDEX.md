# References Index

References grouped by indexing phase or platform/domain.

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
│   ├── graphify-enrich.md              # deprecated compatibility note
│   ├── java-import-resolver.md         # Java target_file_id=NULL design rationale
│   ├── perf-optimization.md            # SQL round-trip elimination patterns
│   └── ue-uht-generated-files.md
├── phase3/
│   ├── phase3-design-rationale.md
│   ├── trace-preflight-debugging.md
│   └── importer-parsing.md
├── platforms/
│   └── wsl-windows-phase123-smoke.md
- query/
│   ├── library-analysis-js-ts.md       # JS/TS library discovery pattern
│   ├── ue-gas-attribute-analysis.md    # UE GAS AttributeSet BP init diagnosis
│   └── ue-substrate-toon-trace.md      # UE Substrate toon shader 3-file trace
├── design/
│   └── sql-is-many-things.md           # Design rationale: A*, SQLite, bounded extraction
├── phase2-design.md                    # Full-scan design rationale, dirty.db pattern
├── contribution-review.md              # PR review checklist
├── third-party-attribution.md          # Open-source audit record
├── public-examples.md                  # Public example DBs
├── db-maintenance.md                   # DB maintenance guide
├── agent-query-loop-lessons.md         # Agent query-loop dogfooding
├── old-format-cleanup.md               # Pre-v5.4.0 table remnant cleanup
└── unreal/
    ├── installed-build-indexing.md
    ├── unreal-installed-indexing-profiles.md
    ├── ue5-installed-engine.gitignore
    ├── ue58-full-phase123-run.md
    └── phase2-overload-test.md
```

## Organization Rules

- Phase references document build-time indexing and enrichment stages.
- Universal Phase 2 coverage is in `SKILL.md` (Operators 2-3) and `scripts/INDEX.md` — no separate reference docs needed for the four universal enrich scripts.
- Platform references document environment-specific validation and pitfalls.
- Unreal references document installed-build indexing policy, UHT enrichment, and full-run results.
- Query references document query-time domain analysis patterns.
- Scripts live under `scripts/phaseN/` or `scripts/verify/`; do not leave executable helpers at `scripts/` root.
- Deprecated notes may stay when they preserve migration context, but canonical docs should point to the replacement.
