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
        try:
            module = source_path.relative_to("src").with_suffix("").as_posix().replace("/", ".")
        except ValueError:
            return set()
        return self.dependents.get(module, set())

    def _extract_imports(self, path: Path) -> set[str]:
        tree = ast.parse(path.read_text())
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        return imports
