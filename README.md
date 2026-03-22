# Cyberbrain

Claude has memory, but it's bounded. Context windows fill. Sessions end. A static memory document can only hold so much before it becomes noise.

Cyberbrain extends Claude's native capabilities with a persistent, searchable knowledge layer built from your actual sessions:

- **Automatic capture** — hooks into Claude Code's compaction events to extract structured knowledge beats (decisions, insights, problems, references) without any manual effort
- **Dynamic context injection** — instead of a fixed memory document, you retrieve only what's relevant to the current task and load it on demand, keeping context lean and targeted
- **Structured search** — vault notes carry typed frontmatter, tags, summaries, and session metadata, enabling search that surfaces the right result rather than just the most recent match
- **Cross-session accumulation** — import from Claude Desktop and ChatGPT exports so everything you've worked through, across every interface, feeds the same store

The automatic hooks and slash commands are built for Claude Code. The MCP server works with any tool that supports the Model Context Protocol — Cursor, Zed, or anything else in the ecosystem.

The result is an external cognitive extension — a second brain that compounds across every conversation and grows more useful the longer you use it.

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
~/.claude/cyberbrain/extractors/extract_beats.py
       │  parses transcript JSONL
       │  calls Claude (Haiku) to extract "beats"
       │  routes beats by scope (project vs. general)
       ▼
Obsidian vault/
  Projects/<project>/Claude-Notes/    ← project-scoped beats
  AI/Claude-Sessions/                 ← general beats (inbox)
       │
       ▼  (next session)
cb_recall(query)  via MCP
       │  hybrid FTS5 + semantic search across vault
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
1. Installs hooks, prompts, extractors, and the MCP server into `~/.claude/cyberbrain/`
2. Registers the `PreCompact` and `SessionEnd` hooks in `~/.claude/settings.json`
3. Creates `~/.claude/cyberbrain/config.json` with a placeholder vault path (if not already present)
4. Registers the MCP server in Claude Desktop (macOS)
5. Creates a Python venv at `~/.claude/cyberbrain/venv/` and installs MCP dependencies

After installation, set `vault_path` in `~/.claude/cyberbrain/config.json` before the system will run.

---

## Uninstallation

```bash
bash uninstall.sh
```

Pass `--yes` to skip the confirmation prompt. The uninstaller removes all installed files and surgically removes the hook entries from `~/.claude/settings.json`.

---

## Configuration

### Global config — `~/.claude/cyberbrain/config.json`

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
  "journal_name": "%Y-%m-%d",
  "proactive_recall": true,
  "working_memory_folder": "AI/Working Memory",
  "working_memory_review_days": 28,
  "consolidation_log": "AI/Cyberbrain-Log.md",
  "consolidation_log_enabled": true,
  "trash_folder": ".trash"
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
| `proactive_recall` | `true` | Trigger cb_recall at session start when working in a known project domain |
| `bedrock_region` | `"us-east-1"` | AWS region — only used when `backend` is `"bedrock"` |
| `ollama_url` | `"http://localhost:11434"` | Ollama endpoint — only used when `backend` is `"ollama"` |
| `claude_path` | `"claude"` | Full path to the `claude` binary — set this when using the MCP server from Claude Desktop, which runs without your shell PATH |
| `working_memory_folder` | `"AI/Working Memory"` | Vault-relative folder for working memory beats (temporally relevant, not durable) |
| `working_memory_review_days` | `28` | Days until a working memory note is flagged for review |
| `consolidation_log` | `"AI/Cyberbrain-Log.md"` | Vault-relative path for the consolidation/review audit log |
| `consolidation_log_enabled` | `true` | Set `false` to disable the audit log |
| `trash_folder` | `".trash"` | Vault-relative folder for soft-deleted notes |
| `autofile_model` | *(uses `model`)* | Separate model for autofile routing decisions |
| `uncertain_filing_behavior` | `"inbox"` | What to do on low-confidence filing: `"inbox"` or `"ask"` |
| `uncertain_filing_threshold` | `0.7` | Confidence cutoff (0.0–1.0) below which `uncertain_filing_behavior` applies |
| `search_backend` | `"hybrid"` | Search backend: `"grep"`, `"fts5"`, or `"hybrid"` |
| `search_db_path` | `~/.claude/cyberbrain/search-index.db` | Path to the SQLite search index |
| `embedding_model` | `"TaylorAI/bge-micro-v2"` | Model for semantic embeddings (hybrid backend) |
| `quality_gate_enabled` | `true` | Run LLM-as-judge validation on curation output |
| `index_refresh_interval` | `3600` | Seconds before cb_recall triggers an incremental index refresh |
| `desktop_capture_mode` | `"suggest"` | Claude Desktop filing behavior: `"suggest"`, `"auto"`, or `"manual"` |

All config fields and their types are defined in the `CyberbrainConfig` TypedDict in `src/cyberbrain/extractors/config.py`.

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

1. Set `vault_path` in `~/.claude/cyberbrain/config.json`
2. Use `cb_setup` (via Claude Desktop or Claude Code MCP) to analyze your vault's existing structure and generate a `CLAUDE.md` at the vault root. This document teaches the system your vault's conventions so that future beats stay consistent with what you already have

---

## Setting up with a new Obsidian vault

1. Create a new vault in Obsidian (an empty vault is fine)
2. Set `vault_path` in `~/.claude/cyberbrain/config.json`
3. The default folder structure works well to start — beats will appear in `AI/Claude-Sessions/`
4. Use `cb_setup` after a few sessions to generate a `CLAUDE.md` once there's enough content to analyze

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

### Beat durability

Each beat is also classified by durability:

| Durability | What it means |
|---|---|
| `durable` | Passes the six-month test — useful to someone with no memory of this session, six months from now |
| `working-memory` | Current project state: open bugs, in-flight refactors, temporary workarounds, unvalidated hypotheses. Routed to a separate folder; reviewed periodically by `cb_review` |

Working memory beats are indexed and searchable like durable beats but live in `AI/Working Memory/`. The `cb_review` tool processes them when they're due, deciding whether to promote them to durable notes, extend the review window, or delete them.

### Beat frontmatter

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
cb_source: hook-extraction
cb_created: 2026-02-25T13:34:00
cb_session: abc123
---

## Decision

Use `json.JSONDecoder().raw_decode()` to parse LLM responses...
```

Provenance fields (`cb_source`, `cb_created`, `cb_session`) are written automatically. Working memory beats also carry `cb_ephemeral: true` and `cb_review_after: <date>`. Set `cb_lock: true` manually to exclude a note from consolidation and review.

---

## Working memory

Working memory beats are routed to a separate folder (`AI/Working Memory/`) rather than the inbox. They are indexed and searchable like durable beats but carry a review date (`cb_review_after`). Use `cb_review` to process them:

```
cb_review(dry_run=True)       # see what's due
cb_review(dry_run=False)      # process — LLM proposes promote / extend / delete per note
cb_review(days_ahead=7)       # also include notes due within 7 days
```

Promoted notes become durable vault notes. Deleted notes are logged to `AI/Cyberbrain-Log.md`.

---

## Vault preferences

Add a `## Cyberbrain Preferences` section to your vault's `CLAUDE.md` to guide extraction and consolidation behavior in natural language — no prompt editing required.

Manage it through `cb_configure`:

```
cb_configure(show_prefs=True)               # view current preferences
cb_configure(set_prefs="Only capture...")   # replace the entire section
cb_configure(reset_prefs=True)             # restore defaults
```

---

## Restructure

`cb_restructure` keeps the vault clean by doing two things in a single pass:

- **Merge**: clusters of related notes (many small notes on the same topic) are merged into one richer note or organized under a hub page
- **Split**: large notes covering multiple unrelated topics are broken into focused sub-notes

```
cb_restructure(dry_run=True)                    # preview proposed changes (always start here)
cb_restructure(folder="Projects/myapp")         # target a specific folder
cb_restructure(split_threshold=3000)            # min note size (chars) to be a split candidate
```

The tool uses semantic similarity to find clusters, then asks the LLM to decide how to restructure each cluster and each large note. Set `cb_lock: true` in a note's frontmatter to protect it from restructuring.

---

## Autofile

When `"autofile": true` is set in `~/.claude/cyberbrain/config.json`, beats are routed into existing vault folders using an LLM filing decision rather than dropped flat into the inbox.

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

The installer registers a FastMCP server in Claude Desktop, exposing eleven tools:

| Tool | Description |
|---|---|
| `cb_extract(transcript_path)` | Extract beats from a transcript file |
| `cb_file(content, instructions?)` | File a piece of text into the vault |
| `cb_recall(query, max_results?)` | Search the vault |
| `cb_read(identifier)` | Read a specific note by path or title |
| `cb_enrich(folder?, since?, dry_run?)` | Backfill missing metadata on existing notes |
| `cb_setup(vault_path?, dry_run?)` | Analyze vault and generate/update its CLAUDE.md |
| `cb_configure(...)` | View or change config, vault path, and preferences |
| `cb_status()` | Show vault health, index stats, and recent extraction runs |
| `cb_restructure(folder?, dry_run?, split_threshold?, folder_hub?, grouping?)` | Merge related note clusters and split large notes to keep the vault clean |
| `cb_review(days_ahead?, dry_run?, folder?)` | Review working memory notes that are due — promote, extend, or delete |
| `cb_reindex(rebuild?, prune?)` | Rebuild or prune the search index |

### Automatic setup (macOS)

`install.sh` writes the MCP server entry to Claude Desktop's config automatically:

```
~/Library/Application Support/Claude/claude_desktop_config.json
```

Restart Claude Desktop after installation. You'll see a hammer icon (🔨) in the chat input when the MCP server is connected.

### Manual setup

If you need to register the server by hand (or if `install.sh` skipped it because Claude Desktop wasn't running), open Claude Desktop's config file:

```bash
open ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

Or navigate there from Claude Desktop: **Settings → Developer → Edit Config**.

Add or merge the `cyberbrain` entry under `mcpServers`:

```json
{
  "mcpServers": {
    "cyberbrain": {
      "command": "/Users/you/.claude/cyberbrain/venv/bin/python",
      "args": ["/Users/you/.claude/cyberbrain/mcp/server.py"]
    }
  }
}
```

Replace `/Users/you` with your actual home directory path. Restart Claude Desktop to apply.

### Setting up a Claude Desktop project

For proactive vault recall and filing within Claude Desktop, create a **Project** and paste the system prompt from `prompts/claude-desktop-project.md` into the project's **Customize** field (Project settings → Customize → Custom instructions).

This instructs Claude to:
- Call `cb_recall` automatically when you mention a topic it may have notes on
- Call `cb_file` when you say "save this" or "capture this"
- Proactively surface past decisions when you return to a topic

The MCP tools are available in any Claude Desktop conversation once connected, but the project system prompt makes the behavior automatic rather than requiring you to ask explicitly.

---

## Troubleshooting

**No beats appear after /compact**

- Confirm `vault_path` in `~/.claude/cyberbrain/config.json` points to a real directory
- Confirm the hook is registered: `cat ~/.claude/settings.json | python3 -m json.tool | grep -A5 PreCompact`
- For `claude-code` backend: confirm `claude` is in PATH: `which claude`
- For `bedrock`: confirm AWS credentials work: `aws sts get-caller-identity`
- For `ollama`: confirm Ollama is running: `curl http://localhost:11434/api/tags`

**"Reached max turns" or backend error**

The session transcript may be very long. Add or increase `claude_timeout` in `~/.claude/cyberbrain/config.json`:

```json
{ "claude_timeout": 180 }
```

**Beats land in inbox instead of project folder**

Confirm `.claude/cyberbrain.local.json` exists in the project root (or a parent directory up to `~`), and that `project_name` and `vault_folder` are both set.

**MCP tools fail in Claude Desktop: "claude CLI not found"**

Claude Desktop spawns the MCP server without your shell's PATH, so the `claude` binary isn't found even though Claude Code is installed. The extractor tries common Homebrew locations automatically, but if yours differs, set the full path explicitly:

```json
{ "claude_path": "/opt/homebrew/bin/claude" }
```

Find your path by running `which claude` in a terminal. Apple Silicon Macs typically use `/opt/homebrew/bin/claude`; Intel Macs typically use `/usr/local/bin/claude`.

---

**"Prompt file not found" error**

The extractor looks for prompts at `~/.claude/cyberbrain/prompts/`. Reinstall to ensure they were copied: `bash install.sh`

---

## File reference

| File | Purpose |
|---|---|
| `install.sh` | Installer |
| `uninstall.sh` | Uninstaller |
| `QUICKSTART.md` | Fast-path setup guide |
| `ARCHITECTURE.md` | Detailed architecture documentation |
| `cyberbrain.example.json` | Template for `~/.claude/cyberbrain/config.json` |
| `cyberbrain.local.example.json` | Template for per-project `.claude/cyberbrain.local.json` |
| `hooks/pre-compact-extract.sh` | PreCompact hook entry point |
| `hooks/session-end-extract.sh` | SessionEnd hook entry point |
| `extractors/extract_beats.py` | Core engine entry point (re-exports all modules) |
| `extractors/extractor.py` | LLM-based beat extraction from transcripts |
| `extractors/backends.py` | LLM backend implementations (claude-code, bedrock, ollama) |
| `extractors/config.py` | Configuration loading and prompt file loading |
| `extractors/transcript.py` | JSONL transcript parsing |
| `extractors/vault.py` | Note writing, routing, filename generation, relations |
| `extractors/autofile.py` | LLM-driven filing decisions |
| `extractors/search_backends.py` | Search backends (grep, FTS5, hybrid) |
| `extractors/search_index.py` | Search index coordination and lifecycle |
| `extractors/analyze_vault.py` | Vault structure analyzer for cb_setup |
| `prompts/extract-beats-system.md` | System prompt for beat extraction |
| `prompts/autofile-system.md` | System prompt for autofile filing decisions |
| `prompts/enrich-system.md` | System prompt for `cb_enrich` |
| `prompts/restructure-*.md` | Prompts for `cb_restructure` (decide, generate, audit, group) |
| `prompts/review-system.md` | System prompt for `cb_review` |
| `prompts/claude-desktop-project.md` | Recommended Claude Desktop Project system prompt |
| `mcp/server.py` | FastMCP server entry point |
| `mcp/shared.py` | Bridge between MCP tools and extractor layer |
| `mcp/resources.py` | MCP resources and prompts |
| `mcp/tools/*.py` | MCP tool implementations (extract, file, recall, manage, setup, enrich, restructure, review, reindex) |
| `scripts/import.py` | Import Claude or ChatGPT export into the vault |
