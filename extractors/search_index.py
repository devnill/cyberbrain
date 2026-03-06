"""
search_index.py

Coordination layer for cyberbrain's search index.

Provides two public functions used by extract_beats.py:
  - update_search_index(note_path, metadata, config)  — called after each note write
  - build_full_index(config)                          — called to rebuild from scratch

The actual search implementations live in search_backends.py.
This module handles backend lifecycle and graceful degradation.

Design note: cyberbrain uses metadata-only embedding (title + summary + tags).
LLM-generated metadata is already optimised for search signal. Full-body embedding
dilutes that signal with prose, headers, and code — and increases indexing cost.
At the 2K-10K notes scale of a personal vault, metadata-only gives better
precision than body embedding at a fraction of the cost.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from search_backends import SearchBackend

# Module-level backend cache: one backend instance per (vault_path, backend_key) pair.
# Avoids re-loading the usearch index on every note write.
_backend_cache: dict[str, "SearchBackend"] = {}


def _get_backend(config: dict) -> "SearchBackend | None":
    """
    Return a cached backend instance.
    Returns None if search indexing is disabled or the backend fails to initialise.
    """
    if not config.get("vault_path"):
        return None

    cache_key = f"{config.get('vault_path')}::{config.get('search_backend', 'auto')}::{config.get('embedding_model', '')}"
    if cache_key in _backend_cache:
        return _backend_cache[cache_key]

    try:
        from search_backends import get_search_backend
        backend = get_search_backend(config)
        _backend_cache[cache_key] = backend
        return backend
    except Exception as e:
        print(f"[search_index] Could not initialise search backend: {e}", file=sys.stderr)
        return None


def update_search_index(note_path: str, metadata: dict, config: dict) -> None:
    """
    Index or re-index a single note after it has been written to the vault.

    Called by extract_beats.write_beat() and extract_beats.autofile_beat().
    Safe to call on every write — content-hash dedup in FTS5Backend skips unchanged notes.
    Failures are logged and swallowed; search index staleness is non-fatal.
    """
    backend = _get_backend(config)
    if backend is None:
        return

    try:
        backend.index_note(note_path, metadata)
    except Exception as e:
        print(
            f"[search_index] Index update failed for {Path(note_path).name}: {e}",
            file=sys.stderr,
        )


def build_full_index(config: dict) -> None:
    """
    Build or rebuild the full search index from the vault.

    Incremental — skips notes whose content hash has not changed.
    Attempts to import Smart Connections embeddings if the vault has a .smart-env/ directory
    and was indexed with a compatible model (avoids double-embedding).
    """
    backend = _get_backend(config)
    if backend is None:
        print("[search_index] No backend available — skipping index build.", file=sys.stderr)
        return

    print(
        f"[search_index] Building index with backend: {backend.backend_name()}",
        file=sys.stderr,
    )
    try:
        backend.build_index()
    except Exception as e:
        print(f"[search_index] Index build failed: {e}", file=sys.stderr)


def active_backend_name(config: dict) -> str:
    """Return the name of the active search backend (for display in cb_recall output)."""
    backend = _get_backend(config)
    if backend is None:
        return "none"
    try:
        return backend.backend_name()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    import json
    from pathlib import Path

    config_path = Path.home() / ".claude" / "cyberbrain" / "config.json"
    if not config_path.exists():
        print("No config found at ~/.claude/cyberbrain/config.json", file=sys.stderr)
        sys.exit(1)
    config = json.loads(config_path.read_text())
    build_full_index(config)
