# SP3 — Full System Audit

**Date:** 2026-02-27
**Auditor:** Claude Code (SP3 spike task)
**Scope:** All components of the knowledge-graph system as installed in `~/.claude/` and sourced from `/Users/dan/code/knowledge-graph/`.

---

## Status Table

| Component | Status | Key Finding |
|---|---|---|
| PreCompact hook — script logic | Working | Correct stdin read, CLAUDECODE strip, exit 0 |
| PreCompact hook — `hooks.json` registration | Working | Correct for plugin-mode use |
| PreCompact hook — `set -euo pipefail` risk | **Broken** | `set -e` means any error in `python3` parse block exits non-zero before `exit 0` |
| PreCompact hook — `~/.claude/settings.json` | Untested | Cannot read file from this context; hook installed at `~/.claude/hooks/`; registration presumed from `install.sh` logic |
| `/kg-recall` skill | Working | Search logic, config read, synthesis all correct |
| `/kg-file` skill | Partially working | Ontology diverges from beat types used by extractor; acts as in-context generator, not vault writer |
| `/kg-extract` skill | Working | Correctly locates transcript, calls extractor via `--beats-json`, handles both autofile paths |
| `/kg-claude-md` skill | **Broken** | References `<skill_dir>/scripts/analyze_vault.py` but script lives at `skills/kg-claude-md/scripts/` not a path Claude can self-locate |
| `extract_beats.py` — config resolution | Working | All documented config keys read correctly |
| `extract_beats.py` — transcript parsing | Working | JSONL parsing, tool-block skipping, truncation all correct |
| `extract_beats.py` — LLM call (claude-cli) | Working | Strips CLAUDECODE, timeout, model config all correct |
| `extract_beats.py` — LLM call (anthropic/bedrock) | Working | Both backends implemented; API key check present |
| `extract_beats.py` — beat writing | Working | VALID_TYPES fallback, collision handling, frontmatter generation correct |
| `extract_beats.py` — autofile path | Working | Search, read related, LLM call, extend/create, fallback all present |
| `extract_beats.py` — `--beats-json` flag | Working | Implemented and correctly bypasses transcript parsing |
| `extract_beats.py` — `--transcript` flag | Working | Implemented |
| `extract_beats.py` — daily journal | Working | `write_journal_entry` called when `daily_journal: true` and beats written |
| MCP server — tool implementations | Working | `kg_extract`, `kg_file`, `kg_recall` all implemented |
| MCP server — import path | **Broken** | `sys.path.insert` adds `~/.claude/extractors` but `mcp` package not installed in venv — server fails to start |
| MCP server — `mcp` package in venv | **Broken** | `~/.claude/mcp-venv` exists but only contains `pip`; `mcp` package was never successfully installed |
| MCP server — Claude Desktop registration | Untested | `install.sh` registers it; cannot verify claude_desktop_config.json from this context |
| Import script — conversation format handling | Working | Content blocks preferred over text field; char counting correct |
| Import script — state file logic | Working | Atomic write via `os.replace`; resumable; deduplication at conversation level |
| Import script — `--dry-run`, `--list`, `--limit` | Working | All modes implemented correctly |
| Import script — journal entry on import | Working | Calls `write_journal_entry` at end of run if `daily_journal: true` |
| Config keys — all documented keys | Working | All 11 keys read from `resolve_config()` or downstream callers |
| Config key — `claude_path` | Working | Read and used in `_call_claude_cli`; not in OVERVIEW.md config table (undocumented) |
| Build pipeline — `build.sh` | Working | Packages skills into `.skill` zips; tarball excludes `skills/` source dir |
| Build pipeline — tarball includes skills? | **Broken** | Tarball excludes `./skills` source but includes `dist/` (compiled `.skill` files); only correct if `build.sh` runs first |
| Install pipeline — `install.sh` | Working | Copies all files, registers hook in `settings.json`, creates MCP venv, registers MCP server |
| Install pipeline — MCP `pip install mcp` | **Broken** | Install script reports success but venv only has pip; `mcp` package not installed |
| Failure modes — missing `vault_path` | Working | Exits 0 with error message (does not block compaction) |
| Failure modes — API call failure | Working | Returns empty string; extractor prints error and exits 0 |
| Failure modes — invalid beat type | Working | Silently remapped to `"reference"` |
| Failure modes — missing `knowledge.json` | Working | Exits 0 with message directing user to create it |

---

## Critical Issues

These issues would prevent the system from working correctly in key scenarios.

### CRITICAL-1: MCP server does not start — `mcp` package not installed

**Location:** `~/.claude/mcp-venv/lib/python3.14/site-packages/`

`mcp/server.py` begins with:
```python
from mcp.server.fastmcp import FastMCP
```

The install script creates `~/.claude/mcp-venv` and attempts `pip install mcp`, but the venv contains only pip. The `mcp` package is not present. Every import of `server.py` will fail with `ModuleNotFoundError`. The MCP server is non-functional.

**Fix:** Run `~/.claude/mcp-venv/bin/pip install mcp` manually, then restart Claude Desktop.

---

### CRITICAL-2: `set -euo pipefail` in hook script creates a silent failure path

**Location:** `/Users/dan/code/knowledge-graph/hooks/pre-compact-extract.sh`, line 6

```bash
set -euo pipefail
```

The hook uses `set -euo pipefail`. The `eval "$(echo "$INPUT" | python3 -c ...)"` block on line 11 will cause the script to exit non-zero if:
- `python3` is not in PATH
- The JSON on stdin is malformed or empty (parsing error)
- The `eval` fails for any reason

With `set -e`, any of these exits the script immediately — before reaching `exit 0` on line 44. A non-zero exit from a PreCompact hook **blocks compaction**. This is exactly the behavior the CLAUDE.md says must be avoided ("must always `exit 0`").

Under normal operation, this path is fine. But if Claude Code sends malformed hook JSON, or if `python3` is unavailable, compaction is blocked. The `exit 0` at the bottom provides a false sense of safety.

**Severity:** High. Rare but catastrophic when it occurs.

**Fix:** Wrap the entire body in `{ ... } || true` or restructure the eval/parse block so errors are caught and silently skipped before reaching the exit.

---

### CRITICAL-3: `kg-claude-md` skill references a non-self-locating script path

**Location:** `/Users/dan/code/knowledge-graph/skills/kg-claude-md/SKILL.md`, Step 1

```
python <skill_dir>/scripts/analyze_vault.py "<vault_path>" --output /tmp/vault_report.json
```

The skill instructs Claude to use `<skill_dir>/scripts/analyze_vault.py` — but `<skill_dir>` is a placeholder that Claude must resolve itself. Claude Code does not automatically expose the skill's directory to the running agent. The skill does not tell Claude how to find this path.

In plugin mode, the script lives at `~/code/knowledge-graph/skills/kg-claude-md/scripts/analyze_vault.py`. In installed mode, it lives at `~/.claude/skills/kg-claude-md/scripts/analyze_vault.py`. The skill gives no instruction for how to locate either path.

`analyze_vault.py` also imports `yaml` (PyYAML). If `pyyaml` is not installed in the Python that Claude selects, the script will fail with `ModuleNotFoundError`.

**Severity:** High. The skill's Step 1 will fail for any user who has not manually inferred the correct path.

**Fix:** Replace `<skill_dir>` with explicit resolution logic (e.g., try `~/.claude/skills/kg-claude-md/scripts/analyze_vault.py`, fallback to searching) or provide an absolute path resolution step.

---

## Detailed Component Notes

### 1. PreCompact Hook

**Script: `hooks/pre-compact-extract.sh`**

The core logic is correct:
- Reads stdin with `INPUT=$(cat)` — correct
- Parses JSON with a single Python call using `shlex.quote` — safe, avoids injection
- Checks `TRANSCRIPT_PATH` is non-empty and file exists — good guard
- Locates extractor: plugin-local copy takes precedence over installed copy — correct priority
- Strips CLAUDECODE via environment construction in `_call_claude_cli` (also done in the Python extractor itself, not the shell script — the hook itself does not strip it, but the Python code does before the subprocess call)
- Final `exit 0` present

**Problem:** See CRITICAL-2. `set -euo pipefail` can exit before reaching `exit 0`.

**`hooks/hooks.json`:**

```json
{
  "hooks": {
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/pre-compact-extract.sh",
            ...
          }
        ]
      }
    ]
  }
}
```

This is the plugin-mode registration. The `${CLAUDE_PLUGIN_ROOT}` variable is set by Claude Code when loading a plugin — this is correct for `--plugin-dir` usage. For the installed mode, the hook is registered in `~/.claude/settings.json` by `install.sh` using a hardcoded `~/.claude/hooks/pre-compact-extract.sh` path. Both registrations are correct for their respective use cases.

**Hook registration in `~/.claude/settings.json`:** The install.sh correctly registers it:
```python
d.setdefault('hooks', {})['PreCompact'] = [DESIRED]
```
where DESIRED uses `~/.claude/hooks/pre-compact-extract.sh`. Cannot verify the file directly from this context, but the install script logic is correct.

---

### 2. Skills

#### `/kg-recall`

**Status: Working**

- Step 1 reads `~/.claude/knowledge.json` via inline Python — correct
- Steps 2-4 run grep commands against vault path — correct, with appropriate `head -20` limits
- Step 5 prefers project vault folder — correct routing logic
- Step 6 sorts by mtime for recency bias — correct
- Reads up to 5 documents — appropriate context budget
- Output format is well-defined

No issues found. The search strategy is redundant (Steps 2 and 4 run the same grep), but this is a minor inefficiency, not a bug.

#### `/kg-file`

**Status: Partially working — ontology mismatch**

This skill generates Obsidian notes using a rich personal knowledge graph ontology defined in `references/ontology.md`. That ontology has 12 entity types: `project`, `concept`, `tool`, `decision`, `insight`, `problem`, `resource`, `person`, `event`, `claude-context`, `domain`, `skill`, `place`.

The extractor (`extract_beats.py`) uses exactly 6 types: `decision`, `insight`, `task`, `problem-solution`, `error-fix`, `reference`.

The two type vocabularies are largely incompatible. A `/kg-file` note of type `concept` or `tool` will not be found by searches for `type: reference` or validated by `VALID_TYPES` if ever processed by the extractor. If a user uses `/kg-file` to produce a note and then tries to recall it with `/kg-recall` (which searches for any `.md` file matching keywords), this is fine — the mismatch doesn't break retrieval. But it does mean the vault has two parallel ontologies, which creates long-term inconsistency.

More importantly, `/kg-file` does not actually write files to the vault. It is an in-context skill that generates markdown and presents it to the user, who must paste it manually into Obsidian. This is not documented as such in OVERVIEW.md, which describes it as: "Manually file any piece of information into the vault right now." The word "right now" implies automatic writing. In contrast, `/kg-extract` directly invokes `extract_beats.py` to write files.

**This is a documentation/expectation mismatch.** The skill header does not explain the manual-paste requirement.

#### `/kg-extract`

**Status: Working**

- Case A (current session): correctly encodes CWD as `cwd.replace('/', '-')` to find the project dir under `~/.claude/projects/` — correct
- Case B (file path given): correctly derives session_id from filename stem, decodes CWD from path components
- Config loading is correct; reads `autofile` and `daily_journal` flags
- Temp JSON path generation is correct; invokes `extract_beats.py --beats-json` then cleans up
- Autofile path uses Grep and Read tools directly (correct for in-session use) rather than spawning the subprocess autofile, avoiding the nested session problem
- Log file written to `~/.claude/logs/kg-extract.log` — the directory is created with `mkdir -p`
- Step 7 summary format is well-defined

Minor note: the skill's CWD decoding (`-` → `/`) is slightly fragile — it will misfire if the actual project path contained a `-` that should not be `/`. However, this is the same encoding Claude Code uses internally, so it's consistent.

#### `/kg-claude-md`

**Status: Broken (see CRITICAL-3)**

Beyond the script location issue, the skill logic itself is sound:
- Step 0 verifies vault path exists and has `.obsidian/` or sufficient `.md` files
- Step 1 runs the vault analyzer
- Step 2 deep-reads selected notes based on vault size
- Step 3 synthesizes findings (type system, naming convention, tag hierarchy)
- Step 4 generates CLAUDE.md with well-defined section order
- Step 5 saves and reports

The `references/output-structure.md`, `references/analysis-process.md`, and `references/claude-md-template.md` reference files all exist.

The `analyze_vault.py` script itself is well-implemented: parses frontmatter, counts tags, detects wikilinks, measures orphan notes, identifies hub nodes. It imports `yaml` — `pyyaml` must be installed.

---

### 3. `extractors/extract_beats.py`

**Status: Working (with one minor issue)**

#### Config resolution

All documented config keys are present:

| Key | Where read | Default |
|---|---|---|
| `vault_path` | `load_global_config()` | Required |
| `inbox` | `load_global_config()` required check + `resolve_output_dir()` | Required |
| `staging_folder` | `load_global_config()` required check + `resolve_output_dir()` | Required |
| `backend` | `call_model()` / `_call_anthropic_sdk()` | `"claude-cli"` |
| `claude_model` | `_call_claude_cli()` | `"claude-haiku-4-5"` |
| `claude_timeout` | `_call_claude_cli()` | `120` |
| `claude_path` | `_call_claude_cli()` | `"claude"` |
| `autofile` | `main()` | `False` |
| `daily_journal` | `main()` | `False` |
| `journal_folder` | `write_journal_entry()` | `"AI/Journal"` |
| `journal_name` | `write_journal_entry()` | `"%Y-%m-%d"` |

All 11 keys are correctly implemented. `claude_path` is implemented but not documented in `OVERVIEW.md`'s config table — minor omission.

#### `resolve_config()` structure

```python
def resolve_config(cwd: str) -> dict:
    global_cfg = load_global_config()
    project_cfg = find_project_config(cwd)
    return {**global_cfg, **project_cfg}
```

Project config keys override global config keys. This is the correct merge order.

#### Transcript parsing

- Skips non-user/assistant entries — correct
- Skips `tool_use` and `thinking` blocks — correct
- Includes `tool_result` but trims at 500 chars — correct
- Truncates at 150,000 chars, keeping the tail — correct

#### LLM backends

All three backends implemented:
- `claude-cli`: strips `CLAUDECODE`, uses `claude -p --model --no-session-persistence --max-turns 1`
- `anthropic`: checks `ANTHROPIC_API_KEY`, uses `anthropic` SDK
- `bedrock`: uses `AnthropicBedrock` with configurable region

#### Beat writing

- `VALID_TYPES` check remaps invalid types to `"reference"` silently — correct for resilience
- Collision handling via numbered prefix (`2 Title.md`, `3 Title.md`) — correct
- Uses `json.dumps()` for YAML string fields — correctly handles quotes and special chars
- `resolve_output_dir()` routes: project scope + vault_folder → vault_folder; otherwise → inbox; staging_folder is fallback when inbox is absent (but inbox is required, so staging_folder effectively unused in practice via this path)

**Minor issue:** `resolve_output_dir()` routes to `inbox` for general-scope beats even when there is no project config. The `staging_folder` is intended for "no project config found" situations, but the code routes to `inbox` in that case too. Only if `inbox` itself is somehow absent does it fall through to `staging_folder`. Since `inbox` is a required field, `staging_folder` is never used in the flat-write path. The distinction between "no project config" and "project config found but beat is general" is collapsed. Both route to `inbox`. This matches the OVERVIEW.md description but may not match user expectation that "no project config" → staging.

#### Daily journal

`write_journal_entry()` is called in `main()`:
```python
if journal_enabled and written:
    project_name = config.get("project_name", Path(args.cwd).name)
    write_journal_entry(written, config, args.session_id, project_name, now)
```

The function creates the journal directory if needed, appends to or creates the daily file, and writes wikilinks for each written beat. The logic is correct. The SP2 spike notes this "may not be functioning" — from code inspection, the logic is correct, but the bug is likely that `daily_journal` might not be set to `true` in the user's `knowledge.json`, or that the journal path is not being checked in the right vault. There is no silent swallow here — errors in `write_journal_entry` would propagate as exceptions and be printed. If nothing is being written, the most likely cause is `daily_journal: false` in config.

---

### 4. MCP Server (`mcp/server.py`)

**Status: Broken — mcp package not installed**

All three tools are implemented:

- `kg_extract(conversation, project_name, cwd, trigger)` — accepts raw conversation text (not a transcript path), calls `call_model` directly, writes beats
- `kg_file(title, body, type, tags, scope, summary)` — creates a single beat dict and calls `write_beat`
- `kg_recall(query, max_results)` — runs grep, ranks by mtime, returns note content

The import chain:
```python
sys.path.insert(0, str(Path.home() / ".claude" / "extractors"))
from mcp.server.fastmcp import FastMCP
```

The `mcp` package must be available when `server.py` is imported. It is not in the venv.

The `~/.claude/mcp-venv/` directory exists and contains Python 3.14 with pip only. The `mcp` package installation failed silently during install.

**Difference from `/kg-extract`:** The MCP `kg_extract` tool accepts pre-rendered conversation text, not a transcript file path. This means the caller (Claude Desktop) must pass the conversation content as a string. This is correct for the Desktop use case (no filesystem access to the transcript file), but limits the tool to conversations that fit in the MCP tool call.

**`CLAUDECODE` in MCP context:** The MCP server runs from Claude Desktop, which does not set `CLAUDECODE=1`. So the `claude-cli` backend works correctly from the MCP server without needing to strip the env var. The Python extractor still strips it as a precaution, which is harmless.

---

### 5. Import Script (`scripts/import-desktop-export.py`)

**Status: Working**

- `load_conversations()` expects a JSON array at the top level — correct for Anthropic export format
- `render_message_text()` prefers `content[].type==text` blocks over `msg['text']` to avoid "This block is not supported" artifacts — documented rationale is correct
- `render_conversation()` emits `## {name}`, `Date:`, `Summary:`, then `**Human:**` / `**Assistant:**` turns — readable format for LLM extraction
- Truncation at `MAX_TRANSCRIPT_CHARS = 150_000` matches `extract_beats.py` — consistent
- State file: `save_state()` uses atomic write via `os.replace(tmp, state_path)` — correct
- `build_work_queue()` correctly skips already-processed conversations, supports date filtering
- Per-conversation error handling records state and continues rather than aborting
- `KeyboardInterrupt` handler saves state before exit — correct
- `--reprocess-errors` re-adds error entries to the queue — correct
- Journal entry written once at end of run (not per-conversation) — correct

**Minor issue:** The `already_done` count calculation (line 505-508) is convoluted and may be off-by-one when `--limit` is used. This is a display issue only; it does not affect processing logic.

**Deduplication:** State is tracked at the conversation UUID level, not the beat level. If the same conversation produces different beats on two runs (e.g., after a model update), the second run is skipped. This is appropriate behavior but means re-extraction of a conversation requires `--reprocess-errors`.

---

### 6. Config Keys Audit

**All keys documented in `steering/OVERVIEW.md` are implemented.** One additional key (`claude_path`) exists in the code but is not documented.

| Key | In OVERVIEW.md | In `resolve_config()` / code | Notes |
|---|---|---|---|
| `vault_path` | Yes | Yes | Required; validated |
| `inbox` | Yes | Yes | Required; validated |
| `staging_folder` | Yes | Yes | Required; validated (but rarely exercised — see beat writing note) |
| `backend` | Yes | Yes | Defaults to `claude-cli` |
| `claude_model` | Yes | Yes | Used by claude-cli backend |
| `autofile` | Yes | Yes | Defaults to `False` |
| `daily_journal` | Yes | Yes | Defaults to `False` |
| `journal_folder` | In CLAUDE.md but not OVERVIEW.md table | Yes | Defaults to `"AI/Journal"` |
| `journal_name` | In CLAUDE.md but not OVERVIEW.md table | Yes | Defaults to `"%Y-%m-%d"` |
| `claude_timeout` | In CLAUDE.md but not OVERVIEW.md table | Yes | Defaults to `120` |
| `claude_path` | Not documented anywhere | Yes | Defaults to `"claude"` |

The `knowledge.example.json` file omits `claude_model`, `claude_timeout`, and `claude_path`. A user who copies the example file will get correct defaults for all three.

---

### 7. Build / Install Pipeline

**`build.sh`:**

- Correctly packages each `skills/*/` directory (that has a `SKILL.md`) into a `.skill` zip
- Tarball uses `--exclude="./skills"` — this excludes the source skill directories from the tarball, relying on the pre-built `.skill` files in `dist/`

**Issue:** The tarball works correctly only if `build.sh` is run before creating the tarball (which it is, since `install.sh` calls `build.sh --skills-only` first). But if someone runs `tar xzf knowledge-graph-X.tar.gz` on a release tarball, they get the `.skill` files in `dist/` which are what `install.sh` needs. This is correct behavior, just non-obvious.

**`install.sh`:**

- Calls `build.sh --skills-only` first — ensures `.skill` files are current
- Creates all target directories
- Copies hook, extractor, prompts, skills, MCP server
- Registers PreCompact hook in `settings.json` using Python (handles missing file, malformed JSON, and upgrades)
- Creates `knowledge.json` from `knowledge.example.json` only if not already present — preserves existing config
- Installs Python deps: skips `anthropic` for `claude-cli` backend; still installs `pyyaml` for `kg-claude-md`
- Creates MCP venv and attempts `pip install mcp` — **this step is failing silently**
- Registers MCP server in Claude Desktop config (macOS only)

**Fresh machine concerns:**
1. The `mcp` package install failure is silent if pip exits non-zero — the `2>/dev/null` suppresses the error output. This is a reliability issue.
2. `pyyaml` install uses `python3 -m pip install pyyaml -q 2>/dev/null || true` — swallows all errors. If pyyaml is not installed and `python3` is conda/managed, the install silently fails and `kg-claude-md` will fail later.
3. The hook registration Python script uses `sys.exit(0)` on parse error, which produces an exit code of 0 even on failure — the outer bash script cannot detect that hook registration failed.

---

### 8. Failure Modes

| Scenario | Behavior | Assessment |
|---|---|---|
| `vault_path` doesn't exist | `load_global_config()` prints error, calls `sys.exit(0)` | Correct — does not block compaction |
| `vault_path` is placeholder string | Same exit(0) path — explicitly checks for `/path/to/your/ObsidianVault` | Correct |
| `knowledge.json` missing | `load_global_config()` prints message, `sys.exit(0)` | Correct |
| API call fails (timeout) | Returns empty string; `extract_beats()` returns `[]`; `main()` prints "No beats extracted" and `sys.exit(0)` | Correct |
| API call fails (non-zero return) | Same empty string path | Correct |
| JSON parse failure (bad LLM output) | Prints raw response (first 500 chars), returns `[]` | Correct |
| Beat has invalid type | Silently remapped to `"reference"` in `write_beat()` | Correct; could optionally log a warning |
| Beat has invalid scope | Silently remapped to `"general"` | Correct |
| Output directory can't be created | `output_dir.mkdir(parents=True, exist_ok=True)` — raises `OSError` which propagates to `main()`'s per-beat exception handler, prints error, continues | Correct |
| Filename collision | Prepends incrementing number: `2 Title.md`, `3 Title.md` | Correct |
| Autofile LLM returns bad JSON | Falls back to `write_beat()` (flat write) | Correct |
| Autofile `extend` target doesn't exist | Falls back to `write_beat()` | Correct |
| `set -e` in hook + python parse error | Hook exits non-zero, **blocks compaction** | Bug — see CRITICAL-2 |
| Transcript is empty | `transcript_text.strip()` is falsy; `sys.exit(0)` | Correct |

---

## Summary of Issues by Severity

### High (would cause silent failures or block core functionality)

1. **MCP server non-functional** — `mcp` package not installed in venv. `kg_recall`, `kg_file`, `kg_extract` all unavailable in Claude Desktop.

2. **Hook `set -euo pipefail` risk** — Python parse errors or missing `python3` would cause the hook to exit non-zero, blocking compaction. The `exit 0` safety at the bottom of the script is not reached.

3. **`/kg-claude-md` script path unresolvable** — Claude cannot determine the path to `analyze_vault.py` from the skill instructions. Step 1 of the skill will fail unless the user manually provides the path.

### Medium (degrades functionality but has workarounds)

4. **`/kg-file` does not write files** — it generates notes for manual paste rather than writing to vault. OVERVIEW.md implies it writes directly. This is an expectation mismatch.

5. **`staging_folder` effectively unreachable** — general-scope beats always route to `inbox` (which is required), so the staging folder is never used in the flat-write path. The documented routing "no project config → staging folder" doesn't match actual code behavior.

6. **`claude_path` config key undocumented** — users on non-standard Claude CLI locations cannot find this key in documentation.

7. **pyyaml installation may fail silently** — install.sh swallows pyyaml install errors; `/kg-claude-md` will fail with `ModuleNotFoundError` if it's missing.

### Low (minor issues, cosmetic or edge-case)

8. **`/kg-recall` Steps 2 and 4 are identical greps** — redundant work, minor inefficiency.

9. **`already_done` display counter in import script** — calculation is convoluted and may display incorrectly with `--limit`, but does not affect processing.

10. **`journal_folder`, `journal_name`, `claude_timeout` absent from OVERVIEW.md config table** — present in CLAUDE.md but not the canonical user-facing reference.

11. **knowledge.example.json** omits `claude_model`, `claude_timeout` — minor, since defaults are correct.

---

## What Actually Works End-to-End

The following path works correctly in the current state:
- A user with `knowledge.json` configured (vault exists, `claude-cli` backend) runs `/compact`
- The hook fires, reads stdin, parses the hook JSON, locates the extractor
- `extract_beats.py` parses the transcript, calls `claude -p`, extracts beats, writes `.md` files to inbox
- The user runs `/kg-recall <query>` to search the vault in a subsequent session

The following paths are broken or untested:
- Claude Desktop MCP integration (broken — `mcp` package missing)
- `/kg-claude-md` (broken — script path resolution fails)
- Automatic extraction if `python3` or hook JSON is malformed (broken — `set -e` exits non-zero)
- `/kg-file` writing directly to vault (it doesn't; requires manual paste)
