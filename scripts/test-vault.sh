#!/usr/bin/env bash
# test-vault.sh — Deploy, reset, and manage mock vault variants for manual testing.
#
# Usage:
#   bash scripts/test-vault.sh deploy <variant>   # deep-copy vault, update config
#   bash scripts/test-vault.sh reset              # restore active vault from repo copy
#   bash scripts/test-vault.sh list               # show available variants
#   bash scripts/test-vault.sh status             # show deployed variant and modifications
#   bash scripts/test-vault.sh teardown           # restore original vault_path

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VAULTS_DIR="$REPO_ROOT/tests/vaults"
CONFIG_DIR="$HOME/.claude/cyberbrain"
CONFIG_FILE="$CONFIG_DIR/config.json"
DEPLOY_DIR="$CONFIG_DIR/test-vault"
STATE_FILE="$CONFIG_DIR/.test-vault-state.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_require_python() {
    command -v python3 >/dev/null 2>&1 || { echo "Error: python3 not found"; exit 1; }
}

_read_config_field() {
    local field="$1"
    _require_python
    CB_CONFIG_FILE="$CONFIG_FILE" CB_FIELD="$field" python3 -c "
import json, os, sys
path = os.environ['CB_CONFIG_FILE']
if not os.path.exists(path):
    sys.exit(0)
cfg = json.load(open(path))
print(cfg.get(os.environ['CB_FIELD'], ''))
" 2>/dev/null || echo ""
}

_write_config_field() {
    local field="$1"
    local value="$2"
    _require_python
    CB_CONFIG_FILE="$CONFIG_FILE" CB_FIELD="$field" CB_VALUE="$value" python3 -c "
import json, os
path = os.environ['CB_CONFIG_FILE']
cfg = {}
if os.path.exists(path):
    cfg = json.load(open(path))
cfg[os.environ['CB_FIELD']] = os.environ['CB_VALUE']
with open(path, 'w') as f:
    json.dump(cfg, f, indent=2)
    f.write('\n')
"
}

_save_state() {
    local variant="$1"
    local original_vault_path="$2"
    _require_python
    CB_STATE_FILE="$STATE_FILE" CB_VARIANT="$variant" CB_ORIG="$original_vault_path" python3 -c "
import json, os
state = {'variant': os.environ['CB_VARIANT'], 'original_vault_path': os.environ['CB_ORIG']}
with open(os.environ['CB_STATE_FILE'], 'w') as f:
    json.dump(state, f, indent=2)
    f.write('\n')
"
}

_load_state_field() {
    local field="$1"
    _require_python
    CB_STATE_FILE="$STATE_FILE" CB_FIELD="$field" python3 -c "
import json, os, sys
path = os.environ['CB_STATE_FILE']
if not os.path.exists(path):
    sys.exit(0)
state = json.load(open(path))
print(state.get(os.environ['CB_FIELD'], ''))
" 2>/dev/null || echo ""
}

_rewrite_dates() {
    # Rewrite REVIEW_DATE_PAST_N and REVIEW_DATE_SOON_N and REVIEW_DATE_FUTURE_N
    # placeholders in vault files to dates relative to today.
    local vault_dir="$1"
    _require_python
    CB_VAULT_DIR="$vault_dir" python3 -c "
import os, re
from datetime import date, timedelta

today = date.today()
vault_dir = os.environ['CB_VAULT_DIR']

# Past-due dates: 7, 14, 21, 28, 35 days ago
past_dates = {
    'REVIEW_DATE_PAST_1': (today - timedelta(days=7)).isoformat(),
    'REVIEW_DATE_PAST_2': (today - timedelta(days=14)).isoformat(),
    'REVIEW_DATE_PAST_3': (today - timedelta(days=21)).isoformat(),
    'REVIEW_DATE_PAST_4': (today - timedelta(days=28)).isoformat(),
    'REVIEW_DATE_PAST_5': (today - timedelta(days=35)).isoformat(),
}

# Due within 7 days: 1, 2, 3, 5, 7 days from now
soon_dates = {
    'REVIEW_DATE_SOON_1': (today + timedelta(days=1)).isoformat(),
    'REVIEW_DATE_SOON_2': (today + timedelta(days=2)).isoformat(),
    'REVIEW_DATE_SOON_3': (today + timedelta(days=3)).isoformat(),
    'REVIEW_DATE_SOON_4': (today + timedelta(days=5)).isoformat(),
    'REVIEW_DATE_SOON_5': (today + timedelta(days=7)).isoformat(),
}

# Future dates: 14, 21, 28, 42, 56 days from now
future_dates = {
    'REVIEW_DATE_FUTURE_1': (today + timedelta(days=14)).isoformat(),
    'REVIEW_DATE_FUTURE_2': (today + timedelta(days=21)).isoformat(),
    'REVIEW_DATE_FUTURE_3': (today + timedelta(days=28)).isoformat(),
    'REVIEW_DATE_FUTURE_4': (today + timedelta(days=42)).isoformat(),
    'REVIEW_DATE_FUTURE_5': (today + timedelta(days=56)).isoformat(),
}

all_dates = {**past_dates, **soon_dates, **future_dates}

for root, dirs, files in os.walk(vault_dir):
    for fname in files:
        if not fname.endswith('.md'):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, 'r') as f:
            content = f.read()
        original = content
        for placeholder, date_str in all_dates.items():
            content = content.replace(placeholder, date_str)
        if content != original:
            with open(fpath, 'w') as f:
                f.write(content)
"
}

_compute_checksum() {
    # Compute a combined checksum of all files in a directory.
    local dir="$1"
    find "$dir" -type f -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256 | awk '{print $1}'
}

_save_checksum() {
    local dir="$1"
    local checksum
    checksum="$(_compute_checksum "$dir")"
    echo "$checksum" > "$CONFIG_DIR/.test-vault-checksum"
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

cmd_deploy() {
    local variant="${1:-}"
    if [ -z "$variant" ]; then
        echo "Usage: test-vault.sh deploy <variant>"
        echo "Run 'test-vault.sh list' to see available variants."
        exit 1
    fi

    local source_dir="$VAULTS_DIR/$variant"
    if [ ! -d "$source_dir" ]; then
        echo "Error: Variant '$variant' not found at $source_dir"
        echo "Run 'test-vault.sh list' to see available variants."
        exit 1
    fi

    # Save current vault_path for teardown
    local current_vault_path
    current_vault_path="$(_read_config_field vault_path)"

    # Don't overwrite original if we're already in a test vault session
    local existing_variant
    existing_variant="$(_load_state_field variant)"
    if [ -z "$existing_variant" ] && [ -n "$current_vault_path" ]; then
        _save_state "$variant" "$current_vault_path"
    elif [ -n "$existing_variant" ]; then
        # Update variant but keep original vault_path
        local orig
        orig="$(_load_state_field original_vault_path)"
        _save_state "$variant" "$orig"
    else
        _save_state "$variant" ""
    fi

    # Deep copy vault to deploy directory
    rm -rf "$DEPLOY_DIR"
    mkdir -p "$DEPLOY_DIR"
    cp -r "$source_dir/." "$DEPLOY_DIR/"

    # Rewrite date placeholders for working-memory and mature vaults
    if [ "$variant" = "working-memory" ] || [ "$variant" = "mature" ]; then
        _rewrite_dates "$DEPLOY_DIR"
    fi

    # Deploy wm-recall.jsonl to ~/.claude/cyberbrain/ if present in vault source
    if [ -f "$DEPLOY_DIR/wm-recall.jsonl" ]; then
        # Back up user's real wm-recall.jsonl before overwriting
        if [ -f "$CONFIG_DIR/wm-recall.jsonl" ] && [ ! -f "$CONFIG_DIR/.wm-recall.jsonl.bak" ]; then
            cp "$CONFIG_DIR/wm-recall.jsonl" "$CONFIG_DIR/.wm-recall.jsonl.bak"
        fi
        cp "$DEPLOY_DIR/wm-recall.jsonl" "$CONFIG_DIR/wm-recall.jsonl"
        rm "$DEPLOY_DIR/wm-recall.jsonl"
    fi

    # Update config.json to point to the test vault
    mkdir -p "$CONFIG_DIR"
    _write_config_field vault_path "$DEPLOY_DIR"

    # Save content checksum for modification detection
    _save_checksum "$DEPLOY_DIR"

    echo "Deployed '$variant' vault to $DEPLOY_DIR"
    echo "Config updated: vault_path = $DEPLOY_DIR"
}

cmd_reset() {
    local variant
    variant="$(_load_state_field variant)"
    if [ -z "$variant" ]; then
        echo "No test vault is currently deployed."
        exit 1
    fi

    local source_dir="$VAULTS_DIR/$variant"
    if [ ! -d "$source_dir" ]; then
        echo "Error: Source variant '$variant' not found at $source_dir"
        exit 1
    fi

    # Re-copy from source
    rm -rf "$DEPLOY_DIR"
    mkdir -p "$DEPLOY_DIR"
    cp -r "$source_dir/." "$DEPLOY_DIR/"

    # Rewrite dates again
    if [ "$variant" = "working-memory" ] || [ "$variant" = "mature" ]; then
        _rewrite_dates "$DEPLOY_DIR"
    fi

    # Deploy wm-recall.jsonl to ~/.claude/cyberbrain/ if present
    if [ -f "$DEPLOY_DIR/wm-recall.jsonl" ]; then
        cp "$DEPLOY_DIR/wm-recall.jsonl" "$CONFIG_DIR/wm-recall.jsonl"
        rm "$DEPLOY_DIR/wm-recall.jsonl"
    fi

    # Save content checksum for modification detection
    _save_checksum "$DEPLOY_DIR"

    echo "Reset '$variant' vault to initial state."
}

cmd_list() {
    echo "Available vault variants:"
    echo ""
    echo "  empty          Fresh onboarding — no notes, no CLAUDE.md"
    echo "  para           PARA methodology — Projects/Areas/Resources/Archive (18 notes)"
    echo "  zettelkasten   Zettelkasten — flat atomic notes with extensive linking (21 notes)"
    echo "  mature         Full feature coverage — all beat types, WM, locked, trash (40+ notes)"
    echo "  working-memory WM lifecycle focus — 18 ephemeral notes with varied review dates"
}

cmd_status() {
    local variant
    variant="$(_load_state_field variant)"
    if [ -z "$variant" ]; then
        echo "No test vault is currently deployed."
        return
    fi

    local original
    original="$(_load_state_field original_vault_path)"

    echo "Deployed variant: $variant"
    echo "Deploy directory:  $DEPLOY_DIR"
    echo "Original vault:    ${original:-<none>}"

    # Check if the deployed vault has been modified
    if [ ! -d "$DEPLOY_DIR" ]; then
        echo "Status: MISSING (deploy directory does not exist)"
        return
    fi

    # Compare content checksum to detect modifications
    local current_checksum saved_checksum
    current_checksum="$(_compute_checksum "$DEPLOY_DIR")"
    saved_checksum=""
    if [ -f "$CONFIG_DIR/.test-vault-checksum" ]; then
        saved_checksum="$(cat "$CONFIG_DIR/.test-vault-checksum")"
    fi

    if [ "$current_checksum" = "$saved_checksum" ]; then
        echo "Status: Deployed (unmodified)"
    else
        echo "Status: MODIFIED (content has changed since deploy/reset)"
    fi
}

cmd_teardown() {
    local original
    original="$(_load_state_field original_vault_path)"

    if [ -z "$original" ] && [ ! -f "$STATE_FILE" ]; then
        echo "No test vault session to tear down."
        exit 1
    fi

    # Restore original vault_path
    if [ -n "$original" ]; then
        _write_config_field vault_path "$original"
        echo "Restored vault_path to: $original"
    else
        echo "Warning: No original vault_path to restore."
    fi

    # Restore original wm-recall.jsonl if backed up
    if [ -f "$CONFIG_DIR/.wm-recall.jsonl.bak" ]; then
        mv "$CONFIG_DIR/.wm-recall.jsonl.bak" "$CONFIG_DIR/wm-recall.jsonl"
        echo "Restored wm-recall.jsonl from backup."
    else
        rm -f "$CONFIG_DIR/wm-recall.jsonl"
    fi

    # Clean up
    rm -rf "$DEPLOY_DIR"
    rm -f "$STATE_FILE"
    rm -f "$CONFIG_DIR/.test-vault-checksum"
    echo "Test vault torn down."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

command="${1:-}"
shift || true

case "$command" in
    deploy)   cmd_deploy "$@" ;;
    reset)    cmd_reset ;;
    list)     cmd_list ;;
    status)   cmd_status ;;
    teardown) cmd_teardown ;;
    *)
        echo "Usage: test-vault.sh <command> [args]"
        echo ""
        echo "Commands:"
        echo "  deploy <variant>  Deploy a vault variant for testing"
        echo "  reset             Restore active test vault to initial state"
        echo "  list              Show available variants"
        echo "  status            Show current deployment status"
        echo "  teardown          Restore original vault_path and clean up"
        exit 1
        ;;
esac
