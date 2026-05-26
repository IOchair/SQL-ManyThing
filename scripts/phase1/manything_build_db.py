"""SQL-ManyThing — Phase 1: FTS5 trigram content index.
Usage:
  # Classic mode (os.walk + SKIP_DIRS):
  python3 manything_build_db.py /path/to/target [--ext h,cpp,cs,py,ts,tsx,js,jsx,rs,md]

  # Git mode (git ls-files, respects .gitignore):
  python3 manything_build_db.py /path/to/target --git [--ext ...]

  # Force full rebuild (drops and recreates all tables):
  python3 manything_build_db.py /path/to/target --rebuild

Creates .srcidx/source.db with FTS5 trigram index of file contents.
Phase 1 only — no symbol enrich. Run Phase 2 scripts separately.

Incremental mode (default): compares content_hash (SHA-256) for each file
and only updates changed/new files, removes deleted files. First run or
--rebuild does a full build. Subsequent runs skip unchanged files.
"""

import sqlite3
import os
import time
import sys
import argparse
import fnmatch
import subprocess
import hashlib

DEFAULT_EXTS = {
    ".h", ".cpp", ".cs", ".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".java",
}
SKIP_DIRS = {".git", "node_modules", "dist", ".venv", "venv", "__pycache__"}

PROFILES = {
    "unreal-installed-core": {
        "exts": {".h", ".cpp", ".cs", ".usf", ".ush", ".hlsl", ".py", ".ini", ".uplugin"},
        "skip_globs": [
            "Source/ThirdParty/*",
            "Plugins/*/Source/ThirdParty/*",
            "Content/*",
            "Plugins/*/Content/*",
            "Platforms/*",
            "ScriptModules/*",
        ],
        "max_size": None,
    },
    "unreal-installed-full": {
        "exts": {".h", ".hpp", ".cpp", ".c", ".cc", ".cs", ".inl", ".ipp", ".usf", ".ush", ".hlsl", ".ini", ".json", ".uplugin", ".uproject", ".py"},
        "skip_globs": [],
        "max_size": None,
    },
}


def list_files_via_git(target: str) -> list[str] | None:
    """Use git ls-files to enumerate all source files respecting .gitignore.

    Returns list of relative paths, or None if target is not a git repo.
    """
    try:
        result = subprocess.run(
            ["git", "-C", target, "ls-files", "--cached", "--others",
             "--exclude-standard"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return None
        lines = result.stdout.strip().splitlines()
        return [ln for ln in lines if ln]  # drop empties
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def walk_files(target: str) -> list[str]:
    """Classic os.walk with SKIP_DIRS pruning. Returns list of relative paths."""
    files = []
    for root, dirs, fnames in os.walk(target):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in fnames:
            relpath = os.path.relpath(os.path.join(root, fname), target)
            files.append(relpath)
    return files


def _norm_rel(path: str) -> str:
    return path.replace(os.sep, "/").strip("/")


def load_gitignore_patterns(gitignore_file: str) -> list[tuple[str, bool]]:
    """Load the common .gitignore subset used for source indexing."""
    patterns: list[tuple[str, bool]] = []
    with open(gitignore_file, "r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if not line or line.lstrip().startswith("#"):
                continue
            negated = line.startswith("!")
            if negated:
                line = line[1:]
            line = line.strip()
            if not line:
                continue
            patterns.append((line.replace("\\", "/"), negated))
    return patterns


def gitignore_matches(relpath: str, patterns: list[tuple[str, bool]], is_dir: bool = False) -> bool:
    """Return True when relpath is ignored by loaded .gitignore patterns."""
    rel = _norm_rel(relpath)
    ignored = False
    for pat, negated in patterns:
        dir_only = pat.endswith("/")
        raw_pat = pat.strip("/")
        anchored = pat.startswith("/")
        matched = False

        if dir_only:
            base = raw_pat.rstrip("/")
            if anchored:
                matched = rel == base or rel.startswith(base + "/")
            else:
                parts = rel.split("/")
                matched = base in parts or rel.startswith(base + "/")
        elif anchored:
            matched = fnmatch.fnmatchcase(rel, raw_pat)
        elif "/" in raw_pat:
            matched = fnmatch.fnmatchcase(rel, raw_pat) or fnmatch.fnmatchcase(rel, "*/" + raw_pat)
        else:
            matched = any(fnmatch.fnmatchcase(part, raw_pat) for part in rel.split("/"))

        if matched:
            ignored = not negated
    return ignored


def walk_files_with_gitignore(target: str, gitignore_file: str) -> list[str]:
    """os.walk filtered only by a supplied .gitignore file."""
    patterns = load_gitignore_patterns(gitignore_file)
    files = []
    for root, dirs, fnames in os.walk(target):
        rel_root = os.path.relpath(root, target)
        if rel_root == ".":
            rel_root = ""
        kept_dirs = []
        for d in dirs:
            rel_dir = _norm_rel(os.path.join(rel_root, d))
            if not gitignore_matches(rel_dir, patterns, is_dir=True):
                kept_dirs.append(d)
        dirs[:] = kept_dirs
        for fname in fnames:
            relpath = _norm_rel(os.path.join(rel_root, fname))
            if gitignore_matches(relpath, patterns, is_dir=False):
                continue
            files.append(relpath)
    return files


def profile_accepts(relpath: str, profile: str | None) -> bool:
    if not profile:
        return True
    cfg = PROFILES.get(profile)
    if not cfg:
        return True
    rel = _norm_rel(relpath)
    for pat in cfg.get("skip_globs", []):
        if fnmatch.fnmatchcase(rel, pat):
            return False
    return True


def apply_path_profile(files: list[str], profile: str | None) -> list[str]:
    if not profile:
        return files
    return [f for f in files if profile_accepts(f, profile)]


def _init_schema(conn: sqlite3.Connection, *, rebuild: bool = False) -> None:
    """Create or migrate the database schema.

    On rebuild, drops all tables and recreates from scratch.
    On incremental, creates tables if missing and adds content_hash column.
    """
    c = conn.cursor()
    if rebuild:
        c.executescript("""
            DROP TABLE IF EXISTS file_enrich;
            DROP TABLE IF EXISTS files_fts;
            DROP TABLE IF EXISTS files;
        """)

    c.executescript("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE,
            ext TEXT,
            size INTEGER,
            mtime TEXT,
            content TEXT,
            content_hash TEXT
        );
        CREATE TABLE IF NOT EXISTS file_enrich (
            file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
            file_key TEXT NOT NULL,
            symbols TEXT,
            enriched_at TEXT DEFAULT (datetime('now'))
        );
    """)

    # Migrate: add content_hash column if missing (old databases)
    cols = [row[1] for row in c.execute("PRAGMA table_info(files)").fetchall()]
    if "content_hash" not in cols:
        c.execute("ALTER TABLE files ADD COLUMN content_hash TEXT")

    # Create FTS5 with content-table mode if not exists
    fts_exists = c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='files_fts'"
    ).fetchone()
    if not fts_exists:
        c.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS files_fts
                USING fts5(path, content, content=files, content_rowid=id, tokenize='trigram');
            CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
                INSERT INTO files_fts(rowid, path, content)
                VALUES (new.id, new.path, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
                INSERT INTO files_fts(files_fts, rowid, path, content)
                VALUES ('delete', old.id, old.path, old.content);
            END;
            CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
                INSERT INTO files_fts(files_fts, rowid, path, content)
                VALUES ('delete', old.id, old.path, old.content);
                INSERT INTO files_fts(rowid, path, content)
                VALUES (new.id, new.path, new.content);
            END;
        """)

    conn.commit()


def build_db(target: str, exts: set, db: str, files: list[str], *,
             rebuild: bool = False) -> dict[str, int]:
    """Phase 1: FTS5 trigram content index with incremental update.

    Returns dict with keys: added, updated, removed, skipped, total.
    On rebuild or first run, all files are treated as new (added).
    """
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _init_schema(conn, rebuild=rebuild)
    c = conn.cursor()

    # Build set of disk paths (filtered by extension)
    disk_files: dict[str, tuple[str, int, str]] = {}  # relpath → (ext, size, mtime_str)
    for relpath in files:
        ext = os.path.splitext(relpath)[1].lower()
        if ext not in exts:
            continue
        fpath = os.path.join(target, relpath)
        try:
            st = os.stat(fpath)
        except OSError:
            continue
        disk_files[relpath] = (ext, st.st_size, str(int(st.st_mtime)))

    # Get existing file paths and hashes from database
    existing = {}
    for row in c.execute("SELECT id, path, content_hash, mtime FROM files"):
        existing[row[1]] = (row[0], row[2], row[3])

    added = 0
    updated = 0
    removed = 0
    skipped = 0
    commit_batch = 0

    for relpath, (ext, size, mtime_str) in disk_files.items():
        fpath = os.path.join(target, relpath)

        if relpath in existing:
            existing_id, old_hash, old_mtime = existing[relpath]
            # Quick check: if mtime unchanged, skip entirely (no file read)
            if old_mtime == mtime_str and old_hash:
                skipped += 1
                del existing[relpath]
                continue

            # Mtime changed — read file and compare hash
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
            except Exception:
                del existing[relpath]
                continue

            new_hash = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
            if new_hash == old_hash:
                # Content unchanged, just update mtime
                c.execute(
                    "UPDATE files SET mtime=?, size=? WHERE id=?",
                    (mtime_str, size, existing_id),
                )
                skipped += 1
                del existing[relpath]
                commit_batch += 1
                continue

            # Content changed
            c.execute(
                "UPDATE files SET ext=?, size=?, mtime=?, content=?, content_hash=? WHERE id=?",
                (ext, size, mtime_str, content, new_hash, existing_id),
            )
            updated += 1
            del existing[relpath]
            commit_batch += 1
        else:
            # New file
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
            except Exception:
                continue

            new_hash = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
            c.execute(
                "INSERT INTO files (path, ext, size, mtime, content, content_hash) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (relpath, ext, size, mtime_str, content, new_hash),
            )
            added += 1
            commit_batch += 1

        if commit_batch >= 500:
            conn.commit()
            commit_batch = 0

    # Remove files that exist in DB but not on disk
    for relpath in list(existing.keys()):
        file_id = existing[relpath][0]
        c.execute("DELETE FROM file_enrich WHERE file_id=?", (file_id,))
        c.execute("DELETE FROM files WHERE id=?", (file_id,))
        removed += 1

    conn.commit()
    total = added + updated + skipped
    conn.close()
    return {"added": added, "updated": updated, "removed": removed,
            "skipped": skipped, "total": total}


def main():
    parser = argparse.ArgumentParser(description="SQL-ManyThing Phase 1: FTS5 content index")
    parser.add_argument("target", help="Project root path")
    parser.add_argument(
        "--ext",
        default=None,
        help="Comma-separated extensions (default: profile exts, or built-in source exts)",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        help="Indexing profile with extension and path policy (e.g. unreal-installed-core)",
    )
    parser.add_argument(
        "--git",
        action="store_true",
        help="Use git ls-files instead of os.walk (respects .gitignore)",
    )
    parser.add_argument(
        "--gitignore",
        help="Enumerate with os.walk filtered by the specified .gitignore file (no built-in skip rules)",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Force full rebuild (DROP + CREATE all tables)",
    )
    args = parser.parse_args()

    target = os.path.realpath(args.target)
    if not os.path.isdir(target):
        print(f"Error: {target} not found")
        sys.exit(1)

    if args.ext:
        exts = {f".{e.strip().lstrip('.')}" for e in args.ext.split(",") if e.strip()}
    elif args.profile:
        exts = set(PROFILES[args.profile]["exts"])
    else:
        exts = set(DEFAULT_EXTS)
    db = os.path.join(target, ".srcidx", "source.db")
    os.makedirs(os.path.dirname(db), exist_ok=True)

    # Collect file list
    if args.gitignore:
        gitignore_file = os.path.realpath(args.gitignore)
        if not os.path.isfile(gitignore_file):
            print(f"Error: gitignore file not found: {gitignore_file}")
            sys.exit(1)
        method = f"os.walk + gitignore ({gitignore_file})"
        files = walk_files_with_gitignore(target, gitignore_file)
        print(f"files found by {method}: {len(files)}")
    elif args.git:
        method = "git ls-files"
        files = list_files_via_git(target)
        if files is None:
            print("Warning: not a git repo, falling back to os.walk")
            method = "os.walk"
            files = walk_files(target)
    else:
        method = "os.walk"
        files = walk_files(target)

    if args.profile:
        before_profile = len(files)
        files = apply_path_profile(files, args.profile)
        method += f" + profile {args.profile} ({before_profile}->{len(files)} paths)"

    print(f"SQL-ManyThing Phase 1 — FTS5 content index")
    print(f"Target: {target}")
    print(f"Method: {method}")
    print(f"Exts:   {', '.join(sorted(exts))}")
    print(f"DB:     {db}")
    if args.rebuild:
        print(f"Mode:   FULL REBUILD")
    else:
        print(f"Mode:   incremental (use --rebuild for full)")
    print(f"Files enumerated: {len(files)}")
    t0 = time.time()
    result = build_db(target, exts, db, files, rebuild=args.rebuild)
    elapsed = time.time() - t0
    db_size = os.path.getsize(db)
    print(f"Added: {result['added']}, Updated: {result['updated']}, "
          f"Removed: {result['removed']}, Skipped: {result['skipped']}")
    print(f"Total: {result['total']} files in {elapsed:.1f}s")
    print(f"DB size: {db_size} bytes ({db_size/1024/1024:.1f} MB)")


if __name__ == "__main__":
    main()
