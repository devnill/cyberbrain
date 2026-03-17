# 011: Quality Gates for Enrichment and Review

## Objective
Integrate quality gates into cb_enrich and cb_review to catch classification errors and bad review decisions. These tools use cheap models for classification — the gate validates that classifications are reasonable.

## Acceptance Criteria
- [ ] cb_enrich runs batch classification results through the quality gate before applying frontmatter updates
- [ ] Enrichment gate catches: wrong type assignment, nonsensical summaries, irrelevant tags
- [ ] cb_review runs promote/extend/delete decisions through the quality gate
- [ ] Review gate catches: premature deletion of still-relevant working memory, incorrect promotion
- [ ] Low-confidence enrichment results are skipped (not applied) and reported to the user
- [ ] Low-confidence review decisions are flagged for user confirmation
- [ ] Existing tests pass; new tests cover gated behavior

## File Scope
- `mcp/tools/enrich.py` (modify) — gate call after LLM classification, before frontmatter write
- `mcp/tools/review.py` (modify) — gate call after LLM review decision, before executing action
- `prompts/quality-gate-system.md` (modify) — add enrich and review evaluation criteria
- `tests/test_setup_enrich_tools.py` (modify) — tests for gated enrichment
- `tests/test_review_tool.py` (modify) — tests for gated review

## Dependencies
- Depends on: 009 (quality gate infrastructure)
- Blocks: none

## Implementation Notes
For enrichment, the gate evaluates each classification in the batch response. The question it answers: "Given this note's content, is this type/summary/tags assignment reasonable?" A note about Python decorators classified as type "problem" with tags ["cooking"] would fail the gate.

For review, the gate evaluates the promote/extend/delete decision. The question: "Given this working memory note's content and age, is this action appropriate?" Deleting a 3-day-old note about an active bug would fail the gate.

Both tools already process results in batches. The gate should evaluate per-item, not per-batch — a bad classification for one note shouldn't block correct classifications for others.

The enrichment gate is highest value because enrichment runs in batch and classification errors compound (wrong type → bad search results → bad recall).

## Complexity
Medium
