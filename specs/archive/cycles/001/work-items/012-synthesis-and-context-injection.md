# 012: RAG Synthesis and Context Injection

## Objective
Improve the existing synthesis in cb_recall to produce token-efficient, LLM-optimized context injection. Move the synthesis prompt from inline code to a prompt template file. Ensure cross-client parity.

## Acceptance Criteria
- [ ] Synthesis prompt moved from inline string in recall.py to `prompts/synthesize-system.md` and `prompts/synthesize-user.md`
- [ ] Synthesis output is formatted for LLM consumption (structured sections, source citations, relevance indicators) not human reading
- [ ] Token efficiency: synthesis extracts relevant paragraphs/facts, not full note bodies
- [ ] When `synthesize=True`, only the synthesis is returned (full note cards are available via cb_read follow-up)
- [ ] When `synthesize=False`, current behavior is preserved (note cards with top-2 full bodies)
- [ ] Cross-client: synthesis produces identical output regardless of which MCP client invokes it
- [ ] Quality gate applied to synthesis output (catch hallucination, missing sources)
- [ ] Existing recall tests pass; new tests cover synthesis formatting and quality

## File Scope
- `mcp/tools/recall.py` (modify) — refactor _synthesize_recall, use prompt templates, integrate quality gate
- `prompts/synthesize-system.md` (create) — synthesis system prompt
- `prompts/synthesize-user.md` (create) — synthesis user prompt template
- `tests/test_recall_read_tools.py` (modify) — synthesis tests

## Dependencies
- Depends on: 009 (quality gate for synthesis validation)
- Blocks: none

## Implementation Notes
The current synthesis is minimal (recall.py lines 69-97): an inline system prompt, a simple user message, and a hardcoded output format. This works but:

1. The prompt is not editable without code changes
2. The output format (synthesis + full note cards below) is wasteful — it includes both the synthesis and all the raw cards
3. There's no quality check on the synthesis

The refactored synthesis should:
1. Load prompts from files (same pattern as enrich, restructure)
2. Include source note metadata (title, type, tags) in the prompt so the LLM can cite properly
3. Format output as structured context: `## Relevant Knowledge\n{synthesis}\n## Sources\n{note titles with paths}`
4. Run the synthesis through quality_gate() to catch hallucination (synthesis claims something not in source notes)
5. On gate failure, fall back to returning note cards without synthesis

The synthesis prompt should instruct the LLM to:
- Extract only information relevant to the query
- Cite source notes by title
- Flag when multiple notes contain contradictory information
- Prioritize recent notes over older ones when content conflicts

## Complexity
Medium
