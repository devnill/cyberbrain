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
- **Status**: settled

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

## D-6: install.sh source paths updated to src/cyberbrain/ locations
- **Decision**: Update all `cp` source paths in install.sh from `$REPO_DIR/extractors/`, `$REPO_DIR/mcp/`, `$REPO_DIR/prompts/` to `src/cyberbrain/` equivalents. Replace `pip install -r requirements.txt` with pyproject.toml-based install. Add missing files found during rework: `quality_gate.py`, four prompt files, and `extractors/__init__.py`.
- **Rationale**: Cycle 002 code-quality (C1), gap-analysis (II1, IR1) independently confirmed install.sh was completely broken after WI-034. `set -euo pipefail` caused abort at first missing path. Claude Desktop users on fresh clone were fully blocked.
- **Source**: archive/cycles/002/decision-log.md (DL4)
- **Status**: settled

## D-7: Bare imports replaced with cyberbrain.* namespace across test files and search_backends.py
- **Decision**: Replace all `from search_backends import X` with `from cyberbrain.extractors.search_backends import X` in test files. Fix `search_backends.py` try block to use `from cyberbrain.extractors.frontmatter import ...` directly, removing the always-failing fallback.
- **Rationale**: Cycle 002 code-quality (C2, S1) found bare module names passed collection but failed at test runtime. The `search_backends.py` fallback was always executing, silently bypassing the canonical `frontmatter.py`.
- **Source**: archive/cycles/002/decision-log.md (DL5)
- **Status**: settled

## D-8: Documentation and domain tracking updated post-WI-034
- **Decision**: Update CLAUDE.md (tool count, paths, dev invocation), all module specs and architecture doc to use `src/cyberbrain/` paths, and distribution domain questions file (Q-1 through Q-7 marked resolved). Add deprecation notice to build.sh. Merge duplicate Distribution section in architecture.md.
- **Rationale**: Spec-adherence review found five architecture deviations (D1–D3 path staleness, D4 shared.py mischaracterization, D5 search_backends.py fallback) and one unmet WI-034 acceptance criterion (CLAUDE.md not updated). Gap-analysis IR2 found Q-1 through Q-7 all open despite being resolved.
- **Source**: archive/cycles/002/decision-log.md (DL6)
- **Status**: settled

## D-9: Token-efficient testing infrastructure implemented without incremental review
- **Decision**: Add pytest markers (core/extended/slow), AST-based import-graph plugin for `--affected-only` mode, quiet addopts defaults, and two-pass wrapper at `scripts/test.py` (WI-048–051). Implemented as a group without individual incremental reviews before the cycle 002 capstone.
- **Rationale**: User request to reduce token spend during ideate cycles. Test suite was running 1200+ tests per change; expected reduction is 95%+ fewer tests and 99% less output volume.
- **Source**: archive/cycles/002/decision-log.md (DL3, DL14)
- **Status**: provisional (implemented; correctness unverified — see Q-10)
