# Work Item 021: Add cb_configure hint to gate-blocked output in restructure.py and review.py

## Objective

Add `cb_configure(quality_gate_enabled=False)` hint to all gate-blocked output paths that currently omit it, matching the pattern established in `enrich.py:395` and `review.py:350` (UNCERTAIN path).

## Complexity

Low

## Dependencies

None

## File Scope

- `mcp/tools/restructure.py` (modify) — add hint to `_format_gate_verdicts()` at line 1719
- `mcp/tools/review.py` (modify) — add hint to the FAIL branch at line 356
- `tests/test_restructure_tool.py` (modify) — add test asserting hint appears in gate-flagged output
- `tests/test_review_tool.py` (modify) — add test asserting hint appears in FAIL verdict output

## Acceptance Criteria

- [ ] `_format_gate_verdicts()` in `restructure.py` includes "To disable quality gates: cb_configure(quality_gate_enabled=False)" when `has_issues` is True
- [ ] `review.py` FAIL branch includes "Call cb_configure(quality_gate_enabled=False) to disable quality gates." matching the UNCERTAIN branch wording
- [ ] Test in `test_restructure_tool.py` mocks quality gate to return a failing verdict and asserts `cb_configure(quality_gate_enabled=False)` appears in the formatted output
- [ ] Test in `test_review_tool.py` mocks quality gate to return a FAIL verdict and asserts `cb_configure(quality_gate_enabled=False)` appears in the result
- [ ] All existing tests pass

## Implementation Notes

- `restructure.py:1717-1722`: Inside the `if has_issues:` block, append the hint line after the existing note. Match wording from `enrich.py:395`: `"To disable quality gates: cb_configure(quality_gate_enabled=False)"`
- `review.py:356-359`: Append the hint to the message assembled for the FAIL branch. Match wording from `review.py:350` (UNCERTAIN branch): `"Call cb_configure(quality_gate_enabled=False) to disable quality gates."`
- Existing test patterns: `test_setup_enrich_tools.py` has enrich gate tests; follow the same mock pattern for restructure and review
