---
name: kg-extract
description: >
  Extract all knowledge beats from a session transcript and file them in the vault.
  Trigger on: "Extract everything from this session.", "Save this conversation.",
  "Capture my notes before I close this.", "What would you extract from this session?",
  "Preview the extraction", "Show me the beats without saving them."
  With no arguments, extracts from the current session. Accepts a path to a Claude Code
  JSONL transcript or plain-text conversation file for processing past sessions.
  Examples: /kg-extract   or   /kg-extract ~/.claude/projects/.../abc123.jsonl
allowed-tools: Bash, Glob, Grep, Read
---

# Knowledge Beat Extraction

Arguments: $ARGUMENTS

---

## Step 1 — Detect Dry-Run Mode

Check `$ARGUMENTS` for `--dry-run` flag, or check the invocation context for natural-
language dry-run phrases: "what would you extract", "preview the extraction", "show me
the beats", "test the extraction", "without saving", "don't write anything".

If dry-run mode is active, confirm at the start:
`[DRY RUN] No files will be written.`

Dry-run: add `--dry-run` to the extractor invocation in Step 5. Do not write log entries.

---

## Step 2 — Resolve the Transcript File

Parse `$ARGUMENTS` (after removing `--dry-run`) to determine the transcript path.

### Case A — No file path given (current session)

Locate the current session's JSONL using the SHA-256 hash of the cwd path:

```bash
python3 -c "
import os, sys, hashlib
from pathlib import Path

cwd = os.getcwd()

# Method 1: SHA-256 hash (used by newer Claude Code versions)
hash_id = hashlib.sha256(cwd.encode()).hexdigest()[:16]
hash_dir = Path.home() / '.claude' / 'projects' / hash_id

# Method 2: Path encoding (used by older versions — replaces / with -)
encoded = cwd.replace('/', '-')
encoded_dir = Path.home() / '.claude' / 'projects' / encoded

# Try both; use whichever exists
project_dir = None
for candidate in [hash_dir, encoded_dir]:
    if candidate.exists():
        project_dir = candidate
        break

if project_dir is None:
    # Fall back: scan all project dirs for matching cwd in recent transcripts
    projects_root = Path.home() / '.claude' / 'projects'
    if projects_root.exists():
        for d in sorted(projects_root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if d.is_dir():
                files = sorted(d.glob('*.jsonl'), key=lambda p: p.stat().st_mtime, reverse=True)
                if files:
                    project_dir = d
                    break

if project_dir is None:
    print('ERROR: no project directory found in ~/.claude/projects/', file=sys.stderr)
    sys.exit(1)

files = sorted(project_dir.glob('*.jsonl'), key=lambda p: p.stat().st_mtime, reverse=True)
if not files:
    print('ERROR: no transcript files found in ' + str(project_dir), file=sys.stderr)
    sys.exit(1)

print(files[0])       # transcript path
print(files[0].stem)  # session_id
print(cwd)            # cwd
"
```

Use the output to set `TRANSCRIPT_PATH`, `SESSION_ID`, and `CWD`.

If the script fails, report clearly:
"Could not locate a JSONL transcript for the current session. No extraction performed.
If you have the transcript path, run `/kg-extract <path>` directly."
Then stop.

### Case B — File path given

Use the provided path as-is. `SESSION_ID` is the filename stem (e.g., `abc12345` from
`abc12345.jsonl`). Set `CWD` to the current working directory unless a `--cwd` flag was
passed.

---

## Step 3 — Load Config

```bash
python3 -c "
import json, os
cfg = json.load(open(os.path.expanduser('~/.claude/knowledge.json')))
print(cfg.get('vault_path', ''))
print(cfg.get('inbox', 'AI/Claude-Sessions'))
print(cfg.get('staging_folder', 'AI/Claude-Inbox'))
"
```

Capture as `VAULT_PATH`, `INBOX_FOLDER`, `STAGING_FOLDER`.

---

## Step 4 — Deduplication Check (skip in dry-run)

If NOT in dry-run mode, check whether this session has already been extracted:

```bash
python3 -c "
import os, sys
from pathlib import Path
session_id = sys.argv[1]
log = Path.home() / '.claude' / 'logs' / 'kg-extract.log'
if log.exists():
    for line in log.read_text().splitlines():
        parts = line.split('\t')
        if len(parts) >= 2 and parts[1].strip() == session_id:
            print('ALREADY_EXTRACTED')
            sys.exit(0)
print('NOT_EXTRACTED')
" "$SESSION_ID" 2>/dev/null || echo "NOT_EXTRACTED"
```

If `ALREADY_EXTRACTED`, report:
"Session `$SESSION_ID` has already been extracted (found in kg-extract.log). Skipping
to avoid duplicates. Use `/kg-extract --dry-run` to preview without the dedup check, or
delete the log entry to force re-extraction."
Then stop.

If the log file is unreadable or corrupt, warn and proceed — do not block extraction.

---

## Step 5 — Invoke the Extractor

```bash
python3 ~/.claude/extractors/extract_beats.py \
  --transcript "$TRANSCRIPT_PATH" \
  --session-id "$SESSION_ID" \
  --trigger manual \
  --cwd "$CWD" \
  2>&1
```

If dry-run mode is active, add `--dry-run`:

```bash
python3 ~/.claude/extractors/extract_beats.py \
  --transcript "$TRANSCRIPT_PATH" \
  --session-id "$SESSION_ID" \
  --trigger manual \
  --cwd "$CWD" \
  --dry-run \
  2>&1
```

If the extractor exits non-zero or produces an error message, report the error clearly.
Do not silently fail.

---

## Step 6 — Report Results

### Normal mode

Parse the extractor output for `[extract_beats] Wrote: ...` and `[extract_beats] Skipped:
...` lines to build the result summary.

```
Extracted N beats from session [SESSION_ID] ([date])

  Created:  [vault-relative path]    (type)
  Created:  [vault-relative path]    (type)
  Extended: [vault-relative path]    (type)
  Skipped:  N beat(s) — [reason]
```

If no beats were found:
"No durable knowledge beats found in session `[SESSION_ID]`. Nothing was filed."

### Dry-run mode

The extractor handles dry-run output formatting. Pass through the extractor's output
directly. The format matches the standard dry-run output:

```
[DRY RUN] Would extract N beats from session [SESSION_ID]

━━━ Beat 1 of N ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Title:   ...
  Type:    ...
  Tags:    [...]
  Summary: ...
  Action:  would create → path/to/Note.md
  Reason:  ...

  Body preview:
  > ...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  N would be filed · M skipped
  No files were written. Run without --dry-run to apply.
```

Note: `/kg-extract --dry-run` on the current session is the primary way to preview what
the PreCompact hook *would* capture before running `/compact`.

---

## Step 7 — Confirm Success (skip in dry-run)

After successful extraction in normal mode, confirm the result to the user based on the
extractor output. The extractor writes its own log entry — no additional log write is needed.
