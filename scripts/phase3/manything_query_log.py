#!/usr/bin/env python3
"""
SQL-ManyThing Phase 3 — query-log CLI

Usage:
  manything-query-log init          Initialize query_log infrastructure
  manything-query-log import        Flush pending.jsonl into query_log.db
  manything-query-log list [N]      Show last N queries (default: 10)

Environment:
  MANYTHING_HOME  — override ~/.hermes/manything (default: $HOME/.hermes/manything)
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path


def get_manything_home() -> Path:
    env = os.environ.get("MANYTHING_HOME")
    if env:
        return Path(env)
    return Path.home() / ".hermes" / "manything"


def schema_sql() -> str:
    return """\
CREATE TABLE IF NOT EXISTS query_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   INTEGER NOT NULL,
    project     TEXT NOT NULL,
    db_path     TEXT NOT NULL,
    sql_text    TEXT NOT NULL,
    rows_hint   INTEGER,
    imported_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS query_notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id      INTEGER NOT NULL REFERENCES query_log(id) ON DELETE CASCADE,
    note        TEXT NOT NULL,
    tag         TEXT,
    created_at  INTEGER NOT NULL
);
CREATE VIEW IF NOT EXISTS query_trace AS
SELECT ql.id, ql.timestamp, ql.project, ql.sql_text,
       qn.note, qn.tag, qn.created_at AS noted_at
FROM query_log ql LEFT JOIN query_notes qn ON qn.log_id = ql.id;
CREATE INDEX IF NOT EXISTS idx_query_log_project ON query_log(project);
CREATE INDEX IF NOT EXISTS idx_query_log_timestamp ON query_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_query_notes_tag ON query_notes(tag);
"""


def cmd_init(args):
    manything_home = get_manything_home()
    manything_home.mkdir(parents=True, exist_ok=True)

    # query_log.db
    db_path = manything_home / "query_log.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(schema_sql())
    conn.commit()
    conn.close()
    print(f"query_log.db: {db_path}")

    # aliases.sh
    aliases_path = manything_home / "aliases.sh"
    if not aliases_path.exists():
        aliases_path.write_text("""#!/bin/bash
# manything aliases — MANYTHING_<project>=\"<absolute_path>\"
# Add: echo 'MANYTHING_myproject=\"/path/to/project\"' >> \"$0\"
""")
    print(f"aliases.sh:   {aliases_path}")

    # pending.jsonl
    pending_path = manything_home / "pending.jsonl"
    pending_path.touch(exist_ok=True)
    print(f"pending.jsonl: {pending_path}")

    print("\nReady. Add project:")
    print(f'  echo \'MANYTHING_<project>="/path/to/project"\' >> {aliases_path}')
    print("Verify:")
    print("  sqlite3 :trace \"SELECT COUNT(*) FROM query_log\"")


def cmd_import(args):
    manything_home = get_manything_home()
    pending_path = manything_home / "pending.jsonl"
    db_path = manything_home / "query_log.db"

    if not pending_path.exists():
        print("No pending.jsonl found. Nothing to import.")
        return

    raw = pending_path.read_text().strip()
    if not raw:
        print("pending.jsonl is empty. Nothing to import.")
        return

    lines = raw.splitlines()
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    i = 0
    imported = 0
    skipped = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # Header: <ts>|<project>|<db_path>
        parts = line.split("|", 2)
        if len(parts) != 3:
            skipped += 1
            i += 1
            continue

        try:
            timestamp = int(parts[0])
        except ValueError:
            skipped += 1
            i += 1
            continue

        project = parts[1]
        db_path_virtual = parts[2]
        i += 1

        # Multi-line SQL until "---" separator
        sql_parts = []
        while i < len(lines):
            if lines[i].strip() == "---":
                i += 1
                break
            sql_parts.append(lines[i])
            i += 1
        else:
            # EOF without separator — partial record, skip
            skipped += 1
            break

        sql_text = "\n".join(sql_parts).strip()
        if not sql_text:
            skipped += 1
            continue

        c.execute(
            "INSERT INTO query_log (timestamp, project, db_path, sql_text) VALUES (?, ?, ?, ?)",
            (timestamp, project, db_path_virtual, sql_text),
        )
        imported += 1

    conn.commit()
    conn.close()

    # Clear pending
    pending_path.write_text("")

    print(f"Imported: {imported}")
    if skipped:
        print(f"Skipped:  {skipped} (malformed records)")
    print(f"Total in query_log.db: {query_count(db_path)}")


def print_trace_rows(rows):
    if not rows:
        print("No matching query traces.")
        return
    print(f"{'ID':<6} {'Timestamp':<14} {'Project':<16} {'Tag':<16} SQL")
    print("-" * 100)
    for row_id, ts, project, tag, sql_preview in rows:
        t_str = time.strftime("%m-%d %H:%M", time.localtime(ts))
        tag = tag or ""
        print(f"{row_id:<6} {t_str:<14} {project:<16} {tag:<16} {sql_preview}")


def cmd_list(args):
    manything_home = get_manything_home()
    db_path = manything_home / "query_log.db"
    if not db_path.exists():
        print("query_log.db not found. Run 'manything-query-log init' first.")
        return

    limit = args.limit
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    rows = c.execute(
        "SELECT id, timestamp, project, tag, substr(sql_text, 1, 120) "
        "FROM query_trace ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    print_trace_rows(rows)


def cmd_search(args):
    manything_home = get_manything_home()
    db_path = manything_home / "query_log.db"
    if not db_path.exists():
        print("query_log.db not found. Run 'manything-query-log init' first.")
        return
    terms = [t.lower() for t in args.terms if t.strip()]
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    if terms:
        where = " AND (" + " OR ".join(["lower(sql_text) LIKE ?" for _ in terms]) + ")"
        params = [args.project] + [f"%{t}%" for t in terms] + [args.limit]
    else:
        where = ""
        params = [args.project, args.limit]
    rows = c.execute(
        "SELECT id, timestamp, project, tag, substr(sql_text, 1, 160) "
        "FROM query_trace WHERE project = ?" + where + " ORDER BY tag IS NULL, id DESC LIMIT ?",
        params,
    ).fetchall()
    conn.close()
    print_trace_rows(rows)


def cmd_tag(args):
    manything_home = get_manything_home()
    db_path = manything_home / "query_log.db"
    if not db_path.exists():
        print("query_log.db not found. Run 'manything-query-log init' first.")
        return
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    exists = c.execute("SELECT 1 FROM query_log WHERE id = ?", (args.log_id,)).fetchone()
    if not exists:
        conn.close()
        print(f"No query_log row with id={args.log_id}")
        sys.exit(1)
    c.execute(
        "INSERT INTO query_notes (log_id, note, tag, created_at) VALUES (?, ?, ?, ?)",
        (args.log_id, args.note, args.tag, int(time.time())),
    )
    conn.commit()
    conn.close()
    print(f"Tagged query {args.log_id} as {args.tag}: {args.note}")


def cmd_preflight(args):
    cmd_import(argparse.Namespace())
    if args.terms:
        print("\nFuzzy matches:")
        search_args = argparse.Namespace(project=args.project, terms=args.terms, limit=args.limit)
        cmd_search(search_args)
    print("\nRecent project traces:")
    recent_args = argparse.Namespace(project=args.project, terms=[], limit=args.limit)
    cmd_search(recent_args)


def query_count(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    cnt = conn.execute("SELECT COUNT(*) FROM query_log").fetchone()[0]
    conn.close()
    return cnt


def main():
    parser = argparse.ArgumentParser(description="SQL-ManyThing query log manager")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize query_log infrastructure")
    p_init.set_defaults(func=cmd_init)

    p_import = sub.add_parser("import", help="Flush pending.jsonl into query_log.db")
    p_import.set_defaults(func=cmd_import)

    p_list = sub.add_parser("list", help="Show recent queries")
    p_list.add_argument("limit", nargs="?", type=int, default=10, help="Number of entries (default: 10)")
    p_list.set_defaults(func=cmd_list)

    p_search = sub.add_parser("search", help="Fuzzy-search prior queries for a project")
    p_search.add_argument("project", help="Project alias (e.g. myproject)")
    p_search.add_argument("terms", nargs="*", help="Fuzzy SQL terms to match")
    p_search.add_argument("--limit", type=int, default=10, help="Number of entries (default: 10)")
    p_search.set_defaults(func=cmd_search)

    p_tag = sub.add_parser("tag", help="Tag a query_log row as useful")
    p_tag.add_argument("log_id", type=int, help="query_log.id to tag")
    p_tag.add_argument("tag", help="Tag value, e.g. useful_pattern or fast_path")
    p_tag.add_argument("note", help="Short note explaining when to reuse this query")
    p_tag.set_defaults(func=cmd_tag)

    p_preflight = sub.add_parser("preflight", help="Import pending logs and fuzzy-search prior project queries")
    p_preflight.add_argument("project", help="Project alias (e.g. myproject)")
    p_preflight.add_argument("terms", nargs="*", help="Fuzzy SQL terms to match")
    p_preflight.add_argument("--limit", type=int, default=10, help="Number of entries (default: 10)")
    p_preflight.set_defaults(func=cmd_preflight)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
