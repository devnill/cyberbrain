# Decision Log — Cycle 009

**Work items reviewed**: WI-052 through WI-057

---

## Chronological Decision Log

### D1: Duplicate-accumulation defect root cause confirmed

**Date**: 2026-03-20 (WI-052)
**Finding**: `_apply_frontmatter_update()` in `enrich.py` appended managed keys on every call without removing prior instances. On repeated enrichment of the same note, `type:`, `summary:`, `tags:`, and `cb_modified:` accumulated.
**Decision**: Fix by stripping managed keys before re-insertion. Use a stateful line filter (`skip_continuations` flag) to suppress block-sequence continuation lines belonging to removed keys.
**Cross-ref**: code-quality M2 (skip_continuations blank-line behavior — benign).

### D2: Repair script uses stdlib-only implementation (T4 accepted)

**Date**: 2026-03-20 (WI-053)
**Finding**: The repair script reimplements `parse_frontmatter()` independently rather than importing the canonical `src/cyberbrain/extractors/frontmatter.py`.
**Decision**: Accepted as design tension T4. Rationale: the repair script is a maintenance utility that must run without the cyberbrain package installed; stdlib-only constraint (D7) takes precedence over DRY.
**Cross-ref**: code-quality M3 (duplication acknowledged), spec-adherence (no violation per GP-10/YAGNI — each file serves a distinct operational constraint).

### D3: Direct vault writes in repair script consistent with T1

**Date**: 2026-03-20 (WI-053)
**Finding**: `repair_frontmatter.py` writes vault files directly via `Path.write_text()`, bypassing `extract_beats.py`.
**Decision**: Acceptable. Architecture.md T1 documents that curation tools already write vault files directly. The repair script is a maintenance utility operating on existing frontmatter, not a beat-creation path. Per spec-adherence review: no C6/T1 violation.

### D4: Last-occurrence-wins strategy consistent across enrich and repair

**Date**: 2026-03-20 (WI-052, WI-053)
**Finding**: Both `_apply_frontmatter_update()` and `deduplicate_frontmatter()` use last-occurrence-wins semantics.
**Decision**: Correct and intentional. `_apply_frontmatter_update()` appends new values at the end; `repair_file()` keeps the last occurrence of any duplicate. Both strategies converge on the same "most recent value wins" behavior. Interaction correct in all orderings.
**Cross-ref**: gap-analysis (defect completeness verification section), code-quality (enrich↔repair interaction).

### D5: Test coverage gap (scripts/ blind spot) discovered and resolved

**Date**: 2026-03-20 (WI-054 → WI-055 → WI-056 → WI-057)
**Finding cascade**:
1. Cycle 2 review found `_dependency_map.py` could not map `scripts/repair_frontmatter.py` to its tests (significant).
2. WI-055 fixed the mapping but used cwd-relative paths — broken from non-root invocations (cycle 3 review found this significant).
3. WI-056 anchored all paths to `_REPO_ROOT = Path(__file__).parent.parent` — fixed cwd-sensitivity.
4. WI-057 added automated proof via `monkeypatch.chdir(tmp_path)` test.
**Decision**: All four items necessary; none could be deferred without leaving a production gap or an unverified fix. Cascading correctly — each fix exposed the next gap.

### D6: enrich.py delimiter inconsistency explicitly deferred

**Date**: 2026-03-20 (review cycle 009)
**Finding**: `enrich.py` uses `"\n---"` (matches `--- heading` patterns); `repair_frontmatter.py` uses `"\n---\n"` (bare dashes only). The repair script fixed this in WI-053 M1 but enrich.py was not updated in that cycle.
**Decision**: Deferred. Pre-existing; not introduced by this cycle. Fix is a one-line change. No notes in production are known to contain `--- heading` patterns that would trigger the mis-parse. All three reviewers note this consistently.
**Cross-ref**: code-quality M1, spec-adherence M1 (carryover), gap-analysis M1.

### D7: spec-adherence M1 output format — defer, update spec to match implementation

**Date**: 2026-03-20 (review cycle 009)
**Finding**: `notes/053.md` spec shows `(3 duplicates → 1)` but implementation emits `(3 → 1)`.
**Decision**: Deferred per D10 (implementation-led spec updates). The shorter format is unambiguous; spec update is documentation-only work.
**Cross-ref**: spec-adherence M1, gap-analysis M5.

---

## Open Questions

### OQ-M1: enrich.py delimiter fix (carryover from cycle 009)

- **Question**: Should `content.find("\n---", 3)` in `enrich.py` be tightened to `"\n---\n"` to match `repair_frontmatter.py`?
- **Status**: Deferred. Pre-existing. No known affected notes in production. One-line fix available.
- **From**: gap-analysis M1, code-quality M1, spec-adherence M1

### OQ-M2: Repair script scans dotfolders including `.trash`

- **Question**: Should `vault_path.rglob("*.md")` in `repair_frontmatter.py:201` exclude dotfolders?
- **Status**: Deferred. Fix known: `not any(part.startswith(".") for part in f.relative_to(vault_path).parts)`.
- **From**: gap-analysis M2

### OQ-M3: No enrich-then-repair integration test

- **Question**: Should a round-trip test be added (enrich → repair → verify no-op)?
- **Status**: Deferred. Individual components tested; compositional correctness verified analytically.
- **From**: gap-analysis M3

### OQ-M4: Architecture component map missing `repair_frontmatter.py`

- **Question**: Should `specs/plan/architecture.md` component map list `scripts/repair_frontmatter.py`?
- **Status**: Deferred. Documentation-only gap.
- **From**: gap-analysis M4

### OQ-M5: `notes/053.md` output format spec not updated

- **Question**: Should `notes/053.md` be updated to show `(3 → 1)` instead of `(3 duplicates → 1)`?
- **Status**: Deferred. Implementation is correct; spec update is cosmetic.
- **From**: gap-analysis M5, spec-adherence M1

---

## Summary

Cycle 009 reviewed 6 work items addressing a single production defect (duplicate YAML frontmatter on repeated `cb_enrich` calls). The fix cascaded correctly into a repair utility, tests for the utility, and test infrastructure improvements. All acceptance criteria met. No critical or significant gaps. Five minor carryover items explicitly deferred — all are pre-existing, pre-documented, or documentation-only.

The dominant decision pattern of this cycle: each gap was real, each fix was necessary, and each fix exposed the next gap. The cascade from WI-052 → WI-057 was legitimate, not speculative.
