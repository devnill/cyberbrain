"""cb_reindex tool — maintain the cyberbrain search index."""

from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from cyberbrain.mcp.shared import _load_config, _get_search_backend, _prune_index


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def cb_reindex(
        prune: Annotated[bool, Field(
            description="Remove index entries for notes that no longer exist on disk. Fast — safe to run anytime."
        )] = True,
        rebuild: Annotated[bool, Field(
            description="Full index rebuild from scratch: re-reads every vault note. Slow on large vaults. Use after major reorganization or if search results seem wrong."
        )] = False,
    ) -> str:
        """
        Maintain the cyberbrain search index.

        prune (default): removes stale index entries for notes that have been deleted
        or moved. Fast — does not re-read any files. Run this after any operation that
        deletes notes if cb_status shows a high stale path count.

        rebuild: walks every vault note and re-indexes from scratch. Use after a major
        vault reorganization or if the index seems corrupted.

        cb_restructure, cb_review, and cb_enrich call prune automatically after writes.
        Call this manually if cb_status shows a high stale path count.
        """
        config = _load_config()
        vault_path = config.get("vault_path", "")
        if not vault_path or not Path(vault_path).exists():
            raise ToolError("No vault configured. Run cb_configure(vault_path=...) first.")

        backend = _get_search_backend(config)
        if backend is None:
            return "No search index available (grep backend active). Nothing to maintain."

        if rebuild:
            if not hasattr(backend, "build_full_index"):
                return "Active search backend does not support full rebuild."
            backend.build_full_index(config)
            return f"Search index fully rebuilt. Vault: {vault_path}"

        if prune:
            pruned = _prune_index(config)
            return f"Pruned {pruned} stale index entry(s). Vault: {vault_path}"

        return "No action taken. Pass prune=True (default) or rebuild=True."
