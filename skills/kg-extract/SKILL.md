---
name: kg-extract
description: >
  Extract knowledge beats from a chat session log and save them to the knowledge vault.
  With no arguments, extracts from the current session. Accepts an optional path to a
  Claude Code JSONL transcript or plain-text conversation file for processing old sessions.
  Examples: /kg-extract   or   /kg-extract ~/.claude/projects/-Users-me-code-myapp/abc123.jsonl
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# Knowledge Beat Extraction

Arguments: **$ARGUMENTS**

---

## Overview

This skill reads a chat session log, identifies durable knowledge within it, and files
each beat into the Obsidian vault — either via intelligent in-context filing (autofile)
or by writing flat markdown files routed by scope.

When invoked with no arguments, it extracts beats from the current running session.

---

## Step 1 — Resolve the transcript file

The argument format is:

```
/kg-extract [<file-path>] [--project <name>] [--cwd <path>]
```

- `<file-path>` — path to a chatlog file; **omit to process the current session**
- `--project <name>` — project name for routing project-scoped beats (optional)
- `--cwd <path>` — working directory for per-project vault folder lookup (optional)

### Case A — No file path given (current session)

Run the following to locate the current session's transcript:

```bash
python3 -c "
import os, sys
from pathlib import Path

cwd = os.getcwd()
encoded = cwd.replace('/', '-')           # /Users/dan/code/app → -Users-dan-code-app
project_dir = Path.home() / '.claude' / 'projects' / encoded

if not project_dir.exists():
    print('ERROR: no project dir at ' + str(project_dir), file=sys.stderr)
    sys.exit(1)

# Most recently modified JSONL = the active session transcript
files = sorted(project_dir.glob('*.jsonl'), key=lambda p: p.stat().st_mtime, reverse=True)
if not files:
    print('ERROR: no transcript files found in ' + str(project_dir), file=sys.stderr)
    sys.exit(1)

print(files[0])           # transcript path
print(files[0].stem)      # session_id (filename without .jsonl)
print(cwd)                # cwd
print(Path(cwd).name)     # project name (last path component)
"
```

Use the output to set `transcript_path`, `session_id`, `cwd`, and `project`.

### Case B — File path given (backlog session)

Parse `$ARGUMENTS` to extract `file_path` and any flags.

**Auto-detect from Claude Code transcript paths**: If the path matches
`~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`, derive values automatically:

- `session_id` — filename without `.jsonl`
- `cwd` — decode the parent directory name by replacing `-` with `/` (the encoded form
  replaces each `/` with `-`, starting with `-` for the leading slash). For example,
  `-Users-dan-code-my-app` → `/Users/dan/code/my-app`
- `project` — last path component of the decoded cwd, unless overridden by `--project`

If the path is not a Claude Code transcript and no `--cwd` was given, set
`cwd = "unknown"` and `project = "unknown"`. Beats will route to the staging folder.

---

## Step 2 — Load config

```bash
python3 -c "
import json, os, sys
path = os.path.expanduser('~/.claude/knowledge.json')
if not os.path.exists(path):
    print('ERROR: ~/.claude/knowledge.json not found', file=sys.stderr)
    sys.exit(1)
cfg = json.load(open(path))
vault = os.path.expanduser(cfg.get('vault_path', ''))
print(vault)
print(cfg.get('inbox', 'AI/Claude-Sessions'))
print(cfg.get('staging_folder', 'AI/Claude-Inbox'))
print(str(cfg.get('autofile', False)).lower())
print(str(cfg.get('daily_journal', False)).lower())
"
```

Capture the five output lines as `vault_path`, `inbox_folder`, `staging_folder`,
`autofile` (`true`/`false`), and `daily_journal` (`true`/`false`).

If `cwd` was determined (not "unknown"), also check for per-project config:

```bash
python3 -c "
import json, os
from pathlib import Path
cwd = Path('$CWD').resolve()
for d in [cwd, *cwd.parents]:
    candidate = d / '.claude' / 'knowledge.local.json'
    if candidate.exists():
        cfg = json.load(open(candidate))
        print(cfg.get('vault_folder', ''))
        print(cfg.get('project_name', ''))
        break
    if d == Path.home():
        break
"
```

---

## Step 3 — Read and parse the chatlog

Read the file using the Read tool.

### Claude Code JSONL format

If each line of the file is a valid JSON object containing a `"type"` field, treat it as
a Claude Code JSONL transcript:

- Include lines where `"type"` is `"user"` or `"assistant"`
- Extract `message.role` and `message.content`
- If `content` is a string, use it directly
- If `content` is a list of blocks:
  - Include only blocks where `"type": "text"` — take the `"text"` field
  - Skip `tool_use`, `tool_result`, and `thinking` blocks (too noisy for extraction)
- Skip turns with no extractable text after filtering
- Format the reconstructed conversation as:
  ```
  [USER]
  <content>

  ---

  [ASSISTANT]
  <content>

  ---
  ```

### Plain text format

If the file is plain text (or a JSON structure not matching the above), use the content
as-is. Common patterns like `Human:` / `Assistant:` or `User:` / `Claude:` prefixes are
fine — the extraction step handles them.

### Large files

If the file is very long, focus on the latter two-thirds of the content (the most recent
exchanges are typically most valuable) and note the truncation in your output.

---

## Step 4 — Extract beats

Apply the criteria below to the parsed conversation. Be selective — a typical 1-hour
session yields 3–8 beats. Do not extract everything; extract only what would be
genuinely useful to a future reader with no other context.

### Extract beats for

- **Decisions** — why X was chosen over Y; architectural choices; trade-offs made
- **Problems solved** — what went wrong and how it was fixed
- **Insights** — non-obvious understanding about a system, library, approach, or pattern
- **Error fixes** — a specific bug or error and the exact fix that resolved it
- **Code patterns or configurations** — reusable setups, commands, or workflows established
- **Reference facts** — API quirks, config values, environment details worth remembering

### Do NOT extract

- Conversational filler, acknowledgements, or clarifying questions
- Exploratory dead-ends that led nowhere
- Obvious or trivial facts
- Process steps that are self-evident from the outcome
- Abandoned approaches (unless the failure itself is informative)

### For each beat, determine

| Field | Description |
|---|---|
| `title` | Brief, descriptive — 5–10 words |
| `type` | `decision` \| `insight` \| `task` \| `problem-solution` \| `error-fix` \| `reference` |
| `scope` | `project` (only useful in this codebase) or `general` (applicable anywhere) |
| `summary` | One information-dense sentence, optimized for future search and retrieval |
| `tags` | 2–6 lowercase keywords |
| `body` | Full markdown, self-contained. A future reader needs no other context. Use `##` headers, code blocks, and bullets as appropriate. |

If no beats worth preserving are found, report that and stop.

---

## Step 5 — File beats

Branch on `autofile`:

---

### autofile=false — flat filing via extract_beats.py

Determine output folder per beat:

| Condition | Output folder |
|---|---|
| `scope: project` AND project vault folder from config | `vault_path/vault_folder/` |
| `scope: general` | `vault_path/inbox_folder/` |
| No project config | `vault_path/staging_folder/` |

Get a temp file path:

```bash
python3 -c "import uuid; print(f'/tmp/kg-extract-{uuid.uuid4()}.json')"
```

Write all beats as a JSON array to that temp path (schema: array of objects with fields
`title`, `type`, `scope`, `summary`, `tags`, `body`). Then invoke the extractor:

```bash
python3 ~/.claude/extractors/extract_beats.py \
  --beats-json "$TEMP_FILE" \
  --session-id "$SESSION_ID" \
  --trigger manual \
  --cwd "$CWD" \
  2>&1

rm -f "$TEMP_FILE"
```

Collect the written paths from the `[extract_beats] Wrote: ...` lines in the output.

---

### autofile=true — in-context filing

File each beat individually. For each beat:

**5a. Search for related vault notes**

Use Grep to search `vault_path` for files containing the beat's tags and significant
title words (4+ chars). Collect unique matching file paths.

```bash
grep -r -l --include="*.md" -i "TERM" "$VAULT_PATH" 2>/dev/null
```

Run one grep per term. Deduplicate results. Sort by modification time (most recent first)
and take the top 5:

```bash
python3 -c "
import os, sys
paths = sys.argv[1:]
ranked = sorted(paths, key=os.path.getmtime, reverse=True)
print('\n'.join(ranked[:5]))
" path1 path2 ...
```

**5b. Read related notes and vault conventions**

- Read up to the top 3 related notes (first 2000 chars each) using the Read tool
- Read `vault_path/CLAUDE.md` if it exists — this defines filing conventions,
  frontmatter schema, folder structure, and naming rules for this vault

**5c. Decide: extend or create**

Extend an existing note when:
- An existing note clearly covers the same concept, decision, or topic
- The beat adds genuinely new information (a new section, updated approach, correction)
- The fit is strong — not just loosely topically related

Create a new note when:
- The beat introduces a concept not covered by any existing note
- No existing note is a natural home for this content

**When in doubt and a reasonable home exists, prefer extend over create.**

**5d. Execute the decision**

**Extend**: Use the Edit tool to append a new `## Section` to the target note.
- The insertion must be a clean, self-contained markdown section
- Do not duplicate information already in the note
- Append at the end of the file

**Create**: Use the Write tool to create a new note.
- Follow the vault's frontmatter schema from CLAUDE.md (e.g., `title`, `type`, `status`,
  `created`, `updated`, `tags`, `aliases`)
- Use the vault's domain tags (`personal`, `work`, `work/<area>`)
- Filename: Title Case with spaces, no date prefix, 3–7 words, `.md` extension
- Place in the most appropriate existing folder based on vault structure

**5e. Track result**

Record for each beat:
- `action`: `extend` or `create`
- `path`: absolute path of the written/edited file
- `title`: beat title
- `reason`: one sentence explaining the filing decision

---

## Step 6 — Write log entry

Append a structured log entry to `~/.claude/logs/kg-extract.log`. Create the directory
if it doesn't exist.

```bash
mkdir -p ~/.claude/logs
```

Log format — one line per beat, tab-separated:

```
<ISO timestamp>\t<session_id[:8]>\t<action>\t<vault-relative path>\t<beat title>
```

Example:
```
2026-02-27T21:04:33Z  14281578  create  Personal/Projects/knowledge-graph/Claude-Notes/Autofile Toggle.md  autofile Toggle for Intelligent Vault Filing
2026-02-27T21:04:35Z  14281578  extend  Personal/Projects/knowledge-graph/Claude-Notes/cli.md  claude-cli Backend Simplified to stdin-Only
```

Write the entries using the Write tool (append to existing file, or create new).

---

## Step 7 — Report results

Summarize the outcome:

- Total beats extracted
- For each filed beat: action (`created`/`extended`), title, vault path, and one-sentence reason
- Where beats were routed (project folder, inbox, or staging)
- Whether the log was written and where
- A note if any beats were routed to staging because no project config was found — and
  how to fix that (add `.claude/knowledge.local.json` to the project root)
