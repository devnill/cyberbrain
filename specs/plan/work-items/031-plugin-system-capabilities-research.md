# 031: Research — Claude Code Plugin System Capabilities

## Objective
Investigate what the Claude Code plugin system supports for distribution: post-install scripts, built-in MCP server bundling, update/versioning mechanism, and how the plugin marketplace handles installs. Produce a research report with concrete findings applicable to cyberbrain's distribution needs.

## Acceptance Criteria
- [ ] Research report exists at `specs/steering/research/plugin-system-capabilities.md`
- [ ] Report covers: what `.claude-plugin/plugin.json` fields are supported and what each does
- [ ] Report covers: whether post-install/setup scripts are supported (for config initialization, Python dep installation, etc.)
- [ ] Report covers: how MCP server bundling works in a plugin — can a plugin ship a self-contained MCP server? What does the `mcpServers` field accept?
- [ ] Report covers: plugin versioning and update mechanism — how do updates propagate to installed users?
- [ ] Report covers: what the plugin marketplace install flow looks like from a user's perspective
- [ ] Report covers: whether a `uvx`-based launch pattern works in plugin context
- [ ] Report identifies: what install.sh responsibilities cannot be delegated to the plugin system
- [ ] Report assesses the cyberbrain repo's existing `.claude-plugin/plugin.json` and `.mcp.json` against what is actually supported
- [ ] Concrete recommendation: what the plugin system can handle, what must stay in install.sh, what uv can handle

## File Scope
- `specs/steering/research/plugin-system-capabilities.md` (create) — research report

## Dependencies
- Depends on: none
- Blocks: 033

## Implementation Notes
Pure research task. No code changes.

Existing state in the repo:
- `.claude-plugin/plugin.json` — skeleton with name, version, description, skills (dead — no skills/ dir exists), hooks, mcpServers
- `.mcp.json` — dev-mode config using `uv run --with mcp python3 mcp/server.py`
- `install.sh` — 456-line bash script: venv at ~/.claude/cyberbrain/venv/, file copying, config init, Claude Desktop registration, hook registration in settings.json

Key questions to resolve:
1. Does the plugin system support any lifecycle hooks (post-install, pre-update)?
2. Can a plugin declare Python dependencies and have them auto-installed?
3. Does `mcpServers` in plugin.json work the same as .mcp.json? What format?
4. How does the plugin marketplace versioning work — semver? Git tags? Manifest version field?
5. When a plugin updates, does the MCP server restart automatically?
6. Is there a `uvx`-based launch pattern that works in plugin context?

## Complexity
Small
