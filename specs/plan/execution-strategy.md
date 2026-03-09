# Execution Strategy

## Mode
Batched parallel

## Parallelism
Max concurrent agents: 3

## Worktrees
Enabled: yes
Reason: Parallel work items may touch overlapping modules. Worktrees provide isolation and clean merge points.

## Review Cadence
After every batch (group)

## Work Item Groups

Group 1 (parallel — foundational, no dependencies):
- 001: Evaluation tooling framework
- 002: Manual validation test plan for automatic invocation
- 003: Knowledge graph + ML research investigation

Group 2 (parallel, depends on group 1):
- 004: Restructure pipeline quality improvements
- 005: RAG synthesis and context injection

Group 3 (sequential, depends on group 2):
- 006: Automatic invocation hardening
- 007: Per-tool model selection

## Dependency Graph

```
001 (eval tooling) ──┬──→ 004 (restructure quality)
                     │
002 (invocation test)┼──→ 006 (invocation hardening)
                     │
003 (graph research) ┴──→ 005 (RAG synthesis)
                              │
                              └──→ 007 (per-tool model selection)
```

## Agent Configuration
Model for workers: opus
Model for reviewers: opus
Permission mode: acceptEdits

## Notes

This is a baseline plan. The work items are large and intentionally broad — they capture workstreams, not atomic tasks. Each will be decomposed into atomic work items via `/ideate:refine` before execution begins.

Group 1 is research and tooling that informs Group 2 decisions. Group 3 depends on Group 2 being stable enough to build on.

The human-in-the-loop concern applies especially to item 004 (restructure). The evaluation tooling (001) must be usable before restructure quality work can iterate effectively.
