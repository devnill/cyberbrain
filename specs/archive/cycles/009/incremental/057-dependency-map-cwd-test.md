# Incremental Review — WI-057: Add cwd-independence test for _dependency_map.py

## Verdict: Pass

## Summary

`tests/test_dependency_map.py` created with 6 tests covering: scripts/ convention mapping, absolute path normalization, src/ import-graph mapping, unknown paths returning empty set, and cwd-independence via `monkeypatch.chdir(tmp_path)`. All 6 tests pass.

## Key Test

`test_mapper_is_cwd_independent` changes the process working directory to `tmp_path` (a temp dir with no project files), calls `build()` and `get_tests_for()`, and asserts both the scripts/ convention path and the src/ import-graph path return the correct test files.

## Acceptance Criteria

| Criterion | Status |
|---|---|
| `pytest tests/test_dependency_map.py` passes (6 tests) | Pass |
| `test_mapper_is_cwd_independent` exercises monkeypatch.chdir | Pass |

## Critical Findings

None.

## Significant Findings

None.

## Minor Findings

None.
