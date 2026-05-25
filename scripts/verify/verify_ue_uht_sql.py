#!/usr/bin/env python3
"""Verify a SQL-ManyThing Unreal Engine DB after Phase 1 + UHT enrich.

Usage:
  python3 scripts/verify_ue_uht_sql.py /path/to/Engine/.srcidx/source.db

Checks:
  - files and files_fts row counts match and are non-empty
  - UHT-enriched file count is non-empty
  - expected UHT symbol kinds exist
  - AActor is enriched with UFUNCTION data when present
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def scalar(cur: sqlite3.Cursor, sql: str, params: tuple = ()):  # noqa: ANN001
    cur.execute(sql, params)
    return cur.fetchone()[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Unreal SQL-ManyThing Phase 1 + UHT enrich output")
    parser.add_argument("db", help="Path to Engine/.srcidx/source.db")
    args = parser.parse_args()

    db = Path(args.db)
    if not db.is_file():
        print(f"ERROR db not found: {db}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(str(db))
    cur = conn.cursor()

    files = scalar(cur, "SELECT COUNT(*) FROM files")
    fts = scalar(cur, "SELECT COUNT(*) FROM files_fts")
    enriched = scalar(cur, "SELECT COUNT(*) FROM file_enrich WHERE symbols IS NOT NULL AND symbols != '[]'")

    print(f"files={files}")
    print(f"files_fts={fts}")
    print(f"uht_enriched_files={enriched}")

    if files <= 0:
        print("ERROR files table is empty", file=sys.stderr)
        return 1
    if files != fts:
        print(f"ERROR files/files_fts mismatch: {files} != {fts}", file=sys.stderr)
        return 1
    if enriched <= 0:
        print("ERROR no UHT-enriched file_enrich rows", file=sys.stderr)
        return 1

    cur.execute(
        """
        SELECT json_extract(value,'$.kind') AS kind, COUNT(*)
        FROM file_enrich, json_each(file_enrich.symbols)
        GROUP BY kind
        ORDER BY COUNT(*) DESC
        """
    )
    counts = dict(cur.fetchall())
    for kind in ("class", "struct", "enum", "interface", "function"):
        print(f"kind.{kind}={counts.get(kind, 0)}")
        if counts.get(kind, 0) <= 0:
            print(f"ERROR missing UHT kind: {kind}", file=sys.stderr)
            return 1

    cur.execute(
        """
        SELECT files.path,
               json_extract(value,'$.name') AS name,
               json_array_length(json_extract(value,'$.uht_functions')) AS fn_count
        FROM files
        JOIN file_enrich ON files.id=file_enrich.file_id,
             json_each(file_enrich.symbols)
        WHERE json_extract(value,'$.name')='AActor'
        LIMIT 1
        """
    )
    actor = cur.fetchone()
    if actor:
        print(f"AActor.path={actor[0]}")
        print(f"AActor.uht_functions={actor[2]}")
        if not actor[2] or actor[2] <= 0:
            print("ERROR AActor found without UHT functions", file=sys.stderr)
            return 1
    else:
        print("WARN AActor not found; DB may be a subset rather than full Engine")

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
