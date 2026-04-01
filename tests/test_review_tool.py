"""
test_review_tool.py — unit tests for src/cyberbrain/mcp/tools/review.py

Covers:
- _read_vault_prefs: no CLAUDE.md, no prefs heading, has prefs, with following section
- _find_due_notes: finds due notes, skips non-ephemeral, skips bad dates, skips hidden dirs
- _cluster_notes: single note, backend=None returns singletons, multi-note with backend
- _format_notes_block: singleton, multi-note cluster
- _extend_review_after: bumps date, OSError, no cb_review_after field
- _append_errata: writes log, skips when empty, skips when disabled
- cb_review: no vault, vault missing, wm_root missing, no due notes, dry_run=True,
             dry_run=False with promote/extend/delete/unknown/missing actions
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# sys.path setup
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# sys.modules setup — why this file needs it
#
# Module guarded:  cyberbrain.extractors.quality_gate  (if not yet imported)
# Module cleared:  cyberbrain.mcp.tools.review
#
# quality_gate imports from cyberbrain.extractors.backends at module level.
# If it loads before the conftest mock is in place it would try to connect to
# a real LLM backend.  We install a MagicMock guard the first time this module
# runs; subsequent runs leave the existing (mock or real) entry untouched.
#
# review.py is evicted from the cache so it re-imports against the current
# conftest mock state and its register() call binds to this file's FakeMCP.
# ---------------------------------------------------------------------------
from tests.conftest import _clear_module_cache

if "cyberbrain.extractors.quality_gate" not in sys.modules:
    _mock_qg = MagicMock()
    sys.modules["cyberbrain.extractors.quality_gate"] = _mock_qg

_clear_module_cache(["cyberbrain.mcp.tools.review"])

from fastmcp.exceptions import ToolError  # noqa: E402

import cyberbrain.mcp.shared as _shared
import cyberbrain.mcp.tools.review as review_mod

# ---------------------------------------------------------------------------
# FakeMCP + tool registration
# ---------------------------------------------------------------------------


class FakeMCP:
    def __init__(self):
        self._tools = {}

    def tool(self, annotations=None, **kwargs):
        def decorator(fn):
            self._tools[fn.__name__] = {"fn": fn}
            return fn

        return decorator


_fake_mcp = FakeMCP()
review_mod.register(_fake_mcp)


def _cb_review():
    return _fake_mcp._tools["cb_review"]["fn"]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_wm_note(tmp_path, name, review_after, summary="", ephemeral=True):
    """Write a working-memory markdown note to tmp_path."""
    fm_lines = ["---", "title: " + name]
    if ephemeral:
        fm_lines.append("cb_ephemeral: true")
        fm_lines.append(f"cb_review_after: {review_after}")
    if summary:
        fm_lines.append(f"summary: {summary}")
    fm_lines.append("---")
    content = "\n".join(fm_lines) + f"\n\n## {name}\n\nBody text.\n"
    path = tmp_path / (name.replace(" ", "-") + ".md")
    path.write_text(content)
    return path


# ===========================================================================
# _read_vault_prefs
# ===========================================================================


class TestReadVaultPrefs:
    def test_returns_empty_when_no_claude_md(self, tmp_path):
        result = review_mod._read_vault_prefs(str(tmp_path))
        assert result == ""

    def test_returns_empty_when_no_prefs_heading(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# Vault\n\n## Other Section\n")
        result = review_mod._read_vault_prefs(str(tmp_path))
        assert result == ""

    def test_returns_prefs_section(self, tmp_path):
        content = "# Vault\n\n## Cyberbrain Preferences\n\nDo this.\n"
        (tmp_path / "CLAUDE.md").write_text(content)
        result = review_mod._read_vault_prefs(str(tmp_path))
        assert "Do this." in result

    def test_prefs_stops_at_next_h2(self, tmp_path):
        content = (
            "## Cyberbrain Preferences\n\nPref text.\n\n## Other Section\n\nOther.\n"
        )
        (tmp_path / "CLAUDE.md").write_text(content)
        result = review_mod._read_vault_prefs(str(tmp_path))
        assert "Pref text." in result
        assert "Other." not in result


# ===========================================================================
# _is_within_vault
# ===========================================================================


class TestIsWithinVault:
    def test_path_inside_vault(self, tmp_path):
        sub = tmp_path / "notes" / "note.md"
        assert _shared._is_within_vault(tmp_path, sub) is True

    def test_path_outside_vault(self, tmp_path):
        outside = Path("/tmp/other_location")
        assert _shared._is_within_vault(tmp_path, outside) is False

    def test_vault_itself(self, tmp_path):
        assert _shared._is_within_vault(tmp_path, tmp_path) is True


# ===========================================================================
# _find_due_notes
# ===========================================================================


class TestFindDueNotes:
    def test_finds_overdue_note(self, tmp_path):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        _make_wm_note(tmp_path, "Old Task", yesterday)
        with patch.object(
            review_mod, "_parse_frontmatter", wraps=review_mod._parse_frontmatter
        ):
            result = review_mod._find_due_notes(tmp_path, tmp_path, 0)
        assert len(result) == 1
        assert result[0]["title"] == "Old Task"
        assert result[0]["days_overdue"] == 1

    def test_finds_note_due_today(self, tmp_path):
        today = date.today().isoformat()
        _make_wm_note(tmp_path, "Today Task", today)
        result = review_mod._find_due_notes(tmp_path, tmp_path, 0)
        assert len(result) == 1
        assert result[0]["days_overdue"] == 0

    def test_skips_future_note_when_days_ahead_zero(self, tmp_path):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        _make_wm_note(tmp_path, "Future Task", tomorrow)
        result = review_mod._find_due_notes(tmp_path, tmp_path, 0)
        assert result == []

    def test_finds_note_within_days_ahead(self, tmp_path):
        in_3_days = (date.today() + timedelta(days=3)).isoformat()
        _make_wm_note(tmp_path, "Soon Task", in_3_days)
        result = review_mod._find_due_notes(tmp_path, tmp_path, 5)
        assert len(result) == 1

    def test_skips_non_ephemeral_note(self, tmp_path):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        _make_wm_note(tmp_path, "Normal Note", yesterday, ephemeral=False)
        result = review_mod._find_due_notes(tmp_path, tmp_path, 0)
        assert result == []

    def test_skips_note_with_bad_date(self, tmp_path):
        p = tmp_path / "bad.md"
        p.write_text("---\ncb_ephemeral: true\ncb_review_after: not-a-date\n---\n")
        result = review_mod._find_due_notes(tmp_path, tmp_path, 0)
        assert result == []

    def test_skips_note_with_no_review_after(self, tmp_path):
        p = tmp_path / "no_date.md"
        p.write_text("---\ncb_ephemeral: true\n---\n")
        result = review_mod._find_due_notes(tmp_path, tmp_path, 0)
        assert result == []

    def test_skips_hidden_dir_notes(self, tmp_path):
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        _make_wm_note(hidden, "Hidden Task", yesterday)
        result = review_mod._find_due_notes(tmp_path, tmp_path, 0)
        assert result == []


# ===========================================================================
# _cluster_notes
# ===========================================================================


class TestClusterNotes:
    def _note(self, title):
        return {"path": Path(f"/vault/{title}.md"), "title": title, "summary": ""}

    def test_single_note_returns_singleton(self):
        notes = [self._note("A")]
        result = review_mod._cluster_notes(notes, None)
        assert result == [[0]]

    def test_backend_none_returns_singletons(self):
        notes = [self._note("A"), self._note("B")]
        result = review_mod._cluster_notes(notes, None)
        assert result == [[0], [1]]

    def test_with_backend_groups_similar_notes(self):
        note_a = {"path": Path("/v/A.md"), "title": "Alpha", "summary": "about alpha"}
        note_b = {"path": Path("/v/B.md"), "title": "Beta", "summary": "related"}

        backend = MagicMock()
        result_a = MagicMock()
        result_a.path = Path("/v/B.md")
        result_a.score = 0.9
        result_b = MagicMock()
        result_b.path = Path("/v/A.md")
        result_b.score = 0.9

        def search_side(query, top_k):
            if "Alpha" in query:
                return [result_a]
            return [result_b]

        backend.search.side_effect = search_side
        result = review_mod._cluster_notes([note_a, note_b], backend)
        # Should have one cluster containing both
        flat = [i for cluster in result for i in cluster]
        assert set(flat) == {0, 1}

    def test_backend_search_exception_is_swallowed(self):
        note_a = {"path": Path("/v/A.md"), "title": "Alpha", "summary": ""}
        note_b = {"path": Path("/v/B.md"), "title": "Beta", "summary": ""}
        backend = MagicMock()
        backend.search.side_effect = RuntimeError("fail")
        result = review_mod._cluster_notes([note_a, note_b], backend)
        # Each note becomes its own cluster
        assert len(result) == 2


# ===========================================================================
# _format_notes_block
# ===========================================================================


class TestFormatNotesBlock:
    def _note(self, title, overdue=0):
        return {
            "title": title,
            "rel_path": f"AI/WM/{title}.md",
            "review_after": date.today(),
            "days_overdue": overdue,
            "summary": "A summary",
            "content": "Some content",
        }

    def test_singleton_cluster(self):
        notes = [self._note("Task A", overdue=2)]
        clusters = [[0]]
        result = review_mod._format_notes_block(notes, clusters)
        assert "Task A" in result
        assert "2 days overdue" in result

    def test_singleton_due_today(self):
        notes = [self._note("Task B", overdue=0)]
        clusters = [[0]]
        result = review_mod._format_notes_block(notes, clusters)
        assert "due today" in result

    def test_multi_note_cluster(self):
        notes = [self._note("A"), self._note("B")]
        clusters = [[0, 1]]
        result = review_mod._format_notes_block(notes, clusters)
        assert "Cluster" in result
        assert "A" in result
        assert "B" in result

    def test_long_content_truncated(self):
        note = self._note("Long")
        note["content"] = "x" * 3000
        clusters = [[0]]
        result = review_mod._format_notes_block([note], clusters)
        assert "truncated" in result


# ===========================================================================
# _extend_review_after
# ===========================================================================


class TestExtendReviewAfter:
    def test_bumps_review_date(self, tmp_path):
        p = tmp_path / "note.md"
        p.write_text("---\ncb_review_after: 2026-01-01\n---\n")
        result = review_mod._extend_review_after(p, weeks=4, vault_path=str(tmp_path))
        assert result is True
        content = p.read_text()
        new_date = (date.today() + timedelta(weeks=4)).isoformat()
        assert new_date in content

    def test_returns_false_on_oserror(self, tmp_path):
        missing = tmp_path / "nonexistent.md"
        result = review_mod._extend_review_after(
            missing, weeks=4, vault_path=str(tmp_path)
        )
        assert result is False

    def test_returns_false_when_no_field(self, tmp_path):
        p = tmp_path / "note.md"
        p.write_text("---\ntitle: X\n---\n")
        result = review_mod._extend_review_after(p, vault_path=str(tmp_path))
        assert result is False


# ===========================================================================
# _append_errata
# ===========================================================================


class TestAppendErrata:
    def test_skips_when_empty(self, tmp_path):
        config = {"consolidation_log": "AI/Log.md", "consolidation_log_enabled": True}
        review_mod._append_errata(tmp_path, config, [])
        assert not (tmp_path / "AI" / "Log.md").exists()

    def test_skips_when_disabled(self, tmp_path):
        config = {"consolidation_log": "AI/Log.md", "consolidation_log_enabled": False}
        review_mod._append_errata(tmp_path, config, ["entry"])
        assert not (tmp_path / "AI" / "Log.md").exists()

    def test_writes_log_entry(self, tmp_path):
        config = {"consolidation_log": "AI/Log.md", "consolidation_log_enabled": True}
        review_mod._append_errata(tmp_path, config, ["Did something"])
        log = (tmp_path / "AI" / "Log.md").read_text()
        assert "Did something" in log
        assert "Working Memory Review" in log

    def test_appends_to_existing_log(self, tmp_path):
        log_path = tmp_path / "AI" / "Log.md"
        log_path.parent.mkdir(parents=True)
        log_path.write_text("# Existing content\n")
        config = {"consolidation_log": "AI/Log.md", "consolidation_log_enabled": True}
        review_mod._append_errata(tmp_path, config, ["new entry"])
        content = log_path.read_text()
        assert "Existing content" in content
        assert "new entry" in content


# ===========================================================================
# cb_review (the main tool)
# ===========================================================================


def _base_config(tmp_path):
    return {
        "vault_path": str(tmp_path),
        "backend": "claude-code",
        "model": "claude-haiku-4-5",
        "working_memory_folder": "AI/WM",
        "consolidation_log": "AI/Log.md",
        "consolidation_log_enabled": True,
    }


class TestCbReviewErrors:
    def test_raises_when_not_configured(self):
        with patch.object(
            review_mod,
            "require_config",
            side_effect=ToolError("Cyberbrain is not configured. Run /cyberbrain:config to set up your vault."),
        ):
            with pytest.raises(ToolError, match="not configured"):
                _cb_review()()

    def test_returns_info_when_wm_folder_missing(self, tmp_path):
        config = _base_config(tmp_path)
        with patch.object(review_mod, "require_config", return_value=config):
            result = _cb_review()()
        assert "not found" in result

    def test_returns_info_when_no_due_notes(self, tmp_path):
        config = _base_config(tmp_path)
        wm = tmp_path / "AI" / "WM"
        wm.mkdir(parents=True)
        with patch.object(review_mod, "require_config", return_value=config):
            result = _cb_review()()
        assert "No working memory notes" in result


class TestCbReviewDryRun:
    def test_dry_run_lists_due_notes(self, tmp_path):
        config = _base_config(tmp_path)
        wm = tmp_path / "AI" / "WM"
        wm.mkdir(parents=True)
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        _make_wm_note(wm, "My Task", yesterday)

        with patch.object(review_mod, "require_config", return_value=config):
            result = _cb_review()(dry_run=True)
        assert "DRY RUN" in result
        assert "My Task" in result

    def test_dry_run_respects_limit(self, tmp_path):
        config = _base_config(tmp_path)
        wm = tmp_path / "AI" / "WM"
        wm.mkdir(parents=True)
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        for i in range(5):
            _make_wm_note(wm, f"Task{i}", yesterday)

        with patch.object(review_mod, "require_config", return_value=config):
            result = _cb_review()(dry_run=True, limit=2)
        assert result.count("→") <= 2

    def test_custom_folder_used(self, tmp_path):
        config = _base_config(tmp_path)
        custom = tmp_path / "My" / "Custom"
        custom.mkdir(parents=True)
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        _make_wm_note(custom, "Custom Task", yesterday)

        with patch.object(review_mod, "require_config", return_value=config):
            result = _cb_review()(folder="My/Custom", dry_run=True)
        assert "Custom Task" in result


class TestCbReviewActions:
    def _setup(self, tmp_path):
        config = _base_config(tmp_path)
        wm = tmp_path / "AI" / "WM"
        wm.mkdir(parents=True)
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        path = _make_wm_note(wm, "Test Note", yesterday, summary="a summary")
        return config, path

    def test_delete_action_removes_file(self, tmp_path):
        config, path = self._setup(tmp_path)
        decisions = [{"action": "delete", "indices": [0], "rationale": "stale"}]

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(review_mod, "_load_prompt", return_value="prompt"),
            patch.object(review_mod, "_index_paths"),
            patch.object(review_mod, "_prune_index"),
            patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(decisions),
            ),
            patch("cyberbrain.extractors.backends.BackendError", Exception),
        ):
            result = _cb_review()(dry_run=False)
        assert not path.exists()
        assert "Deleted" in result

    def test_extend_action_bumps_date(self, tmp_path):
        config, path = self._setup(tmp_path)
        decisions = [{"action": "extend", "indices": [0], "rationale": "still active"}]

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(review_mod, "_load_prompt", return_value="prompt"),
            patch.object(review_mod, "_index_paths"),
            patch.object(review_mod, "_prune_index"),
            patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(decisions),
            ),
            patch("cyberbrain.extractors.backends.BackendError", Exception),
        ):
            result = _cb_review()(dry_run=False, extend_weeks=2)
        assert "Extended" in result
        # Date should be bumped
        new_date = (date.today() + timedelta(weeks=2)).isoformat()
        assert new_date in path.read_text()

    def test_promote_action_writes_new_file(self, tmp_path):
        config, path = self._setup(tmp_path)
        promoted_content = (
            "---\ntitle: Promoted\ntype: reference\nsummary: s\ntags: []\n---\n\nBody\n"
        )
        decisions = [
            {
                "action": "promote",
                "indices": [0],
                "rationale": "valuable",
                "promoted_title": "My Promoted Note",
                "promoted_path": "Knowledge/Promoted.md",
                "promoted_content": promoted_content,
            }
        ]

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(review_mod, "_load_prompt", return_value="prompt"),
            patch.object(review_mod, "_index_paths"),
            patch.object(review_mod, "_prune_index"),
            patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(decisions),
            ),
            patch("cyberbrain.extractors.backends.BackendError", Exception),
        ):
            result = _cb_review()(dry_run=False)
        assert (tmp_path / "Knowledge" / "Promoted.md").exists()
        assert "Promoted" in result

    def test_promote_note_contains_aliases_created_updated(self, tmp_path):
        config, path = self._setup(tmp_path)
        promoted_content = (
            "---\ntitle: Promoted\ntype: reference\nsummary: s\ntags: []\n---\n\nBody\n"
        )
        decisions = [
            {
                "action": "promote",
                "indices": [0],
                "rationale": "valuable",
                "promoted_title": "My Promoted Note",
                "promoted_path": "Knowledge/Promoted.md",
                "promoted_content": promoted_content,
            }
        ]

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(review_mod, "_load_prompt", return_value="prompt"),
            patch.object(review_mod, "_index_paths"),
            patch.object(review_mod, "_prune_index"),
            patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(decisions),
            ),
            patch("cyberbrain.extractors.backends.BackendError", Exception),
        ):
            _cb_review()(dry_run=False)

        written = (tmp_path / "Knowledge" / "Promoted.md").read_text()
        assert "aliases:" in written
        assert "created:" in written
        assert "updated:" in written

    def test_promote_corrects_beat_type_to_entity_type(self, tmp_path):
        config, path = self._setup(tmp_path)
        # LLM returns promoted_content with a beat type (insight) instead of an entity type
        promoted_content = (
            "---\ntitle: Promoted\ntype: insight\nsummary: s\ntags: []\n---\n\nBody\n"
        )
        decisions = [
            {
                "action": "promote",
                "indices": [0],
                "rationale": "valuable",
                "promoted_title": "My Promoted Note",
                "promoted_path": "Knowledge/Promoted.md",
                "promoted_content": promoted_content,
            }
        ]

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(review_mod, "_load_prompt", return_value="prompt"),
            patch.object(review_mod, "_index_paths"),
            patch.object(review_mod, "_prune_index"),
            patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(decisions),
            ),
            patch("cyberbrain.extractors.backends.BackendError", Exception),
        ):
            _cb_review()(dry_run=False)

        written = (tmp_path / "Knowledge" / "Promoted.md").read_text()
        assert 'type: "resource"' in written
        assert "type: insight" not in written

    def test_promote_strips_ephemeral_fields(self, tmp_path):
        config, path = self._setup(tmp_path)
        # LLM returns promoted_content that still contains working-memory-only fields
        promoted_content = (
            "---\n"
            "title: Promoted\n"
            "type: reference\n"
            "durability: durable\n"
            "summary: s\n"
            "tags: []\n"
            "cb_ephemeral: true\n"
            "cb_review_after: 2026-04-01\n"
            "---\n\n"
            "Body text.\n"
        )
        decisions = [
            {
                "action": "promote",
                "indices": [0],
                "rationale": "valuable",
                "promoted_title": "My Promoted Note",
                "promoted_path": "Knowledge/Promoted.md",
                "promoted_content": promoted_content,
            }
        ]

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(review_mod, "_load_prompt", return_value="prompt"),
            patch.object(review_mod, "_index_paths"),
            patch.object(review_mod, "_prune_index"),
            patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(decisions),
            ),
            patch("cyberbrain.extractors.backends.BackendError", Exception),
        ):
            _cb_review()(dry_run=False)

        written = (tmp_path / "Knowledge" / "Promoted.md").read_text()
        assert "cb_ephemeral:" not in written
        assert "cb_review_after:" not in written
        assert "durability: durable" in written

    def test_promote_skips_path_traversal(self, tmp_path):
        config, path = self._setup(tmp_path)
        decisions = [
            {
                "action": "promote",
                "indices": [0],
                "rationale": "valuable",
                "promoted_title": "Escape",
                "promoted_path": "../../etc/passwd",
                "promoted_content": "---\ntitle: X\n---\nbody",
            }
        ]

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(review_mod, "_load_prompt", return_value="prompt"),
            patch.object(review_mod, "_index_paths"),
            patch.object(review_mod, "_prune_index"),
            patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(decisions),
            ),
            patch("cyberbrain.extractors.backends.BackendError", Exception),
        ):
            result = _cb_review()(dry_run=False)
        assert "path traversal rejected" in result

    def test_promote_skips_missing_content(self, tmp_path):
        config, path = self._setup(tmp_path)
        decisions = [
            {
                "action": "promote",
                "indices": [0],
                "promoted_path": "",
                "promoted_content": "",
            }
        ]

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(review_mod, "_load_prompt", return_value="prompt"),
            patch.object(review_mod, "_index_paths"),
            patch.object(review_mod, "_prune_index"),
            patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(decisions),
            ),
            patch("cyberbrain.extractors.backends.BackendError", Exception),
        ):
            result = _cb_review()(dry_run=False)
        assert "missing path or content" in result

    def test_unknown_action_is_skipped(self, tmp_path):
        config, path = self._setup(tmp_path)
        decisions = [{"action": "teleport", "indices": [0], "rationale": "??"}]

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(review_mod, "_load_prompt", return_value="prompt"),
            patch.object(review_mod, "_index_paths"),
            patch.object(review_mod, "_prune_index"),
            patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(decisions),
            ),
            patch("cyberbrain.extractors.backends.BackendError", Exception),
        ):
            result = _cb_review()(dry_run=False)
        assert "Unknown action" in result

    def test_no_indices_skipped(self, tmp_path):
        config, path = self._setup(tmp_path)
        decisions = [{"action": "delete", "indices": []}]

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(review_mod, "_load_prompt", return_value="prompt"),
            patch.object(review_mod, "_index_paths"),
            patch.object(review_mod, "_prune_index"),
            patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(decisions),
            ),
            patch("cyberbrain.extractors.backends.BackendError", Exception),
        ):
            result = _cb_review()(dry_run=False)
        # Unhandled note should be noted
        assert "No decision returned" in result

    def test_backend_error_raises_tool_error(self, tmp_path):
        config, _ = self._setup(tmp_path)

        class FakeBackendError(Exception):
            pass

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(review_mod, "_load_prompt", return_value="prompt"),
            patch(
                "cyberbrain.extractors.backends.call_model",
                side_effect=FakeBackendError("oops"),
            ),
            patch("cyberbrain.extractors.backends.BackendError", FakeBackendError),
        ):
            with pytest.raises(ToolError, match="Backend error"):
                _cb_review()(dry_run=False)

    def test_invalid_json_raises_tool_error(self, tmp_path):
        config, _ = self._setup(tmp_path)

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(review_mod, "_load_prompt", return_value="prompt"),
            patch("cyberbrain.extractors.backends.call_model", return_value="not json"),
            patch("cyberbrain.extractors.backends.BackendError", Exception),
        ):
            with pytest.raises(ToolError, match="invalid JSON"):
                _cb_review()(dry_run=False)

    def test_non_list_json_raises_tool_error(self, tmp_path):
        config, _ = self._setup(tmp_path)

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(review_mod, "_load_prompt", return_value="prompt"),
            patch(
                "cyberbrain.extractors.backends.call_model",
                return_value='{"key": "val"}',
            ),
            patch("cyberbrain.extractors.backends.BackendError", Exception),
        ):
            with pytest.raises(ToolError, match="not a JSON array"):
                _cb_review()(dry_run=False)

    def test_summary_shows_counts(self, tmp_path):
        config, path = self._setup(tmp_path)
        decisions = [{"action": "delete", "indices": [0], "rationale": "old"}]

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(review_mod, "_load_prompt", return_value="prompt"),
            patch.object(review_mod, "_index_paths"),
            patch.object(review_mod, "_prune_index"),
            patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(decisions),
            ),
            patch("cyberbrain.extractors.backends.BackendError", Exception),
        ):
            result = _cb_review()(dry_run=False)
        assert "Deleted:" in result
        assert "Working Memory Review Complete" in result


class TestCbReviewQualityGate:
    """Verify that the quality gate blocks bad review decisions."""

    def _setup(self, tmp_path):
        config = _base_config(tmp_path)
        wm = tmp_path / "AI" / "WM"
        wm.mkdir(parents=True)
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        path = _make_wm_note(wm, "Test Note", yesterday, summary="a summary")
        return config, path

    def test_gate_blocks_bad_delete(self, tmp_path):
        """A delete decision that fails the gate is not executed."""
        config, path = self._setup(tmp_path)
        decisions = [{"action": "delete", "indices": [0], "rationale": "stale"}]

        fail_verdict = MagicMock()
        fail_verdict.passed = False
        fail_verdict.rationale = "Note is only 1 day old and topic may still be active"
        fail_verdict.confidence = 0.3

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(review_mod, "_load_prompt", return_value="prompt"),
            patch.object(review_mod, "_index_paths"),
            patch.object(review_mod, "_prune_index"),
            patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(decisions),
            ),
            patch("cyberbrain.extractors.backends.BackendError", Exception),
            patch(
                "cyberbrain.extractors.quality_gate.quality_gate",
                return_value=fail_verdict,
            ),
        ):
            result = _cb_review()(dry_run=False)

        # File should still exist
        assert path.exists()
        assert "Gate blocked delete" in result
        assert "Deleted:   0" in result
        assert "Blocked:   1" in result

    def test_gate_passes_good_delete(self, tmp_path):
        """A delete decision that passes the gate is executed."""
        config, path = self._setup(tmp_path)
        decisions = [{"action": "delete", "indices": [0], "rationale": "stale"}]

        pass_verdict = MagicMock()
        pass_verdict.passed = True
        pass_verdict.confidence = 0.9

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(review_mod, "_load_prompt", return_value="prompt"),
            patch.object(review_mod, "_index_paths"),
            patch.object(review_mod, "_prune_index"),
            patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(decisions),
            ),
            patch("cyberbrain.extractors.backends.BackendError", Exception),
            patch(
                "cyberbrain.extractors.quality_gate.quality_gate",
                return_value=pass_verdict,
            ),
        ):
            result = _cb_review()(dry_run=False)

        assert not path.exists()
        assert "Deleted:   1" in result
        assert "Blocked:   0" in result

    def test_gate_blocks_bad_promote(self, tmp_path):
        """A promote decision that fails the gate is not executed."""
        config, path = self._setup(tmp_path)
        promoted_content = "---\ntitle: Promoted\ntype: reference\n---\n\nBody\n"
        decisions = [
            {
                "action": "promote",
                "indices": [0],
                "rationale": "valuable",
                "promoted_title": "My Note",
                "promoted_path": "Knowledge/Promoted.md",
                "promoted_content": promoted_content,
            }
        ]

        fail_verdict = MagicMock()
        fail_verdict.passed = False
        fail_verdict.rationale = "Content is still working-memory level"
        fail_verdict.confidence = 0.4

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(review_mod, "_load_prompt", return_value="prompt"),
            patch.object(review_mod, "_index_paths"),
            patch.object(review_mod, "_prune_index"),
            patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(decisions),
            ),
            patch("cyberbrain.extractors.backends.BackendError", Exception),
            patch(
                "cyberbrain.extractors.quality_gate.quality_gate",
                return_value=fail_verdict,
            ),
        ):
            result = _cb_review()(dry_run=False)

        # Promoted file should NOT exist
        assert not (tmp_path / "Knowledge" / "Promoted.md").exists()
        assert "Gate blocked promote" in result
        assert "Promoted:  0" in result

    def test_gate_disabled_skips_check(self, tmp_path):
        """When quality_gate_enabled is false, decisions execute without gating."""
        config, path = self._setup(tmp_path)
        config["quality_gate_enabled"] = False
        decisions = [{"action": "delete", "indices": [0], "rationale": "stale"}]

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(review_mod, "_load_prompt", return_value="prompt"),
            patch.object(review_mod, "_index_paths"),
            patch.object(review_mod, "_prune_index"),
            patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(decisions),
            ),
            patch("cyberbrain.extractors.backends.BackendError", Exception),
            patch(
                "cyberbrain.extractors.quality_gate.quality_gate",
                side_effect=AssertionError("should not be called"),
            ) as mock_gate,
        ):
            result = _cb_review()(dry_run=False)

        assert not path.exists()
        mock_gate.assert_not_called()

    def test_gate_blocks_some_passes_others(self, tmp_path):
        """In a multi-decision review, gate blocks some actions while passing others."""
        config = _base_config(tmp_path)
        wm = tmp_path / "AI" / "WM"
        wm.mkdir(parents=True)
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        path_a = _make_wm_note(wm, "Stale Task", yesterday, summary="old task")
        path_b = _make_wm_note(wm, "Active Bug", yesterday, summary="active bug")

        decisions = [
            {"action": "delete", "indices": [0], "rationale": "no longer relevant"},
            {"action": "delete", "indices": [1], "rationale": "also stale"},
        ]

        pass_verdict = MagicMock()
        pass_verdict.passed = True
        pass_verdict.confidence = 0.9

        fail_verdict = MagicMock()
        fail_verdict.passed = False
        fail_verdict.rationale = "Bug is still active"
        fail_verdict.confidence = 0.2

        call_count = [0]

        def gate_side_effect(op, inp, out, cfg):
            call_count[0] += 1
            if "Active Bug" in inp:
                return fail_verdict
            return pass_verdict

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(review_mod, "_load_prompt", return_value="prompt"),
            patch.object(review_mod, "_index_paths"),
            patch.object(review_mod, "_prune_index"),
            patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(decisions),
            ),
            patch("cyberbrain.extractors.backends.BackendError", Exception),
            patch(
                "cyberbrain.extractors.quality_gate.quality_gate",
                side_effect=gate_side_effect,
            ),
        ):
            result = _cb_review()(dry_run=False)

        assert "Deleted:   1" in result
        assert "Blocked:   1" in result
        assert "Bug is still active" in result

    def test_gate_report_includes_confidence(self, tmp_path):
        """The report shows the gate's confidence score for blocked items."""
        config, path = self._setup(tmp_path)
        decisions = [{"action": "extend", "indices": [0], "rationale": "still active"}]

        fail_verdict = MagicMock()
        fail_verdict.passed = False
        fail_verdict.rationale = "Topic seems resolved"
        fail_verdict.confidence = 0.45

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(review_mod, "_load_prompt", return_value="prompt"),
            patch.object(review_mod, "_index_paths"),
            patch.object(review_mod, "_prune_index"),
            patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(decisions),
            ),
            patch("cyberbrain.extractors.backends.BackendError", Exception),
            patch(
                "cyberbrain.extractors.quality_gate.quality_gate",
                return_value=fail_verdict,
            ),
        ):
            result = _cb_review()(dry_run=False)

        assert "confidence: 0.45" in result
        assert "Topic seems resolved" in result

    def test_gate_fail_shows_configure_hint(self, tmp_path):
        """FAIL verdict output includes cb_configure hint to disable gates."""
        config, path = self._setup(tmp_path)
        decisions = [{"action": "delete", "indices": [0], "rationale": "stale"}]

        fail_verdict = MagicMock()
        fail_verdict.passed = False
        fail_verdict.rationale = "Note is still relevant"
        fail_verdict.confidence = 0.3

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(review_mod, "_load_prompt", return_value="prompt"),
            patch.object(review_mod, "_index_paths"),
            patch.object(review_mod, "_prune_index"),
            patch(
                "cyberbrain.extractors.backends.call_model",
                return_value=json.dumps(decisions),
            ),
            patch("cyberbrain.extractors.backends.BackendError", Exception),
            patch(
                "cyberbrain.extractors.quality_gate.quality_gate",
                return_value=fail_verdict,
            ),
        ):
            result = _cb_review()(dry_run=False)

        assert "cb_configure(quality_gate_enabled=False)" in result


class TestCbReviewLoadPromptError:
    def test_raises_tool_error_when_prompt_missing(self, tmp_path):
        config = _base_config(tmp_path)
        wm = tmp_path / "AI" / "WM"
        wm.mkdir(parents=True)
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        _make_wm_note(wm, "Task", yesterday)

        with (
            patch.object(review_mod, "require_config", return_value=config),
            patch.object(review_mod, "_get_search_backend", return_value=None),
            patch.object(
                review_mod, "_load_prompt", side_effect=ToolError("no prompt")
            ),
        ):
            with pytest.raises(ToolError):
                _cb_review()(dry_run=False)
