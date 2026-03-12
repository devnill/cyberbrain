# Decisions: Distribution

## D-1: Claude Code plugin system adopted as primary distribution path
- **Decision**: Replace install.sh as the Claude Code distribution mechanism with the Claude Code plugin system (`.claude-plugin/plugin.json`, hook auto-registration, MCP server via `.mcp.json`).
- **Rationale**: "The installer is annoying. Wants an in-Claude solution for updates and versioning. Has a GitHub plugin repo. Releases daily and wants the latest version on multiple computers at all times." (interview, cycle 5)
- **Source**: specs/steering/interview.md (Refinement Interview 2026-03-10); archive/cycles/001/decision-log.md (DL14)
- **Status**: settled

## D-2: uv adopted for MCP server launch and dependency resolution
- **Decision**: MCP server is launched via `uv run --directory ${CLAUDE_PLUGIN_ROOT} python -m cyberbrain.mcp.server`. `pyproject.toml` defines dependencies; uv handles resolution.
- **Rationale**: uvx is the de facto pattern for Python MCP servers in the 2026 ecosystem.
- **Source**: archive/cycles/001/decision-log.md (DL17)
- **Status**: settled

## D-3: src layout — all Python under src/cyberbrain/
- **Decision**: Move `mcp/`, `extractors/`, `prompts/` under `src/cyberbrain/`. Add `__init__.py` to make proper packages. Entry point: `cyberbrain-mcp = "cyberbrain.mcp.server:main"`.
- **Rationale**: Cycle 5 capstone identified that the internal `mcp/` directory collided with the PyPI `mcp` package, and the entry point referenced a non-existent namespace. "User chose namespace-wrapping approach over minimal cyberbrain_mcp/ rename for cleaner structure." (DL23)
- **Assumes**: Python 3.8+ throughout (Constraint C1).
- **Source**: archive/cycles/001/decision-log.md (DL23); specs/steering/interview.md (Refinement Interview 2026-03-11)
- **Status**: settled (implementation incomplete as of cycle 6 — see open questions)

## D-4: Claude Desktop distribution deferred to separate research cycle
- **Decision**: MCP distribution to Claude Desktop, Cursor, and Zed is not in scope for the current plugin work. Focus is Claude Code plugin path only.
- **Rationale**: "Focus for this cycle: Claude Code distribution path. MCP distribution to Claude Desktop/Cursor/Zed: deferred, needs separate research." (interview, cycle 5)
- **Source**: archive/cycles/001/decision-log.md (DL16); specs/steering/interview.md (Refinement Interview 2026-03-10)
- **Status**: settled (deferred)

## D-5: Two-level config — global + project override
- **Decision**: Global config at `~/.claude/cyberbrain/config.json`; per-project config at `.claude/cyberbrain.local.json` (searched up directory tree). Project config flat-merges over global.
- **Rationale**: Not recorded explicitly. Supports single global vault with per-project customization (project_name, vault_folder) without requiring separate installs.
- **Source**: specs/plan/architecture.md (Configuration Architecture section); specs/steering/constraints.md (C14)
- **Status**: settled
