# 015: Fix Gate Criteria Dispatch for Split and Hub Operations

## Objective
Fix two gate dispatch bugs where split-candidate and hub-spoke operations are evaluated against `restructure_merge` criteria instead of their correct operation-specific criteria.

## Acceptance Criteria
- [ ] `_gate_decisions` dispatches split-candidate decisions (keyed by `note_index`) to `"restructure_split"` operation
- [ ] `_gate_decisions` dispatches hub-spoke and subfolder cluster decisions to `"restructure_hub"` operation (new)
- [ ] `_gate_generated_content` dispatches hub-spoke and subfolder actions to `"restructure_hub"` operation (new)
- [ ] `prompts/quality-gate-system.md` contains a `### restructure_hub` section with hub-appropriate criteria
- [ ] Merge decisions still use `"restructure_merge"`
- [ ] Generate-phase split dispatch remains `"restructure_split"` (already correct)
- [ ] Tests cover all three dispatch paths (merge, split, hub)
- [ ] All existing tests pass

## File Scope
- `mcp/tools/restructure.py` (modify) — fix dispatch logic in `_gate_decisions` (~line 1307) and `_gate_generated_content` (~line 1373)
- `prompts/quality-gate-system.md` (modify) — add `### restructure_hub` criteria section
- `tests/test_restructure_tool.py` (modify) — add tests for split and hub dispatch

## Dependencies
- Depends on: none
- Blocks: none

## Implementation Notes

### _gate_decisions fix (restructure.py ~line 1307)
Currently:
```python
verdict = quality_gate("restructure_merge", input_ctx, output_text, config)
```
Change to dispatch on decision type:
```python
if "cluster_index" in decision:
    action = decision.get("action", "merge")
    operation = "restructure_hub" if action in ("hub-spoke", "subfolder") else "restructure_merge"
else:
    operation = "restructure_split"
verdict = quality_gate(operation, input_ctx, output_text, config)
```

### _gate_generated_content fix (restructure.py ~line 1373)
Currently dispatches merge vs split but not hub. Add hub-spoke/subfolder → `"restructure_hub"`.

### restructure_hub criteria (quality-gate-system.md)
Add after the `### restructure_split` section:
```markdown
### restructure_hub
- Hub page title is descriptive and aids navigation
- All spoke notes are wikilinked from the hub
- Hub provides sufficient orienting context for each note without reproducing full content
- Hub structure reflects the actual thematic relationships between notes
- No spoke note is omitted from the hub page
```

## Complexity
Low
