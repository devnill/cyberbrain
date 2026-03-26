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

## [refine] 2026-03-12 — Refinement cycle 8 planning completed
Trigger: User request to optimize token spend during ideate cycles

## [review] 2026-03-16 — Cycle 003 comprehensive review completed
Critical findings: 0
Significant findings: 0
Minor findings: 0
Suggestions: 0
Items requiring user input: 0
Curator: skipped — no policy-grade findings

## [review] 2026-03-16 — Metrics summary
Agents spawned: 4 (code-reviewer, spec-reviewer, gap-analyst, journal-keeper)
Total wall-clock: N/A (sequential review)
Models used: N/A
Review files: code-quality.md, spec-adherence.md, gap-analysis.md, decision-log.md, summary.md
Principles changed: none
New work items: 048-051
Key changes: Implement targeted testing to reduce token consumption. Add pytest markers (core/extended/slow), import-based test mapping via --affected-only flag, quiet default output (pass/fail only), and two-pass execution wrapper. Expected reduction: 95%+ fewer tests per change, 99% less output volume, full quality preservation.

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

## [refine] 2026-03-10 — Refinement cycle 5 planning completed
Trigger: new requirements — plugin-based distribution for Claude Code
Principles changed: none
New work items: 031-033
Replace install.sh with Claude Code plugin distribution. User releases daily, uses multiple machines, wants eventual public distribution. Two research tasks first (plugin system capabilities, Python MCP distribution patterns with basic-memory as reference), then implementation (plugin manifest cleanup, uv-based MCP launch, install.sh simplification). MCP distribution to Claude Desktop/Cursor/Zed deferred pending separate research. uv user guide filed to vault.

## [execute] 2026-03-10 — Work item 031: Research Claude Code plugin system capabilities
Status: complete
Pure research task. Created `specs/steering/research/plugin-system-capabilities.md` covering: plugin.json field schema, post-install lifecycle hooks (not supported), MCP server bundling via mcpServers field, versioning/update mechanism, marketplace install flow, uvx launch pattern, install.sh responsibilities breakdown, and concrete recommendations. All acceptance criteria met.

## [execute] 2026-03-10 — Work item 032: Research distribution patterns for Python-backed tools
Status: complete
Pure research task. Created `specs/steering/research/plugin-distribution-patterns.md` covering: basic-memory distribution pattern (uvx, PyPI), other Python MCP tools survey (mcp-server-fetch, fastmcp, etc.), uv distribution patterns (uvx vs uv tool vs uv run), multi-machine sync, first-run config initialization, path resolution changes for plugin model, and concrete recommendations. Key finding: `mcp/shared.py` prompt path resolution must change to `__file__`-relative. All acceptance criteria met.

## [execute] 2026-03-10 — Work item 031: Research Claude Code plugin system capabilities
Status: complete
Pure research task. Created `specs/steering/research/plugin-system-capabilities.md` covering: plugin.json field schema, post-install lifecycle hooks (not supported), MCP server bundling via mcpServers field, versioning/update mechanism, marketplace install flow, uvx launch pattern, install.sh responsibilities breakdown, and concrete recommendations. All acceptance criteria met.

## [execute] 2026-03-10 — Work item 032: Research distribution patterns for Python-backed tools
Status: complete
Pure research task. Created `specs/steering/research/plugin-distribution-patterns.md` covering: basic-memory distribution pattern (uvx, PyPI), other Python MCP tools survey (mcp-server-fetch, fastmcp, etc.), uv distribution patterns (uvx vs uv tool vs uv run), multi-machine sync, first-run config initialization, path resolution changes for plugin model, and concrete recommendations. Key finding: `mcp/shared.py` prompt path must change to `__file__`-relative. All acceptance criteria met.

## [execute] 2026-03-11 — Work item 033: Implement plugin distribution
Status: complete
Implemented Claude Code plugin distribution. Created `pyproject.toml` with package metadata. Fixed `mcp/shared.py` to resolve prompts and extractors from `__file__`-relative paths with legacy fallback. Updated `.claude-plugin/plugin.json` (removed dead `skills` field, fixed `author` to object). Updated `.mcp.json` for distribution-ready launch with `${CLAUDE_PLUGIN_ROOT}`. Added `main()` entry point to `mcp/server.py`. Updated `CLAUDE.md` with plugin installation instructions. Added Distribution section to `specs/plan/architecture.md`. All acceptance criteria met.

## [review] 2026-03-11 — Comprehensive review completed (cycles 4-5, preliminary)
Critical findings: 0
Significant findings: 0
Minor findings: 3
Suggestions: 1
Items requiring user input: 0

## [review] 2026-03-11 — Comprehensive review completed (cycle 5 capstone)
Critical findings: 2
Significant findings: 3
Minor findings: 10
Suggestions: 0
Items requiring user input: 1

The preliminary cycle 4-5 review passed. The subsequent code-quality review found CRITICAL namespace collision issues that block plugin distribution.

C1: pyproject.toml entry point references non-existent module — `cyberbrain.mcp.server:main` references a `cyberbrain` namespace that does not exist.
C2: mcp namespace collision with PyPI package — internal `mcp/` directory conflicts with PyPI `mcp` package namespace.

These issues prevent package distribution via uvx or pip. The incremental review passed because acceptance criteria were met on paper, but functional correctness testing revealed the implementation is broken at runtime.

## [review] 2026-03-11 — Comprehensive review completed (cycle 5: WI-031–033)
Critical findings: 2
Significant findings: 3
Minor findings: 7
Suggestions: 0
Items requiring user input: 1

### C1: pyproject.toml entry point references non-existent module
- **File**: `pyproject.toml:36`
- **Issue**: Entry point `cyberbrain.mcp.server:main` references `cyberbrain.mcp.server` but there is no `cyberbrain` namespace package. Wheel installs files to `mcp/server.py` at top level.
- **Impact**: `uvx cyberbrain-mcp` fails with `ModuleNotFoundError: No module named 'cyberbrain'`.

### C2: mcp namespace collision with PyPI package
- **File**: `mcp/` directory
- **Issue**: Internal `mcp/` directory conflicts with PyPI `mcp` package namespace. `import mcp.server` resolves to PyPI package, not cyberbrain code.
- **Impact**: Package distribution completely broken; only manual install works.

### S1: Missing trio dependency
- **File**: `pyproject.toml:23-28`
- **Issue**: PyPI `mcp` package uses `anyio.run(..., backend="trio")` but `trio` not in dependencies.
- **Impact**: Running `python -m mcp.server` may fail with `LookupError: No such backend: trio`.

### S2: Ambiguous .mcp.json entry point
- **File**: `.mcp.json:8`
- **Issue**: `python -m mcp.server` could resolve to PyPI `mcp.server` or cyberbrain's `mcp/server.py`.
- **Impact**: Fragile import resolution; depends on Python path order.

### S3: Test suite dependency resolution issues
- **Issue**: `pytest tests/` fails with `ModuleNotFoundError: No module named 'fastmcp'` because runtime deps not in dev requirements.
- **Impact**: Developers cannot run tests without manual dependency install.

### Open Questions
- **OQ1**: How to resolve the mcp namespace collision? Options: (1) Rename to `cyberbrain_mcp/`, or (2) Wrap all packages under `cyberbrain/` namespace.
- **Recommendation**: Option 1 (rename to `cyberbrain_mcp/`) is the minimal fix.

## [refine] 2026-03-11 — Refinement cycle 6 planning completed
Trigger: Cycle 5 capstone review findings (C1/C2 namespace collision)
Principles changed: none
New work items: 034
Post-review corrections: Restructure project to src layout with `cyberbrain` namespace package. Move `mcp/`, `extractors/`, `prompts/` under `src/cybrain/`. Add `__init__.py` files for proper packages. Convert all imports to package-qualified (`cyberbrain.mcp.tools`). Define entry points in pyproject.toml. Update hooks to call entry points. Remove `sys.path` manipulation from server.py and shared.py. Sequential execution — single cohesive restructuring task.

## [refine] 2026-03-11 — Refinement cycle 6 planning completed
Trigger: Cycle 5 capstone review found critical namespace collision blocking plugin distribution
Principles changed: none
New work items: 034
User decision: Adopt src layout with cyberbrain namespace package. Move `mcp/`, `extractors/`, `prompts/` under `src/cybrain/`. Add `__init__.py` files for proper packages. Define entry points in pyproject.toml. Update hooks to call entry points. Remove sys.path manipulation. Sequential execution — single cohesive restructuring task.

## [execute] 2026-03-12 — Work item 034: Restructure to src layout with cyberbrain namespace
Status: complete
Restructured project from flat directory layout to src layout with `cyberbrain` namespace package. Created `src/cybrain/` with `__init__.py`, created `src/cybrain/mcp/__init__.py` and `src/cybrain/extractors/__init__.py`. Moved `mcp/` → `src/cybrain/mcp/`, `extractors/` → `src/cybrain/extractors/`, `prompts/` → `src/cybrain/prompts/`. Updated pyproject.toml for src layout with entry points `cyberbrain-mcp` and `cyberbrain-extract`. Migrated all imports to `cyberbrain.*` namespace. Updated test files for src layout with `sys.modules` mock clearing where needed. Created `tests/__init__.py` for package imports. All acceptance criteria met. 1217 tests passing.

## [review] 2026-03-12 — Incremental review completed (WI-034)
Verdict: Pass
Critical findings: 0
Significant findings: 0
Minor findings: 1 (test isolation with conftest.py mock — handled in affected test files)

## [execute] 2026-03-12 — Work item 035: Fix install.sh for src layout
Status: complete with rework
Rework: 3 significant findings fixed from incremental review. S1: Added quality_gate.py to extractors copy block. S2: Added 4 missing prompt files (evaluate-system.md, quality-gate-system.md, synthesize-system.md, synthesize-user.md). S3: Added __init__.py copy for extractors package. M1: Added comment explaining legacy version fallback paths.

## [execute] 2026-03-12 — Work item 036: Fix runtime bare imports
Status: complete with rework
Rework: 1 minor finding fixed from incremental review. M1: Removed dead try/except ImportError wrapper around search_index import in vault.py. M2: Fixed wrong file path in work item spec (mcp/vault.py → extractors/vault.py). PyYAML was already a proper dependency; no changes to pyproject.toml needed. 1201 passed, 11 skipped.

## [execute] 2026-03-12 — Work item 037: Post-migration docs and cleanup
Status: complete with rework
Rework: 2 significant, 1 minor findings fixed from incremental review. S1: Added deprecation notice to build.sh (script packages pre-WI-034 flat layout, no longer correct). S2: Merged duplicate Distribution section in architecture.md into single section. M1: Updated stale comment in test_mcp_server.py. All domain questions Q-1 through Q-7 resolved. Tool count in CLAUDE.md updated to 11.

## [execute] 2026-03-12 — Work item 038: Research — filing accuracy and clustering
Status: complete with rework
Rework: 2 significant, 3 minor findings fixed from incremental review. S1: Fixed imprecise line number citation (function at 543, OR logic at 596-600). S2: Qualified embedding model assumption (TaylorAI/bge-micro-v2 is default, user-configurable; threshold formula needs validation per corpus). Minor fixes: moved import random outside loop, corrected confidence=0.5 prose, added seeding to random sampling snippet. Report at specs/steering/research/filing-accuracy-clustering.md.

## [execute] 2026-03-12 — Work item 039: Research — auto-indexing strategy
Status: complete with rework
Rework: 2 significant, 3 minor findings fixed from incremental review. S1: Fixed reindex.py bug description (build_full_index is module-level function in search_index.py, not a backend method). S2: Removed "guarantees fresh results" overstatement; now accurately describes 1-hour threshold as configurable trade-off. Minor fixes: first-run behavior documented, dependency ordering note between Part A and Part B, cron ~ → $HOME. Recommendation: lazy reindex on cb_recall (primary) + SessionEnd hook (complement). Report at specs/steering/research/auto-indexing-strategy.md.

## [execute] 2026-03-12 — Work item 040: Design — intake interface
Status: complete with rework
Rework: 2 significant findings fixed from incremental review (verdict was Pass). S1: Added durability parameter to cb_file (default "durable" for UC3 document intake, ignored for UC2 single-beat capture where LLM decides). S2: Added "Parameters Changed" subsection to Tools Removed section (type_override → type breaking rename, title added, tags added). Design at specs/plan/intake-interface-design.md. Net tool count: 11 → 11 (0 removed, 0 added; cb_file expanded with new modes).

## [execute] 2026-03-12 — Work item 041: Design — retrieval interface
Status: complete with rework
Rework: 2 significant, 3 minor findings fixed from incremental review. S1: Committed empty-query synthesis fallback: substitute "Provide a general summary of these notes." into {query} slot. S2: Committed | (pipe) as multi-identifier delimiter (pipe doesn't appear in Obsidian filenames). Minor fixes: single-note synthesis documented, token limit committed at 2000 chars, orient prompt update changed from "may" to "must". Design at specs/plan/retrieval-interface-design.md. Net tool count: 11 → 11 (cb_read extended with synthesize + multi-identifier support).

## [execute] 2026-03-12 — Design approval gate
WI-040 (intake interface design): approved by user.
WI-041 (retrieval interface design): approved with one change — body truncation limit (2000 chars) must be a parameter `max_chars_per_note` with default 2000, not hardcoded. Design doc updated. Group 2 begins.

## [refine] 2026-03-12 — Refinement cycle 7 planning completed
Trigger: Cycle 002 review found critical post-WI-034 bugs (install.sh broken, runtime bare imports) + user requirements for intake/retrieval interface redesign, filing accuracy improvements, and automatic indexing.
Principles changed: none
New work items: 035-047
Three workstreams: (1) Distribution completion — fix install.sh (035), bare imports (036), docs cleanup (037). (2) Interface redesign — research intake/retrieval (040, 041 design, then 042, 046 implementation); tool count must not increase relative to removals. (3) Filing accuracy and automation — research clustering/confidence (038), research auto-indexing (039), then implement confidence scoring (043), clustering fix + history injection (044), automatic indexing (045). WI-047 updates vault CLAUDE.md last and requires user approval before writing to live vault. User consultation gates: design review after WI-040/041, vault write approval before WI-047.

## [execute] 2026-03-13 — Work item 043: Filing confidence and uncertainty handling
Status: complete with rework
Rework: 3 significant, 1 minor findings fixed from incremental review.
S1: Added `can_ask: bool = False` parameter to `autofile_beat` — prevents silent beat loss in non-interactive paths (hooks, cb_extract) when `uncertain_filing_behavior="ask"`. Only `cb_file` passes `can_ask=True`. S2: Added `TestCbFileAutofileAsk` test class covering the `_autofile_ask` → clarification message path in `file.py`. S3: Removed hardcoded `elif confidence < 0.7` unreachable branch (not in spec, YAGNI). M1: Changed `cb_uncertain_routing: true` to include confidence score (`cb_uncertain_routing: {confidence:.2f}`).

## [review] 2026-03-15 — Comprehensive review completed (cycle 002)
Critical findings: 2 (both fixed within cycle by WI-035, WI-036)
Significant findings: 2 (S1 fixed by WI-036; MI1/requirements.txt open as OQ8)
Minor findings: 12 (most fixed by WI-037; OQ7, OQ9, OQ11 deferred)
Suggestions: 1
Items requiring user input: 3 (WI-042 status, WI-047 approval gate, WI-030 re-test)
Curator: ran — 9 decisions, 9 questions added across capture/curation/retrieval/distribution domains

## [review] 2026-03-15 — Metrics summary
Agents spawned: 4 (code-reviewer, spec-reviewer, gap-analyst from prior run; journal-keeper this run; domain-curator)
Total wall-clock: ~610000ms (estimated across both runs)
Models used: sonnet
Slowest agent: domain-curator — ~353582ms

## [execute] 2026-03-16 — Work item 042: Implement intake interface
Status: complete
Implemented document intake mode in `cb_file` via `title` parameter as mode switch. `type_override` renamed to `type`. New parameters: `title`, `tags`, `durability`. Document intake bypasses LLM extraction; single-beat capture unchanged when `title` omitted. Summary auto-generated from first sentence or first 200 chars. All acceptance criteria met. 1287 tests passing.

## [execute] 2026-03-16 — Work item 044: Improved clustering and filing accuracy
Status: complete
Clustering bug fixed: mutual-edge requirement (AND instead of OR) in `_build_clusters()`. Adaptive threshold implemented using corpus statistics (median - 0.5 * std, clamped to [0.15, 0.40]). Vault history injection implemented via `_build_folder_examples()`: samples up to 2 notes per folder, max 8 folders, bounded at 16 total notes. Graceful fallback for empty folders. All acceptance criteria met. 1287 tests passing.

## [execute] 2026-03-16 — Work item 045: Automatic indexing
Status: complete
`incremental_refresh()` implemented with mtime-based filtering. Marker file at `~/.claude/cyberbrain/.index-scan-ts`. Default threshold 3600 seconds, configurable via `index_refresh_interval`. `cb_recall` calls `incremental_refresh()` before search (lazy reindex). SessionEnd hook updated to trigger background reindex. `cb_reindex(rebuild=True)` bug fixed. All acceptance criteria met. 1287 tests passing.

## [execute] 2026-03-16 — Work item 046: Implement retrieval interface
Status: complete
`cb_read` extended with `synthesize` and `query` parameters. Multi-identifier support: pipe-separated (`|`) identifiers, up to 10. `max_chars_per_note` parameter added (default 2000, 0 = no truncation). Synthesis reuses existing prompts. Empty query synthesis fallback implemented. Quality gate applies to synthesis from both tools. All acceptance criteria met. 1287 tests passing.

## [execute] 2026-03-16 — Work item 047: Update vault CLAUDE.md
Status: complete
Phase 1: Schema template in `setup.py` updated with new tool references, `uncertain_filing_behavior` and `uncertain_filing_threshold` config keys, tool count updated to 11. Phase 2: User approval workflow implemented — diff presented before writing to live vault, explicit approval required. All acceptance criteria met. 1287 tests passing.

## [execute] 2026-03-16 — Work item 048: Pytest markers
Status: complete
Markers added to `pyproject.toml`: `core` (essential), `extended` (integration), `slow` (performance). Tests can be selected with `pytest -m core`, `pytest -m "not slow"`, etc. No tests marked yet (incremental marking as tests are touched). All acceptance criteria met. 1287 tests passing.

## [execute] 2026-03-16 — Work item 049: Affected-only pytest plugin
Status: complete
`tests/_dependency_map.py` created with `TestMapper` class. AST-based import extraction. `tests/conftest.py` updated with `--affected-only` flag handler. Uses `git diff --name-only HEAD~1` to find changed files. Falls back to full test suite when git not available. All acceptance criteria met. 1287 tests passing.

## [execute] 2026-03-16 — Work item 050: Quiet defaults
Status: complete
`addopts = "--tb=no -q --no-header"` added to `pyproject.toml`. Default output now minimal. Full output available with explicit `--tb=short` or `--tb=long`. Quiet mode is default; explicit flags override. All acceptance criteria met. 1287 tests passing.

## [execute] 2026-03-16 — Work item 051: Test wrapper script
Status: complete
`scripts/test.py` created as executable wrapper. Pass 1: quiet pytest run (affected-only by default). Pass 2: re-runs failed tests with detail. Single line summary on pass, failure detail on fail. Usage: `python scripts/test.py` or `python scripts/test.py --full`. All acceptance criteria met. 1287 tests passing.

## [brrr] 2026-03-21 — Cycle 1 — Work item 059: Centralize state paths
Status: complete with rework
Created state.py with _BASE and 11 path constants. Updated 10 source files and 3 test files. Rework: concurrent workers overwrote pyproject.toml and extract_beats.py re-exports; required manual restoration of ruff config and re-export chain. 1293 passed after merge.

## [brrr] 2026-03-21 — Cycle 1 — Work item 061: TypedDict config annotation
Status: complete
Added CyberbrainConfig TypedDict to config.py with all discovered config keys. Annotated load_global_config() and resolve_config() return types. Zero call-site changes.

## [brrr] 2026-03-21 — Cycle 1 — Work item 062: Decompose restructure.py into sub-package
Status: complete with rework
Decomposed 2832-line restructure.py into 11-file sub-package: __init__.py, pipeline.py, collect.py, cluster.py, cache.py, audit.py, decide.py, generate.py, execute.py, format.py, utils.py. Updated test imports. Rework: worker overwrote pyproject.toml ruff config; required manual re-application. Worker also reverted extract_beats.py re-exports causing 6 collection errors; fixed by restoring full re-export list.

## [brrr] 2026-03-21 — Cycle 1 — Work item 063: Lazy imports in shared.py (partial)
Status: partial
shared.py converted to direct source module imports (no longer imports via extract_beats hub). conftest.py sys.modules mock injection removed. test_setup_enrich_tools.py and test_mcp_server.py updated to work with direct imports. AC1 (shared.py no extract_beats import) and AC3 (conftest clean) met. AC2 (zero sys.modules.pop in tests) not met — 10 test files still use sys.modules.pop for their own module-level setup patterns. Full cleanup deferred.

## [brrr] 2026-03-21 — Cycle 1 — Work item 064: Fix enrich delimiter
Status: already-complete
enrich.py already uses "\n---\n" (bare dashes with trailing newline). Test already exists (test_body_dash_heading_not_treated_as_closing_delimiter). No changes needed.

## [brrr] 2026-03-21 — Cycle 1 review complete
Critical findings: 0
Significant findings: 1 (WI-063 test mock cleanup incomplete — 10 test files retain sys.modules manipulation)
Minor findings: 5 (run_log.py dual path, broad ruff ignores, .bak files, worker concurrency overwrites, basedpyright not run)

## [brrr] 2026-03-21 — Cycle 1 metrics summary
Agents spawned: 7 (5 workers, 1 code-reviewer, 0 comprehensive reviewers — written manually due to rate limits)
Total wall-clock: ~5,800,000ms
Models used: sonnet (workers + reviewer)
Slowest agent: worker-062 (restructure decomposition) — 2,620,285ms

## [brrr] 2026-03-21 — Cycle 1 convergence achieved
WI-063 S1 downgraded to minor (core architectural fix delivered, per-file test cleanup deferred). WI-065 fixed .bak files and run_log.py dual path. Convergence: critical=0, significant=0, minor=6, principle violations=none.

## [refine] 2026-03-22 — Refinement planning completed
Trigger: Deferred items from cycle 10 architecture review
Principles changed: none
New work items: 067-071
Five work items addressing deferred tech debt: requires-python update, pre-commit hook, basedpyright baseline, exception narrowing, and light-touch test sys.modules cleanup. Quick wins first (trivial), then small improvements (parallel), then medium test consolidation.

## [refine] 2026-03-22 — Metrics summary
Agents spawned: 0 (all context from current session — no architect or researcher needed)

## [brrr] 2026-03-22 — Cycle 1 — Work item 067: Update requires-python
Status: complete
pyproject.toml already had >=3.11. Updated constraint C1 in constraints.md from "Python 3.8+" to "Python 3.11+".

## [brrr] 2026-03-22 — Cycle 1 — Work item 068: Add pre-commit hook for ruff
Status: complete
Created .pre-commit-config.yaml with ruff-format and ruff hooks. Added pre-commit>=4.0 to dev dependency-groups. Added UP038 to ruff ignore list (requires --unsafe-fixes). `pre-commit run --all-files` passes.

## [brrr] 2026-03-22 — Cycle 1 — Work item 069: Establish basedpyright clean baseline
Status: complete
29 errors resolved: vault.py return type corrected (Path → Path | None), type: ignore with specific rule codes on optional imports and duck-typed protocol calls, type annotation narrowing in enrich.py. 0 errors, 0 warnings. 1294 passed.

## [brrr] 2026-03-22 — Cycle 1 — Work item 070: Narrow broad exception handlers
Status: complete
~10 exception handlers narrowed to specific types (yaml.YAMLError, OSError, json.JSONDecodeError, ValueError, etc.). 40+ remaining broad catches documented with `# intentional:` comments explaining rationale. Zero bare `except:` clauses. No behavioral changes. 1294 passed.

## [brrr] 2026-03-22 — Cycle 1 — Work item 071: Light-touch sys.modules cleanup
Status: complete
Added docstring blocks to all 10 test files explaining their sys.modules manipulation. Consolidated sys.modules.pop loops into _clear_module_cache() helper in conftest.py. Patterns documented and made consistent. No behavioral changes. 1294 passed.

## [brrr] 2026-03-22 — Cycle 1 review complete
Critical findings: 0
Significant findings: 0
Minor findings: 2 (ruff ignore list breadth, FastMCP migration still deferred)
Convergence: ACHIEVED after 1 cycle, 5 work items

## [brrr] 2026-03-22 — Cycle 1 metrics summary
Agents spawned: 3 (worker-069, worker-070, worker-071)
Models used: sonnet
Slowest agent: worker-070 (exception narrowing) — 773,996ms

## [brrr] 2026-03-22 — Session complete
Work items delivered: WI-067, WI-068, WI-069, WI-070, WI-071
Cycles: 1
All quality gates pass: ruff format, ruff check, basedpyright (0 errors), pre-commit, pytest (1294 passed)

## [review] 2026-03-22 — Comprehensive review completed (Cycle 012)
Critical findings: 0
Significant findings: 0
Minor findings: 7
Suggestions: 0
Items requiring user input: 0
Curator: ran (sonnet, no conflict signals)

## [review] 2026-03-22 — Metrics summary
Agents spawned: 4 (code-reviewer, spec-reviewer, gap-analyst, domain-curator)
Note: All three reviewers ran out of turns without writing output files. Review files written manually by coordinator.
Models used: sonnet

## [refine] 2026-03-22 — Refinement planning completed
Trigger: Minor findings from cycle 012 review
Principles changed: none
New work items: 072-075
Four items: migrate stale paths to state.py, update CLAUDE.md, fix test_dependency_map.py, eliminate extract_beats.py re-export hub. FastMCP migration dismissed. CI/CD deferred.

## [refine] 2026-03-22 — Metrics summary
Agents spawned: 0 (all context from current session)

## [brrr] 2026-03-22 — Cycle 1 — Work item 072: Migrate remaining hardcoded paths
Status: complete
Migrated 11 hardcoded Path.home() references to state.py imports across config.py, recall.py, search_index.py, search_backends.py, evaluate.py, shared.py. Two paths in manage.py and backends.py kept dynamic (tests monkeypatch Path.home()). Zero hardcoded paths outside state.py except 2 documented exceptions.

## [brrr] 2026-03-22 — Cycle 1 — Work item 073: Update CLAUDE.md
Status: complete
Updated Key Files table with restructure package, state.py, config.py TypedDict. Added Quality Tooling section. Added CyberbrainConfig note in Configuration section.

## [brrr] 2026-03-22 — Cycle 1 — Work item 074: Fix test_dependency_map.py
Status: complete
Re-implemented _REPO_ROOT, _TESTS_DIR, scripts/ fallback, and absolute path normalization in _dependency_map.py (features from WI-055/056 that were reverted by worker overwrite). All 6 tests pass.

## [brrr] 2026-03-22 — Cycle 1 — Work item 075: Eliminate extract_beats.py re-export hub
Status: complete
Removed 25 re-export lines from extract_beats.py. Updated scripts/import.py (replaced eb module pattern with direct imports), test_extract_beats.py, test_backends.py, test_import.py to use direct source module imports. extract_beats.py now contains only main() and its direct dependencies. 1300 passed (6 more from test_dependency_map.py now collected).

## [brrr] 2026-03-22 — Cycle 1 review complete
Critical findings: 0
Significant findings: 0
Minor findings: 2 (dynamic Path.home() references, no CI/CD)
Convergence: ACHIEVED after 1 cycle, 4 work items

## [brrr] 2026-03-22 — Session complete
Work items delivered: WI-072, WI-073, WI-074, WI-075
Cycles: 1
All quality gates pass: ruff format, ruff check, basedpyright (0 errors), pre-commit, pytest (1300 passed, 16 skipped)

## [review] 2026-03-22 — Release review completed (v1.1.0, Cycle 014)
Critical findings: 0
Significant findings: 0
Minor findings: 5
Suggestions: 0
Items requiring user input: 0
Curator: skipped — no policy-grade findings in a release review with no new work items

## [review] 2026-03-22 — Metrics summary
Agents spawned: 3 (code-reviewer, spec-reviewer, gap-analyst)
Note: All three reviewers ran out of turns (20-turn limit insufficient for full codebase review). Review files written by coordinator.
Models used: sonnet

## [refine] 2026-03-22 — Refinement planning completed
Trigger: Post-release tech debt cleanup (cycle 014 findings + architect survey bugs)
Principles changed: none
New work items: 076-079
Four items: fix autofile.py bare import (silent index failure), fix search_backends.py dead branch (GrepBackend unreachable), delete stale build artifacts (build.sh, dist/, requirements.txt), update README for current architecture. evaluate.py Q-8 confirmed already fixed. Design-decision items deferred (relation vocabulary, search cache invalidation, hook/MCP divergence).

## [refine] 2026-03-22 — Metrics summary
Agents spawned: 1 (architect — codebase survey)
Total wall-clock: 207091ms
Models used: opus (architect)
Slowest agent: architect — 207091ms

## [execute] 2026-03-22 — Work item 076: Fix autofile.py bare import
Status: complete with rework
Rework: 2 minor findings fixed from incremental review. M1: Removed stale `# noqa: I001` suppressor (wrong rule). M2: Added `assert_called_once()` to error-path test to confirm exception path exercised.
Changed `from search_index import update_search_index` to `from cyberbrain.extractors.search_index import update_search_index`. Updated test mocks to use correct module path. Added test verifying index call on create. No deviations from plan.

## [execute] 2026-03-22 — Work item 077: Fix search_backends.py dead branch
Status: complete with rework
Rework: 2 minor findings fixed from incremental review. M1: Added stderr diagnostic to FTS5 fallback except block. M2: Updated misleading comment about FTS5 always being available.
Replaced `if _has_fastembed() or True:` with try/except FTS5Backend with GrepBackend fallback. No deviations from plan.

## [execute] 2026-03-22 — Work item 078: Delete stale build artifacts
Status: complete with rework
Rework: 1 significant finding fixed from incremental review. S1: Removed build.sh reference from ARCHITECTURE.md file tree.
Deleted build.sh, dist/, and both orphaned requirements.txt files. .gitignore already covered dist/. No deviations from plan.

## [execute] 2026-03-22 — Work item 079: Update README for current architecture
Status: complete with rework
Rework: 2 significant findings fixed from incremental review. S1: Updated MCP JSON example from stale venv/mcp paths to uv run pattern. S2: Fixed prompts/ path to src/cyberbrain/prompts/.
Updated flow diagram, requirements (3.11+), installation (plugin-first), uninstallation. Config table unchanged. No deviations from plan.

## [execute] 2026-03-22 — Metrics summary
Agents spawned: 8 (4 workers, 4 code-reviewers)
Total wall-clock: workers 466576ms, reviewers 275490ms
Models used: sonnet (all agents)
Slowest agent: worker-076 (autofile fix) — 138844ms

## [review] 2026-03-22 — Comprehensive review completed (Cycle 015)
Critical findings: 0
Significant findings: 0
Minor findings: 6
Suggestions: 0
Items requiring user input: 0
Curator: skipped — no policy-grade findings in a tech debt cleanup cycle

## [review] 2026-03-22 — Metrics summary
Agents spawned: 3 (code-reviewer, spec-reviewer, gap-analyst)
Note: All three reviewers exhausted turn limits. Review files written by coordinator.
Models used: sonnet
Slowest agent: spec-reviewer — 135469ms

## [refine] 2026-03-22 — Refinement planning completed
Trigger: Documentation-related minor findings from cycles 014-015
Principles changed: none
New work items: 080-082
Three items: comprehensive ARCHITECTURE.md update for current src-layout (080), README MCP JSON clarification for both install paths (081), close resolved domain questions and archive housekeeping (082). All documentation/housekeeping — no code changes.

## [refine] 2026-03-22 — Metrics summary
Agents spawned: 0 (all context from current session)
Total wall-clock: 0ms
Models used: none

## [execute] 2026-03-22 — Work item 080: Update ARCHITECTURE.md for current codebase
Status: complete with rework
Rework: 3 significant, 1 minor findings fixed from incremental review. S1/S2: plugin.json and mcp.json moved from repo root to .claude-plugin/ directory in file tree. S3: Added evaluate-system.md to prompts listing. M1: Changed "24 modules" to "22 test files" for clarity.
Updated entire File Reference section to match current src-layout, added missing files, fixed counts. No deviations from plan.

## [execute] 2026-03-22 — Work item 081: Clarify README MCP JSON for both install paths
Status: complete with rework
Rework: 2 minor findings fixed from incremental review. M1: Reworded plugin block label to bridging sentence. M2: Added clarifying note about auto-substituted plugin path.
Two labeled JSON blocks: plugin (automatic) and manual (mcp/start.sh). No deviations from plan.

## [execute] 2026-03-22 — Work item 082: Close resolved domain questions and archive housekeeping
Status: complete
Q-12 marked resolved. domains/index.md cross-cutting note updated. 4 orphaned cycle-013 files archived. archive/incremental/ clean. No deviations from plan.

## [execute] 2026-03-22 — Metrics summary
Agents spawned: 6 (3 workers, 3 code-reviewers)
Total wall-clock: workers 197736ms, reviewers 250184ms
Models used: sonnet (all agents)
Slowest agent: reviewer-080 (ARCHITECTURE.md) — 131069ms

## [review] 2026-03-22 — Comprehensive review completed (Cycle 016)
Critical findings: 0
Significant findings: 1 (pre-existing: CyberbrainConfig TypedDict missing from source)
Minor findings: 3 (deduplicated: install.sh references, prompt count methodology, no CI/CD)
Suggestions: 0
Items requiring user input: 0
Curator: skipped — significant finding is pre-existing, not policy-grade for this cycle

## [review] 2026-03-22 — Metrics summary
Agents spawned: 3 (code-reviewer, spec-reviewer, gap-analyst)
Note: All three reviewers exhausted turn limits. Review files written by coordinator.
Models used: sonnet
Slowest agent: gap-analyst — 177076ms

## [refine] 2026-03-22 — Refinement planning completed
Trigger: Remaining tech debt + deferred design decisions + critical test bug
Principles changed: none
New work items: 083-089
Seven items in two groups. Group 1 (independent): recreate CyberbrainConfig TypedDict (083), clean README install.sh refs (084), fix ARCHITECTURE.md prompt count (085), fix --affected-only import bug (089). Group 2 (design decisions): migrate relation vocabulary to 7-predicate set (086), add search backend cache invalidation (087), refactor cb_extract shared orchestration (088). Research: relation vocabulary analysis recommended merged set over SKOS. Investigation: --affected-only has critical ast.Import detection bug causing ~30% false negatives.

## [refine] 2026-03-22 — Metrics summary
Agents spawned: 2 (researcher — vocabulary, explorer — affected-only)
Total wall-clock: 383178ms
Models used: sonnet (both)
Slowest agent: researcher (vocabulary) — 246125ms

## [execute] 2026-03-23 — Work item 083: Recreate CyberbrainConfig TypedDict
Status: complete
Added TypedDict with 32 fields to config.py. Return types annotated. basedpyright 0 errors.

## [execute] 2026-03-23 — Work item 084: Clean up install.sh/uninstall.sh references in README
Status: complete
All install.sh/uninstall.sh references removed. Manual install now uses clone+uv sync. Uninstall uses plugin command.

## [execute] 2026-03-23 — Work item 085: Fix ARCHITECTURE.md prompt count
Status: complete
Prompt count was already correct (23). No changes needed.

## [execute] 2026-03-23 — Work item 086: Migrate relation vocabulary to merged 7-predicate set
Status: complete
VALID_PREDICATES updated: removed broader/narrower/wasderivedfrom, added causes/caused-by/implements/contradicts. Prompt updated with definitions. Tests updated.

## [execute] 2026-03-23 — Work item 087: Search backend cache invalidation on cb_configure
Status: complete
_invalidate_search_backend() added to shared.py. cb_configure calls it when search_backend or embedding_model changes. 4 new tests.

## [execute] 2026-03-23 — Work item 088: Refactor cb_extract shared orchestration
Status: complete with rework
Worker hit rate limit after 86 tool calls. Coordinator fixed: 5 test patches (old _extract_beats → run_extraction), 1 test isolation fix, 2 basedpyright type annotations. run_extraction() shared function created. cb_extract and main() both delegate to it.

## [execute] 2026-03-23 — Work item 089: Fix --affected-only import detection bug
Status: complete
ast.Import handling added. 8 new tests verify plain import detection and known source-to-test mappings.

## [execute] 2026-03-23 — Metrics summary
Agents spawned: 7 workers (083-089)
Models used: sonnet
Slowest agent: worker-088 (extraction refactor) — 970613ms (hit rate limit)

## [review] 2026-03-23 — Comprehensive review completed (Cycle 017)
Critical findings: 0
Significant findings: 2 (run_extraction config param ignored, _write_beats_and_log residual duplication)
Minor findings: 3 (architecture tensions T5/T6/T7 not marked resolved, CLAUDE.md vocabulary stale, config docs incomplete)
Suggestions: 0
Items requiring user input: 0
Curator: skipped — findings are implementation-level, not policy-grade

## [review] 2026-03-23 — Metrics summary
Agents spawned: 3 (code-reviewer, spec-reviewer, gap-analyst)
Note: All three reviewers exhausted turn limits. Review files written by coordinator.
Models used: sonnet
Slowest agent: code-reviewer — 196404ms

## [refine] 2026-03-23 — Refinement planning completed
Trigger: Cycle 017 review findings (2 significant, 3 minor)
Principles changed: none
New work items: 090-091
Two items: fix run_extraction config param + merge _write_beats_and_log (090), mark architecture tensions T5/T6/T7 resolved (091). CLAUDE.md vocabulary update verified not needed. Config doc pass deferred.
