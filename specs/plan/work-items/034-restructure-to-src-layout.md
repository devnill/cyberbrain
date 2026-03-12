# WI-034: Restructure to src layout with cyberbrain namespace

## Objective

Fix the critical namespace collision with PyPI's `mcp` package by restructuring the project to use a src layout with a `cyberbrain` namespace package.

## Dependencies

None — this is a standalone restructuring task.

## Scope

### Files to move

- `mcp/` → `src/cybrain/mcp/`
- `extractors/` → `src/cybrain/extractors/`
- `prompts/` → `src/cybrain/prompts/` (data files, not a package)

### Files to modify

- `pyproject.toml` — update packages directive, add entry points, configure src layout
- `.mcp.json` — update command to use new module path
- `hooks/pre-compact-extract.sh` — update to call entry point
- `hooks/session-end-extract.sh` — update to call entry point (if it exists)
- `CLAUDE.md` — update architecture documentation

### Files to create

- `src/cybrain/__init__.py`
- `src/cybrain/mcp/__init__.py`
- `src/cybrain/extractors/__init__.py`

### Files to update (import paths)

All Python files in `src/cybrain/` that use imports:
- `from tools import ...` → `from cyberbrain.mcp.tools import ...`
- `from shared import ...` → `from cyberbrain.mcp.shared import ...`
- `from extract_beats import ...` → `from cyberbrain.extractors.extract_beats import ...`
- etc.

### Test files to update

All test files that import from `mcp/` or `extractors/`:
- Update imports to use `cyberbrain.*` namespace
- Remove `sys.path` manipulation code that adds `mcp/` and `extractors/` directories

## Acceptance Criteria

- [ ] `src/cybrain/` directory exists with `__init__.py` making it a proper package
- [ ] `src/cybrain/mcp/__init__.py` exists
- [ ] `src/cybrain/extractors/__init__.py` exists
- [ ] `pyproject.toml` updated for src layout with correct entry points
- [ ] Entry point `cyberbrain-mcp = "cyberbrain.mcp.server:main"` works
- [ ] Entry point for extract script (if needed) works
- [ ] `.mcp.json` uses `python -m cyberbrain.mcp.server`
- [ ] All imports use `cyberbrain.*` namespace
- [ ] `sys.path` manipulation removed from `server.py`, `shared.py`, and test files
- [ ] `python3 -m pytest tests/` passes
- [ ] `uvx cyberbrain-mcp` or `uv tool install` works (verified manually)
- [ ] Hooks call entry points instead of file paths

## Implementation Notes

### pyproject.toml changes

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["cyberbrain"]
# src layout configuration
```

Hatchling automatically detects src layout when packages are under `src/`.

### Entry points

```toml
[project.scripts]
cyberbrain-mcp = "cyberbrain.mcp.server:main"
# Consider adding extract script if hooks need it
```

### Hook changes

The hooks currently call Python scripts directly. After this change, they should use the installed entry point:

```bash
# Before (in hook):
# python "$SCRIPT_DIR/../extractors/extract_beats.py" ...

# After:
# cyberbrain-extract --transcript "$TRANSCRIPT" ...
# OR
# python -m cyberbrain.extractors.extract_beats --transcript "$TRANSCRIPT" ...
```

The `--directory` flag in `.mcp.json` already handles the source directory case via `uv run --directory`.

### Import migration

All internal imports change:

```python
# Old (in mcp/server.py):
from tools import extract, file, recall, ...
from shared import _load_config, ...

# New:
from cyberbrain.mcp.tools import extract, file, recall, ...
from cyberbrain.mcp.shared import _load_config, ...
```

```python
# Old (in mcp/shared.py):
from extract_beats import ...
from frontmatter import ...

# New:
from cyberbrain.extractors.extract_beats import ...
from cyberbrain.extractors.frontmatter import ...
```

### Test imports

Test files currently manipulate `sys.path`:

```python
# Old pattern (remove):
MCP_DIR = Path(__file__).parent.parent / "mcp"
EXTRACTORS_DIR = Path(__file__).parent.parent / "extractors"
for d in [str(MCP_DIR), str(EXTRACTORS_DIR)]:
    if d not in sys.path:
        sys.path.insert(0, d)
```

With src layout and proper packages, tests can import directly:

```python
# New pattern:
from cyberbrain.mcp.tools import manage
from cyberbrain.extractors.extract_beats import extract_beats
```

Tests may need `pip install -e .` or `uv pip install -e .` to run against the installed package.

### Path resolution in shared.py

The `_PROMPTS_DIR` and `_EXTRACTOR_DIR` resolution currently uses `__file__`-relative paths. After restructuring:

```python
# Old:
_PROMPTS_DIR_PRIMARY = Path(__file__).parent.parent / "prompts"

# New (still works, just different path):
_PROMPTS_DIR_PRIMARY = Path(__file__).parent.parent / "prompts"
# __file__ is now src/cybrain/mcp/shared.py
# parent.parent is src/cybrain/
# prompts is src/cybrain/prompts/
```

The `${CLAUDE_PLUGIN_ROOT}` fallback in `shared.py` should still work — it resolves at runtime.

### Risks

1. **Breaking imports in installed plugin:** The `sys.path` manipulation was a workaround. Removing it requires that all imports be package-qualified.

2. **Test discovery:** Tests may need `pip install -e .` or explicit `PYTHONPATH=src` to find the package.

3. **Hook execution:** Hooks that call Python scripts need to use entry points or `python -m` invocations.

## Estimated Complexity

Medium — straightforward but touches many files. The changes are mechanical but require careful attention to import paths.