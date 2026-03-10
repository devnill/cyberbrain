# 016: Add Synthesis Gate Criteria

## Objective
Add a dedicated `### synthesis` section to `quality-gate-system.md` so the synthesis quality gate evaluates against synthesis-specific failure modes rather than falling through to generic `### general` criteria.

## Acceptance Criteria
- [ ] `prompts/quality-gate-system.md` contains a `### synthesis` section
- [ ] Criteria address: hallucinated facts not in source notes, omitted relevant sources, cited titles matching provided sources, synthesis addressing the query
- [ ] `mcp/tools/recall.py` calls `quality_gate(operation="synthesis", ...)` (already does — verify unchanged)
- [ ] Existing tests pass

## File Scope
- `prompts/quality-gate-system.md` (modify) — add `### synthesis` criteria section

## Dependencies
- Depends on: none
- Blocks: none

## Implementation Notes
Add after the `### review_delete` section (or after the new `### restructure_hub` if WI-015 runs first):

```markdown
### synthesis
- The synthesis does not claim facts absent from the provided source notes
- All note titles cited in the synthesis exist in the source notes provided
- No source note containing information directly relevant to the query is omitted from the synthesis
- The synthesis addresses the user's query rather than summarizing unrelated content
- Source attribution is present — the user can trace claims back to specific notes
```

`recall.py:140` already calls `quality_gate(operation="synthesis", ...)`. No code changes needed — this is prompt-only.

## Complexity
Low
