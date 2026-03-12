# Code Quality Review — Cycle 6 (WI-034: Restructure to src layout)

## Verdict: Fail

The src layout migration is structurally correct but incomplete: three blocking defects prevent the package from working — the `pyproject.toml` `packages` directive still points at the deleted directories, `.mcp.json` still invokes the old module path, and every test file still manipulates `sys.path` to point at the deleted directory tree, causing 18 of 20 test modules to fail at collection.

---

## Critical Findings

### C1: pyproject.toml packages directive points at deleted directories

- **File**: `/Users/dan/code/cyberbrain/pyproject.toml:43`
- **Issue**: `packages = ["mcp", "extractors", "prompts"]` lists the old flat directories that were deleted by WI-034. The actual source code now lives under `src/cyberbrain/`. Hatchling will not find these packages and will build an empty wheel.
- **Impact**: `pip install .`, `uv sync`, and `uvx cyberbrain-mcp` all silently install a wheel that contains no Python code. The entry point `cyberbrain-mcp = "cyberbrain.mcp.server:main"` will fail at runtime with `ModuleNotFoundError: No module named 'cyberbrain'`.
- **Suggested fix**: Replace the `packages` directive with the src layout configuration Hatchling uses for `src/` directories:
  ```toml
  [tool.hatch.build.targets.wheel]
  packages = ["src/cyberbrain"]
  ```
  Hatchling will then install `cyberbrain/` (with all sub-packages) into site-packages, and the entry point will resolve correctly.

### C2: .mcp.json still uses the old module path

- **File**: `/Users/dan/code/cyberbrain/.mcp.json:8`
- **Issue**: The MCP server launch command is `python -m mcp.server`. After WI-034 the server module moved to `cyberbrain.mcp.server`. The old path `mcp.server` resolves to the PyPI `mcp` package's `mcp/server/` module, which has no `main()` function.
- **Impact**: Every plugin installation launches the wrong process. The MCP server will fail to start — Claude Code plugin users get no MCP tools.
- **Suggested fix**: Change `.mcp.json` to:
  ```json
  "args": ["run", "--directory", "${CLAUDE_PLUGIN_ROOT}", "python", "-m", "cyberbrain.mcp.server"]
  ```

### C3: All test files fail to import — 18 of 20 test modules error at collection

- **File**: Multiple test files; representative examples at `tests/conftest.py:22-29`, `tests/test_mcp_server.py:39-44`, `tests/test_extract_beats.py:24-26`, `tests/conftest.py:56-76`
- **Issue**: Every test file still adds the old flat directory paths (`REPO_ROOT/extractors`, `REPO_ROOT/mcp`) to `sys.path` and imports modules by their bare pre-migration names (`import autofile`, `import search_backends`, `from mcp.server import ...`, `import shared`, etc.). These directories were deleted by WI-034. Running `python3 -m pytest tests/` produces 18 collection errors with `ModuleNotFoundError`.
  
  Additional problems in `conftest.py`:
  - Line 22: `EXTRACTORS_DIR = REPO_ROOT / "extractors"` — this directory no longer exists.
  - Line 56-76: Mocks `sys.modules["extract_beats"]` by bare name. After migration, `shared.py` imports via `from cyberbrain.extractors.extract_beats import ...`, so the mock key would need to be `cyberbrain.extractors.extract_beats`.
  - Line 220: `from search_backends import SearchResult` — bare import fails since `extractors/` is not on `sys.path`.

  `tests/test_extract_beats.py` line 26: `import extractors.extract_beats as eb` — this worked when the repo root was on `sys.path` and `extractors/` was a directory, but `extractors/` no longer exists at repo root.

  `tests/test_manage_tool.py` line 12 (import): `import shared as _shared` — bare name import requires `mcp/` on `sys.path`.

  `tests/test_setup_enrich_tools.py` line 85: `import shared as _shared`.

  `tests/test_mcp_server.py` line 144: `from mcp.server.fastmcp.exceptions import ToolError` — `mcp.server` here may resolve to the PyPI package, not cyberbrain's server.

- **Impact**: The acceptance criterion "`python3 -m pytest tests/` passes" is not met. 18 of 20 modules cannot even be collected.
- **Suggested fix**: All test files must be updated to use `cyberbrain.*` imports and remove `sys.path` manipulation. The conftest mock must use the fully-qualified module key `cyberbrain.extractors.extract_beats`. Tests should run against the installed package via `pip install -e .` (already documented in WI-034 implementation notes). A `pytest.ini` or `pyproject.toml` `[tool.pytest.ini_options]` setting of `pythonpath = ["src"]` would let tests import `cyberbrain.*` without requiring an editable install.

---

## Significant Findings

### S1: Bare unqualified import in setup.py survives migration

- **File**: `/Users/dan/code/cyberbrain/src/cyberbrain/mcp/tools/setup.py:18`
- **Issue**: `from analyze_vault import analyze_vault` is an unqualified import. This works only if the `extractors/` directory is on `sys.path`. After migration, the correct import is `from cyberbrain.extractors.analyze_vault import analyze_vault`.
- **Impact**: `cb_setup` will raise `ModuleNotFoundError: No module named 'analyze_vault'` when called in a properly installed environment where `sys.path` does not include the bare extractors directory.
- **Suggested fix**: Change to `from cyberbrain.extractors.analyze_vault import analyze_vault`.

### S2: manage.py imports tools.recall by unqualified relative path

- **File**: `/Users/dan/code/cyberbrain/src/cyberbrain/mcp/tools/manage.py:12`
- **Issue**: `from tools.recall import _DEFAULT_DB_PATH, _DEFAULT_MANIFEST_PATH` is a partially-qualified import. This works only if the parent of `tools/` (i.e., `mcp/`) is on `sys.path`. After migration the correct import is `from cyberbrain.mcp.tools.recall import _DEFAULT_DB_PATH, _DEFAULT_MANIFEST_PATH`.
- **Impact**: `cb_configure` and `cb_status` will raise `ModuleNotFoundError: No module named 'tools'` in a properly installed package, where the old `mcp/` directory is not on `sys.path`.
- **Suggested fix**: Change to `from cyberbrain.mcp.tools.recall import _DEFAULT_DB_PATH, _DEFAULT_MANIFEST_PATH`.

### S3: extract_beats.py retains sys.path manipulation that defeats the migration

- **File**: `/Users/dan/code/cyberbrain/src/cyberbrain/extractors/extract_beats.py:26-28`
- **Issue**: Lines 26-28 add `Path(__file__).parent` (i.e., `src/cyberbrain/extractors/`) to `sys.path`. All internal imports in `extract_beats.py` and all other extractor files still use bare unqualified names (`from config import ...`, `from backends import ...`, `from vault import ...`, etc.). This works at runtime when the file is run as a script or imported as a module — because `sys.path` manipulation puts the extractors directory in scope — but it bypasses the `cyberbrain.*` namespace entirely and would not work if the `sys.path` hack were removed.
- **Impact**: The architecture goal of "all imports use `cyberbrain.*` namespace" is not met for the entire extractor layer. The 14 extractor Python files all import each other by bare names (`from config import`, `from backends import`, `from vault import`, `from frontmatter import`, etc.), making them dependent on the `sys.path` hack to function.
- **Suggested fix**: All intra-extractor imports must be changed to `from cyberbrain.extractors.X import Y`. The `sys.path` manipulation block in `extract_beats.py` must be removed. This is the bulk of the work in WI-034 that was not completed.

### S4: Hooks still look for the extractor at the old path

- **File**: `/Users/dan/code/cyberbrain/hooks/pre-compact-extract.sh:29-33`, `/Users/dan/code/cyberbrain/hooks/session-end-extract.sh:45-49`
- **Issue**: Both hooks check `$CLAUDE_PLUGIN_ROOT/extractors/extract_beats.py` (old flat path) and fall back to `$HOME/.claude/cyberbrain/extractors/extract_beats.py`. After WI-034 the extractor lives at `$CLAUDE_PLUGIN_ROOT/src/cyberbrain/extractors/extract_beats.py`. Neither path in the hook matches the post-migration location.
- **Impact**: In plugin mode, `EXTRACTOR` is set to `$CLAUDE_PLUGIN_ROOT/extractors/extract_beats.py` which does not exist. The hook then falls through to `$HOME/.claude/cyberbrain/extractors/extract_beats.py` (legacy installed location). On a fresh plugin install with no legacy install, the `[ ! -f "$EXTRACTOR" ]` check on line 35/51 triggers and the hook exits without extracting. Automatic knowledge capture is silently broken for plugin users.
- **Suggested fix**: The hooks should call the entry point `cyberbrain-extract` (if added to `[project.scripts]`) or use `python -m cyberbrain.extractors.extract_beats`. The path check should be changed to `$CLAUDE_PLUGIN_ROOT/src/cyberbrain/extractors/extract_beats.py` at minimum.

---

## Minor Findings

### M1: _EXTRACTOR_DIR computed in shared.py but never used

- **File**: `/Users/dan/code/cyberbrain/src/cyberbrain/mcp/shared.py:15-23`
- **Issue**: `_EXTRACTOR_DIR` is computed (with fallback logic) but is never referenced anywhere in the file. The actual extractor imports happen via `from cyberbrain.extractors.extract_beats import ...` at lines 30-44, which does not use this variable.
- **Suggested fix**: Remove the dead `_PLUGIN_ROOT`, `_EXTRACTOR_DIR_PLUGIN`, `_EXTRACTOR_DIR_LEGACY`, and `_EXTRACTOR_DIR` variable declarations.

### M2: Architecture documentation still references old paths

- **File**: `/Users/dan/code/cyberbrain/specs/plan/architecture.md:495-554` (Distribution section)
- **Issue**: The Distribution section contains two copies and still references `python -m mcp.server` as the launch command and `mcp/shared.py` as the path resolver — both reflecting the pre-migration layout.
- **Suggested fix**: Update to reflect `python -m cyberbrain.mcp.server` and `src/cyberbrain/mcp/shared.py`.

### M3: WI-034 spec has a typo in the directory name

- **File**: `/Users/dan/code/cyberbrain/specs/plan/work-items/034-restructure-to-src-layout.md:29-31`
- **Issue**: The spec says `src/cybrain/__init__.py` (missing the 'e' in 'cyberbrain') for the acceptance criteria, but the actual implementation correctly uses `src/cyberbrain/`. This is a documentation issue.
- **Suggested fix**: Correct the spec to `src/cyberbrain/__init__.py`.

---

## Unmet Acceptance Criteria

- [ ] `pyproject.toml` updated for src layout with correct entry points — **Not met**: `packages = ["mcp", "extractors", "prompts"]` still references deleted directories; must be `packages = ["src/cyberbrain"]`.
- [ ] `.mcp.json` uses `python -m cyberbrain.mcp.server` — **Not met**: still uses `python -m mcp.server`.
- [ ] All imports use `cyberbrain.*` namespace — **Not met**: all 14 extractor files use bare unqualified imports; `setup.py` uses `from analyze_vault import`; `manage.py` uses `from tools.recall import`.
- [ ] `sys.path` manipulation removed from `server.py`, `shared.py`, and test files — **Not met**: `extract_beats.py` retains `sys.path` manipulation; all test files retain extensive `sys.path` manipulation adding the deleted directory paths.
- [ ] `python3 -m pytest tests/` passes — **Not met**: 18 of 20 test modules fail at collection with `ModuleNotFoundError`.
- [ ] Hooks call entry points instead of file paths — **Not met**: both hooks check the old `$CLAUDE_PLUGIN_ROOT/extractors/extract_beats.py` path.

---

## Acceptance Criteria Verification

- [x] `src/cyberbrain/` directory exists with `__init__.py` making it a proper package — present at `/Users/dan/code/cyberbrain/src/cyberbrain/__init__.py`
- [x] `src/cyberbrain/mcp/__init__.py` exists — confirmed
- [x] `src/cyberbrain/extractors/__init__.py` exists — confirmed
- [ ] `pyproject.toml` updated for src layout with correct entry points — **FAIL** (C1)
- [x] Entry point `cyberbrain-mcp = "cyberbrain.mcp.server:main"` declared in pyproject.toml — declared, but non-functional due to C1
- [ ] `.mcp.json` uses `python -m cyberbrain.mcp.server` — **FAIL** (C2)
- [ ] All imports use `cyberbrain.*` namespace — **FAIL** (S3, S1, S2)
- [ ] `sys.path` manipulation removed from `server.py`, `shared.py`, and test files — **FAIL** (S3, C3)
- [ ] `python3 -m pytest tests/` passes — **FAIL** (C3)
- [ ] `uvx cyberbrain-mcp` or `uv tool install` works — **FAIL** (C1, C2)
- [ ] Hooks call entry points instead of file paths — **FAIL** (S4)

---

## Files Modified by WI-034

Files correctly migrated (source moved to new location, package `__init__.py` files created):
- `src/cyberbrain/__init__.py` — created
- `src/cyberbrain/mcp/__init__.py` — created
- `src/cyberbrain/extractors/__init__.py` — created
- `src/cyberbrain/mcp/server.py` — imports updated to `cyberbrain.*`
- `src/cyberbrain/mcp/shared.py` — imports updated to `cyberbrain.*`
- `src/cyberbrain/mcp/resources.py` — imports updated
- `src/cyberbrain/mcp/tools/extract.py` — imports updated
- `src/cyberbrain/mcp/tools/file.py` — imports updated
- `src/cyberbrain/mcp/tools/recall.py` — imports updated
- `src/cyberbrain/mcp/tools/enrich.py` — imports updated
- `src/cyberbrain/mcp/tools/restructure.py` — imports updated
- `src/cyberbrain/mcp/tools/review.py` — imports updated
- `src/cyberbrain/mcp/tools/reindex.py` — imports updated
- `src/cyberbrain/mcp/tools/setup.py` — partially updated (S1)
- `src/cyberbrain/mcp/tools/manage.py` — partially updated (S2)

Files not updated (blocking defects):
- `pyproject.toml` — `packages` directive not updated (C1)
- `.mcp.json` — module path not updated (C2)
- `hooks/pre-compact-extract.sh` — extractor path not updated (S4)
- `hooks/session-end-extract.sh` — extractor path not updated (S4)
- `src/cyberbrain/extractors/*.py` (all 14 files) — still use bare unqualified imports and `sys.path` manipulation (S3)
- `tests/*.py` (all test files) — still use old `sys.path` manipulation and bare imports (C3)
