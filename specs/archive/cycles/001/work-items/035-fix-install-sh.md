# WI-035: Fix install.sh for src layout

## Objective

Update `install.sh` to use the correct post-WI-034 source paths under `src/cyberbrain/`. The script currently references directories that were deleted during the src layout migration, blocking manual installation.

## Acceptance Criteria

- [ ] `bash install.sh` completes without errors on a clean clone
- [ ] All `cp` commands reference files under `src/cyberbrain/` (not bare `extractors/`, `mcp/`, or `prompts/`)
- [ ] Python dependency installation uses `pip install -e .` (or `uv sync`) from `pyproject.toml`, not `pip install -r requirements.txt`
- [ ] The installed hook (`hooks/pre-compact-extract.sh`) invokes `cyberbrain-extract` entry point (not `python3 extractors/extract_beats.py`)
- [ ] `bash install.sh --dry-run` or equivalent still works if it existed before

## File Scope

- `modify`: `install.sh`

## Dependencies

None.

## Implementation Notes

The src layout migration (WI-034) moved:
- `extractors/` → `src/cyberbrain/extractors/`
- `mcp/` → `src/cyberbrain/mcp/`
- `prompts/` → `src/cyberbrain/prompts/`

`install.sh` likely copies these files or directories to `~/.claude/cyberbrain/`. All such copy operations must be updated to reference the new paths.

The entry point `cyberbrain-extract` is defined in `pyproject.toml` and resolves to `cyberbrain.extractors.extract_beats:main`. The hook script should invoke this entry point after install rather than calling the Python file directly.

If `requirements.txt` still exists, it should not be used; all dependencies are in `pyproject.toml`.
