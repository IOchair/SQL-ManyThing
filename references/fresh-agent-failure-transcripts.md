# Fresh-Agent Failure Transcripts (Evidence for v5.4.0 Restructure)

Two sessions where an agent loaded the old sql-manything SKILL.md (v5.3.1)
and followed its top-down reading order — SQL templates first, Frame later.
Both failed in predictable, document-structure-driven ways.

## Transcript A: 43-Query Substrate Toon Overview (No Frame)

User asked for "UE58 Substrate Toon 实现概况". Agent loaded sql-manything,
read the document top-down, hit the SQL templates at L54, and started writing
DISCOVER queries — **without writing an Abstraction Frame.** The Frame section
was at L188, after 134 lines of SQL.

### Failure chain

```
L54:  Four Canonical SQL Templates        ← agent starts here
L58:  1. DISCOVER — "I know how to query!"
      → writes DISCOVER: MATCH 'substrate toon BSDF'
      → writes DISCOVER: MATCH 'SubstrateToon'
      ... 43 queries later, no Frame ever written
L188: Abstraction Frame (Mandatory)       ← never reached / skipped
L481: Common Violations #1: "Skipping the frame" ← at the bottom
```

### Consequences

| Metric | Value |
|---|---|
| Total queries | 43 |
| Layers implied | ~4 (shader, eval, C++, ToonProfile) |
| Layers with clear boundaries | 0 (no Frame = no layer declaration) |
| Budget annotations | All present (g=1..43) — budget format was followed, Frame was not |
| Frame written | No |
| Pre-flight schema check | No (was at L439) |
| TRACE_DEPS used as search accelerator | Only g=3-4 (L1), skipped for L3 despite 2+ candidates |
| substr(block_content_full, 1, N) truncation | g=39,42,43 — hard truncation instead of trusting 6000-char budget |
| Skip PROBE → EXTRACT_BLOCK | g=28,31 |
| Effective queries | ~33/43 (77%) — ~10 queries were wasted |

### Root cause

Document trained agent to write SQL before writing Frame. By the time agent
reached the Frame section, cognitive momentum said "I already know how to
query, skip this."

---

## Transcript B: Trace Session (No Frame, Deps Misused)

User asked for "trace" of Substrate Toon call chain. Agent started with
`SELECT '--- step ---'` labels instead of Frame, used deps as call-chain
tracer instead of search accelerator.

### Failure chain

```
T1: enrich_file_refs WHERE target_raw LIKE '%SubstrateToonBSDF%'
    → Agent used deps as "who uses this file" — trace direction, not search acceleration
    → User feedback: "没问链条才猛用dep，无语"
Step 1a: C++ MaterialExpressionSubstrate.cpp  ← jump to C++
Step 1b: back to refs (callers of SubstrateGenerateMaterialTopologyTree)
Step 2a: SubstrateEvaluation.ush              ← jump to shader dispatch
Step 2b: SubstrateEvaluation.ush depth=3
Step 3:  SubstrateToonBSDF.ush               ← jump to BSDF impl
Step 3b: back to SubstrateToonBSDF.ush offset=4281 container lookup
Step 3c: SubstrateToonBSDF.ush body
Step 4a-e: ToonProfileCommon.ush             ← jump to profile
Step 5a-b: SubstrateToonBSDF.ush             ← jump BACK to BSDF packing
Step 6: SubstrateEvaluation.ush              ← jump BACK to dispatch
```

6 direction changes in one session. No Frame = no call-chain direction declared.

### Consequences

| Metric | Value |
|---|---|
| Total queries | ~23 |
| Budget annotations | Only T1 had `[budget]`, g=2..23 all missing |
| Frame written | No |
| Function-name guess failures | 4 (EvaluateToonProfileDiffuseRamp ×2, EvaluateToonProfileRamp ×2) |
| SELECT '--- label ---' as decoration | ~12 queries — not a valid SQL template |
| substr(block_content_full, 1, N) truncation | Step 6 (500 char) |

### User feedback (verbatim)

> "没问链条才猛用dep，无语"

Translation: agent used deps (TRACE_DEPS) even though user didn't ask about
call chains — and when user DID ask about call chains (trace), agent used
deps as a tracing tool instead of a search accelerator.

---

## What v5.4.0 Fixes

| Old structure (v5.3.1) | New structure (v5.4.0) | Prevents |
|---|---|---|
| SQL templates L54, Frame L188 | Frame §3 before SQL templates §4 | Transcript A: Frame skip |
| Pre-flight L439 | Pre-flight §1 | Transcript A+B: no schema check |
| TRACE_DEPS in "Templates" §2 + "Dep Tracing" §6 (duplicated) | §4.2 as search accelerator, §6 as deep reference | Transcript B: deps-as-tracer confusion |
| Depth by Language L376 | §4.3 inline with EXTRACT | Both: wrong depth level |
| Common Violations L481 | Inline at decision points + §8 checklist | Both: violations discovered too late |
| No Quick Start | §2 minimal path (Frame + 3 queries) | Both: no "first query" model |
