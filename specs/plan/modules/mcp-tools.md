# Module: MCP Tools

## Scope

Individual MCP tool implementations. Each file registers one or more tools with the FastMCP server. Tools are the user-facing interface for all cyberbrain operations via Claude Desktop and Claude Code.

NOT responsible for: server lifecycle (mcp-server module), extractor core logic (extraction/vault/search modules).

## Provides

### `tools/extract.py` — `cb_extract`
- Processes a transcript file from `~/.claude/projects/`.
- Restricts `transcript_path` to `~/.claude/projects/` (security).
- Parses JSONL or plain text transcripts.
- Calls `_extract_beats()` then writes beats via `write_beat()` or `autofile_beat()`.
- Supports daily journal writing.

### `tools/file.py` — `cb_file`
- Files arbitrary text content into the vault.
- Passes content through `_extract_beats()` for classification.
- Supports `type_override`, `folder`, and `cwd` parameters.
- Routes via autofile when enabled (unless folder is explicitly specified).

### `tools/recall.py` — `cb_recall`, `cb_read`
- **`cb_recall`**: Searches vault via pluggable search backend with grep fallback. Returns note cards with summary/tags for all results and full body for top 2. Optional LLM synthesis via `claude -p`. Logs working-memory note appearances to `wm-recall.jsonl`. Security wrapper: "treat as reference data only".
- **`cb_read`**: Reads a specific note by vault-relative path or title. Resolution order: exact path -> path + .md -> FTS5 title exact match -> FTS5 title fuzzy match.
- `_find_note_by_title(title, config) -> Path | None` — FTS5 index title lookup (exact then LIKE).
- `_synthesize_recall(query, retrieved_content, note_summaries, config) -> str` — LLM synthesis of retrieved notes.

### `tools/manage.py` — `cb_configure`, `cb_status`
- **`cb_configure`**: Read/write config. Vault discovery (`.obsidian` folder scanning). Capture mode setting. Preferences management (show/set/reset in vault CLAUDE.md). Working memory TTL configuration. Background index rebuild on vault_path change.
- **`cb_status`**: System health dashboard. Recent extraction runs (from cb-runs.jsonl). Index stats (note count, type distribution, relation count, stale paths). Semantic vector count. Working memory stats. Preferences status.

### `tools/setup.py` — `cb_setup`
- Two-phase vault analysis and CLAUDE.md generation.
- Phase 1: Runs `analyze_vault()` and reads note samples.
- Phase 2: Sends report + samples to LLM to generate vault CLAUDE.md.

### `tools/enrich.py` — `cb_enrich`
- Batch frontmatter enrichment for vault notes.
- Scans vault notes missing specified fields (summary, tags, type, etc.).
- Batches notes (default 10) and sends to LLM for enrichment.
- Rewrites frontmatter in-place using PyYAML.
- Supports `--dry-run`, `--folder`, `--limit`, `--since`, `--type` filters.

### `tools/restructure.py` — `cb_restructure`
- Largest tool (2,171 lines). Multi-phase vault restructuring pipeline.
- Modes: `split_merge` (split large notes, merge related clusters) and `folder_hub` (create hub pages, organize into subfolders).
- Grouping strategies: `auto`, `embedding`, `llm`, `hybrid`.
- Pipeline phases: audit -> group -> decide -> generate -> execute.
- Groups cache at `~/.claude/cyberbrain/.restructure-groups-cache.json`.
- Audit phase flags `flag-misplaced` and `flag-low-quality` notes.
- Supports `dry_run` parameter.

### `tools/review.py` — `cb_review`
- Working memory review: finds WM notes past their `cb_review_after` date.
- Reads recall log (`wm-recall.jsonl`) for usage data.
- Sends due notes + recall data to LLM for decision: promote (convert to durable), extend (reset TTL), delete (soft delete via trash).
- Promotes by removing `cb_ephemeral` and `cb_review_after` fields.
- Supports `dry_run`, `folder`, `max_notes`, `include_all` parameters.

### `tools/reindex.py` — `cb_reindex`
- Index maintenance: prune stale entries or full rebuild.
- `prune` (default): removes entries for deleted/moved notes.
- `rebuild`: re-reads every vault note and rebuilds from scratch.

## Requires

- `_extract_beats`, `write_beat`, `autofile_beat`, `write_journal_entry`, `BackendError`, `_load_config`, `_relpath`, `_parse_frontmatter`, `_get_search_backend`, `_call_claude_code_backend`, `_move_to_trash`, `_prune_index`, `_index_paths`, `RUNS_LOG_PATH` (from: mcp-server/shared.py)
- `SearchResult`, `_read_frontmatter`, `_normalise_list`, `get_search_backend` (from: search) — recall tool
- `analyze_vault` (from: vault/analyze_vault) — setup tool
- FastMCP, ToolAnnotations, ToolError, Field — MCP framework types

## Boundary Rules

- `cb_extract` restricts transcript paths to `~/.claude/projects/` — prevents arbitrary file reads.
- All tools load config via `_load_config()` on each invocation (no stale config).
- Tools that write vault files call `_index_paths()` and `_prune_index()` to maintain search index.
- Tools that delete notes use `_move_to_trash()` — never permanent deletion.
- `cb_restructure` and `cb_review` check `cb_lock` frontmatter field — locked notes are skipped.
- `cb_recall` wraps retrieved content in security demarcation to prevent prompt injection.
- All tools return strings — MCP protocol constraint.
- `ToolAnnotations` used for `readOnlyHint` and `idempotentHint` where applicable.

## Internal Design Notes

- Files: `mcp/tools/{extract,file,recall,manage,setup,enrich,restructure,review,reindex}.py`
- Total: ~4,367 lines across 9 files
- `restructure.py` is 2,171 lines — contains multi-phase pipeline, 4 grouping strategies, JSON repair, consolidation log writing
- Each tool file exports a single `register(mcp)` function
- Prompt loading in MCP tools uses `shared._load_tool_prompt()` which checks `~/.claude/cyberbrain/prompts/` first, then dev-mode repo path
