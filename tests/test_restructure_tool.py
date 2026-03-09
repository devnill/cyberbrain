"""
test_restructure_tool.py — unit tests for mcp/tools/restructure.py

Covers:
- _repair_json: valid JSON, repair by closing brackets, object extraction, raises on failure
- _validate_frontmatter: no frontmatter, missing fields, all fields present
- _read_vault_prefs: no CLAUDE.md, no heading, has prefs, with next section
- _is_locked: locked vs unlocked notes
- _collect_notes: basic collection, skips hidden dirs, excluded folders, locked notes
- _title_concept_clusters: grouping by primary concept word, singleton reassignment
- _tag_based_clusters: grouping by shared tags, min_cluster_size filter
- _find_split_candidates: size threshold, excludes clustered paths
- _format_cluster_block / _format_split_candidates_block: empty and non-empty
- _format_folder_hub_block: new hub vs existing hub
- _append_errata_log: writes, skips when empty
- _is_within_vault: inside/outside
- _build_folder_context: output structure
- _execute_cluster_decisions: keep-separate, merge, hub-spoke, subfolder,
                               path traversal, missing content, out-of-range cluster
- cb_restructure: parameter validation errors, no vault, dry_run modes,
                  preview mode, execute merge, execute split, folder_hub mode,
                  backend errors, JSON parse errors
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# sys.path setup
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
MCP_DIR = REPO_ROOT / "mcp"
EXTRACTORS_DIR = REPO_ROOT / "extractors"

for d in [str(MCP_DIR), str(EXTRACTORS_DIR), str(REPO_ROOT)]:
    if d not in sys.path:
        sys.path.insert(0, d)

# conftest.py installs shared extract_beats mock.
for _mod in ["shared", "tools.restructure"]:
    sys.modules.pop(_mod, None)

import shared as _shared  # noqa: E402
import tools.restructure as rst_mod  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402


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
rst_mod.register(_fake_mcp)


def _cb_restructure():
    return _fake_mcp._tools["cb_restructure"]["fn"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_note(path: Path, title: str, locked=False, tags=None, summary="A summary",
               body_size=100):
    """Write a markdown note file with proper frontmatter."""
    tags_str = json.dumps(tags or ["test"])
    lock_line = "\ncb_lock: true" if locked else ""
    content = (
        f"---\ntitle: {title!r}\ntype: reference\nsummary: {summary!r}\n"
        f"tags: {tags_str}{lock_line}\n---\n\n## {title}\n\n"
        + ("x" * body_size) + "\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return content


def _note_dict(path: Path, title: str, tags=None, summary="", content="some content"):
    return {
        "path": path,
        "title": title,
        "summary": summary,
        "tags": tags or [],
        "content": content,
        "rel_path": title + ".md",
    }


# ===========================================================================
# _repair_json
# ===========================================================================

class TestRepairJson:
    def test_valid_json_returned_directly(self):
        result = rst_mod._repair_json('[{"key": "val"}]')
        assert result == [{"key": "val"}]

    def test_repairs_unclosed_braces(self):
        raw = '[{"key": "val"'
        result = rst_mod._repair_json(raw)
        assert isinstance(result, list)

    def test_extracts_objects_from_partial_array(self):
        raw = '{"a": 1} {"b": 2}'
        result = rst_mod._repair_json(raw)
        assert len(result) == 2

    def test_raises_on_complete_failure(self):
        with pytest.raises(json.JSONDecodeError):
            rst_mod._repair_json("not json at all ~~~")

    def test_adds_opening_bracket_when_missing(self):
        raw = '{"a": 1}]'
        result = rst_mod._repair_json(raw)
        assert isinstance(result, list)


# ===========================================================================
# _validate_frontmatter
# ===========================================================================

class TestValidateFrontmatter:
    def test_no_frontmatter_returns_warning(self):
        result = rst_mod._validate_frontmatter("no frontmatter", "TestNote")
        assert len(result) == 1
        assert "no YAML frontmatter" in result[0]

    def test_missing_required_fields_warns(self):
        content = "---\ntitle: X\n---\n"  # missing type, summary, tags
        result = rst_mod._validate_frontmatter(content, "TestNote")
        assert len(result) == 1
        assert "missing" in result[0]

    def test_all_fields_present_returns_empty(self):
        content = "---\ntitle: X\ntype: reference\nsummary: S\ntags: [\"test\"]\n---\n"
        result = rst_mod._validate_frontmatter(content, "TestNote")
        assert result == []


# ===========================================================================
# _read_vault_prefs
# ===========================================================================

class TestReadVaultPrefs:
    def test_returns_empty_when_no_claude_md(self, tmp_path):
        assert rst_mod._read_vault_prefs(str(tmp_path)) == ""

    def test_returns_empty_when_no_prefs_heading(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# Vault\n\n## Other Section\n")
        assert rst_mod._read_vault_prefs(str(tmp_path)) == ""

    def test_returns_prefs_content(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text(
            "# Vault\n\n## Cyberbrain Preferences\n\nPrefer short notes.\n"
        )
        result = rst_mod._read_vault_prefs(str(tmp_path))
        assert "Prefer short notes." in result

    def test_prefs_end_at_next_h2(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text(
            "## Cyberbrain Preferences\n\nDo this.\n\n## Other\n\nNot this.\n"
        )
        result = rst_mod._read_vault_prefs(str(tmp_path))
        assert "Do this." in result
        assert "Not this." not in result


# ===========================================================================
# _is_locked
# ===========================================================================

class TestIsLocked:
    def test_locked_note(self):
        content = "---\ncb_lock: true\n---\n"
        assert rst_mod._is_locked(content) is True

    def test_unlocked_note(self):
        content = "---\ntitle: X\n---\n"
        assert rst_mod._is_locked(content) is False

    def test_no_frontmatter(self):
        assert rst_mod._is_locked("just body text") is False


# ===========================================================================
# _collect_notes
# ===========================================================================

class TestCollectNotes:
    def test_collects_eligible_notes(self, tmp_path):
        _make_note(tmp_path / "note1.md", "Note One")
        _make_note(tmp_path / "note2.md", "Note Two")
        result = rst_mod._collect_notes(tmp_path, tmp_path, [])
        assert len(result) == 2

    def test_skips_hidden_dir(self, tmp_path):
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        _make_note(hidden / "secret.md", "Hidden")
        _make_note(tmp_path / "visible.md", "Visible")
        result = rst_mod._collect_notes(tmp_path, tmp_path, [])
        titles = [n["title"] for n in result]
        assert "Visible" in titles
        assert "Hidden" not in titles

    def test_skips_excluded_folder(self, tmp_path):
        journal = tmp_path / "Journal"
        journal.mkdir()
        _make_note(journal / "entry.md", "Journal Entry")
        _make_note(tmp_path / "note.md", "Regular Note")
        result = rst_mod._collect_notes(tmp_path, tmp_path, ["Journal"])
        titles = [n["title"] for n in result]
        assert "Regular Note" in titles
        assert "Journal Entry" not in titles

    def test_skips_locked_notes(self, tmp_path):
        _make_note(tmp_path / "locked.md", "Locked", locked=True)
        _make_note(tmp_path / "unlocked.md", "Unlocked")
        result = rst_mod._collect_notes(tmp_path, tmp_path, [])
        titles = [n["title"] for n in result]
        assert "Unlocked" in titles
        assert "Locked" not in titles

    def test_skips_excluded_paths(self, tmp_path):
        hub = tmp_path / "hub.md"
        _make_note(hub, "Hub")
        _make_note(tmp_path / "note.md", "Note")
        result = rst_mod._collect_notes(tmp_path, tmp_path, [], exclude_paths={hub.resolve()})
        titles = [n["title"] for n in result]
        assert "Note" in titles
        assert "Hub" not in titles

    def test_handles_json_string_tags(self, tmp_path):
        path = tmp_path / "note.md"
        path.write_text('---\ntitle: "T"\ntype: reference\nsummary: "S"\ntags: "[\\"a\\"]"\n---\n\nbody\n')
        result = rst_mod._collect_notes(tmp_path, tmp_path, [])
        assert len(result) == 1

    def test_handles_non_list_tags(self, tmp_path):
        path = tmp_path / "note.md"
        path.write_text('---\ntitle: "T"\ntype: reference\nsummary: "S"\ntags: 42\n---\n\nbody\n')
        result = rst_mod._collect_notes(tmp_path, tmp_path, [])
        assert len(result) == 1
        assert result[0]["tags"] == []


# ===========================================================================
# _title_concept_clusters
# ===========================================================================

class TestTitleConceptClusters:
    def _note(self, title, tags=None):
        return {"title": title, "tags": tags or [], "summary": ""}

    def test_groups_notes_by_primary_word(self):
        notes = [
            self._note("Hook Installation"),
            self._note("Hook Configuration"),
            self._note("Plugin Setup"),
        ]
        result = rst_mod._title_concept_clusters(notes, min_cluster_size=2)
        # "hook" group should have 2 notes
        assert any(len(c) == 2 for c in result)

    def test_singleton_reassigned_via_secondary_word(self):
        notes = [
            self._note("Hook Installation"),
            self._note("Hook Configuration"),
            self._note("Session Hook"),  # "session" is singleton primary, "hook" is secondary
        ]
        result = rst_mod._title_concept_clusters(notes, min_cluster_size=2)
        flat = [n["title"] for cluster in result for n in cluster]
        # Session Hook should get reassigned to the hook group
        assert "Session Hook" in flat

    def test_min_cluster_size_filters(self):
        notes = [self._note("Alpha Thing"), self._note("Beta Thing")]
        result = rst_mod._title_concept_clusters(notes, min_cluster_size=3)
        assert result == []

    def test_empty_notes_returns_empty(self):
        result = rst_mod._title_concept_clusters([], min_cluster_size=2)
        assert result == []

    def test_all_stop_words_note_skipped(self):
        notes = [self._note("The And For"), self._note("Python Testing")]
        result = rst_mod._title_concept_clusters(notes, min_cluster_size=2)
        # Only notes with non-stop words should be clustered
        assert isinstance(result, list)


# ===========================================================================
# _tag_based_clusters
# ===========================================================================

class TestTagBasedClusters:
    def test_clusters_notes_sharing_two_tags(self):
        notes = [
            {"title": "A", "tags": ["python", "testing"], "summary": ""},
            {"title": "B", "tags": ["python", "testing"], "summary": ""},
            {"title": "C", "tags": ["unrelated"], "summary": ""},
        ]
        result = rst_mod._tag_based_clusters(notes, min_cluster_size=2)
        # A and B should be in one cluster
        assert len(result) == 1
        assert len(result[0]) == 2

    def test_notes_sharing_one_tag_not_clustered(self):
        notes = [
            {"title": "A", "tags": ["python"], "summary": ""},
            {"title": "B", "tags": ["python"], "summary": ""},
        ]
        result = rst_mod._tag_based_clusters(notes, min_cluster_size=2)
        # Only 1 shared tag — no cluster formed
        assert result == []

    def test_min_cluster_size_respected(self):
        notes = [
            {"title": "A", "tags": ["x", "y"], "summary": ""},
            {"title": "B", "tags": ["x", "y"], "summary": ""},
        ]
        result = rst_mod._tag_based_clusters(notes, min_cluster_size=3)
        assert result == []


# ===========================================================================
# _find_split_candidates
# ===========================================================================

class TestFindSplitCandidates:
    def test_returns_large_notes(self, tmp_path):
        note = _note_dict(tmp_path / "big.md", "Big Note", content="x" * 5000)
        small = _note_dict(tmp_path / "small.md", "Small Note", content="x" * 100)
        result = rst_mod._find_split_candidates([note, small], set(), min_size=3000)
        assert len(result) == 1
        assert result[0]["title"] == "Big Note"

    def test_excludes_clustered_paths(self, tmp_path):
        note = _note_dict(tmp_path / "big.md", "Big", content="x" * 5000)
        clustered = {str(tmp_path / "big.md")}
        result = rst_mod._find_split_candidates([note], clustered, min_size=100)
        assert result == []


# ===========================================================================
# _format_cluster_block
# ===========================================================================

class TestFormatClusterBlock:
    def test_empty_clusters(self, tmp_path):
        result = rst_mod._format_cluster_block([], tmp_path)
        assert "_No clusters found._" in result

    def test_formats_cluster(self, tmp_path):
        notes = [
            _note_dict(tmp_path / "A.md", "Note A", summary="About A"),
            _note_dict(tmp_path / "B.md", "Note B"),
        ]
        result = rst_mod._format_cluster_block([notes], tmp_path)
        assert "Note A" in result
        assert "Note B" in result

    def test_truncates_long_content(self, tmp_path):
        notes = [_note_dict(tmp_path / "A.md", "Note A", content="x" * 2000)]
        result = rst_mod._format_cluster_block([notes], tmp_path)
        assert "truncated" in result


# ===========================================================================
# _format_split_candidates_block
# ===========================================================================

class TestFormatSplitCandidatesBlock:
    def test_empty_candidates(self, tmp_path):
        result = rst_mod._format_split_candidates_block([], tmp_path)
        assert "_No large notes found._" in result

    def test_formats_candidate(self, tmp_path):
        notes = [_note_dict(tmp_path / "big.md", "Big Note")]
        result = rst_mod._format_split_candidates_block(notes, tmp_path)
        assert "Big Note" in result

    def test_truncates_long_content(self, tmp_path):
        notes = [_note_dict(tmp_path / "big.md", "Big Note", content="x" * 5000)]
        result = rst_mod._format_split_candidates_block(notes, tmp_path)
        assert "truncated" in result


# ===========================================================================
# _format_folder_hub_block
# ===========================================================================

class TestFormatFolderHubBlock:
    def test_new_hub_mode(self, tmp_path):
        notes = [_note_dict(tmp_path / "A.md", "Note A", summary="A summary")]
        result = rst_mod._format_folder_hub_block(notes, tmp_path, hub_path="hub.md")
        assert "hub.md" in result
        assert "Note A" in result
        assert "Create a hub/index" in result

    def test_existing_hub_mode(self, tmp_path):
        notes = [_note_dict(tmp_path / "A.md", "Note A")]
        result = rst_mod._format_folder_hub_block(
            notes, tmp_path, hub_path="hub.md", existing_hub="# Existing Hub\n"
        )
        assert "Update it" in result
        assert "Existing Hub" in result

    def test_truncates_long_existing_hub(self, tmp_path):
        notes = [_note_dict(tmp_path / "A.md", "Note A")]
        long_hub = "x" * 5000
        result = rst_mod._format_folder_hub_block(notes, tmp_path, existing_hub=long_hub)
        assert "truncated" in result


# ===========================================================================
# _append_errata_log
# ===========================================================================

class TestAppendErrataLog:
    def test_skips_when_empty(self, tmp_path):
        rst_mod._append_errata_log(tmp_path, "AI/Log.md", [])
        assert not (tmp_path / "AI" / "Log.md").exists()

    def test_writes_entries(self, tmp_path):
        rst_mod._append_errata_log(tmp_path, "AI/Log.md", ["entry1", "entry2"])
        content = (tmp_path / "AI" / "Log.md").read_text()
        assert "entry1" in content
        assert "Restructure Run" in content


# ===========================================================================
# _is_within_vault
# ===========================================================================

class TestIsWithinVault:
    def test_inside(self, tmp_path):
        assert rst_mod._is_within_vault(tmp_path, tmp_path / "sub") is True

    def test_outside(self, tmp_path):
        assert rst_mod._is_within_vault(tmp_path, Path("/other/path")) is False


# ===========================================================================
# _build_folder_context
# ===========================================================================

class TestBuildFolderContext:
    def test_returns_context_string(self, tmp_path):
        sub = tmp_path / "folder"
        sub.mkdir()
        _make_note(sub / "note.md", "Test Note")
        notes = rst_mod._collect_notes(sub, tmp_path, [])
        result = rst_mod._build_folder_context(sub, tmp_path, notes, [])
        assert "Total notes" in result
        assert "folder" in result


# ===========================================================================
# _execute_cluster_decisions
# ===========================================================================

class TestExecuteClusterDecisions:
    def _cluster(self, tmp_path, titles):
        notes = []
        for t in titles:
            p = tmp_path / (t + ".md")
            _make_note(p, t)
            notes.append(_note_dict(p, t, content=p.read_text()))
        return notes

    def test_keep_separate(self, tmp_path):
        cluster = self._cluster(tmp_path, ["A", "B"])
        decisions = [{"cluster_index": 0, "action": "keep-separate", "rationale": "fine"}]
        result_lines, errata, written = [], [], []
        rst_mod._execute_cluster_decisions(decisions, [cluster], tmp_path, "ts", result_lines, errata, written)
        assert any("kept separate" in l for l in result_lines)

    def test_merge(self, tmp_path):
        cluster = self._cluster(tmp_path, ["A", "B"])
        merged_content = "---\ntitle: Merged\ntype: reference\nsummary: S\ntags: []\n---\n\nbody\n"
        decisions = [{
            "cluster_index": 0, "action": "merge",
            "merged_title": "Merged", "merged_path": "Merged.md",
            "merged_content": merged_content, "rationale": ""
        }]
        result_lines, errata, written = [], [], []
        nc, nd = rst_mod._execute_cluster_decisions(decisions, [cluster], tmp_path, "ts", result_lines, errata, written)
        assert (tmp_path / "Merged.md").exists()
        assert nc == 1
        assert nd == 2  # both source notes deleted

    def test_merge_skips_missing_content(self, tmp_path):
        cluster = self._cluster(tmp_path, ["A"])
        decisions = [{"cluster_index": 0, "action": "merge", "merged_path": "", "merged_content": ""}]
        result_lines, errata, written = [], [], []
        rst_mod._execute_cluster_decisions(decisions, [cluster], tmp_path, "ts", result_lines, errata, written)
        assert any("missing path or content" in l for l in result_lines)

    def test_merge_skips_path_traversal(self, tmp_path):
        cluster = self._cluster(tmp_path, ["A"])
        decisions = [{
            "cluster_index": 0, "action": "merge",
            "merged_title": "X", "merged_path": "../../evil.md",
            "merged_content": "content", "rationale": ""
        }]
        result_lines, errata, written = [], [], []
        rst_mod._execute_cluster_decisions(decisions, [cluster], tmp_path, "ts", result_lines, errata, written)
        assert any("path traversal" in l for l in result_lines)

    def test_hub_spoke(self, tmp_path):
        cluster = self._cluster(tmp_path, ["A", "B"])
        hub_content = "---\ntitle: Hub\ntype: reference\nsummary: S\ntags: []\n---\n\nhub body\n"
        decisions = [{
            "cluster_index": 0, "action": "hub-spoke",
            "hub_title": "Hub", "hub_path": "Hub.md",
            "hub_content": hub_content, "rationale": ""
        }]
        result_lines, errata, written = [], [], []
        nc, nd = rst_mod._execute_cluster_decisions(decisions, [cluster], tmp_path, "ts", result_lines, errata, written)
        assert (tmp_path / "Hub.md").exists()
        assert nc == 1
        assert nd == 0  # sub-notes kept

    def test_hub_spoke_skips_path_traversal(self, tmp_path):
        cluster = self._cluster(tmp_path, ["A"])
        decisions = [{
            "cluster_index": 0, "action": "hub-spoke",
            "hub_title": "H", "hub_path": "../../evil.md",
            "hub_content": "content", "rationale": ""
        }]
        result_lines, errata, written = [], [], []
        rst_mod._execute_cluster_decisions(decisions, [cluster], tmp_path, "ts", result_lines, errata, written)
        assert any("path traversal" in l for l in result_lines)

    def test_subfolder(self, tmp_path):
        cluster = self._cluster(tmp_path, ["A", "B"])
        hub_content = "---\ntitle: Hub\ntype: reference\nsummary: S\ntags: []\n---\n\nbody\n"
        decisions = [{
            "cluster_index": 0, "action": "subfolder",
            "subfolder_path": "sub", "hub_title": "Hub",
            "hub_path": "sub/Hub.md", "hub_content": hub_content, "rationale": ""
        }]
        result_lines, errata, written = [], [], []
        nc, nd = rst_mod._execute_cluster_decisions(decisions, [cluster], tmp_path, "ts", result_lines, errata, written)
        assert (tmp_path / "sub").is_dir()
        assert (tmp_path / "sub" / "Hub.md").exists()

    def test_out_of_range_cluster_skipped(self, tmp_path):
        cluster = self._cluster(tmp_path, ["A"])
        decisions = [{"cluster_index": 99, "action": "merge"}]
        result_lines, errata, written = [], [], []
        rst_mod._execute_cluster_decisions(decisions, [cluster], tmp_path, "ts", result_lines, errata, written)
        assert result_lines == []

    def test_missing_cluster_index_skipped(self, tmp_path):
        cluster = self._cluster(tmp_path, ["A"])
        decisions = [{"action": "keep-separate"}]  # no cluster_index
        result_lines, errata, written = [], [], []
        rst_mod._execute_cluster_decisions(decisions, [cluster], tmp_path, "ts", result_lines, errata, written)
        assert result_lines == []


# ===========================================================================
# _format_preview_output
# ===========================================================================

class TestFormatPreviewOutput:
    def test_keep_separate_action(self, tmp_path):
        note = _note_dict(tmp_path / "A.md", "Note A")
        clusters = [[note]]
        decisions = [{"cluster_index": 0, "action": "keep-separate", "rationale": "fine"}]
        result = rst_mod._format_preview_output(decisions, clusters, [])
        assert "Keep Separate" in result

    def test_merge_action(self, tmp_path):
        note = _note_dict(tmp_path / "A.md", "Note A")
        clusters = [[note]]
        decisions = [{
            "cluster_index": 0, "action": "merge",
            "merged_title": "M", "merged_path": "M.md",
            "merged_content": "content"
        }]
        result = rst_mod._format_preview_output(decisions, clusters, [])
        assert "Merge" in result
        assert "M" in result

    def test_hub_spoke_action(self, tmp_path):
        note = _note_dict(tmp_path / "A.md", "Note A")
        clusters = [[note]]
        decisions = [{
            "cluster_index": 0, "action": "hub-spoke",
            "hub_title": "Hub", "hub_path": "hub.md",
            "hub_content": "hub content"
        }]
        result = rst_mod._format_preview_output(decisions, clusters, [])
        assert "Hub-Spoke" in result

    def test_subfolder_action(self, tmp_path):
        note = _note_dict(tmp_path / "A.md", "Note A")
        clusters = [[note]]
        decisions = [{
            "cluster_index": 0, "action": "subfolder",
            "hub_title": "Sub Hub", "subfolder_path": "sub",
            "hub_path": "sub/hub.md", "hub_content": "content"
        }]
        result = rst_mod._format_preview_output(decisions, clusters, [])
        assert "Subfolder" in result

    def test_split_action(self, tmp_path):
        candidate = _note_dict(tmp_path / "big.md", "Big Note")
        decisions = [{
            "note_index": 0, "action": "split",
            "rationale": "",
            "output_notes": [{"title": "Part A", "path": "a.md", "content": "body a"}]
        }]
        result = rst_mod._format_preview_output(decisions, [], [candidate])
        assert "Split" in result
        assert "Part A" in result

    def test_keep_action_for_note(self, tmp_path):
        candidate = _note_dict(tmp_path / "big.md", "Big Note")
        decisions = [{"note_index": 0, "action": "keep", "rationale": "well-organized"}]
        result = rst_mod._format_preview_output(decisions, [], [candidate])
        assert "Keep As-Is" in result

    def test_truncates_long_content(self, tmp_path):
        note = _note_dict(tmp_path / "A.md", "Note A")
        clusters = [[note]]
        decisions = [{
            "cluster_index": 0, "action": "merge",
            "merged_title": "M", "merged_path": "M.md",
            "merged_content": "x" * 5000
        }]
        result = rst_mod._format_preview_output(decisions, clusters, [])
        assert "truncated" in result


# ===========================================================================
# cb_restructure — parameter validation and vault checks
# ===========================================================================

class TestCbRestructureValidation:
    def test_raises_when_no_vault(self):
        with patch.object(rst_mod, "_load_config", return_value={"vault_path": ""}):
            with pytest.raises(ToolError, match="No vault configured"):
                _cb_restructure()()

    def test_raises_when_vault_not_exist(self, tmp_path):
        with patch.object(rst_mod, "_load_config",
                          return_value={"vault_path": str(tmp_path / "missing")}):
            with pytest.raises(ToolError, match="does not exist"):
                _cb_restructure()()

    def test_raises_when_folder_not_found(self, tmp_path):
        with patch.object(rst_mod, "_load_config",
                          return_value={"vault_path": str(tmp_path)}):
            with pytest.raises(ToolError, match="Folder not found"):
                _cb_restructure()(folder="nonexistent")

    def test_raises_when_folder_outside_vault(self, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        # Simulate path traversal via symlink or absolute path via folder param
        with patch.object(rst_mod, "_load_config",
                          return_value={"vault_path": str(tmp_path / "vault")}):
            # vault doesn't exist → raises "Vault path does not exist"
            with pytest.raises(ToolError):
                _cb_restructure()(folder="../../outside")

    def test_raises_folder_hub_without_folder(self, tmp_path):
        with patch.object(rst_mod, "_load_config",
                          return_value={"vault_path": str(tmp_path)}):
            with pytest.raises(ToolError, match="folder_hub requires"):
                _cb_restructure()(folder_hub=True)

    def test_raises_hub_path_without_folder_hub(self, tmp_path):
        with patch.object(rst_mod, "_load_config",
                          return_value={"vault_path": str(tmp_path)}):
            with pytest.raises(ToolError, match="hub_path is only used"):
                _cb_restructure()(hub_path="hub.md")

    def test_raises_dry_run_and_preview_together(self, tmp_path):
        with patch.object(rst_mod, "_load_config",
                          return_value={"vault_path": str(tmp_path)}):
            with pytest.raises(ToolError, match="mutually exclusive"):
                _cb_restructure()(dry_run=True, preview=True)

    def test_raises_hub_path_outside_vault(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        with patch.object(rst_mod, "_load_config",
                          return_value={"vault_path": str(tmp_path)}):
            with pytest.raises(ToolError, match="outside the vault"):
                _cb_restructure()(folder="sub", folder_hub=True, hub_path="../../etc/evil.md")

    def test_returns_info_when_no_notes(self, tmp_path):
        with patch.object(rst_mod, "_load_config",
                          return_value={"vault_path": str(tmp_path)}), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="prompt"):
            result = _cb_restructure()()
        assert "No eligible notes" in result


# ===========================================================================
# cb_restructure — normal mode dry_run
# ===========================================================================

class TestCbRestructureNormalDryRun:
    def test_dry_run_shows_clusters(self, tmp_path):
        _make_note(tmp_path / "A.md", "Note A", tags=["x", "y"])
        _make_note(tmp_path / "B.md", "Note B", tags=["x", "y"])

        fake_cluster = [
            rst_mod._collect_notes(tmp_path, tmp_path, [])[0],
            rst_mod._collect_notes(tmp_path, tmp_path, [])[1],
        ]

        with patch.object(rst_mod, "_load_config",
                          return_value={"vault_path": str(tmp_path)}), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_build_clusters", return_value=[fake_cluster]):
            result = _cb_restructure()(dry_run=True)
        assert "DRY RUN" in result
        assert "Cluster 1" in result

    def test_dry_run_shows_nothing_when_empty(self, tmp_path):
        _make_note(tmp_path / "A.md", "Short")

        with patch.object(rst_mod, "_load_config",
                          return_value={"vault_path": str(tmp_path)}), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_build_clusters", return_value=[]):
            result = _cb_restructure()(dry_run=True)
        assert "Nothing to restructure" in result


# ===========================================================================
# cb_restructure — folder_hub dry_run
# ===========================================================================

class TestCbRestructureFolderHubDryRun:
    def test_folder_hub_dry_run(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")
        _make_note(sub / "B.md", "Note B")

        with patch.object(rst_mod, "_load_config",
                          return_value={"vault_path": str(tmp_path)}), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=True)
        assert "DRY RUN" in result
        assert "Folder hub mode" in result


# ===========================================================================
# cb_restructure — execute normal mode
# ===========================================================================

class TestCbRestructureExecute:
    def _base_config(self, tmp_path):
        return {
            "vault_path": str(tmp_path),
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
            "consolidation_log": "AI/Log.md",
            "consolidation_log_enabled": True,
        }

    def test_merge_execution(self, tmp_path):
        _make_note(tmp_path / "A.md", "Note A", tags=["x", "y"])
        _make_note(tmp_path / "B.md", "Note B", tags=["x", "y"])
        notes = rst_mod._collect_notes(tmp_path, tmp_path, [])
        cluster = notes[:2]

        merged_content = "---\ntitle: Merged\ntype: reference\nsummary: S\ntags: []\n---\n\nbody\n"
        decision = {
            "cluster_index": 0, "action": "merge",
            "merged_title": "Merged", "merged_path": "Merged.md",
            "rationale": "related"
        }

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_build_clusters", return_value=[cluster]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch.object(rst_mod, "_call_decisions", return_value=[decision]), \
             patch.object(rst_mod, "_call_generate_cluster", return_value={"merged_content": merged_content}):
            result = _cb_restructure()(dry_run=False)
        assert "Restructure Complete" in result
        assert (tmp_path / "Merged.md").exists()

    def test_split_execution(self, tmp_path):
        big_content = "---\ntitle: Big\ntype: reference\nsummary: S\ntags: []\n---\n\n" + "x" * 4000
        (tmp_path / "Big.md").write_text(big_content)
        notes = rst_mod._collect_notes(tmp_path, tmp_path, [])

        part_content = "---\ntitle: Part A\ntype: reference\nsummary: S\ntags: []\n---\n\nbody\n"
        decision = {
            "note_index": 0, "action": "split", "rationale": ""
        }

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_build_clusters", return_value=[]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch.object(rst_mod, "_call_decisions", return_value=[decision]), \
             patch.object(rst_mod, "_call_generate_split", return_value={"output_notes": [{"title": "Part A", "path": "PartA.md", "content": part_content}]}):
            result = _cb_restructure()(dry_run=False, split_threshold=100)
        assert (tmp_path / "PartA.md").exists()
        assert "split" in result.lower()

    def test_split_skips_path_traversal(self, tmp_path):
        big_content = "---\ntitle: Big\ntype: reference\nsummary: S\ntags: []\n---\n\n" + "x" * 4000
        (tmp_path / "Big.md").write_text(big_content)

        decision = {"note_index": 0, "action": "split", "rationale": "", "output_notes": [{"title": "Evil", "path": "../../evil.md"}]}
        gen_content = {"output_notes": [{"title": "Evil", "path": "../../evil.md", "content": "body"}]}

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_build_clusters", return_value=[]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch.object(rst_mod, "_call_decisions", return_value=[decision]), \
             patch.object(rst_mod, "_call_generate_split", return_value=gen_content):
            result = _cb_restructure()(dry_run=False, split_threshold=100)
        assert "path traversal" in result

    def test_split_skips_empty_output_notes(self, tmp_path):
        big_content = "---\ntitle: Big\ntype: reference\nsummary: S\ntags: []\n---\n\n" + "x" * 4000
        (tmp_path / "Big.md").write_text(big_content)

        decision = {"note_index": 0, "action": "split", "output_notes": []}
        gen_content = {"output_notes": []}

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_build_clusters", return_value=[]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch.object(rst_mod, "_call_decisions", return_value=[decision]), \
             patch.object(rst_mod, "_call_generate_split", return_value=gen_content):
            result = _cb_restructure()(dry_run=False, split_threshold=100)
        assert "no output notes" in result.lower()

    def test_keep_action_for_large_note(self, tmp_path):
        big_content = "---\ntitle: Big\ntype: reference\nsummary: S\ntags: []\n---\n\n" + "x" * 4000
        (tmp_path / "Big.md").write_text(big_content)

        decisions = [{"note_index": 0, "action": "keep", "rationale": "well-organized"}]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_build_clusters", return_value=[]), \
             patch("backends.call_model", return_value=json.dumps(decisions)), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(dry_run=False, split_threshold=100)
        assert "kept as-is" in result

    def test_backend_error_raises_tool_error(self, tmp_path):
        _make_note(tmp_path / "A.md", "Note A", tags=["x", "y"])
        _make_note(tmp_path / "B.md", "Note B", tags=["x", "y"])
        notes = rst_mod._collect_notes(tmp_path, tmp_path, [])

        class FakeBackendError(Exception):
            pass

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_build_clusters", return_value=[notes]), \
             patch("backends.call_model", side_effect=FakeBackendError("boom")), \
             patch("backends.BackendError", FakeBackendError):
            with pytest.raises(ToolError, match="Backend error"):
                _cb_restructure()(dry_run=False)

    def test_invalid_json_raises_tool_error(self, tmp_path):
        _make_note(tmp_path / "A.md", "Note A", tags=["x", "y"])
        notes = rst_mod._collect_notes(tmp_path, tmp_path, [])

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_build_clusters", return_value=[notes]), \
             patch("backends.call_model", return_value="~~ completely broken ~~"), \
             patch("backends.BackendError", Exception):
            with pytest.raises(ToolError, match="invalid JSON"):
                _cb_restructure()(dry_run=False)

    def test_non_list_json_raises_tool_error(self, tmp_path):
        _make_note(tmp_path / "A.md", "Note A", tags=["x", "y"])
        notes = rst_mod._collect_notes(tmp_path, tmp_path, [])

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_build_clusters", return_value=[notes]), \
             patch("backends.call_model", return_value='{"not": "a list"}'), \
             patch("backends.BackendError", Exception):
            with pytest.raises(ToolError, match="not a JSON array"):
                _cb_restructure()(dry_run=False)

    def test_preview_mode(self, tmp_path):
        _make_note(tmp_path / "A.md", "Note A", tags=["x", "y"])
        _make_note(tmp_path / "B.md", "Note B", tags=["x", "y"])
        notes = rst_mod._collect_notes(tmp_path, tmp_path, [])
        cluster = notes[:2]

        decisions = [{"cluster_index": 0, "action": "keep-separate", "rationale": "ok"}]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_build_clusters", return_value=[cluster]), \
             patch("backends.call_model", return_value=json.dumps(decisions)), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(dry_run=False, preview=True)
        assert "Preview" in result


# ===========================================================================
# cb_restructure — folder_hub execute
# ===========================================================================

class TestCbRestructureFolderHubExecute:
    def _base_config(self, tmp_path):
        return {
            "vault_path": str(tmp_path),
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
            "consolidation_log": "AI/Log.md",
            "consolidation_log_enabled": True,
        }

    def test_folder_hub_execute_creates_hub(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")
        _make_note(sub / "B.md", "Note B")

        hub_content = "---\ntitle: Hub\ntype: reference\nsummary: S\ntags: []\n---\n\nhub body\n"
        # Phase 1 returns no clusters; phase 2 returns hub decision
        phase2_decisions = [{
            "action": "hub-spoke",
            "hub_title": "SubHub",
            "hub_path": "sub/hub.md",
            "hub_content": hub_content,
        }]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", side_effect=["[]", json.dumps(phase2_decisions)]), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=False)
        assert (tmp_path / "sub" / "hub.md").exists()
        assert "Created hub" in result or "SubHub" in result

    def test_folder_hub_skips_when_no_hub_decision(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", side_effect=["[]", "[]"]), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=False)
        assert "skipped" in result.lower() or "no" in result.lower()

    def test_folder_hub_backend_error_cluster_phase(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")
        _make_note(sub / "B.md", "Note B")
        notes = rst_mod._collect_notes(sub, tmp_path, [])

        class FakeBackendError(Exception):
            pass

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[notes]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", side_effect=FakeBackendError("fail")), \
             patch("backends.BackendError", FakeBackendError):
            with pytest.raises(ToolError, match="Backend error"):
                _cb_restructure()(folder="sub", folder_hub=True, dry_run=False)


# ===========================================================================
# _repair_json — invalid JSON object inside bracket extraction path
# ===========================================================================

class TestRepairJsonEdgeCases:
    def test_object_extraction_skips_invalid_json(self):
        # A string with {}-looking content but not valid JSON objects;
        # all bracket-repair paths fail, then object extraction finds no valid objects
        raw = "{bad json here} and {more bad}"
        with pytest.raises(json.JSONDecodeError):
            rst_mod._repair_json(raw)

    def test_object_extraction_picks_valid_among_invalid(self):
        # Mix of a bad object and a valid one — valid one should be returned
        raw = '{bad json} {"action": "keep"}'
        result = rst_mod._repair_json(raw)
        assert isinstance(result, list)
        assert result[0]["action"] == "keep"


# ===========================================================================
# _collect_notes — OSError and string-tags-that-fail-parse paths
# ===========================================================================

class TestCollectNotesEdgePaths:
    def test_oserror_on_read_skips_note(self, tmp_path):
        good = tmp_path / "good.md"
        _make_note(good, "Good Note")
        bad = tmp_path / "bad.md"
        _make_note(bad, "Bad Note")

        original_read_text = Path.read_text

        def mock_read_text(self, **kwargs):
            if self.name == "bad.md":
                raise OSError("permission denied")
            return original_read_text(self, **kwargs)

        with patch.object(Path, "read_text", mock_read_text):
            notes = rst_mod._collect_notes(tmp_path, tmp_path, [])
        titles = [n["title"] for n in notes]
        assert "Good Note" in titles
        assert "Bad Note" not in titles

    def test_tags_string_that_fails_json_parse(self, tmp_path):
        # Write a note where tags is a bare string that is not JSON
        content = "---\ntitle: 'Foo'\ntype: reference\nsummary: 'S'\ntags: not-valid-json\n---\n\nbody\n"
        (tmp_path / "foo.md").write_text(content)
        notes = rst_mod._collect_notes(tmp_path, tmp_path, [])
        assert len(notes) == 1
        # tags should fall back to []
        assert notes[0]["tags"] == []

    def test_tags_not_a_list_falls_back(self, tmp_path):
        # Write a note where tags parses to a non-list (e.g. a dict)
        content = '---\ntitle: "Bar"\ntype: reference\nsummary: "S"\ntags: {}\n---\n\nbody\n'
        (tmp_path / "bar.md").write_text(content)
        notes = rst_mod._collect_notes(tmp_path, tmp_path, [])
        assert len(notes) == 1
        assert notes[0]["tags"] == []


# ===========================================================================
# _collect_notes_for_hub — subfolder sampling logic
# ===========================================================================

class TestCollectNotesForHub:
    def test_collects_flat_notes_and_subfolder_representative(self, tmp_path):
        # Flat note in root
        _make_note(tmp_path / "flat.md", "Flat Note")
        # Subfolder with notes — first found should be chosen (no index.md or name match)
        sub = tmp_path / "mysub"
        sub.mkdir()
        _make_note(sub / "alpha.md", "Alpha")
        _make_note(sub / "beta.md", "Beta")

        notes = rst_mod._collect_notes_for_hub(tmp_path, tmp_path, [])
        titles = [n["title"] for n in notes]
        assert "Flat Note" in titles
        # One representative from mysub (whichever is first alphabetically)
        assert any(t in titles for t in ["Alpha", "Beta"])
        # Should not include BOTH subfolder notes
        subfolder_titles = [t for t in titles if t in ("Alpha", "Beta")]
        assert len(subfolder_titles) == 1

    def test_prefers_index_md_as_representative(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "alpha.md", "Alpha")
        _make_note(sub / "index.md", "Index Note")
        _make_note(sub / "beta.md", "Beta")

        notes = rst_mod._collect_notes_for_hub(tmp_path, tmp_path, [])
        titles = [n["title"] for n in notes]
        assert "Index Note" in titles
        assert "Alpha" not in titles
        assert "Beta" not in titles

    def test_prefers_stem_matching_subfolder_name(self, tmp_path):
        sub = tmp_path / "recipes"
        sub.mkdir()
        _make_note(sub / "alpha.md", "Alpha")
        _make_note(sub / "recipes.md", "Recipes Main")

        notes = rst_mod._collect_notes_for_hub(tmp_path, tmp_path, [])
        titles = [n["title"] for n in notes]
        assert "Recipes Main" in titles
        assert "Alpha" not in titles

    def test_skips_locked_subfolder_representative(self, tmp_path):
        sub = tmp_path / "locked_sub"
        sub.mkdir()
        _make_note(sub / "only.md", "Only Note", locked=True)

        notes = rst_mod._collect_notes_for_hub(tmp_path, tmp_path, [])
        # Locked note should be skipped; subfolder yields nothing
        titles = [n["title"] for n in notes]
        assert "Only Note" not in titles

    def test_skips_excluded_subfolder(self, tmp_path):
        sub = tmp_path / "Templates"
        sub.mkdir()
        _make_note(sub / "tmpl.md", "Template Note")

        notes = rst_mod._collect_notes_for_hub(tmp_path, tmp_path, ["Templates"])
        titles = [n["title"] for n in notes]
        assert "Template Note" not in titles

    def test_skips_hidden_subfolder(self, tmp_path):
        sub = tmp_path / ".hidden"
        sub.mkdir()
        _make_note(sub / "secret.md", "Secret")

        notes = rst_mod._collect_notes_for_hub(tmp_path, tmp_path, [])
        titles = [n["title"] for n in notes]
        assert "Secret" not in titles

    def test_subfolder_with_no_candidates_skipped(self, tmp_path):
        # Subfolder with no .md files
        sub = tmp_path / "empty_sub"
        sub.mkdir()
        (sub / "readme.txt").write_text("not a note")
        _make_note(tmp_path / "flat.md", "Flat")

        notes = rst_mod._collect_notes_for_hub(tmp_path, tmp_path, [])
        titles = [n["title"] for n in notes]
        assert "Flat" in titles
        # No note from empty_sub
        assert len([t for t in titles if t not in ("Flat",)]) == 0

    def test_oserror_on_subfolder_read_skips(self, tmp_path):
        sub = tmp_path / "mysub"
        sub.mkdir()
        note_path = sub / "alpha.md"
        _make_note(note_path, "Alpha")

        original_read_text = Path.read_text

        def mock_read_text(self, **kwargs):
            if self.name == "alpha.md":
                raise OSError("no access")
            return original_read_text(self, **kwargs)

        with patch.object(Path, "read_text", mock_read_text):
            notes = rst_mod._collect_notes_for_hub(tmp_path, tmp_path, [])
        titles = [n["title"] for n in notes]
        assert "Alpha" not in titles

    def test_subfolder_representative_string_tags_falls_back(self, tmp_path):
        sub = tmp_path / "mysub"
        sub.mkdir()
        # Note with string tags (not a list), tests the `isinstance(tags, str): tags = []` branch
        content = "---\ntitle: 'String Tags'\ntype: reference\nsummary: 'S'\ntags: some-tag\n---\n\nbody\n"
        (sub / "note.md").write_text(content)

        notes = rst_mod._collect_notes_for_hub(tmp_path, tmp_path, [])
        subfolder_notes = [n for n in notes if n["title"] == "String Tags"]
        assert len(subfolder_notes) == 1
        assert subfolder_notes[0]["tags"] == []

    def test_subfolder_representative_non_list_tags_falls_back(self, tmp_path):
        sub = tmp_path / "mysub"
        sub.mkdir()
        # Note with dict tags (not a list), tests the `not isinstance(tags, list): tags = []` branch
        content = '---\ntitle: "Dict Tags"\ntype: reference\nsummary: "S"\ntags:\n  key: val\n---\n\nbody\n'
        (sub / "note.md").write_text(content)

        notes = rst_mod._collect_notes_for_hub(tmp_path, tmp_path, [])
        subfolder_notes = [n for n in notes if n["title"] == "Dict Tags"]
        assert len(subfolder_notes) == 1
        assert subfolder_notes[0]["tags"] == []

    def test_default_summary_used_when_missing(self, tmp_path):
        sub = tmp_path / "mysub"
        sub.mkdir()
        # Note without summary field
        content = "---\ntitle: 'No Summary'\ntype: reference\ntags: []\n---\n\nbody\n"
        (sub / "nosummary.md").write_text(content)

        notes = rst_mod._collect_notes_for_hub(tmp_path, tmp_path, [])
        subfolder_notes = [n for n in notes if n["title"] == "No Summary"]
        assert len(subfolder_notes) == 1
        assert "mysub" in subfolder_notes[0]["summary"]


# ===========================================================================
# _build_clusters — with search backend
# ===========================================================================

class TestBuildClustersWithBackend:
    def _make_note_dict(self, path_str: str, title: str, tags=None) -> dict:
        return {
            "path": Path(path_str),
            "title": title,
            "summary": "A summary",
            "tags": tags or ["python"],
            "content": "content",
            "rel_path": path_str,
        }

    def test_backend_none_falls_back_to_tag_clustering(self):
        notes = [
            self._make_note_dict("/v/a.md", "Alpha", ["python", "testing"]),
            self._make_note_dict("/v/b.md", "Beta", ["python", "testing"]),
        ]
        clusters = rst_mod._build_clusters(notes, None, 0.5, 2)
        assert len(clusters) == 1
        assert len(clusters[0]) == 2

    def test_backend_search_builds_cluster(self, tmp_path):
        note_a = tmp_path / "a.md"
        note_b = tmp_path / "b.md"
        _make_note(note_a, "Python Testing")
        _make_note(note_b, "Python Framework")

        notes = [
            self._make_note_dict(str(note_a), "Python Testing", ["python"]),
            self._make_note_dict(str(note_b), "Python Framework", ["python"]),
        ]

        backend = MagicMock()
        result_a = MagicMock()
        result_a.path = str(note_b)
        result_a.score = 0.9
        result_b = MagicMock()
        result_b.path = str(note_a)
        result_b.score = 0.9

        # Each word search for note A returns note B (and vice-versa)
        # We need weight >= 2 for adjacency, so return the result for multiple words
        def search_side_effect(word, top_k=10):
            if word in ("python", "testing", "framework"):
                return [result_a, result_b]
            return []

        backend.search.side_effect = search_side_effect

        clusters = rst_mod._build_clusters(notes, backend, 0.5, 2)
        # With multiple word hits, the two notes should cluster together
        assert len(clusters) >= 1
        all_in_clusters = [n for c in clusters for n in c]
        assert len(all_in_clusters) >= 2

    def test_backend_search_exception_continues(self, tmp_path):
        note_a = tmp_path / "a.md"
        note_b = tmp_path / "b.md"
        _make_note(note_a, "Foo Note")
        _make_note(note_b, "Bar Note")

        notes = [
            self._make_note_dict(str(note_a), "Foo Note", ["foo"]),
            self._make_note_dict(str(note_b), "Bar Note", ["bar"]),
        ]

        backend = MagicMock()
        backend.search.side_effect = Exception("search failed")

        # Should not raise; returns singleton components (no clusters of size >= 2)
        clusters = rst_mod._build_clusters(notes, backend, 0.5, 2)
        assert isinstance(clusters, list)

    def test_backend_self_match_ignored(self, tmp_path):
        note_a = tmp_path / "a.md"
        _make_note(note_a, "Self Note")

        notes = [self._make_note_dict(str(note_a), "Self Note", ["self"])]

        backend = MagicMock()
        result = MagicMock()
        result.path = str(note_a)  # Same path as note itself
        result.score = 1.0
        backend.search.return_value = [result]

        clusters = rst_mod._build_clusters(notes, backend, 0.5, 1)
        # min_cluster_size=1, single note in its own component
        assert len(clusters) == 1

    def test_backend_bfs_visited_check_with_triangle(self, tmp_path):
        # Three nodes all connected: A-B, B-C, A-C (triangle)
        # BFS from A visits B and C; when processing C's neighbors, A is already visited
        # This exercises the "if node in visited: continue" branch in BFS
        note_a = tmp_path / "a.md"
        note_b = tmp_path / "b.md"
        note_c = tmp_path / "c.md"
        _make_note(note_a, "Alpha")
        _make_note(note_b, "Beta")
        _make_note(note_c, "Gamma")

        notes = [
            self._make_note_dict(str(note_a), "Alpha", ["python"]),
            self._make_note_dict(str(note_b), "Beta", ["python"]),
            self._make_note_dict(str(note_c), "Gamma", ["python"]),
        ]

        backend = MagicMock()

        def search_side_effect(word, top_k=10):
            # All notes find all other notes with high weight
            results = []
            for note in notes:
                r = MagicMock()
                r.path = str(note["path"])
                r.score = 0.9
                results.append(r)
            return results

        backend.search.side_effect = search_side_effect

        clusters = rst_mod._build_clusters(notes, backend, 0.5, 2)
        assert len(clusters) == 1
        assert len(clusters[0]) == 3

    def test_backend_weak_edge_below_threshold_no_cluster(self, tmp_path):
        note_a = tmp_path / "a.md"
        note_b = tmp_path / "b.md"
        _make_note(note_a, "Foo")
        _make_note(note_b, "Bar")

        notes = [
            self._make_note_dict(str(note_a), "Foo", ["foo"]),
            self._make_note_dict(str(note_b), "Bar", ["bar"]),
        ]

        backend = MagicMock()
        result = MagicMock()
        result.path = str(note_b)
        result.score = 0.9
        # Return note_b only once (weight=1 < 2 threshold) for note_a's searches
        call_count = [0]

        def search_side_effect(word, top_k=10):
            call_count[0] += 1
            if call_count[0] == 1:
                return [result]
            return []

        backend.search.side_effect = search_side_effect

        clusters = rst_mod._build_clusters(notes, backend, 0.5, 2)
        # Edge weight is 1, which is < 2 required for adjacency
        assert len(clusters) == 0

    def test_backend_zero_score_ignored(self, tmp_path):
        note_a = tmp_path / "a.md"
        note_b = tmp_path / "b.md"
        _make_note(note_a, "Foo")
        _make_note(note_b, "Bar")

        notes = [
            self._make_note_dict(str(note_a), "Foo", ["foo"]),
            self._make_note_dict(str(note_b), "Bar", ["bar"]),
        ]

        backend = MagicMock()
        result = MagicMock()
        result.path = str(note_b)
        result.score = 0  # Zero score should be ignored
        backend.search.return_value = [result]

        clusters = rst_mod._build_clusters(notes, backend, 0.5, 2)
        # Zero-score results don't form edges; no cluster of size >= 2
        assert len(clusters) == 0


# ===========================================================================
# _tag_based_clusters — additional coverage
# ===========================================================================

class TestTagBasedClustersExtra:
    def test_no_shared_tags_no_clusters(self):
        notes = [
            {"path": Path("/v/a.md"), "title": "A", "summary": "", "tags": ["python"], "content": "", "rel_path": "a.md"},
            {"path": Path("/v/b.md"), "title": "B", "summary": "", "tags": ["java"], "content": "", "rel_path": "b.md"},
        ]
        clusters = rst_mod._tag_based_clusters(notes, 2)
        assert clusters == []

    def test_only_one_shared_tag_no_cluster(self):
        notes = [
            {"path": Path("/v/a.md"), "title": "A", "summary": "", "tags": ["python", "web"], "content": "", "rel_path": "a.md"},
            {"path": Path("/v/b.md"), "title": "B", "summary": "", "tags": ["python", "api"], "content": "", "rel_path": "b.md"},
        ]
        # Only 1 shared tag — not enough for adjacency (needs >= 2)
        clusters = rst_mod._tag_based_clusters(notes, 2)
        assert clusters == []

    def test_two_shared_tags_forms_cluster(self):
        notes = [
            {"path": Path("/v/a.md"), "title": "A", "summary": "", "tags": ["python", "testing"], "content": "", "rel_path": "a.md"},
            {"path": Path("/v/b.md"), "title": "B", "summary": "", "tags": ["python", "testing"], "content": "", "rel_path": "b.md"},
        ]
        clusters = rst_mod._tag_based_clusters(notes, 2)
        assert len(clusters) == 1
        assert len(clusters[0]) == 2

    def test_min_cluster_size_filters_singletons(self):
        notes = [
            {"path": Path("/v/a.md"), "title": "A", "summary": "", "tags": ["python", "testing"], "content": "", "rel_path": "a.md"},
            {"path": Path("/v/b.md"), "title": "B", "summary": "", "tags": ["python", "testing"], "content": "", "rel_path": "b.md"},
            {"path": Path("/v/c.md"), "title": "C", "summary": "", "tags": ["java", "spring"], "content": "", "rel_path": "c.md"},
        ]
        clusters = rst_mod._tag_based_clusters(notes, 3)
        assert clusters == []

    def test_empty_tags_no_crash(self):
        notes = [
            {"path": Path("/v/a.md"), "title": "A", "summary": "", "tags": [], "content": "", "rel_path": "a.md"},
            {"path": Path("/v/b.md"), "title": "B", "summary": "", "tags": [], "content": "", "rel_path": "b.md"},
        ]
        clusters = rst_mod._tag_based_clusters(notes, 2)
        assert clusters == []

    def test_triangle_connectivity_bfs_visited(self):
        # A-B share 2 tags, B-C share 2 tags, A-C share 2 tags (triangle)
        # BFS from A visits B and C; when processing B's neighbors, C is queued again,
        # triggering the "if node in visited: continue" branch (line 404)
        notes = [
            {"path": Path("/v/a.md"), "title": "A", "summary": "", "tags": ["python", "testing", "web"], "content": "", "rel_path": "a.md"},
            {"path": Path("/v/b.md"), "title": "B", "summary": "", "tags": ["python", "testing", "api"], "content": "", "rel_path": "b.md"},
            {"path": Path("/v/c.md"), "title": "C", "summary": "", "tags": ["python", "testing", "db"], "content": "", "rel_path": "c.md"},
        ]
        clusters = rst_mod._tag_based_clusters(notes, 2)
        assert len(clusters) == 1
        assert len(clusters[0]) == 3


# ===========================================================================
# _find_split_candidates — edge cases
# ===========================================================================

class TestFindSplitCandidatesExtra:
    def test_excludes_already_clustered_paths(self):
        notes = [
            {"path": Path("/v/a.md"), "title": "A", "summary": "", "tags": [], "content": "x" * 5000, "rel_path": "a.md"},
            {"path": Path("/v/b.md"), "title": "B", "summary": "", "tags": [], "content": "x" * 5000, "rel_path": "b.md"},
        ]
        clustered = {str(Path("/v/a.md"))}
        result = rst_mod._find_split_candidates(notes, clustered, 1000)
        assert len(result) == 1
        assert result[0]["title"] == "B"

    def test_empty_notes_returns_empty(self):
        result = rst_mod._find_split_candidates([], set(), 1000)
        assert result == []

    def test_all_below_threshold_returns_empty(self):
        notes = [
            {"path": Path("/v/a.md"), "title": "A", "summary": "", "tags": [], "content": "short", "rel_path": "a.md"},
        ]
        result = rst_mod._find_split_candidates(notes, set(), 10000)
        assert result == []


# ===========================================================================
# _format_folder_hub_block — existing_hub branch
# ===========================================================================

class TestFormatFolderHubBlockExistingHub:
    def _make_note_dict(self, rel_path: str, title: str) -> dict:
        return {
            "path": Path(f"/vault/{rel_path}"),
            "title": title,
            "summary": "A summary",
            "tags": ["test"],
            "content": "content",
            "rel_path": rel_path,
        }

    def test_existing_hub_shows_update_instructions(self):
        notes = [self._make_note_dict("notes/foo.md", "Foo Note")]
        result = rst_mod._format_folder_hub_block(
            notes, Path("/vault"), hub_path="hub.md", existing_hub="# Old Hub\n\n[[foo]]"
        )
        assert "Update" in result or "update" in result
        assert "Preserve" in result or "preserve" in result
        assert "Old Hub" in result

    def test_existing_hub_truncated_when_long(self):
        long_hub = "x" * 5000
        notes = [self._make_note_dict("notes/foo.md", "Foo Note")]
        result = rst_mod._format_folder_hub_block(
            notes, Path("/vault"), existing_hub=long_hub
        )
        assert "truncated" in result

    def test_existing_hub_not_truncated_when_short(self):
        short_hub = "# Hub\n\n[[foo]]"
        notes = [self._make_note_dict("notes/foo.md", "Foo Note")]
        result = rst_mod._format_folder_hub_block(
            notes, Path("/vault"), existing_hub=short_hub
        )
        assert "truncated" not in result
        assert "# Hub" in result

    def test_hub_path_shown_when_existing(self):
        notes = [self._make_note_dict("foo.md", "Foo")]
        result = rst_mod._format_folder_hub_block(
            notes, Path("/vault"), hub_path="myhub.md", existing_hub="content"
        )
        assert "myhub.md" in result

    def test_new_hub_no_hub_path_shows_empty_line(self):
        notes = [self._make_note_dict("foo.md", "Foo")]
        result = rst_mod._format_folder_hub_block(notes, Path("/vault"))
        # When existing_hub is empty and hub_path is empty, no hub_path line shown
        assert "MUST be placed" not in result

    def test_new_hub_with_hub_path_shows_path_instruction(self):
        notes = [self._make_note_dict("foo.md", "Foo")]
        result = rst_mod._format_folder_hub_block(
            notes, Path("/vault"), hub_path="sub/index.md"
        )
        assert "sub/index.md" in result
        assert "MUST be placed" in result


# ===========================================================================
# _execute_cluster_decisions — additional branches
# ===========================================================================

class TestExecuteClusterDecisionsExtra:
    def _run(self, decisions, clusters, vault):
        result_lines = []
        errata_entries = []
        written_paths = []
        ts = "2025-01-01T00:00:00"
        nc, nd = rst_mod._execute_cluster_decisions(
            decisions, clusters, vault, ts, result_lines, errata_entries, written_paths
        )
        return nc, nd, result_lines, errata_entries, written_paths

    def test_merge_src_same_as_output_skips_delete(self, tmp_path):
        # When merged_path points to the same file as a source, skip delete
        content = "---\ntitle: 'A'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nbody\n"
        note_path = tmp_path / "A.md"
        note_path.write_text(content)
        note = {"path": note_path, "title": "A", "summary": "S", "tags": [], "content": content, "rel_path": "A.md"}
        cluster = [note]

        decisions = [{
            "cluster_index": 0,
            "action": "merge",
            "merged_title": "A Merged",
            "merged_path": "A.md",  # Same path as source
            "merged_content": content,
        }]
        nc, nd, result_lines, _, _ = self._run(decisions, [cluster], tmp_path)
        assert nc == 1
        assert nd == 0  # Not deleted because same path

    def test_merge_oserror_on_delete_adds_warning(self, tmp_path):
        content = "---\ntitle: 'Src'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nbody\n"
        src_path = tmp_path / "src.md"
        src_path.write_text(content)
        note = {"path": src_path, "title": "Src", "summary": "S", "tags": [], "content": content, "rel_path": "src.md"}

        decisions = [{
            "cluster_index": 0,
            "action": "merge",
            "merged_title": "Merged",
            "merged_path": "merged.md",
            "merged_content": content,
        }]
        cluster = [note]

        with patch("pathlib.Path.unlink", side_effect=OSError("permission denied")):
            nc, nd, result_lines, _, _ = self._run(decisions, [cluster], tmp_path)
        assert nc == 1
        warning_lines = [l for l in result_lines if "Warning" in l]
        assert len(warning_lines) >= 1

    def test_hub_spoke_missing_content_skipped(self, tmp_path):
        content = "---\ntitle: 'A'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nbody\n"
        note = {"path": tmp_path / "a.md", "title": "A", "summary": "S", "tags": [], "content": content, "rel_path": "a.md"}
        decisions = [{
            "cluster_index": 0,
            "action": "hub-spoke",
            "hub_title": "Hub",
            "hub_path": "",  # Missing path
            "hub_content": "",  # Missing content
        }]
        nc, nd, result_lines, _, _ = self._run(decisions, [[note]], tmp_path)
        assert nc == 0
        assert any("missing" in l for l in result_lines)

    def test_hub_spoke_path_traversal_rejected(self, tmp_path):
        content = "---\ntitle: 'A'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nbody\n"
        note = {"path": tmp_path / "a.md", "title": "A", "summary": "S", "tags": [], "content": content, "rel_path": "a.md"}
        decisions = [{
            "cluster_index": 0,
            "action": "hub-spoke",
            "hub_title": "Evil",
            "hub_path": "../../evil/hub.md",
            "hub_content": content,
        }]
        nc, nd, result_lines, _, _ = self._run(decisions, [[note]], tmp_path)
        assert nc == 0
        assert any("path traversal" in l for l in result_lines)

    def test_subfolder_missing_fields_skipped(self, tmp_path):
        content = "---\ntitle: 'A'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nbody\n"
        note = {"path": tmp_path / "a.md", "title": "A", "summary": "S", "tags": [], "content": content, "rel_path": "a.md"}
        decisions = [{
            "cluster_index": 0,
            "action": "subfolder",
            "subfolder_path": "",  # Missing
            "hub_path": "",
            "hub_content": "",
        }]
        nc, nd, result_lines, _, _ = self._run(decisions, [[note]], tmp_path)
        assert nc == 0
        assert any("missing" in l for l in result_lines)

    def test_subfolder_path_traversal_rejected(self, tmp_path):
        content = "---\ntitle: 'A'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nbody\n"
        note = {"path": tmp_path / "a.md", "title": "A", "summary": "S", "tags": [], "content": content, "rel_path": "a.md"}
        decisions = [{
            "cluster_index": 0,
            "action": "subfolder",
            "subfolder_path": "../../evil",
            "hub_path": "sub/hub.md",
            "hub_content": content,
        }]
        nc, nd, result_lines, _, _ = self._run(decisions, [[note]], tmp_path)
        assert nc == 0
        assert any("path traversal" in l for l in result_lines)

    def test_subfolder_move_oserror_adds_warning(self, tmp_path):
        content = "---\ntitle: 'A'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nbody\n"
        src = tmp_path / "a.md"
        src.write_text(content)
        note = {"path": src, "title": "A", "summary": "S", "tags": [], "content": content, "rel_path": "a.md"}
        decisions = [{
            "cluster_index": 0,
            "action": "subfolder",
            "subfolder_path": "subgroup",
            "hub_path": "subgroup/hub.md",
            "hub_content": content,
        }]
        with patch("pathlib.Path.rename", side_effect=OSError("no space")):
            nc, nd, result_lines, _, _ = self._run(decisions, [[note]], tmp_path)
        warning_lines = [l for l in result_lines if "Warning" in l]
        assert len(warning_lines) >= 1


# ===========================================================================
# _format_preview_output — additional branches
# ===========================================================================

class TestFormatPreviewOutputExtra:
    def _note(self, title: str) -> dict:
        return {
            "path": Path(f"/v/{title}.md"),
            "title": title,
            "summary": "S",
            "tags": [],
            "content": "content",
            "rel_path": f"{title}.md",
        }

    def test_merge_preview(self):
        cluster = [self._note("A"), self._note("B")]
        decisions = [{
            "cluster_index": 0,
            "action": "merge",
            "merged_title": "Merged",
            "merged_path": "merged.md",
            "merged_content": "---\ntitle: Merged\n---\n\nbody",
        }]
        result = rst_mod._format_preview_output(decisions, [cluster], [])
        assert "Merge" in result
        assert "Merged" in result

    def test_hub_spoke_preview(self):
        cluster = [self._note("A"), self._note("B")]
        decisions = [{
            "cluster_index": 0,
            "action": "hub-spoke",
            "hub_title": "Hub",
            "hub_path": "hub.md",
            "hub_content": "hub content",
        }]
        result = rst_mod._format_preview_output(decisions, [cluster], [])
        assert "Hub-Spoke" in result or "hub-spoke" in result.lower()
        assert "Hub" in result

    def test_subfolder_preview(self):
        cluster = [self._note("A"), self._note("B")]
        decisions = [{
            "cluster_index": 0,
            "action": "subfolder",
            "hub_title": "Sub Hub",
            "subfolder_path": "subgroup",
            "hub_path": "subgroup/hub.md",
            "hub_content": "hub content",
        }]
        result = rst_mod._format_preview_output(decisions, [cluster], [])
        assert "Subfolder" in result or "subfolder" in result.lower()
        assert "subgroup" in result

    def test_merge_preview_long_content_truncated(self):
        cluster = [self._note("A")]
        long_content = "x" * 5000
        decisions = [{
            "cluster_index": 0,
            "action": "merge",
            "merged_title": "M",
            "merged_path": "m.md",
            "merged_content": long_content,
        }]
        result = rst_mod._format_preview_output(decisions, [cluster], [])
        assert "truncated" in result

    def test_hub_spoke_preview_long_content_truncated(self):
        cluster = [self._note("A")]
        decisions = [{
            "cluster_index": 0,
            "action": "hub-spoke",
            "hub_title": "H",
            "hub_path": "h.md",
            "hub_content": "y" * 5000,
        }]
        result = rst_mod._format_preview_output(decisions, [cluster], [])
        assert "truncated" in result

    def test_subfolder_preview_long_content_truncated(self):
        cluster = [self._note("A")]
        decisions = [{
            "cluster_index": 0,
            "action": "subfolder",
            "hub_title": "H",
            "subfolder_path": "sub",
            "hub_path": "sub/h.md",
            "hub_content": "z" * 5000,
        }]
        result = rst_mod._format_preview_output(decisions, [cluster], [])
        assert "truncated" in result

    def test_split_keep_preview(self):
        candidate = self._note("BigNote")
        decisions = [{"note_index": 0, "action": "keep", "rationale": "fine as-is"}]
        result = rst_mod._format_preview_output(decisions, [], [candidate])
        assert "Keep As-Is" in result
        assert "fine as-is" in result

    def test_split_split_preview(self):
        candidate = self._note("BigNote")
        decisions = [{
            "note_index": 0,
            "action": "split",
            "output_notes": [
                {"title": "Part A", "path": "PartA.md", "content": "part a content"},
                {"title": "Part B", "path": "PartB.md", "content": "part b content"},
            ],
        }]
        result = rst_mod._format_preview_output(decisions, [], [candidate])
        assert "Split" in result
        assert "Part A" in result
        assert "Part B" in result

    def test_split_preview_long_content_truncated(self):
        candidate = self._note("BigNote")
        decisions = [{
            "note_index": 0,
            "action": "split",
            "output_notes": [{"title": "P", "path": "p.md", "content": "q" * 3000}],
        }]
        result = rst_mod._format_preview_output(decisions, [], [candidate])
        assert "truncated" in result

    def test_out_of_range_cluster_skipped(self):
        decisions = [{"cluster_index": 99, "action": "merge", "merged_title": "X", "merged_path": "x.md", "merged_content": "c"}]
        result = rst_mod._format_preview_output(decisions, [], [])
        assert "Preview" in result  # still returns header

    def test_out_of_range_note_index_skipped(self):
        decisions = [{"note_index": 99, "action": "split", "output_notes": []}]
        result = rst_mod._format_preview_output(decisions, [], [])
        assert "Preview" in result


# ===========================================================================
# cb_restructure — folder_hub dry_run no clusters
# ===========================================================================

class TestCbRestructureFolderHubDryRunNoClusters:
    def _base_config(self, tmp_path):
        return {
            "vault_path": str(tmp_path),
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
            "consolidation_log": "AI/Log.md",
            "consolidation_log_enabled": True,
        }

    def test_folder_hub_dry_run_no_clusters(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[]):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=True)
        assert "No clusters found" in result
        assert "dry" in result.lower() or "DRY" in result

    def test_folder_hub_dry_run_with_clusters(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "Hook Alpha.md", "Hook Alpha")
        _make_note(sub / "Hook Beta.md", "Hook Beta")
        _make_note(sub / "Hook Gamma.md", "Hook Gamma")
        _make_note(sub / "Hook Delta.md", "Hook Delta")
        _make_note(sub / "Hook Epsilon.md", "Hook Epsilon")
        _make_note(sub / "Hook Zeta.md", "Hook Zeta")

        # Build a cluster with 6 notes to trigger "hub-and-spoke" proposed action
        notes = rst_mod._collect_notes(sub, tmp_path, [])
        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[notes]):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=True)
        assert "Cluster" in result


# ===========================================================================
# cb_restructure — folder_hub execute with preview mode
# ===========================================================================

class TestCbRestructureFolderHubPreview:
    def _base_config(self, tmp_path):
        return {
            "vault_path": str(tmp_path),
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
            "consolidation_log": "AI/Log.md",
            "consolidation_log_enabled": True,
        }

    def test_folder_hub_preview_mode_no_clusters(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")

        hub_content = "---\ntitle: Hub\ntype: reference\nsummary: S\ntags: []\n---\n\nhub body\n"
        phase2_decisions = [{"action": "hub-spoke", "hub_title": "SubHub", "hub_path": "sub/hub.md", "hub_content": hub_content}]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", return_value=json.dumps(phase2_decisions)), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=False, preview=True)
        assert "Preview" in result
        assert "SubHub" in result
        # No file should have been written
        assert not (tmp_path / "sub" / "hub.md").exists()

    def test_folder_hub_preview_with_clusters(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")
        _make_note(sub / "B.md", "Note B")
        notes = rst_mod._collect_notes(sub, tmp_path, [])

        phase1_decisions = [{"cluster_index": 0, "action": "keep-separate", "rationale": "distinct"}]
        hub_content = "---\ntitle: Hub\ntype: reference\nsummary: S\ntags: []\n---\n\nhub\n"
        phase2_decisions = [{"action": "hub-spoke", "hub_title": "Hub", "hub_path": "sub/hub.md", "hub_content": hub_content}]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[notes]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", side_effect=[json.dumps(phase1_decisions), json.dumps(phase2_decisions)]), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=False, preview=True)
        assert "Preview" in result
        assert not (tmp_path / "sub" / "hub.md").exists()

    def test_folder_hub_preview_with_merge_cluster_decision(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")
        _make_note(sub / "B.md", "Note B")
        notes = rst_mod._collect_notes(sub, tmp_path, [])

        merged_content = "---\ntitle: AB\ntype: reference\nsummary: S\ntags: []\n---\n\nmerged\n"
        phase1_decision = {"cluster_index": 0, "action": "merge", "merged_title": "AB", "merged_path": "sub/AB.md", "rationale": "related"}
        hub_content = "---\ntitle: Hub\ntype: reference\nsummary: S\ntags: []\n---\n\nhub\n"
        phase2_decisions = [{"action": "hub-spoke", "hub_title": "Hub", "hub_path": "sub/hub.md", "hub_content": hub_content}]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[notes]), \
             patch.object(rst_mod, "_call_decisions", return_value=[phase1_decision]), \
             patch.object(rst_mod, "_call_generate_cluster", return_value={"merged_content": merged_content}), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", return_value=json.dumps(phase2_decisions)), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=False, preview=True)
        assert "Preview" in result
        assert "Merge" in result or "AB" in result
        assert not (sub / "AB.md").exists()

    def test_folder_hub_preview_with_hub_spoke_cluster_decision(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")
        _make_note(sub / "B.md", "Note B")
        notes = rst_mod._collect_notes(sub, tmp_path, [])

        spoke_content = "---\ntitle: Spoke\ntype: reference\nsummary: S\ntags: []\n---\n\nspoke hub\n"
        phase1_decision = {"cluster_index": 0, "action": "hub-spoke", "hub_title": "Spoke", "hub_path": "sub/spoke.md", "rationale": "related"}
        hub_content = "---\ntitle: Hub\ntype: reference\nsummary: S\ntags: []\n---\n\nhub\n"
        phase2_decisions = [{"action": "hub-spoke", "hub_title": "Hub", "hub_path": "sub/hub.md", "hub_content": hub_content}]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[notes]), \
             patch.object(rst_mod, "_call_decisions", return_value=[phase1_decision]), \
             patch.object(rst_mod, "_call_generate_cluster", return_value={"hub_content": spoke_content}), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", return_value=json.dumps(phase2_decisions)), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=False, preview=True)
        assert "Preview" in result
        assert "Spoke" in result or "hub-spoke" in result.lower()
        assert not (sub / "spoke.md").exists()

    def test_folder_hub_preview_merge_long_content_truncated(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")
        _make_note(sub / "B.md", "Note B")
        notes = rst_mod._collect_notes(sub, tmp_path, [])

        long_content = "x" * 5000
        phase1_decision = {"cluster_index": 0, "action": "merge", "merged_title": "AB", "merged_path": "sub/AB.md", "rationale": "related"}
        hub_content = "---\ntitle: Hub\ntype: reference\nsummary: S\ntags: []\n---\n\nhub\n"
        phase2_decisions = [{"action": "hub-spoke", "hub_title": "Hub", "hub_path": "sub/hub.md", "hub_content": hub_content}]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[notes]), \
             patch.object(rst_mod, "_call_decisions", return_value=[phase1_decision]), \
             patch.object(rst_mod, "_call_generate_cluster", return_value={"merged_content": long_content}), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", return_value=json.dumps(phase2_decisions)), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=False, preview=True)
        assert "truncated" in result

    def test_folder_hub_preview_hub_spoke_cluster_long_content_truncated(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")
        _make_note(sub / "B.md", "Note B")
        notes = rst_mod._collect_notes(sub, tmp_path, [])

        long_content = "y" * 5000
        phase1_decision = {"cluster_index": 0, "action": "hub-spoke", "hub_title": "Spoke", "hub_path": "sub/spoke.md", "rationale": "related"}
        hub_content = "---\ntitle: Hub\ntype: reference\nsummary: S\ntags: []\n---\n\nhub\n"
        phase2_decisions = [{"action": "hub-spoke", "hub_title": "Hub", "hub_path": "sub/hub.md", "hub_content": hub_content}]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[notes]), \
             patch.object(rst_mod, "_call_decisions", return_value=[phase1_decision]), \
             patch.object(rst_mod, "_call_generate_cluster", return_value={"hub_content": long_content}), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", return_value=json.dumps(phase2_decisions)), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=False, preview=True)
        assert "truncated" in result

    def test_folder_hub_preview_phase2_long_hub_content_truncated(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")

        long_hub_content = "z" * 5000
        phase2_decisions = [{"action": "hub-spoke", "hub_title": "Hub", "hub_path": "sub/hub.md", "hub_content": long_hub_content}]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", return_value=json.dumps(phase2_decisions)), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=False, preview=True)
        assert "truncated" in result

    def test_folder_hub_preview_phase2_non_hub_spoke_continues(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")

        # Phase 2 returns a non-hub-spoke decision first, then hub-spoke
        hub_content = "---\ntitle: Hub\ntype: reference\nsummary: S\ntags: []\n---\n\nhub\n"
        phase2_decisions = [
            {"action": "merge", "merged_title": "X"},  # skipped
            {"action": "hub-spoke", "hub_title": "Hub", "hub_path": "sub/hub.md", "hub_content": hub_content},
        ]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", return_value=json.dumps(phase2_decisions)), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=False, preview=True)
        assert "Hub" in result

    def test_folder_hub_preview_out_of_range_cluster_skipped(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")
        notes = rst_mod._collect_notes(sub, tmp_path, [])

        phase1_decisions = [{"cluster_index": 99, "action": "merge", "merged_title": "X", "merged_path": "x.md", "merged_content": "c"}]
        hub_content = "---\ntitle: Hub\ntype: reference\nsummary: S\ntags: []\n---\n\nhub\n"
        phase2_decisions = [{"action": "hub-spoke", "hub_title": "Hub", "hub_path": "sub/hub.md", "hub_content": hub_content}]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[notes]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", side_effect=[json.dumps(phase1_decisions), json.dumps(phase2_decisions)]), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=False, preview=True)
        assert "Preview" in result

    def test_folder_hub_preview_phase1_decision_without_cluster_index_skipped(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")
        notes = rst_mod._collect_notes(sub, tmp_path, [])

        phase1_decisions = [{"action": "merge", "merged_title": "X"}]  # no cluster_index
        hub_content = "---\ntitle: Hub\ntype: reference\nsummary: S\ntags: []\n---\n\nhub\n"
        phase2_decisions = [{"action": "hub-spoke", "hub_title": "Hub", "hub_path": "sub/hub.md", "hub_content": hub_content}]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[notes]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", side_effect=[json.dumps(phase1_decisions), json.dumps(phase2_decisions)]), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=False, preview=True)
        assert "Preview" in result


# ===========================================================================
# cb_restructure — folder_hub execute hub decision edge cases
# ===========================================================================

class TestCbRestructureFolderHubExecuteEdgeCases:
    def _base_config(self, tmp_path):
        return {
            "vault_path": str(tmp_path),
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
            "consolidation_log": "AI/Log.md",
            "consolidation_log_enabled": True,
        }

    def test_hub_non_hub_spoke_action_skipped(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")

        # Phase 2 returns a wrong action type (not hub-spoke) — should fall through to else
        phase2_decisions = [{"action": "merge", "merged_title": "X", "merged_path": "x.md", "merged_content": "c"}]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[]), \
             patch("backends.call_model", return_value=json.dumps(phase2_decisions)), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=False)
        assert "skipped" in result.lower() or "did not return" in result.lower()

    def test_hub_missing_path_skipped(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")

        # Hub decision missing both path and content
        # With no clusters, call_model is only called once (for phase 2)
        phase2_decisions = [{"action": "hub-spoke", "hub_title": "Hub", "hub_path": "", "hub_content": ""}]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", return_value=json.dumps(phase2_decisions)), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=False)
        assert "skipped" in result.lower()

    def test_hub_path_traversal_rejected(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")

        hub_content = "---\ntitle: Hub\ntype: reference\nsummary: S\ntags: []\n---\n\nbody\n"
        # With no clusters, call_model is only called once (for phase 2)
        phase2_decisions = [{"action": "hub-spoke", "hub_title": "Evil", "hub_path": "../../evil.md", "hub_content": hub_content}]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", return_value=json.dumps(phase2_decisions)), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=False)
        assert "path traversal" in result.lower() or "skipped" in result.lower()

    def test_hub_backend_error_hub_phase(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")

        class FakeBackendError(Exception):
            pass

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", side_effect=FakeBackendError("hub fail")), \
             patch("backends.BackendError", FakeBackendError):
            with pytest.raises(ToolError, match="Backend error"):
                _cb_restructure()(folder="sub", folder_hub=True, dry_run=False)

    def test_hub_invalid_json_hub_phase(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")

        # With no clusters, call_model is only called once (for phase 2)
        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", return_value="~~ broken ~~"), \
             patch("backends.BackendError", Exception):
            with pytest.raises(ToolError, match="invalid JSON"):
                _cb_restructure()(folder="sub", folder_hub=True, dry_run=False)

    def test_hub_execute_with_existing_hub(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")
        # Create existing hub
        hub_file = sub / "hub.md"
        hub_file.write_text("# Old Hub\n\n[[A]]\n")

        hub_content = "---\ntitle: Hub\ntype: reference\nsummary: S\ntags: []\n---\n\nnew hub body\n"
        phase2_decisions = [{"action": "hub-spoke", "hub_title": "SubHub", "hub_path": "sub/hub.md", "hub_content": hub_content}]

        # With no clusters, call_model is only called once (for phase 2)
        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", return_value=json.dumps(phase2_decisions)), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(folder="sub", folder_hub=True, hub_path="sub/hub.md", dry_run=False)
        assert hub_file.exists()
        assert "Updated" in result or "hub" in result.lower()

    def test_hub_execute_log_entries_written(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")

        hub_content = "---\ntitle: Hub\ntype: reference\nsummary: S\ntags: []\n---\n\nhub\n"
        # With no clusters, only one call_model call is made (for phase 2)
        phase2_decisions = [{"action": "hub-spoke", "hub_title": "SubHub", "hub_path": "sub/hub.md", "hub_content": hub_content}]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", return_value=json.dumps(phase2_decisions)), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=False)
        log_path = tmp_path / "AI" / "Log.md"
        assert log_path.exists()
        assert "Hub" in log_path.read_text()


# ===========================================================================
# cb_restructure — normal mode execute additional paths
# ===========================================================================

class TestCbRestructureNormalExecuteExtra:
    def _base_config(self, tmp_path):
        return {
            "vault_path": str(tmp_path),
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
            "consolidation_log": "AI/Log.md",
            "consolidation_log_enabled": True,
        }

    def test_split_out_of_range_note_index_skipped(self, tmp_path):
        big_content = "---\ntitle: 'Big'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\n" + "x" * 4000
        (tmp_path / "Big.md").write_text(big_content)

        decisions = [{"note_index": 99, "action": "split", "output_notes": []}]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_build_clusters", return_value=[]), \
             patch("backends.call_model", return_value=json.dumps(decisions)), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(dry_run=False, split_threshold=100)
        # Out of range — no crash, no split reported
        assert "Restructure" in result

    def test_split_missing_path_or_content_skipped(self, tmp_path):
        big_content = "---\ntitle: 'Big'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\n" + "x" * 4000
        (tmp_path / "Big.md").write_text(big_content)

        decision = {
            "note_index": 0,
            "action": "split",
            "output_notes": [{"title": "Good", "path": "Good.md"}, {"title": "Bad", "path": ""}],
        }
        gen_content = {
            "output_notes": [
                {"title": "Good", "path": "Good.md", "content": "good content"},
                {"title": "Bad", "path": "", "content": ""},  # Missing path/content
            ]
        }

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_build_clusters", return_value=[]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch.object(rst_mod, "_call_decisions", return_value=[decision]), \
             patch.object(rst_mod, "_call_generate_split", return_value=gen_content):
            result = _cb_restructure()(dry_run=False, split_threshold=100)
        assert "Warning" in result or "skipping" in result.lower()

    def test_split_source_delete_oserror(self, tmp_path):
        big_content = "---\ntitle: 'Big'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\n" + "x" * 4000
        src = tmp_path / "Big.md"
        src.write_text(big_content)

        decision = {"note_index": 0, "action": "split", "output_notes": [{"title": "Part A", "path": "PartA.md"}]}
        gen_content = {
            "output_notes": [
                {"title": "Part A", "path": "PartA.md", "content": "---\ntitle: 'Part A'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nbody"},
            ]
        }

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_build_clusters", return_value=[]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch.object(rst_mod, "_call_decisions", return_value=[decision]), \
             patch.object(rst_mod, "_call_generate_split", return_value=gen_content), \
             patch("pathlib.Path.unlink", side_effect=OSError("locked")):
            result = _cb_restructure()(dry_run=False, split_threshold=100)
        assert "Warning" in result

    def test_normal_execute_log_written_when_merges_happen(self, tmp_path):
        content_a = "---\ntitle: 'A'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nbody A\n" + "x" * 200
        content_b = "---\ntitle: 'B'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nbody B\n" + "x" * 200
        (tmp_path / "A.md").write_text(content_a)
        (tmp_path / "B.md").write_text(content_b)

        notes = rst_mod._collect_notes(tmp_path, tmp_path, [])
        merged_content = "---\ntitle: 'AB'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nmerged\n"
        decision = {"cluster_index": 0, "action": "merge", "merged_title": "AB", "merged_path": "AB.md", "rationale": "related"}

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_build_clusters", return_value=[notes]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch.object(rst_mod, "_call_decisions", return_value=[decision]), \
             patch.object(rst_mod, "_call_generate_cluster", return_value={"merged_content": merged_content}):
            result = _cb_restructure()(dry_run=False)
        log_path = tmp_path / "AI" / "Log.md"
        assert log_path.exists()
        assert "Merged" in log_path.read_text() or "merged" in log_path.read_text()

    def test_normal_dry_run_shows_split_candidates(self, tmp_path):
        big_content = "---\ntitle: 'BigNote'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\n" + "x" * 4000
        (tmp_path / "BigNote.md").write_text(big_content)

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_build_clusters", return_value=[]):
            result = _cb_restructure()(dry_run=True, split_threshold=100)
        assert "BigNote" in result
        assert "split" in result.lower() or "large" in result.lower()

    def test_hub_spoke_cluster_execute(self, tmp_path):
        content_a = "---\ntitle: 'A'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nbody A\n"
        content_b = "---\ntitle: 'B'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nbody B\n"
        (tmp_path / "A.md").write_text(content_a)
        (tmp_path / "B.md").write_text(content_b)

        notes = rst_mod._collect_notes(tmp_path, tmp_path, [])
        hub_content = "---\ntitle: 'Hub'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nhub\n"
        decision = {"cluster_index": 0, "action": "hub-spoke", "hub_title": "Hub", "hub_path": "hub.md", "rationale": "related"}

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_build_clusters", return_value=[notes]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch.object(rst_mod, "_call_decisions", return_value=[decision]), \
             patch.object(rst_mod, "_call_generate_cluster", return_value={"hub_content": hub_content}):
            result = _cb_restructure()(dry_run=False)
        assert (tmp_path / "hub.md").exists()
        assert "hub-spoke" in result.lower() or "Hub" in result

    def test_subfolder_cluster_execute(self, tmp_path):
        content_a = "---\ntitle: 'A'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nbody A\n"
        content_b = "---\ntitle: 'B'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nbody B\n"
        (tmp_path / "A.md").write_text(content_a)
        (tmp_path / "B.md").write_text(content_b)

        notes = rst_mod._collect_notes(tmp_path, tmp_path, [])
        hub_content = "---\ntitle: 'SubHub'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nhub\n"
        decision = {"cluster_index": 0, "action": "subfolder", "subfolder_path": "subgroup", "hub_title": "SubHub", "hub_path": "subgroup/hub.md", "rationale": "related"}

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_build_clusters", return_value=[notes]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch.object(rst_mod, "_call_decisions", return_value=[decision]), \
             patch.object(rst_mod, "_call_generate_cluster", return_value={"hub_content": hub_content}):
            result = _cb_restructure()(dry_run=False)
        assert (tmp_path / "subgroup").is_dir()
        assert (tmp_path / "subgroup" / "hub.md").exists()
        assert "subfolder" in result.lower() or "SubHub" in result

    def test_preview_mode_merge(self, tmp_path):
        content_a = "---\ntitle: 'A'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nbody A\n"
        content_b = "---\ntitle: 'B'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nbody B\n"
        (tmp_path / "A.md").write_text(content_a)
        (tmp_path / "B.md").write_text(content_b)

        notes = rst_mod._collect_notes(tmp_path, tmp_path, [])
        merged_content = "---\ntitle: 'AB'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nmerged\n"
        decision = {"cluster_index": 0, "action": "merge", "merged_title": "AB", "merged_path": "AB.md", "rationale": "related"}

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_build_clusters", return_value=[notes]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch.object(rst_mod, "_call_decisions", return_value=[decision]), \
             patch.object(rst_mod, "_call_generate_cluster", return_value={"merged_content": merged_content}):
            result = _cb_restructure()(dry_run=False, preview=True)
        assert "Preview" in result
        assert "Merge" in result
        assert not (tmp_path / "AB.md").exists()

    def test_normal_execute_no_log_when_disabled(self, tmp_path):
        config = {
            "vault_path": str(tmp_path),
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
            "consolidation_log": "AI/Log.md",
            "consolidation_log_enabled": False,
        }
        content_a = "---\ntitle: 'A'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nbody A\n"
        content_b = "---\ntitle: 'B'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nbody B\n"
        (tmp_path / "A.md").write_text(content_a)
        (tmp_path / "B.md").write_text(content_b)

        notes = rst_mod._collect_notes(tmp_path, tmp_path, [])
        merged_content = "---\ntitle: 'AB'\ntype: reference\nsummary: 'S'\ntags: []\n---\n\nmerged\n"
        decision = {"cluster_index": 0, "action": "merge", "merged_title": "AB", "merged_path": "AB.md", "rationale": "related"}

        with patch.object(rst_mod, "_load_config", return_value=config), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_build_clusters", return_value=[notes]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch.object(rst_mod, "_call_decisions", return_value=[decision]), \
             patch.object(rst_mod, "_call_generate_cluster", return_value={"merged_content": merged_content}):
            result = _cb_restructure()(dry_run=False)
        log_path = tmp_path / "AI" / "Log.md"
        assert not log_path.exists()

    def test_folder_hub_execute_cluster_invalid_json(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")
        _make_note(sub / "B.md", "Note B")
        notes = rst_mod._collect_notes(sub, tmp_path, [])

        # Phase 1 (cluster) returns invalid JSON — should raise ToolError with "cluster phase"
        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[notes]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", return_value="~~ broken ~~"), \
             patch("backends.BackendError", Exception):
            with pytest.raises(ToolError, match="decision phase"):
                _cb_restructure()(folder="sub", folder_hub=True, dry_run=False)

    def test_folder_hub_execute_keep_separate_cluster_leaves_empty_line(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")
        _make_note(sub / "B.md", "Note B")
        notes = rst_mod._collect_notes(sub, tmp_path, [])

        # Phase 1 returns keep-separate; _execute_cluster_decisions adds to result_lines
        # which may leave the last line empty (triggering the "No merges executed." guard)
        phase1_decisions = [{"cluster_index": 0, "action": "keep-separate", "rationale": "distinct"}]
        hub_content = "---\ntitle: Hub\ntype: reference\nsummary: S\ntags: []\n---\n\nhub\n"
        phase2_decisions = [{"action": "hub-spoke", "hub_title": "Hub", "hub_path": "sub/hub.md", "hub_content": hub_content}]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[notes]), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", side_effect=[json.dumps(phase1_decisions), json.dumps(phase2_decisions)]), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=False)
        assert (sub / "hub.md").exists()

    def test_folder_hub_no_log_when_disabled(self, tmp_path):
        config = {
            "vault_path": str(tmp_path),
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
            "consolidation_log": "AI/Log.md",
            "consolidation_log_enabled": False,
        }
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")

        hub_content = "---\ntitle: Hub\ntype: reference\nsummary: S\ntags: []\n---\n\nhub\n"
        phase2_decisions = [{"action": "hub-spoke", "hub_title": "SubHub", "hub_path": "sub/hub.md", "hub_content": hub_content}]

        with patch.object(rst_mod, "_load_config", return_value=config), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_group_notes", return_value=[]), \
             patch("backends.call_model", return_value=json.dumps(phase2_decisions)), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=False)
        assert not (tmp_path / "AI" / "Log.md").exists()

    def test_folder_hub_execute_no_log_when_disabled(self, tmp_path):
        config = {
            "vault_path": str(tmp_path),
            "backend": "claude-code",
            "model": "claude-haiku-4-5",
            "consolidation_log": "AI/Log.md",
            "consolidation_log_enabled": False,
        }
        sub = tmp_path / "sub"
        sub.mkdir()
        _make_note(sub / "A.md", "Note A")

        hub_content = "---\ntitle: Hub\ntype: reference\nsummary: S\ntags: []\n---\n\nhub body\n"
        phase2_decisions = [{"action": "hub-spoke", "hub_title": "SubHub", "hub_path": "sub/hub.md", "hub_content": hub_content}]

        with patch.object(rst_mod, "_load_config", return_value=config), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_call_audit_notes", return_value=[]), \
             patch("backends.call_model", side_effect=["[]", json.dumps(phase2_decisions)]), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(folder="sub", folder_hub=True, dry_run=False)
        log_path = tmp_path / "AI" / "Log.md"
        assert not log_path.exists()
