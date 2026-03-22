# Gap Analysis — Cycle 004

**Work items reviewed**: WI-052 (enrich.py fix), WI-053 (repair_frontmatter.py)

---

## Missing Requirements from Interview

None. The 2026-03-20 refinement interview contains two Q&A pairs: (1) guiding principles hold unchanged, (2) repair should be a standalone script. Both WI-052 and WI-053 directly address the stated requirements. No expressed requirements are missing from implementation.

---

## Unhandled Edge Cases

### EC1: repair_frontmatter.py does not skip dotfolders

- **Component**: `scripts/repair_frontmatter.py`
- **Gap**: `vault_path.rglob("*.md")` includes notes in dotfolders (`.trash`, `.obsidian`). Soft-deleted notes in `.trash` are scanned and reported, inflating the "found" count with noise.
- **Severity**: Minor — no incorrect writes; only cosmetic output noise. Consistent with Obsidian hiding dotfolders in its UI.
- **Recommendation**: Defer. Fix by adding `not any(part.startswith(".") for part in f.relative_to(vault_path).parts)` filter, consistent with the pattern in `enrich.py:276`.

---

## Incomplete Integrations

### II1: No integration test for enrich-then-repair pipeline

- **Gap**: No test verifies the end-to-end scenario: run enrich with `overwrite=True`, then run repair, assert final state is correct.
- **Severity**: Minor — strategies are logically consistent (enrich appends last, repair keeps last). Individual components are tested.
- **Recommendation**: Defer.

---

## Missing Infrastructure

### MI1: repair_frontmatter.py has no automated test coverage

- **Gap**: No `tests/test_repair_frontmatter.py` exists. The affected-only test runner (`tests/_dependency_map.py`) only maps modules under `src/`, so changes to `scripts/repair_frontmatter.py` silently report "no tests" and exit clean.
- **Impact**: The repair script modifies vault files on disk. Regressions in `parse_frontmatter`, `deduplicate_frontmatter`, or `repair_file` would not be caught before release. This is a data-safety risk.
- **Severity**: Significant — the script is the only mechanism for fixing already-broken vault notes. Regressions could corrupt user data with no automated signal.
- **Recommendation**: Address in a follow-up work item. Tests needed: `parse_frontmatter` (no frontmatter, valid frontmatter, edge delimiters), `find_duplicate_keys` (no duplicates, single, multiple, block-sequence values), `deduplicate_frontmatter` (last-wins, continuation lines preserved), `repair_file` (idempotency, body preservation). ~50 lines, no mocking required.

---

## Implicit Requirements

### IR1: Output format wording diverges from spec

- **Spec**: `notes/053.md:71` — `- type (3 duplicates → 1)`
- **Actual**: `scripts/repair_frontmatter.py:224` — `- type (3 → 1)`
- **Severity**: Minor — informational content equivalent. Recommend updating spec to match implementation rather than reverse.
