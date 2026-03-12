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

# Invoke extractor via uv if CLAUDE_PLUGIN_ROOT is set (plugin mode), else fall back to installed path
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
  uv run --directory "$CLAUDE_PLUGIN_ROOT" python -m cyberbrain.extractors.extract_beats \
    --transcript "$TRANSCRIPT_PATH" \
    --session-id "$SESSION_ID" \
    --trigger "$TRIGGER" \
    --cwd "$CWD" \
    2>&1
elif command -v cyberbrain-extract >/dev/null 2>&1; then
  cyberbrain-extract \
    --transcript "$TRANSCRIPT_PATH" \
    --session-id "$SESSION_ID" \
    --trigger "$TRIGGER" \
    --cwd "$CWD" \
    2>&1
else
  echo "pre-compact-extract: cyberbrain not found, skipping" >&2
  exit 0
fi

# The extractor writes its own log entry to ~/.claude/logs/cb-extract.log.
# No separate registry write needed here.

exit 0
