# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Specification

The authoritative requirements document for this project is:

| Document | Purpose |
|---|---|
| [`.specs/v1_spec.md`](.specs/v1_spec.md) | V1 specification — UX requirements, feature scope, architecture decisions, success criteria |

Read `.specs/v1_spec.md` before making any significant changes. It supersedes all prior steering documents and phase specs.

---

## Project Overview

A knowledge capture and retrieval system for LLM interactions. It automatically extracts durable knowledge ("beats") from Claude sessions and stores them as structured Obsidian markdown notes, making that knowledge searchable and injectable into future sessions.

The system exposes five slash command skills (`/cb-recall`, `/cb-file`, `/cb-extract`, `/cb-setup`, `/cb-enrich`), an MCP server for Claude Desktop, a PreCompact hook for automatic capture, and CLI import scripts for Claude and ChatGPT data exports.

---

## Build & Install

```bash
bash build.sh                  # build all .skill files + release tarball
bash build.sh --skills-only    # build .skill files only
bash build.sh --clean          # wipe dist/ before building
bash install.sh                # install to ~/.claude/
bash uninstall.sh [--yes]      # uninstall
```

**Validate the extractor directly:**
```bash
python3 extractors/extract_beats.py \
  --transcript <path-to-jsonl> \
  --session-id test-session \
  --trigger manual \
  --cwd /some/project/path
```

Pass `--beats-json <path>` instead of `--transcript` to skip transcript parsing and feed pre-extracted beats JSON directly.

**Test the hook independently:**
```bash
echo '{"transcript_path": "/path/to/transcript.jsonl", "session_id": "test-123", "trigger": "compact", "cwd": "/Users/dan/code/my-project"}' | \
  bash hooks/pre-compact-extract.sh
```

**Run the test suite:**
```bash
python3 -m pytest tests/
```

**Hot reload:** Skills load at session start — start a new Claude Code session after `install.sh`. The hook and `extract_beats.py` reload on each invocation. MCP server changes require restarting Claude Desktop.

---

## Architecture

### Data Flow

```
Claude Code session
  → PreCompact event fires hooks/pre-compact-extract.sh
  → invokes extractors/extract_beats.py with transcript path
  → calls LLM (via configured backend) to extract beats as JSON
  → writes .md files to Obsidian vault
```

Beat routing:
- `scope: project` → project vault folder (from `.claude/cyberbrain.local.json`)
- `scope: general` → `inbox` folder (warn and skip if inbox is not configured)

### Key Files

| File | Purpose |
|---|---|
| `hooks/pre-compact-extract.sh` | PreCompact hook; reads hook context JSON from stdin, strips nested-session env vars, calls extractor; always exits 0 |
| `extractors/extract_beats.py` | Core engine; parses JSONL/text transcripts, calls LLM backend, writes vault notes, daily journal |
| `prompts/extract-beats-system.md` / `extract-beats-user.md` | Extraction LLM prompts — edit to change extraction behavior |
| `prompts/autofile-system.md` / `autofile-user.md` | Autofile routing prompts |
| `mcp/server.py` | FastMCP server for Claude Desktop; wraps extraction logic; runs in `~/.claude/cyberbrain/venv/` |
| `skills/cb-recall/SKILL.md` | `/cb-recall` slash command |
| `skills/cb-file/SKILL.md` | `/cb-file` slash command |
| `skills/cb-extract/SKILL.md` | `/cb-extract` slash command |
| `skills/cb-setup/SKILL.md` | `/cb-setup` slash command (vault analyzer + CLAUDE.md generator) |
| `skills/cb-enrich/SKILL.md` | `/cb-enrich` slash command |
| `scripts/import.py` | Unified import for Claude Desktop and ChatGPT data exports |
| `tests/` | Test suite — unit and integration tests with mocked LLM calls |

### Beat Types

The extractor uses 4 types (defined by the vault's CLAUDE.md; these are the defaults):

| Type | What it captures |
|---|---|
| `decision` | A choice made between alternatives, with rationale |
| `insight` | A non-obvious understanding or pattern discovered |
| `problem` | Something broken, blocked, or constrained — with or without resolution |
| `reference` | A fact, command, snippet, or configuration detail for future lookup |

### Configuration

Global config at `~/.claude/cyberbrain.json`:
```json
{
  "vault_path": "/path/to/vault",
  "inbox": "AI/Claude-Sessions",
  "backend": "claude-code",
  "model": "claude-haiku-4-5",
  "claude_timeout": 120,
  "autofile": false,
  "daily_journal": false,
  "journal_folder": "AI/Journal",
  "journal_name": "%Y-%m-%d"
}
```

Per-project config at `.claude/cyberbrain.local.json` (searched up the directory tree from the session's cwd):
```json
{
  "project_name": "my-project",
  "vault_folder": "Projects/my-project/Claude-Notes"
}
```

### LLM Backends

Three backends, selected via `backend` config key:

| Backend | Key | Auth | Notes |
|---|---|---|---|
| `claude-code` | `model` | None (uses active session) | Default; shells out to `claude -p` |
| `bedrock` | `model` | AWS credentials | Anthropic SDK + Bedrock |
| `ollama` | `model`, `ollama_url` | None | Local inference; default URL `http://localhost:11434` |

### Claude Code Environment Variables

When `claude -p` is spawned as a subprocess, these inherited env vars cause hangs and must be stripped before the subprocess launches:

- `CLAUDECODE`
- `CLAUDE_CODE_ENTRYPOINT`
- `CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY`
- `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`

The `claude-code` backend strips all four. Skills running inside an active session cannot spawn `claude -p` subprocesses — they use Claude's in-context tools (Grep, Read, Edit, Write) instead.

**Architectural constraint:** Skills never write vault files directly using Claude's Write tool. All vault writes go through `extract_beats.py` or `import.py`. This ensures path validation, logging, and error fallback are consistently enforced in Python.

### Skills vs MCP

Skills (`skills/`) are slash commands for Claude Code CLI. The MCP server (`mcp/`) exposes the same capabilities to Claude Desktop. Both are built and distributed separately.

---

## Distribution

Skills are packaged as `.skill` zip archives. The release tarball includes hooks, extractors, prompts, skills, and the MCP server. `install.sh` copies files to `~/.claude/` and registers the PreCompact hook in `~/.claude/settings.json`.

Plugin mode (no install required):
```bash
claude --plugin-dir ~/code/cyberbrain
```
Skills appear namespaced: `/cyberbrain:cb-recall` etc.
