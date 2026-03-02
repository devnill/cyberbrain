#!/usr/bin/env bash
# install.sh — Set up the Claude Code Cyberbrain Memory System
# Run this once from the repo root to install into ~/.claude/

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"

NEW_VERSION="$(cat "$REPO_DIR/VERSION" 2>/dev/null | tr -d '[:space:]' || echo "unknown")"
INSTALLED_VERSION="$(cat "$CLAUDE_DIR/extractors/.cb-version" 2>/dev/null | tr -d '[:space:]' || echo "")"

echo "Claude Code Cyberbrain Memory System — Installer (v${NEW_VERSION})"
echo "======================================================"
if [ -z "$INSTALLED_VERSION" ]; then
  echo "Fresh install"
elif [ "$INSTALLED_VERSION" = "$NEW_VERSION" ]; then
  echo "Reinstalling v${NEW_VERSION}"
else
  echo "Upgrading from v${INSTALLED_VERSION} to v${NEW_VERSION}"
fi
echo ""

# ---------------------------------------------------------------------------
# 0. Build .skill packages
# ---------------------------------------------------------------------------
echo "Building skill packages..."
bash "$REPO_DIR/build.sh" --skills-only
echo ""

# ---------------------------------------------------------------------------
# 1. Create target directories
# ---------------------------------------------------------------------------
echo "Creating directories..."
mkdir -p "$CLAUDE_DIR/hooks"
mkdir -p "$CLAUDE_DIR/extractors"
mkdir -p "$CLAUDE_DIR/prompts"
mkdir -p "$CLAUDE_DIR/skills"
mkdir -p "$CLAUDE_DIR/cyberbrain/mcp"
echo "  $CLAUDE_DIR/hooks/"
echo "  $CLAUDE_DIR/extractors/"
echo "  $CLAUDE_DIR/prompts/"
echo "  $CLAUDE_DIR/skills/"
echo "  $CLAUDE_DIR/cyberbrain/mcp/"

# ---------------------------------------------------------------------------
# 2. Install files
# ---------------------------------------------------------------------------
echo ""
echo "Installing files..."

# Hooks
cp "$REPO_DIR/hooks/pre-compact-extract.sh" "$CLAUDE_DIR/hooks/pre-compact-extract.sh"
chmod +x "$CLAUDE_DIR/hooks/pre-compact-extract.sh"
echo "  [OK] hooks/pre-compact-extract.sh"
cp "$REPO_DIR/hooks/session-end-extract.sh" "$CLAUDE_DIR/hooks/session-end-extract.sh"
chmod +x "$CLAUDE_DIR/hooks/session-end-extract.sh"
echo "  [OK] hooks/session-end-extract.sh"

# Extractor
cp "$REPO_DIR/extractors/extract_beats.py" "$CLAUDE_DIR/extractors/extract_beats.py"
cp "$REPO_DIR/extractors/requirements.txt" "$CLAUDE_DIR/extractors/requirements.txt"
echo "  [OK] extractors/extract_beats.py"
echo "  [OK] extractors/requirements.txt"

# Prompts
cp "$REPO_DIR/prompts/extract-beats-system.md" "$CLAUDE_DIR/prompts/extract-beats-system.md"
cp "$REPO_DIR/prompts/extract-beats-user.md"   "$CLAUDE_DIR/prompts/extract-beats-user.md"
echo "  [OK] prompts/extract-beats-system.md"
echo "  [OK] prompts/extract-beats-user.md"
cp "$REPO_DIR/prompts/autofile-system.md" "$CLAUDE_DIR/prompts/autofile-system.md"
cp "$REPO_DIR/prompts/autofile-user.md"   "$CLAUDE_DIR/prompts/autofile-user.md"
echo "  [OK] prompts/autofile-system.md"
echo "  [OK] prompts/autofile-user.md"
cp "$REPO_DIR/prompts/enrich-system.md" "$CLAUDE_DIR/prompts/enrich-system.md"
cp "$REPO_DIR/prompts/enrich-user.md"   "$CLAUDE_DIR/prompts/enrich-user.md"
echo "  [OK] prompts/enrich-system.md"
echo "  [OK] prompts/enrich-user.md"
cp "$REPO_DIR/prompts/claude-desktop-project.md" "$CLAUDE_DIR/prompts/claude-desktop-project.md"
echo "  [OK] prompts/claude-desktop-project.md"

# Skills — prefer pre-built .skill packages from dist/ if available;
# fall back to copying source directories (useful during local development).
install_skill() {
  local name="$1"
  local pkg="$REPO_DIR/dist/$name.skill"
  if [ -f "$pkg" ]; then
    unzip -o -q "$pkg" -d "$CLAUDE_DIR/skills/"
    echo "  [OK] skills/$name/ (from $name.skill)"
  else
    cp -r "$REPO_DIR/skills/$name" "$CLAUDE_DIR/skills/$name"
    echo "  [OK] skills/$name/ (from source)"
  fi
}

install_skill cb-recall
install_skill cb-file
install_skill cb-setup
install_skill cb-extract
install_skill cb-enrich

# MCP server
cp "$REPO_DIR/mcp/server.py" "$CLAUDE_DIR/cyberbrain/mcp/server.py"
echo "  [OK] cyberbrain/mcp/server.py"

# Write version stamp so future installs can detect upgrades
echo "$NEW_VERSION" > "$CLAUDE_DIR/extractors/.cb-version"
echo "  [OK] extractors/.cb-version (v${NEW_VERSION})"

# ---------------------------------------------------------------------------
# 3. Global config
# ---------------------------------------------------------------------------
echo ""
GLOBAL_CONFIG="$CLAUDE_DIR/cyberbrain.json"
if [ -f "$GLOBAL_CONFIG" ]; then
  echo "Global config already exists at $GLOBAL_CONFIG — skipping."
  echo "  Edit it manually if you need to update your vault path."
else
  cp "$REPO_DIR/cyberbrain.example.json" "$GLOBAL_CONFIG"
  echo "Created $GLOBAL_CONFIG"
  echo ""
  echo "  *** ACTION REQUIRED ***"
  echo "  Edit $GLOBAL_CONFIG and set your Obsidian vault path:"
  echo "    \"vault_path\": \"/absolute/path/to/your/vault\""
fi

# ---------------------------------------------------------------------------
# 4. Register PreCompact hook in settings.json
# ---------------------------------------------------------------------------
echo ""
echo "Registering PreCompact hook in settings.json..."
python3 -c "
import json, sys
from pathlib import Path

path = Path(sys.argv[1])

DESIRED = {
    'hooks': [{
        'type': 'command',
        'command': '~/.claude/hooks/pre-compact-extract.sh',
        'timeout': 120,
        'statusMessage': 'Extracting knowledge before compaction...'
    }]
}

# Load existing config or start fresh
if path.exists():
    try:
        with open(path) as f:
            d = json.load(f)
    except Exception as e:
        print(f'  [warn] Could not parse {path}: {e}')
        print(f'         Add the PreCompact hook manually.')
        sys.exit(0)
else:
    d = {}

DESIRED_SESSION_END = {
    'hooks': [{
        'type': 'command',
        'command': '~/.claude/hooks/session-end-extract.sh',
        'timeout': 120,
    }]
}

existing_precompact = d.get('hooks', {}).get('PreCompact')
existing_session_end = d.get('hooks', {}).get('SessionEnd')

# Always write so upgrades propagate
d.setdefault('hooks', {})['PreCompact'] = [DESIRED]
d.setdefault('hooks', {})['SessionEnd'] = [DESIRED_SESSION_END]

path.parent.mkdir(parents=True, exist_ok=True)
with open(path, 'w') as f:
    json.dump(d, f, indent=2)
    f.write('\n')

if existing_precompact is None:
    print(f'  [OK] PreCompact hook registered in {path}')
else:
    print(f'  [OK] PreCompact hook up to date')

if existing_session_end is None:
    print(f'  [OK] SessionEnd hook registered in {path}')
else:
    print(f'  [OK] SessionEnd hook up to date')
" "$CLAUDE_DIR/settings.json"

# ---------------------------------------------------------------------------
# 5. Python dependencies
# ---------------------------------------------------------------------------
echo ""
BACKEND=$(python3 -c "
import json, os
path = os.path.expanduser('~/.claude/cyberbrain.json')
cfg = json.load(open(path)) if os.path.exists(path) else {}
print(cfg.get('backend', 'claude-code'))
" 2>/dev/null || echo "claude-code")

if [ "$BACKEND" = "bedrock" ]; then
  echo "Installing Python dependencies (bedrock backend)..."
  if python3 -m pip install -r "$CLAUDE_DIR/extractors/requirements.txt" -q; then
    echo "  [OK] dependencies installed"
  else
    echo "  [WARN] pip install failed. Run: pip install anthropic pyyaml"
  fi
else
  echo "  [skip] anthropic package not needed for backend=$BACKEND"
  # Still install pyyaml (used by cb-setup)
  python3 -m pip install pyyaml -q 2>/dev/null || true
fi

# Install MCP package into a dedicated venv (avoids system/conda Python conflicts)
MCP_VENV="$CLAUDE_DIR/cyberbrain/venv"
MCP_PYTHON=""
# Prefer Python 3.11/3.12 — mcp wheels are not yet available for Python 3.14+
for candidate in python3.12 python3.11 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
  if command -v "$candidate" &>/dev/null && "$candidate" -m venv --help &>/dev/null; then
    MCP_PYTHON=$(command -v "$candidate")
    break
  fi
done

if [ -n "$MCP_PYTHON" ]; then
  if [ ! -d "$MCP_VENV" ]; then
    "$MCP_PYTHON" -m venv "$MCP_VENV"
  fi
  echo "  Installing mcp into venv ($MCP_PYTHON)..."
  if "$MCP_VENV/bin/pip" install mcp -q; then
    if "$MCP_VENV/bin/python3" -c "from mcp.server.fastmcp import FastMCP" 2>/dev/null; then
      echo "  [OK] mcp venv ready at $MCP_VENV"
    else
      echo "  [ERROR] FastMCP import failed after install — MCP server will not work."
      echo "          Try: $MCP_PYTHON -m venv $MCP_VENV && $MCP_VENV/bin/pip install mcp"
    fi
  else
    echo "  [ERROR] pip install mcp failed — see output above."
    echo "          Try: $MCP_PYTHON -m venv $MCP_VENV && $MCP_VENV/bin/pip install mcp"
  fi
else
  echo "  [WARN] Could not find a suitable Python for the MCP venv. Install python3 via Homebrew."
fi

# ---------------------------------------------------------------------------
# 6. Check credentials / CLI
# ---------------------------------------------------------------------------
echo ""
if [ "$BACKEND" = "claude-code" ]; then
  if command -v claude &>/dev/null; then
    echo "  [OK] 'claude' CLI found in PATH (claude-code backend)"
  else
    echo "  *** ACTION REQUIRED ***"
    echo "  backend is set to 'claude-code' but 'claude' is not in PATH."
    echo "  Install Claude Code: https://claude.ai/download"
  fi
elif [ "$BACKEND" = "bedrock" ]; then
  if aws sts get-caller-identity &>/dev/null; then
    echo "  [OK] AWS credentials configured (Bedrock backend)"
  else
    echo "  *** ACTION REQUIRED ***"
    echo "  backend is set to 'bedrock' but AWS credentials are not configured."
    echo "  Set up AWS credentials via 'aws configure' or environment variables."
  fi
elif [ "$BACKEND" = "ollama" ]; then
  echo "  [OK] ollama backend — no credentials required (local model)"
else
  echo "  [warn] Unknown backend '$BACKEND' — verify credentials manually."
fi

# ---------------------------------------------------------------------------
# 7. Register MCP server in Claude Desktop (macOS only)
# ---------------------------------------------------------------------------
echo ""
DESKTOP_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
if [ "$(uname)" = "Darwin" ] && [ -d "$HOME/Library/Application Support/Claude" ]; then
  echo "Registering MCP server in Claude Desktop..."
  python3 -c "
import json, sys
from pathlib import Path

path = Path(sys.argv[1])
server_path = sys.argv[2]
venv_python = sys.argv[3]

ENTRY = {'command': venv_python, 'args': [server_path]}

if path.exists():
    try:
        cfg = json.loads(path.read_text())
    except Exception as e:
        print(f'  [warn] Could not parse {path}: {e}')
        print(f'         Add the MCP server manually.')
        sys.exit(0)
else:
    cfg = {}

existing = cfg.get('mcpServers', {}).get('cyberbrain')
cfg.setdefault('mcpServers', {})['cyberbrain'] = ENTRY

path.write_text(json.dumps(cfg, indent=2) + '\n')

if existing is None:
    print(f'  [OK] cyberbrain MCP server registered in Claude Desktop')
elif existing == ENTRY:
    print(f'  [OK] cyberbrain MCP server already up to date')
else:
    print(f'  [OK] cyberbrain MCP server updated in Claude Desktop')
print('  Restart Claude Desktop for the change to take effect.')
" "$DESKTOP_CONFIG" "$CLAUDE_DIR/cyberbrain/mcp/server.py" "${MCP_VENV:-}/bin/python3"
else
  echo "  [skip] Claude Desktop not found (macOS only)"
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "======================================================"
echo "Installation complete."
echo ""
echo "Next steps:"
echo "  1. Edit ~/.claude/cyberbrain.json — set vault_path to your Obsidian vault"
echo "  2. Set backend (optional):"
echo "       - claude-code (default): uses your Claude subscription — no API key needed"
echo "       - bedrock: add \"backend\": \"bedrock\" to cyberbrain.json, configure AWS credentials"
echo "       - ollama: add \"backend\": \"ollama\" to cyberbrain.json (local model, no API key)"
echo "  3. (Optional) Copy cyberbrain.local.example.json to .claude/cyberbrain.local.json"
echo "     in any project and update project_name and vault_folder"
echo "  4. Run /compact in a Claude Code session to test the hook"
echo "  5. Use /cb-recall <query> to retrieve knowledge in any session"
echo "  6. Use /cb-extract <path> to backfill beats from old session logs"
echo ""
