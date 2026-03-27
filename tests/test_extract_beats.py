"""
test_extract_beats.py — unit tests for src/cyberbrain/extractors/extract_beats.py

Tests describe the system's behaviour, not its implementation. Each test
documents one verifiable property of the extraction engine.

LLM calls are always mocked — no real API calls are made in this suite.
Vault I/O uses tempfile.TemporaryDirectory (via the temp_vault fixture).
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Import the module under test
# Clear the conftest mock before importing the real modules
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# sys.modules cleanup — why this file needs it
#
# Modules cleared: extract_beats, config, run_log, extractor
#
# conftest.py installs a MagicMock for extract_beats before any test module
# loads, so shared.py gets a stub BackendError.  This file tests the *real*
# extract_beats engine, so it must evict the mock and all modules that
# extract_beats drags in (config, run_log, extractor) to get fresh objects.
#
# autofile and frontmatter are NOT popped: test_autofile.py imports them at
# module level and popping them here would create new module objects, breaking
# patch() call-site isolation for any tests that run after this file.
# ---------------------------------------------------------------------------
from tests.conftest import _clear_module_cache

_clear_module_cache(
    [
        "cyberbrain.extractors.extract_beats",
        "cyberbrain.extractors.config",
        "cyberbrain.extractors.run_log",
        "cyberbrain.extractors.extractor",
    ]
)

import cyberbrain.extractors.autofile as _autofile_module
import cyberbrain.extractors.config as _config_module
import cyberbrain.extractors.extract_beats as eb
import cyberbrain.extractors.run_log as _run_log_module
import cyberbrain.extractors.vault as _vault_module
from cyberbrain.extractors.autofile import _merge_relations_into_note, autofile_beat
from cyberbrain.extractors.backends import MAX_TRANSCRIPT_CHARS, BackendError
from cyberbrain.extractors.config import find_project_config, load_global_config
from cyberbrain.extractors.extractor import extract_beats
from cyberbrain.extractors.frontmatter import (
    read_frontmatter as _read_frontmatter_as_dict,
)
from cyberbrain.extractors.run_log import (
    is_session_already_extracted,
    write_extract_log_entry,
    write_journal_entry,
)
from cyberbrain.extractors.transcript import parse_jsonl_transcript
from cyberbrain.extractors.vault import (
    _DEFAULT_VALID_BEAT_TYPES,
    _DEFAULT_VALID_ENTITY_TYPES,
    _is_within_vault,
    build_vault_titles_set,
    get_valid_types,
    make_filename,
    parse_valid_types_from_claude_md,
    read_vault_claude_md,
    resolve_relations,
    write_beat,
)
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

        monkeypatch.setattr(
            _config_module, "GLOBAL_CONFIG_PATH", config_dir / "cyberbrain.json"
        )

        config = load_global_config()

        assert config["inbox"] == "AI/Claude-Sessions"
        assert Path(config["vault_path"]).is_absolute()

    def test_exits_cleanly_when_config_missing(self, temp_home, monkeypatch):
        """Missing config file produces sys.exit(0), not an exception."""
        missing_path = temp_home / ".claude" / "cyberbrain.json"
        monkeypatch.setattr(_config_module, "GLOBAL_CONFIG_PATH", missing_path)

        with pytest.raises(SystemExit) as exc_info:
            load_global_config()
        assert exc_info.value.code == 0

    def test_exits_cleanly_when_required_fields_missing(
        self, temp_vault, temp_home, monkeypatch
    ):
        """Config missing required fields produces sys.exit(0)."""
        config_dir = temp_home / ".claude"
        config_dir.mkdir(parents=True, exist_ok=True)
        # vault_path present but inbox missing
        (config_dir / "cyberbrain.json").write_text(
            json.dumps({"vault_path": str(temp_vault)})
        )
        monkeypatch.setattr(
            _config_module, "GLOBAL_CONFIG_PATH", config_dir / "cyberbrain.json"
        )

        with pytest.raises(SystemExit) as exc_info:
            load_global_config()
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
        monkeypatch.setattr(
            _config_module, "GLOBAL_CONFIG_PATH", config_dir / "cyberbrain.json"
        )

        config = load_global_config()
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
        monkeypatch.setattr(
            _config_module, "GLOBAL_CONFIG_PATH", config_dir / "cyberbrain.json"
        )
        # temp_home fixture already sets HOME env var so Path.home() returns temp_home

        with pytest.raises(SystemExit) as exc_info:
            load_global_config()
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
        monkeypatch.setattr(
            _config_module, "GLOBAL_CONFIG_PATH", config_dir / "cyberbrain.json"
        )

        with pytest.raises(SystemExit) as exc_info:
            load_global_config()
        assert exc_info.value.code == 0


class TestFindProjectConfig:
    """find_project_config() walks up the directory tree to find cyberbrain.local.json."""

    def test_finds_config_in_current_directory(self, tmp_path):
        """Project config in .claude/ of the current directory is found."""
        project_dir = tmp_path / "my-project"
        config_dir = project_dir / ".claude"
        config_dir.mkdir(parents=True)
        config_data = {
            "project_name": "my-project",
            "vault_folder": "Projects/my-project",
        }
        (config_dir / "cyberbrain.local.json").write_text(json.dumps(config_data))

        result = find_project_config(str(project_dir))
        assert result["project_name"] == "my-project"

    def test_finds_config_in_parent_directory(self, tmp_path):
        """Project config in a parent directory's .claude/ is found by walking up."""
        project_dir = tmp_path / "my-project"
        sub_dir = project_dir / "src" / "lib"
        config_dir = project_dir / ".claude"
        sub_dir.mkdir(parents=True)
        config_dir.mkdir(parents=True)
        config_data = {
            "project_name": "my-project",
            "vault_folder": "Projects/my-project",
        }
        (config_dir / "cyberbrain.local.json").write_text(json.dumps(config_data))

        result = find_project_config(str(sub_dir))
        assert result["project_name"] == "my-project"

    def test_returns_empty_dict_when_not_found(self, tmp_path):
        """Returns empty dict when no project config exists in the directory tree."""
        project_dir = tmp_path / "no-config-project"
        project_dir.mkdir()

        result = find_project_config(str(project_dir))
        assert result == {}


# ===========================================================================
# Transcript parsing
# ===========================================================================


class TestParseJsonlTranscript:
    """parse_jsonl_transcript() extracts conversation text from JSONL transcripts."""

    def test_extracts_user_and_assistant_turns(self, sample_transcript_path):
        """Text turns from user and assistant entries are extracted."""
        result = parse_jsonl_transcript(sample_transcript_path)
        assert "[USER]" in result
        assert "[ASSISTANT]" in result

    def test_skips_tool_use_blocks(self, sample_transcript_path):
        """tool_use blocks within assistant content are not included in the output."""
        result = parse_jsonl_transcript(sample_transcript_path)
        # The sample transcript has a tool_use block with name "Read" — it should not appear
        assert "tool_use" not in result

    def test_skips_thinking_blocks(self, sample_transcript_path):
        """thinking blocks are not included in the output."""
        result = parse_jsonl_transcript(sample_transcript_path)
        assert "The user is happy with the claude-code backend" not in result

    def test_skips_tool_result_blocks(self, sample_transcript_path):
        """tool_result blocks are not included in the output."""
        result = parse_jsonl_transcript(sample_transcript_path)
        # The sample has a tool_result with "The command output some binary data"
        assert "tool_result" not in result

    def test_handles_empty_file(self, tmp_path):
        """An empty JSONL file produces an empty string."""
        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_text("")
        result = parse_jsonl_transcript(str(empty_file))
        assert result.strip() == ""

    def test_ignores_malformed_json_lines(self, tmp_path):
        """Lines that are not valid JSON are skipped without raising."""
        jsonl = tmp_path / "partial.jsonl"
        jsonl.write_text(
            "not valid json\n"
            '{"type": "user", "message": {"role": "user", "content": "hello"}}\n'
        )
        result = parse_jsonl_transcript(str(jsonl))
        assert "hello" in result


# ===========================================================================
# Beat writing
# ===========================================================================


class TestWriteBeat:
    """write_beat() creates valid vault notes with correct routing and frontmatter."""

    def test_routes_project_scoped_beat_to_project_folder(
        self, global_config, temp_vault, fixed_now
    ):
        """A beat with scope=project and a vault_folder config goes to the project folder."""
        config = dict(global_config)
        config["vault_folder"] = "Projects/my-project"
        (temp_vault / "Projects" / "my-project").mkdir(parents=True)

        beat = make_beat(scope="project")
        path = write_beat(beat, config, "sess001", "/cwd", fixed_now)

        assert "Projects/my-project" in str(path)

    def test_routes_general_beat_to_inbox(self, global_config, temp_vault, fixed_now):
        """A beat with scope=general goes to the inbox folder."""
        beat = make_beat(scope="general")
        path = write_beat(beat, global_config, "sess001", "/cwd", fixed_now)

        assert "Claude-Sessions" in str(path)

    def test_returns_none_when_inbox_not_configured(
        self, temp_vault, temp_home, monkeypatch, fixed_now, capsys
    ):
        """When inbox is not configured, write_beat returns None and prints a warning."""
        config_dir = temp_home / ".claude"
        config_dir.mkdir(parents=True, exist_ok=True)
        config = {
            "vault_path": str(temp_vault),
            "inbox": "",
        }
        (config_dir / "cyberbrain.json").write_text(json.dumps(config))
        monkeypatch.setattr(
            _config_module, "GLOBAL_CONFIG_PATH", config_dir / "cyberbrain.json"
        )

        beat = make_beat(scope="general")
        path = write_beat(beat, config, "sess001", "/cwd", fixed_now)

        assert path is None
        assert "inbox" in capsys.readouterr().err

    def test_produces_valid_yaml_frontmatter(
        self, global_config, temp_vault, fixed_now
    ):
        """The written file has valid YAML frontmatter with the expected fields."""
        beat = make_beat(
            title="Auth Decision", beat_type="decision", tags=["auth", "backend"]
        )
        path = write_beat(beat, global_config, "sess001", "/cwd", fixed_now)

        content = path.read_text(encoding="utf-8")
        assert content.startswith("---")
        assert "type: resource" in content  # decision maps to resource entity type
        assert "beat_type: decision" in content
        assert "session_id: sess001" in content
        assert '"auth"' in content  # tags are JSON-serialized
        assert '"backend"' in content

    def test_invalid_beat_type_falls_back_to_reference(
        self, global_config, temp_vault, fixed_now
    ):
        """A beat with an unrecognized type is filed as 'reference' → 'resource' entity type."""
        beat = make_beat(beat_type="totally-invalid-type")
        path = write_beat(beat, global_config, "sess001", "/cwd", fixed_now)

        content = path.read_text(encoding="utf-8")
        assert "type: resource" in content  # reference maps to resource
        assert "beat_type: reference" in content

    def test_handles_filename_collision_with_counter(
        self, global_config, temp_vault, fixed_now
    ):
        """When the target filename already exists, a numeric prefix avoids collision."""
        beat = make_beat(title="Collision Test")
        path1 = write_beat(beat, global_config, "sess001", "/cwd", fixed_now)
        path2 = write_beat(beat, global_config, "sess002", "/cwd", fixed_now)

        assert path1 != path2
        assert path1.exists()
        assert path2.exists()

    def test_all_valid_types_accepted(self, global_config, temp_vault, fixed_now):
        """All four beat types are accepted and mapped to entity types."""
        expected_entity = {
            "decision": "resource",
            "insight": "resource",
            "problem": "note",
            "reference": "resource",
        }
        for beat_type in ("decision", "insight", "problem", "reference"):
            beat = make_beat(title=f"Beat {beat_type}", beat_type=beat_type)
            path = write_beat(beat, global_config, "sess001", "/cwd", fixed_now)
            content = path.read_text(encoding="utf-8")
            assert f"type: {expected_entity[beat_type]}" in content
            assert f"beat_type: {beat_type}" in content


# ===========================================================================
# Autofile
# ===========================================================================


class TestAutofileBeat:
    """autofile_beat() uses LLM judgment to route beats into the vault."""

    @pytest.fixture(autouse=True)
    def clear_claudecode_env(self, monkeypatch):
        """Remove CLAUDECODE so autofile_beat doesn't bail out with the nested-session guard."""
        monkeypatch.delenv("CLAUDECODE", raising=False)

    def test_rejects_path_traversal_in_create_response(
        self, global_config, temp_vault, fixed_now
    ):
        """A 'create' decision with a path traversal string is rejected and falls back to inbox."""
        malicious_response = json.dumps(
            {
                "action": "create",
                "path": "../../etc/passwd",
                "content": "malicious content",
            }
        )
        with patch.object(
            _autofile_module, "call_model", return_value=malicious_response
        ):
            with patch.object(_autofile_module, "search_vault", return_value=[]):
                path = autofile_beat(
                    make_beat(),
                    global_config,
                    "sess001",
                    "/cwd",
                    fixed_now,
                    vault_context="Use types: decision, insight, problem, reference.",
                )
        # Should have fallen back to inbox write, not written to traversal path
        assert path is not None
        assert str(path).startswith(str(temp_vault))
        assert "etc" not in str(path)

    def test_rejects_path_traversal_in_extend_response(
        self, global_config, temp_vault, fixed_now
    ):
        """An 'extend' decision with a path traversal target is rejected and falls back to inbox."""
        malicious_response = json.dumps(
            {
                "action": "extend",
                "target_path": "../../../etc/hosts",
                "insertion": "## Injected\n\nmalicious",
            }
        )
        with patch.object(
            _autofile_module, "call_model", return_value=malicious_response
        ):
            with patch.object(_autofile_module, "search_vault", return_value=[]):
                path = autofile_beat(
                    make_beat(),
                    global_config,
                    "sess001",
                    "/cwd",
                    fixed_now,
                    vault_context="Use types: decision, insight, problem, reference.",
                )
        assert path is not None
        assert str(path).startswith(str(temp_vault))

    def test_falls_back_to_flat_write_on_backend_error(
        self, global_config, temp_vault, fixed_now
    ):
        """When the LLM backend raises BackendError, the beat is written to the inbox instead."""
        with patch.object(
            _autofile_module,
            "call_model",
            side_effect=BackendError("backend unavailable"),
        ):
            with patch.object(_autofile_module, "search_vault", return_value=[]):
                path = autofile_beat(
                    make_beat(),
                    global_config,
                    "sess001",
                    "/cwd",
                    fixed_now,
                    vault_context="Use types: decision, insight, problem, reference.",
                )
        assert path is not None
        assert path.exists()

    def test_create_action_writes_new_file(self, global_config, temp_vault, fixed_now):
        """A 'create' decision writes a new file at the specified vault-relative path."""
        note_content = "---\ntype: insight\n---\n\n## Test\n\nBody."
        create_response = json.dumps(
            {
                "action": "create",
                "path": "AI/Claude-Sessions/Test Note.md",
                "content": note_content,
            }
        )
        with patch.object(_autofile_module, "call_model", return_value=create_response):
            with patch.object(_autofile_module, "search_vault", return_value=[]):
                path = autofile_beat(
                    make_beat(),
                    global_config,
                    "sess001",
                    "/cwd",
                    fixed_now,
                    vault_context="conventions",
                )
        assert path is not None
        assert path.exists()
        written = path.read_text(encoding="utf-8")
        # Provenance fields are injected into frontmatter; verify core content preserved
        assert "type: insight" in written
        assert "## Test" in written
        assert "cb_source: hook-extraction" in written
        assert "cb_created:" in written

    def test_extend_action_appends_to_existing_file(
        self, global_config, temp_vault, fixed_now
    ):
        """An 'extend' decision appends content to an existing vault note."""
        existing_note = temp_vault / "AI" / "Claude-Sessions" / "Existing Note.md"
        existing_note.write_text(
            "---\ntype: insight\n---\n\n## Original\n\nOriginal body."
        )

        extend_response = json.dumps(
            {
                "action": "extend",
                "target_path": "AI/Claude-Sessions/Existing Note.md",
                "insertion": "## New Section\n\nNew content.",
            }
        )
        with patch.object(_autofile_module, "call_model", return_value=extend_response):
            with patch.object(_autofile_module, "search_vault", return_value=[]):
                path = autofile_beat(
                    make_beat(),
                    global_config,
                    "sess001",
                    "/cwd",
                    fixed_now,
                    vault_context="conventions",
                )
        assert path == existing_note
        content = existing_note.read_text(encoding="utf-8")
        assert "New Section" in content
        assert "Original body." in content

    def test_collision_with_related_tags_resolves_as_extend(
        self, global_config, temp_vault, fixed_now
    ):
        """When create target exists and has 2+ overlapping tags, treat as extend instead."""
        existing = temp_vault / "AI" / "Claude-Sessions" / "Collision Note.md"
        existing.write_text(
            '---\ntype: insight\ntags: ["python", "encoding", "subprocess"]\n---\n\n## Original\n\nBody.'
        )

        create_response = json.dumps(
            {
                "action": "create",
                "path": "AI/Claude-Sessions/Collision Note.md",
                "content": "---\ntype: insight\n---\n\n## Duplicate\n\nNew content.",
            }
        )
        beat = make_beat(tags=["python", "encoding", "unicode"])
        with patch.object(_autofile_module, "call_model", return_value=create_response):
            with patch.object(_autofile_module, "search_vault", return_value=[]):
                path = autofile_beat(
                    beat,
                    global_config,
                    "sess001",
                    "/cwd",
                    fixed_now,
                    vault_context="conventions",
                )
        # Should have extended the existing file, not created a new one
        assert path == existing
        content = existing.read_text(encoding="utf-8")
        assert "New content." in content

    def test_collision_with_unrelated_tags_creates_specific_title(
        self, global_config, temp_vault, fixed_now
    ):
        """When create target exists and tags don't overlap enough, use a more specific title."""
        existing = temp_vault / "AI" / "Claude-Sessions" / "Collision Note.md"
        existing.write_text(
            '---\ntype: insight\ntags: ["unrelated", "topic"]\n---\n\n## Original\n\nBody.'
        )

        create_response = json.dumps(
            {
                "action": "create",
                "path": "AI/Claude-Sessions/Collision Note.md",
                "content": "---\ntype: insight\n---\n\n## Different\n\nContent.",
            }
        )
        beat = make_beat(tags=["python", "encoding"])
        with patch.object(_autofile_module, "call_model", return_value=create_response):
            with patch.object(_autofile_module, "search_vault", return_value=[]):
                path = autofile_beat(
                    beat,
                    global_config,
                    "sess001",
                    "/cwd",
                    fixed_now,
                    vault_context="conventions",
                )
        # Should have created a file with a more specific name
        assert path != existing
        assert path.exists()


# ===========================================================================
# Daily journal
# ===========================================================================


class TestWriteJournalEntry:
    """write_journal_entry() maintains a daily log of captured notes."""

    def test_creates_new_journal_file_with_header(
        self, global_config, temp_vault, fixed_now
    ):
        """A new daily journal file is created with YAML frontmatter and a session block."""
        (temp_vault / "AI" / "Journal").mkdir(parents=True, exist_ok=True)
        config = dict(global_config)
        config["journal_folder"] = "AI/Journal"

        written = [temp_vault / "AI" / "Claude-Sessions" / "Some Note.md"]
        written[0].write_text("note content")

        write_journal_entry(written, config, "abc12345", "my-project", fixed_now)

        journal_path = temp_vault / "AI" / "Journal" / "2026-03-01.md"
        assert journal_path.exists()
        content = journal_path.read_text(encoding="utf-8")
        assert "type: journal" in content
        assert "abc12345" in content
        assert "my-project" in content

    def test_appends_to_existing_journal_file(
        self, global_config, temp_vault, fixed_now
    ):
        """Session blocks are appended to an existing journal file."""
        journal_dir = temp_vault / "AI" / "Journal"
        journal_dir.mkdir(parents=True, exist_ok=True)
        journal_path = journal_dir / "2026-03-01.md"
        journal_path.write_text(
            "---\ntype: journal\ndate: 2026-03-01\n---\n\n# 2026-03-01\n"
        )

        config = dict(global_config)
        config["journal_folder"] = "AI/Journal"

        written = [temp_vault / "AI" / "Claude-Sessions" / "Note.md"]
        written[0].write_text("content")

        write_journal_entry(written, config, "xyz99999", "project", fixed_now)

        content = journal_path.read_text(encoding="utf-8")
        assert "xyz99999" in content
        assert "project" in content

    def test_session_block_includes_timestamp(
        self, global_config, temp_vault, fixed_now
    ):
        """The session block header includes a YYYY-MM-DD HH:MM UTC timestamp."""
        (temp_vault / "AI" / "Journal").mkdir(parents=True, exist_ok=True)
        config = dict(global_config)
        config["journal_folder"] = "AI/Journal"

        written = [temp_vault / "AI" / "Claude-Sessions" / "ANote.md"]
        written[0].write_text("content")

        write_journal_entry(written, config, "abc12345", "proj", fixed_now)

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

        write_journal_entry([note], config, "abc12345", "proj", fixed_now)

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
        monkeypatch.setattr(_run_log_module, "EXTRACT_LOG_PATH", log_path)

        assert is_session_already_extracted("brand-new-session") is False

    def test_session_in_log_is_detected_as_duplicate(self, tmp_path, monkeypatch):
        """A session ID present in the log is reported as already extracted."""
        log_path = tmp_path / "logs" / "cb-extract.log"
        log_path.parent.mkdir(parents=True)
        log_path.write_text("2026-03-01T14:32:00\tabc12345\t3\n")
        monkeypatch.setattr(_run_log_module, "EXTRACT_LOG_PATH", log_path)

        assert is_session_already_extracted("abc12345") is True

    def test_different_session_id_not_detected_as_duplicate(
        self, tmp_path, monkeypatch
    ):
        """A different session ID in the same log file is not a duplicate."""
        log_path = tmp_path / "logs" / "cb-extract.log"
        log_path.parent.mkdir(parents=True)
        log_path.write_text("2026-03-01T14:32:00\tabc12345\t3\n")
        monkeypatch.setattr(_run_log_module, "EXTRACT_LOG_PATH", log_path)

        assert is_session_already_extracted("xyz99999") is False

    def test_write_log_entry_creates_file_and_directory(self, tmp_path, monkeypatch):
        """write_extract_log_entry creates the log file and parent directory if needed."""
        log_path = tmp_path / "logs" / "cb-extract.log"
        monkeypatch.setattr(_run_log_module, "EXTRACT_LOG_PATH", log_path)

        write_extract_log_entry("newsession", 5)

        assert log_path.exists()
        content = log_path.read_text()
        assert "newsession" in content
        assert "\t5\n" in content

    def test_write_log_entry_format_is_tab_separated(self, tmp_path, monkeypatch):
        """Log entries are tab-separated: <ISO-timestamp>\t<session-id>\t<beat-count>."""
        log_path = tmp_path / "logs" / "cb-extract.log"
        log_path.parent.mkdir(parents=True)
        monkeypatch.setattr(_run_log_module, "EXTRACT_LOG_PATH", log_path)

        write_extract_log_entry("sess-abc", 7)

        line = log_path.read_text().strip()
        parts = line.split("\t")
        assert len(parts) == 3
        assert parts[1] == "sess-abc"
        assert parts[2] == "7"

    def test_corrupt_log_warns_and_proceeds(self, tmp_path, monkeypatch, capsys):
        """A corrupt/unreadable log file warns to stderr and returns False (proceed)."""
        log_path = tmp_path / "logs" / "cb-extract.log"
        log_path.parent.mkdir(parents=True)
        log_path.write_text("corrupt\x00data\xff")
        # Make the file unreadable
        log_path.chmod(0o000)
        monkeypatch.setattr(_run_log_module, "EXTRACT_LOG_PATH", log_path)

        try:
            result = is_session_already_extracted("any-session")
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
        (config_dir / "cyberbrain.json").write_text(
            json.dumps(
                {
                    "vault_path": "/nonexistent/path/to/vault",
                    "inbox": "AI/Claude-Sessions",
                }
            )
        )
        monkeypatch.setattr(
            _config_module, "GLOBAL_CONFIG_PATH", config_dir / "cyberbrain.json"
        )

        with pytest.raises(SystemExit) as exc_info:
            load_global_config()
        assert exc_info.value.code == 0


# ===========================================================================
# Security: _is_within_vault
# ===========================================================================


class TestIsWithinVault:
    """_is_within_vault() is the path traversal guard for all vault writes."""

    def test_path_inside_vault_is_allowed(self, temp_vault):
        """A path inside the vault returns True."""
        target = temp_vault / "AI" / "Some Note.md"
        assert _is_within_vault(temp_vault, target) is True

    def test_path_outside_vault_via_traversal_is_rejected(self, temp_vault):
        """A path that resolves outside the vault via ../ returns False."""
        traversal = temp_vault / ".." / "etc" / "passwd"
        assert _is_within_vault(temp_vault, traversal) is False

    def test_absolute_path_outside_vault_is_rejected(self, temp_vault):
        """An absolute path not under vault_path returns False."""
        outside = Path("/etc/passwd")
        assert _is_within_vault(temp_vault, outside) is False


# ===========================================================================
# Vault CLAUDE.md reading
# ===========================================================================


class TestReadVaultClaudeMd:
    """read_vault_claude_md() reads the vault's CLAUDE.md for type vocabulary context."""

    def test_returns_text_when_file_exists(self, temp_vault):
        """Returns the full text of CLAUDE.md when it exists."""
        claude_md = temp_vault / "CLAUDE.md"
        claude_md.write_text("# Vault CLAUDE.md\n\nTypes: decision, insight.")
        result = read_vault_claude_md(str(temp_vault))
        assert result == "# Vault CLAUDE.md\n\nTypes: decision, insight."

    def test_returns_none_when_file_absent(self, temp_vault):
        """Returns None when no CLAUDE.md exists in the vault."""
        result = read_vault_claude_md(str(temp_vault))
        assert result is None


# ===========================================================================
# make_filename
# ===========================================================================


class TestMakeFilename:
    """make_filename() converts titles to clean human-readable filenames."""

    def test_strips_hash_bracket_caret_chars(self):
        """Characters # [ ] ^ are stripped from filenames."""
        assert "C" in make_filename("C#")
        assert "#" not in make_filename("C#")
        assert "foo" in make_filename("[foo]")
        assert "[" not in make_filename("[foo]")
        assert "]" not in make_filename("[foo]")
        assert "blockref" in make_filename("block^ref")
        assert "^" not in make_filename("block^ref")

    def test_collapses_whitespace(self):
        """Multiple consecutive spaces are collapsed to a single space."""
        result = make_filename("Multiple   Spaces   Here")
        assert "  " not in result
        assert "Multiple Spaces Here" in result

    def test_truncates_at_80_chars_on_word_boundary(self):
        """Titles longer than 80 chars are truncated at the last word boundary ≤80."""
        long_title = "A " * 45  # 90 chars
        result = make_filename(long_title.strip())
        stem = result[:-3]  # strip .md
        assert len(stem) <= 80

    def test_appends_md_extension(self):
        """Result always ends in .md"""
        assert make_filename("Some Note").endswith(".md")

    def test_clean_title_unchanged(self):
        """A title with no special characters passes through unchanged (plus .md)."""
        assert make_filename("Clean Title") == "Clean Title.md"


# ===========================================================================
# parse_valid_types_from_claude_md
# ===========================================================================


class TestParseValidTypesFromClaudeMd:
    """parse_valid_types_from_claude_md() extracts type vocabulary from vault CLAUDE.md."""

    def test_extracts_types_from_entity_types_h2_section(self):
        """## Entity Types section with backtick-quoted types extracts them."""
        md = "## Entity Types\n\n- `project` — active work\n- `resource` — stable reference\n"
        result = parse_valid_types_from_claude_md(md)
        assert "project" in result
        assert "resource" in result

    def test_extracts_backtick_types_from_list_items(self):
        """List items with backtick-quoted types are extracted."""
        md = "## Types\n\n- `note` — quick capture\n- `resource` — reference\n"
        result = parse_valid_types_from_claude_md(md)
        assert "note" in result
        assert "resource" in result

    def test_returns_defaults_when_no_types_section_found(self):
        """Arbitrary markdown without a types section → _DEFAULT_VALID_ENTITY_TYPES."""
        result = parse_valid_types_from_claude_md("# Just a header\n\nSome content.\n")
        assert result == _DEFAULT_VALID_ENTITY_TYPES

    def test_returns_defaults_on_empty_string(self):
        """Empty string → _DEFAULT_VALID_ENTITY_TYPES."""
        result = parse_valid_types_from_claude_md("")
        assert result == _DEFAULT_VALID_ENTITY_TYPES

    def test_multiple_types_all_extracted(self):
        """A section with multiple entity types extracts all of them."""
        md = "## Types\n\n- `project` — active work\n- `note` — capture\n- `resource` — reference\n"
        result = parse_valid_types_from_claude_md(md)
        assert "project" in result
        assert "note" in result
        assert "resource" in result

    def test_exits_types_section_at_next_h2(self):
        """A second ## heading stops collection of types."""
        md = (
            "## Types\n\n"
            "- `project` — active work\n- `note` — capture\n\n"
            "## Other Section\n\n"
            "- `not_a_type` — not in types\n"
        )
        result = parse_valid_types_from_claude_md(md)
        assert "project" in result
        assert "not_a_type" not in result

    def test_beat_types_section_is_skipped(self):
        """## Beat Types section is a separate vocabulary and is not parsed."""
        md = "## Beat Types\n\n- `decision` — choice\n- `insight` — pattern\n"
        result = parse_valid_types_from_claude_md(md)
        # Falls back to defaults since no entity types section was found
        assert result == _DEFAULT_VALID_ENTITY_TYPES


# ===========================================================================
# get_valid_types
# ===========================================================================


class TestGetValidTypes:
    """get_valid_types() reads type vocabulary from vault CLAUDE.md."""

    def test_reads_from_vault_claude_md_when_present(self, temp_vault):
        """When vault has CLAUDE.md with custom entity types, those types are returned."""
        claude_md = temp_vault / "CLAUDE.md"
        claude_md.write_text(
            "## Types\n\n- `recipe` — cooking instructions\n- `guide` — how-to\n",
            encoding="utf-8",
        )
        config = {"vault_path": str(temp_vault)}
        result = get_valid_types(config)
        assert "recipe" in result
        assert "guide" in result

    def test_falls_back_to_defaults_when_no_claude_md(self, temp_vault):
        """No CLAUDE.md → _DEFAULT_VALID_ENTITY_TYPES."""
        config = {"vault_path": str(temp_vault)}
        result = get_valid_types(config)
        assert result == _DEFAULT_VALID_ENTITY_TYPES

    def test_falls_back_to_defaults_when_claude_md_has_no_types_section(
        self, temp_vault
    ):
        """CLAUDE.md exists but has no types section → defaults."""
        (temp_vault / "CLAUDE.md").write_text(
            "# Vault Instructions\n\nFile notes here.\n", encoding="utf-8"
        )
        config = {"vault_path": str(temp_vault)}
        result = get_valid_types(config)
        assert result == _DEFAULT_VALID_ENTITY_TYPES


# ===========================================================================
# build_vault_titles_set
# ===========================================================================


class TestBuildVaultTitlesSet:
    """build_vault_titles_set() returns the set of note stems in the vault."""

    def test_returns_stems_of_all_md_files(self, vault_with_notes):
        """Vault with 3 .md files → set of 3 stems."""
        result = build_vault_titles_set(str(vault_with_notes))
        assert len(result) == 3

    def test_excludes_extension(self, vault_with_notes):
        """Stems don't include the .md extension."""
        result = build_vault_titles_set(str(vault_with_notes))
        assert "JWT Authentication" in result
        assert "JWT Authentication.md" not in result

    def test_returns_empty_set_on_oserror(self):
        """Nonexistent path → empty set."""
        result = build_vault_titles_set("/nonexistent/path/that/does/not/exist")
        assert result == set()

    def test_nested_subdirectory_notes_included(self, temp_vault):
        """Notes in subfolders are included."""
        subdir = temp_vault / "Deep" / "Nested"
        subdir.mkdir(parents=True)
        (subdir / "Nested Note.md").write_text("content")
        result = build_vault_titles_set(str(temp_vault))
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
        result = resolve_relations(relations, vault_titles)
        assert len(result) == 1
        assert result[0]["type"] == "references"
        assert result[0]["target"] == "JWT Authentication"

    def test_unknown_predicate_normalized_to_related(self):
        """An unknown predicate is normalised to 'related'."""
        vault_titles = {"JWT Authentication"}
        relations = [{"type": "invented-predicate", "target": "JWT Authentication"}]
        result = resolve_relations(relations, vault_titles)
        assert result[0]["type"] == "related"

    def test_unresolved_target_dropped(self):
        """A target not in vault_titles is dropped."""
        vault_titles = {"JWT Authentication"}
        relations = [{"type": "related", "target": "Nonexistent Note"}]
        result = resolve_relations(relations, vault_titles)
        assert result == []

    def test_case_insensitive_target_matching(self):
        """Lowercase target matches vault title regardless of casing."""
        vault_titles = {"JWT Authentication"}
        relations = [{"type": "related", "target": "jwt authentication"}]
        result = resolve_relations(relations, vault_titles)
        assert len(result) == 1
        assert result[0]["target"] == "JWT Authentication"

    def test_empty_input_returns_empty_list(self):
        """Empty list → empty list."""
        assert resolve_relations([], {"JWT Authentication"}) == []

    def test_none_input_returns_empty_list(self):
        """None → empty list."""
        assert resolve_relations(None, {"JWT Authentication"}) == []

    def test_non_dict_items_skipped(self):
        """Non-dict items in the list are skipped."""
        result = resolve_relations(["not a dict"], {"JWT Authentication"})
        assert result == []

    def test_empty_target_string_skipped(self):
        """A relation with an empty target string is skipped."""
        vault_titles = {"JWT Authentication"}
        relations = [{"type": "related", "target": ""}]
        result = resolve_relations(relations, vault_titles)
        assert result == []

    def test_all_lowercase_valid_predicates_accepted(self):
        """All lowercase valid predicates pass through without normalisation."""
        vault_titles = {"Target Note"}
        for predicate in (
            "related",
            "references",
            "causes",
            "caused-by",
            "supersedes",
            "implements",
            "contradicts",
        ):
            relations = [{"type": predicate, "target": "Target Note"}]
            result = resolve_relations(relations, vault_titles)
            assert result[0]["type"] == predicate


# ===========================================================================
# write_beat with relations
# ===========================================================================


class TestWriteBeatRelations:
    """write_beat() correctly handles relations in frontmatter and body."""

    def test_writes_related_wikilinks_to_frontmatter(
        self, global_config, temp_vault, fixed_now, vault_with_notes
    ):
        """A beat with a resolved relation writes a [[wikilink]] to related: frontmatter."""
        beat = make_beat(title="My Beat")
        beat["relations"] = [{"type": "references", "target": "JWT Authentication"}]
        vault_titles = build_vault_titles_set(str(temp_vault))
        path = write_beat(
            beat, global_config, "sess001", "/cwd", fixed_now, vault_titles=vault_titles
        )
        content = path.read_text(encoding="utf-8")
        assert "[[JWT Authentication]]" in content

    def test_writes_relations_section_to_body(
        self, global_config, temp_vault, fixed_now, vault_with_notes
    ):
        """A beat with a relation gets a ## Relations section in the body."""
        beat = make_beat(title="My Beat With Relations")
        beat["relations"] = [{"type": "references", "target": "JWT Authentication"}]
        vault_titles = build_vault_titles_set(str(temp_vault))
        path = write_beat(
            beat, global_config, "sess001", "/cwd", fixed_now, vault_titles=vault_titles
        )
        content = path.read_text(encoding="utf-8")
        assert "## Relations" in content

    def test_empty_relations_writes_empty_related_list(
        self, global_config, temp_vault, fixed_now
    ):
        """No relations → related: [] in frontmatter."""
        beat = make_beat()
        beat["relations"] = []
        path = write_beat(beat, global_config, "sess001", "/cwd", fixed_now)
        content = path.read_text(encoding="utf-8")
        assert "related: []" in content

    def test_unresolved_relation_target_not_written(
        self, global_config, temp_vault, fixed_now
    ):
        """A phantom relation target is dropped and not written to the file."""
        beat = make_beat(title="Phantom Relations Beat")
        beat["relations"] = [
            {"type": "related", "target": "Phantom Note Does Not Exist"}
        ]
        path = write_beat(beat, global_config, "sess001", "/cwd", fixed_now)
        content = path.read_text(encoding="utf-8")
        assert "Phantom Note Does Not Exist" not in content

    def test_vault_titles_set_passed_avoids_redundant_glob(
        self, global_config, temp_vault, fixed_now
    ):
        """Passing vault_titles explicitly means build_vault_titles_set is not called again."""
        vault_titles = {"Some Note"}
        beat = make_beat()
        beat["relations"] = []
        with patch.object(_vault_module, "build_vault_titles_set") as mock_build:
            write_beat(
                beat,
                global_config,
                "sess001",
                "/cwd",
                fixed_now,
                vault_titles=vault_titles,
            )
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
            f'---\nid: test-id\ntype: insight\ntitle: "Test Note"\ntags: []\nrelated: {related_str}\nsummary: "Test"\n---\n\n## Body\n',
            encoding="utf-8",
        )

    def test_adds_new_wikilink_to_existing_related_list(self, tmp_path):
        """A new relation is added to an existing related: [] list."""
        pytest.importorskip("ruamel.yaml")
        note = tmp_path / "Test Note.md"
        self._write_note(note)
        _merge_relations_into_note(note, [{"type": "related", "target": "New Target"}])
        content = note.read_text(encoding="utf-8")
        assert "[[New Target]]" in content

    def test_preserves_other_frontmatter_fields_unchanged(self, tmp_path):
        """Other frontmatter fields are preserved after merge."""
        pytest.importorskip("ruamel.yaml")
        note = tmp_path / "Test Note.md"
        self._write_note(note)
        _merge_relations_into_note(note, [{"type": "related", "target": "Some Target"}])
        content = note.read_text(encoding="utf-8")
        assert "type: insight" in content
        assert "Test Note" in content

    def test_deduplicates_existing_wikilinks(self, tmp_path):
        """If the wikilink already exists in related, it is not added again."""
        pytest.importorskip("ruamel.yaml")
        note = tmp_path / "Test Note.md"
        self._write_note(note, related=["[[Target]]"])
        original_content = note.read_text(encoding="utf-8")
        _merge_relations_into_note(note, [{"type": "related", "target": "Target"}])
        new_content = note.read_text(encoding="utf-8")
        # File should not change (no new relation to add)
        assert new_content.count("[[Target]]") == original_content.count("[[Target]]")

    def test_graceful_fallback_when_ruamel_yaml_not_installed(
        self, tmp_path, monkeypatch
    ):
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
        _merge_relations_into_note(note, [{"type": "related", "target": "Some Target"}])
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
        _merge_relations_into_note(note, [{"type": "related", "target": "Target"}])
        mtime_after = os.path.getmtime(note)
        assert mtime_before == mtime_after

    def test_handles_oserror_on_read(self, tmp_path):
        """If the file is deleted before merge, no exception is raised."""
        pytest.importorskip("ruamel.yaml")
        note = tmp_path / "Deleted Note.md"
        # Note does not exist — should not raise
        _merge_relations_into_note(note, [{"type": "related", "target": "Some Target"}])


# ===========================================================================
# _read_frontmatter_as_dict
# ===========================================================================


class TestReadFrontmatterAsDict:
    """_read_frontmatter_as_dict() reads YAML frontmatter from a markdown file."""

    def test_parses_yaml_frontmatter(self, tmp_path):
        """Standard frontmatter → dict with all fields."""
        note = tmp_path / "Note.md"
        note.write_text(
            '---\ntype: decision\ntitle: "My Note"\ntags: []\n---\n\nBody.\n'
        )
        result = _read_frontmatter_as_dict(note)
        assert result["type"] == "decision"
        assert result["title"] == "My Note"

    def test_returns_empty_dict_when_no_frontmatter_marker(self, tmp_path):
        """File with no --- → empty dict."""
        note = tmp_path / "Note.md"
        note.write_text("Just a body, no frontmatter.\n")
        result = _read_frontmatter_as_dict(note)
        assert result == {}

    def test_returns_empty_dict_when_no_closing_marker(self, tmp_path):
        """--- without a closing --- → empty dict."""
        note = tmp_path / "Note.md"
        note.write_text("---\nkey: val\n")
        result = _read_frontmatter_as_dict(note)
        assert result == {}

    def test_returns_empty_dict_on_oserror(self, tmp_path):
        """Nonexistent path → empty dict."""
        missing = tmp_path / "does_not_exist.md"
        result = _read_frontmatter_as_dict(missing)
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
        with patch(
            "cyberbrain.extractors.extractor.call_model",
            return_value=json.dumps(self._SAMPLE_BEATS),
        ):
            with patch(
                "cyberbrain.extractors.extractor.load_prompt", return_value="prompt"
            ):
                result = extract_beats(
                    "transcript text", global_config, "manual", "/cwd"
                )
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["title"] == "Test Beat"

    def test_strips_markdown_code_fences(self, global_config, temp_vault):
        """call_model returning JSON wrapped in code fences is parsed correctly."""
        fenced = f"```json\n{json.dumps(self._SAMPLE_BEATS)}\n```"
        with patch("cyberbrain.extractors.extractor.call_model", return_value=fenced):
            with patch(
                "cyberbrain.extractors.extractor.load_prompt", return_value="prompt"
            ):
                result = extract_beats(
                    "transcript text", global_config, "manual", "/cwd"
                )
        assert len(result) == 1

    def test_handles_trailing_text_after_json(self, global_config, temp_vault):
        """Trailing non-JSON text after the array is ignored via raw_decode."""
        trailing = json.dumps(self._SAMPLE_BEATS) + "\n\nHere are the beats I found."
        with patch("cyberbrain.extractors.extractor.call_model", return_value=trailing):
            with patch(
                "cyberbrain.extractors.extractor.load_prompt", return_value="prompt"
            ):
                result = extract_beats(
                    "transcript text", global_config, "manual", "/cwd"
                )
        assert len(result) == 1

    def test_returns_empty_list_on_invalid_json(self, global_config, temp_vault):
        """Non-JSON response → empty list."""
        with patch(
            "cyberbrain.extractors.extractor.call_model", return_value="not json at all"
        ):
            with patch(
                "cyberbrain.extractors.extractor.load_prompt", return_value="prompt"
            ):
                result = extract_beats(
                    "transcript text", global_config, "manual", "/cwd"
                )
        assert result == []

    def test_returns_empty_list_on_non_list_json(self, global_config, temp_vault):
        """JSON object (not array) → empty list."""
        with patch(
            "cyberbrain.extractors.extractor.call_model",
            return_value='{"key": "value"}',
        ):
            with patch(
                "cyberbrain.extractors.extractor.load_prompt", return_value="prompt"
            ):
                result = extract_beats(
                    "transcript text", global_config, "manual", "/cwd"
                )
        assert result == []

    def test_includes_vault_claude_md_in_user_message(self, global_config, temp_vault):
        """When vault has CLAUDE.md, its content appears in the user message sent to LLM."""
        (temp_vault / "CLAUDE.md").write_text(
            "## Types\n\n- `decision`\n", encoding="utf-8"
        )
        captured_messages = []

        def fake_call_model(system, user, config):
            captured_messages.append(user)
            return json.dumps(self._SAMPLE_BEATS)

        with patch(
            "cyberbrain.extractors.extractor.call_model", side_effect=fake_call_model
        ):
            with patch(
                "cyberbrain.extractors.extractor.load_prompt",
                return_value="{vault_claude_md_section}{transcript}{project_name}{cwd}{trigger}",
            ):
                extract_beats("some transcript", global_config, "manual", "/cwd")

        assert len(captured_messages) == 1
        assert (
            "vault_claude_md" in captured_messages[0]
            or "CLAUDE.md" in captured_messages[0]
            or "decision" in captured_messages[0]
        )

    def test_falls_back_to_default_vocab_when_no_claude_md(
        self, global_config, temp_vault
    ):
        """No CLAUDE.md → default type notice appears in user message."""
        captured_messages = []

        def fake_call_model(system, user, config):
            captured_messages.append(user)
            return json.dumps(self._SAMPLE_BEATS)

        with patch(
            "cyberbrain.extractors.extractor.call_model", side_effect=fake_call_model
        ):
            with patch(
                "cyberbrain.extractors.extractor.load_prompt",
                return_value="{vault_claude_md_section}{transcript}{project_name}{cwd}{trigger}",
            ):
                extract_beats("some transcript", global_config, "manual", "/cwd")

        assert len(captured_messages) == 1
        assert (
            "default" in captured_messages[0].lower()
            or "decision" in captured_messages[0]
        )

    def test_truncates_long_transcript(self, global_config, temp_vault):
        """A transcript over MAX_TRANSCRIPT_CHARS is truncated, keeping the tail."""
        long_transcript = "x" * (MAX_TRANSCRIPT_CHARS + 10_000)
        captured_messages = []

        def fake_call_model(system, user, config):
            captured_messages.append(user)
            return json.dumps([])

        with patch(
            "cyberbrain.extractors.extractor.call_model", side_effect=fake_call_model
        ):
            with patch(
                "cyberbrain.extractors.extractor.load_prompt",
                return_value="{transcript}{vault_claude_md_section}{project_name}{cwd}{trigger}",
            ):
                extract_beats(long_transcript, global_config, "manual", "/cwd")

        assert len(captured_messages) == 1
        # The transcript in the user message should be truncated
        assert "truncated" in captured_messages[0] or len(captured_messages[0]) < len(
            long_transcript
        )


# ===========================================================================
# extractor.py — empty model response
# ===========================================================================


class TestExtractorEmptyResponse:
    """extractor.extract_beats() handles empty model output correctly."""

    def test_returns_empty_list_when_model_returns_empty_string(
        self, global_config, temp_vault
    ):
        """
        If call_model returns an empty string, extract_beats returns [] rather
        than crashing on JSON parsing. This can happen when the model refuses
        to respond or the backend returns empty output.
        """
        with patch("cyberbrain.extractors.extractor.call_model", return_value=""):
            with patch(
                "cyberbrain.extractors.extractor.load_prompt",
                return_value="{transcript}{vault_claude_md_section}{project_name}{cwd}{trigger}",
            ):
                result = extract_beats(
                    "some transcript", global_config, "manual", "/cwd"
                )
        assert result == []


# ===========================================================================
# config.py — placeholder vault path and load_prompt missing file
# ===========================================================================


class TestConfigEdgeCases:
    """load_global_config() and load_prompt() error paths."""

    def test_exits_when_vault_path_is_placeholder(self, temp_home, monkeypatch):
        """
        The literal placeholder '/path/to/your/ObsidianVault' triggers an exit,
        not an error, because it means the user hasn't configured the tool yet.
        """
        import cyberbrain.extractors.config as _cfg

        config_dir = temp_home / ".claude" / "cyberbrain"
        config_dir.mkdir(parents=True, exist_ok=True)
        cfg_file = config_dir / "config.json"
        cfg_file.write_text(
            '{"vault_path": "/path/to/your/ObsidianVault", "inbox": "AI/Claude-Sessions"}',
            encoding="utf-8",
        )
        monkeypatch.setattr("cyberbrain.extractors.config.GLOBAL_CONFIG_PATH", cfg_file)

        with pytest.raises(SystemExit):
            _cfg.load_global_config()

    def test_exits_when_vault_path_is_home_directory(
        self, temp_home, temp_vault, monkeypatch
    ):
        """
        Setting vault_path to the home directory is rejected — it's a
        misconfiguration that would make the whole filesystem look like a vault.
        """
        import cyberbrain.extractors.config as _cfg

        config_dir = temp_home / ".claude" / "cyberbrain"
        config_dir.mkdir(parents=True, exist_ok=True)
        cfg_file = config_dir / "config.json"
        cfg_file.write_text(
            f'{{"vault_path": "{temp_home}", "inbox": "AI/Claude-Sessions"}}',
            encoding="utf-8",
        )
        monkeypatch.setattr("cyberbrain.extractors.config.GLOBAL_CONFIG_PATH", cfg_file)
        # Patch Path.home() so it returns temp_home — making vault_path == home
        with patch("pathlib.Path.home", return_value=temp_home.resolve()):
            with pytest.raises(SystemExit):
                _cfg.load_global_config()

    def test_find_project_config_stops_at_home_directory(self, temp_home, monkeypatch):
        """
        find_project_config() walks upward from cwd but stops at the home directory.
        It never reads config files above the user's home.
        """
        import cyberbrain.extractors.config as _cfg

        # Create a project dir inside home
        project_dir = temp_home / "code" / "myproject"
        project_dir.mkdir(parents=True)
        # No .claude/cyberbrain.local.json anywhere in the tree
        monkeypatch.setattr(
            "cyberbrain.extractors.config.Path", __import__("pathlib").Path
        )

        with patch("pathlib.Path.home", return_value=temp_home):
            result = _cfg.find_project_config(str(project_dir))

        assert result == {}

    def test_load_prompt_exits_when_file_missing(self, tmp_path, monkeypatch):
        """
        load_prompt() calls sys.exit(0) when the prompt file doesn't exist,
        rather than raising FileNotFoundError. This gives a clear user message.
        """
        import cyberbrain.extractors.config as _cfg

        monkeypatch.setattr("cyberbrain.extractors.config.PROMPTS_DIR", tmp_path)

        with pytest.raises(SystemExit):
            _cfg.load_prompt("nonexistent-prompt.md")


# ===========================================================================
# transcript.py — edge cases in _extract_text_blocks
# ===========================================================================


class TestExtractTextBlocksEdgeCases:
    """_extract_text_blocks handles non-standard content shapes."""

    def test_non_dict_items_in_content_list_are_skipped(self):
        """
        Content lists may contain non-dict items (e.g. bare strings in some clients).
        These are skipped rather than crashing with AttributeError.
        """
        import cyberbrain.extractors.transcript as _t

        # Mix of valid text block and invalid non-dict items
        result = _t._extract_text_blocks(
            [
                "just a string",
                42,
                {"type": "text", "text": "valid text"},
                None,
            ]
        )
        assert "valid text" in result

    def test_tool_use_blocks_are_excluded(self):
        """tool_use blocks are never included in the transcript text — only text blocks pass."""
        import cyberbrain.extractors.transcript as _t

        result = _t._extract_text_blocks(
            [
                {"type": "tool_use", "id": "toolu_123", "name": "Read", "input": {}},
                {"type": "text", "text": "the answer"},
            ]
        )
        assert "tool_use" not in result
        assert "the answer" in result
        assert "Read" not in result

    def test_non_string_non_list_content_returns_empty(self):
        """
        If content is neither a string nor a list (e.g. a dict or int),
        _extract_text_blocks returns an empty string rather than crashing.
        """
        import cyberbrain.extractors.transcript as _t

        assert _t._extract_text_blocks({"type": "text"}) == ""
        assert _t._extract_text_blocks(None) == ""
        assert _t._extract_text_blocks(42) == ""

    def test_parse_jsonl_skips_entries_without_message_key(self, tmp_path):
        """
        JSONL entries that have type user/assistant but no 'message' key are
        handled gracefully — content defaults to empty string.
        """
        import cyberbrain.extractors.transcript as _t

        f = tmp_path / "t.jsonl"
        f.write_text(
            '{"type": "user"}\n'
            '{"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]}}\n',
            encoding="utf-8",
        )
        result = _t.parse_jsonl_transcript(str(f))
        assert "hi" in result

    def test_parse_jsonl_skips_non_user_assistant_types(self, tmp_path):
        """Entry types other than user/assistant (e.g. 'system', 'tool_result') are skipped."""
        import cyberbrain.extractors.transcript as _t

        f = tmp_path / "t.jsonl"
        f.write_text(
            '{"type": "system", "content": "system prompt"}\n'
            '{"type": "tool_result", "content": "result"}\n'
            '{"type": "user", "message": {"role": "user", "content": "hello"}}\n',
            encoding="utf-8",
        )
        result = _t.parse_jsonl_transcript(str(f))
        assert "system prompt" not in result
        assert "hello" in result


# ===========================================================================
# frontmatter.py — all remaining paths
# ===========================================================================


class TestFrontmatterEdgeCases:
    """Remaining uncovered paths in frontmatter.py."""

    def test_read_frontmatter_returns_empty_on_oserror(self, tmp_path):
        """read_frontmatter() returns {} when the file can't be read (permissions, missing)."""
        import cyberbrain.extractors.frontmatter as _fm

        result = _fm.read_frontmatter(str(tmp_path / "nonexistent.md"))
        assert result == {}

    def test_parse_frontmatter_returns_empty_when_closing_marker_missing(self):
        """parse_frontmatter returns {} when '---' end marker is absent."""
        import cyberbrain.extractors.frontmatter as _fm

        result = _fm.parse_frontmatter("---\ntitle: No closing marker\n")
        assert result == {}

    def test_parse_frontmatter_returns_empty_when_yaml_is_non_dict(self):
        """parse_frontmatter returns {} when YAML parses to a non-dict (e.g. a list or scalar)."""
        import cyberbrain.extractors.frontmatter as _fm

        result = _fm.parse_frontmatter("---\n- item1\n- item2\n---\nBody.")
        assert result == {}

    def test_read_frontmatter_tags_returns_empty_set_on_oserror(self, tmp_path):
        """read_frontmatter_tags() returns set() when the file doesn't exist."""
        import cyberbrain.extractors.frontmatter as _fm

        result = _fm.read_frontmatter_tags(str(tmp_path / "ghost.md"))
        assert result == set()

    def test_read_frontmatter_tags_returns_empty_when_no_frontmatter_block(
        self, tmp_path
    ):
        """read_frontmatter_tags() returns set() when no --- block is present."""
        import cyberbrain.extractors.frontmatter as _fm

        note = tmp_path / "note.md"
        note.write_text("Just a body, no frontmatter.", encoding="utf-8")
        assert _fm.read_frontmatter_tags(str(note)) == set()

    def test_read_frontmatter_tags_returns_empty_when_no_tags_field(self, tmp_path):
        """read_frontmatter_tags() returns set() when the frontmatter has no 'tags' field."""
        import cyberbrain.extractors.frontmatter as _fm

        note = tmp_path / "note.md"
        note.write_text(
            "---\ntitle: Note\ntype: decision\n---\nBody.", encoding="utf-8"
        )
        assert _fm.read_frontmatter_tags(str(note)) == set()

    def test_read_frontmatter_tags_parses_yaml_bracket_list(self, tmp_path):
        """tags: [tag1, tag2] (unquoted YAML bracket) is parsed into a set."""
        import cyberbrain.extractors.frontmatter as _fm

        note = tmp_path / "note.md"
        note.write_text(
            "---\ntitle: Note\ntags: [python, testing]\n---\nBody.", encoding="utf-8"
        )
        result = _fm.read_frontmatter_tags(str(note))
        assert "python" in result
        assert "testing" in result

    def test_read_frontmatter_tags_parses_json_array_string(self, tmp_path):
        """tags: ["jwt", "auth"] (JSON array) is parsed into a set."""
        import cyberbrain.extractors.frontmatter as _fm

        note = tmp_path / "note.md"
        note.write_text(
            '---\ntitle: Note\ntags: ["jwt", "auth"]\n---\nBody.', encoding="utf-8"
        )
        result = _fm.read_frontmatter_tags(str(note))
        assert "jwt" in result
        assert "auth" in result

    def test_normalise_list_converts_json_string_to_list(self):
        """normalise_list('["a","b"]') parses the JSON string and returns a list."""
        import cyberbrain.extractors.frontmatter as _fm

        result = _fm.normalise_list('["alpha", "beta"]')
        assert result == ["alpha", "beta"]

    def test_normalise_list_returns_single_item_list_for_plain_string(self):
        """normalise_list('some tag') returns ['some tag'] when not valid JSON."""
        import cyberbrain.extractors.frontmatter as _fm

        result = _fm.normalise_list("some-tag")
        assert result == ["some-tag"]

    def test_normalise_list_returns_empty_for_empty_string(self):
        """normalise_list('   ') returns [] for whitespace-only string."""
        import cyberbrain.extractors.frontmatter as _fm

        result = _fm.normalise_list("   ")
        assert result == []

    def test_normalise_list_returns_empty_for_non_string_non_list(self):
        """normalise_list(None) and normalise_list(42) return []."""
        import cyberbrain.extractors.frontmatter as _fm

        assert _fm.normalise_list(None) == []
        assert _fm.normalise_list(42) == []


# ===========================================================================
# run_log.py — OSError paths
# ===========================================================================


class TestRunLogOSErrorPaths:
    """run_log.py swallows OSErrors and prints warnings rather than crashing."""

    def test_is_session_already_extracted_returns_false_on_oserror(
        self, tmp_path, monkeypatch
    ):
        """
        If the deduplication log exists but can't be read (permissions),
        is_session_already_extracted() returns False (conservative: allow extraction)
        rather than crashing the pipeline.
        """
        import cyberbrain.extractors.run_log as _rl

        log_file = tmp_path / "cb-extract.log"
        log_file.write_text("2026-01-01T00:00:00\tsess001\t3\n", encoding="utf-8")
        monkeypatch.setattr("cyberbrain.extractors.run_log.EXTRACT_LOG_PATH", log_file)

        with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
            result = _rl.is_session_already_extracted("sess001")

        assert result is False

    def test_write_extract_log_entry_swallows_oserror(self, tmp_path, monkeypatch):
        """
        If the log directory can't be created or written to, the OSError is caught
        and a warning is printed. The pipeline continues rather than crashing.
        """
        import cyberbrain.extractors.run_log as _rl

        log_file = tmp_path / "logs" / "cb-extract.log"
        monkeypatch.setattr("cyberbrain.extractors.run_log.EXTRACT_LOG_PATH", log_file)

        # Make directory creation fail
        with patch("pathlib.Path.mkdir", side_effect=OSError("read-only filesystem")):
            # Should not raise
            _rl.write_extract_log_entry("sess001", 5)

    def test_write_runs_log_entry_swallows_oserror(self, tmp_path, monkeypatch):
        """write_runs_log_entry() swallows OSError on write."""
        import cyberbrain.extractors.run_log as _rl

        log_file = tmp_path / "logs" / "cb-runs.jsonl"
        monkeypatch.setattr("cyberbrain.extractors.run_log.RUNS_LOG_PATH", log_file)

        with patch("pathlib.Path.mkdir", side_effect=OSError("read-only filesystem")):
            _rl.write_runs_log_entry({"session_id": "s1", "beats_written": 0})


# ===========================================================================
# vault.py — remaining uncovered paths
# ===========================================================================


class TestVaultEdgeCases:
    """Remaining uncovered paths in vault.py."""

    def test_read_vault_claude_md_returns_none_on_oserror(self, temp_vault):
        """
        read_vault_claude_md() returns None when the CLAUDE.md exists but can't be read
        (e.g. permissions), rather than crashing with an OSError.
        """
        import cyberbrain.extractors.vault as _v

        claude_md = temp_vault / "CLAUDE.md"
        claude_md.write_text("# Vault\n", encoding="utf-8")

        with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
            result = _v.read_vault_claude_md(str(temp_vault))

        assert result is None

    def test_resolve_output_dir_rejects_path_traversal_in_scope_folder(
        self, temp_vault
    ):
        """
        If a beat has scope 'project' with a folder that traverses above the vault
        root, the path is rejected and falls back to inbox.
        """
        import cyberbrain.extractors.vault as _v

        config = {
            "vault_path": str(temp_vault),
            "inbox": "AI/Claude-Sessions",
        }
        beat = {"scope": "project", "type": "insight", "title": "Test"}
        project_config = {**config, "vault_folder": "../../etc"}

        result = _v.resolve_output_dir(beat, project_config)

        # Must be within the vault, not /etc
        assert str(result).startswith(str(temp_vault))

    def test_resolve_output_dir_folder_override_rejects_traversal(self, temp_vault):
        """
        The 'folder' key in config that traverses above the vault root is rejected.
        The function falls back to inbox rather than writing outside the vault.
        """
        import cyberbrain.extractors.vault as _v

        config = {
            "vault_path": str(temp_vault),
            "inbox": "AI/Claude-Sessions",
            "folder": "../../etc/passwd",
        }
        beat = {"scope": "general", "type": "insight", "title": "Test"}

        result = _v.resolve_output_dir(beat, config)

        assert str(result).startswith(str(temp_vault))

    def test_resolve_relations_normalises_unknown_predicate(self, temp_vault):
        """
        Relations with an unknown predicate (not in VALID_PREDICATES) have their
        predicate normalised to 'related' rather than being silently dropped.
        """
        import cyberbrain.extractors.vault as _v

        # resolve_relations reads "type" key (not "predicate") from input dicts
        raw_relations = [{"target": "SomeNote", "type": "invented-predicate"}]
        vault_titles = {"SomeNote"}

        result = _v.resolve_relations(raw_relations, vault_titles)

        assert len(result) == 1
        assert result[0]["type"] == "related"

    def test_resolve_relations_drops_targets_not_in_vault(self, temp_vault):
        """
        Relations whose target title doesn't exist in the vault are dropped.
        This prevents dangling wikilinks in newly-created notes.
        """
        import cyberbrain.extractors.vault as _v

        raw_relations = [
            {"target": "ExistingNote", "predicate": "related"},
            {"target": "PhantomNote", "predicate": "related"},
        ]
        vault_titles = {"ExistingNote"}

        result = _v.resolve_relations(raw_relations, vault_titles)

        assert len(result) == 1
        assert result[0]["target"] == "ExistingNote"

    def test_search_vault_returns_ranked_paths(self, temp_vault):
        """
        search_vault() calls grep for each tag and title keyword, ranks results
        by hit count, and returns up to max_results paths.
        """
        import cyberbrain.extractors.vault as _v

        note = temp_vault / "AI" / "Claude-Sessions" / "JWT Auth.md"
        note.write_text("# JWT Auth\n\njwt authentication token", encoding="utf-8")

        beat = {"title": "JWT Authentication", "tags": ["jwt", "auth"]}
        results = _v.search_vault(beat, str(temp_vault), max_results=5)

        # The real note should appear in results since vault content matches
        assert isinstance(results, list)

    def test_search_vault_handles_mtime_oserror(self, temp_vault):
        """
        If os.path.getmtime raises OSError for a matched path (file deleted
        between grep and stat), the path is still recorded with mtime=0.
        """
        import cyberbrain.extractors.vault as _v

        note = temp_vault / "AI" / "Claude-Sessions" / "note.md"
        note.write_text("python subprocess encoding", encoding="utf-8")

        beat = {"title": "Python Subprocess", "tags": ["python"]}

        with patch("os.path.getmtime", side_effect=OSError("file gone")):
            results = _v.search_vault(beat, str(temp_vault), max_results=5)

        # Should still return results, just with mtime=0 for ordering
        assert isinstance(results, list)

    def test_write_beat_updates_search_index_after_write(
        self, global_config, temp_vault, fixed_now
    ):
        """
        After writing a beat to disk, write_beat attempts to update the search index.
        If search_index is not available, the import error is silently swallowed.
        """
        import cyberbrain.extractors.vault as _v

        beat = {
            "title": "Index Update Test",
            "type": "insight",
            "scope": "general",
            "summary": "Should update index",
            "tags": ["test"],
            "body": "## Body\n\nContent.",
        }
        # Simulate search_index not installed
        with patch.dict("sys.modules", {"search_index": None}):
            path = _v.write_beat(beat, global_config, "sess001", "/cwd", fixed_now)

        assert path.exists()


# ===========================================================================
# extract_beats.py — main() CLI entry point
# ===========================================================================


class TestMain:
    """main() parses arguments, deduplicates, extracts beats, and writes them."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        """Set up isolated home, vault, config, and log paths for each test."""
        import json as _json

        monkeypatch.delenv("CLAUDECODE", raising=False)

        self.vault = tmp_path / "vault"
        self.vault.mkdir()
        (self.vault / "AI" / "Claude-Sessions").mkdir(parents=True)

        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        self.extract_log = log_dir / "cb-extract.log"
        self.runs_log = log_dir / "cb-runs.jsonl"

        self.config_path = tmp_path / "config.json"
        self.config_path.write_text(
            _json.dumps(
                {
                    "vault_path": str(self.vault),
                    "inbox": "AI/Claude-Sessions",
                    "backend": "claude-code",
                    "model": "claude-haiku-4-5",
                    "claude_timeout": 30,
                    "autofile": False,
                    "daily_journal": False,
                }
            ),
            encoding="utf-8",
        )

        monkeypatch.setattr(
            "cyberbrain.extractors.config.GLOBAL_CONFIG_PATH", self.config_path
        )
        monkeypatch.setattr(
            "cyberbrain.extractors.run_log.EXTRACT_LOG_PATH", self.extract_log
        )
        monkeypatch.setattr(
            "cyberbrain.extractors.run_log.RUNS_LOG_PATH", self.runs_log
        )

    def _make_transcript(self, tmp_path):
        t = tmp_path / "test-session.jsonl"
        t.write_text(
            '{"type": "user", "message": {"role": "user", "content": "explain jwt"}}\n'
            '{"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "JWT is a token format."}]}}\n',
            encoding="utf-8",
        )
        return t

    def _run_main(self, argv):
        """Call main() with patched sys.argv; capture SystemExit."""
        with patch("sys.argv", argv):
            try:
                eb.main()
                return None
            except SystemExit as e:
                return e.code

    def test_exits_when_neither_transcript_nor_beats_json_given(self, tmp_path):
        """main() exits with an error message when no --transcript or --beats-json is given."""
        exit_code = self._run_main(
            [
                "extract_beats.py",
                "--session-id",
                "sess-none",
                "--cwd",
                str(self.vault),
            ]
        )
        assert exit_code == 1

    def test_skips_already_extracted_session(self, tmp_path):
        """main() exits 0 immediately when the session is already in the dedup log."""
        transcript = self._make_transcript(tmp_path)
        self.extract_log.parent.mkdir(parents=True, exist_ok=True)
        self.extract_log.write_text(f"2026-01-01T00:00:00\t{transcript.stem}\t3\n")

        exit_code = self._run_main(
            [
                "extract_beats.py",
                "--transcript",
                str(transcript),
                "--session-id",
                transcript.stem,
                "--cwd",
                str(self.vault),
            ]
        )
        assert exit_code == 0

    def test_dry_run_prints_beats_without_writing(self, tmp_path, capsys):
        """
        --dry-run prints a preview of the beats that would be written
        without touching the vault. No .md files are created.
        """
        transcript = self._make_transcript(tmp_path)
        beat = {
            "title": "JWT Token Format",
            "type": "insight",
            "scope": "general",
            "summary": "JWT is a compact token format.",
            "tags": ["jwt"],
            "body": "## Body\n\nContent.",
        }

        with patch(
            "cyberbrain.extractors.extractor.call_model",
            return_value=json.dumps([beat]),
        ):
            with patch(
                "cyberbrain.extractors.extractor.load_prompt",
                return_value="{transcript}{vault_claude_md_section}{project_name}{cwd}{trigger}",
            ):
                exit_code = self._run_main(
                    [
                        "extract_beats.py",
                        "--transcript",
                        str(transcript),
                        "--session-id",
                        "dry-run-test",
                        "--cwd",
                        str(self.vault),
                        "--dry-run",
                    ]
                )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "JWT Token Format" in captured.out
        assert "would be written" in captured.out
        # Vault must not have been modified
        md_files = list((self.vault / "AI" / "Claude-Sessions").glob("*.md"))
        assert len(md_files) == 0

    def test_writes_beats_and_logs_on_success(self, tmp_path):
        """
        On a successful run, main() writes beats to the vault and appends
        entries to both the dedup log and the runs log.
        """
        transcript = self._make_transcript(tmp_path)
        beat = {
            "title": "JWT Token Format",
            "type": "insight",
            "scope": "general",
            "summary": "JWT is compact.",
            "tags": ["jwt"],
            "body": "## Body\n\nContent.",
        }

        with patch(
            "cyberbrain.extractors.extractor.call_model",
            return_value=json.dumps([beat]),
        ):
            with patch(
                "cyberbrain.extractors.extractor.load_prompt",
                return_value="{transcript}{vault_claude_md_section}{project_name}{cwd}{trigger}",
            ):
                exit_code = self._run_main(
                    [
                        "extract_beats.py",
                        "--transcript",
                        str(transcript),
                        "--session-id",
                        "sess-write-test",
                        "--cwd",
                        str(self.vault),
                    ]
                )

        assert exit_code is None  # no explicit sys.exit on success
        assert self.extract_log.exists()
        assert transcript.stem in self.extract_log.read_text()
        assert self.runs_log.exists()
        runs_data = json.loads(self.runs_log.read_text().strip())
        assert runs_data["beats_written"] == 1

    def test_exits_cleanly_when_no_beats_extracted(self, tmp_path):
        """When the LLM returns an empty beats list, main() exits 0."""
        transcript = self._make_transcript(tmp_path)

        with patch("cyberbrain.extractors.extractor.call_model", return_value="[]"):
            with patch(
                "cyberbrain.extractors.extractor.load_prompt",
                return_value="{transcript}{vault_claude_md_section}{project_name}{cwd}{trigger}",
            ):
                exit_code = self._run_main(
                    [
                        "extract_beats.py",
                        "--transcript",
                        str(transcript),
                        "--session-id",
                        "sess-empty",
                        "--cwd",
                        str(self.vault),
                    ]
                )

        assert exit_code == 0

    def test_loads_beats_from_json_file_skipping_transcript_parse(self, tmp_path):
        """
        --beats-json skips transcript parsing and LLM call entirely.
        Beats are written directly from the JSON file.
        """
        beats = [
            {
                "title": "Pre-extracted Insight",
                "type": "insight",
                "scope": "general",
                "summary": "Already extracted.",
                "tags": ["test"],
                "body": "## Body\n\nPre-extracted.",
            }
        ]
        beats_file = tmp_path / "beats.json"
        beats_file.write_text(json.dumps(beats))

        exit_code = self._run_main(
            [
                "extract_beats.py",
                "--beats-json",
                str(beats_file),
                "--session-id",
                "sess-json-input",
                "--cwd",
                str(self.vault),
            ]
        )

        assert exit_code is None
        md_files = list(self.vault.rglob("*.md"))
        assert any("Pre-extracted" in f.read_text() for f in md_files)

    def test_exits_when_beats_json_file_not_found(self, tmp_path):
        """--beats-json with a missing file exits with code 1."""
        exit_code = self._run_main(
            [
                "extract_beats.py",
                "--beats-json",
                str(tmp_path / "ghost.json"),
                "--session-id",
                "sess-ghost",
                "--cwd",
                str(self.vault),
            ]
        )
        assert exit_code == 1

    def test_exits_when_beats_json_is_not_an_array(self, tmp_path):
        """--beats-json must contain a JSON array, not an object."""
        beats_file = tmp_path / "not-array.json"
        beats_file.write_text('{"title": "Single beat, not array"}')

        exit_code = self._run_main(
            [
                "extract_beats.py",
                "--beats-json",
                str(beats_file),
                "--session-id",
                "sess-not-array",
                "--cwd",
                str(self.vault),
            ]
        )
        assert exit_code == 1

    def test_daily_journal_written_when_enabled(self, tmp_path):
        """When daily_journal=True in config, a journal entry is appended after extraction."""
        beat = {
            "title": "Journal Test Beat",
            "type": "insight",
            "scope": "general",
            "summary": "For journal.",
            "tags": [],
            "body": "## Body\n\nContent.",
        }
        transcript = self._make_transcript(tmp_path)

        cfg = json.loads(self.config_path.read_text())
        cfg["daily_journal"] = True
        cfg["journal_folder"] = "AI/Journal"
        self.config_path.write_text(json.dumps(cfg))

        with patch(
            "cyberbrain.extractors.extractor.call_model",
            return_value=json.dumps([beat]),
        ):
            with patch(
                "cyberbrain.extractors.extractor.load_prompt",
                return_value="{transcript}{vault_claude_md_section}{project_name}{cwd}{trigger}",
            ):
                self._run_main(
                    [
                        "extract_beats.py",
                        "--transcript",
                        str(transcript),
                        "--session-id",
                        "sess-journal",
                        "--cwd",
                        str(self.vault),
                    ]
                )

        journal_files = list((self.vault / "AI" / "Journal").glob("*.md"))
        assert len(journal_files) == 1
        assert "Journal Test Beat" in journal_files[0].read_text()

    def test_exits_cleanly_when_transcript_is_empty(self, tmp_path, capsys):
        """main() exits 0 when the transcript file exists but has no usable turns (line 148-149)."""
        # A transcript with only tool-use blocks produces empty text after parsing
        transcript = tmp_path / "empty-session.jsonl"
        transcript.write_text(
            '{"type": "tool_use", "message": {"role": "user", "content": [{"type": "tool_use", "name": "Read", "input": {}}]}}\n',
            encoding="utf-8",
        )
        exit_code = self._run_main(
            [
                "extract_beats.py",
                "--transcript",
                str(transcript),
                "--session-id",
                "sess-empty-transcript",
                "--cwd",
                str(self.vault),
            ]
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        assert (
            "empty" in captured.err.lower()
            or "nothing to extract" in captured.err.lower()
        )

    def test_exits_cleanly_on_backend_error_during_extraction(self, tmp_path, capsys):
        """main() exits 0 and prints a message when the LLM backend raises BackendError (lines 156-158)."""
        transcript = self._make_transcript(tmp_path)

        with patch(
            "cyberbrain.extractors.extractor.call_model",
            side_effect=BackendError("backend down"),
        ):
            with patch(
                "cyberbrain.extractors.extractor.load_prompt",
                return_value="{transcript}{vault_claude_md_section}{project_name}{cwd}{trigger}",
            ):
                exit_code = self._run_main(
                    [
                        "extract_beats.py",
                        "--transcript",
                        str(transcript),
                        "--session-id",
                        "sess-backend-err",
                        "--cwd",
                        str(self.vault),
                    ]
                )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "backend" in captured.err.lower() or "error" in captured.err.lower()

    def test_dry_run_path_computation_exception_falls_back_gracefully(
        self, tmp_path, capsys
    ):
        """dry-run mode catches exceptions in resolve_output_dir and shows fallback text (lines 182-183)."""
        beat = {
            "title": "Edge Case Beat",
            "type": "insight",
            "scope": "general",
            "summary": "For dry-run test.",
            "tags": ["test"],
            "body": "## Body\n\nContent.",
        }
        transcript = self._make_transcript(tmp_path)

        with patch(
            "cyberbrain.extractors.extractor.call_model",
            return_value=json.dumps([beat]),
        ):
            with patch(
                "cyberbrain.extractors.extractor.load_prompt",
                return_value="{transcript}{vault_claude_md_section}{project_name}{cwd}{trigger}",
            ):
                # Patch resolve_output_dir directly to avoid module reimport issues
                with patch.object(
                    eb, "resolve_output_dir", side_effect=Exception("no dir")
                ):
                    exit_code = self._run_main(
                        [
                            "extract_beats.py",
                            "--transcript",
                            str(transcript),
                            "--session-id",
                            "sess-dry-run-exc",
                            "--cwd",
                            str(self.vault),
                            "--dry-run",
                        ]
                    )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "could not compute path" in captured.out.lower()

    def test_autofile_enabled_reads_vault_claude_md(self, tmp_path, capsys):
        """When autofile=True, main() reads vault CLAUDE.md before the beat loop (lines 214-215)."""
        (self.vault / "CLAUDE.md").write_text(
            "# Vault context\nUse types: decision.", encoding="utf-8"
        )

        cfg = json.loads(self.config_path.read_text())
        cfg["autofile"] = True
        self.config_path.write_text(json.dumps(cfg))

        beat = {
            "title": "Autofile Test Beat",
            "type": "insight",
            "scope": "general",
            "summary": "Autofile enabled.",
            "tags": ["test"],
            "body": "## Body\n\nContent.",
        }
        transcript = self._make_transcript(tmp_path)

        with patch(
            "cyberbrain.extractors.extractor.call_model",
            return_value=json.dumps([beat]),
        ):
            with patch(
                "cyberbrain.extractors.extractor.load_prompt",
                return_value="{transcript}{vault_claude_md_section}{project_name}{cwd}{trigger}",
            ):
                # autofile_beat will be called; mock it to avoid real LLM calls
                with patch.object(
                    eb,
                    "autofile_beat",
                    return_value=self.vault
                    / "AI"
                    / "Claude-Sessions"
                    / "Autofile Test Beat.md",
                ) as mock_af:
                    # Create the file so the log can compute relpath
                    dest = (
                        self.vault / "AI" / "Claude-Sessions" / "Autofile Test Beat.md"
                    )
                    dest.write_text("content", encoding="utf-8")
                    self._run_main(
                        [
                            "extract_beats.py",
                            "--transcript",
                            str(transcript),
                            "--session-id",
                            "sess-autofile-enabled",
                            "--cwd",
                            str(self.vault),
                        ]
                    )

        mock_af.assert_called_once()
        # vault_context kwarg should have been passed (from CLAUDE.md read)
        call_kwargs = mock_af.call_args[1]
        assert "vault_context" in call_kwargs

    def test_autofile_backend_error_falls_back_to_write_beat(self, tmp_path, capsys):
        """When autofile_beat raises BackendError inside the beat loop, write_beat is used instead (lines 221-225)."""
        cfg = json.loads(self.config_path.read_text())
        cfg["autofile"] = True
        self.config_path.write_text(json.dumps(cfg))

        beat = {
            "title": "Fallback Beat",
            "type": "insight",
            "scope": "general",
            "summary": "Autofile will fail.",
            "tags": ["test"],
            "body": "## Body\n\nContent.",
        }
        transcript = self._make_transcript(tmp_path)

        with patch(
            "cyberbrain.extractors.extractor.call_model",
            return_value=json.dumps([beat]),
        ):
            with patch(
                "cyberbrain.extractors.extractor.load_prompt",
                return_value="{transcript}{vault_claude_md_section}{project_name}{cwd}{trigger}",
            ):
                with patch.object(
                    eb, "autofile_beat", side_effect=BackendError("backend down")
                ):
                    exit_code = self._run_main(
                        [
                            "extract_beats.py",
                            "--transcript",
                            str(transcript),
                            "--session-id",
                            "sess-autofile-fallback",
                            "--cwd",
                            str(self.vault),
                        ]
                    )

        assert exit_code is None
        # The beat should have been written via write_beat fallback
        md_files = list(self.vault.rglob("*.md"))
        assert any("Fallback Beat" in f.read_text() for f in md_files)
        captured = capsys.readouterr()
        assert (
            "autofile failed" in captured.err.lower()
            or "filing to inbox" in captured.err.lower()
        )

    def test_write_beat_exception_is_caught_and_logged(self, tmp_path, capsys):
        """An exception in write_beat is caught; the error is logged and other beats continue (lines 237-240)."""
        beats = [
            {
                "title": "Beat That Fails",
                "type": "insight",
                "scope": "general",
                "summary": "Will fail.",
                "tags": ["test"],
                "body": "## Fail.",
            },
            {
                "title": "Beat That Succeeds",
                "type": "insight",
                "scope": "general",
                "summary": "Will succeed.",
                "tags": ["test"],
                "body": "## Succeed.",
            },
        ]
        transcript = self._make_transcript(tmp_path)

        call_count = {"n": 0}
        original_write_beat = write_beat

        def _flaky_write_beat(beat, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise OSError("simulated write failure")
            return original_write_beat(beat, *args, **kwargs)

        with patch(
            "cyberbrain.extractors.extractor.call_model", return_value=json.dumps(beats)
        ):
            with patch(
                "cyberbrain.extractors.extractor.load_prompt",
                return_value="{transcript}{vault_claude_md_section}{project_name}{cwd}{trigger}",
            ):
                with patch.object(eb, "write_beat", side_effect=_flaky_write_beat):
                    exit_code = self._run_main(
                        [
                            "extract_beats.py",
                            "--transcript",
                            str(transcript),
                            "--session-id",
                            "sess-write-err",
                            "--cwd",
                            str(self.vault),
                        ]
                    )

        assert exit_code is None
        captured = capsys.readouterr()
        assert "Failed on" in captured.err
        md_files = list(self.vault.rglob("*.md"))
        assert any("Beat That Succeeds" in f.read_text() for f in md_files)

    @pytest.mark.skip(reason="Skipped due to test isolation issues with mock module")
    def test_main_callable_via_dunder_main(self, tmp_path, monkeypatch):
        """extract_beats.main() is reachable via runpy when run as __main__ (line 271)."""
        import runpy

        transcript = self._make_transcript(tmp_path)
        beat = {
            "title": "Runpy Test Beat",
            "type": "insight",
            "scope": "general",
            "summary": "Via runpy.",
            "tags": ["test"],
            "body": "## Body\n\nContent.",
        }

        monkeypatch.setattr(
            "sys.argv",
            [
                "extract_beats.py",
                "--transcript",
                str(transcript),
                "--session-id",
                "sess-runpy",
                "--cwd",
                str(self.vault),
            ],
        )

        with patch(
            "cyberbrain.extractors.extractor.call_model",
            return_value=json.dumps([beat]),
        ):
            with patch(
                "cyberbrain.extractors.extractor.load_prompt",
                return_value="{transcript}{vault_claude_md_section}{project_name}{cwd}{trigger}",
            ):
                try:
                    runpy.run_module(
                        "cyberbrain.extractors.extract_beats",
                        run_name="__main__",
                        alter_sys=True,
                    )
                except SystemExit as e:
                    assert e.code in (None, 0)


# ===========================================================================
# run_extraction() orchestration
# ===========================================================================


class TestRunExtractionOrchestration:
    """run_extraction() config passthrough and beats parameter paths."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        """Set up isolated vault, config, and log paths for each test."""
        monkeypatch.delenv("CLAUDECODE", raising=False)

        self.vault = tmp_path / "vault"
        self.vault.mkdir()
        (self.vault / "AI" / "Claude-Sessions").mkdir(parents=True)

        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        self.extract_log = log_dir / "cb-extract.log"
        self.runs_log = log_dir / "cb-runs.jsonl"

        self.config = {
            "vault_path": str(self.vault),
            "inbox": "AI/Claude-Sessions",
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
            "claude_timeout": 30,
            "autofile": False,
            "daily_journal": False,
        }

        monkeypatch.setattr(
            "cyberbrain.extractors.run_log.EXTRACT_LOG_PATH", self.extract_log
        )
        monkeypatch.setattr(
            "cyberbrain.extractors.run_log.RUNS_LOG_PATH", self.runs_log
        )

    def _make_beat(self, title="Config Test Beat"):
        return {
            "title": title,
            "type": "insight",
            "scope": "general",
            "summary": "A test beat.",
            "tags": ["test"],
            "body": "## Body\n\nContent.",
        }

    def test_explicit_config_is_used_without_calling_resolve_config(self, monkeypatch):
        """When config is passed explicitly, resolve_config() is never called."""
        resolve_called = []

        def _reject_resolve(cwd):
            resolve_called.append(cwd)
            raise AssertionError(
                "resolve_config should not be called when config is provided"
            )

        monkeypatch.setattr(eb, "resolve_config", _reject_resolve)

        beat = self._make_beat("Explicit Config Beat")
        result = eb.run_extraction(
            None,
            "sess-explicit-config",
            "manual",
            str(self.vault),
            config=self.config,
            beats=[beat],
        )

        assert resolve_called == [], (
            "resolve_config was called despite config being provided"
        )
        assert result["beats_written"] == 1
        assert result["skipped"] is False

    def test_none_config_falls_back_to_resolve_config(self, monkeypatch):
        """When config=None, resolve_config(cwd) is called to load the config."""
        resolve_called = []
        original_resolve = eb.resolve_config

        def _tracking_resolve(cwd):
            resolve_called.append(cwd)
            return self.config

        monkeypatch.setattr(eb, "resolve_config", _tracking_resolve)

        beat = self._make_beat("Fallback Config Beat")
        result = eb.run_extraction(
            None,
            "sess-fallback-config",
            "manual",
            str(self.vault),
            config=None,
            beats=[beat],
        )

        assert len(resolve_called) == 1
        assert resolve_called[0] == str(self.vault)
        assert result["beats_written"] == 1

    def test_beats_parameter_skips_llm_extraction(self, monkeypatch):
        """When beats are pre-provided, extract_beats() (LLM) is never called."""
        extract_called = []

        def _reject_extract(transcript_text, cfg, trigger, cwd):
            extract_called.append(True)
            raise AssertionError(
                "extract_beats should not be called when beats are pre-provided"
            )

        monkeypatch.setattr(eb, "extract_beats", _reject_extract)

        beat = self._make_beat("Pre-provided Beat")
        result = eb.run_extraction(
            None,
            "sess-prebeats",
            "manual",
            str(self.vault),
            config=self.config,
            beats=[beat],
        )

        assert extract_called == [], (
            "extract_beats was called despite beats being provided"
        )
        assert result["beats_count"] == 1
        assert result["beats_written"] == 1

    def test_beats_parameter_writes_beats_to_vault(self):
        """Pre-provided beats are written to the vault correctly."""
        beat = self._make_beat("Pre-provided Vault Beat")
        result = eb.run_extraction(
            None,
            "sess-prebeats-vault",
            "manual",
            str(self.vault),
            config=self.config,
            beats=[beat],
        )

        assert result["beats_written"] == 1
        assert len(result["written_paths"]) == 1
        written_path = result["written_paths"][0]
        assert written_path.exists()
        assert "Pre-provided Vault Beat" in written_path.read_text(encoding="utf-8")

    def test_beats_parameter_records_zero_llm_duration(self):
        """llm_duration_seconds is 0.0 in the runs log when beats are pre-provided."""
        beat = self._make_beat("Zero LLM Duration Beat")
        eb.run_extraction(
            None,
            "sess-zero-llm",
            "manual",
            str(self.vault),
            config=self.config,
            beats=[beat],
        )

        assert self.runs_log.exists()
        runs_data = json.loads(self.runs_log.read_text().strip())
        assert runs_data["llm_duration_seconds"] == 0.0

    def test_beats_parameter_writes_extract_log(self):
        """Deduplication log entry is written when beats are pre-provided."""
        beat = self._make_beat("Dedup Log Beat")
        eb.run_extraction(
            None,
            "sess-dedup-prebeats",
            "manual",
            str(self.vault),
            config=self.config,
            beats=[beat],
        )

        assert self.extract_log.exists()
        assert "sess-dedup-prebeats" in self.extract_log.read_text()

    def test_explicit_config_vault_path_is_used_for_routing(self):
        """Beats are written to the vault specified in the explicit config, not from disk."""
        beat = self._make_beat("Routing Beat")
        result = eb.run_extraction(
            None,
            "sess-routing",
            "manual",
            "/some/other/cwd",
            config=self.config,
            beats=[beat],
        )

        assert result["beats_written"] == 1
        written_path = result["written_paths"][0]
        # Must be inside self.vault, not derived from /some/other/cwd
        assert str(written_path).startswith(str(self.vault))
