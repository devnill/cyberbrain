#!/usr/bin/env bash
# test-smoke.sh — Manual smoke test for cyberbrain.
#
# Verifies the happy path end-to-end without making any LLM API calls.
# Run this from the repo root:
#
#   bash scripts/test-smoke.sh
#
# Exit codes:
#   0 — all tests passed
#   1 — one or more tests failed

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0
FAIL=0
HOOK="$REPO_DIR/hooks/pre-compact-extract.sh"

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

EXTRACTOR_OUT=$(uv run --directory "$REPO_DIR" python -m cyberbrain.extractors.extract_beats \
  --beats-json "$BEATS_FILE" \
  --session-id "smoke-test-$$" \
  --trigger manual \
  --cwd /tmp 2>&1) || true

WRITTEN_PATH=$(echo "$EXTRACTOR_OUT" | grep '^\[extract_beats\] Wrote:' | head -1 | sed 's/\[extract_beats\] Wrote: //')

if [ -z "$WRITTEN_PATH" ]; then
  fail "No 'Wrote:' line in extractor output — beat was not written"
  echo "    Output: $EXTRACTOR_OUT" | head -5
elif [ ! -f "$WRITTEN_PATH" ]; then
  fail "Extractor reported writing $WRITTEN_PATH but file does not exist"
else
  pass "Beat written to $WRITTEN_PATH"

  if grep -q "Smoke Test Beat" "$WRITTEN_PATH"; then
    pass "Content: beat title found in written file"
  else
    fail "Content: beat title not found in written file"
  fi

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

  if [ -n "$WRITTEN_PATH" ] && grep -q "Smoke Test Beat" "$WRITTEN_PATH" 2>/dev/null; then
    if ! grep -q "smoke-test" "$WRITTEN_PATH" 2>/dev/null || [ "$AUTOFILE" = "false" ]; then
      rm -f "$WRITTEN_PATH"
    fi
  fi
fi

rm -f "$BEATS_FILE"

# ---------------------------------------------------------------------------
# Test 2: hook exits 0 on malformed JSON input
# ---------------------------------------------------------------------------
section "Test 2: pre-compact-extract.sh exits 0 on malformed JSON"

echo "invalid json that is not valid" | bash "$HOOK"
HOOK_EXIT=$?
if [ "$HOOK_EXIT" -eq 0 ]; then
  pass "Hook exited 0 on malformed JSON (compaction not blocked)"
else
  fail "Hook exited $HOOK_EXIT on malformed JSON — compaction would be blocked"
fi

# ---------------------------------------------------------------------------
# Test 3: hook exits 0 on empty input
# ---------------------------------------------------------------------------
section "Test 3: pre-compact-extract.sh exits 0 on empty input"

echo "" | bash "$HOOK"
HOOK_EXIT=$?
if [ "$HOOK_EXIT" -eq 0 ]; then
  pass "Hook exited 0 on empty input"
else
  fail "Hook exited $HOOK_EXIT on empty input"
fi

# ---------------------------------------------------------------------------
# Test 4: MCP server can be imported
# ---------------------------------------------------------------------------
section "Test 4: MCP server importable via uv run"

if uv run --directory "$REPO_DIR" python -c "from cyberbrain.mcp.server import mcp; print('ok')" 2>/dev/null | grep -q "ok"; then
  pass "MCP server import succeeded"
else
  fail "MCP server import failed — server will not start"
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
