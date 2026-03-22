# Changelog

## 1.1.0 — 2026-03-22

Architecture and code quality release. No new features or breaking changes.

### Improvements

- **restructure.py decomposed** — 2,832-line god module split into 11-file sub-package (`restructure/pipeline.py`, `collect.py`, `cluster.py`, `cache.py`, `audit.py`, `decide.py`, `generate.py`, `execute.py`, `format.py`, `utils.py`)
- **Centralized state paths** — all `~/.claude/cyberbrain/` file paths defined in `state.py` (12 constants)
- **Eliminated re-export hub** — `extract_beats.py` is now a pure CLI script; all callers use direct imports from source modules
- **Direct imports in shared.py** — MCP shared module imports from source modules, not via re-export hub
- **TypedDict config** — `CyberbrainConfig` in `config.py` defines all known config fields with types
- **Exception handlers** — ~10 narrowed to specific types, ~40 documented with `# intentional:` rationale
- **Test infrastructure** — `conftest.py` sys.modules mock injection removed; test sys.modules patterns documented and consolidated via `_clear_module_cache()` helper; `_dependency_map.py` restored with repo-root anchoring

### Tooling

- **ruff** — linter and formatter configured (`[tool.ruff]` in pyproject.toml)
- **basedpyright** — type checker configured, 0 errors in basic mode
- **pre-commit** — enforces ruff format + lint on every commit
- **Python 3.11+** — `requires-python` updated from `>=3.8` to `>=3.11`; constraint C1 updated

### Bug Fixes

- Fixed broken import in `autofile.py` (`from search_index` → `from cyberbrain.extractors.search_index`) — autofile now correctly updates the search index after creating notes
- Fixed `enrich.py` frontmatter delimiter inconsistency (`"\n---"` → `"\n---\n"`) — prevents mis-parsing notes with `--- heading` patterns in the body

### Documentation

- CLAUDE.md updated: restructure package, state.py, TypedDict config, quality tooling section
- README.md config table expanded with all config keys
- Constraint C1 updated to Python 3.11+

## 1.0.2 — 2026-03-20

- Fix hook permissions, move .mcp.json out of project root

## 1.0.1

- Fix: use sh wrapper for MCP server to handle PATH

## 1.0.0

- Initial release
