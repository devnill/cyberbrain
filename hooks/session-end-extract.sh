#!/usr/bin/env bash
# session-end-extract.sh
# Claude Code SessionEnd hook — extracts knowledge beats when a session ends
# without having been compacted. Skips sessions already captured by PreCompact.
# Receives hook context JSON on stdin; invokes the Python extractor.
#
# The extractor runs detached (setsid + background) so it survives Claude Code
# exiting. Output goes to ~/.claude/logs/cb-session-end.log instead of stderr
# (stderr is discarded once the session closes).

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

# Deduplication check: skip if already captured by PreCompact hook.
# The extractor logs to ~/.claude/cyberbrain/logs/cb-extract.log; check it here as a
# fast pre-flight so we don't spawn the extractor unnecessarily.
EXTRACT_LOG="$HOME/.claude/cyberbrain/logs/cb-extract.log"
TAB="$(printf '\t')"
if [ -n "$SESSION_ID" ] && [ -f "$EXTRACT_LOG" ]; then
  if grep -qF "${TAB}${SESSION_ID}${TAB}" "$EXTRACT_LOG" 2>/dev/null; then
    exit 0
  fi
fi

SESSION_END_LOG="$HOME/.claude/logs/cb-session-end.log"
mkdir -p "$(dirname "$SESSION_END_LOG")"

# Invoke extractor via uv if CLAUDE_PLUGIN_ROOT is set (plugin mode), else fall back to installed path
# Run detached: nohup + background lets extraction continue after Claude Code exits.
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
  nohup uv run --directory "$CLAUDE_PLUGIN_ROOT" python -m cyberbrain.extractors.extract_beats \
    --transcript "$TRANSCRIPT_PATH" \
    --session-id "$SESSION_ID" \
    --trigger "session-end" \
    --cwd "$CWD" \
    >> "$SESSION_END_LOG" 2>&1 &
elif command -v cyberbrain-extract >/dev/null 2>&1; then
  nohup cyberbrain-extract \
    --transcript "$TRANSCRIPT_PATH" \
    --session-id "$SESSION_ID" \
    --trigger "session-end" \
    --cwd "$CWD" \
    >> "$SESSION_END_LOG" 2>&1 &
else
  echo "session-end-extract: cyberbrain not found, skipping" >&2
  exit 0
fi

exit 0
