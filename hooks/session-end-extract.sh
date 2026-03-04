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
# The extractor logs to ~/.claude/logs/cb-extract.log; check it here as a
# fast pre-flight so we don't spawn the extractor unnecessarily.
EXTRACT_LOG="$HOME/.claude/logs/cb-extract.log"
TAB="$(printf '\t')"
if [ -n "$SESSION_ID" ] && [ -f "$EXTRACT_LOG" ]; then
  if grep -qF "${TAB}${SESSION_ID}${TAB}" "$EXTRACT_LOG" 2>/dev/null; then
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

SESSION_END_LOG="$HOME/.claude/logs/cb-session-end.log"
mkdir -p "$(dirname "$SESSION_END_LOG")"

# Run detached: nohup + background lets extraction continue after Claude Code
# exits. setsid is Linux-only and not available on macOS.
nohup python3 "$EXTRACTOR" \
  --transcript "$TRANSCRIPT_PATH" \
  --session-id "$SESSION_ID" \
  --trigger "session-end" \
  --cwd "$CWD" \
  >> "$SESSION_END_LOG" 2>&1 &

exit 0
