# Claude Code Knowledge Graph

A memory system for Claude Code that survives context compaction. It extracts structured knowledge from sessions automatically, stores it as Obsidian-compatible markdown, and makes it retrievable in future sessions via slash commands.

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
       │  calls Claude API (Haiku) to extract "beats"
       │  routes beats by scope (project vs. general)
       ▼
Obsidian vault/
  Projects/<project>/Claude-Notes/    ← project-scoped beats
  AI/Claude-Sessions/                 ← general beats
  AI/Claude-Inbox/                    ← staging (no project config)
       │
       ▼  (next session)
/kg-recall <query>
       │  grep-based search across vault
       ▼
Relevant beats injected into context
```

Extraction happens automatically on every compaction — both auto and manual. You'll see **"Extracting knowledge before compaction..."** in the Claude Code status bar while it runs.

Three skills are also included for manual knowledge management: `/kg-recall` (retrieve), `/kg-file` (manually save anything), and `/kg-claude-md` (generate a guidance document for your vault).

---

## Requirements

- Python 3.8+
- **One of**: `ANTHROPIC_API_KEY` set in your shell environment *(default)*, or AWS credentials configured for Bedrock *(optional — see [API Authentication](#api-authentication) below)*
- An Obsidian vault (existing or new — see setup sections below)
- Claude Code

---

## Installation

Run the installer from the repo root:

```bash
bash install.sh
```

The installer:
1. Creates `~/.claude/hooks/`, `~/.claude/extractors/`, `~/.claude/prompts/`, `~/.claude/skills/`
2. Copies all files into place
3. Registers the `PreCompact` hook in `~/.claude/settings.json`
4. Creates `~/.claude/knowledge.json` with a placeholder vault path (if not already present)
5. Installs Python dependencies (`anthropic`, `pyyaml`)

After installation, complete the steps in the **Configuration** section below before the system will run.

---

## Uninstallation

```bash
bash uninstall.sh
```

Pass `--yes` to skip the confirmation prompt:

```bash
bash uninstall.sh --yes
```

The uninstaller removes all files copied by `install.sh`, surgically removes the `PreCompact` hook entry from `~/.claude/settings.json` (preserving other hooks and settings), and prunes any directories that are left empty. It does not uninstall pip packages (`anthropic`, `pyyaml`), since those may be used by other tools.

---

## Configuration

### Global config — `~/.claude/knowledge.json`

This is created by the installer. Edit it to point at your vault:

```json
{
  "vault_path": "/Users/you/Documents/MyVault",
  "inbox": "AI/Claude-Sessions",
  "staging_folder": "AI/Claude-Inbox"
}
```

| Field | Required | Description |
|---|---|---|
| `vault_path` | yes | Absolute path to your Obsidian vault root |
| `inbox` | yes | Where general beats go (not project-specific) |
| `staging_folder` | yes | Where beats land when there's no project config |
| `backend` | no | `"anthropic"` *(default)* or `"bedrock"` |
| `bedrock_region` | no | AWS region for Bedrock *(default: `"us-east-1"`)*; only used when `backend` is `"bedrock"` |
| `model` | no | Override the model ID; defaults to `claude-haiku-4-5` (direct) or `us.anthropic.claude-haiku-4-5-20251001` (Bedrock) |

The extractor will not run until `vault_path` is set to a real, existing directory.

---

## Setting up with an existing Obsidian vault

1. Open `~/.claude/knowledge.json` and set `vault_path` to your vault root:

   ```json
   {
     "vault_path": "/Users/you/Documents/MyVault",
     "inbox": "AI/Claude-Sessions",
     "staging_folder": "AI/Claude-Inbox"
   }
   ```

2. The folders named in `inbox` and `staging_folder` will be created automatically inside your vault the first time beats are written. They don't need to exist in advance.

3. Optionally, run `/kg-claude-md` in a Claude Code session to analyze your vault's existing structure and generate a `CLAUDE.md` at the vault root. This document teaches Claude your vault's conventions so that `/kg-file` and future notes stay consistent with what you already have.

4. To connect a specific project, see **Per-project configuration** below.

---

## Setting up with a new Obsidian vault

1. Create a new vault in Obsidian. An empty vault is fine — the system will build structure as you work.

2. Set `vault_path` in `~/.claude/knowledge.json` to the new vault root.

3. Decide on folder structure. The defaults work well to start:
   - `AI/Claude-Sessions/` — general session beats
   - `AI/Claude-Inbox/` — staging area for beats from projects without a config

4. If you plan to use `/kg-file` to manually add notes, skim the **Ontology** section below to understand the entity types and field conventions before you start, so your notes are consistent from the beginning.

5. After a few sessions, run `/kg-claude-md` to generate a `CLAUDE.md`. For a new vault this will be lightweight, but it's a good anchor to grow from.

---

## Per-project configuration

To route beats from a specific project into a dedicated vault folder rather than the staging inbox, add a `.claude/knowledge.local.json` file to the project root:

```json
{
  "project_name": "my-api",
  "vault_folder": "Projects/my-api/Claude-Notes"
}
```

Copy `knowledge.local.example.json` from this repo as a starting point. The file is gitignored by convention — add `knowledge.local.json` to your project's `.gitignore`.

When the extractor runs, it walks up from the session's working directory looking for this file. If found, project-scoped beats go to `vault_folder`; general beats (decisions, insights not tied to the project) still go to `inbox`.

Without this file, all beats land in `staging_folder` for you to triage manually.

---

## Skills

Four slash commands are installed into Claude Code. Invoke them in any Claude Code session.

### `/kg-extract [path]`

Extract knowledge beats from a chat session and save them to the vault.

**Current session** (no arguments):
```
/kg-extract
```

**Previous session** (path to transcript or exported log):
```
/kg-extract ~/.claude/projects/-Users-me-code-myapp/abc123.jsonl
/kg-extract ~/Downloads/old-session.jsonl --project my-api --cwd ~/code/my-api
/kg-extract ~/Downloads/chatlog.txt --project personal
```

With no arguments, the skill finds the active session's transcript automatically (most
recently modified JSONL in the current project's folder) and extracts beats from it.
This is useful mid-session to capture knowledge without waiting for compaction, or at
the end of a session before closing.

With a path, use it to backfill the knowledge base from sessions that predate the
automatic hook, or from chat logs exported from Claude Desktop or other sources.

The skill parses the conversation (Claude Code JSONL or plain text), applies the same
extraction criteria as the automatic hook, and writes beat files to the vault. Beats are
routed to the project folder if a per-project config is found for the given `--cwd`,
otherwise to the general or staging folder.

**Claude Code transcripts** live at `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`.
When you point the skill at one of these, the working directory and session ID are
decoded automatically from the path — no flags needed.

---

### `/kg-recall <query>`

Search the vault and inject relevant context from previous sessions.

```
/kg-recall redis cache
/kg-recall auth token expiry
/kg-recall api-service decisions
```

The skill reads `~/.claude/knowledge.json` to find the vault, searches by keywords in titles and summaries (highest signal), then by tags, then in body content. It reads up to 5 matching documents and synthesizes a structured context block — titles, types, dates, key findings, and source paths.

If no results are found, the skill says so clearly and reminds you that content will accumulate after your next compaction.

**When to use it**: At the start of a session when you're returning to a topic or project you've worked on before. Also useful mid-session when you hit a problem and want to know if you've solved something similar before.

---

### `/kg-file`

Manually file any piece of information into your vault as a structured Obsidian note.

Trigger phrases: `"save this"`, `"file this"`, `"add to my notes"`, `"capture this"`, `"log this"`, or any phrasing that implies you want something preserved.

The skill classifies the input into an entity type (see **Ontology** below), extracts structured fields, generates complete YAML frontmatter and a formatted body, suggests a canonical file path, and identifies wikilinks to create as stubs.

Example uses:
- Paste a decision you just made and say "file this"
- Describe a bug you solved and say "save this as a problem-solution"
- Ask Claude to summarize the current session and file it

The output is the complete note, ready to paste into Obsidian. The suggested file path follows the `type/kebab-case-title.md` convention.

---

### `/kg-claude-md`

Analyze your Obsidian vault and generate a `CLAUDE.md` at the vault root.

```
/kg-claude-md
```

The skill runs `scripts/analyze_vault.py` against your vault, which produces a structural report covering entity type distribution, tag usage, wikilink patterns, naming conventions, and orphan notes. It then deep-reads a sample of notes (scaled to vault size), synthesizes the findings, and generates a `CLAUDE.md` that documents:

- Your vault's actual entity types, required fields, and naming conventions
- Domain taxonomy and tag namespaces
- Linking conventions
- Rules for extending the ontology (adding new types, domains, tags)
- Known gaps and inconsistencies

The `CLAUDE.md` serves as standing instructions for Claude in any future session — it ensures `/kg-file` produces notes consistent with your existing vault structure rather than inventing new conventions.

Run this again periodically as your vault evolves. If a `CLAUDE.md` already exists, the skill preserves any custom sections you've added.

---

## Automatic extraction — beat types

When the PreCompact hook fires, it sends the session transcript to Claude (Haiku) and asks it to identify "beats" — moments in the session worth preserving. The extractor looks for these types:

| Type | What it captures |
|---|---|
| `decision` | An architectural or design choice made with its rationale |
| `insight` | A non-obvious understanding or pattern that emerged |
| `task` | A completed unit of work and its outcome |
| `problem-solution` | A problem that was encountered and how it was solved |
| `error-fix` | A specific bug or error and the fix that resolved it |
| `reference` | A useful fact, config value, snippet, or command to remember |

Each beat is written as a markdown file with YAML frontmatter:

```markdown
---
id: <uuid>
date: 2026-02-25T13:34:00
session_id: abc123
type: error-fix
scope: project
title: "Fix auth token expiry race condition"
project: api-service
cwd: /Users/dan/code/api-service
tags: ["auth", "redis", "cache"]
related: []
status: completed
summary: "Token TTL was in seconds but Redis expected ms; fixed by multiplying × 1000 in cache layer."
---

## Fix: Auth Token Expiry Race Condition

### Problem
...

### Solution
...
```

The `summary` field is a single information-dense sentence — optimized for both human scanning and future vector embedding (Phase 2).

---

## Ontology — labeling content with `/kg-file`

The `/kg-file` skill uses a structured ontology to classify notes. Understanding the entity types helps you get clean, consistent output.

### Entity types

| Type | Use for |
|---|---|
| `project` | Active or historical work — something being built, repaired, or learned |
| `concept` | A principle, technique, method, or body of knowledge |
| `tool` | A specific piece of hardware, software, library, or service |
| `decision` | A specific choice made, with its rationale captured |
| `insight` | A lesson learned, pattern noticed, or realization |
| `problem` | An open issue, bug, unknown, or challenge |
| `resource` | A book, article, documentation page, URL, or other reference |
| `person` | A contact, collaborator, or person worth tracking |
| `event` | A one-time or recurring happening |
| `claude-context` | A structured snapshot of Claude's knowledge for a domain |
| `domain` | A broad area of knowledge or practice |
| `skill` | A capability you have or are developing |
| `place` | A physical or logical location |

When in doubt: a realization from working on a project is an `insight`, not a `project`. Between two plausible types, choose the more specific one.

### Key fields

Every note has a small set of fields that appear across all types:

- **`domain`** — the broad topic area, kebab-case (e.g., `amateur-radio`, `ios-dev`, `woodworking`, `personal`). When a note spans domains, use the most specific one and add others as tags.
- **`status`** — current state; valid values vary by type (e.g., `active`/`complete`/`archived` for projects; `open`/`resolved` for problems; `seedling`/`evergreen` for concepts and insights).
- **`confidence`** — `high` (from direct experience or verified docs), `medium` (recalled or inferred), `low` (speculative).
- **`source`** — where the information came from: `personal-experience`, `claude-context`, `documentation`, `book`, `conversation`, `research`.

### Relationships and wikilinks

Notes connect to each other through YAML arrays and inline wikilinks. Use `[[type/note-name]]` syntax throughout — in frontmatter arrays and in the prose of the note body.

Common relationship fields:

| Field | Meaning |
|---|---|
| `caused-by` | What prompted this decision or problem |
| `resolves` | What problem this decision or fix addresses |
| `applies-to` | What concepts or projects an insight is relevant to |
| `learned-from` | Where an insight came from (event, project, resource) |
| `related` | Loose association when no specific relationship fits |

It's fine to wikilink notes that don't exist yet — these become stubs that fill in over time. The link matters even before the target note exists.

### File naming

Notes follow `type/kebab-case-title.md` — for example:

```
insight/fft-window-size-affects-ctcss-accuracy.md
decision/use-arduino-fft-over-mt8870.md
problem/squelch-tail-noise.md
tool/anytone-at778uv.md
```

---

## Vault folder structure

A typical vault with this system active might look like:

```
MyVault/
├── CLAUDE.md                      ← generated by /kg-claude-md
├── AI/
│   ├── Claude-Sessions/           ← general beats (auto-extracted)
│   └── Claude-Inbox/              ← staging beats (no project config)
├── Projects/
│   └── my-api/
│       └── Claude-Notes/          ← project beats (per-project config)
├── concept/
├── decision/
├── insight/
├── problem/
├── tool/
└── ...                            ← your existing vault structure
```

The `AI/` folders are managed by the extractor. The typed folders (`concept/`, `decision/`, etc.) are where `/kg-file` suggests saving manual notes.

---

## API Authentication

The extractor needs credentials to call Claude. Two backends are supported.

### Direct Anthropic API *(default)*

Set your API key in your shell environment:

```bash
export ANTHROPIC_API_KEY='sk-ant-...'
```

Add this to `~/.zshrc` or `~/.bashrc` so it's available in all shell sessions, including those launched by Claude Code hooks. No changes to `knowledge.json` are needed — the direct API is the default backend.

### AWS Bedrock *(alternative)*

If you have AWS credentials configured and access to Anthropic models via Bedrock, add to `~/.claude/knowledge.json`:

```json
{
  "vault_path": "/Users/you/Documents/MyVault",
  "inbox": "AI/Claude-Sessions",
  "staging_folder": "AI/Claude-Inbox",
  "backend": "bedrock",
  "bedrock_region": "us-east-1"
}
```

The extractor will use your ambient AWS credentials (`~/.aws/credentials`, environment variables, or IAM role). `ANTHROPIC_API_KEY` is not required when using Bedrock.

---

## Troubleshooting

**Extraction is silent / no beats appear**

Check that:
- For direct API: `ANTHROPIC_API_KEY` is set in your environment (not just in Claude Code's env)
- For Bedrock: `"backend": "bedrock"` is set in `~/.claude/knowledge.json` and AWS credentials are configured
- `vault_path` in `~/.claude/knowledge.json` points to a real directory
- The hook is registered: open `~/.claude/settings.json` and confirm a `PreCompact` key exists under `hooks`
- The hook is executable: `ls -l ~/.claude/hooks/pre-compact-extract.sh`

**"Prompt file not found" error**

The extractor looks for prompt files at `~/.claude/prompts/`. Reinstall to ensure they were copied:

```bash
bash install.sh
```

**Beats land in the inbox instead of my project folder**

`.claude/knowledge.local.json` was not found. Confirm it exists in the project root (or a parent directory up to `~`), and that `project_name` and `vault_folder` are set.

**`/kg-claude-md` fails to run**

The skill requires Python 3 and the `pyyaml` package. Confirm both are available:

```bash
python3 --version
python3 -c "import yaml; print('ok')"
```

If pyyaml is missing: `pip install pyyaml`

---

## File reference

| File | Purpose |
|---|---|
| `install.sh` | Installer |
| `uninstall.sh` | Uninstaller |
| `knowledge.example.json` | Template for `~/.claude/knowledge.json` |
| `knowledge.local.example.json` | Template for per-project `.claude/knowledge.local.json` |
| `hooks/pre-compact-extract.sh` | PreCompact hook entry point |
| `extractors/extract_beats.py` | Transcript parser and beat writer |
| `extractors/requirements.txt` | Python dependencies |
| `prompts/extract-beats-system.md` | System prompt for beat extraction |
| `prompts/extract-beats-user.md` | User message template for beat extraction |
| `skills/kg-recall/SKILL.md` | `/kg-recall` skill |
| `skills/kg-file/SKILL.md` | `/kg-file` skill |
| `skills/kg-file/references/ontology.md` | Full entity type schemas and relationship vocabulary |
| `skills/kg-claude-md/SKILL.md` | `/kg-claude-md` skill |
| `skills/kg-claude-md/scripts/analyze_vault.py` | Vault structure analyzer |
| `skills/kg-claude-md/references/` | Output structure spec and CLAUDE.md template |
| `skills/kg-extract/SKILL.md` | `/kg-extract` skill |
