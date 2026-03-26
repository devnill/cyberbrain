# Review Summary

## Overview
The cyberbrain project is in a stable, functional state. All 1310 tests pass, all 11 MCP tools are implemented, and the architecture is substantially followed. Two significant findings from cycle 017 (run_extraction config parameter, orchestration duplication) remain unaddressed after the planned cycle 018 was never executed. No critical issues exist.

## Significant Findings
- [code-reviewer] `run_extraction()` ignores its `config` parameter — always calls `resolve_config(cwd)` regardless, causing double config load per extraction — relates to: GP-06, GP-10 (dead parameter)
- [code-reviewer] `_write_beats_and_log()` duplicates the beat-writing loop from `run_extraction()` — the `--beats-json` CLI path and the normal path can diverge silently — relates to: GP-06, architecture tension T5

## Minor Findings
- [code-reviewer] Test `test_vault_path_rebuild_thread_executes` can corrupt production `config.json` due to fragile `Path.home()` isolation — relates to: C-12
- [code-reviewer] basedpyright reports 2 type errors (CyberbrainConfig assignability) — relates to: C-12
- [code-reviewer] `state.py` evaluates `Path.home()` at import time, making paths untestable without sys.modules manipulation — relates to: C-12, GP-06
- [spec-reviewer] C-06 (vault writes through Python) violated by cb_restructure and cb_review (documented as T1, no resolution path) — relates to: C-06
- [spec-reviewer] Architecture doc tensions T5/T6/T7 not marked resolved — relates to: documentation accuracy
- [gap-analyst] No CI/CD pipeline — pre-commit runs locally only — relates to: C-12
- [gap-analyst] No config backup mechanism — production config was corrupted by test run — relates to: GP-08
- [spec-reviewer] MCP tools cb_extract and cb_file lack dry_run (GP-09 partially unmet) — relates to: GP-09
- [code-reviewer] Restructure pipeline.py at 889 lines remains largest MCP tools module — relates to: T3

## Suggestions
- [code-reviewer] Consolidate vault-write paths to resolve C-06 tension T1
- [code-reviewer] Make `state.py` paths lazy (function instead of module-level constant)
- [gap-analyst] Add config backup-on-write (`config.json.bak` before overwriting)
- [gap-analyst] Extend `cb_status` with system health validation (config, vault path, claude CLI, hook registration)

## Findings Requiring User Input
- **Should C-06 be enforced or formally relaxed?** — cb_restructure and cb_review violate it by design. Tension T1 has been open since early cycles. Options: (a) route curation writes through a shared helper for consistency, (b) amend C-06 to permit curation tools to write directly. Impact of leaving unresolved: continued documentation/reality mismatch, but no functional impact.
- **Should the planned cycle 018 work items (WI-090, WI-091) be executed?** — These fix the two significant findings. They were planned on 2026-03-23 but never started. Impact of leaving unresolved: double config load per extraction, divergent code paths for `--beats-json`.

## Proposed Refinement Plan
Two significant findings warrant a small refinement cycle:
1. Fix `run_extraction()` to use passed config when non-None, remove double load (WI-090, trivial)
2. Merge `_write_beats_and_log()` into `run_extraction()` via optional beats parameter (WI-090, small)
3. Mark architecture tensions T5/T6/T7 as resolved (WI-091, trivial)
4. Fix the 2 basedpyright errors (trivial)

Estimated scope: 2 work items, trivial to small complexity. This is identical to the cycle 018 plan that was never executed.
