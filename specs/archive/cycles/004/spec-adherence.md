# Spec Adherence Review — Cycle 004

**Work items reviewed**: WI-052 (fix duplicate frontmatter in `cb_enrich`), WI-053 (standalone vault frontmatter repair script)

---

## Architecture Deviations

### D1: `scripts/repair_frontmatter.py` not listed in architecture component map

- **Expected**: `specs/plan/architecture.md` lists `scripts/import.py` as the only `scripts/` component.
- **Actual**: `scripts/repair_frontmatter.py` exists and is absent from the component map.
- **Risk**: Low. Script was explicitly planned (WI-053). `specs/plan/overview.md:45` states "No architectural changes" as a deliberate scope decision. Parallels the `scripts/import.py` precedent.

---

## Unmet Acceptance Criteria

### WI-052

- [x] Duplicate prevention — `TestApplyFrontmatterUpdate` tests calling `_apply_frontmatter_update` twice with `overwrite=True`; asserts exactly one occurrence of managed keys.
- [x] Repair of existing duplicates — tests cover notes with pre-existing duplicate keys.
- [x] Field preservation — `test_unmanaged_fields_preserved` asserts `id`, `date`, `session_id`, `project` unchanged.
- [x] S1 fix (block-sequence tags) — `skip_continuations` logic at `src/cyberbrain/mcp/tools/enrich.py:174–183`; verified by `test_block_sequence_tags_replaced_cleanly`.
- [x] M1/M2 fix (debug prints) — no `print(f"DEBUG:` patterns remain in test file.

**All acceptance criteria met.**

### WI-053

- [x] Config loading — `get_vault_path()` checks `args.vault` first, then reads `~/.claude/cyberbrain/config.json`.
- [x] Duplicate detection — `find_duplicate_keys()` correctly identifies repeated top-level keys.
- [x] Last-occurrence deduplication — `deduplicate_frontmatter()` keeps last occurrence.
- [x] Dry-run default — `args.apply` is False by default; no writes in dry-run path.
- [x] `--apply` flag — `scripts/repair_frontmatter.py:206–229` writes only when `args.apply`.
- [x] Final report — summary line printed in both modes.
- [x] Standalone runnable — stdlib only (argparse, json, pathlib, sys).
- [x] Body preserved — body is sliced at closing `\n---` and appended unchanged.
- [x] M1 fix (delimiter scan) — `rest.find("\n---\n")` with end-of-string fallback at lines 62–63.
- [x] M2 fix (unused variable) — `mode_label` variable not present in current implementation.
- [ ] Output format matches spec — `scripts/repair_frontmatter.py:224` produces `- type (3 → 1)` but `notes/053.md:71` specifies `- type (3 duplicates → 1)`. Informational content equivalent; wording deviates from spec.

---

## Principle Violations

None.

---

## Principle Adherence Evidence

- **GP-1 Zero Ceremony**: `scripts/repair_frontmatter.py` defaults to dry-run; `cb_enrich` fix is transparent to callers.
- **GP-2 Vault is Canonical Store**: Both changes operate on vault `.md` files directly; no derived index consulted during repair.
- **GP-3 High Signal-to-Noise**: Fix prevents accumulation of 9+ duplicate frontmatter keys per note observed in production.
- **GP-4 Feels Like Memory**: Not directly testable — both changes are infrastructure operations.
- **GP-5 Vault-Adaptive**: `repair_frontmatter.py` scans via `rglob("*.md")` with no imposed structure.
- **GP-6 Lean Architecture**: Zero non-stdlib dependencies in repair script; no new imports in enrich fix.
- **GP-7 Cheap Models**: Neither change makes any LLM calls.
- **GP-8 Graceful Degradation**: Per-file `OSError`/`UnicodeDecodeError` handling with continue; `_apply_frontmatter_update` returns `False` on failure.
- **GP-9 Dry Run First-Class**: Repair script defaults to dry-run; `cb_enrich` retains `dry_run` parameter.
- **GP-10 YAGNI**: Fix is surgical; repair script is standalone with no new config keys or MCP tools.
- **GP-11 Curation Quality**: Fix directly prevents corrupt YAML frontmatter in vault notes during enrichment.
- **GP-12 Iterative Refinement**: Addresses confirmed production defect without pipeline redesign.
- **GP-13 Works Everywhere**: CLI repair script works from any shell; enrich fix applies to all Claude interfaces via MCP.

---

## Naming/Pattern Inconsistencies

### N1: Output format omits "duplicates" label word

- **Convention**: `specs/plan/notes/053.md:71` specifies `- type (3 duplicates → 1)`.
- **Violation**: `scripts/repair_frontmatter.py:224` produces `- type (3 → 1)`.
- **Severity**: Minor — informational content equivalent.
