#!/usr/bin/env bash
# uninstall.sh — Remove the Claude Code Knowledge Graph Memory System from ~/.claude/
# Run this from the repo root.

set -euo pipefail

CLAUDE_DIR="$HOME/.claude"

# Read backend before we delete knowledge.json
BACKEND=$(python3 -c "
import json, os
path = os.path.expanduser('~/.claude/knowledge.json')
cfg = json.load(open(path)) if os.path.exists(path) else {}
print(cfg.get('backend', 'claude-cli'))
" 2>/dev/null || echo "claude-cli")

echo "Claude Code Knowledge Graph Memory System — Uninstaller"
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
  echo "  $CLAUDE_DIR/extractors/extract_beats.py"
  echo "  $CLAUDE_DIR/extractors/requirements.txt"
  echo "  $CLAUDE_DIR/prompts/extract-beats-system.md"
  echo "  $CLAUDE_DIR/prompts/extract-beats-user.md"
  echo "  $CLAUDE_DIR/skills/kg-recall/"
  echo "  $CLAUDE_DIR/skills/kg-file/"
  echo "  $CLAUDE_DIR/skills/kg-claude-md/"
  echo "  $CLAUDE_DIR/skills/kg-extract/"
  echo "  $CLAUDE_DIR/knowledge.json"
  echo "  PreCompact hook entry from $CLAUDE_DIR/settings.json"
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
# 1. Hook
# ---------------------------------------------------------------------------
echo "Removing hook..."
remove_file "$CLAUDE_DIR/hooks/pre-compact-extract.sh"

# ---------------------------------------------------------------------------
# 2. Extractor
# ---------------------------------------------------------------------------
echo ""
echo "Removing extractor..."
remove_file "$CLAUDE_DIR/extractors/extract_beats.py"
remove_file "$CLAUDE_DIR/extractors/requirements.txt"
remove_file "$CLAUDE_DIR/extractors/.kg-version"

# ---------------------------------------------------------------------------
# 3. Prompts
# ---------------------------------------------------------------------------
echo ""
echo "Removing prompts..."
remove_file "$CLAUDE_DIR/prompts/extract-beats-system.md"
remove_file "$CLAUDE_DIR/prompts/extract-beats-user.md"

# ---------------------------------------------------------------------------
# 4. Skills
# ---------------------------------------------------------------------------
echo ""
echo "Removing skills..."
remove_dir "$CLAUDE_DIR/skills/kg-recall"
remove_dir "$CLAUDE_DIR/skills/kg-file"
remove_dir "$CLAUDE_DIR/skills/kg-claude-md"
remove_dir "$CLAUDE_DIR/skills/kg-extract"

# ---------------------------------------------------------------------------
# 5. Global config
# ---------------------------------------------------------------------------
echo ""
echo "Removing global config..."
remove_file "$CLAUDE_DIR/knowledge.json"

# ---------------------------------------------------------------------------
# 6. settings.json — remove PreCompact hook only, preserve other settings
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
    print(f'            Remove the PreCompact entry manually.')
    sys.exit(0)

hooks = d.get('hooks', {})
if 'PreCompact' not in hooks:
    print(f'  [skip]    PreCompact not present in {path}')
    sys.exit(0)

del hooks['PreCompact']
if not hooks:
    del d['hooks']

with open(path, 'w') as f:
    json.dump(d, f, indent=2)
    f.write('\n')

print(f'  [updated] Removed PreCompact hook from {path}')
" "$SETTINGS"
else
  echo "  [skip]    $SETTINGS (not found)"
fi

# ---------------------------------------------------------------------------
# 7. Prune empty directories
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
if [ "$BACKEND" = "anthropic" ] || [ "$BACKEND" = "bedrock" ]; then
  echo "To uninstall them, run:"
  echo "  pip uninstall anthropic pyyaml"
else
  echo "To uninstall pyyaml (used by kg-claude-md), run:"
  echo "  pip uninstall pyyaml"
fi
echo ""
