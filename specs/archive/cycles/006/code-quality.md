# Code Quality Review — Cycle 006

**Work items reviewed**: WI-055 (_dependency_map.py scripts/ registration)

---

## Verdict: Pass

No critical or significant correctness defects. Two minor structural issues noted.

---

## Critical Findings

None.

---

## Significant Findings

None.

---

## Minor Findings

### M1: `candidate.exists()` and `build()` are cwd-sensitive

- **File**: `tests/_dependency_map.py:13,27`
- **Issue**: `Path("tests").glob("test_*.py")` in `build()` and `Path("tests") / f"test_{source_path.stem}.py"` in `get_tests_for()` resolve against `os.getcwd()`. If pytest is invoked from a non-root directory, both return empty/False silently.
- **Suggested fix**: Anchor to `Path(__file__).parent.parent`.

### M2: Absolute-path `src/` files fall through to convention fallback

- **File**: `tests/_dependency_map.py:19-23`
- **Issue**: If `source_path` is absolute (e.g., from a CI tool), `relative_to("src")` raises `ValueError` and the import-graph result is missed. The convention fallback then looks for `tests/test_enrich.py` (non-existent) and returns empty set.
- **Suggested fix**: Normalize to repo-relative path at the top of `get_tests_for()`.
