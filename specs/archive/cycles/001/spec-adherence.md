# Spec Adherence Review — WI-034 (Restructure to src Layout)

## Verdict: Fail

The src layout restructuring is partially complete. The directory structure, package `__init__.py` files, MCP layer imports, and entry point function are correctly implemented. However, five acceptance criteria are not met: the extractor layer retains the old `sys.path` manipulation and bare imports; all test files retain bare imports and `sys.path` manipulation; both hooks use stale paths that will not resolve in plugin mode; `.mcp.json` still launches `python -m mcp.server` instead of `python -m cyberbrain.mcp.server`; and the wheel packages directive still lists non-existent top-level directories.

---

## Acceptance Criteria

- [x] `src/cyberbrain/` directory exists with `__init__.py` making it a proper package — `src/cyberbrain/__init__.py` exists.
- [x] `src/cyberbrain/mcp/__init__.py` exists — confirmed.
- [x] `src/cyberbrain/extractors/__init__.py` exists — confirmed.
- [x] `pyproject.toml` updated for src layout with correct entry points — `[project.scripts]` has `cyberbrain-mcp = "cyberbrain.mcp.server:main"` at line 36.
- [x] Entry point `cyberbrain-mcp = "cyberbrain.mcp.server:main"` defined — `server.py` has a `main()` function; MCP layer imports use `cyberbrain.*` namespace.
- [ ] Entry point for extract script (if needed) works — No `cyberbrain-extract` entry point is defined. Hooks still invoke the extractor as a file path.
- [ ] `.mcp.json` uses `python -m cyberbrain.mcp.server` — `.mcp.json` line 8 still reads `"python", "-m", "mcp.server"`. This launches the PyPI `mcp` package's server, not `cyberbrain.mcp.server`. The namespace collision that WI-034 was created to fix is still present in `.mcp.json`.
- [ ] All imports use `cyberbrain.*` namespace — The MCP layer (`src/cyberbrain/mcp/`) uses `cyberbrain.*` imports at the top level. The extractor layer (`src/cyberbrain/extractors/`) does not. All extractor submodules still use bare unqualified imports (`from backends import`, `from config import`, `from frontmatter import`, etc.). Multiple MCP tool files also have bare imports: `restructure.py`, `recall.py`, `enrich.py`, `manage.py`, `setup.py`, `review.py`.
- [ ] `sys.path` manipulation removed from `server.py`, `shared.py`, and test files — `shared.py` has no `sys.path` manipulation (pass). `server.py` has no `sys.path` manipulation (pass). `extract_beats.py` adds its own directory to `sys.path` at lines 26–28. All test files still contain `sys.path.insert` calls pointing at the deleted `mcp/` and `extractors/` directories.
- [ ] `python3 -m pytest tests/` passes — Test `sys.path` manipulations point to `REPO_ROOT / "mcp"` and `REPO_ROOT / "extractors"` which are now deleted. 18 of 20 test modules fail on collection.
- [ ] `uvx cyberbrain-mcp` or `uv tool install` works — `pyproject.toml` line 43: `packages = ["mcp", "extractors", "prompts"]` still lists top-level directories that were deleted in this restructure. Hatchling will produce an empty or malformed wheel.
- [ ] Hooks call entry points instead of file paths — Both `pre-compact-extract.sh` (line 29) and `session-end-extract.sh` (line 45) look for `$CLAUDE_PLUGIN_ROOT/extractors/extract_beats.py`. That path does not exist after the restructure. In plugin mode, both hooks silently fall through to the legacy `~/.claude/cyberbrain/extractors/extract_beats.py` path.

---

## Architecture Adherence

### Component map still references old paths

`specs/plan/architecture.md` component map (lines 82–98) and data flow section (line 112) still document components under `extractors/` and `mcp/` rather than `src/cyberbrain/extractors/` and `src/cyberbrain/mcp/`. The Distribution section at line 550 explicitly states "MCP server launches via `uv run --directory ${CLAUDE_PLUGIN_ROOT} python -m mcp.server`" — the old ambiguous command the restructure was meant to replace. The architecture document was not updated as required by the "Files to modify" section of WI-034.

### CLAUDE.md documentation still references old paths

`CLAUDE.md` key files table and data flow section reference `extractors/extract_beats.py`, `mcp/server.py`, and `mcp/shared.py` at their old flat locations. The validation command instructs `python3 extractors/extract_beats.py ...`, a path that no longer exists. `CLAUDE.md` was in the WI-034 "Files to modify" list but was not updated.

### MCP layer boundary correctly updated

The MCP layer (`src/cyberbrain/mcp/`) fully uses the `cyberbrain.*` namespace for top-level imports. `server.py` imports from `cyberbrain.mcp.tools` and `cyberbrain.mcp`. `shared.py` imports from `cyberbrain.extractors.extract_beats` and `cyberbrain.extractors.frontmatter`. This layer is largely correct.

### Extractor layer boundary not updated

The extractor layer (`src/cyberbrain/extractors/`) was moved to the new location but its internal imports were not migrated to use the `cyberbrain.*` namespace. The layer still uses flat-module import style, relying on `sys.path` injection by `extract_beats.py` to resolve sibling modules. Extractor modules are not importable as `cyberbrain.extractors.*` from outside the extractors directory unless `extract_beats.py` has been imported first to inject the path.

### Wheel packages directive broken

`pyproject.toml` line 43 still lists `packages = ["mcp", "extractors", "prompts"]`. These top-level directories were deleted by the restructure. The correct directive for the src layout is `packages = ["src/cyberbrain"]` or hatchling's auto-discovery from `src/`.

---

## Guiding Principle Adherence

### Principle 6 — Lean Architecture, Heavy on Quality

Partially followed. The restructure eliminates the confusing flat layout and creates a proper namespace package for the MCP layer. The extractor layer retains `sys.path` manipulation — the exact non-lean workaround the restructure was intended to remove. Evidence: `src/cyberbrain/extractors/extract_beats.py` lines 26–28.

### Principle 8 — Graceful Degradation Over Hard Failure

Violated for the hook path in plugin mode. `pre-compact-extract.sh` line 29 checks `$CLAUDE_PLUGIN_ROOT/extractors/extract_beats.py`. After the restructure the file lives at `src/cyberbrain/extractors/extract_beats.py`. The check will always be false in plugin mode, so the hook silently skips — no extraction occurs. For a new plugin-only install without the legacy `~/.claude/cyberbrain/` path, extraction is silently disabled. Evidence: `hooks/pre-compact-extract.sh` lines 29–33, `hooks/session-end-extract.sh` lines 45–49.

### Principle 10 — YAGNI Discipline

Followed. No new features or abstractions were introduced.

---

## Constraint Adherence

### "All vault writes go through extract_beats.py or import.py"

Constraint holds. The extractor entry point is now at `src/cyberbrain/extractors/extract_beats.py` and performs the same role. The MCP layer continues to delegate vault writes to the extractor layer via `shared.py`.

### Hook exit codes (always exit 0)

Hooks continue to exit 0 in all paths. No regression.

### Filename character restrictions and soft delete

No changes to `make_filename()` or `_move_to_trash()`. Both constraints hold.

---

## Cross-Cutting Concerns

### Test suite points to deleted directories

Every test file builds paths relative to `REPO_ROOT / "mcp"` and `REPO_ROOT / "extractors"`. Both directories were deleted by this restructure. The `sys.path` manipulation in every test file inserts paths that no longer exist. Running `python3 -m pytest tests/` from a clean checkout without `pip install -e .` will fail on 18 of 20 modules at import time.

### conftest.py mocks under old module key

`tests/conftest.py` installs the mock at `sys.modules["extract_beats"]`. After the restructure, `shared.py` imports from `cyberbrain.extractors.extract_beats`. The mock will not intercept imports that use the new namespace. Test isolation may be silently broken.

---

## Deviations from Plan

1. `.mcp.json` was not updated from `python -m mcp.server` to `python -m cyberbrain.mcp.server`. The spec explicitly required this change.
2. The extractor layer's internal imports were not migrated to `cyberbrain.*` namespace. The spec listed all extractor files under "Files to update (import paths)".
3. All test files were not updated. The spec section "Test files to update" required removing `sys.path` manipulation and switching to `cyberbrain.*` imports.
4. Both hooks were not updated to use the new extractor path. The spec required hooks to "call entry points instead of file paths."
5. `pyproject.toml` `[tool.hatch.build.targets.wheel]` packages directive was not updated from `["mcp", "extractors", "prompts"]`.
6. `specs/plan/architecture.md` was not updated to reflect the src layout. The spec listed it under "Files to modify."
7. `CLAUDE.md` was not updated to reflect the src layout paths. The spec listed it under "Files to modify."

Note: The WI-034 spec document itself contains a typo — it refers to the package as `src/cybrain/` (missing `er`) in the "Files to create" section. The implementation correctly uses `src/cyberbrain/`. This is a spec typo, not an implementation error.

All work items adhere to guiding principles, architecture, and constraints. Research outputs (WI-031, WI-032) correctly inform WI-033's scope without oversteering into implementation.

---

## Architectural Adherence

### Module boundaries respected

- **WI-027** (dead code removal): Removed code from `mcp/tools/restructure.py`, `mcp/tools/review.py`, `mcp/shared.py`, and `extractors/analyze_vault.py` without violating module boundaries. The consolidation of `_is_within_vault` into `shared.py` maintains the MCP/extractor layer separation.
- **WI-028** (gate hint wording): Changed output strings in `enrich.py` and `restructure.py` — text-only, no architectural impact.
- **WI-029** (predicate guidance): Modified `mcp/tools/setup.py` (prompt text) and `extractors/vault.py` (predicate set normalization). Both changes are localized and consistent with existing patterns.

### Data flow unchanged

No changes to data flow in cycles 4-5. All modifications are localized to individual modules.

---

## Guiding Principles Adherence

### P6: Lean Architecture, Heavy on Quality

**WI-027** removes dead code and consolidates utilities, directly supporting lean architecture. No new dependencies were introduced.

**WI-031/WI-032** recommend uvx-based distribution as a leaner alternative to the current install.sh, consistent with P6. The research explicitly avoids adding complexity (e.g., recommends against uv run --with as the primary launch pattern, recommends keeping config at `~/.claude/cyberbrain/config.json` rather than relocating it).

### P10: YAGNI Discipline

**WI-027** removed `similarity_threshold` and `quality_gate_threshold` as YAGNI — both were plumbing that was never wired into production logic. This is P10 in action.

**WI-029** removed unsupportable predicate suggestions from the setup prompt. The system now suggests only the 6 supported predicates rather than hypothetical custom ones.

### P8: Graceful Degradation Over Hard Failure

No changes to error handling in cycles 4-5. The research outputs (WI-031, WI-032) correctly identify that the plugin system cannot run post-install scripts, and recommend keeping a thin `install.sh` for first-run config and migration — this preserves graceful degradation for users who cannot or do not use the plugin system.

---

## Constraints Adherence

### C7: Hook exit codes

No changes to hooks in cycles 4-5. Existing hooks continue to exit 0 regardless of internal errors.

### C8: Path validation

**WI-027** consolidated `_is_within_vault` into `mcp/shared.py`. The function remains unchanged and continues to validate all vault write paths. No security regression.

### C10: Soft delete

No changes to trash handling in cycles 4-5.

### C11: Filename character restrictions

No changes to filename handling in cycles 4-5.

---

## Work Item Scope Adherence

| Work Item | Scope Defined | Scope Delivered | Verdict |
|---|---|---|---|
| WI-027 | Remove dead code, consolidate utilities, delete stale files | All criteria met after rework | Pass |
| WI-028 | Standardize gate hint wording | All criteria met after rework | Pass |
| WI-029 | Fix predicate guidance, resolve wasDerivedFrom bug | All criteria met after rework | Pass |
| WI-030 | Document re-test procedure, execute test | Documented; execution pending user action | Pass (procedural) |
| WI-031 | Research plugin system capabilities | All acceptance criteria met | Pass |
| WI-032 | Research distribution patterns | All acceptance criteria met | Pass |

---

## Documentation Alignment

### WI-027: README updated

The incremental review found that README.md still documented `similarity_threshold` in two locations. This was fixed in rework.

### WI-031/WI-032: Research docs reference each other

Both research documents cross-reference correctly. WI-032's recommendations directly build on WI-031's findings. No contradictions.

### WI-033: Implementation plan exists

`specs/plan/work-items/033-implement-plugin-distribution.md` was created during refinement cycle 5 and correctly references both research outputs.

---

## Cross-Cutting Consistency

### Error message patterns

**WI-028** standardized error message hint wording across `enrich.py`, `restructure.py`, and `review.py`. All three now use imperative form: "Run cb_configure(...)" rather than descriptive "To disable the gate, you can run...".

### Import patterns

**WI-027** established the pattern for MCP-layer imports from extractor modules: `from frontmatter import parse_frontmatter as _parse_frontmatter`. This is consistent with existing import aliases in `mcp/shared.py`.

---

## Findings Requiring User Input

None. All work items are self-contained and adherent to existing architecture and principles.