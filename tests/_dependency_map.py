import ast
from collections import defaultdict
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_TESTS_DIR = _REPO_ROOT / "tests"


class TestMapper:
    """Maps source modules to tests that import them."""

    def __init__(self):
        self.dependents: dict[str, set[str]] = defaultdict(set)

    def build(self):
        for test_file in _TESTS_DIR.glob("test_*.py"):
            for imported in self._extract_imports(test_file):
                self.dependents[imported].add(str(test_file.relative_to(_REPO_ROOT)))

    def get_tests_for(self, source_path: Path) -> set[str]:
        # Normalize absolute paths to repo-relative
        if source_path.is_absolute():
            try:
                source_path = source_path.relative_to(_REPO_ROOT)
            except ValueError:
                return set()

        # src/ paths: resolve via import graph
        try:
            module = (
                source_path.relative_to("src")
                .with_suffix("")
                .as_posix()
                .replace("/", ".")
            )
        except ValueError:
            pass
        else:
            return self.dependents.get(module, set())

        # scripts/ paths: filename-convention fallback
        candidate = _TESTS_DIR / f"test_{source_path.stem}.py"
        if candidate.exists():
            return {str(candidate.relative_to(_REPO_ROOT))}

        return set()

    def _extract_imports(self, path: Path) -> set[str]:
        tree = ast.parse(path.read_text())
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
        return imports
