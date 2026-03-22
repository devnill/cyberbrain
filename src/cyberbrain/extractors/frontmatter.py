"""
frontmatter.py

Canonical YAML frontmatter helpers for cyberbrain.

Consolidates four previously duplicated implementations from:
- extractors/extract_beats.py (_read_frontmatter_as_dict, _read_frontmatter_tags)
- extractors/search_backends.py (_read_frontmatter, _normalise_list, _derive_id)
- mcp/server.py (_parse_frontmatter)
"""

import json
import re
from pathlib import Path


def parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter fields from a markdown content string. Returns empty dict on any error."""
    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end == -1:
        return {}
    try:
        import yaml

        fm = yaml.safe_load(content[3:end])
        return fm if isinstance(fm, dict) else {}
    except yaml.YAMLError:
        return {}


def read_frontmatter(path: str) -> dict:
    """Read YAML frontmatter from a markdown file path. Returns empty dict on any error."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return {}
    return parse_frontmatter(text)


def read_frontmatter_tags(path) -> set:
    """Read the tags field from YAML frontmatter of a markdown file. Returns a set of lowercase strings."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return set()

    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return set()

    frontmatter_block = m.group(1)

    tags_match = re.search(r"^tags:\s*(.+)$", frontmatter_block, re.MULTILINE)
    if not tags_match:
        return set()

    tags_raw = tags_match.group(1).strip()

    # Try JSON array first (our write format)
    try:
        tags_list = json.loads(tags_raw)
        if isinstance(tags_list, list):
            return {str(t).lower() for t in tags_list if t}
    except (json.JSONDecodeError, ValueError):
        pass

    # Try YAML-style bracketed list: ["tag1", "tag2"] or [tag1, tag2]
    m2 = re.match(r"^\[(.*)\]$", tags_raw)
    if m2:
        inner = m2.group(1)
        parts = [p.strip().strip("\"'") for p in inner.split(",")]
        return {p.lower() for p in parts if p}

    return set()


def normalise_list(value) -> list:
    """Coerce a frontmatter list value (may be JSON string or Python list) to list[str]."""
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(v) for v in parsed if v]
        except (json.JSONDecodeError, ValueError):
            pass
        return [value] if value.strip() else []
    return []


def derive_id(note_path: str) -> str:
    """Derive a stable ID from path when no UUID is in frontmatter."""
    import hashlib

    return hashlib.sha256(note_path.encode()).hexdigest()[:36]
