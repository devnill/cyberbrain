# WI-046: Implement new retrieval interface

## Objective

Implement the retrieval interface design approved in WI-041. Replace existing retrieval tools with the new interface, delete old tool implementations and tests, and write new tests.

## Acceptance Criteria

- [ ] All tools listed as "removed" in the WI-041 design are deleted from `src/cyberbrain/mcp/tools/`
- [ ] All tools listed as "removed" are unregistered from `src/cyberbrain/mcp/server.py`
- [ ] New tools defined in the WI-041 design are implemented in `src/cyberbrain/mcp/tools/`
- [ ] New tools are registered in `src/cyberbrain/mcp/server.py`
- [ ] All three retrieval use cases are covered: search (semantic/keyword/hybrid), direct read by path or title, context synthesis
- [ ] Test files for removed tools are deleted
- [ ] New test files cover all new tool parameter combinations and error paths
- [ ] `uv run pytest tests/` passes with 0 failures
- [ ] CLAUDE.md tool list updated to reflect new retrieval interface

## File Scope

- `modify`: `src/cyberbrain/mcp/server.py`
- `modify` or `delete`: `src/cyberbrain/mcp/tools/recall.py`
- `create` (if new tool files needed): `src/cyberbrain/mcp/tools/{new-tool-name}.py`
- `modify` or `delete`: `tests/test_recall_read_tools.py`
- `create`: `tests/test_{new-tool-name}.py` (tests for new tools)
- `modify`: `CLAUDE.md`

## Dependencies

- WI-041 (retrieval interface design, user-approved)

## Implementation Notes

The exact file scope depends on the approved WI-041 design. Read `specs/plan/retrieval-interface-design.md` before writing any code.

The current `cb_recall` implementation in `src/cyberbrain/mcp/tools/recall.py` handles both `cb_recall` (search + optional synthesis) and `cb_read` (direct read). Any new implementation must preserve all three underlying capabilities (search, read, synthesis) even if they are reorganized into different tool boundaries.

Follow existing patterns in `src/cyberbrain/mcp/tools/` for error handling, vault path validation, search index access, and return value format.
