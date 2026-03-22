"""Tests for tests/_dependency_map.py."""

from pathlib import Path

from tests._dependency_map import _REPO_ROOT, TestMapper


class TestTestMapper:
    def test_scripts_path_returns_test_file(self):
        """scripts/repair_frontmatter.py maps to tests/test_repair_frontmatter.py."""
        m = TestMapper()
        m.build()
        result = m.get_tests_for(Path("scripts/repair_frontmatter.py"))
        assert result == {"tests/test_repair_frontmatter.py"}

    def test_absolute_scripts_path_returns_test_file(self):
        """Absolute path to a scripts file is normalised and returns the correct test."""
        m = TestMapper()
        m.build()
        result = m.get_tests_for(_REPO_ROOT / "scripts/repair_frontmatter.py")
        assert result == {"tests/test_repair_frontmatter.py"}

    def test_src_path_returns_test_file(self):
        """src/ module path maps to its test via import-graph analysis."""
        m = TestMapper()
        m.build()
        result = m.get_tests_for(Path("src/cyberbrain/mcp/tools/enrich.py"))
        assert "tests/test_setup_enrich_tools.py" in result

    def test_absolute_src_path_returns_test_file(self):
        """Absolute src/ path is normalised and returns the correct test."""
        m = TestMapper()
        m.build()
        result = m.get_tests_for(_REPO_ROOT / "src/cyberbrain/mcp/tools/enrich.py")
        assert "tests/test_setup_enrich_tools.py" in result

    def test_unknown_scripts_path_returns_empty(self):
        """A scripts/ file with no matching test returns empty set."""
        m = TestMapper()
        m.build()
        result = m.get_tests_for(Path("scripts/nonexistent_tool.py"))
        assert result == set()

    def test_mapper_is_cwd_independent(self, tmp_path, monkeypatch):
        """build() and get_tests_for() produce correct results regardless of cwd."""
        monkeypatch.chdir(tmp_path)
        assert Path.cwd() != _REPO_ROOT
        m = TestMapper()
        m.build()
        # scripts/ convention path — should work because _TESTS_DIR is absolute
        result = m.get_tests_for(Path("scripts/repair_frontmatter.py"))
        assert result == {"tests/test_repair_frontmatter.py"}
        # src/ import-graph path — should work because build() used _TESTS_DIR.glob
        enrich_result = m.get_tests_for(Path("src/cyberbrain/mcp/tools/enrich.py"))
        assert "tests/test_setup_enrich_tools.py" in enrich_result
