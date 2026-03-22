# Gap Analysis — Cycle 009

**Work items reviewed**: WI-052 through WI-057

---

## Critical Gaps

None.

---

## Significant Gaps

None.

---

## Minor Gaps

### M1: `enrich.py` closing-delimiter scan uses `"\n---"` (inconsistent with repair script)

- **File**: `src/cyberbrain/mcp/tools/enrich.py:123,153`
- **Gap**: `content.find("\n---", 3)` matches any line starting with `---`, including `--- heading` lines in note bodies. The repair script fixed this to `"\n---\n"` (WI-053 M1). Notes with `--- heading` patterns in the body could be mis-parsed by `cb_enrich`. Pre-existing; not introduced by this cycle.
- **Impact**: Minor — affects only notes with Markdown horizontal rules (`---`) in their body section. `cb_enrich` would treat the horizontal rule as the frontmatter closing delimiter, leaving frontmatter content in the "body". Such notes would not be correctly enriched.
- **Recommendation**: Defer. Fix is a one-line change mirroring repair_frontmatter.py's approach.

### M2: Repair script scans dotfolders including `.trash` (OQ2 — carryover)

- **File**: `scripts/repair_frontmatter.py:201`
- **Gap**: `vault_path.rglob("*.md")` includes `.trash`, `.obsidian`, and any other dotfolder contents. Inflates the count and rewrites soft-deleted notes.
- **Recommendation**: Defer. Fix: `not any(part.startswith(".") for part in f.relative_to(vault_path).parts)`.

### M3: No enrich-then-repair integration test (OQ3 — carryover)

- **Gap**: No test exercises the full round-trip: enrich a note with the fixed `_apply_frontmatter_update()`, run `repair_file()` on the result, verify it's a no-op.
- **Recommendation**: Defer. Individual components are tested and strategies are logically aligned (last-occurrence-wins in both).

### M4: Architecture component map does not list `repair_frontmatter.py` (OQ4 — carryover)

- **File**: `specs/plan/architecture.md`
- **Gap**: Component map lists `scripts/import.py` but not `scripts/repair_frontmatter.py`.
- **Recommendation**: Defer. Documentation-only gap.

### M5: `notes/053.md` output format spec not updated (OQ5 — carryover)

- **Gap**: Spec shows `(3 duplicates → 1)`, implementation emits `(3 → 1)`.
- **Recommendation**: Defer. Update spec to match implementation per D10.

---

## Defect Completeness Verification

**Other curation tools with similar write patterns**: Checked `restructure.py` and `review.py`. Both use `content[:end] + provenance_lines + content[end:]` patterns, but exclusively on freshly LLM-generated content that does not yet contain those fields. They do not repeatedly enrich the same note with the same keys. The duplicate-accumulation defect was specific to `_apply_frontmatter_update()` in `enrich.py` (the only function that overwrites fields in an existing note on repeated calls). No analogous defect sites exist in other curation tools.

**Enrich + repair workflow**: Correct in all orderings. Post-fix `cb_enrich` produces exactly one instance of each managed key. `repair_file()` on that output is a no-op. A second `cb_enrich` call on a repaired note filters-then-inserts correctly. The last-occurrence-wins strategy in repair_frontmatter.py is consistent with enrich.py's append behavior (new values go last, so the last occurrence is always the most recent).

---

## Summary

The primary defect and its direct consequences are fully addressed. No critical or significant gaps remain. Four minor carryover items from prior cycles remain explicitly deferred. The enrich.py delimiter inconsistency (M1) is a pre-existing latent issue worth tracking but does not affect the correctness of this cycle's work.
