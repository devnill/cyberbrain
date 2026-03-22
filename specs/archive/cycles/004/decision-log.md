# Decision Log — Cycle 004

## Decisions

### D1: Repair delivery as standalone script
- **When**: Planning — 2026-03-20 refinement interview
- **Decision**: Vault repair delivered as `scripts/repair_frontmatter.py`, not as a mode of an existing MCP tool.
- **Rationale**: User stated "a manual standalone repair is fine." Repair is a one-time remediation for an existing defect, not an ongoing product capability.

### D2: Guiding principles held unchanged
- **When**: Planning — 2026-03-20 refinement interview
- **Decision**: All 13 guiding principles apply without modification. GP-9 (Dry Run First-Class), GP-10 (YAGNI), GP-6 (Lean Architecture) directly shaped the repair script design.

### D3: No architectural changes in scope
- **When**: Planning — specs/plan/overview.md
- **Decision**: Scope boundary: "No architectural changes. enrich.py is a single-file fix." `scripts/repair_frontmatter.py` not added to architecture component map (low risk per scope decision).

### D4: Line-by-line filter with `skip_continuations` flag
- **When**: Execution — WI-052 rework
- **Decision**: `_apply_frontmatter_update()` rewritten to filter managed keys line-by-line. `skip_continuations` flag suppresses blank/indented/block-sequence lines following a removed managed key.
- **Rationale**: Avoids structured YAML parsing while handling block-sequence tags edge case surfaced in incremental review S1.

### D5: WI-052 required rework
- **When**: Execution — WI-052 incremental review
- **Decision**: Initial implementation rejected (Fail). Block-sequence tags leaked through the line filter (S1) and debug prints were left in the test file (M1/M2/M3).

### D6: Dry-run default for repair script
- **When**: Execution — WI-053
- **Decision**: `--apply` flag required to perform writes. Default is dry-run. GP-9 (Dry Run First-Class).

### D7: stdlib-only constraint for repair script
- **When**: Execution — WI-053
- **Decision**: No third-party packages. Stdlib only (`argparse`, `json`, `pathlib`, `sys`). Enables standalone use without project installation.

### D8: Last-occurrence wins for deduplication
- **When**: Execution — WI-053
- **Decision**: When `deduplicate_frontmatter()` finds a repeated key, it keeps the last occurrence. Consistent with pyyaml behavior and with how enrich.py appends (new values go last).

### D9: Closing-delimiter scan tightened in WI-053 rework
- **When**: Execution — WI-053 incremental review (M1)
- **Decision**: Delimiter scan changed from `rest.find("\n---")` to `rest.find("\n---\n")` with end-of-string fallback. Prevents body lines like `--- heading` from triggering false delimiter detection.

### D10: Output format spec deviation — update spec, not script
- **When**: Review — gap-analysis IR1, spec-adherence N1
- **Decision**: Script produces `- type (3 → 1)` vs spec's `- type (3 duplicates → 1)`. Both reviewers recommend updating `notes/053.md` to match the implementation. No functional change.

---

## Open Questions

### OQ1 [SIGNIFICANT]: `scripts/repair_frontmatter.py` has no automated test coverage

The repair script is the sole remediation mechanism for vault frontmatter corruption. It modifies vault files on disk. The affected-only test runner (`tests/_dependency_map.py`) only maps modules under `src/`, so any change to this script silently reports "no tests" and exits clean. A regression in `parse_frontmatter`, `deduplicate_frontmatter`, or `repair_file` would reach users running `--apply` against live vaults.

**Recommended action**: Create `tests/test_repair_frontmatter.py` (~50 lines, no mocking required). Cover: `parse_frontmatter` (no frontmatter, valid frontmatter, edge delimiters), `find_duplicate_keys` (no duplicates, single, multiple, block-sequence values), `deduplicate_frontmatter` (last-wins, continuation lines preserved), `repair_file` (idempotency, body preservation).

### OQ2 [MINOR]: Repair script scans dotfolders including `.trash`

`rglob("*.md")` includes soft-deleted notes in `.trash`, inflating the repair report count. Fix: filter with `not any(part.startswith(".") for part in f.relative_to(vault_path).parts)`, consistent with `enrich.py:276`.

### OQ3 [MINOR]: No integration test for enrich-then-repair pipeline

The two components are logically consistent (enrich appends last, repair keeps last) but no test verifies the full chain. Deferrable — individual components are tested and strategies are aligned.

### OQ4 [MINOR]: Architecture component map does not list `scripts/repair_frontmatter.py`

Documentation gap. Update `specs/plan/architecture.md` to list alongside `scripts/import.py` in a future housekeeping pass.

### OQ5 [MINOR]: `notes/053.md:71` output format spec not updated

Update spec to match implementation (`- type (3 → 1)`) in a future housekeeping pass.

---

## Work Item Completion

| WI | Title | Status | Verdict | Findings (C/S/M) |
|---|---|---|---|---|
| 052 | Fix duplicate frontmatter fields in `cb_enrich` | Complete with rework | Pass | 0/1/3 → fixed |
| 053 | Standalone vault frontmatter repair script | Complete with rework | Pass | 0/0/2 → fixed |

---

## Most Important Finding

**OQ1**: `scripts/repair_frontmatter.py` has no automated test coverage and is invisible to the affected-only test runner. The script modifies vault files on disk. Regressions would silently pass CI.
