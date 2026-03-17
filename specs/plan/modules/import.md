# Module: Import

## Scope

Batch import of conversation exports from Claude Desktop and ChatGPT into the cyberbrain vault. Parses platform-specific export formats, extracts beats from each conversation, and writes them to the vault using the standard extraction pipeline.

NOT responsible for: extraction logic (extraction module), vault writing (vault module). Import delegates to `extract_beats` for all LLM calls and vault writes.

## Provides

- `scripts/import.py` — CLI script supporting three formats:
  - `--format claude` — Claude Desktop data export (conversations.json)
  - `--format claude-web` — Claude web export
  - `--format chatgpt` — ChatGPT data export
- Resumable: state file at `~/.claude/cyberbrain/import-state.json` tracks processed conversation UUIDs. Re-runs skip already-imported conversations.
- Supports `--dry-run`, `--limit N`, `--since YYYY-MM-DD` filters.

## Requires

- `cyberbrain.extractors.extract_beats` module (from: extraction) — Uses `extract_beats()`, `write_beat()`, `autofile_beat()`, `resolve_config()`.

## Boundary Rules

- All vault writes go through the extractor layer — `import.py` never writes vault files directly.
- Conversations below `MIN_CHARS_FOR_EXTRACTION` (100 chars) are skipped.
- Transcript text is truncated to `MAX_TRANSCRIPT_CHARS` (150K chars) keeping the tail.
- State file enables full resumability — interrupted imports can be restarted.
- Import uses the global config (no project config) — all beats route to inbox or via autofile.

## Internal Design Notes

- File: `scripts/import.py` (698 lines)
- Imports `cyberbrain.extractors.extract_beats` via package import; exits with a clear message if the package is not installed
- State file is a JSON dict mapping conversation UUIDs to import timestamps
- Claude Desktop format: nested JSON with `chat_messages` array
- ChatGPT format: nested JSON with `mapping` dict containing message nodes
