# WI-044: Improved clustering and filing accuracy

## Objective

Fix the clustering bug in `cb_restructure` identified in WI-038. Implement vault history injection into autofile routing to improve filing accuracy for future beats.

## Acceptance Criteria

- [ ] Clustering bug fixed per WI-038 diagnosis: the specific parameter or algorithm change identified in research is applied
- [ ] Cluster quality is measurably better: test cases that previously produced bad clusters now produce semantically coherent ones
- [ ] Vault history injection implemented in autofile routing: a sample of existing notes from candidate folders is included in the autofile prompt as examples
- [ ] Vault history injection is bounded: at most N notes (configurable, default per WI-038 recommendation) are sampled per candidate folder to avoid token bloat
- [ ] When no notes exist in a candidate folder (new folder), routing proceeds without history injection (graceful fallback)
- [ ] Tests cover: clustering with fixed parameters, autofile with history injection, autofile without history (empty folder), vault history sampling respects the configured limit
- [ ] `uv run pytest tests/` passes with 0 failures

## File Scope

- `modify`: `src/cyberbrain/mcp/tools/restructure.py` (clustering algorithm parameters)
- `modify`: `src/cyberbrain/mcp/tools/file.py` or `src/cyberbrain/extractors/extract_beats.py` (autofile routing with history injection)
- `modify`: `prompts/autofile-system.md` and/or `prompts/autofile-user.md` (update template to accept example notes)
- `modify`: `tests/test_restructure_tool.py`
- `modify`: `tests/test_setup_enrich_tools.py` (if autofile tests live here)

## Dependencies

- WI-038 (research findings identifying the specific clustering bug and history injection approach)

## Implementation Notes

Read WI-038's research output at `specs/steering/research/filing-accuracy-clustering.md` before implementing. Apply the exact fix recommended there — do not invent a different approach.

For vault history injection: before calling the autofile LLM, read a sample of existing note titles (and optionally first paragraph) from each candidate folder. Inject these as examples into the prompt so the LLM can calibrate its routing decision. The sampling should be deterministic (e.g., most-recently-modified N notes) to avoid non-deterministic test behavior.

Keep the clustering fix minimal: change only the parameter(s) identified in the research. Do not refactor the entire clustering pipeline.
