"""Tests for tests/_dependency_map.py."""

import ast
import textwrap
from pathlib import Path

from tests._dependency_map import _REPO_ROOT, TestMapper


class TestExtractImports:
    """Unit tests for _extract_imports() covering ast.Import nodes."""

    def _make_mapper_with_source(self, source: str, tmp_path: Path) -> tuple["TestMapper", Path]:
        test_file = tmp_path / "test_fake.py"
        test_file.write_text(textwrap.dedent(source))
        m = TestMapper()
        return m, test_file

    def test_plain_import_captured(self, tmp_path):
        """Plain 'import X' statements are captured."""
        m, test_file = self._make_mapper_with_source(
            """
            import os
            import json
            """,
            tmp_path,
        )
        result = m._extract_imports(test_file)
        assert "os" in result
        assert "json" in result

    def test_import_as_captured(self, tmp_path):
        """'import X as Y' statements are captured by the original module name."""
        m, test_file = self._make_mapper_with_source(
            """
            import cyberbrain.extractors.extract_beats as eb
            import cyberbrain.mcp.tools.restructure.pipeline as rst_pipeline
            """,
            tmp_path,
        )
        result = m._extract_imports(test_file)
        assert "cyberbrain.extractors.extract_beats" in result
        assert "cyberbrain.mcp.tools.restructure.pipeline" in result

    def test_from_import_still_captured(self, tmp_path):
        """Existing ast.ImportFrom handling is not broken."""
        m, test_file = self._make_mapper_with_source(
            """
            from cyberbrain.extractors.config import load_global_config
            from pathlib import Path
            """,
            tmp_path,
        )
        result = m._extract_imports(test_file)
        assert "cyberbrain.extractors.config" in result
        assert "pathlib" in result

    def test_mixed_import_styles_captured(self, tmp_path):
        """Both ast.Import and ast.ImportFrom nodes are captured together."""
        m, test_file = self._make_mapper_with_source(
            """
            import json
            from pathlib import Path
            import cyberbrain.mcp.shared as _shared
            from cyberbrain.extractors.backends import BackendError
            """,
            tmp_path,
        )
        result = m._extract_imports(test_file)
        assert "json" in result
        assert "pathlib" in result
        assert "cyberbrain.mcp.shared" in result
        assert "cyberbrain.extractors.backends" in result


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

    def test_extract_beats_maps_to_test_extract_beats(self):
        """extract_beats.py changes should trigger test_extract_beats.py."""
        m = TestMapper()
        m.build()
        result = m.get_tests_for(Path("src/cyberbrain/extractors/extract_beats.py"))
        assert "tests/test_extract_beats.py" in result

    def test_restructure_pipeline_maps_to_test_restructure_tool(self):
        """restructure/pipeline.py changes should trigger test_restructure_tool.py."""
        m = TestMapper()
        m.build()
        result = m.get_tests_for(Path("src/cyberbrain/mcp/tools/restructure/pipeline.py"))
        assert "tests/test_restructure_tool.py" in result

    def test_shared_maps_to_test_mcp_server(self):
        """shared.py changes should trigger test_mcp_server.py."""
        m = TestMapper()
        m.build()
        result = m.get_tests_for(Path("src/cyberbrain/mcp/shared.py"))
        assert "tests/test_mcp_server.py" in result

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
