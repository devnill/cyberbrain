# Review Summary — Refinement Cycle 3 (WI-021 through WI-026)

## Overview

Cycle 3 addressed all 5 significant findings from the cycle 2 capstone review and added mock vault testing infrastructure. WI-021 through WI-025 are complete with all acceptance criteria met. WI-026 has structural gaps: the `empty` vault variant was never created, no vault has `.obsidian/` marker directories, and teardown destroys the user's wm-recall.jsonl without backup. These are fixable without architectural changes.

## Significant Findings

- [spec-reviewer, gap-analyst] `tests/vaults/empty/` directory does not exist — the WI-026 acceptance criterion "5 vault variants exist" is unmet; `deploy empty` fails with an error while `list` advertises it. Blocks first-run onboarding testing. — relates to: WI-026
- [spec-reviewer, gap-analyst] No `.obsidian/` marker directory in any of the 4 existing vault variants — WI-026 requires each vault to have `.obsidian/` for vault detection; Git does not track empty directories so they were never committed. `cb_configure(discover=True)` cannot find deployed test vaults. — relates to: WI-026
- [code-reviewer] `teardown` destroys user's real `wm-recall.jsonl` with no restoration — deploy of mature/working-memory copies test data to `~/.claude/cyberbrain/wm-recall.jsonl`, overwriting the user's real file; teardown does not restore or remove it, causing permanent data loss. — relates to: WI-026

## Minor Findings

- [code-reviewer, gap-analyst] `_WM_RECALL_LOG` dead constant at `mcp/tools/review.py:15` — defined but never referenced. No work item tracks removal. — relates to: cross-cutting
- [code-reviewer] README deploy description omits `wm-recall.jsonl` side effect for mature/working-memory variants — relates to: WI-026
- [code-reviewer] Gate-blocked hint wording inconsistency: enrich.py/restructure.py use colon format, review.py uses imperative with period — relates to: WI-021
- [journal-keeper] Manual capture mode behavioral effectiveness unconfirmed — WI-023 strengthened wording but WI-020 test D2 was not re-executed to verify — relates to: WI-023

## Findings Requiring User Input

None — all findings can be resolved from existing context. The three significant findings are mechanical fixes (create directories, add .gitkeep files, add backup/restore logic).

## Proposed Refinement Plan

The three significant findings are scoped entirely to WI-026 (mock vault infrastructure) and require no architectural changes. They can be addressed as direct fixes without a full refinement cycle:

1. **Create `tests/vaults/empty/.obsidian/.gitkeep`** — satisfies both the empty variant and .obsidian/ marker for that variant (addresses S1 + partial S2)
2. **Add `.obsidian/.gitkeep` to para, zettelkasten, mature, working-memory** — completes S2
3. **Add wm-recall.jsonl backup/restore to test-vault.sh** — in `cmd_deploy()`, back up existing file before overwriting; in `cmd_teardown()`, restore it (addresses S3)
4. **Update README** — document wm-recall.jsonl side effect (addresses M2)

Estimated scope: 1 small work item, low complexity. No architecture or principle changes needed.
