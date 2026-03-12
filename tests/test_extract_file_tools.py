"""
test_extract_file_tools.py — tests for mcp/tools/extract.py and mcp/tools/file.py

Covers gaps not reached by test_mcp_server.py:
- extract.py: transcript outside ~/.claude/projects/ -> ToolError
- extract.py: plain text .txt file (non-JSONL path)
- extract.py: autofile_enabled=True calls autofile_beat
- extract.py: OSError reading plain text file -> ToolError
- extract.py: BackendError -> ToolError with backend name
- extract.py: daily_journal=True + written -> write_journal_entry called
- file.py: autofile_enabled=True calls autofile_beat
- file.py: autofile_enabled=True + folder override -> uses write_beat (autofile disabled)
- file.py: daily_journal=True -> write_journal_entry called

Patching strategy: use patch.object(module, "attr") rather than string-based
patch("tools.extract.attr") so patches always target the live module object
held by our import reference, regardless of what other test files do to
sys.modules.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# sys.path setup + mock extract_beats BEFORE any shared/tools imports
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent


# conftest.py installs the shared extract_beats mock before any test module runs.
# We just import the tool modules here; no additional mock setup needed.
# Using patch.object (not string-based patch) ensures patches always target the
# live module object, regardless of what other test files do to sys.modules.
import cyberbrain.mcp.tools.extract as extract_module
import cyberbrain.mcp.tools.file as file_module


def _get_backend_error():
    """Return the BackendError class currently bound in the extract module.

    Looking this up dynamically ensures we use whatever BackendError is live in
    the module (installed by conftest.py), so 'except BackendError' in the tool
    code catches our side_effect exception.
    """
    mod = _get_extract_module()
    return getattr(mod, "BackendError", Exception)


def _get_extract_module():
    """Return the live extract module — may have been replaced by another test file."""
    return sys.modules.get("cyberbrain.mcp.tools.extract", extract_module)


def _get_file_module():
    """Return the live file module — may have been replaced by another test file."""
    return sys.modules.get("cyberbrain.mcp.tools.file", file_module)


# ---------------------------------------------------------------------------
# FakeMCP
# ---------------------------------------------------------------------------

class FakeMCP:
    def __init__(self):
        self.tools = {}
        self.annotations = {}

    def tool(self, annotations=None, **kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            self.annotations[fn.__name__] = annotations
            return fn
        return decorator


def _register_extract():
    mod = _get_extract_module()
    mcp = FakeMCP()
    mod.register(mcp)
    return mcp.tools["cb_extract"]


def _register_file():
    mod = _get_file_module()
    mcp = FakeMCP()
    mod.register(mcp)
    return mcp.tools["cb_file"]


# ---------------------------------------------------------------------------
# Shared beat fixture
# ---------------------------------------------------------------------------

SAMPLE_BEAT = {
    "title": "Use Connection Pooling",
    "type": "decision",
    "scope": "project",
    "summary": "Always use connection pooling for DB access.",
    "tags": ["postgres", "performance"],
    "body": "## Decision\n\nUse pgbouncer for connection pooling.",
}


def _base_config(vault: Path, **overrides) -> dict:
    cfg = {
        "vault_path": str(vault),
        "inbox": "AI/Claude-Sessions",
        "backend": "claude-code",
        "model": "claude-haiku-4-5",
        "autofile": False,
        "daily_journal": False,
    }
    cfg.update(overrides)
    return cfg


# ===========================================================================
# cb_extract — path restriction
# ===========================================================================

class TestCbExtractPathRestriction:
    """transcript_path must be within ~/.claude/projects/."""

    def test_path_outside_projects_raises_tool_error(self, tmp_path, monkeypatch):
        """A transcript path outside ~/.claude/projects/ raises ToolError."""
        from fastmcp.exceptions import ToolError

        home = tmp_path / "home"
        (home / ".claude" / "projects").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        # Write a file outside the allowed root
        bad_file = tmp_path / "sneaky.txt"
        bad_file.write_text("some content", encoding="utf-8")

        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault)

        mod = _get_extract_module()
        cb_extract = _register_extract()
        with patch.object(mod, "_load_config", return_value=config):
            with pytest.raises(ToolError, match="must be within"):
                cb_extract(transcript_path=str(bad_file))

    def test_path_inside_projects_passes_restriction(self, tmp_path, monkeypatch):
        """A .jsonl file inside ~/.claude/projects/ passes the path check."""
        home = tmp_path / "home"
        (home / ".claude" / "projects").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        transcript = home / ".claude" / "projects" / "session.jsonl"
        transcript.write_text(
            '{"type": "user", "message": {"role": "user", "content": "hello"}}\n',
            encoding="utf-8",
        )

        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault)

        mod = _get_extract_module()
        cb_extract = _register_extract()
        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "parse_jsonl_transcript", return_value="User: hello"):
                with patch.object(mod, "_extract_beats", return_value=[]):
                    result = cb_extract(transcript_path=str(transcript))

        assert "No beats extracted" in result


# ===========================================================================
# cb_extract — plain text transcript
# ===========================================================================

class TestCbExtractPlainText:
    """Non-.jsonl transcripts are read as plain text."""

    def test_txt_file_is_read_as_plain_text(self, tmp_path, monkeypatch):
        """A .txt file bypasses parse_jsonl_transcript and is read directly."""
        home = tmp_path / "home"
        (home / ".claude" / "projects").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        transcript = home / ".claude" / "projects" / "export.txt"
        transcript.write_text("User: what is jwt?\nAssistant: JWT is a token format.", encoding="utf-8")

        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault)

        mod = _get_extract_module()
        cb_extract = _register_extract()
        mock_beats = MagicMock(return_value=[])
        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_extract_beats", mock_beats):
                result = cb_extract(transcript_path=str(transcript))

        # extract_beats should have been called with the plain text content
        mock_beats.assert_called_once()
        call_args = mock_beats.call_args[0]
        assert "jwt" in call_args[0].lower() or "JWT" in call_args[0]
        assert "No beats extracted" in result

    def test_unreadable_txt_file_raises_tool_error(self, tmp_path, monkeypatch):
        """OSError reading a plain text transcript raises ToolError."""
        from fastmcp.exceptions import ToolError

        home = tmp_path / "home"
        (home / ".claude" / "projects").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        transcript = home / ".claude" / "projects" / "broken.txt"
        transcript.write_text("content", encoding="utf-8")

        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault)

        mod = _get_extract_module()
        cb_extract = _register_extract()
        with patch.object(mod, "_load_config", return_value=config):
            with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
                with pytest.raises(ToolError, match="Failed to read"):
                    cb_extract(transcript_path=str(transcript))


# ===========================================================================
# cb_extract — BackendError
# ===========================================================================

class TestCbExtractBackendError:
    """BackendError from _extract_beats is wrapped in ToolError."""

    def test_backend_error_raises_tool_error_with_backend_name(self, tmp_path, monkeypatch):
        """BackendError becomes ToolError mentioning the backend name."""
        from fastmcp.exceptions import ToolError

        home = tmp_path / "home"
        (home / ".claude" / "projects").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        transcript = home / ".claude" / "projects" / "session.jsonl"
        transcript.write_text(
            '{"type": "user", "message": {"role": "user", "content": "hello"}}\n',
            encoding="utf-8",
        )

        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault, backend="ollama")

        BackendError = _get_backend_error()
        mod = _get_extract_module()
        cb_extract = _register_extract()
        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "parse_jsonl_transcript", return_value="User: hello"):
                with patch.object(mod, "_extract_beats", side_effect=BackendError("connection refused")):
                    with pytest.raises(ToolError, match="ollama"):
                        cb_extract(transcript_path=str(transcript))


# ===========================================================================
# cb_extract — autofile path
# ===========================================================================

class TestCbExtractAutofile:
    """When autofile=True, autofile_beat is called instead of write_beat."""

    def test_autofile_enabled_calls_autofile_beat(self, tmp_path, monkeypatch):
        """autofile=True routes each beat through autofile_beat."""
        home = tmp_path / "home"
        (home / ".claude" / "projects").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        transcript = home / ".claude" / "projects" / "session.jsonl"
        transcript.write_text(
            '{"type": "user", "message": {"role": "user", "content": "hello"}}\n',
            encoding="utf-8",
        )

        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault, autofile=True)

        fake_path = vault / "AI/Claude-Sessions/Use Connection Pooling.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_extract_module()
        cb_extract = _register_extract()
        mock_autofile = MagicMock(return_value=fake_path)
        mock_write = MagicMock(return_value=None)

        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "parse_jsonl_transcript", return_value="User: hello"):
                with patch.object(mod, "_extract_beats", return_value=[SAMPLE_BEAT]):
                    with patch.object(mod, "autofile_beat", mock_autofile):
                        with patch.object(mod, "write_beat", mock_write):
                            result = cb_extract(transcript_path=str(transcript))

        mock_autofile.assert_called_once()
        mock_write.assert_not_called()
        assert "Created" in result

    def test_autofile_disabled_calls_write_beat(self, tmp_path, monkeypatch):
        """autofile=False routes each beat through write_beat."""
        home = tmp_path / "home"
        (home / ".claude" / "projects").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        transcript = home / ".claude" / "projects" / "session.jsonl"
        transcript.write_text(
            '{"type": "user", "message": {"role": "user", "content": "hello"}}\n',
            encoding="utf-8",
        )

        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault, autofile=False)

        fake_path = vault / "AI/Claude-Sessions/Use Connection Pooling.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_extract_module()
        cb_extract = _register_extract()
        mock_autofile = MagicMock(return_value=None)
        mock_write = MagicMock(return_value=fake_path)

        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "parse_jsonl_transcript", return_value="User: hello"):
                with patch.object(mod, "_extract_beats", return_value=[SAMPLE_BEAT]):
                    with patch.object(mod, "autofile_beat", mock_autofile):
                        with patch.object(mod, "write_beat", mock_write):
                            result = cb_extract(transcript_path=str(transcript))

        mock_write.assert_called_once()
        mock_autofile.assert_not_called()


# ===========================================================================
# cb_extract — daily journal
# ===========================================================================

class TestCbExtractDailyJournal:
    """When daily_journal=True and beats were written, write_journal_entry is called."""

    def test_daily_journal_called_when_beats_written(self, tmp_path, monkeypatch):
        """daily_journal=True causes write_journal_entry to be invoked after extraction."""
        home = tmp_path / "home"
        (home / ".claude" / "projects").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        transcript = home / ".claude" / "projects" / "session.jsonl"
        transcript.write_text(
            '{"type": "user", "message": {"role": "user", "content": "hello"}}\n',
            encoding="utf-8",
        )

        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault, daily_journal=True)

        fake_path = vault / "AI/Claude-Sessions/Use Connection Pooling.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_extract_module()
        cb_extract = _register_extract()
        mock_journal = MagicMock()
        mock_write = MagicMock(return_value=fake_path)

        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "parse_jsonl_transcript", return_value="User: hello"):
                with patch.object(mod, "_extract_beats", return_value=[SAMPLE_BEAT]):
                    with patch.object(mod, "write_beat", mock_write):
                        with patch.object(mod, "write_journal_entry", mock_journal):
                            cb_extract(transcript_path=str(transcript))

        mock_journal.assert_called_once()

    def test_daily_journal_not_called_when_no_beats_written(self, tmp_path, monkeypatch):
        """daily_journal=True but no beats written -> write_journal_entry NOT called."""
        home = tmp_path / "home"
        (home / ".claude" / "projects").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        transcript = home / ".claude" / "projects" / "session.jsonl"
        transcript.write_text(
            '{"type": "user", "message": {"role": "user", "content": "hello"}}\n',
            encoding="utf-8",
        )

        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault, daily_journal=True)

        mod = _get_extract_module()
        cb_extract = _register_extract()
        mock_journal = MagicMock()

        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "parse_jsonl_transcript", return_value="User: hello"):
                with patch.object(mod, "_extract_beats", return_value=[]):
                    with patch.object(mod, "write_journal_entry", mock_journal):
                        result = cb_extract(transcript_path=str(transcript))

        mock_journal.assert_not_called()
        assert "No beats extracted" in result


# ===========================================================================
# cb_file — autofile path
# ===========================================================================

class TestCbFileAutofile:
    """cb_file: autofile routing behavior."""

    def test_autofile_enabled_calls_autofile_beat(self, tmp_path):
        """autofile=True calls autofile_beat instead of write_beat."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault, autofile=True)

        fake_path = vault / "AI/Claude-Sessions/Use Connection Pooling.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_file_module()
        cb_file = _register_file()
        mock_autofile = MagicMock(return_value=fake_path)
        mock_write = MagicMock(return_value=None)

        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_extract_beats", return_value=[SAMPLE_BEAT]):
                with patch.object(mod, "autofile_beat", mock_autofile):
                    with patch.object(mod, "write_beat", mock_write):
                        result = cb_file(content="Use connection pooling for all DB access.")

        mock_autofile.assert_called_once()
        mock_write.assert_not_called()
        assert "Filed" in result or "Use Connection Pooling" in result

    def test_autofile_enabled_with_folder_override_uses_write_beat(self, tmp_path):
        """autofile=True but folder is specified -> autofile disabled, uses write_beat."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault, autofile=True)

        fake_path = vault / "Personal/Recipes/Use Connection Pooling.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_file_module()
        cb_file = _register_file()
        mock_autofile = MagicMock(return_value=None)
        mock_write = MagicMock(return_value=fake_path)

        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_extract_beats", return_value=[SAMPLE_BEAT]):
                with patch.object(mod, "autofile_beat", mock_autofile):
                    with patch.object(mod, "write_beat", mock_write):
                        result = cb_file(
                            content="Use connection pooling for all DB access.",
                            folder="Personal/Recipes",
                        )

        # autofile_beat should NOT be called when folder is explicitly set
        mock_autofile.assert_not_called()
        mock_write.assert_called_once()

    def test_autofile_disabled_calls_write_beat(self, tmp_path):
        """autofile=False always uses write_beat."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault, autofile=False)

        fake_path = vault / "AI/Claude-Sessions/Use Connection Pooling.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_file_module()
        cb_file = _register_file()
        mock_autofile = MagicMock(return_value=None)
        mock_write = MagicMock(return_value=fake_path)

        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_extract_beats", return_value=[SAMPLE_BEAT]):
                with patch.object(mod, "autofile_beat", mock_autofile):
                    with patch.object(mod, "write_beat", mock_write):
                        result = cb_file(content="Use connection pooling for all DB access.")

        mock_autofile.assert_not_called()
        mock_write.assert_called_once()


# ===========================================================================
# cb_file — daily journal
# ===========================================================================

class TestCbFileDailyJournal:
    """cb_file: daily_journal=True calls write_journal_entry after filing."""

    def test_daily_journal_called_when_beat_filed(self, tmp_path):
        """daily_journal=True calls write_journal_entry after a beat is written."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault, daily_journal=True)

        fake_path = vault / "AI/Claude-Sessions/Use Connection Pooling.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_file_module()
        cb_file = _register_file()
        mock_journal = MagicMock()
        mock_write = MagicMock(return_value=fake_path)

        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_extract_beats", return_value=[SAMPLE_BEAT]):
                with patch.object(mod, "write_beat", mock_write):
                    with patch.object(mod, "write_journal_entry", mock_journal):
                        cb_file(content="Use connection pooling for all DB access.")

        mock_journal.assert_called_once()

    def test_daily_journal_not_called_when_no_writes(self, tmp_path):
        """daily_journal=True but write_beat returns None -> write_journal_entry NOT called."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault, daily_journal=True)

        mod = _get_file_module()
        cb_file = _register_file()
        mock_journal = MagicMock()
        mock_write = MagicMock(return_value=None)

        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_extract_beats", return_value=[SAMPLE_BEAT]):
                with patch.object(mod, "write_beat", mock_write):
                    with patch.object(mod, "write_journal_entry", mock_journal):
                        # write_beat returns None -> written list is empty -> ToolError raised
                        from fastmcp.exceptions import ToolError
                        with pytest.raises(ToolError):
                            cb_file(content="Use connection pooling for all DB access.")

        mock_journal.assert_not_called()


# ===========================================================================
# cb_file — BackendError
# ===========================================================================

class TestCbFileBackendError:
    """BackendError from _extract_beats is wrapped in ToolError."""

    def test_backend_error_raises_tool_error(self, tmp_path):
        """BackendError propagates as ToolError mentioning the backend."""
        from fastmcp.exceptions import ToolError

        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault, backend="bedrock")

        BackendError = getattr(_get_file_module(), "BackendError", Exception)
        mod = _get_file_module()
        cb_file = _register_file()
        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_extract_beats", side_effect=BackendError("timeout")):
                with pytest.raises(ToolError, match="bedrock"):
                    cb_file(content="some content to file")


# ===========================================================================
# cb_file — no content worth filing
# ===========================================================================

class TestCbFileNoContent:
    """cb_file returns a message when no beats are extracted."""

    def test_returns_no_content_message_when_beats_empty(self, tmp_path):
        """Empty beat list returns a 'No content worth filing' message."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault)

        mod = _get_file_module()
        cb_file = _register_file()
        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_extract_beats", return_value=[]):
                result = cb_file(content="hmm")

        assert "No content worth filing" in result


# ===========================================================================
# cb_file — type_override
# ===========================================================================

class TestCbFileTypeOverride:
    """type_override forces the beat type after extraction."""

    def test_type_override_applied_to_all_beats(self, tmp_path):
        """All extracted beats have their type overridden when type_override is given."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault)

        beat = dict(SAMPLE_BEAT)  # type: "decision"
        fake_path = vault / "AI/Claude-Sessions/Use Connection Pooling.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_file_module()
        cb_file = _register_file()
        captured_beats = []

        def capture_write(b, *args, **kwargs):
            captured_beats.append(dict(b))
            return fake_path

        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_extract_beats", return_value=[beat]):
                with patch.object(mod, "write_beat", side_effect=capture_write):
                    cb_file(content="some content", type_override="reference")

        assert len(captured_beats) == 1
        assert captured_beats[0]["type"] == "reference"


# ===========================================================================
# cb_extract — transcript truncation and vault CLAUDE.md reading
# ===========================================================================

class TestCbExtractAdditional:
    """Additional coverage for less common paths."""

    def test_long_transcript_is_truncated(self, tmp_path, monkeypatch):
        """Transcripts over 150k characters are truncated before extraction."""
        home = tmp_path / "home"
        (home / ".claude" / "projects").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        transcript = home / ".claude" / "projects" / "long.txt"
        # Write content just over MAX_CHARS (150_000) using a plain text file
        long_content = "x" * 160_000
        transcript.write_text(long_content, encoding="utf-8")

        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault)

        mod = _get_extract_module()
        cb_extract = _register_extract()
        captured_text = []

        def capture_extract(text, *args, **kwargs):
            captured_text.append(text)
            return []

        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_extract_beats", side_effect=capture_extract):
                cb_extract(transcript_path=str(transcript))

        assert len(captured_text) == 1
        assert captured_text[0].startswith("...[earlier content truncated]...")
        assert len(captured_text[0]) < 160_000

    def test_autofile_reads_vault_claude_md_when_present(self, tmp_path, monkeypatch):
        """When autofile=True and vault CLAUDE.md exists, it's read and passed to autofile_beat."""
        home = tmp_path / "home"
        (home / ".claude" / "projects").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        transcript = home / ".claude" / "projects" / "session.jsonl"
        transcript.write_text(
            '{"type": "user", "message": {"role": "user", "content": "hello"}}\n',
            encoding="utf-8",
        )

        vault = tmp_path / "vault"
        vault.mkdir()
        # Write a vault CLAUDE.md
        claude_md = vault / "CLAUDE.md"
        claude_md.write_text("# Vault Instructions\n\nUse type: decision, insight.", encoding="utf-8")

        config = _base_config(vault, autofile=True)

        fake_path = vault / "AI/Claude-Sessions/Use Connection Pooling.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_extract_module()
        cb_extract = _register_extract()
        mock_autofile = MagicMock(return_value=fake_path)

        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "parse_jsonl_transcript", return_value="User: hello"):
                with patch.object(mod, "_extract_beats", return_value=[SAMPLE_BEAT]):
                    with patch.object(mod, "autofile_beat", mock_autofile):
                        with patch.object(mod, "write_beat", MagicMock(return_value=None)):
                            cb_extract(transcript_path=str(transcript))

        # autofile_beat should have been called with vault_context containing the CLAUDE.md content
        mock_autofile.assert_called_once()
        call_kwargs = mock_autofile.call_args[1]
        assert "vault_context" in call_kwargs
        assert "Vault Instructions" in call_kwargs["vault_context"]

    def test_write_beat_exception_is_recorded_in_output(self, tmp_path, monkeypatch):
        """When write_beat raises, the error is recorded in the summary (not re-raised)."""
        home = tmp_path / "home"
        (home / ".claude" / "projects").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        transcript = home / ".claude" / "projects" / "session.jsonl"
        transcript.write_text(
            '{"type": "user", "message": {"role": "user", "content": "hello"}}\n',
            encoding="utf-8",
        )

        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault)

        mod = _get_extract_module()
        cb_extract = _register_extract()

        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "parse_jsonl_transcript", return_value="User: hello"):
                with patch.object(mod, "_extract_beats", return_value=[SAMPLE_BEAT]):
                    with patch.object(mod, "write_beat", side_effect=OSError("disk full")):
                        result = cb_extract(transcript_path=str(transcript))

        # Error is recorded in the summary, not raised
        assert "Error on" in result or "disk full" in result


# ===========================================================================
# cb_file — vault CLAUDE.md reading during autofile
# ===========================================================================

class TestCbFileAdditional:
    """Additional coverage for file.py autofile vault context reading."""

    def test_autofile_reads_vault_claude_md_when_present(self, tmp_path):
        """When autofile=True and vault CLAUDE.md exists, it's read and passed to autofile_beat."""
        vault = tmp_path / "vault"
        vault.mkdir()
        # Write a vault CLAUDE.md
        claude_md = vault / "CLAUDE.md"
        claude_md.write_text("# Vault Guide\n\nUse types: decision, reference.", encoding="utf-8")

        config = _base_config(vault, autofile=True)

        fake_path = vault / "AI/Claude-Sessions/Use Connection Pooling.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_file_module()
        cb_file = _register_file()
        mock_autofile = MagicMock(return_value=fake_path)

        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_extract_beats", return_value=[SAMPLE_BEAT]):
                with patch.object(mod, "autofile_beat", mock_autofile):
                    with patch.object(mod, "write_beat", MagicMock(return_value=None)):
                        cb_file(content="Use connection pooling for all DB access.")

        mock_autofile.assert_called_once()
        call_kwargs = mock_autofile.call_args[1]
        assert "vault_context" in call_kwargs
        assert "Vault Guide" in call_kwargs["vault_context"]
