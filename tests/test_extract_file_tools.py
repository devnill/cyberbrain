"""
test_extract_file_tools.py — tests for src/cyberbrain/mcp/tools/extract.py and src/cyberbrain/mcp/tools/file.py

Covers gaps not reached by test_mcp_server.py:
- extract.py: transcript outside ~/.claude/projects/ -> ToolError
- extract.py: plain text .txt file (non-JSONL path)
- extract.py: BackendError from run_extraction -> ToolError with backend name
- extract.py: OSError reading plain text file -> ToolError
- extract.py: run_extraction returns beats -> summary formatted correctly
- extract.py: run_extraction returns skipped -> skipped message returned
- extract.py: transcript truncation applied before calling run_extraction
- file.py: autofile_enabled=True calls autofile_beat
- file.py: autofile_enabled=True + folder override -> uses write_beat (autofile disabled)
- file.py: daily_journal=True -> write_journal_entry called

Patching strategy: use patch.object(module, "attr") rather than string-based
patch("tools.extract.attr") so patches always target the live module object
held by our import reference, regardless of what other test files do to
sys.modules.

cb_extract delegates orchestration (dedup, vault writing, logs, journal) to
run_extraction() in extract_beats.py. Tests for that shared orchestration live
in test_extract_beats.py. These tests verify the MCP layer: path restriction,
transcript parsing/truncation, BackendError handling, and result formatting.
"""

import json
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
        with patch.object(mod, "require_config", return_value=config):
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
        _fake_result = {
            "skipped": False,
            "beats_count": 0,
            "beats_written": 0,
            "written_paths": [],
            "beat_records": [],
            "run_errors": [],
        }
        with patch.object(mod, "require_config", return_value=config):
            with patch.object(
                mod, "parse_jsonl_transcript", return_value="User: hello"
            ):
                with patch.object(mod, "run_extraction", return_value=_fake_result):
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
        transcript.write_text(
            "User: what is jwt?\nAssistant: JWT is a token format.", encoding="utf-8"
        )

        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault)

        mod = _get_extract_module()
        cb_extract = _register_extract()
        _fake_result = {
            "skipped": False,
            "beats_count": 0,
            "beats_written": 0,
            "written_paths": [],
            "beat_records": [],
            "run_errors": [],
        }
        mock_run = MagicMock(return_value=_fake_result)
        with patch.object(mod, "require_config", return_value=config):
            with patch.object(mod, "run_extraction", mock_run):
                result = cb_extract(transcript_path=str(transcript))

        # run_extraction should have been called with the plain text content
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0]
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
        with patch.object(mod, "require_config", return_value=config):
            with patch(
                "pathlib.Path.read_text", side_effect=OSError("permission denied")
            ):
                with pytest.raises(ToolError, match="Failed to read"):
                    cb_extract(transcript_path=str(transcript))


# ===========================================================================
# cb_extract — BackendError
# ===========================================================================


class TestCbExtractBackendError:
    """BackendError from _extract_beats is wrapped in ToolError."""

    def test_backend_error_raises_tool_error_with_backend_name(
        self, tmp_path, monkeypatch
    ):
        """BackendError from run_extraction becomes ToolError mentioning the backend name."""
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
        with patch.object(mod, "require_config", return_value=config):
            with patch.object(
                mod, "parse_jsonl_transcript", return_value="User: hello"
            ):
                with patch.object(
                    mod,
                    "run_extraction",
                    side_effect=BackendError("connection refused"),
                ):
                    with pytest.raises(ToolError, match="ollama"):
                        cb_extract(transcript_path=str(transcript))


# ===========================================================================
# cb_extract — autofile path
# ===========================================================================


class TestCbExtractAutofile:
    """cb_extract delegates autofile routing to run_extraction; result is formatted correctly."""

    def test_beats_written_appear_in_summary(self, tmp_path, monkeypatch):
        """run_extraction result with written beats produces a 'Created:' summary."""
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

        fake_record = {
            "title": "Use Connection Pooling",
            "type": "decision",
            "scope": "project",
            "path": "AI/Claude-Sessions/Use Connection Pooling.md",
        }
        _fake_result = {
            "skipped": False,
            "beats_count": 1,
            "beats_written": 1,
            "written_paths": [vault / "AI/Claude-Sessions/Use Connection Pooling.md"],
            "beat_records": [fake_record],
            "run_errors": [],
        }

        mod = _get_extract_module()
        cb_extract = _register_extract()
        with patch.object(mod, "require_config", return_value=config):
            with patch.object(
                mod, "parse_jsonl_transcript", return_value="User: hello"
            ):
                with patch.object(mod, "run_extraction", return_value=_fake_result):
                    result = cb_extract(transcript_path=str(transcript))

        assert "Created" in result
        assert "Use Connection Pooling.md" in result

    def test_no_beats_returns_no_beats_message(self, tmp_path, monkeypatch):
        """run_extraction returning zero beats produces 'No beats extracted.' message."""
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

        _fake_result = {
            "skipped": False,
            "beats_count": 0,
            "beats_written": 0,
            "written_paths": [],
            "beat_records": [],
            "run_errors": [],
        }

        mod = _get_extract_module()
        cb_extract = _register_extract()
        with patch.object(mod, "require_config", return_value=config):
            with patch.object(
                mod, "parse_jsonl_transcript", return_value="User: hello"
            ):
                with patch.object(mod, "run_extraction", return_value=_fake_result):
                    result = cb_extract(transcript_path=str(transcript))

        assert "No beats extracted" in result


# ===========================================================================
# cb_extract — daily journal
# ===========================================================================


class TestCbExtractDailyJournal:
    """cb_extract delegates journal writing to run_extraction.

    Journal behavior (write_journal_entry called/not-called) is tested at the
    run_extraction level in test_extract_beats.py. Here we verify that the
    cb_extract MCP layer correctly passes the config to run_extraction and
    formats the result.
    """

    def test_run_extraction_called_with_correct_trigger(self, tmp_path, monkeypatch):
        """cb_extract always calls run_extraction with trigger='manual'."""
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

        _fake_result = {
            "skipped": False,
            "beats_count": 0,
            "beats_written": 0,
            "written_paths": [],
            "beat_records": [],
            "run_errors": [],
        }

        mod = _get_extract_module()
        cb_extract = _register_extract()
        mock_run = MagicMock(return_value=_fake_result)

        with patch.object(mod, "require_config", return_value=config):
            with patch.object(
                mod, "parse_jsonl_transcript", return_value="User: hello"
            ):
                with patch.object(mod, "run_extraction", mock_run):
                    cb_extract(transcript_path=str(transcript))

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        # trigger is passed as positional arg index 2 or keyword
        args, kwargs = call_kwargs
        trigger = (
            args[2]
            if len(args) > 2
            else kwargs.get("trigger", args[2] if len(args) > 2 else None)
        )
        assert trigger == "manual"

    def test_skipped_session_returns_skipped_message(self, tmp_path, monkeypatch):
        """When run_extraction returns skipped=True, cb_extract returns a skipped message."""
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

        _skipped_result = {
            "skipped": True,
            "beats_count": 0,
            "beats_written": 0,
            "written_paths": [],
            "beat_records": [],
            "run_errors": [],
        }

        mod = _get_extract_module()
        cb_extract = _register_extract()
        with patch.object(mod, "require_config", return_value=config):
            with patch.object(
                mod, "parse_jsonl_transcript", return_value="User: hello"
            ):
                with patch.object(mod, "run_extraction", return_value=_skipped_result):
                    result = cb_extract(transcript_path=str(transcript))

        assert "already extracted" in result.lower() or "Skipping" in result


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

        with patch.object(mod, "require_config", return_value=config):
            with patch.object(mod, "_extract_beats", return_value=[SAMPLE_BEAT]):
                with patch.object(mod, "autofile_beat", mock_autofile):
                    with patch.object(mod, "write_beat", mock_write):
                        result = cb_file(
                            content="Use connection pooling for all DB access."
                        )

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

        with patch.object(mod, "require_config", return_value=config):
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

        with patch.object(mod, "require_config", return_value=config):
            with patch.object(mod, "_extract_beats", return_value=[SAMPLE_BEAT]):
                with patch.object(mod, "autofile_beat", mock_autofile):
                    with patch.object(mod, "write_beat", mock_write):
                        result = cb_file(
                            content="Use connection pooling for all DB access."
                        )

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

        with patch.object(mod, "require_config", return_value=config):
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

        with patch.object(mod, "require_config", return_value=config):
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
        with patch.object(mod, "require_config", return_value=config):
            with patch.object(
                mod, "_extract_beats", side_effect=BackendError("timeout")
            ):
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
        with patch.object(mod, "require_config", return_value=config):
            with patch.object(mod, "_extract_beats", return_value=[]):
                result = cb_file(content="hmm")

        assert "No content worth filing" in result


# ===========================================================================
# cb_file — type parameter (UC2: type override after extraction)
# ===========================================================================


class TestCbFileTypeOverride:
    """type forces the beat type after extraction (UC2: single-beat capture)."""

    def test_type_applied_to_all_beats(self, tmp_path):
        """All extracted beats have their type overridden when type is given."""
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

        with patch.object(mod, "require_config", return_value=config):
            with patch.object(mod, "_extract_beats", return_value=[beat]):
                with patch.object(mod, "write_beat", side_effect=capture_write):
                    cb_file(content="some content", type="reference")

        assert len(captured_beats) == 1
        assert captured_beats[0]["type"] == "reference"

    def test_tags_merged_with_llm_tags(self, tmp_path):
        """Tags provided via the tags parameter are merged with LLM-generated tags."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault)

        beat = dict(SAMPLE_BEAT)  # tags: ["postgres", "performance"]
        fake_path = vault / "AI/Claude-Sessions/Use Connection Pooling.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_file_module()
        cb_file = _register_file()
        captured_beats = []

        def capture_write(b, *args, **kwargs):
            captured_beats.append(dict(b))
            return fake_path

        with patch.object(mod, "require_config", return_value=config):
            with patch.object(mod, "_extract_beats", return_value=[beat]):
                with patch.object(mod, "write_beat", side_effect=capture_write):
                    cb_file(content="some content", tags="python, async")

        assert len(captured_beats) == 1
        result_tags = captured_beats[0]["tags"]
        assert "postgres" in result_tags  # from LLM
        assert "performance" in result_tags  # from LLM
        assert "python" in result_tags  # from caller
        assert "async" in result_tags  # from caller


# ===========================================================================
# cb_file — document intake (UC3)
# ===========================================================================


class TestCbFileDocumentIntake:
    """cb_file with title provided: document intake mode (UC3)."""

    def test_with_title_skips_llm_extraction(self, tmp_path):
        """When title is provided, _extract_beats is never called."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault)

        fake_path = vault / "AI/Claude-Sessions/My Research Report.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_file_module()
        cb_file = _register_file()
        mock_extract = MagicMock(return_value=[SAMPLE_BEAT])
        mock_write = MagicMock(return_value=fake_path)

        with patch.object(mod, "require_config", return_value=config):
            with patch.object(mod, "_extract_beats", mock_extract):
                with patch.object(mod, "write_beat", mock_write):
                    cb_file(
                        content="This is my research report body.",
                        title="My Research Report",
                    )

        mock_extract.assert_not_called()
        mock_write.assert_called_once()

    def test_with_title_and_type_uses_provided_type(self, tmp_path):
        """Document intake uses the provided type (not defaulting to reference)."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault)

        fake_path = vault / "AI/Claude-Sessions/Meeting Notes.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_file_module()
        cb_file = _register_file()
        captured_beats = []

        def capture_write(b, *args, **kwargs):
            captured_beats.append(dict(b))
            return fake_path

        with patch.object(mod, "require_config", return_value=config):
            with patch.object(mod, "_extract_beats", MagicMock()):
                with patch.object(mod, "write_beat", side_effect=capture_write):
                    cb_file(
                        content="Discussed Q3 goals.",
                        title="Meeting Notes",
                        type="decision",
                    )

        assert len(captured_beats) == 1
        assert captured_beats[0]["type"] == "decision"

    def test_with_title_defaults_type_to_reference(self, tmp_path):
        """Document intake defaults type to 'reference' when type is not provided."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault)

        fake_path = vault / "AI/Claude-Sessions/API Docs.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_file_module()
        cb_file = _register_file()
        captured_beats = []

        def capture_write(b, *args, **kwargs):
            captured_beats.append(dict(b))
            return fake_path

        with patch.object(mod, "require_config", return_value=config):
            with patch.object(mod, "_extract_beats", MagicMock()):
                with patch.object(mod, "write_beat", side_effect=capture_write):
                    cb_file(
                        content="Detailed API reference for the authentication module.",
                        title="API Docs",
                    )

        assert len(captured_beats) == 1
        assert captured_beats[0]["type"] == "reference"

    def test_with_title_and_tags_applies_tags(self, tmp_path):
        """Document intake applies provided tags directly."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault)

        fake_path = vault / "AI/Claude-Sessions/Rust Notes.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_file_module()
        cb_file = _register_file()
        captured_beats = []

        def capture_write(b, *args, **kwargs):
            captured_beats.append(dict(b))
            return fake_path

        with patch.object(mod, "require_config", return_value=config):
            with patch.object(mod, "_extract_beats", MagicMock()):
                with patch.object(mod, "write_beat", side_effect=capture_write):
                    cb_file(
                        content="Notes on Rust ownership model.",
                        title="Rust Notes",
                        tags="rust, ownership, memory",
                    )

        assert len(captured_beats) == 1
        assert "rust" in captured_beats[0]["tags"]
        assert "ownership" in captured_beats[0]["tags"]
        assert "memory" in captured_beats[0]["tags"]

    def test_with_title_and_durability_working_memory(self, tmp_path):
        """Document intake with durability='working-memory' sets the beat durability."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault)

        fake_path = vault / "AI/Claude-Sessions/Temp Notes.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_file_module()
        cb_file = _register_file()
        captured_beats = []

        def capture_write(b, *args, **kwargs):
            captured_beats.append(dict(b))
            return fake_path

        with patch.object(mod, "require_config", return_value=config):
            with patch.object(mod, "_extract_beats", MagicMock()):
                with patch.object(mod, "write_beat", side_effect=capture_write):
                    cb_file(
                        content="Temporary workaround notes.",
                        title="Temp Notes",
                        durability="working-memory",
                    )

        assert len(captured_beats) == 1
        assert captured_beats[0]["durability"] == "working-memory"

    def test_with_title_defaults_durability_to_durable(self, tmp_path):
        """Document intake defaults durability to 'durable'."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault)

        fake_path = vault / "AI/Claude-Sessions/Perm Doc.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_file_module()
        cb_file = _register_file()
        captured_beats = []

        def capture_write(b, *args, **kwargs):
            captured_beats.append(dict(b))
            return fake_path

        with patch.object(mod, "require_config", return_value=config):
            with patch.object(mod, "_extract_beats", MagicMock()):
                with patch.object(mod, "write_beat", side_effect=capture_write):
                    cb_file(
                        content="A permanent document.",
                        title="Perm Doc",
                    )

        assert len(captured_beats) == 1
        assert captured_beats[0]["durability"] == "durable"

    def test_with_title_and_folder_uses_write_beat(self, tmp_path):
        """Document intake with explicit folder uses write_beat (not autofile_beat)."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault, autofile=True)

        fake_path = vault / "Work/Projects/Project Report.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_file_module()
        cb_file = _register_file()
        mock_autofile = MagicMock(return_value=None)
        mock_write = MagicMock(return_value=fake_path)

        with patch.object(mod, "require_config", return_value=config):
            with patch.object(mod, "_extract_beats", MagicMock()):
                with patch.object(mod, "autofile_beat", mock_autofile):
                    with patch.object(mod, "write_beat", mock_write):
                        cb_file(
                            content="Project report body.",
                            title="Project Report",
                            folder="Work/Projects",
                        )

        mock_autofile.assert_not_called()
        mock_write.assert_called_once()

    def test_with_title_uses_document_intake_source(self, tmp_path):
        """Document intake passes source='document-intake' to write_beat."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault)

        fake_path = vault / "AI/Claude-Sessions/Some Doc.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_file_module()
        cb_file = _register_file()
        captured_kwargs = []

        def capture_write(b, *args, **kwargs):
            captured_kwargs.append(kwargs)
            return fake_path

        with patch.object(mod, "require_config", return_value=config):
            with patch.object(mod, "_extract_beats", MagicMock()):
                with patch.object(mod, "write_beat", side_effect=capture_write):
                    cb_file(
                        content="Some document content.",
                        title="Some Doc",
                    )

        assert len(captured_kwargs) == 1
        assert captured_kwargs[0].get("source") == "document-intake"

    def test_with_title_autofile_enabled_calls_autofile_beat(self, tmp_path):
        """Document intake with autofile=True and no folder calls autofile_beat."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault, autofile=True)

        fake_path = vault / "AI/Claude-Sessions/Auto Filed Doc.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_file_module()
        cb_file = _register_file()
        mock_autofile = MagicMock(return_value=fake_path)
        mock_write = MagicMock(return_value=None)

        with patch.object(mod, "require_config", return_value=config):
            with patch.object(mod, "_extract_beats", MagicMock()):
                with patch.object(mod, "autofile_beat", mock_autofile):
                    with patch.object(mod, "write_beat", mock_write):
                        cb_file(
                            content="A document for autofile.",
                            title="Auto Filed Doc",
                        )

        mock_autofile.assert_called_once()
        mock_write.assert_not_called()


# ===========================================================================
# cb_file — document intake + autofile integration (no mocks on autofile/write_beat)
# ===========================================================================


class TestCbFileDocumentIntakeIntegration:
    """Integration test: cb_file → autofile_beat → write_beat with real vault I/O.

    Only call_model is mocked (to control the autofile LLM response).
    autofile_beat and write_beat run with real logic against a temp vault.
    """

    def test_document_intake_autofile_preserves_content_end_to_end(self, tmp_path):
        """Full round-trip: cb_file(title=...) with autofile enabled writes the
        original content to the vault, not LLM-rewritten content."""
        vault = tmp_path / "vault"
        vault.mkdir()
        inbox = vault / "AI" / "Claude-Sessions"
        inbox.mkdir(parents=True)
        # Create the target folder so write_beat can write there
        target_folder = vault / "Knowledge" / "Python"
        target_folder.mkdir(parents=True)

        config = _base_config(vault, autofile=True)
        original_body = "## Vision Analysis\n\nThis is the original document content that must be preserved verbatim."

        # LLM returns a create decision with rewritten content
        llm_decision = json.dumps(
            {
                "action": "create",
                "path": "Knowledge/Python/Vision Analysis.md",
                "content": "---\ntype: reference\ntitle: Rewritten\n---\n\nRewritten by LLM.",
                "confidence": 0.9,
            }
        )

        mod = _get_file_module()
        cb_file = _register_file()

        with patch.object(mod, "require_config", return_value=config):
            with patch(
                "cyberbrain.extractors.autofile.call_model", return_value=llm_decision
            ):
                with patch(
                    "cyberbrain.extractors.autofile.search_vault", return_value=[]
                ):
                    result = cb_file(
                        content=original_body,
                        title="Vision Analysis",
                        type="reference",
                        tags="python, vision",
                    )

        # The result should confirm the note was filed
        assert "Vision Analysis" in result

        # Find the written file — should be in Knowledge/Python/ (LLM-chosen path)
        written_files = list(target_folder.glob("*.md"))
        assert len(written_files) == 1, f"Expected 1 file in {target_folder}, found {len(written_files)}"

        content_on_disk = written_files[0].read_text(encoding="utf-8")
        # Original body must be present
        assert original_body in content_on_disk
        # LLM-rewritten content must NOT be present
        assert "Rewritten by LLM" not in content_on_disk
        assert "Rewritten" not in content_on_disk.split("---", 2)[-1] if content_on_disk.startswith("---") else True


# ===========================================================================
# cb_file — entity type pass-through for document intake (WI-111)
# ===========================================================================


class TestCbFileIntakeEntityType:
    """cb_file document-intake: entity types pass through; beat types are remapped."""

    def test_cb_file_intake_preserves_entity_type(self, tmp_path):
        """cb_file(title='X', type='project') writes a beat with type='project'."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = _base_config(vault)

        fake_path = vault / "AI/Claude-Sessions/Test Note.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_file_module()
        cb_file = _register_file()
        captured_beats = []

        def capture_write(b, *args, **kwargs):
            captured_beats.append(dict(b))
            return fake_path

        with patch.object(mod, "require_config", return_value=config):
            with patch.object(mod, "_extract_beats", MagicMock()):
                with patch.object(mod, "write_beat", side_effect=capture_write):
                    cb_file(
                        content="A project-scoped document.",
                        title="Test Note",
                        type="project",
                    )

        assert len(captured_beats) == 1
        assert captured_beats[0]["type"] == "project"

    def test_cb_file_intake_remaps_beat_type(self, tmp_path):
        """cb_file(title='X', type='reference') produces a note with entity type 'resource'."""
        from unittest.mock import patch as std_patch

        vault = tmp_path / "vault"
        vault.mkdir()
        inbox = vault / "AI/Claude-Sessions"
        inbox.mkdir(parents=True, exist_ok=True)
        config = _base_config(vault)

        mod = _get_file_module()
        cb_file = _register_file()

        # Do not mock write_beat — let the real implementation run so we can
        # verify that 'reference' is remapped to entity type 'resource' on disk.
        # update_search_index is imported lazily inside write_beat; patch it at
        # its source module so the lazy import picks up the mock.
        with patch.object(mod, "require_config", return_value=config):
            with patch.object(mod, "_extract_beats", MagicMock()):
                with std_patch(
                    "cyberbrain.extractors.search_index.update_search_index"
                ):
                    cb_file(
                        content="A reference document.",
                        title="Remap Test",
                        type="reference",
                        # cwd=None -> effective_cwd = Path.home(), bypasses pytest guard
                    )

        # Find the written file
        written_files = list(inbox.rglob("*.md"))
        assert len(written_files) == 1, f"Expected 1 written file, got: {written_files}"
        content = written_files[0].read_text(encoding="utf-8")
        assert 'type: "resource"' in content


# ===========================================================================
# cb_extract — transcript truncation and vault CLAUDE.md reading
# ===========================================================================


class TestCbExtractAdditional:
    """Additional coverage for less common paths."""

    def test_long_transcript_is_truncated(self, tmp_path, monkeypatch):
        """Transcripts over 150k characters are truncated before run_extraction is called."""
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

        _fake_result = {
            "skipped": False,
            "beats_count": 0,
            "beats_written": 0,
            "written_paths": [],
            "beat_records": [],
            "run_errors": [],
        }

        def capture_run(text, *args, **kwargs):
            captured_text.append(text)
            return _fake_result

        with patch.object(mod, "require_config", return_value=config):
            with patch.object(mod, "run_extraction", side_effect=capture_run):
                cb_extract(transcript_path=str(transcript))

        assert len(captured_text) == 1
        assert captured_text[0].startswith("...[earlier content truncated]...")
        assert len(captured_text[0]) < 160_000

    def test_run_errors_appear_in_summary(self, tmp_path, monkeypatch):
        """Per-beat write errors from run_extraction are included in the summary."""
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

        _fake_result = {
            "skipped": False,
            "beats_count": 1,
            "beats_written": 0,
            "written_paths": [],
            "beat_records": [],
            "run_errors": ["write error on 'Use Connection Pooling': disk full"],
        }

        mod = _get_extract_module()
        cb_extract = _register_extract()

        with patch.object(mod, "require_config", return_value=config):
            with patch.object(
                mod, "parse_jsonl_transcript", return_value="User: hello"
            ):
                with patch.object(mod, "run_extraction", return_value=_fake_result):
                    result = cb_extract(transcript_path=str(transcript))

        # Error is recorded in the summary, not raised
        assert "disk full" in result or "write error" in result.lower()


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
        claude_md.write_text(
            "# Vault Guide\n\nUse types: decision, reference.", encoding="utf-8"
        )

        config = _base_config(vault, autofile=True)

        fake_path = vault / "AI/Claude-Sessions/Use Connection Pooling.md"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.touch()

        mod = _get_file_module()
        cb_file = _register_file()
        mock_autofile = MagicMock(return_value=fake_path)

        with patch.object(mod, "require_config", return_value=config):
            with patch.object(mod, "_extract_beats", return_value=[SAMPLE_BEAT]):
                with patch.object(mod, "autofile_beat", mock_autofile):
                    with patch.object(mod, "write_beat", MagicMock(return_value=None)):
                        cb_file(content="Use connection pooling for all DB access.")

        mock_autofile.assert_called_once()
        call_kwargs = mock_autofile.call_args[1]
        assert "vault_context" in call_kwargs
        assert "Vault Guide" in call_kwargs["vault_context"]


class TestCbFileAutofileAsk:
    """cb_file returns clarification prompt when autofile signals low-confidence ask."""

    def test_autofile_ask_returns_clarification_message(self, tmp_path):
        """When autofile_beat returns None with _autofile_ask set, cb_file returns clarification."""
        vault = tmp_path / "vault"
        vault.mkdir()
        config = {
            "vault_path": str(vault),
            "inbox": "AI/Claude-Sessions",
            "backend": "claude-code",
            "autofile": True,
            "daily_journal": False,
            "uncertain_filing_behavior": "ask",
            "uncertain_filing_threshold": 0.5,
        }

        def mock_autofile_with_ask(beat, *args, **kwargs):
            # Simulate low-confidence ask: set sentinel and return None
            beat["_autofile_ask"] = {
                "confidence": 0.3,
                "rationale": "Ambiguous topic",
                "decision": {"path": "Projects/maybe-here"},
            }
            return None

        mod = _get_file_module()
        cb_file = _register_file()

        with patch.object(mod, "require_config", return_value=config):
            with patch.object(mod, "_extract_beats", return_value=[SAMPLE_BEAT.copy()]):
                with patch.object(
                    mod, "autofile_beat", side_effect=mock_autofile_with_ask
                ):
                    result = cb_file(content="Some content to file.")

        assert "Confidence in routing is low" in result
        assert "0.30" in result
        assert "Projects/maybe-here" in result
        assert "Please confirm" in result
