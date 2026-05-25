# Third-Party Notices

SQL-ManyThing uses or references the following third-party software.
This file lists all dependencies and their licenses.

---

## SQLite / FTS5

**License:** Public Domain
**Source:** https://sqlite.org/

SQLite is the core substrate of SQL-ManyThing. All indexed data lives in
SQLite databases with FTS5 trigram tokenization. No modifications are made
to SQLite itself.

---

## Cymbal (optional runtime dependency)

**License:** MIT License
**Copyright:** Copyright (c) 2026 George Dikeakos
**Source:** https://github.com/1broseidon/cymbal

Cymbal is an optional Phase 2 enrichment tool for symbol extraction.
Users install cymbal independently via GitHub releases or package manager.
SQL-ManyThing does not redistribute cymbal binaries.

```
MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Graphify (optional runtime dependency)

**License:** MIT License
**Copyright:** Copyright (c) 2026 Safi Shamsi
**Source:** https://github.com/safishamsi/graphify

Graphify is an optional Phase 2 enrichment tool for AST-based graph extraction.
Users install graphify independently. SQL-ManyThing's `enrich_graphify.py`
script imports it at runtime if available; a built-in fallback (original work)
provides basic functionality when graphify is absent.

---

## Tree-sitter (optional transitive dependency)

**License:** MIT License
**Source:** https://tree-sitter.github.io/

Tree-sitter parsers are used by graphify for AST extraction. Installed via pip:
`tree-sitter`, `tree-sitter-rust`, `tree-sitter-python`, `tree-sitter-javascript`,
`tree-sitter-typescript`, `tree-sitter-java`, `tree-sitter-c`, `tree-sitter-bash`,
`tree-sitter-json`. Not vendored.

---

## UnrealEngine.gitignore (reference file)

**License:** CC0 1.0 Universal
**Source:** https://github.com/github/gitignore/blob/main/UnrealEngine.gitignore

The file `references/unreal/ue5-installed-engine.gitignore` is a verbatim copy
of the UnrealEngine.gitignore from the github/gitignore project. It is provided
as a convenience for users who want to index an installed Unreal Engine tree.

---

## Python Standard Library

SQL-ManyThing scripts use only Python stdlib modules: `sqlite3`, `os`, `sys`,
`json`, `re`, `argparse`, `fnmatch`, `subprocess`, `time`, `pathlib`. No
third-party Python packages are required for Phase 1 or Phase 3.
