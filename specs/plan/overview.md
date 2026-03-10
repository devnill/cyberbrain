# Refinement Cycle 4 — Dead Code Cleanup, Utility Consolidation, and Consistency Fixes

## What is Changing

Cycle 3 capstone review identified 4 minor findings. Architect analysis of the codebase surfaced additional dead code, duplicated utilities, and a misleading predicate guidance instruction. This cycle addresses all findings plus validates the manual capture mode fix from WI-023.

Key changes:
1. **Remove dead code** — `_WM_RECALL_LOG` constant, `_title_concept_clusters()` function, `similarity_threshold` dead parameter, stale `.skill` bundles and `.py,cover` files
2. **Consolidate duplicated utilities** — `_is_within_vault()` (3 copies → 1), frontmatter parsing (4 implementations → 1 canonical import)
3. **Standardize gate hint wording** — enrich.py and restructure.py aligned to review.py's imperative form
4. **Fix cb_setup predicate guidance** — stop instructing LLM to define domain-specific predicates that get silently normalized to "related"
5. **Validate manual capture mode** — re-execute WI-020 test D2 against the WI-023 fix

## Triggering Context

- Cycle 3 capstone review minor findings (M1 dead code, M3 hint inconsistency)
- Architect codebase analysis (dead functions, dead parameters, duplicated utilities, stale artifacts)
- Decision log open questions OQ4-OQ6

## Scope Boundary

**In scope:** Dead code removal, utility consolidation, hint wording standardization, predicate guidance fix, manual capture mode re-test.

**Not in scope:** Restructure pipeline refactoring (T3), graph expansion (DL15), invocation hardening (WI-006), architecture changes.

## Expected Impact

- Reduced dead code and duplication across the codebase
- Single canonical frontmatter parsing implementation used everywhere
- Consistent gate-blocked hint wording across all curation tools
- Vault CLAUDE.md no longer suggests unsupported relation predicates
- Manual capture mode effectiveness confirmed or flagged for further work

## New Work Items

027-030 (4 items). See `plan/work-items/` for details.
