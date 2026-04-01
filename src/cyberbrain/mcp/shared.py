"""Shared state and extractor imports for the cyberbrain MCP server."""

import os
from pathlib import Path

# Prompt directory resolution:
# 1. Primary: relative to this file (works in plugin cache via ${CLAUDE_PLUGIN_ROOT})
# 2. Fallback: legacy installed location for existing installs
_PROMPTS_DIR_PRIMARY = Path(__file__).parent.parent / "prompts"
from cyberbrain.extractors.state import prompts_dir_legacy as _prompts_dir_legacy
from cyberbrain.extractors.state import runs_log_path as _runs_log_path

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
    from cyberbrain.extractors.run_log import write_journal_entry
    from cyberbrain.extractors.transcript import parse_jsonl_transcript
    from cyberbrain.extractors.vault import (
        _is_within_vault,
        move_vault_note,
        update_vault_note,
        write_beat,
        write_vault_note,
    )
except ImportError as e:
    raise RuntimeError(
        f"Could not import cyberbrain extractors. "
        f"Ensure cyberbrain is installed: {e}. "
        "Run `uv sync` or install via `claude plugin install cyberbrain@devnill-cyberbrain`."
    ) from e

# Search backend — lazy-loaded on first cb_recall call
_search_backend = None


def _invalidate_search_backend() -> None:
    """Reset the cached search backend so the next call re-initialises it."""
    global _search_backend
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
    legacy_path = _prompts_dir_legacy() / filename
    if legacy_path.exists():
        return legacy_path.read_text(encoding="utf-8")

    raise ToolError(
        f"Prompt file not found: {filename}. "
        "Checked: {} and {}. "
        "Run `uv sync` or install via `claude plugin install cyberbrain@devnill-cyberbrain`.".format(
            primary_path, legacy_path
        )
    )


def _load_config(cwd: str = "") -> dict:
    from typing import cast

    return cast(dict, _resolve_config(cwd or str(Path.home())))


def require_config(cwd: str = "") -> dict:
    """Load config or raise ToolError with an actionable message if not configured.

    Checks performed (in order):
    1. Config file exists at ~/.claude/cyberbrain/config.json
    2. vault_path is set and is not a placeholder
    3. vault_path directory exists on disk

    Raises ToolError with a specific message for each failure mode.
    Returns the merged config dict (global + project) on success.
    """
    from fastmcp.exceptions import ToolError

    import cyberbrain.extractors.config as _config_mod

    cfg_path = _config_mod.GLOBAL_CONFIG_PATH

    # Check 1: config file exists
    if not cfg_path.exists():
        raise ToolError(
            "Cyberbrain is not configured. Run /cyberbrain:config to set up your vault."
        )

    # Load raw JSON (no sys.exit)
    import json as _json

    try:
        with open(cfg_path) as _f:
            raw = _json.load(_f)
    except (OSError, _json.JSONDecodeError) as _e:
        raise ToolError(
            f"Cyberbrain config is unreadable ({_e}). "
            "Run /cyberbrain:config to reconfigure your vault."
        )

    # Check 2: vault_path is set and not a placeholder
    vault_path_raw = raw.get("vault_path", "")
    _PLACEHOLDER = "/path/to/your/ObsidianVault"
    if not vault_path_raw:
        raise ToolError(
            "Cyberbrain is not configured. Run /cyberbrain:config to set up your vault."
        )
    if vault_path_raw == _PLACEHOLDER:
        raise ToolError(
            "vault_path is still the placeholder value. "
            "Run /cyberbrain:config to set your real vault path."
        )

    # Check 3: vault_path directory exists
    vault_resolved = Path(vault_path_raw).expanduser().resolve()
    if not vault_resolved.exists():
        raise ToolError(
            f"vault_path '{vault_path_raw}' does not exist on disk. "
            "Run /cyberbrain:config to update your vault path."
        )

    # Check 4: vault_path must not be home or root
    _home = Path.home().resolve()
    _root = Path("/").resolve()
    if vault_resolved == _home or vault_resolved == _root:
        raise ToolError(
            f"vault_path '{vault_path_raw}' must not be your home directory or filesystem root. "
            "Run /cyberbrain:config to set a valid vault path."
        )

    # Delegate final merge (global + project) to the standard loader
    from typing import cast

    try:
        return cast(dict, _resolve_config(cwd or str(Path.home())))
    except Exception as _ce:  # intentional: catch ConfigError or any config-loading failure
        raise ToolError(
            f"Cyberbrain config is invalid: {_ce}. "
            "Run /cyberbrain:config to reconfigure your vault."
        ) from _ce


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
