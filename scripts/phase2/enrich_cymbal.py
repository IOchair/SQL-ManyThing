"""SQL-ManyThing — Phase 2: cymbal symbol enrich.
Usage: python3 enrich_cymbal.py /path/to/target [--batch 50] [--skip-index]

Requires: .srcidx/source.db from Phase 1, cymbal CLI installed.
Enriches each file with its cymbal outline symbols (function/class/struct names, kinds, line numbers).

Incremental: skips files whose size+mtime match cached key.
"""

import sqlite3
import os
import subprocess
import json
import time
import sys
import argparse

# macOS adaptation: auto-detect cymbal in both locations
CYMBAL = None
for _c in [
    os.path.expanduser("~/.local/bin/cymbal"),
    os.path.expanduser("~/.hermes/node/bin/cymbal"),
]:
    if os.path.isfile(_c) and os.access(_c, os.X_OK):
        CYMBAL = _c
        break
if CYMBAL is None:
    CYMBAL = "cymbal"  # fallback to PATH

SKIP_DIRS = {".git", "node_modules", "dist", ".venv", "venv", "__pycache__"}


def ensure_git(target: str):
    """Init git if missing — cymbal requires it for index persistence."""
    git_dir = os.path.join(target, ".git")
    if not os.path.isdir(git_dir):
        print("  no .git — initializing")
        subprocess.run(["git", "init", "-q"], cwd=target, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "manything@local"],
            cwd=target, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "manything"],
            cwd=target, capture_output=True,
        )


def enrich_cymbal(target: str, db: str, batch_size: int, skip_index: bool = False) -> int:
    """Phase 2: cymbal index + outline symbol enrich."""
    conn = sqlite3.connect(db)
    c = conn.cursor()

    # Ensure git for cymbal persistence
    ensure_git(target)

    if not skip_index:
        index_dirs = [target] + sorted(
            os.path.join(target, d) for d in os.listdir(target)
            if os.path.isdir(os.path.join(target, d)) and d not in SKIP_DIRS
        )
        for d in index_dirs:
            subprocess.run(
                [CYMBAL, "index", d, "--include-generated"],
                capture_output=True, timeout=60, cwd=target,
            )

    # Find pending files
    c.execute("SELECT id, path, size, mtime FROM files")
    pending = []
    for fid, path, size, mtime in c.fetchall():
        key = f"{size}:{mtime}"
        c.execute(
            "SELECT 1 FROM file_enrich WHERE file_id = ? AND file_key = ?",
            (fid, key),
        )
        if c.fetchone() is None:
            pending.append((fid, path, key))

    if not pending:
        print("  all files up-to-date")
        conn.close()
        return 0

    print(f"  pending: {len(pending)} files")

    inserted = 0
    for i in range(0, len(pending), batch_size):
        batch = pending[i : i + batch_size]
        paths = [os.path.join(target, p) for _, p, _ in batch]

        t0 = time.time()
        proc = subprocess.run(
            [CYMBAL, "outline", "--json"] + paths,
            capture_output=True, text=True, timeout=120, cwd=target,
        )
        if proc.returncode != 0:
            print(f"  batch {i//batch_size} error: {proc.stderr[:200]}")
            continue

        data = json.loads(proc.stdout)
        raw = data.get("results", [])

        # Build lookup: abs_path → symbols
        syms_by_abspath: dict[str, list] = {}
        if isinstance(raw, dict):
            for key, symlist in raw.items():
                if not symlist:
                    continue
                if key.startswith("/"):
                    abspath = os.path.realpath(key)
                else:
                    rel = key.lstrip("./")
                    abspath = os.path.realpath(os.path.join(target, rel))
                syms_by_abspath[abspath] = symlist
        elif isinstance(raw, list):
            for item in raw:
                f = item.get("file", "")
                syms_by_abspath.setdefault(f, []).append(item)

        batch_ok = 0
        for fid, path, key in batch:
            abspath = os.path.realpath(os.path.join(target, path))
            syms = syms_by_abspath.get(abspath)
            if syms is None:
                continue
            c.execute(
                "INSERT OR REPLACE INTO file_enrich (file_id, file_key, symbols) VALUES (?, ?, ?)",
                (fid, key, json.dumps(syms)),
            )
            batch_ok += 1
        conn.commit()
        inserted += batch_ok
        print(f"  batch {i//batch_size}: {batch_ok}/{len(batch)} in {time.time()-t0:.1f}s")

    conn.close()
    return inserted


def main():
    parser = argparse.ArgumentParser(description="SQL-ManyThing Phase 2: cymbal symbol enrich")
    parser.add_argument("target", help="Project root path (must have .srcidx/source.db)")
    parser.add_argument("--batch", type=int, default=50, help="Outline batch size (default: 50)")
    parser.add_argument("--skip-index", action="store_true",
                        help="Skip cymbal index step when repo already indexed")
    args = parser.parse_args()

    target = os.path.realpath(args.target)
    db = os.path.join(target, ".srcidx", "source.db")
    if not os.path.isdir(target):
        print(f"Error: {target} not found")
        sys.exit(1)
    if not os.path.isfile(db):
        print(f"Error: DB not found ({db}). Run Phase 1 (manything_build_db.py) first.")
        sys.exit(1)

    print(f"SQL-ManyThing Phase 2 — cymbal symbol enrich")
    print(f"Target: {target}")
    print(f"Cymbal: {CYMBAL}")
    t0 = time.time()
    enriched = enrich_cymbal(target, db, args.batch, args.skip_index)
    elapsed = time.time() - t0
    print(f"Enriched: {enriched} files in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
