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

## D-10: ruff + basedpyright adopted as the quality tooling stack
- **Decision**: ruff (linter + formatter) and basedpyright (type checker) are the enforced quality tools. Both configured in pyproject.toml with targeted ignores. ruff was chosen as the de facto standard; basedpyright over mypy for speed, stricter defaults, and pyproject.toml-native config.
- **Rationale**: Cycles 10-11 evaluated alternatives; ruff + basedpyright combination reaches 0 type errors on the codebase in basic mode.
- **Source**: archive/cycles/012/decision-log.md (D1); archive/incremental/058-tooling-foundation.md
- **Status**: settled

## D-11: Per-file F401 ignores for re-export hubs, not global suppression
- **Decision**: Modules that intentionally re-export symbols (extract_beats.py, shared.py) use per-file `# noqa: F401` or pyproject.toml per-file ignores rather than a global F401 suppression rule.
- **Rationale**: Global F401 ignore was rejected in code review as too broad — it would suppress legitimate unused-import warnings across the whole codebase.
- **Source**: archive/cycles/012/decision-log.md (D2); archive/incremental/058-tooling-foundation.md
- **Status**: settled

## D-12: pre-commit configured with ruff hooks; UP038 added to global ignore
- **Decision**: Standard ruff-pre-commit integration. UP038 (`non-pep604-isinstance`) added to ruff's global ignore list because some cases require `--unsafe-fixes` to auto-correct.
- **Rationale**: UP038 cannot be safely auto-applied everywhere; ignoring it globally avoids pre-commit blocking commits unnecessarily.
- **Source**: archive/cycles/012/decision-log.md (D7); archive/incremental/068-cycle11.md
- **Status**: settled

## D-13: shared.py converted to direct imports; conftest sys.modules mock dependency removed
- **Decision**: shared.py changed from importing via the extract_beats.py re-export hub to importing directly from source modules (e.g., `from cyberbrain.extractors.vault import ...`). This removed the prerequisite for conftest.py sys.modules mock injection in tests.
- **Rationale**: The re-export hub added an indirection layer that forced tests to mock the hub rather than the real modules. Direct imports are more transparent and correct.
- **Source**: archive/cycles/012/decision-log.md (D4); archive/incremental/063-lazy-imports.md
- **Status**: settled

## D-14: Exception handler ambiguity resolved by documentation, not narrowing
- **Decision**: For exception handlers where the correct narrow type was ambiguous, `# intentional: <reason>` comments were added rather than narrowing to a potentially incorrect type. Approximately 10 handlers were narrowed where unambiguous; 40+ were documented.
- **Rationale**: Incorrect narrowing can mask real errors at runtime. Documentation preserves the intentionality signal without introducing false-safety.
- **Source**: archive/cycles/012/decision-log.md (D5); archive/incremental/070-cycle11.md
- **Status**: settled

## D-15: sys.modules patterns in tests documented and consolidated; full elimination deferred
- **Decision**: sys.modules injection patterns in 10 test files were refactored to use a shared helper function with consistent structure, but not fully eliminated. Full elimination is deferred.
- **Rationale**: Full rewrite would be high risk with low immediate benefit. The consolidation reduces inconsistency without touching behavior. Deferred per GP-10 (YAGNI).
- **Source**: archive/cycles/012/decision-log.md (D6); archive/incremental/071-cycle11.md
- **Status**: provisional (consolidated; full elimination deferred)

## D-16: requires-python updated to >=3.11
- **Decision**: pyproject.toml `requires-python` updated from `>=3.8` to `>=3.11`. Constraint C1 in specs updated accordingly.
- **Rationale**: Tool configs (ruff, basedpyright) already target 3.11+ syntax. Aligning the declared minimum prevents false compatibility claims.
- **Source**: archive/cycles/012/review-manifest.md (WI-067); archive/incremental/067-cycle11.md
- **Status**: settled
