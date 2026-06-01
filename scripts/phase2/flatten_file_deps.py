#!/usr/bin/env python3
"""SQL-ManyThing — Phase 2b: File-level dependency flattening.

Iteratively expands upstream and downstream dependency trees from
enrich_file_refs into enrich_file_deps. One-pass per depth level,
pure SQL + loop.

Upstream:   A imports B, B imports C → A upstream of C
Downstream: B imported by A, A imported by D → D downstream of B

Query result:
  SELECT dep_file_id FROM enrich_file_deps
  WHERE file_id=? AND direction='upstream' ORDER BY depth;

  SELECT file_id FROM enrich_file_deps
  WHERE dep_file_id=? AND direction='downstream' ORDER BY depth;

Usage:
  python3 flatten_file_deps.py /path/to/target [--max-depth 50] [--batch 5000]

Requires: enrich_file_refs populated.
"""

import sqlite3, os, sys, argparse, time

DEPS_TABLE = "enrich_file_deps"


def ensure_schema(conn: sqlite3.Connection):
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS {DEPS_TABLE} (
            file_id      INTEGER NOT NULL,
            dep_file_id  INTEGER NOT NULL,
            direction    TEXT NOT NULL,
            depth        INTEGER NOT NULL,
            PRIMARY KEY (file_id, dep_file_id, direction)
        ) WITHOUT ROWID;
        CREATE INDEX IF NOT EXISTS idx_{DEPS_TABLE}_upstream
            ON {DEPS_TABLE}(file_id, direction, depth);
        CREATE INDEX IF NOT EXISTS idx_{DEPS_TABLE}_downstream
            ON {DEPS_TABLE}(dep_file_id, direction, depth);
    """)


def flatten(db: str, max_depth: int = 50, batch: int = 5000) -> tuple[int, int]:
    """Flatten upstream and downstream trees. Returns (up_rounds, down_rounds)."""
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    ensure_schema(conn)
    c = conn.cursor()

    # ── verify refs table ─────────────────────────────────────────────
    c.execute("SELECT COUNT(*) FROM enrich_file_refs WHERE target_file_id IS NOT NULL")
    resolvable = c.fetchone()[0]
    if resolvable == 0:
        print("  no resolvable refs — run enrich_file_refs.py first")
        conn.close()
        return (0, 0)
    print(f"  resolvable refs: {resolvable}")

    # ── upstream: A imports B, B imports C → A upstream of C ─────────
    print("  flattening upstream...")
    c.execute(f"DELETE FROM {DEPS_TABLE} WHERE direction='upstream'")

    # depth 1: direct imports
    c.execute(f"""
        INSERT OR IGNORE INTO {DEPS_TABLE}
        SELECT file_id, target_file_id, 'upstream', 1
        FROM enrich_file_refs WHERE target_file_id IS NOT NULL
    """)
    conn.commit()
    total_up = c.rowcount
    print(f"    depth 1: {total_up} deps")

    up_rounds = 1
    for depth in range(2, max_depth + 1):
        c.execute(f"""
            INSERT OR IGNORE INTO {DEPS_TABLE}
            SELECT DISTINCT d.file_id, r.target_file_id, 'upstream', ?
            FROM {DEPS_TABLE} d
            JOIN enrich_file_refs r ON r.file_id = d.dep_file_id
            WHERE d.direction = 'upstream' AND d.depth = ?
              AND r.target_file_id IS NOT NULL
        """, (depth, depth - 1))
        conn.commit()
        inserted = c.rowcount
        if inserted == 0:
            break
        total_up += inserted
        up_rounds += 1
        print(f"    depth {depth}: {inserted} deps")

    print(f"  upstream done: {total_up} total deps in {up_rounds} rounds")

    # ── downstream: B imported by A, A imported by D → D downstream of B ──
    print("  flattening downstream...")
    c.execute(f"DELETE FROM {DEPS_TABLE} WHERE direction='downstream'")

    # depth 1: files that import target
    c.execute(f"""
        INSERT OR IGNORE INTO {DEPS_TABLE}
        SELECT target_file_id, file_id, 'downstream', 1
        FROM enrich_file_refs WHERE target_file_id IS NOT NULL
    """)
    conn.commit()
    total_down = c.rowcount
    print(f"    depth 1: {total_down} deps")

    down_rounds = 1
    for depth in range(2, max_depth + 1):
        c.execute(f"""
            INSERT OR IGNORE INTO {DEPS_TABLE}
            SELECT DISTINCT d.file_id, r.file_id, 'downstream', ?
            FROM {DEPS_TABLE} d
            JOIN enrich_file_refs r ON r.target_file_id = d.dep_file_id
            WHERE d.direction = 'downstream' AND d.depth = ?
              AND r.target_file_id IS NOT NULL
        """, (depth, depth - 1))
        conn.commit()
        inserted = c.rowcount
        if inserted == 0:
            break
        total_down += inserted
        down_rounds += 1
        print(f"    depth {depth}: {inserted} deps")

    print(f"  downstream done: {total_down} total deps in {down_rounds} rounds")

    conn.close()
    return (up_rounds, down_rounds)


def main():
    parser = argparse.ArgumentParser(
        description="SQL-ManyThing Phase 2b: flatten file dependency tree"
    )
    parser.add_argument("target", help="Project root path")
    parser.add_argument("--max-depth", type=int, default=50,
                        help="Max depth to traverse (default: 50)")
    args = parser.parse_args()

    target = os.path.realpath(args.target)
    db = os.path.join(target, ".srcidx", "source.db")
    if not os.path.isdir(target):
        print(f"Error: {target} not found")
        sys.exit(1)
    if not os.path.isfile(db):
        print(f"Error: DB not found ({db})")
        sys.exit(1)

    print("SQL-ManyThing Phase 2b — file dependency flattening")
    print(f"Target:     {target}")
    print(f"Max depth:  {args.max_depth}")
    t0 = time.time()
    up, down = flatten(db, args.max_depth)
    elapsed = time.time() - t0
    print(f"Done:       {up} upstream rounds, {down} downstream rounds in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
