# Questions: Distribution

## Q-1: pyproject.toml packages directive must be updated (blocking install)
- **Question**: `packages = ["mcp", "extractors", "prompts"]` still lists directories deleted by WI-034. Must be changed to `packages = ["src/cyberbrain"]`. Until fixed, `uvx cyberbrain-mcp` builds an empty wheel.
- **Source**: archive/cycles/001/decision-log.md (OQ1); archive/cycles/001/gap-analysis.md (MR1)
- **Impact**: The package cannot be distributed. All installation paths silently install a no-op wheel.
- **Status**: resolved — WI-034 migration completed. `pyproject.toml` now has `[tool.hatch.build.targets.wheel] packages = ["src/cyberbrain"]`. Entry points `cyberbrain-mcp` and `cyberbrain-extract` are defined in `[project.scripts]`.
- **Resolved**: WI-037

## Q-2: .mcp.json module path still references old pre-migration path (blocking)
- **Question**: `.mcp.json` launches `python -m mcp.server`, which resolves to the PyPI `mcp` package, not cyberbrain's server. Must be changed to `python -m cyberbrain.mcp.server`.
- **Source**: archive/cycles/001/decision-log.md (OQ2); archive/cycles/001/gap-analysis.md (MR2)
- **Impact**: All plugin users get no MCP tools — the server launches the wrong process.
- **Status**: resolved — `.mcp.json` now uses `"python", "-m", "cyberbrain.mcp.server"`.
- **Resolved**: WI-037

## Q-3: Hook scripts reference deleted extractor path (blocking, silent failure)
- **Question**: Both hooks check `$CLAUDE_PLUGIN_ROOT/extractors/extract_beats.py` which no longer exists after WI-034. Must use `$CLAUDE_PLUGIN_ROOT/src/cyberbrain/extractors/extract_beats.py` or the `cyberbrain-extract` entry point.
- **Source**: archive/cycles/001/decision-log.md (OQ3); archive/cycles/001/gap-analysis.md (MR3)
- **Impact**: Automatic knowledge capture is silently disabled on all fresh plugin installs. No error is shown.
- **Status**: resolved — hooks now invoke `uv run --directory "$CLAUDE_PLUGIN_ROOT" python -m cyberbrain.extractors.extract_beats` in plugin mode.
- **Resolved**: WI-037

## Q-4: Extractor layer — 14 files still use bare imports and sys.path manipulation (blocking)
- **Question**: All 14 extractor files use bare unqualified imports and `extract_beats.py` injects its own directory into `sys.path`. Must be migrated to `cyberbrain.extractors.*` namespace.
- **Source**: archive/cycles/001/decision-log.md (OQ4, OQ5); archive/cycles/001/gap-analysis.md (MR4, MR5)
- **Impact**: The package cannot be used in a properly installed environment without the sys.path hack.
- **Status**: resolved — all extractor files now use `from cyberbrain.extractors.*` imports. `extract_beats.py` no longer injects `sys.path`.
- **Resolved**: WI-037

## Q-5: Test suite fails at collection — 18 of 20 modules (blocking CI)
- **Question**: All test files add deleted directories to `sys.path` and use bare pre-migration imports. `conftest.py` installs the mock at the wrong module key (`extract_beats` instead of `cyberbrain.extractors.extract_beats`). Must update all 20 test files and add `pythonpath = ["src"]` to pytest config.
- **Source**: archive/cycles/001/decision-log.md (OQ6, OQ8); archive/cycles/001/gap-analysis.md (IR1, IR2, MI2)
- **Impact**: `python3 -m pytest tests/` produces 18 collection errors. CI cannot pass.
- **Status**: resolved (migration) / deferred (environment) — all test files now use `cyberbrain.*` namespaced imports. `pyproject.toml` has `pythonpath = ["src", "tests"]`. Remaining 9 collection errors are due to `fastmcp` not being installed in the test environment, not import path issues. Install deps with `uv sync` or `pip install -e ".[dev]"` to resolve.
- **Resolved**: WI-037

## Q-6: No cyberbrain-extract entry point defined in pyproject.toml
- **Question**: Implementation notes and P-6 policy reference `cyberbrain-extract` as the hook invocation pattern, but it is not defined in `[project.scripts]`. Hooks cannot use an entry point that doesn't exist.
- **Source**: archive/cycles/001/decision-log.md (OQ7); archive/cycles/001/gap-analysis.md (MI1)
- **Impact**: Hooks must fall back to a direct file path, which couples them to the internal layout.
- **Status**: resolved — `pyproject.toml` now defines both `cyberbrain-mcp = "cyberbrain.mcp.server:main"` and `cyberbrain-extract = "cyberbrain.extractors.extract_beats:main"` in `[project.scripts]`.
- **Resolved**: WI-037

## Q-7: scripts/import.py hardcodes legacy extractor path
- **Question**: `scripts/import.py` hardcodes `EXTRACTORS_DIR = Path.home() / ".claude" / "cyberbrain" / "extractors"`. Must use `cyberbrain.extractors.*` imports directly.
- **Source**: archive/cycles/001/decision-log.md (OQ9); archive/cycles/001/gap-analysis.md (MR6)
- **Impact**: Batch import fails for plugin-only installs with no legacy `~/.claude/cyberbrain/` directory.
- **Status**: resolved (import path) / deferred (dead constant) — `scripts/import.py` now imports via `cyberbrain.extractors.extract_beats` directly (line 48). The `EXTRACTORS_DIR` constant at line 33 is now dead code — never referenced. Removing it is a minor cleanup deferred to a future housekeeping pass; it has no functional impact.
- **Resolved**: WI-037

## Q-8: evaluate.py CLI main() uses bare unqualified import
- **Question**: `src/cyberbrain/extractors/evaluate.py` line ~407 uses `from config import resolve_config` inside `main()`. Should be `from cyberbrain.extractors.config import resolve_config`. Violates P-3 (all code must use `cyberbrain.*` namespace).
- **Source**: archive/cycles/002/decision-log.md (OQ7); archive/cycles/002/gap-analysis.md (EC1)
- **Impact**: The evaluate dev tool fails with `ModuleNotFoundError` on CLI invocation in any packaged install. Failure is invisible at import time; surfaces only when the tool is actually run.
- **Status**: open
- **Reexamination trigger**: One-line fix; address in next housekeeping pass or alongside WI-044/045.

## Q-9: requirements.txt files inside src/cyberbrain/ are orphaned
- **Question**: Should `src/cyberbrain/extractors/requirements.txt` and `src/cyberbrain/mcp/requirements.txt` be deleted? They specify an incomplete dependency subset and any path that still references them (e.g. the bedrock install path in install.sh) installs without `fastmcp`, `mcp`, and `ruamel.yaml`.
- **Source**: archive/cycles/002/decision-log.md (OQ8); archive/cycles/002/gap-analysis.md (MI1); archive/cycles/002/code-quality.md (M3)
- **Impact**: Developers following a `pip install -r` path get an under-specified install that fails at runtime on import. The files will also be bundled in any built wheel, creating confusion.
- **Status**: open
- **Reexamination trigger**: Address in same housekeeping pass as Q-8; delete both files and replace any remaining `pip install -r` references with pyproject.toml-based install.

## Q-10: WI-048–051 (token-efficient testing) implemented without incremental review
- **Question**: Are the affected-only import-graph plugin and marker implementations correct and complete? The `--affected-only` mode may silently skip tests if import graph analysis is incorrect.
- **Source**: archive/cycles/002/decision-log.md (OQ6, DL14); archive/cycles/002/summary.md (WI-048–051)
- **Impact**: If `--affected-only` has incorrect import graph analysis, it may produce false confidence in passing test suites by silently skipping affected tests.
- **Status**: open
- **Reexamination trigger**: Technical investigation of scripts/test.py and the AST-based import graph plugin; verify affected-only mapping against known dependency relationships.
