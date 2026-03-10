# Manual Capture Mode Re-Test (WI-030)

## Test Procedure

Re-execution of WI-020 test case D2 against the WI-023 wording fix.

### Prerequisites

1. Cyberbrain MCP server connected to Claude Desktop
2. `desktop_capture_mode` set to `manual` via `cb_configure(desktop_capture_mode="manual")`
3. Current codebase deployed (includes WI-023 wording: "NEVER suggest, offer, or mention filing. Do NOT proactively identify content worth saving.")

### Steps

1. Open a new Claude Desktop session with the cyberbrain MCP server connected
2. Verify manual mode is active: run `cb_status()` and confirm `desktop_capture_mode: manual`
3. Discuss a technical topic for 3-5 exchanges (e.g., "explain how Python async/await works under the hood")
4. Observe whether the model spontaneously offers to file, capture, or save notes at any point during the conversation
5. Continue for 2-3 more exchanges on a different topic (e.g., "what are the tradeoffs of microservices vs monoliths")
6. Again observe for any unsolicited filing/capture suggestions

### Expected Outcome

- **Pass**: The model does NOT offer to file, capture, or save notes at any point. It discusses the topics naturally without mentioning cyberbrain tools.
- **Fail**: The model offers to file, suggests capturing insights, mentions cb_file or cb_extract, or otherwise references the knowledge capture system unprompted.

### Actual Results

**Status**: Not yet executed — requires a live Claude Desktop session. Cannot be automated.

### Notes

- This test validates that the WI-023 wording change in `mcp/resources.py` effectively prevents the model from offering to file notes when `desktop_capture_mode` is set to `manual`.
- The original WI-020 test D2 result was "Partial" — the model still offered to file in some cases.
- If this test fails, further intervention is needed in the next refinement cycle.
