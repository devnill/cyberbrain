# Module: Config

## Scope

Configuration loading, merging, and prompt file loading. Responsible for the two-level config system (global + per-project) and locating prompt template files.

NOT responsible for: config file writing (handled by `mcp/tools/manage.py`), vault CLAUDE.md reading (handled by `vault.py`).

## Provides

- `load_global_config() -> dict` — Reads `~/.claude/cyberbrain/config.json`; validates required fields (`vault_path`, `inbox`); resolves and validates vault path; exits on missing/invalid config.
- `find_project_config(cwd: str) -> dict` — Walks up from `cwd` looking for `.claude/cyberbrain.local.json`; stops at home directory; returns empty dict if not found.
- `resolve_config(cwd: str) -> dict` — Merges global + project config (project overrides global via flat dict merge).
- `load_prompt(filename: str) -> str` — Reads a prompt markdown file from `PROMPTS_DIR` (`extractors/../prompts/`); exits on missing file.
- `GLOBAL_CONFIG_PATH` — `Path.home() / ".claude" / "cyberbrain" / "config.json"`
- `PROJECT_CONFIG_NAME` — `"cyberbrain.local.json"`
- `PROMPTS_DIR` — `Path(__file__).parent.parent / "prompts"`

## Requires

- Standard library only (`json`, `sys`, `pathlib`)

## Boundary Rules

- `load_global_config()` calls `sys.exit(0)` on missing or invalid config — this is intentional for the hook path where failing silently is better than crashing the parent Claude session.
- Project config is searched up the directory tree, stopping at `$HOME`.
- Config merging is a flat dict update — nested dicts are not deep-merged.
- `load_prompt()` exits on missing prompt file rather than raising — consistent with the "hooks always exit 0" pattern.

## Internal Design Notes

- File: `extractors/config.py` (97 lines)
- `REQUIRED_GLOBAL_FIELDS = ["vault_path", "inbox"]`
- Vault path validation rejects: placeholder paths, non-existent paths, home directory, filesystem root
- MCP tools use `shared._load_config()` which wraps `resolve_config()`
