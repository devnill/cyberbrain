# Gap Analysis — Cycle 006

**Work items reviewed**: WI-055 (_dependency_map.py scripts/ registration)

---

## Critical Gaps

None.

---

## Significant Gaps

### SI1: `_dependency_map.py` path resolution is cwd-relative (breaks non-root invocation)

- **Component**: `tests/_dependency_map.py`
- **Issue**: `build()` uses `Path("tests").glob("test_*.py")` and `get_tests_for()` uses `candidate.exists()` where candidate is `Path("tests") / ...`. Both resolve against `os.getcwd()`. If pytest is run from any directory other than the repo root, the mapper silently returns empty sets for all changed files — including the `scripts/` mapping that WI-055 was created to provide.
- **Impact**: Defeats the purpose of WI-055. In CI environments where the working directory is not the repo root, changes to `scripts/repair_frontmatter.py` would still silently bypass `test_repair_frontmatter.py`.
- **Pre-existing context**: The `build()` relative path issue pre-existed WI-055. WI-055 added `candidate.exists()`, which has the same latent issue in new code.
- **Recommendation**: Create WI-056 to anchor all path operations to `Path(__file__).parent.parent`. One-line fix per occurrence.

---

## Minor Gaps

### M1: Repair script scans dotfolders including `.trash` (OQ2 — still deferred)

### M2: No enrich-then-repair integration test (OQ3 — still deferred)

### M3: Architecture component map missing repair script (OQ4 — still deferred)

### M4: `notes/053.md` output format not updated (OQ5 — still deferred)

### M5: `deduplicate_frontmatter` positional ordering untested (G2 — still deferred)
