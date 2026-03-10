# Work Item 029: Fix cb_setup predicate guidance

## Objective

Fix the `cb_setup` prompt instruction that tells the LLM to define "2-4 domain-specific" relation predicates. These custom predicates are silently normalized to `"related"` by `vault.py`'s `resolve_relations()`, making the instruction misleading and the generated CLAUDE.md inaccurate.

## Complexity

Low

## Dependencies

None

## File Scope

- `mcp/tools/setup.py` (modify) — fix the relation predicate instruction (around line 114)
- `tests/test_setup_enrich_tools.py` (modify) — update test if it asserts on the old instruction text

## Acceptance Criteria

- [ ] `cb_setup` does not instruct the LLM to define domain-specific relation predicates beyond the 6 base predicates
- [ ] The instruction references only the supported predicates: `related`, `references`, `broader`, `narrower`, `supersedes`, `wasDerivedFrom`
- [ ] Generated vault CLAUDE.md will not suggest users can define custom relation predicates
- [ ] All existing tests pass

## Implementation Notes

- `vault.py:161` defines `VALID_PREDICATES = {"related", "references", "broader", "narrower", "supersedes", "wasDerivedFrom"}`. Any predicate not in this set is normalized to `"related"` by `resolve_relations()` (line 198).
- The extraction prompt (`prompts/extract-beats-system.md`) already lists only the 6 base predicates and is consistent with the code.
- The fix is to the setup.py instruction that generates the vault CLAUDE.md, not to the extraction prompt or vault.py.
- The instruction should list the 6 supported predicates and not suggest adding custom ones. This aligns with YAGNI (Principle 10) — if custom predicates are ever needed, `VALID_PREDICATES` should be extended first.
