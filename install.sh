#!/usr/bin/env bash
# install.sh — Set up the Claude Code Cyberbrain Memory System
# Run this once from the repo root to install into ~/.claude/

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
CB_DIR="$CLAUDE_DIR/cyberbrain"

NEW_VERSION="$(cat "$REPO_DIR/VERSION" 2>/dev/null | tr -d '[:space:]' || echo "unknown")"
# Legacy fallbacks for pre-WI-034 installs (extractors/ lived at root before src layout migration)
INSTALLED_VERSION="$(cat "$CB_DIR/.cb-version" 2>/dev/null | tr -d '[:space:]' \
  || cat "$CB_DIR/extractors/.cb-version" 2>/dev/null | tr -d '[:space:]' \
  || cat "$CLAUDE_DIR/extractors/.cb-version" 2>/dev/null | tr -d '[:space:]' \
  || echo "")"

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
# M. Migration — move old scattered layout into cyberbrain/ subtree
# ---------------------------------------------------------------------------
migrate_dir()  {
  local src="$1" dst="$2"
  [ -d "$src" ] && [ ! -d "$dst" ] && mv "$src" "$dst" && echo "  Migrated $src → $dst"
  return 0
}
migrate_file() {
  local src="$1" dst="$2"
  [ -f "$src" ] && [ ! -f "$dst" ] && mv "$src" "$dst" && echo "  Migrated $src → $dst"
  return 0
}

migrate_file "$CLAUDE_DIR/cyberbrain.json"   "$CB_DIR/config.json"
migrate_dir  "$CLAUDE_DIR/extractors"        "$CB_DIR/extractors"
migrate_dir  "$CLAUDE_DIR/prompts"           "$CB_DIR/prompts"
migrate_dir  "$CLAUDE_DIR/logs"              "$CB_DIR/logs"
migrate_file "$CLAUDE_DIR/import-state.json" "$CB_DIR/import-state.json"

# ---------------------------------------------------------------------------
# 1. Create target directories
# ---------------------------------------------------------------------------
echo "Creating directories..."
mkdir -p "$CLAUDE_DIR/hooks"
mkdir -p "$CB_DIR/extractors"
mkdir -p "$CB_DIR/prompts"
mkdir -p "$CB_DIR/mcp"
mkdir -p "$CB_DIR/mcp/tools"
echo "  $CLAUDE_DIR/hooks/"
echo "  $CB_DIR/extractors/"
echo "  $CB_DIR/prompts/"
echo "  $CB_DIR/mcp/"

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
cp "$REPO_DIR/hooks/session-end-reindex.sh" "$CLAUDE_DIR/hooks/session-end-reindex.sh"
chmod +x "$CLAUDE_DIR/hooks/session-end-reindex.sh"
echo "  [OK] hooks/session-end-reindex.sh"

# Extractor → cyberbrain/extractors/
cp "$REPO_DIR/src/cyberbrain/extractors/extract_beats.py"   "$CB_DIR/extractors/extract_beats.py"
cp "$REPO_DIR/src/cyberbrain/extractors/config.py"          "$CB_DIR/extractors/config.py"
cp "$REPO_DIR/src/cyberbrain/extractors/backends.py"        "$CB_DIR/extractors/backends.py"
cp "$REPO_DIR/src/cyberbrain/extractors/transcript.py"      "$CB_DIR/extractors/transcript.py"
cp "$REPO_DIR/src/cyberbrain/extractors/frontmatter.py"     "$CB_DIR/extractors/frontmatter.py"
cp "$REPO_DIR/src/cyberbrain/extractors/vault.py"           "$CB_DIR/extractors/vault.py"
cp "$REPO_DIR/src/cyberbrain/extractors/extractor.py"       "$CB_DIR/extractors/extractor.py"
cp "$REPO_DIR/src/cyberbrain/extractors/autofile.py"        "$CB_DIR/extractors/autofile.py"
cp "$REPO_DIR/src/cyberbrain/extractors/run_log.py"         "$CB_DIR/extractors/run_log.py"
cp "$REPO_DIR/src/cyberbrain/extractors/search_backends.py" "$CB_DIR/extractors/search_backends.py"
cp "$REPO_DIR/src/cyberbrain/extractors/search_index.py"    "$CB_DIR/extractors/search_index.py"
cp "$REPO_DIR/src/cyberbrain/extractors/analyze_vault.py"   "$CB_DIR/extractors/analyze_vault.py"
cp "$REPO_DIR/src/cyberbrain/extractors/quality_gate.py"   "$CB_DIR/extractors/quality_gate.py"
cp "$REPO_DIR/src/cyberbrain/extractors/__init__.py"        "$CB_DIR/extractors/__init__.py"
echo "  [OK] cyberbrain/extractors/extract_beats.py"
echo "  [OK] cyberbrain/extractors/config.py"
echo "  [OK] cyberbrain/extractors/backends.py"
echo "  [OK] cyberbrain/extractors/transcript.py"
echo "  [OK] cyberbrain/extractors/frontmatter.py"
echo "  [OK] cyberbrain/extractors/vault.py"
echo "  [OK] cyberbrain/extractors/extractor.py"
echo "  [OK] cyberbrain/extractors/autofile.py"
echo "  [OK] cyberbrain/extractors/run_log.py"
echo "  [OK] cyberbrain/extractors/search_backends.py"
echo "  [OK] cyberbrain/extractors/search_index.py"
echo "  [OK] cyberbrain/extractors/analyze_vault.py"
echo "  [OK] cyberbrain/extractors/quality_gate.py"
echo "  [OK] cyberbrain/extractors/__init__.py"

# Prompts → cyberbrain/prompts/
cp "$REPO_DIR/src/cyberbrain/prompts/extract-beats-system.md" "$CB_DIR/prompts/extract-beats-system.md"
cp "$REPO_DIR/src/cyberbrain/prompts/extract-beats-user.md"   "$CB_DIR/prompts/extract-beats-user.md"
echo "  [OK] cyberbrain/prompts/extract-beats-system.md"
echo "  [OK] cyberbrain/prompts/extract-beats-user.md"
cp "$REPO_DIR/src/cyberbrain/prompts/autofile-system.md" "$CB_DIR/prompts/autofile-system.md"
cp "$REPO_DIR/src/cyberbrain/prompts/autofile-user.md"   "$CB_DIR/prompts/autofile-user.md"
echo "  [OK] cyberbrain/prompts/autofile-system.md"
echo "  [OK] cyberbrain/prompts/autofile-user.md"
cp "$REPO_DIR/src/cyberbrain/prompts/enrich-system.md" "$CB_DIR/prompts/enrich-system.md"
cp "$REPO_DIR/src/cyberbrain/prompts/enrich-user.md"   "$CB_DIR/prompts/enrich-user.md"
echo "  [OK] cyberbrain/prompts/enrich-system.md"
echo "  [OK] cyberbrain/prompts/enrich-user.md"
cp "$REPO_DIR/src/cyberbrain/prompts/restructure-system.md"          "$CB_DIR/prompts/restructure-system.md"
cp "$REPO_DIR/src/cyberbrain/prompts/restructure-user.md"            "$CB_DIR/prompts/restructure-user.md"
cp "$REPO_DIR/src/cyberbrain/prompts/restructure-decide-system.md"   "$CB_DIR/prompts/restructure-decide-system.md"
cp "$REPO_DIR/src/cyberbrain/prompts/restructure-decide-user.md"     "$CB_DIR/prompts/restructure-decide-user.md"
cp "$REPO_DIR/src/cyberbrain/prompts/restructure-generate-system.md" "$CB_DIR/prompts/restructure-generate-system.md"
cp "$REPO_DIR/src/cyberbrain/prompts/restructure-generate-user.md"   "$CB_DIR/prompts/restructure-generate-user.md"
cp "$REPO_DIR/src/cyberbrain/prompts/restructure-audit-system.md"    "$CB_DIR/prompts/restructure-audit-system.md"
cp "$REPO_DIR/src/cyberbrain/prompts/restructure-audit-user.md"      "$CB_DIR/prompts/restructure-audit-user.md"
cp "$REPO_DIR/src/cyberbrain/prompts/restructure-group-system.md"    "$CB_DIR/prompts/restructure-group-system.md"
cp "$REPO_DIR/src/cyberbrain/prompts/restructure-group-user.md"      "$CB_DIR/prompts/restructure-group-user.md"
echo "  [OK] cyberbrain/prompts/restructure-system.md"
echo "  [OK] cyberbrain/prompts/restructure-user.md"
echo "  [OK] cyberbrain/prompts/restructure-decide-system.md"
echo "  [OK] cyberbrain/prompts/restructure-decide-user.md"
echo "  [OK] cyberbrain/prompts/restructure-generate-system.md"
echo "  [OK] cyberbrain/prompts/restructure-generate-user.md"
echo "  [OK] cyberbrain/prompts/restructure-audit-system.md"
echo "  [OK] cyberbrain/prompts/restructure-audit-user.md"
echo "  [OK] cyberbrain/prompts/restructure-group-system.md"
echo "  [OK] cyberbrain/prompts/restructure-group-user.md"
cp "$REPO_DIR/src/cyberbrain/prompts/review-system.md" "$CB_DIR/prompts/review-system.md"
cp "$REPO_DIR/src/cyberbrain/prompts/review-user.md"   "$CB_DIR/prompts/review-user.md"
echo "  [OK] cyberbrain/prompts/review-system.md"
echo "  [OK] cyberbrain/prompts/review-user.md"
cp "$REPO_DIR/src/cyberbrain/prompts/claude-desktop-project.md" "$CB_DIR/prompts/claude-desktop-project.md"
echo "  [OK] cyberbrain/prompts/claude-desktop-project.md"
cp "$REPO_DIR/src/cyberbrain/prompts/evaluate-system.md"     "$CB_DIR/prompts/evaluate-system.md"
cp "$REPO_DIR/src/cyberbrain/prompts/quality-gate-system.md" "$CB_DIR/prompts/quality-gate-system.md"
cp "$REPO_DIR/src/cyberbrain/prompts/synthesize-system.md"   "$CB_DIR/prompts/synthesize-system.md"
cp "$REPO_DIR/src/cyberbrain/prompts/synthesize-user.md"     "$CB_DIR/prompts/synthesize-user.md"
echo "  [OK] cyberbrain/prompts/evaluate-system.md"
echo "  [OK] cyberbrain/prompts/quality-gate-system.md"
echo "  [OK] cyberbrain/prompts/synthesize-system.md"
echo "  [OK] cyberbrain/prompts/synthesize-user.md"

# MCP server package (recursive copy, excluding __pycache__)
cp -r "$REPO_DIR/src/cyberbrain/mcp/." "$CB_DIR/mcp/"
find "$CB_DIR/mcp" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
echo "  [OK] cyberbrain/mcp/ (package)"

# Write version stamp
echo "$NEW_VERSION" > "$CB_DIR/.cb-version"
echo "  [OK] cyberbrain/.cb-version (v${NEW_VERSION})"

# ---------------------------------------------------------------------------
# 3. Global config + vault path
# ---------------------------------------------------------------------------
echo ""

# Determine vault path: skip prompt on upgrade (existing config preserved)
EXISTING_VAULT=""
if [ -f "$CB_DIR/config.json" ]; then
  EXISTING_VAULT=$(python3 -c \
    "import json; c=json.load(open('$CB_DIR/config.json')); print(c.get('vault_path',''))" \
    2>/dev/null || true)
fi

DEFAULT_VAULT="$CB_DIR/vault"

if [ -z "$EXISTING_VAULT" ]; then
  echo "Where should cyberbrain store your notes?"
  echo "  Press Enter for the default: $DEFAULT_VAULT"
  echo "  Or enter the path to an existing Obsidian vault."
  read -r -p "Vault path: " VAULT_INPUT
  VAULT_PATH="${VAULT_INPUT:-$DEFAULT_VAULT}"
  mkdir -p "$VAULT_PATH"

  python3 -c "
import json
with open('$REPO_DIR/cyberbrain.example.json') as f:
    c = json.load(f)
c['vault_path'] = '$VAULT_PATH'
with open('$CB_DIR/config.json', 'w') as f:
    json.dump(c, f, indent=2)
    f.write('\n')
"
  echo "Created $CB_DIR/config.json"
  echo "  Vault: $VAULT_PATH"
else
  echo "Config already exists at $CB_DIR/config.json — skipping."
  echo "  Vault: $EXISTING_VAULT"
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
    'hooks': [
        {
            'type': 'command',
            'command': '~/.claude/hooks/pre-compact-extract.sh',
            'timeout': 120,
            'statusMessage': 'Extracting knowledge before compaction...'
        }
    ]
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
    'hooks': [
        {
            'type': 'command',
            'command': '~/.claude/hooks/session-end-extract.sh',
            'timeout': 120,
        },
        {
            'type': 'command',
            'command': '~/.claude/hooks/session-end-reindex.sh',
            'timeout': 10,
        },
    ]
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
path = os.path.expanduser('~/.claude/cyberbrain/config.json')
cfg = json.load(open(path)) if os.path.exists(path) else {}
print(cfg.get('backend', 'claude-code'))
" 2>/dev/null || echo "claude-code")

# Install the package and all dependencies into a dedicated venv (avoids system/conda Python conflicts)
MCP_VENV="$CB_DIR/venv"
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
  echo "  Installing cyberbrain package into venv ($MCP_PYTHON)..."
  if "$MCP_VENV/bin/pip" install -e "$REPO_DIR" -q; then
    if "$MCP_VENV/bin/python3" -c "from fastmcp import FastMCP" 2>/dev/null; then
      echo "  [OK] fastmcp venv ready at $MCP_VENV"
    else
      echo "  [ERROR] FastMCP import failed after install — MCP server will not work."
      echo "          Try: $MCP_PYTHON -m venv $MCP_VENV && $MCP_VENV/bin/pip install -e $REPO_DIR"
    fi
  else
    echo "  [ERROR] pip install failed — see output above."
    echo "          Try: $MCP_PYTHON -m venv $MCP_VENV && $MCP_VENV/bin/pip install -e $REPO_DIR"
  fi

  # Optional: bedrock backend (anthropic SDK)
  if [ "$BACKEND" = "bedrock" ]; then
    echo "  Installing bedrock extra (anthropic SDK)..."
    if "$MCP_VENV/bin/pip" install -e "$REPO_DIR[bedrock]" -q; then
      echo "  [OK] bedrock dependencies installed"
    else
      echo "  [WARN] bedrock extra install failed. Run: $MCP_VENV/bin/pip install -e $REPO_DIR[bedrock]"
    fi
  fi

  # Optional: semantic search layer (fastembed + usearch)
  echo ""
  echo "  Optional semantic search dependencies (fastembed + usearch):"
  if "$MCP_VENV/bin/pip" install -e "$REPO_DIR[semantic]" -q 2>/dev/null; then
    echo "  [OK] fastembed + usearch installed — hybrid semantic search enabled"
  else
    echo "  [skip] fastembed/usearch not installed — BM25 keyword search will be used."
    echo "         To enable semantic search later:"
    echo "           $MCP_VENV/bin/pip install -e $REPO_DIR[semantic]"
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
mcp_entry_point = sys.argv[2]

ENTRY = {'command': mcp_entry_point, 'args': []}

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
" "$DESKTOP_CONFIG" "${MCP_VENV:-}/bin/cyberbrain-mcp"
else
  echo "  [skip] Claude Desktop not found (macOS only)"
fi

# ---------------------------------------------------------------------------
# 8. Prune stale index entries
# ---------------------------------------------------------------------------
echo ""
echo "Pruning stale search index entries..."
PRUNE_PYTHON="${MCP_VENV:-}/bin/python3"
if [ ! -x "$PRUNE_PYTHON" ]; then
  PRUNE_PYTHON="python3"
fi
"$PRUNE_PYTHON" -c "
import sys, json
from pathlib import Path

config_path = Path.home() / '.claude' / 'cyberbrain' / 'config.json'
if not config_path.exists():
    print('  [skip] No config found — skipping prune.')
    sys.exit(0)

config = json.loads(config_path.read_text())
vault_path = config.get('vault_path', '')
db_path = config.get('search_db_path', str(Path.home() / '.claude' / 'cyberbrain' / 'search-index.db'))

if not vault_path or not Path(vault_path).exists():
    print('  [skip] vault_path not configured or does not exist — skipping prune.')
    sys.exit(0)

if not Path(db_path).exists():
    print('  [skip] No search index found — skipping prune.')
    sys.exit(0)

from cyberbrain.extractors.search_backends import FTS5Backend
b = FTS5Backend(vault_path, db_path)
pruned = b.prune_stale_notes()
if pruned:
    print(f'  [OK] Pruned {pruned} stale note(s) from search index')
else:
    print('  [OK] Search index: no stale notes found')
"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "======================================================"
echo "Installation complete."
echo ""
echo "Next steps:"
echo "  1. Notes go to the vault path configured above."
echo "     To switch: edit ~/.claude/cyberbrain/config.json (vault_path)"
echo "     or run cb_configure(discover=True) in Claude Desktop."
echo "  2. Set backend (optional):"
echo "       - claude-code (default): uses your Claude subscription — no API key needed"
echo "       - bedrock: add \"backend\": \"bedrock\" to config.json, configure AWS credentials"
echo "       - ollama: add \"backend\": \"ollama\" to config.json (local model, no API key)"
echo "  3. (Optional) Copy cyberbrain.local.example.json to .claude/cyberbrain.local.json"
echo "     in any project and update project_name and vault_folder"
echo "  4. Restart Claude Desktop to load the MCP server"
echo "  5. Use cb_recall in Claude Desktop to search your vault"
echo "  6. Run /compact in Claude Code to test the PreCompact hook"
echo ""
