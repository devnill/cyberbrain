# Questions: Distribution

## Q-1: pyproject.toml packages directive must be updated (blocking install)
- **Question**: `packages = ["mcp", "extractors", "prompts"]` still lists directories deleted by WI-034. Must be changed to `packages = ["src/cyberbrain"]`. Until fixed, `uvx cyberbrain-mcp` builds an empty wheel.
- **Source**: archive/cycles/001/decision-log.md (OQ1); archive/cycles/001/gap-analysis.md (MR1)
- **Impact**: The package cannot be distributed. All installation paths silently install a no-op wheel.
- **Status**: open
- **Reexamination trigger**: Start of next execution cycle (WI-035 or equivalent).

## Q-2: .mcp.json module path still references old pre-migration path (blocking)
- **Question**: `.mcp.json` launches `python -m mcp.server`, which resolves to the PyPI `mcp` package, not cyberbrain's server. Must be changed to `python -m cyberbrain.mcp.server`.
- **Source**: archive/cycles/001/decision-log.md (OQ2); archive/cycles/001/gap-analysis.md (MR2)
- **Impact**: All plugin users get no MCP tools — the server launches the wrong process.
- **Status**: open
- **Reexamination trigger**: Start of next execution cycle.

## Q-3: Hook scripts reference deleted extractor path (blocking, silent failure)
- **Question**: Both hooks check `$CLAUDE_PLUGIN_ROOT/extractors/extract_beats.py` which no longer exists after WI-034. Must use `$CLAUDE_PLUGIN_ROOT/src/cyberbrain/extractors/extract_beats.py` or the `cyberbrain-extract` entry point.
- **Source**: archive/cycles/001/decision-log.md (OQ3); archive/cycles/001/gap-analysis.md (MR3)
- **Impact**: Automatic knowledge capture is silently disabled on all fresh plugin installs. No error is shown.
- **Status**: open
- **Reexamination trigger**: Start of next execution cycle.

## Q-4: Extractor layer — 14 files still use bare imports and sys.path manipulation (blocking)
- **Question**: All 14 extractor files use bare unqualified imports and `extract_beats.py` injects its own directory into `sys.path`. Must be migrated to `cyberbrain.extractors.*` namespace.
- **Source**: archive/cycles/001/decision-log.md (OQ4, OQ5); archive/cycles/001/gap-analysis.md (MR4, MR5)
- **Impact**: The package cannot be used in a properly installed environment without the sys.path hack.
- **Status**: open
- **Reexamination trigger**: Start of next execution cycle.

## Q-5: Test suite fails at collection — 18 of 20 modules (blocking CI)
- **Question**: All test files add deleted directories to `sys.path` and use bare pre-migration imports. `conftest.py` installs the mock at the wrong module key (`extract_beats` instead of `cyberbrain.extractors.extract_beats`). Must update all 20 test files and add `pythonpath = ["src"]` to pytest config.
- **Source**: archive/cycles/001/decision-log.md (OQ6, OQ8); archive/cycles/001/gap-analysis.md (IR1, IR2, MI2)
- **Impact**: `python3 -m pytest tests/` produces 18 collection errors. CI cannot pass.
- **Status**: open
- **Reexamination trigger**: Start of next execution cycle.

## Q-6: No cyberbrain-extract entry point defined in pyproject.toml
- **Question**: Implementation notes and P-6 policy reference `cyberbrain-extract` as the hook invocation pattern, but it is not defined in `[project.scripts]`. Hooks cannot use an entry point that doesn't exist.
- **Source**: archive/cycles/001/decision-log.md (OQ7); archive/cycles/001/gap-analysis.md (MI1)
- **Impact**: Hooks must fall back to a direct file path, which couples them to the internal layout.
- **Status**: open
- **Reexamination trigger**: Start of next execution cycle (required for Q-3 fix).

## Q-7: scripts/import.py hardcodes legacy extractor path
- **Question**: `scripts/import.py` hardcodes `EXTRACTORS_DIR = Path.home() / ".claude" / "cyberbrain" / "extractors"`. Must use `cyberbrain.extractors.*` imports directly.
- **Source**: archive/cycles/001/decision-log.md (OQ9); archive/cycles/001/gap-analysis.md (MR6)
- **Impact**: Batch import fails for plugin-only installs with no legacy `~/.claude/cyberbrain/` directory.
- **Status**: open
- **Reexamination trigger**: Start of next execution cycle.
