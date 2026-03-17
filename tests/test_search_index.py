"""
test_search_index.py — unit tests for src/cyberbrain/extractors/search_index.py

Coverage:
- _get_backend: vault_path missing, caching, ImportError graceful handling
- update_search_index: calls index_note, swallows None backend, swallows exception
- build_full_index: calls build_index, logs backend name, handles None backend
- active_backend_name: returns name or "none"

No real backends are loaded — all tests use mocks.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import search_index from the extractors directory
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent

import cyberbrain.extractors.search_index as si


@pytest.fixture(autouse=True)
def clear_backend_cache():
    """Clear the module-level backend cache before each test."""
    si._backend_cache.clear()
    yield
    si._backend_cache.clear()


# ===========================================================================
# _get_backend
# ===========================================================================

class TestGetBackend:
    """_get_backend() returns a cached backend or None."""

    def test_returns_none_when_vault_path_missing(self):
        """Config without vault_path → None."""
        result = si._get_backend({})
        assert result is None

    def test_caches_backend_on_second_call(self, tmp_path):
        """Two calls with the same config return the same backend object."""
        mock_backend = MagicMock()
        config = {"vault_path": str(tmp_path), "search_backend": "fts5"}

        with patch("cyberbrain.extractors.search_backends.get_search_backend", return_value=mock_backend) as mock_factory:
            b1 = si._get_backend(config)
            b2 = si._get_backend(config)

        assert b1 is b2
        # Factory should only be called once
        assert mock_factory.call_count == 1

    def test_different_config_produces_different_cached_entry(self, tmp_path):
        """Different backend keys produce different cache entries."""
        mock_backend_1 = MagicMock()
        mock_backend_2 = MagicMock()
        config1 = {"vault_path": str(tmp_path), "search_backend": "grep"}
        config2 = {"vault_path": str(tmp_path), "search_backend": "fts5"}

        with patch("cyberbrain.extractors.search_backends.get_search_backend", side_effect=[mock_backend_1, mock_backend_2]):
            b1 = si._get_backend(config1)
            b2 = si._get_backend(config2)

        assert b1 is not b2

    def test_returns_none_on_import_error(self, tmp_path):
        """If get_search_backend raises ImportError, returns None without propagating."""
        config = {"vault_path": str(tmp_path), "search_backend": "fts5"}
        with patch("cyberbrain.extractors.search_backends.get_search_backend", side_effect=ImportError("no module")):
            result = si._get_backend(config)
        assert result is None


# ===========================================================================
# update_search_index
# ===========================================================================

class TestUpdateSearchIndex:
    """update_search_index() indexes a note post-write."""

    def test_calls_index_note_on_backend(self, tmp_path):
        """With a working backend, index_note is called with the correct path."""
        mock_backend = MagicMock()
        config = {"vault_path": str(tmp_path)}
        note_path = str(tmp_path / "Note.md")
        metadata = {"title": "Note", "type": "insight"}

        with patch.object(si, "_get_backend", return_value=mock_backend):
            si.update_search_index(note_path, metadata, config)

        mock_backend.index_note.assert_called_once_with(note_path, metadata)

    def test_swallows_backend_none(self, tmp_path):
        """If _get_backend returns None, no exception is raised."""
        with patch.object(si, "_get_backend", return_value=None):
            si.update_search_index("/some/path.md", {}, {"vault_path": str(tmp_path)})

    def test_swallows_index_note_exception(self, tmp_path):
        """If index_note raises, the exception is swallowed and not propagated."""
        mock_backend = MagicMock()
        mock_backend.index_note.side_effect = RuntimeError("index failure")
        config = {"vault_path": str(tmp_path)}

        with patch.object(si, "_get_backend", return_value=mock_backend):
            # Should not raise
            si.update_search_index("/some/path.md", {}, config)


# ===========================================================================
# build_full_index
# ===========================================================================

class TestBuildFullIndex:
    """build_full_index() rebuilds the entire search index."""

    def test_calls_build_index_on_backend(self, tmp_path):
        """With a working backend, build_index() is called once."""
        mock_backend = MagicMock()
        mock_backend.backend_name.return_value = "fts5"
        config = {"vault_path": str(tmp_path)}

        with patch.object(si, "_get_backend", return_value=mock_backend):
            si.build_full_index(config)

        mock_backend.build_index.assert_called_once()

    def test_logs_backend_name(self, tmp_path, capsys):
        """stderr contains the backend name."""
        mock_backend = MagicMock()
        mock_backend.backend_name.return_value = "fts5"
        config = {"vault_path": str(tmp_path)}

        with patch.object(si, "_get_backend", return_value=mock_backend):
            si.build_full_index(config)

        captured = capsys.readouterr()
        assert "fts5" in captured.err

    def test_swallows_backend_none(self, tmp_path, capsys):
        """No backend available → logs a message, no exception."""
        config = {"vault_path": str(tmp_path)}

        with patch.object(si, "_get_backend", return_value=None):
            si.build_full_index(config)

        captured = capsys.readouterr()
        assert "No backend" in captured.err or "no backend" in captured.err.lower()


# ===========================================================================
# active_backend_name
# ===========================================================================

class TestActiveBackendName:
    """active_backend_name() returns the name of the active search backend."""

    def test_returns_backend_name(self, tmp_path):
        """A mock backend with backend_name()='fts5' → returns 'fts5'."""
        mock_backend = MagicMock()
        mock_backend.backend_name.return_value = "fts5"
        config = {"vault_path": str(tmp_path)}

        with patch.object(si, "_get_backend", return_value=mock_backend):
            result = si.active_backend_name(config)

        assert result == "fts5"

    def test_returns_none_when_no_backend(self, tmp_path):
        """No backend → returns 'none'."""
        config = {"vault_path": str(tmp_path)}

        with patch.object(si, "_get_backend", return_value=None):
            result = si.active_backend_name(config)

        assert result == "none"


# ===========================================================================
# Additional exception path coverage
# ===========================================================================

class TestBuildFullIndexExceptions:
    """build_full_index handles backend exceptions gracefully."""

    def test_swallows_build_index_exception(self, tmp_path, capsys):
        """If backend.build_index() raises, the error is logged and not propagated."""
        mock_backend = MagicMock()
        mock_backend.backend_name.return_value = "fts5"
        mock_backend.build_index.side_effect = RuntimeError("build failed")
        config = {"vault_path": str(tmp_path)}

        with patch.object(si, "_get_backend", return_value=mock_backend):
            si.build_full_index(config)  # should not raise

        captured = capsys.readouterr()
        assert "failed" in captured.err.lower() or "error" in captured.err.lower()


class TestActiveBackendNameExceptions:
    """active_backend_name() handles backend_name() exceptions gracefully."""

    def test_returns_unknown_when_backend_name_raises(self, tmp_path):
        """If backend.backend_name() raises, 'unknown' is returned."""
        mock_backend = MagicMock()
        mock_backend.backend_name.side_effect = RuntimeError("name error")
        config = {"vault_path": str(tmp_path)}

        with patch.object(si, "_get_backend", return_value=mock_backend):
            result = si.active_backend_name(config)

        assert result == "unknown"
