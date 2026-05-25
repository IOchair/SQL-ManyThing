# pending.jsonl Importer — Parsing Logic

## Format

```
<unix_timestamp>|<project>|<virtual_db_path>
<multi-line SQL text>
---
```

Each record is 3 logical parts: header line (pipe-delimited), SQL text (may span N lines), separator line (`---`).

## Parser algorithm (SQL-ManyThing-query-log import)

```
i = 0
while i < len(lines):
    if line matches "digits|text|text":       # header heuristic
        parse ts, project, db_path
        i += 1
        sql_parts = []
        while i < len(lines):
            if line.strip() == "---":
                i += 1  # skip separator
                break
            sql_parts.append(line.rstrip("\n"))
            i += 1
        sql = "\n".join(sql_parts).strip()
        if sql:
            INSERT INTO query_log(timestamp, project, db_path, sql_text, imported_at)
        continue
    i += 1
```

## Historical bug (2026-05-24)

Old importer read `lines[i + 1]` only (single line), skipped rest until `i += 3`. Multi-line SQL thus stored with sql_text="" (length 0). Fixed by collecting all lines between header and `---`.
