# Decision Log — Cycle 006

## Decisions

None new.

---

## Open Questions

### OQ7 [SIGNIFICANT]: `_dependency_map.py` uses cwd-relative paths throughout

`build()` and `get_tests_for()` both resolve paths against `os.getcwd()`. In non-root invocation contexts (common in CI), the mapper silently returns empty sets. WI-055 added `candidate.exists()` with the same latent issue. Fix in WI-056: anchor to `Path(__file__).parent.parent`.

---

## Work Item Completion

| WI | Title | Status | Verdict | Findings (C/S/M) |
|---|---|---|---|---|
| 055 | Register scripts/ tree in _dependency_map.py | Complete | Pass | 0/0/2 |

---

## Most Important Finding

**OQ7**: `_dependency_map.py` path operations are cwd-relative. Non-root invocation silently yields empty test sets, defeating the mapper's purpose. Fix: anchor to `Path(__file__).parent.parent` in WI-056.
