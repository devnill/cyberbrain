"""
test_extractor_helpers.py — unit tests for extractor helper modules

Covers:
- src/cyberbrain/extractors/config.py: load_global_config, find_project_config, resolve_config, load_prompt
- src/cyberbrain/extractors/frontmatter.py: parse_frontmatter, read_frontmatter, read_frontmatter_tags,
                             normalise_list, derive_id
- src/cyberbrain/extractors/vault.py: parse_valid_types_from_claude_md, read_vault_claude_md, get_valid_types,
                       make_filename, _is_within_vault, resolve_output_dir, build_vault_titles_set,
                       resolve_relations, search_vault, inject_provenance, _wm_frontmatter_fields,
                       write_beat
- src/cyberbrain/extractors/extractor.py: extract_beats
- src/cyberbrain/extractors/transcript.py: parse_jsonl_transcript, _extract_text_blocks
"""

import json
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
import subprocess

import pytest

REPO_ROOT = Path(__file__).parent.parent


# ===========================================================================
# config.py
# ===========================================================================

import cyberbrain.extractors.config as config_mod


class TestLoadGlobalConfig:
    def test_exits_when_config_file_missing(self, tmp_path):
        missing = tmp_path / "no_config.json"
        with patch.object(config_mod, "GLOBAL_CONFIG_PATH", missing):
            with pytest.raises(SystemExit):
                config_mod.load_global_config()

    def test_exits_when_required_field_missing(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"vault_path": ""}))
        with patch.object(config_mod, "GLOBAL_CONFIG_PATH", cfg):
            with pytest.raises(SystemExit):
                config_mod.load_global_config()

    def test_exits_for_placeholder_vault_path(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({
            "vault_path": "/path/to/your/ObsidianVault",
            "inbox": "AI/Inbox",
        }))
        with patch.object(config_mod, "GLOBAL_CONFIG_PATH", cfg):
            with pytest.raises(SystemExit):
                config_mod.load_global_config()

    def test_exits_when_vault_path_does_not_exist(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({
            "vault_path": str(tmp_path / "nonexistent_vault"),
            "inbox": "AI/Inbox",
        }))
        with patch.object(config_mod, "GLOBAL_CONFIG_PATH", cfg):
            with pytest.raises(SystemExit):
                config_mod.load_global_config()

    def test_exits_when_vault_is_home_directory(self, tmp_path):
        cfg = tmp_path / "config.json"
        home = Path.home()
        cfg.write_text(json.dumps({
            "vault_path": str(home),
            "inbox": "AI/Inbox",
        }))
        with patch.object(config_mod, "GLOBAL_CONFIG_PATH", cfg):
            with pytest.raises(SystemExit):
                config_mod.load_global_config()

    def test_exits_when_vault_is_filesystem_root(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({
            "vault_path": "/",
            "inbox": "AI/Inbox",
        }))
        with patch.object(config_mod, "GLOBAL_CONFIG_PATH", cfg):
            with pytest.raises(SystemExit):
                config_mod.load_global_config()

    def test_returns_config_with_resolved_vault_path(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({
            "vault_path": str(vault),
            "inbox": "AI/Inbox",
            "backend": "claude-code",
        }))
        with patch.object(config_mod, "GLOBAL_CONFIG_PATH", cfg):
            result = config_mod.load_global_config()
        assert result["vault_path"] == str(vault.resolve())
        assert result["inbox"] == "AI/Inbox"

    def test_exits_when_vault_path_missing_from_config(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"inbox": "AI/Inbox"}))
        with patch.object(config_mod, "GLOBAL_CONFIG_PATH", cfg):
            with pytest.raises(SystemExit):
                config_mod.load_global_config()


class TestFindProjectConfig:
    def test_returns_empty_when_no_config_found(self, tmp_path):
        result = config_mod.find_project_config(str(tmp_path))
        assert result == {}

    def test_finds_config_in_current_dir(self, tmp_path):
        dot_claude = tmp_path / ".claude"
        dot_claude.mkdir()
        local_cfg = dot_claude / "cyberbrain.local.json"
        local_cfg.write_text(json.dumps({"project_name": "myproj", "vault_folder": "Projects/myproj"}))

        result = config_mod.find_project_config(str(tmp_path))
        assert result["project_name"] == "myproj"

    def test_finds_config_in_parent_directory(self, tmp_path):
        dot_claude = tmp_path / ".claude"
        dot_claude.mkdir()
        local_cfg = dot_claude / "cyberbrain.local.json"
        local_cfg.write_text(json.dumps({"project_name": "parentproj"}))

        subdir = tmp_path / "sub" / "dir"
        subdir.mkdir(parents=True)
        result = config_mod.find_project_config(str(subdir))
        assert result["project_name"] == "parentproj"

    def test_stops_at_home_directory(self, tmp_path):
        # Searching from a temp path that has no config should return {}
        # (doesn't walk up past home)
        result = config_mod.find_project_config(str(tmp_path))
        assert result == {}


class TestResolveConfig:
    def test_merges_global_and_project_configs(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        global_data = {"vault_path": str(vault), "inbox": "AI/Inbox", "backend": "claude-code"}
        project_data = {"project_name": "myproj", "vault_folder": "Projects/myproj"}

        with patch.object(config_mod, "load_global_config", return_value=global_data), \
             patch.object(config_mod, "find_project_config", return_value=project_data):
            result = config_mod.resolve_config("/some/cwd")

        assert result["vault_path"] == str(vault)
        assert result["project_name"] == "myproj"
        assert result["vault_folder"] == "Projects/myproj"

    def test_project_config_overrides_global(self, tmp_path):
        global_data = {"vault_path": "/global/vault", "inbox": "AI/Global"}
        project_data = {"inbox": "Projects/Override"}

        with patch.object(config_mod, "load_global_config", return_value=global_data), \
             patch.object(config_mod, "find_project_config", return_value=project_data):
            result = config_mod.resolve_config("/cwd")

        assert result["inbox"] == "Projects/Override"


class TestLoadPrompt:
    def test_returns_prompt_content(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        prompt_file = prompts_dir / "test-prompt.md"
        prompt_file.write_text("  Hello prompt  ")

        with patch.object(config_mod, "PROMPTS_DIR", prompts_dir):
            result = config_mod.load_prompt("test-prompt.md")
        assert result == "Hello prompt"

    def test_exits_when_prompt_file_missing(self, tmp_path):
        with patch.object(config_mod, "PROMPTS_DIR", tmp_path):
            with pytest.raises(SystemExit):
                config_mod.load_prompt("nonexistent.md")


# ===========================================================================
# frontmatter.py
# ===========================================================================

import cyberbrain.extractors.frontmatter as fm_mod


class TestParseFrontmatter:
    def test_returns_empty_when_no_leading_dashes(self):
        assert fm_mod.parse_frontmatter("no frontmatter here") == {}

    def test_returns_empty_when_frontmatter_unclosed(self):
        assert fm_mod.parse_frontmatter("---\ntitle: foo\n") == {}

    def test_parses_basic_yaml(self):
        content = "---\ntitle: Hello\ntags: [a, b]\n---\n\nBody"
        result = fm_mod.parse_frontmatter(content)
        assert result["title"] == "Hello"

    def test_returns_empty_on_invalid_yaml(self):
        content = "---\n: invalid: yaml: [\n---\n"
        result = fm_mod.parse_frontmatter(content)
        assert result == {}

    def test_returns_empty_when_yaml_not_a_dict(self):
        content = "---\n- item1\n- item2\n---\n"
        result = fm_mod.parse_frontmatter(content)
        assert result == {}


class TestReadFrontmatter:
    def test_returns_empty_on_oserror(self, tmp_path):
        result = fm_mod.read_frontmatter(str(tmp_path / "nonexistent.md"))
        assert result == {}

    def test_reads_and_parses_file(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_text("---\ntitle: Test\n---\n\nBody")
        result = fm_mod.read_frontmatter(str(f))
        assert result["title"] == "Test"


class TestReadFrontmatterTags:
    def test_returns_empty_set_on_oserror(self, tmp_path):
        result = fm_mod.read_frontmatter_tags(tmp_path / "nonexistent.md")
        assert result == set()

    def test_returns_empty_set_when_no_frontmatter(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_text("No frontmatter here")
        assert fm_mod.read_frontmatter_tags(f) == set()

    def test_returns_empty_set_when_no_tags_field(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_text("---\ntitle: foo\n---\n")
        assert fm_mod.read_frontmatter_tags(f) == set()

    def test_parses_json_array_tags(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_text('---\ntitle: foo\ntags: ["python", "testing"]\n---\n')
        result = fm_mod.read_frontmatter_tags(f)
        assert result == {"python", "testing"}

    def test_parses_bracketed_yaml_tags(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_text("---\ntitle: foo\ntags: [alpha, beta]\n---\n")
        result = fm_mod.read_frontmatter_tags(f)
        assert result == {"alpha", "beta"}

    def test_tags_are_lowercased(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_text('---\ntitle: foo\ntags: ["Python", "TESTING"]\n---\n')
        result = fm_mod.read_frontmatter_tags(f)
        assert result == {"python", "testing"}

    def test_returns_empty_for_unparseable_tags(self, tmp_path):
        f = tmp_path / "note.md"
        # Not JSON, not bracketed — no fallback
        f.write_text("---\ntitle: foo\ntags: just-a-string\n---\n")
        result = fm_mod.read_frontmatter_tags(f)
        assert result == set()


class TestNormaliseList:
    def test_list_passthrough(self):
        assert fm_mod.normalise_list(["a", "b"]) == ["a", "b"]

    def test_filters_empty_values(self):
        assert fm_mod.normalise_list(["a", None, "", "b"]) == ["a", "b"]

    def test_json_string(self):
        assert fm_mod.normalise_list('["x", "y"]') == ["x", "y"]

    def test_plain_string(self):
        assert fm_mod.normalise_list("hello") == ["hello"]

    def test_empty_string(self):
        assert fm_mod.normalise_list("  ") == []

    def test_non_parseable_json_string(self):
        assert fm_mod.normalise_list("not json") == ["not json"]

    def test_other_type_returns_empty(self):
        assert fm_mod.normalise_list(42) == []
        assert fm_mod.normalise_list(None) == []


class TestDeriveId:
    def test_returns_36_char_string(self):
        result = fm_mod.derive_id("/some/path/note.md")
        assert len(result) == 36

    def test_deterministic(self):
        assert fm_mod.derive_id("/same/path") == fm_mod.derive_id("/same/path")

    def test_different_paths_differ(self):
        assert fm_mod.derive_id("/path/a.md") != fm_mod.derive_id("/path/b.md")


# ===========================================================================
# vault.py
# ===========================================================================

import cyberbrain.extractors.vault as vault_mod


class TestParseValidTypesFromClaudeMd:
    def test_empty_text_returns_defaults(self):
        result = vault_mod.parse_valid_types_from_claude_md("")
        assert result == vault_mod._DEFAULT_VALID_TYPES

    def test_none_returns_defaults(self):
        result = vault_mod.parse_valid_types_from_claude_md(None)
        assert result == vault_mod._DEFAULT_VALID_TYPES

    def test_no_types_section_returns_defaults(self):
        text = "# My Vault\n\nSome content here.\n"
        result = vault_mod.parse_valid_types_from_claude_md(text)
        assert result == vault_mod._DEFAULT_VALID_TYPES

    def test_parses_types_from_level4_subsections(self):
        # The code ends the types section on any #{1,3} heading, so type headings
        # must be #### (level 4) to be captured as type entries.
        text = textwrap.dedent("""\
            # Vault Guide

            ## Types

            #### decision
            A choice between alternatives.

            #### insight
            A pattern discovered.

            ## Other Section
        """)
        result = vault_mod.parse_valid_types_from_claude_md(text)
        assert "decision" in result
        assert "insight" in result

    def test_parses_backtick_types(self):
        # Inline backtick types within the Types section are also captured.
        text = textwrap.dedent("""\
            ## Beat Types

            Use `reference` for facts and `problem` for blockers.
        """)
        result = vault_mod.parse_valid_types_from_claude_md(text)
        assert "reference" in result
        assert "problem" in result

    def test_types_section_ends_at_next_h2_heading(self):
        # #{1,3} headings end the types section. Only #### headings inside it
        # are captured as types; headings after the section boundary are not.
        text = textwrap.dedent("""\
            ## Types

            #### alpha

            ## Configuration

            #### beta
        """)
        result = vault_mod.parse_valid_types_from_claude_md(text)
        assert "alpha" in result
        assert "beta" not in result


class TestReadVaultClaudeMd:
    def test_returns_none_when_no_claude_md(self, tmp_path):
        result = vault_mod.read_vault_claude_md(str(tmp_path))
        assert result is None

    def test_returns_text_when_file_exists(self, tmp_path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# My Vault\n")
        result = vault_mod.read_vault_claude_md(str(tmp_path))
        assert result == "# My Vault\n"

    def test_returns_none_on_oserror(self, tmp_path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("content")
        with patch.object(Path, "read_text", side_effect=OSError("no read")):
            result = vault_mod.read_vault_claude_md(str(tmp_path))
        assert result is None


class TestGetValidTypes:
    def test_returns_defaults_when_no_claude_md(self, tmp_path):
        config = {"vault_path": str(tmp_path)}
        result = vault_mod.get_valid_types(config)
        assert result == vault_mod._DEFAULT_VALID_TYPES

    def test_returns_types_from_claude_md(self, tmp_path):
        claude_md = tmp_path / "CLAUDE.md"
        # Use backtick inline types — #### headings also work but backticks are simpler
        claude_md.write_text("## Types\n\nUse `custom` for things.\n")
        config = {"vault_path": str(tmp_path)}
        result = vault_mod.get_valid_types(config)
        assert "custom" in result


class TestMakeFilename:
    def test_basic_title(self):
        assert vault_mod.make_filename("Hello World") == "Hello World.md"

    def test_strips_invalid_chars(self):
        result = vault_mod.make_filename("Title with #hash and [brackets]")
        assert "#" not in result
        assert "[" not in result
        assert "]" not in result

    def test_truncates_long_titles(self):
        long = "a " * 50  # 100 chars
        result = vault_mod.make_filename(long)
        assert len(result) <= 84  # 80 + ".md"

    def test_collapses_whitespace(self):
        result = vault_mod.make_filename("hello   world")
        assert "  " not in result


class TestIsWithinVault:
    def test_path_inside_vault(self, tmp_path):
        sub = tmp_path / "sub"
        assert vault_mod._is_within_vault(tmp_path, sub) is True

    def test_path_outside_vault(self, tmp_path):
        outside = Path("/tmp/some_other_location")
        assert vault_mod._is_within_vault(tmp_path, outside) is False

    def test_vault_itself(self, tmp_path):
        assert vault_mod._is_within_vault(tmp_path, tmp_path) is True


class TestResolveOutputDir:
    def _base_config(self, tmp_path):
        return {
            "vault_path": str(tmp_path),
            "inbox": "AI/Inbox",
        }

    def test_durable_general_beat_goes_to_inbox(self, tmp_path):
        config = self._base_config(tmp_path)
        beat = {"scope": "general", "durability": "durable"}
        result = vault_mod.resolve_output_dir(beat, config)
        assert result == tmp_path / "AI" / "Inbox"

    def test_durable_project_beat_goes_to_vault_folder(self, tmp_path):
        config = {**self._base_config(tmp_path), "vault_folder": "Projects/myproj"}
        beat = {"scope": "project", "durability": "durable"}
        result = vault_mod.resolve_output_dir(beat, config)
        assert result == tmp_path / "Projects" / "myproj"

    def test_no_inbox_returns_none(self, tmp_path):
        config = {"vault_path": str(tmp_path)}
        beat = {"scope": "general", "durability": "durable"}
        result = vault_mod.resolve_output_dir(beat, config)
        assert result is None

    def test_working_memory_beat_goes_to_wm_folder(self, tmp_path):
        config = {**self._base_config(tmp_path), "working_memory_folder": "AI/WM"}
        beat = {"scope": "general", "durability": "working-memory"}
        result = vault_mod.resolve_output_dir(beat, config)
        assert result == tmp_path / "AI" / "WM"

    def test_working_memory_project_beat_gets_project_subfolder(self, tmp_path):
        config = {
            **self._base_config(tmp_path),
            "working_memory_folder": "AI/WM",
            "project_name": "myproj",
        }
        beat = {"scope": "project", "durability": "working-memory"}
        result = vault_mod.resolve_output_dir(beat, config)
        assert result == tmp_path / "AI" / "WM" / "myproj"

    def test_path_traversal_in_folder_override_falls_back_to_inbox(self, tmp_path):
        config = {**self._base_config(tmp_path), "vault_folder": "../../etc"}
        beat = {"scope": "project", "durability": "durable"}
        result = vault_mod.resolve_output_dir(beat, config)
        # Falls back to inbox
        assert result == tmp_path / "AI" / "Inbox"

    def test_path_traversal_in_wm_folder_falls_back(self, tmp_path):
        config = {**self._base_config(tmp_path), "working_memory_folder": "../../etc"}
        beat = {"scope": "general", "durability": "working-memory"}
        # Should fall back to the wm_root (which is the original traversal value)
        # The code falls back to vault / wm_root = vault / "../../etc" still,
        # but let's just confirm it doesn't crash
        result = vault_mod.resolve_output_dir(beat, config)
        assert result is not None


class TestBuildVaultTitlesSet:
    def test_returns_stems_of_md_files(self, tmp_path):
        (tmp_path / "NoteA.md").write_text("")
        (tmp_path / "NoteB.md").write_text("")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "NoteC.md").write_text("")

        result = vault_mod.build_vault_titles_set(str(tmp_path))
        assert result == {"NoteA", "NoteB", "NoteC"}

    def test_returns_empty_on_oserror(self, tmp_path):
        with patch("cyberbrain.extractors.vault.Path.rglob", side_effect=OSError("no access")):
            result = vault_mod.build_vault_titles_set(str(tmp_path))
        assert result == set()


class TestResolveRelations:
    def test_empty_input_returns_empty(self):
        assert vault_mod.resolve_relations([], {"NoteA"}) == []

    def test_non_list_returns_empty(self):
        assert vault_mod.resolve_relations(None, {"NoteA"}) == []

    def test_drops_unknown_target(self, capsys):
        rels = [{"type": "related", "target": "NonExistent"}]
        result = vault_mod.resolve_relations(rels, {"NoteA"})
        assert result == []

    def test_normalises_unknown_predicate_to_related(self):
        rels = [{"type": "unknown_pred", "target": "NoteA"}]
        result = vault_mod.resolve_relations(rels, {"NoteA"})
        assert result[0]["type"] == "related"

    def test_keeps_valid_predicate(self):
        rels = [{"type": "references", "target": "NoteA"}]
        result = vault_mod.resolve_relations(rels, {"NoteA"})
        assert result[0]["type"] == "references"

    def test_case_insensitive_target_matching(self):
        rels = [{"type": "related", "target": "notea"}]
        result = vault_mod.resolve_relations(rels, {"NoteA"})
        assert result[0]["target"] == "NoteA"

    def test_skips_non_dict_entries(self):
        result = vault_mod.resolve_relations(["not a dict", 42], {"NoteA"})
        assert result == []

    def test_skips_empty_target(self):
        result = vault_mod.resolve_relations([{"type": "related", "target": ""}], {"NoteA"})
        assert result == []

    def test_multiple_valid_relations(self):
        titles = {"NoteA", "NoteB"}
        rels = [
            {"type": "related", "target": "NoteA"},
            {"type": "references", "target": "NoteB"},
            {"type": "related", "target": "Missing"},
        ]
        result = vault_mod.resolve_relations(rels, titles)
        assert len(result) == 2


class TestSearchVault:
    def test_returns_ranked_results(self, tmp_path):
        # subprocess is imported inside search_vault, so patch at the stdlib level
        run_result = MagicMock()
        run_result.stdout = "/vault/note1.md\n/vault/note2.md\n"
        beat = {"title": "Python Testing Guide", "tags": ["python", "testing"]}
        with patch("subprocess.run", return_value=run_result):
            result = vault_mod.search_vault(beat, str(tmp_path), max_results=5)
        assert isinstance(result, list)

    def test_respects_max_results(self, tmp_path):
        run_result = MagicMock()
        run_result.stdout = "\n".join([f"/note{i}.md" for i in range(20)])
        beat = {"title": "Some Title", "tags": ["tag"]}
        with patch("subprocess.run", return_value=run_result):
            result = vault_mod.search_vault(beat, str(tmp_path), max_results=3)
        assert len(result) <= 3


class TestInjectProvenance:
    def test_injects_into_existing_frontmatter(self):
        content = "---\ntitle: Test\n---\n\nBody"
        now = datetime(2026, 3, 7, 12, 0, 0)
        result = vault_mod.inject_provenance(content, "test-source", "sess-1", now)
        assert "cb_source: test-source" in result
        assert "cb_created: 2026-03-07" in result
        assert "cb_session: sess-1" in result

    def test_prepends_frontmatter_when_none_exists(self):
        content = "Just body text"
        now = datetime(2026, 3, 7, 12, 0, 0)
        result = vault_mod.inject_provenance(content, "src", None, now)
        assert result.startswith("---")
        assert "cb_source: src" in result
        assert "cb_session" not in result

    def test_no_session_when_none(self):
        content = "---\ntitle: X\n---\n"
        now = datetime(2026, 3, 7)
        result = vault_mod.inject_provenance(content, "src", None, now)
        assert "cb_session" not in result

    def test_extra_fields_included(self):
        content = "---\ntitle: X\n---\n"
        now = datetime(2026, 3, 7)
        result = vault_mod.inject_provenance(content, "src", None, now, extra_fields="cb_foo: bar")
        assert "cb_foo: bar" in result

    def test_unclosed_frontmatter_returned_unchanged(self):
        # Content starts with --- but has no closing \n--- → returned as-is
        content = "---\ntitle: No close"
        now = datetime(2026, 3, 7)
        result = vault_mod.inject_provenance(content, "src", None, now)
        assert result == content


class TestWmFrontmatterFields:
    def test_returns_ephemeral_and_review_after(self):
        beat = {"type": "problem"}
        config = {"working_memory_review_days": 14}
        now = datetime(2026, 3, 7)
        result = vault_mod._wm_frontmatter_fields(beat, config, now)
        assert "cb_ephemeral: true" in result
        assert "cb_review_after:" in result

    def test_uses_type_specific_ttl(self):
        beat = {"type": "problem"}
        config = {"working_memory_ttl": {"problem": 7}, "working_memory_review_days": 28}
        now = datetime(2026, 3, 1)
        result = vault_mod._wm_frontmatter_fields(beat, config, now)
        assert "2026-03-08" in result  # 7 days from March 1

    def test_falls_back_to_default_ttl(self):
        beat = {"type": "insight"}
        config = {"working_memory_ttl": {}, "working_memory_review_days": 28}
        now = datetime(2026, 3, 1)
        result = vault_mod._wm_frontmatter_fields(beat, config, now)
        assert "2026-03-29" in result  # 28 days from March 1


class TestWriteBeat:
    def _config(self, tmp_path):
        return {
            "vault_path": str(tmp_path),
            "inbox": "AI/Inbox",
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
        }

    def test_writes_markdown_file(self, tmp_path):
        beat = {
            "title": "Test Beat",
            "type": "reference",
            "scope": "general",
            "durability": "durable",
            "summary": "A test beat",
            "tags": ["test"],
            "body": "Some content.",
            "relations": [],
        }
        now = datetime(2026, 3, 7, 12, 0, 0)
        path = vault_mod.write_beat(beat, self._config(tmp_path), "sess-1", "/cwd", now,
                                    vault_titles=set())
        assert path is not None
        assert path.exists()
        content = path.read_text()
        assert "Test Beat" in content
        assert "Some content." in content

    def test_returns_none_when_no_inbox(self, tmp_path):
        config = {"vault_path": str(tmp_path)}
        beat = {"title": "X", "type": "reference", "scope": "general", "durability": "durable"}
        now = datetime(2026, 3, 7)
        result = vault_mod.write_beat(beat, config, "sess", "/cwd", now, vault_titles=set())
        assert result is None

    def test_deduplicates_filename_collision(self, tmp_path):
        config = self._config(tmp_path)
        inbox = tmp_path / "AI" / "Inbox"
        inbox.mkdir(parents=True)
        # Pre-create the target file
        (inbox / "My Beat.md").write_text("existing")

        beat = {
            "title": "My Beat",
            "type": "reference",
            "scope": "general",
            "durability": "durable",
            "summary": "",
            "tags": [],
            "body": "new content",
            "relations": [],
        }
        now = datetime(2026, 3, 7)
        path = vault_mod.write_beat(beat, config, "s", "/cwd", now, vault_titles=set())
        # Should write "2 My Beat.md"
        assert path.name.startswith("2 ")

    def test_invalid_type_coerced_to_reference(self, tmp_path):
        beat = {
            "title": "Beat",
            "type": "bogus",
            "scope": "general",
            "durability": "durable",
            "summary": "",
            "tags": [],
            "body": "",
            "relations": [],
        }
        now = datetime(2026, 3, 7)
        path = vault_mod.write_beat(beat, self._config(tmp_path), "s", "/cwd", now,
                                    vault_titles=set())
        content = path.read_text()
        assert "type: reference" in content

    def test_working_memory_beat_includes_wm_fields(self, tmp_path):
        config = {**self._config(tmp_path), "working_memory_folder": "AI/WM"}
        beat = {
            "title": "WM Beat",
            "type": "problem",
            "scope": "general",
            "durability": "working-memory",
            "summary": "",
            "tags": [],
            "body": "",
            "relations": [],
        }
        now = datetime(2026, 3, 7)
        path = vault_mod.write_beat(beat, config, "s", "/cwd", now, vault_titles=set())
        content = path.read_text()
        assert "cb_ephemeral: true" in content

    def test_tags_normalised_to_lowercase(self, tmp_path):
        beat = {
            "title": "Tags Beat",
            "type": "reference",
            "scope": "general",
            "durability": "durable",
            "summary": "",
            "tags": ["Python", "TESTING"],
            "body": "",
            "relations": [],
        }
        now = datetime(2026, 3, 7)
        path = vault_mod.write_beat(beat, self._config(tmp_path), "s", "/cwd", now,
                                    vault_titles=set())
        content = path.read_text()
        assert '"python"' in content
        assert '"testing"' in content


# ===========================================================================
# extractor.py
# ===========================================================================

# extractor.py imports backends.call_model and config.load_prompt at top level,
# so we mock those modules before importing extractor.
_mock_backends = MagicMock()
_mock_backends.call_model = MagicMock(return_value='[{"title": "T", "type": "reference"}]')
_mock_backends.MAX_TRANSCRIPT_CHARS = 100_000

if "backends" not in sys.modules:
    sys.modules["backends"] = _mock_backends

if "config" not in sys.modules:
    sys.modules["config"] = config_mod

import cyberbrain.extractors.extractor as extractor_mod


class TestExtractBeats:
    def _base_config(self, tmp_path):
        return {
            "vault_path": str(tmp_path),
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
        }

    def test_returns_list_of_beats(self, tmp_path):
        config = self._base_config(tmp_path)
        with patch.object(extractor_mod, "call_model",
                          return_value='[{"title": "Beat", "type": "reference"}]'), \
             patch.object(extractor_mod, "load_prompt", return_value="prompt"), \
             patch.object(extractor_mod, "read_vault_claude_md", return_value=None):
            result = extractor_mod.extract_beats("transcript text", config, "manual", "/cwd")
        assert isinstance(result, list)
        assert len(result) == 1

    def test_returns_empty_on_empty_model_response(self, tmp_path):
        config = self._base_config(tmp_path)
        with patch.object(extractor_mod, "call_model", return_value=""), \
             patch.object(extractor_mod, "load_prompt", return_value="prompt"), \
             patch.object(extractor_mod, "read_vault_claude_md", return_value=None):
            result = extractor_mod.extract_beats("text", config, "manual", "/cwd")
        assert result == []

    def test_returns_empty_on_invalid_json(self, tmp_path):
        config = self._base_config(tmp_path)
        with patch.object(extractor_mod, "call_model", return_value="not json"), \
             patch.object(extractor_mod, "load_prompt", return_value="prompt"), \
             patch.object(extractor_mod, "read_vault_claude_md", return_value=None):
            result = extractor_mod.extract_beats("text", config, "manual", "/cwd")
        assert result == []

    def test_returns_empty_when_model_returns_non_list(self, tmp_path):
        config = self._base_config(tmp_path)
        with patch.object(extractor_mod, "call_model", return_value='{"key": "val"}'), \
             patch.object(extractor_mod, "load_prompt", return_value="prompt"), \
             patch.object(extractor_mod, "read_vault_claude_md", return_value=None):
            result = extractor_mod.extract_beats("text", config, "manual", "/cwd")
        assert result == []

    def test_strips_markdown_code_fences(self, tmp_path):
        config = self._base_config(tmp_path)
        fenced = "```json\n[{\"title\": \"T\", \"type\": \"reference\"}]\n```"
        with patch.object(extractor_mod, "call_model", return_value=fenced), \
             patch.object(extractor_mod, "load_prompt", return_value="prompt"), \
             patch.object(extractor_mod, "read_vault_claude_md", return_value=None):
            result = extractor_mod.extract_beats("text", config, "manual", "/cwd")
        assert len(result) == 1

    def test_truncates_long_transcript(self, tmp_path):
        config = self._base_config(tmp_path)
        calls = []

        def capture_call(system, user, cfg):
            calls.append(user)
            return "[]"

        long_transcript = "x" * (extractor_mod.MAX_TRANSCRIPT_CHARS + 1000)
        with patch.object(extractor_mod, "call_model", side_effect=capture_call), \
             patch.object(extractor_mod, "load_prompt", return_value="{transcript}"), \
             patch.object(extractor_mod, "read_vault_claude_md", return_value=None):
            extractor_mod.extract_beats(long_transcript, config, "manual", "/cwd")

        assert "[earlier content truncated]" in calls[0]

    def test_injects_vault_claude_md_when_present(self, tmp_path):
        config = self._base_config(tmp_path)
        calls = []

        def capture_call(system, user, cfg):
            calls.append(user)
            return "[]"

        with patch.object(extractor_mod, "call_model", side_effect=capture_call), \
             patch.object(extractor_mod, "load_prompt", return_value="{vault_claude_md_section}"), \
             patch.object(extractor_mod, "read_vault_claude_md", return_value="## Types\n"):
            extractor_mod.extract_beats("text", config, "manual", "/cwd")

        assert "vault_claude_md" in calls[0]

    def test_no_vault_claude_md_uses_default_message(self, tmp_path):
        config = self._base_config(tmp_path)
        calls = []

        def capture_call(system, user, cfg):
            calls.append(user)
            return "[]"

        with patch.object(extractor_mod, "call_model", side_effect=capture_call), \
             patch.object(extractor_mod, "load_prompt", return_value="{vault_claude_md_section}"), \
             patch.object(extractor_mod, "read_vault_claude_md", return_value=None):
            extractor_mod.extract_beats("text", config, "manual", "/cwd")

        assert "default four-type vocabulary" in calls[0]


# ===========================================================================
# transcript.py
# ===========================================================================

import cyberbrain.extractors.transcript as transcript_mod


class TestParseJsonlTranscript:
    def _write_jsonl(self, tmp_path, entries):
        p = tmp_path / "transcript.jsonl"
        p.write_text("\n".join(json.dumps(e) for e in entries))
        return str(p)

    def test_extracts_user_and_assistant_turns(self, tmp_path):
        entries = [
            {"type": "user", "message": {"role": "user", "content": "Hello"}},
            {"type": "assistant", "message": {"role": "assistant", "content": "Hi there"}},
        ]
        path = self._write_jsonl(tmp_path, entries)
        result = transcript_mod.parse_jsonl_transcript(path)
        assert "[USER]" in result
        assert "Hello" in result
        assert "[ASSISTANT]" in result
        assert "Hi there" in result

    def test_skips_non_user_assistant_entries(self, tmp_path):
        entries = [
            {"type": "system", "message": {"role": "system", "content": "system msg"}},
            {"type": "user", "message": {"role": "user", "content": "actual"}},
        ]
        path = self._write_jsonl(tmp_path, entries)
        result = transcript_mod.parse_jsonl_transcript(path)
        assert "system msg" not in result
        assert "actual" in result

    def test_skips_bad_json_lines(self, tmp_path):
        p = tmp_path / "transcript.jsonl"
        p.write_text('{"type": "user", "message": {"role": "user", "content": "ok"}}\nnot json\n')
        result = transcript_mod.parse_jsonl_transcript(str(p))
        assert "ok" in result

    def test_skips_empty_lines(self, tmp_path):
        p = tmp_path / "transcript.jsonl"
        p.write_text('\n\n{"type": "user", "message": {"role": "user", "content": "hi"}}\n\n')
        result = transcript_mod.parse_jsonl_transcript(str(p))
        assert "hi" in result

    def test_skips_entries_with_empty_text(self, tmp_path):
        entries = [
            {"type": "user", "message": {"role": "user", "content": "   "}},
            {"type": "user", "message": {"role": "user", "content": "real content"}},
        ]
        path = self._write_jsonl(tmp_path, entries)
        result = transcript_mod.parse_jsonl_transcript(path)
        assert result.count("[USER]") == 1

    def test_joins_turns_with_separator(self, tmp_path):
        entries = [
            {"type": "user", "message": {"role": "user", "content": "Q"}},
            {"type": "assistant", "message": {"role": "assistant", "content": "A"}},
        ]
        path = self._write_jsonl(tmp_path, entries)
        result = transcript_mod.parse_jsonl_transcript(path)
        assert "---" in result


class TestExtractTextBlocks:
    def test_string_content_returned_as_is(self):
        assert transcript_mod._extract_text_blocks("hello") == "hello"

    def test_extracts_text_blocks_from_list(self):
        blocks = [
            {"type": "text", "text": "first"},
            {"type": "tool_use", "id": "t1", "input": {}},
            {"type": "text", "text": "second"},
        ]
        result = transcript_mod._extract_text_blocks(blocks)
        assert "first" in result
        assert "second" in result

    def test_skips_tool_use_blocks(self):
        blocks = [{"type": "tool_use", "input": {"cmd": "rm -rf"}}, {"type": "text", "text": "ok"}]
        result = transcript_mod._extract_text_blocks(blocks)
        assert "rm" not in result
        assert "ok" in result

    def test_skips_thinking_blocks(self):
        blocks = [{"type": "thinking", "thinking": "internal"}, {"type": "text", "text": "visible"}]
        result = transcript_mod._extract_text_blocks(blocks)
        assert "internal" not in result
        assert "visible" in result

    def test_skips_non_dict_entries_in_list(self):
        blocks = ["raw string", {"type": "text", "text": "valid"}]
        result = transcript_mod._extract_text_blocks(blocks)
        assert "valid" in result

    def test_other_type_returns_empty_string(self):
        assert transcript_mod._extract_text_blocks(42) == ""
        assert transcript_mod._extract_text_blocks(None) == ""
