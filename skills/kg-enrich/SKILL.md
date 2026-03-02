---
name: kg-enrich
description: >
  Scan vault notes for missing or invalid metadata and enrich them so they surface
  correctly in /kg-recall. Trigger on: "Clean up the vault.", "Enrich missing metadata.",
  "My manually-added notes need metadata.", "Tidy up my notes.",
  "Do a dry run of the enrichment."
allowed-tools: Bash, Glob, Grep, Read, Edit
---

# Knowledge Vault Enrichment

Arguments: $ARGUMENTS

Scans the Obsidian vault for notes missing required metadata (`type`, `summary`, `tags`)
and adds them using in-context classification — making human-authored notes findable via
`/kg-recall`. Additive-only by default: existing fields are never overwritten unless
`--overwrite` is set.

---

## Step 1 — Parse Arguments

Parse `$ARGUMENTS` for the following flags:

| Flag | Default | Description |
|---|---|---|
| `--folder <path>` | (entire vault) | Vault-relative folder to scan |
| `--dry-run` | false | Report what would change without modifying any files |
| `--since <YYYY-MM-DD>` | (all) | Only notes modified on or after this date (filesystem mtime) |
| `--limit <n>` | (unlimited) | Process at most N notes needing enrichment |
| `--overwrite` | false | Replace existing type/summary/tags values instead of additive-only |

Check the invocation context for natural-language dry-run phrases: "dry run",
"what would change", "preview", "don't modify", "show me what needs enrichment".

If dry-run mode is active, confirm at the start:
`[DRY RUN] No files will be written.`

---

## Step 2 — Load Config and Vault CLAUDE.md

### Load vault path

```bash
python3 -c "
import json, os
cfg = json.load(open(os.path.expanduser('~/.claude/knowledge.json')))
print(cfg.get('vault_path', ''))
"
```

Set `VAULT_PATH`. If empty or the path does not exist, report an error and stop.

### Load type vocabulary from CLAUDE.md

Check for `CLAUDE.md` at the vault root:

```bash
ls "$VAULT_PATH/CLAUDE.md" 2>/dev/null
```

If it exists, read it using the Read tool. Extract the valid type vocabulary — the list
of types that are recognized in this vault.

If no `CLAUDE.md` exists, warn the user:
"No vault CLAUDE.md found. Using the 4-type default vocabulary (decision, insight,
problem, reference). Run `/kg-setup` to configure your vault's type vocabulary."
Use the four-type default: `decision`, `insight`, `problem`, `reference`.

If a `CLAUDE.md` exists but no type vocabulary can be identified from its content, warn:
"CLAUDE.md found but no type vocabulary could be identified — using default types
(decision, insight, problem, reference)."
Use the four-type default.

Set `VALID_TYPES` to the resolved vocabulary. This is the authoritative list for all
type validation in this run.

---

## Step 3 — Find Candidate Files

```bash
python3 -c "
import os, sys
from pathlib import Path
from datetime import datetime

vault = sys.argv[1]
folder = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else ''
since = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else ''

base = Path(vault) / folder if folder else Path(vault)
since_dt = datetime.fromisoformat(since) if since else None

for p in sorted(base.rglob('*.md')):
    if since_dt and datetime.fromtimestamp(p.stat().st_mtime) < since_dt:
        continue
    print(p)
" "\$VAULT_PATH" "\$FOLDER" "\$SINCE_DATE"
```

This produces a full list of candidate paths.

---

## Step 4 — Detect Notes Needing Enrichment

For each candidate file, read the **first 40 lines** using the Read tool with
`limit: 40`. This is sufficient to read the YAML frontmatter without loading the full
body.

### Skip conditions (do not process; count as skipped)

- Frontmatter contains `enrich: skip`
- Filename matches `YYYY-MM-DD.md` (daily journal files)
- File path contains `/templates/` or `/_templates/`
- `type:` value is `journal` or `moc`

### Needs enrichment if ANY of these is true

1. No frontmatter (file does not start with `---`)
2. Frontmatter exists but `type:` field is absent
3. `type:` is present but its value is not in `VALID_TYPES`
4. `type:` is valid but `summary:` is absent or empty
5. `type:` is valid, `summary:` is non-empty, but `tags:` is absent, empty (`[]`), or
   contains only domain-level terms (`personal`, `work`, `home`)

### Tracking

Maintain running counts:
- `needs_enrichment` — list of file paths that pass the detection check
- `already_done` — count of files with all required fields already present and valid
- `skipped` — count of files matching a skip condition

Apply `--limit` to the `needs_enrichment` list before proceeding to Step 5.

---

## Step 5 — Enrich Each Note

### If `--dry-run`

For each file in `needs_enrichment`, record the file path and the specific reason it
needs enrichment (missing `type`, invalid `type`, empty `summary`, etc.). Do not read
full content or modify anything. Skip to Step 6 for the dry-run report.

### Otherwise (normal mode)

For each file in `needs_enrichment`:

#### 5a. Read the full note

Use the Read tool to load the complete file content.

#### 5b. Classify the note

Using the `VALID_TYPES` vocabulary loaded from CLAUDE.md, determine the appropriate
values for missing or invalid fields. Work entirely in-context.

**Type assignment:** Choose the type from `VALID_TYPES` that best describes what kind
of thinking produced this note. If the note is a draft, journal entry, meeting notes,
reading list, or otherwise cannot be meaningfully classified into any of the valid types,
mark it as skipped with reason "cannot classify — no matching type" and move on.

**Summary rules:**
- One information-dense sentence
- Start with the key concept — not "This note...", not "A guide to..."
- Front-load the key noun or concept
- Include terms a future searcher would use

**Tags rules:**
- 2–6 lowercase keywords
- Most distinguishing terms only
- Omit generic words: `note`, `guide`, `tips`, `overview`
- Omit domain-level terms already covered by vault structure: `personal`, `work`, `home`

#### 5c. Apply frontmatter update (additive-only by default)

**If frontmatter exists** (file starts with `---`):

Identify which fields are missing or invalid. For each such field:
- If `--overwrite` is set: replace the existing value
- Otherwise: add only absent/invalid fields; leave existing fields untouched

Use the Edit tool to insert new fields immediately before the closing `---` of the
frontmatter block.

Example — adding `type`, `summary`, and `tags` before the closing `---`:

```
old_string:  "---\n\n## [first body line or heading]"
new_string:  "type: insight\nsummary: \"One-sentence summary here.\"\ntags: [keyword1, keyword2]\n---\n\n## [first body line or heading]"
```

Adjust to match only the fields actually being added.

**If no frontmatter exists** (file does not start with `---`):

Generate a UUID:
```bash
python3 -c "import uuid; print(uuid.uuid4())"
```

Prepend a complete frontmatter block using the Edit tool on the first line of the file.

#### 5d. Record result

For each successfully enriched note, record:
- File path (vault-relative)
- Fields added or changed and their new values

For each error (failed to parse, Edit tool failed, etc.): record the path and reason.

---

## Step 6 — Report Results

### Normal mode

```
/kg-enrich complete — N notes scanned

  Enriched:      N notes
  Already done:  N notes
  Skipped:       N notes (templates, daily journals, enrich:skip)
  Errors:         N notes (parse or edit failure)

Enriched:
  + Note Title.md  → type: insight, tags: [keyword1, keyword2]
  + Another Note.md → type: decision, tags: [arch, api-design]
```

If no notes needed enrichment:
```
/kg-enrich complete — N notes scanned. All notes already have required metadata.
```

### Dry-run mode

```
[DRY RUN] Would enrich N of M notes scanned

Would enrich:
  + Note Title.md  — missing: type, summary
  + Another Note.md — invalid type: "mytopic" (not in vocabulary)
  + Third Note.md  — missing: tags

Would skip:
  - Daily Journal.md (daily journal)
  - Template.md (in /templates/ folder)

Already done:  N notes
No files were modified. Run without --dry-run to apply.
```
