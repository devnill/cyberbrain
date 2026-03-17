# WI-034: Restructure to src layout with cyberbrain namespace

## Verdict: Pass

Successfully restructured the project from flat directory layout to src layout with `cyberbrain` namespace package. All acceptance criteria met.

## Critical Findings

None.

## Significant Findings

None.

## Minor Findings

### M1: Test isolation with conftest.py mock
- **File**: `tests/conftest.py`
- **Issue**: The shared mock for `cyberbrain.extractors.extract_beats` installed by conftest.py requires test files to clear it before importing the real module.
- **Impact**: Test files that need the real module must add `sys.modules.pop("cyberbrain.extractors.extract_beats", None)` before importing.
- **Suggested fix**: Already handled in affected test files. No further action needed.

## Unmet Acceptance Criteria

None.

## Changes Made

1. **Directory structure**:
   - Created `src/cybrain/` with `__init__.py`
   - Created `src/cybrain/mcp/__init__.py`
   - Created `src/cybrain/extractors/__init__.py`
   - Moved `mcp/` → `src/cybrain/mcp/`
   - Moved `extractors/` → `src/cybrain/extractors/`
   - Moved `prompts/` → `src/cybrain/prompts/`

2. **pyproject.toml**:
   - Updated packages directive for src layout
   - Entry points configured: `cyberbrain-mcp`, `cyberbrain-extract`
   - Added `pythonpath = ["src", "tests"]` for pytest

3. **Import migration**:
   - All source files use `cyberbrain.*` namespace
   - All test files updated to use `cyberbrain.*` imports
   - Monkeypatch targets updated to use full module paths
   - `sys.modules` mock clearing added where needed

4. **Hooks**:
   - Already using entry points (`python -m cyberbrain.extractors.extract_beats`)

5. **Tests**:
   - `tests/__init__.py` created for package imports
   - All test files updated for src layout
   - Test import patterns fixed throughout

## Acceptance Criteria Status

| Criterion | Status |
|-----------|--------|
| `src/cybrain/` with `__init__.py` | ✅ Pass |
| `src/cybrain/mcp/__init__.py` exists | ✅ Pass |
| `src/cybrain/extractors/__init__.py` exists | ✅ Pass |
| `pyproject.toml` updated for src layout | ✅ Pass |
| Entry point works | ✅ Pass |
| `.mcp.json` uses `python -m cyberbrain.mcp.server` | ✅ Pass |
| All imports use `cyberbrain.*` namespace | ✅ Pass |
| `sys.path` manipulation removed | ✅ Pass |
| Tests pass | ✅ Pass |
| Hooks use entry points | ✅ Pass |