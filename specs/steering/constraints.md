# Constraints

## Technology Constraints
1. **Python 3.8+ for all backend code.** The extractor, MCP server, search backends, and scripts are all Python. No other runtime.
2. **FastMCP v3 for MCP server.** Stdio transport. Compatible with Claude Desktop, Claude Code, Cursor, Zed.
3. **Obsidian-compatible markdown.** All vault notes must be valid Obsidian markdown with YAML frontmatter. Wikilinks use `[[Title]]` shortest-path resolution. No plugin dependencies — everything must work in vanilla Obsidian.
4. **SQLite for derived data.** Search index, FTS5, and vector storage use SQLite. No external database servers in the current architecture (though this constraint may be revisited for hosted deployment).
5. **Filename character restrictions.** Beat titles cannot contain `#`, `[`, `]`, or `^` — these break Obsidian wikilink resolution.

## Design Constraints
6. **All vault writes go through Python.** `extract_beats.py` (or `import.py`) is the single write path. MCP tools never write vault files directly. This ensures consistent path validation, logging, and error handling.
7. **Hooks always exit 0.** PreCompact and SessionEnd hooks must never block the parent Claude Code session, even on failure.
8. **Subprocess env var stripping.** When spawning `claude -p`, strip `CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` to prevent subprocess hangs.
9. **Subprocess runs from neutral CWD.** `claude -p` subprocess runs from `~/.claude/cyberbrain/` (no CLAUDE.md) to prevent project config injection.
10. **Soft delete only.** All vault note deletions go through `_move_to_trash()`. Notes are moved to the trash folder, never permanently deleted. Vault-relative structure is preserved in trash.
11. **Single session dedup.** Extraction is deduplicated by session ID via `cb-extract.log`. Each session is processed at most once.

## Process Constraints
12. **Test suite must pass.** `python3 -m pytest tests/` must pass before any release. All LLM calls are mocked in tests.
13. **Hot reload for hooks and extractors.** Hooks and `extract_beats.py` reload on each invocation. MCP server changes require restarting Claude Desktop.
14. **Config at two levels.** Global config at `~/.claude/cyberbrain/config.json`, per-project at `.claude/cyberbrain.local.json` (searched up directory tree). Project config overrides global.

## Scope Constraints
15. **No code generation.** Cyberbrain captures knowledge, not code. Beats are prose with optional code snippets, not executable artifacts.
16. **Single user.** The system is designed for a single user's vault. Multi-user, multi-tenant, and collaboration features are out of scope.
17. **Obsidian as human review layer.** The system does not provide its own UI for vault browsing, editing, or visualization. Obsidian fills that role.
