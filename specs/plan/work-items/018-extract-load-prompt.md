# 018: Extract Duplicated _load_prompt to shared.py

## Objective
Consolidate the four identical `_load_prompt` functions (in `enrich.py`, `review.py`, `restructure.py`, `recall.py`) into a single function in `mcp/shared.py`.

## Acceptance Criteria
- [ ] `mcp/shared.py` exports `_load_tool_prompt(filename: str) -> str`
- [ ] `mcp/tools/enrich.py` imports and uses `_load_tool_prompt` instead of its own `_load_prompt`
- [ ] `mcp/tools/review.py` imports and uses `_load_tool_prompt` instead of its own `_load_prompt`
- [ ] `mcp/tools/restructure.py` imports and uses `_load_tool_prompt` instead of its own `_load_prompt`
- [ ] `mcp/tools/recall.py` imports and uses `_load_tool_prompt` instead of its own `_load_prompt`
- [ ] Local `_load_prompt` definitions removed from all four tool files
- [ ] All existing tests pass (mock targets may need updating)

## File Scope
- `mcp/shared.py` (modify) — add `_load_tool_prompt` function
- `mcp/tools/enrich.py` (modify) — remove local `_load_prompt`, import from shared
- `mcp/tools/review.py` (modify) — remove local `_load_prompt`, import from shared
- `mcp/tools/restructure.py` (modify) — remove local `_load_prompt`, import from shared
- `mcp/tools/recall.py` (modify) — remove local `_load_prompt`, import from shared
- `tests/test_setup_enrich_tools.py` (modify) — update mock targets if needed
- `tests/test_review_tool.py` (modify) — update mock targets if needed
- `tests/test_restructure_tool.py` (modify) — update mock targets if needed
- `tests/test_recall_read_tools.py` (modify) — update mock targets if needed
- `tests/test_mcp_server.py` (modify) — update mock targets if needed

## Dependencies
- Depends on: none
- Blocks: none

## Implementation Notes
The function body is identical in all four files. Example from `enrich.py:22-34`:
```python
def _load_prompt(filename):
    installed = Path("~/.claude/cyberbrain/prompts").expanduser() / filename
    if installed.exists():
        return installed.read_text()
    dev = Path(__file__).parent.parent.parent / "prompts" / filename
    if dev.exists():
        return dev.read_text()
    raise ToolError(f"Prompt file not found: {filename}")
```

Move to `shared.py` as `_load_tool_prompt`. In each tool file, replace:
```python
from shared import _load_config, ...
```
with:
```python
from shared import _load_config, _load_tool_prompt, ...
```

**Test mock targets**: Tests that mock `_load_prompt` on individual tool modules (e.g., `@patch("tools.enrich._load_prompt")`) will need to update to mock `shared._load_tool_prompt` or the tool module's imported name. Check each test file.

## Complexity
Medium
