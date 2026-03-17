#!/usr/bin/env bash
# session-end-reindex.sh
# Claude Code SessionEnd hook — runs an incremental search index refresh after
# a session ends. Runs in the background (nohup) so it never blocks the session.
# Always exits 0.

REINDEX_LOG="$HOME/.claude/cyberbrain/logs/cb-reindex.log"
mkdir -p "$(dirname "$REINDEX_LOG")"

if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
  nohup uv run --directory "$CLAUDE_PLUGIN_ROOT" \
    python -m cyberbrain.extractors.search_index \
    >> "$REINDEX_LOG" 2>&1 &
elif command -v cyberbrain-reindex >/dev/null 2>&1; then
  nohup cyberbrain-reindex >> "$REINDEX_LOG" 2>&1 &
fi

exit 0
