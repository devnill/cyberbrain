# Module: Extraction

## Scope

Transcript parsing and LLM-based beat extraction. Converts raw session transcripts (JSONL format) into structured beat dicts by calling an LLM with extraction prompts.

Also serves as the CLI entry point (`extract_beats.py`) and re-export hub for all extractor submodules.

NOT responsible for: vault writing (vault module), LLM communication (backends module), search indexing (search module), filing decisions (autofile in vault module).

## Provides

### From `extractor.py`:
- `extract_beats(transcript_text: str, config: dict, trigger: str, cwd: str) -> list[dict]` — Core extraction: reads vault CLAUDE.md, loads prompts, calls LLM, parses JSON response. Returns list of beat dicts.

### From `transcript.py`:
- `parse_jsonl_transcript(transcript_path: str) -> str` — Parses JSONL transcript file into plain-text conversation. Extracts user/assistant text blocks; skips tool_use, tool_result, thinking blocks.

### From `frontmatter.py`:
- `parse_frontmatter(content: str) -> dict` — Extract YAML frontmatter from markdown content string.
- `read_frontmatter(path: str) -> dict` — Read YAML frontmatter from a file path.
- `read_frontmatter_tags(path) -> set` — Read tags field specifically (regex-based, no YAML dependency for this path).
- `normalise_list(value) -> list` — Coerce JSON-string or Python list to `list[str]`.
- `derive_id(note_path: str) -> str` — SHA-256-based stable ID from path.

### From `extract_beats.py` (entry point):
- Re-exports all symbols from config, backends, transcript, vault, extractor, autofile, frontmatter, run_log modules.
- `main()` — CLI entry point with argparse: `--transcript`, `--beats-json`, `--session-id`, `--trigger`, `--cwd`, `--dry-run`.

## Requires

- `call_model(system_prompt, user_message, config) -> str` (from: backends) — LLM invocation
- `load_prompt(filename) -> str` (from: config) — Prompt template loading
- `read_vault_claude_md(vault_path) -> str | None` (from: vault) — Vault type vocabulary context

## Boundary Rules

- Transcript text is truncated to `MAX_TRANSCRIPT_CHARS` (150K) keeping the tail (most recent content).
- LLM response is parsed as JSON using `raw_decode` (tolerates trailing text after JSON).
- Code fences in LLM response are stripped before parsing.
- Returns empty list on any parse failure — never raises to caller.
- `frontmatter.py` uses `yaml.safe_load` when available; falls back to regex parsing for tags.
- Dry-run mode in `main()` executes the full extraction pipeline but skips all writes.

## Internal Design Notes

- Files: `extractors/extractor.py` (72 lines), `extractors/transcript.py` (64 lines), `extractors/frontmatter.py` (97 lines), `extractors/extract_beats.py` (257 lines)
- `extract_beats.py` is both a CLI script and an import hub — all external callers (MCP shared.py, import.py, tests) import via this file
- Beat JSON schema: `{title, type, scope, summary, tags, body, durability, relations}`
- The `trigger` parameter is passed through to the user prompt but not used for routing logic
