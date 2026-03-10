# Project Journal

## [plan] 2026-03-09 — Retroactive planning session completed
Captured the existing cyberbrain codebase (~7,200 LOC, 16 test modules) into ideate artifact structure. Produced 10 module specs, full architecture document with 8 design tensions identified, 13 guiding principles, and 17 constraints. Seven work items across two active workstreams (vault curation quality + RAG/retrieval) plus cross-cutting evaluation tooling. Existing specs moved to `specs/legacy/`. Key open questions deferred to future refinement cycles: restructure architecture (D10 decision/generation split), knowledge graph ML approach selection, and per-tool model selection. Next step: decompose work items into atomic tasks via `/ideate:refine`, starting with evaluation tooling (001) and research tasks (002, 003).

## [execute] 2026-03-09 — Group 1 executed
Completed work items 001 (evaluation tooling framework), 002 (automatic invocation validation test plan), 003 (knowledge graph + ML research). Key output: cb_evaluate MCP tool + extractors/evaluate.py (18 tests passing), manual test plan with 16 test cases across 4 groups, 466-line research report recommending SQL-based graph expansion over graph ML. Research finding: graph ML methods (TransE, RotatE, GNNs) are not viable at personal vault scale (1K-10K notes, sparse graph). Recommended approach: recursive CTEs on existing relations table as third RRF channel.

## [refine] 2026-03-09 — Refinement cycle 1 planning completed
Trigger: Group 1 research findings + user feedback on evaluation tooling design.
Principles changed: none
New work items: 008-013
Key decisions: (1) cb_evaluate removed from MCP server — evaluation is internal dev tooling, not a product feature. (2) Quality gates built into curation tools instead — LLM-as-judge validates cheap model output during normal use. (3) Graph expansion deferred until search improvements are validated. (4) Invocation hardening (006) deferred until manual test plan (002) is executed. Decomposed original workstreams 004-007 into 6 atomic work items: MCP cleanup (008), quality gate infra (009), restructure gates (010), enrich/review gates (011), RAG synthesis (012), per-tool model selection (013).

## [execute] 2026-03-09 — Work item 008: Remove cb_evaluate from MCP server
Status: complete
Removed `evaluate` import and `evaluate.register(mcp)` from `mcp/server.py`. Deleted `mcp/tools/evaluate.py`. Preserved `extractors/evaluate.py` and `prompts/evaluate-system.md` as internal dev tooling. All 18 evaluate tests pass. No deviations from plan.

## [execute] 2026-03-09 — Work item 009: Quality gate infrastructure
Status: complete with rework
Rework: 2 significant, 1 minor findings fixed from incremental review.
S1: Added `Verdict` enum (pass/fail/uncertain) as first-class verdict state — original used boolean only. S2: Removed duplicate `get_judge_model` from quality_gate.py, now imported from backends.py. M1: Added `issues` field to GateVerdict. Created `extractors/quality_gate.py`, `prompts/quality-gate-system.md`, `tests/test_quality_gate.py` (19 tests). Added `get_judge_model()` to `backends.py`.

## [execute] 2026-03-09 — Work item 010: Restructure quality gates
Status: complete
Integrated quality gates into restructure pipeline at decide and generate phases. Added 6 gate functions, dry-run gate verdict display, retry-on-fail for generated content, config-driven gate toggle. 201 tests passing. No deviations from plan.

## [execute] 2026-03-09 — Work item 011: Enrich/review quality gates
Status: complete
Integrated quality gates into cb_enrich (per-item classification validation) and cb_review (per-decision promote/extend/delete validation). Gate blocks bad classifications from being applied; flags uncertain review decisions. Added enrich_classify and review_decide criteria to quality-gate-system.md. 86 enrich tests + 55 review tests passing. Fixed test isolation issue (sys.modules contamination between test files). No deviations from plan.

## [execute] 2026-03-09 — Work item 012: Synthesis and context injection
Status: complete with rework
Rework: 2 significant, 1 minor findings fixed from incremental review.
S1: Added security demarcation wrapper to synthesis output (was missing on success path). S2: Added quality_gate_enabled config guard (other tools had it, synthesis did not). M1: Removed unused Verdict import. Created prompts/synthesize-system.md and synthesize-user.md. Refactored _synthesize_recall to use templates, quality gate, token-efficient summaries. Updated test_mcp_server.py synthesis tests for new function signature. 32 recall tests passing.

## [execute] 2026-03-09 — Work item 013: Per-tool model selection
Status: complete with rework
Rework: 2 minor findings fixed from incremental review.
M1: Removed unused `get_model_for_tool` import from quality_gate.py. M2: Incorporated `total_notes` into cb_status output string (was queried but discarded). Added `get_model_for_tool(config, tool)` to backends.py. Updated `get_judge_model` to delegate. Each curation tool (restructure, recall, enrich, review) now resolves its model via the helper. cb_configure accepts per-tool model keys; cb_status reports them. Added tests in test_backends.py and test_manage_tool.py. Fixed test suite sys.modules contamination in test_quality_gate.py and test_evaluate.py (stubs leaked into subsequent test files). 1196 tests passing.

## [review] 2026-03-09 — Comprehensive review completed
Critical findings: 0
Significant findings: 4
Minor findings: 16
Suggestions: 2
Items requiring user input: 3

## [refine] 2026-03-09 — Refinement cycle 2 planning completed
Trigger: capstone review findings from refinement cycle 1
Principles changed: none
New work items: 014-020
Post-review corrections: remove dead quality_gate_threshold plumbing (YAGNI), fix gate criteria dispatch for split and hub operations, add synthesis gate criteria, make quality_gate_enabled configurable via cb_configure, extract duplicated _load_prompt to shared.py, sync all stale documentation. Also executing WI-002 automatic invocation test plan to unblock WI-006.

## [execute] 2026-03-09 — Work item 014: Remove dead threshold plumbing
Status: complete with rework
Rework: 1 minor finding fixed from incremental review.
M1: Updated stale TestGateHelpers docstring that still referenced _get_gate_threshold. Removed _get_gate_threshold function from restructure.py and 2 threshold tests from test_restructure_tool.py. Verified no other production code references quality_gate_threshold. 1194 tests passing.

## [execute] 2026-03-09 — Work item 015: Fix gate criteria dispatch
Status: complete
Fixed _gate_decisions to dispatch split→restructure_split, hub-spoke/subfolder→restructure_hub (was always restructure_merge). Fixed _gate_generated_content hub-spoke/subfolder dispatch to restructure_hub. Added ### restructure_hub criteria to quality-gate-system.md. Added 8 dispatch tests. 1202 tests passing. No deviations from plan.

## [execute] 2026-03-09 — Work item 016: Add synthesis gate criteria
Status: complete
Added ### synthesis section to quality-gate-system.md with 5 criteria covering hallucination, source attribution, query relevance, and completeness. Verified recall.py already calls quality_gate(operation="synthesis"). Prompt-only change, no code modifications needed. 1202 tests passing.

## [execute] 2026-03-09 — Work item 017: Quality gate cb_configure
Status: complete with rework
Rework: 2 significant findings fixed from incremental review.
S1: Added cb_configure hint to enrich.py gate-blocked output. S2: Fixed no-args display to only show gate status when disabled (was showing "enabled" when explicitly True). Added quality_gate_enabled param to cb_configure, gate status to cb_status, updated review.py error message. 6 tests added. 1208 tests passing.

## [execute] 2026-03-09 — Work item 018: Extract _load_prompt to shared.py
Status: complete
Extracted _load_tool_prompt to mcp/shared.py. All four tool files (enrich, review, restructure, recall) import via `_load_tool_prompt as _load_prompt`, preserving existing test mock targets. Removed local _load_prompt and _PROMPTS_DIR from all tool files. Updated TestLoadPrompt in test_setup_enrich_tools.py to test shared._load_tool_prompt. 1208 tests passing.

## [execute] 2026-03-09 — Work item 019: Documentation sync
Status: complete
Updated 6 documentation files to match current implementation. Changes: added quality_gate.py to component map (D1); prompt count 19→23 (D2); added per-tool model config keys (D7/II1); updated enrich/review prompt variables (D5); added synthesis/quality-gate/evaluate prompt families; marked T2 resolved (D9); added 5th env var CLAUDE_CODE_SESSION_ACCESS_TOKEN to architecture, constraints, CLAUDE.md (D8/II3); added get_model_for_tool/get_judge_model to backends.md (D4); updated _synthesize_recall signature (D3); removed ruamel.yaml reference (D6); updated prompts.md count and families (II2); added _load_tool_prompt to shared.py interface. Documentation-only, no code changes.

## [execute] 2026-03-09 — Work item 020: Execute invocation test plan
Status: complete
Executed all 16 manual test cases across Claude Desktop and Claude Code CLI. Results: 12 pass, 2 fail, 1 partial, 1 expected fail. Key findings: (1) Claude Desktop does not auto-fetch MCP resources — orient prompt required for proactive recall. (2) Claude Code can read MCP resources via readMcpResource but Desktop cannot. (3) CLAUDE.md instructions effectively substitute for the guide in Claude Code. (4) Manual capture mode partially fails — model still offers to file. (5) proactive_recall not settable via cb_configure. Results saved to specs/steering/research/invocation-test-results.md.

## [review] 2026-03-09 — Comprehensive review completed (cycle 2)
Critical findings: 0
Significant findings: 5
Minor findings: 12
Suggestions: 1
Items requiring user input: 3

## [refine] 2026-03-09 — Refinement cycle 3 planning completed
Trigger: Cycle 2 capstone review findings + user request for mock vault testing infrastructure
Principles changed: none
New work items: 021-026
Post-review corrections: add cb_configure hints to gate-blocked output in restructure.py and review.py, add proactive_recall to cb_configure, strengthen manual capture mode wording, add orient-prompt/CLAUDE.md guidance to cb_setup, fix residual documentation errors from cycle 2 review. New feature: mock vault testing infrastructure with 5 vault variants (empty, PARA, Zettelkasten, mature, working-memory) and deploy/reset scripts for human-in-the-loop QA.

## [execute] 2026-03-09 — Work item 021: Gate output cb_configure hints
Status: complete with rework
Rework: 1 minor finding fixed from incremental review. Added assertion for cb_configure hint in pre-existing generation-gate uncertain test.
Added cb_configure(quality_gate_enabled=False) hint to restructure.py _format_gate_verdicts() and review.py FAIL branch. Added tests in both test files. No deviations from plan.

## [execute] 2026-03-09 — Work item 022: Proactive recall cb_configure
Status: complete with rework
Rework: 2 minor findings fixed from incremental review. Mocked _read_index_stats in no-args display tests; added explicit True case test.
Added proactive_recall parameter to cb_configure, no-args display, and cb_status. 6 tests added. No deviations from plan.

## [execute] 2026-03-09 — Work item 023: Manual capture mode wording
Status: complete with rework
Rework: 1 minor finding fixed from incremental review. Added NEVER/Do NOT assertions to existing manual capture mode test.
Updated manual mode guide text with emphatic prohibitions. No deviations from plan.

## [execute] 2026-03-09 — Work item 024: Setup orient guidance
Status: complete with rework
Rework: 1 significant, 1 minor finding fixed from incremental review. S1: Added test assertions for guidance content in both Phase 2 return paths. M1: Split long snippet line at sentence boundary.
Added _SETUP_GUIDANCE constant with Desktop orient-prompt instructions and Claude Code CLAUDE.md snippet. Appended to both Phase 2 return paths. No deviations from plan.

## [execute] 2026-03-09 — Work item 025: Documentation corrections
Status: complete with rework
Rework: 1 significant finding fixed from incremental review. S1: evaluate.py docstring had introduced a new false claim ("Called by mcp/tools/review.py"); replaced with accurate statement that it is a standalone dev tool.
Fixed prompt variable tables in architecture.md, mcp-tools.md _synthesize_recall signature, prompts.md enrich-user.md variables, tool counts in architecture.md and mcp-server.md, evaluate.py docstring, WI-006 implementation notes updated with WI-020 findings. No deviations from plan.

## [execute] 2026-03-09 — Work item 026: Mock vault testing infrastructure
Status: complete with rework
Rework: 3 significant, 2 minor findings fixed from incremental review. S1: wm-recall.jsonl now deployed to ~/.claude/cyberbrain/ instead of vault directory. S2: All Python-invoking helpers in test-vault.sh now use environment variables instead of string interpolation to prevent quote injection. S3: Status modification detection replaced file count comparison with SHA-256 checksums. M1: Removed duplicate relations body section from Rate Limiting Strategy note. M2: Added sample journal files to mature vault's AI/Journal/ directory. M3 (dead _WM_RECALL_LOG in review.py) noted but out of scope.
Created 5 vault variants (empty, para, zettelkasten, mature, working-memory) in tests/vaults/ with deploy/reset/status/teardown scripts and documentation. No deviations from plan.

## [review] 2026-03-09 — Comprehensive review completed (cycle 3)
Critical findings: 0
Significant findings: 3
Minor findings: 4
Suggestions: 0
Items requiring user input: 0

## [execute] 2026-03-09 — Post-review fixes (cycle 3 capstone)
Status: complete
Fixed all 3 significant findings from cycle 3 capstone review:
S1/S2: Created tests/vaults/empty/.obsidian/.gitkeep and added .obsidian/.gitkeep to all 4 existing vault variants (para, zettelkasten, mature, working-memory). Satisfies WI-026 acceptance criteria for 5 variants with .obsidian/ markers.
S3: Added wm-recall.jsonl backup/restore to test-vault.sh. Deploy backs up existing file before overwriting; teardown restores from backup or removes test copy.
Also fixed M2: Updated README deploy description to document wm-recall.jsonl side effect.
1217 tests passing.

## [refine] 2026-03-09 — Refinement cycle 4 planning completed
Trigger: Cycle 3 capstone review findings (3 significant, 4 minor) + architect codebase analysis (dead code, duplicated utilities, misleading predicate guidance)
Principles changed: none
New work items: 027-030
Dead code removal (_WM_RECALL_LOG, _title_concept_clusters, similarity_threshold, stale files), utility consolidation (_is_within_vault to shared.py, frontmatter parsing to frontmatter.py), gate hint wording standardization (align enrich.py and restructure.py to review.py imperative form), cb_setup predicate guidance fix (stop suggesting domain-specific predicates that get normalized), manual capture mode re-test (WI-020 test D2 validation).

## [execute] 2026-03-09 — Work item 027: Dead code removal and utility consolidation
Status: complete with rework
Rework: 1 significant, 1 minor finding fixed from incremental review. S1: README still documented removed similarity_threshold parameter at two locations — removed example line and updated tool signature. M1: Moved mid-file frontmatter import in shared.py to top-level import block.
Removed _WM_RECALL_LOG, _title_concept_clusters(), similarity_threshold parameter. Consolidated _is_within_vault to shared.py, frontmatter parsing to frontmatter.py imports. Deleted 6 stale .skill bundles and 4 .py,cover files. No deviations from plan.

## [execute] 2026-03-09 — Work item 029: Fix cb_setup predicate guidance
Status: complete with rework
Rework: 1 critical (pre-existing) finding fixed from incremental review. C1: wasDerivedFrom in VALID_PREDICATES was camelCase but resolve_relations() lowercases before comparison, silently coercing all wasDerivedFrom relations to "related". Fixed by lowercasing the set entry.
Fixed setup.py _GENERATION_SYSTEM_PROMPT to list only the 6 supported predicates and not suggest custom ones. No deviations from plan.

## [execute] 2026-03-09 — Work item 028: Gate hint wording standardization
Status: complete with rework
Rework: 1 unmet acceptance criterion fixed from incremental review. Added hint text assertion to test_setup_enrich_tools.py gate-blocked test.
Changed enrich.py and restructure.py hint wording to imperative form matching review.py. No deviations from plan.

## [execute] 2026-03-09 — Work item 030: Manual capture mode re-test
Status: complete
Re-test procedure documented at specs/steering/research/manual-capture-retest.md. Actual test execution requires a live Claude Desktop session and is pending manual execution by the user.
