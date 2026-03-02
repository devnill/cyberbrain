#!/usr/bin/env bash
# pre-compact-extract.sh
# Claude Code PreCompact hook — extracts knowledge beats before compaction.
# Receives hook context JSON on stdin; invokes the Python extractor.

INPUT=$(cat)

# Parse all fields in a single python3 call — wrapped in explicit error guard.
# Do NOT use set -euo pipefail: a non-zero exit from a PreCompact hook blocks compaction.
if ! PARSE_OUT=$(echo "$INPUT" | python3 -c "
import sys, json, shlex
d = json.load(sys.stdin)
print('TRANSCRIPT_PATH=' + shlex.quote(d.get('transcript_path', '')))
print('SESSION_ID='      + shlex.quote(d.get('session_id', '')))
print('TRIGGER='         + shlex.quote(d.get('trigger', 'auto')))
print('CWD='             + shlex.quote(d.get('cwd', '')))
" 2>/dev/null); then
  echo "pre-compact-extract: failed to parse hook JSON, skipping" >&2
  exit 0
fi
eval "$PARSE_OUT"

if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
  echo "pre-compact-extract: transcript not found, skipping" >&2
  exit 0
fi

# Locate extractor: plugin-local copy takes precedence over installed copy
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -f "$CLAUDE_PLUGIN_ROOT/extractors/extract_beats.py" ]; then
  EXTRACTOR="$CLAUDE_PLUGIN_ROOT/extractors/extract_beats.py"
else
  EXTRACTOR="$HOME/.claude/extractors/extract_beats.py"
fi

if [ ! -f "$EXTRACTOR" ]; then
  echo "pre-compact-extract: extractor not found, skipping" >&2
  exit 0
fi

python3 "$EXTRACTOR" \
  --transcript "$TRANSCRIPT_PATH" \
  --session-id "$SESSION_ID" \
  --trigger "$TRIGGER" \
  --cwd "$CWD" \
  2>&1

# The extractor writes its own log entry to ~/.claude/logs/kg-extract.log.
# No separate registry write needed here.

exit 0
