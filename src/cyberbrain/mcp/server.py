#!/usr/bin/env python3
"""
Cyberbrain MCP Server

Exposes cb_extract, cb_file, cb_recall, cb_read, cb_configure, cb_status,
cb_enrich, cb_restructure, cb_review, cb_reindex, cb_setup, and cb_audit as MCP tools
so Claude Code and Claude Desktop can file beats into and search an Obsidian vault.

Install: via Claude Code plugin system (`claude plugin install cyberbrain@devnill-cyberbrain`)
or development install (`uv sync`).
"""

from fastmcp import FastMCP

mcp = FastMCP("cyberbrain")

from cyberbrain.mcp import resources
from cyberbrain.mcp.tools import (
    audit,
    enrich,
    extract,
    file,
    manage,
    recall,
    reindex,
    restructure,
    review,
    setup,
)

extract.register(mcp)
file.register(mcp)
recall.register(mcp)
manage.register(mcp)
setup.register(mcp)
enrich.register(mcp)
restructure.register(mcp)
review.register(mcp)
reindex.register(mcp)
audit.register(mcp)
resources.register(mcp)

if __name__ == "__main__":
    mcp.run()


def main():
    """Entry point for the cyberbrain MCP server."""
    mcp.run()
