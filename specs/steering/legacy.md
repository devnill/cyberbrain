# Interview Transcript — 2026-03-09

## Context
Retroactive planning capture for cyberbrain, an existing knowledge capture and retrieval system. The project has a mature codebase (~7,200 LOC Python/Bash), comprehensive test suite (17,600 LOC), and detailed legacy specs. This planning session establishes a baseline for future `/ideate:refine` cycles.

The user provided all existing specs (v1_spec.md, GOALS.md, deferred.md, mcp_gaps.md, mcp-enhancements.md, mcp-architecture.md, enhanced-retrieval.md, knowledge-graph-enhancement.md) and the project CLAUDE.md. A full codebase survey was performed by the architect agent.

---

**Q: What is the scope of what you want to plan? Are you retroactively creating a plan for the existing system, or planning new changes?**
A: Retroactively capture the current state so we can continue to refine. Existing specs should be moved to a subfolder for safekeeping while assembling the correct ideate artifact structure.

**Q: What is the current focus?**
A: Two main goals:
1. Continue to refine the Obsidian vault curation logic — this covers the full pipeline: extraction, autofiling, daily journal, enrichment, working memory, and restructuring. Restructuring has proven particularly challenging as it requires intelligently rewriting notes by merging, combining, creating sub-hubs, and applying clustering heuristics. This needs to be near perfect because notes must be highly discoverable as the vault continuously grows.
2. Begin serious work on improving retrieval, aiming for a RAG system that can effectively supplement memory and context systems. Claude Code is the primary use case, but it should work equally well in Claude Desktop and mobile without manual tool invocation.

**Q: How do you want execution structured?**
A: As much work in parallel as possible. One tension: vault curation heuristics need human-in-the-loop refinement. Creating good heuristics has been tricky and required a lot of tweaking. LLMs can critically evaluate output quality but producing high-quality output has been harder. This might be a model tier issue (haiku vs sonnet/opus) but the process needs to become less hands-on, or at least faster to iterate on.

**Q: On restructure quality — is the right direction to split into decision/generation phases (D10), or is the problem more fundamental?**
A: Not sure about the best approach. In a future refinement, want to critically evaluate deferred tasks to ensure they serve the overarching goals. The current approach needs several passes, but there might be a better solution if we work through the problem. Cheap models are preferred where possible, but that's debatable. The logic itself is prone to false groupings at times which can be confusing.

**Q: On retrieval scope — what's missing to make it RAG-ready?**
A: Several things: fully implementing RAG including synthesis and context injection, automatic invocation (proactive recall without user triggering), and precision improvements. Has drifted away from the original goal of a full knowledge graph but wants to research ML approaches that could work with knowledge graphs to increase semantic search quality. This will require a large effort but is worthy of investigation.

**Q: What ML approaches are you thinking for knowledge graph augmentation?**
A: Currently using a transformer for semantic search. Not deeply versed in what's available, but having more types of edges could augment semantic search to find stronger links than just embedding chunks. This needs significant research and testing. Open to running a local graph database if it makes sense, but likes the lean nature of the project. Precomputing vectors into SQLite is a fine compromise but debatable. Worth noting: may want to reshape the app for hosted deployment in the future, in which case larger infrastructure footprints could make sense.

**Q: On automatic invocation — what's the gap?**
A: This area has been minimally validated. Haven't seen it work without prompting in Claude Desktop. Need a test plan for manual validation to gauge the state of the feature set before planning further revisions.

**Q: Any other areas of attention?**
A: Yes — developing better testing and planning tools is a cross-cutting concern. Dry run is a very crude instrument. It might be worth investing effort into creating dedicated evaluation tools that allow comparing which results look best when presented with several alternatives. This applies across the full curation pipeline, not just restructuring.

---

## Refinement Interview — 2026-03-09

**Context**: Group 1 complete (001 evaluation tooling, 002 invocation validation test plan, 003 KG+ML research). Decomposing Groups 2-3 (004-007) into atomic work items, informed by research findings.

**Q: Group 1 research is done. Key findings: KG graph ML is not viable at vault scale; SQL CTEs recommended for graph expansion; invocation test plan written but unexecuted. How should these findings shape the next work?**

A: Defer graph expansion (003 recommendations) until other search improvements are validated. Want to see if KG is needed after RAG synthesis and retrieval are improved. Defer 006 (invocation hardening) until 002's manual tests are executed. Keep 004 broad — covers full curation pipeline, not just restructure.

**Q: The evaluation framework (cb_evaluate) was built as an MCP tool. Should it be in the MCP server or a companion tool? Is the data actionable during regular usage? How does a manual, laborious tool align with guiding principles?**

A: Unless the data captured by an MCP tool can be acted on during regular usage, it shouldn't be in the product. Like the idea of human-in-the-loop quality gates to validate work is done well, or using opus to judge work done by cheaper models. The problem to address is confusion and frustration from poor curation — just need to make curation work well with minimum intervention during regular usage.

**Q: So the direction is: quality gates built into curation tools (cheap model produces, judge evaluates, escalate on low confidence). The evaluation framework stays as internal dev tooling but not a product feature?**

A: Yes. Want to formalize the ability to improve results without leaning on heavy, expensive models. Keep 007 (per-tool model selection) in scope — valuable for users who aren't price-conscious.

**Decisions made:**
- cb_evaluate removed from MCP server (not a product feature)
- extractors/evaluate.py preserved as internal dev tooling
- Quality gates built into curation tools (restructure, enrich, review)
- Graph expansion deferred until search improvements are validated
- Invocation hardening deferred until manual tests executed
- Per-tool model selection stays in scope

---
## Refinement Interview — 2026-03-09

**Context**: Post-review correction. Capstone review of refinement cycle 1 (WI-008–013) found 4 significant findings, 16 minor findings, and 3 user decision points. All findings to be addressed; none deferred.

**Q: Guiding principles still hold?**
A: Yes, no changes.

**Q: quality_gate_threshold — remove (YAGNI) or wire it into the gate?**
A: Remove. YAGNI.

**Q: quality_gate_enabled configurable via cb_configure?**
A: Yes. We're removing the threshold, but quality_gate_enabled should be configurable via cb_configure. Update error messages to reference cb_configure syntax.

**Q: Execute the automatic invocation test plan (WI-002) before next cycle?**
A: Yes.

**Q: _load_prompt duplication (M2/N2) and hub-page gate criteria (EC1/EC2) — defer or address now?**
A: Address them now.

**Decisions made:**
- Remove `_get_gate_threshold` and `quality_gate_threshold` config key entirely (YAGNI)
- Add `quality_gate_enabled` to `cb_configure` and `cb_status`; update error messages to reference `cb_configure` syntax
- Execute WI-002 automatic invocation test plan this cycle
- Fix all significant and minor findings from capstone review; no deferrals
- Extract `_load_prompt` into `mcp/shared.py`
- Add `### synthesis` and `### restructure_hub` criteria to quality-gate-system.md
- Sync all stale documentation (architecture, constraints, CLAUDE.md, module specs)

---
## Refinement Interview — 2026-03-09 (Cycle 3)

**Context**: Post-review correction + new requirement. Cycle 2 capstone review found 5 significant findings and 12 minor findings. User also wants mock vault testing infrastructure for human-in-the-loop QA.

**Q: Guiding principles still hold?**
A: Yes, no changes.

**Q: Review findings — address all, defer any, or dismiss any?**
A: Address all significant findings (S1/S2 gate hints, MR1 proactive_recall, MR2 manual capture mode, MR3 setup guidance).

**Q: Mock vault — what problem does this solve?**
A: Complement to automated test fixtures. Need a way for humans to test against actual vault structures, not just conceptual unit tests. Feel the effects of changes.

**Q: What should mock vaults contain?**
A: A few variants for different use cases — onboarding from empty vault, specific vault structures (PARA, Zettelkasten, custom), and fully populated vaults. Simulate real-world scenarios.

**Q: Mock vault scope — how many variants, where do they live?**
A: 3-5 variants in a test directory. Should be resettable to initial state. Simple scripts to reset or choose variant, deployed to a predictable location. Use best judgement on use cases, iterate if needed.

**Q: Execution strategy changes?**
A: Parallel if feasible, sonnet model, bypass permissions.

**Decisions made:**
- Fix gate-blocked output hints in restructure.py and review.py FAIL path
- Add proactive_recall to cb_configure following quality_gate_enabled pattern
- Strengthen manual capture mode wording in resources.py
- Add orient-prompt and CLAUDE.md recall guidance to cb_setup completion output
- Fix all residual documentation errors from cycle 2 review
- Update WI-006 with WI-020 confirmed findings
- Create 5 mock vault variants (empty, PARA, Zettelkasten, mature, working-memory) with deploy/reset scripts
- Parallel execution with sonnet model

---
## Refinement Interview — 2026-03-09 (Cycle 4)

**Context**: Post-review correction. Cycle 3 capstone review found 0 critical, 3 significant (fixed immediately), 4 minor findings. Architect codebase analysis surfaced additional dead code, duplicated utilities, and a misleading predicate guidance instruction.

**Q: Guiding principles still hold?**
A: Yes, no changes.

**Q: Review findings and architect analysis items — address all, defer, or dismiss?**
A: Address all: dead code removal (_WM_RECALL_LOG, _title_concept_clusters, similarity_threshold, stale files), utility consolidation (_is_within_vault, frontmatter parsing), gate hint wording standardization, cb_setup predicate guidance fix, and manual capture mode re-test.

**Q: Manual capture re-test ordering?**
A: Execute last, after all code changes are complete.

**Q: Execution strategy?**
A: Same as last cycle — parallel, sonnet, bypass permissions.

**Decisions made:**
- Remove all dead code identified by review and architect analysis
- Consolidate _is_within_vault to shared.py, frontmatter parsing to frontmatter.py
- Standardize gate hint wording to review.py's imperative form
- Fix cb_setup to not suggest domain-specific predicates that get normalized away
- Re-execute WI-020 test D2 as final validation of manual capture mode fix
- Parallel execution with sonnet model

---
## Refinement Interview — 2026-03-10

**Context**: New requirements. User wants to replace the install.sh distribution mechanism with a Claude Code plugin, enabling in-Claude updates/versioning across multiple machines (personal + work) and eventual public distribution.

**Q: Do the guiding principles still hold?**
A: Yes, no changes.

**Q: What problem is plugin distribution solving?**
A: The installer (install.sh) is annoying. Wants an in-Claude solution for updates and versioning. Has a GitHub plugin repo to add cyberbrain to. Releases daily and wants latest version on multiple computers at all times.

**Q: What is "the Claude Code portion"?**
A: The MCP server is still important for Claude Desktop and other apps. That needs additional research to move outside of developer tools. Focus for this cycle: Claude Code distribution path.

**Q: Plugin system capabilities and MCP bundling approach?**
A: Research task. Can we ship a built-in MCP with the plugin? Should we support multiple deployment methods?

**Q: Does install.sh need to be preserved?**
A: Research task. Want to understand how other tools handle these issues — particularly basic-memory as a reference for the kind of tool cyberbrain aims to be.

**Q: Distribution scope?**
A: Both personal use (personal + work machines) and eventual public distribution.

**Q: uv as runtime — acceptable?**
A: Yes, if it makes the most sense in 2026. CLAUDE.md should be updated accordingly. Remove dead skills/ reference from plugin.json.

**Decisions made:**
- Remove dead `"skills"` field from plugin.json (no skills/ directory exists; MCP is the single interface)
- Adopt uv for MCP server launch if research confirms it as the right approach
- Two research tasks before implementation: plugin system capabilities (031), distribution patterns (032)
- MCP distribution to Claude Desktop/Cursor/Zed: deferred, needs separate research
- CLAUDE.md updated once uv approach confirmed by research (WI-033)
- uv user guide filed to vault for review

---
## Refinement Interview — 2026-03-11

**Context**: Post-review correction. Cycle 5 capstone review found 2 critical findings (namespace collision), 3 significant findings, 10 minor findings. The WI-033 implementation passed incremental review but is broken at runtime.

**Q: Guiding principles still hold?**
A: Yes, no changes.

**Q: How to resolve the namespace collision?**
A: Rename `mcp/` to `cyberbrain_mcp/` with proper `__init__.py` files (conventional package approach). No wrapping under a top-level `cyberbrain/` directory at repo root.

**Q: Use src layout?**
A: Yes, with proper packages. Move `mcp/`, `extractors/`, `prompts/` under `src/cybrain/`. Add `__init__.py` files. Use package-qualified imports throughout. Remove `sys.path` manipulation.

**Q: How should hooks/scripts be handled?**
A: Define entry points in pyproject.toml. Hooks call entry points instead of file paths. Non-Python files (hooks, scripts, install.sh) stay at repo root.

**Q: Execution strategy?**
A: Sequential. Single cohesive restructuring task that cannot be broken into testable pieces.

**Decisions made:**
- Adopt src layout: `mcp/` → `src/cybrain/mcp/`, `extractors/` → `src/cybrain/extractors/`, `prompts/` → `src/cybrain/prompts/`
- Add `__init__.py` to make proper packages (`cyberbrain`, `cyberbrain.mcp`, `cyberbrain.extractors`)
- Entry points: `cyberbrain-mcp = "cyberbrain.mcp.server:main"`
- Remove `sys.path` manipulation from server.py and shared.py
- All imports use `cyberbrain.*` namespace
- Sequential execution (single work item)

---
## Refinement Interview — 2026-03-11 (Cycle 6)

**Context**: Post-review correction. Cycle 5 capstone review found 2 critical findings (C1, C2) that block plugin distribution: namespace collision with PyPI `mcp` package and broken entry point in pyproject.toml.

**Q: Guiding principles still hold?**
A: Yes, no changes.

**Q: Review findings — the critical findings block plugin distribution entirely. How to resolve?**
A: Two options presented:
1. Rename `mcp/` to `cyberbrain_mcp/` (minimal change)
2. Wrap all packages under `cyberbrain/` namespace (cleaner organization)
User chose option 2 (namespace wrapping) for cleaner structure.

**Q: Namespace layout — standard src layout puts the package under `src/cybrain/`. This means tests and config files stay at repo root, not inside the package. Acceptable?**
A: Yes, that's the standard pattern.

**Q: Hooks and scripts — they currently call Python files directly. Should they become entry points?**
A: Yes, add entry points for extract_beats and any other callable scripts. Hooks should call entry points, not file paths.

**Q: extractors and prompts — should they also be proper packages?**
A: Yes, add `__init__.py` to `extractors/` as well. Prompts stays as data files (markdown).

**Q: What about the repo structure? Having a single `cyberbrain/` directory at the root seems redundant.**
A: Use src layout — `src/cybrain/` — so tests, hooks, config files stay at repo root. This is the standard Python pattern.

**Q: Execution strategy?**
A: Sequential. This is a cohesive restructuring task that touches many files.

**Decisions made:**
- Restructure to src layout: `mcp/` → `src/cybrain/mcp/`, `extractors/` → `src/cybrain/extractors/`, `prompts/` → `src/cybrain/prompts/`
- Add `__init__.py` files to make proper packages
- Remove `sys.path` manipulation from server.py and shared.py
- Update all imports to package-qualified (`from cyberbrain.mcp.tools import ...`)
- Add entry points in pyproject.toml
- Update hooks to call entry points
- Update tests to use package imports
- Sequential execution

---
## Decision — 2026-03-16: install.sh and uninstall.sh removed

`install.sh` and `uninstall.sh` were deleted. Reasons:

1. **Hooks are Claude Code-only.** PreCompact and SessionEnd hooks are not supported by Claude Desktop or other MCP clients. The Claude Code plugin system registers hooks automatically via `hooks/hooks.json` — `install.sh` registering them in `settings.json` was redundant.

2. **MCP registration is plugin-handled for Claude Code.** The plugin auto-registers the MCP server. Claude Desktop doesn't support the plugin system, but it also doesn't support hooks — so the only thing install.sh provided for Desktop was MCP registration in `claude_desktop_config.json`, which is a one-line manual step.

3. **Dependencies are handled by `uv run`.** The plugin launches the MCP server via `uv run --directory ${CLAUDE_PLUGIN_ROOT}`, which manages the venv automatically. No pre-created venv needed.

4. **YAGNI.** With the plugin covering the Claude Code path entirely, install.sh had no remaining use case that justified its complexity. Config setup is handled by `cb_configure`.

