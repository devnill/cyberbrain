# Project Overview

This document describes what the knowledge-graph project is, why it exists, how it works, and how users interface with it. It is the definitive high-level reference for the project — read this first before diving into implementation details.

For the motivating goals behind decisions described here, see [GOALS.md](GOALS.md). For concrete scenarios, see [USE_CASES.md](USE_CASES.md). For open research questions, see [SPIKES.md](SPIKES.md).

---

## What This Is

A knowledge capture and retrieval system for LLM interactions. It automatically extracts durable knowledge from Claude sessions and stores it as structured notes in an Obsidian vault — making that knowledge searchable and injectable into future sessions.

Every productive conversation with an LLM produces signal: decisions made and their rationale, problems solved, patterns discovered, facts worth remembering. Almost all of it evaporates when the session ends. This project captures that signal as a byproduct of normal work, without requiring the user to do anything.

The scope is intentionally broad. While the current implementation focuses on Claude Code sessions (where hooks can fire automatically), the design supports any context where useful knowledge surfaces: technical work, research, writing, planning, learning. The vault is source-agnostic — a fact filed via `/kg-file` from a web article and a fix extracted from a debugging session are equally first-class.

The core framing: this is not a note-taking tool. It is an extension of memory — one that compounds in value the longer you use it. A vault with a year of sessions behind it means you never re-research the same question twice, never re-litigate a decision you've already made, and can pick up any thread as if you'd just left it.

---

## Core Concepts

### Beats

A "beat" is the atomic unit of knowledge in the vault. Each beat captures one thing worth remembering. There are six types:

| Type | What it captures |
|---|---|
| `decision` | An architectural or design choice, with its rationale |
| `insight` | A non-obvious understanding or pattern that emerged |
| `task` | A completed unit of work and its outcome |
| `problem-solution` | A problem encountered and how it was solved |
| `error-fix` | A specific error or bug and the fix that resolved it |
| `reference` | A useful fact, command, config value, or snippet |

Each beat is a markdown file with structured YAML frontmatter (`id`, `type`, `scope`, `title`, `tags`, `summary`, `project`, etc.) and a human-readable body.

### The Vault

Beats are stored in an Obsidian vault — a folder of markdown files the user already has, or creates for this purpose. The vault is the canonical store. It is readable directly in Obsidian, queryable by the system's retrieval tools, and syncs across devices via any file sync solution (iCloud, Obsidian Sync, Dropbox, etc.).

Beat routing within the vault:
- **Project-scoped beats** → a per-project folder (e.g., `Projects/my-api/Claude-Notes/`)
- **General beats** → a general inbox folder (e.g., `AI/Claude-Sessions/`)
- **Unrouted beats** (no project config found) → a staging folder for manual triage

### Scope

Each beat is either `project`-scoped (specific to the project being worked on) or `general` (broadly applicable knowledge not tied to a specific codebase). The extraction LLM assigns scope. This determines where the beat lands in the vault.

---

## How It Works

### Phase 1: Extraction (automatic)

The primary capture path is automatic. When the user runs `/compact` in Claude Code, a PreCompact hook fires before the transcript is truncated:

```
User runs /compact
    │
    ▼
PreCompact hook fires
    │  (stdin: transcript path, session id, working directory)
    ▼
hooks/pre-compact-extract.sh
    │  strips CLAUDECODE env var, calls extractor
    ▼
extractors/extract_beats.py
    │  parses transcript JSONL
    │  calls Claude (Haiku) to extract beats as JSON
    │  routes each beat by scope + project config
    ▼
Obsidian vault
    │  project beats → vault_folder
    │  general beats → inbox
    │  no project config → staging_folder
```

The hook always exits 0 — it never blocks compaction even if extraction fails. The user sees "Extracting knowledge before compaction..." in the status bar while it runs.

**Extraction is transparent.** The user doesn't need to think about it. The vault grows as a byproduct of working normally.

### Phase 2: Retrieval (manual or proactive)

Knowledge is retrieved by searching the vault. The primary interface is the `/kg-recall` slash command:

```
/kg-recall <query>
    │
    ▼
Grep-based keyword search across vault files
    │  (searches title, summary, tags, body — in that priority order)
    ▼
Rank results (recency bias, project-first if in project)
    │
    ▼
Read top matching notes
    │
    ▼
Inject structured context into the active session
```

This is the moment the compounding value becomes concrete: prior knowledge from past sessions becomes available to the current one.

---

## User Interfaces

The project exposes four interfaces. They are complementary, not alternatives.

### 1. Automatic: The PreCompact Hook

**Who triggers it:** No one — it fires automatically on every `/compact`.

**What it does:** Extracts beats from the full session transcript before truncation. Files them to the vault.

**User action required:** None after initial setup.

---

### 2. Slash Commands (Claude Code Skills)

Four commands are available in any Claude Code session:

**`/kg-recall <query>`**
Search the vault and inject relevant context from previous sessions.
```
/kg-recall redis cache eviction
/kg-recall auth token expiry
/kg-recall api-service architecture decisions
```
Use this at the start of a session when returning to a project, or mid-session when you hit a problem you may have solved before.

---

**`/kg-file`**
Manually file any piece of information into the vault right now.

Trigger phrases: `"save this"`, `"file this"`, `"add to my notes"`, `"capture this"`, or `"log this"`.

```
/kg-file The retry logic silently drops jobs within the 30s idempotency window — this is by design, not a bug
```

Use this for insights you want to capture mid-session without waiting for compaction, or for knowledge from external sources (documentation, Stack Overflow, conversations).

---

**`/kg-extract [path]`**
Manually trigger extraction from a session transcript — the current session, or a specific transcript file.

```
/kg-extract                                     # current session
/kg-extract ~/.claude/projects/.../abc123.jsonl # specific transcript
```

Use this to capture a session before closing without compacting, to backfill from old transcripts, or to process plain-text chat logs.

---

**`/kg-claude-md`**
Analyze your Obsidian vault and generate a `CLAUDE.md` at the vault root. This document describes your vault's filing conventions so that `/kg-file` and autofile produce notes consistent with your existing structure.

Run this once after initial setup, then again periodically as the vault evolves.

---

### 3. MCP Server (Claude Desktop)

An MCP server exposes the same capabilities to Claude Desktop. The three MCP tools are:

| Tool | Equivalent to |
|---|---|
| `kg_recall(query, max_results)` | `/kg-recall` |
| `kg_file(content, ...)` | `/kg-file` |
| `kg_extract(transcript_path, ...)` | `/kg-extract` |

This enables LLM agents in Claude Desktop to consult the vault mid-task, not just at session start, and allows the vault to serve as external memory for any Claude interface that supports MCP.

---

### 4. Obsidian (Human Review Layer)

The vault is a folder of readable markdown files. Obsidian is the human interface for reviewing, curating, and browsing what's been captured:

- Read beats from a recent session to see what was learned
- Correct a miscategorized beat by editing its frontmatter
- Add rough notes directly, which can be enriched later
- Browse by project, tag, or type using Obsidian's native views
- Use Obsidian's wikilink graph to navigate related notes

Obsidian is not required for the system to function — the vault is just files — but it is the right tool for human review and curation.

---

## Configuration

**Global config** at `~/.claude/knowledge.json`:

```json
{
  "vault_path": "/Users/you/Documents/MyVault",
  "inbox": "AI/Claude-Sessions",
  "staging_folder": "AI/Claude-Inbox",
  "backend": "claude-cli",
  "claude_model": "claude-haiku-4-5",
  "autofile": false,
  "daily_journal": false
}
```

**Per-project config** at `<project>/.claude/knowledge.local.json`:

```json
{
  "project_name": "my-api",
  "vault_folder": "Projects/my-api/Claude-Notes"
}
```

The extractor walks up the directory tree from the session's working directory to find the nearest `knowledge.local.json`. Project-scoped beats route to `vault_folder`; general beats go to `inbox`.

**Key config options:**

| Key | Default | Purpose |
|---|---|---|
| `vault_path` | — | Required. Absolute path to your Obsidian vault |
| `inbox` | `"AI/Claude-Sessions"` | Where general beats land |
| `staging_folder` | `"AI/Claude-Inbox"` | Where beats land with no project config |
| `backend` | `"claude-cli"` | LLM backend: `claude-cli`, `anthropic`, or `bedrock` |
| `claude_model` | `"claude-haiku-4-5"` | Model for `claude-cli` backend |
| `autofile` | `false` | Use LLM to intelligently route beats into existing vault structure |
| `daily_journal` | `false` | Append a dated work log entry after each extraction |

---

## LLM Backends

Three backends for the extraction LLM, selected via the `backend` config key:

| Backend | Key | Auth required | Notes |
|---|---|---|---|
| `claude-cli` | `claude_model` | None (uses active Claude Code session) | Default. No API key needed |
| `anthropic` | `model` | `ANTHROPIC_API_KEY` | Direct SDK call |
| `bedrock` | `model` | AWS credentials | For AWS environments |

The `claude-cli` backend shells out to `claude -p`, which uses the same credentials as the active session. This is the default because it requires no additional setup.

---

## Autofile Mode

When `autofile: true`, extracted beats are not simply dropped into inbox folders. Instead, each beat goes through an intelligent filing step:

1. Search the vault for notes with matching tags and title keywords
2. Read the top 3 related notes
3. Load the vault's `CLAUDE.md` (or use default conventions)
4. Call the LLM to decide: **extend** an existing note, or **create** a new one
5. Execute the decision — append a section to an existing note, or write a new file at the right path
6. On any error, fall back to flat inbox write

Autofile is most useful once the vault has accumulated structure and you've run `/kg-claude-md` to document your filing conventions. On an empty vault, it behaves like the flat write path.

---

## Installation

```bash
cd ~/code/knowledge-graph
bash install.sh
```

The installer copies hooks, extractors, skills, prompts, and the MCP server to `~/.claude/`, registers the PreCompact hook in `~/.claude/settings.json`, and creates `~/.claude/knowledge.json` with a placeholder if it doesn't exist.

After installation:
1. Edit `~/.claude/knowledge.json` to set `vault_path`
2. Start a new Claude Code session (skills load at session start)
3. Optionally, add `.claude/knowledge.local.json` to any project you want project-scoped routing for

**Plugin mode** (no install required):
```bash
claude --plugin-dir ~/code/knowledge-graph
```
Skills become namespaced: `/knowledge-graph:kg-recall`, etc.

---

## What's Implemented vs. What's Planned

### Currently implemented and working

- PreCompact hook: automatic extraction on `/compact`
- `extract_beats.py`: transcript parsing, LLM extraction, vault writes
- 4 slash commands: `/kg-recall`, `/kg-file`, `/kg-extract`, `/kg-claude-md`
- MCP server: `kg_recall`, `kg_file`, `kg_extract` tools for Claude Desktop
- Autofile: LLM-driven extend/create routing
- Historical import: `scripts/import-desktop-export.py` for Anthropic data exports
- Daily journal: optional work log on each extraction
- 3 LLM backends: `claude-cli`, `anthropic`, `bedrock`
- Build + install pipeline

### Known gaps and planned work

These are captured as research questions in [SPIKES.md](SPIKES.md). The highest-priority gaps:

- **Session-end capture without compaction** (SP7): Sessions that close without `/compact` are not captured. The PreCompact hook is the only current trigger.
- **Mobile and Claude.ai capture** (SP5, UC19): Sessions on phone or Claude.ai web produce no vault beats. This is a primary usage gap.
- **Semantic retrieval** (SP12): Current retrieval is keyword grep. Semantically relevant notes using different vocabulary are missed.
- **Multi-device setup** (SP4): The system works per-machine. Getting it running on a second device requires manual setup.
- **Classification quality and review flow** (SP6): Some beats are miscategorized or misfiled. No human-in-the-loop review mechanism exists yet.
- **Daily journal debugging** (SP2): The daily journal feature may not be functioning correctly.
- **Full system audit** (SP3): No end-to-end verification that all components work as documented.

---

## Project Identity

The project is currently named "knowledge-graph" — a functional description of its mechanism. Whether this name accurately captures what the system *does for the user* (extend cognition, not file documents) is an open question addressed in [SPIKES.md](SPIKES.md) (SP1).

The goal framing from [GOALS.md](GOALS.md) is instructive: this system should feel like **consciousness expansion**, not archival (G10). The name, the command vocabulary, and the onboarding should communicate capability, not infrastructure.
