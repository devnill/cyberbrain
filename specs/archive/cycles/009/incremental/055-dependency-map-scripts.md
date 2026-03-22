# Incremental Review — WI-055: Register scripts/ tree in _dependency_map.py

## Verdict: Pass

## Summary

`tests/_dependency_map.py` updated with a filename-convention fallback for paths outside `src/`. `get_tests_for(Path("scripts/repair_frontmatter.py"))` now returns `{"tests/test_repair_frontmatter.py"}`. Existing `src/` behavior unchanged. 111 tests pass.

## Implementation

- `get_tests_for` restructured: try `relative_to("src")` first; on `ValueError`, check for `tests/test_{stem}.py` by convention.
- Convention: `scripts/X.py` → `tests/test_X.py` if the file exists.
- Returns empty set if no convention match (safe fallback).

## Acceptance Criteria

| Criterion | Status |
|---|---|
| `get_tests_for(Path("scripts/repair_frontmatter.py"))` returns `{"tests/test_repair_frontmatter.py"}` | Pass |
| `get_tests_for(Path("src/cyberbrain/mcp/tools/enrich.py"))` still returns correct test set | Pass |
| `python3 -m pytest tests/test_repair_frontmatter.py` passes | Pass — 21 tests |

## Critical Findings

None.

## Significant Findings

None.

## Minor Findings

None.
