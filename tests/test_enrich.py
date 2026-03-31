"""
test_enrich.py — focused tests for WI-104 fixes:
  - _apply_frontmatter_update idempotency (ruamel.yaml rewrite)
  - no duplicate frontmatter keys
  - placeholder summary/tag detection in _needs_enrichment
  - valid summary preserved when overwrite=False
"""

import re
from pathlib import Path

from cyberbrain.extractors.frontmatter import parse_frontmatter
from cyberbrain.mcp.tools.enrich import (
    _PLACEHOLDER_SUMMARIES,
    _PLACEHOLDER_TAGS,
    _apply_frontmatter_update,
    _needs_enrichment,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_note(tmp_path: Path, content: str) -> Path:
    note = tmp_path / "test_note.md"
    note.write_text(content, encoding="utf-8")
    return note


# ---------------------------------------------------------------------------
# _apply_frontmatter_update — idempotency
# ---------------------------------------------------------------------------


def _strip_timestamps(s: str) -> str:
    """Remove cb_modified and updated timestamp lines to avoid second-boundary flakiness."""
    s = re.sub(r"cb_modified: .*\n", "", s)
    s = re.sub(r"updated: .*\n", "", s)
    return s


class TestApplyFrontmatterIdempotent:
    def test_apply_frontmatter_idempotent(self, tmp_path):
        """Running _apply_frontmatter_update twice with same classification produces identical output."""
        note = make_note(
            tmp_path,
            "---\ntitle: Test Note\ntype: note\nsummary: Original summary\ntags: [tag1, tag2]\n---\nBody content.\n",
        )
        classification = {
            "type": "resource",
            "summary": "New summary",
            "tags": ["tag1", "tag2"],
        }

        _apply_frontmatter_update(
            note, note.read_text(), classification, overwrite=True
        )
        first_result = note.read_text()

        _apply_frontmatter_update(
            note, note.read_text(), classification, overwrite=True
        )
        second_result = note.read_text()

        assert _strip_timestamps(first_result) == _strip_timestamps(second_result), (
            "Second run should produce identical output to first run (idempotent).\n"
            f"First:\n{first_result}\n\nSecond:\n{second_result}"
        )


# ---------------------------------------------------------------------------
# _apply_frontmatter_update — no duplicate keys
# ---------------------------------------------------------------------------


class TestApplyFrontmatterNoDuplicateKeys:
    def test_apply_frontmatter_no_duplicate_keys(self, tmp_path):
        """Running enrich multiple times must not produce duplicate frontmatter keys."""
        note = make_note(
            tmp_path,
            "---\ntitle: Test Note\ntype: note\nsummary: Original summary\ntags: [tag1, tag2]\n---\nBody.\n",
        )
        classification = {
            "type": "resource",
            "summary": "Enriched summary",
            "tags": ["work", "python"],
        }

        # Run three times
        for _ in range(3):
            _apply_frontmatter_update(
                note, note.read_text(), classification, overwrite=True
            )

        content = note.read_text()
        # Extract frontmatter block
        assert content.startswith("---"), "Note should start with ---"
        fm_end = content.find("\n---", 3)
        assert fm_end != -1, "Should have closing ---"
        fm_text = content[3:fm_end]

        # Count occurrences of each key
        seen_keys: dict[str, int] = {}
        for line in fm_text.splitlines():
            if ":" in line and not line.startswith(" ") and not line.startswith("-"):
                key = line.split(":")[0].strip()
                if key:
                    seen_keys[key] = seen_keys.get(key, 0) + 1

        duplicates = {k: v for k, v in seen_keys.items() if v > 1}
        assert not duplicates, f"Duplicate frontmatter keys found: {duplicates}"


# ---------------------------------------------------------------------------
# _needs_enrichment — placeholder detection
# ---------------------------------------------------------------------------


class TestNeedsEnrichmentPlaceholderSummary:
    def test_needs_enrichment_detects_placeholder_summary(self, tmp_path):
        """_needs_enrichment returns (True, 'placeholder summary') for placeholder summary value."""
        note = make_note(
            tmp_path,
            '---\ntitle: Test\ntype: note\nsummary: "New accurate summary."\ntags: [real-tag]\n---\nBody.\n',
        )
        fm = parse_frontmatter(note.read_text())
        result, reason = _needs_enrichment(
            note, fm, {"project", "note", "resource", "archived"}, False
        )
        assert result is True
        assert "placeholder" in reason.lower()

    def test_placeholder_summary_constant_defined(self):
        """_PLACEHOLDER_SUMMARIES constant must contain the known placeholder value."""
        assert "New accurate summary." in _PLACEHOLDER_SUMMARIES
        assert "" in _PLACEHOLDER_SUMMARIES


class TestNeedsEnrichmentPlaceholderTags:
    def test_needs_enrichment_detects_placeholder_tags(self, tmp_path):
        """_needs_enrichment returns (True, 'placeholder tags') when tags are all placeholders."""
        note = make_note(
            tmp_path,
            "---\ntitle: Test\ntype: note\nsummary: A real summary that is not a placeholder.\ntags: [new-tag, updated]\n---\nBody.\n",
        )
        fm = parse_frontmatter(note.read_text())
        result, reason = _needs_enrichment(
            note, fm, {"project", "note", "resource", "archived"}, False
        )
        assert result is True
        assert "placeholder" in reason.lower()

    def test_placeholder_tags_constant_defined(self):
        """_PLACEHOLDER_TAGS constant must contain the known placeholder values."""
        assert "new-tag" in _PLACEHOLDER_TAGS
        assert "updated" in _PLACEHOLDER_TAGS

    def test_partial_placeholder_tags_not_flagged(self, tmp_path):
        """Tags that include real tags alongside placeholder values are NOT flagged."""
        note = make_note(
            tmp_path,
            "---\ntitle: Test\ntype: note\nsummary: A real summary that is not a placeholder.\ntags: [new-tag, python]\n---\nBody.\n",
        )
        fm = parse_frontmatter(note.read_text())
        result, reason = _needs_enrichment(
            note, fm, {"project", "note", "resource", "archived"}, False
        )
        # python is not in _PLACEHOLDER_TAGS so set is not a subset
        assert result is False


# ---------------------------------------------------------------------------
# _apply_frontmatter_update — preserves valid summary when overwrite=False
# ---------------------------------------------------------------------------


class TestApplyFrontmatterPreservesValidSummary:
    def test_apply_frontmatter_preserves_valid_summary(self, tmp_path):
        """A real, non-placeholder summary must not be overwritten when overwrite=False."""
        original_summary = (
            "This is a detailed and accurate summary that should be kept."
        )
        note = make_note(
            tmp_path,
            f"---\ntitle: Test\ntype: note\nsummary: {original_summary}\ntags: [python, work]\n---\nBody.\n",
        )
        classification = {
            "type": "resource",
            "summary": "Replacement summary that should NOT be used",
            "tags": ["new-tag"],
        }

        _apply_frontmatter_update(
            note, note.read_text(), classification, overwrite=False
        )

        content = note.read_text()
        fm = parse_frontmatter(content)
        assert fm.get("summary") == original_summary, (
            f"Valid summary should be preserved. Got: {fm.get('summary')!r}"
        )

    def test_apply_frontmatter_overwrites_placeholder_summary_when_overwrite_false(
        self, tmp_path
    ):
        """Placeholder summary IS replaced even when overwrite=False."""
        note = make_note(
            tmp_path,
            '---\ntitle: Test\ntype: note\nsummary: "New accurate summary."\ntags: [python]\n---\nBody.\n',
        )
        classification = {
            "type": "note",
            "summary": "Real replacement summary",
            "tags": ["python"],
        }

        _apply_frontmatter_update(
            note, note.read_text(), classification, overwrite=False
        )

        content = note.read_text()
        fm = parse_frontmatter(content)
        assert fm.get("summary") == "Real replacement summary", (
            f"Placeholder summary should have been replaced. Got: {fm.get('summary')!r}"
        )


# ---------------------------------------------------------------------------
# _apply_frontmatter_update — timestamps
# ---------------------------------------------------------------------------


class TestApplyFrontmatterTimestamps:
    def test_sets_cb_modified_and_updated_on_write(self, tmp_path):
        """cb_modified and updated fields are set when changes are written."""
        note = make_note(
            tmp_path,
            "---\ntitle: Test\ntype: note\n---\nBody.\n",
        )
        classification = {
            "type": "resource",
            "summary": "Summary",
            "tags": ["python"],
        }

        _apply_frontmatter_update(
            note, note.read_text(), classification, overwrite=True
        )

        fm = parse_frontmatter(note.read_text())
        assert "cb_modified" in fm, "cb_modified should be set"
        assert "updated" in fm, "updated should be set"

        # updated should be YYYY-MM-DD format
        import re

        assert re.match(r"^\d{4}-\d{2}-\d{2}$", str(fm["updated"])), (
            f"updated should be YYYY-MM-DD, got: {fm['updated']!r}"
        )
