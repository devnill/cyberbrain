# WI-041: Design — retrieval interface

## Objective

Evaluate the current retrieval tools (`cb_recall`, `cb_read`) and produce a concrete interface design proposal for the retrieval layer. The design must cover all retrieval use cases (search, direct read, synthesis), eliminate redundancies, and explicitly list which tools to remove.

This is a design-only work item. Output is a proposal document, not code.

## Acceptance Criteria

- [ ] Design proposal written to `specs/plan/retrieval-interface-design.md`
- [ ] Proposal documents all retrieval use cases:
  1. Search: find notes matching a query (semantic, keyword, or hybrid) and return matching results
  2. Direct read: retrieve a specific note by path or title
  3. Context synthesis: produce an injected context block from multiple notes for use in a session
- [ ] Proposal defines a proposed tool set: exact tool names, parameters, and return values for each
- [ ] Proposal explicitly lists which existing tools are removed and which (if any) are renamed
- [ ] Tool count constraint satisfied: the total number of retrieval tools does not increase relative to what is removed (net change ≤ 0)
- [ ] Proposal includes rationale for each naming and scoping decision
- [ ] Proposal notes any implementation concerns or risks
- [ ] Proposal is concrete enough to be implemented without further design clarification

## File Scope

- `create`: `specs/plan/retrieval-interface-design.md`

## Dependencies

None.

## Implementation Notes

Read `src/cyberbrain/mcp/tools/recall.py` (which implements both `cb_recall` and `cb_read`) to understand current tool signatures and behavior. Read `specs/plan/architecture.md` and `specs/steering/guiding-principles.md` before designing.

The current state: `cb_recall` does search and can also synthesize context from results. `cb_read` reads a specific note. The redundancy risk: if `cb_recall` synthesizes, it subsumes `cb_read`'s use case for contextual retrieval, leaving `cb_read` only useful for exact-path access. Evaluate whether these can be merged, and if so, what the unified interface looks like.

The design question is also about what "synthesis" means as a tool interface: is it a separate tool, a mode of the search tool, or a parameter? Evaluate. Synthesis was added in earlier cycles as a distinct capability — any proposal that removes or merges it must preserve its functionality.

This proposal is presented to the user before any implementation begins (Group 1 pause point).
