# 010: Integrate Quality Gates into Restructure Pipeline

## Objective
Wire quality gates into the restructure pipeline to catch false groupings, bad merges, and low-quality generated content. When the gate detects a problem, surface it to the user rather than committing a bad result.

## Acceptance Criteria
- [ ] The restructure decide phase runs its proposed actions through the quality gate before executing
- [ ] The restructure generate phase (merge content, hub pages) runs generated content through the gate
- [ ] False groupings are caught: when the gate flags a proposed cluster as low-confidence, the tool reports uncertainty and asks for confirmation
- [ ] Low-quality generated content triggers a retry with the same or stronger model before surfacing to user
- [ ] Dry-run mode shows gate verdicts alongside proposed actions
- [ ] The gate does not fire when the restructure operation is simple and high-confidence (no unnecessary LLM calls)
- [ ] Existing restructure tests pass; new tests cover gated behavior

## File Scope
- `mcp/tools/restructure.py` (modify) — integrate quality_gate() calls after decide and generate phases
- `prompts/quality-gate-system.md` (modify) — add restructure-specific evaluation criteria
- `tests/test_restructure_tool.py` (modify) — tests for gated restructure behavior

## Dependencies
- Depends on: 009 (quality gate infrastructure)
- Blocks: none

## Implementation Notes
The restructure pipeline has distinct phases where gates add value:

1. **After grouping/clustering** — gate evaluates whether proposed groups are topically coherent. This catches false groupings early.
2. **After decide phase** — gate evaluates whether proposed actions (merge, split, create hub) make sense for the cluster.
3. **After generate phase** — gate evaluates whether the generated content (merged note, hub page) is accurate and complete.

For phase 1 (grouping), the gate prompt should ask: "Are these notes topically related enough to be in the same group?" This is where false groupings are caught.

For phase 3 (generate), the gate prompt should check: "Does this merged note faithfully represent all source notes without losing information?"

The confidence threshold for proceeding without user confirmation should be configurable (default: 0.7). Below threshold, the tool reports what it would do and asks for confirmation.

The audit phase already exists and runs before structural decisions. The quality gate is complementary — the audit catches misplaced/low-quality individual notes; the gate catches bad groupings and bad generated output.

Restructure.py is 2,171 lines. Changes should be surgical — add gate calls at the three integration points, not refactor the pipeline.

## Complexity
Medium
