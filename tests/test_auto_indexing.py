"""
test_auto_indexing.py — unit tests for automatic search index maintenance.

Coverage:
- incremental_refresh: first-run (no marker), threshold skip, detects new files,
  detects deleted files, prune called, marker updated, error handling
- cb_recall: calls incremental_refresh before search, errors swallowed
- cb_reindex(rebuild=True): calls search_index.build_full_index directly (bug fix)
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

import importlib

# Force a fresh import so any prior cached version (without new attributes) is dropped.
import cyberbrain.extractors.search_index
importlib.reload(cyberbrain.extractors.search_index)
import cyberbrain.extractors.search_index as si


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_backend_cache():
    """Clear the module-level backend cache before each test."""
    si._backend_cache.clear()
    yield
    si._backend_cache.clear()


@pytest.fixture()
def vault(tmp_path):
    """A temporary vault with a couple of .md files."""
    (tmp_path / "Note1.md").write_text("---\ntitle: Note1\n---\nBody one")
    (tmp_path / "Note2.md").write_text("---\ntitle: Note2\n---\nBody two")
    return tmp_path


@pytest.fixture()
def config(vault):
    return {"vault_path": str(vault)}


@pytest.fixture()
def mock_backend():
    b = MagicMock()
    b.backend_name.return_value = "fts5"
    b.prune_stale_notes.return_value = 0
    return b


# ===========================================================================
# incremental_refresh
# ===========================================================================

class TestIncrementalRefresh:
    """Tests for search_index.incremental_refresh()."""

    def test_first_run_indexes_all_files(self, vault, config, mock_backend, tmp_path):
        """When no marker file exists, all vault .md files are indexed."""
        marker = tmp_path / "marker"

        with patch.object(si, "_SCAN_MARKER_PATH", marker), \
             patch.object(si, "_get_backend", return_value=mock_backend):
            count = si.incremental_refresh(config, max_age_seconds=3600)

        # Two files in vault → both indexed
        assert count == 2
        assert mock_backend.index_note.call_count == 2

    def test_first_run_creates_marker(self, vault, config, mock_backend, tmp_path):
        """After first run, the marker file is created."""
        marker = tmp_path / "marker"

        with patch.object(si, "_SCAN_MARKER_PATH", marker), \
             patch.object(si, "_get_backend", return_value=mock_backend):
            si.incremental_refresh(config, max_age_seconds=3600)

        assert marker.exists()
        ts = float(marker.read_text())
        assert ts > 0

    def test_skips_when_index_fresh(self, vault, config, mock_backend, tmp_path):
        """Returns -1 without touching the backend when the marker is recent."""
        marker = tmp_path / "marker"
        # Write a very recent timestamp
        marker.write_text(str(time.time()))

        with patch.object(si, "_SCAN_MARKER_PATH", marker), \
             patch.object(si, "_get_backend", return_value=mock_backend):
            count = si.incremental_refresh(config, max_age_seconds=3600)

        assert count == -1
        mock_backend.index_note.assert_not_called()

    def test_runs_when_marker_older_than_threshold(self, vault, config, mock_backend, tmp_path):
        """When marker is older than threshold, refresh runs."""
        marker = tmp_path / "marker"
        # Write a timestamp 2 hours ago
        marker.write_text(str(time.time() - 7200))

        with patch.object(si, "_SCAN_MARKER_PATH", marker), \
             patch.object(si, "_get_backend", return_value=mock_backend):
            count = si.incremental_refresh(config, max_age_seconds=3600)

        # Both files have mtime newer than 2 hours ago → both indexed
        assert count == 2

    def test_only_indexes_modified_files(self, vault, config, mock_backend, tmp_path):
        """Only files with mtime > last_scan_ts are re-indexed."""
        marker = tmp_path / "marker"
        # Set marker to now so no existing files qualify
        marker.write_text(str(time.time()))

        # Create a new file after the marker
        new_file = vault / "NewNote.md"
        new_file.write_text("---\ntitle: New\n---\nbody")
        # Touch it to ensure mtime is after marker
        import os
        os.utime(str(new_file), (time.time() + 1, time.time() + 1))

        with patch.object(si, "_SCAN_MARKER_PATH", marker), \
             patch.object(si, "_get_backend", return_value=mock_backend):
            # Use max_age_seconds=0 to force the scan to run
            count = si.incremental_refresh(config, max_age_seconds=0)

        # Only the new file should be indexed (marker ts is very recent)
        assert count >= 1
        indexed_paths = [str(c.args[0]) for c in mock_backend.index_note.call_args_list]
        assert str(new_file) in indexed_paths

    def test_prune_called_after_indexing(self, vault, config, mock_backend, tmp_path):
        """prune_stale_notes is called once after indexing to remove deleted entries."""
        marker = tmp_path / "marker"

        with patch.object(si, "_SCAN_MARKER_PATH", marker), \
             patch.object(si, "_get_backend", return_value=mock_backend):
            si.incremental_refresh(config, max_age_seconds=3600)

        mock_backend.prune_stale_notes.assert_called_once()

    def test_returns_minus_one_when_no_backend(self, vault, config, tmp_path):
        """Returns -1 when no search backend is available."""
        marker = tmp_path / "marker"

        with patch.object(si, "_SCAN_MARKER_PATH", marker), \
             patch.object(si, "_get_backend", return_value=None):
            count = si.incremental_refresh(config, max_age_seconds=3600)

        assert count == -1
        assert not marker.exists()

    def test_returns_minus_one_when_vault_missing(self, tmp_path):
        """Returns -1 when the vault path does not exist."""
        config = {"vault_path": str(tmp_path / "nonexistent")}
        marker = tmp_path / "marker"

        with patch.object(si, "_SCAN_MARKER_PATH", marker):
            count = si.incremental_refresh(config, max_age_seconds=3600)

        assert count == -1

    def test_swallows_index_note_exception(self, vault, config, mock_backend, tmp_path):
        """If index_note raises for a file, the error is logged and refresh continues."""
        marker = tmp_path / "marker"
        mock_backend.index_note.side_effect = RuntimeError("index failure")

        with patch.object(si, "_SCAN_MARKER_PATH", marker), \
             patch.object(si, "_get_backend", return_value=mock_backend):
            # Should not raise
            count = si.incremental_refresh(config, max_age_seconds=3600)

        # Errors on individual files are swallowed; marker should still be written
        assert marker.exists()

    def test_swallows_prune_exception(self, vault, config, mock_backend, tmp_path, capsys):
        """If prune_stale_notes raises, the error is logged and not propagated."""
        marker = tmp_path / "marker"
        mock_backend.prune_stale_notes.side_effect = RuntimeError("prune failure")

        with patch.object(si, "_SCAN_MARKER_PATH", marker), \
             patch.object(si, "_get_backend", return_value=mock_backend):
            count = si.incremental_refresh(config, max_age_seconds=3600)

        captured = capsys.readouterr()
        assert "Prune failed" in captured.err or "prune" in captured.err.lower()

    def test_uses_config_refresh_interval(self, vault, tmp_path, mock_backend):
        """config['index_refresh_interval'] overrides the default threshold."""
        config = {"vault_path": str(vault), "index_refresh_interval": 100}
        marker = tmp_path / "marker"
        # Marker is 50 seconds old → should be skipped with 100s interval
        marker.write_text(str(time.time() - 50))

        with patch.object(si, "_SCAN_MARKER_PATH", marker), \
             patch.object(si, "_get_backend", return_value=mock_backend):
            count = si.incremental_refresh(config)

        assert count == -1

    def test_marker_updated_after_successful_refresh(self, vault, config, mock_backend, tmp_path):
        """Marker file timestamp is updated to approximately now after a successful run."""
        marker = tmp_path / "marker"
        before = time.time()

        with patch.object(si, "_SCAN_MARKER_PATH", marker), \
             patch.object(si, "_get_backend", return_value=mock_backend):
            si.incremental_refresh(config, max_age_seconds=3600)

        after = time.time()
        ts = float(marker.read_text())
        assert before <= ts <= after + 1


# ===========================================================================
# cb_recall calls incremental_refresh
# ===========================================================================

class TestCbRecallCallsRefresh:
    """cb_recall calls incremental_refresh before the search."""

    def _make_mcp(self):
        from unittest.mock import MagicMock
        mcp = MagicMock()
        tools = {}

        def tool_decorator(**kwargs):
            def inner(fn):
                tools[fn.__name__] = fn
                return fn
            return inner

        mcp.tool = tool_decorator
        mcp._tools = tools
        return mcp, tools

    def test_incremental_refresh_called_on_recall(self, tmp_path):
        """cb_recall triggers incremental_refresh before executing the search."""
        vault = tmp_path / "vault"
        vault.mkdir()

        mcp, tools = self._make_mcp()

        # Clear cached imports so our patched shared module is used
        # Only pop specific modules to avoid breaking other tests
        for mod in ["cyberbrain.mcp.shared", "cyberbrain.mcp.tools.recall", "cyberbrain.mcp.tools.reindex", "cyberbrain.mcp.tools.enrich"]:
            sys.modules.pop(mod, None)

        mock_config = {"vault_path": str(vault), "search_backend": "grep"}

        refresh_called_with = []

        def fake_refresh(config, max_age_seconds=None):
            refresh_called_with.append(config)
            return -1

        with patch("cyberbrain.mcp.shared._load_config", return_value=mock_config), \
             patch("cyberbrain.mcp.shared._get_search_backend", return_value=None), \
             patch("cyberbrain.extractors.search_index.incremental_refresh", side_effect=fake_refresh):

            import cyberbrain.mcp.tools.recall as recall_module
            recall_module.register(mcp)
            cb_recall = tools["cb_recall"]

            # Create a note so grep has something to find
            (vault / "test.md").write_text("---\ntitle: Test\n---\nsome content here")

            try:
                cb_recall(query="some content")
            except Exception:
                pass  # we only care that refresh was called

        assert len(refresh_called_with) >= 1

    def test_incremental_refresh_error_does_not_block_recall(self, tmp_path):
        """If incremental_refresh raises, cb_recall still returns results."""
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "alpha.md").write_text("---\ntitle: Alpha\n---\nalpha beta gamma")

        mcp, tools = self._make_mcp()

        for mod in ["cyberbrain.mcp.shared", "cyberbrain.mcp.tools.recall", "cyberbrain.mcp.tools.reindex", "cyberbrain.mcp.tools.enrich"]:
            sys.modules.pop(mod, None)

        mock_config = {"vault_path": str(vault), "search_backend": "grep"}

        with patch("cyberbrain.mcp.shared._load_config", return_value=mock_config), \
             patch("cyberbrain.mcp.shared._get_search_backend", return_value=None), \
             patch("cyberbrain.extractors.search_index.incremental_refresh",
                   side_effect=RuntimeError("refresh exploded")):

            import cyberbrain.mcp.tools.recall as recall_module
            recall_module.register(mcp)
            cb_recall = tools["cb_recall"]

            # Should not raise even though incremental_refresh raises
            result = cb_recall(query="alpha beta")
            assert "alpha" in result.lower() or "note" in result.lower()


# ===========================================================================
# cb_reindex rebuild bug fix
# ===========================================================================

class TestCbReindexRebuildFix:
    """cb_reindex(rebuild=True) calls search_index.build_full_index, not backend method."""

    def _register_reindex(self):
        mcp = MagicMock()
        tools = {}

        def tool_decorator(**kwargs):
            def inner(fn):
                tools[fn.__name__] = fn
                return fn
            return inner

        mcp.tool = tool_decorator

        for mod in list(sys.modules.keys()):
            if "cyberbrain.mcp.tools.reindex" in mod:
                sys.modules.pop(mod, None)

        import cyberbrain.mcp.tools.reindex as reindex_module
        reindex_module.register(mcp)
        return tools["cb_reindex"]

    def test_rebuild_calls_build_full_index(self, tmp_path):
        """rebuild=True calls search_index.build_full_index, not backend.build_full_index."""
        mock_backend = MagicMock()
        mock_backend.backend_name.return_value = "fts5"

        config = {"vault_path": str(tmp_path)}

        build_called = []

        def fake_build(cfg):
            build_called.append(cfg)

        with patch("cyberbrain.mcp.shared._load_config", return_value=config), \
             patch("cyberbrain.mcp.shared._get_search_backend", return_value=mock_backend), \
             patch("cyberbrain.extractors.search_index.build_full_index",
                   side_effect=fake_build):

            cb_reindex = self._register_reindex()
            result = cb_reindex(rebuild=True, prune=False)

        assert len(build_called) == 1
        assert "rebuilt" in result.lower()
        # The old bug: backend has no build_full_index → was silently returning error message
        assert "does not support" not in result

    def test_rebuild_no_longer_returns_unsupported_error(self, tmp_path):
        """After bug fix, rebuild never returns 'does not support full rebuild'."""
        mock_backend = MagicMock()
        # Intentionally do NOT define build_full_index on mock_backend
        del mock_backend.build_full_index

        config = {"vault_path": str(tmp_path)}

        with patch("cyberbrain.mcp.shared._load_config", return_value=config), \
             patch("cyberbrain.mcp.shared._get_search_backend", return_value=mock_backend), \
             patch("cyberbrain.extractors.search_index.build_full_index"):

            cb_reindex = self._register_reindex()
            result = cb_reindex(rebuild=True, prune=False)

        assert "does not support" not in result
