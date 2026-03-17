# Refinement Cycle 8 — Token-Efficient Testing

## What is Changing

Optimize the ideate cycle for lower token spend by implementing targeted testing. Instead of running all 1285 tests with verbose output on every change, run only tests affected by changed code with minimal output (pass/fail only), then escalate to detailed output only on failure.

## Triggering Context

User feedback during execution of prior cycles: running 1200+ tests with verbose output consumes excessive tokens. Need to preserve quality while minimizing token spend during development.

## Scope Boundary

**In scope:**
- Add pytest markers for test categorization (core, extended, slow)
- Implement `--affected-only` pytest plugin with import-based test mapping
- Configure default pytest for minimal output (quiet mode)
- Create test wrapper script for two-pass execution

**Not in scope:**
- Changes to actual test logic or assertions
- Changes to production code
- Changes to CI/CD configuration

## New Work Items

048–051 (4 items). See `plan/work-items/` for details.

## Execution Strategy

**Mode:** Sequential
**Review cadence:** Single comprehensive review after all items complete
**Agent configuration:** Default models acceptable (testing infrastructure is straightforward)

**Ordering:**
1. WI-048 (markers) — Foundation for categorization
2. WI-049 (affected-only plugin) — Core functionality
3. WI-050 (quiet defaults) — Output configuration
4. WI-051 (wrapper script) — Convenience wrapper

Dependencies: WI-048 → WI-049 → WI-050/051 (parallel after 049)

## Expected Impact

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Tests run per change | 1285 | 50-100 | 92-96% |
| Lines of test output | 500+ | 1-3 | 99% |
| Context window usage | Heavy | Minimal | ~95% |
| Quality preservation | Full | Full | No loss |

## Principles

No changes. All existing guiding principles hold.

## Architecture

No changes to system architecture. Testing configuration only.
