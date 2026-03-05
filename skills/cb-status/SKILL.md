# cb-status

When the user invokes /cb-status, generate a cyberbrain system status report.

## Steps

1. **Read global config** to get vault_path and search_db_path:
   - Read `~/.claude/cyberbrain.json`

2. **Read recent runs log** (last 20 lines of `~/.claude/logs/cb-runs.jsonl`):
   - Use Bash: `tail -20 ~/.claude/logs/cb-runs.jsonl 2>/dev/null || echo ""`
   - Parse each line as JSON; skip malformed lines

3. **Query SQLite index stats** (if the DB exists):
   - Use Bash: `sqlite3 ~/.claude/cyberbrain/search-index.db "SELECT type, COUNT(*) FROM notes GROUP BY type ORDER BY COUNT(*) DESC;" 2>/dev/null || echo ""`
   - Use Bash: `sqlite3 ~/.claude/cyberbrain/search-index.db "SELECT COUNT(*) FROM relations;" 2>/dev/null || echo "0"`
   - Use Bash: `sqlite3 ~/.claude/cyberbrain/search-index.db "SELECT COUNT(*) FROM notes;" 2>/dev/null || echo "0"`

4. **Check for stale paths** (paths in DB that no longer exist on disk):
   - Use Bash: `sqlite3 ~/.claude/cyberbrain/search-index.db "SELECT path FROM notes;" 2>/dev/null | while IFS= read -r p; do [ -e "$p" ] || echo "$p"; done | wc -l | tr -d ' '`

5. **Read vector manifest** if it exists:
   - Read `~/.claude/cyberbrain/search-index-manifest.json`
   - Extract `model_name` and length of `id_map` array

6. **Format and output the status report** in this structure:

```
## Cyberbrain Status

### Recent Runs (last N)
| Time | Session | Project | Trigger | Beats | Duration |
|------|---------|---------|---------|-------|----------|
| 2026-03-04 15:11 | fd907b6b | cyberbrain | compact | 4/5 | 14.2s |
...

### Last Run — Beats Extracted
- **<title>** (<type> · <scope>) → <path>
- ⚠ <error message if any>

### Index Health
- Notes indexed: <total>
  - decision: 42, insight: 38, problem: 31, reference: 16
- Relations: <count>
- Stale paths: <count> (✓ all indexed notes exist on disk)
- Semantic vectors: <count> (model: TaylorAI/bge-micro-v2)   ← omit if no manifest

### Config
- Vault: /path/to/vault
- Inbox: AI/Claude-Sessions
- Backend: claude-code (claude-haiku-4-5)
```

## Graceful Handling

- If `~/.claude/logs/cb-runs.jsonl` does not exist: show "No runs recorded yet."
- If the SQLite DB does not exist: show "Index not found — run /cb-recall or /cb-extract to build it."
- If the manifest does not exist: omit the "Semantic vectors" line.
- Never error out — always produce a report with whatever data is available.
