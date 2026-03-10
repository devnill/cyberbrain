# Code Quality Review — Cycle 3 Capstone (WI-021 through WI-026)

## Verdict: Fail

All 1217 tests pass and cross-cutting patterns are consistent. One significant issue: teardown does not restore the user's wm-recall.jsonl that was overwritten during deploy.

## Critical Findings

None.

## Significant Findings

### S1: `teardown` destroys user's real `wm-recall.jsonl` with no restoration

- **File**: `scripts/test-vault.sh:301-322`
- **Issue**: When deploying `mature` or `working-memory` vault variants, the script copies the test `wm-recall.jsonl` to `~/.claude/cyberbrain/wm-recall.jsonl`, overwriting the user's real recall log. On `teardown`, the script restores `vault_path` but does not restore or remove the test `wm-recall.jsonl`. After teardown, `~/.claude/cyberbrain/wm-recall.jsonl` contains test data, and any real recall log the user had is permanently lost.
- **Impact**: Permanent data loss for the wm-recall.jsonl file that drives working memory prioritization in `cb_review`.
- **Suggested fix**: Back up the original before overwriting in `cmd_deploy()`. In `cmd_teardown()`, restore it or remove the test copy.

## Minor Findings

### M1: `_WM_RECALL_LOG` is dead code in `review.py`

- **File**: `mcp/tools/review.py:15`
- **Issue**: The constant is defined but never referenced anywhere in the file.
- **Suggested fix**: Remove line 15.

### M2: README `deploy` description omits `wm-recall.jsonl` side effect

- **File**: `tests/vaults/README.md`
- **Issue**: The `deploy` row does not mention that for `mature` and `working-memory` variants, `wm-recall.jsonl` is copied to `~/.claude/cyberbrain/`, overwriting any existing file.
- **Suggested fix**: Document this behavior in the README.

### M3: Hint wording inconsistency across gate-blocked output paths

- **File**: `mcp/tools/enrich.py:395`, `mcp/tools/restructure.py:1724`, `mcp/tools/review.py:350,359`
- **Issue**: `enrich.py` and `restructure.py` use colon format without period. `review.py` uses imperative with period.
- **Suggested fix**: Standardize on one form in a future work item.

## Unmet Acceptance Criteria

None.
