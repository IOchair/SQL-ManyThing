#!/bin/bash
# =============================================================================
# SQL-ManyThing Phase 3 — sqlite3 wrapper
# PATH-intercept the system sqlite3, intercepting SQL-ManyThing queries and logging them asynchronously.
#
# Install:
#   mkdir -p ~/.local/bin
#   cp sqlite3 ~/.local/bin/sqlite3
#   chmod +x ~/.local/bin/sqlite3
#   # Ensure ~/.local/bin is before /usr/bin in PATH
#
# Dispatch logic:
#   DB_PATH == ":trace"          → route to global query_log.db
#   DB_PATH =~ /manything/<proj>/   → resolve project → append pending.jsonl → transparent exec
#   otherwise                    → transparent exec system sqlite3 (zero perturbation)
# =============================================================================
set -euo pipefail

MANYTHING_HOME="${MANYTHING_HOME:-$HOME/.hermes/manything}"
REAL_SQLITE3="/usr/bin/sqlite3"
ALIASES="$MANYTHING_HOME/aliases.sh"
PENDING_LOG="$MANYTHING_HOME/pending.jsonl"
QUERY_LOG_DB="$MANYTHING_HOME/query_log.db"

# --- Parse first non-flag arg as DB path ---
DB_PATH=""
ARGS=()
for arg in "$@"; do
    if [[ -z "$DB_PATH" && "$arg" != -* ]]; then
        DB_PATH="$arg"
    else
        ARGS+=("$arg")
    fi
done

# --- :trace virtual DB → query_log.db ---
if [[ "$DB_PATH" == ":trace" ]]; then
    exec "$REAL_SQLITE3" "$QUERY_LOG_DB" "${ARGS[@]}"
fi

# --- /manything/<project>/source.db → resolve via aliases.sh ---
if [[ "$DB_PATH" =~ ^/manything/([^/]+)/source\.db$ ]]; then
    PROJECT="${BASH_REMATCH[1]}"

    # Source aliases to resolve path
    if [[ -f "$ALIASES" ]]; then
        source "$ALIASES"
        ALIAS_VAR="MANYTHING_${PROJECT}"
        REAL_PATH="${!ALIAS_VAR:-}"
    else
        REAL_PATH=""
    fi

    if [[ -z "$REAL_PATH" ]]; then
        echo "manything wrapper: unknown project '$PROJECT'" >&2
        echo "  Add to $ALIASES: echo 'MANYTHING_${PROJECT}=\"/real/path\"' >> \"$ALIASES\"" >&2
        exit 1
    fi

    REAL_DB="$REAL_PATH/.srcidx/source.db"
    if [[ ! -f "$REAL_DB" ]]; then
        echo "manything wrapper: index not found at $REAL_DB" >&2
        echo "  Run Phase 1 first: python3 scripts/phase1/manything_build_db.py \"$REAL_PATH\"" >&2
        exit 1
    fi

    # --- Append to pending.jsonl (async, zero-risk, no escaping needed) ---
    SQL_TEXT="${ARGS[*]:-}"
    {
        echo "$(date +%s)|${PROJECT}|${DB_PATH}"
        echo "$SQL_TEXT"
        echo "---"
    } >> "$PENDING_LOG"

    # --- Forward to real sqlite3 ---
    exec "$REAL_SQLITE3" "$REAL_DB" "${ARGS[@]}"
fi

# --- Anything else: transparent pass-through ---
exec "$REAL_SQLITE3" "$DB_PATH" "${ARGS[@]}"
