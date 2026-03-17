# WI-047: Update vault CLAUDE.md schema and regenerate current vault

## Objective

Update the vault CLAUDE.md schema template to reflect the new tool names and capabilities from this refinement cycle (new intake tools from WI-042, new retrieval tools from WI-046, confidence scoring from WI-043). Then regenerate the user's current live vault's CLAUDE.md from the updated schema.

**IMPORTANT**: This work item writes to the user's live vault. The executor must read the current vault CLAUDE.md, prepare a diff of proposed changes, present it to the user, and wait for explicit approval before writing anything.

## Acceptance Criteria

- [ ] Vault CLAUDE.md schema template (in `src/cyberbrain/mcp/tools/setup.py` or equivalent) updated to reference new tool names
- [ ] Schema template reflects accurate tool count after WI-042 and WI-046 changes
- [ ] Proposed changes to the live vault's CLAUDE.md are presented to the user as a diff before writing
- [ ] User explicitly approves the changes before any file is written to the live vault
- [ ] Live vault CLAUDE.md is regenerated only after approval
- [ ] No other vault files are modified
- [ ] `uv run pytest tests/` passes with 0 failures after schema template update

## File Scope

- `modify`: `src/cyberbrain/mcp/tools/setup.py` (schema template)
- `modify`: `tests/test_setup_enrich_tools.py` (update tool name references in schema tests)
- **User's live vault `CLAUDE.md`** (written only after user approval — not a source file in this repo)

## Dependencies

- WI-042 (new intake interface — determines new tool names)
- WI-043 (filing confidence — new config keys to document in CLAUDE.md)

## Implementation Notes

This work item has two distinct phases:

**Phase 1 (no user approval needed):** Update the schema template in `setup.py`. This is a source code change — update the tool references, add documentation for `uncertain_filing_behavior` and `uncertain_filing_threshold` config keys, update tool count. Run tests.

**Phase 2 (user approval required):** Read the user's live vault CLAUDE.md (path from `~/.claude/cyberbrain/config.json` → `vault_path` + the configured CLAUDE.md location). Diff the current content against what `cb_setup` would generate with the updated schema. Present the diff to the user. Only write if approved.

The executor must not skip Phase 2's approval gate. Present the diff in a readable format (unified diff or side-by-side). If the user modifies the proposed changes, apply their modifications before writing.
