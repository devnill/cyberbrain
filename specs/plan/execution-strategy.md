# Execution Strategy — Refinement Cycle 4

## Mode
Batched parallel

## Parallelism
Max concurrent agents: 4

## Worktrees
Enabled: no

## Review Cadence
After every work item

## Work Item Groups

Group 1 (parallel — non-overlapping file scope):
- 027: Dead code removal and utility consolidation
- 029: Fix cb_setup predicate guidance

Group 2 (after Group 1 — depends on 027 for restructure.py):
- 028: Gate hint wording standardization

Group 3 (last — manual test, after all code changes):
- 030: Manual capture mode re-test

## Dependency Graph

```
027 (dead code + consolidation) ── independent
029 (predicate guidance) ── independent
028 (hint wording) ── depends on 027
030 (manual retest) ── depends on 027, 028, 029
```

## Agent Configuration
Model for workers: sonnet
Model for reviewers: sonnet
Permission mode: bypassPermissions

## Notes

027 and 029 have non-overlapping file scope and can run in parallel. 028 depends on 027 because both modify `restructure.py` and `test_restructure_tool.py`. 030 is a manual test procedure that runs last after all code changes are complete.

WI-030 produces a research document, not code changes. It requires a live Claude Desktop session and cannot be automated.
