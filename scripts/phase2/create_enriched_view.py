#!/usr/bin/env python3
"""SQL-ManyThing — Phase 2: Create v_enriched wide view.

Combines files + depth_segments + file_refs into one denormalized VIEW.
Every row = one depth_segment with pre-extracted block_content + refs.

Run after all other Phase 2 scripts:
  enrich_depth_segments.py
  enrich_file_refs.py

Usage: python3 create_enriched_view.py /path/to/target
"""

import argparse, os, sys


def create_view(target: str):
    db = os.path.join(target, ".srcidx", "source.db")
    if not os.path.isfile(db):
        print(f"Error: {db} not found — run Phase 1 first")
        sys.exit(1)

    import sqlite3
    conn = sqlite3.connect(db)
    cur = conn.cursor()

    # Check dependencies exist
    cur.execute("SELECT COUNT(*) FROM enrich_depth_segments")
    ds_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM enrich_file_refs")
    ref_count = cur.fetchone()[0]

    if ds_count == 0:
        print("Warning: enrich_depth_segments empty — run enrich_depth_segments.py first")

    sql = """
    DROP VIEW IF EXISTS v_enriched;
    CREATE VIEW v_enriched AS
    SELECT
        f.id AS file_id,
        f.path AS file_path,
        f.ext,
        ds.depth_level,
        ds.start_offset,
        ds.end_offset,
        substr(f.content, ds.start_offset + 1, ds.end_offset - ds.start_offset) AS block_content,
        refs_out.refs_to,
        refs_in.refs_from
    FROM files f
    JOIN enrich_depth_segments ds ON ds.file_id = f.id
    LEFT JOIN (
        SELECT file_id, json_group_array(DISTINCT target_raw) AS refs_to
        FROM enrich_file_refs WHERE target_raw IS NOT NULL
        GROUP BY file_id
    ) refs_out ON refs_out.file_id = f.id
    LEFT JOIN (
        SELECT r.target_file_id AS file_id, json_group_array(DISTINCT f2.path) AS refs_from
        FROM enrich_file_refs r
        JOIN files f2 ON f2.id = r.file_id
        WHERE r.target_file_id IS NOT NULL
        GROUP BY r.target_file_id
    ) refs_in ON refs_in.file_id = f.id;
    """

    cur.executescript(sql)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM v_enriched")
    row_count = cur.fetchone()[0]
    conn.close()

    print(f"v_enriched created: {row_count} rows ({ds_count} segments, {ref_count} refs)")


def main():
    parser = argparse.ArgumentParser(description="SQL-ManyThing Phase 2: Create v_enriched wide view")
    parser.add_argument("target", help="Project root path")
    args = parser.parse_args()
    target = os.path.realpath(args.target)
    if not os.path.isdir(target):
        print(f"Error: {target} not found")
        sys.exit(1)
    create_view(target)


if __name__ == "__main__":
    main()
