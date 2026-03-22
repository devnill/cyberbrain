"""
tests/test_repair_frontmatter.py — Tests for scripts/repair_frontmatter.py

Tests cover:
- parse_frontmatter: no frontmatter, valid frontmatter with body, frontmatter
  with --- heading lines in body (closing-delimiter edge case), malformed
  frontmatter (no closing ---)
- find_duplicate_keys: no duplicates, single duplicate, multiple distinct
  duplicates, block-sequence continuation lines not misidentified as keys
- deduplicate_frontmatter: last-occurrence wins, all keys deduplicated,
  block-sequence continuation lines preserved, body content preserved exactly
- repair_file: idempotent, body preserved, no-duplicate files returned as-is
"""

import importlib.util
from pathlib import Path

# ---------------------------------------------------------------------------
# Module loading — repair_frontmatter.py lives in scripts/
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "repair_frontmatter", SCRIPTS_DIR / "repair_frontmatter.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()
parse_frontmatter = _mod.parse_frontmatter
find_duplicate_keys = _mod.find_duplicate_keys
deduplicate_frontmatter = _mod.deduplicate_frontmatter
repair_file = _mod.repair_file


# ---------------------------------------------------------------------------
# parse_frontmatter
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    def test_no_frontmatter_plain_markdown(self):
        text = "# Hello\n\nJust some content.\n"
        lines, body, has_fm = parse_frontmatter(text)
        assert has_fm is False
        assert lines is None
        assert body == text

    def test_valid_frontmatter_with_body(self):
        text = "---\ntitle: My Note\ntags: [foo, bar]\n---\n# Body\n\nContent here.\n"
        lines, body, has_fm = parse_frontmatter(text)
        assert has_fm is True
        assert lines is not None
        joined = "".join(lines)
        assert "title: My Note" in joined
        assert "tags: [foo, bar]" in joined
        assert body == "\n# Body\n\nContent here.\n"

    def test_non_bare_dashes_not_treated_as_closing_delimiter(self):
        """'--- heading' inside frontmatter block must not be treated as closing delimiter."""
        text = (
            "---\n"
            "title: Edge Case\n"
            "--- not a delimiter\n"
            "extra_key: value\n"
            "---\n"
            "Body content\n"
        )
        lines, body, has_fm = parse_frontmatter(text)
        assert has_fm is True
        # Real closing --- is the bare one; frontmatter includes all three key lines
        assert "title: Edge Case" in "".join(lines)
        assert "extra_key: value" in "".join(lines)
        assert body == "\nBody content\n"

    def test_bare_dashes_in_body_preserved(self):
        """A bare --- horizontal rule in the body must not disturb the already-found closing delimiter."""
        text = "---\ntitle: My Note\n---\n## Heading\n---\nMore content\n"
        lines, body, has_fm = parse_frontmatter(text)
        assert has_fm is True
        assert "title: My Note" in "".join(lines)
        assert "---\n" in body
        assert "More content\n" in body

    def test_malformed_no_closing_delimiter(self):
        text = "---\ntitle: Broken\nno closing delimiter here\n"
        lines, body, has_fm = parse_frontmatter(text)
        assert has_fm is False
        assert lines is None
        assert body == text

    def test_empty_frontmatter_block(self):
        text = "---\n---\n# Just a body\n"
        lines, body, has_fm = parse_frontmatter(text)
        assert has_fm is True
        assert lines == []
        assert body == "\n# Just a body\n"

    def test_frontmatter_no_body(self):
        text = "---\ntitle: No Body\n---"
        lines, body, has_fm = parse_frontmatter(text)
        assert has_fm is True
        assert "title: No Body" in "".join(lines)
        assert body == ""


# ---------------------------------------------------------------------------
# find_duplicate_keys
# ---------------------------------------------------------------------------


class TestFindDuplicateKeys:
    def test_no_duplicates(self):
        lines = ["title: My Note\n", "tags: [foo]\n", "type: insight\n"]
        result = find_duplicate_keys(lines)
        assert result == {}

    def test_single_duplicate_key(self):
        lines = ["title: First\n", "tags: [foo]\n", "title: Second\n"]
        result = find_duplicate_keys(lines)
        assert result == {"title": 2}

    def test_multiple_distinct_duplicate_keys(self):
        lines = [
            "title: A\n",
            "tags: [x]\n",
            "title: B\n",
            "tags: [y]\n",
            "type: insight\n",
        ]
        result = find_duplicate_keys(lines)
        assert result == {"title": 2, "tags": 2}

    def test_block_sequence_continuation_not_a_key(self):
        """Indented continuation lines in a block sequence must not be counted as keys."""
        lines = [
            "title: My Note\n",
            "tags:\n",
            "  - foo\n",
            "  - bar\n",
            "type: insight\n",
        ]
        result = find_duplicate_keys(lines)
        assert result == {}

    def test_key_with_colon_in_value_not_double_counted(self):
        """A value containing ':' should not create a spurious duplicate."""
        lines = ["url: https://example.com\n", "title: Note\n"]
        result = find_duplicate_keys(lines)
        assert result == {}


# ---------------------------------------------------------------------------
# deduplicate_frontmatter
# ---------------------------------------------------------------------------


class TestDeduplicateFrontmatter:
    def test_last_occurrence_wins(self):
        lines = ["title: First\n", "title: Second\n"]
        result = deduplicate_frontmatter(lines)
        # Only the last 'title' should remain
        assert result == ["title: Second\n"]

    def test_all_keys_deduplicated(self):
        lines = [
            "title: A\n",
            "tags: [x]\n",
            "title: B\n",
            "tags: [y]\n",
        ]
        result = deduplicate_frontmatter(lines)
        result_text = "".join(result)
        assert "title: B\n" in result_text
        assert "tags: [y]\n" in result_text
        assert "title: A" not in result_text
        assert "tags: [x]" not in result_text

    def test_continuation_lines_preserved_under_last_occurrence(self):
        """Block-sequence values (indented lines) must travel with their key."""
        lines = [
            "title: First\n",
            "tags:\n",
            "  - old\n",
            "title: Second\n",
            "tags:\n",
            "  - new\n",
        ]
        result = deduplicate_frontmatter(lines)
        result_text = "".join(result)
        assert "title: Second\n" in result_text
        assert "  - new\n" in result_text
        assert "title: First" not in result_text
        assert "  - old" not in result_text

    def test_no_duplicates_unchanged(self):
        lines = ["title: Note\n", "tags: [foo]\n", "type: insight\n"]
        result = deduplicate_frontmatter(lines)
        assert result == lines


# ---------------------------------------------------------------------------
# repair_file
# ---------------------------------------------------------------------------


class TestRepairFile:
    def test_no_frontmatter_returns_none(self):
        text = "# Plain Note\n\nNo frontmatter here.\n"
        repaired, dupes = repair_file(text)
        assert repaired is None
        assert dupes == {}

    def test_no_duplicates_returns_none(self):
        text = "---\ntitle: Clean\ntags: [foo]\n---\n\n# Body\n"
        repaired, dupes = repair_file(text)
        assert repaired is None
        assert dupes == {}

    def test_duplicates_repaired_and_body_preserved(self):
        body = "\n# My Note\n\nSome content.\n"
        text = "---\ntitle: First\ntags: [foo]\ntitle: Second\n---" + body
        repaired, dupes = repair_file(text)
        assert repaired is not None
        assert "title" in dupes
        assert dupes["title"] == 2
        # Body must be preserved exactly
        assert repaired.endswith(body)
        # Only last title remains
        assert "title: Second" in repaired
        assert "title: First" not in repaired

    def test_idempotent(self):
        """Calling repair_file twice on the output produces the same result."""
        text = "---\ntitle: First\ntitle: Second\n---\n\n# Body\n"
        repaired1, dupes1 = repair_file(text)
        assert repaired1 is not None
        assert dupes1 == {"title": 2}
        # Second pass: no duplicates remain, so repair_file returns None
        repaired2, dupes2 = repair_file(repaired1)
        assert repaired2 is None
        assert dupes2 == {}

    def test_repair_file_with_tmp_path(self, tmp_path):
        """Integration-style check: write file, repair, verify file on disk."""
        md = tmp_path / "note.md"
        original = "---\ntitle: One\ntags: [a]\ntitle: Two\n---\n\n# Content\n"
        md.write_text(original, encoding="utf-8")

        text = md.read_text(encoding="utf-8")
        repaired, dupes = repair_file(text)
        assert repaired is not None

        md.write_text(repaired, encoding="utf-8")
        on_disk = md.read_text(encoding="utf-8")

        # Idempotency: second repair returns None
        repaired2, _ = repair_file(on_disk)
        assert repaired2 is None
