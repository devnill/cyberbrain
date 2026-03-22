"""
search_index.py

Coordination layer for cyberbrain's search index.

Provides two public functions used by extract_beats.py:
  - update_search_index(note_path, metadata, config)  — called after each note write
  - build_full_index(config)                          — called to rebuild from scratch
  - incremental_refresh(config, max_age_seconds)      — lazy incremental update

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
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cyberbrain.extractors.search_backends import SearchBackend

from cyberbrain.extractors.state import INDEX_SCAN_MARKER_PATH as _SCAN_MARKER_PATH

_DEFAULT_REFRESH_INTERVAL = 3600  # seconds

# Module-level backend cache: one backend instance per (vault_path, backend_key) pair.
# Avoids re-loading the usearch index on every note write.
_backend_cache: dict[str, SearchBackend] = {}


def _get_backend(config: dict) -> SearchBackend | None:
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
        from cyberbrain.extractors.search_backends import get_search_backend

        backend = get_search_backend(config)
        _backend_cache[cache_key] = backend
        return backend
    except Exception as e:  # intentional: backend init failure (missing deps, bad config) is non-fatal; search degrades to grep
        print(
            f"[search_index] Could not initialise search backend: {e}", file=sys.stderr
        )
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
    except Exception as e:  # intentional: index update failure is non-fatal per docstring; search index staleness is acceptable
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
        print(
            "[search_index] No backend available — skipping index build.",
            file=sys.stderr,
        )
        return

    print(
        f"[search_index] Building index with backend: {backend.backend_name()}",
        file=sys.stderr,
    )
    try:
        backend.build_index()
    except (
        Exception
    ) as e:  # intentional: index build failure is non-fatal; search degrades to grep
        print(f"[search_index] Index build failed: {e}", file=sys.stderr)


def active_backend_name(config: dict) -> str:
    """Return the name of the active search backend (for display in cb_recall output)."""
    backend = _get_backend(config)
    if backend is None:
        return "none"
    try:
        return backend.backend_name()
    except (
        Exception
    ):  # intentional: backend may be in a broken state; return safe fallback string
        return "unknown"


def incremental_refresh(config: dict, max_age_seconds: int | None = None) -> int:
    """
    If the last scan is older than max_age_seconds, walk the vault and re-index
    files whose mtime is newer than last_scan_ts, then prune deleted entries.

    Returns the number of notes re-indexed, or -1 if skipped (index is fresh
    or no backend is available).

    On first run (no marker file), last_scan_ts is treated as 0 so that all vault
    files are indexed, bootstrapping the index without special-case logic.

    Errors are caught and logged; a failed refresh never blocks the caller.
    """
    if max_age_seconds is None:
        max_age_seconds = int(
            config.get("index_refresh_interval", _DEFAULT_REFRESH_INTERVAL)
        )

    vault_path = config.get("vault_path", "")
    if not vault_path or not Path(vault_path).exists():
        return -1

    # Read the marker timestamp
    try:
        if _SCAN_MARKER_PATH.exists():
            last_scan_ts = float(_SCAN_MARKER_PATH.read_text().strip())
        else:
            last_scan_ts = 0.0
    except (OSError, ValueError) as e:
        print(f"[search_index] Could not read scan marker: {e}", file=sys.stderr)
        last_scan_ts = 0.0

    now = time.time()

    # Check if index is fresh enough to skip
    if last_scan_ts > 0 and (now - last_scan_ts) < max_age_seconds:
        return -1

    backend = _get_backend(config)
    if backend is None:
        return -1

    count = 0
    try:
        # Walk vault for files modified since last scan
        for md_file in Path(vault_path).rglob("*.md"):
            try:
                if md_file.stat().st_mtime > last_scan_ts:
                    backend.index_note(str(md_file), {})
                    count += 1
            except Exception as e:  # intentional: per-file indexing failure is non-fatal; continue scan
                print(
                    f"[search_index] Could not index {md_file.name}: {e}",
                    file=sys.stderr,
                )

        # Prune entries for deleted notes
        if hasattr(backend, "prune_stale_notes"):
            try:
                backend.prune_stale_notes()  # type: ignore[reportAttributeAccessIssue]  # runtime duck-typed: hasattr guard above
            except Exception as e:  # intentional: prune failure is non-fatal; stale entries are harmless
                print(f"[search_index] Prune failed: {e}", file=sys.stderr)

        # Update marker
        _SCAN_MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SCAN_MARKER_PATH.write_text(str(now))

    except Exception as e:  # intentional: any vault walk failure (permissions, etc.) is non-fatal; caller gets -1
        print(f"[search_index] incremental_refresh failed: {e}", file=sys.stderr)
        return -1

    return count


def main() -> None:
    """Entry point for cyberbrain-reindex CLI and __main__ invocation."""
    import json

    from cyberbrain.extractors.state import CONFIG_PATH

    config_path = CONFIG_PATH
    if not config_path.exists():
        print("No config found at ~/.claude/cyberbrain/config.json", file=sys.stderr)
        sys.exit(1)
    config = json.loads(config_path.read_text())
    # Force refresh regardless of age by passing max_age_seconds=0
    count = incremental_refresh(config, max_age_seconds=0)
    if count >= 0:
        print(
            f"[search_index] Incremental refresh complete: {count} note(s) updated.",
            file=sys.stderr,
        )
    else:
        print(
            "[search_index] Refresh skipped (no backend or vault unavailable).",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
