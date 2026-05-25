#!/bin/bash
# SQL-ManyThing Phase 3 installer
# Install the sqlite3 wrapper and query-log tool for query tracing.
#
# Usage:
#   ./install.sh              # install to ~/.local/bin
#   ./install.sh --prefix ~/mytools  # custom install dir
#   ./install.sh --uninstall  # remove installed files
#
# Requires: scripts/phase3/sqlite3_wrapper.sh, scripts/phase3/SQL-ManyThing-query-log

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${1:-$HOME/.local/bin}"

# Handle --dry-run (must check before --uninstall)
if [[ "$*" == *"--dry-run"* ]]; then
    echo "SQL-ManyThing Phase 3 — dry run"
    echo "Would install:"
    echo "  $PREFIX/sqlite3         (from scripts/phase3/sqlite3_wrapper.sh)"
    echo "  $PREFIX/SQL-ManyThing-query-log  (from scripts/phase3/SQL-ManyThing-query-log)"
    echo "Would initialize: query_log.db"
    echo "PATH recommendation: export PATH=\"$PREFIX:\$PATH\""
    exit 0
fi

# Handle --uninstall
if [[ "${1:-}" == "--uninstall" ]]; then
    echo "Uninstalling SQL-ManyThing Phase 3..."
    rm -f "$PREFIX/sqlite3"
    rm -f "$PREFIX/SQL-ManyThing-query-log"
    echo "Removed: $PREFIX/sqlite3"
    echo "Removed: $PREFIX/SQL-ManyThing-query-log"
    echo ""
    echo "Note: query_log.db and pending.jsonl in ~/.hermes/manything/ are NOT removed."
    echo "To delete those: rm -f ~/.hermes/manything/query_log.db ~/.hermes/manything/pending.jsonl"
    exit 0
fi

# Handle --prefix
if [[ "${1:-}" == "--prefix" ]]; then
    PREFIX="$2"
fi

SOURCE_WRAPPER="$SCRIPT_DIR/scripts/phase3/sqlite3_wrapper.sh"
SOURCE_SHIM="$SCRIPT_DIR/scripts/phase3/SQL-ManyThing-query-log"
INIT_SCRIPT="$SCRIPT_DIR/scripts/phase3/manything_query_log.py"

# Verify sources exist
for f in "$SOURCE_WRAPPER" "$SOURCE_SHIM" "$INIT_SCRIPT"; do
    if [[ ! -f "$f" ]]; then
        echo "Error: $f not found. Run this script from the SQL-ManyThing root directory."
        exit 1
    fi
done

# Create install dir
mkdir -p "$PREFIX"

# Install wrapper
cp "$SOURCE_WRAPPER" "$PREFIX/sqlite3"
chmod +x "$PREFIX/sqlite3"
echo "Installed: $PREFIX/sqlite3 (sqlite3 wrapper)"

# Install query-log shim
cp "$SOURCE_SHIM" "$PREFIX/SQL-ManyThing-query-log"
chmod +x "$PREFIX/SQL-ManyThing-query-log"
echo "Installed: $PREFIX/SQL-ManyThing-query-log"

# Initialize query_log.db
python3 "$INIT_SCRIPT" init
echo "Initialized: query_log.db"

echo ""
echo "Installation complete."
echo ""
echo "IMPORTANT: Ensure $PREFIX comes before /usr/bin in your PATH:"
echo "  export PATH=\"$PREFIX:\$PATH\""
echo ""
echo "Add project aliases:"
echo "  echo 'MANYTHING_myproject=\"/path/to/project\"' >> ~/.hermes/manything/aliases.sh"
echo ""
echo "Verify installation:"
echo "  sqlite3 :trace \".tables\""
echo "  # Expected: query_log  query_notes  query_trace"
