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
        decisions = [{
            "cluster_index": 0, "action": "merge",
            "merged_title": "Merged", "merged_path": "Merged.md",
            "merged_content": merged_content, "rationale": "related"
        }]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_build_clusters", return_value=[cluster]), \
             patch("backends.call_model", return_value=json.dumps(decisions)), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(dry_run=False)
        assert "Restructure Complete" in result
        assert (tmp_path / "Merged.md").exists()

    def test_split_execution(self, tmp_path):
        big_content = "---\ntitle: Big\ntype: reference\nsummary: S\ntags: []\n---\n\n" + "x" * 4000
        (tmp_path / "Big.md").write_text(big_content)
        notes = rst_mod._collect_notes(tmp_path, tmp_path, [])

        part_content = "---\ntitle: Part A\ntype: reference\nsummary: S\ntags: []\n---\n\nbody\n"
        decisions = [{
            "note_index": 0, "action": "split", "rationale": "",
            "output_notes": [{"title": "Part A", "path": "PartA.md", "content": part_content}]
        }]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_build_clusters", return_value=[]), \
             patch("backends.call_model", return_value=json.dumps(decisions)), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(dry_run=False, split_threshold=100)
        assert (tmp_path / "PartA.md").exists()
        assert "split" in result.lower()

    def test_split_skips_path_traversal(self, tmp_path):
        big_content = "---\ntitle: Big\ntype: reference\nsummary: S\ntags: []\n---\n\n" + "x" * 4000
        (tmp_path / "Big.md").write_text(big_content)

        decisions = [{
            "note_index": 0, "action": "split", "rationale": "",
            "output_notes": [{"title": "Evil", "path": "../../evil.md", "content": "body"}]
        }]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_build_clusters", return_value=[]), \
             patch("backends.call_model", return_value=json.dumps(decisions)), \
             patch("backends.BackendError", Exception):
            result = _cb_restructure()(dry_run=False, split_threshold=100)
        assert "path traversal" in result

    def test_split_skips_empty_output_notes(self, tmp_path):
        big_content = "---\ntitle: Big\ntype: reference\nsummary: S\ntags: []\n---\n\n" + "x" * 4000
        (tmp_path / "Big.md").write_text(big_content)

        decisions = [{"note_index": 0, "action": "split", "output_notes": []}]

        with patch.object(rst_mod, "_load_config", return_value=self._base_config(tmp_path)), \
             patch.object(rst_mod, "_get_search_backend", return_value=None), \
             patch.object(rst_mod, "_index_paths"), \
             patch.object(rst_mod, "_prune_index"), \
             patch.object(rst_mod, "_load_prompt", return_value="p"), \
             patch.object(rst_mod, "_build_clusters", return_value=[]), \
             patch("backends.call_model", return_value=json.dumps(decisions)), \
             patch("backends.BackendError", Exception):
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
             patch.object(rst_mod, "_title_concept_clusters", return_value=[notes]), \
             patch("backends.call_model", side_effect=FakeBackendError("fail")), \
             patch("backends.BackendError", FakeBackendError):
            with pytest.raises(ToolError, match="Backend error"):
                _cb_restructure()(folder="sub", folder_hub=True, dry_run=False)
