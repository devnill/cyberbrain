# Code Quality Review — Full Audit

## Verdict: Pass (with caveats)

All 1310 tests pass, 16 skipped, 0 failures. basedpyright reports 2 type errors (both CyberbrainConfig assignability — minor annotation gaps, not runtime issues). Pre-commit hooks (ruff format + lint) are configured. No critical findings. Two significant findings warrant follow-up.

## Test Results
- **1310 passed**, 16 skipped, 4 warnings (3 RuntimeWarnings from analyze_vault import order, 1 PytestCollectionWarning)
- basedpyright: 2 errors (CyberbrainConfig TypedDict not assignable to `dict` in `shared.py:90` and `evaluate.py:465`)
- ruff: clean

## Critical Findings

None.

## Significant Findings

### S1: run_extraction() ignores its `config` parameter
**File**: `src/cyberbrain/extractors/extract_beats.py:68`
**Issue**: The function signature accepts `config=None` but line 68 unconditionally calls `resolve_config(cwd)`, discarding any passed config. The MCP `cb_extract` tool loads config at line 60 of `extract.py` then calls `run_extraction()` which loads it again. This is wasted work and prevents callers from overriding config.
**Known since**: Cycle 017 (still unfixed — cycle 018 planned but never executed).
**Relates to**: GP-06 (Lean Architecture), GP-10 (YAGNI — dead parameter)

### S2: _write_beats_and_log() duplicates run_extraction() orchestration
**File**: `src/cyberbrain/extractors/extract_beats.py:398-488`
**Issue**: The `--beats-json` CLI path uses `_write_beats_and_log()` which is a near-copy of the beat-writing loop in `run_extraction()` (lines 118-206). Both contain identical autofile logic, error handling, and runs-log writing. If one is updated, the other must be manually kept in sync.
**Known since**: Cycle 017 (planned for cycle 018, never executed).
**Relates to**: GP-06, cross-cutting code duplication

## Minor Findings

### M1: Test can corrupt production config.json
**File**: `tests/test_mcp_server.py:1708` (`test_vault_path_rebuild_thread_executes`)
**Issue**: This test monkeypatches `Path.home()` but `state.py:12` evaluates `_BASE = Path.home()` at import time, creating a race between import-time and call-time resolution. While current code appears to work (the dynamic `Path.home()` in `manage.py:240` is evaluated at call time), the production config was found corrupted with a pytest temp path during this session. The isolation is fragile.
**Relates to**: C-12 (test safety)

### M2: basedpyright reports 2 type errors
**Files**: `src/cyberbrain/mcp/shared.py:90`, `src/cyberbrain/extractors/evaluate.py:465`
**Issue**: `CyberbrainConfig` (TypedDict) is not assignable to bare `dict`. These are annotation mismatches, not runtime bugs, but they break the stated quality gate of 0 pyright errors.
**Relates to**: C-12

### M3: Restructure pipeline still large
**File**: `src/cyberbrain/mcp/tools/restructure/pipeline.py` (889 lines)
**Issue**: The restructure module was split into 10 sub-modules (3,817 lines total) which is an improvement over the prior monolithic 2,171-line file. However, `pipeline.py` itself at 889 lines remains the largest single module in the MCP tools layer. The orchestration logic is complex but functional.
**Relates to**: Architecture tension T3

### M4: state.py module-level Path.home() evaluation
**File**: `src/cyberbrain/extractors/state.py:12`
**Issue**: `_BASE = Path.home() / ".claude" / "cyberbrain"` is evaluated at import time. All constants derived from `_BASE` (CONFIG_PATH, SEARCH_DB_PATH, etc.) are frozen at import. This makes the module untestable without sys.modules manipulation and creates the fragile test isolation described in M1.
**Relates to**: C-12, GP-06

## Suggestions

### SG1: Consolidate vault-write paths
cb_review (`review.py:192,208,432`) and cb_restructure (`execute.py`) write vault files directly, violating C-06. This is documented as design tension T1. Consider routing these through a shared write helper that provides consistent logging and validation.

### SG2: Make state.py paths lazy
Replace `_BASE = Path.home() / ...` with a function `_base() -> Path` that evaluates `Path.home()` at call time. This would make all state paths testable without monkeypatching and eliminate the M1/M4 fragility.
