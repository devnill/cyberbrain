#!/usr/bin/env bash
# session-end-reindex.sh
# Claude Code SessionEnd hook — runs an incremental search index refresh after
# a session ends. Runs in the background (nohup) so it never blocks the session.
# Always exits 0.

REINDEX_LOG="$HOME/.claude/cyberbrain/logs/cb-reindex.log"
mkdir -p "$(dirname "$REINDEX_LOG")"

# Pre-flight: check config exists before launching detached reindex.
CYBERBRAIN_CONFIG="$HOME/.claude/cyberbrain/config.json"
if [ ! -f "$CYBERBRAIN_CONFIG" ]; then
  echo "session-end-reindex: Cyberbrain config not found at $CYBERBRAIN_CONFIG. Run /cyberbrain:config in Claude Code to set up." >> "$REINDEX_LOG" 2>&1
  exit 0
fi

# Add common uv/Homebrew locations to PATH
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# Pre-flight: check uv is available before attempting plugin-mode launch.
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && ! command -v uv >/dev/null 2>&1; then
  echo "cyberbrain: uv not found. Install via: brew install uv" >> "$REINDEX_LOG" 2>&1
  exit 0
fi

if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
  nohup uv run --directory "$CLAUDE_PLUGIN_ROOT" \
    python -m cyberbrain.extractors.search_index \
    >> "$REINDEX_LOG" 2>&1 &
elif command -v cyberbrain-reindex >/dev/null 2>&1; then
  nohup cyberbrain-reindex >> "$REINDEX_LOG" 2>&1 &
fi

exit 0
