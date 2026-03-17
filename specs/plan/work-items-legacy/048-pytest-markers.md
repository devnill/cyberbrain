# WI-048: Add pytest markers for test categorization

## Objective

Add pytest markers to categorize tests by importance and speed: core (essential), extended (integration), slow (performance). This allows selective test execution during development.

## Acceptance Criteria

- [ ] Add markers section to pyproject.toml under [tool.pytest.ini_options]
- [ ] Define markers: `core` (essential functionality), `extended` (integration tests), `slow` (performance/heavy tests)
- [ ] Document marker usage in comments
- [ ] Tests can be selected with `pytest -m core`, `pytest -m "not slow"`, etc.

## File Scope

- `modify`: `pyproject.toml`

## Implementation Notes

The markers should follow pytest conventions:
```toml
[tool.pytest.ini_options]
markers = [
    "core: Essential tests - always run in targeted mode",
    "extended: Integration tests - run on full regression only",
    "slow: Performance tests - run manually only",
]
```

No tests need to be marked in this work item. Marking will happen incrementally as tests are touched.
