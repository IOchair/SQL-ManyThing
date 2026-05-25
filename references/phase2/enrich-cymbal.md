# Phase 2 — cymbal Symbol Enrich

## Purpose

Extract symbol declarations (functions, classes, structs, methods) using cymbal CLI. Best for bracket languages (Python, Go, JS/TS). Fallback for languages without build output.

## Script

`scripts/phase2/enrich_cymbal.py`

## Usage

```bash
# First run (index + outline)
python3 scripts/phase2/enrich_cymbal.py /path/to/project

# Re-run (skip index if already indexed — saves ~30s)
python3 scripts/phase2/enrich_cymbal.py /path/to/project --skip-index

# Custom batch size (for 200+ file repos)
python3 scripts/phase2/enrich_cymbal.py /path/to/project --batch 100
```

## Prerequisites

- `.srcidx/source.db` from Phase 1
- `cymbal` CLI installed and available in PATH
- Git: cymbal needs `.git` for index persistence (script auto-inits if missing)

## Install cymbal

Download the latest release from GitHub:

```bash
# Linux (x86_64)
curl -LO https://github.com/1broseidon/cymbal/releases/latest/download/cymbal_linux_x86_64.tar.gz
tar xzf cymbal_linux_x86_64.tar.gz
chmod +x cymbal
sudo mv cymbal /usr/local/bin/

# macOS (ARM64)
curl -LO https://github.com/1broseidon/cymbal/releases/latest/download/cymbal_darwin_arm64.tar.gz
tar xzf cymbal_darwin_arm64.tar.gz
chmod +x cymbal
sudo mv cymbal /usr/local/bin/

# Windows (x86_64) — run from PowerShell or Command Prompt, then use from WSL
# Download cymbal_windows_x86_64.zip, extract cymbal.exe, add to PATH
```

Or use a package manager if available.

## Binary Discovery

The enrich script searches for cymbal in this order:

1. `~/.local/bin/cymbal`
2. `~/.hermes/node/bin/cymbal`
3. Fallback to `cymbal` in PATH

WSL validation on a Windows-hosted repo (`/mnt/d/...`) showed that Linux `cymbal v0.13.1` can index DrvFs project paths when executed from WSL. Use the Linux binary for all WSL-side work.

## Output

Writes JSON symbol arrays into `file_enrich.symbols` column.

```
file_enrich (file_id→files, file_key, symbols JSON array)
```

Each symbol: `{name, kind (function|class|struct|...), start_line, ...}`

## Incremental

Skips files whose `size:mtime` key matches cached entry.

## Languages covered

Python, Go, JS/TS — bracket languages with clear structure.
Not suitable for: Rust (traits/impls), Markdown, non-code files.

## When NOT to use

- Projects with build output (Java .class, C# .dll, UHT headers) — use build-based enrich instead
- Non-bracket files (.md, .json, .yaml) — use graphify enrich
- Rust with complex trait/impl mapping — combine with graphify enrich

## Enrichment Strategy Decision Table

| Use case | Strategy | Script |
|---|---|---|
| Bracket languages (Python, Go, JS/TS) | cymbal outline — fast symbol names, kinds, line ranges | `enrich_cymbal.py` |
| Rust (traits, impls), Markdown, docs | graphify AST — call graphs, containment edges, heading trees | `enrich_graphify.py` |
| Java with built project (JDK available) | javap from .class — resolved generics, annotations, full signatures | `enrich_java_build.py` |
| Java without JDK | graphify fallback — structural edges (calls, inherits) from source AST | `enrich_graphify.py` |
| Unreal Engine (installed build) | UHT .generated.h — class hierarchy, UFUNCTION thunks, module info | `uht_enrich.py` |
| C#, Swift, other compiled langs | Phase 1 FTS5 only (no enrich) — use trigram search + bounded extraction | none |
