# Module: MCP Server

## Scope

FastMCP server entry point: creates the MCP instance, imports all tool/resource modules, calls their `register()` functions, and runs the server. Also includes `shared.py` which bridges the MCP layer to the extractor layer.

NOT responsible for: individual tool logic (mcp-tools module), extractor internals (extraction/vault/search modules).

## Provides

### From `server.py`:
- FastMCP instance named `"cyberbrain"` with 11 registered tools, 1 resource, 2 prompts.
- Entry point: `python3 server.py` starts the MCP server (stdio transport).

### From `shared.py`:
- `_load_config(cwd="") -> dict` — Wraps `resolve_config()` with default cwd of `$HOME`.
- `_get_search_backend(config) -> SearchBackend | None` — Lazy-loaded, module-level cached search backend.
- `_parse_frontmatter(content) -> dict` — YAML frontmatter extraction (own implementation).
- `_move_to_trash(file_path, vault, config) -> Path` — Soft delete: moves file to `config["trash_folder"]` preserving vault-relative structure. Numeric suffix on collision.
- `_prune_index(config) -> int` — Removes stale index entries. Delegates to backend.
- `_index_paths(paths, config) -> int` — Indexes a list of note paths. Reads frontmatter from each file.
- `_relpath(path, vault_path) -> str` — Convenience wrapper for `os.path.relpath`.
- Re-exports from extractor layer: `_extract_beats`, `parse_jsonl_transcript`, `write_beat`, `autofile_beat`, `write_journal_entry`, `BackendError`, `_resolve_config`, `_call_claude_code_backend`, `RUNS_LOG_PATH`.

### From `resources.py`:
- `cyberbrain://guide` resource — Behavioral guide for Claude Desktop/Code describing when to call each tool.
- `orient` prompt — Session-start orientation: loads guide + triggers `cb_status`.
- `recall` prompt — Mid-session vault scan for unfamiliar topics.

## Requires

- `resolve_config(cwd)` (from: config via extract_beats re-export) — Config loading
- `extract_beats`, `write_beat`, `autofile_beat`, etc. (from: extraction/vault via extract_beats) — Core extractor functions
- `_call_claude_code` (from: backends via extract_beats) — Direct backend access for recall synthesis
- `get_search_backend(config)` (from: search) — Search backend initialization
- FastMCP v3 library — `from fastmcp import FastMCP`

## Boundary Rules

- `server.py` is run as `python -m cyberbrain.mcp.server` via the package entry point.
- `shared.py` imports from `cyberbrain.extractors.*` — requires the package to be installed or `src/` on `sys.path`.
- `_get_search_backend()` is a module-level singleton with no invalidation mechanism.
- `_move_to_trash()` uses `Path.rename()` — same-filesystem move only (vault and trash must be on same volume).
- Trash folder defaults to `.trash` (dotfolder, invisible to Obsidian by default).
- The behavioral guide (`resources.py`) adapts to `config["proactive_recall"]` and `config["desktop_capture_mode"]`.

## Internal Design Notes

- Files: `src/cyberbrain/mcp/server.py`, `src/cyberbrain/mcp/shared.py`, `src/cyberbrain/mcp/resources.py`
- Registration pattern: each tool/resource module exposes `register(mcp: FastMCP) -> None`
- Modules are imported as `cyberbrain.mcp.shared`, `cyberbrain.mcp.tools.*`, `cyberbrain.mcp.resources` via the standard package layout
