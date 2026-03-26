# Spec Adherence Review — Cycle 017

## Verdict: Pass

Design decisions correctly implemented. One significant finding: run_extraction() ignores its config parameter. Architecture doc tensions not updated.

## Critical Findings

None.

## Significant Findings

### S1: run_extraction() ignores config parameter
- **File**: `src/cyberbrain/extractors/extract_beats.py:53,68`
- **Issue**: `run_extraction(transcript_text, session_id, trigger, cwd, config=None)` accepts a config parameter but line 68 always calls `resolve_config(cwd)` regardless. The MCP tool passes `config=config` at extract.py:93 but it's ignored. Config is loaded twice (once in extract.py, once in run_extraction).
- **Principle**: GP-10 (YAGNI) — unused parameter; GP-6 (Lean Architecture) — double config load
- **Impact**: Functionally harmless (same config both times), but violates the function's documented contract ("config loading if not provided") and wastes a filesystem read.
- **Suggested fix**: Either use the passed config when non-None (`cfg = config if config is not None else resolve_config(cwd)`), or remove the parameter entirely.

## Minor Findings

### M1: Architecture doc design tensions T5, T6, T7 not updated
- **File**: `specs/plan/architecture.md`
- **Issue**: T5 (hook/MCP divergence) partially resolved by WI-088, T6 (search backend cache) resolved by WI-087, T7 (relation vocabulary) resolved by WI-086. None of these are marked resolved in the architecture doc.
- **Impact**: Future readers will see outdated tension descriptions.

### M2: CLAUDE.md relation vocabulary section not updated
- **File**: `CLAUDE.md`
- **Issue**: CLAUDE.md still describes the old SKOS predicates in the Architecture section. The new 7-predicate set from WI-086 is not reflected.
- **Impact**: Developers reading CLAUDE.md get stale relation vocabulary information.

## Unmet Acceptance Criteria

None — WI-088 criteria say "shared orchestration function exists" and it does. The ignored config parameter is a quality issue, not an unmet criterion.

_Note: Spec-reviewer agent exhausted turn limit. Review completed by coordinator using agent's partial analysis._
