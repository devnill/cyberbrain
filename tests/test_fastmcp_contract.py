"""
FastMCP contract tests.

Verify that all registered handlers satisfy FastMCP's dispatch contract —
that the real framework can render, read, or call each handler type without
errors. These tests use a real FastMCP instance (not FakeMCP) and catch
framework API breakage that unit tests miss.
"""

import asyncio
from unittest.mock import patch

from fastmcp import FastMCP

import cyberbrain.mcp.resources as resources_mod
import cyberbrain.mcp.tools.manage as manage_mod
import cyberbrain.mcp.tools.recall as recall_mod

BASE_CONFIG = {
    "vault_path": "/tmp/test-vault",
    "inbox": "Inbox",
    "backend": "claude-code",
    "model": "claude-haiku-4-5",
    "proactive_recall": True,
    "desktop_capture_mode": "suggest",
}


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Prompts — no mocking needed
# ---------------------------------------------------------------------------


class TestPromptContract:
    """render_prompt() succeeds and returns well-formed Message objects."""

    def setup_method(self):
        self.mcp = FastMCP("cyberbrain-test")
        with patch.object(resources_mod, "_load_config", return_value=BASE_CONFIG):
            resources_mod.register(self.mcp)

    def test_recall_renders(self):
        result = _run(self.mcp.render_prompt("recall", {}))
        assert result.messages
        assert result.messages[0].role == "user"
        assert result.messages[0].content.text  # non-empty

    def test_orient_renders(self):
        with patch.object(resources_mod, "_load_config", return_value=BASE_CONFIG):
            result = _run(self.mcp.render_prompt("orient", {}))
        assert result.messages
        assert result.messages[0].role == "user"
        assert "cyberbrain" in result.messages[0].content.text.lower()


# ---------------------------------------------------------------------------
# Resource — patch _load_config
# ---------------------------------------------------------------------------


class TestResourceContract:
    """read_resource() succeeds and returns a string."""

    def setup_method(self):
        self.mcp = FastMCP("cyberbrain-test")
        with patch.object(resources_mod, "_load_config", return_value=BASE_CONFIG):
            resources_mod.register(self.mcp)

    def test_guide_readable(self):
        with patch.object(resources_mod, "_load_config", return_value=BASE_CONFIG):
            result = _run(self.mcp.read_resource("cyberbrain://guide"))
        # FastMCP returns a ResourceResult with a .contents list
        assert result.contents
        text = result.contents[0].content
        assert "cb_recall" in text


# ---------------------------------------------------------------------------
# Tools — patch _load_config, verify dispatch succeeds
# ---------------------------------------------------------------------------


class TestToolContract:
    """call_tool() dispatches without FastMCP-level errors."""

    def setup_method(self):
        self.mcp = FastMCP("cyberbrain-test")
        with patch.object(manage_mod, "_load_config", return_value=BASE_CONFIG):
            manage_mod.register(self.mcp)
        with patch.object(recall_mod, "_load_config", return_value=BASE_CONFIG):
            recall_mod.register(self.mcp)

    def test_cb_status_dispatches(self, tmp_path):
        config = {**BASE_CONFIG, "vault_path": str(tmp_path)}
        with patch.object(manage_mod, "_load_config", return_value=config):
            result = _run(self.mcp.call_tool("cb_status", {}))
        # Result is a list of content items; we just need it to not raise
        assert result is not None

    def test_cb_recall_dispatches(self, tmp_path):
        config = {**BASE_CONFIG, "vault_path": str(tmp_path)}
        with patch.object(recall_mod, "_load_config", return_value=config):
            result = _run(self.mcp.call_tool("cb_recall", {"query": "test"}))
        assert result is not None
