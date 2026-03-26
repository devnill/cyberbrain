# Spec Adherence Review — Full Audit

## Verdict: Pass

The implementation substantially follows the stated architecture, constraints, and guiding principles. Two constraints are knowingly violated (documented as design tensions). No undocumented deviations found.

## Constraint Adherence

| Constraint | Status | Notes |
|---|---|---|
| C-01: Python 3.11+ | **Upheld** | Match statements, `X \| Y` syntax used throughout |
| C-02: FastMCP v3, stdio | **Upheld** | `src/cyberbrain/mcp/server.py` uses FastMCP |
| C-03: Obsidian-compatible markdown | **Upheld** | YAML frontmatter, wikilinks, no plugin deps |
| C-04: SQLite for derived data | **Upheld** | FTS5 + usearch in SQLite |
| C-05: Filename char restrictions | **Upheld** | `make_filename()` in vault.py strips `#[]\^` |
| C-06: All vault writes through Python | **Partially violated** | cb_restructure and cb_review write directly (documented as T1) |
| C-07: Hooks always exit 0 | **Upheld** | Both hooks end with `exit 0`, no `set -e` |
| C-08: Env var stripping | **Upheld** | `_STRIP_VARS` in backends.py matches all 5 documented vars |
| C-09: Neutral CWD | **Upheld** | `SUBPROCESS_CWD` in state.py, used in backends.py subprocess call |
| C-10: Soft delete only | **Upheld** | `_move_to_trash()` in shared.py, used by review.py and restructure |
| C-11: Session dedup | **Upheld** | `is_session_already_extracted()` in run_log.py |
| C-12: Test suite passes | **Upheld** | 1310 pass, 0 fail. 2 pyright errors (minor annotation issues) |
| C-13: Hot reload | **Upheld** | Hooks invoke extract_beats.py as script; MCP server is long-lived |
| C-14: Two-level config | **Upheld** | `resolve_config()` merges global + project config |
| C-15: No code generation | **Upheld** | Beats are prose with optional snippets |
| C-16: Single user | **Upheld** | No multi-user logic |
| C-17: Obsidian as human review layer | **Upheld** | No custom UI |

## Principle Adherence

### GP-01: Zero Ceremony for the Common Case — **Upheld**
PreCompact and SessionEnd hooks fire automatically. No user action required after `cb_configure`. Plugin installation handles hook registration.

### GP-02: The Vault is the Canonical Store — **Upheld**
All knowledge lives as markdown files in the vault. Search index is explicitly a rebuild-able acceleration layer (`cb_reindex(rebuild=True)`).

### GP-03: High Signal-to-Noise — **Upheld**
Extraction prompts include durability classification. Working memory notes have TTL-based review cycle.

### GP-04: Feels Like Memory — **Upheld**
Proactive recall is implemented (`proactive_recall` config flag). `cb_recall` returns formatted context suitable for injection.

### GP-05: Vault-Adaptive — **Upheld**
`parse_valid_types_from_claude_md()` reads the vault's own CLAUDE.md for type vocabulary. Autofile uses vault structure context.

### GP-06: Lean Architecture — **Mostly upheld**
Minimal dependencies (SQLite, FastMCP, subprocess). The `run_extraction()` config-ignore bug (S1 from code review) and `_write_beats_and_log()` duplication (S2) are minor violations of leanness.

### GP-07: Cheap Models Where Possible — **Upheld**
Per-tool model selection via `get_model_for_tool()`. Default is haiku for extraction; stronger models configurable per task.

### GP-08: Graceful Degradation — **Upheld**
Search backend falls back to grep when FTS5/semantic unavailable. Optional deps (ruamel.yaml) degrade gracefully. All broad exception handlers have comments explaining intent.

### GP-09: Dry Run as First-Class Feature — **Partially upheld**
cb_restructure, cb_enrich, and the CLI `--dry-run` flag support preview mode. cb_extract and cb_file (MCP tools) do not expose dry_run. cb_review does not have a dry_run mode (it always operates).

### GP-10: YAGNI — **Upheld**
No speculative features observed. The codebase is focused on its stated scope.

### GP-11: Curation Quality — **Upheld**
Quality gates, judge model for restructure decisions, uncertain filing behavior with configurable threshold.

### GP-12: Iterative Refinement — **Upheld**
Evaluation tooling exists (`evaluate.py`). Per-tool model overrides enable experimentation.

### GP-13: Works Everywhere — **Upheld**
MCP server works with Claude Desktop and Claude Code. Plugin system handles Claude Code distribution.

## Interface Contract Adherence

### Config -> All Modules — **Upheld**
`resolve_config()` returns merged dict. All tools access config through `_load_config()`.

### Backends -> Extractor — **Upheld**
`call_model()` dispatches to `_call_claude_code`, `_call_bedrock`, or `_call_ollama`. Returns text. Raises `BackendError`.

### Extractor -> Vault — **Upheld**
`write_beat()` writes markdown. `resolve_output_dir()` handles routing logic.

### Search -> MCP Tools — **Upheld**
`SearchResult` dataclass used consistently. `_get_search_backend()` provides lazy-loaded cached backend.

### MCP Shared -> MCP Tools — **Upheld**
shared.py re-exports from extractor layer. All tools import from shared.py.

## Significant Findings

### S1: C-06 constraint violation is documented but unresolved
cb_restructure and cb_review write vault files directly. This is documented as design tension T1 in the architecture doc but no resolution path is defined.
**Relates to**: C-06, T1

## Minor Findings

### M1: GP-09 (Dry Run) not implemented for cb_extract and cb_file MCP tools
The CLI supports `--dry-run` but the MCP tools for `cb_extract` and `cb_file` do not expose a dry_run parameter. Users cannot preview extraction results through the MCP interface.
**Relates to**: GP-09

### M2: Architecture doc tensions T5/T6/T7 still not marked resolved
The cycle 018 overview planned to update these but the cycle was never executed.
**Relates to**: Documentation accuracy

## Suggestions

None beyond addressing the findings above.
