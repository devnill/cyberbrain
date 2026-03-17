# WI-042: Implement new intake interface

## Objective

Implement the intake interface design approved in WI-040. Replace existing intake tools with the new interface, implement document intake mode, delete old tool implementations and tests, and write new tests.

## Acceptance Criteria

- [ ] All tools listed as "removed" in the WI-040 design are deleted from `src/cyberbrain/mcp/tools/`
- [ ] All tools listed as "removed" are unregistered from `src/cyberbrain/mcp/server.py`
- [ ] New tools defined in the WI-040 design are implemented in `src/cyberbrain/mcp/tools/`
- [ ] New tools are registered in `src/cyberbrain/mcp/server.py`
- [ ] Document intake mode: accepts a pre-written document string, adds frontmatter (title, type, tags, date), routes via autofile or specified folder, writes to vault, adds to search index — no LLM extraction step
- [ ] Test files for removed tools are deleted
- [ ] New test files cover all new tool parameter combinations and error paths
- [ ] `uv run pytest tests/` passes with 0 failures
- [ ] CLAUDE.md tool list updated to reflect new intake interface

## File Scope

- `modify`: `src/cyberbrain/mcp/server.py`
- `modify` or `delete`: `src/cyberbrain/mcp/tools/extract.py`
- `modify` or `delete`: `src/cyberbrain/mcp/tools/file.py`
- `create` (if new tool files needed): `src/cyberbrain/mcp/tools/{new-tool-name}.py`
- `modify` or `delete`: `tests/test_extract*.py` (tests for removed tools)
- `modify` or `delete`: `tests/test_manage_tool.py` (if intake-related tests exist here)
- `create`: `tests/test_{new-tool-name}.py` (tests for new tools)
- `modify`: `CLAUDE.md`

## Dependencies

- WI-040 (intake interface design, user-approved)

## Implementation Notes

The exact file scope depends on the approved WI-040 design. Read `specs/plan/intake-interface-design.md` before writing any code.

For document intake mode: the document arrives as a string parameter. Add YAML frontmatter (title derived from first heading or a `title` parameter, `type` from a parameter with default, `tags` from a parameter, `date` as today). Route via autofile if `folder` is not specified. Write to vault using the existing `_write_beat` or equivalent path. Index the new file using the existing search index write path.

Do not add a new LLM call for document intake — the document is already structured. Autofile routing (which does call the LLM) is acceptable if the user hasn't specified a folder.

Follow existing patterns in `src/cyberbrain/mcp/tools/` for error handling, vault path validation, and return value format.
