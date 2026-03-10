# Work Item 025: Documentation corrections from cycle 2 review

## Objective

Fix residual documentation errors identified by the cycle 2 capstone review that WI-019 missed or introduced incorrectly.

## Complexity

Low

## Dependencies

None

## File Scope

- `specs/plan/architecture.md` (modify) — fix prompt variable table rows for `enrich-user.md` and `review-user.md`; update tool count from 10 to 11
- `specs/plan/modules/mcp-tools.md` (modify) — fix `_synthesize_recall` parameter names and types
- `specs/plan/modules/mcp-server.md` (modify) — update tool count from 10 to 11
- `specs/plan/modules/prompts.md` (modify) — fix `enrich-user.md` variable list (`{notes_batch}` → `{count}`, `{notes_block}`)
- `extractors/evaluate.py` (modify) — fix stale docstring referencing removed MCP tool
- `specs/plan/work-items/006-automatic-invocation-hardening.md` (modify) — update with WI-020 findings, replace speculative notes with confirmed facts

## Acceptance Criteria

- [ ] `architecture.md` prompt variable table: `enrich-user.md` row shows `{count}`, `{notes_block}` (not `{vault_type_context}`); `review-user.md` row shows `{note_count}`, `{vault_prefs_section}`, `{notes_block}`
- [ ] `architecture.md` and `mcp-server.md` report 11 tools (not 10)
- [ ] `mcp-tools.md:28` reads `_synthesize_recall(query, retrieved_content, note_summaries, config)` with correct types
- [ ] `prompts.md:23` reads `Variables: {count}, {notes_block}` for `enrich-user.md`
- [ ] `evaluate.py` docstring no longer references `mcp/tools/evaluate.py` or `cb_evaluate`
- [ ] WI-006 implementation notes updated with WI-020 confirmed findings (B1: auto-fetch unsupported, C1-C4: orient works, A5: mid-session recall works, D2: manual mode insufficient); acceptance criteria narrowed to confirmed gaps
- [ ] No code changes — documentation and comments only (except evaluate.py docstring)

## Implementation Notes

- These are all errors from the cycle 2 capstone review: code-quality M1/M2/M3, spec-adherence D1/D2/D3/U1, gap-analysis II1
- The incremental review for WI-019 passed without catching these — verify actual file content against source code this time
- For WI-006 update: reference `specs/steering/research/invocation-test-results.md` for the confirmed findings
