# Execution Strategy — Refinement Cycle 18

## Mode
Full parallel

## Parallelism
- Max concurrent agents: 2
- Worktree isolation: no
- Model: sonnet for implementation

## Review Cadence
Incremental review after each work item.

## Work Item Groups

### Group 1 — All items (parallel)

| WI | Title | Complexity |
|----|-------|-----------|
| 090 | Fix run_extraction config param and merge _write_beats_and_log | small |
| 091 | Mark architecture doc tensions T5/T6/T7 resolved | trivial |

Non-overlapping file scope:
- WI-090: extract_beats.py, test_extract_beats.py
- WI-091: specs/plan/architecture.md

## Dependency Graph

```
090
091    (independent)
```

## Agent Configuration

- Implementation agents: sonnet
- Review agents: sonnet
