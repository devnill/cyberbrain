"""Shared state and extractor imports for the cyberbrain MCP server."""

import os
from pathlib import Path

# Prompt directory resolution:
# 1. Primary: relative to this file (works in plugin cache via ${CLAUDE_PLUGIN_ROOT})
# 2. Fallback: legacy installed location for existing installs
_PROMPTS_DIR_PRIMARY = Path(__file__).parent.parent / "prompts"
from cyberbrain.extractors.state import PROMPTS_DIR_LEGACY as _PROMPTS_DIR_LEGACY

# ---------------------------------------------------------------------------
# Direct imports from source modules — avoids the extract_beats re-export hub,
# which lets tests mock individual modules without sys.modules manipulation.
# ---------------------------------------------------------------------------

try:
    from cyberbrain.extractors.autofile import autofile_beat
    from cyberbrain.extractors.backends import BackendError
    from cyberbrain.extractors.backends import (
        _call_claude_code as _call_claude_code_backend,
    )
    from cyberbrain.extractors.config import resolve_config as _resolve_config
    from cyberbrain.extractors.extractor import extract_beats as _extract_beats
    from cyberbrain.extractors.frontmatter import (
        parse_frontmatter as _parse_frontmatter,
    )
    from cyberbrain.extractors.run_log import RUNS_LOG_PATH, write_journal_entry
    from cyberbrain.extractors.transcript import parse_jsonl_transcript
    from cyberbrain.extractors.vault import write_beat
except ImportError as e:
    raise RuntimeError(
        f"Could not import cyberbrain extractors. "
        f"Ensure cyberbrain is installed: {e}. "
        "Run install.sh or ensure plugin is correctly installed."
    ) from e

# Search backend — lazy-loaded on first cb_recall call
_search_backend = None


def _get_search_backend(config: dict):
    """Return cached search backend, initialised lazily."""
    global _search_backend
    if _search_backend is None:
        try:
            from cyberbrain.extractors.search_backends import get_search_backend

            _search_backend = get_search_backend(config)
        except Exception:  # intentional: backend init failure (missing optional deps) is non-fatal; falls back to grep
            _search_backend = None
    return _search_backend


def _load_tool_prompt(filename: str) -> str:
    """Load a prompt file from the cyberbrain prompts directory.

    Search order:
    1. Primary location (relative to mcp/shared.py) — works in plugin mode
    2. Legacy location (~/.claude/cyberbrain/prompts) — for existing installs
    """
    from fastmcp.exceptions import ToolError

    # Primary: relative to this file's location (plugin cache or repo root)
    primary_path = _PROMPTS_DIR_PRIMARY / filename
    if primary_path.exists():
        return primary_path.read_text(encoding="utf-8")

    # Fallback: legacy installed location
    legacy_path = _PROMPTS_DIR_LEGACY / filename
    if legacy_path.exists():
        return legacy_path.read_text(encoding="utf-8")

    raise ToolError(
        f"Prompt file not found: {filename}. "
        "Checked: {} and {}. "
        "Run install.sh or ensure plugin is correctly installed.".format(
            primary_path, legacy_path
        )
    )


def _load_config(cwd: str = "") -> dict:
    return _resolve_config(cwd or str(Path.home()))


def _is_within_vault(vault: Path, target: Path) -> bool:
    """Return True if target path is within the vault directory."""
    try:
        target.resolve().relative_to(vault.resolve())
        return True
    except ValueError:
        return False


def _relpath(path: Path, vault_path: str) -> str:
    return os.path.relpath(str(path), vault_path)


def _move_to_trash(file_path: Path, vault: Path, config: dict) -> Path:
    """Move a file to the configured trash folder instead of deleting it.

    Preserves vault-relative folder structure inside the trash folder.
    Appends a numeric suffix to avoid clobbering existing files.
    Returns the destination path.
    """
    trash_rel = config.get("trash_folder", ".trash")
    trash_root = vault / trash_rel

    # Preserve folder structure relative to vault
    try:
        rel = file_path.resolve().relative_to(vault.resolve())
    except ValueError:
        rel = Path(file_path.name)

    dest = trash_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Avoid clobbering: append numeric suffix if dest exists
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        counter = 1
        while dest.exists():
            dest = dest.parent / f"{stem}_{counter}{suffix}"
            counter += 1

    file_path.rename(dest)
    return dest


def _prune_index(config: dict) -> int:
    """Remove index entries for notes no longer on disk. Returns count pruned."""
    backend = _get_search_backend(config)
    if backend is None or not hasattr(backend, "prune_stale_notes"):
        return 0
    try:
        return backend.prune_stale_notes() or 0  # type: ignore[reportAttributeAccessIssue]  # runtime duck-typed: hasattr guard above
    except (
        Exception
    ):  # intentional: prune failure is non-fatal; stale entries are harmless
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
        except (
            Exception
        ):  # intentional: per-path indexing failure is non-fatal; continue to next path
            pass
    return count
