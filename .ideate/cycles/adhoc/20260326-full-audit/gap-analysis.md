# Gap Analysis — Full Audit

## Missing Requirements

### No missing core requirements
All 11 MCP tools exist and are registered. Both hooks are implemented. All three LLM backends are present. Three-tier search works. Two-level config is in place. Import scripts exist. The feature surface matches the architecture document.

## Integration Gaps

### IG1: run_extraction() config parameter is dead code
**Severity**: Significant
**File**: `src/cyberbrain/extractors/extract_beats.py:53,68`
The `config` parameter on `run_extraction()` is never used — line 68 always calls `resolve_config(cwd)`. The MCP `cb_extract` tool (extract.py:60) loads config via `_load_config()` then passes nothing to `run_extraction()`, so config is loaded twice per extraction. This wastes one `resolve_config()` call per extraction.
**Relates to**: GP-06, planned for cycle 018 (never executed)

### IG2: --beats-json path bypasses run_extraction()
**Severity**: Significant
**File**: `src/cyberbrain/extractors/extract_beats.py:289,398`
The `--beats-json` CLI flag calls `_write_beats_and_log()` instead of `run_extraction()`. This duplicates the beat-writing, autofile, and logging orchestration. Changes to `run_extraction()` do not propagate to the `--beats-json` path.
**Relates to**: GP-06, architecture tension T5 (hook vs MCP path divergence)

## Infrastructure Gaps

### IG3: No CI/CD pipeline
**Severity**: Minor
Pre-commit hooks run ruff and lint locally, but there is no CI pipeline (GitHub Actions, etc.). The test suite (1310 tests) and type checker (basedpyright) run only when a developer remembers to invoke them. This is documented as a known deferred item.
**Relates to**: C-12

### IG4: No automated config backup
**Severity**: Minor
The production config at `~/.claude/cyberbrain/config.json` has no backup mechanism. A test run corrupted it during this session (replacing vault_path with a pytest temp dir). There is no `config.json.bak` or versioning scheme.
**Relates to**: GP-08 (graceful degradation)

## Implicit Requirements Not Met

### IR1: MCP tools lack dry_run for cb_extract and cb_file
**Severity**: Minor
GP-09 states "all destructive operations support dry-run mode." The CLI `extract_beats.py` supports `--dry-run` but the MCP tools `cb_extract` and `cb_file` do not expose this. Users interacting via Claude Desktop or Claude Code cannot preview extraction results before committing them to the vault.
**Relates to**: GP-09

### IR2: No health check or self-diagnosis tool
**Severity**: Suggestion
`cb_status` shows recent runs, index health, and config summary. However, there's no tool that validates the full system (checks that the claude CLI is accessible, config is valid, vault path exists, hooks are registered, etc.). When the config was corrupted in this session, the failure mode was silent — writes just failed with no diagnostic.
**Relates to**: GP-08

## Critical Findings

None.

## Significant Findings

- **IG1**: run_extraction() ignores config parameter — double config load per extraction
- **IG2**: _write_beats_and_log() duplicates run_extraction() orchestration

## Minor Findings

- **IG3**: No CI/CD pipeline (known deferred item)
- **IG4**: No config backup mechanism
- **IR1**: MCP tools cb_extract and cb_file lack dry_run

## Suggestions

- **IR2**: Add a `cb_diagnose` or extend `cb_status` to validate system health (config, vault path, claude CLI, hook registration)
- Consider adding config backup-on-write (write `config.json.bak` before overwriting)
