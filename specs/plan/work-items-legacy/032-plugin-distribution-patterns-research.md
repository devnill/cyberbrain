# 032: Research — Distribution Patterns for Python-backed Tools

## Objective
Survey how other Python-backed Claude Code / MCP tools handle distribution, installation, and updates. Focus on basic-memory as the primary reference. Identify the uv-based distribution pattern that has emerged as standard in 2025-2026. Produce a research report with recommendations applicable to cyberbrain.

## Acceptance Criteria
- [ ] Research report exists at `specs/steering/research/plugin-distribution-patterns.md`
- [ ] Report covers basic-memory: how it distributes, installs, handles updates, and what its MCP server launch command looks like
- [ ] Report covers at least 2 other Python-backed MCP tools as additional data points
- [ ] Report covers the uv-based distribution patterns: when to use `uvx tool-name` vs `uv run --with deps` vs `uv tool install`
- [ ] Report covers multi-machine sync: how do users keep a tool current across machines?
- [ ] Report covers first-run config initialization: how do tools handle setup (vault path, etc.) without an installer?
- [ ] Report assesses whether cyberbrain's MCP server can be distributed as a `uvx` package or `uv run` command without file copying to `~/.claude/cyberbrain/`
- [ ] Report addresses how path resolution changes when moving from installed-copy model to run-from-repo model (cyberbrain currently reads prompts from ~/.claude/cyberbrain/prompts/)
- [ ] Concrete recommendation: which distribution pattern fits cyberbrain's needs in 2026

## File Scope
- `specs/steering/research/plugin-distribution-patterns.md` (create) — research report

## Dependencies
- Depends on: none
- Blocks: 033

## Implementation Notes
Pure research task. No code changes.

Key questions to resolve:
1. Does basic-memory ship via uvx? pip? A custom installer? A Claude Code plugin?
2. What's the minimal install flow for a Python MCP tool with optional heavy deps (fastembed, usearch)?
3. Can cyberbrain's MCP server (fastmcp, pyyaml, optional fastembed/usearch) be distributed as a `uvx` package from GitHub without PyPI?
4. The current MCP server reads prompts and extractors from `~/.claude/cyberbrain/` (installed copies). If we run from the plugin directory, how do paths change?
5. How does config initialization (vault path setup) happen in tools that don't have an installer?
6. Multi-machine: does uv's global tool cache help? Or does each machine need to install separately?

Reference:
- basic-memory: https://github.com/basicmachines-co/basic-memory (user cited as positive example of how cyberbrain should present itself)

## Complexity
Small
