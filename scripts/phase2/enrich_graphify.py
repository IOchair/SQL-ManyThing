"""SQL-ManyThing — graphify AST enrich phase (Phase 2 add-on).
Usage: python3 manything_graphify_enrich.py /path/to/project

Runs graphify extractors on files cymbal can't handle:
  - .md → extract_markdown (heading tree + code blocks)
  - .rs → _extract_generic Rust (functions, traits, impls, structs)

Writes into enrich_graphify_nodes + enrich_graphify_edges tables.
"""

import sqlite3
import os
import sys
import time
from pathlib import Path

# Prefer graphify when installed, but keep this script runnable on fresh WSL
# checkouts where the original macOS-only ~/graphify checkout is absent.
try:
    sys.path.insert(0, os.path.expanduser("~/graphify"))
    from graphify.extract import (  # type: ignore
        extract_markdown,
        extract_rust,
        extract_python,
        extract_java,
        extract_js,
        _extract_python_rationale,
    )
except Exception as exc:  # pragma: no cover - exercised by smoke scripts
    import re

    GRAPHIFY_IMPORT_ERROR = exc

    def _line_number(text: str, offset: int) -> int:
        return text.count("\n", 0, offset) + 1

    def extract_markdown(path: Path):
        text = path.read_text(encoding="utf-8", errors="replace")
        nodes = []
        edges = []
        stack = []
        for m in re.finditer(r"^(#{1,6})\s+(.+)$", text, re.MULTILINE):
            level = len(m.group(1))
            title = m.group(2).strip()
            line = _line_number(text, m.start())
            node_id = f"md:{line}:{level}:{title}"
            nodes.append({
                "id": node_id,
                "label": title,
                "file_type": "document",
                "source_location": f"L{line}",
            })
            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                edges.append({"source": stack[-1][1], "target": node_id, "relation": "contains"})
            stack.append((level, node_id))
        return {"nodes": nodes, "edges": edges}

    def _extract_code_like(path: Path, language: str):
        text = path.read_text(encoding="utf-8", errors="replace")
        patterns = [
            ("function", r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\("),
            ("class", r"(?:export\s+)?class\s+([A-Za-z_$][\w$]*)"),
            ("const", r"(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*="),
            ("interface", r"(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)"),
            ("type", r"(?:export\s+)?type\s+([A-Za-z_$][\w$]*)\s*="),
        ]
        nodes = []
        for kind, pat in patterns:
            for m in re.finditer(pat, text):
                name = m.group(1)
                line = _line_number(text, m.start())
                nodes.append({
                    "id": f"{kind}:{line}:{name}",
                    "label": f"{name} ({kind})",
                    "file_type": "code",
                    "source_location": f"L{line}",
                })
        return {"nodes": nodes, "edges": []}

    def extract_js(path: Path):
        return _extract_code_like(path, "javascript")

    def extract_python(path: Path):
        text = path.read_text(encoding="utf-8", errors="replace")
        nodes = []
        for kind, pat in [("function", r"^\s*def\s+([A-Za-z_]\w*)\s*\("), ("class", r"^\s*class\s+([A-Za-z_]\w*)")]:
            for m in re.finditer(pat, text, re.MULTILINE):
                name = m.group(1)
                line = _line_number(text, m.start())
                nodes.append({"id": f"{kind}:{line}:{name}", "label": f"{name} ({kind})", "file_type": "code", "source_location": f"L{line}"})
        return {"nodes": nodes, "edges": []}

    def extract_java(path: Path):
        return _extract_code_like(path, "java")

    def extract_rust(path: Path):
        return _extract_code_like(path, "rust")

EXTRACTORS = {
    ".md": extract_markdown,
    ".rs": extract_rust,
    ".py": extract_python,
    ".java": extract_java,
    ".js": extract_js,
    ".ts": extract_js,
}


def ensure_tables(conn):
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS enrich_graphify_nodes (
            file_id INTEGER REFERENCES files(id),
            node_id TEXT,
            label TEXT,
            file_type TEXT,
            source_location TEXT,
            PRIMARY KEY (file_id, node_id)
        );
        CREATE TABLE IF NOT EXISTS enrich_graphify_edges (
            file_id INTEGER REFERENCES files(id),
            source_node_id TEXT,
            target_node_id TEXT,
            relation TEXT,
            weight REAL DEFAULT 1.0
        );
        CREATE INDEX IF NOT EXISTS idx_eg_nodes_type ON enrich_graphify_nodes(file_type);
        CREATE INDEX IF NOT EXISTS idx_eg_nodes_label ON enrich_graphify_nodes(label);
        CREATE INDEX IF NOT EXISTS idx_eg_edges_rel ON enrich_graphify_edges(relation);
    """)
    conn.commit()


def enrich_project(target: str, db: str):
    conn = sqlite3.connect(db)
    ensure_tables(conn)
    c = conn.cursor()

    # Get files by extension
    target_path = Path(target)
    for ext, extractor in EXTRACTORS.items():
        print(f"\nExtracting {ext} files...")
        c.execute(
            "SELECT id, path FROM files WHERE ext = ? ORDER BY path",
            (ext,),
        )
        files = c.fetchall()
        if not files:
            print(f"  no {ext} files found")
            continue

        total_nodes = 0
        total_edges = 0
        skipped = 0

        for fid, relpath in files:
            abspath = os.path.join(target, relpath)
            if not os.path.isfile(abspath):
                skipped += 1
                continue

            # Check if already enriched (same mtime)
            st = os.stat(abspath)
            key = f"{st.st_size}:{int(st.st_mtime)}"
            c.execute(
                "SELECT 1 FROM file_enrich WHERE file_id = ? AND file_key = ?",
                (fid, key),
            )
            enriched = c.fetchone() is not None

            try:
                t0 = time.time()
                result = extractor(Path(abspath))
                elapsed = time.time() - t0
            except Exception as e:
                print(f"  ERROR {relpath}: {e}")
                skipped += 1
                continue

            nodes = result.get("nodes", [])
            edges = result.get("edges", [])

            if not nodes:
                continue

            # Clear old
            c.execute("DELETE FROM enrich_graphify_nodes WHERE file_id = ?", (fid,))
            c.execute("DELETE FROM enrich_graphify_edges WHERE file_id = ?", (fid,))

            # Insert nodes
            for n in nodes:
                nid = n.get("id", "")
                label = n.get("label", "")
                file_type = n.get("file_type", "code")
                loc = n.get("source_location", "")
                c.execute(
                    "INSERT OR REPLACE INTO enrich_graphify_nodes "
                    "(file_id, node_id, label, file_type, source_location) VALUES (?, ?, ?, ?, ?)",
                    (fid, nid, label, file_type, loc),
                )

            # Insert edges
            for e in edges:
                src = e.get("source", "")
                tgt = e.get("target", "")
                rel = e.get("relation", "contains")
                wt = e.get("weight", 1.0)
                c.execute(
                    "INSERT INTO enrich_graphify_edges "
                    "(file_id, source_node_id, target_node_id, relation, weight) VALUES (?, ?, ?, ?, ?)",
                    (fid, src, tgt, rel, wt),
                )

            total_nodes += len(nodes)
            total_edges += len(edges)

            # Flush every 50 files
            if (total_nodes + total_edges) % 5000 == 0:
                conn.commit()

        conn.commit()
        print(f"  {ext}: {total_nodes} nodes, {total_edges} edges from {len(files)-skipped} files")

    # Summary
    c.execute("SELECT COUNT(*) FROM enrich_graphify_nodes")
    all_nodes = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM enrich_graphify_edges")
    all_edges = c.fetchone()[0]
    print(f"\nTotal enrich: {all_nodes} nodes, {all_edges} edges")
    conn.close()


if __name__ == "__main__":
    target = os.path.realpath(sys.argv[1])
    db = os.path.join(target, ".srcidx", "source.db")
    if not os.path.isdir(target):
        print(f"Error: {target} not found")
        sys.exit(1)
    if not os.path.isfile(db):
        print(f"Error: DB not found ({db})")
        sys.exit(1)
    print(f"Target: {target}")
    print(f"DB:     {db}")
    t0 = time.time()
    enrich_project(target, db)
    print(f"Total:  {time.time()-t0:.1f}s")
