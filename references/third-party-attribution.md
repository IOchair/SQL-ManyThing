# Third-Party Attribution Audit

Audit date: 2026-05-25
Scope: all external dependencies referenced, vendored, or archived in this skill tree.

## 1. Cymbal (archived binary)

- **Repo:** https://github.com/1broseidon/cymbal
- **License:** MIT — Copyright 2026 George Dikeakos
- **Usage:** symbol enrichment via `scripts/phase2/enrich_cymbal.py` (external CLI)
- **Archive:** `assets/bin/cymbal_v0.13.1/`
  - `cymbal_v0.13.1_linux_x86_64.tar.gz` — binary only, **no LICENSE file**
  - `cymbal_v0.13.1_windows_x86_64.zip` — binary only, **no LICENSE file**
  - `linux/cymbal` — extracted binary, **no LICENSE file**
- **Issue:** MIT requires including license text with distribution. Archived binaries lack it.
- **Resolution (2026-05-25):** Binaries excluded via `.gitignore`; users install from GitHub releases.
  - `.gitignore` blocks `*.zip`, `*.tar.gz`, `linux/cymbal` under `assets/bin/cymbal_v0.13.1/`
  - `references/phase2/enrich-cymbal.md` updated with install instructions
  - Existing committed binaries remain in git history but are no longer tracked for future commits
  - `THIRD_PARTY_NOTICES.md` includes full MIT license text

## 2. Graphify (runtime import, not vendored)

- **Repo:** https://github.com/safishamsi/graphify (branch `v8`)
- **License:** MIT — Copyright 2026 Safi Shamsi
- **Usage:** `import` from `~/graphify` at runtime in `scripts/phase2/enrich_graphify.py`
- **Status:** Not committed to repo. Script has original fallback (hand-written regex) when graphify absent. `references/phase2/enrich-graphify.md` already notes the MIT license.
- **Action:** none needed.

## 3. UnrealEngine.gitignore (reference copy)

- **Source:** https://github.com/github/gitignore/blob/main/UnrealEngine.gitignore
- **License:** CC0 1.0 Universal (public domain)
- **Location:** `references/unreal/ue5-installed-engine.gitignore`
- **Status:** verbatim copy — diff against upstream is empty
- **Action:** add source URL comment to file header as best practice. CC0 requires no attribution but documenting provenance helps maintainers.

## 4. SQLite / FTS5 (core runtime)

- **Source:** https://sqlite.org/
- **License:** Public domain
- **Usage:** `sqlite3` module + FTS5 trigram tokenizer — entire project builds on this
- **Action:** mention in third-party notices as courtesy; no license restriction.

## 5. Tree-sitter Python packages (optional runtime dep)

- **Source:** https://tree-sitter.github.io/
- **License:** MIT
- **Usage:** `pip install tree-sitter tree-sitter-rust tree-sitter-python tree-sitter-javascript tree-sitter-typescript tree-sitter-java tree-sitter-c tree-sitter-bash tree-sitter-json` — required for graphify enrich
- **Action:** mention in third-party notices.

## Summary: TODO P0 item status

| Sub-item | Status |
|----------|--------|
| SQLite/FTS5 attribution | ✅ THIRD_PARTY_NOTICES.md includes full entry |
| cymbal binary license compliance | ✅ Resolved — .gitignore blocks commits, install docs point upstream, MIT text in THIRD_PARTY_NOTICES.md |
| graphify attribution | ✅ Done in enrich-graphify.md + THIRD_PARTY_NOTICES.md |
| Unreal references disclaimer | ✅ Source URL + CC0 noted in ue5-installed-engine.gitignore header, THIRD_PARTY_NOTICES.md |
| cymbal binary commit policy | ✅ Resolved — not committed; install via GitHub releases |
| THIRD_PARTY_NOTICES.md | ✅ Created at skill root |
