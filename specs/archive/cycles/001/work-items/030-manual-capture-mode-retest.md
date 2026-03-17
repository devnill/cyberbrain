# Work Item 030: Manual capture mode re-test procedure

## Objective

Document the re-test procedure for WI-020 test case D2 (manual capture mode) and execute it to confirm that the WI-023 wording fix actually prevents the model from offering to file notes.

## Complexity

Low

## Dependencies

- 027, 028, 029 (execute last, after all code changes are complete)

## File Scope

- `specs/steering/research/manual-capture-retest.md` (create) — document procedure, expected outcome, and actual results

## Acceptance Criteria

- [ ] Re-test procedure documented with exact steps to reproduce WI-020 test D2
- [ ] Test executed against current implementation (WI-023 wording in place)
- [ ] Result recorded: pass (model does not offer to file) or fail (model still offers)
- [ ] If fail: describe the observed behavior and note that further intervention is needed
- [ ] If pass: confirm WI-023 fix is effective

## Implementation Notes

- WI-020 test D2: "Set `desktop_capture_mode` to `manual` via `cb_configure`. In a Claude Desktop session, discuss a technical topic. Observe whether the model spontaneously offers to file or capture notes."
- WI-023 changed the manual mode guide text in `mcp/resources.py` to use emphatic prohibitions: "NEVER suggest, offer, or mention filing. Do NOT proactively identify content worth saving."
- The test requires a live Claude Desktop session with the cyberbrain MCP server connected.
- This is a manual test — the work item produces a research document with results, not code changes.
- If the test fails, the finding should be noted for the next refinement cycle. Do not attempt code fixes in this work item.
