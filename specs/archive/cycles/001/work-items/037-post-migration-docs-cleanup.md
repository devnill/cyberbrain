# WI-037: Post-migration docs and cleanup

## Objective

Update documentation and remove stale artifacts left over from the WI-034 src layout migration. CLAUDE.md references wrong paths and tool counts; architecture docs may reference deleted files; domain open questions Q-1 through Q-7 can be resolved now that migration is complete.

## Acceptance Criteria

- [ ] `CLAUDE.md` key files table references `src/cyberbrain/` paths, not bare `mcp/`, `extractors/`, `prompts/` paths
- [ ] `CLAUDE.md` tool count is accurate (reflects tools that exist after all cycles through 034)
- [ ] `specs/plan/architecture.md` has no references to deleted directories or old flat layout paths
- [ ] Any module spec files under `specs/plan/modules/` that reference old paths are updated
- [ ] Domain questions Q-1 through Q-7 (in `specs/domains/*/questions.md`) are resolved or explicitly deferred with rationale
- [ ] Any `dist/` wheel or build artifact references are removed from documentation
- [ ] `build.sh` is either updated or marked deprecated in documentation if it no longer applies
- [ ] Dead `EXTRACTORS_DIR` references in documentation are removed
- [ ] No stale comments in test files referring to the old flat layout

## File Scope

- `modify`: `CLAUDE.md`
- `modify`: `specs/plan/architecture.md`
- `modify`: `specs/plan/modules/*.md` (only files with stale path references)
- `modify`: `specs/domains/*/questions.md` (resolve Q-1 through Q-7 where possible)

## Dependencies

None. (Can run in parallel with 035 and 036.)

## Implementation Notes

Read each file before modifying. Do not rewrite sections that are still accurate — only fix the stale references. For domain questions, a question is "resolved" if the migration completed it or made it moot; "deferred" means it still requires future work but is not a blocker. Update the questions file to reflect the status with a brief rationale.

The `EXTRACTORS_DIR` constant was removed in WI-034 (or is a dead reference). Any documentation saying "EXTRACTORS_DIR is the path to..." should be deleted.
