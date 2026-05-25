#!/bin/bash
# =============================================================================
# SQL-ManyThing Phase 3 — aliases.sh
# Project-to-path mapping table.
# Source this file before any SQL-ManyThing query:
#   source ~/.hermes/manything/aliases.sh
#
# Format: MANYTHING_<PROJECT>="<absolute_path>"
# The sqlite3 wrapper uses these to resolve /manything/<project>/source.db
# to the real .srcidx/source.db location.
# =============================================================================

# --- Example projects (replace with your own) ---
# MANYTHING_hermes="/path/to/hermes"
# MANYTHING_neo4j="/path/to/neo4j"
# MANYTHING_unreal="/path/to/Engine"

# --- Active projects ---
# (add via: echo 'MANYTHING_<project>="<path>"' >> aliases.sh)
