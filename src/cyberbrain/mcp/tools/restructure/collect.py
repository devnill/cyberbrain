"""Note collection helpers for cb_restructure."""

import json
import re
from pathlib import Path

from cyberbrain.mcp.shared import _parse_frontmatter

_PREFS_HEADING = "## Cyberbrain Preferences"
_LOCK_FIELD = "cb_lock"


def _is_locked(content: str) -> bool:
    """Return True if the note has cb_lock: true in frontmatter."""
    fm = _parse_frontmatter(content)
    return bool(fm.get(_LOCK_FIELD))


def _read_vault_prefs(vault_path: str) -> str:
    """Return the Cyberbrain Preferences section from vault CLAUDE.md, or empty string."""
    claude_md = Path(vault_path) / "CLAUDE.md"
    if not claude_md.exists():
        return ""
    text = claude_md.read_text(encoding="utf-8")
    idx = text.find(_PREFS_HEADING)
    if idx == -1:
        return ""
    rest = text[idx:]
    end_match = None
    for m in re.finditer(r"^## ", rest, re.MULTILINE):
        if m.start() > 0:
            end_match = m.start()
            break
    return rest[:end_match].strip() if end_match else rest.strip()


def _collect_notes(
    scan_root: Path,
    vault: Path,
    excluded_folders: list[str],
    exclude_paths: set[Path] | None = None,
    shallow: bool = False,
) -> list[dict]:
    """Collect all eligible notes from scan_root. Returns list of note dicts.

    shallow=True: only collect notes directly inside scan_root, not in subdirectories.
    Use this in folder_hub mode so existing subfolders are left undisturbed.
    """
    notes = []
    glob_pattern = "*.md" if shallow else "**/*.md"
    for path in sorted(scan_root.glob(glob_pattern)):
        # Skip hidden dirs
        if any(part.startswith(".") for part in path.relative_to(vault).parts):
            continue
        # Skip excluded folders
        rel_parts = [p.lower() for p in path.relative_to(vault).parts[:-1]]
        if any(excl.lower() in rel_parts for excl in excluded_folders):
            continue
        # Skip explicitly excluded paths (e.g. existing hub)
        if exclude_paths and path.resolve() in exclude_paths:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _is_locked(content):
            continue

        fm = _parse_frontmatter(content)
        title = fm.get("title") or path.stem
        summary = fm.get("summary", "")
        tags = fm.get("tags", [])
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, ValueError):
                tags = []
        if not isinstance(tags, list):
            tags = []

        notes.append(
            {
                "path": path,
                "title": str(title),
                "summary": str(summary),
                "tags": [str(t) for t in tags],
                "content": content,
                "rel_path": str(path.relative_to(vault)),
            }
        )
    return notes


def _collect_notes_for_hub(
    scan_root: Path,
    vault: Path,
    excluded_folders: list[str],
    exclude_paths: set[Path] | None = None,
) -> list[dict]:
    """Collect notes for hub creation in folder_hub mode.

    Returns:
    - All .md files directly in scan_root (flat notes)
    - The best representative hub note from each immediate subdirectory
      (prefers index.md, then the note whose stem matches the subfolder name,
       then the first .md found)

    This gives the LLM enough context to write a useful top-level hub without
    overwhelming it with every individual note inside subfolders.
    """
    flat_notes = _collect_notes(
        scan_root, vault, excluded_folders, exclude_paths=exclude_paths, shallow=True
    )

    # Add one representative note from each immediate subdirectory
    subfolder_notes = []
    for subdir in sorted(scan_root.iterdir()):
        if not subdir.is_dir() or subdir.name.startswith("."):
            continue
        rel_parts = [p.lower() for p in subdir.relative_to(vault).parts]
        if any(excl.lower() in rel_parts for excl in excluded_folders):
            continue
        candidates = sorted(subdir.glob("*.md"))
        if not candidates:
            continue
        # Prefer index.md, then note matching subfolder name, then first found
        chosen = None
        for c in candidates:
            if c.stem.lower() == "index":
                chosen = c
                break
        if chosen is None:
            for c in candidates:
                if c.stem.lower() == subdir.name.lower():
                    chosen = c
                    break
        if chosen is None:
            chosen = candidates[0]
        try:
            content = chosen.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _is_locked(content):
            continue
        fm = _parse_frontmatter(content)
        title = fm.get("title") or chosen.stem
        summary = fm.get("summary", f"Notes in the {subdir.name} subfolder.")
        tags = fm.get("tags", [])
        if isinstance(tags, str):
            tags = []
        if not isinstance(tags, list):
            tags = []
        subfolder_notes.append(
            {
                "path": chosen,
                "title": str(title),
                "summary": str(summary),
                "tags": [str(t) for t in tags],
                "content": content,
                "rel_path": str(chosen.relative_to(vault)),
            }
        )

    return flat_notes + subfolder_notes


def _find_split_candidates(
    notes: list[dict], clustered_paths: set[str], min_size: int
) -> list[dict]:
    """Return notes that are large enough to be worth splitting.

    Excludes notes already in a cluster (those are handled by merge/hub-spoke).
    """
    return [
        n
        for n in notes
        if str(n["path"]) not in clustered_paths and len(n["content"]) >= min_size
    ]
