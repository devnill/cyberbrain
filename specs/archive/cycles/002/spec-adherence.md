# Spec Adherence Review — Cycle 002

## Verdict: Fail

One unmet acceptance criterion (CLAUDE.md not updated per WI-034 scope) and five architecture deviations — all documentation/spec issues, no behavioral failures.

---

## Architecture Deviations

### D1: Component map and module specs use pre-WI-034 flat-layout paths throughout

- **Expected**: After WI-034 migrated all Python source files to `src/cyberbrain/`, the architecture document component map and all module specs should reference the new paths `src/cyberbrain/extractors/` and `src/cyberbrain/mcp/`.
- **Actual**: All spec documents retain the old flat-layout paths with no `src/cyberbrain/` prefix.
- **Evidence**:
  - `specs/plan/architecture.md:82–98` — Component Map lists all components as `extractors/X.py` and `mcp/X.py`. Actual files are at `src/cyberbrain/extractors/X.py` and `src/cyberbrain/mcp/X.py`.
  - `specs/plan/modules/extraction.md:47` — "Files: `extractors/extractor.py` ... `extractors/extract_beats.py`"
  - `specs/plan/modules/vault.md:62` — "Files: `extractors/vault.py` ..."
  - `specs/plan/modules/search.md:47` — "Files: `extractors/search_backends.py` ..."
  - `specs/plan/modules/backends.md:38` — "File: `extractors/backends.py`"
  - `specs/plan/modules/mcp-tools.md:87` — "Files: `mcp/tools/{...}.py`"
  - `CLAUDE.md:76` — `python3 extractors/extract_beats.py` dev invocation (old flat path, no longer valid)
  - `CLAUDE.md:102` — "invokes `extractors/extract_beats.py` with transcript path"
  - `CLAUDE.md:117–137` — Key Files table uses old flat paths for all source files

### D2: mcp-server module spec boundary rules describe the removed sys.path mechanism

- **Expected**: Boundary rules should reflect that `server.py` and `shared.py` use package-qualified imports after WI-034.
- **Actual**: Two of the four boundary rules describe the old `sys.path.insert` approach that WI-034 explicitly removed.
- **Evidence**:
  - `specs/plan/modules/mcp-server.md:40` — "server.py is run as a script, not a package — uses `sys.path.insert` for flat imports." Actual `src/cyberbrain/mcp/server.py:17` uses `from cyberbrain.mcp.tools import ...`.
  - `specs/plan/modules/mcp-server.md:41` — "shared.py inserts `~/.claude/cyberbrain/extractors` into `sys.path` at module level." Actual `src/cyberbrain/mcp/shared.py:17` uses `from cyberbrain.extractors.extract_beats import ...`.
  - `specs/plan/modules/mcp-server.md:51` — "Import strategy: `sys.path.insert(0, str(_MCP_DIR))` makes shared, tools.*, resources importable as flat modules." No `sys.path` manipulation exists anywhere in `src/cyberbrain/mcp/`.
  - `specs/plan/modules/mcp-server.md:52` — "No naming conflict with the `mcp` pip package because the `mcp/` directory has no `mcp/` subdirectory." The WI-034 rationale was precisely that this conflict existed; the module spec's claim contradicts the WI-034 problem statement.

### D3: import.md module spec describes sys.path.insert mechanism that was replaced

- **Expected**: The import module spec should describe the package-based import introduced in WI-034.
- **Actual**: The spec describes `sys.path.insert` from the installed location as the import mechanism.
- **Evidence**:
  - `specs/plan/modules/import.md:20` — "Imported from `~/.claude/cyberbrain/extractors/`." Actual `scripts/import.py:48` uses `import cyberbrain.extractors.extract_beats as eb`.
  - `specs/plan/modules/import.md:33` — "Imports `extract_beats` via `sys.path.insert` from the installed location, not the repo." No `sys.path` manipulation exists in `scripts/import.py`.

### D4: Architecture.md and mcp-server module spec describe _parse_frontmatter in shared.py as an "own implementation"

- **Expected**: Architecture T4 acknowledges `frontmatter.py` as the canonical source. The mcp-server module spec should note that shared.py delegates to it.
- **Actual**: Both documents describe `shared.py._parse_frontmatter()` as an independent implementation; T4 lists shared.py as one of the files still with its own copy.
- **Evidence**:
  - `specs/plan/architecture.md:452` — "shared.py._parse_frontmatter(), analyze_vault.parse_frontmatter(), and search_backends.py (fallback path) each still contain their own implementations."
  - `specs/plan/modules/mcp-server.md:18` — "`_parse_frontmatter(content) -> dict` — YAML frontmatter extraction (own implementation)."
  - `src/cyberbrain/mcp/shared.py:26` — `from cyberbrain.extractors.frontmatter import parse_frontmatter as _parse_frontmatter`. This is a delegation, not an own implementation. T4 is partially resolved for shared.py and analyze_vault.py but the documentation has not been updated to reflect this. `search_backends.py` remains the one true holdout.

### D5: search_backends.py frontmatter import always falls back to inline implementations in the installed package

- **Expected**: Per T4, `search_backends.py` is the one remaining file with its own frontmatter implementation. The try/except structure intends to use `frontmatter.py` when available.
- **Actual**: The `try` block attempts `from frontmatter import ...` (bare module name). In the `src/cyberbrain` package, there is no bare `frontmatter` module — the canonical module is `cyberbrain.extractors.frontmatter`. The `try` always raises `ImportError` and the inline fallback implementations are always used.
- **Evidence**:
  - `src/cyberbrain/extractors/search_backends.py:783–786` — `try: from frontmatter import read_frontmatter as _read_frontmatter` — structurally unreachable in the installed package. The correct form (as used in `analyze_vault.py:28`) is `from cyberbrain.extractors.frontmatter import read_frontmatter as _read_frontmatter`.
  - `src/cyberbrain/extractors/analyze_vault.py:28` — correct package-qualified form not replicated in search_backends.py.

---

## Unmet Acceptance Criteria

### Work Item 034: Restructure to src layout

- [ ] **CLAUDE.md updated with new architecture documentation** — WI-034 scope (`specs/plan/work-items/034-restructure-to-src-layout.md:25`) explicitly lists `CLAUDE.md` as a file to modify: "update architecture documentation". The incremental review's "Changes Made" section (`specs/archive/incremental/034-restructure-to-src-layout.md:27–52`) does not list CLAUDE.md. The file still contains:
  - Old flat-path dev invocation at `CLAUDE.md:76`
  - Old Key Files table at `CLAUDE.md:117–137` with flat paths
  - "ten tools" at `CLAUDE.md:24` when 11 are implemented
  - Old data flow description at `CLAUDE.md:102`

---

## Principle Violations

None.

---

## Principle Adherence Evidence

- **GP-1** (Zero Ceremony): `hooks/pre-compact-extract.sh` and `hooks/session-end-extract.sh` fire automatically; no user action required after setup.
- **GP-2** (Vault is Canonical Store): `src/cyberbrain/mcp/tools/reindex.py` — full rebuild from vault via `cb_reindex`; search index at `~/.claude/cyberbrain/` is derived data.
- **GP-3** (High Signal-to-Noise): `src/cyberbrain/extractors/quality_gate.py` — LLM-as-judge quality gate with pass/fail/uncertain applied to all curation operations.
- **GP-4** (Feels Like Memory): `src/cyberbrain/mcp/resources.py:98–136` — `orient` and `recall` prompts enable proactive retrieval at session start and mid-session.
- **GP-5** (Vault-Adaptive): `src/cyberbrain/extractors/vault.py:26–60` — `parse_valid_types_from_claude_md()` reads type vocabulary from vault's CLAUDE.md; hardcoded defaults used only as fallback.
- **GP-6** (Lean Architecture): `pyproject.toml:23–33` — SQLite (stdlib) for all derived data; `fastembed` and `usearch` are optional extras; no daemon processes.
- **GP-7** (Cheap Models): `src/cyberbrain/extractors/backends.py:249–265` — `get_model_for_tool(config, tool)` enables per-task model selection; `CLI_DEFAULT_MODEL = "claude-haiku-4-5"` as global default.
- **GP-8** (Graceful Degradation): `hooks/pre-compact-extract.sh:19,46,51` and `session-end-extract.sh:25,65,68` — all error paths `exit 0`; `mcp/shared.py:38–47` — `_get_search_backend` returns `None` on failure.
- **GP-9** (Dry Run First-Class): `src/cyberbrain/extractors/extract_beats.py:79` — `--dry-run` CLI argument; full pipeline executes but writes are skipped.
- **GP-10** (YAGNI): `src/cyberbrain/mcp/server.py` — no `evaluate` tool registered; dev tool preserved at `src/cyberbrain/extractors/evaluate.py` per WI-008.
- **GP-11** (Curation Quality Paramount): `src/cyberbrain/mcp/tools/restructure.py` — restructure pipeline runs audit phase before grouping/deciding; misplaced/low-quality notes removed from clusters before execution.
- **GP-12** (Iterative Refinement): `src/cyberbrain/extractors/evaluate.py` — evaluation framework for comparing outputs side-by-side; `tests/vaults/` — test vaults for repeated testing.
- **GP-13** (Works Everywhere): `.mcp.json` and `.claude-plugin/plugin.json` — both Claude Code (plugin) and Claude Desktop (manual install) are supported.

---

## Undocumented Additions

### U1: search_backends.py fallback frontmatter implementations are always active in the installed package

- **Location**: `src/cyberbrain/extractors/search_backends.py:783–840`
- **Description**: Three helper functions (`_read_frontmatter`, `_normalise_list`, `_derive_id`) defined inside an `except ImportError` block after a failed `from frontmatter import ...`. The try block uses the old flat module name which does not resolve in the `cyberbrain` package namespace. These inline implementations are therefore always active in the installed package — the `except` branch always executes.
- **Risk**: Silent behavioral divergence from the canonical `frontmatter.py`. Any future bug fix or behavior change in `frontmatter.py`'s parsing will not affect the search index build path. Design tension T4 is documented as "partially resolved" but `search_backends.py` remains the holdout, and the mechanism silently prevents resolution.

---

## Naming/Pattern Inconsistencies

### N1: WI-034 spec and incremental review consistently misspell the directory name as "cybrain"

- **Convention**: Package name and directory are `cyberbrain`; the actual path is `src/cyberbrain/`.
- **Violation**: `specs/plan/work-items/034-restructure-to-src-layout.md:15,16,17,29,30,31,49,50,51` and `specs/archive/incremental/034-restructure-to-src-layout.md:30,31,32,33,34,35,60,61,62` — both documents write `src/cybrain/` throughout (missing the 'e'). The implementation is correct (`src/cyberbrain/`). The acceptance criteria table in the incremental review marks `src/cybrain/ with __init__.py` as passing, which cannot have been literally verified since no directory named `src/cybrain/` exists.

### N2: CLAUDE.md reports "ten tools" while listing eleven and while the architecture document states 11

- **Convention**: `specs/plan/architecture.md:23` — "11 tools". Implementation registers exactly 11 tools.
- **Violation**: `CLAUDE.md:24` — "an MCP server with ten tools (`cb_extract`, `cb_file`, `cb_recall`, `cb_read`, `cb_setup`, `cb_enrich`, `cb_configure`, `cb_status`, `cb_restructure`, `cb_review`, `cb_reindex`)". The parenthetical list contains 11 tool names. The word "ten" contradicts both the list and the architecture document.
