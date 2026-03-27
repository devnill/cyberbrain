# Code Quality Review — Cycle 21

## Verdict: Pass

1331 tests pass, 0 pyright errors. No critical or significant findings. Two minor issues and one suggestion.

## Test Results
- 1331 passed, 16 skipped, 0 failures
- basedpyright: 0 errors, 0 warnings, 0 notes

## Critical Findings
None.

## Significant Findings
None.

## Minor Findings

### M1: Redundant _is_within_vault check in review.py promote path
**File**: `src/cyberbrain/mcp/tools/review.py:422`
**Issue**: The promote action still calls `_is_within_vault(vault, output_path)` as a pre-check before `write_vault_note()`. But `write_vault_note()` already performs this validation internally via `_is_within_vault_check()`. The pre-check is redundant — if it passes, the vault function will also pass. If it would fail, the vault function would raise ValueError.
**Impact**: No functional impact. Redundant code that could diverge if one check is updated but not the other.
**Suggested fix**: Remove the `_is_within_vault` pre-check and let `write_vault_note` handle validation. Wrap in try/except ValueError for the skip message.

### M2: Duplicate _is_within_vault implementation persists in shared.py
**File**: `src/cyberbrain/mcp/shared.py:95-101`
**Issue**: `shared.py` retains its own `_is_within_vault()` (boolean return) alongside vault.py's new `_is_within_vault_check()` (raises ValueError). Both implement `resolve().relative_to()`. Three modules still import the boolean version from shared.py: review.py (1 use at line 422), restructure/pipeline.py, and restructure/collect.py.
**Impact**: Maintenance divergence risk. Two implementations of the same logic with different signatures.
**Suggested fix**: Consolidate to vault.py's implementation. Re-export from shared.py for backward compatibility.

## Suggestions

### SG1: Dead code in --beats-json CLI path
**File**: `src/cyberbrain/extractors/extract_beats.py:308-312`
**Issue**: The `result["skipped"]` check after `run_extraction()` in the `--beats-json` path is dead code. The dedup check at line 293 calls `sys.exit(0)` before `run_extraction` is reached, so the inner guard can never return `skipped=True` via this path.
**Suggested fix**: Remove lines 308-312.
