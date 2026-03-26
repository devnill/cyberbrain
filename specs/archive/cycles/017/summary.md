# Review Summary — Cycle 017 Tech Debt and Design Decisions

## Overview

Cycle 017 addressed 7 items: CyberbrainConfig TypedDict recreation, README cleanup, relation vocabulary migration, search backend cache invalidation, cb_extract orchestration refactor, and --affected-only import fix. All items function correctly (1310 tests pass, 0 pyright errors). The extraction refactor partially achieves its goal — the MCP/hook path is unified but the --beats-json CLI path retains a separate orchestration function.

## Significant Findings
- [code-reviewer] run_extraction() accepts a config parameter but ignores it — always calls resolve_config(cwd) regardless — relates to: WI-088, GP-6/GP-10
- [gap-analyst] _write_beats_and_log() is residual orchestration duplicate — --beats-json path bypasses run_extraction() — relates to: WI-088

## Minor Findings
- [spec-reviewer] Architecture doc tensions T5, T6, T7 not marked resolved — relates to: cross-cutting documentation
- [spec-reviewer] CLAUDE.md relation vocabulary section not updated to new 7-predicate set — relates to: WI-086
- [gap-analyst] Config docs incomplete vs TypedDict (32 fields vs 13-25 documented) — relates to: WI-083

## Findings Requiring User Input
None — all findings can be resolved from existing context.

## Proposed Refinement Plan
Two significant findings warrant a small follow-up:
1. Fix run_extraction() config parameter (use passed config or remove param) — trivial
2. Merge _write_beats_and_log() into run_extraction() with optional beats param — small
3. Update architecture doc tensions T5/T6/T7 as resolved — trivial
4. Update CLAUDE.md relation vocabulary — trivial

Estimated scope: 2-3 work items, trivial to small complexity. Can be bundled into next cycle.
