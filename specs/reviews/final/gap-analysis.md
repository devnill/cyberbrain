# Gap Analysis — Cycle 3 Capstone (WI-021 through WI-026)

## Verdict: Fail

Cycle 3 work items 021-025 are complete with no gaps. WI-026 has two structural gaps: the `empty` vault variant was not created, and no vault has the `.obsidian/` marker required for vault discovery.

## Critical Findings

None.

## Significant Findings

### S1: `tests/vaults/empty/` directory does not exist

The empty vault variant is specified by WI-026 for testing `cb_setup` first-run experience and `cb_configure` vault discovery. The directory was never created. The `list` command references it, but `deploy` would fail.

**Impact**: The first-run onboarding test scenario is untestable.

**Fix**: Create `tests/vaults/empty/.obsidian/.gitkeep`.

### S2: `.obsidian/` marker directory missing from all vault variants

WI-026 requires each variant to have `.obsidian/` for vault detection. None have it. Git doesn't track empty directories.

**Impact**: `cb_configure(discover=True)` cannot find deployed test vaults.

**Fix**: Add `.obsidian/.gitkeep` to each variant.

## Minor Findings

### M1: Dead `_WM_RECALL_LOG` constant not tracked for cleanup

`mcp/tools/review.py:15` defines `_WM_RECALL_LOG` but never uses it. Flagged in WI-026 incremental review as out of scope. No future work item exists to track its removal.

**Fix**: Include in next cycle's cleanup pass.

## Unmet Acceptance Criteria

From WI-026:
- "5 vault variants exist, each with `.obsidian/` marker directory" — 4 exist, none have `.obsidian/`.
- "Contains only `.obsidian/` directory" (empty variant) — Does not exist.
