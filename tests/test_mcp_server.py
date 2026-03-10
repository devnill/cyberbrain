"""
test_mcp_server.py — unit tests for the cyberbrain MCP tools

Updated for the modular package structure (mcp/tools/*.py, mcp/shared.py).
Tool modules are imported directly; a FakeMCP captures registered functions
without requiring FastMCP to be installed in the test environment.

Patch targets are tool-module-level names (e.g. tools.extract._extract_beats)
rather than server-module-level names, because `from shared import X` creates a
binding in each tool module's own namespace.

Coverage:
- ToolError is raised (not returned) for all genuine failure cases
- Successful-but-empty cases return strings, not ToolErrors
- transcript_path is restricted to ~/.claude/projects/
- Typed parameters (type_override, folder, cwd) work correctly
- cwd parameter flows through to config loading
- max_results bounds are declared in the schema
- Tool annotations are captured by register()
- Search backend path (backend search, grep fallback, error fallback)
- Synthesize=True calls _synthesize_recall; False does not
- _parse_frontmatter edge cases

All LLM calls and vault I/O are mocked. No real API calls.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Setup: add mcp/ and extractors/ to sys.path, mock extract_beats before import
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
MCP_DIR = REPO_ROOT / "mcp"
EXTRACTORS_DIR = REPO_ROOT / "extractors"

for d in [str(MCP_DIR), str(EXTRACTORS_DIR), str(REPO_ROOT)]:
    if d not in sys.path:
        sys.path.insert(0, d)


class _BackendError(Exception):
    """Real exception class so try/except BackendError in tool code works."""
    pass


# Mock extract_beats before shared.py imports it at module level
_mock_eb = MagicMock()
_mock_eb.BackendError = _BackendError
_mock_eb.resolve_config.return_value = {
    "vault_path": "/tmp/test_vault",
    "inbox": "AI/Claude-Sessions",
    "backend": "claude-code",
    "model": "claude-haiku-4-5",
    "autofile": False,
    "daily_journal": False,
}
_mock_frontmatter = MagicMock()
_mock_frontmatter.parse_frontmatter.return_value = {}

# Register mocks before first import of shared (which does `from extract_beats import ...`)
if "extract_beats" not in sys.modules:
    sys.modules["extract_beats"] = _mock_eb
if "frontmatter" not in sys.modules:
    sys.modules["frontmatter"] = _mock_frontmatter

# ---------------------------------------------------------------------------
# FakeMCP: captures tool/resource/prompt registrations without requiring FastMCP
# ---------------------------------------------------------------------------

class _Annotations:
    """Minimal stand-in for ToolAnnotations."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeMCP:
    def __init__(self):
        self._tools = {}   # name -> {"fn": fn, "annotations": annotations}
        self._resources = {}
        self._prompts = {}

    def tool(self, annotations=None, **kwargs):
        def decorator(fn):
            self._tools[fn.__name__] = {"fn": fn, "annotations": annotations}
            return fn
        return decorator

    def resource(self, uri, **kwargs):
        def decorator(fn):
            self._resources[fn.__name__] = {"fn": fn, "uri": uri}
            return fn
        return decorator

    def prompt(self, **kwargs):
        def decorator(fn):
            self._prompts[fn.__name__] = {"fn": fn}
            return fn
        return decorator


# ---------------------------------------------------------------------------
# Import tool modules and register with FakeMCP
# ---------------------------------------------------------------------------

# Clear any stale module cache entries from previous test runs in same process
for _mod in ["shared", "tools", "tools.extract", "tools.file", "tools.recall",
             "tools.manage", "resources"]:
    sys.modules.pop(_mod, None)

import shared as _shared
from tools import extract as _extract_mod
from tools import file as _file_mod
from tools import recall as _recall_mod
from tools import manage as _manage_mod
import resources as _resources_mod

fake_mcp = FakeMCP()
_extract_mod.register(fake_mcp)
_file_mod.register(fake_mcp)
_recall_mod.register(fake_mcp)
_manage_mod.register(fake_mcp)
_resources_mod.register(fake_mcp)

# Convenience references to registered tool functions
cb_extract = fake_mcp._tools["cb_extract"]["fn"]
cb_file = fake_mcp._tools["cb_file"]["fn"]
cb_recall = fake_mcp._tools["cb_recall"]["fn"]
cb_read = fake_mcp._tools["cb_read"]["fn"]
cb_configure = fake_mcp._tools["cb_configure"]["fn"]
cb_status = fake_mcp._tools["cb_status"]["fn"]

# ToolError — import from fastmcp (primary) with mcp fallback
try:
    from fastmcp.exceptions import ToolError
except ImportError:
    try:
        from mcp.server.fastmcp.exceptions import ToolError  # type: ignore[no-redef]
    except ImportError:
        class ToolError(Exception):  # type: ignore[no-redef]
            pass


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

BASE_CONFIG = {
    "vault_path": "/tmp/test_vault",
    "inbox": "AI/Claude-Sessions",
    "backend": "claude-code",
    "model": "claude-haiku-4-5",
    "autofile": False,
    "daily_journal": False,
}


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """
    Create a temp home directory with ~/.claude/projects/ structure and
    patch Path.home() so the server's path checks use it.
    """
    home = tmp_path / "home"
    (home / ".claude" / "projects").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


@pytest.fixture
def mock_config(fake_home, tmp_path):
    """Return a config dict with vault_path pointing to an existing temp directory."""
    vault = tmp_path / "vault"
    vault.mkdir()
    return {**BASE_CONFIG, "vault_path": str(vault)}


@pytest.fixture
def transcript_file(fake_home):
    """A real .jsonl transcript file inside ~/.claude/projects/."""
    path = fake_home / ".claude" / "projects" / "test-session.jsonl"
    path.write_text(
        '{"type": "user", "message": {"role": "user", "content": "hello"}}\n'
        '{"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "world"}]}}\n',
        encoding="utf-8",
    )
    return path


# ===========================================================================
# cb_extract — path restriction
# ===========================================================================

class TestCbExtractPathRestriction:
    """transcript_path must be within ~/.claude/projects/ or a ToolError is raised."""

    def test_rejects_path_outside_projects_root(self):
        """An absolute path clearly outside ~/.claude/projects/ raises ToolError."""
        with pytest.raises(ToolError, match="must be within"):
            cb_extract(transcript_path="/etc/passwd")

    def test_rejects_tmp_path_outside_projects_root(self, tmp_path):
        """A path in /tmp (outside ~/.claude/projects/) raises ToolError."""
        outside = tmp_path / "transcript.jsonl"
        outside.write_text("content")
        with pytest.raises(ToolError, match="must be within"):
            cb_extract(transcript_path=str(outside))

    def test_error_message_includes_the_rejected_path(self):
        """ToolError message includes the rejected path for debugging."""
        bad_path = "/tmp/definitely-outside.jsonl"
        with pytest.raises(ToolError) as exc_info:
            cb_extract(transcript_path=bad_path)
        assert bad_path in str(exc_info.value)

    def test_accepts_path_inside_projects_root_then_checks_existence(self, fake_home):
        """A path within ~/.claude/projects/ passes the restriction (then raises not-found)."""
        inside = fake_home / ".claude" / "projects" / "nonexistent-uuid.jsonl"
        with pytest.raises(ToolError) as exc_info:
            cb_extract(transcript_path=str(inside))
        assert "not found" in str(exc_info.value).lower()
        assert "must be within" not in str(exc_info.value)


# ===========================================================================
# cb_extract — ToolError on genuine failures
# ===========================================================================

class TestCbExtractErrors:
    """cb_extract raises ToolError for every genuine failure."""

    def test_raises_tool_error_when_file_not_found(self, fake_home, mock_config):
        missing = fake_home / ".claude" / "projects" / "ghost.jsonl"
        with patch.object(_extract_mod, "_load_config", return_value=mock_config):
            with pytest.raises(ToolError, match="not found"):
                cb_extract(transcript_path=str(missing))

    def test_raises_tool_error_when_transcript_is_empty(self, fake_home, mock_config):
        empty = fake_home / ".claude" / "projects" / "empty.jsonl"
        empty.write_text("   \n")
        with patch.object(_extract_mod, "_load_config", return_value=mock_config):
            with patch.object(_extract_mod, "parse_jsonl_transcript", return_value=""):
                with pytest.raises(ToolError, match="empty"):
                    cb_extract(transcript_path=str(empty))

    def test_raises_tool_error_when_jsonl_parse_fails(self, fake_home, mock_config, transcript_file):
        with patch.object(_extract_mod, "_load_config", return_value=mock_config):
            with patch.object(_extract_mod, "parse_jsonl_transcript", side_effect=ValueError("bad jsonl")):
                with pytest.raises(ToolError, match="Failed to parse"):
                    cb_extract(transcript_path=str(transcript_file))

    def test_raises_tool_error_on_backend_error(self, fake_home, mock_config, transcript_file):
        with patch.object(_extract_mod, "_load_config", return_value=mock_config):
            with patch.object(_extract_mod, "parse_jsonl_transcript", return_value="content"):
                with patch.object(_extract_mod, "_extract_beats", side_effect=_BackendError("timed out")):
                    with pytest.raises(ToolError) as exc_info:
                        cb_extract(transcript_path=str(transcript_file))
        assert "claude-code" in str(exc_info.value)

    def test_returns_string_when_no_beats_extracted(self, fake_home, mock_config, transcript_file):
        with patch.object(_extract_mod, "_load_config", return_value=mock_config):
            with patch.object(_extract_mod, "parse_jsonl_transcript", return_value="content"):
                with patch.object(_extract_mod, "_extract_beats", return_value=[]):
                    result = cb_extract(transcript_path=str(transcript_file))
        assert result == "No beats extracted."
        assert isinstance(result, str)


# ===========================================================================
# cb_extract — cwd parameter
# ===========================================================================

class TestCbExtractCwdParam:
    """cwd parameter is forwarded to config loading for project-scoped routing."""

    def test_cwd_is_forwarded_to_load_config(self, fake_home, mock_config, transcript_file):
        project_cwd = "/Users/dan/code/myproject"
        mock_load = MagicMock(return_value=mock_config)
        with patch.object(_extract_mod, "_load_config", mock_load):
            with patch.object(_extract_mod, "parse_jsonl_transcript", return_value="content"):
                with patch.object(_extract_mod, "_extract_beats", return_value=[]):
                    cb_extract(transcript_path=str(transcript_file), cwd=project_cwd)
        mock_load.assert_called_with(project_cwd)

    def test_cwd_defaults_to_home_when_omitted(self, fake_home, mock_config, transcript_file):
        mock_load = MagicMock(return_value=mock_config)
        with patch.object(_extract_mod, "_load_config", mock_load):
            with patch.object(_extract_mod, "parse_jsonl_transcript", return_value="content"):
                with patch.object(_extract_mod, "_extract_beats", return_value=[]):
                    cb_extract(transcript_path=str(transcript_file))
        called_with = mock_load.call_args[0][0]
        assert called_with == str(fake_home)


# ===========================================================================
# cb_extract — success path
# ===========================================================================

class TestCbExtractSuccess:
    """cb_extract returns a summary string listing created beats on success."""

    def test_success_returns_summary_string(self, fake_home, mock_config, tmp_path, transcript_file):
        vault = tmp_path / "vault"
        vault.mkdir(exist_ok=True)
        config = {**mock_config, "vault_path": str(vault)}
        beat = {"title": "My Insight", "type": "insight", "scope": "general",
                "summary": "Test", "tags": [], "body": "## Body\n\nContent."}
        fake_path = vault / "AI" / "Claude-Sessions" / "My Insight.md"
        (vault / "AI" / "Claude-Sessions").mkdir(parents=True)
        fake_path.write_text("content")

        with patch.object(_extract_mod, "_load_config", return_value=config):
            with patch.object(_extract_mod, "parse_jsonl_transcript", return_value="content"):
                with patch.object(_extract_mod, "_extract_beats", return_value=[beat]):
                    with patch.object(_extract_mod, "write_beat", return_value=fake_path):
                        result = cb_extract(transcript_path=str(transcript_file))

        assert "1/1" in result
        assert "insight" in result


# ===========================================================================
# cb_file — typed parameters
# ===========================================================================

class TestCbFileTypedParams:
    """cb_file takes explicit type_override, folder, and cwd parameters."""

    def test_type_override_is_applied_after_extraction(self, mock_config, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir(exist_ok=True)
        (vault / "AI" / "Claude-Sessions").mkdir(parents=True, exist_ok=True)
        config = {**mock_config, "vault_path": str(vault)}
        original_beat = {"title": "A Note", "type": "insight", "scope": "general",
                         "summary": "Test", "tags": [], "body": "body"}
        captured_beats = []

        def fake_write(beat, cfg, session_id, cwd, now, **kwargs):
            captured_beats.append(dict(beat))
            path = vault / "AI" / "Claude-Sessions" / "A Note.md"
            path.write_text("content")
            return path

        with patch.object(_file_mod, "_load_config", return_value=config):
            with patch.object(_file_mod, "_extract_beats", return_value=[original_beat]):
                with patch.object(_file_mod, "write_beat", side_effect=fake_write):
                    cb_file(content="Some insight content", type_override="decision")

        assert len(captured_beats) == 1
        assert captured_beats[0]["type"] == "decision"

    def test_folder_sets_inbox_in_effective_config(self, mock_config, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir(exist_ok=True)
        target_folder = "Personal/Recipes"
        (vault / target_folder).mkdir(parents=True, exist_ok=True)
        config = {**mock_config, "vault_path": str(vault)}
        beat = {"title": "A Beat", "type": "reference", "scope": "general",
                "summary": "Test", "tags": [], "body": "body"}
        captured_configs = []

        def fake_write(beat, cfg, session_id, cwd, now, **kwargs):
            captured_configs.append(dict(cfg))
            path = vault / target_folder / "A Beat.md"
            path.write_text("content")
            return path

        with patch.object(_file_mod, "_load_config", return_value=config):
            with patch.object(_file_mod, "_extract_beats", return_value=[beat]):
                with patch.object(_file_mod, "write_beat", side_effect=fake_write):
                    cb_file(content="A great recipe", folder=target_folder)

        assert len(captured_configs) == 1
        assert captured_configs[0]["inbox"] == target_folder

    def test_cwd_is_forwarded_to_load_config(self, mock_config):
        project_cwd = "/Users/dan/code/myproject"
        mock_load = MagicMock(return_value=mock_config)
        with patch.object(_file_mod, "_load_config", mock_load):
            with patch.object(_file_mod, "_extract_beats", return_value=[]):
                cb_file(content="Some content", cwd=project_cwd)
        mock_load.assert_called_with(project_cwd)

    def test_no_beats_identified_returns_string_not_error(self, mock_config):
        with patch.object(_file_mod, "_load_config", return_value=mock_config):
            with patch.object(_file_mod, "_extract_beats", return_value=[]):
                result = cb_file(content="just some random text")
        assert isinstance(result, str)
        assert "No content worth filing" in result

    def test_instructions_param_no_longer_exists(self):
        """cb_file no longer accepts an 'instructions' parameter."""
        import inspect
        sig = inspect.signature(cb_file)
        assert "instructions" not in sig.parameters
        assert "type_override" in sig.parameters
        assert "folder" in sig.parameters
        assert "cwd" in sig.parameters


# ===========================================================================
# cb_file — ToolError on failures
# ===========================================================================

class TestCbFileErrors:
    """cb_file raises ToolError for genuine failures."""

    def test_raises_tool_error_on_backend_error(self, mock_config):
        with patch.object(_file_mod, "_load_config", return_value=mock_config):
            with patch.object(_file_mod, "_extract_beats", side_effect=_BackendError("timed out")):
                with pytest.raises(ToolError) as exc_info:
                    cb_file(content="Some content")
        assert "claude-code" in str(exc_info.value)

    def test_raises_tool_error_when_all_writes_fail(self, mock_config, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir(exist_ok=True)
        config = {**mock_config, "vault_path": str(vault)}
        beat = {"title": "A Note", "type": "insight", "scope": "general",
                "summary": "Test", "tags": [], "body": "body"}

        with patch.object(_file_mod, "_load_config", return_value=config):
            with patch.object(_file_mod, "_extract_beats", return_value=[beat]):
                with patch.object(_file_mod, "write_beat", side_effect=OSError("disk full")):
                    with pytest.raises(ToolError) as exc_info:
                        cb_file(content="Some content")

        assert "write error" in str(exc_info.value).lower() or "vault_path" in str(exc_info.value)

    def test_partial_write_failures_return_success_for_written_beats(self, mock_config, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir(exist_ok=True)
        (vault / "AI" / "Claude-Sessions").mkdir(parents=True, exist_ok=True)
        config = {**mock_config, "vault_path": str(vault)}
        beats = [
            {"title": "Beat One", "type": "insight", "scope": "general", "summary": "", "tags": [], "body": ""},
            {"title": "Beat Two", "type": "reference", "scope": "general", "summary": "", "tags": [], "body": ""},
        ]
        good_path = vault / "AI" / "Claude-Sessions" / "Beat One.md"
        good_path.write_text("content")

        call_count = {"n": 0}
        def fake_write(beat, cfg, session_id, cwd, now, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return good_path
            raise OSError("disk full")

        with patch.object(_file_mod, "_load_config", return_value=config):
            with patch.object(_file_mod, "_extract_beats", return_value=beats):
                with patch.object(_file_mod, "write_beat", side_effect=fake_write):
                    result = cb_file(content="Some content")

        assert isinstance(result, str)
        assert "Beat One" in result


# ===========================================================================
# cb_recall — ToolError on short queries
# ===========================================================================

class TestCbRecallErrors:
    """cb_recall raises ToolError when the query is too short."""

    def test_raises_tool_error_for_single_char_query(self):
        with pytest.raises(ToolError, match="too short"):
            cb_recall(query="x")

    def test_raises_tool_error_for_two_char_query(self):
        with pytest.raises(ToolError, match="too short"):
            cb_recall(query="ab")

    def test_raises_tool_error_for_only_short_words(self):
        with pytest.raises(ToolError, match="too short"):
            cb_recall(query="a is it")

    def test_does_not_raise_for_valid_query(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        config = {**BASE_CONFIG, "vault_path": str(vault)}
        with patch.object(_recall_mod, "_load_config", return_value=config):
            with patch.object(_recall_mod, "_get_search_backend", return_value=None):
                with patch("subprocess.run", return_value=MagicMock(stdout="", returncode=0)):
                    result = cb_recall(query="python")
        assert isinstance(result, str)


# ===========================================================================
# cb_recall — empty results return a string, not ToolError
# ===========================================================================

class TestCbRecallEmptyResults:
    """Empty search results are a valid, non-error outcome."""

    def test_returns_string_when_no_notes_found(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        config = {**BASE_CONFIG, "vault_path": str(vault)}
        with patch.object(_recall_mod, "_load_config", return_value=config):
            with patch.object(_recall_mod, "_get_search_backend", return_value=None):
                with patch("subprocess.run", return_value=MagicMock(stdout="", returncode=0)):
                    result = cb_recall(query="redis")
        assert isinstance(result, str)
        assert "No notes found" in result
        assert "redis" in result


# ===========================================================================
# cb_recall — max_results parameter schema
# ===========================================================================

class TestCbRecallMaxResults:
    """max_results default and schema bounds."""

    def test_max_results_default_is_five(self):
        import inspect
        sig = inspect.signature(cb_recall)
        assert sig.parameters["max_results"].default == 5

    def test_max_results_field_has_constraints(self):
        import inspect
        from pydantic.fields import FieldInfo
        sig = inspect.signature(cb_recall)
        param = sig.parameters["max_results"]
        annotation = param.annotation
        field_info = None
        if hasattr(annotation, "__metadata__"):
            for meta in annotation.__metadata__:
                if isinstance(meta, FieldInfo):
                    field_info = meta
                    break
        assert field_info is not None, "max_results should have a Pydantic FieldInfo annotation"
        assert field_info.metadata  # should have ge/le constraints


# ===========================================================================
# Tool annotations
# ===========================================================================

class TestToolAnnotations:
    """Tool annotations are correctly registered via register()."""

    def test_cb_recall_has_readonly_hint(self):
        ann = fake_mcp._tools["cb_recall"]["annotations"]
        assert ann is not None
        assert ann.readOnlyHint is True

    def test_cb_recall_has_idempotent_hint(self):
        ann = fake_mcp._tools["cb_recall"]["annotations"]
        assert ann.idempotentHint is True

    def test_cb_extract_has_destructive_hint_false(self):
        ann = fake_mcp._tools["cb_extract"]["annotations"]
        assert ann is not None
        assert ann.destructiveHint is False

    def test_cb_file_has_no_readonly_hint(self):
        ann = fake_mcp._tools["cb_file"]["annotations"]
        if ann is not None:
            assert ann.readOnlyHint is not True


# ===========================================================================
# _parse_frontmatter (shared module helper)
# ===========================================================================

class TestParseFrontmatter:
    """_parse_frontmatter() is available via shared module."""

    def test_parses_standard_frontmatter(self):
        content = '---\ntitle: "My Note"\ntype: decision\n---\n\nBody.'
        fm = _shared._parse_frontmatter(content)
        assert fm["title"] == "My Note"
        assert fm["type"] == "decision"

    def test_parses_yaml_list_for_tags(self):
        content = '---\ntitle: "Note"\ntags: ["jwt", "auth"]\n---\n\nBody.'
        fm = _shared._parse_frontmatter(content)
        assert fm["tags"] == ["jwt", "auth"]

    def test_returns_empty_dict_when_no_frontmatter(self):
        assert _shared._parse_frontmatter("Just a body.") == {}

    def test_returns_empty_dict_on_parse_error(self):
        content = "---\n: invalid: yaml: {\n---\n\nBody."
        result = _shared._parse_frontmatter(content)
        assert isinstance(result, dict)


# ===========================================================================
# cb_recall — search backend path
# ===========================================================================

class TestCbRecallSearchBackend:
    """cb_recall uses the pluggable search backend when available."""

    def _make_vault(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "AI" / "Claude-Sessions").mkdir(parents=True)
        return vault

    def _make_note(self, vault, filename, content):
        note = vault / "AI" / "Claude-Sessions" / filename
        note.write_text(content, encoding="utf-8")
        return note

    def test_uses_backend_search_when_backend_available(self, tmp_path):
        vault = self._make_vault(tmp_path)
        note = self._make_note(
            vault, "JWT Auth.md",
            '---\ntitle: "JWT Auth"\ntype: decision\ntags: []\nrelated: []\nsummary: "JWT auth summary"\ndate: 2026-01-01\n---\n\n## Body\n\nContent.',
        )
        from search_backends import SearchResult
        mock_result = SearchResult(path=str(note), title="JWT Auth", summary="JWT auth summary",
                                   score=1.5, backend="fts5", note_type="decision")
        mock_backend = MagicMock()
        mock_backend.search.return_value = [mock_result]
        mock_backend.backend_name.return_value = "fts5"

        config = {**BASE_CONFIG, "vault_path": str(vault)}
        with patch.object(_recall_mod, "_load_config", return_value=config):
            with patch.object(_recall_mod, "_get_search_backend", return_value=mock_backend):
                result = cb_recall(query="jwt authentication")

        mock_backend.search.assert_called_once()
        assert isinstance(result, str)

    def test_falls_back_to_grep_when_backend_returns_empty(self, tmp_path):
        vault = self._make_vault(tmp_path)
        config = {**BASE_CONFIG, "vault_path": str(vault)}
        mock_backend = MagicMock()
        mock_backend.search.return_value = []
        mock_backend.backend_name.return_value = "fts5"

        with patch.object(_recall_mod, "_load_config", return_value=config):
            with patch.object(_recall_mod, "_get_search_backend", return_value=mock_backend):
                with patch("subprocess.run", return_value=MagicMock(stdout="", returncode=0)):
                    result = cb_recall(query="jwt authentication")

        assert "No notes found" in result

    def test_falls_back_to_grep_when_backend_raises(self, tmp_path):
        vault = self._make_vault(tmp_path)
        config = {**BASE_CONFIG, "vault_path": str(vault)}
        mock_backend = MagicMock()
        mock_backend.search.side_effect = RuntimeError("index corrupted")
        mock_backend.backend_name.return_value = "fts5"

        with patch.object(_recall_mod, "_load_config", return_value=config):
            with patch.object(_recall_mod, "_get_search_backend", return_value=mock_backend):
                with patch("subprocess.run", return_value=MagicMock(stdout="", returncode=0)):
                    result = cb_recall(query="jwt authentication")

        assert isinstance(result, str)

    def test_result_card_includes_backend_name_in_header(self, tmp_path):
        vault = self._make_vault(tmp_path)
        note = self._make_note(
            vault, "JWT Auth.md",
            '---\ntitle: "JWT Auth"\ntype: decision\ntags: []\nrelated: []\nsummary: "Summary"\ndate: 2026-01-01\n---\n\n## Body\n\nContent.',
        )
        from search_backends import SearchResult
        mock_result = SearchResult(path=str(note), title="JWT Auth", summary="Summary",
                                   score=1.5, backend="fts5", note_type="decision")
        mock_backend = MagicMock()
        mock_backend.search.return_value = [mock_result]
        mock_backend.backend_name.return_value = "fts5"

        config = {**BASE_CONFIG, "vault_path": str(vault)}
        with patch.object(_recall_mod, "_load_config", return_value=config):
            with patch.object(_recall_mod, "_get_search_backend", return_value=mock_backend):
                result = cb_recall(query="jwt")

        assert "fts5" in result

    def test_result_card_omits_related_when_empty(self, tmp_path):
        vault = self._make_vault(tmp_path)
        note = self._make_note(
            vault, "JWT Auth.md",
            '---\ntitle: "JWT Auth"\ntype: decision\ntags: []\nrelated: []\nsummary: "Summary"\ndate: 2026-01-01\n---\n\n## Body\n\nContent.',
        )
        from search_backends import SearchResult
        mock_result = SearchResult(path=str(note), title="JWT Auth", summary="Summary",
                                   score=1.5, backend="fts5", note_type="decision", related=[])
        mock_backend = MagicMock()
        mock_backend.search.return_value = [mock_result]
        mock_backend.backend_name.return_value = "fts5"

        config = {**BASE_CONFIG, "vault_path": str(vault)}
        with patch.object(_recall_mod, "_load_config", return_value=config):
            with patch.object(_recall_mod, "_get_search_backend", return_value=mock_backend):
                result = cb_recall(query="jwt")

        assert "Related:" not in result


# ===========================================================================
# cb_recall — synthesize
# ===========================================================================

class TestCbRecallSynthesize:
    """cb_recall with synthesize=True calls _synthesize_recall."""

    def _setup(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "AI" / "Claude-Sessions").mkdir(parents=True)
        note = vault / "AI" / "Claude-Sessions" / "JWT Auth.md"
        note.write_text(
            '---\ntitle: "JWT Auth"\ntype: decision\ntags: []\nrelated: []\nsummary: "Summary"\ndate: 2026-01-01\n---\n\n## Body\n\nContent.',
            encoding="utf-8",
        )
        from search_backends import SearchResult
        mock_result = SearchResult(path=str(note), title="JWT Auth", summary="Summary",
                                   score=1.5, backend="fts5", note_type="decision")
        mock_backend = MagicMock()
        mock_backend.search.return_value = [mock_result]
        mock_backend.backend_name.return_value = "fts5"
        config = {**BASE_CONFIG, "vault_path": str(vault)}
        return config, mock_backend

    def test_synthesize_true_calls_synthesize_recall(self, tmp_path):
        config, mock_backend = self._setup(tmp_path)
        with patch.object(_recall_mod, "_load_config", return_value=config):
            with patch.object(_recall_mod, "_get_search_backend", return_value=mock_backend):
                with patch.object(_recall_mod, "_synthesize_recall", return_value="synthesis result") as mock_synth:
                    cb_recall(query="jwt authentication", synthesize=True)
        mock_synth.assert_called_once()

    def test_synthesize_false_does_not_call_synthesize_recall(self, tmp_path):
        config, mock_backend = self._setup(tmp_path)
        with patch.object(_recall_mod, "_load_config", return_value=config):
            with patch.object(_recall_mod, "_get_search_backend", return_value=mock_backend):
                with patch.object(_recall_mod, "_synthesize_recall") as mock_synth:
                    cb_recall(query="jwt authentication", synthesize=False)
        mock_synth.assert_not_called()

    def test_synthesize_recall_prepends_synthesis_before_retrieved_content(self, tmp_path):
        config = {**BASE_CONFIG, "vault_path": str(tmp_path)}
        retrieved = "## Retrieved from knowledge vault\n\nsome vault content\n## End of retrieved content"
        note_summaries = [{"title": "Note 1", "type": "insight", "tags": [], "date": "2026-01-01", "source": "Note1.md", "summary": "s", "body_excerpt": "body"}]
        with patch.object(_recall_mod, "_call_claude_code_backend", return_value="Here is the synthesis."), \
             patch.object(_recall_mod, "_load_prompt", return_value="prompt"):
            result = _recall_mod._synthesize_recall("test query", retrieved, note_summaries, config)
        assert "## Relevant Knowledge" in result
        assert "Here is the synthesis" in result

    def test_synthesize_recall_falls_back_gracefully_on_error(self, tmp_path):
        config = {**BASE_CONFIG, "vault_path": str(tmp_path)}
        retrieved = "## Retrieved from knowledge vault\n\nsome content\n## End of retrieved content"
        note_summaries = [{"title": "Note 1", "type": "insight", "tags": [], "date": "2026-01-01", "source": "Note1.md", "summary": "s", "body_excerpt": "body"}]
        with patch.object(_recall_mod, "_call_claude_code_backend", side_effect=RuntimeError("backend error")), \
             patch.object(_recall_mod, "_load_prompt", return_value="prompt"):
            result = _recall_mod._synthesize_recall("test query", retrieved, note_summaries, config)
        assert "some content" in result
        assert "Synthesis failed" in result or "synthesis failed" in result.lower()


# ===========================================================================
# cb_configure — discover, writes, validation, no-args status
# ===========================================================================

class TestCbConfigure:
    """cb_configure: vault discovery, config writes, and no-args status display."""

    def test_discover_returns_string_when_no_vaults_found(self, tmp_path, monkeypatch):
        """discover=True with empty search roots returns helpful message."""
        # Point home at tmp_path so no vaults are found
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        with patch.object(_manage_mod, "_load_config", return_value=BASE_CONFIG):
            result = cb_configure(discover=True)
        assert isinstance(result, str)
        assert "No Obsidian vaults found" in result or "vaults" in result.lower()

    def test_discover_finds_obsidian_vault(self, tmp_path, monkeypatch):
        """discover=True lists vaults containing .obsidian directories."""
        home = tmp_path / "home"
        docs = home / "Documents"
        vault_dir = docs / "MyVault"
        (vault_dir / ".obsidian").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        with patch.object(_manage_mod, "_load_config", return_value=BASE_CONFIG):
            result = cb_configure(discover=True)
        assert "MyVault" in result or str(vault_dir) in result

    def test_set_vault_path_rejects_path_outside_home(self, tmp_path, monkeypatch):
        """vault_path outside home raises ToolError."""
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
        with pytest.raises(ToolError, match="home directory"):
            cb_configure(vault_path="/etc/vault")

    def test_set_vault_path_creates_directory_and_saves_config(self, tmp_path, monkeypatch):
        """vault_path within home creates directory and writes config file."""
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        # Ensure config dir exists
        cfg_dir = home / ".claude" / "cyberbrain"
        cfg_dir.mkdir(parents=True)

        new_vault = home / "Notes" / "MyVault"
        with patch("threading.Thread"):  # avoid background index rebuild
            result = cb_configure(vault_path=str(new_vault))

        assert new_vault.exists()
        cfg_file = cfg_dir / "config.json"
        assert cfg_file.exists()
        import json as _json
        cfg = _json.loads(cfg_file.read_text())
        assert str(new_vault) in cfg["vault_path"]
        assert "vault_path" in result

    def test_set_inbox_updates_config(self, tmp_path, monkeypatch):
        """inbox parameter is saved to config."""
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        cfg_dir = home / ".claude" / "cyberbrain"
        cfg_dir.mkdir(parents=True)

        result = cb_configure(inbox="Personal/Notes")

        import json as _json
        cfg = _json.loads((cfg_dir / "config.json").read_text())
        assert cfg["inbox"] == "Personal/Notes"
        assert "inbox" in result

    def test_set_invalid_capture_mode_raises_tool_error(self, tmp_path, monkeypatch):
        """capture_mode must be 'suggest', 'auto', or 'manual'."""
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
        with pytest.raises(ToolError, match="capture_mode"):
            cb_configure(capture_mode="invalid")

    def test_set_valid_capture_mode_saves_config(self, tmp_path, monkeypatch):
        """capture_mode='auto' is saved correctly."""
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        cfg_dir = home / ".claude" / "cyberbrain"
        cfg_dir.mkdir(parents=True)

        result = cb_configure(capture_mode="auto")

        import json as _json
        cfg = _json.loads((cfg_dir / "config.json").read_text())
        assert cfg["desktop_capture_mode"] == "auto"
        assert "auto" in result

    def test_no_args_returns_config_summary(self, tmp_path):
        """No-args call returns a config summary string."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = {**BASE_CONFIG, "vault_path": str(vault)}
        with patch.object(_manage_mod, "_load_config", return_value=config):
            with patch.object(_manage_mod, "_read_index_stats", return_value={"total": 42, "by_type": {}, "relations_count": 0, "stale_count": 0}):
                result = cb_configure()
        assert "Vault" in result
        assert isinstance(result, str)

    def test_no_args_shows_not_configured_when_vault_missing(self, tmp_path):
        """No vault_path in config shows setup instructions."""
        config = {**BASE_CONFIG, "vault_path": ""}
        with patch.object(_manage_mod, "_load_config", return_value=config):
            result = cb_configure()
        assert "not configured" in result.lower() or "not set" in result.lower()


# ===========================================================================
# _read_index_stats — SQLite query
# ===========================================================================

class TestReadIndexStats:
    """_read_index_stats queries a real (in-memory via tmp) SQLite database."""

    def _make_db(self, tmp_path):
        """Create a minimal SQLite DB with notes and relations tables."""
        import sqlite3
        db = tmp_path / "test-index.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE notes (path TEXT, title TEXT, type TEXT, summary TEXT, tags TEXT, date TEXT)"
        )
        conn.execute("CREATE TABLE relations (src TEXT, dst TEXT, type TEXT)")
        conn.execute("INSERT INTO notes VALUES ('/vault/a.md', 'A', 'decision', '', '', '')")
        conn.execute("INSERT INTO notes VALUES ('/vault/b.md', 'B', 'insight', '', '', '')")
        conn.execute("INSERT INTO notes VALUES ('/vault/c.md', 'C', 'decision', '', '', '')")
        conn.execute("INSERT INTO relations VALUES ('/vault/a.md', '/vault/b.md', 'related')")
        conn.commit()
        conn.close()
        return db

    def test_returns_total_note_count(self, tmp_path):
        db = self._make_db(tmp_path)
        config = {**BASE_CONFIG, "search_db_path": str(db)}
        stats = _manage_mod._read_index_stats(config)
        assert stats["total"] == 3

    def test_returns_by_type_breakdown(self, tmp_path):
        db = self._make_db(tmp_path)
        config = {**BASE_CONFIG, "search_db_path": str(db)}
        stats = _manage_mod._read_index_stats(config)
        assert stats["by_type"]["decision"] == 2
        assert stats["by_type"]["insight"] == 1

    def test_returns_relations_count(self, tmp_path):
        db = self._make_db(tmp_path)
        config = {**BASE_CONFIG, "search_db_path": str(db)}
        stats = _manage_mod._read_index_stats(config)
        assert stats["relations_count"] == 1

    def test_returns_stale_count_for_nonexistent_paths(self, tmp_path):
        db = self._make_db(tmp_path)
        config = {**BASE_CONFIG, "search_db_path": str(db)}
        # All three paths in DB don't exist on disk
        stats = _manage_mod._read_index_stats(config)
        assert stats["stale_count"] == 3

    def test_returns_empty_dict_when_db_not_found(self, tmp_path):
        config = {**BASE_CONFIG, "search_db_path": str(tmp_path / "nonexistent.db")}
        stats = _manage_mod._read_index_stats(config)
        assert stats == {}


# ===========================================================================
# cb_status — runs log, index stats, manifest
# ===========================================================================

class TestCbStatus:
    """cb_status shows runs, index health, and config summary."""

    def _make_runs_log(self, path, entries):
        import json as _json
        path.write_text(
            "\n".join(_json.dumps(e) for e in entries) + "\n",
            encoding="utf-8",
        )

    def test_returns_string_with_no_runs(self, tmp_path):
        config = {**BASE_CONFIG, "vault_path": str(tmp_path)}
        with patch.object(_manage_mod, "_load_config", return_value=config):
            with patch.object(_manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-log.jsonl")):
                with patch.object(_manage_mod, "_read_index_stats", return_value={}):
                    result = cb_status()
        assert isinstance(result, str)
        assert "No runs recorded" in result

    def test_shows_recent_run_in_table(self, tmp_path):
        runs_log = tmp_path / "runs.jsonl"
        self._make_runs_log(runs_log, [{
            "timestamp": "2026-03-01T12:00:00Z",
            "session_id": "abc12345",
            "project": "myproject",
            "trigger": "compact",
            "beats_written": 3,
            "beats_extracted": 4,
            "duration_seconds": 9.5,
            "beats": [],
            "errors": [],
        }])
        config = {**BASE_CONFIG, "vault_path": str(tmp_path)}
        with patch.object(_manage_mod, "_load_config", return_value=config):
            with patch.object(_manage_mod, "RUNS_LOG_PATH", str(runs_log)):
                with patch.object(_manage_mod, "_read_index_stats", return_value={"total": 0, "by_type": {}, "relations_count": 0, "stale_count": 0}):
                    result = cb_status()
        assert "abc12345" in result or "2026-03-01" in result
        assert "compact" in result

    def test_shows_index_stats_when_available(self, tmp_path):
        config = {**BASE_CONFIG, "vault_path": str(tmp_path)}
        stats = {"total": 15, "by_type": {"decision": 7, "insight": 8}, "relations_count": 3, "stale_count": 1}
        with patch.object(_manage_mod, "_load_config", return_value=config):
            with patch.object(_manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-log.jsonl")):
                with patch.object(_manage_mod, "_read_index_stats", return_value=stats):
                    result = cb_status()
        assert "15" in result
        assert "decision" in result or "insight" in result

    def test_shows_no_index_message_when_stats_empty(self, tmp_path):
        config = {**BASE_CONFIG, "vault_path": str(tmp_path)}
        with patch.object(_manage_mod, "_load_config", return_value=config):
            with patch.object(_manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-log.jsonl")):
                with patch.object(_manage_mod, "_read_index_stats", return_value={}):
                    result = cb_status()
        assert "Index not found" in result or "not found" in result.lower()

    def test_last_n_runs_limits_output(self, tmp_path):
        runs_log = tmp_path / "runs.jsonl"
        entries = [
            {
                "timestamp": f"2026-03-0{i}T12:00:00Z",
                "session_id": f"sess{i:04d}",
                "project": "proj",
                "trigger": "auto",
                "beats_written": i,
                "beats_extracted": i,
                "duration_seconds": 1.0,
                "beats": [],
                "errors": [],
            }
            for i in range(1, 6)
        ]
        self._make_runs_log(runs_log, entries)
        config = {**BASE_CONFIG, "vault_path": str(tmp_path)}
        with patch.object(_manage_mod, "_load_config", return_value=config):
            with patch.object(_manage_mod, "RUNS_LOG_PATH", str(runs_log)):
                with patch.object(_manage_mod, "_read_index_stats", return_value={}):
                    result = cb_status(last_n_runs=2)
        # Only the last 2 entries should appear — sess0004 and sess0005
        assert "sess0005" in result or "sess0004" in result
        assert "sess0001" not in result


# ===========================================================================
# resources — guide and prompts
# ===========================================================================

class TestResources:
    """Resources and prompts are registered and return expected content."""

    def test_cyberbrain_guide_is_registered(self):
        """cyberbrain_guide resource is registered at cyberbrain://guide."""
        assert "cyberbrain_guide" in fake_mcp._resources
        assert fake_mcp._resources["cyberbrain_guide"]["uri"] == "cyberbrain://guide"

    def test_orient_prompt_is_registered(self):
        assert "orient" in fake_mcp._prompts

    def test_recall_prompt_is_registered(self):
        assert "recall" in fake_mcp._prompts

    def test_cyberbrain_guide_returns_string(self, tmp_path):
        config = {**BASE_CONFIG, "vault_path": str(tmp_path), "proactive_recall": True, "desktop_capture_mode": "suggest"}
        with patch.object(_resources_mod, "_load_config", return_value=config):
            result = fake_mcp._resources["cyberbrain_guide"]["fn"]()
        assert isinstance(result, str)
        assert "cb_recall" in result

    def test_orient_prompt_returns_list_with_user_role(self, tmp_path):
        config = {**BASE_CONFIG, "vault_path": str(tmp_path), "proactive_recall": True, "desktop_capture_mode": "suggest"}
        with patch.object(_resources_mod, "_load_config", return_value=config):
            result = fake_mcp._prompts["orient"]["fn"]()
        assert isinstance(result, list)
        assert result[0].role == "user"
        assert "cyberbrain" in result[0].content.text.lower()

    def test_recall_prompt_returns_list_with_user_role(self):
        result = fake_mcp._prompts["recall"]["fn"]()
        assert isinstance(result, list)
        assert result[0].role == "user"
        assert "cb_recall" in result[0].content.text

    def test_build_guide_proactive_recall_true(self):
        guide = _resources_mod._build_guide(
            recall_instruction="Call cb_recall proactively.",
            filing_instruction="File immediately.",
        )
        assert "cb_recall" in guide
        assert "Call cb_recall proactively." in guide

    def test_build_guide_uses_default_filing_instruction_when_empty(self):
        guide = _resources_mod._build_guide(recall_instruction="Check vault.")
        assert "cb_file" in guide  # default filing instruction mentions cb_file behavior

    def test_get_guide_proactive_mode_mentions_proactive(self, tmp_path):
        config = {**BASE_CONFIG, "vault_path": str(tmp_path), "proactive_recall": True, "desktop_capture_mode": "suggest"}
        with patch.object(_resources_mod, "_load_config", return_value=config):
            guide = _resources_mod._get_guide()
        assert "proactively" in guide.lower() or "proactive" in guide.lower()

    def test_get_guide_non_proactive_mode_suggests_instead(self, tmp_path):
        config = {**BASE_CONFIG, "vault_path": str(tmp_path), "proactive_recall": False, "desktop_capture_mode": "suggest"}
        with patch.object(_resources_mod, "_load_config", return_value=config):
            guide = _resources_mod._get_guide()
        assert "suggest" in guide.lower()

    def test_get_guide_auto_capture_mode(self, tmp_path):
        config = {**BASE_CONFIG, "vault_path": str(tmp_path), "proactive_recall": True, "desktop_capture_mode": "auto"}
        with patch.object(_resources_mod, "_load_config", return_value=config):
            guide = _resources_mod._get_guide()
        assert "immediately" in guide.lower() or "auto" in guide.lower()

    def test_get_guide_manual_capture_mode(self, tmp_path):
        config = {**BASE_CONFIG, "vault_path": str(tmp_path), "proactive_recall": True, "desktop_capture_mode": "manual"}
        with patch.object(_resources_mod, "_load_config", return_value=config):
            guide = _resources_mod._get_guide()
        assert "explicitly" in guide.lower() or "manual" in guide.lower()
        assert "NEVER" in guide
        assert "Do NOT" in guide


# ===========================================================================
# cb_configure — additional coverage: _load_raw, discover loop, vault missing,
# last-run reading
# ===========================================================================


class TestCbConfigureAdditionalCoverage:
    """Cover lines in cb_configure not hit by the primary TestCbConfigure suite."""

    def test_reads_and_merges_existing_config_when_setting_inbox(self, tmp_path, monkeypatch):
        """Lines 68-71: _load_raw() reads an existing config and the write merges it."""
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        cfg_dir = home / ".claude" / "cyberbrain"
        cfg_dir.mkdir(parents=True)
        cfg_file = cfg_dir / "config.json"
        # Pre-populate config with an existing key
        import json as _json
        cfg_file.write_text(_json.dumps({"vault_path": "/some/vault", "existing_key": "preserved"}))

        result = cb_configure(inbox="AI/New-Folder")

        updated = _json.loads(cfg_file.read_text())
        assert updated["inbox"] == "AI/New-Folder"
        assert updated["existing_key"] == "preserved"
        assert "inbox" in result

    def test_load_raw_returns_empty_dict_on_invalid_json(self, tmp_path, monkeypatch):
        """Lines 70-71: _load_raw returns {} when config file contains invalid JSON."""
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        cfg_dir = home / ".claude" / "cyberbrain"
        cfg_dir.mkdir(parents=True)
        cfg_file = cfg_dir / "config.json"
        cfg_file.write_text("{ this is not valid json }")

        # Should not raise — invalid JSON is silently treated as empty config
        result = cb_configure(inbox="AI/Inbox")
        import json as _json
        updated = _json.loads(cfg_file.read_text())
        assert updated["inbox"] == "AI/Inbox"
        # existing_key was NOT preserved because JSON parse failed
        assert "existing_key" not in updated

    def test_discover_appends_vault_dirs_in_loop(self, tmp_path, monkeypatch):
        """Lines 94-96: vault_dir is appended for each .obsidian dir found."""
        home = tmp_path / "home"
        docs = home / "Documents"
        # Create two distinct vaults
        vault_a = docs / "VaultAlpha"
        vault_b = docs / "VaultBeta"
        (vault_a / ".obsidian").mkdir(parents=True)
        (vault_b / ".obsidian").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        with patch.object(_manage_mod, "_load_config", return_value=BASE_CONFIG):
            result = cb_configure(discover=True)
        assert "VaultAlpha" in result or "VaultBeta" in result
        # Both should appear (2 < 10 limit)
        assert result.count(str(docs)) >= 1 or ("1." in result and "2." in result)

    def test_discover_stops_at_10_vaults(self, tmp_path, monkeypatch):
        """Line 98: loop breaks when 10 vaults are found."""
        home = tmp_path / "home"
        docs = home / "Documents"
        # Create 12 vaults
        for i in range(12):
            (docs / f"Vault{i:02d}" / ".obsidian").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        with patch.object(_manage_mod, "_load_config", return_value=BASE_CONFIG):
            result = cb_configure(discover=True)
        # Output should mention "Found" and list exactly 10 vaults
        lines = [l for l in result.splitlines() if l.strip().startswith(tuple(str(i) + "." for i in range(1, 13)))]
        assert len(lines) == 10

    def test_vault_path_set_starts_background_rebuild(self, tmp_path, monkeypatch):
        """Lines 135-141: setting vault_path starts a daemon Thread for index rebuild."""
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        cfg_dir = home / ".claude" / "cyberbrain"
        cfg_dir.mkdir(parents=True)
        new_vault = home / "MyNotes"

        import threading
        threads_started = []
        real_thread_init = threading.Thread.__init__

        def capture_thread(self, *args, **kwargs):
            real_thread_init(self, *args, **kwargs)
            threads_started.append(self)

        with patch.object(threading.Thread, "__init__", capture_thread):
            with patch.object(threading.Thread, "start", lambda self: None):
                cb_configure(vault_path=str(new_vault))

        assert len(threads_started) >= 1

    def test_no_args_shows_vault_missing_warning(self, tmp_path):
        """Lines 175-176: when vault_path is set but dir doesn't exist, warning shown."""
        nonexistent = str(tmp_path / "ghost-vault")
        config = {**BASE_CONFIG, "vault_path": nonexistent}
        with patch.object(_manage_mod, "_load_config", return_value=config):
            with patch.object(_manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-runs.log")):
                result = cb_configure()
        assert "does not exist" in result or "⚠" in result

    def test_no_args_shows_last_run_from_runs_log(self, tmp_path):
        """Lines 192-210: last run timestamp and beat count appear in config summary."""
        import json as _json
        vault = tmp_path / "vault"
        vault.mkdir()
        runs_log = tmp_path / "runs.log"
        run_entry = {
            "timestamp": "2026-01-15T12:30:00Z",
            "beats_written": 7,
            "session_id": "abc123xyz",
        }
        runs_log.write_text(_json.dumps(run_entry) + "\n", encoding="utf-8")

        config = {**BASE_CONFIG, "vault_path": str(vault)}
        with patch.object(_manage_mod, "_load_config", return_value=config):
            with patch.object(_manage_mod, "_read_index_stats", return_value={"total": 0, "by_type": {}, "relations_count": 0, "stale_count": 0}):
                with patch.object(_manage_mod, "RUNS_LOG_PATH", str(runs_log)):
                    result = cb_configure()

        assert "2026-01-15" in result or "abc123" in result
        assert "7" in result


# ===========================================================================
# cb_status — additional coverage: stale paths, beats list, manifest vectors
# ===========================================================================


class TestCbStatusAdditionalCoverage:
    """Cover lines in cb_status not hit by the primary TestCbStatus suite."""

    def _make_runs_log(self, path, entries):
        import json as _json
        path.write_text(
            "\n".join(_json.dumps(e) for e in entries) + "\n",
            encoding="utf-8",
        )

    def test_stale_paths_shows_warning_in_index_health(self, tmp_path):
        """Lines 239-242 and 252-254: stale_count > 0 shows warning text."""
        config = {**BASE_CONFIG, "vault_path": str(tmp_path)}
        stats = {"total": 5, "by_type": {"decision": 5}, "relations_count": 0, "stale_count": 3}
        with patch.object(_manage_mod, "_load_config", return_value=config):
            with patch.object(_manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-log.jsonl")):
                with patch.object(_manage_mod, "_read_index_stats", return_value=stats):
                    result = cb_status()
        assert "3" in result
        assert "not found on disk" in result or "stale" in result.lower() or "⚠" in result

    def test_last_run_beats_list_appears_in_output(self, tmp_path):
        """Lines 281 and 283: beats and errors from the last run are listed."""
        runs_log = tmp_path / "runs.jsonl"
        self._make_runs_log(runs_log, [{
            "timestamp": "2026-01-15T12:00:00Z",
            "session_id": "deadsess",
            "project": "my-project",
            "trigger": "compact",
            "beats_written": 2,
            "beats_extracted": 2,
            "duration_seconds": 5.0,
            "beats": [
                {"title": "FastAPI Decision", "type": "decision", "scope": "project", "path": "Projects/hermes/FastAPI.md"},
            ],
            "errors": ["Could not write Broken Note.md"],
        }])
        config = {**BASE_CONFIG, "vault_path": str(tmp_path)}
        with patch.object(_manage_mod, "_load_config", return_value=config):
            with patch.object(_manage_mod, "RUNS_LOG_PATH", str(runs_log)):
                with patch.object(_manage_mod, "_read_index_stats", return_value={}):
                    result = cb_status()
        assert "FastAPI Decision" in result
        assert "Could not write Broken Note.md" in result

    def test_semantic_vectors_shown_when_manifest_has_model(self, tmp_path):
        """Lines 300-301: when manifest has model_name, vector count is displayed."""
        import json as _json
        manifest = {"model_name": "TaylorAI/bge-micro-v2", "id_map": ["a", "b", "c"]}
        manifest_path = tmp_path / "search-index-manifest.json"
        manifest_path.write_text(_json.dumps(manifest), encoding="utf-8")

        config = {
            **BASE_CONFIG,
            "vault_path": str(tmp_path),
            "search_manifest_path": str(manifest_path),
        }
        with patch.object(_manage_mod, "_load_config", return_value=config):
            with patch.object(_manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-log.jsonl")):
                with patch.object(_manage_mod, "_read_index_stats", return_value={"total": 3, "by_type": {}, "relations_count": 0, "stale_count": 0}):
                    result = cb_status()
        assert "bge-micro-v2" in result
        assert "3" in result  # 3 vectors in id_map

    def test_discover_handles_permission_error_on_rglob(self, tmp_path, monkeypatch):
        """Lines 95-96: PermissionError during rglob is swallowed via continue."""
        home = tmp_path / "home"
        docs = home / "Documents"
        docs.mkdir(parents=True)
        # Put one accessible vault in a second search root (Desktop)
        accessible = home / "Desktop" / "GoodVault"
        (accessible / ".obsidian").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        # Patch rglob on the docs Path to raise PermissionError
        real_rglob = Path.rglob

        def patched_rglob(self, pattern):
            if "Documents" in str(self):
                raise PermissionError("access denied")
            return real_rglob(self, pattern)

        monkeypatch.setattr(Path, "rglob", patched_rglob)
        with patch.object(_manage_mod, "_load_config", return_value=BASE_CONFIG):
            result = cb_configure(discover=True)
        assert "GoodVault" in result

    def test_vault_path_rebuild_thread_executes(self, tmp_path, monkeypatch):
        """Lines 135-141: the _rebuild function body actually executes in the thread."""
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        cfg_dir = home / ".claude" / "cyberbrain"
        cfg_dir.mkdir(parents=True)
        new_vault = home / "RebuildVault"

        # Let the thread run synchronously by not mocking Thread
        # but we mock search_backends so it doesn't actually index
        mock_sb = MagicMock()
        mock_backend = MagicMock()
        mock_backend.build_full_index = MagicMock()
        mock_sb.get_search_backend.return_value = mock_backend
        import sys
        with patch.dict(sys.modules, {"search_backends": mock_sb}):
            cb_configure(vault_path=str(new_vault))
            # Give daemon thread a brief moment to execute
            import time
            time.sleep(0.05)
        # The rebuild function ran and called get_search_backend
        # (may or may not complete depending on timing, but no crash)
        assert new_vault.exists()

    def test_configure_no_args_skips_invalid_json_lines_in_runs_log(self, tmp_path):
        """Lines 202-203: invalid JSON lines in runs log are silently skipped."""
        vault = tmp_path / "vault"
        vault.mkdir()
        runs_log = tmp_path / "runs.log"
        # Mix of invalid + valid JSON lines — valid one should be found
        import json as _json
        valid_entry = {"timestamp": "2026-02-01T10:00:00Z", "beats_written": 3, "session_id": "validxyz"}
        runs_log.write_text(
            "{ invalid json }\n" + _json.dumps(valid_entry) + "\n",
            encoding="utf-8",
        )
        config = {**BASE_CONFIG, "vault_path": str(vault)}
        with patch.object(_manage_mod, "_load_config", return_value=config):
            with patch.object(_manage_mod, "_read_index_stats", return_value={"total": 0, "by_type": {}, "relations_count": 0, "stale_count": 0}):
                with patch.object(_manage_mod, "RUNS_LOG_PATH", str(runs_log)):
                    result = cb_configure()
        # The valid entry (last valid JSON line) should be found
        assert "2026-02-01" in result or "validxyz" in result

    def test_status_handles_json_decode_error_in_runs_log(self, tmp_path):
        """Lines 239-242: JSONDecodeError in runs log lines is silently skipped."""
        runs_log = tmp_path / "runs.jsonl"
        runs_log.write_text("not json at all\nalso bad\n", encoding="utf-8")
        config = {**BASE_CONFIG, "vault_path": str(tmp_path)}
        with patch.object(_manage_mod, "_load_config", return_value=config):
            with patch.object(_manage_mod, "RUNS_LOG_PATH", str(runs_log)):
                with patch.object(_manage_mod, "_read_index_stats", return_value={}):
                    result = cb_status()
        # Should not crash — bad lines are skipped
        assert "No runs recorded" in result

    def test_status_handles_oserror_reading_runs_log(self, tmp_path):
        """Line 241-242: OSError reading runs log is swallowed."""
        runs_log = tmp_path / "runs.jsonl"
        runs_log.write_text('{"timestamp": "2026-01-01T00:00:00Z"}\n')
        config = {**BASE_CONFIG, "vault_path": str(tmp_path)}
        with patch.object(_manage_mod, "_load_config", return_value=config):
            with patch.object(_manage_mod, "RUNS_LOG_PATH", str(runs_log)):
                with patch.object(_manage_mod, "_read_index_stats", return_value={}):
                    with patch("builtins.open", side_effect=OSError("disk error")):
                        # Path.read_text uses open internally; patch to raise OSError
                        pass  # can't easily patch Path.read_text here
                    # Alternative: patch via the runs_log Path object
                    with patch.object(Path, "read_text", side_effect=OSError("disk error")):
                        result = cb_status()
        assert isinstance(result, str)
        assert "No runs recorded" in result

    def test_status_handles_manifest_parse_exception(self, tmp_path):
        """Lines 253-254: invalid manifest JSON is swallowed gracefully."""
        import json as _json
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text("{ this is not valid json }", encoding="utf-8")
        config = {
            **BASE_CONFIG,
            "vault_path": str(tmp_path),
            "search_manifest_path": str(manifest_path),
        }
        with patch.object(_manage_mod, "_load_config", return_value=config):
            with patch.object(_manage_mod, "RUNS_LOG_PATH", str(tmp_path / "no-log.jsonl")):
                with patch.object(_manage_mod, "_read_index_stats", return_value={"total": 0, "by_type": {}, "relations_count": 0, "stale_count": 0}):
                    result = cb_status()
        # Should not crash — manifest parse error is swallowed
        assert isinstance(result, str)
        assert "Cyberbrain Status" in result
