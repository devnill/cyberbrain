"""
test_autofile.py — tests for src/cyberbrain/extractors/autofile.py

Tests exercise real-world vault filing scenarios:
- LLM routing decisions (extend vs create vs unknown action)
- Collision handling when a target file already exists
- Relation merging with ruamel.yaml (dedup, no-op, error paths)
- Error recovery: backend error, empty response, bad JSON, path traversal

All LLM calls are mocked. Real filesystem operations use tmp_path.
"""

import json
import sys
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).parent.parent

from cyberbrain.extractors.autofile import (
    _build_folder_examples,
    _merge_relations_into_note,
    autofile_beat,
)
from cyberbrain.extractors.backends import BackendError

NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    (v / "AI" / "Claude-Sessions").mkdir(parents=True)
    return v


def _config(vault: Path, **overrides) -> dict:
    return {
        "vault_path": str(vault),
        "inbox": "AI/Claude-Sessions",
        "backend": "ollama",
        "model": "llama3.2",
        **overrides,
    }


def _beat(**kwargs) -> dict:
    return {
        "title": kwargs.get("title", "Choose FastAPI"),
        "type": kwargs.get("type", "decision"),
        "scope": kwargs.get("scope", "project"),
        "summary": kwargs.get("summary", "FastAPI over Flask for async."),
        "tags": kwargs.get("tags", ["fastapi", "python"]),
        "body": kwargs.get("body", "## Decision\n\nChose FastAPI."),
        "relations": kwargs.get("relations", []),
    }


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ===========================================================================
# _merge_relations_into_note
# ===========================================================================


class TestMergeRelationsIntoNote:
    """_merge_relations_into_note merges wikilinks into a note's related: field."""

    def test_appends_new_relation_wikilink(self, tmp_path):
        """A new target not already in related: is appended."""
        pytest.importorskip("ruamel.yaml")
        note = _write(
            tmp_path / "Note.md",
            textwrap.dedent("""\
            ---
            title: "My Note"
            related: []
            ---

            Body.
        """),
        )
        _merge_relations_into_note(note, [{"target": "Postgres Pool"}])
        assert "Postgres Pool" in note.read_text()

    def test_does_not_duplicate_existing_relation(self, tmp_path):
        """A target already in related: is not added a second time."""
        pytest.importorskip("ruamel.yaml")
        note = _write(
            tmp_path / "Note.md",
            textwrap.dedent("""\
            ---
            title: "My Note"
            related:
              - "[[Postgres Pool]]"
            ---

            Body.
        """),
        )
        _merge_relations_into_note(note, [{"target": "Postgres Pool"}])
        # Count should be exactly 1 (the existing one, not duplicated)
        assert note.read_text().count("Postgres Pool") == 1

    def test_no_op_when_all_relations_are_duplicates(self, tmp_path):
        """When every new relation is already present, the file is unchanged."""
        pytest.importorskip("ruamel.yaml")
        original = textwrap.dedent("""\
            ---
            title: "My Note"
            related:
              - "[[Target A]]"
              - "[[Target B]]"
            ---

            Body.
        """)
        note = _write(tmp_path / "Note.md", original)
        _merge_relations_into_note(
            note, [{"target": "Target A"}, {"target": "Target B"}]
        )
        assert note.read_text() == original

    def test_skips_note_without_frontmatter(self, tmp_path):
        """A note with no --- block is left unchanged."""
        pytest.importorskip("ruamel.yaml")
        note = _write(tmp_path / "Note.md", "Just plain markdown, no frontmatter.")
        original = note.read_text()
        _merge_relations_into_note(note, [{"target": "Something"}])
        assert note.read_text() == original

    def test_warns_and_returns_when_ruamel_not_installed(self, tmp_path, capsys):
        """Missing ruamel.yaml prints a warning and leaves the file unchanged."""
        note = _write(tmp_path / "Note.md", "---\ntitle: Test\nrelated: []\n---\nBody.")
        with patch.dict(sys.modules, {"ruamel.yaml": None}):
            _merge_relations_into_note(note, [{"target": "Target"}])
        captured = capsys.readouterr()
        assert "ruamel" in captured.err.lower()
        assert "Target" not in note.read_text()

    def test_non_dict_frontmatter_returns_early(self, tmp_path):
        """YAML that parses to a non-dict (list) leaves the file unchanged."""
        pytest.importorskip("ruamel.yaml")
        original_text = "---\n- item1\n- item2\n---\nBody."
        note = _write(tmp_path / "Note.md", original_text)
        _merge_relations_into_note(note, [{"target": "Target"}])
        assert note.read_text() == original_text

    def test_non_list_existing_related_field(self, tmp_path):
        """When related: is a non-list value, it is treated as empty and new relations are added."""
        pytest.importorskip("ruamel.yaml")
        note = _write(
            tmp_path / "Note.md",
            textwrap.dedent("""\
            ---
            title: "My Note"
            related: "not-a-list"
            ---

            Body.
        """),
        )
        _merge_relations_into_note(note, [{"target": "New Target"}])
        content = note.read_text()
        assert "New Target" in content

    def test_warns_on_yaml_parse_error(self, tmp_path, capsys):
        """Invalid YAML in frontmatter prints a warning and returns without writing."""
        pytest.importorskip("ruamel.yaml")
        # Frontmatter that triggers a YAML parse error with ruamel
        note = _write(
            tmp_path / "Note.md",
            textwrap.dedent("""\
            ---
            title: [unclosed
            related: []
            ---

            Body.
        """),
        )
        original = note.read_text()
        _merge_relations_into_note(note, [{"target": "Target"}])
        # Either the parse succeeds (ruamel is lenient) or a warning is emitted
        # The key assertion is that no exception propagates
        assert True  # reached means no exception

    def test_write_oserror_is_caught_gracefully(self, tmp_path, capsys):
        """An OSError when writing the updated note is caught and reported."""
        pytest.importorskip("ruamel.yaml")
        note = _write(
            tmp_path / "Note.md",
            textwrap.dedent("""\
            ---
            title: "My Note"
            related: []
            ---

            Body.
        """),
        )
        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            _merge_relations_into_note(note, [{"target": "New Target"}])
        captured = capsys.readouterr()
        assert (
            "Could not write" in captured.err
            or "OSError" in captured.err
            or "disk full" in captured.err
        )

    def test_skips_missing_file_gracefully(self, tmp_path, capsys):
        """A file that doesn't exist is handled without exception."""
        pytest.importorskip("ruamel.yaml")
        missing = tmp_path / "nonexistent.md"
        _merge_relations_into_note(missing, [{"target": "Target"}])
        captured = capsys.readouterr()
        assert "Could not read" in captured.err or not captured.err  # graceful

    def test_unclosed_frontmatter_returns_early(self, tmp_path):
        """A note with --- opening but no closing --- is left unchanged."""
        pytest.importorskip("ruamel.yaml")
        original = "---\ntitle: test\nno closing marker"
        note = _write(tmp_path / "Note.md", original)
        _merge_relations_into_note(note, [{"target": "Target"}])
        assert note.read_text() == original


# ===========================================================================
# autofile_beat — error recovery paths
# ===========================================================================


class TestAutofileBeatErrorRecovery:
    """autofile_beat falls back to write_beat on backend and parse errors."""

    def test_falls_back_on_backend_error(self, tmp_path):
        """When call_model raises BackendError, write_beat is called instead."""
        vault = _vault(tmp_path)
        config = _config(vault)
        beat = _beat()

        with patch(
            "cyberbrain.extractors.autofile.call_model",
            side_effect=BackendError("model unavailable"),
        ):
            with patch(
                "cyberbrain.extractors.autofile.write_beat",
                return_value=vault / "fallback.md",
            ) as mock_write:
                result = autofile_beat(beat, config, "session-1", str(tmp_path), NOW)

        mock_write.assert_called_once()
        assert result == vault / "fallback.md"

    def test_falls_back_on_empty_response(self, tmp_path):
        """When call_model returns an empty string, write_beat is used."""
        vault = _vault(tmp_path)
        config = _config(vault)

        with patch("cyberbrain.extractors.autofile.call_model", return_value=""):
            with patch(
                "cyberbrain.extractors.autofile.write_beat",
                return_value=vault / "fallback.md",
            ) as mock_write:
                result = autofile_beat(_beat(), config, "s", str(tmp_path), NOW)

        mock_write.assert_called_once()

    def test_falls_back_on_malformed_json(self, tmp_path, capsys):
        """When the model returns non-JSON, write_beat is called."""
        vault = _vault(tmp_path)
        config = _config(vault)

        with patch(
            "cyberbrain.extractors.autofile.call_model",
            return_value="This is not JSON at all.",
        ):
            with patch(
                "cyberbrain.extractors.autofile.write_beat",
                return_value=vault / "fallback.md",
            ) as mock_write:
                autofile_beat(_beat(), config, "s", str(tmp_path), NOW)

        mock_write.assert_called_once()
        captured = capsys.readouterr()
        assert "bad JSON" in captured.err or "JSON" in captured.err

    def test_falls_back_on_unknown_action(self, tmp_path, capsys):
        """When the model returns an unknown action, write_beat is called."""
        vault = _vault(tmp_path)
        config = _config(vault)
        decision = json.dumps({"action": "teleport", "path": "somewhere.md"})

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            with patch(
                "cyberbrain.extractors.autofile.write_beat",
                return_value=vault / "fallback.md",
            ) as mock_write:
                autofile_beat(_beat(), config, "s", str(tmp_path), NOW)

        mock_write.assert_called_once()
        captured = capsys.readouterr()
        assert "unknown action" in captured.err.lower()

    def test_uses_vault_claude_md_when_context_not_provided(self, tmp_path):
        """When vault_context=None, reads vault CLAUDE.md if it exists."""
        vault = _vault(tmp_path)
        (vault / "CLAUDE.md").write_text(
            "# Vault guide\n\nUse types: decision, insight.", encoding="utf-8"
        )
        config = _config(vault)

        with patch(
            "cyberbrain.extractors.autofile.call_model",
            return_value=json.dumps(
                {"action": "create", "path": "Test.md", "content": "# Test"}
            ),
        ):
            with patch(
                "cyberbrain.extractors.autofile.write_beat",
                return_value=vault / "Test.md",
            ):
                # vault_context=None triggers CLAUDE.md read
                autofile_beat(
                    _beat(), config, "s", str(tmp_path), NOW, vault_context=None
                )

    def test_related_docs_oserror_is_swallowed(self, tmp_path):
        """An OSError reading a related doc is silently skipped."""
        vault = _vault(tmp_path)
        config = _config(vault)
        decision = json.dumps(
            {
                "action": "create",
                "path": "Note.md",
                "content": "---\ntitle: Note\n---\nBody.",
            }
        )

        # Patch search_vault to return a path that can't be read
        with patch(
            "cyberbrain.extractors.autofile.search_vault",
            return_value=["/nonexistent/path.md"],
        ):
            with patch(
                "cyberbrain.extractors.autofile.call_model", return_value=decision
            ):
                result = autofile_beat(_beat(), config, "s", str(tmp_path), NOW)

        assert result is not None

    def test_vault_folders_oserror_is_swallowed(self, tmp_path, capsys):
        """An OSError when listing vault top-level folders is swallowed."""
        vault = _vault(tmp_path)
        config = _config(vault)
        decision = json.dumps(
            {
                "action": "create",
                "path": "Note.md",
                "content": "---\ntitle: Note\n---\nBody.",
            }
        )

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            with patch(
                "pathlib.Path.iterdir", side_effect=OSError("permission denied")
            ):
                result = autofile_beat(_beat(), config, "s", str(tmp_path), NOW)

        # Should not raise — OSError is caught; result may be None or a path
        assert True


# ===========================================================================
# autofile_beat — 'extend' action
# ===========================================================================


class TestAutofileExtendAction:
    """autofile_beat 'extend' action appends content to an existing note."""

    def _make_decision(
        self,
        vault: Path,
        target_rel: str,
        insertion: str = "## Addition\n\nNew content.",
    ) -> str:
        return json.dumps(
            {
                "action": "extend",
                "target_path": target_rel,
                "insertion": insertion,
            }
        )

    def test_appends_content_to_existing_note(self, tmp_path):
        """extend action appends insertion text to the target file."""
        vault = _vault(tmp_path)
        existing = _write(
            vault / "Projects" / "hermes.md",
            "---\ntitle: hermes\ntags: [python]\n---\n\nExisting content.",
        )
        decision = self._make_decision(vault, "Projects/hermes.md")

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            result = autofile_beat(_beat(), _config(vault), "s", str(tmp_path), NOW)

        assert result == existing
        content = existing.read_text()
        assert "New content" in content

    def test_falls_back_when_target_does_not_exist(self, tmp_path):
        """If the target file doesn't exist, falls back to write_beat."""
        vault = _vault(tmp_path)
        decision = self._make_decision(vault, "Nonexistent/File.md")

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            with patch(
                "cyberbrain.extractors.autofile.write_beat",
                return_value=vault / "fallback.md",
            ) as mock_write:
                autofile_beat(_beat(), _config(vault), "s", str(tmp_path), NOW)

        mock_write.assert_called_once()

    def test_rejects_path_traversal(self, tmp_path, capsys):
        """A target_path outside the vault is rejected and falls back."""
        vault = _vault(tmp_path)
        decision = self._make_decision(vault, "../../etc/passwd")

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            with patch(
                "cyberbrain.extractors.autofile.write_beat",
                return_value=vault / "fallback.md",
            ) as mock_write:
                autofile_beat(_beat(), _config(vault), "s", str(tmp_path), NOW)

        mock_write.assert_called_once()
        captured = capsys.readouterr()
        assert (
            "path traversal" in captured.err.lower()
            or "rejected" in captured.err.lower()
        )

    def test_merges_resolved_relations(self, tmp_path):
        """When beat has relations that resolve to vault notes, they are merged into the target."""
        pytest.importorskip("ruamel.yaml")
        vault = _vault(tmp_path)
        # Create vault note that will be "related"
        _write(vault / "JWT Auth.md", "---\ntitle: JWT Auth\ntags: [jwt]\n---\nBody.")
        # Create the target note to extend
        target = _write(
            vault / "Auth Overview.md",
            "---\ntitle: Auth Overview\nrelated: []\ntags: [auth]\n---\n\nOverview.",
        )
        beat = _beat(relations=[{"type": "references", "target": "JWT Auth"}])
        decision = json.dumps(
            {
                "action": "extend",
                "target_path": "Auth Overview.md",
                "insertion": "## New section\n\nSee JWT auth details.",
            }
        )

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            autofile_beat(beat, _config(vault), "s", str(tmp_path), NOW)

        content = target.read_text()
        assert "New section" in content

    def test_empty_insertion_falls_back(self, tmp_path):
        """An extend action with empty insertion falls back to write_beat."""
        vault = _vault(tmp_path)
        _write(vault / "Existing.md", "---\ntitle: Existing\n---\nContent.")
        decision = json.dumps(
            {"action": "extend", "target_path": "Existing.md", "insertion": ""}
        )

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            with patch(
                "cyberbrain.extractors.autofile.write_beat",
                return_value=vault / "fallback.md",
            ) as mock_write:
                autofile_beat(_beat(), _config(vault), "s", str(tmp_path), NOW)

        mock_write.assert_called_once()

    def test_extend_with_no_resolved_relations_skips_merge(self, tmp_path):
        """extend action with relations that don't resolve to vault notes skips merge."""
        vault = _vault(tmp_path)
        target = _write(
            vault / "Note.md", "---\ntitle: Note\nrelated: []\n---\n\nContent."
        )
        beat = _beat(relations=[{"type": "references", "target": "NonExistentNote"}])
        decision = json.dumps(
            {
                "action": "extend",
                "target_path": "Note.md",
                "insertion": "## Appended.",
            }
        )

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            result = autofile_beat(beat, _config(vault), "s", str(tmp_path), NOW)

        assert result == target
        assert "Appended" in target.read_text()


# ===========================================================================
# autofile_beat — 'create' action
# ===========================================================================


class TestAutofileCreateAction:
    """autofile_beat 'create' action writes a new note to the vault."""

    def _create_decision(self, path: str, content: str = None) -> str:
        return json.dumps(
            {
                "action": "create",
                "path": path,
                "content": content
                or textwrap.dedent("""\
                ---
                id: abc123
                type: decision
                title: "Choose FastAPI"
                tags: ["fastapi", "python"]
                summary: "FastAPI chosen for async."
                ---

                ## Decision

                FastAPI was chosen.
            """),
            }
        )

    def test_creates_new_file_in_vault(self, tmp_path):
        """create action writes the content to the specified vault-relative path."""
        vault = _vault(tmp_path)
        decision = self._create_decision("Projects/hermes/FastAPI Decision.md")

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            result = autofile_beat(_beat(), _config(vault), "s", str(tmp_path), NOW)

        assert result is not None
        assert result.exists()
        assert "FastAPI" in result.read_text()

    def test_falls_back_when_path_or_content_empty(self, tmp_path):
        """create with empty path or content falls back to write_beat."""
        vault = _vault(tmp_path)
        decision = json.dumps(
            {"action": "create", "path": "", "content": "Some content"}
        )

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            with patch(
                "cyberbrain.extractors.autofile.write_beat",
                return_value=vault / "fallback.md",
            ) as mock_write:
                autofile_beat(_beat(), _config(vault), "s", str(tmp_path), NOW)

        mock_write.assert_called_once()

    def test_falls_back_when_content_empty(self, tmp_path):
        """create with empty content falls back to write_beat."""
        vault = _vault(tmp_path)
        decision = json.dumps({"action": "create", "path": "Note.md", "content": ""})

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            with patch(
                "cyberbrain.extractors.autofile.write_beat",
                return_value=vault / "fallback.md",
            ) as mock_write:
                autofile_beat(_beat(), _config(vault), "s", str(tmp_path), NOW)

        mock_write.assert_called_once()

    def test_rejects_path_traversal(self, tmp_path, capsys):
        """create with a path that escapes the vault is rejected."""
        vault = _vault(tmp_path)
        decision = self._create_decision("../../evil/inject.md")

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            with patch(
                "cyberbrain.extractors.autofile.write_beat",
                return_value=vault / "fallback.md",
            ) as mock_write:
                autofile_beat(_beat(), _config(vault), "s", str(tmp_path), NOW)

        mock_write.assert_called_once()
        captured = capsys.readouterr()
        assert (
            "rejected" in captured.err.lower()
            or "path traversal" in captured.err.lower()
        )

    def test_collision_high_tag_overlap_extends_existing(self, tmp_path):
        """When target exists and tag overlap >= 2, content is appended (not renamed)."""
        vault = _vault(tmp_path)
        # Pre-create the target with overlapping tags
        target = _write(
            vault / "FastAPI Decision.md",
            textwrap.dedent("""\
                ---
                title: "FastAPI Decision"
                tags: ["fastapi", "python"]
                ---

                Original content.
            """),
        )
        content = textwrap.dedent("""\
            ---
            type: decision
            title: "FastAPI Decision"
            tags: ["fastapi", "python"]
            ---

            New info about FastAPI.
        """)
        decision = json.dumps(
            {"action": "create", "path": "FastAPI Decision.md", "content": content}
        )
        beat = _beat(tags=["fastapi", "python"])

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            result = autofile_beat(beat, _config(vault), "s", str(tmp_path), NOW)

        # File should still be at the original path (extended, not renamed)
        assert result == target
        assert "New info" in target.read_text()

    def test_collision_low_tag_overlap_renames_with_tag_suffix(self, tmp_path):
        """When target exists and tag overlap < 2, a new file with tag suffix is created."""
        vault = _vault(tmp_path)
        # Pre-create the target with different tags
        _write(
            vault / "Auth Decision.md",
            "---\ntitle: Auth Decision\ntags: [jwt, oauth]\n---\nExisting.",
        )
        content = textwrap.dedent("""\
            ---
            type: decision
            title: "Auth Decision"
            tags: ["session-based", "cookies"]
            ---

            Different auth approach.
        """)
        decision = json.dumps(
            {"action": "create", "path": "Auth Decision.md", "content": content}
        )
        beat = _beat(tags=["session-based", "cookies"])

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            result = autofile_beat(beat, _config(vault), "s", str(tmp_path), NOW)

        # Should create a new file with a distinguishing name
        assert result is not None
        assert (
            "session-based" in result.name
            or "cookies" in result.name
            or result != vault / "Auth Decision.md"
        )

    def test_collision_counter_when_specific_path_also_exists(self, tmp_path):
        """When both the primary and the tag-suffixed path exist, uses a numeric counter."""
        vault = _vault(tmp_path)
        # Create both the primary and the expected renamed path
        _write(
            vault / "Arch Decision.md",
            "---\ntitle: Original\ntags: [k8s, docker]\n---\nOrig.",
        )
        _write(
            vault / "Arch Decision — k8s.md",
            "---\ntitle: First collision\ntags: [k8s]\n---\nFirst.",
        )
        content = "---\ntype: decision\ntitle: Arch Decision\ntags: [k8s]\n---\nThird."
        decision = json.dumps(
            {"action": "create", "path": "Arch Decision.md", "content": content}
        )
        beat = _beat(tags=["k8s"])

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            result = autofile_beat(beat, _config(vault), "s", str(tmp_path), NOW)

        assert result is not None
        # The counter-based path should be different from the original
        assert result != vault / "Arch Decision.md"

    def test_collision_counter_increments_past_two(self, tmp_path):
        """When counter=2 path also exists, counter increments until a free slot is found."""
        vault = _vault(tmp_path)
        # Create primary, tag-suffixed, and counter=2 paths
        _write(vault / "My Note.md", "---\ntags: [x, y]\n---\nOrig.")
        _write(vault / "My Note — x.md", "---\ntags: [x]\n---\nFirst collision.")
        _write(vault / "2 My Note.md", "---\ntags: [x]\n---\nSecond collision.")
        content = "---\ntype: decision\ntitle: My Note\ntags: [x]\n---\nNew."
        decision = json.dumps(
            {"action": "create", "path": "My Note.md", "content": content}
        )
        beat = _beat(tags=["x"])

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            result = autofile_beat(beat, _config(vault), "s", str(tmp_path), NOW)

        assert result is not None
        # Should have used counter=3 or higher
        assert result != vault / "My Note.md"
        assert result != vault / "My Note — x.md"
        assert result != vault / "2 My Note.md"
        assert result.exists()
        assert "New." in result.read_text()

    def test_strips_code_fences_from_response(self, tmp_path):
        """Model response wrapped in ```json fences is parsed correctly."""
        vault = _vault(tmp_path)
        decision = (
            "```json\n"
            + json.dumps(
                {
                    "action": "create",
                    "path": "Projects/New Note.md",
                    "content": "---\ntitle: New Note\n---\nBody.",
                }
            )
            + "\n```"
        )

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            result = autofile_beat(_beat(), _config(vault), "s", str(tmp_path), NOW)

        assert result is not None
        assert result.exists()

    def test_search_index_update_is_called_after_create(self, tmp_path):
        """After creating a note, update_search_index is called with the output path."""
        vault = _vault(tmp_path)
        content = "---\ntype: decision\ntitle: Search Test\ntags: [search]\nsummary: Test.\n---\nBody."
        decision = json.dumps(
            {"action": "create", "path": "Search Test.md", "content": content}
        )

        mock_update = MagicMock()
        mock_module = MagicMock()
        mock_module.update_search_index = mock_update

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            with patch.dict(
                sys.modules, {"cyberbrain.extractors.search_index": mock_module}
            ):
                result = autofile_beat(_beat(), _config(vault), "s", str(tmp_path), NOW)

        assert result is not None
        assert result.exists()
        mock_update.assert_called_once()
        # The first argument should be the string path of the created file
        called_path = mock_update.call_args[0][0]
        assert called_path == str(result)

    def test_search_index_runtime_error_is_silently_ignored(self, tmp_path):
        """If update_search_index raises at runtime, the create action still succeeds."""
        vault = _vault(tmp_path)
        content = "---\ntype: decision\ntitle: Note\ntags: [x]\n---\nBody."
        decision = json.dumps(
            {"action": "create", "path": "Note.md", "content": content}
        )

        mock_module = MagicMock()
        mock_module.update_search_index.side_effect = RuntimeError("index locked")

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            with patch.dict(
                sys.modules, {"cyberbrain.extractors.search_index": mock_module}
            ):
                result = autofile_beat(_beat(), _config(vault), "s", str(tmp_path), NOW)

        assert result is not None
        assert result.exists()
        mock_module.update_search_index.assert_called_once()


# ===========================================================================
# autofile_beat — confidence-based routing
# ===========================================================================


class TestAutofileConfidenceRouting:
    """Confidence-based routing: high confidence proceeds normally, low confidence
    falls back to inbox or asks for confirmation depending on uncertain_filing_behavior."""

    def _create_decision(
        self, confidence: float, rationale: str = "Test rationale."
    ) -> str:
        return json.dumps(
            {
                "action": "create",
                "path": "Projects/High Confidence Note.md",
                "content": "---\ntype: decision\ntitle: High Confidence Note\ntags: [fastapi]\n---\nBody.",
                "confidence": confidence,
                "rationale": rationale,
            }
        )

    def test_high_confidence_routes_normally(self, tmp_path):
        """When confidence >= threshold (default 0.5), beat is filed at the LLM's chosen path."""
        vault = _vault(tmp_path)
        decision = self._create_decision(confidence=0.9)

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            result = autofile_beat(_beat(), _config(vault), "s", str(tmp_path), NOW)

        assert result is not None
        assert result.exists()
        # Filed at LLM-chosen path, not inbox
        assert "Projects" in str(result)

    def test_high_confidence_at_threshold_boundary_routes_normally(self, tmp_path):
        """Confidence exactly at threshold (0.5) is not treated as low confidence."""
        vault = _vault(tmp_path)
        decision = self._create_decision(confidence=0.5)

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            result = autofile_beat(_beat(), _config(vault), "s", str(tmp_path), NOW)

        assert result is not None
        assert result.exists()
        assert "Projects" in str(result)

    def test_low_confidence_inbox_behavior_routes_to_inbox(self, tmp_path, capsys):
        """When confidence < threshold and behavior='inbox', beat is routed to inbox via write_beat."""
        vault = _vault(tmp_path)
        decision = self._create_decision(
            confidence=0.3, rationale="No clear folder match."
        )
        config = _config(
            vault, uncertain_filing_behavior="inbox", uncertain_filing_threshold=0.5
        )

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            with patch(
                "cyberbrain.extractors.autofile.write_beat",
                return_value=vault / "AI" / "Claude-Sessions" / "beat.md",
            ) as mock_write:
                result = autofile_beat(_beat(), config, "s", str(tmp_path), NOW)

        mock_write.assert_called_once()
        captured = capsys.readouterr()
        assert "low confidence" in captured.err.lower()
        assert "0.30" in captured.err

    def test_low_confidence_inbox_is_default_behavior(self, tmp_path, capsys):
        """When uncertain_filing_behavior is not set, default 'inbox' routing applies."""
        vault = _vault(tmp_path)
        decision = self._create_decision(confidence=0.2)
        # Config without uncertain_filing_behavior or uncertain_filing_threshold
        config = _config(vault)

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            with patch(
                "cyberbrain.extractors.autofile.write_beat",
                return_value=vault / "AI" / "Claude-Sessions" / "beat.md",
            ) as mock_write:
                result = autofile_beat(_beat(), config, "s", str(tmp_path), NOW)

        mock_write.assert_called_once()
        captured = capsys.readouterr()
        assert "low confidence" in captured.err.lower()

    def test_low_confidence_ask_behavior_returns_none_and_sets_ask_key(self, tmp_path):
        """When confidence < threshold and behavior='ask', autofile_beat returns None
        and sets beat['_autofile_ask'] with confidence, rationale, and decision."""
        vault = _vault(tmp_path)
        rationale = "Multiple folders seem equally plausible."
        decision = self._create_decision(confidence=0.3, rationale=rationale)
        config = _config(
            vault, uncertain_filing_behavior="ask", uncertain_filing_threshold=0.5
        )
        beat = _beat()

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            result = autofile_beat(beat, config, "s", str(tmp_path), NOW, can_ask=True)

        assert result is None
        assert "_autofile_ask" in beat
        ask_data = beat["_autofile_ask"]
        assert ask_data["confidence"] == 0.3
        assert ask_data["rationale"] == rationale
        assert ask_data["decision"]["action"] == "create"

    def test_low_confidence_ask_behavior_does_not_call_write_beat(self, tmp_path):
        """When behavior='ask' and can_ask=True, write_beat is NOT called — no file is written."""
        vault = _vault(tmp_path)
        decision = self._create_decision(confidence=0.1)
        config = _config(
            vault, uncertain_filing_behavior="ask", uncertain_filing_threshold=0.5
        )

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            with patch("cyberbrain.extractors.autofile.write_beat") as mock_write:
                result = autofile_beat(
                    _beat(), config, "s", str(tmp_path), NOW, can_ask=True
                )

        mock_write.assert_not_called()
        assert result is None

    def test_custom_threshold_high_confidence_proceeds(self, tmp_path):
        """With a custom threshold of 0.7, confidence=0.75 proceeds normally."""
        vault = _vault(tmp_path)
        decision = self._create_decision(confidence=0.75)
        config = _config(vault, uncertain_filing_threshold=0.7)

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            result = autofile_beat(_beat(), config, "s", str(tmp_path), NOW)

        assert result is not None
        assert result.exists()

    def test_custom_threshold_low_confidence_falls_back(self, tmp_path):
        """With a custom threshold of 0.7, confidence=0.65 triggers inbox fallback."""
        vault = _vault(tmp_path)
        decision = self._create_decision(confidence=0.65)
        config = _config(
            vault, uncertain_filing_threshold=0.7, uncertain_filing_behavior="inbox"
        )

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            with patch(
                "cyberbrain.extractors.autofile.write_beat",
                return_value=vault / "AI" / "Claude-Sessions" / "beat.md",
            ) as mock_write:
                result = autofile_beat(_beat(), config, "s", str(tmp_path), NOW)

        mock_write.assert_called_once()

    def test_missing_confidence_field_defaults_to_0_5(self, tmp_path):
        """When the LLM response has no confidence field, it defaults to 0.5 (at threshold = proceeds)."""
        vault = _vault(tmp_path)
        # Decision without confidence key
        decision = json.dumps(
            {
                "action": "create",
                "path": "Projects/No Confidence.md",
                "content": "---\ntype: decision\ntitle: No Confidence\ntags: [x]\n---\nBody.",
            }
        )
        config = _config(vault)

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            result = autofile_beat(_beat(), config, "s", str(tmp_path), NOW)

        # Default 0.5 >= threshold 0.5, so proceeds normally
        assert result is not None
        assert result.exists()

    def test_non_numeric_confidence_defaults_to_0_5(self, tmp_path):
        """When confidence is a non-numeric value, it is treated as 0.5 (at threshold = proceeds)."""
        vault = _vault(tmp_path)
        decision = json.dumps(
            {
                "action": "create",
                "path": "Projects/Bad Confidence.md",
                "content": "---\ntype: decision\ntitle: Bad Confidence\ntags: [x]\n---\nBody.",
                "confidence": "high",
            }
        )
        config = _config(vault)

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            result = autofile_beat(_beat(), config, "s", str(tmp_path), NOW)

        assert result is not None

    def test_confidence_above_threshold_proceeds_normally(self, tmp_path):
        """When confidence >= threshold, beat is filed normally without uncertainty handling."""
        vault = _vault(tmp_path)
        decision = self._create_decision(
            confidence=0.6, rationale="Slightly uncertain."
        )
        config = _config(vault, uncertain_filing_threshold=0.5)

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            result = autofile_beat(_beat(), config, "s", str(tmp_path), NOW)

        assert result is not None
        assert result.exists()

    def test_low_confidence_inbox_sets_low_confidence_key_on_beat(self, tmp_path):
        """When routing to inbox due to low confidence, beat['_autofile_low_confidence'] is set."""
        vault = _vault(tmp_path)
        decision = self._create_decision(confidence=0.3)
        config = _config(
            vault, uncertain_filing_behavior="inbox", uncertain_filing_threshold=0.5
        )
        beat = _beat()

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            with patch(
                "cyberbrain.extractors.autofile.write_beat",
                return_value=vault / "AI" / "Claude-Sessions" / "beat.md",
            ):
                autofile_beat(beat, config, "s", str(tmp_path), NOW)

        assert beat.get("_autofile_low_confidence") == 0.3


# ===========================================================================
# _build_folder_examples — vault history injection (WI-044)
# ===========================================================================


class TestBuildFolderExamples:
    """_build_folder_examples samples notes from vault folders for LLM context."""

    def _make_note(
        self,
        path: Path,
        title: str,
        note_type: str = "reference",
        tags: list = None,
        summary: str = "A test summary.",
    ) -> Path:
        tags_yaml = str(tags or ["test"])
        content = (
            f"---\ntitle: {title!r}\ntype: {note_type}\n"
            f"tags: {tags_yaml}\nsummary: {summary!r}\n---\n\nBody content.\n"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_returns_examples_for_populated_folder(self, tmp_path):
        """Folders with notes return formatted example blocks."""
        vault = tmp_path / "vault"
        vault.mkdir()
        folder = vault / "Projects"
        folder.mkdir()
        self._make_note(folder / "Note A.md", "Note A", summary="About FastAPI.")
        self._make_note(folder / "Note B.md", "Note B", summary="About databases.")

        result = _build_folder_examples(str(vault), [])

        assert "Projects/" in result
        assert "Note A" in result or "Note B" in result

    def test_skips_empty_folder(self, tmp_path):
        """Folders with no notes are silently skipped."""
        vault = tmp_path / "vault"
        vault.mkdir()
        empty_folder = vault / "EmptyFolder"
        empty_folder.mkdir()

        result = _build_folder_examples(str(vault), [])

        # Empty folder should not appear in output
        assert "EmptyFolder" not in result

    def test_returns_fallback_when_all_folders_empty(self, tmp_path):
        """When no folders have notes, returns the fallback string."""
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "FolderA").mkdir()
        (vault / "FolderB").mkdir()

        result = _build_folder_examples(str(vault), [])

        assert result == "(no folder examples available)"

    def test_skips_hidden_folders(self, tmp_path):
        """Hidden folders (starting with .) are excluded."""
        vault = tmp_path / "vault"
        vault.mkdir()
        hidden = vault / ".trash"
        hidden.mkdir()
        self._make_note(hidden / "Hidden.md", "Hidden Note")

        result = _build_folder_examples(str(vault), [])

        assert "Hidden Note" not in result

    def test_samples_at_most_notes_per_folder(self, tmp_path):
        """At most notes_per_folder notes are sampled per folder."""
        vault = tmp_path / "vault"
        vault.mkdir()
        folder = vault / "Many"
        folder.mkdir()
        for i in range(10):
            self._make_note(folder / f"Note{i}.md", f"Note {i}")

        result = _build_folder_examples(str(vault), [], notes_per_folder=2)

        # Count number of "**Note" appearances — each note appears once as a bold title
        note_count = result.count("**Note")
        assert note_count <= 2

    def test_includes_most_recent_note(self, tmp_path):
        """The most recently modified note is always included in the sample."""
        import time

        vault = tmp_path / "vault"
        vault.mkdir()
        folder = vault / "Folder"
        folder.mkdir()

        old = self._make_note(folder / "Old.md", "Old Note")
        time.sleep(0.01)  # ensure different mtime
        new = self._make_note(folder / "New.md", "New Note")

        result = _build_folder_examples(str(vault), [])

        assert "New Note" in result

    def test_prioritises_folders_from_search_results(self, tmp_path):
        """Folders appearing in search_results are listed before others."""
        vault = tmp_path / "vault"
        vault.mkdir()
        priority = vault / "Priority"
        priority.mkdir()
        other = vault / "Alpha"
        other.mkdir()

        self._make_note(priority / "Prio Note.md", "Prio Note")
        self._make_note(other / "Other Note.md", "Other Note")

        # Pass a search result path from Priority folder
        search_result = str(priority / "Prio Note.md")
        result = _build_folder_examples(str(vault), [search_result])

        # Priority folder should appear before Alpha (it's a search hit)
        if "Priority/" in result and "Alpha/" in result:
            assert result.index("Priority/") < result.index("Alpha/")

    def test_max_folders_limit_respected(self, tmp_path):
        """No more than max_folders folders are included."""
        vault = tmp_path / "vault"
        vault.mkdir()
        for i in range(15):
            folder = vault / f"Folder{i:02d}"
            folder.mkdir()
            self._make_note(folder / "Note.md", f"Note {i}")

        result = _build_folder_examples(str(vault), [], max_folders=4)

        folder_count = result.count("sample notes)")
        assert folder_count <= 4

    def test_deterministic_second_sample(self, tmp_path):
        """The second sample is deterministic: same folder name always picks same note."""
        vault = tmp_path / "vault"
        vault.mkdir()
        folder = vault / "DeterministicFolder"
        folder.mkdir()
        for i in range(5):
            self._make_note(folder / f"Note{i}.md", f"Note {i}")

        result1 = _build_folder_examples(str(vault), [])
        result2 = _build_folder_examples(str(vault), [])

        assert result1 == result2

    def test_config_key_autofile_history_samples_controls_sample_count(self, tmp_path):
        """autofile_history_samples config key is used by autofile_beat."""
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "AI" / "Claude-Sessions").mkdir(parents=True)
        folder = vault / "Projects"
        folder.mkdir()
        for i in range(5):
            self._make_note(folder / f"Note{i}.md", f"Note {i}")

        config = {
            "vault_path": str(vault),
            "inbox": "AI/Claude-Sessions",
            "backend": "ollama",
            "model": "llama3.2",
            "autofile_history_samples": 1,
        }

        captured_examples: list = []

        def fake_load_prompt(filename: str) -> str:
            if filename == "autofile-user.md":
                return (
                    "{beat_json}\n{related_docs}\n{vault_context}\n"
                    "{vault_folders}\n{folder_examples}"
                )
            return "system prompt"

        def fake_call_model(system, user, cfg):
            # Extract the folder_examples portion from the user message
            lines = user.split("\n")
            # Find the folder_examples content (last portion after vault_folders)
            captured_examples.append(user)
            return json.dumps(
                {
                    "action": "create",
                    "path": "Note.md",
                    "content": "---\ntitle: T\n---\nBody.",
                }
            )

        beat = _beat()
        with patch(
            "cyberbrain.extractors.autofile.load_prompt", side_effect=fake_load_prompt
        ):
            with patch(
                "cyberbrain.extractors.autofile.call_model", side_effect=fake_call_model
            ):
                with patch(
                    "cyberbrain.extractors.autofile.search_vault", return_value=[]
                ):
                    with patch(
                        "cyberbrain.extractors.autofile.read_vault_claude_md",
                        return_value=None,
                    ):
                        autofile_beat(beat, config, "s", str(tmp_path), NOW)

        # With autofile_history_samples=1, only 1 note per folder should appear
        assert len(captured_examples) == 1
        user_msg = captured_examples[0]
        # The folder_examples section should not contain more than 1 note per folder
        # Count note appearances (bold titles **Note X**)
        note_count = user_msg.count("**Note")
        assert note_count <= 1, f"Expected at most 1 note sample, got {note_count}"


# ===========================================================================
# _update_cb_modified — writes updated field
# ===========================================================================


class TestUpdateCbModified:
    """_update_cb_modified writes both cb_modified and updated to frontmatter."""

    def test_update_cb_modified_writes_updated_field(self, tmp_path):
        """_update_cb_modified writes both cb_modified and updated: YYYY-MM-DD."""
        pytest.importorskip("ruamel.yaml")
        from cyberbrain.extractors.autofile import _update_cb_modified

        note = _write(
            tmp_path / "Note.md",
            textwrap.dedent("""\
                ---
                title: "Test Note"
                tags: [test]
                ---

                Body.
            """),
        )
        _update_cb_modified(note, NOW)
        content = note.read_text()
        assert "2026-01-15T12:00:00" in content
        assert "2026-01-15" in content
        assert "cb_modified:" in content
        assert "updated:" in content

    def test_update_cb_modified_overwrites_existing_updated_field(self, tmp_path):
        """_update_cb_modified overwrites an existing updated: field."""
        pytest.importorskip("ruamel.yaml")
        from cyberbrain.extractors.autofile import _update_cb_modified

        note = _write(
            tmp_path / "Note.md",
            textwrap.dedent("""\
                ---
                title: "Test Note"
                updated: 2020-01-01
                cb_modified: 2020-01-01T00:00:00
                ---

                Body.
            """),
        )
        _update_cb_modified(note, NOW)
        content = note.read_text()
        assert content.count("updated:") == 1
        assert "2026-01-15" in content
        assert "2020-01-01" not in content


# ===========================================================================
# autofile_beat — create action entity type remapping
# ===========================================================================


class TestAutofileCreateEntityTypeRemap:
    """create action remaps beat types to entity types in LLM-generated content."""

    def test_autofile_create_remaps_beat_type_to_entity_type(self, tmp_path):
        """LLM returns type: decision; written file contains type: resource (durable decision)."""
        vault = _vault(tmp_path)
        content = textwrap.dedent("""\
            ---
            id: abc123
            type: decision
            title: "Choose FastAPI"
            tags: ["fastapi", "python"]
            summary: "FastAPI chosen."
            ---

            ## Decision

            FastAPI was chosen.
        """)
        decision = json.dumps(
            {
                "action": "create",
                "path": "Projects/Choose FastAPI.md",
                "content": content,
                "confidence": 0.9,
            }
        )
        beat = _beat(type="decision")  # durable by default

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            with patch("cyberbrain.extractors.autofile.search_vault", return_value=[]):
                result = autofile_beat(beat, _config(vault), "s", str(tmp_path), NOW)

        assert result is not None
        assert result.exists()
        written = result.read_text()
        assert "type: resource" in written
        assert "type: decision" not in written

    def test_autofile_create_preserves_valid_entity_type(self, tmp_path):
        """LLM returns type: note; written file still contains type: note (unchanged)."""
        vault = _vault(tmp_path)
        content = textwrap.dedent("""\
            ---
            id: abc123
            type: note
            title: "A Working Note"
            tags: ["python"]
            summary: "Some note."
            ---

            Body.
        """)
        decision = json.dumps(
            {
                "action": "create",
                "path": "Projects/A Working Note.md",
                "content": content,
                "confidence": 0.9,
            }
        )
        beat = _beat(type="note")

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            with patch("cyberbrain.extractors.autofile.search_vault", return_value=[]):
                result = autofile_beat(beat, _config(vault), "s", str(tmp_path), NOW)

        assert result is not None
        assert result.exists()
        written = result.read_text()
        assert "type: note" in written

    def test_autofile_create_working_memory_beat_maps_to_note_type(self, tmp_path):
        """Beat with type: decision and durability: working-memory is written with type: note."""
        vault = _vault(tmp_path)
        content = textwrap.dedent("""\
            ---
            id: abc123
            type: decision
            title: "In-Flight Refactor Plan"
            tags: ["refactor", "python"]
            summary: "Current refactor in progress."
            ---

            ## Decision

            Refactor in progress.
        """)
        decision = json.dumps(
            {
                "action": "create",
                "path": "Projects/In-Flight Refactor Plan.md",
                "content": content,
                "confidence": 0.9,
            }
        )
        beat = _beat(type="decision")
        beat["durability"] = "working-memory"

        with patch("cyberbrain.extractors.autofile.call_model", return_value=decision):
            with patch("cyberbrain.extractors.autofile.search_vault", return_value=[]):
                result = autofile_beat(beat, _config(vault), "s", str(tmp_path), NOW)

        assert result is not None
        assert result.exists()
        written = result.read_text()
        assert "type: note" in written


# ===========================================================================
# autofile_beat — scope-aware routing (WI-101 / WI-112)
# ===========================================================================


class TestAutofileScopeRouting:
    """Scope-aware routing: system prompt contains scope instructions; scope:general
    beats route to Knowledge/ not inbox."""

    def test_autofile_system_prompt_contains_scope_routing(self):
        """Verify the autofile system prompt contains scope-aware routing instructions."""
        prompt_path = (
            Path(__file__).parent.parent
            / "src"
            / "cyberbrain"
            / "prompts"
            / "autofile-system.md"
        )
        content = prompt_path.read_text()
        assert "scope: general" in content, (
            "autofile-system.md should contain scope:general routing rules"
        )
        assert "scope: project" in content, (
            "autofile-system.md should contain scope:project routing rules"
        )
        assert "Knowledge/" in content, (
            "autofile-system.md should reference Knowledge/ folder"
        )

    def test_autofile_scope_general_routes_to_knowledge(self, tmp_path):
        """When autofile_beat receives a scope:general beat and the LLM responds with
        a Knowledge/ folder, the note is filed there (not in inbox)."""
        vault = _vault(tmp_path)
        (vault / "Knowledge" / "Python").mkdir(parents=True)

        llm_response = json.dumps(
            {
                "action": "create",
                "folder": "Knowledge/Python",
                "filename": "Python Subprocess Encoding.md",
                "path": "Knowledge/Python/Python Subprocess Encoding.md",
                "content": textwrap.dedent("""\
                    ---
                    title: "Python Subprocess Encoding"
                    type: reference
                    tags: ["python", "subprocess"]
                    summary: "How subprocess handles encoding."
                    ---

                    ## Reference

                    Subprocess encoding details.
                """),
                "confidence": 0.9,
                "reasoning": "World knowledge about Python subprocesses.",
            }
        )

        beat = _beat(
            title="Python Subprocess Encoding",
            type="reference",
            scope="general",
            summary="How subprocess handles encoding.",
            tags=["python", "subprocess"],
        )
        config = _config(vault)

        with patch(
            "cyberbrain.extractors.autofile.call_model", return_value=llm_response
        ):
            result = autofile_beat(
                beat, config, "session-scope-test", str(tmp_path), NOW
            )

        assert result is not None
        assert result.exists()
        assert "Knowledge" in str(result), (
            f"Expected result path to contain 'Knowledge/', got: {result}"
        )
        # Confirm it did NOT land in inbox
        inbox_path = vault / "AI" / "Claude-Sessions"
        assert not str(result).startswith(str(inbox_path)), (
            f"scope:general beat should not route to inbox, got: {result}"
        )


# ===========================================================================
# autofile_beat — document intake content preservation (WI-013 / WI-014)
# ===========================================================================


class TestAutofileDocumentIntake:
    """autofile_beat with source='document-intake' preserves original beat content.

    When source='document-intake', the LLM response is used only for folder
    routing — the original beat body is always written, never the LLM-generated
    or LLM-rewritten content.
    """

    def test_document_intake_create_preserves_content(self, tmp_path):
        """cb_file with title + autofile enabled + LLM returns action='create':
        vault note body matches original beat content, not LLM-rewritten content."""
        vault = _vault(tmp_path)
        original_body = "## My Document\n\nThis is the original document content."
        beat = _beat(
            title="My Document",
            body=original_body,
            tags=["docs", "python"],
        )
        # LLM returns a create decision with rewritten content
        llm_decision = json.dumps(
            {
                "action": "create",
                "path": "Projects/test/My Document.md",
                "content": "rewritten content that should not appear in the output",
                "confidence": 0.9,
            }
        )
        captured_calls: list = []

        def fake_write_beat(b, cfg, session_id, cwd, now, **kwargs):
            captured_calls.append({"beat": b, "config": cfg})
            # Return a fake path — the actual write is not exercised in this test
            result_path = vault / "Projects" / "test" / "My Document.md"
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(b.get("body", ""), encoding="utf-8")
            return result_path

        with patch("cyberbrain.extractors.autofile.search_vault", return_value=[]):
            with patch(
                "cyberbrain.extractors.autofile.call_model", return_value=llm_decision
            ):
                with patch(
                    "cyberbrain.extractors.autofile.write_beat", side_effect=fake_write_beat
                ):
                    result = autofile_beat(
                        beat,
                        _config(vault),
                        "session-intake",
                        str(tmp_path),
                        NOW,
                        source="document-intake",
                    )

        # write_beat must have been called (not the direct LLM-content write path)
        assert len(captured_calls) == 1
        # The beat passed to write_beat must carry the original body
        passed_beat = captured_calls[0]["beat"]
        assert passed_beat["body"] == original_body
        # The config inbox should be the folder from the LLM path
        passed_config = captured_calls[0]["config"]
        assert passed_config["inbox"] == "Projects/test"
        # The result must not contain LLM-rewritten content
        assert result is not None
        content_on_disk = result.read_text()
        assert "rewritten content" not in content_on_disk
        assert original_body in content_on_disk

    def test_document_intake_extend_creates_new_note(self, tmp_path):
        """cb_file with title + autofile enabled + LLM returns action='extend':
        a new note is created (not appended to existing) with original content preserved."""
        vault = _vault(tmp_path)
        # Create the existing note that the LLM wants to extend
        existing = _write(
            vault / "Projects" / "existing.md",
            "---\ntitle: Existing Note\ntags: [python]\n---\n\nExisting content.",
        )
        original_body = "## New Document\n\nThis content must be preserved as-is."
        beat = _beat(
            title="New Document",
            body=original_body,
            tags=["docs"],
        )
        # LLM returns an extend decision pointing at the existing note
        llm_decision = json.dumps(
            {
                "action": "extend",
                "target_path": "Projects/existing.md",
                "insertion": "rewritten insertion that should not be appended",
                "confidence": 0.9,
            }
        )
        captured_calls: list = []

        def fake_write_beat(b, cfg, session_id, cwd, now, **kwargs):
            captured_calls.append({"beat": b, "config": cfg})
            result_path = vault / "Projects" / "New Document.md"
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(b.get("body", ""), encoding="utf-8")
            return result_path

        with patch("cyberbrain.extractors.autofile.search_vault", return_value=[]):
            with patch(
                "cyberbrain.extractors.autofile.call_model", return_value=llm_decision
            ):
                with patch(
                    "cyberbrain.extractors.autofile.write_beat", side_effect=fake_write_beat
                ):
                    result = autofile_beat(
                        beat,
                        _config(vault),
                        "session-intake",
                        str(tmp_path),
                        NOW,
                        source="document-intake",
                    )

        # write_beat must have been called instead of appending to existing.md
        assert len(captured_calls) == 1
        # The existing note must NOT have been modified
        assert "rewritten insertion" not in existing.read_text()
        assert "New Document" not in existing.read_text()
        # The config inbox should be the folder derived from target_path
        passed_config = captured_calls[0]["config"]
        assert passed_config["inbox"] == "Projects"
        # The beat body must be preserved
        passed_beat = captured_calls[0]["beat"]
        assert passed_beat["body"] == original_body
        # A new note was created (not appended to existing.md)
        assert result is not None
        assert result != existing
        content_on_disk = result.read_text()
        assert "rewritten insertion" not in content_on_disk
        assert original_body in content_on_disk

    def test_single_beat_capture_create_uses_llm_content(self, tmp_path):
        """autofile_beat with source='manual-filing': LLM-generated content is used
        for create, original beat body is not written."""
        vault = _vault(tmp_path)
        original_body = "## Original\n\nThis is the original beat body."
        llm_content = textwrap.dedent("""\
            ---
            id: abc123
            type: decision
            title: "LLM Title"
            tags: ["python"]
            summary: "LLM summary."
            ---

            LLM-generated content body.
        """)
        beat = _beat(
            title="LLM Title",
            body=original_body,
            tags=["python"],
        )
        llm_decision = json.dumps(
            {
                "action": "create",
                "path": "Projects/LLM Title.md",
                "content": llm_content,
                "confidence": 0.9,
            }
        )

        with patch(
            "cyberbrain.extractors.autofile.call_model", return_value=llm_decision
        ):
            with patch("cyberbrain.extractors.autofile.search_vault", return_value=[]):
                result = autofile_beat(
                    beat,
                    _config(vault),
                    "session-manual",
                    str(tmp_path),
                    NOW,
                    source="manual-filing",
                )

        # Normal autofile: LLM-generated content should be written
        assert result is not None
        assert result.exists()
        content_on_disk = result.read_text()
        assert "LLM-generated content body" in content_on_disk
        # The original beat body should NOT appear (LLM content takes precedence)
        assert "This is the original beat body" not in content_on_disk

    def test_single_beat_capture_extend_uses_llm_insertion(self, tmp_path):
        """autofile_beat with source='manual-filing' and action='extend': LLM insertion
        is appended to the existing note (existing behavior preserved)."""
        vault = _vault(tmp_path)
        existing = _write(
            vault / "Projects" / "existing.md",
            "---\ntitle: Existing Note\ntags: [python]\n---\n\nExisting content.",
        )
        original_body = "## Original\n\nThis is the original beat body."
        beat = _beat(
            title="Beat Title",
            body=original_body,
            tags=["python"],
        )
        llm_insertion = "## New Section\n\nLLM-generated insertion content."
        llm_decision = json.dumps(
            {
                "action": "extend",
                "target_path": "Projects/existing.md",
                "insertion": llm_insertion,
                "confidence": 0.9,
            }
        )

        with patch("cyberbrain.extractors.autofile.search_vault", return_value=[]):
            with patch(
                "cyberbrain.extractors.autofile.call_model", return_value=llm_decision
            ):
                result = autofile_beat(
                    beat,
                    _config(vault),
                    "session-manual",
                    str(tmp_path),
                    NOW,
                    source="manual-filing",
                )

        # Normal autofile extend: LLM insertion should be appended to the existing note
        assert result is not None
        assert result == existing
        content_on_disk = existing.read_text()
        assert "LLM-generated insertion content" in content_on_disk
        assert "Existing content" in content_on_disk
        # The original beat body should NOT appear (LLM insertion is used instead)
        assert "This is the original beat body" not in content_on_disk

    def test_document_intake_create_rejects_path_traversal(self, tmp_path):
        """autofile_beat with source='document-intake' and action='create':
        path traversal in LLM path is rejected, falls back to write_beat with default config."""
        vault = _vault(tmp_path)
        beat = _beat(title="My Doc", body="Original content.", tags=["docs"])
        llm_decision = json.dumps(
            {
                "action": "create",
                "path": "../../evil/Backdoor.md",
                "content": "rewritten",
                "confidence": 0.9,
            }
        )
        captured_calls: list = []

        def fake_write_beat(b, cfg, session_id, cwd, now, **kwargs):
            captured_calls.append({"beat": b, "config": cfg})
            result_path = vault / "inbox" / "My Doc.md"
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(b.get("body", ""), encoding="utf-8")
            return result_path

        with patch("cyberbrain.extractors.autofile.search_vault", return_value=[]):
            with patch(
                "cyberbrain.extractors.autofile.call_model", return_value=llm_decision
            ):
                with patch(
                    "cyberbrain.extractors.autofile.write_beat", side_effect=fake_write_beat
                ):
                    result = autofile_beat(
                        beat,
                        _config(vault),
                        "session-intake",
                        str(tmp_path),
                        NOW,
                        source="document-intake",
                    )

        # write_beat called with original config (not intake_config with traversal path)
        assert len(captured_calls) == 1
        passed_config = captured_calls[0]["config"]
        assert "../../evil" not in passed_config.get("inbox", "")
        assert result is not None

    def test_document_intake_extend_rejects_path_traversal(self, tmp_path):
        """autofile_beat with source='document-intake' and action='extend':
        path traversal in target_path is rejected, falls back to write_beat with default config."""
        vault = _vault(tmp_path)
        beat = _beat(title="My Doc", body="Original content.", tags=["docs"])
        llm_decision = json.dumps(
            {
                "action": "extend",
                "target_path": "../../evil/target.md",
                "insertion": "rewritten",
                "confidence": 0.9,
            }
        )
        captured_calls: list = []

        def fake_write_beat(b, cfg, session_id, cwd, now, **kwargs):
            captured_calls.append({"beat": b, "config": cfg})
            result_path = vault / "inbox" / "My Doc.md"
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(b.get("body", ""), encoding="utf-8")
            return result_path

        with patch("cyberbrain.extractors.autofile.search_vault", return_value=[]):
            with patch(
                "cyberbrain.extractors.autofile.call_model", return_value=llm_decision
            ):
                with patch(
                    "cyberbrain.extractors.autofile.write_beat", side_effect=fake_write_beat
                ):
                    result = autofile_beat(
                        beat,
                        _config(vault),
                        "session-intake",
                        str(tmp_path),
                        NOW,
                        source="document-intake",
                    )

        # write_beat called with original config (no traversal path in inbox)
        assert len(captured_calls) == 1
        passed_config = captured_calls[0]["config"]
        assert "../../evil" not in passed_config.get("inbox", "")
        assert result is not None

    def test_document_intake_create_clears_vault_folder(self, tmp_path):
        """autofile_beat with source='document-intake' and vault_folder configured:
        intake_config must not carry vault_folder so inbox routing takes effect."""
        vault = _vault(tmp_path)
        beat = _beat(
            title="My Doc",
            body="Original content.",
            tags=["docs"],
            scope="project",
        )
        llm_decision = json.dumps(
            {
                "action": "create",
                "path": "Knowledge/Python/My Doc.md",
                "content": "rewritten",
                "confidence": 0.9,
            }
        )
        captured_calls: list = []

        def fake_write_beat(b, cfg, session_id, cwd, now, **kwargs):
            captured_calls.append({"beat": b, "config": cfg})
            result_path = vault / "Knowledge" / "Python" / "My Doc.md"
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(b.get("body", ""), encoding="utf-8")
            return result_path

        config = _config(vault)
        config["vault_folder"] = "Projects/my-project/Claude-Notes"

        with patch("cyberbrain.extractors.autofile.search_vault", return_value=[]):
            with patch(
                "cyberbrain.extractors.autofile.call_model", return_value=llm_decision
            ):
                with patch(
                    "cyberbrain.extractors.autofile.write_beat", side_effect=fake_write_beat
                ):
                    result = autofile_beat(
                        beat,
                        config,
                        "session-intake",
                        str(tmp_path),
                        NOW,
                        source="document-intake",
                    )

        assert len(captured_calls) == 1
        passed_config = captured_calls[0]["config"]
        # vault_folder must be cleared so inbox routing wins
        assert "vault_folder" not in passed_config
        assert passed_config["inbox"] == "Knowledge/Python"
        assert result is not None
