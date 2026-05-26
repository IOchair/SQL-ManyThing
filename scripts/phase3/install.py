#!/usr/bin/env python3
"""SQL-ManyThing Phase 3 — cross-platform installer.

Replaces install.sh with Python for Windows/Linux/macOS support.

Usage:
  python3 install.py              # install to default location
  python3 install.py --prefix ~/mytools  # custom install dir
  python3 install.py --uninstall  # remove installed files
  python3 install.py --dry-run    # preview without changes
"""

from __future__ import annotations

import os
import platform
import shutil
import stat
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent

WRAPPER_SRC = SCRIPT_DIR / "sqlite3_wrapper.py"
QUERY_LOG_CLI = SCRIPT_DIR / "manything_query_log.py"


def default_prefix() -> Path:
    """Return the default install location for the current platform."""
    system = platform.system()
    # if system == "Windows":
    #     appdata = os.environ.get("APPDATA")
    #     if appdata:
    #         return Path(appdata) / "sql-manything"
    #     return Path.home() / "AppData" / "Roaming" / "sql-manything"
    # else:
    return Path.home() / ".local" / "bin"


def _make_executable(path: Path) -> None:
    st = os.stat(path)
    os.chmod(path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _write_cmd_wrapper(dest: Path, target: Path) -> None:
    """Generate a .cmd wrapper on Windows that calls the Python script."""
    cmd_path = dest.with_suffix(".cmd") if dest.suffix != ".cmd" else dest
    python = sys.executable.replace("\\", "\\\\")
    target_str = str(target).replace("\\", "/")
    cmd_path.write_text(
        f'@"{python}" "{target_str}" %*\n',
        encoding="utf-8",
    )
    return cmd_path


def do_install(prefix: Path, dry_run: bool = False) -> int:
    system = platform.system()

    for src, name in [
        (WRAPPER_SRC, "sqlite3"),
        (QUERY_LOG_CLI, "SQL-ManyThing-query-log"),
    ]:
        if not src.exists():
            print(f"Error: {src} not found. Run from SQL-ManyThing root.", file=sys.stderr)
            return 1

    if dry_run:
        print("SQL-ManyThing Phase 3 — dry run")
        print(f"Would install to: {prefix}")
        print(f"  {prefix / 'sqlite3'}  (from {WRAPPER_SRC})")
        print(f"  {prefix / 'SQL-ManyThing-query-log'}  (from {QUERY_LOG_CLI})")
        print("Would initialize: query_log.db")
        print(f"PATH recommendation: add {prefix} to your PATH")
        return 0

    prefix.mkdir(parents=True, exist_ok=True)

    # Install sqlite3 wrapper
    wrapper_dest = prefix / "sqlite3"
    shutil.copy2(str(WRAPPER_SRC), str(wrapper_dest))
    if system != "Windows":
        _make_executable(wrapper_dest)
    else:
        # On Windows, create a .cmd wrapper
        cmd_path = _write_cmd_wrapper(wrapper_dest, wrapper_dest)
        print(f"Installed: {cmd_path} (.cmd wrapper)")
    print(f"Installed: {wrapper_dest}")

    # Install query-log CLI
    ql_dest = prefix / "SQL-ManyThing-query-log"
    shutil.copy2(str(QUERY_LOG_CLI), str(ql_dest))
    if system != "Windows":
        _make_executable(ql_dest)
    print(f"Installed: {ql_dest}")

    # Initialize query_log.db
    manything_home = Path(os.environ.get("MANYTHING_HOME", str(Path.home() / ".hermes" / "manything")))
    manything_home.mkdir(parents=True, exist_ok=True)
    ql_db = manything_home / "query_log.db"
    if not ql_db.exists():
        import sqlite3 as sq
        from manything_query_log import schema_sql
        conn = sq.connect(str(ql_db))
        conn.executescript(schema_sql())
        conn.commit()
        conn.close()
        print(f"Initialized: {ql_db}")
    else:
        print(f"Already exists: {ql_db}")

    # Initialize aliases.sh if missing
    aliases = manything_home / "aliases.sh"
    if not aliases.exists():
        aliases.write_text(
            "#!/bin/bash\n"
            "# manything aliases — MANYTHING_<project>=\"<absolute_path>\"\n"
            "# Add: echo 'MANYTHING_myproject=\"/path/to/project\"' >> \"$0\"\n",
            encoding="utf-8",
        )
        print(f"Created: {aliases}")

    # Initialize pending.jsonl
    pending = manything_home / "pending.jsonl"
    if not pending.exists():
        pending.touch()
        print(f"Created: {pending}")

    print()
    print("Installation complete.")
    print()
    print(f"IMPORTANT: Ensure {prefix} is in your PATH.")
    if system != "Windows":
        print(f'  export PATH="{prefix}:$PATH"')
    print()
    print("Add project aliases:")
    print(f"  echo 'MANYTHING_<project>=\"/path/to/project\"' >> {aliases}")
    print()
    print("Verify installation:")
    print("  sqlite3 :trace \".tables\"")
    print("  # Expected: query_log  query_notes  query_trace")
    return 0


def do_uninstall(prefix: Path) -> int:
    print("Uninstalling SQL-ManyThing Phase 3...")
    removed = 0
    for name in ["sqlite3", "sqlite3.cmd", "SQL-ManyThing-query-log"]:
        target = prefix / name
        if target.exists():
            target.unlink()
            print(f"Removed: {target}")
            removed += 1
    if removed == 0:
        print("Nothing to remove.")
    print()
    print("Note: query_log.db and pending.jsonl in ~/.hermes/manything/ are NOT removed.")
    print("To delete those: rm -f ~/.hermes/manything/query_log.db ~/.hermes/manything/pending.jsonl")
    return 0


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="SQL-ManyThing Phase 3 installer")
    parser.add_argument("--prefix", type=Path, default=None, help="Custom install directory")
    parser.add_argument("--uninstall", action="store_true", help="Remove installed files")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    args = parser.parse_args()

    prefix = args.prefix or default_prefix()

    if args.uninstall:
        return do_uninstall(prefix)
    return do_install(prefix, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
