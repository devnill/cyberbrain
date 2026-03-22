# Incremental Review — WI-056: Anchor _dependency_map.py paths to repo root

## Verdict: Pass

## Summary

`tests/_dependency_map.py` refactored to derive `_REPO_ROOT`, `_TESTS_DIR`, and `_SRC_DIR` from `Path(__file__).parent.parent`. All relative path operations replaced with anchored paths. Absolute path inputs now normalized to repo-relative before processing. All acceptance criteria met.

## Changes

- Added module-level constants: `_REPO_ROOT`, `_TESTS_DIR`, `_SRC_DIR`
- `build()`: uses `_TESTS_DIR.glob(...)` and stores test paths relative to `_REPO_ROOT`
- `get_tests_for()`: normalizes absolute inputs; uses `_TESTS_DIR / ...` and `candidate.relative_to(_REPO_ROOT)` for consistent output format

## Acceptance Criteria

| Criterion | Status |
|---|---|
| Repo-relative scripts/ path returns correct test | Pass |
| Absolute scripts/ path returns correct test | Pass |
| Repo-relative src/ path returns correct test | Pass |
| Absolute src/ path returns correct test | Pass |
| 1297 tests pass | Pass |

## Critical Findings

None.

## Significant Findings

None.

## Minor Findings

None.
