# 001: Evaluation Tooling Framework

## Objective
Build a framework for comparing alternative outputs from curation tools (extraction, autofile, restructure, enrichment, review) so that heuristic refinement can be data-driven rather than ad-hoc. Replace the current crude dry-run approach with structured side-by-side comparison.

## Acceptance Criteria
- [ ] A CLI tool or MCP tool that accepts a vault note (or set of notes) and a curation operation, runs the operation with multiple configurations (model, prompt variant, parameters), and presents results side-by-side
- [ ] Output includes: input notes, each variant's output, diff between variants, and a structured quality assessment
- [ ] Supports at minimum: restructure (merge/split/hub), enrichment (frontmatter generation), and extraction (beat quality)
- [ ] Results are persisted to a reviewable format (markdown or JSON) for longitudinal tracking
- [ ] Can be run non-destructively (no vault writes) against real vault data
- [ ] Test coverage for the evaluation framework itself

## File Scope
- `extractors/evaluate.py` (create) — core evaluation engine
- `mcp/tools/evaluate.py` (create) — optional MCP tool wrapper
- `tests/test_evaluate.py` (create) — tests for evaluation framework
- `prompts/evaluate-system.md` (create) — quality assessment prompt (if LLM-scored)

## Dependencies
- Depends on: none
- Blocks: 004, 005

## Implementation Notes
This is the cross-cutting concern identified in the interview. The key design question is how to structure "variants" — options include:
- Multiple model tiers (haiku vs sonnet vs opus) on same prompt
- Multiple prompt variants on same model
- Multiple parameter settings (clustering threshold, max_clusters, grouping strategy)

The framework should be agnostic to what varies — it runs N configurations, collects outputs, and presents them. Quality scoring can be manual (human picks the best), LLM-scored (a judge model rates each), or both.

Consider whether this should integrate with the existing dry-run infrastructure or be a separate tool. Dry-run shows "what would happen"; evaluation shows "which approach produces the best result."

Longitudinal tracking matters: when a prompt change improves restructure quality, the evaluation results should demonstrate the improvement over the previous baseline.

## Complexity
High
