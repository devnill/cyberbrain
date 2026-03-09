# 004: Restructure Pipeline Quality Improvements

## Objective
Improve the quality of vault restructuring across the full curation pipeline — clustering accuracy, merge/split decisions, hub page generation, and content rewriting. Reduce false groupings, minimize required passes, and evaluate whether per-phase model selection or architectural changes (decision/generation split) improve output quality.

## Acceptance Criteria
- [ ] False grouping rate is measurably reduced (measured via evaluation tooling from 001)
- [ ] Restructure operations produce acceptable results in a single pass for the common case (no mandatory re-runs)
- [ ] Clustering strategies (embedding, llm, hybrid) are evaluated against real vault data with documented quality comparisons
- [ ] Decision on D10 (decision/generation split) is made with supporting evidence: either implemented or explicitly re-deferred with rationale
- [ ] Decision on per-phase model selection is made: which phases benefit from stronger models, documented with comparison data
- [ ] Prompt improvements (if any) are validated against baseline using evaluation tooling
- [ ] Existing test suite continues to pass; new tests cover any changed behavior
- [ ] Curation quality improvements extend to autofile, enrichment, and working memory review where applicable (not restructure-only)

## File Scope
- `mcp/tools/restructure.py` (modify) — pipeline logic, grouping, decision/generation phases
- `extractors/search_backends.py` (modify) — clustering quality improvements if needed
- `prompts/restructure-*.md` (modify) — prompt improvements across all 8 restructure prompt files
- `prompts/enrich-*.md` (modify) — enrichment prompt improvements if needed
- `prompts/autofile-*.md` (modify) — autofile prompt improvements if needed
- `prompts/review-*.md` (modify) — review prompt improvements if needed
- `tests/test_restructure_tool.py` (modify) — updated tests for changed behavior
- `mcp/tools/enrich.py` (modify) — if enrichment quality improvements are identified
- `mcp/tools/review.py` (modify) — if review quality improvements are identified
- `extractors/autofile.py` (modify) — if autofile quality improvements are identified

## Dependencies
- Depends on: 001 (evaluation tooling — needed to measure improvements)
- Blocks: 007

## Implementation Notes
This is the hardest work item. The interview identified several interacting problems:

1. **False groupings:** Embedding-based clustering sometimes groups unrelated notes. Root causes may include: poor embedding quality on short metadata, inappropriate distance threshold (0.25), or insufficient pre-filtering.

2. **Multi-pass requirement:** Users need to run restructure multiple times to get acceptable results. This suggests the single-pass pipeline is either too conservative (doesn't do enough) or too aggressive (does the wrong thing and needs correction).

3. **Model capability gap:** Haiku may lack the reasoning capacity for content generation (merging notes, writing hub pages). The D10 decision/generation split would allow using haiku for classification and sonnet/opus for generation.

4. **Audit accuracy:** The audit phase (flag-misplaced, flag-low-quality) needs to be reliable enough that its decisions are trustworthy for downstream phases.

The evaluation tooling (001) is critical here — without the ability to compare alternative approaches quantitatively, improvements are guesswork.

Approach:
1. Use evaluation tooling to baseline current quality on real vault data
2. Identify the highest-impact failure mode (false groupings? bad merges? wrong decisions?)
3. Test targeted fixes: threshold tuning, prompt changes, model upgrades, pipeline changes
4. Measure each change against the baseline
5. Iterate until single-pass quality is acceptable for the common case

This work item explicitly covers the broader curation pipeline (autofile, enrichment, review) because improvements in prompts, model selection, and evaluation methodology apply across tools.

## Complexity
High
