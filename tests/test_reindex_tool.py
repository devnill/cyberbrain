"""
test_reindex_tool.py — unit tests for mcp/tools/reindex.py

Covers:
- No vault configured (empty or missing path) → ToolError
- No search index (grep backend, backend is None) → info string
- rebuild=True with build_full_index support → calls rebuild, returns message
- rebuild=True without build_full_index support → returns unsupported message
- prune=True (default) → calls _prune_index, returns count message
- prune=False + rebuild=False → returns "No action taken"
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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

# conftest.py installs the shared extract_beats mock before this module is imported.
# Clear any stale module cache so we get a fresh import.
for _mod in ["shared", "tools.reindex"]:
    sys.modules.pop(_mod, None)

import shared as _shared  # noqa: E402
import tools.reindex as reindex_mod  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402


# ---------------------------------------------------------------------------
# FakeMCP — captures the registered cb_reindex function
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
reindex_mod.register(_fake_mcp)


def _cb_reindex():
    """Return the registered cb_reindex function."""
    return _fake_mcp._tools["cb_reindex"]["fn"]


# ---------------------------------------------------------------------------
# Tests: vault not configured
# ---------------------------------------------------------------------------

class TestCbReindexNoVault:
    def test_raises_when_vault_path_empty(self):
        with patch.object(reindex_mod, "_load_config", return_value={"vault_path": ""}):
            with pytest.raises(ToolError, match="No vault configured"):
                _cb_reindex()()

    def test_raises_when_vault_path_missing_from_config(self):
        with patch.object(reindex_mod, "_load_config", return_value={}):
            with pytest.raises(ToolError, match="No vault configured"):
                _cb_reindex()()

    def test_raises_when_vault_path_does_not_exist(self, tmp_path):
        nonexistent = str(tmp_path / "no_such_vault")
        with patch.object(reindex_mod, "_load_config", return_value={"vault_path": nonexistent}):
            with pytest.raises(ToolError, match="No vault configured"):
                _cb_reindex()()


# ---------------------------------------------------------------------------
# Tests: no search index (grep backend)
# ---------------------------------------------------------------------------

class TestCbReindexNoBackend:
    def test_returns_info_when_backend_is_none(self, tmp_path):
        config = {"vault_path": str(tmp_path)}
        with patch.object(reindex_mod, "_load_config", return_value=config), \
             patch.object(reindex_mod, "_get_search_backend", return_value=None):
            result = _cb_reindex()()
        assert "grep backend" in result
        assert "Nothing to maintain" in result


# ---------------------------------------------------------------------------
# Tests: rebuild=True
# ---------------------------------------------------------------------------

class TestCbReindexRebuild:
    def test_rebuild_calls_build_full_index(self, tmp_path):
        config = {"vault_path": str(tmp_path)}
        backend = MagicMock(spec=["build_full_index"])
        with patch.object(reindex_mod, "_load_config", return_value=config), \
             patch.object(reindex_mod, "_get_search_backend", return_value=backend):
            result = _cb_reindex()(rebuild=True)
        backend.build_full_index.assert_called_once_with(config)
        assert "fully rebuilt" in result
        assert str(tmp_path) in result

    def test_rebuild_returns_unsupported_when_method_missing(self, tmp_path):
        config = {"vault_path": str(tmp_path)}
        backend = MagicMock(spec=[])  # no build_full_index attribute
        with patch.object(reindex_mod, "_load_config", return_value=config), \
             patch.object(reindex_mod, "_get_search_backend", return_value=backend):
            result = _cb_reindex()(rebuild=True)
        assert "does not support" in result


# ---------------------------------------------------------------------------
# Tests: prune (default)
# ---------------------------------------------------------------------------

class TestCbReindexPrune:
    def test_prune_calls_prune_index_and_returns_count(self, tmp_path):
        config = {"vault_path": str(tmp_path)}
        backend = MagicMock()
        with patch.object(reindex_mod, "_load_config", return_value=config), \
             patch.object(reindex_mod, "_get_search_backend", return_value=backend), \
             patch.object(reindex_mod, "_prune_index", return_value=5) as mock_prune:
            result = _cb_reindex()(prune=True)
        mock_prune.assert_called_once_with(config)
        assert "5" in result
        assert "stale" in result

    def test_prune_zero_returns_zero_count(self, tmp_path):
        config = {"vault_path": str(tmp_path)}
        backend = MagicMock()
        with patch.object(reindex_mod, "_load_config", return_value=config), \
             patch.object(reindex_mod, "_get_search_backend", return_value=backend), \
             patch.object(reindex_mod, "_prune_index", return_value=0):
            result = _cb_reindex()(prune=True)
        assert "0" in result


# ---------------------------------------------------------------------------
# Tests: no-op
# ---------------------------------------------------------------------------

class TestCbReindexNoOp:
    def test_returns_no_action_when_both_false(self, tmp_path):
        config = {"vault_path": str(tmp_path)}
        backend = MagicMock()
        with patch.object(reindex_mod, "_load_config", return_value=config), \
             patch.object(reindex_mod, "_get_search_backend", return_value=backend):
            result = _cb_reindex()(prune=False, rebuild=False)
        assert "No action taken" in result
