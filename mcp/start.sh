#!/bin/sh
# Startup wrapper for cyberbrain MCP server.
# Finds uv in common locations and launches the server via uv run.

DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Add common uv/Homebrew locations to PATH
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# Find uv
UV=""
for candidate in uv /opt/homebrew/bin/uv /usr/local/bin/uv "$HOME/.cargo/bin/uv" "$HOME/.local/bin/uv"; do
  if command -v "$candidate" >/dev/null 2>&1; then
    UV="$candidate"
    break
  fi
done

if [ -z "$UV" ]; then
  echo "cyberbrain: uv not found — install via: brew install uv" >&2
  exit 1
fi

exec "$UV" run --directory "$DIR" python -m cyberbrain.mcp.server
