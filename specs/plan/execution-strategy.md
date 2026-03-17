# Execution Strategy — Refinement Cycle 7

## Mode
Batched parallel

## Parallelism
Max concurrent agents: 4

## Worktrees
Enabled: no

## Review Cadence
After each work item completion

## Work Item Groups

### Group 1 (parallel — no dependencies between items)
- 035: Fix install.sh for src layout
- 036: Fix runtime bare imports
- 037: Post-migration docs and cleanup
- 038: Research — filing accuracy and clustering
- 039: Research — auto-indexing strategy
- 040: Design — intake interface
- 041: Design — retrieval interface

**PAUSE after Group 1**: Executor presents WI-040 and WI-041 design proposals to user for approval before Group 2 begins. Group 2 must not start until user explicitly approves both designs.

### Group 2 (parallel — depends on Group 1 outputs)
- 042: Implement new intake interface (depends on 040, requires user approval of design)
- 043: Filing confidence and uncertainty handling (depends on 038)
- 044: Improved clustering and filing accuracy (depends on 038)
- 045: Automatic indexing (depends on 039)
- 046: Implement new retrieval interface (depends on 041, requires user approval of design)

### Group 3 (sequential — user review required before execution)
- 047: Update vault CLAUDE.md schema and regenerate current vault (depends on 042, 043)

**PAUSE before Group 3**: Executor presents proposed vault CLAUDE.md changes to user for approval before any file is written to the live vault.

## Dependency Graph

```
035 ──────────────────────────────────────────────────────────────► (done)
036 ──────────────────────────────────────────────────────────────► (done)
037 ──────────────────────────────────────────────────────────────► (done)
038 ──────────────────────────────────────────────────────────────► 043, 044
039 ──────────────────────────────────────────────────────────────► 045
040 ──────────── [user approves design] ──────────────────────────► 042
041 ──────────── [user approves design] ──────────────────────────► 046
                                                042, 043 ──────────► 047
```

## Agent Configuration
Model for workers: sonnet
Model for reviewers: sonnet
Model for research and design agents: opus
Permission mode: bypassPermissions

## Notes

WI-040 and WI-041 produce design proposals (documents, no code). After Group 1 completes, the executor reads both proposals and presents them to the user before starting any Group 2 item. The executor must not start WI-042 or WI-046 until the user approves the respective design.

WI-047 modifies the user's live vault. The executor reads the current vault CLAUDE.md, prepares a diff of proposed changes, presents it to the user, and waits for explicit approval before writing.

Research items (038, 039) and design items (040, 041) should use opus-grade reasoning. Implementation items (042–046) use sonnet.
