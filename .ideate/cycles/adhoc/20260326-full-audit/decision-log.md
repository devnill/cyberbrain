# Decision Log — Full Audit

## Key Decisions (Chronological)

### Cycle 015 — Plugin distribution and restructure splitting
- Restructure module split from monolithic 2,171-line file into 10 sub-modules (pipeline.py + 9 phase modules, 3,817 lines total)
- Plugin distribution system adopted for Claude Code installation

### Cycle 016–017 — Quality tooling and tech debt
- CyberbrainConfig TypedDict recreated (WI-083)
- Relation vocabulary migrated to 7-predicate set (WI-086)
- Search backend cache invalidation added (WI-087)
- cb_extract orchestration partially refactored (WI-088) — unified MCP/hook path via `run_extraction()`, but `--beats-json` CLI path retained separate `_write_beats_and_log()`
- `--affected-only` import bug fixed (WI-089) — ast.Import detection was causing ~30% false negatives

### Cycle 018 (planned) — Review follow-up
- Planned: fix `run_extraction()` config parameter, merge `_write_beats_and_log()`, mark T5/T6/T7 resolved
- **Never executed** — work items WI-090 and WI-091 were created but not implemented

### Cycle 020 — Refinement planning
- Refinement planning completed for the cycle 017 findings
- Work items 090-091 created, but no execution cycle followed

## Open Questions

### From domain layer (8 open)
- **Distribution domain** (3 questions): details unknown — likely relate to plugin marketplace, versioning, update mechanisms
- **Retrieval domain** (5 questions): details unknown — likely relate to search quality, ranking, proactive recall behavior

### From this audit
1. **Should C-06 (vault writes through Python) be enforced or relaxed?** — cb_restructure and cb_review violate it. The tension (T1) has been documented since early cycles but no resolution path is defined. Options: (a) route all writes through a shared vault-write helper, (b) formally relax C-06 to allow curation tools to write directly.

2. **Should state.py paths be made lazy?** — Module-level `Path.home()` evaluation creates test fragility and contributed to the config corruption found in this session. The fix is straightforward (function instead of constant) but touches every import site.

3. **Should MCP tools expose dry_run?** — GP-09 says "all destructive operations support dry-run mode" but cb_extract and cb_file don't. The CLI does. Is MCP dry_run needed or is the CLI sufficient?

## Cross-References

### run_extraction() config + duplication cluster
All three reviewers flagged the same root issue:
- **Code review S1**: `run_extraction()` ignores config parameter
- **Code review S2**: `_write_beats_and_log()` duplicates orchestration
- **Spec review**: GP-06 (Lean Architecture) partially violated by duplication
- **Gap analysis IG1/IG2**: integration gap — double config load, divergent code paths
This was the primary finding of cycle 017 review and was planned for cycle 018 (never executed).

### C-06 constraint violation cluster
Two reviewers flagged the vault-write constraint:
- **Spec review S1**: C-06 violated by cb_restructure and cb_review
- **Code review SG1**: suggests consolidating vault-write paths
- Documented as architecture tension T1 since early project lifecycle

### Dry run coverage gap
Two reviewers noted incomplete dry_run support:
- **Spec review M1**: GP-09 not fully implemented for MCP tools
- **Gap analysis IR1**: cb_extract and cb_file lack dry_run
