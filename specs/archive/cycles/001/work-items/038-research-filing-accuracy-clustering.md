# WI-038: Research — filing accuracy and clustering

## Objective

Investigate and document: (1) the root cause of clustering quality issues in `cb_restructure`, (2) approaches to improve autofile routing accuracy, (3) per-beat confidence scoring design, and (4) learning from vault history to improve future routing decisions.

This is a research-only work item. No code changes.

## Acceptance Criteria

- [ ] Research report written to `specs/steering/research/filing-accuracy-clustering.md`
- [ ] Report diagnoses the clustering bug: which algorithm, what threshold/linkage parameters, what failure mode (over-splitting, under-splitting, or semantic mismatch)
- [ ] Report evaluates at least two alternative clustering approaches (e.g., different distance metrics, threshold values, or algorithm choices)
- [ ] Report proposes a concrete confidence scoring design: what score means (0.0–1.0 range or categorical), how it is computed from autofile LLM output, how it maps to routing decisions
- [ ] Report proposes how vault history can be injected into the autofile prompt to improve accuracy (e.g., sampling existing notes from candidate folders as examples)
- [ ] Report identifies any risks or failure modes in the proposed approaches
- [ ] All proposals are concrete enough for a implementation work item to execute without further research

## File Scope

- `create`: `specs/steering/research/filing-accuracy-clustering.md`

## Dependencies

None.

## Implementation Notes

Read the current clustering implementation in `src/cyberbrain/mcp/tools/restructure.py` and the autofile implementation in `src/cyberbrain/mcp/tools/file.py` (or wherever autofile routing lives). Read the restructure grouping strategies documented in `CLAUDE.md` and `specs/plan/architecture.md`.

The clustering bug likely manifests as: notes with different topics being placed in the same cluster, or notes that belong together being split across clusters. Look at the threshold value (0.25 in embedding mode) and the linkage method (average) as the first hypothesis.

For confidence scoring: the autofile prompt already asks the LLM to select a folder. Extending it to also output a confidence score (0.0–1.0 or low/medium/high) is the proposed direction. The research should determine whether this works reliably or whether a separate validation call is needed.
