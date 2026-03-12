#!/usr/bin/env python3
"""
Cyberbrain MCP Server

Exposes cb_extract, cb_file, cb_recall, cb_read, cb_configure, cb_status,
cb_enrich, cb_restructure, cb_review, cb_reindex, and cb_setup as MCP tools
so Claude Code and Claude Desktop can file beats into and search an Obsidian vault.

Install: see install.sh — copies this package to ~/.claude/cyberbrain/mcp/ and
registers it in ~/Library/Application Support/Claude/claude_desktop_config.json.
"""

from fastmcp import FastMCP

mcp = FastMCP("cyberbrain")

from cyberbrain.mcp.tools import extract, file, recall, manage, setup, enrich, restructure, review, reindex
from cyberbrain.mcp import resources

extract.register(mcp)
file.register(mcp)
recall.register(mcp)
manage.register(mcp)
setup.register(mcp)
enrich.register(mcp)
restructure.register(mcp)
review.register(mcp)
reindex.register(mcp)
resources.register(mcp)

if __name__ == "__main__":
    mcp.run()


def main():
    """Entry point for the cyberbrain MCP server."""
    mcp.run()
