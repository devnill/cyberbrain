# Refinement Cycle 6 — Namespace Collision Fix (src Layout)

## What is Changing

Restructuring the project from flat directory layout (`mcp/`, `extractors/`, `prompts/`) to src layout with a `cyberbrain` namespace package. This fixes the critical namespace collision with PyPI's `mcp` package discovered in the cycle 5 capstone review.

Key changes:
1. **Directory structure** — Move `mcp/`, `extractors/`, `prompts/` under `src/cybrain/`
2. **Package structure** — Add `__init__.py` files to make proper packages
3. **Imports** — Convert all imports to package-qualified (`from cyberbrain.mcp.tools import ...`)
4. **Entry points** — Define console scripts in pyproject.toml
5. **Hooks** — Update to call entry points instead of file paths

## Triggering Context

Cycle 5 capstone review found critical issues (C1, C2) that block plugin distribution:
- pyproject.toml entry point `cyberbrain.mcp.server:main` references non-existent namespace
- Internal `mcp/` directory collides with PyPI `mcp` package namespace
- `uvx cyberbrain-mcp` or `pip install` would fail with import errors

The incremental review passed because acceptance criteria were met, but functional correctness testing revealed the implementation is broken at runtime.

## Scope Boundary

**In scope:** Directory restructuring, package creation, import migration, entry point configuration, hook updates, test import fixes, documentation updates.

**Not in scope:** Behavior changes, new features, architecture changes beyond the namespace fix.

## Expected Impact

- Plugin distribution via uvx/pip works correctly
- `python -m cyberbrain.mcp.server` resolves correctly
- All imports use `cyberbrain.*` namespace
- Tests pass with proper package imports
- No `sys.path` manipulation needed

## New Work Items

034 (1 item). See `plan/work-items/034-restructure-to-src-layout.md` for details.