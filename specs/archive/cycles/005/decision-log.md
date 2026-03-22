# Decision Log — Cycle 005

## Decisions

### D11: Minor test findings fixed silently without new work items

- **When**: Review — cycle 005 code-quality, spec-adherence
- **Decision**: Renamed `test_frontmatter_with_dash_heading_in_body` to `test_non_bare_dashes_not_treated_as_closing_delimiter`; added assertion `dupes1 == {"title": 2}` to `test_idempotent`; added `test_bare_dashes_in_body_preserved` to cover spec's stated parse_frontmatter case 3. All handled in-cycle without creating new work items (minor findings per brrr protocol).

### D12: Positional ordering gap (G2) deferred

- **When**: Review — cycle 005 spec-adherence
- **Decision**: `deduplicate_frontmatter` case 4 wording in `notes/054.md` says "first occurrence establishes position" but implementation uses last-occurrence position (consistent with D8). No test added for positional ordering. The behavioral choice (last-wins, including position) is correct per D8 and matches pyyaml. Spec wording is imprecise — deferred to housekeeping.

---

## Open Questions

### OQ6 [SIGNIFICANT]: `_dependency_map.py` blind to `scripts/` tree

The affected-only test runner cannot map changes to `scripts/repair_frontmatter.py` to `tests/test_repair_frontmatter.py`. A regression in the repair script would pass the affected-only runner silently, defeating OQ1's original intent. Addressed by WI-055 (created in cycle 005 refinement).

---

## Work Item Completion

| WI | Title | Status | Verdict | Findings (C/S/M) |
|---|---|---|---|---|
| 054 | Add automated tests for repair_frontmatter.py | Complete with minor fixes | Pass | 0/0/4 → all fixed/deferred |

---

## Most Important Finding

**SI1 / OQ6**: `tests/_dependency_map.py` does not include a `scripts/` path mapping. Changes to `scripts/repair_frontmatter.py` silently produce "no tests" in the affected-only runner. WI-054 delivered the test file; WI-055 must register it with the runner.
