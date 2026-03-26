# Refinement Cycle 18 — Cycle 017 Review Follow-up

## What is Changing

Addressing the 2 significant and 3 minor findings from cycle 017 review. Completing the extraction orchestration unification and updating documentation.

## Triggering Context

Cycle 017 review found run_extraction() ignores its config parameter and _write_beats_and_log() remains as residual duplication. Architecture doc tensions T5/T6/T7 were resolved in code but not marked in documentation.

## Scope Boundary

**In scope:**
- Fix run_extraction() to use passed config when non-None
- Merge _write_beats_and_log() into run_extraction() via optional beats parameter
- Mark T5/T6/T7 resolved in specs/plan/architecture.md

**Not in scope:**
- Config documentation pass (deferred — TypedDict is canonical reference)
- CI/CD pipeline
- New features

## Principles / Architecture

No changes to principles. Architecture doc updated to mark resolved tensions.
