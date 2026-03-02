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
            "staging_folder": "AI/Claude-Inbox",
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
        }
        (config_dir / "knowledge.json").write_text(json.dumps(config_data))

        monkeypatch.setattr(eb, "GLOBAL_CONFIG_PATH", config_dir / "knowledge.json")

        config = eb.load_global_config()

        assert config["inbox"] == "AI/Claude-Sessions"
        assert Path(config["vault_path"]).is_absolute()

    def test_exits_cleanly_when_config_missing(self, temp_home, monkeypatch):
        """Missing config file produces sys.exit(0), not an exception."""
        missing_path = temp_home / ".claude" / "knowledge.json"
        monkeypatch.setattr(eb, "GLOBAL_CONFIG_PATH", missing_path)

        with pytest.raises(SystemExit) as exc_info:
            eb.load_global_config()
        assert exc_info.value.code == 0

    def test_exits_cleanly_when_required_fields_missing(self, temp_vault, temp_home, monkeypatch):
        """Config missing required fields produces sys.exit(0)."""
        config_dir = temp_home / ".claude"
        config_dir.mkdir(parents=True, exist_ok=True)
        # vault_path present but inbox and staging_folder missing
        (config_dir / "knowledge.json").write_text(
            json.dumps({"vault_path": str(temp_vault)})
        )
        monkeypatch.setattr(eb, "GLOBAL_CONFIG_PATH", config_dir / "knowledge.json")

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
            "staging_folder": "AI/Claude-Inbox",
        }
        (config_dir / "knowledge.json").write_text(json.dumps(config_data))
        monkeypatch.setattr(eb, "GLOBAL_CONFIG_PATH", config_dir / "knowledge.json")

        config = eb.load_global_config()
        assert os.path.isabs(config["vault_path"])

    def test_rejects_vault_path_equal_to_home_directory(self, temp_home, monkeypatch):
        """vault_path set to the home directory produces sys.exit(0) with a clear error."""
        config_dir = temp_home / ".claude"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_data = {
            "vault_path": str(temp_home),
            "inbox": "AI/Claude-Sessions",
            "staging_folder": "AI/Claude-Inbox",
        }
        (config_dir / "knowledge.json").write_text(json.dumps(config_data))
        monkeypatch.setattr(eb, "GLOBAL_CONFIG_PATH", config_dir / "knowledge.json")
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
            "staging_folder": "AI/Claude-Inbox",
        }
        (config_dir / "knowledge.json").write_text(json.dumps(config_data))
        monkeypatch.setattr(eb, "GLOBAL_CONFIG_PATH", config_dir / "knowledge.json")

        with pytest.raises(SystemExit) as exc_info:
            eb.load_global_config()
        assert exc_info.value.code == 0


class TestFindProjectConfig:
    """find_project_config() walks up the directory tree to find knowledge.local.json."""

    def test_finds_config_in_current_directory(self, tmp_path):
        """Project config in .claude/ of the current directory is found."""
        project_dir = tmp_path / "my-project"
        config_dir = project_dir / ".claude"
        config_dir.mkdir(parents=True)
        config_data = {"project_name": "my-project", "vault_folder": "Projects/my-project"}
        (config_dir / "knowledge.local.json").write_text(json.dumps(config_data))

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
        (config_dir / "knowledge.local.json").write_text(json.dumps(config_data))

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


class TestParsePlainTranscript:
    """parse_plain_transcript() handles Human:/Assistant: and You:/Claude: role prefixes."""

    def test_splits_on_human_assistant_prefixes(self):
        """Human: / Assistant: prefixed turns are split into labeled blocks."""
        text = "Human: What is X?\nAssistant: X is Y."
        result = eb.parse_plain_transcript(text)
        assert "[USER]" in result
        assert "[ASSISTANT]" in result

    def test_splits_on_you_claude_prefixes(self):
        """You: / Claude: prefixed turns are split into labeled blocks."""
        text = "You: How do I do X?\nClaude: Here is how."
        result = eb.parse_plain_transcript(text)
        assert "[USER]" in result
        assert "[ASSISTANT]" in result

    def test_returns_text_as_is_when_no_prefixes(self):
        """Text without role prefixes is returned unchanged."""
        text = "This is a plain paragraph with no role markers."
        result = eb.parse_plain_transcript(text)
        assert result == text


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

    def test_routes_to_staging_when_no_project_config(self, temp_vault, temp_home, monkeypatch, fixed_now):
        """When no project config exists and no inbox is configured, beat goes to staging_folder."""
        config_dir = temp_home / ".claude"
        config_dir.mkdir(parents=True, exist_ok=True)
        config = {
            "vault_path": str(temp_vault),
            "inbox": "",
            "staging_folder": "AI/Claude-Inbox",
        }
        (config_dir / "knowledge.json").write_text(json.dumps(config))
        monkeypatch.setattr(eb, "GLOBAL_CONFIG_PATH", config_dir / "knowledge.json")

        beat = make_beat(scope="general")
        path = eb.write_beat(beat, config, "sess001", "/cwd", fixed_now)

        assert "Claude-Inbox" in str(path)

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
        log_path = tmp_path / "logs" / "kg-extract.log"
        monkeypatch.setattr(eb, "EXTRACT_LOG_PATH", log_path)

        assert eb.is_session_already_extracted("brand-new-session") is False

    def test_session_in_log_is_detected_as_duplicate(self, tmp_path, monkeypatch):
        """A session ID present in the log is reported as already extracted."""
        log_path = tmp_path / "logs" / "kg-extract.log"
        log_path.parent.mkdir(parents=True)
        log_path.write_text("2026-03-01T14:32:00\tabc12345\t3\n")
        monkeypatch.setattr(eb, "EXTRACT_LOG_PATH", log_path)

        assert eb.is_session_already_extracted("abc12345") is True

    def test_different_session_id_not_detected_as_duplicate(self, tmp_path, monkeypatch):
        """A different session ID in the same log file is not a duplicate."""
        log_path = tmp_path / "logs" / "kg-extract.log"
        log_path.parent.mkdir(parents=True)
        log_path.write_text("2026-03-01T14:32:00\tabc12345\t3\n")
        monkeypatch.setattr(eb, "EXTRACT_LOG_PATH", log_path)

        assert eb.is_session_already_extracted("xyz99999") is False

    def test_write_log_entry_creates_file_and_directory(self, tmp_path, monkeypatch):
        """write_extract_log_entry creates the log file and parent directory if needed."""
        log_path = tmp_path / "logs" / "kg-extract.log"
        monkeypatch.setattr(eb, "EXTRACT_LOG_PATH", log_path)

        eb.write_extract_log_entry("newsession", 5)

        assert log_path.exists()
        content = log_path.read_text()
        assert "newsession" in content
        assert "\t5\n" in content

    def test_write_log_entry_format_is_tab_separated(self, tmp_path, monkeypatch):
        """Log entries are tab-separated: <ISO-timestamp>\t<session-id>\t<beat-count>."""
        log_path = tmp_path / "logs" / "kg-extract.log"
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
        log_path = tmp_path / "logs" / "kg-extract.log"
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
        (config_dir / "knowledge.json").write_text(json.dumps({
            "vault_path": "/nonexistent/path/to/vault",
            "inbox": "AI/Claude-Sessions",
            "staging_folder": "AI/Claude-Inbox",
        }))
        monkeypatch.setattr(eb, "GLOBAL_CONFIG_PATH", config_dir / "knowledge.json")

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
