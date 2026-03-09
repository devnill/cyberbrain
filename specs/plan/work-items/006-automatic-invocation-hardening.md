# 006: Automatic Invocation Hardening

## Objective
Make cyberbrain tools invoke automatically in Claude Desktop and Claude Code without the user knowing tool names or manually triggering searches. Fix issues identified in the validation test plan (002).

## Acceptance Criteria
- [ ] All issues identified in the validation test plan (002) are addressed or explicitly deferred with rationale
- [ ] Claude Desktop: `cyberbrain://guide` resource is fetched and influences model behavior at session start
- [ ] Claude Desktop: `orient` prompt works from the UI and produces useful session-start context
- [ ] Claude Code: `proactive_recall` config flag triggers relevant recall at session start without user action
- [ ] Mid-session proactive recall triggers on topic changes (when configured)
- [ ] The system works without the user knowing tool names — natural language like "what do I know about X" routes to the right tool
- [ ] Test coverage for proactive recall logic

## File Scope
- `mcp/resources.py` (modify) — guide content, orient prompt, recall prompt
- `mcp/tools/recall.py` (modify) — proactive recall trigger logic
- `prompts/claude-desktop-project.md` (modify) — system prompt guidance for automatic behavior
- `tests/test_recall_read_tools.py` (modify) — proactive recall tests

## Dependencies
- Depends on: 002 (validation results inform what to fix), 005 (synthesis quality affects whether automatic injection is useful)
- Blocks: none

## Implementation Notes
This depends heavily on what the validation (002) reveals. Possible issues and approaches:

- **Guide resource not auto-loaded:** May need to embed guide content directly in prompt messages rather than relying on resource auto-fetch. Or accept that resources require manual loading and focus on prompts instead.

- **Proactive recall not triggering:** The `proactive_recall` config flag may not be wired up correctly, or the trigger conditions may be wrong. Need to trace the code path.

- **Mid-session recall:** Currently there's no mechanism for the system to detect topic changes and proactively recall. This may require adding guidance to the Claude Desktop system prompt or the guide resource.

- **Natural language routing (D7):** The deferred spec describes intent-to-tool routing. This could be addressed via the guide resource (teaching the model which tool handles which intent) or via a dedicated routing layer.

The key insight from the interview: the user hasn't seen automatic invocation work without prompting. This might be a simple bug, a missing configuration, or a fundamental gap in how MCP resources/prompts work in current Claude Desktop versions.

## Complexity
Medium
