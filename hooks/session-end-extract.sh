#!/usr/bin/env bash
# session-end-extract.sh
# Claude Code SessionEnd hook — extracts knowledge beats when a session ends
# without having been compacted. Skips sessions already captured by PreCompact.
# Receives hook context JSON on stdin; invokes the Python extractor.

INPUT=$(cat)

# Parse all fields — same guard as pre-compact-extract.sh.
# Do NOT use set -euo pipefail: a non-zero exit from a SessionEnd hook may cause issues.
if ! PARSE_OUT=$(echo "$INPUT" | python3 -c "
import sys, json, shlex
d = json.load(sys.stdin)
print('TRANSCRIPT_PATH=' + shlex.quote(d.get('transcript_path', '')))
print('SESSION_ID='      + shlex.quote(d.get('session_id', '')))
print('TRIGGER='         + shlex.quote(d.get('trigger', 'session-end')))
print('CWD='             + shlex.quote(d.get('cwd', '')))
" 2>/dev/null); then
  echo "session-end-extract: failed to parse hook JSON, skipping" >&2
  exit 0
fi
eval "$PARSE_OUT"

if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
  echo "session-end-extract: transcript not found, skipping" >&2
  exit 0
fi

# Deduplication check: skip if already captured by PreCompact hook
SESSIONS_FILE="$HOME/.claude/kg-sessions.json"
if [ -n "$SESSION_ID" ] && [ -f "$SESSIONS_FILE" ]; then
  if python3 -c "
import sys, json
data = json.load(open('$SESSIONS_FILE'))
sys.exit(0 if '$SESSION_ID' in data.get('sessions', {}) else 1)
" 2>/dev/null; then
    echo "session-end-extract: session $SESSION_ID already captured by PreCompact, skipping" >&2
    exit 0
  fi
fi

# Locate extractor: plugin-local copy takes precedence over installed copy
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -f "$CLAUDE_PLUGIN_ROOT/extractors/extract_beats.py" ]; then
  EXTRACTOR="$CLAUDE_PLUGIN_ROOT/extractors/extract_beats.py"
else
  EXTRACTOR="$HOME/.claude/extractors/extract_beats.py"
fi

if [ ! -f "$EXTRACTOR" ]; then
  echo "session-end-extract: extractor not found, skipping" >&2
  exit 0
fi

python3 "$EXTRACTOR" \
  --transcript "$TRANSCRIPT_PATH" \
  --session-id "$SESSION_ID" \
  --trigger "session-end" \
  --cwd "$CWD" \
  2>&1

# Write session registry entry to prevent double-extraction if both hooks fire
if [ -n "$SESSION_ID" ]; then
  python3 -c "
import json, os
from pathlib import Path
from datetime import datetime, timezone

registry_path = Path.home() / '.claude' / 'kg-sessions.json'
try:
    data = json.loads(registry_path.read_text()) if registry_path.exists() else {'version': 1, 'sessions': {}}
    data.setdefault('sessions', {})['$SESSION_ID'] = {
        'extracted_at': datetime.now(timezone.utc).isoformat(),
        'trigger': 'session-end',
        'cwd': '$CWD',
    }
    tmp = str(registry_path) + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, str(registry_path))
except Exception:
    pass  # Never fail on registry write
" 2>/dev/null
fi

exit 0
