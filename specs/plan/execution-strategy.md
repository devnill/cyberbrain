# Execution Strategy — Refinement Cycle 6

## Mode
Sequential

## Parallelism
Max concurrent agents: 1

## Worktrees
Enabled: no

## Review Cadence
After work item completion

## Work Item Groups

Group 1 (sequential — single cohesive restructuring):
- 034: Restructure to src layout with cyberbrain namespace

## Dependency Graph

```
034 (restructure) ── standalone
```

## Agent Configuration
Model for workers: sonnet
Model for reviewers: sonnet
Permission mode: bypassPermissions

## Notes

WI-034 is a cohesive restructuring task that touches many files. Breaking it into smaller pieces would create incomplete intermediate states that cannot be tested. Sequential execution ensures each step is verified before moving to the next.

The work item includes mechanical import path changes that must be tested together. After completion, verify:
1. `python3 -m pytest tests/` passes
2. `uv run python -m cyberbrain.mcp.server` works
3. `uvx cyberbrain-mcp` works (manual verification may be needed)