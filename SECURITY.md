# Security and Privacy

## Data exposure risks

SQL-ManyThing indexes source code into a local SQLite database. This database
contains the full text of every indexed file.

### `source.db` (per-project)

- Location: `<project>/.srcidx/source.db`
- Contains: full file contents of all indexed files
- Risk: if committed to a repository or shared, exposes your source code

To delete:
```bash
rm -rf <project>/.srcidx
```

### `query_log.db` (global)

- Location: `~/.hermes/manything/query_log.db`
- Contains: logged SQL queries with snippets, paths, and project names
- Risk: query logs may contain proprietary terms, file paths, and code snippets

To delete:
```bash
rm -f ~/.hermes/manything/query_log.db
```

### `pending.jsonl` (temporary buffer)

- Location: `~/.hermes/manything/pending.jsonl`
- Contains: unimported query traces
- Risk: same as query_log.db

To clear:
```bash
rm -f ~/.hermes/manything/pending.jsonl
```

## Best practices

- Never commit `.srcidx/` directories to version control.
- Add `.srcidx/` to your project's `.gitignore`.
- Regularly review and clear `query_log.db` if you work with sensitive code.
- Consider running `VACUUM` after deleting large amounts of indexed data to reclaim disk space.
