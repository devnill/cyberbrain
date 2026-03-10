# Work Item 023: Strengthen manual capture mode guide wording

## Objective

Update the manual capture mode wording in `mcp/resources.py` to more effectively suppress model-initiated filing offers, addressing the confirmed test failure from WI-020 test D2.

## Complexity

Low

## Dependencies

None

## File Scope

- `mcp/resources.py` (modify) — update manual mode guide text at line 87-89

## Acceptance Criteria

- [ ] Manual mode guide text uses emphatic language that clearly prohibits unsolicited filing offers
- [ ] The wording includes an explicit "NEVER" or "DO NOT" prohibition on suggesting, offering, or mentioning filing
- [ ] The instruction makes clear that filing should only happen in response to an explicit user request containing words like "save", "file", "capture", or "remember"
- [ ] No other capture modes are affected

## Implementation Notes

- Current wording at `resources.py:87-89`: `"Only call cb_file when the user explicitly asks you to save or file something. Do not proactively identify or offer to file anything."`
- WI-020 test D2 confirmed this is insufficient — model still offered to file
- Recommended replacement: `"NEVER suggest, offer, or mention filing. Do NOT proactively identify content worth saving. Only call cb_file when the user explicitly says words like 'save', 'file', 'capture', or 'remember this'. If unsure whether the user is asking to file, do nothing."`
- This is a prompt engineering change — test by reading the guide resource after the change to verify wording
