#!/usr/bin/env python3
"""SQL-ManyThing Phase 3 — sqlite3 wrapper (Python, cross-platform).

Replaces the bash sqlite3_wrapper.sh with identical dispatch logic:
  DB_PATH == ":trace"              → route to global query_log.db
  DB_PATH =~ /manything/<proj>/…   → resolve project, log, execute
  otherwise                        → transparent pass-through

Uses Python's sqlite3 module directly (no external sqlite3 binary needed).
Supports the output modes and dot-commands that agents commonly use.

Install:
  python3 install.py              # installs this as ~/.local/bin/sqlite3
  python3 install.py --uninstall  # removes it
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

MANYTHING_HOME = Path(os.environ.get("MANYTHING_HOME", str(Path.home() / ".hermes" / "manything")))
QUERY_LOG_DB = MANYTHING_HOME / "query_log.db"
PENDING_LOG = MANYTHING_HOME / "pending.jsonl"
ALIASES_FILE = MANYTHING_HOME / "aliases.sh"


# ---------------------------------------------------------------------------
# Alias resolution (replaces bash `source aliases.sh`)
# ---------------------------------------------------------------------------

_alias_cache: dict[str, str] | None = None


def _load_aliases() -> dict[str, str]:
    global _alias_cache
    if _alias_cache is not None:
        return _alias_cache
    aliases: dict[str, str] = {}
    if ALIASES_FILE.exists():
        for line in ALIASES_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r'MANYTHING_(\w+)=(["\'])(.+?)\2', line)
            if m:
                aliases[m.group(1)] = m.group(3)
    _alias_cache = aliases
    return aliases


def _resolve_project(project: str) -> str | None:
    aliases = _load_aliases()
    path = aliases.get(project)
    if path and os.path.isdir(path):
        return path
    return None


# ---------------------------------------------------------------------------
# Pending log (append-only, async-safe)
# ---------------------------------------------------------------------------

def _append_pending(project: str, db_path: str, sql_text: str) -> None:
    MANYTHING_HOME.mkdir(parents=True, exist_ok=True)
    with open(PENDING_LOG, "a", encoding="utf-8") as f:
        f.write(f"{int(time.time())}|{project}|{db_path}\n")
        f.write(sql_text + "\n")
        f.write("---\n")


# ---------------------------------------------------------------------------
# SQLite CLI emulation
# ---------------------------------------------------------------------------

def _execute_sql(conn: sqlite3.Connection, sql: str, *,
                 headers: bool = False, mode: str = "list") -> str:
    """Execute SQL and return formatted output."""
    sql_stripped = sql.strip()

    # Handle dot-commands
    if sql_stripped.startswith("."):
        return _handle_dot_command(conn, sql_stripped)

    # Regular SQL
    try:
        cursor = conn.execute(sql_stripped)
    except Exception as exc:
        return f"Error: {exc}"

    if cursor.description is None:
        return ""

    cols = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    if mode == "json":
        result = [dict(zip(cols, row)) for row in rows]
        return json.dumps(result, indent=2, ensure_ascii=False)
    elif mode == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        if headers:
            writer.writerow(cols)
        writer.writerows(rows)
        return buf.getvalue().rstrip("\n")
    elif mode == "line":
        lines = []
        for i, row in enumerate(rows):
            if i > 0:
                lines.append("")
            for col, val in zip(cols, row):
                lines.append(f"  {col} = {val}")
        return "\n".join(lines)
    else:
        # Default: pipe-separated (sqlite3 CLI default)
        lines = []
        if headers:
            lines.append("|".join(cols))
        for row in rows:
            lines.append("|".join(str(v) if v is not None else "" for v in row))
        return "\n".join(lines)


def _handle_dot_command(conn: sqlite3.Connection, cmd: str) -> str:
    cmd_lower = cmd.lower().strip()

    if cmd_lower == ".tables":
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "ORDER BY name"
        ).fetchall()
        return "  ".join(r[0] for r in rows)

    if cmd_lower.startswith(".tables ") or cmd_lower.startswith(".tables%"):
        pattern = cmd.split(None, 1)[1].strip().strip("'\"")
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ? "
            "ORDER BY name",
            (f"%{pattern}%",),
        ).fetchall()
        return "  ".join(r[0] for r in rows)

    if cmd_lower == ".schema":
        rows = conn.execute(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"
        ).fetchall()
        return "\n\n".join(r[0] for r in rows)

    if cmd_lower.startswith(".schema "):
        name = cmd.split(None, 1)[1].strip().strip("'\"")
        rows = conn.execute(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name LIKE ? "
            "ORDER BY name",
            (f"%{name}%",),
        ).fetchall()
        return "\n\n".join(r[0] for r in rows)

    if cmd_lower.startswith(".mode "):
        return f"Error: .mode should be set via CLI flags, not inline. Use --csv, --json, or --line."

    if cmd_lower == ".help":
        return (
            ".tables [PATTERN]  List tables\n"
            ".schema [NAME]     Show schema\n"
            ".help              This help\n"
        )

    return f"Error: unknown dot-command: {cmd}"


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

_MANYTHING_RE = re.compile(r"^/manything/([^/]+)/source\.db$")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SQL-ManyThing sqlite3 wrapper (Python)",
        add_help=False,
    )
    parser.add_argument("db_path", nargs="?", default="")
    parser.add_argument("sql", nargs="?", default="")
    parser.add_argument("-header", action="store_true", dest="headers")
    parser.add_argument("-csv", action="store_const", const="csv", dest="mode")
    parser.add_argument("-json", action="store_const", const="json", dest="mode")
    parser.add_argument("-cmd", action="append", dest="cmds", default=[])
    parser.add_argument("-separator", default="|")
    parser.add_argument("-nullvalue", default="")
    parser.add_argument("-bail", action="store_true")
    parser.add_argument("-interactive", action="store_true")
    # Allow unknown flags for forward compatibility
    args, _ = parser.parse_known_args()

    mode = args.mode or "list"
    db_path = args.db_path

    # --- Dispatch: :trace → global query_log.db ---
    if db_path == ":trace":
        if not QUERY_LOG_DB.exists():
            print(f"Error: query_log.db not found at {QUERY_LOG_DB}", file=sys.stderr)
            print("Run: SQL-ManyThing-query-log init", file=sys.stderr)
            return 1
        conn = sqlite3.connect(str(QUERY_LOG_DB))
        conn.row_factory = None
        sql_parts = []
        if args.cmds:
            sql_parts.extend(args.cmds)
        if args.sql:
            sql_parts.append(args.sql)
        for sql in sql_parts:
            output = _execute_sql(conn, sql, headers=args.headers, mode=mode)
            if output:
                print(output)
        conn.close()
        return 0

    # --- Dispatch: /manything/<project>/source.db → resolve + log + execute ---
    m = _MANYTHING_RE.match(db_path)
    if m:
        project = m.group(1)
        project_root = _resolve_project(project)
        if not project_root:
            print(f"manything wrapper: unknown project '{project}'", file=sys.stderr)
            print(f"  Add to {ALIASES_FILE}: echo 'MANYTHING_{project}=\"/real/path\"' >> \"{ALIASES_FILE}\"", file=sys.stderr)
            return 1

        real_db = os.path.join(project_root, ".srcidx", "source.db")
        if not os.path.isfile(real_db):
            print(f"manything wrapper: index not found at {real_db}", file=sys.stderr)
            print(f"  Run Phase 1 first: python3 scripts/phase1/manything_build_db.py \"{project_root}\"", file=sys.stderr)
            return 1

        # Log to pending.jsonl
        sql_text = args.sql or " ".join(args.cmds) or ""
        if sql_text:
            _append_pending(project, db_path, sql_text)

        # Execute
        conn = sqlite3.connect(real_db)
        conn.row_factory = None
        sql_parts = []
        if args.cmds:
            sql_parts.extend(args.cmds)
        if args.sql:
            sql_parts.append(args.sql)
        for sql in sql_parts:
            output = _execute_sql(conn, sql, headers=args.headers, mode=mode)
            if output:
                print(output)
        conn.close()
        return 0

    # --- Dispatch: pass-through (any other DB path) ---
    if db_path:
        conn = sqlite3.connect(db_path)
        conn.row_factory = None
        sql_parts = []
        if args.cmds:
            sql_parts.extend(args.cmds)
        if args.sql:
            sql_parts.append(args.sql)
        for sql in sql_parts:
            output = _execute_sql(conn, sql, headers=args.headers, mode=mode)
            if output:
                print(output)
        conn.close()
        return 0

    # No arguments — print version info
    print(f"SQL-ManyThing sqlite3 wrapper (Python)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
