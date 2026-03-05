"""
test_extract_beats.py — unit tests for extractors/extract_beats.py

Tests describe the system's behaviour, not its implementation. Each test
documents one verifiable property of the extraction engine.

LLM calls are always mocked — no real API calls are made in this suite.
Vault I/O uses tempfile.TemporaryDirectory (via the temp_vault fixture).
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

import extractors.extract_beats as eb
from tests.conftest import make_beat


# ===========================================================================
# Config loading
# ===========================================================================

class TestLoadGlobalConfig:
    """load_global_config() reads, validates, and resolves the global config."""

    def test_loads_valid_config(self, temp_vault, temp_home, monkeypatch):
        """A config with all required fields loads successfully."""
        config_dir = temp_home / ".claude"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_data = {
            "vault_path": str(temp_vault),
            "inbox": "AI/Claude-Sessions",
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
        }
        (config_dir / "cyberbrain.json").write_text(json.dumps(config_data))

        monkeypatch.setattr(eb, "GLOBAL_CONFIG_PATH", config_dir / "cyberbrain.json")

        config = eb.load_global_config()

        assert config["inbox"] == "AI/Claude-Sessions"
        assert Path(config["vault_path"]).is_absolute()

    def test_exits_cleanly_when_config_missing(self, temp_home, monkeypatch):
        """Missing config file produces sys.exit(0), not an exception."""
        missing_path = temp_home / ".claude" / "cyberbrain.json"
        monkeypatch.setattr(eb, "GLOBAL_CONFIG_PATH", missing_path)

        with pytest.raises(SystemExit) as exc_info:
            eb.load_global_config()
        assert exc_info.value.code == 0

    def test_exits_cleanly_when_required_fields_missing(self, temp_vault, temp_home, monkeypatch):
        """Config missing required fields produces sys.exit(0)."""
        config_dir = temp_home / ".claude"
        config_dir.mkdir(parents=True, exist_ok=True)
        # vault_path present but inbox missing
        (config_dir / "cyberbrain.json").write_text(
            json.dumps({"vault_path": str(temp_vault)})
        )
        monkeypatch.setattr(eb, "GLOBAL_CONFIG_PATH", config_dir / "cyberbrain.json")

        with pytest.raises(SystemExit) as exc_info:
            eb.load_global_config()
        assert exc_info.value.code == 0

    def test_vault_path_resolved_to_absolute(self, temp_vault, temp_home, monkeypatch):
        """vault_path is always returned as an absolute path string."""
        config_dir = temp_home / ".claude"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_data = {
            "vault_path": str(temp_vault),
            "inbox": "AI/Claude-Sessions",
        }
        (config_dir / "cyberbrain.json").write_text(json.dumps(config_data))
        monkeypatch.setattr(eb, "GLOBAL_CONFIG_PATH", config_dir / "cyberbrain.json")

        config = eb.load_global_config()
        assert os.path.isabs(config["vault_path"])

    def test_rejects_vault_path_equal_to_home_directory(self, temp_home, monkeypatch):
        """vault_path set to the home directory produces sys.exit(0) with a clear error."""
        config_dir = temp_home / ".claude"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_data = {
            "vault_path": str(temp_home),
            "inbox": "AI/Claude-Sessions",
        }
        (config_dir / "cyberbrain.json").write_text(json.dumps(config_data))
        monkeypatch.setattr(eb, "GLOBAL_CONFIG_PATH", config_dir / "cyberbrain.json")
        # temp_home fixture already sets HOME env var so Path.home() returns temp_home

        with pytest.raises(SystemExit) as exc_info:
            eb.load_global_config()
        assert exc_info.value.code == 0

    def test_rejects_vault_path_equal_to_filesystem_root(self, temp_home, monkeypatch):
        """vault_path set to '/' produces sys.exit(0) with a clear error."""
        config_dir = temp_home / ".claude"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_data = {
            "vault_path": "/",
            "inbox": "AI/Claude-Sessions",
        }
        (config_dir / "cyberbrain.json").write_text(json.dumps(config_data))
        monkeypatch.setattr(eb, "GLOBAL_CONFIG_PATH", config_dir / "cyberbrain.json")

        with pytest.raises(SystemExit) as exc_info:
            eb.load_global_config()
        assert exc_info.value.code == 0


class TestFindProjectConfig:
    """find_project_config() walks up the directory tree to find cyberbrain.local.json."""

    def test_finds_config_in_current_directory(self, tmp_path):
        """Project config in .claude/ of the current directory is found."""
        project_dir = tmp_path / "my-project"
        config_dir = project_dir / ".claude"
        config_dir.mkdir(parents=True)
        config_data = {"project_name": "my-project", "vault_folder": "Projects/my-project"}
        (config_dir / "cyberbrain.local.json").write_text(json.dumps(config_data))

        result = eb.find_project_config(str(project_dir))
        assert result["project_name"] == "my-project"

    def test_finds_config_in_parent_directory(self, tmp_path):
        """Project config in a parent directory's .claude/ is found by walking up."""
        project_dir = tmp_path / "my-project"
        sub_dir = project_dir / "src" / "lib"
        config_dir = project_dir / ".claude"
        sub_dir.mkdir(parents=True)
        config_dir.mkdir(parents=True)
        config_data = {"project_name": "my-project", "vault_folder": "Projects/my-project"}
        (config_dir / "cyberbrain.local.json").write_text(json.dumps(config_data))

        result = eb.find_project_config(str(sub_dir))
        assert result["project_name"] == "my-project"

    def test_returns_empty_dict_when_not_found(self, tmp_path):
        """Returns empty dict when no project config exists in the directory tree."""
        project_dir = tmp_path / "no-config-project"
        project_dir.mkdir()

        result = eb.find_project_config(str(project_dir))
        assert result == {}


# ===========================================================================
# Transcript parsing
# ===========================================================================

class TestParseJsonlTranscript:
    """parse_jsonl_transcript() extracts conversation text from JSONL transcripts."""

    def test_extracts_user_and_assistant_turns(self, sample_transcript_path):
        """Text turns from user and assistant entries are extracted."""
        result = eb.parse_jsonl_transcript(sample_transcript_path)
        assert "[USER]" in result
        assert "[ASSISTANT]" in result

    def test_skips_tool_use_blocks(self, sample_transcript_path):
        """tool_use blocks within assistant content are not included in the output."""
        result = eb.parse_jsonl_transcript(sample_transcript_path)
        # The sample transcript has a tool_use block with name "Read" — it should not appear
        assert "tool_use" not in result

    def test_skips_thinking_blocks(self, sample_transcript_path):
        """thinking blocks are not included in the output."""
        result = eb.parse_jsonl_transcript(sample_transcript_path)
        assert "The user is happy with the claude-code backend" not in result

    def test_skips_tool_result_blocks(self, sample_transcript_path):
        """tool_result blocks are not included in the output."""
        result = eb.parse_jsonl_transcript(sample_transcript_path)
        # The sample has a tool_result with "The command output some binary data"
        assert "tool_result" not in result

    def test_handles_empty_file(self, tmp_path):
        """An empty JSONL file produces an empty string."""
        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_text("")
        result = eb.parse_jsonl_transcript(str(empty_file))
        assert result.strip() == ""

    def test_ignores_malformed_json_lines(self, tmp_path):
        """Lines that are not valid JSON are skipped without raising."""
        jsonl = tmp_path / "partial.jsonl"
        jsonl.write_text(
            'not valid json\n'
            '{"type": "user", "message": {"role": "user", "content": "hello"}}\n'
        )
        result = eb.parse_jsonl_transcript(str(jsonl))
        assert "hello" in result



# ===========================================================================
# Beat writing
# ===========================================================================

class TestWriteBeat:
    """write_beat() creates valid vault notes with correct routing and frontmatter."""

    def test_routes_project_scoped_beat_to_project_folder(self, global_config, temp_vault, fixed_now):
        """A beat with scope=project and a vault_folder config goes to the project folder."""
        config = dict(global_config)
        config["vault_folder"] = "Projects/my-project"
        (temp_vault / "Projects" / "my-project").mkdir(parents=True)

        beat = make_beat(scope="project")
        path = eb.write_beat(beat, config, "sess001", "/cwd", fixed_now)

        assert "Projects/my-project" in str(path)

    def test_routes_general_beat_to_inbox(self, global_config, temp_vault, fixed_now):
        """A beat with scope=general goes to the inbox folder."""
        beat = make_beat(scope="general")
        path = eb.write_beat(beat, global_config, "sess001", "/cwd", fixed_now)

        assert "Claude-Sessions" in str(path)

    def test_returns_none_when_inbox_not_configured(self, temp_vault, temp_home, monkeypatch, fixed_now, capsys):
        """When inbox is not configured, write_beat returns None and prints a warning."""
        config_dir = temp_home / ".claude"
        config_dir.mkdir(parents=True, exist_ok=True)
        config = {
            "vault_path": str(temp_vault),
            "inbox": "",
        }
        (config_dir / "cyberbrain.json").write_text(json.dumps(config))
        monkeypatch.setattr(eb, "GLOBAL_CONFIG_PATH", config_dir / "cyberbrain.json")

        beat = make_beat(scope="general")
        path = eb.write_beat(beat, config, "sess001", "/cwd", fixed_now)

        assert path is None
        assert "inbox" in capsys.readouterr().err

    def test_produces_valid_yaml_frontmatter(self, global_config, temp_vault, fixed_now):
        """The written file has valid YAML frontmatter with the expected fields."""
        beat = make_beat(title="Auth Decision", beat_type="decision", tags=["auth", "backend"])
        path = eb.write_beat(beat, global_config, "sess001", "/cwd", fixed_now)

        content = path.read_text(encoding="utf-8")
        assert content.startswith("---")
        assert "type: decision" in content
        assert "session_id: sess001" in content
        assert '"auth"' in content  # tags are JSON-serialized
        assert '"backend"' in content

    def test_invalid_beat_type_falls_back_to_reference(self, global_config, temp_vault, fixed_now):
        """A beat with an unrecognized type is filed as 'reference'."""
        beat = make_beat(beat_type="totally-invalid-type")
        path = eb.write_beat(beat, global_config, "sess001", "/cwd", fixed_now)

        content = path.read_text(encoding="utf-8")
        assert "type: reference" in content

    def test_handles_filename_collision_with_counter(self, global_config, temp_vault, fixed_now):
        """When the target filename already exists, a numeric prefix avoids collision."""
        beat = make_beat(title="Collision Test")
        path1 = eb.write_beat(beat, global_config, "sess001", "/cwd", fixed_now)
        path2 = eb.write_beat(beat, global_config, "sess002", "/cwd", fixed_now)

        assert path1 != path2
        assert path1.exists()
        assert path2.exists()

    def test_all_valid_types_accepted(self, global_config, temp_vault, fixed_now):
        """All four valid types are accepted without fallback to 'reference'."""
        for beat_type in ("decision", "insight", "problem", "reference"):
            beat = make_beat(title=f"Beat {beat_type}", beat_type=beat_type)
            path = eb.write_beat(beat, global_config, "sess001", "/cwd", fixed_now)
            content = path.read_text(encoding="utf-8")
            assert f"type: {beat_type}" in content


# ===========================================================================
# Autofile
# ===========================================================================

class TestAutofileBeat:
    """autofile_beat() uses LLM judgment to route beats into the vault."""

    def test_rejects_path_traversal_in_create_response(self, global_config, temp_vault, fixed_now):
        """A 'create' decision with a path traversal string is rejected and falls back to inbox."""
        malicious_response = json.dumps({
            "action": "create",
            "path": "../../etc/passwd",
            "content": "malicious content",
        })
        with patch.object(eb, "call_model", return_value=malicious_response):
            with patch.object(eb, "search_vault", return_value=[]):
                path = eb.autofile_beat(
                    make_beat(), global_config, "sess001", "/cwd", fixed_now,
                    vault_context="Use types: decision, insight, problem, reference."
                )
        # Should have fallen back to inbox write, not written to traversal path
        assert path is not None
        assert str(path).startswith(str(temp_vault))
        assert "etc" not in str(path)

    def test_rejects_path_traversal_in_extend_response(self, global_config, temp_vault, fixed_now):
        """An 'extend' decision with a path traversal target is rejected and falls back to inbox."""
        malicious_response = json.dumps({
            "action": "extend",
            "target_path": "../../../etc/hosts",
            "insertion": "## Injected\n\nmalicious",
        })
        with patch.object(eb, "call_model", return_value=malicious_response):
            with patch.object(eb, "search_vault", return_value=[]):
                path = eb.autofile_beat(
                    make_beat(), global_config, "sess001", "/cwd", fixed_now,
                    vault_context="Use types: decision, insight, problem, reference."
                )
        assert path is not None
        assert str(path).startswith(str(temp_vault))

    def test_falls_back_to_flat_write_on_backend_error(self, global_config, temp_vault, fixed_now):
        """When the LLM backend raises BackendError, the beat is written to the inbox instead."""
        with patch.object(eb, "call_model", side_effect=eb.BackendError("backend unavailable")):
            with patch.object(eb, "search_vault", return_value=[]):
                path = eb.autofile_beat(
                    make_beat(), global_config, "sess001", "/cwd", fixed_now,
                    vault_context="Use types: decision, insight, problem, reference."
                )
        assert path is not None
        assert path.exists()

    def test_create_action_writes_new_file(self, global_config, temp_vault, fixed_now):
        """A 'create' decision writes a new file at the specified vault-relative path."""
        note_content = "---\ntype: insight\n---\n\n## Test\n\nBody."
        create_response = json.dumps({
            "action": "create",
            "path": "AI/Claude-Sessions/Test Note.md",
            "content": note_content,
        })
        with patch.object(eb, "call_model", return_value=create_response):
            with patch.object(eb, "search_vault", return_value=[]):
                path = eb.autofile_beat(
                    make_beat(), global_config, "sess001", "/cwd", fixed_now,
                    vault_context="conventions"
                )
        assert path is not None
        assert path.exists()
        assert path.read_text(encoding="utf-8") == note_content

    def test_extend_action_appends_to_existing_file(self, global_config, temp_vault, fixed_now):
        """An 'extend' decision appends content to an existing vault note."""
        existing_note = temp_vault / "AI" / "Claude-Sessions" / "Existing Note.md"
        existing_note.write_text("---\ntype: insight\n---\n\n## Original\n\nOriginal body.")

        extend_response = json.dumps({
            "action": "extend",
            "target_path": "AI/Claude-Sessions/Existing Note.md",
            "insertion": "## New Section\n\nNew content.",
        })
        with patch.object(eb, "call_model", return_value=extend_response):
            with patch.object(eb, "search_vault", return_value=[]):
                path = eb.autofile_beat(
                    make_beat(), global_config, "sess001", "/cwd", fixed_now,
                    vault_context="conventions"
                )
        assert path == existing_note
        content = existing_note.read_text(encoding="utf-8")
        assert "New Section" in content
        assert "Original body." in content

    def test_collision_with_related_tags_resolves_as_extend(self, global_config, temp_vault, fixed_now):
        """When create target exists and has 2+ overlapping tags, treat as extend instead."""
        existing = temp_vault / "AI" / "Claude-Sessions" / "Collision Note.md"
        existing.write_text(
            '---\ntype: insight\ntags: ["python", "encoding", "subprocess"]\n---\n\n## Original\n\nBody.'
        )

        create_response = json.dumps({
            "action": "create",
            "path": "AI/Claude-Sessions/Collision Note.md",
            "content": "---\ntype: insight\n---\n\n## Duplicate\n\nNew content.",
        })
        beat = make_beat(tags=["python", "encoding", "unicode"])
        with patch.object(eb, "call_model", return_value=create_response):
            with patch.object(eb, "search_vault", return_value=[]):
                path = eb.autofile_beat(
                    beat, global_config, "sess001", "/cwd", fixed_now,
                    vault_context="conventions"
                )
        # Should have extended the existing file, not created a new one
        assert path == existing
        content = existing.read_text(encoding="utf-8")
        assert "New content." in content

    def test_collision_with_unrelated_tags_creates_specific_title(self, global_config, temp_vault, fixed_now):
        """When create target exists and tags don't overlap enough, use a more specific title."""
        existing = temp_vault / "AI" / "Claude-Sessions" / "Collision Note.md"
        existing.write_text(
            '---\ntype: insight\ntags: ["unrelated", "topic"]\n---\n\n## Original\n\nBody.'
        )

        create_response = json.dumps({
            "action": "create",
            "path": "AI/Claude-Sessions/Collision Note.md",
            "content": "---\ntype: insight\n---\n\n## Different\n\nContent.",
        })
        beat = make_beat(tags=["python", "encoding"])
        with patch.object(eb, "call_model", return_value=create_response):
            with patch.object(eb, "search_vault", return_value=[]):
                path = eb.autofile_beat(
                    beat, global_config, "sess001", "/cwd", fixed_now,
                    vault_context="conventions"
                )
        # Should have created a file with a more specific name
        assert path != existing
        assert path.exists()


# ===========================================================================
# Daily journal
# ===========================================================================

class TestWriteJournalEntry:
    """write_journal_entry() maintains a daily log of captured notes."""

    def test_creates_new_journal_file_with_header(self, global_config, temp_vault, fixed_now):
        """A new daily journal file is created with YAML frontmatter and a session block."""
        (temp_vault / "AI" / "Journal").mkdir(parents=True, exist_ok=True)
        config = dict(global_config)
        config["journal_folder"] = "AI/Journal"

        written = [temp_vault / "AI" / "Claude-Sessions" / "Some Note.md"]
        written[0].write_text("note content")

        eb.write_journal_entry(written, config, "abc12345", "my-project", fixed_now)

        journal_path = temp_vault / "AI" / "Journal" / "2026-03-01.md"
        assert journal_path.exists()
        content = journal_path.read_text(encoding="utf-8")
        assert "type: journal" in content
        assert "abc12345" in content
        assert "my-project" in content

    def test_appends_to_existing_journal_file(self, global_config, temp_vault, fixed_now):
        """Session blocks are appended to an existing journal file."""
        journal_dir = temp_vault / "AI" / "Journal"
        journal_dir.mkdir(parents=True, exist_ok=True)
        journal_path = journal_dir / "2026-03-01.md"
        journal_path.write_text("---\ntype: journal\ndate: 2026-03-01\n---\n\n# 2026-03-01\n")

        config = dict(global_config)
        config["journal_folder"] = "AI/Journal"

        written = [temp_vault / "AI" / "Claude-Sessions" / "Note.md"]
        written[0].write_text("content")

        eb.write_journal_entry(written, config, "xyz99999", "project", fixed_now)

        content = journal_path.read_text(encoding="utf-8")
        assert "xyz99999" in content
        assert "project" in content

    def test_session_block_includes_timestamp(self, global_config, temp_vault, fixed_now):
        """The session block header includes a YYYY-MM-DD HH:MM UTC timestamp."""
        (temp_vault / "AI" / "Journal").mkdir(parents=True, exist_ok=True)
        config = dict(global_config)
        config["journal_folder"] = "AI/Journal"

        written = [temp_vault / "AI" / "Claude-Sessions" / "ANote.md"]
        written[0].write_text("content")

        eb.write_journal_entry(written, config, "abc12345", "proj", fixed_now)

        journal_path = temp_vault / "AI" / "Journal" / "2026-03-01.md"
        content = journal_path.read_text(encoding="utf-8")
        # Timestamp: 2026-03-01 14:32 UTC
        assert "2026-03-01 14:32 UTC" in content

    def test_wikilinks_use_stem_only(self, global_config, temp_vault, fixed_now):
        """Journal wikilinks use just the note title stem, not the full path."""
        (temp_vault / "AI" / "Journal").mkdir(parents=True, exist_ok=True)
        config = dict(global_config)
        config["journal_folder"] = "AI/Journal"

        note = temp_vault / "AI" / "Claude-Sessions" / "My Important Note.md"
        note.write_text("content")

        eb.write_journal_entry([note], config, "abc12345", "proj", fixed_now)

        journal_path = temp_vault / "AI" / "Journal" / "2026-03-01.md"
        content = journal_path.read_text(encoding="utf-8")
        assert "[[My Important Note]]" in content
        # Should not include the full vault-relative path
        assert "AI/Claude-Sessions" not in content


# ===========================================================================
# Deduplication log
# ===========================================================================

class TestDeduplicationLog:
    """Deduplication log prevents re-extracting sessions already processed."""

    def test_new_session_is_not_duplicate(self, tmp_path, monkeypatch):
        """A session ID not in the log is reported as not-yet-extracted."""
        log_path = tmp_path / "logs" / "cb-extract.log"
        monkeypatch.setattr(eb, "EXTRACT_LOG_PATH", log_path)

        assert eb.is_session_already_extracted("brand-new-session") is False

    def test_session_in_log_is_detected_as_duplicate(self, tmp_path, monkeypatch):
        """A session ID present in the log is reported as already extracted."""
        log_path = tmp_path / "logs" / "cb-extract.log"
        log_path.parent.mkdir(parents=True)
        log_path.write_text("2026-03-01T14:32:00\tabc12345\t3\n")
        monkeypatch.setattr(eb, "EXTRACT_LOG_PATH", log_path)

        assert eb.is_session_already_extracted("abc12345") is True

    def test_different_session_id_not_detected_as_duplicate(self, tmp_path, monkeypatch):
        """A different session ID in the same log file is not a duplicate."""
        log_path = tmp_path / "logs" / "cb-extract.log"
        log_path.parent.mkdir(parents=True)
        log_path.write_text("2026-03-01T14:32:00\tabc12345\t3\n")
        monkeypatch.setattr(eb, "EXTRACT_LOG_PATH", log_path)

        assert eb.is_session_already_extracted("xyz99999") is False

    def test_write_log_entry_creates_file_and_directory(self, tmp_path, monkeypatch):
        """write_extract_log_entry creates the log file and parent directory if needed."""
        log_path = tmp_path / "logs" / "cb-extract.log"
        monkeypatch.setattr(eb, "EXTRACT_LOG_PATH", log_path)

        eb.write_extract_log_entry("newsession", 5)

        assert log_path.exists()
        content = log_path.read_text()
        assert "newsession" in content
        assert "\t5\n" in content

    def test_write_log_entry_format_is_tab_separated(self, tmp_path, monkeypatch):
        """Log entries are tab-separated: <ISO-timestamp>\t<session-id>\t<beat-count>."""
        log_path = tmp_path / "logs" / "cb-extract.log"
        log_path.parent.mkdir(parents=True)
        monkeypatch.setattr(eb, "EXTRACT_LOG_PATH", log_path)

        eb.write_extract_log_entry("sess-abc", 7)

        line = log_path.read_text().strip()
        parts = line.split("\t")
        assert len(parts) == 3
        assert parts[1] == "sess-abc"
        assert parts[2] == "7"

    def test_corrupt_log_warns_and_proceeds(self, tmp_path, monkeypatch, capsys):
        """A corrupt/unreadable log file warns to stderr and returns False (proceed)."""
        log_path = tmp_path / "logs" / "cb-extract.log"
        log_path.parent.mkdir(parents=True)
        log_path.write_text("corrupt\x00data\xFF")
        # Make the file unreadable
        log_path.chmod(0o000)
        monkeypatch.setattr(eb, "EXTRACT_LOG_PATH", log_path)

        try:
            result = eb.is_session_already_extracted("any-session")
            # Should return False (proceed) not raise
            assert result is False
        finally:
            log_path.chmod(0o644)  # restore for cleanup


# ===========================================================================
# Security: vault path validation
# ===========================================================================

class TestVaultPathValidation:
    """Vault path validation rejects dangerous configurations."""

    def test_rejects_nonexistent_vault_path(self, temp_home, monkeypatch):
        """A vault_path that does not exist on disk produces sys.exit(0)."""
        config_dir = temp_home / ".claude"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "cyberbrain.json").write_text(json.dumps({
            "vault_path": "/nonexistent/path/to/vault",
            "inbox": "AI/Claude-Sessions",
        }))
        monkeypatch.setattr(eb, "GLOBAL_CONFIG_PATH", config_dir / "cyberbrain.json")

        with pytest.raises(SystemExit) as exc_info:
            eb.load_global_config()
        assert exc_info.value.code == 0


# ===========================================================================
# Security: _is_within_vault
# ===========================================================================

class TestIsWithinVault:
    """_is_within_vault() is the path traversal guard for all vault writes."""

    def test_path_inside_vault_is_allowed(self, temp_vault):
        """A path inside the vault returns True."""
        target = temp_vault / "AI" / "Some Note.md"
        assert eb._is_within_vault(temp_vault, target) is True

    def test_path_outside_vault_via_traversal_is_rejected(self, temp_vault):
        """A path that resolves outside the vault via ../ returns False."""
        traversal = temp_vault / ".." / "etc" / "passwd"
        assert eb._is_within_vault(temp_vault, traversal) is False

    def test_absolute_path_outside_vault_is_rejected(self, temp_vault):
        """An absolute path not under vault_path returns False."""
        outside = Path("/etc/passwd")
        assert eb._is_within_vault(temp_vault, outside) is False


# ===========================================================================
# Vault CLAUDE.md reading
# ===========================================================================

class TestReadVaultClaudeMd:
    """read_vault_claude_md() reads the vault's CLAUDE.md for type vocabulary context."""

    def test_returns_text_when_file_exists(self, temp_vault):
        """Returns the full text of CLAUDE.md when it exists."""
        claude_md = temp_vault / "CLAUDE.md"
        claude_md.write_text("# Vault CLAUDE.md\n\nTypes: decision, insight.")
        result = eb.read_vault_claude_md(str(temp_vault))
        assert result == "# Vault CLAUDE.md\n\nTypes: decision, insight."

    def test_returns_none_when_file_absent(self, temp_vault):
        """Returns None when no CLAUDE.md exists in the vault."""
        result = eb.read_vault_claude_md(str(temp_vault))
        assert result is None


# ===========================================================================
# make_filename
# ===========================================================================

class TestMakeFilename:
    """make_filename() converts titles to clean human-readable filenames."""

    def test_strips_hash_bracket_caret_chars(self):
        """Characters # [ ] ^ are stripped from filenames."""
        assert "C" in eb.make_filename("C#")
        assert "#" not in eb.make_filename("C#")
        assert "foo" in eb.make_filename("[foo]")
        assert "[" not in eb.make_filename("[foo]")
        assert "]" not in eb.make_filename("[foo]")
        assert "blockref" in eb.make_filename("block^ref")
        assert "^" not in eb.make_filename("block^ref")

    def test_collapses_whitespace(self):
        """Multiple consecutive spaces are collapsed to a single space."""
        result = eb.make_filename("Multiple   Spaces   Here")
        assert "  " not in result
        assert "Multiple Spaces Here" in result

    def test_truncates_at_80_chars_on_word_boundary(self):
        """Titles longer than 80 chars are truncated at the last word boundary ≤80."""
        long_title = "A " * 45  # 90 chars
        result = eb.make_filename(long_title.strip())
        stem = result[:-3]  # strip .md
        assert len(stem) <= 80

    def test_appends_md_extension(self):
        """Result always ends in .md"""
        assert eb.make_filename("Some Note").endswith(".md")

    def test_clean_title_unchanged(self):
        """A title with no special characters passes through unchanged (plus .md)."""
        assert eb.make_filename("Clean Title") == "Clean Title.md"


# ===========================================================================
# parse_valid_types_from_claude_md
# ===========================================================================

class TestParseValidTypesFromClaudeMd:
    """parse_valid_types_from_claude_md() extracts type vocabulary from vault CLAUDE.md."""

    def test_extracts_types_from_entity_types_h2_section(self):
        """## Entity Types section with ### decision extracts 'decision'."""
        md = "## Entity Types\n\n### decision\n\nA choice made between alternatives.\n"
        result = eb.parse_valid_types_from_claude_md(md)
        assert "decision" in result

    def test_extracts_backtick_types_from_list_items(self):
        """List items with backtick-quoted types are extracted."""
        md = "## Types\n\n- `insight` — a non-obvious understanding\n"
        result = eb.parse_valid_types_from_claude_md(md)
        assert "insight" in result

    def test_returns_defaults_when_no_types_section_found(self):
        """Arbitrary markdown without a types section → _DEFAULT_VALID_TYPES."""
        result = eb.parse_valid_types_from_claude_md("# Just a header\n\nSome content.\n")
        assert result == eb._DEFAULT_VALID_TYPES

    def test_returns_defaults_on_empty_string(self):
        """Empty string → _DEFAULT_VALID_TYPES."""
        result = eb.parse_valid_types_from_claude_md("")
        assert result == eb._DEFAULT_VALID_TYPES

    def test_multiple_types_all_extracted(self):
        """A section with multiple types extracts all of them."""
        md = "## Types\n\n- `decision` — choice\n- `insight` — understanding\n- `problem` — blocker\n"
        result = eb.parse_valid_types_from_claude_md(md)
        assert "decision" in result
        assert "insight" in result
        assert "problem" in result

    def test_exits_types_section_at_next_h2(self):
        """A second ## heading stops collection of types."""
        md = (
            "## Types\n\n"
            "- `decision` — choice\n\n"
            "## Other Section\n\n"
            "- `not_a_type` — not in types\n"
        )
        result = eb.parse_valid_types_from_claude_md(md)
        assert "decision" in result
        assert "not_a_type" not in result


# ===========================================================================
# get_valid_types
# ===========================================================================

class TestGetValidTypes:
    """get_valid_types() reads type vocabulary from vault CLAUDE.md."""

    def test_reads_from_vault_claude_md_when_present(self, temp_vault):
        """When vault has CLAUDE.md with custom types, those types are returned."""
        claude_md = temp_vault / "CLAUDE.md"
        claude_md.write_text(
            "## Types\n\n- `decision` — choice\n- `recipe` — cooking instructions\n",
            encoding="utf-8",
        )
        config = {"vault_path": str(temp_vault)}
        result = eb.get_valid_types(config)
        assert "recipe" in result

    def test_falls_back_to_defaults_when_no_claude_md(self, temp_vault):
        """No CLAUDE.md → _DEFAULT_VALID_TYPES."""
        config = {"vault_path": str(temp_vault)}
        result = eb.get_valid_types(config)
        assert result == eb._DEFAULT_VALID_TYPES

    def test_falls_back_to_defaults_when_claude_md_has_no_types_section(self, temp_vault):
        """CLAUDE.md exists but has no types section → defaults."""
        (temp_vault / "CLAUDE.md").write_text(
            "# Vault Instructions\n\nFile notes here.\n", encoding="utf-8"
        )
        config = {"vault_path": str(temp_vault)}
        result = eb.get_valid_types(config)
        assert result == eb._DEFAULT_VALID_TYPES


# ===========================================================================
# build_vault_titles_set
# ===========================================================================

class TestBuildVaultTitlesSet:
    """build_vault_titles_set() returns the set of note stems in the vault."""

    def test_returns_stems_of_all_md_files(self, vault_with_notes):
        """Vault with 3 .md files → set of 3 stems."""
        result = eb.build_vault_titles_set(str(vault_with_notes))
        assert len(result) == 3

    def test_excludes_extension(self, vault_with_notes):
        """Stems don't include the .md extension."""
        result = eb.build_vault_titles_set(str(vault_with_notes))
        assert "JWT Authentication" in result
        assert "JWT Authentication.md" not in result

    def test_returns_empty_set_on_oserror(self):
        """Nonexistent path → empty set."""
        result = eb.build_vault_titles_set("/nonexistent/path/that/does/not/exist")
        assert result == set()

    def test_nested_subdirectory_notes_included(self, temp_vault):
        """Notes in subfolders are included."""
        subdir = temp_vault / "Deep" / "Nested"
        subdir.mkdir(parents=True)
        (subdir / "Nested Note.md").write_text("content")
        result = eb.build_vault_titles_set(str(temp_vault))
        assert "Nested Note" in result


# ===========================================================================
# resolve_relations
# ===========================================================================

class TestResolveRelations:
    """resolve_relations() validates and normalises beat relation lists."""

    def test_valid_predicate_and_existing_target_passes(self):
        """A relation with valid predicate and known target is returned unchanged."""
        vault_titles = {"JWT Authentication"}
        relations = [{"type": "references", "target": "JWT Authentication"}]
        result = eb.resolve_relations(relations, vault_titles)
        assert len(result) == 1
        assert result[0]["type"] == "references"
        assert result[0]["target"] == "JWT Authentication"

    def test_unknown_predicate_normalized_to_related(self):
        """An unknown predicate is normalised to 'related'."""
        vault_titles = {"JWT Authentication"}
        relations = [{"type": "causes", "target": "JWT Authentication"}]
        result = eb.resolve_relations(relations, vault_titles)
        assert result[0]["type"] == "related"

    def test_unresolved_target_dropped(self):
        """A target not in vault_titles is dropped."""
        vault_titles = {"JWT Authentication"}
        relations = [{"type": "related", "target": "Nonexistent Note"}]
        result = eb.resolve_relations(relations, vault_titles)
        assert result == []

    def test_case_insensitive_target_matching(self):
        """Lowercase target matches vault title regardless of casing."""
        vault_titles = {"JWT Authentication"}
        relations = [{"type": "related", "target": "jwt authentication"}]
        result = eb.resolve_relations(relations, vault_titles)
        assert len(result) == 1
        assert result[0]["target"] == "JWT Authentication"

    def test_empty_input_returns_empty_list(self):
        """Empty list → empty list."""
        assert eb.resolve_relations([], {"JWT Authentication"}) == []

    def test_none_input_returns_empty_list(self):
        """None → empty list."""
        assert eb.resolve_relations(None, {"JWT Authentication"}) == []

    def test_non_dict_items_skipped(self):
        """Non-dict items in the list are skipped."""
        result = eb.resolve_relations(["not a dict"], {"JWT Authentication"})
        assert result == []

    def test_empty_target_string_skipped(self):
        """A relation with an empty target string is skipped."""
        vault_titles = {"JWT Authentication"}
        relations = [{"type": "related", "target": ""}]
        result = eb.resolve_relations(relations, vault_titles)
        assert result == []

    def test_all_lowercase_valid_predicates_accepted(self):
        """All lowercase valid predicates pass through without normalisation."""
        vault_titles = {"Target Note"}
        for predicate in ("related", "references", "broader", "narrower", "supersedes"):
            relations = [{"type": predicate, "target": "Target Note"}]
            result = eb.resolve_relations(relations, vault_titles)
            assert result[0]["type"] == predicate


# ===========================================================================
# write_beat with relations
# ===========================================================================

class TestWriteBeatRelations:
    """write_beat() correctly handles relations in frontmatter and body."""

    def test_writes_related_wikilinks_to_frontmatter(self, global_config, temp_vault, fixed_now, vault_with_notes):
        """A beat with a resolved relation writes a [[wikilink]] to related: frontmatter."""
        beat = make_beat(title="My Beat")
        beat["relations"] = [{"type": "references", "target": "JWT Authentication"}]
        vault_titles = eb.build_vault_titles_set(str(temp_vault))
        path = eb.write_beat(beat, global_config, "sess001", "/cwd", fixed_now, vault_titles=vault_titles)
        content = path.read_text(encoding="utf-8")
        assert "[[JWT Authentication]]" in content

    def test_writes_relations_section_to_body(self, global_config, temp_vault, fixed_now, vault_with_notes):
        """A beat with a relation gets a ## Relations section in the body."""
        beat = make_beat(title="My Beat With Relations")
        beat["relations"] = [{"type": "references", "target": "JWT Authentication"}]
        vault_titles = eb.build_vault_titles_set(str(temp_vault))
        path = eb.write_beat(beat, global_config, "sess001", "/cwd", fixed_now, vault_titles=vault_titles)
        content = path.read_text(encoding="utf-8")
        assert "## Relations" in content

    def test_empty_relations_writes_empty_related_list(self, global_config, temp_vault, fixed_now):
        """No relations → related: [] in frontmatter."""
        beat = make_beat()
        beat["relations"] = []
        path = eb.write_beat(beat, global_config, "sess001", "/cwd", fixed_now)
        content = path.read_text(encoding="utf-8")
        assert "related: []" in content

    def test_unresolved_relation_target_not_written(self, global_config, temp_vault, fixed_now):
        """A phantom relation target is dropped and not written to the file."""
        beat = make_beat(title="Phantom Relations Beat")
        beat["relations"] = [{"type": "related", "target": "Phantom Note Does Not Exist"}]
        path = eb.write_beat(beat, global_config, "sess001", "/cwd", fixed_now)
        content = path.read_text(encoding="utf-8")
        assert "Phantom Note Does Not Exist" not in content

    def test_vault_titles_set_passed_avoids_redundant_glob(self, global_config, temp_vault, fixed_now):
        """Passing vault_titles explicitly means build_vault_titles_set is not called again."""
        vault_titles = {"Some Note"}
        beat = make_beat()
        beat["relations"] = []
        with patch.object(eb, "build_vault_titles_set") as mock_build:
            eb.write_beat(beat, global_config, "sess001", "/cwd", fixed_now, vault_titles=vault_titles)
        mock_build.assert_not_called()


# ===========================================================================
# _merge_relations_into_note
# ===========================================================================

class TestMergeRelationsIntoNote:
    """_merge_relations_into_note() merges relations into existing vault notes."""

    def _write_note(self, path, related=None):
        """Write a simple note with frontmatter."""
        related_str = json.dumps(related or [])
        path.write_text(
            f"---\nid: test-id\ntype: insight\ntitle: \"Test Note\"\ntags: []\nrelated: {related_str}\nsummary: \"Test\"\n---\n\n## Body\n",
            encoding="utf-8",
        )

    def test_adds_new_wikilink_to_existing_related_list(self, tmp_path):
        """A new relation is added to an existing related: [] list."""
        pytest.importorskip("ruamel.yaml")
        note = tmp_path / "Test Note.md"
        self._write_note(note)
        eb._merge_relations_into_note(note, [{"type": "related", "target": "New Target"}])
        content = note.read_text(encoding="utf-8")
        assert "[[New Target]]" in content

    def test_preserves_other_frontmatter_fields_unchanged(self, tmp_path):
        """Other frontmatter fields are preserved after merge."""
        pytest.importorskip("ruamel.yaml")
        note = tmp_path / "Test Note.md"
        self._write_note(note)
        eb._merge_relations_into_note(note, [{"type": "related", "target": "Some Target"}])
        content = note.read_text(encoding="utf-8")
        assert "type: insight" in content
        assert "Test Note" in content

    def test_deduplicates_existing_wikilinks(self, tmp_path):
        """If the wikilink already exists in related, it is not added again."""
        pytest.importorskip("ruamel.yaml")
        note = tmp_path / "Test Note.md"
        self._write_note(note, related=["[[Target]]"])
        original_content = note.read_text(encoding="utf-8")
        eb._merge_relations_into_note(note, [{"type": "related", "target": "Target"}])
        new_content = note.read_text(encoding="utf-8")
        # File should not change (no new relation to add)
        assert new_content.count("[[Target]]") == original_content.count("[[Target]]")

    def test_graceful_fallback_when_ruamel_yaml_not_installed(self, tmp_path, monkeypatch):
        """ImportError from ruamel → no exception raised, no write attempted."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "ruamel.yaml" or name == "ruamel":
                raise ImportError("ruamel.yaml not installed")
            return real_import(name, *args, **kwargs)

        note = tmp_path / "Test Note.md"
        self._write_note(note)
        original = note.read_text(encoding="utf-8")
        monkeypatch.setattr(builtins, "__import__", mock_import)
        # Should not raise
        eb._merge_relations_into_note(note, [{"type": "related", "target": "Some Target"}])
        # File should be unchanged
        assert note.read_text(encoding="utf-8") == original

    def test_returns_without_writing_when_no_new_relations(self, tmp_path):
        """If all relations are already present, the file is not modified."""
        pytest.importorskip("ruamel.yaml")
        note = tmp_path / "Test Note.md"
        self._write_note(note, related=["[[Target]]"])
        import os
        mtime_before = os.path.getmtime(note)
        import time
        time.sleep(0.01)
        eb._merge_relations_into_note(note, [{"type": "related", "target": "Target"}])
        mtime_after = os.path.getmtime(note)
        assert mtime_before == mtime_after

    def test_handles_oserror_on_read(self, tmp_path):
        """If the file is deleted before merge, no exception is raised."""
        pytest.importorskip("ruamel.yaml")
        note = tmp_path / "Deleted Note.md"
        # Note does not exist — should not raise
        eb._merge_relations_into_note(note, [{"type": "related", "target": "Some Target"}])


# ===========================================================================
# _read_frontmatter_as_dict
# ===========================================================================

class TestReadFrontmatterAsDict:
    """_read_frontmatter_as_dict() reads YAML frontmatter from a markdown file."""

    def test_parses_yaml_frontmatter(self, tmp_path):
        """Standard frontmatter → dict with all fields."""
        note = tmp_path / "Note.md"
        note.write_text("---\ntype: decision\ntitle: \"My Note\"\ntags: []\n---\n\nBody.\n")
        result = eb._read_frontmatter_as_dict(note)
        assert result["type"] == "decision"
        assert result["title"] == "My Note"

    def test_returns_empty_dict_when_no_frontmatter_marker(self, tmp_path):
        """File with no --- → empty dict."""
        note = tmp_path / "Note.md"
        note.write_text("Just a body, no frontmatter.\n")
        result = eb._read_frontmatter_as_dict(note)
        assert result == {}

    def test_returns_empty_dict_when_no_closing_marker(self, tmp_path):
        """--- without a closing --- → empty dict."""
        note = tmp_path / "Note.md"
        note.write_text("---\nkey: val\n")
        result = eb._read_frontmatter_as_dict(note)
        assert result == {}

    def test_returns_empty_dict_on_oserror(self, tmp_path):
        """Nonexistent path → empty dict."""
        missing = tmp_path / "does_not_exist.md"
        result = eb._read_frontmatter_as_dict(missing)
        assert result == {}


# ===========================================================================
# extract_beats (pipeline function)
# ===========================================================================

class TestExtractBeats:
    """extract_beats() runs the full extraction pipeline (LLM mocked)."""

    _SAMPLE_BEATS = [
        {
            "title": "Test Beat",
            "type": "insight",
            "scope": "general",
            "summary": "A test insight.",
            "tags": ["test"],
            "body": "## Test Beat\n\nBody content.",
        }
    ]

    def test_parses_json_array_from_model_response(self, global_config, temp_vault):
        """A valid JSON array from call_model is parsed into a list of dicts."""
        with patch("extractors.extract_beats.call_model", return_value=json.dumps(self._SAMPLE_BEATS)):
            with patch("extractors.extract_beats.load_prompt", return_value="prompt"):
                result = eb.extract_beats("transcript text", global_config, "manual", "/cwd")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["title"] == "Test Beat"

    def test_strips_markdown_code_fences(self, global_config, temp_vault):
        """call_model returning JSON wrapped in code fences is parsed correctly."""
        fenced = f"```json\n{json.dumps(self._SAMPLE_BEATS)}\n```"
        with patch("extractors.extract_beats.call_model", return_value=fenced):
            with patch("extractors.extract_beats.load_prompt", return_value="prompt"):
                result = eb.extract_beats("transcript text", global_config, "manual", "/cwd")
        assert len(result) == 1

    def test_handles_trailing_text_after_json(self, global_config, temp_vault):
        """Trailing non-JSON text after the array is ignored via raw_decode."""
        trailing = json.dumps(self._SAMPLE_BEATS) + "\n\nHere are the beats I found."
        with patch("extractors.extract_beats.call_model", return_value=trailing):
            with patch("extractors.extract_beats.load_prompt", return_value="prompt"):
                result = eb.extract_beats("transcript text", global_config, "manual", "/cwd")
        assert len(result) == 1

    def test_returns_empty_list_on_invalid_json(self, global_config, temp_vault):
        """Non-JSON response → empty list."""
        with patch("extractors.extract_beats.call_model", return_value="not json at all"):
            with patch("extractors.extract_beats.load_prompt", return_value="prompt"):
                result = eb.extract_beats("transcript text", global_config, "manual", "/cwd")
        assert result == []

    def test_returns_empty_list_on_non_list_json(self, global_config, temp_vault):
        """JSON object (not array) → empty list."""
        with patch("extractors.extract_beats.call_model", return_value='{"key": "value"}'):
            with patch("extractors.extract_beats.load_prompt", return_value="prompt"):
                result = eb.extract_beats("transcript text", global_config, "manual", "/cwd")
        assert result == []

    def test_includes_vault_claude_md_in_user_message(self, global_config, temp_vault):
        """When vault has CLAUDE.md, its content appears in the user message sent to LLM."""
        (temp_vault / "CLAUDE.md").write_text("## Types\n\n- `decision`\n", encoding="utf-8")
        captured_messages = []

        def fake_call_model(system, user, config):
            captured_messages.append(user)
            return json.dumps(self._SAMPLE_BEATS)

        with patch("extractors.extract_beats.call_model", side_effect=fake_call_model):
            with patch("extractors.extract_beats.load_prompt", return_value="{vault_claude_md_section}{transcript}{project_name}{cwd}{trigger}"):
                eb.extract_beats("some transcript", global_config, "manual", "/cwd")

        assert len(captured_messages) == 1
        assert "vault_claude_md" in captured_messages[0] or "CLAUDE.md" in captured_messages[0] or "decision" in captured_messages[0]

    def test_falls_back_to_default_vocab_when_no_claude_md(self, global_config, temp_vault):
        """No CLAUDE.md → default type notice appears in user message."""
        captured_messages = []

        def fake_call_model(system, user, config):
            captured_messages.append(user)
            return json.dumps(self._SAMPLE_BEATS)

        with patch("extractors.extract_beats.call_model", side_effect=fake_call_model):
            with patch("extractors.extract_beats.load_prompt", return_value="{vault_claude_md_section}{transcript}{project_name}{cwd}{trigger}"):
                eb.extract_beats("some transcript", global_config, "manual", "/cwd")

        assert len(captured_messages) == 1
        assert "default" in captured_messages[0].lower() or "decision" in captured_messages[0]

    def test_truncates_long_transcript(self, global_config, temp_vault):
        """A transcript over MAX_TRANSCRIPT_CHARS is truncated, keeping the tail."""
        long_transcript = "x" * (eb.MAX_TRANSCRIPT_CHARS + 10_000)
        captured_messages = []

        def fake_call_model(system, user, config):
            captured_messages.append(user)
            return json.dumps([])

        with patch("extractors.extract_beats.call_model", side_effect=fake_call_model):
            with patch("extractors.extract_beats.load_prompt", return_value="{transcript}{vault_claude_md_section}{project_name}{cwd}{trigger}"):
                eb.extract_beats(long_transcript, global_config, "manual", "/cwd")

        assert len(captured_messages) == 1
        # The transcript in the user message should be truncated
        assert "truncated" in captured_messages[0] or len(captured_messages[0]) < len(long_transcript)
