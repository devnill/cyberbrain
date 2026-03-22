# Decision Log — Cycle 010

## D1: Per-file F401 ignores instead of global

Initial implementation used a global F401 ignore. Code review (S1) flagged this as overly broad. Changed to per-file-ignores for extract_beats.py and shared.py (re-export hubs). All other files are subject to F401 enforcement.

## D2: PTH rules globally ignored

pathlib migration (os.path → pathlib) is too large for a formatting pass. All PTH rules globally ignored. Can be narrowed incrementally in future cycles.

## D3: WI-063 accepted as partial

Full test mock cleanup requires rewriting 10 test files individually. The shared.py and conftest.py changes deliver the core architectural improvement. The per-file cleanup is deferred to a future cycle as a dedicated effort.

## D4: WI-064 was already complete

enrich.py already used "\n---\n" for closing delimiter detection. The work item was created based on cycle 009 findings but the fix was applied before this cycle started.

## D5: Concurrent workers need worktree isolation

Workers running in parallel without worktree isolation caused file overwrites (WI-062 reverted pyproject.toml). Future cycles must use isolation: "worktree" for all parallel work items.

## Open Questions

### OQ-1: pyproject.toml requires-python vs actual minimum
requires-python = ">=3.8" but code uses 3.11+ features. Should be updated.

### OQ-2: Full test mock cleanup scope
Estimated 10 test files × ~50-200 lines of import/setup each. Dedicated work item needed.
