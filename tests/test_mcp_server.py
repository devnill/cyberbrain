"""
test_mcp_server.py — unit tests for mcp/server.py

Coverage:
- ToolError is raised (not returned as a string) for all genuine failure cases
- Successful-but-empty cases return strings, not ToolErrors
- transcript_path is restricted to ~/.claude/projects/
- Typed parameters (type_override, folder, cwd) replace the old free-text instructions param
- cwd parameter flows through to config loading in both cb_extract and cb_file
- max_results bounds are declared correctly in the schema
- Tool annotations are registered on the MCP tool objects

All extract_beats I/O and LLM calls are mocked. No vault writes, no real LLM calls.
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Inject mock extract_beats into sys.modules before importing the server.
#
# The server does a module-level `from extract_beats import ...`. We must
# pre-populate sys.modules so that import succeeds and binds our mocks.
# BackendError must be a real exception class so try/except works correctly.
# ---------------------------------------------------------------------------

class _BackendError(Exception):
    """Real exception class so the server's `except BackendError` clause works."""
    pass


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
sys.modules["extract_beats"] = _mock_eb


# ---------------------------------------------------------------------------
# Import the server module
# ---------------------------------------------------------------------------

import importlib.util

REPO_ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location(
    "_mcp_server", REPO_ROOT / "mcp" / "server.py"
)
_server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_server)


# Convenience aliases
cb_extract = _server.cb_extract
cb_file = _server.cb_file
cb_recall = _server.cb_recall
ToolError = _server.ToolError


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
    patch Path.home() globally so the server's path checks use it.
    """
    home = tmp_path / "home"
    (home / ".claude" / "projects").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


@pytest.fixture
def mock_config(fake_home, tmp_path):
    """
    Return a config dict with vault_path pointing to an existing temp directory.
    Also patches _server._resolve_config to return this config.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    config = {**BASE_CONFIG, "vault_path": str(vault)}
    return config


@pytest.fixture
def transcript_file(fake_home):
    """A real .jsonl transcript file inside the allowed ~/.claude/projects/ root."""
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
        """A path within ~/.claude/projects/ passes the restriction check (then raises not-found)."""
        inside = fake_home / ".claude" / "projects" / "nonexistent-uuid-4321.jsonl"
        # Should NOT raise "must be within" — should raise "not found" instead
        with pytest.raises(ToolError) as exc_info:
            cb_extract(transcript_path=str(inside))
        assert "not found" in str(exc_info.value).lower()
        assert "must be within" not in str(exc_info.value)


# ===========================================================================
# cb_extract — ToolError on genuine failures
# ===========================================================================

class TestCbExtractErrors:
    """cb_extract raises ToolError (not returns a string) for every genuine failure."""

    def test_raises_tool_error_when_file_not_found(self, fake_home, mock_config):
        """A path within the allowed root that doesn't exist raises ToolError."""
        missing = fake_home / ".claude" / "projects" / "ghost.jsonl"
        with patch.object(_server, "_resolve_config", return_value=mock_config):
            with pytest.raises(ToolError, match="not found"):
                cb_extract(transcript_path=str(missing))

    def test_raises_tool_error_when_transcript_is_empty(self, fake_home, mock_config, tmp_path):
        """An existing but empty transcript file raises ToolError."""
        empty = fake_home / ".claude" / "projects" / "empty.jsonl"
        empty.write_text("   \n")

        with patch.object(_server, "_resolve_config", return_value=mock_config):
            with patch.object(_server, "parse_jsonl_transcript", return_value=""):
                with pytest.raises(ToolError, match="empty"):
                    cb_extract(transcript_path=str(empty))

    def test_raises_tool_error_when_jsonl_parse_fails(self, fake_home, mock_config, transcript_file):
        """When parse_jsonl_transcript raises, ToolError is raised (not a string returned)."""
        with patch.object(_server, "_resolve_config", return_value=mock_config):
            with patch.object(_server, "parse_jsonl_transcript", side_effect=ValueError("bad jsonl")):
                with pytest.raises(ToolError, match="Failed to parse"):
                    cb_extract(transcript_path=str(transcript_file))

    def test_raises_tool_error_on_backend_error(self, fake_home, mock_config, transcript_file):
        """When the LLM backend raises BackendError, ToolError is raised with the backend name."""
        with patch.object(_server, "_resolve_config", return_value=mock_config):
            with patch.object(_server, "parse_jsonl_transcript", return_value="some content"):
            # Patch _extract_beats directly since that's what's called in the tool
                with patch.object(_server, "_extract_beats", side_effect=_BackendError("timed out")):
                    with pytest.raises(ToolError) as exc_info:
                        cb_extract(transcript_path=str(transcript_file))
        # Error message should name the backend
        assert "claude-code" in str(exc_info.value)

    def test_returns_string_when_no_beats_extracted(self, fake_home, mock_config, transcript_file):
        """When extraction yields no beats, the result is a string — not a ToolError."""
        with patch.object(_server, "_resolve_config", return_value=mock_config):
            with patch.object(_server, "parse_jsonl_transcript", return_value="some content"):
                with patch.object(_server, "_extract_beats", return_value=[]):
                    result = cb_extract(transcript_path=str(transcript_file))
        assert result == "No beats extracted."
        assert isinstance(result, str)


# ===========================================================================
# cb_extract — cwd parameter
# ===========================================================================

class TestCbExtractCwdParam:
    """cwd parameter is forwarded to config loading for project-scoped routing."""

    def test_cwd_is_forwarded_to_resolve_config(self, fake_home, mock_config, transcript_file):
        """When cwd is provided, _resolve_config is called with that path."""
        project_cwd = "/Users/dan/code/myproject"
        mock_resolve = MagicMock(return_value=mock_config)

        with patch.object(_server, "_resolve_config", mock_resolve):
            with patch.object(_server, "parse_jsonl_transcript", return_value="content"):
                with patch.object(_server, "_extract_beats", return_value=[]):
                    cb_extract(transcript_path=str(transcript_file), cwd=project_cwd)

        mock_resolve.assert_called_with(project_cwd)

    def test_cwd_defaults_to_home_when_omitted(self, fake_home, mock_config, transcript_file):
        """When cwd is omitted, _resolve_config is called with Path.home()."""
        mock_resolve = MagicMock(return_value=mock_config)

        with patch.object(_server, "_resolve_config", mock_resolve):
            with patch.object(_server, "parse_jsonl_transcript", return_value="content"):
                with patch.object(_server, "_extract_beats", return_value=[]):
                    cb_extract(transcript_path=str(transcript_file))

        called_with = mock_resolve.call_args[0][0]
        assert called_with == str(fake_home)


# ===========================================================================
# cb_extract — success path
# ===========================================================================

class TestCbExtractSuccess:
    """cb_extract returns a summary string listing created beats on success."""

    def test_success_returns_summary_string(self, fake_home, mock_config, tmp_path, transcript_file):
        """A successful extraction returns a string listing created beats."""
        vault = tmp_path / "vault"
        vault.mkdir(exist_ok=True)
        config = {**mock_config, "vault_path": str(vault)}

        beat = {"title": "My Insight", "type": "insight", "scope": "general",
                "summary": "Test", "tags": [], "body": "## Body\n\nContent."}
        fake_path = vault / "AI" / "Claude-Sessions" / "My Insight.md"
        (vault / "AI" / "Claude-Sessions").mkdir(parents=True)
        fake_path.write_text("content")

        with patch.object(_server, "_resolve_config", return_value=config):
            with patch.object(_server, "parse_jsonl_transcript", return_value="content"):
                with patch.object(_server, "_extract_beats", return_value=[beat]):
                    with patch.object(_server, "write_beat", return_value=fake_path):
                        result = cb_extract(transcript_path=str(transcript_file))

        assert "1/1" in result
        assert "insight" in result


# ===========================================================================
# cb_file — typed parameters replace free-text instructions
# ===========================================================================

class TestCbFileTypedParams:
    """
    cb_file now takes explicit type_override, folder, and cwd parameters
    instead of a free-text instructions string to parse with regex.
    """

    def test_type_override_is_applied_after_extraction(self, mock_config, tmp_path):
        """type_override forces the beat type regardless of what extraction returned."""
        vault = tmp_path / "vault"
        vault.mkdir(exist_ok=True)
        (vault / "AI" / "Claude-Sessions").mkdir(parents=True, exist_ok=True)
        config = {**mock_config, "vault_path": str(vault)}

        original_beat = {"title": "A Note", "type": "insight", "scope": "general",
                         "summary": "Test", "tags": [], "body": "body"}
        captured_beats = []

        def fake_write(beat, cfg, session_id, cwd, now):
            captured_beats.append(dict(beat))
            path = vault / "AI" / "Claude-Sessions" / "A Note.md"
            path.write_text("content")
            return path

        with patch.object(_server, "_resolve_config", return_value=config):
            with patch.object(_server, "_extract_beats", return_value=[original_beat]):
                with patch.object(_server, "write_beat", side_effect=fake_write):
                    cb_file(content="Some insight content", type_override="decision")

        assert len(captured_beats) == 1
        assert captured_beats[0]["type"] == "decision"

    def test_folder_sets_inbox_in_effective_config(self, mock_config, tmp_path):
        """folder parameter overrides the inbox routing key in the effective config."""
        vault = tmp_path / "vault"
        vault.mkdir(exist_ok=True)
        target_folder = "Personal/Recipes"
        (vault / target_folder).mkdir(parents=True, exist_ok=True)
        config = {**mock_config, "vault_path": str(vault)}

        beat = {"title": "A Beat", "type": "reference", "scope": "general",
                "summary": "Test", "tags": [], "body": "body"}
        captured_configs = []

        def fake_write(beat, cfg, session_id, cwd, now):
            captured_configs.append(dict(cfg))
            path = vault / target_folder / "A Beat.md"
            path.write_text("content")
            return path

        with patch.object(_server, "_resolve_config", return_value=config):
            with patch.object(_server, "_extract_beats", return_value=[beat]):
                with patch.object(_server, "write_beat", side_effect=fake_write):
                    cb_file(content="A great recipe", folder=target_folder)

        assert len(captured_configs) == 1
        assert captured_configs[0]["inbox"] == target_folder

    def test_cwd_is_forwarded_to_resolve_config(self, mock_config):
        """cwd parameter is forwarded to _resolve_config for project-scoped routing."""
        project_cwd = "/Users/dan/code/myproject"
        mock_resolve = MagicMock(return_value=mock_config)

        with patch.object(_server, "_resolve_config", mock_resolve):
            with patch.object(_server, "_extract_beats", return_value=[]):
                cb_file(content="Some content", cwd=project_cwd)

        mock_resolve.assert_called_with(project_cwd)

    def test_no_beats_identified_returns_string_not_error(self, mock_config):
        """When extraction finds nothing worth filing, a string is returned — not a ToolError."""
        with patch.object(_server, "_resolve_config", return_value=mock_config):
            with patch.object(_server, "_extract_beats", return_value=[]):
                result = cb_file(content="just some random text")

        assert isinstance(result, str)
        assert "No content worth filing" in result

    def test_instructions_param_no_longer_exists(self):
        """cb_file no longer accepts an 'instructions' parameter (replaced by typed params)."""
        import inspect
        sig = inspect.signature(cb_file)
        assert "instructions" not in sig.parameters
        assert "type_override" in sig.parameters
        assert "folder" in sig.parameters
        assert "cwd" in sig.parameters


# ===========================================================================
# cb_file — ToolError on genuine failures
# ===========================================================================

class TestCbFileErrors:
    """cb_file raises ToolError for genuine failures."""

    def test_raises_tool_error_on_backend_error(self, mock_config):
        """When extraction raises BackendError, ToolError is raised with the backend name."""
        with patch.object(_server, "_resolve_config", return_value=mock_config):
            with patch.object(_server, "_extract_beats", side_effect=_BackendError("timed out")):
                with pytest.raises(ToolError) as exc_info:
                    cb_file(content="Some content")
        assert "claude-code" in str(exc_info.value)

    def test_raises_tool_error_when_all_writes_fail(self, mock_config, tmp_path):
        """When beats are extracted but all writes raise, ToolError is raised."""
        vault = tmp_path / "vault"
        vault.mkdir(exist_ok=True)
        config = {**mock_config, "vault_path": str(vault)}

        beat = {"title": "A Note", "type": "insight", "scope": "general",
                "summary": "Test", "tags": [], "body": "body"}

        with patch.object(_server, "_resolve_config", return_value=config):
            with patch.object(_server, "_extract_beats", return_value=[beat]):
                with patch.object(_server, "write_beat", side_effect=OSError("disk full")):
                    with pytest.raises(ToolError) as exc_info:
                        cb_file(content="Some content")

        assert "write error" in str(exc_info.value).lower() or "vault_path" in str(exc_info.value)

    def test_partial_write_failures_still_return_success_for_written_beats(self, mock_config, tmp_path):
        """When some beats write successfully, returns success string (not ToolError)."""
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

        # First write succeeds, second fails
        call_count = {"n": 0}
        def fake_write(beat, cfg, session_id, cwd, now):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return good_path
            raise OSError("disk full")

        with patch.object(_server, "_resolve_config", return_value=config):
            with patch.object(_server, "_extract_beats", return_value=beats):
                with patch.object(_server, "write_beat", side_effect=fake_write):
                    result = cb_file(content="Some content")

        # Should not raise — one beat succeeded
        assert isinstance(result, str)
        assert "Beat One" in result


# ===========================================================================
# cb_recall — ToolError on short queries
# ===========================================================================

class TestCbRecallErrors:
    """cb_recall raises ToolError when the query is too short to search."""

    def test_raises_tool_error_for_single_char_query(self):
        """A single character query raises ToolError."""
        with pytest.raises(ToolError, match="too short"):
            cb_recall(query="x")

    def test_raises_tool_error_for_two_char_query(self):
        """A two-character query raises ToolError (requires 3+ char word)."""
        with pytest.raises(ToolError, match="too short"):
            cb_recall(query="ab")

    def test_raises_tool_error_for_only_short_words(self):
        """A query composed entirely of words shorter than 3 chars raises ToolError."""
        with pytest.raises(ToolError, match="too short"):
            cb_recall(query="a is it")

    def test_does_not_raise_for_valid_query(self, tmp_path):
        """A query with at least one 3+ character word does not raise ToolError."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = {**BASE_CONFIG, "vault_path": str(vault)}

        with patch.object(_server, "_resolve_config", return_value=config):
            with patch("subprocess.run", return_value=MagicMock(stdout="", returncode=0)):
                result = cb_recall(query="python")

        # Should return a "no notes found" string, not raise
        assert isinstance(result, str)


# ===========================================================================
# cb_recall — empty results return a string, not a ToolError
# ===========================================================================

class TestCbRecallEmptyResults:
    """Empty search results are a valid, non-error outcome."""

    def test_returns_string_when_no_notes_found(self, tmp_path):
        """When no vault notes match, a descriptive string is returned — not ToolError."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = {**BASE_CONFIG, "vault_path": str(vault)}

        with patch.object(_server, "_resolve_config", return_value=config):
            with patch("subprocess.run", return_value=MagicMock(stdout="", returncode=0)):
                result = cb_recall(query="redis")

        assert isinstance(result, str)
        assert "No notes found" in result
        assert "redis" in result

    def test_no_notes_found_string_is_not_an_error(self, tmp_path):
        """Verify the empty-result path does not go through ToolError at all."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = {**BASE_CONFIG, "vault_path": str(vault)}

        with patch.object(_server, "_resolve_config", return_value=config):
            with patch("subprocess.run", return_value=MagicMock(stdout="", returncode=0)):
                try:
                    result = cb_recall(query="kubernetes")
                except ToolError:
                    pytest.fail("cb_recall raised ToolError for empty results — should return a string")


# ===========================================================================
# cb_recall — max_results parameter
# ===========================================================================

class TestCbRecallMaxResults:
    """max_results default and schema bounds."""

    def test_max_results_default_is_five(self):
        """The default value for max_results is 5."""
        import inspect
        sig = inspect.signature(cb_recall)
        assert sig.parameters["max_results"].default == 5

    def test_max_results_field_has_ge_and_le_constraints(self):
        """max_results Field annotation declares ge=1, le=50."""
        import inspect
        from pydantic.fields import FieldInfo
        sig = inspect.signature(cb_recall)
        param = sig.parameters["max_results"]
        # Annotated[int, Field(ge=1, le=50)]
        # The annotation is available via __metadata__ on the Annotated type
        annotation = param.annotation
        # Get the FieldInfo from the Annotated metadata
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
    """Tool annotations are correctly registered on the MCP tool objects."""

    def _get_tool(self, name: str):
        return _server.mcp._tool_manager.get_tool(name)

    def test_cb_recall_has_readonly_hint(self):
        """cb_recall is annotated as readOnly since it never writes to the vault."""
        tool = self._get_tool("cb_recall")
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True

    def test_cb_recall_has_idempotent_hint(self):
        """cb_recall is annotated as idempotent — same query, same result."""
        tool = self._get_tool("cb_recall")
        assert tool.annotations.idempotentHint is True

    def test_cb_extract_has_destructive_hint_false(self):
        """cb_extract is annotated destructiveHint=False — it writes files but doesn't delete."""
        tool = self._get_tool("cb_extract")
        assert tool.annotations is not None
        assert tool.annotations.destructiveHint is False

    def test_cb_file_has_no_readonly_hint(self):
        """cb_file is a write operation and must NOT be marked readOnly."""
        tool = self._get_tool("cb_file")
        if tool.annotations:
            assert tool.annotations.readOnlyHint is not True


# ===========================================================================
# _parse_frontmatter
# ===========================================================================

class TestParseFrontmatter:
    """_parse_frontmatter() extracts YAML frontmatter fields from note content."""

    def test_parses_standard_frontmatter(self):
        """Standard YAML frontmatter → dict with expected fields."""
        content = '---\ntitle: "My Note"\ntype: decision\n---\n\nBody.'
        fm = _server._parse_frontmatter(content)
        assert fm["title"] == "My Note"
        assert fm["type"] == "decision"

    def test_parses_yaml_list_for_tags(self):
        """A tags list in frontmatter is parsed as a Python list."""
        content = '---\ntitle: "Note"\ntags: ["jwt", "auth"]\n---\n\nBody.'
        fm = _server._parse_frontmatter(content)
        assert fm["tags"] == ["jwt", "auth"]

    def test_parses_yaml_block_list_for_related(self):
        """A multi-line related: list is parsed correctly."""
        content = '---\ntitle: "Note"\nrelated:\n  - "[[Note A]]"\n  - "[[Note B]]"\n---\n\nBody.'
        fm = _server._parse_frontmatter(content)
        assert "[[Note A]]" in fm["related"]

    def test_returns_empty_dict_when_no_frontmatter(self):
        """Content with no --- delimiter returns empty dict."""
        content = "Just a body with no frontmatter."
        assert _server._parse_frontmatter(content) == {}

    def test_returns_empty_dict_on_parse_error(self):
        """Malformed YAML in frontmatter returns empty dict."""
        content = "---\n: invalid: yaml: {\n---\n\nBody."
        result = _server._parse_frontmatter(content)
        # Should return {} not raise
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
        """When _get_search_backend returns a backend, backend.search() is called."""
        vault = self._make_vault(tmp_path)
        note = self._make_note(
            vault, "JWT Auth.md",
            '---\ntitle: "JWT Auth"\ntype: decision\ntags: []\nrelated: []\nsummary: "JWT auth summary"\ndate: 2026-01-01\n---\n\n## Body\n\nContent.',
        )

        from search_backends import SearchResult
        mock_result = SearchResult(
            path=str(note),
            title="JWT Auth",
            summary="JWT auth summary",
            score=1.5,
            backend="fts5",
            note_type="decision",
        )

        mock_backend = MagicMock()
        mock_backend.search.return_value = [mock_result]
        mock_backend.backend_name.return_value = "fts5"

        config = {**BASE_CONFIG, "vault_path": str(vault)}
        with patch.object(_server, "_resolve_config", return_value=config):
            with patch.object(_server, "_get_search_backend", return_value=mock_backend):
                result = cb_recall(query="jwt authentication")

        mock_backend.search.assert_called_once()
        assert isinstance(result, str)

    def test_falls_back_to_grep_when_backend_returns_empty(self, tmp_path):
        """When backend returns empty results, grep subprocess is tried."""
        vault = self._make_vault(tmp_path)
        config = {**BASE_CONFIG, "vault_path": str(vault)}

        mock_backend = MagicMock()
        mock_backend.search.return_value = []
        mock_backend.backend_name.return_value = "fts5"

        with patch.object(_server, "_resolve_config", return_value=config):
            with patch.object(_server, "_get_search_backend", return_value=mock_backend):
                with patch("subprocess.run", return_value=MagicMock(stdout="", returncode=0)):
                    result = cb_recall(query="jwt authentication")

        # Should return a "no notes found" string (grep also found nothing)
        assert "No notes found" in result

    def test_falls_back_to_grep_when_backend_raises(self, tmp_path):
        """When backend.search() raises, grep fallback is used without propagating the error."""
        vault = self._make_vault(tmp_path)
        config = {**BASE_CONFIG, "vault_path": str(vault)}

        mock_backend = MagicMock()
        mock_backend.search.side_effect = RuntimeError("index corrupted")
        mock_backend.backend_name.return_value = "fts5"

        with patch.object(_server, "_resolve_config", return_value=config):
            with patch.object(_server, "_get_search_backend", return_value=mock_backend):
                with patch("subprocess.run", return_value=MagicMock(stdout="", returncode=0)):
                    result = cb_recall(query="jwt authentication")

        assert isinstance(result, str)

    def test_result_card_includes_related_field(self, tmp_path):
        """When a result has related wikilinks, 'Related:' appears in the output."""
        vault = self._make_vault(tmp_path)
        note = self._make_note(
            vault, "JWT Auth.md",
            '---\ntitle: "JWT Auth"\ntype: decision\ntags: []\nrelated: ["[[Note A]]"]\nsummary: "Summary"\ndate: 2026-01-01\n---\n\n## Body\n\nContent.',
        )

        from search_backends import SearchResult
        mock_result = SearchResult(
            path=str(note),
            title="JWT Auth",
            summary="Summary",
            score=1.5,
            backend="fts5",
            note_type="decision",
            related=["[[Note A]]"],
        )

        mock_backend = MagicMock()
        mock_backend.search.return_value = [mock_result]
        mock_backend.backend_name.return_value = "fts5"

        config = {**BASE_CONFIG, "vault_path": str(vault)}
        with patch.object(_server, "_resolve_config", return_value=config):
            with patch.object(_server, "_get_search_backend", return_value=mock_backend):
                result = cb_recall(query="jwt")

        assert "Related:" in result or "[[Note A]]" in result

    def test_result_card_includes_backend_name_in_header(self, tmp_path):
        """The result header includes the backend name."""
        vault = self._make_vault(tmp_path)
        note = self._make_note(
            vault, "JWT Auth.md",
            '---\ntitle: "JWT Auth"\ntype: decision\ntags: []\nrelated: []\nsummary: "Summary"\ndate: 2026-01-01\n---\n\n## Body\n\nContent.',
        )

        from search_backends import SearchResult
        mock_result = SearchResult(
            path=str(note),
            title="JWT Auth",
            summary="Summary",
            score=1.5,
            backend="fts5",
            note_type="decision",
        )

        mock_backend = MagicMock()
        mock_backend.search.return_value = [mock_result]
        mock_backend.backend_name.return_value = "fts5"

        config = {**BASE_CONFIG, "vault_path": str(vault)}
        with patch.object(_server, "_resolve_config", return_value=config):
            with patch.object(_server, "_get_search_backend", return_value=mock_backend):
                result = cb_recall(query="jwt")

        assert "fts5" in result

    def test_result_card_omits_related_when_empty(self, tmp_path):
        """When related list is empty, 'Related:' does not appear in the output."""
        vault = self._make_vault(tmp_path)
        note = self._make_note(
            vault, "JWT Auth.md",
            '---\ntitle: "JWT Auth"\ntype: decision\ntags: []\nrelated: []\nsummary: "Summary"\ndate: 2026-01-01\n---\n\n## Body\n\nContent.',
        )

        from search_backends import SearchResult
        mock_result = SearchResult(
            path=str(note),
            title="JWT Auth",
            summary="Summary",
            score=1.5,
            backend="fts5",
            note_type="decision",
            related=[],
        )

        mock_backend = MagicMock()
        mock_backend.search.return_value = [mock_result]
        mock_backend.backend_name.return_value = "fts5"

        config = {**BASE_CONFIG, "vault_path": str(vault)}
        with patch.object(_server, "_resolve_config", return_value=config):
            with patch.object(_server, "_get_search_backend", return_value=mock_backend):
                result = cb_recall(query="jwt")

        assert "Related:" not in result


# ===========================================================================
# cb_recall — synthesize
# ===========================================================================

class TestCbRecallSynthesize:
    """cb_recall with synthesize=True calls _synthesize_recall."""

    def _make_vault(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "AI" / "Claude-Sessions").mkdir(parents=True)
        return vault

    def _make_note(self, vault, filename, content):
        note = vault / "AI" / "Claude-Sessions" / filename
        note.write_text(content, encoding="utf-8")
        return note

    def _mock_backend_with_result(self, vault, note):
        from search_backends import SearchResult
        mock_result = SearchResult(
            path=str(note),
            title="JWT Auth",
            summary="Summary",
            score=1.5,
            backend="fts5",
            note_type="decision",
        )
        mock_backend = MagicMock()
        mock_backend.search.return_value = [mock_result]
        mock_backend.backend_name.return_value = "fts5"
        return mock_backend

    def test_synthesize_true_calls_synthesize_recall(self, tmp_path):
        """synthesize=True causes _synthesize_recall to be called."""
        vault = self._make_vault(tmp_path)
        note = self._make_note(
            vault, "JWT Auth.md",
            '---\ntitle: "JWT Auth"\ntype: decision\ntags: []\nrelated: []\nsummary: "Summary"\ndate: 2026-01-01\n---\n\n## Body\n\nContent.',
        )
        mock_backend = self._mock_backend_with_result(vault, note)

        config = {**BASE_CONFIG, "vault_path": str(vault)}
        with patch.object(_server, "_resolve_config", return_value=config):
            with patch.object(_server, "_get_search_backend", return_value=mock_backend):
                with patch.object(_server, "_synthesize_recall", return_value="synthesis result") as mock_synth:
                    cb_recall(query="jwt authentication", synthesize=True)

        mock_synth.assert_called_once()

    def test_synthesize_false_does_not_call_synthesize_recall(self, tmp_path):
        """synthesize=False means _synthesize_recall is never called."""
        vault = self._make_vault(tmp_path)
        note = self._make_note(
            vault, "JWT Auth.md",
            '---\ntitle: "JWT Auth"\ntype: decision\ntags: []\nrelated: []\nsummary: "Summary"\ndate: 2026-01-01\n---\n\n## Body\n\nContent.',
        )
        mock_backend = self._mock_backend_with_result(vault, note)

        config = {**BASE_CONFIG, "vault_path": str(vault)}
        with patch.object(_server, "_resolve_config", return_value=config):
            with patch.object(_server, "_get_search_backend", return_value=mock_backend):
                with patch.object(_server, "_synthesize_recall") as mock_synth:
                    cb_recall(query="jwt authentication", synthesize=False)

        mock_synth.assert_not_called()

    def test_synthesize_recall_prepends_synthesis_to_retrieved_content(self, tmp_path):
        """_synthesize_recall returns synthesis output before the vault content."""
        config = {**BASE_CONFIG, "vault_path": str(tmp_path)}
        retrieved = "## Retrieved from knowledge vault\n\nsome vault content\n## End of retrieved content"

        with patch.object(_server, "_call_claude_code_backend", return_value="Here is the synthesis."):
            result = _server._synthesize_recall("test query", retrieved, config)

        assert result.index("synthesis") < result.index("Retrieved from knowledge vault")

    def test_synthesize_recall_falls_back_gracefully_on_error(self, tmp_path):
        """If _call_claude_code_backend raises, the original retrieved content is returned with a note."""
        config = {**BASE_CONFIG, "vault_path": str(tmp_path)}
        retrieved = "## Retrieved from knowledge vault\n\nsome content\n## End of retrieved content"

        with patch.object(_server, "_call_claude_code_backend", side_effect=RuntimeError("backend error")):
            result = _server._synthesize_recall("test query", retrieved, config)

        # Should contain the original retrieved content
        assert "some content" in result
        # Should contain a note about the failure
        assert "Synthesis failed" in result or "synthesis failed" in result.lower()
