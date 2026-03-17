# Code Quality Review — Cycle 002

## Verdict: Fail

The src layout migration (WI-034) is incomplete. Multiple test files contain bare `from search_backends import` and `patch("search_backends...")` calls not updated to use the `cyberbrain.extractors.` namespace. `install.sh` copies from source directories that no longer exist at the repo root, making manual installation completely broken. `src/cyberbrain/extractors/search_backends.py` uses a bare `from frontmatter import` that always falls through to a fallback implementation in the src layout, silently bypassing the canonical module.

---

## Critical Findings

### C1: install.sh copies from non-existent source directories
- **File**: `install.sh:75–144`
- **Issue**: `install.sh` copies files from `$REPO_DIR/extractors/`, `$REPO_DIR/mcp/`, and `$REPO_DIR/prompts/`. After WI-034, none of these directories exist at the repo root — they are now at `src/cyberbrain/extractors/`, `src/cyberbrain/mcp/`, and `src/cyberbrain/prompts/`. Every `cp` command in the file installation section (lines 75–145) fails with a path-not-found error. Running `bash install.sh` installs nothing.
- **Impact**: Manual installation (for Claude Desktop users) is completely broken. `set -euo pipefail` exits on the first failed `cp`, leaving the target directory empty.
- **Suggested fix**: Update all source paths to reference `$REPO_DIR/src/cyberbrain/`.

### C2: Multiple test files contain bare module imports not updated to cyberbrain.* namespace
- **Files**: `tests/test_search_backends.py` (30+ occurrences), `tests/test_search_index.py` (lines 53, 68, 77), `tests/test_mcp_server.py`, `tests/test_recall_read_tools.py`
- **Issue**: These test files use bare imports inside test methods: `from search_backends import HybridBackend`, `from search_backends import SearchResult`, `from search_backends import get_search_backend, FTS5Backend`, and bare patch targets `patch("search_backends.get_search_backend", ...)`. In the src layout there is no top-level `search_backends` module. These fail at runtime with `ModuleNotFoundError: No module named 'search_backends'`. The incremental WI-034 review missed this class of bare imports inside test method bodies.
- **Impact**: Tests pass collection but fail at runtime. The WI-034 acceptance criterion `python3 -m pytest tests/` passes is not met.
- **Suggested fix**: Replace all `from search_backends import X` with `from cyberbrain.extractors.search_backends import X`. Replace `patch("search_backends.X", ...)` with `patch("cyberbrain.extractors.search_backends.X", ...)`.

---

## Significant Findings

### S1: search_backends.py bare `from frontmatter import` always falls through to fallback
- **File**: `src/cyberbrain/extractors/search_backends.py:783–824`
- **Issue**: Lines 783–786 attempt `from frontmatter import read_frontmatter as _read_frontmatter` with a bare module name. In the src layout, `frontmatter` is not a top-level module — it is `cyberbrain.extractors.frontmatter`. This import always raises `ImportError`. The except block (lines 787–824) always executes, defining inline fallback implementations. The canonical `frontmatter.py` is never used by `search_backends.py`.
- **Impact**: The canonical module is silently bypassed. Any future changes to `frontmatter.py` will not affect search indexing behavior. The WI-034 criterion "all imports use `cyberbrain.*` namespace" is not met here.
- **Suggested fix**: Replace the try/except block with direct `from cyberbrain.extractors.frontmatter import read_frontmatter as _read_frontmatter` (and normalise_list, derive_id). Remove the fallback function definitions.

---

## Minor Findings

### M1: Stale EXTRACTORS_DIR constant in scripts/import.py
- **File**: `scripts/import.py:33`
- **Issue**: `EXTRACTORS_DIR = Path.home() / ".claude" / "cyberbrain" / "extractors"` is defined but never referenced. Dead constant from the pre-src-layout era.
- **Suggested fix**: Remove line 33.

### M2: Stale `# sys.path setup` comment blocks in test files
- **Files**: Multiple test files
- **Issue**: Section header comments reading `# sys.path setup` remain but no `sys.path` manipulation follows. Leftover stubs from the pre-src-layout era.

### M3: Legacy requirements.txt files inside src/cyberbrain/
- **Files**: `src/cyberbrain/extractors/requirements.txt`, `src/cyberbrain/mcp/requirements.txt`
- **Issue**: Superseded by `pyproject.toml`. Will be included in any built wheel, creating confusion.

### M4: Stale docstring in scripts/import.py
- **File**: `scripts/import.py:17`
- **Issue**: Still references the old `~/.claude/cyberbrain/extractors/extract_beats.py` install path.

---

## Unmet Acceptance Criteria

From WI-034:

- [ ] `python3 -m pytest tests/` passes — **Not met.** Multiple tests fail with `ModuleNotFoundError: No module named 'search_backends'`.
- [ ] All imports use `cyberbrain.*` namespace — **Not met.** `search_backends.py` lines 783–786 use bare `from frontmatter import`. Multiple test files use bare `search_backends` imports inside test method bodies.
