# Knowledge Graph Memory System

## Overview

A two-component system that extracts structured knowledge from Claude Code sessions before compaction and makes it retrievable in future sessions.

**Problem**: Auto-compaction discards nuance and detail from long sessions. Context anxiety sets in as the window fills. Knowledge produced across sessions isn't reused.

**Solution**: Extract meaningful "beats" from the conversation transcript before compaction, store them as Obsidian-compatible markdown, and retrieve them on demand with `/kg-recall`.

---

## Architecture

```
Session in progress
       │
       ▼ (context fills or /compact)
PreCompact hook fires
       │
       ▼
~/.claude/hooks/pre-compact-extract.sh
       │  reads transcript path from hook stdin
       ▼
~/.claude/extractors/extract_beats.py
       │  parses transcript JSONL
       │  calls Claude API (haiku) to extract beats
       │  routes beats by scope (project vs general)
       ▼
<obsidian_vault>/
  Projects/<project>/Claude-Notes/    ← project beats
  AI/Claude-Sessions/                 ← general beats
  AI/Claude-Inbox/                    ← staging (no project config)
       │
       ▼ (later, in a new session)
/kg-recall <query>
       │  grep-based search across vault
       ▼
Relevant beats injected into context
```

---

## Configuration

### Global: `~/.claude/knowledge.json`

```json
{
  "vault_path": "/path/to/your/ObsidianVault",
  "inbox": "AI/Claude-Sessions",
  "staging_folder": "AI/Claude-Inbox"
}
```

### Per-project: `.claude/knowledge.local.json` (gitignored)

```json
{
  "project_name": "my-project",
  "vault_folder": "Projects/my-project/Claude-Notes"
}
```

Without a project config, beats land in `staging_folder` for manual triage.

---

## Beat Types

| Type | Description |
|------|-------------|
| `decision` | Architectural or design choice made |
| `insight` | Non-obvious understanding gained |
| `task` | Completed work unit with outcome |
| `problem-solution` | Problem + how it was solved |
| `error-fix` | Bug or error + the fix |
| `reference` | Useful fact, config, or snippet to remember |

---

## Beat Document Format

```markdown
---
id: <uuid4>
date: 2026-02-25T13:34:00
session_id: abc123
type: error-fix
scope: project
title: Fix auth token expiry race condition
project: api-service
cwd: /Users/dan/code/api-service
tags: [auth, redis, cache]
related: []
status: completed
summary: Token TTL was in seconds but Redis expected ms; fixed by multiplying × 1000 in cache layer.
---

## Fix: Auth Token Expiry Race Condition

### Problem
...

### Solution
...

### Key Detail
...
```

---

## Files

| File | Purpose |
|------|---------|
| `~/.claude/knowledge.json` | Global config |
| `~/.claude/hooks/pre-compact-extract.sh` | Hook entry point |
| `~/.claude/extractors/extract_beats.py` | Python extraction logic |
| `~/.claude/extractors/requirements.txt` | Python dependencies |
| `~/.claude/prompts/extract-beats-system.md` | Extraction system prompt |
| `~/.claude/prompts/extract-beats-user.md` | Extraction user template |
| `~/.claude/skills/kg-recall/SKILL.md` | `/kg-recall` skill |
| `~/.claude/skills/kg-file/SKILL.md` | `/kg-file` skill |
| `~/.claude/skills/kg-claude-md/SKILL.md` | `/kg-claude-md` skill |
| `.claude/knowledge.local.json` | Per-project config (template below) |

---

## Setup

### 1. Install Python dependencies

```bash
pip install -r ~/.claude/extractors/requirements.txt
```

### 2. Set your vault path

Edit `~/.claude/knowledge.json` and set `vault_path` to your Obsidian vault root.

### 3. Set your API key

The extractor uses `ANTHROPIC_API_KEY` from the environment. Make sure it's set in your shell profile.

### 4. Configure a project (optional)

Copy `.claude/knowledge.local.json` into any project's `.claude/` directory and update `project_name` and `vault_folder`.

### 5. Make the hook executable

```bash
chmod +x ~/.claude/hooks/pre-compact-extract.sh
```

---

## Usage

**Ingest** happens automatically on compaction (both auto and manual). You'll see "Extracting knowledge before compaction..." in the status bar.

**Retrieval**: In any Claude Code session, run:

```
/kg-recall <topic or keywords>
```

Examples:
- `/kg-recall redis cache`
- `/kg-recall auth token expiry`
- `/kg-recall api-service decisions`

---

## Future: Phase 2 (MCP + Semantic Search)

The beat schema is designed for a future upgrade:
- `id` field = stable key for vector DB
- `summary` field = optimized for embedding (information-dense single sentence)
- `tags` + `type` = hybrid retrieval filters

Add an MCP server later that embeds summaries at write time and exposes a `search_knowledge` tool. The `/kg-recall` skill can delegate to it transparently.

---

*Generated: 2026-02-25*
