# WI-043: Filing confidence and uncertainty handling

## Objective

Extend autofile routing to return a per-beat confidence score. Add a new config key `uncertain_filing_behavior` that controls what happens when confidence is below a threshold: route to inbox or prompt the user. Implement confidence-based routing in the filing pipeline.

## Acceptance Criteria

- [ ] Autofile LLM call returns a confidence score for each routing decision (0.0–1.0 range or categorical equivalent per WI-038 recommendation)
- [ ] New config key `uncertain_filing_behavior` with values `"inbox"` and `"ask"` is added to `~/.claude/cyberbrain/config.json` schema
- [ ] Default value for `uncertain_filing_behavior` is `"inbox"`
- [ ] A configurable `uncertain_filing_threshold` (float, default per WI-038 recommendation) is added to the config schema
- [ ] When confidence < threshold and behavior is `"inbox"`: beat is routed to the inbox folder with a note in its frontmatter indicating uncertain routing
- [ ] When confidence < threshold and behavior is `"ask"`: a clarification prompt is returned to the user before writing (mechanism per WI-038 recommendation)
- [ ] When confidence ≥ threshold: beat is routed normally with no change in behavior
- [ ] `cb_configure` `no-args` display shows the current `uncertain_filing_behavior` and threshold values
- [ ] `cb_configure` accepts `uncertain_filing_behavior` and `uncertain_filing_threshold` as settable parameters
- [ ] Tests cover: high-confidence routing (unchanged), low-confidence inbox routing, low-confidence ask routing
- [ ] `uv run pytest tests/` passes with 0 failures

## File Scope

- `modify`: `src/cyberbrain/mcp/tools/file.py` (or whichever file contains autofile routing after WI-042)
- `modify`: `src/cyberbrain/extractors/extract_beats.py` (if autofile routing happens here for session extraction)
- `modify`: `src/cyberbrain/mcp/tools/manage.py` (cb_configure)
- `modify`: `src/cyberbrain/mcp/shared.py` (config defaults and loading)
- `modify`: `prompts/autofile-system.md` and/or `prompts/autofile-user.md` (add confidence score to LLM output format)
- `modify`: `tests/test_manage_tool.py`
- `modify`: `tests/test_setup_enrich_tools.py` (if autofile tests live here)

## Dependencies

- WI-038 (research findings on confidence scoring design)

## Implementation Notes

Read WI-038's research output at `specs/steering/research/filing-accuracy-clustering.md` before implementing. Use the confidence scoring approach recommended there.

The autofile prompt currently asks the LLM to select a folder. Extend the output format to also include a confidence field. Parse the confidence from the LLM response alongside the folder selection.

For `uncertain_filing_behavior: "ask"`: the MCP tool should return a response asking the user to confirm the folder before writing, rather than writing immediately. The write should only happen after confirmation. Consider whether this needs a two-step tool call pattern or can be handled in a single call with a clear prompt.

Keep the change backward-compatible: if `uncertain_filing_behavior` is absent from config, default to `"inbox"` (safest fallback, no behavior change for existing users).
