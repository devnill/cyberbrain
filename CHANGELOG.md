# Changelog

## 1.2.1 — 2026-03-31

First-time setup and onboarding fixes.

### New Features

- **`/cyberbrain:config` skill** — guided setup slash command that walks new users through vault discovery, configuration, and first extraction
- **Vault scaffolding** — `cb_configure(create_vault=True)` creates vault directory structure with inbox folder and starter CLAUDE.md

### Fixes

- **First-run config guard** — MCP tools return actionable setup instructions instead of cryptic errors when config is missing
- **Silent error handling** — hooks and CLI now surface errors to stderr instead of swallowing them silently
- **Plugin manifest error handler** — SKILL.md and plugin.json fixes for edge cases
- **`cb_configure` / `cb_status` fresh install** — handle missing config gracefully with guided next steps
- **`uv` availability check** — hooks verify `uv` is on PATH before attempting extraction; augment PATH with common install locations
- **`cb_configure` prefs path** — `ConfigError` caught in manage.py prefs path and resources.py
- **SKILL.md phase ordering** — `cb_setup` runs before `reset_prefs` in config skill
- **`create_vault` ordering** — fixed sequencing; catch `JSONDecodeError` in manage.py and resources.py

### Documentation

- Updated QUICKSTART.md and README.md for new onboarding flow

## 1.2.0 — 2026-03-27

Transcript noise filtering, full audit fixes, and vocabulary separation.

### New Features

- **Transcript noise filtering** — `transcript.py` now strips skill prompts, command messages, task notifications, system reminders, and usage blocks before extraction. Sessions dominated by tooling output (e.g., ideate skills at 65% noise) now produce beats from actual conversation content instead of returning 0 beats.
- **Transcript truncation limit raised** — `MAX_TRANSCRIPT_CHARS` increased from 150K to 190K. Safe because noise filtering removes bulk before truncation applies.
- **Beat type / entity type vocabulary split** — extraction uses beat types (`decision`, `insight`, `problem`, `reference`); vault notes use entity types (`project`, `note`, `resource`, `archived`) with automatic mapping via `_resolve_entity_type()`
- **Domain tag inference** — `_infer_domain_tag()` auto-tags notes with `work`, `personal`, or `knowledge` based on vault folder path
- **`beat_type` frontmatter field** — vault notes carry both `type` (entity) and `beat_type` (extraction) for traceability

### Fixes

- **YAML frontmatter safety** — all string fields in `write_beat()` use `json.dumps()` quoting; prevents YAML corruption from project names with colons or special characters
- **SQLite connection leak** — `_find_note_by_title` uses `try/finally` for `conn.close()`; LIKE wildcards (`%`, `_`) escaped in user input
- **Search backend cache invalidation** — `vault_path` changes in `cb_configure` now invalidate the cached backend
- **Incremental reindex metadata** — `incremental_refresh` parses frontmatter instead of passing empty dict to `index_note`
- **C-06 vault write abstraction** — routed `pipeline.py` (4), `enrich.py` (1), `format.py` (1) through `write_vault_note()`/`update_vault_note()`
- **Lazy import in vault.py** — replaced module-scope `GLOBAL_CONFIG_PATH` with lazy `config_path()` call
- **move_vault_note overwrite guard** — raises `FileExistsError` if destination exists
- **cb_configure config path** — uses `state.config_path()` instead of hardcoded literal
- **Updated relation predicates** — `causes`/`caused-by`/`implements`/`contradicts` replace `broader`/`narrower`/`wasDerivedFrom`
- **Dead status branch removed** — both branches returned `"active"`

### Documentation

- Added `session-end-extract.sh`, `session-end-reindex.sh` hooks to CLAUDE.md
- Added `synthesize-system/user.md`, `evaluate-system.md`, `quality-gate-system.md` prompts to CLAUDE.md
- Added `resources.py` MCP resource/prompts to CLAUDE.md
- Updated QUICKSTART.md install instructions (removed `install.sh` references)
- Fixed README.md `uncertain_filing_threshold` default (0.7 → 0.5)
- Updated error messages to reference plugin install / `uv sync`
- Added `bedrock_region`, `claude_path`, `search_db_path` to `CyberbrainConfig` TypedDict
- Removed dead `EXTRACTORS_DIR` constant in `scripts/import.py`

## 1.1.3 — 2026-03-26

Full audit fixes — correctness, constraint enforcement, and documentation.

### Fixes

- **YAML frontmatter safety** — all string fields in `write_beat()` now use `json.dumps()` quoting; prevents YAML corruption from project names with colons or special characters
- **SQLite connection leak** — `_find_note_by_title` in `recall.py` now uses `try/finally` for `conn.close()`; also escapes LIKE wildcards (`%`, `_`) in user input
- **Search backend cache invalidation** — `vault_path` changes in `cb_configure` now call `_invalidate_search_backend()` (previously only `search_backend`/`embedding_model` changes did)
- **Incremental reindex metadata** — `incremental_refresh` now parses frontmatter and passes it to `index_note` instead of empty dict; reindexed notes no longer lose title/tags/summary
- **C-06 vault write abstraction** — routed `pipeline.py` (4 calls), `enrich.py` (1 call), `format.py` (1 call) through `write_vault_note()`/`update_vault_note()`; CLAUDE.md metadata writes in `manage.py`/`setup.py` exempt by design
- **Lazy import in vault.py** — replaced module-scope `GLOBAL_CONFIG_PATH` binding with lazy `config_path()` call from `state.py`
- **move_vault_note overwrite guard** — raises `FileExistsError` if destination already exists instead of silently overwriting
- **cb_configure config path** — uses `state.config_path()` instead of hardcoded `Path.home() / ...`
- **Dead status branch** — removed `"active" if durability == "durable" else "active"` ternary

### Documentation

- Added `session-end-extract.sh` and `session-end-reindex.sh` hooks to key files table and data flow diagram
- Added `synthesize-system/user.md`, `evaluate-system.md`, `quality-gate-system.md` prompts to key files table
- Added `resources.py` (MCP resource + prompts) to key files table
- Updated QUICKSTART.md install instructions (removed `install.sh` references)
- Fixed README.md `uncertain_filing_threshold` default (0.7 → 0.5)
- Updated error messages in `shared.py`/`server.py` to reference plugin install
- Removed dead `EXTRACTORS_DIR` constant and stale docstring in `scripts/import.py`
- Added `bedrock_region`, `claude_path`, `search_db_path` to `CyberbrainConfig` TypedDict

## 1.1.2 — 2026-03-26

Vocabulary separation and frontmatter model update.

### Improvements

- **Beat type / entity type split** — extraction uses beat types (`decision`, `insight`, `problem`, `reference`); vault notes use entity types (`project`, `note`, `resource`, `archived`). Mapping is automatic via `_resolve_entity_type()` in `vault.py`
- **`beat_type` frontmatter field** — vault notes now carry both `type` (entity type) and `beat_type` (original extraction type) for traceability
- **Domain tag inference** — `_infer_domain_tag()` auto-tags notes with `work`, `personal`, or `knowledge` based on vault folder path
- **Updated relation predicates** — replaced `broader`/`narrower`/`wasDerivedFrom` with `causes`/`caused-by`/`implements`/`contradicts`
- **`CyberbrainConfig` TypedDict** — all known config fields now have typed definitions in `config.py`
- **`cb_extract` uses `run_extraction()`** — MCP tool now shares the unified orchestration path, gaining dedup checking
- **Enrichment prompt updated** — `enrich-system.md` now enforces entity type vocabulary and domain tagging rules
- **Extraction prompt updated** — `extract-beats-system.md` clarifies beat types are fixed regardless of vault CLAUDE.md entity types

### Bug Fixes

- Fixed `_get_valid_types()` in `enrich.py` returning beat types instead of entity types when parsing vault CLAUDE.md
- Fixed `parse_valid_types_from_claude_md()` matching `## Beat Types` sections as entity type definitions

### Tests

- Added `test_vault.py` with coverage for entity type mapping, domain tag inference, and relation predicates
- Expanded `test_extract_beats.py` with `run_extraction()` integration tests
- Expanded `test_manage_tool.py` with additional config and status scenarios
- Added `test_dependency_map.py` for the test infrastructure mapper

## 1.1.1 — 2026-03-26

Code quality and constraint enforcement patch.

### Improvements

- **Extraction orchestration unified** — `run_extraction()` now accepts `config` and `beats` parameters; `_write_beats_and_log()` removed (eliminated duplicate orchestration path)
- **Lazy state paths** — `state.py` constants converted to functions; `Path.home()` no longer evaluated at import time (fixes test isolation fragility)
- **C-06 enforced** — `cb_review` and `cb_restructure` vault writes routed through `write_vault_note()`/`update_vault_note()`/`move_vault_note()` abstraction layer in `vault.py`
- **`_is_within_vault` consolidated** — single implementation in `vault.py`, re-exported via `shared.py`; duplicate in `shared.py` removed

### Bug Fixes

- Fixed `run_extraction()` ignoring passed `config` parameter (always re-loaded from disk)
- Fixed 2 basedpyright type errors (`CyberbrainConfig` assignability in `shared.py` and `evaluate.py`)
- Removed dead code in `--beats-json` CLI path (unreachable `result["skipped"]` check)

### Documentation

- Architecture tensions T5, T6, T7 marked as resolved

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
