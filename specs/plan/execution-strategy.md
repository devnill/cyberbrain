# Execution Strategy — Refinement Cycle 13

## Mode
Batched parallel

## Parallelism
- Max concurrent agents: 4
- Worktree isolation: yes
- Model: sonnet for implementation

## Review Cadence
Incremental review after each work item. Comprehensive review after all items complete.

## Work Item Groups

### Group 1 — All items (parallel)

| WI | Title | Complexity |
|----|-------|-----------|
| 072 | Migrate remaining hardcoded paths to state.py | trivial |
| 073 | Update CLAUDE.md for restructure decomposition | trivial |
| 074 | Fix test_dependency_map.py collection error | trivial |
| 075 | Eliminate extract_beats.py re-export hub | small |

All four run in parallel. Non-overlapping primary file scope:
- WI-072: config.py, recall.py
- WI-073: CLAUDE.md only
- WI-074: tests/test_dependency_map.py only
- WI-075: extract_beats.py, scripts/import.py, test files

## Dependency Graph

```
072
073    (all independent)
074
075
```

## Agent Configuration

- Implementation agents: sonnet
- Review agents: sonnet
- Worktree isolation: all items
