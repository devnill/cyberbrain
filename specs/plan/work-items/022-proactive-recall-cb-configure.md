# Work Item 022: Add proactive_recall to cb_configure

## Objective

Make `proactive_recall` settable via `cb_configure` and visible in `cb_status` and the no-args display, following the `quality_gate_enabled` pattern from WI-017.

## Complexity

Low

## Dependencies

None

## File Scope

- `mcp/tools/manage.py` (modify) — add `proactive_recall` parameter, no-args display, cb_status display
- `tests/test_manage_tool.py` (modify) — add tests for setting, displaying, and invalid value rejection

## Acceptance Criteria

- [ ] `cb_configure(proactive_recall=True)` and `cb_configure(proactive_recall=False)` write to config.json
- [ ] `cb_configure()` no-args display shows `proactive_recall: disabled` when set to False (hidden when True/default)
- [ ] `cb_status` shows `Proactive recall: DISABLED` when set to False
- [ ] Tests cover: setting True, setting False, no-args display when disabled, no-args hidden when default
- [ ] All existing tests pass

## Implementation Notes

- Follow the exact pattern from `quality_gate_enabled` (lines 145-147 for parameter, 313-315 for write logic)
- No-args display: add after the `quality_gate_enabled` check — `if cfg.get("proactive_recall") is False: lines.append("Proactive recall: disabled")`
- cb_status: add near the quality gate status check — `if not config.get("proactive_recall", True): lines.append("- Proactive recall: DISABLED")`
- Update the docstring for `cb_configure` to include `proactive_recall=True/False`
