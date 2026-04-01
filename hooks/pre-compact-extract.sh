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

# Add common uv/Homebrew locations to PATH
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# Invoke extractor via uv if CLAUDE_PLUGIN_ROOT is set (plugin mode), else fall back to installed path
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && ! command -v uv >/dev/null 2>&1; then
  echo "cyberbrain: uv not found. Install via: brew install uv" >&2
  exit 0
fi

if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
  uv run --directory "$CLAUDE_PLUGIN_ROOT" python -m cyberbrain.extractors.extract_beats \
    --transcript "$TRANSCRIPT_PATH" \
    --session-id "$SESSION_ID" \
    --trigger "$TRIGGER" \
    --cwd "$CWD" \
    2>&1
  EXTRACTOR_EXIT=$?
elif command -v cyberbrain-extract >/dev/null 2>&1; then
  cyberbrain-extract \
    --transcript "$TRANSCRIPT_PATH" \
    --session-id "$SESSION_ID" \
    --trigger "$TRIGGER" \
    --cwd "$CWD" \
    2>&1
  EXTRACTOR_EXIT=$?
else
  echo "pre-compact-extract: cyberbrain not found, skipping" >&2
  exit 0
fi

if [ "${EXTRACTOR_EXIT:-0}" -ne 0 ]; then
  echo "pre-compact-extract: extractor failed (exit ${EXTRACTOR_EXIT}). Check config at ~/.claude/cyberbrain/config.json. Run /cyberbrain:config in Claude Code to set up." >&2
fi

# The extractor writes its own log entry to ~/.claude/logs/cb-extract.log.
# No separate registry write needed here.

exit 0
