# Decision Log — Cyberbrain Cycle 002

## Decision Log (chronological)

---

### Planning Phase (Refinement Cycle 7)

#### DL1: Three-workstream plan for cycle 002

- **When**: Refinement cycle 7 planning — 2026-03-12
- **Decision**: Structure cycle 002 around three concurrent workstreams: (1) distribution completion — fix post-WI-034 breakage identified by cycle 002 reviewers; (2) interface redesign — intake (WI-042) and retrieval (WI-046) backed by research (WI-040, WI-041); (3) filing accuracy and automation — confidence scoring (WI-043), clustering fix (WI-044), automatic indexing (WI-045).
- **Rationale**: Cycle 002 reviewers found two critical and multiple significant issues left by WI-034 that blocked all distribution paths. Interface redesign and filing accuracy improvements were pre-existing user requirements.
- **Implications**: Distribution workstream (WI-035–037) must complete before interface or filing workstreams can be published. WI-047 (vault CLAUDE.md update) is gated on WI-042 and WI-046 completing first.

#### DL2: Design-before-implementation gate for interface redesign

- **When**: Refinement cycle 7 planning — 2026-03-12
- **Decision**: Execute WI-040 (intake interface design) and WI-041 (retrieval interface design) before WI-042 and WI-046 (implementations). Require explicit user approval of both designs before group 2 execution begins.
- **Rationale**: Interface changes affect tool count and public API; user approval was required before any tool was added or removed.
- **Implications**: WI-042 and WI-046 cannot start until designs are reviewed and approved. User consultation is a hard gate, not advisory.

#### DL3: Token-efficient testing infrastructure added as refinement cycle 8

- **When**: Refinement cycle 8 planning — 2026-03-12
- **Decision**: Add WI-048 through WI-051: pytest markers (core/extended/slow), AST-based import-graph plugin for `--affected-only` mode, quiet addopts defaults, two-pass wrapper script at `scripts/test.py`.
- **Rationale**: User request to reduce token spend during ideate cycles. Test suite was running 1200+ tests on every change. Expected reduction: 95%+ fewer tests per change, 99% less output volume.
- **Implications**: WI-048–051 are pure infrastructure; they do not change test coverage or acceptance criteria for any feature work item.

---

### Execution Phase — Distribution Workstream

#### DL4: WI-035 — install.sh paths updated to src/cyberbrain/ locations

- **When**: WI-035 execution — 2026-03-12
- **Decision**: Update all `cp` source paths in install.sh from `$REPO_DIR/extractors/`, `$REPO_DIR/mcp/`, `$REPO_DIR/prompts/` to `src/cyberbrain/` equivalents. Replace `pip install -r requirements.txt` with pyproject.toml-based install. Add missing files identified during rework: `quality_gate.py`, four prompt files, and `extractors/__init__.py`.
- **Rationale**: Code-quality C1, gap-analysis II1, and gap-analysis IR1 all classified install.sh as critically broken. Claude Desktop users on a fresh clone were completely blocked. `set -euo pipefail` aborted at the first missing `cp` target.
- **Implications**: Manual installation for Claude Desktop users is restored.

#### DL5: WI-036 — bare imports fixed in test files and search_backends.py

- **When**: WI-036 execution — 2026-03-12
- **Decision**: Replace all `from search_backends import X` with `from cyberbrain.extractors.search_backends import X` across multiple test files. Fix `search_backends.py` `try` block to use `from cyberbrain.extractors.frontmatter import ...`. Remove dead `try/except ImportError` wrapper in `vault.py`.
- **Rationale**: Code-quality C2 (test runtime failures) and S1 (search_backends.py always using fallback implementations) were both caused by bare module names that resolved under the old flat layout but not under src layout.
- **Implications**: The canonical `frontmatter.py` is now always used by `search_backends.py`. Any future change to `frontmatter.py` will be reflected in search index builds.

#### DL6: WI-037 — documentation and domain questions updated

- **When**: WI-037 execution — 2026-03-12
- **Decision**: Update CLAUDE.md (tool count 10→11, paths, dev invocation), update all module specs and architecture doc to use `src/cyberbrain/` paths, update distribution domain questions file (Q-1 through Q-7 marked resolved), add deprecation notice to build.sh, merge duplicate Distribution section in architecture.md.
- **Rationale**: Spec-adherence review found five architecture deviations (D1–D3 path staleness, D4 shared.py mischaracterization, D5 search_backends.py fallback) and one unmet WI-034 acceptance criterion (CLAUDE.md not updated). Gap-analysis IR2 noted Q-1 through Q-7 all showed `status: open` despite being resolved.
- **Implications**: All seven cycle-001 distribution domain open questions are now closed.

---

### Execution Phase — Research and Design

#### DL7: WI-038 — filing accuracy research completed

- **When**: WI-038 execution — 2026-03-12
- **Decision**: Research complete at `specs/steering/research/filing-accuracy-clustering.md`. Key findings: clustering parameter adjustment and vault history injection as examples in autofile prompt. Qualifying assumption recorded: threshold formula may need per-corpus validation.
- **Implications**: WI-044 (improved clustering) is unblocked but unstarted as of cycle 002 review.

#### DL8: WI-039 — auto-indexing research completed

- **When**: WI-039 execution — 2026-03-12
- **Decision**: Recommendation: lazy reindex on `cb_recall` (primary) plus SessionEnd hook (complement). No persistent daemon. Research at `specs/steering/research/auto-indexing-strategy.md`.
- **Implications**: WI-045 (automatic indexing) is unblocked but unstarted as of cycle 002 review.

#### DL9: WI-040 — intake interface design approved with durability parameter addition

- **When**: WI-040 design review — 2026-03-12
- **Decision**: Approve intake interface design. `cb_file` expanded with document intake mode (accepts pre-written document, applies frontmatter, routes via autofile or specified folder, no LLM extraction). Add `durability` parameter with default "durable" for UC3; ignored for UC2.
- **Implications**: Net tool count remains 11. WI-042 implements this design.

#### DL10: WI-041 — retrieval interface design approved with max_chars_per_note as parameter

- **When**: WI-041 design review — 2026-03-12
- **Decision**: `cb_read` extended with `synthesize: bool`, multi-identifier support (pipe `|` delimiter, up to 10 identifiers), and `max_chars_per_note: int` (default 2000, 0 = no truncation). User changed body truncation from hardcoded to an explicit parameter.
- **Implications**: WI-046 implements this design. Empty-query synthesis uses fallback message. Pipe `|` is the multi-identifier delimiter (does not appear in Obsidian filenames).

---

### Execution Phase — Filing Confidence

#### DL11: WI-043 — can_ask parameter added to autofile_beat

- **When**: WI-043 execution — 2026-03-13
- **Decision**: Add `can_ask: bool = False` parameter to `autofile_beat`. When `can_ask=False` (default for all non-interactive callers), uncertain beats fall back to inbox routing. Only `cb_file` passes `can_ask=True`.
- **Rationale**: Incremental review S1: without this guard, hooks and `cb_extract` silently dropped beats when `uncertain_filing_behavior="ask"`. Silent beat loss violates GP-8.
- **Implications**: All non-interactive callers have a safe fallback. The `ask` path is only active when a user is present to respond.

#### DL12: WI-043 — hardcoded confidence threshold branch removed (YAGNI)

- **When**: WI-043 execution — 2026-03-13
- **Decision**: Remove hardcoded `elif confidence < 0.7` branch from `autofile.py`. Branch was unreachable when `uncertain_filing_threshold >= 0.7` and was not in the WI-043 spec.
- **Rationale**: Incremental review S3. YAGNI discipline (GP-10).

#### DL13: WI-043 — confidence score included in frontmatter routing flag

- **When**: WI-043 execution — 2026-03-13
- **Decision**: Change `cb_uncertain_routing` frontmatter field from `cb_uncertain_routing: true` to `cb_uncertain_routing: {confidence:.2f}`.
- **Rationale**: Incremental review M1. The bare boolean discarded the confidence value, making it impossible to audit why a note was routed to inbox.

---

### Execution Phase — Token-Efficient Testing

#### DL14: WI-048 through WI-051 implemented without incremental reviews

- **When**: Refinement cycle 8 execution — 2026-03-12
- **Decision**: Implement pytest markers (WI-048), affected-only plugin (WI-049), quiet addopts (WI-050), and test wrapper script (WI-051) as a group without individual incremental reviews before the cycle 002 capstone.
- **Implications**: These four work items lack incremental review coverage. Their correctness and completeness are unverified by the formal review process.

---

### Review Phase

#### DL15: Reviewer outputs generated against pre-fix WI-034 state

- **When**: Cycle 002 review phase — before WI-035/036/037 execution
- **Decision**: Accept that the three reviewer outputs (code-quality, spec-adherence, gap-analysis) were generated against the post-WI-034 but pre-fix state of the codebase.
- **Implications**: Code-quality verdict (Fail) and spec-adherence verdict (Fail) describe a state that no longer exists. The cycle includes its own fix wave. The capstone review predates the corrections it motivated.

#### DL16: Distribution domain questions file updated to resolved status

- **When**: WI-037 execution (review-phase consequence) — 2026-03-12
- **Decision**: Mark all seven distribution domain open questions (Q-1 through Q-7) as resolved.
- **Rationale**: Gap-analysis IR2 flagged stale open-status entries risking re-investigation of solved problems in the next planning cycle.

---

## Open Questions

### OQ1: WI-042 implementation status unknown — no incremental review

- **Question**: Was WI-042 (implement intake interface) executed? The incremental review file is empty (1 line). No incremental verdict exists.
- **Impact**: The cb_file document intake mode (title parameter, document mode switch, durability parameter) may not be implemented. WI-046 and WI-047 depend on WI-042 completing.
- **Who answers**: Technical investigation — check `src/cyberbrain/mcp/tools/file.py` against the WI-040 design (title parameter, document intake mode, durability parameter).
- **Consequence of inaction**: If WI-042 was not executed, the design-approved intake interface is absent and WI-047 cannot proceed.

### OQ2: WI-044 (improved clustering/filing accuracy) not started

- **Question**: Has the clustering fix and vault history injection been implemented?
- **Impact**: Filing accuracy improvements from WI-038 research remain unrealized.
- **Who answers**: Technical investigation — check `src/cyberbrain/extractors/autofile.py` and related files.

### OQ3: WI-045 (automatic indexing) not started

- **Question**: Has lazy reindex on `cb_recall` plus SessionEnd hook triggering been implemented?
- **Impact**: Users must manually run `cb_reindex` to keep search index current.
- **Who answers**: Technical investigation — check `src/cyberbrain/mcp/tools/recall.py` and SessionEnd hook.

### OQ4: WI-046 (implement retrieval interface) not started

- **Question**: Has the retrieval interface been implemented (multi-identifier `cb_read`, `synthesize` parameter, `max_chars_per_note` parameter)?
- **Impact**: Approved retrieval interface design remains a design document only.
- **Who answers**: Technical investigation — check `src/cyberbrain/mcp/tools/recall.py` against WI-041 design.

### OQ5: WI-047 (update vault CLAUDE.md) not started — blocked by OQ1 and OQ4

- **Question**: Given that WI-042 and WI-046 status is uncertain, what is WI-047's status?
- **Impact**: Live vault CLAUDE.md may reference stale tool names.
- **Who answers**: User decision — requires user approval before writing to vault; blocked until OQ1 and OQ4 are resolved.

### OQ6: WI-048–051 (token-efficient testing) not reviewed

- **Question**: Are the affected-only plugin and marker implementations correct and complete?
- **Impact**: If `--affected-only` has incorrect import graph analysis, it may silently skip tests, producing false confidence in passing suites.
- **Who answers**: Technical investigation — verify affected-only mapping and marker application.

### OQ7: evaluate.py CLI main() bare unqualified import

- **Question**: `src/cyberbrain/extractors/evaluate.py` line 407 uses `from config import resolve_config` inside `main()`. Should be `from cyberbrain.extractors.config import resolve_config`.
- **Impact**: Evaluate dev tool unusable in packaged installs. Failure is invisible at import time; surfaces only on CLI invocation.
- **Who answers**: Technical investigation — one-line fix; gap-analysis EC1 recommended addressing now.

### OQ8: requirements.txt files inside src/cyberbrain/ are orphaned

- **Question**: Should `src/cyberbrain/extractors/requirements.txt` and `src/cyberbrain/mcp/requirements.txt` be deleted or marked as legacy?
- **Impact**: Developers following pip install -r path get under-specified dependency install (missing fastmcp, mcp, ruamel.yaml).
- **Source**: code-quality M3; gap-analysis MI1.

### OQ9: Stale "sys.path setup" comment headers in test files

- **Question**: Should the stale `# sys.path setup` section headers be renamed in a batch cleanup?
- **Impact**: Minor contributor confusion. No functional regression.
- **Source**: gap-analysis MI3; code-quality M2. Deferred from WI-037.

### OQ10: WI-030 manual capture mode re-test still pending user action

- **Question**: Has the emphatic prohibition wording from WI-023 been validated against live Claude Desktop behavior?
- **Impact**: If wording did not fix behavior, users in manual mode continue receiving unsolicited filing offers.
- **Who answers**: User action — requires live Claude Desktop session with procedure at `specs/steering/research/manual-capture-retest.md`.

### OQ11: WI-034 spec documents contain "cybrain" typo throughout

- **Question**: Should the archived WI-034 work item spec and incremental review be corrected (both write `src/cybrain/` missing the 'e')?
- **Impact**: Acceptance criteria in archived specs reference a path that does not exist. Minor documentation quality issue.
- **Source**: spec-adherence N1.

---

## Cross-References

### CR1: install.sh breakage — convergence across all three reviewers

All three reviewers independently identified the same root cause from different angles:
- **Code-quality C1**: runtime failure — `set -euo pipefail` aborts on first missing `cp` target.
- **Gap-analysis II1, IR1**: functional breakage — Claude Desktop installation contract violated.
- **Spec-adherence D1–D3**: documentation staleness — same underlying cause: WI-034 moved files but did not update all references.

Combined picture: WI-034 migration was applied to source imports and directory structure but not to install.sh, hooks, or documentation — a consistent pattern of partial migration. All addressed together by WI-035 (install.sh), WI-036 (imports), WI-037 (docs).

### CR2: search_backends.py frontmatter fallback — same defect, two reviewers

- **Code-quality S1**: `from frontmatter import` always fails in src layout; `except` branch always executes; `frontmatter.py` never used.
- **Spec-adherence D5, U1**: same issue; notes `analyze_vault.py` uses correct form while `search_backends.py` does not; characterizes inline fallback as always-active with divergence risk.
- **Gap-analysis EC2**: same issue; classifies as minor; recommends addressing now to prevent future divergence.

No contradictions between reviewers. All three documents overlap at lines 783–786 of `search_backends.py`. Fixed by WI-036.

### CR3: Stale path references — systematic pattern identified independently

- **Code-quality**: M1 (dead EXTRACTORS_DIR), M2 (stale sys.path comments), M4 (stale docstring).
- **Spec-adherence**: D1–D3 (module specs and architecture doc use pre-WI-034 paths).
- **Gap-analysis**: MI2 (dead EXTRACTORS_DIR), MI3 (stale sys.path headers), IR2 (domain questions file shows all 7 questions as open).

Pattern: WI-034 updated source code but left documentation, comments, and tracking documents in the pre-migration state. All addressed by WI-037.

### CR4: WI-042 implementation gap — synthesis-level observation

No reviewer directly evaluated WI-042. The empty incremental review file is the only signal that implementation status is uncertain. This gap was not catchable from any single reviewer's output; it emerges only from cross-referencing the review-manifest with the incremental review directory. Recorded as OQ1.
