# Refinement Cycle 13 — Minor Review Findings Cleanup

## What is Changing

Addressing the 7 minor findings from cycle 012 review plus dismissing the FastMCP pattern migration.

## Triggering Context

Cycle 012 review passed with 0 critical, 0 significant, 7 minor findings. User requested all minor items be handled. FastMCP migration explicitly dismissed as a non-issue.

## Scope Boundary

**In scope:**
- Migrate remaining hardcoded paths to state.py imports (config.py, recall.py)
- Update CLAUDE.md to reflect restructure.py decomposition
- Fix test_dependency_map.py collection error
- Remove extract_beats.py re-export hub (migrate callers to direct imports)

**Not in scope:**
- FastMCP pattern migration (dismissed)
- CI/CD pipeline (deferred — requires infrastructure decisions beyond code)
- ruff ignore list narrowing (documented, acceptable)
- New features

## Principles / Architecture

No changes.
