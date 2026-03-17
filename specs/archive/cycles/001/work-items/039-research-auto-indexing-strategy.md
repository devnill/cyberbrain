# WI-039: Research — auto-indexing strategy

## Objective

Investigate options for keeping the cyberbrain search index current without requiring manual `cb_reindex` calls. The index becomes stale when users edit notes in Obsidian, add files, or move things. This research determines the right mechanism.

This is a research-only work item. No code changes.

## Acceptance Criteria

- [ ] Research report written to `specs/steering/research/auto-indexing-strategy.md`
- [ ] Report identifies current coverage gaps: which operations cause stale index entries, how stale entries manifest (wrong search results, missing results, etc.)
- [ ] Report evaluates at least two indexing trigger mechanisms: cron/scheduled job, Claude Code hook (SessionEnd or similar), file system watcher
- [ ] Report assesses each option against the constraint: no persistent daemon, lightweight
- [ ] Report makes a concrete recommendation with rationale
- [ ] If a hook-based approach is recommended, report specifies which hook event, what the hook script does, and how it handles errors without blocking the main session
- [ ] If cron is recommended, report provides a concrete cron expression and documents how to install/uninstall it
- [ ] Report identifies any failure modes or edge cases (vault not mounted, index lock contention, etc.)

## File Scope

- `create`: `specs/steering/research/auto-indexing-strategy.md`

## Dependencies

None.

## Implementation Notes

Read `src/cyberbrain/mcp/tools/reindex.py` to understand the current reindex implementation. Read `CLAUDE.md` and `specs/plan/architecture.md` for the existing hook architecture (PreCompact hook is already registered; SessionEnd hook may be available).

The user's stated preference: lightweight, no persistent daemon. If a cron job runs `cyberbrain-reindex` every N minutes, that may be acceptable. If Claude Code's `SessionEnd` hook fires on session completion, that's another option. File system events (FSEvents on macOS, inotify on Linux) would require a daemon — evaluate but likely reject.

Consider: how large is the index typically? How long does a full reindex take? Is incremental reindexing possible (only re-index files modified since last index run)?
