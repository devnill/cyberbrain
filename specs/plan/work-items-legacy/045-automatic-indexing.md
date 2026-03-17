# WI-045: Automatic indexing

## Objective

Implement automatic search index maintenance so the index stays current without manual `cb_reindex` calls. The approach is determined by WI-039 research.

## Acceptance Criteria

- [ ] Implementation follows the approach recommended in WI-039 research
- [ ] Index is updated automatically when vault files change (new files, edits, moves, deletes)
- [ ] No persistent daemon required
- [ ] Implementation handles errors gracefully: if auto-indexing fails, it logs the failure and does not block the user's session
- [ ] Manual `cb_reindex` still works as a fallback (no regression)
- [ ] If a cron-based approach: cron job is installable/uninstallable via `install.sh` (or equivalent setup script); cron expression is documented
- [ ] If a hook-based approach: hook is registered in the plugin manifest or hook config; hook script is idempotent
- [ ] Tests cover: the indexing trigger mechanism (mocked), graceful failure handling
- [ ] `uv run pytest tests/` passes with 0 failures

## File Scope

- Determined by WI-039 recommendation. Likely one or more of:
  - `modify`: `install.sh` (if cron installation)
  - `create`: `hooks/session-end-reindex.sh` (if hook-based)
  - `modify`: `.claude-plugin/plugin.json` (if hook registration needed)
  - `modify`: `src/cyberbrain/mcp/tools/reindex.py` (if incremental indexing implemented)
  - `create`: `tests/test_auto_indexing.py`

## Dependencies

- WI-039 (research findings on auto-indexing strategy)

## Implementation Notes

Read WI-039's research output at `specs/steering/research/auto-indexing-strategy.md` before writing any code. Implement exactly what is recommended there — do not invent a different mechanism.

If the research recommends incremental reindexing (only re-index files modified since last run), implement the modification-time check in `reindex.py`. The full rebuild path must remain available.

If the research recommends a hook-based approach, the hook script must: (1) exit 0 always (never block the session), (2) run reindex in the background or with a timeout, (3) not require user interaction.
