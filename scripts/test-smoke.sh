#!/usr/bin/env bash
# test-smoke.sh — Manual smoke test for the knowledge graph memory system.
#
# Verifies the happy path end-to-end without making any LLM API calls.
# Run this from the repo root after install.sh:
#
#   bash scripts/test-smoke.sh
#
# Exit codes:
#   0 — all tests passed
#   1 — one or more tests failed

set -euo pipefail

PASS=0
FAIL=0
EXTRACTOR="${HOME}/.claude/cyberbrain/extractors/extract_beats.py"
HOOK="${HOME}/.claude/hooks/pre-compact-extract.sh"
MCP_VENV="${HOME}/.claude/cyberbrain/venv"

# Resolve vault_path and inbox from config
VAULT_PATH=$(python3 -c "
import json, os
path = os.path.expanduser('~/.claude/cyberbrain/config.json')
cfg = json.load(open(path)) if os.path.exists(path) else {}
print(cfg.get('vault_path', ''))
" 2>/dev/null || echo "")

INBOX=$(python3 -c "
import json, os
path = os.path.expanduser('~/.claude/cyberbrain/config.json')
cfg = json.load(open(path)) if os.path.exists(path) else {}
print(cfg.get('inbox', 'AI/Claude-Sessions'))
" 2>/dev/null || echo "AI/Claude-Sessions")

AUTOFILE=$(python3 -c "
import json, os
path = os.path.expanduser('~/.claude/cyberbrain/config.json')
cfg = json.load(open(path)) if os.path.exists(path) else {}
print('true' if cfg.get('autofile', False) else 'false')
" 2>/dev/null || echo "false")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

pass() { echo "  [PASS] $1"; PASS=$((PASS + 1)); }
fail() { echo "  [FAIL] $1"; FAIL=$((FAIL + 1)); }

section() { echo ""; echo "--- $1 ---"; }

# ---------------------------------------------------------------------------
# Test 1: extractor writes a beat from pre-extracted JSON (no LLM call)
# ---------------------------------------------------------------------------
section "Test 1: extract_beats.py --beats-json (no LLM call)"

BEATS_FILE="/tmp/kg-smoke-beats-$$.json"
cat > "$BEATS_FILE" <<'EOF'
[{
  "type": "insight",
  "scope": "general",
  "title": "Smoke Test Beat",
  "summary": "This beat was written by the smoke test to verify the extractor pipeline.",
  "tags": ["smoke-test", "ci"],
  "body": "## Smoke Test Beat\n\nThis note was created by `scripts/test-smoke.sh` to verify the extraction pipeline works end-to-end without an LLM API call."
}]
EOF

if [ ! -f "$EXTRACTOR" ]; then
  fail "extract_beats.py not found at $EXTRACTOR (run install.sh first)"
else
  EXTRACTOR_OUT=$(python3 "$EXTRACTOR" \
    --beats-json "$BEATS_FILE" \
    --session-id "smoke-test-$$" \
    --trigger manual \
    --cwd /tmp 2>&1)

  WRITTEN_PATH=$(echo "$EXTRACTOR_OUT" | grep '^\[extract_beats\] Wrote:' | head -1 | sed 's/\[extract_beats\] Wrote: //')

  if [ -z "$WRITTEN_PATH" ]; then
    fail "No 'Wrote:' line in extractor output — beat was not written"
    echo "    Output: $EXTRACTOR_OUT" | head -5
  elif [ ! -f "$WRITTEN_PATH" ]; then
    fail "Extractor reported writing $WRITTEN_PATH but file does not exist"
  else
    pass "Beat written to $WRITTEN_PATH"

    # Verify the beat content appears in the written file
    if grep -q "Smoke Test Beat" "$WRITTEN_PATH"; then
      pass "Content: beat title found in written file"
    else
      fail "Content: beat title not found in written file"
    fi

    # Frontmatter checks only apply to freshly created notes (autofile=false or action=create)
    # When autofile=true and action=extend, the new section is appended to an existing note
    if [ "$AUTOFILE" = "false" ]; then
      if grep -q "^type: insight" "$WRITTEN_PATH"; then
        pass "Frontmatter: type=insight"
      else
        fail "Frontmatter missing or wrong type field"
      fi

      if grep -q "^session_id:" "$WRITTEN_PATH"; then
        pass "Frontmatter: session_id present"
      else
        fail "Frontmatter missing session_id"
      fi

      if grep -q "^summary:" "$WRITTEN_PATH"; then
        pass "Frontmatter: summary present"
      else
        fail "Frontmatter missing summary"
      fi
    else
      pass "Frontmatter checks skipped (autofile=true — beat appended to existing note)"
    fi

    # Clean up any newly created test beat (don't delete if it predated this run)
    if [ -n "$WRITTEN_PATH" ] && grep -q "Smoke Test Beat" "$WRITTEN_PATH" 2>/dev/null; then
      # Only delete if the whole file is our test content (newly created)
      if ! grep -q "smoke-test" "$WRITTEN_PATH" 2>/dev/null || [ "$AUTOFILE" = "false" ]; then
        rm -f "$WRITTEN_PATH"
      fi
    fi
  fi
fi

rm -f "$BEATS_FILE"

# ---------------------------------------------------------------------------
# Test 2: hook exits 0 on malformed JSON input
# ---------------------------------------------------------------------------
section "Test 2: pre-compact-extract.sh exits 0 on malformed JSON"

if [ ! -f "$HOOK" ]; then
  fail "Hook not found at $HOOK (run install.sh first)"
else
  echo "invalid json that is not valid" | bash "$HOOK"
  HOOK_EXIT=$?
  if [ "$HOOK_EXIT" -eq 0 ]; then
    pass "Hook exited 0 on malformed JSON (compaction not blocked)"
  else
    fail "Hook exited $HOOK_EXIT on malformed JSON — compaction would be blocked"
  fi
fi

# ---------------------------------------------------------------------------
# Test 3: hook exits 0 on empty input
# ---------------------------------------------------------------------------
section "Test 3: pre-compact-extract.sh exits 0 on empty input"

if [ -f "$HOOK" ]; then
  echo "" | bash "$HOOK"
  HOOK_EXIT=$?
  if [ "$HOOK_EXIT" -eq 0 ]; then
    pass "Hook exited 0 on empty input"
  else
    fail "Hook exited $HOOK_EXIT on empty input"
  fi
fi

# ---------------------------------------------------------------------------
# Test 4: MCP venv can import FastMCP
# ---------------------------------------------------------------------------
section "Test 4: MCP venv has FastMCP available"

if [ ! -d "$MCP_VENV" ]; then
  fail "MCP venv not found at $MCP_VENV (run install.sh first)"
elif [ ! -f "$MCP_VENV/bin/python3" ]; then
  fail "MCP venv has no python3 binary"
else
  if "$MCP_VENV/bin/python3" -c "from mcp.server.fastmcp import FastMCP; print('ok')" 2>/dev/null | grep -q "ok"; then
    pass "FastMCP import succeeded"
  else
    fail "FastMCP import failed — MCP server will not start"
    echo "    Try: $MCP_VENV/bin/pip install mcp"
  fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
TOTAL=$((PASS + FAIL))
echo ""
echo "============================================"
echo "Smoke test complete: $PASS/$TOTAL passed"
if [ "$FAIL" -gt 0 ]; then
  echo "$FAIL test(s) failed — see output above"
  exit 1
else
  echo "All tests passed."
  exit 0
fi
