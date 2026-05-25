"""uht_enrich — enrich manything DB from UE UHT .generated.h files.

Extracts from .generated.h: UCLASS, UINTERFACE, USTRUCT, UENUM + values,
UFUNCTION list, class hierarchy. No cymbal needed — pure text processing.

Usage:
  python3 uht_enrich.py \
    --db /path/to/.srcidx/source.db \
    --uht-dir Engine/Intermediate/Build/Win64/UnrealEditor/Inc \
    --source-prefix Engine/
"""

import sqlite3, re, json, os, sys, argparse, time

# Patterns — 4 type categories
RE_BEGIN = re.compile(
    r'//\s+\*+\s*Begin\s+(Class|Interface|ScriptStruct|Enum)\s+(\w+)'
)
RE_END = re.compile(r'//\s+\*+\s*End\s+(Class|Interface|ScriptStruct|Enum)\s+\w+')
RE_DECLARE_FUNCTION = re.compile(r'DECLARE_FUNCTION\((\w+)\)')
RE_DECLARE_CLASS2 = re.compile(
    r'DECLARE_CLASS2\(\s*(\w+)\s*,\s*(\w+)\s*,'
)
RE_FOREACH_ENUM = re.compile(
    r'op\(\s*(\w+(?:::\w+)?)\s*\)'
)
RE_MODULE_NAME = re.compile(
    r'TEXT\(\s*"/Script/(\w+)"\s*\)'
)
RE_CURRENT_FILE = re.compile(r'#define\s+CURRENT_FILE_ID\s+FID_(.+)')
RE_GENERATED_UINTERFACE = re.compile(r'GENERATED_UINTERFACE_BODY')
RE_STATIC_STRUCT = re.compile(r'Z_Construct_UScriptStruct_(\w+)')


def decode_fid(fid_path: str) -> str:
    """Decode FID_Engine_Source_..._h -> Engine/Source/.../File.h"""
    path = fid_path.replace('_', '/')
    for ext in ['/h', '/cpp', '/cs']:
        if path.endswith(ext):
            path = path[:-(len(ext))] + '.' + ext[1:]
            break
    return path


def find_uht_files(uht_dir: str) -> list[str]:
    """Find all */UHT/*.generated.h under uht_dir."""
    results = []
    try:
        for module in os.scandir(uht_dir):
            if not module.is_dir():
                continue
            uht_path = os.path.join(module.path, 'UHT')
            try:
                for f in os.scandir(uht_path):
                    if f.name.endswith('.generated.h') and f.is_file():
                        results.append(f.path)
            except (FileNotFoundError, PermissionError):
                continue
    except FileNotFoundError:
        pass
    return sorted(results)


def parse_uht_file(filepath: str) -> dict | None:
    """Parse .generated.h — return {source_path, module, symbols} or None."""

    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception:
        return None

    # Source file path from CURRENT_FILE_ID
    m = RE_CURRENT_FILE.search(content)
    if not m:
        return None
    source_path = decode_fid(m.group(1))

    # Module name from dir structure (fallback)
    module_name = os.path.basename(os.path.dirname(os.path.dirname(filepath)))

    # Try exact module name from TEXT("/Script/Module")
    m = RE_MODULE_NAME.search(content)
    if m:
        module_name = m.group(1)

    symbols = []

    # State machine: walk lines, track current block
    current_type = None       # 'class', 'interface', 'struct', 'enum'
    current_name = None
    current_parent = None
    current_functions = []
    current_values = []        # enum values
    current_start_line = 0
    is_interface = False

    for lineno, line in enumerate(content.split('\n'), 1):
        # --- BEGIN marker ---
        m = RE_BEGIN.search(line)
        if m:
            # Flush previous block
            if current_name:
                flush_block(symbols, current_type, current_name, current_parent,
                            current_functions, current_values, current_start_line,
                            module_name, is_interface)

            raw_type = m.group(1)
            current_name = m.group(2)
            current_type = {
                'Class': 'class',
                'Interface': 'interface',
                'ScriptStruct': 'struct',
                'Enum': 'enum',
            }[raw_type]
            current_parent = None
            current_functions = []
            current_values = []
            current_start_line = lineno
            is_interface = (raw_type == 'Interface')
            continue

        # --- Parent (UCLASS / UINTERFACE only) ---
        if current_type in ('class', 'interface') and current_name:
            m = RE_DECLARE_CLASS2.search(line)
            if m and m.group(1) == current_name:
                current_parent = m.group(2)

        # --- UINTERFACE marker ---
        if current_type == 'interface' and RE_GENERATED_UINTERFACE.search(line):
            is_interface = True

        # --- UFUNCTION thunks (UCLASS and Blueprint-capable UINTERFACE) ---
        if current_type in ('class', 'interface'):
            m = RE_DECLARE_FUNCTION.search(line)
            if m:
                fn_name = m.group(1)
                if fn_name.startswith('exec'):
                    fn_name = fn_name[4:]
                if fn_name not in current_functions:
                    current_functions.append(fn_name)

        # --- Enum values ---
        if current_type == 'enum':
            m = RE_FOREACH_ENUM.search(line)
            if m:
                val = m.group(1)
                if '::' in val:
                    val = val.split('::')[1]  # strip enum name prefix
                if val not in current_values:
                    current_values.append(val)

        # --- END marker ---
        m = RE_END.search(line)
        if m and current_name:
            flush_block(symbols, current_type, current_name, current_parent,
                        current_functions, current_values, current_start_line,
                        module_name, is_interface)
            current_type = None
            current_name = None
            current_parent = None
            current_functions = []
            current_values = []
            current_start_line = 0
            is_interface = False

    # Flush last (unclosed) block
    if current_name:
        flush_block(symbols, current_type, current_name, current_parent,
                    current_functions, current_values, current_start_line,
                    module_name, is_interface)

    if not symbols:
        return None

    return {
        'source_path': source_path,
        'module': module_name,
        'symbols': symbols,
    }


def flush_block(symbols: list, kind: str, name: str, parent: str | None,
                functions: list, values: list, start_line: int,
                module: str, is_interface: bool):
    """Emit symbol entries for one type block."""

    entry = {
        'name': name,
        'kind': kind,
        'uht_module': module,
        'start_line': start_line,
    }

    if kind == 'interface':
        entry['kind'] = 'interface'
        entry['uht_interface'] = True
    elif kind == 'struct':
        entry['kind'] = 'struct'
    elif kind == 'enum':
        entry['kind'] = 'enum'
        if values:
            entry['uht_values'] = values
        symbols.append(entry)
        return  # enums don't have functions to add
    elif kind == 'class':
        entry['kind'] = 'class'

    if parent:
        if kind == 'interface':
            entry['parent'] = parent
        else:
            entry['parent'] = parent

    if functions:
        entry['uht_functions'] = functions

    symbols.append(entry)

    # Individual function entries
    for fn in functions:
        symbols.append({
            'name': fn,
            'kind': 'function',
            'uht_class': name,
            'uht_module': module,
        })


def resolve_source_row(cursor, src_path: str):
    """Resolve decoded UHT FID path to a row in files.

    UHT encodes both path separators and literal underscores as `_` in
    CURRENT_FILE_ID. decode_fid() chooses separators, which is correct for most
    paths but wrong for headers such as AnimBlueprintExtension_Base.h. When an
    exact lookup fails, progressively join trailing path components with `_`
    and retry against the DB.
    """
    candidates = [src_path, src_path.replace('/', '\\')]
    parts = src_path.split('/')
    for i in range(len(parts) - 1, 0, -1):
        candidate = '/'.join(parts[:i] + ['_'.join(parts[i:])])
        candidates.append(candidate)
        candidates.append(candidate.replace('/', '\\'))

    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        cursor.execute("SELECT id, size, mtime, path FROM files WHERE path = ?", (candidate,))
        row = cursor.fetchone()
        if row is not None:
            return row, candidate
    return None, None


def enrich(db_path: str, uht_dir: str, source_prefix: str, batch_size: int):
    """Main enrich flow."""
    all_uht_files = find_uht_files(uht_dir)
    print(f"UHT files: {len(all_uht_files)}")

    if not all_uht_files:
        print("No UHT files found — check --uht-dir path")
        return

    parsed = []
    for fpath in all_uht_files:
        result = parse_uht_file(fpath)
        if result and result['symbols']:
            parsed.append(result)

    print(f"Parsed: {len(parsed)} files with symbols")

    # Group by source file
    source_symbols: dict[str, list] = {}
    for p in parsed:
        src = p['source_path']
        if source_prefix and src.startswith(source_prefix):
            src = src[len(source_prefix):]
        source_symbols.setdefault(src, []).extend(p['symbols'])

    print(f"Unique source files: {len(source_symbols)}")

    # Batch update DB
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    total_updated = 0
    all_src_paths = sorted(source_symbols.keys())
    for i in range(0, len(all_src_paths), batch_size):
        batch = all_src_paths[i:i + batch_size]
        t0 = time.time()

        for src_path in batch:
            syms = source_symbols[src_path]
            row, resolved_path = resolve_source_row(c, src_path)
            if row is None:
                continue
            fid, size, mtime, db_path_rel = row
            key = f"{size}:{mtime}" if size else f"uht:{len(syms)}"

            if resolved_path and resolved_path != src_path:
                for sym in syms:
                    sym.setdefault('uht_decoded_source_path', src_path)

            c.execute(
                "INSERT OR REPLACE INTO file_enrich (file_id, file_key, symbols) VALUES (?, ?, ?)",
                (fid, key, json.dumps(syms)),
            )
            total_updated += 1

        conn.commit()
        elapsed = time.time() - t0
        print(f"  batch {i // batch_size}: {len(batch)} files in {elapsed:.1f}s")

    conn.close()
    print(f"Enriched: {total_updated} files")
    return total_updated


def main():
    parser = argparse.ArgumentParser(description="Enrich manything DB from UE UHT files")
    parser.add_argument("--db", required=True, help="Path to .srcidx/source.db")
    parser.add_argument("--uht-dir", required=True,
                        help="UHT Inc directory (e.g., Engine/Intermediate/Build/Win64/UnrealEditor/Inc)")
    parser.add_argument("--source-prefix", default="Engine/",
                        help="Path prefix to strip from source paths (default: Engine/)")
    parser.add_argument("--batch", type=int, default=200,
                        help="DB update batch size (default: 200)")
    args = parser.parse_args()

    db_path = os.path.realpath(args.db)
    if not os.path.isfile(db_path):
        print(f"Error: DB not found: {db_path}")
        sys.exit(1)

    uht_dir = os.path.realpath(args.uht_dir)
    if not os.path.isdir(uht_dir):
        print(f"Error: UHT dir not found: {uht_dir}")
        sys.exit(1)

    t0 = time.time()
    enriched = enrich(db_path, uht_dir, args.source_prefix, args.batch)
    print(f"Total: {enriched} files in {time.time() - t0:.1f}s")


if __name__ == '__main__':
    main()
