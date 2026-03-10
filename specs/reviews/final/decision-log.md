# Decision Log — Cycle 3 Capstone (WI-021 through WI-026)

## Decision Log

### Planning Phase

#### DL1: Retroactive planning capture for existing codebase
- **When**: Planning — interview Q1
- **Decision**: Establish ideate artifact structure retroactively over an existing ~7,200 LOC codebase rather than planning from scratch. Move existing specs to `specs/legacy/` for safekeeping.
- **Rationale**: Codebase was mature but lacked a structured planning framework; goal was to enable continued refinement cycles using the ideate process.

#### DL2: Two active workstreams defined
- **When**: Planning — interview Q2
- **Decision**: Scope the plan to (1) vault curation quality improvement and (2) retrieval improvement targeting RAG with automatic invocation.

#### DL3: Vault CLAUDE.md as single source of truth for beat types
- **When**: Planning — architecture document
- **Decision**: Beat type vocabulary defined by the vault's CLAUDE.md, not hardcoded. The system reads the vault's CLAUDE.md before extraction.

#### DL4: All vault writes routed through Python
- **When**: Planning — architecture document
- **Decision**: All vault writes go through `extract_beats.py` or `import.py`. Known deviation documented as T1 design tension.

#### DL5: Soft delete via trash folder
- **When**: Planning — architecture document
- **Decision**: All vault note deletions move files to `trash_folder` using `_move_to_trash()`.

#### DL6: MCP server as single interface
- **When**: Planning — architecture document
- **Decision**: The MCP server is the sole user-facing interface. No slash command skills.

#### DL7: Three LLM backends with claude-code as default
- **When**: Planning — architecture document
- **Decision**: Three backends: `claude-code`, `bedrock`, `ollama`. Direct Anthropic SDK removed (YAGNI).

#### DL8: Dry run as first-class feature
- **When**: Planning — guiding principles (Principle 9)
- **Decision**: All destructive operations support dry-run mode.

#### DL9: YAGNI discipline
- **When**: Planning — guiding principles (Principle 10)
- **Decision**: Features must earn their way in through demonstrated need.

#### DL10: Graph ML approaches deferred pending research
- **When**: Planning — interview Q4/Q5
- **Decision**: Knowledge graph ML augmentation placed in scope for research but not implementation. WI-003 findings: not viable at personal vault scale.

#### DL11: Evaluation tooling as internal dev tool
- **When**: Refinement Interview 1
- **Decision**: `cb_evaluate` removed from MCP server. `extractors/evaluate.py` preserved as internal dev tooling.

#### DL12: Quality gates built into curation tools
- **When**: Refinement Interview 1
- **Decision**: LLM-as-judge quality gates integrated into `cb_restructure`, `cb_enrich`, and `cb_review`.

#### DL13: Per-tool model selection
- **When**: Refinement Interview 1
- **Decision**: `get_model_for_tool(config, tool)` allows per-tool model configuration. Resolves T2.

### Execution Phase — Cycle 1 (WI-008 through WI-013)

#### DL14: `Verdict` enum with three states
- **When**: WI-009 rework
- **Decision**: Three-state Verdict enum (pass/fail/uncertain) rather than boolean.

#### DL15: Graph expansion deferred
- **When**: Refinement Interview 1, following WI-003
- **Decision**: SQL-based graph expansion deferred until RAG synthesis validated.

#### DL16: Security demarcation on synthesis output
- **When**: WI-012 rework
- **Decision**: All retrieval output wrapped with security demarcation.

### Execution Phase — Cycle 2 (WI-014 through WI-020)

#### DL17: Remove `quality_gate_threshold` (YAGNI)
- **When**: WI-014
- **Decision**: Dead threshold plumbing removed.

#### DL18: `quality_gate_enabled` configurable via `cb_configure`
- **When**: WI-017
- **Decision**: Settable, displayed in cb_status and no-args output.

#### DL19: Execute invocation test plan
- **When**: WI-020
- **Decision**: 16 manual tests executed. Results: 12 pass, 2 fail, 1 partial, 1 expected fail.

#### DL20: Extract `_load_prompt` to shared.py
- **When**: WI-018
- **Decision**: Centralized prompt loading in `mcp/shared.py`.

### Execution Phase — Cycle 3 (WI-021 through WI-026)

#### DL21: Gate-blocked output hints standardized
- **When**: WI-021
- **Decision**: `cb_configure(quality_gate_enabled=False)` hint added to restructure.py and review.py FAIL branch, completing the pattern from WI-017.

#### DL22: `proactive_recall` settable via `cb_configure`
- **When**: WI-022
- **Decision**: Added following the `quality_gate_enabled` pattern.

#### DL23: Manual capture mode wording strengthened
- **When**: WI-023
- **Decision**: NEVER/DO NOT prohibitions added. Behavioral effectiveness not yet re-validated.

#### DL24: Orient guidance added to cb_setup
- **When**: WI-024
- **Decision**: `_SETUP_GUIDANCE` constant appended to both Phase 2 return paths.

#### DL25: Mock vault testing infrastructure
- **When**: WI-026
- **Decision**: 5 vault variants with deploy/reset/status/teardown scripts.

#### DL26: wm-recall.jsonl deployed to ~/.claude/cyberbrain/
- **When**: WI-026 rework (S1)
- **Decision**: Copied to correct location during deploy/reset. Introduced teardown data loss risk (OQ3).

#### DL27: Environment variables for shell-to-Python data passing
- **When**: WI-026 rework (S2)
- **Decision**: All helpers use env vars instead of string interpolation.

#### DL28: SHA-256 checksums for modification detection
- **When**: WI-026 rework (S3)
- **Decision**: Replaced file count comparison with checksums.

#### DL29: Hint wording inconsistency deferred
- **When**: Cycle 3 capstone review (M3)
- **Decision**: Not corrected in cycle 3.

---

## Open Questions

### OQ1: `tests/vaults/empty/` directory does not exist
The empty vault variant was never created. `list` advertises it but `deploy empty` fails. Blocks first-run onboarding testing.
**Source**: spec-adherence S1, gap-analysis S1

### OQ2: `.obsidian/` marker directories absent from all vault variants
No variant has the `.obsidian/` directory. `cb_configure(discover=True)` cannot find deployed vaults.
**Source**: spec-adherence S2, gap-analysis S2

### OQ3: `teardown` destroys user's real `wm-recall.jsonl`
Deploy overwrites `~/.claude/cyberbrain/wm-recall.jsonl` without backup. Teardown does not restore it.
**Source**: code-quality S1

### OQ4: Dead `_WM_RECALL_LOG` constant in review.py
Defined at line 15 but never used. No work item tracks removal.
**Source**: code-quality M1, gap-analysis M1

### OQ5: Gate-blocked hint wording inconsistency
enrich.py/restructure.py use colon format; review.py uses imperative with period.
**Source**: code-quality M3

### OQ6: Manual capture mode behavioral effectiveness unconfirmed
WI-023 strengthened wording but WI-020 test D2 was not re-executed to verify the fix works.
**Source**: journal WI-023, WI-020 results

### OQ7: Restructure pipeline complexity (T3)
`restructure.py` is 2,171 lines with monolithic orchestration. No resolution path defined.
**Source**: architecture T3

### OQ8: Relation vocabulary divergence (T7)
`VALID_PREDICATES` in vault.py vs prompt-instructed vocabulary. Richer predicates silently normalized to "related".
**Source**: architecture T7

### OQ9: Duplicate frontmatter parsing (T4)
Three independent implementations; `frontmatter.py` is canonical but not universally used.
**Source**: architecture T4

### OQ10: Invocation hardening (WI-006) still deferred
2 of 16 manual tests failed. No work item created to address findings.
**Source**: journal WI-020

### OQ11: Graph expansion scheduling
No validation checkpoint established to re-evaluate graph expansion.
**Source**: journal WI-003, DL15

---

## Cross-References

### CR1: Mock vault empty + .obsidian/
spec-adherence S1/S2 and gap-analysis S1/S2 independently found the same structural gaps. Both stem from Git not tracking empty directories. Fix: `.gitkeep` files.

### CR2: wm-recall.jsonl data loss
Code-quality S1 was the only reviewer to catch this. Related to DL26 — the fix for wrong-directory introduced the data-loss problem.

### CR3: Manual capture mode
WI-023 (DL23) strengthened wording but no reviewer flagged the unvalidated behavioral fix. OQ6 captures this.

### CR4: Dead _WM_RECALL_LOG
code-quality M1 and gap-analysis M1 independently identified the same dead constant. No tracking item exists.
