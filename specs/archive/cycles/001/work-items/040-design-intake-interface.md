# WI-040: Design — intake interface

## Objective

Evaluate the current intake tools (`cb_extract`, `cb_file`) and produce a concrete interface design proposal for the intake layer. The design must cover all three intake use cases (session extraction, single-beat capture, document intake), eliminate redundancies, and explicitly list which tools to remove.

This is a design-only work item. Output is a proposal document, not code.

## Acceptance Criteria

- [ ] Design proposal written to `specs/plan/intake-interface-design.md`
- [ ] Proposal documents all three intake use cases:
  1. Session extraction: extract beats from a Claude conversation transcript (existing cb_extract behavior)
  2. Single-beat capture: manually capture a specific insight from the current session (existing cb_file behavior)
  3. Document intake: file a pre-written document (report, research findings, structured output) into the vault without beat extraction
- [ ] Proposal defines a proposed tool set: exact tool names, parameters, and return values for each
- [ ] Proposal explicitly lists which existing tools are removed and which (if any) are renamed
- [ ] Tool count constraint satisfied: the total number of intake tools does not increase relative to what is removed (net change ≤ 0)
- [ ] Proposal includes rationale for each naming and scoping decision
- [ ] Proposal notes any implementation concerns or risks
- [ ] Proposal is concrete enough to be implemented without further design clarification

## File Scope

- `create`: `specs/plan/intake-interface-design.md`

## Dependencies

None.

## Implementation Notes

Read `src/cyberbrain/mcp/tools/extract.py` and `src/cyberbrain/mcp/tools/file.py` to understand current tool signatures and behavior. Read `specs/plan/architecture.md` and `specs/steering/guiding-principles.md` before designing.

Document intake (use case 3) differs from session extraction (use case 1) in a key way: there is no transcript to parse, no LLM extraction step. The document is already structured. The intake operation should add frontmatter, route via autofile (or a specified folder), and add to the search index. This is closer to `cb_file` than `cb_extract` in spirit, but accepts an arbitrary document rather than a single beat description.

The design question is whether document intake belongs in the same tool as single-beat capture (with a mode parameter), or as a separate operation. Evaluate both. The tool count constraint means one option likely requires removing one of the existing tools.

This proposal is presented to the user before any implementation begins (Group 1 pause point).
