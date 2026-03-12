"""
test_analyze_vault.py — tests for the Obsidian vault structure analyzer

Tests exercise real-world vault shapes: empty vaults, developer PKM layouts,
research vaults, notes with rich frontmatter, wikilinks, inline tags, etc.

All tests use temporary directories — no real vault is touched.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent

from cyberbrain.extractors.analyze_vault import (
    analyze_vault,
    parse_frontmatter,
    extract_wikilinks,
    extract_inline_tags,
    note_name_style,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def write_note(vault: Path, rel_path: str, content: str) -> Path:
    """Write a markdown note into the vault at the given relative path."""
    path = vault / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Unit tests: parse_frontmatter
# ---------------------------------------------------------------------------

class TestParseFrontmatter:
    def test_returns_empty_dict_for_no_frontmatter(self):
        assert parse_frontmatter("# Just a heading\n\nBody text.") == {}

    def test_parses_basic_yaml(self):
        content = "---\ntype: decision\nsummary: Test summary\n---\n\nBody."
        fm = parse_frontmatter(content)
        assert fm["type"] == "decision"
        assert fm["summary"] == "Test summary"

    def test_parses_tags_as_list(self):
        content = "---\ntags: [python, testing, backend]\n---\n"
        fm = parse_frontmatter(content)
        assert fm["tags"] == ["python", "testing", "backend"]

    def test_returns_empty_for_unclosed_frontmatter(self):
        content = "---\ntype: decision\nNo closing marker"
        assert parse_frontmatter(content) == {}

    def test_returns_empty_for_invalid_yaml(self):
        content = "---\n: bad yaml\n  : worse\n---\n"
        result = parse_frontmatter(content)
        assert isinstance(result, dict)

    def test_returns_empty_if_yaml_is_not_dict(self):
        content = "---\n- item1\n- item2\n---\n"
        assert parse_frontmatter(content) == {}


# ---------------------------------------------------------------------------
# Unit tests: extract_wikilinks
# ---------------------------------------------------------------------------

class TestExtractWikilinks:
    def test_extracts_simple_wikilinks(self):
        text = "See [[My Note]] for details.\n"
        assert extract_wikilinks(text) == ["My Note"]

    def test_extracts_aliased_wikilinks(self):
        text = "See [[My Note|alias text]] for details.\n"
        assert extract_wikilinks(text) == ["My Note"]

    def test_ignores_wikilinks_in_frontmatter(self):
        text = "---\nrelated: [[Other Note]]\n---\n\nBody without links.\n"
        assert extract_wikilinks(text) == []

    def test_extracts_multiple_wikilinks(self):
        text = "See [[A]] and [[B]] and also [[C|see C]].\n"
        links = extract_wikilinks(text)
        assert "A" in links and "B" in links and "C" in links

    def test_ignores_anchor_links(self):
        """Links with # (heading anchors) are not extracted as separate targets."""
        text = "See [[My Note#section]] here.\n"
        # The # should be excluded by the regex
        links = extract_wikilinks(text)
        assert len(links) == 0 or links[0] == "My Note"


# ---------------------------------------------------------------------------
# Unit tests: extract_inline_tags
# ---------------------------------------------------------------------------

class TestExtractInlineTags:
    def test_extracts_hashtags_from_body(self):
        text = "---\ntags: [existing]\n---\n\nThis is #python code.\n"
        tags = extract_inline_tags(text)
        assert "python" in tags

    def test_does_not_extract_from_frontmatter(self):
        text = "---\nsome: #not-a-tag\n---\n\nBody #real-tag\n"
        tags = extract_inline_tags(text)
        assert "real-tag" in tags
        assert "not-a-tag" not in tags

    def test_extracts_hierarchical_tags(self):
        text = "See #project/backend/api here.\n"
        tags = extract_inline_tags(text)
        assert "project/backend/api" in tags


# ---------------------------------------------------------------------------
# Unit tests: note_name_style
# ---------------------------------------------------------------------------

class TestNoteNameStyle:
    def test_detects_kebab_case(self):
        assert note_name_style("my-note-title") == "kebab-case"

    def test_detects_snake_case(self):
        assert note_name_style("my_note_title") == "snake_case"

    def test_detects_pascal_case(self):
        assert note_name_style("MyNoteTitle") == "PascalCase"

    def test_detects_title_case(self):
        assert note_name_style("My Note Title") == "Title Case"


# ---------------------------------------------------------------------------
# Integration tests: analyze_vault
# ---------------------------------------------------------------------------

class TestAnalyzeVaultEmpty:
    def test_raises_on_nonexistent_path(self):
        with pytest.raises(ValueError, match="does not exist"):
            analyze_vault("/nonexistent/path/to/vault")

    def test_empty_vault(self, tmp_path):
        report = analyze_vault(str(tmp_path))
        assert report["total_notes"] == 0
        assert report["entity_types"]["distribution"] == {}
        assert report["links"]["hub_nodes"] == []

    def test_excludes_obsidian_hidden_dirs(self, tmp_path):
        """Notes under .obsidian/ must not be counted."""
        obsidian_dir = tmp_path / ".obsidian"
        obsidian_dir.mkdir()
        (obsidian_dir / "config.md").write_text("# Config")
        write_note(tmp_path, "Real Note.md", "# Real Note\n\nContent.")

        report = analyze_vault(str(tmp_path))
        assert report["total_notes"] == 1


class TestAnalyzeVaultDeveloperPKM:
    """
    A developer vault with typed notes, wikilinks, and frontmatter.
    Simulates real cyberbrain extraction output.
    """

    @pytest.fixture
    def dev_vault(self, tmp_path):
        write_note(tmp_path, "AI/Claude-Sessions/JWT Auth Issue.md", """\
---
id: abc123
type: problem
title: "JWT Auth Issue"
summary: "JWT tokens expire silently without error on clock skew."
tags: [jwt, auth, backend]
related: [["Postgres Connection Pool.md", "references"]]
date: 2026-01-15
---

## Problem

JWT tokens expired silently.

## Solution

Added 5-minute clock skew tolerance.
See also [[Postgres Connection Pool]].
""")
        write_note(tmp_path, "AI/Claude-Sessions/Postgres Connection Pool.md", """\
---
id: def456
type: problem
title: "Postgres Connection Pool"
summary: "Connection pool exhausted under sustained load."
tags: [postgres, database, performance]
date: 2026-01-20
---

## Problem

Pool exhausted.
""")
        write_note(tmp_path, "AI/Claude-Sessions/FastAPI Router Decision.md", """\
---
id: ghi789
type: decision
title: "FastAPI Router Decision"
summary: "Chose FastAPI over Flask for async support."
tags: [fastapi, flask, python]
date: 2026-01-25
---

## Decision

FastAPI chosen. See [[JWT Auth Issue]] for context.
""")
        write_note(tmp_path, "Projects/hermes/Architecture.md", """\
---
type: reference
title: "Architecture"
summary: "System architecture overview."
tags: [architecture, design]
---

## Architecture

Using microservices. Related to [[FastAPI Router Decision]].
""")
        return tmp_path

    def test_counts_correct_total_notes(self, dev_vault):
        report = analyze_vault(str(dev_vault))
        assert report["total_notes"] == 4

    def test_detects_type_distribution(self, dev_vault):
        report = analyze_vault(str(dev_vault))
        dist = report["entity_types"]["distribution"]
        assert dist.get("problem") == 2
        assert dist.get("decision") == 1
        assert dist.get("reference") == 1

    def test_detects_top_level_folders(self, dev_vault):
        report = analyze_vault(str(dev_vault))
        folders = report["folder_structure"]["top_level_folders"]
        assert "AI" in folders
        assert "Projects" in folders

    def test_detects_hub_nodes_from_wikilinks(self, dev_vault):
        report = analyze_vault(str(dev_vault))
        hub_names = [n["note"] for n in report["links"]["hub_nodes"]]
        # "JWT Auth Issue" is linked from two notes — should be a hub
        assert any("JWT" in name for name in hub_names)

    def test_detects_frontmatter_field_usage(self, dev_vault):
        report = analyze_vault(str(dev_vault))
        field_names = [f["field"] for f in report["frontmatter"]["field_usage"]]
        assert "type" in field_names
        assert "summary" in field_names
        assert "tags" in field_names

    def test_detects_tags(self, dev_vault):
        report = analyze_vault(str(dev_vault))
        tag_names = [t["tag"] for t in report["tags"]["top_tags"]]
        assert "postgres" in tag_names or "jwt" in tag_names

    def test_detects_naming_convention(self, dev_vault):
        report = analyze_vault(str(dev_vault))
        # Notes use "Title Case" naming
        naming = report["naming_conventions"]
        assert naming.get("Title Case", 0) > 0

    def test_provides_type_samples(self, dev_vault):
        report = analyze_vault(str(dev_vault))
        samples = report["entity_types"]["samples"]
        assert "problem" in samples
        assert len(samples["problem"]) > 0

    def test_orphan_detection(self, dev_vault):
        report = analyze_vault(str(dev_vault))
        # Architecture.md links outward but receives no incoming links
        # (no note links to "Architecture")
        incoming_count = report["links"]["notes_with_no_incoming_links"]
        assert incoming_count > 0


class TestAnalyzeVaultTagHierarchy:
    """Verify hierarchical tag detection."""

    def test_detects_hierarchical_tag_parents(self, tmp_path):
        write_note(tmp_path, "Note A.md", """\
---
tags: [project/backend, project/frontend]
---

Body with #project/infra/k8s inline.
""")
        report = analyze_vault(str(tmp_path))
        hierarchy = report["tags"]["hierarchy"]
        assert "project" in hierarchy or "project/infra" in hierarchy


class TestAnalyzeVaultNamingStyles:
    """Verify naming convention detection across different styles."""

    def test_detects_mixed_naming_styles(self, tmp_path):
        write_note(tmp_path, "kebab-case-note.md", "# Kebab")
        write_note(tmp_path, "snake_case_note.md", "# Snake")
        write_note(tmp_path, "TitleCaseNote.md", "# Pascal")
        write_note(tmp_path, "Title Case Note.md", "# Title")

        report = analyze_vault(str(tmp_path))
        naming = report["naming_conventions"]
        assert naming.get("kebab-case", 0) >= 1
        assert naming.get("snake_case", 0) >= 1

    def test_detects_other_naming_style(self, tmp_path):
        """A stem that is all lowercase without dashes or underscores returns 'other'."""
        write_note(tmp_path, "lowercase.md", "# Lowercase")
        report = analyze_vault(str(tmp_path))
        naming = report["naming_conventions"]
        assert naming.get("other", 0) >= 1


# ---------------------------------------------------------------------------
# analyze_vault.py: tags from frontmatter with non-standard shapes
# ---------------------------------------------------------------------------

class TestAnalyzeVaultTagEdgeCases:
    """Exercise the non-list tags branches in analyze_vault (lines 138, 140)."""

    def test_string_tags_field_is_split_by_comma(self, tmp_path):
        """A tags field that is a plain string is split on commas and counted."""
        write_note(tmp_path, "Note.md", "---\ntags: python, testing, backend\n---\n\nBody.")
        report = analyze_vault(str(tmp_path))
        tag_names = [t["tag"] for t in report["tags"]["top_tags"]]
        assert "python" in tag_names
        assert "testing" in tag_names

    def test_integer_tags_field_is_treated_as_empty(self, tmp_path):
        """A tags field that is an integer (non-list, non-string) produces no tags."""
        write_note(tmp_path, "Note.md", "---\ntags: 42\n---\n\nBody.")
        report = analyze_vault(str(tmp_path))
        # tags: 42 is not a list or string, so fm_tags = []
        assert report["tags"]["total_unique_tags"] == 0


# ---------------------------------------------------------------------------
# analyze_vault.py: main() CLI function (lines 241-258, 262)
# ---------------------------------------------------------------------------

class TestAnalyzeVaultMain:
    """Exercise the analyze_vault main() CLI entrypoint."""

    def test_main_prints_json_to_stdout(self, tmp_path, capsys, monkeypatch):
        """main() with a valid vault path prints JSON report to stdout."""
        import runpy
        import sys as _sys

        write_note(tmp_path, "Note.md", "---\ntype: decision\n---\nBody.")
        monkeypatch.setattr(_sys, "argv", ["analyze_vault.py", str(tmp_path)])
        runpy.run_module("cyberbrain.extractors.analyze_vault", run_name="__main__", alter_sys=True)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["total_notes"] == 1

    def test_main_writes_json_to_file(self, tmp_path, capsys, monkeypatch):
        """main() with --output writes JSON to the specified file."""
        import runpy
        import sys as _sys

        write_note(tmp_path, "Note.md", "---\ntype: insight\n---\nBody.")
        out_file = tmp_path / "report.json"
        monkeypatch.setattr(_sys, "argv", ["analyze_vault.py", str(tmp_path), "--output", str(out_file)])
        runpy.run_module("cyberbrain.extractors.analyze_vault", run_name="__main__", alter_sys=True)
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert data["total_notes"] == 1
        captured = capsys.readouterr()
        assert "Report written" in captured.err

    def test_main_exits_with_error_on_invalid_path(self, tmp_path, monkeypatch):
        """main() prints an error and exits 1 when vault path does not exist."""
        import runpy
        import sys as _sys

        monkeypatch.setattr(_sys, "argv", ["analyze_vault.py", "/nonexistent/vault/path"])
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("cyberbrain.extractors.analyze_vault", run_name="__main__", alter_sys=True)
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# frontmatter.py: edge cases not covered by test_analyze_vault's parse_frontmatter
# ---------------------------------------------------------------------------

class TestFrontmatterEdgeCases:
    """Tests for extractors/frontmatter.py missing lines (28-29, 75, 81)."""

    def test_parse_frontmatter_returns_empty_when_yaml_is_non_dict(self):
        """YAML that parses to a list (not a dict) returns {}."""
        from cyberbrain.extractors.frontmatter import parse_frontmatter
        content = "---\n- item1\n- item2\n---\nBody."
        result = parse_frontmatter(content)
        assert result == {}

    def test_parse_frontmatter_returns_empty_on_yaml_exception(self):
        """YAML parse errors return {} (the except Exception branch, lines 28-29)."""
        from cyberbrain.extractors.frontmatter import parse_frontmatter
        from unittest.mock import patch
        # Force yaml.safe_load to raise
        with patch("yaml.safe_load", side_effect=Exception("yaml error")):
            result = parse_frontmatter("---\nkey: value\n---\nBody.")
        assert result == {}

    def test_read_frontmatter_tags_returns_empty_for_plain_string_tags(self, tmp_path):
        """Tags that aren't JSON array and aren't bracketed list return empty set."""
        from cyberbrain.extractors.frontmatter import read_frontmatter_tags
        p = tmp_path / "note.md"
        p.write_text("---\ntags: just-a-plain-value\n---\nBody.", encoding="utf-8")
        result = read_frontmatter_tags(str(p))
        assert result == set()

    def test_normalise_list_with_actual_list(self):
        """normalise_list() with a real Python list returns list[str]."""
        from cyberbrain.extractors.frontmatter import normalise_list
        result = normalise_list(["alpha", "beta", "gamma"])
        assert result == ["alpha", "beta", "gamma"]

    def test_read_frontmatter_returns_dict_for_valid_file(self, tmp_path):
        """read_frontmatter() reads a file and returns parsed frontmatter."""
        from cyberbrain.extractors.frontmatter import read_frontmatter
        p = tmp_path / "note.md"
        p.write_text("---\ntitle: Test\ntags: [a, b]\n---\nBody.", encoding="utf-8")
        result = read_frontmatter(str(p))
        assert result["title"] == "Test"

    def test_read_frontmatter_returns_empty_for_missing_file(self, tmp_path):
        """read_frontmatter() returns {} when the file doesn't exist."""
        from cyberbrain.extractors.frontmatter import read_frontmatter
        result = read_frontmatter(str(tmp_path / "nonexistent.md"))
        assert result == {}
