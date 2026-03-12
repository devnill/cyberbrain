# Policies: Distribution

## P-1: User config is never relocated by the plugin system
User config lives at `~/.claude/cyberbrain/config.json` regardless of plugin installation location. Plugin cache paths change on version update; config is persistent user data and must not move.
- **Derived from**: DL18; GP-2 (The Vault is the Canonical Store — extended to config)
- **Established**: WI-032 research, cycle 5
- **Status**: active

## P-2: Plugin paths use ${CLAUDE_PLUGIN_ROOT}, never hardcoded
All hook scripts and MCP server references to plugin files use the `${CLAUDE_PLUGIN_ROOT}` environment variable. Hardcoded paths break when the plugin cache is updated.
- **Derived from**: DL19
- **Established**: WI-032 research, cycle 5
- **Status**: active

## P-3: All Python code lives under the cyberbrain.* namespace
The `src/cyberbrain/` layout with `__init__.py` files in all sub-packages is mandatory. No bare module imports; no `sys.path` manipulation. All intra-package imports use fully-qualified `cyberbrain.*` names.
- **Derived from**: DL23; Constraint C1 (Python 3.8+)
- **Established**: cycle 6 planning (WI-034)
- **Status**: active (partially implemented — see open questions)

## P-4: install.sh is retained for Claude Desktop users and first-time config
The plugin system cannot run post-install scripts or initialize config interactively. `install.sh` handles config initialization, file migration for existing installs, and Claude Desktop MCP registration.
- **Derived from**: DL20
- **Established**: WI-031 research, cycle 5
- **Status**: active

## P-5: uv is the dependency manager for the MCP server
`uv run --directory ${CLAUDE_PLUGIN_ROOT}` is the canonical invocation for the MCP server. This aligns with the de facto ecosystem pattern for Python MCP servers.
- **Derived from**: DL17; GP-6 (Lean Architecture)
- **Established**: WI-032 research, cycle 5
- **Status**: active

## P-6: Entry points, not file paths, in hook invocations
Hooks call entry points defined in `pyproject.toml` (e.g., `cyberbrain-extract`) rather than hardcoded file paths. This decouples hooks from the internal directory layout.
- **Derived from**: DL23; GP-8 (Graceful Degradation — hooks should not silently fail when layout changes)
- **Established**: cycle 6 planning interview
- **Status**: active (not yet fully implemented)
