# Steering Interview

## Initial Planning Interview — 2026-03-09

See `specs/legacy/v1_spec.md` for the original product vision captured in the initial planning session.

---

## Refinement Interview — 2026-03-12

**Context**: Cycle 002 capstone review identified critical bugs in the post-WI-034 (src layout migration) codebase. User also surfaced three new workstreams: intake/retrieval tool interface redesign, filing accuracy improvements, and automatic indexing.

**Q: Do the existing guiding principles still apply?**
A: Yes, with no changes needed. The user confirmed all principles still hold.

**Q: The cycle 002 review found critical bugs: install.sh references deleted directories, and vault.py/search_backends.py/evaluate.py have bare imports that fail in packaged installs. Should these be addressed first?**
A: Yes — critical bugs take priority. All three should be fixed before any new feature work begins. They block users from installing and running the package.

**Q: You mentioned wanting to reshape the MCP tools for intake and retrieval. What problems are you seeing with cb_extract and cb_file?**
A: cb_extract is for session extraction (extracting beats from a Claude conversation transcript). cb_file is for manually capturing a specific insight or note. But there's a third use case: I sometimes have Claude generate a research report or findings document as a standalone artifact, and I want to file that whole document into the vault — not just extract beats from a conversation about it. That "document intake" mode doesn't fit cleanly into either existing tool.

**Q: And for retrieval — what's the issue with cb_recall and cb_read?**
A: cb_recall does search (semantic/keyword) and returns matching notes. cb_read reads a specific note by path. The problem is that cb_recall can also synthesize context from multiple results, and cb_read can also be used for checking what's already in a folder. There's redundancy and unclear purpose separation. I want cleaner, non-redundant interfaces.

**Q: Should we add new tools for these use cases, or redesign the existing ones?**
A: Redesign. Adding interfaces alone is not good — we should remove redundancies. The tool count must not increase relative to what is removed. If we add document intake mode, something else needs to go or be merged.

**Q: On filing accuracy — what's broken?**
A: Two things. First, the clustering algorithm in cb_restructure sometimes produces bad clusters that don't reflect semantic relationships. Second, when autofile routes a beat to a folder, I'd like to know how confident it is. If confidence is low, I want the option to either let it go to the inbox or to ask me before filing.

**Q: For the uncertainty handling — should "ask me" mean a prompt at filing time, or a config flag?**
A: A config flag. I don't want to be interrupted every time there's a low-confidence filing. Set a config key like `uncertain_filing_behavior` with values `ask` or `inbox`, and apply it at filing time.

**Q: Should confidence scoring apply per-beat or per-session?**
A: Per-beat. Each beat might route differently — one might be highly certain (project-specific technical detail), another uncertain (general insight that could go anywhere).

**Q: On automatic indexing — what's the gap?**
A: When beats are written to the vault, they're indexed. But if I edit notes manually in Obsidian, add files, or move things around, the search index gets stale. I'd like the index to stay current without manual `cb_reindex` calls.

**Q: Should this be triggered by file system events, a scheduled job, or something else?**
A: I don't know — that's worth researching first. I'd prefer a lightweight approach that doesn't require a persistent daemon. If cron or a Claude Code hook can cover it, that's better than a file watcher.

**Q: Should we update the vault CLAUDE.md schema to reflect the new tool names and capabilities after all this is implemented?**
A: Yes, and regenerate the current vault's CLAUDE.md from the updated schema. But I want to review the proposed changes before anything is written to the live vault.

**Q: Any ordering constraints? Which items are blockers for others?**
A: The critical bug fixes (install.sh, bare imports) should go first but don't block design work. The design proposals for intake and retrieval (040, 041) should be presented to me before any implementation starts. The vault CLAUDE.md update (047) comes last and requires approval before writing.

**Q: Any execution preferences — sequential vs parallel, model choices?**
A: Parallel where possible, max 4 concurrent agents. Research and design work can use opus. Implementation uses sonnet. I only need to be consulted at the two pause points: design review for WI-040/041, and before WI-047 writes to the live vault. All other decisions are unilateral.

---
## Refinement Interview — 2026-03-22

**Context**: Post-cycle-10 deferred tech debt items. User requested light-touch quick wins first, then heavier tasks.

**Q: Do the existing guiding principles still apply?**
A: Yes, confirmed unchanged (same session as cycle 10).

**Q: What do you want this next cycle to focus on?**
A: Take care of the deferred tasks from cycle 10.

**Q: Priority and approach for the deferred items?**
A: Start with light touch quick wins first before moving on to heavier tasks. For the sys.modules cleanup (10 test files), a lighter-touch approach is acceptable — consolidate patterns, add documentation, reduce fragility without full rewrites.

---
## Refinement Interview — 2026-03-22

**Context**: Minor findings from cycle 012 review. All trivial/small items.

**Q: What do you want this cycle to focus on?**
A: Handle the minor items. Remove the FastMCP pattern migration — it's a non-issue.

**Decisions:**
- FastMCP migration: dismissed (non-issue, current pattern works)
- CI/CD: deferred (infrastructure decision, not a code change)
- ruff ignore list: no action (documented, acceptable breadth)
- All other minor items: address now

---

## Refinement Interview — 2026-03-22

**Context**: Post-release (v1.1.0) tech debt cleanup. Cycle 014 release review passed clean. Architect survey found additional bugs. User wants to address findings and tech debt with obvious solutions first, deferring items requiring design decisions.

**Q: Review findings exist from cycle 014. Are you here to address those findings, to make other changes, or both?**
A: Address findings as well as focusing on technical debt.

**Q: Which items have obvious solutions vs need design decisions?**
A: Fix everything with an obvious solution first, come back to the rest later. Use best judgment, adhere to all rules and principles.

**Items triaged as obvious fixes:**
- autofile.py bare import (line 469): `from search_index` → `from cyberbrain.extractors.search_index` — silent bug, autofile notes never indexed
- search_backends.py dead branch (line 862): `or True` makes GrepBackend unreachable
- Stale build artifacts: build.sh (deprecated), dist/ (stale 0.1.0 wheel), orphaned requirements.txt files
- README: stale paths, Python 3.8+ requirement, install.sh-first installation instructions
- evaluate.py bare import (Q-8): already fixed, removed from scope

**Items deferred (require design decisions):**
- Relation vocabulary mismatch (capture Q-3)
- Search backend cache invalidation (retrieval Q-2)
- Hook/MCP extraction path divergence (capture Q-2)
- Proactive recall validation (retrieval Q-1)
- Manual capture mode re-test (capture Q-1)
- --affected-only correctness (distribution Q-10)
- CI/CD pipeline (distribution Q-11)

**Items accepted as-is (per cycle 014):**
- Dynamic Path.home() references (intentional)
- ruff ignore list breadth (acceptable)
- No formal changelog (journal.md serves)

**Decisions:**
- All principles unchanged
- Architecture unchanged
- Scope limited to obvious fixes only

---

## Refinement Interview — 2026-03-22 (Cycle 16)

**Context**: Post cycle-015 tech debt cleanup. User wants to address all documentation-related minor findings.

**Q: Which deferred items do you want to address?**
A: All of the documentation-related minor findings.

**Q: For ARCHITECTURE.md — should it be updated comprehensively or deprecated in favor of specs/plan/architecture.md?**
A: It should match reality. No deprecation for top-level architecture documentation; it is designed for human-centric review where specs are a record of decisions.

**Q: Anything else documentation-related to bundle in?**
A: This is the full scope.

**Items in scope:**
- ARCHITECTURE.md comprehensive update to match current src-layout
- README MCP JSON example clarification for both install paths
- Close resolved domain question Q-12
- Archive orphaned cycle-013 incremental reviews
- Clean up domains/index.md stale cross-cutting note

**Decisions:**
- All principles unchanged
- Architecture unchanged
- ARCHITECTURE.md is the human-facing overview; specs/plan/architecture.md is the decision record — both maintained

---

## Refinement Interview — 2026-03-22 (Cycle 17)

**Context**: Addressing all remaining tech debt, deferred design decisions, and a critical test infrastructure bug.

**Q: Which items do you want to address?**
A: All of them except CI/CD (item 10) and skip proactive recall / manual capture mode validation (items 7 & 8).

**Q: Relation vocabulary — which is more useful for a knowledge graph like this?**
A: Need to determine which is the more useful vocabulary. [Research spawned]
Research recommended merged 7-predicate set: related, references, causes, caused-by, supersedes, implements, contradicts.
A: Let's do it.

**Q: Search backend cache invalidation — invalidate on config write (a) or TTL-based (b)?**
A: Option a is fine.

**Q: Hook/MCP extraction path divergence — refactor to shared function (a) or document and leave (b)?**
A: Option a.

**Investigation: --affected-only correctness**
Result: Critical bug — _extract_imports() only handles ast.ImportFrom, ignores plain import X. ~30% of import relationships missed. Tests silently skipped.

**Items in scope:**
- Recreate CyberbrainConfig TypedDict (lost during brrr cycle)
- Clean up install.sh/uninstall.sh references in README
- Fix ARCHITECTURE.md prompt count
- Migrate relation vocabulary to merged 7-predicate set
- Add search backend cache invalidation on cb_configure
- Refactor cb_extract to share orchestration with main()
- Fix --affected-only import detection bug

**Decisions:**
- Relation vocabulary: merged 7-predicate set (research-backed)
- Search cache: invalidate on config write
- Extraction path: shared orchestration function
- All principles unchanged

---

## Refinement Interview — 2026-03-23 (Cycle 18)

**Context**: Cycle 017 review found 2 significant findings (run_extraction config param, residual _write_beats_and_log) and 3 minor (architecture tensions, CLAUDE.md vocabulary, config docs).

**Q: Address all remaining items?**
A: Yes, do a refine cycle to address all remaining items.

**Items in scope:**
- Fix run_extraction() config parameter and merge _write_beats_and_log()
- Mark architecture doc tensions T5/T6/T7 resolved

**Decisions:**
- All principles unchanged
- CLAUDE.md vocabulary update: verified not needed (CLAUDE.md doesn't mention relations)
- Config doc pass: deferred (TypedDict is canonical)
