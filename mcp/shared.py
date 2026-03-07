"""Shared state and extractor imports for the cyberbrain MCP server."""

import os
import sys
from pathlib import Path

# Reuse extract_beats logic from the installed extractor
sys.path.insert(0, str(Path.home() / ".claude" / "cyberbrain" / "extractors"))

# ---------------------------------------------------------------------------
# Module-level import of extract_beats — fail fast at startup, not mid-session
# ---------------------------------------------------------------------------

try:
    from extract_beats import (
        extract_beats as _extract_beats,
        parse_jsonl_transcript,
        write_beat, autofile_beat, write_journal_entry,
        BackendError,
        resolve_config as _resolve_config,
        _call_claude_code as _call_claude_code_backend,
        RUNS_LOG_PATH,
    )
except ImportError as e:
    raise RuntimeError(
        f"Could not import extract_beats from ~/.claude/cyberbrain/extractors/: {e}. "
        "Run install.sh to ensure the extractor is installed."
    ) from e

# Search backend — lazy-loaded on first cb_recall call
_search_backend = None


def _get_search_backend(config: dict):
    """Return cached search backend, initialised lazily."""
    global _search_backend
    if _search_backend is None:
        try:
            from search_backends import get_search_backend
            _search_backend = get_search_backend(config)
        except Exception:
            _search_backend = None
    return _search_backend


def _load_config(cwd: str = "") -> dict:
    return _resolve_config(cwd or str(Path.home()))


def _relpath(path: Path, vault_path: str) -> str:
    return os.path.relpath(str(path), vault_path)


def _parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from markdown content. Returns {} on any error."""
    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end == -1:
        return {}
    try:
        import yaml
        fm = yaml.safe_load(content[3:end])
        return fm if isinstance(fm, dict) else {}
    except Exception:
        return {}


def _prune_index(config: dict) -> int:
    """Remove index entries for notes no longer on disk. Returns count pruned."""
    backend = _get_search_backend(config)
    if backend is None or not hasattr(backend, "prune_stale_notes"):
        return 0
    try:
        return backend.prune_stale_notes() or 0
    except Exception:
        return 0


def _index_paths(paths: list, config: dict) -> int:
    """Index a list of written note paths into the search index. Returns count indexed."""
    backend = _get_search_backend(config)
    if backend is None or not hasattr(backend, "index_note"):
        return 0
    count = 0
    for path in paths:
        try:
            content = Path(path).read_text(encoding="utf-8")
            fm = _parse_frontmatter(content)
            backend.index_note(str(path), fm)
            count += 1
        except Exception:
            pass
    return count
