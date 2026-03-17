# Work Item 027: Dead code removal and utility consolidation

## Objective

Remove dead code identified by the cycle 3 capstone review and architect analysis. Consolidate duplicated utility functions (`_is_within_vault`, frontmatter parsing) into their canonical locations. Remove stale build artifacts.

## Complexity

Medium

## Dependencies

None

## File Scope

- `mcp/tools/restructure.py` (modify) — remove `_title_concept_clusters()` (lines 223-272), remove `similarity_threshold` parameter, remove local `_is_within_vault()` and import from shared
- `mcp/tools/review.py` (modify) — remove `_WM_RECALL_LOG` constant (line 15), remove local `_is_within_vault()` and import from shared
- `mcp/shared.py` (modify) — add `_is_within_vault()` function (import from vault.py or define once), replace local `_parse_frontmatter()` with import from `frontmatter.py`
- `extractors/analyze_vault.py` (modify) — replace local `parse_frontmatter()` with import from `frontmatter.py`
- `extractors/frontmatter.py` (modify) — no changes expected, but verify it exports `parse_frontmatter()` correctly for both call sites
- `tests/test_restructure_tool.py` (modify) — remove tests for `similarity_threshold`, update any tests referencing removed functions
- `tests/test_review_tool.py` (modify) — update if any tests reference `_WM_RECALL_LOG`
- `tests/test_analyze_vault.py` (modify) — update if frontmatter import path changes
- `dist/*.skill` (delete) — 6 stale pre-MCP skill bundles
- `mcp/shared.py,cover`, `mcp/tools/enrich.py,cover`, `mcp/tools/manage.py,cover`, `mcp/tools/setup.py,cover` (delete) — stale coverage files

## Acceptance Criteria

- [ ] `_WM_RECALL_LOG` constant removed from `review.py`
- [ ] `_title_concept_clusters()` function removed from `restructure.py` (lines 223-272)
- [ ] `similarity_threshold` parameter removed from `cb_restructure` tool signature and any internal references
- [ ] `_is_within_vault()` exists in exactly one location (`mcp/shared.py`); `restructure.py` and `review.py` import it from there; `vault.py` retains its copy (extractor layer, separate import context)
- [ ] `analyze_vault.py` imports `parse_frontmatter` from `frontmatter.py` instead of defining its own
- [ ] `shared.py` imports `_parse_frontmatter` from `frontmatter.py` instead of defining its own (function name may use underscore prefix for internal API consistency)
- [ ] No `.skill` files exist in `dist/`
- [ ] No `.py,cover` files exist in `mcp/`
- [ ] All existing tests pass
- [ ] No new dead code introduced

## Implementation Notes

- `_is_within_vault()` in `vault.py` (extractor layer) should remain — it's used by extractor-layer code that doesn't import from `mcp/shared.py`. The MCP layer gets its own copy in `shared.py`.
- `shared.py` already imports several things from the extractor layer via `sys.path` manipulation (line 8). `_parse_frontmatter` can follow the same pattern — import `parse_frontmatter` from `frontmatter` module, alias as `_parse_frontmatter` for internal API consistency.
- `analyze_vault.py` is in the extractor layer and can import directly: `from frontmatter import parse_frontmatter`.
- The `similarity_threshold` parameter appears in the tool's `@mcp.tool` decorated function signature. Remove it from the parameter list and from any place it's passed through to `_build_clusters()`. Verify `_build_clusters()` does not actually use it (it uses hardcoded `weight >= 2`).
- `_title_concept_clusters()` at lines 223-272 is not called by any code path. Verify with grep before removing.
- For stale file deletion: `dist/cb-enrich.skill`, `dist/cb-extract.skill`, `dist/cb-file.skill`, `dist/cb-recall.skill`, `dist/cb-setup.skill`, `dist/cb-status.skill`. Also delete `mcp/shared.py,cover`, `mcp/tools/enrich.py,cover`, `mcp/tools/manage.py,cover`, `mcp/tools/setup.py,cover`.
