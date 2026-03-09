# 002: Manual Validation Test Plan for Automatic Invocation

## Objective
Produce a structured manual test plan that exercises automatic invocation (proactive recall, orient prompt, cyberbrain://guide resource) across Claude Desktop, Claude Code, and any other MCP clients. Execute the plan and document which features work, which don't, and what the failure modes are.

## Acceptance Criteria
- [ ] Test plan document exists at `specs/steering/research/automatic-invocation-validation.md`
- [ ] Test plan covers: proactive_recall config flag behavior, cyberbrain://guide resource loading, orient prompt invocation, recall prompt invocation, mid-session proactive recall triggers
- [ ] Test plan covers each client: Claude Desktop, Claude Code
- [ ] Each test case has: preconditions, steps, expected behavior, actual behavior (filled in during execution), pass/fail
- [ ] Test execution results are recorded with timestamps and client versions
- [ ] Gap analysis section identifies what needs to change for each failed test

## File Scope
- `specs/steering/research/automatic-invocation-validation.md` (create) — test plan and results

## Dependencies
- Depends on: none
- Blocks: 006

## Implementation Notes
This is a research/validation task, not a code change. The goal is to understand the current state before planning improvements.

Key areas to investigate:
- Does `proactive_recall: true` actually trigger cb_recall at session start in Claude Code? Under what conditions?
- Does Claude Desktop auto-fetch the `cyberbrain://guide` resource? Does it affect model behavior?
- Do the `orient` and `recall` MCP prompts appear in Claude Desktop's UI? Do they work when selected?
- Is there a way to make Claude Desktop call cb_recall proactively without the user knowing tool names?
- What happens on mobile Claude (if MCP is supported)?

The results directly inform work item 006 (automatic invocation hardening).

## Complexity
Low
