# 020: Execute Automatic Invocation Test Plan

## Objective
Execute the 16-case manual test plan from WI-002 to validate the current state of automatic invocation (proactive recall) across Claude Code and Claude Desktop. Record results to unblock WI-006 (invocation hardening) planning.

## Acceptance Criteria
- [ ] All 16 test cases from the WI-002 test plan have been executed
- [ ] Results recorded with pass/fail/partial for each case
- [ ] Failure modes documented (what happened vs what was expected)
- [ ] Summary of findings: which invocation paths work, which don't, which are partially functional
- [ ] Results saved to `specs/steering/research/invocation-test-results.md`
- [ ] Journal entry with summary of findings

## File Scope
- `specs/steering/research/invocation-test-results.md` (create) — test execution results
- `specs/steering/research/automatic-invocation-validation.md` (reference) — the test plan to execute

## Dependencies
- Depends on: none (independent of code changes)
- Blocks: future WI-006 (invocation hardening)

## Implementation Notes
This is a MANUAL test execution work item. It requires a human to:
1. Read the test plan at `specs/steering/research/automatic-invocation-validation.md`
2. Set up the test environment (Claude Code session, Claude Desktop session)
3. Execute each test case
4. Record observed behavior vs expected behavior
5. Write results to the output file

The executor should present the test plan to the user and guide them through execution, recording results as they go. This is not automatable — it requires real Claude Code and Claude Desktop sessions with a real vault.

## Complexity
Medium (time-intensive, not technically complex)
