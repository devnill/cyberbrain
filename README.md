# Claude Code Knowledge Graph

A knowledge capture and retrieval system for LLM interactions. It extracts structured knowledge from Claude sessions automatically, stores it as Obsidian-compatible markdown, and makes it retrievable in future sessions via slash commands. While it integrates tightly with Claude Code, the vault is designed to hold knowledge from any source — technical work, research, writing, or any domain where you want to remember what you've learned.

→ **New here? See [QUICKSTART.md](QUICKSTART.md).**

---

## How it works

```
Session in progress
       │
       ▼  (context fills or /compact)
PreCompact hook fires
       │
       ▼
~/.claude/hooks/pre-compact-extract.sh
       │  reads transcript path from hook stdin
       ▼
~/.claude/extractors/extract_beats.py
       │  parses transcript JSONL
       │  calls Claude (Haiku) to extract "beats"
       │  routes beats by scope (project vs. general)
       ▼
Obsidian vault/
  Projects/<project>/Claude-Notes/    ← project-scoped beats
  AI/Claude-Sessions/                 ← general beats (inbox)
       │
       ▼  (next session)
/cb-recall <query>
       │  grep-based search across vault
       ▼
Relevant beats injected into context
```

Extraction happens automatically on every compaction — both auto and manual. You'll see **"Extracting knowledge before compaction..."** in the Claude Code status bar while it runs.

A `SessionEnd` hook also fires when a session ends without compacting, so no session is missed.

---

## Requirements

- Python 3.8+
- Claude Code (the `claude` CLI)
- An Obsidian vault, or any directory for plain-markdown storage
- **Optional**: AWS credentials for the `bedrock` backend, or Ollama for the `ollama` backend. The default `claude-code` backend uses your active Claude Code session — no separate API key needed.

---

## Installation

```bash
bash install.sh
```

The installer:
1. Builds and installs all skills, hooks, prompts, and the extractor into `~/.claude/`
2. Registers the `PreCompact` and `SessionEnd` hooks in `~/.claude/settings.json`
3. Creates `~/.claude/cyberbrain.json` with a placeholder vault path (if not already present)
4. Installs the MCP server into `~/.claude/cyberbrain/` and registers it in Claude Desktop (macOS)

After installation, set `vault_path` in `~/.claude/cyberbrain.json` before the system will run.

---

## Uninstallation

```bash
bash uninstall.sh
```

Pass `--yes` to skip the confirmation prompt. The uninstaller removes all installed files and surgically removes the hook entries from `~/.claude/settings.json`.

---

## Configuration

### Global config — `~/.claude/cyberbrain.json`

```json
{
  "vault_path": "/Users/you/Documents/MyVault",
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

| Field | Default | Description |
|---|---|---|
| `vault_path` | *(required)* | Absolute path to your Obsidian vault root |
| `inbox` | `"AI/Claude-Sessions"` | Where general beats go (not project-specific) |
| `backend` | `"claude-code"` | LLM backend: `"claude-code"`, `"bedrock"`, or `"ollama"` |
| `model` | `"claude-haiku-4-5"` | Model name passed to the backend |
| `claude_timeout` | `120` | Seconds before the LLM call times out |
| `autofile` | `false` | Use LLM to route beats into existing vault folders instead of flat inbox |
| `daily_journal` | `false` | Append a session entry to a daily journal note after each extraction |
| `journal_folder` | `"AI/Journal"` | Vault-relative folder for journal notes |
| `journal_name` | `"%Y-%m-%d"` | Journal filename pattern (strftime format) |
| `bedrock_region` | `"us-east-1"` | AWS region — only used when `backend` is `"bedrock"` |
| `ollama_url` | `"http://localhost:11434"` | Ollama endpoint — only used when `backend` is `"ollama"` |

---

### Per-project config — `.claude/cyberbrain.local.json`

Add this file to a project root to route that project's beats into a dedicated vault folder:

```json
{
  "project_name": "my-app",
  "vault_folder": "Projects/my-app/Claude-Notes"
}
```

Copy `cyberbrain.local.example.json` from this repo as a starting point. Add `cyberbrain.local.json` to your project's `.gitignore` — it contains local paths and is not meant to be committed.


---

## Setting up with an existing Obsidian vault

1. Set `vault_path` in `~/.claude/cyberbrain.json`
3. Run `/cb-setup` in a Claude Code session to analyze your vault's existing structure and generate a `CLAUDE.md` at the vault root. This document teaches Claude your vault's conventions so that future beats and `/cb-file` notes stay consistent with what you already have

---

## Setting up with a new Obsidian vault

1. Create a new vault in Obsidian (an empty vault is fine)
2. Set `vault_path` in `~/.claude/cyberbrain.json`
3. The default folder structure works well to start — beats will appear in `AI/Claude-Sessions/`
4. Run `/cb-setup` after a few sessions to generate a `CLAUDE.md` once there's enough content to analyze

---

## Skills

Six slash commands are installed into Claude Code. Invoke them in any Claude Code session.

### `/cb-extract [path] [--dry-run]`

Extract knowledge beats from a session and save them to the vault.

```
/cb-extract                        # current session
/cb-extract --dry-run              # preview without writing
/cb-extract ~/.claude/projects/-Users-me-code-myapp/abc123.jsonl
/cb-extract ~/Downloads/export.jsonl --cwd ~/code/my-app
```

With no arguments, the skill finds the active session's transcript automatically (most recently modified JSONL in the current project's folder). With a path, use it to backfill from sessions that predate the automatic hook, or from logs exported from Claude Desktop or other sources.

`--dry-run` runs the full extraction pipeline — parses transcript, calls LLM, computes routing — but writes nothing. Shows the complete beat content so you can evaluate quality before committing.

---

### `/cb-recall <query>`

Search the vault and inject relevant context from previous sessions.

```
/cb-recall redis cache expiry
/cb-recall auth token decisions
```

Searches vault notes by keyword across titles, summaries, tags, and body content. Returns summary cards for all matches, with full body content for the top 1–2 most relevant results. Results are wrapped in a security demarcation block so Claude treats them as reference data, not instructions.

Call this when returning to a topic you've worked on before, or when you hit a problem and want to know if you've solved something similar.

---

### `/cb-file [--dry-run] [--type TYPE] [--folder PATH]`

Manually file any piece of information into your vault.

Trigger phrases: "save this", "file this", "add to my notes", "capture this".

The skill reads your vault's `CLAUDE.md` for type vocabulary and filing conventions, classifies the input, generates YAML frontmatter and a structured body, and writes the note. Use `--dry-run` to preview without writing.

---

### `/cb-enrich [--since DATE] [--dry-run]`

Backfill metadata on vault notes that are missing `type`, `summary`, or `tags`.

```
/cb-enrich
/cb-enrich --since 2026-01-01
/cb-enrich --dry-run
```

Scans notes in the vault and enriches those with incomplete frontmatter so they surface correctly in `/cb-recall` queries. Reads vault `CLAUDE.md` for type vocabulary. `--since` filters by file modification time.

---

### `/cb-setup [--types TYPE1,TYPE2,...] [--dry-run]`

Analyze your vault and generate or update a `CLAUDE.md` at the vault root.

```
/cb-setup
/cb-setup --dry-run
/cb-setup --types decision,insight,problem,reference
```

Runs `scripts/analyze_vault.py` against the vault, deep-reads a sample of notes, and generates a `CLAUDE.md` that documents your vault's entity types, naming conventions, tag taxonomy, and filing rules. The `CLAUDE.md` is read by the extractor and `/cb-file` before every write, keeping all future notes consistent with your existing structure.

Use `--types` to specify the type vocabulary directly instead of inferring it from existing notes.

---

## Beat types

When the PreCompact hook fires, Claude (Haiku) reads the session transcript and identifies "beats" — moments worth preserving. The default type vocabulary:

| Type | What it captures |
|---|---|
| `decision` | An architectural or design choice made, with rationale |
| `insight` | A non-obvious understanding or pattern that emerged |
| `problem` | A problem encountered — open or resolved |
| `reference` | A useful fact, config value, snippet, or command to remember |

If your vault's `CLAUDE.md` defines a different type vocabulary, the extractor uses that instead. This keeps beat types consistent with how you organize the rest of your vault.

Each beat is written as a markdown file with YAML frontmatter:

```markdown
---
id: <uuid>
date: 2026-02-25T13:34:00
session_id: abc123
type: decision
scope: project
title: "Use raw_decode() for LLM JSON response parsing"
project: cyberbrain
cwd: /Users/dan/code/cyberbrain
tags: ["json", "llm", "parsing", "robustness"]
related: []
status: completed
summary: "json.JSONDecoder().raw_decode() tolerates trailing explanation text after the JSON blob."
---

## Decision

Use `json.JSONDecoder().raw_decode()` to parse LLM responses...
```

---

## Autofile

When `"autofile": true` is set in `~/.claude/cyberbrain.json`, beats are routed into existing vault folders using an LLM filing decision rather than dropped flat into the inbox.

The autofile process:
1. Searches the vault for existing notes that thematically match the beat (by keyword)
2. Passes the top candidates to the LLM along with the vault's `CLAUDE.md`
3. The LLM chooses: create a new note, extend an existing one, or use the inbox
4. On collision (two beats targeting the same file), extends if tag overlap ≥ 2; otherwise creates a more specific title

Autofile adds one LLM call per beat. With the `claude-code` backend, this costs nothing extra beyond the time it takes. With API-based backends, expect roughly 2× the token usage of flat extraction.

---

## Capturing Claude.ai and mobile sessions

Claude Code sessions are captured automatically. Sessions from Claude.ai (web, iOS, Android) require a periodic export.

**Step 1: Request a data export**

Go to **claude.ai → Settings → Privacy → Export Data**.
The export ZIP arrives by email, typically within a few hours.

**Step 2: Run the import script**

Extract the ZIP and run:

```bash
python3 scripts/import.py --export ~/Downloads/claude-export/ --format claude
```

The script tracks which conversations have already been processed. Re-running on a newer export safely skips already-imported conversations.

**ChatGPT history:**

```bash
python3 scripts/import.py --export ~/Downloads/chatgpt-export/ --format chatgpt
```

**Flags:**

| Flag | Description |
|---|---|
| `--export PATH` | Path to the export directory or conversations file |
| `--format claude\|chatgpt` | Source format |
| `--dry-run` | Preview extractions without writing |
| `--limit N` | Process at most N conversations |
| `--since YYYY-MM-DD` | Skip conversations older than this date |
| `--cwd PATH` | Working directory context for project routing |

---

## Backends

### `claude-code` (default — no API key required)

Shells out to `claude -p`, which uses your active Claude Code subscription. No additional API key needed.

```json
{
  "backend": "claude-code",
  "model": "claude-haiku-4-5",
  "claude_timeout": 120
}
```

### `bedrock`

Uses the Anthropic SDK with AWS Bedrock. Requires AWS credentials (`~/.aws/credentials`, env vars, or IAM role).

```json
{
  "backend": "bedrock",
  "model": "us.anthropic.claude-haiku-4-5-20251001",
  "bedrock_region": "us-east-1"
}
```

### `ollama`

Calls a local Ollama instance. No API key or cloud dependency.

```json
{
  "backend": "ollama",
  "model": "llama3.2",
  "ollama_url": "http://localhost:11434"
}
```

Requires Ollama running locally with a model pulled (`ollama pull llama3.2`). Quality of extraction varies by model — models with strong instruction-following and JSON output work best.

---

## MCP server (Claude Desktop)

The installer registers a FastMCP server in Claude Desktop, exposing three tools:

| Tool | Description |
|---|---|
| `kg_extract(transcript_path)` | Extract beats from a transcript file |
| `kg_file(content, instructions?)` | File a piece of text into the vault |
| `kg_recall(query, max_results?)` | Search the vault |

Restart Claude Desktop after installation for the MCP server to appear.

---

## Troubleshooting

**No beats appear after /compact**

- Confirm `vault_path` in `~/.claude/cyberbrain.json` points to a real directory
- Confirm the hook is registered: `cat ~/.claude/settings.json | python3 -m json.tool | grep -A5 PreCompact`
- For `claude-code` backend: confirm `claude` is in PATH: `which claude`
- For `bedrock`: confirm AWS credentials work: `aws sts get-caller-identity`
- For `ollama`: confirm Ollama is running: `curl http://localhost:11434/api/tags`

**"Reached max turns" or backend error**

The session transcript may be very long. Add or increase `claude_timeout` in `~/.claude/cyberbrain.json`:

```json
{ "claude_timeout": 180 }
```

**Beats land in inbox instead of project folder**

Confirm `.claude/cyberbrain.local.json` exists in the project root (or a parent directory up to `~`), and that `project_name` and `vault_folder` are both set.

**"Prompt file not found" error**

The extractor looks for prompts at `~/.claude/prompts/`. Reinstall to ensure they were copied: `bash install.sh`

**Skills not found after install**

Skills load at session start. Open a new Claude Code session after running `bash install.sh`.

---

## File reference

| File | Purpose |
|---|---|
| `install.sh` | Installer |
| `uninstall.sh` | Uninstaller |
| `QUICKSTART.md` | Fast-path setup guide |
| `cyberbrain.example.json` | Template for `~/.claude/cyberbrain.json` |
| `cyberbrain.local.example.json` | Template for per-project `.claude/cyberbrain.local.json` |
| `hooks/pre-compact-extract.sh` | PreCompact hook entry point |
| `hooks/session-end-extract.sh` | SessionEnd hook entry point |
| `extractors/extract_beats.py` | Transcript parser, LLM caller, and vault writer |
| `extractors/requirements.txt` | Python dependencies |
| `prompts/extract-beats-system.md` | System prompt for beat extraction |
| `prompts/extract-beats-user.md` | User message template for beat extraction |
| `prompts/autofile-system.md` | System prompt for autofile filing decisions |
| `prompts/enrich-system.md` | System prompt for `/cb-enrich` |
| `prompts/claude-desktop-project.md` | Recommended Claude Desktop Project system prompt |
| `mcp/server.py` | FastMCP server for Claude Desktop |
| `scripts/import.py` | Import Claude or ChatGPT export into the vault |
| `skills/cb-extract/SKILL.md` | `/cb-extract` skill |
| `skills/cb-recall/SKILL.md` | `/cb-recall` skill |
| `skills/cb-file/SKILL.md` | `/cb-file` skill |
| `skills/cb-enrich/SKILL.md` | `/cb-enrich` skill |
| `skills/cb-setup/SKILL.md` | `/cb-setup` skill |
| `skills/cb-setup/scripts/analyze_vault.py` | Vault structure analyzer |
| `skills/cb-setup/references/` | Output structure spec and `CLAUDE.md` template |
