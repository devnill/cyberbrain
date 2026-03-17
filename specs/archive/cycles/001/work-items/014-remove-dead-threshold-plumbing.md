# 014: Remove Dead quality_gate_threshold Plumbing

## Objective
Remove `_get_gate_threshold` function and all references to `quality_gate_threshold` config key. The function is defined and tested but never called in production code — the effective threshold is hardcoded at 0.7 in `quality_gate.py:109`.

## Acceptance Criteria
- [ ] `_get_gate_threshold` function removed from `mcp/tools/restructure.py`
- [ ] `quality_gate_threshold` not accepted by `cb_configure` (if it was — verify)
- [ ] `quality_gate_threshold` not referenced in any production code
- [ ] Tests for `_get_gate_threshold` removed or updated
- [ ] All remaining tests pass

## File Scope
- `mcp/tools/restructure.py` (modify) — remove `_get_gate_threshold` function (line ~1253)
- `tests/test_restructure_tool.py` (modify) — remove tests for `_get_gate_threshold` (line ~2669-2673)

## Dependencies
- Depends on: none
- Blocks: none

## Implementation Notes
The function at `restructure.py:1253`:
```python
def _get_gate_threshold(config):
    return float(config.get("quality_gate_threshold", 0.7))
```
It is never called. Remove the function definition and its tests. Do not modify `quality_gate.py` — the 0.7 threshold there is the correct hardcoded value used by `_parse_verdict`.

Verify `quality_gate_threshold` is not referenced elsewhere (grep the codebase).

## Complexity
Low
