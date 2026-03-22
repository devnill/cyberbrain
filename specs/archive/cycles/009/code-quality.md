# Code Quality Review — Cycle 009

**Work items reviewed**: WI-052 through WI-057

---

## Verdict: Pass

No critical or significant findings. Three minor findings — two pre-existing, one intentional architectural duplication documented in the design decisions.

---

## Critical Findings

None.

---

## Significant Findings

None.

---

## Minor Findings

### M1: `enrich.py` closing-delimiter pattern weaker than `repair_frontmatter.py`

- **File**: `src/cyberbrain/mcp/tools/enrich.py:123,153`
- **Pattern**: `content.find("\n---", 3)` matches any line beginning with `---`, including `--- heading` style horizontal rules in note bodies.
- **Contrast**: `repair_frontmatter.py` uses `"\n---\n"` (bare dashes only), introduced as a fix in WI-053 M1.
- **Impact**: Notes with `--- heading` patterns in their body section could be mis-parsed by `cb_enrich` — the horizontal rule would be treated as the frontmatter closing delimiter, leaving frontmatter content in the body. Pre-existing; not introduced by this cycle.
- **Recommendation**: One-line fix mirroring repair_frontmatter.py's approach. Defer.

### M2: `skip_continuations` flag suppresses blank lines after removed managed keys

- **File**: `src/cyberbrain/mcp/tools/enrich.py:174,179–183`
- **Pattern**: The `skip_continuations` flag continues skipping lines that are blank or start with whitespace after a managed key is removed. This means a blank separator line after (e.g.) `tags:` is silently dropped.
- **Impact**: Negligible. YAML frontmatter does not rely on blank lines for structure; the resulting frontmatter parses identically. The blank line is cosmetic. Pre-existing behavior; no regression introduced by this cycle.
- **Recommendation**: Acceptable as-is. No action needed.

### M3: `parse_frontmatter()` duplicated between `repair_frontmatter.py` and canonical `frontmatter.py`

- **Files**: `scripts/repair_frontmatter.py:40–68`, `src/cyberbrain/extractors/frontmatter.py`
- **Gap**: Two independent implementations of frontmatter parsing exist. The repair script's version is intentionally standalone (D7: stdlib-only, no MCP imports).
- **Impact**: Future changes to frontmatter parsing conventions must be applied in both locations. This is a maintenance burden, not a correctness issue.
- **Per design decision D7**: This duplication is explicitly accepted. The repair script is a one-time maintenance utility that must run without the cyberbrain package on the path.
- **Recommendation**: Document the duplication in a comment in repair_frontmatter.py. Defer.

---

## Cross-Cutting Observations

### Enrich ↔ Repair interaction: correct in all orderings

Verified that `_apply_frontmatter_update()` (post-fix, WI-052) and `repair_file()` (WI-053) are compositionally correct:

1. **Enrich then repair**: Post-fix `cb_enrich` produces exactly one instance of each managed key. `repair_file()` on that output finds no duplicates — no-op. Correct.
2. **Repair then enrich**: `repair_file()` on a pre-existing note with duplicates deduplicates to last-occurrence. Subsequent `cb_enrich` call filters managed keys (finds one of each), re-inserts once. Correct.
3. **Double enrich**: Two `cb_enrich` calls on the same note produce exactly one instance of each managed key (fixed by WI-052). Correct.
4. **Enrich on repaired note**: `repair_file()` last-occurrence-wins is consistent with `_apply_frontmatter_update()`'s append behavior — new values go last, so the last occurrence is always the most recent in both strategies. No semantic conflict.

### Error handling complete

- `repair_frontmatter.py`: per-file `OSError` and `UnicodeDecodeError` caught at line 207, per-file write `OSError` caught at line 230. Scan never aborts on single file failure.
- `enrich.py`: existing error handling around file I/O unchanged; no regression.

### No new dependencies introduced

Neither WI-052 nor WI-053 introduces new imports to `pyproject.toml`. `repair_frontmatter.py` uses stdlib only (`pathlib`, `re`, `argparse`, `json`). `enrich.py` modifications are internal rewrites of existing functions.

### Test coverage adequate

- 4 regression tests added to `test_setup_enrich_tools.py` covering the specific defect cases (double overwrite, repair of existing duplicates, unmanaged field preservation, block-sequence replacement).
- 21 tests in `test_repair_frontmatter.py` covering parse_frontmatter detection, find_duplicate_keys, deduplicate_frontmatter (including continuation lines), CLI dry-run/apply modes, config loading, and per-file error handling.
- `_dependency_map.py` now maps `scripts/repair_frontmatter.py` to its test file, so future changes to the repair script will trigger the test suite automatically.
