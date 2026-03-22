# Decision Log — Cycle 011

## D1: UP038 added to ruff ignore list
`isinstance(x, (int, float))` → `isinstance(x, int | float)` requires --unsafe-fixes for some cases. Added to global ignore rather than applying unsafe fixes.

## D2: Exception narrowing strategy — document over narrow
For ambiguous cases (multiple possible exception types, safety-net catches), documenting with `# intentional:` comments was preferred over potentially incorrect narrowing. ~10 handlers narrowed to specific types where the exception source was unambiguous; 40+ documented.

## D3: sys.modules patterns documented, not rewritten
The light-touch approach adds documentation and consolidates helpers without rewriting the import architecture. Full elimination of sys.modules manipulation would require a different test architecture (dependency injection or lazy imports throughout).

## D4: Constraint C1 updated from 3.8+ to 3.11+
pyproject.toml already specified >=3.11. The constraint document was the only artifact still referencing 3.8+.

## Open Questions
None remaining from cycle 10 deferred list (except FastMCP migration, which is low priority).
