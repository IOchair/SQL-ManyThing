"""SQL-ManyThing — Phase 2: Java build-file enrich (Maven pom.xml + .class files).
Usage: python3 enrich_java_build.py /path/to/project

Two enrich layers (priority order, matching reference doc):

  Level 1 (primary, requires JDK): Parse .class files in target/ dirs via javap.
    Resolved generic type signatures, annotation info, access flags.
    Writes into enrich_java_classfiles table.

  Level 2 (supplement, always runs): Parse Maven pom.xml files → module hierarchy tree.
    Each module node: artifactId, parent, groupId, packaging type.
    Parent-child edges: parent→child module.
    Writes into enrich_java_modules table.

Output tables:
  enrich_java_classfiles — class-level type info (only when JDK + .class files)
  enrich_java_modules    — Maven module hierarchy (always written)
"""

import sqlite3
import os
import sys
import time
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

MAVEN_NS = "http://maven.apache.org/POM/4.0.0"
SKIP_DIRS = {".git", "node_modules", "dist", ".venv", "venv", "__pycache__", "target"}


def _ns(tag):
    return f"{{{MAVEN_NS}}}{tag}"


def parse_pom(path: str) -> dict | None:
    """Extract module metadata from a pom.xml."""
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except Exception:
        return None

    get = lambda tag: (root.findtext(_ns(tag)) or "").strip()

    info = {
        "groupId": get("groupId"),
        "artifactId": get("artifactId"),
        "version": get("version"),
        "packaging": get("packaging") or "jar",
        "parent_groupId": "",
        "parent_artifactId": "",
        "parent_version": "",
        "modules": [],
    }

    # Parent reference
    parent = root.find(_ns("parent"))
    if parent is not None:
        info["parent_groupId"] = (parent.findtext(_ns("groupId")) or "").strip()
        info["parent_artifactId"] = (parent.findtext(_ns("artifactId")) or "").strip()
        info["parent_version"] = (parent.findtext(_ns("version")) or "").strip()

    # Resolve groupId inheritance (child can omit groupId/version, inherit from parent)
    if not info["groupId"]:
        info["groupId"] = info["parent_groupId"]
    if not info["version"]:
        info["version"] = info["parent_version"]

    # Child modules
    modules_el = root.find(_ns("modules"))
    if modules_el is not None:
        for m in modules_el.findall(_ns("module")):
            name = m.text.strip() if m.text else ""
            if name:
                info["modules"].append(name)

    return info


def enrich_modules(target: str, db: str) -> int:
    """Level 1: Parse all pom.xml files → module hierarchy."""
    conn = sqlite3.connect(db)
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS enrich_java_modules (
            module_id TEXT PRIMARY KEY,
            artifact_id TEXT NOT NULL,
            group_id TEXT NOT NULL,
            parent_id TEXT,
            packaging TEXT DEFAULT 'jar',
            rel_path TEXT NOT NULL
        );
    """)
    conn.commit()

    # Find all pom.xml files (excluding .git, target dirs)
    pom_files = []
    for root, dirs, fnames in os.walk(target):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        for fname in fnames:
            if fname == "pom.xml":
                pom_files.append(os.path.join(root, fname))

    print(f"  pom.xml files found: {len(pom_files)}")

    # Phase 1: parse all poms, build module map
    modules: dict[str, dict] = {}
    for pom_path in sorted(pom_files):
        info = parse_pom(pom_path)
        if info is None:
            continue
        mid = f"{info['groupId']}:{info['artifactId']}"
        rel = os.path.relpath(pom_path, target)
        modules[mid] = {
            "id": mid,
            "artifactId": info["artifactId"],
            "groupId": info["groupId"],
            "parentId": f"{info['parent_groupId']}:{info['parent_artifactId']}" if info['parent_artifactId'] else "",
            "packaging": info["packaging"],
            "relPath": rel,
            "modules": info["modules"],
        }

    # Phase 2: resolve parent-child edges (including module refs in parent pom)
    for mid, mod in modules.items():
        # Child modules (from <modules> in pom.xml)
        for child_name in mod["modules"]:
            child_dir = os.path.dirname(os.path.join(target, mod["relPath"]))
            child_pom = os.path.join(child_dir, child_name, "pom.xml")
            if os.path.isfile(child_pom):
                child_info = parse_pom(child_pom)
                if child_info:
                    child_id = f"{child_info['groupId']}:{child_info['artifactId']}"
                    if child_id in modules:
                        modules[child_id]["parentId"] = mid

    # Phase 3: write to DB
    c.execute("DELETE FROM enrich_java_modules")
    inserted = 0
    for mod in modules.values():
        c.execute(
            "INSERT OR REPLACE INTO enrich_java_modules "
            "(module_id, artifact_id, group_id, parent_id, packaging, rel_path) VALUES (?, ?, ?, ?, ?, ?)",
            (mod["id"], mod["artifactId"], mod["groupId"],
             mod["parentId"] or None, mod["packaging"], mod["relPath"]),
        )
        inserted += 1
    conn.commit()
    conn.close()
    return inserted


def enrich_classfiles(target: str, db: str) -> int:
    """Level 2 (optional): Parse .class files in target/ directories via javap.

    Requires JDK installed and the project to have been built (target/ dirs exist).
    """
    import subprocess
    import json

    # Check javap availability
    try:
        subprocess.run(["javap", "-version"], capture_output=True, timeout=5)
    except Exception:
        print("  javap not found — skipping Level 2 (.class parsing)")
        return 0

    conn = sqlite3.connect(db)
    c = conn.cursor()
    c.executescript("""
        DROP TABLE IF EXISTS enrich_java_classfiles;
        CREATE TABLE IF NOT EXISTS enrich_java_classfiles (
            class_id TEXT PRIMARY KEY,
            file_id INTEGER REFERENCES files(id),
            class_name TEXT NOT NULL,
            super_class TEXT,
            interfaces TEXT,
            method_signatures TEXT,
            field_types TEXT,
            access_flags TEXT,
            source TEXT
        );
    """)
    conn.commit()

    # Find .class files (excluding test-classes)
    class_files = []
    for root, dirs, fnames in os.walk(target):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if "/test-classes" in root or "\\test-classes" in root:
            continue
        for fname in fnames:
            if fname.endswith(".class") and fname != "module-info.class":
                class_files.append(os.path.join(root, fname))

    if not class_files:
        print("  no .class files found — skip Level 2")
        conn.close()
        return 0

    print(f"  .class files found: {len(class_files)}")

    inserted = 0
    for cf_path in class_files:
        try:
            # Derive classpath: find Maven output dir (target/classes or target/test-classes)
            cf_dir = os.path.dirname(cf_path)
            parts = cf_dir.split(os.sep)
            cp = cf_dir
            if "target" in parts:
                idx = parts.index("target")
                cp = os.sep.join(parts[: idx + 1]) + os.sep + "classes"
                if not os.path.isdir(cp):
                    cp = cf_dir  # fallback to .class dir
            proc = subprocess.run(
                ["javap", "-p", "-cp", cp, cf_path],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode != 0:
                continue
            output = proc.stdout
            # javap output: first line is "Compiled from 'Foo.java'" or "public class Foo ..."
            lines = output.splitlines()
            if not lines:
                continue
            # Extract class declaration line
            class_decl = lines[0]
            if class_decl.startswith("Compiled from"):
                class_decl = lines[1] if len(lines) > 1 else class_decl

            c.execute(
                "INSERT OR REPLACE INTO enrich_java_classfiles "
                "(class_id, class_name, method_signatures, source) VALUES (?, ?, ?, ?)",
                (cf_path, class_decl, output, cf_path),
            )
            inserted += 1
        except Exception:
            continue

        if inserted % 500 == 0:
            conn.commit()

    conn.commit()
    conn.close()
    return inserted


def main():
    parser = argparse.ArgumentParser(description="SQL-ManyThing Phase 2: Java build-file enrich")
    parser.add_argument("target", help="Project root path")
    parser.add_argument("--skip-classes", action="store_true",
                        help="Skip Level 2 (.class file parsing, even if JDK available)")
    args = parser.parse_args()

    target = os.path.realpath(args.target)
    db = os.path.join(target, ".srcidx", "source.db")
    if not os.path.isdir(target):
        print(f"Error: {target} not found")
        sys.exit(1)
    if not os.path.isfile(db):
        print(f"Error: DB not found ({db}). Run Phase 1 first.")
        sys.exit(1)

    print(f"SQL-ManyThing Phase 2 — Java build-file enrich")
    print(f"Target: {target}")

    # Level 1: .class file signatures (primary, requires JDK)
    if not args.skip_classes:
        t0 = time.time()
        m = enrich_classfiles(target, db)
        if m:
            print(f"  Classes: {m} in {time.time()-t0:.1f}s")
        else:
            print(f"  Classes: skipped (no JDK or no .class files)")

    # Level 2: pom.xml module hierarchy (supplement, always runs)
    t0 = time.time()
    n = enrich_modules(target, db)
    print(f"  Modules: {n} in {time.time()-t0:.1f}s")

    # Summary
    conn = sqlite3.connect(db)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM enrich_java_modules")
    mods = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='enrich_java_classfiles'")
    has_class = c.fetchone()[0] > 0
    if has_class:
        c.execute("SELECT COUNT(*) FROM enrich_java_classfiles")
        classes = c.fetchone()[0]
        print(f"  Total: {mods} modules, {classes} classfiles")
    else:
        print(f"  Total: {mods} modules")
    conn.close()


if __name__ == "__main__":
    main()
