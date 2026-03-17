# Gap Analysis — Cycle 002

## Scope

This analysis covers WI-034 (Restructure to src layout with cyberbrain namespace). The cycle-001 gap analysis identified 7 open questions in `specs/domains/distribution/questions.md`. This review verifies their resolution status and identifies any new gaps introduced by the restructure.

## Open Question Resolution Status

All 7 open questions from cycle-001 are resolved in the implementation:

| Question | Status | Evidence |
|----------|--------|----------|
| Q-1: pyproject.toml packages directive | Resolved | `packages = ["src/cyberbrain"]`; both entry points defined |
| Q-2: .mcp.json module path | Resolved | `.mcp.json` uses `python -m cyberbrain.mcp.server` |
| Q-3: Hook scripts reference deleted path | Resolved | Hooks use `python -m cyberbrain.extractors.extract_beats` with `${CLAUDE_PLUGIN_ROOT}` |
| Q-4: Extractor bare imports | Resolved | All extractor files use `cyberbrain.*` namespace |
| Q-5: Test suite collection failures | Resolved | `pythonpath = ["src"]` in pyproject.toml; all imports use `cyberbrain.*` |
| Q-6: cyberbrain-extract entry point missing | Resolved | `cyberbrain-extract = "cyberbrain.extractors.extract_beats:main"` defined |
| Q-7: import.py legacy path | Resolved | `_import_extract_beats()` uses `cyberbrain.extractors.extract_beats` directly |

---

## Missing Requirements from Interview

None.

The interview transcript is not present at `specs/steering/interview.md`. All interview requirements were confirmed covered in cycle-001. No requirements from the original interview scope were lost in WI-034.

---

## Unhandled Edge Cases

### EC1: evaluate.py CLI main() uses bare unqualified import
- **Component**: `src/cyberbrain/extractors/evaluate.py`
- **Scenario**: User runs `python -m cyberbrain.extractors.evaluate` in a packaged install (via `uvx` or `pip install`).
- **Current behavior**: Line 407 inside `main()` executes `from config import resolve_config`. In a packaged install, no top-level `config` module exists. This raises `ModuleNotFoundError` at runtime when the CLI is used, not at import time — so the failure is invisible until the tool is actually invoked.
- **Expected behavior**: Should use `from cyberbrain.extractors.config import resolve_config`.
- **Severity**: Minor
- **Recommendation**: Address now — `evaluate.py` is an installed dev tool. The fix is one line. Deferring means any developer who runs the evaluate tool from a clean install hits an immediate crash.

### EC2: search_backends.py try/except bare imports always fall through in packaged install
- **Component**: `src/cyberbrain/extractors/search_backends.py`
- **Scenario**: Running in any packaged install (via `uvx` or `pip install`).
- **Current behavior**: Lines 783-786 attempt `from frontmatter import read_frontmatter`, `from frontmatter import normalise_list`, `from frontmatter import derive_id`. In a packaged install, there is no top-level `frontmatter` module. The `except ImportError` branch always executes, silently providing duplicate fallback implementations written for the legacy `sys.path` flat-directory install model.
- **Expected behavior**: The try block should use `from cyberbrain.extractors.frontmatter import ...` so the canonical implementations are always used. The fallback was only needed when files were copied flat to `~/.claude/cyberbrain/extractors/` without a package structure.
- **Severity**: Minor
- **Recommendation**: Address now — the fallback implementations can diverge from `frontmatter.py` without any enforcement. The try block target is wrong for the current package layout. The fallback can be removed entirely since `cyberbrain.extractors.frontmatter` is always present in a proper install.

---

## Incomplete Integrations

### II1: install.sh copies from deleted source paths
- **Interface**: Manual installation path for Claude Desktop users
- **Producer**: `install.sh`
- **Consumer**: `~/.claude/cyberbrain/extractors/`, `~/.claude/cyberbrain/prompts/`, `~/.claude/cyberbrain/mcp/`
- **Gap**: `install.sh` copies from `$REPO_DIR/extractors/` (line 75), `$REPO_DIR/prompts/` (line 103), and `$REPO_DIR/mcp/` (line 143). All three source directories were deleted by WI-034; the files now live at `src/cyberbrain/extractors/`, `src/cyberbrain/prompts/`, and `src/cyberbrain/mcp/`. The script uses `set -euo pipefail` and aborts at the first missing file. No files are installed. Claude Desktop users on a fresh clone are completely blocked.
- **Severity**: Critical
- **Recommendation**: Address now — this is the only installation path for Claude Desktop users. All `cp` source paths must be updated to the new `src/cyberbrain/` locations. The `pip install -r requirements.txt` dependency install (line 270) should also be replaced with a `pyproject.toml`-based install.

---

## Missing Infrastructure

### MI1: requirements.txt files inside src/cyberbrain are orphaned dependency specs
- **Category**: Configuration
- **Gap**: `src/cyberbrain/extractors/requirements.txt` and `src/cyberbrain/mcp/requirements.txt` were moved into `src/cyberbrain/` by WI-034 but are now superseded by `pyproject.toml`. They specify an incomplete subset of the actual dependencies. `install.sh` (line 270) references `$CB_DIR/extractors/requirements.txt` for the bedrock install path. After II1 is fixed, this will install `pyyaml` and `anthropic` but miss `fastmcp`, `mcp`, and `ruamel.yaml`.
- **Impact**: Any installation following the `requirements.txt` path will be under-specified. After II1 is fixed, the bedrock dependency install path silently misses required runtime dependencies.
- **Severity**: Significant
- **Recommendation**: Address now, as part of the same work item that fixes II1 — replace the `pip install -r` call with `pip install -e .` (or `pip install cyberbrain-mcp[bedrock]` for release installs) and either delete the `requirements.txt` files or mark them as legacy.

### MI2: Dead EXTRACTORS_DIR constant in scripts/import.py
- **Category**: Configuration
- **Gap**: `scripts/import.py` line 33 defines `EXTRACTORS_DIR = Path.home() / ".claude" / "cyberbrain" / "extractors"`. This constant is never referenced anywhere in the file. The import function now uses `cyberbrain.extractors.extract_beats` directly. The constant and the module docstring's reference to "The extractor lives at `~/.claude/cyberbrain/extractors/extract_beats.py`" are both stale.
- **Impact**: Misleads readers into thinking the module depends on a path it does not use, and points to a path that does not exist in fresh plugin installs.
- **Severity**: Minor
- **Recommendation**: Address now — a one-line deletion plus one docstring update. No behavioral change.

### MI3: Stale "sys.path setup" comment headers in test files
- **Category**: Documentation
- **Gap**: Ten test files contain section headers labeled `# sys.path setup` or `# sys.path setup + mock extract_beats BEFORE any shared/tools imports`. In every case, no `sys.path` manipulation occurs beneath these headers — the code performs `sys.modules.pop()` and `cyberbrain.*` imports. The headers are stale artifacts from before WI-034.
- **Impact**: Misleads contributors reviewing the test code.
- **Severity**: Minor
- **Recommendation**: Defer — tests are functional. Rename the headers (e.g. "# Mock setup before imports") as a batch with other comment cleanup.

---

## Implicit Requirements

### IR1: Claude Desktop installation path must function after WI-034
- **Expectation**: A user following the documented `bash install.sh` installation path can successfully install cyberbrain from a clean checkout.
- **Current state**: Unmet. `install.sh` copies from `$REPO_DIR/extractors/`, `$REPO_DIR/prompts/`, and `$REPO_DIR/mcp/` which no longer exist after WI-034. With `set -euo pipefail`, the script aborts at the first `cp` failure. No files are installed.
- **Gap**: `install.sh` was not updated when WI-034 relocated the source files to `src/cyberbrain/`. This is the same root cause as II1 and MI1; all three should be fixed together.
- **Severity**: Critical
- **Recommendation**: Address now — the complete fix: update `cp` source paths to `src/cyberbrain/` locations; replace `pip install -r requirements.txt` with a pyproject.toml-based install; remove or mark the stale `requirements.txt` files.

### IR2: Domain questions file must reflect resolution status after WI-034
- **Expectation**: `specs/domains/distribution/questions.md` tracks distribution blocker status. After WI-034 resolves the open questions, the file should reflect that.
- **Current state**: All 7 questions (Q-1 through Q-7) are marked `status: open`. All 7 are resolved in the implementation.
- **Gap**: The questions file was not updated to record resolutions. It is the authoritative tracking document for what remains to be done in distribution.
- **Severity**: Minor
- **Recommendation**: Address now — update each question's `status` field to `resolved` with a brief reference to WI-034. This prevents the next planning cycle from re-investigating already-solved problems.
