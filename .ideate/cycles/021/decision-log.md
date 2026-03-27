# Decision Log — Cycle 21

## Key Decisions

### D1: PEP 562 __getattr__ for backward-compatible lazy paths
**When**: WI-093 rework
**What**: Module-level constants that were evaluated at import time via `Path.home()` were converted to lazy `__getattr__` handlers (PEP 562). Internal code calls state.py functions directly. Tests that patch module attributes continue to work because `setattr` shadows `__getattr__`.
**Why**: The initial worker approach (assigning function results at module scope) still evaluated `Path.home()` at import time, defeating the purpose. The `__getattr__` approach defers evaluation until first access while preserving test patching compatibility.
**Trade-off**: More complex module semantics. But eliminates the root cause of the config corruption bug found in the full audit.

### D2: update_vault_note requires file existence
**When**: WI-094 review
**What**: `update_vault_note()` raises `FileNotFoundError` if the target doesn't exist, unlike `write_vault_note()` which creates. This was a review finding — the original implementation silently created new files.
**Why**: Prevents phantom files from typo'd paths. `write_vault_note` is for creation, `update_vault_note` is for modification — the distinction must be enforced.

### D3: Consolidation log uses create-or-update pattern
**When**: WI-095
**What**: `_append_errata` in review.py reads existing content + appends new content + writes via `update_vault_note`. Falls back to `write_vault_note` when the log file doesn't exist yet.
**Why**: The old `open("a")` append mode was a direct vault write violating C-06. Read-then-write through the vault abstraction preserves C-06 while maintaining append semantics.

### D4: try/except ValueError replaces _is_within_vault boolean checks in execute.py
**When**: WI-096
**What**: Inline `_is_within_vault()` boolean checks replaced with try/except ValueError around `write_vault_note`/`move_vault_note` calls.
**Why**: The vault write functions perform the same validation internally and raise ValueError. Catching the exception produces the same skip-and-continue behavior with less code.

## Open Questions
- The duplicate `_is_within_vault` in shared.py should be consolidated into vault.py (noted by all three reviewers as a minor finding).
- Pre-existing deferred items remain: CI/CD, MCP dry_run, config backup.

## Cross-References
- All three reviewers flagged the same minor issue: `_is_within_vault` duplication between shared.py and vault.py. This is a cleanup item, not a correctness issue.
- The redundant pre-check in review.py:422 (code-quality M1 = spec-adherence M1) is a direct consequence of WI-095 migrating writes but not removing the now-redundant pre-check.
