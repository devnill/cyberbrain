# Gap Analysis — WI-034 (Restructure to src layout with cyberbrain namespace)

## Summary

The directory restructuring moved files to `src/cyberbrain/` and created `__init__.py` files, and `main()` was defined in `server.py`. However, three of the five configuration targets (`pyproject.toml` packages directive, `.mcp.json` module path, and hook extractor-path resolution) were not updated from their pre-restructure values. Internal imports inside `extract_beats.py` and multiple MCP tool files (`restructure.py`, `recall.py`, `enrich.py`, `manage.py`, `setup.py`, `review.py`) still use bare unqualified names that rely on `sys.path` manipulation rather than the `cyberbrain.*` namespace. All test files continue to manipulate `sys.path` to add the old `mcp/` and `extractors/` directories. A clean install via `uvx cyberbrain-mcp` or `python -m cyberbrain.mcp.server` will fail.

---

## Missing Requirements

### MR1: pyproject.toml packages directive not updated for src layout

- **WI-034 reference**: Acceptance criterion "pyproject.toml updated for src layout with correct entry points"
- **Current state**: `pyproject.toml` line 43: `packages = ["mcp", "extractors", "prompts"]`. These directories no longer exist at the repo root.
- **Gap**: The wheel builder will produce an empty wheel. The `cyberbrain-mcp` entry point will fail at runtime with `ModuleNotFoundError`.
- **Severity**: Critical

### MR2: .mcp.json module path not updated

- **WI-034 reference**: Acceptance criterion "`.mcp.json` uses `python -m cyberbrain.mcp.server`"
- **Current state**: `.mcp.json` line 8: `"python", "-m", "mcp.server"`. This is the pre-restructure path.
- **Gap**: The MCP server will fail to launch for plugin users. `python -m mcp.server` resolves to the PyPI `mcp` package — the exact namespace collision the restructure was meant to fix.
- **Severity**: Critical

### MR3: Hook scripts still reference old extractor path

- **WI-034 reference**: Acceptance criterion "Hooks call entry points instead of file paths"
- **Current state**: Both `hooks/pre-compact-extract.sh` (line 29) and `hooks/session-end-extract.sh` (line 45) check for `$CLAUDE_PLUGIN_ROOT/extractors/extract_beats.py`. That path no longer exists.
- **Gap**: Automatic capture silently fails for clean plugin installations. The hook falls back to `~/.claude/cyberbrain/extractors/extract_beats.py` which does not exist on a fresh plugin-only install.
- **Severity**: Critical

### MR4: Internal imports in MCP tool files not migrated to cyberbrain namespace

- **WI-034 reference**: Acceptance criterion "All imports use `cyberbrain.*` namespace"
- **Current state**: Multiple MCP tool files use bare unqualified imports:
  - `src/cyberbrain/mcp/tools/restructure.py`: `from backends import call_model, BackendError, get_model_for_tool`
  - `src/cyberbrain/mcp/tools/recall.py`: `from backends import get_model_for_tool`; `from search_backends import SearchResult, ...`
  - `src/cyberbrain/mcp/tools/enrich.py`: `from backends import call_model, get_model_for_tool`
  - `src/cyberbrain/mcp/tools/manage.py`: `from tools.recall import _DEFAULT_DB_PATH, _DEFAULT_MANIFEST_PATH`; `from search_backends import get_search_backend`
  - `src/cyberbrain/mcp/tools/setup.py`: `from backends import call_model`
  - `src/cyberbrain/mcp/tools/review.py`: `from backends import call_model, BackendError, get_model_for_tool`
- **Gap**: None of these will resolve in a clean installed environment. `from tools.recall import` in `manage.py` will collide with PyPI `tools` namespace.
- **Severity**: Critical

### MR5: extract_beats.py internal imports not migrated to cyberbrain namespace

- **WI-034 reference**: Implementation note showing migration from `from config import` to `from cyberbrain.extractors.config import`
- **Current state**: `src/cyberbrain/extractors/extract_beats.py` lines 35-57 still use bare imports: `from config import`, `from backends import`, `from transcript import`, `from run_log import`, `from vault import`. The file injects its own directory into `sys.path` at lines 27-28.
- **Gap**: The `sys.path` injection is a workaround that creates brittle import ordering dependencies. The acceptance criterion requires removing it.
- **Severity**: Significant

### MR6: `scripts/import.py` still hardcodes legacy extractor path

- **WI-034 reference**: Scope includes updating all files that import from `mcp/` or `extractors/`
- **Current state**: `scripts/import.py` lines 33-34 hardcode `EXTRACTORS_DIR = Path.home() / ".claude" / "cyberbrain" / "extractors"` and add it to `sys.path`.
- **Gap**: `scripts/import.py` will fail in a clean plugin install where the extractor is at the plugin cache location.
- **Severity**: Significant

---

## Missing Implicit Requirements

### IR1: Test files must import from cyberbrain namespace

- **Expectation**: After src layout restructure, tests should run with `python -m pytest tests/` after `pip install -e .`, with no `sys.path` manipulation.
- **Current state**: Every test file and `conftest.py` still adds old paths to `sys.path`. `conftest.py` lines 22-29 add `EXTRACTORS_DIR = REPO_ROOT / "extractors"` and `MCP_DIR = REPO_ROOT / "mcp"` — directories that no longer exist. Tests then use bare imports: `import shared`, `from tools import recall`, `from search_backends import`, `import extractors.extract_beats as eb`.
- **Gap**: The sys.path manipulation adds nonexistent directories. 18 of 20 test modules fail at collection from a clean checkout.
- **Severity**: Significant

### IR2: conftest.py mock targets wrong module keys

- **Expectation**: The shared mock in `conftest.py` that installs a fake `extract_beats` module in `sys.modules` should use the correct module key for the new namespace.
- **Current state**: `tests/conftest.py` installs the mock at `sys.modules["extract_beats"]`. `shared.py` imports from `cyberbrain.extractors.extract_beats`. The mock will not intercept `shared.py`'s import.
- **Gap**: Test isolation breaks silently. Tests that rely on this mock to prevent real LLM calls or vault writes may not be properly isolated.
- **Severity**: Significant

### IR3: CLAUDE.md key files table references old paths

- **Expectation**: Developer-facing documentation must reflect the current layout after a structural change.
- **Current state**: `CLAUDE.md` lists files using old paths: `extractors/extract_beats.py`, `mcp/server.py`, `mcp/shared.py`, etc. The validation command instructs `python3 extractors/extract_beats.py ...` — a path that no longer exists.
- **Gap**: Primary developer onboarding document will cause immediate confusion and failed commands.
- **Severity**: Significant

### IR4: architecture.md component map references old paths

- **Expectation**: Architecture document should reflect actual file locations.
- **Current state**: `specs/plan/architecture.md` component map lists all components under `mcp/` and `extractors/` paths. No `src/cyberbrain/` references appear.
- **Severity**: Minor

---

## Integration Gaps

### II1: manage.py imports from tools.recall using bare name

- **Interface**: `manage.py` → `recall.py` for `_DEFAULT_DB_PATH` and `_DEFAULT_MANIFEST_PATH`
- **Current state**: `src/cyberbrain/mcp/tools/manage.py` lines 12 and 516: `from tools.recall import _DEFAULT_DB_PATH`
- **Gap**: In a packaged install, `tools` is not a top-level package. This raises `ModuleNotFoundError`. `cb_configure` and `cb_status` will crash on server startup.
- **Severity**: Critical

### II2: _EXTRACTOR_DIR in shared.py may be dead code post-restructure

- **Interface**: `shared.py` → extractor layer path resolution
- **Current state**: `shared.py` constructs `_EXTRACTOR_DIR` but actual extractor imports use `cyberbrain.*` module names directly.
- **Gap**: `_EXTRACTOR_DIR` variable may be unused. Should be verified and removed if dead.
- **Severity**: Minor

---

## Infrastructure Gaps

### MI1: No cyberbrain-extract entry point defined

- **Category**: Configuration
- **Gap**: The WI-034 implementation notes reference `cyberbrain-extract --transcript "$TRANSCRIPT" ...` as a hook invocation pattern. `pyproject.toml` defines only `cyberbrain-mcp`. No `cyberbrain-extract` script is defined. Hooks cannot use this entry point.
- **Severity**: Significant

### MI2: No pytest configuration for src layout

- **Category**: Configuration
- **Gap**: No `[tool.pytest.ini_options]` in `pyproject.toml` sets `pythonpath = ["src"]`. Without this or `pip install -e .`, `pytest` cannot resolve the `cyberbrain` package. This is not documented anywhere.
- **Severity**: Significant

---

## Out of Scope

- **Behavior changes**: WI-034 is a structural rename only. No changes to extraction logic, tool behavior, or configuration schema are expected.
- **`install.sh` update for src layout paths**: Updating `install.sh` to copy from `src/cyberbrain/` is a distribution concern beyond WI-034's stated scope. Worth flagging as a follow-on task.
- **WI-034 spec typo** (`src/cybrain/` vs `src/cyberbrain/`): The work item text consistently spells the directory `cybrain` (missing the `e`). The actual implementation correctly uses `cyberbrain`. Documentation-only error in the spec; no runtime impact.

---

## Critical Findings

None.

---

## Significant Findings

None.

---

## Minor Findings

### M1: WI-030 manual test pending execution

The re-test procedure for manual capture mode (WI-020 test D2) is documented but not executed. This requires a live Claude Desktop session and cannot be automated.

**Impact**: The WI-023 wording fix (emphatic prohibitions in manual mode guide) has not been empirically validated.

**Resolution**: User must execute the procedure manually before the feature can be considered verified.

### M2: `.obsidian/` marker directories present (resolved in prior cycle)

The gap from cycle 3 (missing `.obsidian/` directories in test vaults) was resolved in the post-review fixes. All 5 vault variants now have `.obsidian/.gitkeep`. No new gaps introduced.

---

## Unmet Acceptance Criteria

### WI-030: Test executed against current implementation

- **Criterion**: "Test executed against current implementation"
- **Status**: Cannot be executed in automated environment
- **Reason**: Requires live Claude Desktop session
- **Resolution**: Documented procedure at `specs/steering/research/manual-capture-retest.md` awaiting manual execution

---

## Missing Requirements Analysis

### Interview requirements coverage

The original interview (cycle 1) identified these focus areas:

1. **Vault curation quality** — Active workstream through WI-004, WI-010, WI-011, now complete with quality gates
2. **RAG/retrieval improvements** — WI-012 completed (synthesis and context injection); graph expansion deferred pending retrieval validation
3. **Evaluation tooling** — WI-001 completed (evaluation framework exists as dev tooling)
4. **Automatic invocation** — WI-002 (test plan) and WI-020 (execution) completed; identified issues addressed in WI-021 through WI-024

No requirements from the original interview have been dropped or forgotten.

### Cycle 4-5 scope coverage

Cycle 4 (WI-027–030) addressed capstone review findings from cycle 3. All findings were resolved:
- Dead code removed
- Gate hint wording standardized
- Setup predicate guidance fixed
- Manual capture mode re-test documented

Cycle 5 (WI-031–033) addresses plugin distribution:
- WI-031 (plugin system research): Complete
- WI-032 (distribution patterns research): Complete
- WI-033 (implementation): Not yet started

---

## Integration Gaps

### WI-033 prerequisites are complete

Both research tasks (WI-031, WI-032) provide all information needed to implement WI-033:

- What the plugin system can and cannot handle
- How to structure `.claude-plugin/plugin.json`, `hooks/hooks.json`, and `.mcp.json`
- The path resolution fix required in `mcp/shared.py`
- The hook script changes to use `${CLAUDE_PLUGIN_ROOT}`
- What install.sh responsibilities remain (config init, migration, Claude Desktop registration)

No additional research or prerequisites are blocking WI-033.

---

## Deferred Work

### Graph expansion (from cycle 1)

Still deferred per WI-003 recommendation. The rationale (wait until search improvements are validated) remains sound. No new information suggests revisiting this decision.

### Invocation hardening (WI-006)

Still deferred per cycle 1 interview. WI-002 test plan was executed; identified issues were addressed in cycles 2-3. WI-006 could be revived if additional invocation issues surface.

---

## Findings Requiring User Input

None. All work items are self-contained and complete. WI-030 requires user action to execute the manual test, but no decisions are pending.