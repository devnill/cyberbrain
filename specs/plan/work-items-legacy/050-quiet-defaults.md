# WI-050: Configure default pytest for minimal output

## Objective

Update pyproject.toml to default to quiet test output (pass/fail only, no tracebacks).

## Acceptance Criteria

- [ ] Set `addopts = "--tb=no -q --no-header"` in pyproject.toml
- [ ] Verify output is minimal (e.g., "45 passed, 2 failed")
- [ ] Full output still available with explicit `--tb=short` or `--tb=long` flags
- [ ] Quiet mode is the default; explicit flags override

## File Scope

- `modify`: `pyproject.toml`

## Implementation Notes

Update the existing pytest configuration:

```toml
[tool.pytest.ini_options]
pythonpath = ["src", "tests"]
addopts = "--tb=no -q --no-header"
markers = [
    "core: Essential tests - always run in targeted mode",
    "extended: Integration tests - run on full regression only",
    "slow: Performance tests - run manually only",
]
```

**Output comparison:**

Before:
```
============================= test session starts ==============================
platform darwin -- Python 3.12.9, pytest-9.0.2, pluggy-1.6.0 -- /Users/dan/...
cachedir: .pytest_cache
rootdir: /Users/dan/code/cyberbrain
configfile: pyproject.toml
plugins: anyio-4.12.1
collected 1285 items
tests/test_analyze_vault.py::TestParseFrontmatter::test_returns_empty PASSED
tests/test_analyze_vault.py::TestParseFrontmatter::test_parses_basic PASSED
... (hundreds of lines)
======================== 1285 passed in 75.15s ================================
```

After:
```
1285 passed in 75.15s
```

Users can still get full output with:
```bash
pytest --tb=short -v  # Normal output
pytest --tb=long -v   # Full tracebacks
```
