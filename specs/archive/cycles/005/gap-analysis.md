# Gap Analysis — Cycle 005

**Work items reviewed**: WI-054 (test_repair_frontmatter.py)

---

## Critical Gaps

None.

---

## Significant Gaps

### SI1: `tests/_dependency_map.py` does not map `scripts/` to tests

- **Component**: `tests/_dependency_map.py`
- **Issue**: The affected-only test runner resolves test files by calling `source_path.relative_to("src")`. Files under `scripts/` raise `ValueError` and the runner reports "no tests" for any change to `scripts/repair_frontmatter.py`. `test_repair_frontmatter.py` exists but will never be triggered by the affected-only runner on a script change.
- **Impact**: The data-safety goal of OQ1 (cycle 004) is only partially achieved. The test file covers the functions, but the CI runner that gates commits will silently skip it when the repair script changes.
- **Recommendation**: Create WI-055 to extend `_dependency_map.py` with a `scripts/` mapping path or a filename-convention lookup (`test_repair_frontmatter.py` ↔ `scripts/repair_frontmatter.py`).

---

## Minor Gaps

### M1: Enrich-then-repair integration test absent (OQ3 — deferred)

- **Issue**: No test verifies the full `cb_enrich` → `repair_frontmatter` pipeline.
- **Status**: Deferred. Components are individually tested and strategies are logically aligned (D8).

### M2: `notes/053.md` output format not updated (OQ5 — deferred)

- **Issue**: Spec shows `- type (3 duplicates → 1)` but script produces `- type (3 → 1)`.
- **Status**: Deferred. D10 in decision log explicitly calls for spec update in a housekeeping pass.

### M3: Architecture component map missing `repair_frontmatter.py` (OQ4 — deferred)

- **Issue**: `specs/plan/architecture.md` lists `scripts/import.py` but not `scripts/repair_frontmatter.py`.
- **Status**: Deferred. D3 in decision log explicitly deferred this.
