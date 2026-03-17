# WI-049: Implement --affected-only pytest plugin

## Objective

Create pytest plugin that auto-discovers tests affected by changed files using AST-based import analysis.

## Acceptance Criteria

- [ ] Create `tests/_dependency_map.py` with import graph builder class
- [ ] Create/modify `tests/conftest.py` with `--affected-only` flag handler
- [ ] Map source files to tests via import analysis (AST-based)
- [ ] Use `git diff --name-only HEAD~1` to find changed files
- [ ] Output minimal test list when flag is used
- [ ] Falls back to full test suite when git not available

## File Scope

- `create`: `tests/_dependency_map.py`
- `create/modify`: `tests/conftest.py`

## Implementation Notes

**tests/_dependency_map.py:**
```python
import ast
from pathlib import Path
from collections import defaultdict

class TestMapper:
    """Maps source modules to tests that import them."""

    def __init__(self):
        self.dependents: dict[str, set[str]] = defaultdict(set)

    def build(self):
        for test_file in Path("tests").glob("test_*.py"):
            for imported in self._extract_imports(test_file):
                self.dependents[imported].add(str(test_file))

    def get_tests_for(self, source_path: Path) -> set[str]:
        module = source_path.relative_to("src").with_suffix("").as_posix().replace("/", ".")
        return self.dependents.get(module, set())

    def _extract_imports(self, path: Path) -> set[str]:
        tree = ast.parse(path.read_text())
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        return imports
```

**tests/conftest.py:**
```python
def pytest_addoption(parser):
    parser.addoption(
        "--affected-only",
        action="store_true",
        default=False,
        help="Run only tests affected by changed files",
    )

def pytest_configure(config):
    if config.getoption("--affected-only"):
        from _dependency_map import TestMapper
        import subprocess

        # Get changed files from git
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1"],
            capture_output=True, text=True
        )
        changed = {Path(f) for f in result.stdout.splitlines() if f.endswith(".py")}

        # Map to tests
        mapper = TestMapper()
        mapper.build()

        affected = set()
        for src in changed:
            affected.update(mapper.get_tests_for(src))

        if affected:
            config.args = sorted(affected)
            config.option.verbose = 0
            config.option.tbstyle = "no"
```

The plugin should:
1. Build import graph once (cached)
2. Find changed files via git
3. Map to affected test files
4. Set as test args with quiet mode

Test mapping heuristic: `src/cyberbrain/x/y.py` → module `cyberbrain.x.y` → tests importing that module.
