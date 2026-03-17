# 008: Remove cb_evaluate from MCP Server

## Objective
Remove the cb_evaluate tool from the MCP server interface. The evaluation framework remains as internal developer tooling in `extractors/evaluate.py` but is not a product feature. The MCP server should only expose tools that provide value during regular usage.

## Acceptance Criteria
- [ ] `cb_evaluate` is no longer registered as an MCP tool
- [ ] `mcp/tools/evaluate.py` is deleted
- [ ] `mcp/server.py` no longer imports or registers the evaluate module
- [ ] `extractors/evaluate.py` is preserved as-is (internal dev tool)
- [ ] `prompts/evaluate-system.md` is preserved (used by extractors/evaluate.py)
- [ ] Test suite passes (remove or update any tests that depend on cb_evaluate being an MCP tool)
- [ ] `tests/test_evaluate.py` continues to pass (tests extractors/evaluate.py, not the MCP wrapper)

## File Scope
- `mcp/server.py` (modify) — remove evaluate import and registration
- `mcp/tools/evaluate.py` (delete) — MCP tool wrapper no longer needed
- `tests/test_evaluate.py` (verify) — should still pass since it tests extractors/evaluate.py

## Dependencies
- Depends on: none
- Blocks: none

## Implementation Notes
Simple removal. The `mcp/tools/evaluate.py` wrapper calls `extractors/evaluate.py` which is preserved. Only the MCP-facing surface is removed.

In `mcp/server.py`, remove:
- The `evaluate` import from the `from tools import ...` line
- The `evaluate.register(mcp)` call

Delete `mcp/tools/evaluate.py`.

Verify `tests/test_evaluate.py` still passes — it imports from `extractors/evaluate.py` directly, not from the MCP tool.

## Complexity
Low
