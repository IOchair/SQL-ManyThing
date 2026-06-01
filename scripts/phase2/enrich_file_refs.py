#!/usr/bin/env python3
"""SQL-ManyThing — Phase 2a: File-level reference extraction (import/require/include).

Scans each file's content for import-like statements.
Stores raw import strings + resolved target_file_id (when mappable to a project file).

Dependency flattening (upstream/downstream tree): see flatten_file_deps.py (Phase 2b).

Usage:
  python3 enrich_file_refs.py /path/to/target [--batch 50]

Language patterns (add as needed):
  Python:  import X, from X import Y, from . import X
  JS/TS:   import X from 'Y', require('Y'), import 'Y'
  Java:    import com.foo.Bar;
  Go:      import "pkg", import ("pkg1"; "pkg2")
  Rust:    use crate::foo, use std::collections
  C/C++:   #include "file.h", #include <file.h>
  Scala:   import com.foo.bar
"""

import sqlite3, os, sys, argparse, re, time

REFS_TABLE = "enrich_file_refs"
TRACKER_TABLE = "enrich_refs_tracker"

# ── language patterns ─────────────────────────────────────────────────

# Each entry: (re_pattern, ext_filter, resolver_func)
# pattern captures the raw import target string (group 1)

# Python
RE_PY_IMPORT = re.compile(
    r'(?:from\s+(\S+)\s+import|\bimport\s+(\S+))'
)

# JS/TS
RE_JS_REQUIRE = re.compile(r"(?:require|require\.resolve)\s*\(\s*['\"](\S+?)['\"]")
RE_JS_IMPORT = re.compile(
    r"(?:import\s+(?:\{[^}]*\}|\*\s+as\s+\S+|\S+)\s+from\s+|export\s+\{[^}]*\}\s+from\s+)['\"](\S+?)['\"]"
)
RE_JS_IMPORT_BARE = re.compile(r"import\s+['\"](\S+?)['\"]")

# Java
RE_JAVA_IMPORT = re.compile(r'^import\s+(?:static\s+)?(\S+)\s*;', re.MULTILINE)

# Go
RE_GO_IMPORT_SINGLE = re.compile(r'^import\s+[ "](\S+)[ "]$', re.MULTILINE)
RE_GO_IMPORT_MULTI = re.compile(r'^\s+[ "](\S+?)[ "]\s*$', re.MULTILINE)

# Rust
RE_RS_USE = re.compile(r'^use\s+(\S+?)(?:\s+as\s+\S+)?\s*;', re.MULTILINE)

# C/C++
RE_C_INCLUDE = re.compile(r'#include\s+[<"](.+?)[>"]')

# Scala
RE_SCALA_IMPORT = re.compile(r'^import\s+(?:{.*?}|(\S+))\s*$', re.MULTILINE)


LANG_PATTERNS = {
    '.py':   [RE_PY_IMPORT],
    '.js':   [RE_JS_IMPORT, RE_JS_REQUIRE, RE_JS_IMPORT_BARE],
    '.jsx':  [RE_JS_IMPORT, RE_JS_REQUIRE, RE_JS_IMPORT_BARE],
    '.mjs':  [RE_JS_IMPORT, RE_JS_REQUIRE, RE_JS_IMPORT_BARE],
    '.cjs':  [RE_JS_IMPORT, RE_JS_REQUIRE, RE_JS_IMPORT_BARE],
    '.ts':   [RE_JS_IMPORT, RE_JS_REQUIRE, RE_JS_IMPORT_BARE],
    '.tsx':  [RE_JS_IMPORT, RE_JS_REQUIRE, RE_JS_IMPORT_BARE],
    '.mts':  [RE_JS_IMPORT, RE_JS_REQUIRE, RE_JS_IMPORT_BARE],
    '.cts':  [RE_JS_IMPORT, RE_JS_REQUIRE, RE_JS_IMPORT_BARE],
    '.java': [RE_JAVA_IMPORT],
    '.go':   [RE_GO_IMPORT_SINGLE, RE_GO_IMPORT_MULTI],
    '.rs':   [RE_RS_USE],
    '.c':    [RE_C_INCLUDE],
    '.cc':   [RE_C_INCLUDE],
    '.cpp':  [RE_C_INCLUDE],
    '.cxx':  [RE_C_INCLUDE],
    '.h':    [RE_C_INCLUDE],
    '.hpp':  [RE_C_INCLUDE],
    '.hh':   [RE_C_INCLUDE],
    '.scala': [RE_SCALA_IMPORT],
    '.kt':   [RE_JAVA_IMPORT],  # Kotlin uses Java-style imports
    '.kts':  [RE_JAVA_IMPORT],
    '.usf':  [RE_C_INCLUDE],   # UE shader files use #include
    '.ush':  [RE_C_INCLUDE],   # UE shader headers use #include
    '.hlsl': [RE_C_INCLUDE],   # HLSL uses #include
}


# ── import resolution ─────────────────────────────────────────────────

def resolve_import_paths(target_raw: str, file_dir: str,
                         project_root: str, file_ext: str,
                         known_paths: set[str]) -> list[str]:
    """Return candidate project-relative paths for an import string.

    Returns empty list if unresolvable (external lib, stdlib, etc.).
    """
    candidates: list[str] = []

    # ── handle relative imports ───────────────────────────────────────
    # Python: from . import X, from .. import X, from .module import X
    # JS/TS:  import { X } from './foo', require('../bar')
    if target_raw.startswith('.'):
        parts = file_dir.strip('/').split('/') if file_dir else []
        rel = target_raw
        while rel.startswith('..'):
            if parts:
                parts.pop()
            rel = rel[3:] if rel.startswith('../') else rel[2:]
        rel = rel.lstrip('./')
        # relative path candidates
        base = '/'.join(parts) + '/' + rel if parts else rel
        for p in _file_candidates(base, file_ext):
            candidates.append(p)
    elif '/' in target_raw:
        # has slash — likely a path-style import
        # Python: import os.path → os/path.py or os/path/__init__.py
        # JS:     import { X } from 'lodash/map' → external
        # C/C++:  #include "myheader.h" → myheader.h
        path = target_raw.replace('.', '/')
        for p in _file_candidates(path, file_ext):
            candidates.append(p)
    else:
        # bare name — could be Python/Go/Rust module
        # Python: import os → os.py or os/__init__.py (stdlib → skip)
        # Go:     import "fmt" → stdlib → skip
        # Try as project file first
        for p in _file_candidates(target_raw.replace('.', '/'), file_ext):
            if p in known_paths:
                candidates.append(p)
                break  # found in project, use it

    return candidates


def _file_candidates(base_path: str, file_ext: str) -> list[str]:
    """Generate candidate file paths for a base path.
    Strips any existing extension for remapping (e.g. import './foo.js' → foo.ts).
    """
    base = base_path.lstrip('/')
    name, _ext = os.path.splitext(base)
    candidates = []

    if file_ext == '.py':
        candidates.append(name + '.py')
        candidates.append(os.path.join(name, '__init__.py'))
    elif file_ext in ('.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.mts', '.cts'):
        for ext in ('.tsx', '.ts', '.jsx', '.js', '.mjs', '.cjs'):
            candidates.append(name + ext)
        for ext in ('/index.tsx', '/index.ts', '/index.jsx', '/index.js',
                     '/index.mjs', '/index.cjs'):
            candidates.append(name + ext)
    elif file_ext in ('.h', '.hpp', '.hh', '.hxx'):
        candidates.append(name)
        candidates.append(name + '.hpp')
        candidates.append(name + '.h')
    elif file_ext in ('.c', '.cc', '.cpp', '.cxx'):
        candidates.append(name)
        candidates.append(name + '.hpp')
        candidates.append(name + '.h')
        candidates.append(name + '.c')
    else:
        candidates.append(name)
        candidates.append(name + file_ext)

    return candidates


def _skip_external(target_raw: str, file_ext: str) -> bool:
    """Heuristic: skip known external / stdlib imports."""
    if target_raw.startswith('.'):
        return False  # relative → project internal
    if file_ext == '.py':
        # Python stdlib modules (non-exhaustive, just common noise)
        stdlib = {'os', 'sys', 're', 'json', 'math', 'time', 'datetime',
                  'typing', 'collections', 'pathlib', 'functools', 'itertools',
                  'subprocess', 'tempfile', 'shutil', 'hashlib', 'random',
                  'uuid', 'inspect', 'logging', 'warnings', 'io', 'abc',
                  'enum', 'dataclasses', 'types', 'textwrap', 'string',
                  'argparse', 'configparser', 'copy', 'pprint'}
        if target_raw.split('.')[0] in stdlib:
            return True
    if file_ext in ('.go',):
        # Go stdlib is typically single-word
        if '/' not in target_raw and not target_raw.startswith('.'):
            return True
    if file_ext in ('.rs',):
        # Rust stdlib
        if target_raw.startswith('std::') or target_raw.startswith('core::'):
            return True
    if file_ext in ('.java', '.kt', '.kts', '.scala'):
        # Java stdlib
        if target_raw.startswith(('java.', 'javax.', 'java.util.',
                                  'java.io.', 'java.lang.', 'java.nio.',
                                  'java.net.', 'java.security.')):
            return True
    return False


def extract_refs(content: str, ext: str, file_dir: str, project_root: str,
                 known_paths: set[str]) -> list[tuple[str, int | None, int]]:
    """Return list of (target_raw, target_file_id_or_None, line_num)."""
    patterns = LANG_PATTERNS.get(ext, [])
    if not patterns:
        return []

    refs: list[tuple[str, int | None, int]] = []
    for pat in patterns:
        for m in pat.finditer(content):
            raw = (m.group(1) or m.group(2) or '').strip()
            if not raw:
                continue
            # count lines from start to match position
            line_num = content[:m.start()].count('\n') + 1

            # try to resolve
            target_id = None
            if not _skip_external(raw, ext):
                candidates = resolve_import_paths(raw, file_dir, project_root, ext, known_paths)
                # For now, just store candidate path; we resolve file_id in batch
                # We need known_paths set which is built from files table
                # So resolution is done later in batch
                refs.append((raw, None, line_num))
            else:
                refs.append((raw, None, line_num))

    return refs


# ── enrichment driver ────────────────────────────────────────────────

def ensure_schema(conn: sqlite3.Connection):
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS {REFS_TABLE} (
            file_id      INTEGER NOT NULL,
            target_raw   TEXT NOT NULL,
            target_file_id INTEGER REFERENCES files(id),
            ref_type     TEXT NOT NULL DEFAULT '',
            line_num     INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_{REFS_TABLE}_file
            ON {REFS_TABLE}(file_id);
        CREATE INDEX IF NOT EXISTS idx_{REFS_TABLE}_target
            ON {REFS_TABLE}(target_file_id);
        CREATE TABLE IF NOT EXISTS {TRACKER_TABLE} (
            file_id     INTEGER PRIMARY KEY REFERENCES files(id),
            file_key    TEXT NOT NULL,
            enriched_at TEXT DEFAULT (datetime('now'))
        );
    """)


def resolve_targets(conn: sqlite3.Connection, known_paths: set[str]):
    """Phase 2: resolve target_raw → target_file_id using known_paths.

    Called after all raw refs are inserted. Batch-resolves all NULL
    target_file_id refs in a single pass.
    """
    c = conn.cursor()
    c.execute(f"SELECT rowid, file_id, target_raw FROM {REFS_TABLE} WHERE target_file_id IS NULL")
    pending = c.fetchall()
    if not pending:
        return

    # Build file_id → (dir, ext) and path→file_id in single pass
    c.execute("SELECT id, path, ext FROM files")
    file_info: dict[int, tuple[str, str]] = {}  # id → (dir, ext)
    path_to_id: dict[str, int] = {}
    for fid, path, ext in c.fetchall():
        file_info[fid] = (os.path.dirname(path), ext)
        path_to_id[path] = fid

    # Batch resolve: collect updates, apply in one go
    updates: list[tuple[int, int]] = []  # (target_file_id, rowid)
    resolved = 0
    for rowid, fid, raw in pending:
        info = file_info.get(fid)
        if not info:
            continue
        file_dir, ext = info

        candidates = resolve_import_paths(raw, file_dir, '', ext, known_paths)
        for cand in candidates:
            tid = path_to_id.get(cand)
            if tid is not None:
                updates.append((tid, rowid))
                resolved += 1
                break

    if updates:
        c.executemany(
            f"UPDATE {REFS_TABLE} SET target_file_id=? WHERE rowid=?",
            updates,
        )
    conn.commit()
    if resolved:
        print(f"  resolved {resolved} refs to project files")


def enrich_refs(target: str, db: str, batch_size: int) -> int:
    """Main enrich loop."""
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    ensure_schema(conn)
    c = conn.cursor()

    # Build known paths set + file_ext lookup
    c.execute("SELECT id, path, ext, size, mtime FROM files")
    all_files = c.fetchall()
    known_paths: set[str] = set()
    file_info: dict[int, tuple[str, str, str]] = {}  # id → (path, ext, key)
    for fid, path, ext, size, mtime in all_files:
        known_paths.add(path)
        file_info[fid] = (path, ext, f"{size}:{mtime}")

    # Find pending files — batch LEFT JOIN
    c.execute(f"""
        SELECT f.id, f.path, f.ext
        FROM files f
        LEFT JOIN {TRACKER_TABLE} t ON t.file_id = f.id
            AND t.file_key = (f.size || ':' || f.mtime)
        WHERE t.file_id IS NULL
    """)
    pending: list[tuple[int, str, str]] = []
    for fid, path, ext in c.fetchall():
        pending.append((fid, path, file_info[fid][2]))

    if not pending:
        print("  all files up-to-date")
        conn.close()
        return 0

    print(f"  pending: {len(pending)} files")

    # Process in batches
    inserted = 0
    for batch_i in range(0, len(pending), batch_size):
        batch = pending[batch_i: batch_i + batch_size]
        t0 = time.time()

        # Delete old refs
        fids = [fid for fid, _, _ in batch]
        placeholders = ",".join("?" * len(fids))
        c.execute(f"DELETE FROM {REFS_TABLE} WHERE file_id IN ({placeholders})", fids)
        c.execute(f"DELETE FROM {TRACKER_TABLE} WHERE file_id IN ({placeholders})", fids)

        # Extract refs
        ref_rows: list[tuple[int, str, int | None, str, int]] = []
        for fid, path, key in batch:
            ext = file_info[fid][1]
            patterns = LANG_PATTERNS.get(ext, [])
            if not patterns:
                # mark as done even without patterns
                ref_rows.append((fid, '', None, ext, 0))
                continue

            c.execute("SELECT content FROM files WHERE id=?", (fid,))
            row = c.fetchone()
            if row is None or row[0] is None:
                continue
            content = row[0]
            file_dir = os.path.dirname(path)

            for pat in patterns:
                for m in pat.finditer(content):
                    raw = m.group(1) if m.lastindex and m.group(1) else ''
                    if not raw or not isinstance(raw, str):
                        continue
                    raw = raw.strip()
                    if not raw:
                        continue
                    line_num = content[:m.start()].count('\n') + 1
                    ref_rows.append((fid, raw, None, ext, line_num))

        # Bulk insert refs
        if ref_rows:
            c.executemany(
                f"INSERT INTO {REFS_TABLE} "
                f"(file_id, target_raw, target_file_id, ref_type, line_num) "
                f"VALUES (?, ?, ?, ?, ?)",
                ref_rows,
            )

        # Update tracker
        c.executemany(
            f"INSERT OR REPLACE INTO {TRACKER_TABLE} (file_id, file_key) VALUES (?, ?)",
            [(fid, key) for fid, _, key in batch],
        )

        conn.commit()
        inserted += len(batch)
        print(f"  batch {batch_i // batch_size}: {len(batch)} files, "
              f"{len(ref_rows)} refs in {time.time() - t0:.1f}s")

    # Phase 2: resolve targets
    print("  resolving target_file_id...")
    resolve_targets(conn, known_paths)

    conn.close()
    return inserted


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SQL-ManyThing Phase 2a: file-level reference extraction"
    )
    parser.add_argument("target", help="Project root path")
    parser.add_argument("--batch", type=int, default=50, help="Batch size (default: 50)")
    args = parser.parse_args()

    target = os.path.realpath(args.target)
    db = os.path.join(target, ".srcidx", "source.db")
    if not os.path.isdir(target):
        print(f"Error: {target} not found")
        sys.exit(1)
    if not os.path.isfile(db):
        print(f"Error: DB not found ({db})")
        sys.exit(1)

    print("SQL-ManyThing Phase 2a — file reference extraction")
    print(f"Target: {target}")
    print(f"Batch:  {args.batch}")
    t0 = time.time()
    enriched = enrich_refs(target, db, args.batch)
    elapsed = time.time() - t0
    print(f"Done:   {enriched} files in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
