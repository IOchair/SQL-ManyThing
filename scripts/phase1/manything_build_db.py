"""SQL-ManyThing — Phase 1: FTS5 trigram content index.
Usage:
  # Classic mode (os.walk + SKIP_DIRS):
  python3 manything_build_db.py /path/to/target [--ext h,cpp,cs,py,ts,tsx,js,jsx,rs,md]

  # Git mode (git ls-files, respects .gitignore):
  python3 manything_build_db.py /path/to/target --git [--ext ...]

Creates .srcidx/source.db with FTS5 trigram index of file contents.
Phase 1 only — no symbol enrich. Run Phase 2 scripts separately.

Full rebuild each run (DROP + CREATE). Fast enough for all use cases
(sub-minute for typical projects; ~85 min for Unreal-level scale).
Phase 2 scripts handle all symbol enrich — no incremental logic needed.
"""

import sqlite3
import os
import time
import sys
import argparse
import fnmatch
import subprocess

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


def build_db(target: str, exts: set, db: str, files: list[str]) -> int:
    """Phase 1: FTS5 trigram content index from a pre-computed file list."""
    conn = sqlite3.connect(db)
    c = conn.cursor()
    c.executescript("""
        DROP TABLE IF EXISTS file_enrich;
        DROP TABLE IF EXISTS files;
        DROP TABLE IF EXISTS files_fts;
        CREATE TABLE files (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE,
            ext TEXT,
            size INTEGER,
            mtime TEXT,
            content TEXT
        );
        CREATE VIRTUAL TABLE files_fts
            USING fts5(path, content, tokenize='trigram');
        CREATE TABLE IF NOT EXISTS file_enrich (
            file_id INTEGER PRIMARY KEY REFERENCES files(id),
            file_key TEXT NOT NULL,
            symbols TEXT,
            enriched_at TEXT DEFAULT (datetime('now'))
        );
    """)
    total = 0
    for relpath in files:
        ext = os.path.splitext(relpath)[1].lower()
        if ext not in exts:
            continue
        fpath = os.path.join(target, relpath)
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except Exception:
            continue
        try:
            st = os.stat(fpath)
        except Exception:
            continue
        c.execute(
            "INSERT OR REPLACE INTO files (path, ext, size, mtime, content) VALUES (?, ?, ?, ?, ?)",
            (relpath, ext, st.st_size, str(int(st.st_mtime)), content),
        )
        c.execute(
            "INSERT OR REPLACE INTO files_fts (rowid, path, content) VALUES (?, ?, ?)",
            (c.lastrowid, relpath, content),
        )
        total += 1
    conn.commit()
    conn.close()
    return total


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
    print(f"Files enumerated: {len(files)}")
    t0 = time.time()
    count = build_db(target, exts, db, files)
    elapsed = time.time() - t0
    db_size = os.path.getsize(db)
    print(f"Indexed: {count} files in {elapsed:.1f}s")
    print(f"DB size: {db_size} bytes ({db_size/1024/1024:.1f} MB)")


if __name__ == "__main__":
    main()
