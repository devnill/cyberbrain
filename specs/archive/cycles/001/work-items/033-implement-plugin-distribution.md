# 033: Implement Plugin Distribution

## Objective
Based on research from WI-031 and WI-032, implement the plugin-based distribution strategy for the Claude Code path. Includes: cleaning up the plugin manifest, switching to uv-based MCP server launch, simplifying or replacing install.sh for the Claude Code distribution path, and updating CLAUDE.md documentation.

## Acceptance Criteria
- [ ] `.claude-plugin/plugin.json` is accurate: no dead fields, correct MCP server reference, correct version
- [ ] Dead `"skills": "./skills/"` field removed from plugin.json (no skills directory exists)
- [ ] MCP server can be launched via uv without the current venv setup at `~/.claude/cyberbrain/venv/`
- [ ] `.mcp.json` reflects the distribution-ready launch command (not just dev mode)
- [ ] install.sh is either eliminated for Claude Code users or reduced to only what the plugin system cannot handle (e.g., first-time config initialization with vault path)
- [ ] `CLAUDE.md` Build & Install section updated to reflect uv-based approach
- [ ] `python3 -m pytest tests/` passes after all changes
- [ ] A new user can install and run cyberbrain following the updated instructions without running install.sh
- [ ] `specs/plan/architecture.md` deployment section updated if the deployment model changes
- [ ] All changes are consistent with research recommendations from WI-031 and WI-032

## File Scope
- `.claude-plugin/plugin.json` (modify) — remove dead skills field, set correct MCP reference
- `.mcp.json` (modify) — update for distribution-ready launch
- `install.sh` (modify or scope-reduce) — eliminate or reduce to config-only for CC users; exact scope determined by research
- `CLAUDE.md` (modify) — update Build & Install section for uv
- `specs/plan/architecture.md` (modify) — update deployment section
- `mcp/requirements.txt` (possibly modify) — may convert to pyproject.toml or inline uv deps per research recommendation
- `extractors/requirements.txt` (possibly modify) — same

## Dependencies
- Depends on: 031, 032
- Blocks: none

## Implementation Notes
**Must read both research reports before making any implementation decisions.**

The executor must resolve based on research:
1. Whether to use `uv run` (local source from plugin dir) or `uvx` (from PyPI/GitHub package) — depends on whether we publish to PyPI or distribute as a GitHub plugin
2. Whether install.sh is kept (reduced scope) or eliminated for Claude Code users
3. How config initialization happens without install.sh (first-run wizard in MCP server? separate cb_setup phase? manual config file creation?)
4. Whether pyproject.toml replaces requirements.txt for uv dependency declaration
5. How prompt file paths are resolved when moving from installed-copy model to run-from-source model

Things that are certain regardless of research findings:
- `plugin.json` `"skills"` field must be removed (no skills directory exists; MCP is the interface)
- `.mcp.json` needs a distribution-ready config alongside or replacing the current dev-mode config

## Complexity
Medium
