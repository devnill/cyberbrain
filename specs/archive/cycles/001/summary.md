# Review Summary — Cycle 6 (WI-034)

## Overview

WI-034 moved the project directory structure from a flat layout (`mcp/`, `extractors/`, `prompts/`) to `src/cyberbrain/` and correctly updated the MCP layer imports to use the `cyberbrain.*` namespace. The `__init__.py` files, `main()` entry point, and `server.py` imports are all correct. However, the migration is approximately half-complete: the extractor layer (14 files), all test files, both hook scripts, `pyproject.toml` packages directive, and `.mcp.json` module path were not updated. The package cannot be installed or distributed in its current state.

## Critical Findings

- **[code-reviewer]** pyproject.toml packages directive still lists deleted directories — `packages = ["mcp", "extractors", "prompts"]` references directories deleted by WI-034. Hatchling builds an empty wheel. `uvx cyberbrain-mcp` fails with `ModuleNotFoundError`. (`pyproject.toml:43`) — relates to: WI-034
- **[code-reviewer]** .mcp.json still uses old module path — `python -m mcp.server` launches the PyPI `mcp` package's server module, not cyberbrain's. MCP tools are unavailable to all plugin users. (`.mcp.json:8`) — relates to: WI-034
- **[code-reviewer]** All test files fail at collection — 18 of 20 test modules add deleted directories to `sys.path` and use bare pre-migration imports. `python3 -m pytest tests/` produces 18 collection errors. (`tests/conftest.py:22-29`, multiple files) — relates to: WI-034
- **[gap-analyst]** manage.py imports from tools.recall using bare name — `from tools.recall import _DEFAULT_DB_PATH` will collide with PyPI `tools` namespace. `cb_configure` and `cb_status` crash on server startup. (`src/cyberbrain/mcp/tools/manage.py:12,516`) — relates to: WI-034

## Significant Findings

- **[code-reviewer]** setup.py bare import of analyze_vault — `from analyze_vault import analyze_vault` fails in any packaged install. `cb_setup` raises `ModuleNotFoundError`. (`src/cyberbrain/mcp/tools/setup.py:18`) — relates to: WI-034
- **[code-reviewer]** manage.py partially-qualified import of tools.recall — `from tools.recall import ...` fails in packaged install. (`src/cyberbrain/mcp/tools/manage.py:12`) — relates to: WI-034
- **[code-reviewer]** All 14 extractor files retain bare imports and sys.path manipulation — `extract_beats.py` injects its own directory into `sys.path`; all extractor modules use bare names (`from config import`, `from backends import`, etc.). The `cyberbrain.*` namespace requirement is not met for the extractor layer. (`src/cyberbrain/extractors/extract_beats.py:26-28`, 13 other files) — relates to: WI-034
- **[code-reviewer]** Hook scripts check old extractor path — both hooks check `$CLAUDE_PLUGIN_ROOT/extractors/extract_beats.py` which no longer exists. On a fresh plugin install, automatic knowledge capture is silently disabled. (`hooks/pre-compact-extract.sh:29-33`, `hooks/session-end-extract.sh:45-49`) — relates to: WI-034
- **[gap-analyst]** conftest.py mock targets wrong module key — mock installed at `sys.modules["extract_beats"]`; `shared.py` imports from `cyberbrain.extractors.extract_beats`. Mock does not intercept; test isolation silently broken. (`tests/conftest.py`) — relates to: WI-034
- **[gap-analyst]** scripts/import.py still hardcodes legacy extractor path — `EXTRACTORS_DIR = Path.home() / ".claude" / "cyberbrain" / "extractors"`. Fails on clean plugin installs. (`scripts/import.py:33-34`) — relates to: WI-034
- **[gap-analyst]** No cyberbrain-extract entry point defined — implementation notes reference `cyberbrain-extract` for hooks but it is not in `pyproject.toml`. — relates to: WI-034
- **[gap-analyst]** No pytest configuration for src layout — no `pythonpath = ["src"]` in `pyproject.toml`. `pytest` cannot resolve `cyberbrain` without `pip install -e .` which is undocumented. — relates to: WI-034
- **[spec-reviewer]** CLAUDE.md validation command references deleted path — `python3 extractors/extract_beats.py ...` will fail; primary developer onboarding document gives incorrect commands. (`CLAUDE.md`) — relates to: WI-034
- **[spec-reviewer]** Principle 8 violation (Graceful Degradation) — hook silently skips extraction on fresh plugin install with no error; automatic capture, the primary value proposition, is not functional. — relates to: WI-034

## Minor Findings

- **[code-reviewer]** `_EXTRACTOR_DIR` computed but never used in `shared.py` — four dead variable declarations. (`src/cyberbrain/mcp/shared.py:15-23`) — relates to: WI-034
- **[code-reviewer]** Architecture.md still references old paths and launch command — Distribution section references `python -m mcp.server` and `mcp/shared.py`. (`specs/plan/architecture.md:495-554`) — relates to: WI-034
- **[code-reviewer]** WI-034 spec has typo `src/cybrain/` instead of `src/cyberbrain/` — documentation-only error in the work item spec. — relates to: WI-034
- **[spec-reviewer]** Six MCP tool files retain unqualified imports for intra-tool calls — `restructure.py`, `recall.py`, `enrich.py`, `review.py` still have `from backends import` bare imports that work only via `sys.path` injection. — relates to: WI-034

## Findings Requiring User Input

None — all findings can be resolved from existing context. The required changes are technically clear and follow directly from the WI-034 acceptance criteria. No architectural decisions are required.

## Proposed Refinement Plan

A refinement cycle (WI-035 or similar) is required to complete the WI-034 migration. The following areas require work:

**Critical fixes (must be done for any installation to work):**
1. `pyproject.toml` — change `packages = ["mcp", "extractors", "prompts"]` to `packages = ["src/cyberbrain"]`
2. `.mcp.json` — change `python -m mcp.server` to `python -m cyberbrain.mcp.server`
3. `hooks/pre-compact-extract.sh` and `hooks/session-end-extract.sh` — update extractor path to `src/cyberbrain/extractors/` or use entry point invocation
4. `src/cyberbrain/mcp/tools/manage.py` — fix `from tools.recall import` to `from cyberbrain.mcp.tools.recall import`
5. `src/cyberbrain/mcp/tools/setup.py` — fix `from analyze_vault import` to `from cyberbrain.extractors.analyze_vault import`

**Extractor layer import migration (bulk of remaining work):**
6. All 14 extractor files in `src/cyberbrain/extractors/` — convert bare imports to `cyberbrain.extractors.*`; remove `sys.path` injection from `extract_beats.py`
7. Remaining MCP tool files with bare imports — `restructure.py`, `recall.py`, `enrich.py`, `review.py`

**Test suite update:**
8. All 20 test files — replace `sys.path` manipulation with `cyberbrain.*` imports; update `conftest.py` mock key to `cyberbrain.extractors.extract_beats`
9. `pyproject.toml` — add `[tool.pytest.ini_options] pythonpath = ["src"]`

**Documentation and infrastructure:**
10. `CLAUDE.md` — update all file paths and validation commands to `src/cyberbrain/` paths
11. `specs/plan/architecture.md` — update component map and distribution section
12. `pyproject.toml` — add `cyberbrain-extract` entry point for hook invocation
13. `scripts/import.py` — replace path-based extractor resolution with `cyberbrain.extractors.*` imports