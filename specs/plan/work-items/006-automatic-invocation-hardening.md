# 006: Automatic Invocation Hardening

## Objective
Make cyberbrain tools invoke automatically in Claude Desktop and Claude Code without the user knowing tool names or manually triggering searches. Fix issues identified in the validation test plan (002).

## Acceptance Criteria
- [ ] All issues identified in the validation test plan (002) are addressed or explicitly deferred with rationale
- [ ] Claude Desktop: orient prompt works from the UI and produces useful session-start context (confirmed working — C1, C2)
- [ ] Claude Desktop: proactive recall triggers reliably after orient prompt loads the guide (confirmed working — A1, A5)
- [ ] Claude Code: CLAUDE.md instructions effectively drive tool usage as a substitute for guide resource (confirmed working — A4)
- [ ] Mid-session proactive recall triggers on topic changes in Desktop (confirmed working — A5)
- [ ] Manual capture mode enforcement is strengthened — model currently still offers to file in manual mode (D2 partial pass)
- [ ] The system works without the user knowing tool names — natural language like "what do I know about X" routes to the right tool (confirmed working — D1)
- [ ] Test coverage for proactive recall logic

## File Scope
- `mcp/resources.py` (modify) — guide content, orient prompt, recall prompt
- `mcp/tools/recall.py` (modify) — proactive recall trigger logic
- `prompts/claude-desktop-project.md` (modify) — system prompt guidance for automatic behavior
- `tests/test_recall_read_tools.py` (modify) — proactive recall tests

## Dependencies
- Depends on: 002 (validation results inform what to fix), 005 (synthesis quality affects whether automatic injection is useful)
- Informed by: 020 (WI-020 invocation test results — see `specs/steering/research/invocation-test-results.md`)
- Blocks: none

## Implementation Notes

Findings from WI-020 validation (see `specs/steering/research/invocation-test-results.md`):

- **Guide resource auto-fetch unsupported (B1):** Claude Desktop does not auto-fetch `cyberbrain://guide`. The guide only loads when the user selects the orient prompt. This means proactive recall in Desktop requires the user to explicitly select orient at session start. Accept this limitation — focus on making orient discoverable rather than trying to auto-fetch the resource.

- **Orient and recall prompts work well (C1-C4):** Both prompts appear in the Desktop connector picker and execute correctly. Orient loads guide content and triggers cb_status + cb_recall. Recall prompt scans for unfamiliar topics mid-session. These are confirmed working and need no changes.

- **Mid-session recall works (A5):** Topic shifts within a Desktop session (after orient) correctly trigger proactive cb_recall. No code changes needed for this.

- **CLAUDE.md is the path for Code (A4):** CLAUDE.md instructions effectively replicate guide behavior in Claude Code. cb_setup should ensure the generated CLAUDE.md includes recall-on-topic-mention instructions.

- **Manual capture mode insufficient (D2):** In manual mode, the model still offers to file when it should not. The guide says "only when asked" but the model's helpfulness overrides the instruction. Needs stronger wording (e.g., "Do NOT offer to file anything") or removal of the filing suggestion entirely in manual mode.

- **Tool discovery from descriptions works (D1):** Both clients find and use tools from MCP tool descriptions alone, without needing the guide resource. Natural language routing works.

- **proactive_recall config toggle works (A3):** Setting proactive_recall: false correctly suppresses automatic cb_recall calls in Desktop.

### Remaining work
1. Strengthen manual capture mode enforcement in guide resource text
2. Ensure cb_setup generates CLAUDE.md with recall-on-topic-mention instructions for Claude Code
3. Consider adding a reminder about the orient prompt to cb_setup output or first-run experience
4. Add proactive_recall to cb_configure parameters (currently only settable by editing config.json)

## Complexity
Medium
