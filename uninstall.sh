#!/usr/bin/env bash
# uninstall.sh — Remove the Claude Code Cyberbrain Memory System from ~/.claude/
# Run this from the repo root.

set -euo pipefail

CLAUDE_DIR="$HOME/.claude"

BACKEND=$(python3 -c "
import json, os
path = os.path.expanduser('~/.claude/cyberbrain.json')
cfg = json.load(open(path)) if os.path.exists(path) else {}
print(cfg.get('backend', 'claude-code'))
" 2>/dev/null || echo "claude-code")

echo "Claude Code Cyberbrain Memory System — Uninstaller"
echo "========================================================"
echo ""

# ---------------------------------------------------------------------------
# Confirm unless --yes is passed
# ---------------------------------------------------------------------------
YES=0
for arg in "$@"; do
  [ "$arg" = "--yes" ] || [ "$arg" = "-y" ] && YES=1
done

if [ "$YES" -eq 0 ]; then
  echo "This will remove:"
  echo "  $CLAUDE_DIR/hooks/pre-compact-extract.sh"
  echo "  $CLAUDE_DIR/hooks/session-end-extract.sh"
  echo "  $CLAUDE_DIR/extractors/extract_beats.py"
  echo "  $CLAUDE_DIR/extractors/requirements.txt"
  echo "  $CLAUDE_DIR/prompts/extract-beats-*.md"
  echo "  $CLAUDE_DIR/prompts/autofile-*.md"
  echo "  $CLAUDE_DIR/prompts/enrich-*.md"
  echo "  $CLAUDE_DIR/prompts/claude-desktop-project.md"
  echo "  $CLAUDE_DIR/skills/cb-*/"
  echo "  $CLAUDE_DIR/cyberbrain/mcp/server.py"
  echo "  PreCompact and SessionEnd hook entries from $CLAUDE_DIR/settings.json"
  echo ""
  echo "Preserving:"
  echo "  $CLAUDE_DIR/cyberbrain.json (your settings)"
  echo ""
  printf "Continue? [y/N] "
  read -r REPLY
  if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
  fi
  echo ""
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
remove_file() {
  if [ -f "$1" ]; then
    rm "$1"
    echo "  [removed] $1"
  else
    echo "  [skip]    $1 (not found)"
  fi
}

remove_dir() {
  if [ -d "$1" ]; then
    rm -rf "$1"
    echo "  [removed] $1/"
  else
    echo "  [skip]    $1/ (not found)"
  fi
}

prune_empty_dir() {
  if [ -d "$1" ] && [ -z "$(ls -A "$1")" ]; then
    rmdir "$1"
    echo "  [pruned]  $1/ (empty)"
  fi
}

# ---------------------------------------------------------------------------
# 1. Hooks
# ---------------------------------------------------------------------------
echo "Removing hooks..."
remove_file "$CLAUDE_DIR/hooks/pre-compact-extract.sh"
remove_file "$CLAUDE_DIR/hooks/session-end-extract.sh"

# ---------------------------------------------------------------------------
# 2. Extractor
# ---------------------------------------------------------------------------
echo ""
echo "Removing extractor..."
remove_file "$CLAUDE_DIR/extractors/extract_beats.py"
remove_file "$CLAUDE_DIR/extractors/requirements.txt"
remove_file "$CLAUDE_DIR/extractors/.cb-version"

# ---------------------------------------------------------------------------
# 3. Prompts
# ---------------------------------------------------------------------------
echo ""
echo "Removing prompts..."
remove_file "$CLAUDE_DIR/prompts/extract-beats-system.md"
remove_file "$CLAUDE_DIR/prompts/extract-beats-user.md"
remove_file "$CLAUDE_DIR/prompts/autofile-system.md"
remove_file "$CLAUDE_DIR/prompts/autofile-user.md"
remove_file "$CLAUDE_DIR/prompts/enrich-system.md"
remove_file "$CLAUDE_DIR/prompts/enrich-user.md"
remove_file "$CLAUDE_DIR/prompts/claude-desktop-project.md"

# ---------------------------------------------------------------------------
# 4. Skills
# ---------------------------------------------------------------------------
echo ""
echo "Removing skills..."
remove_dir "$CLAUDE_DIR/skills/cb-recall"
remove_dir "$CLAUDE_DIR/skills/cb-file"
remove_dir "$CLAUDE_DIR/skills/cb-extract"
remove_dir "$CLAUDE_DIR/skills/cb-setup"
remove_dir "$CLAUDE_DIR/skills/cb-enrich"
remove_dir "$CLAUDE_DIR/skills/cb-claude-md"  # legacy: removed in v0.2

# ---------------------------------------------------------------------------
# 5. MCP server
# ---------------------------------------------------------------------------
echo ""
echo "Removing MCP server..."
remove_file "$CLAUDE_DIR/cyberbrain/mcp/server.py"
prune_empty_dir "$CLAUDE_DIR/cyberbrain/mcp"
prune_empty_dir "$CLAUDE_DIR/cyberbrain"

# ---------------------------------------------------------------------------
# 6. settings.json — remove PreCompact and SessionEnd hooks, preserve other settings
# Note: cyberbrain.json (user settings) is intentionally NOT removed.
# ---------------------------------------------------------------------------
echo ""
echo "Updating settings.json..."
SETTINGS="$CLAUDE_DIR/settings.json"
if [ -f "$SETTINGS" ]; then
  python3 -c "
import json, sys

path = sys.argv[1]
try:
    with open(path) as f:
        d = json.load(f)
except Exception as e:
    print(f'  [warn]    Could not parse {path}: {e}')
    print(f'            Remove hooks manually.')
    sys.exit(0)

hooks = d.get('hooks', {})
changed = False
for key in ('PreCompact', 'SessionEnd'):
    if key in hooks:
        del hooks[key]
        changed = True
        print(f'  [updated] Removed {key} hook from {path}')
    else:
        print(f'  [skip]    {key} not present in {path}')

if changed:
    if not hooks:
        del d['hooks']
    with open(path, 'w') as f:
        json.dump(d, f, indent=2)
        f.write('\n')
" "$SETTINGS"
else
  echo "  [skip]    $SETTINGS (not found)"
fi

# ---------------------------------------------------------------------------
# 8. Prune empty directories
# ---------------------------------------------------------------------------
echo ""
echo "Pruning empty directories..."
prune_empty_dir "$CLAUDE_DIR/hooks"
prune_empty_dir "$CLAUDE_DIR/extractors"
prune_empty_dir "$CLAUDE_DIR/prompts"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "========================================================"
echo "Uninstall complete."
echo ""
echo "Note: pip packages were not removed."
if [ "$BACKEND" = "bedrock" ]; then
  echo "To uninstall them, run:"
  echo "  pip uninstall anthropic pyyaml"
else
  echo "To uninstall pyyaml (used by cb-setup), run:"
  echo "  pip uninstall pyyaml"
fi
echo ""
