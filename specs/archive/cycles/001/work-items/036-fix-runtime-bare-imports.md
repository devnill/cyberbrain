# WI-036: Fix runtime bare imports

## Objective

Fix bare (non-package-qualified) imports in three source files that cause `ImportError` at runtime when cyberbrain is installed as a package. In a packaged install, Python resolves imports relative to the installed package namespace — bare module names like `search_index`, `frontmatter`, and `config` do not resolve.

## Acceptance Criteria

- [ ] `vault.py` has no bare `from search_index import ...` — replaced with `from cyberbrain.mcp.search_index import ...` (or equivalent package-qualified path)
- [ ] `search_backends.py` has no bare `from frontmatter import ...` — replaced with `from cyberbrain.mcp.frontmatter import ...` (or equivalent)
- [ ] `search_backends.py` has no `try/except ImportError` fallback wrapping the bare import — the fallback is removed entirely since the package-qualified import is always correct
- [ ] `evaluate.py` has no bare `from config import ...` — replaced with `from cyberbrain.extractors.config import ...` (or equivalent)
- [ ] `uv run pytest tests/` passes with 0 failures after fixes

## File Scope

- `modify`: `src/cyberbrain/extractors/vault.py`
- `modify`: `src/cyberbrain/mcp/search_backends.py`
- `modify`: `src/cyberbrain/extractors/evaluate.py`

## Dependencies

None.

## Implementation Notes

The `try/except ImportError` fallback in `search_backends.py` was originally a compatibility shim for running the file as a script vs. as a package. In the src layout, this shim is always wrong: the bare import always fails (correct behavior), but the except branch's fallback may also fail or import the wrong thing. Remove the entire `try/except` block and use only the package-qualified import.

Verify the exact import names by reading each file before modifying. The module names in the package-qualified path must match the actual filenames under `src/cyberbrain/`.
