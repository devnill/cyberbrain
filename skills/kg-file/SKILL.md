---
name: kg-file
description: >
  File a specific piece of knowledge into the personal vault right now. Trigger on:
  "Save this.", "File this.", "Remember this.", "Add this to my notes.", "Capture this.",
  or any phrasing that implies the user wants a specific piece of information preserved.
  Also trigger on dry-run variants: "Show me what you'd file", "Preview this",
  "What beat would this become?", "Test the filing".
allowed-tools: Bash, Glob, Grep, Read
---

# Knowledge Filing

Arguments: $ARGUMENTS

---

## Step 1 — Detect Dry-Run Mode

Check `$ARGUMENTS` for `--dry-run` flag, or check the invocation context for natural-
language dry-run phrases: "preview", "what would happen", "show me what you'd file",
"test the filing", "don't actually write".

If dry-run mode is active, confirm at the start of output:
`[DRY RUN] No files will be written.`

---

## Step 2 — Extract Content and Flags

Parse `$ARGUMENTS` for:
- `--type <type>` — override type assignment
- `--folder <path>` — override filing destination (vault-relative path)
- `--dry-run` — dry-run mode (already detected in Step 1)
- Remaining text after flag parsing is the content to file

If content is present in `$ARGUMENTS` (after removing flags), use it.

If no content is provided, use the last few exchanges of the current conversation as the
content to extract from.

---

## Step 3 — Load Config

```bash
python3 -c "
import json, os
cfg = json.load(open(os.path.expanduser('~/.claude/knowledge.json')))
print(cfg.get('vault_path', ''))
print(cfg.get('inbox', 'AI/Claude-Sessions'))
print(cfg.get('staging_folder', 'AI/Claude-Inbox'))
print(str(cfg.get('autofile', False)).lower())
"
```

Capture as `VAULT_PATH`, `INBOX_FOLDER`, `STAGING_FOLDER`, `AUTOFILE`.

Check for per-project vault folder:

```bash
python3 -c "
import json, os
from pathlib import Path
cwd = Path(os.getcwd()).resolve()
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

Capture as `PROJECT_FOLDER` and `PROJECT_NAME` (may be empty).

---

## Step 4 — Read Vault CLAUDE.md

Check for a `CLAUDE.md` at the vault root:

```bash
ls "$VAULT_PATH/CLAUDE.md" 2>/dev/null
```

If it exists, read it using the Read tool. Extract:
- Type vocabulary (valid types for this vault)
- Filing rules (which types go where)
- Required frontmatter fields
- Tag vocabulary and conventions
- Naming conventions

If no `CLAUDE.md` exists, warn the user:
"No vault CLAUDE.md found. Filing with default type vocabulary (decision, insight,
problem, reference). Run `/kg-setup` to configure your vault's conventions."

Use the four-type default vocabulary: `decision`, `insight`, `problem`, `reference`.

If a `CLAUDE.md` exists but no type vocabulary can be identified from its content, warn:
"CLAUDE.md found but no type vocabulary could be identified — filing with default types
(decision, insight, problem, reference)."

---

## Step 5 — Extract Beats

From the content (Step 2), extract beats. A short one-liner yields one beat. A richer
passage may yield 1–3. Be selective — do not over-extract.

For each beat, determine:
- **title** — brief and descriptive (5–10 words)
- **type** — from the CLAUDE.md vocabulary (or 4-type default); use `--type` override if provided
- **summary** — one information-dense sentence, optimized for future search and retrieval
- **tags** — 2–6 lowercase keywords
- **scope** — `project` (only useful in this specific codebase) or `general`
- **body** — full markdown; self-contained; a future reader needs no other context

If `--type` was provided, use it for all beats (do not override individual assignments).

---

## Step 6 — Determine Filing Destination

For each beat:

1. If `--folder` was provided, use it as the filing destination (vault-relative).
2. Otherwise, determine routing:
   - `autofile: true` → LLM routing: extend an existing note or create a new one,
     guided by CLAUDE.md conventions
   - `autofile: false` (default) → drop in inbox:
     - `scope: project` AND `PROJECT_FOLDER` is set → `PROJECT_FOLDER`
     - `scope: general` → `INBOX_FOLDER`
     - No project config → `STAGING_FOLDER`

---

## Step 7 — File via Extractor (or Dry-Run Preview)

### Dry-run mode

Do not invoke the extractor. Instead, for each beat, output a full preview block:

```
[DRY RUN] Would file 1 beat

━━━ Beat 1 of 1 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Title:   [title]
  Type:    [type]
  Tags:    [tags]
  Summary: [summary]
  Action:  would create → [destination folder]/[Title].md

  Body preview:
  > [full beat body]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1 would be filed · 0 skipped
  No files were written. Run without --dry-run to apply.
```

### Normal mode

Write all beats as a JSON array to a temp file:

```bash
python3 -c "import uuid; print(f'/tmp/kg-file-{uuid.uuid4()}.json')"
```

Then invoke the extractor:

```bash
python3 ~/.claude/extractors/extract_beats.py \
  --beats-json "$TEMP_FILE" \
  --session-id "manual-$(date +%s)" \
  --trigger manual \
  --cwd "$(pwd)" \
  2>&1

rm -f "$TEMP_FILE"
```

Collect the written paths from `[extract_beats] Wrote: ...` lines in the output.

The JSON array format for `--beats-json`:
```json
[
  {
    "title": "...",
    "type": "...",
    "scope": "project|general",
    "summary": "...",
    "tags": ["tag1", "tag2"],
    "body": "..."
  }
]
```

---

## Step 8 — Report

### Normal mode output

```
Filed: "[title]"
  Type:   [type]
  Action: created [vault-relative/path/to/Note.md]
  Tags:   [tag1, tag2, tag3]
```

One block per beat. If multiple beats were filed, list each.

### Error handling

If the extractor reports an error, surface it clearly:
"Filing failed: [error message]. The beat was not saved."

Do not retry silently. Report the error and stop.
