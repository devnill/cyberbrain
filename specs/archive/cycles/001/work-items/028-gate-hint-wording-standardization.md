# Work Item 028: Gate hint wording standardization

## Objective

Standardize the `cb_configure(quality_gate_enabled=False)` hint wording across all gate-blocked output paths to use the imperative form established in `review.py`.

## Complexity

Low

## Dependencies

- 027 (overlapping file: `restructure.py`)

## File Scope

- `mcp/tools/enrich.py` (modify) — change hint wording at line 395
- `mcp/tools/restructure.py` (modify) — change hint wording in `_format_gate_verdicts()`
- `tests/test_setup_enrich_tools.py` (modify) — update assertion for new wording
- `tests/test_restructure_tool.py` (modify) — update assertion for new wording

## Acceptance Criteria

- [ ] `enrich.py` gate-blocked output uses: `"Call cb_configure(quality_gate_enabled=False) to disable quality gates."`
- [ ] `restructure.py` `_format_gate_verdicts()` uses: `"Call cb_configure(quality_gate_enabled=False) to disable quality gates."`
- [ ] `review.py` wording unchanged (it is already the canonical form)
- [ ] All three tools produce identical hint text when gate-blocked
- [ ] Tests updated to assert the new wording
- [ ] All existing tests pass

## Implementation Notes

- Current wording in `enrich.py:395`: `"To disable quality gates: cb_configure(quality_gate_enabled=False)"`
- Current wording in `restructure.py` `_format_gate_verdicts()`: `"To disable quality gates: cb_configure(quality_gate_enabled=False)"`
- Target wording (from `review.py:350` and `review.py:359`): `"Call cb_configure(quality_gate_enabled=False) to disable quality gates."`
- This is a string replacement in 2 source files + corresponding test assertion updates.
