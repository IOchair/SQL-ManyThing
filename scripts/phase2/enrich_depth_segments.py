#!/usr/bin/env python3
"""SQL-ManyThing — Phase 2: Pre-index depth/indent segments.

Scans file content once per file at enrich time. Records offset ranges
at each brace-depth (for {} languages) or indent-level (for Python/YAML).

Includes transient merge for indent mode: depth=N → depth=N+1 → depth=N
parameter lists get merged into a single depth=N segment, so function
signatures aren't fragmented across multiple segments (see
extract_indent_segments_merged for details).

Query-time: given ANY byte offset in a file, a single SQL query returns
the depth level and its exact (start_offset, end_offset) — no guesswork.

Three strategies, chosen by file extension:
  brace   — .js .ts .jsx .tsx .rs .go .java .c .cpp .h .hpp .cs .kt .swift
            Tracks {} depth, skipping strings and comments.
  indent  — .py .rb .yaml .yml .coffee .styl .sass .haml
            Tracks leading-whitespace indent level.

Usage:
  python3 enrich_depth_segments.py /path/to/target [--batch 50]
  python3 enrich_depth_segments.py /path/to/target --mode brace  # force mode
  python3 enrich_depth_segments.py /path/to/target --mode indent

Incremental: skips files whose size+mtime haven't changed since last run.
Batcher: processes --batch files per transaction, commits between batches.
"""

import sqlite3, os, sys, argparse, time

SEGMENTS_TABLE = "enrich_depth_segments"
TRACKER_TABLE  = "enrich_depth_tracker"

# Ext → mode
BRACE_EXTS = {
    ".js", ".jsx", ".mjs", ".cjs",
    ".ts", ".tsx", ".mts", ".cts",
    ".rs", ".go", ".java",
    ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh",
    ".cs", ".kt", ".kts", ".scala", ".swift",
    ".groovy", ".clj", ".cljs", ".edn",
    ".usf", ".ush", ".hlsl",  # UE shaders (C-style braces)
}
INDENT_EXTS = {
    ".py", ".pyw",
    ".rb", ".ru", ".gemspec",
    ".yaml", ".yml",
    ".coffee", ".styl", ".sass", ".haml",
    ".pug", ".jade",
    ".moon",  # moonscript
    ".nim", ".nims",
}


# ── helpers ──────────────────────────────────────────────────────────

def detect_mode(ext: str, mode_arg: str) -> str:
    if mode_arg != "auto":
        return mode_arg
    if ext in BRACE_EXTS:
        return "brace"
    if ext in INDENT_EXTS:
        return "indent"
    return "brace"  # safe default


def ensure_schema(conn: sqlite3.Connection):
    """Create tables if missing (idempotent)."""
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS {SEGMENTS_TABLE} (
            file_id      INTEGER NOT NULL,
            depth_level  INTEGER NOT NULL,
            start_offset INTEGER NOT NULL,
            end_offset   INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_{SEGMENTS_TABLE}_fid_start
            ON {SEGMENTS_TABLE}(file_id, start_offset);
        CREATE TABLE IF NOT EXISTS {TRACKER_TABLE} (
            file_id     INTEGER PRIMARY KEY REFERENCES files(id),
            file_key    TEXT NOT NULL,
            mode        TEXT NOT NULL DEFAULT 'brace',
            enriched_at TEXT DEFAULT (datetime('now'))
        );
    """)
    # Phase 2.1: scope_end_offset column (added post-enrich_depth_segments).
    # Tells v_enriched where a segment's enclosing scope ends —
    # the start_offset of the next segment at same-or-shallower depth,
    # or the file's content length.
    try:
        conn.execute(
            f"ALTER TABLE {SEGMENTS_TABLE} ADD COLUMN scope_end_offset INTEGER"
        )
    except sqlite3.OperationalError:
        pass  # column already exists


# ── brace mode ───────────────────────────────────────────────────────

def extract_brace_segments(content: str):
    """Scan content, yield (depth_level, start_offset, end_offset).

    Three-phase approach:
      1. Build skip mask — mark bytes inside strings/comments
      2. Find ALL {} positions outside skip mask
      3. Walk sorted position list, track depth, emit segments
    """
    n = len(content)
    if n == 0:
        return

    # Phase 1: skip mask — which bytes are inside string/comment
    skipped = bytearray(n)  # zero-init; 1 = skipped
    i = 0
    while i < n:
        ch = content[i]
        # line comment
        if ch == "/" and i + 1 < n and content[i + 1] == "/":
            i += 2
            while i < n and content[i] != "\n":
                skipped[i] = 1
                i += 1
            continue
        # block comment
        if ch == "/" and i + 1 < n and content[i + 1] == "*":
            i += 2
            while i < n - 1:
                if content[i] == "*" and content[i + 1] == "/":
                    skipped[i] = 1
                    skipped[i + 1] = 1
                    i += 2
                    break
                skipped[i] = 1
                i += 1
            continue
        # string literal
        if ch in ('"', "'", "`"):
            skipped[i] = 1  # mark the opening quote
            quote = ch
            while True:
                i += 1
                if i >= n:
                    break
                skipped[i] = 1
                c = content[i]
                if c == "\\":
                    i += 1
                    if i < n:
                        skipped[i] = 1
                    continue
                if c == quote:
                    break
                # template literal ${...} — skip inner content too,
                # but let main loop handle the {/} inside expression
                if quote == "`" and c == "$" and i + 1 < n and content[i + 1] == "{":
                    # skip $, then let main loop handle {
                    continue
            i += 1
            continue
        i += 1

    # Phase 2: find all {} positions outside skip mask
    events: list[tuple[int, str]] = []
    for i, ch in enumerate(content):
        if not skipped[i] and ch in ("{", "}"):
            events.append((i, ch))

    # Phase 3: walk sorted events, track depth, emit segments
    depth = 0
    seg_start = 0
    for pos, ch in events:
        if ch == "{":
            if pos > seg_start:
                yield (depth, seg_start, pos)
            seg_start = pos
            depth += 1
        else:  # "}"
            if depth > 0:
                if pos + 1 > seg_start:
                    yield (depth, seg_start, pos + 1)
                seg_start = pos + 1
                depth -= 1
            else:
                # unmatched } — treat as depth-0
                if pos > seg_start:
                    yield (depth, seg_start, pos)
                seg_start = pos + 1

    if seg_start < n:
        yield (depth, seg_start, n)


# ── indent mode ──────────────────────────────────────────────────────

def extract_indent_segments(content: str, tab_width: int = 4):
    """Scan content, yield (indent_level, start_offset, end_offset).

    Three-phase: skip mask → line indent levels → emit segments.
    Handles Python (''' triple-quotes) and Ruby/YAML (#) idioms.
    """
    n = len(content)
    if n == 0:
        return

    # Phase 1: skip mask — bytes inside strings/comments
    skipped = bytearray(n)
    i = 0
    while i < n:
        ch = content[i]

        # line comment (#)
        if ch == "#":
            while i < n and content[i] != "\n":
                skipped[i] = 1
                i += 1
            continue

        # triple-quoted string (''' or """)
        if ch in ('"', "'") and i + 2 < n and content[i] == content[i+1] == content[i+2]:
            quote = ch
            for j in range(3):
                skipped[i + j] = 1
            i += 3
            while i < n - 2:
                if content[i] == content[i+1] == content[i+2] == quote:
                    for j in range(3):
                        skipped[i + j] = 1
                    i += 3
                    break
                skipped[i] = 1
                i += 1
            continue

        # single/double quote string
        if ch in ('"', "'"):
            skipped[i] = 1
            quote = ch
            while True:
                i += 1
                if i >= n:
                    break
                skipped[i] = 1
                c = content[i]
                if c == "\\":
                    i += 1
                    if i < n:
                        skipped[i] = 1
                    continue
                if c == quote:
                    break
            i += 1
            continue

        i += 1

    # Phase 2: compute indent level per line
    # Record (line_start_offset, indent_level) for non-skipped lines
    lines = content.split("\n")
    line_data: list[tuple[int, int, int]] = []  # (start_offset, end_offset, indent_level)
    offset = 0
    for line in lines:
        line_len = len(line)
        line_end = offset + line_len + 1  # +1 for \n

        # Check if this line is entirely inside a string/comment
        # (first non-whitespace char is skipped)
        stripped = line.lstrip()
        if stripped:
            leading = len(line) - len(stripped)
            first_content = offset + leading
            if first_content < n and skipped[first_content]:
                # line content is inside string/comment — skip
                offset = line_end
                continue

            # compute indent level
            if stripped:
                indent = leading // tab_width
            else:
                indent = 0

            line_data.append((offset, line_end, indent))
        else:
            # blank line — use previous indent
            if line_data:
                indent = line_data[-1][2]
            else:
                indent = 0
            line_data.append((offset, line_end, indent))

        offset = line_end

    # Phase 3: walk indent changes, emit segments
    prev_indent = 0
    seg_start = 0
    for start_off, end_off, indent in line_data:
        if indent != prev_indent or start_off == 0:
            if start_off > seg_start:
                yield (prev_indent, seg_start, start_off)
            seg_start = start_off
            prev_indent = indent
    # final segment
    if seg_start < n:
        yield (prev_indent, seg_start, n)


def extract_indent_segments_merged(content: str, tab_width: int = 4):
    """Like extract_indent_segments but merges transient parameter indent spikes.

    Only merges depth=N → depth=N+1 → depth=N when N >= 1 (within functions).
    Skips depth=0 merges (file-level class/def boundaries stay separate).
    """
    raw = list(extract_indent_segments(content, tab_width))
    if len(raw) < 3:
        return raw

    merged: list[tuple[int, int, int]] = []
    i = 0
    while i < len(raw):
        d, s, e = raw[i]

        # Merge pattern: depth=N (sig) → depth=N+1 (params/body) → depth=N (closing/next)
        # Only for N >= 1 (avoids merging class body with next top-level def)
        if (d >= 1 and i + 2 < len(raw) and
            raw[i + 1][0] == d + 1 and
            raw[i + 2][0] == d):
            # Check: no nested deeper blocks (depth >= d+2) in between
            has_deeper = False
            for k in range(i + 1, i + 3):
                if k < len(raw) and raw[k][0] >= d + 2:
                    has_deeper = True
                    break
            if not has_deeper:
                # Transient merge: absorb the deeper segment into parent
                merged.append((d, s, raw[i + 2][2]))
                i += 3
                continue

        # No merge — try adjacent-same-depth merge for depth >= 1
        if d >= 1:
            j = i + 1
            while j < len(raw) and raw[j][0] == d:
                e = raw[j][2]
                j += 1
            if j > i + 1:
                merged.append((d, s, e))
                i = j
                continue

        merged.append(raw[i])
        i += 1

    return merged


# ── enrichment driver ────────────────────────────────────────────────

def enrich_depth(target: str, db: str, batch_size: int,
                 mode_arg: str = "auto") -> int:
    """Main enrich loop. Uses extract_indent_segments_merged for indent mode
    (transient parameter merge) and extract_brace_segments for brace mode."""
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    ensure_schema(conn)
    c = conn.cursor()

    # discover pending files — batch LEFT JOIN instead of N+1
    c.execute(f"""
        SELECT f.id, f.path, f.ext, f.size, f.mtime
        FROM files f
        LEFT JOIN {TRACKER_TABLE} t ON t.file_id = f.id
            AND t.file_key = (f.size || ':' || f.mtime)
        WHERE t.file_id IS NULL
    """)
    pending: list[tuple[int, str, str, str]] = []
    for fid, path, ext, size, mtime in c.fetchall():
        key = f"{size}:{mtime}"
        mode = detect_mode(ext, mode_arg)
        pending.append((fid, path, mode, key))

    if not pending:
        print("  all files up-to-date")
        conn.close()
        return 0

    print(f"  pending: {len(pending)} files")

    # batch process
    inserted = 0
    for batch_i in range(0, len(pending), batch_size):
        batch = pending[batch_i: batch_i + batch_size]
        t0 = time.time()

        # delete old segments for these files
        fids = [fid for fid, _, _, _ in batch]
        placeholders = ",".join("?" * len(fids))
        c.execute(
            f"DELETE FROM {SEGMENTS_TABLE} WHERE file_id IN ({placeholders})",
            fids,
        )
        c.execute(
            f"DELETE FROM {TRACKER_TABLE} WHERE file_id IN ({placeholders})",
            fids,
        )

        # read content and extract segments
        seg_rows: list[tuple[int, int, int, int]] = []
        for fid, path, mode, key in batch:
            c.execute("SELECT content FROM files WHERE id=?", (fid,))
            row = c.fetchone()
            if row is None or row[0] is None:
                continue
            content = row[0]

            if mode == "brace":
                segments = list(extract_brace_segments(content))
            else:
                segments = list(extract_indent_segments_merged(content))

            for depth, start, end in segments:
                seg_rows.append((fid, depth, start, end))

        # bulk insert segments
        if seg_rows:
            c.executemany(
                f"INSERT INTO {SEGMENTS_TABLE} (file_id, depth_level, start_offset, end_offset) "
                "VALUES (?, ?, ?, ?)",
                seg_rows,
            )

        # update tracker
        c.executemany(
            f"INSERT OR REPLACE INTO {TRACKER_TABLE} (file_id, file_key, mode) "
            "VALUES (?, ?, ?)",
            [(fid, key, mode) for fid, _, mode, key in batch],
        )

        conn.commit()
        batch_ok = len(batch)
        inserted += batch_ok
        print(f"  batch {batch_i // batch_size}: {batch_ok} files, "
              f"{len(seg_rows)} segments in {time.time() - t0:.1f}s")

    # Compute scope-end offsets after all segments are inserted.
    # Must run AFTER all files are done so cross-file joins don't race.
    t0 = time.time()
    compute_scope_end_offsets(conn)
    print(f"  scope_end_offset computed in {time.time() - t0:.1f}s")

    conn.close()
    return inserted


def compute_scope_end_offsets(conn: sqlite3.Connection):
    """Compute scope_end_offset for every segment in one SQL pass.

    For a segment at depth N, scope_end_offset is the start_offset of
    the next segment at depth <= N (same or shallower), or the file's
    content length if no such segment follows.  This gives the exact
    byte range of the enclosing scope — e.g. for a method header at
    depth=1, scope_end_offset = the start of the next depth<=1 segment,
    which is the next method / class end.  v_enriched uses this to
    produce block_content_full without stitching multiple depth rows.
    """
    conn.execute("""
        UPDATE enrich_depth_segments SET scope_end_offset = (
            SELECT COALESCE(
                MIN(ds2.start_offset),
                (SELECT length(f.content) FROM files f
                 WHERE f.id = enrich_depth_segments.file_id)
            )
            FROM enrich_depth_segments ds2
            WHERE ds2.file_id = enrich_depth_segments.file_id
              AND ds2.start_offset > enrich_depth_segments.start_offset
              AND ds2.depth_level <= enrich_depth_segments.depth_level
        )
    """)
    conn.commit()


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SQL-ManyThing Phase 2: pre-index depth/indent segments"
    )
    parser.add_argument("target", help="Project root path (must have .srcidx/source.db)")
    parser.add_argument("--batch", type=int, default=50,
                        help="Batch size (default: 50)")
    parser.add_argument("--mode", choices=["auto", "brace", "indent"],
                        default="auto",
                        help="Force mode (default: auto-detect by ext)")
    args = parser.parse_args()

    target = os.path.realpath(args.target)
    db = os.path.join(target, ".srcidx", "source.db")

    if not os.path.isdir(target):
        print(f"Error: {target} not found")
        sys.exit(1)
    if not os.path.isfile(db):
        print(f"Error: DB not found ({db}). Run Phase 1 first.")
        sys.exit(1)

    print("SQL-ManyThing Phase 2 — depth/indent segment enrich")
    print(f"Target: {target}")
    print(f"Mode:   {args.mode}")
    print(f"Batch:  {args.batch}")
    t0 = time.time()
    enriched = enrich_depth(target, db, args.batch, args.mode)
    elapsed = time.time() - t0
    print(f"Done:   {enriched} files in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
