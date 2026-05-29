#!/usr/bin/env python3
"""SQL-ManyThing Phase 3 — sqlite3 wrapper (Python, cross-platform).

Replaces the bash sqlite3_wrapper.sh with matching dispatch logic:
    DB_PATH == ":trace"              → route to global query_log.db
    DB_PATH =~ /manything/<proj>/…   → resolve project, log, execute
    otherwise                        → transparent pass-through

Execution is forwarded to a real sqlite3 CLI for near-transparent argument,
output, and interactive behavior. On Windows, the installer can place a bundled
sqlite3 binary next to this wrapper as `sqlite3-real.exe`.

Install:
  python3 install.py              # installs this as ~/.local/bin/sqlite3
  python3 install.py --uninstall  # removes it
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent

MANYTHING_HOME = Path(os.environ.get("MANYTHING_HOME", str(Path.home() / ".hermes" / "manything")))
QUERY_LOG_DB = MANYTHING_HOME / "query_log.db"
PENDING_LOG = MANYTHING_HOME / "pending.jsonl"
ALIASES_FILE = MANYTHING_HOME / "aliases.sh"
_BUNDLED_WINDOWS_SQLITE3 = PROJECT_ROOT / "external" / "windows" / "sqlite3" / "sqlite3.exe"
_VALUE_OPTIONS = {
    "-cmd",
    "-init",
    "-newline",
    "-nonce",
    "-nullvalue",
    "-separator",
    "-vfs",
}


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
# Real sqlite3 discovery + forwarding
# ---------------------------------------------------------------------------


def _self_candidates() -> set[Path]:
    current = Path(__file__).resolve()
    candidates = {current}
    if current.suffix != ".cmd":
        candidates.add(current.with_suffix(".cmd"))
    return candidates


def _is_self_path(path: Path) -> bool:
    try:
        return path.resolve() in _self_candidates()
    except OSError:
        return False


def _candidate_sqlite_paths() -> list[Path]:
    candidates: list[Path] = []

    env_path = os.environ.get("SQLMANYTHING_REAL_SQLITE3") or os.environ.get("MANYTHING_REAL_SQLITE3")
    if env_path:
        candidates.append(Path(env_path))

    if os.name == "nt":
        candidates.extend(
            [
                SCRIPT_DIR / "sqlite3-real.exe",
                SCRIPT_DIR / "sqlite3.exe",
                _BUNDLED_WINDOWS_SQLITE3,
            ]
        )
    else:
        candidates.extend(
            [
                SCRIPT_DIR / "sqlite3-real",
                Path("/usr/bin/sqlite3"),
                Path("/usr/local/bin/sqlite3"),
            ]
        )

    which_names = ["sqlite3.exe", "sqlite3"] if os.name == "nt" else ["sqlite3"]
    for name in which_names:
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))

    return candidates


def _find_real_sqlite3() -> Path | None:
    for candidate in _candidate_sqlite_paths():
        if not candidate.exists() or _is_self_path(candidate):
            continue
        return candidate
    return None


def _run_real_sqlite3(argv: list[str]) -> int:
    real_sqlite3 = _find_real_sqlite3()
    if real_sqlite3 is None:
        print("manything wrapper: real sqlite3 executable not found", file=sys.stderr)
        print(
            "  Set SQLMANYTHING_REAL_SQLITE3 or reinstall Phase 3 so a real sqlite3 binary is available.",
            file=sys.stderr,
        )
        return 1

    result = subprocess.run([str(real_sqlite3), *argv], check=False)
    return result.returncode


def _db_path_index(argv: list[str]) -> int | None:
    i = 0
    while i < len(argv):
        arg = argv[i]

        if arg == "--":
            return i + 1 if i + 1 < len(argv) else None

        if arg in _VALUE_OPTIONS:
            i += 2
            continue

        if any(arg.startswith(option) and arg != option for option in _VALUE_OPTIONS):
            i += 1
            continue

        if arg.startswith("-") and arg != "-":
            i += 1
            continue

        return i

    return None


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

_MANYTHING_RE = re.compile(r"^/manything/([^/]+)/source\.db$")
_MSYS_MANYTHING_RE = re.compile(r"^[A-Za-z]:/Program Files/Git/manything/([^/]+)/source\.db$")


def _strip_msys_pathconv(db_path: str) -> str:
    """Undo MSYS2 /manything/... → C:/Program Files/Git/manything/... conversion."""
    m = _MSYS_MANYTHING_RE.match(db_path)
    if m:
        return f"/manything/{m.group(1)}/source.db"
    return db_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SQL-ManyThing sqlite3 wrapper (Python)",
        add_help=False,
    )
    _, passthrough = parser.parse_known_args()
    forward_argv = passthrough.copy()
    db_index = _db_path_index(forward_argv)

    if db_index is None:
        return _run_real_sqlite3(forward_argv)

    db_path = _strip_msys_pathconv(forward_argv[db_index])
    if db_path == ":trace":
        forward_argv[db_index] = str(QUERY_LOG_DB)
        return _run_real_sqlite3(forward_argv)

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
        sql_text = " ".join(arg for i, arg in enumerate(forward_argv) if i != db_index)
        if sql_text:
            _append_pending(project, db_path, sql_text)

        forward_argv[db_index] = real_db
        return _run_real_sqlite3(forward_argv)

    # --- Dispatch: pass-through (any other DB path) ---
    return _run_real_sqlite3(forward_argv)


if __name__ == "__main__":
    sys.exit(main())
