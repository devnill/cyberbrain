# 017: Make Quality Gate Configurable via cb_configure

## Objective
Add `quality_gate_enabled` to `cb_configure` so users can enable/disable quality gates through MCP tools without editing `config.json` directly. Update error messages in curation tools to reference `cb_configure` syntax instead of raw config keys.

## Acceptance Criteria
- [ ] `cb_configure(quality_gate_enabled=True/False)` writes the key to config.json
- [ ] `cb_configure()` (no args) displays quality gate status when not default
- [ ] `cb_status` displays quality gate status when explicitly set to non-default
- [ ] Error messages in `review.py`, `enrich.py`, `restructure.py` reference `cb_configure(quality_gate_enabled=False)` instead of raw config key
- [ ] `cb_configure` docstring includes quality_gate_enabled parameter
- [ ] Tests cover: setting quality_gate_enabled, displaying it, invalid value rejection
- [ ] All existing tests pass

## File Scope
- `mcp/tools/manage.py` (modify) — add `quality_gate_enabled` parameter to `cb_configure`; add gate status to `cb_status`
- `mcp/tools/review.py` (modify) — update gate-block error messages
- `mcp/tools/enrich.py` (modify) — update gate-block error messages
- `mcp/tools/restructure.py` (modify) — update gate-block error messages
- `tests/test_manage_tool.py` (modify) — add tests for quality_gate_enabled config
- `tests/test_review_tool.py` (modify) — verify updated error message text
- `tests/test_setup_enrich_tools.py` (modify) — verify updated error message text

## Dependencies
- Depends on: 014 (threshold removed — don't add quality_gate_threshold to cb_configure)
- Blocks: none

## Implementation Notes

### cb_configure changes (manage.py)
Add `quality_gate_enabled: bool | None = None` parameter. When set, validate it's a boolean and write to config. Pattern matches existing `tool_models` parameter handling.

For `cb_configure()` no-args display, add after the per-tool model section:
```python
gate_enabled = config.get("quality_gate_enabled")
if gate_enabled is not None:
    lines.append(f"- Quality gate: {'enabled' if gate_enabled else 'disabled'}")
```

### cb_status changes (manage.py)
Add near line 472-476 (per-tool model display):
```python
if not config.get("quality_gate_enabled", True):
    lines.append("- Quality gate: DISABLED")
```

### Error message updates
Replace messages like:
```
"Re-run with quality_gate_enabled=false to proceed."
```
With:
```
"Call cb_configure(quality_gate_enabled=False) to disable quality gates."
```

Search all tool files for `quality_gate_enabled` error message strings and update them consistently.

## Complexity
Medium
