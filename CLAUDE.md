# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Steering Documents

The `steering/` directory contains the authoritative project-level documents. Read these before making significant changes:

| Document | Purpose |
|---|---|
| [`steering/OVERVIEW.md`](steering/OVERVIEW.md) | What this project is, how it works, interfaces, and current status |
| [`steering/GOALS.md`](steering/GOALS.md) | Motivating goals — why decisions were made this way |
| [`steering/USE_CASES.md`](steering/USE_CASES.md) | Concrete scenarios the system should support |
| [`steering/SPIKES.md`](steering/SPIKES.md) | Open research questions before the next phase of work |
| [`.specs/PHASE2_SPEC.md`](.specs/PHASE2_SPEC.md) | Phase 2 implementation specification (informed by spike outputs) |
| [`.specs/PHASE3_SPEC.md`](.specs/PHASE3_SPEC.md) | Phase 3 backlog — deferred items from Phase 2 |

## Project Overview

This is a knowledge capture and retrieval system for LLM interactions. It automatically extracts durable knowledge ("beats") from Claude sessions and stores them as structured notes in an Obsidian vault, making them searchable and injectable into future sessions. The scope is broad — any context where useful knowledge surfaces, not just programming work. The system hooks into Claude Code's PreCompact event as its primary automatic capture path.

## Build & Install

```bash
bash build.sh                  # build all .skill files + release tarball
bash build.sh --skills-only    # build .skill files only
bash build.sh --clean          # wipe dist/ before building
bash install.sh                # install to ~/.claude/
bash uninstall.sh [--yes]      # uninstall
```

There are no automated tests. Validate changes by running the extractor directly:

```bash
python3 extractors/extract_beats.py \
  --transcript <path-to-jsonl> \
  --session-id test-session \
  --trigger manual \
  --cwd /some/project/path
```

Pass `--beats-json <path>` instead of `--transcript` to skip transcript parsing and feed pre-extracted beats JSON directly.

Test the hook independently:
```bash
echo '{"transcript_path": "/path/to/transcript.jsonl", "session_id": "test-123", "trigger": "compact", "cwd": "/Users/dan/code/my-project"}' | \
  bash hooks/pre-compact-extract.sh
```

**Hot reload:** Skills load at session start — start a new Claude Code session after `install.sh`. The hook and `extract_beats.py` reload on each invocation. MCP server changes require restarting Claude Desktop.

## Architecture

### Data Flow

```
Claude Code session
  → PreCompact event fires hooks/pre-compact-extract.sh
  → invokes extractors/extract_beats.py with transcript path
  → calls Claude (Haiku) to extract beats as JSON
  → writes .md files to Obsidian vault
```

Beats are routed based on scope:
- `scope: project` → project vault folder (from `.claude/knowledge.local.json`)
- `scope: general` → `inbox` folder (or `staging_folder` if project not configured)

### Key Files

- **`hooks/pre-compact-extract.sh`** — PreCompact hook entry point; reads hook context JSON from stdin, strips `CLAUDECODE` env var, calls the Python extractor; must always `exit 0` (non-zero blocks compaction)
- **`extractors/extract_beats.py`** — Core engine; parses JSONL/text transcripts, calls LLM, writes vault notes
- **`prompts/extract-beats-system.md`** / **`extract-beats-user.md`** — LLM prompts for beat extraction (edit these to change extraction behavior)
- **`prompts/autofile-system.md`** / **`autofile-user.md`** — Prompts for intelligent autofile mode
- **`mcp/server.py`** — FastMCP server for Claude Desktop integration; wraps the same extraction logic; runs in `~/.claude/mcp-venv/` (Homebrew Python, requires restart after changes)
- **`skills/kg-*/SKILL.md`** — Slash command definitions for `/kg-recall`, `/kg-file`, `/kg-extract`, `/kg-claude-md`, `/kg-enrich`
- **`scripts/import-desktop-export.py`** — Backfill vault from an Anthropic data export (`conversations.json`)

### Beat Types

The extractor recognizes exactly 6 types: `decision`, `insight`, `task`, `problem-solution`, `error-fix`, `reference`. Invalid types are rejected.

### Configuration

Global config at `~/.claude/knowledge.json`:
```json
{
  "vault_path": "/path/to/vault",
  "inbox": "AI/Claude-Sessions",
  "staging_folder": "AI/Claude-Inbox",
  "backend": "claude-cli",
  "claude_model": "claude-haiku-4-5",
  "claude_timeout": 120,
  "claude_allowed_tools": "",
  "autofile": false,
  "daily_journal": false,
  "journal_folder": "AI/Journal",
  "journal_name": "%Y-%m-%d"
}
```

Notes:
- `claude_model` is used by the `claude-cli` backend (default). The `anthropic` and `bedrock` backends use the key `model` instead.
- `claude_allowed_tools` controls which tools the `claude -p` subprocess may use (passed as `--tools`). Defaults to `""` (no tools). The extraction prompt is pure text→JSON and needs no tools; keeping this empty also prevents the subprocess from sending PermissionRequest IPC events to the parent session's TUI, which would cause it to hang in hook/MCP contexts. Only set this if you have customised the extraction prompt to require specific tools.

Per-project config at `.claude/knowledge.local.json` (searched up the directory tree):
```json
{
  "project_name": "my-project",
  "vault_folder": "Projects/my-project/Claude-Notes"
}
```

### LLM Backends

Three backends in `extract_beats.py`, selected via `backend` config key:
- `claude-cli` (default) — shells out to `claude` CLI; no API key needed; uses `claude_model` config key
- `anthropic` — uses `anthropic` Python SDK directly; requires `ANTHROPIC_API_KEY`; uses `model` config key
- `bedrock` — uses `anthropic` SDK with Bedrock; requires AWS credentials; uses `model` config key

### Claude Code Environment Variables

When `claude -p` is spawned as a subprocess from inside an active Claude Code session, several inherited environment variables cause it to hang or fail:

- `CLAUDECODE=1` — triggers a nested-session guard that blocks startup
- `CLAUDE_CODE_ENTRYPOINT=cli` — prevents the child process from establishing API connections (see [issue #26190](https://github.com/anthropics/claude-code/issues/26190))
- `CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY` / `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` — additional vars that contribute to API connection failures

`_call_claude_cli()` strips all four before launching the subprocess. Skills running inside an active session still **cannot** spawn `claude -p` subprocesses (they run synchronously in the same process group) — they must use Claude's in-context tools (Grep, Read, Edit, Write) instead.

### Skills vs MCP

Skills (`skills/`) are for Claude Code CLI slash commands. The MCP server (`mcp/`) exposes the same functionality to Claude Desktop. Both are built/distributed separately.

### Vault Note Format

Each beat becomes a markdown file with YAML frontmatter containing `id`, `date`, `session_id`, `type`, `scope`, `title`, `project`, `cwd`, `tags`, `related`, `status`, `summary` fields, followed by a structured markdown body.

## Distribution

Skills are packaged as `.skill` zip archives. The release tarball includes all hooks, extractors, prompts, and skills. `install.sh` copies files to `~/.claude/` and registers the PreCompact hook in `~/.claude/settings.json`.

The project can also be loaded as a Claude Code plugin without installing:
```bash
claude --plugin-dir ~/code/knowledge-graph
```
Skills appear namespaced in this mode: `/knowledge-graph:kg-recall` etc.
