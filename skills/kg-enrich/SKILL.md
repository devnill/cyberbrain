---
name: kg-enrich
description: >
  Scan vault notes and enrich those missing structured metadata (type, summary, tags)
  so they surface correctly in /kg-recall queries. Run /kg-enrich to bridge the gap
  between human-authored notes and beat-style recall-ready notes.
allowed-tools: Bash, Glob, Grep, Read, Edit, Write
---

# Knowledge Vault Enrichment

Arguments: $ARGUMENTS

Scans the Obsidian vault for notes missing `type`, `summary`, or `tags` fields and
adds them using in-context classification — making human-authored notes findable via
`/kg-recall`.

---

## Step 1 — Parse Arguments

Parse `$ARGUMENTS` for the following flags:

| Flag | Default | Description |
|---|---|---|
| `--folder <path>` | (entire vault) | Vault-relative folder to scan |
| `--dry-run` | false | Report what would change without modifying any files |
| `--since <YYYY-MM-DD>` | (all) | Only process files modified on or after this date |
| `--limit <n>` | (unlimited) | Process at most N notes needing enrichment |
| `--overwrite` | false | Overwrite existing `type`, `summary`, `tags` values; default is additive-only |

---

## Step 2 — Load Config

```bash
python3 -c "
import json, os
cfg = json.load(open(os.path.expanduser('~/.claude/knowledge.json')))
print(cfg.get('vault_path', ''))
"
```

Set `VAULT_PATH` from the output. If empty or the path does not exist, report an error
and stop.

---

## Step 3 — Find Candidate Files

Run the following to get a sorted list of `.md` files to evaluate:

```bash
python3 -c "
import os, sys
from pathlib import Path
from datetime import datetime

vault = sys.argv[1]
folder = sys.argv[2] if len(sys.argv) > 2 else ''
since = sys.argv[3] if len(sys.argv) > 3 else ''

base = Path(vault) / folder if folder else Path(vault)
since_dt = datetime.fromisoformat(since) if since else None

for p in sorted(base.rglob('*.md')):
    if since_dt and datetime.fromtimestamp(p.stat().st_mtime) < since_dt:
        continue
    print(p)
" "\$VAULT_PATH" "\$FOLDER" "\$SINCE_DATE"
```

This produces a full list of candidate paths. You will process them in Step 4.

---

## Step 4 — Detect Notes Needing Enrichment

For each candidate file, read the **first 40 lines** using the Read tool with
`limit: 40`. This is sufficient to read the YAML frontmatter without loading the
full body.

### Skip conditions (do not process, do not count as needing enrichment)

- Frontmatter contains `enrich: skip`
- Filename matches `YYYY-MM-DD.md` (daily journal files)
- File path contains `/templates/` or `/_templates/`
- `type:` is `journal` or `moc`

### Needs enrichment if ANY of these is true

1. No frontmatter (file does not start with `---`)
2. Frontmatter exists but `type:` field is absent
3. `type:` is present but not in VALID_TYPES (see below)
4. Valid `type:` present but `summary:` is absent or empty
5. Valid `type:` and non-empty `summary:` but `tags:` is absent, empty (`[]`), or
   contains only domain-level terms: `personal`, `work`, `home`

### VALID_TYPES

```
decision, insight, task, problem-solution, error-fix, reference,
project, concept, tool, problem, resource, person, event,
claude-context, domain, skill, place
```

### Tracking

Maintain running counts:
- `needs_enrichment` — list of file paths that pass the detection check
- `already_done` — count of files with all required fields already present
- `skipped` — count of files matching a skip condition

Apply `--limit` to the `needs_enrichment` list before proceeding to Step 5.

---

## Step 5 — Enrich Each Note

For each file in `needs_enrichment`:

**If `--dry-run`:** Record the file and detection reason, but do not read or modify it.
Skip to Step 6 for the report.

**Otherwise:**

### 5a. Read the full note

Use the Read tool to load the complete file content.

### 5b. Classify the note

Using the classification criteria below, determine the appropriate values for the
missing or invalid fields. Work entirely in-context — do not call any external process.

**Type definitions:**
- `decision` — a choice made between alternatives, with rationale recorded
- `insight` — a non-obvious understanding or pattern about a system, tool, or approach
- `task` — a completed unit of work and its outcome
- `problem-solution` — a problem that required judgment to diagnose and solve
- `error-fix` — a specific error or bug and the exact fix that resolved it
- `reference` — a fact, command, config value, API detail, or snippet to look up later

If the note is a draft, journal entry, meeting notes, reading list, or otherwise does
not fit any type: mark it as skipped (reason: "null type") and move on.

**Summary rules:**
- One information-dense sentence
- Start with what the note covers — not "This note...", not "A guide to..."
- Front-load the key noun or concept
- Include terms a future searcher would use

**Tags rules:**
- 2–6 lowercase keywords
- Most distinguishing terms only
- Omit generic words: `note`, `guide`, `tips`, `overview`
- Omit domain-level terms: `personal`, `work`, `home`

**Scope:**
- `project` — only useful in one specific codebase or project context
- `general` — applicable broadly across contexts

### 5c. Apply additive-only frontmatter update

**If frontmatter exists** (file starts with `---`):

For each field that is absent or invalid (and not `--overwrite`):
- Add the field at the end of the frontmatter block, immediately before the closing `---`
- Do not modify existing fields unless `--overwrite` is set

Use the Edit tool. The `old_string` should be the closing `---` of the frontmatter;
`new_string` inserts the new fields before it:

```
old_string:  "---\n\n## Note title"   (the closing --- plus first body line)
new_string:  "type: error-fix\nsummary: \"...\"\ntags: [\"a\", \"b\"]\nscope: general\n---\n\n## Note title"
```

**If no frontmatter exists** (file does not start with `---`):

Prepend a complete frontmatter block using the Edit tool on the first line of the file:

```yaml
---
id: <new-uuid>
type: error-fix
summary: "One-sentence summary."
tags: ["keyword1", "keyword2"]
scope: general
---
```

Generate a UUID with:
```bash
python3 -c "import uuid; print(uuid.uuid4())"
```

### 5d. Record result

For each successfully enriched note, record:
- File path (vault-relative)
- Fields added/changed
- The assigned type and tags

For each error (failed to parse, Edit tool failed, etc.): record the path and reason.

---

## Step 6 — Report Results

Print a summary in this format:

```
/kg-enrich complete — N notes scanned

  Enriched:     N notes
  Already done: N notes (all required fields present)
  Skipped:      N notes (enrich: skip or null type or excluded pattern)
  Errors:        N notes (parse or edit failure)

Enriched:
  + filename.md → type: error-fix, tags: [hook, python, pre-compact]
  + Another Note.md → type: decision, tags: [architecture, api-design]
  ...
```

If `--dry-run`, replace the "Enriched" section with a "Would enrich" section listing the
files and the detection reason for each (missing field, invalid type, etc.).

If no notes needed enrichment, report:
```
/kg-enrich complete — N notes scanned. All notes already have required metadata.
```
