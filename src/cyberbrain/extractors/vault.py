"""
vault.py

Vault writing, routing, relation resolution, and search for cyberbrain.
"""

import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

from cyberbrain.extractors.state import config_path as _config_path

# ---------------------------------------------------------------------------
# Beat type and scope vocabulary
# ---------------------------------------------------------------------------

_DEFAULT_VALID_BEAT_TYPES = {"decision", "insight", "problem", "reference"}
_DEFAULT_VALID_ENTITY_TYPES = {"project", "note", "resource", "archived"}
VALID_SCOPES = {"project", "general"}

# Beat type → vault entity type mapping.
# Durable beats are reference material; working-memory beats are temporal captures.
_BEAT_TO_ENTITY_TYPE = {
    "decision": "resource",
    "insight": "resource",
    "problem": "note",
    "reference": "resource",
}


def _resolve_entity_type(beat_type: str, durability: str) -> str:
    """Map a beat type to a vault entity type based on durability."""
    if durability == "working-memory":
        return "note"
    return _BEAT_TO_ENTITY_TYPE.get(beat_type, "resource")


def parse_valid_types_from_claude_md(vault_claude_md_text: str) -> set:
    """
    Extract the entity type vocabulary from a vault CLAUDE.md.
    Looks for a ## Entity Types or ## Types section and reads subsection headings.
    Explicitly skips ## Beat Types sections (those are a separate vocabulary).
    Falls back to _DEFAULT_VALID_ENTITY_TYPES if nothing parseable is found.
    """
    if not vault_claude_md_text:
        return _DEFAULT_VALID_ENTITY_TYPES

    types: set = set()

    in_types_section = False
    for line in vault_claude_md_text.splitlines():
        stripped = line.strip()
        # Skip Beat Types sections — those define a separate vocabulary
        if re.match(
            r"^#{1,3}\s+beat\s+types?\s*$",
            stripped,
            re.IGNORECASE,
        ):
            in_types_section = False
            continue
        if re.match(
            r"^#{1,3}\s+(entity\s+types?|note\s+types?|types?)\s*$",
            stripped,
            re.IGNORECASE,
        ):
            in_types_section = True
            continue
        if in_types_section and re.match(r"^#{1,3}\s+\w", stripped):
            in_types_section = False
        if in_types_section:
            m = re.match(r"^#{2,4}\s+`?(\w[\w-]*)`?", stripped)
            if m:
                types.add(m.group(1).lower())
                continue
            for match in re.finditer(r"`(\w[\w-]+)`", stripped):
                candidate = match.group(1).lower()
                if 3 <= len(candidate) <= 20 and not candidate[0].isdigit():
                    types.add(candidate)

    if types:
        return types
    return _DEFAULT_VALID_ENTITY_TYPES


def read_vault_claude_md(vault_path: str) -> str | None:
    """Read the vault's CLAUDE.md file if it exists. Returns full text or None."""
    claude_md_path = Path(vault_path) / "CLAUDE.md"
    if claude_md_path.exists():
        try:
            return claude_md_path.read_text(encoding="utf-8")
        except OSError:
            return None
    return None


def get_valid_types(config: dict) -> set:
    """Return the valid entity types for this vault, read from vault CLAUDE.md if available."""
    vault_claude_md = read_vault_claude_md(config["vault_path"])
    if vault_claude_md:
        return parse_valid_types_from_claude_md(vault_claude_md)
    return _DEFAULT_VALID_ENTITY_TYPES


def get_valid_beat_types(config: dict) -> set:
    """Return the valid beat types (extraction vocabulary). Always the default set."""
    return _DEFAULT_VALID_BEAT_TYPES.copy()


# ---------------------------------------------------------------------------
# Filename and path helpers
# ---------------------------------------------------------------------------

_FILENAME_INVALID = re.compile(r'[<>:"/\\|?*#\[\]^\x00-\x1f]')


def make_filename(title: str) -> str:
    """Convert a title to a clean human-readable filename."""
    clean = _FILENAME_INVALID.sub("", title)
    clean = re.sub(r"\s+", " ", clean).strip()
    if len(clean) > 80:
        clean = clean[:80].rsplit(" ", 1)[0].strip()
    return clean + ".md"


def _is_within_vault(vault: Path, target: Path) -> bool:
    """Return True if target resolves to a path within vault."""
    try:
        target.resolve().relative_to(vault.resolve())
        return True
    except ValueError:
        return False


def resolve_output_dir(beat: dict, config: dict) -> Path | None:
    """
    Route a beat to the correct vault folder based on durability, scope, and project config.
    Returns the absolute directory path (created if needed), or None if inbox is not configured.
    """
    vault = Path(config["vault_path"])
    durability = beat.get("durability", "durable")

    if durability == "working-memory":
        wm_root = config.get("working_memory_folder", "AI/Working Memory")
        # Project-scoped WM beats get a project subfolder
        project_name = config.get("project_name", "")
        if beat.get("scope") == "project" and project_name:
            folder = f"{wm_root}/{project_name}"
        else:
            folder = wm_root
        output_dir = vault / folder
        if not _is_within_vault(vault, output_dir):
            print(
                f"[extract_beats] Path traversal rejected for working-memory folder: {folder!r}",
                file=sys.stderr,
            )
            output_dir = vault / wm_root
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    # Durable routing (existing logic)
    if beat.get("scope") == "project" and config.get("vault_folder"):
        folder = config["vault_folder"]
    elif config.get("inbox"):
        folder = config["inbox"]
    else:
        print(
            "[extract_beats] 'inbox' is not configured. "
            f"Set 'inbox' in {_config_path()} before writing beats.",
            file=sys.stderr,
        )
        return None
    output_dir = vault / folder
    # Validate resolved path stays within vault
    if not _is_within_vault(vault, output_dir):
        print(
            f"[extract_beats] Path traversal rejected in folder override: {folder!r} → {output_dir}",
            file=sys.stderr,
        )
        # Fall back to inbox
        inbox = config.get("inbox", "AI/Claude-Sessions")
        output_dir = vault / inbox
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# ---------------------------------------------------------------------------
# Relation resolution
# ---------------------------------------------------------------------------

# Controlled predicate vocabulary.
VALID_PREDICATES = {
    "related",
    "references",
    "causes",
    "caused-by",
    "supersedes",
    "implements",
    "contradicts",
}


def build_vault_titles_set(vault_path: str) -> set:
    """
    Return a set of note stems (filenames without .md extension) from the vault.
    Used for relation target validation. Built once per extraction run (~1ms).
    """
    vault = Path(vault_path)
    try:
        return {p.stem for p in vault.rglob("*.md")}
    except OSError:
        return set()


def resolve_relations(raw_relations: list, vault_titles: set) -> list:
    """
    Validate and normalise a beat's raw relation list.

    For each relation:
    - Normalise the predicate to VALID_PREDICATES; fall back to "related" if unknown.
    - Check the target title against vault_titles (case-insensitive).
    - Drop the relation if the target does not exist in the vault (no phantom nodes).

    Returns a list of dicts: [{type, target}, ...] with only validated targets.
    """
    if not raw_relations or not isinstance(raw_relations, list):
        return []

    lower_to_actual: dict = {t.lower(): t for t in vault_titles}

    resolved = []
    for rel in raw_relations:
        if not isinstance(rel, dict):
            continue
        predicate = str(rel.get("type", "related")).strip().lower()
        if predicate not in VALID_PREDICATES:
            predicate = "related"
        target = str(rel.get("target", "")).strip()
        if not target:
            continue
        if target.lower() not in lower_to_actual:
            print(
                f"[extract_beats] Dropping unresolved relation target: '{target}'",
                file=sys.stderr,
            )
            continue
        actual_title = lower_to_actual[target.lower()]
        resolved.append({"type": predicate, "target": actual_title})

    return resolved


# ---------------------------------------------------------------------------
# Vault search
# ---------------------------------------------------------------------------


def search_vault(beat: dict, vault_path: str, max_results: int = 5) -> list:
    """
    Search vault for files related to a beat by tags and title keywords.
    Returns up to max_results paths, ranked by keyword match count (most first),
    using file mtime as tiebreaker.
    """
    import subprocess

    terms = list(beat.get("tags", []))
    terms += [w for w in beat["title"].split() if len(w) >= 4][:5]
    terms = list(dict.fromkeys(terms))

    found_counts: dict = {}
    found_mtime: dict = {}

    for term in terms:
        result = subprocess.run(
            ["grep", "-r", "-l", "--include=*.md", "-i", term, vault_path],
            capture_output=True,
            text=True,
        )
        for path in result.stdout.strip().splitlines():
            if path:
                found_counts[path] = found_counts.get(path, 0) + 1
                if path not in found_mtime:
                    try:
                        found_mtime[path] = os.path.getmtime(path)
                    except OSError:
                        found_mtime[path] = 0.0

    ranked = sorted(
        found_counts.keys(),
        key=lambda p: (found_counts[p], found_mtime.get(p, 0.0)),
        reverse=True,
    )
    return ranked[:max_results]


# ---------------------------------------------------------------------------
# Beat writing
# ---------------------------------------------------------------------------


def inject_provenance(
    content: str,
    source: str,
    session_id: str | None,
    now: datetime,
    extra_fields: str | None = None,
) -> str:
    """
    Inject cb_ provenance fields into YAML frontmatter of a markdown content string.

    Used for LLM-generated content (autofile create) where we can't control
    what the model puts in frontmatter. Inserts fields before the closing ---.
    If no frontmatter is present, prepends a minimal one.

    extra_fields: optional additional YAML lines (e.g. WM fields) to append after provenance.
    """
    ts = now.strftime("%Y-%m-%dT%H:%M:%S")
    lines = [f"cb_source: {source}", f"cb_created: {ts}"]
    if session_id:
        lines.append(f"cb_session: {session_id}")
    if extra_fields:
        lines.extend(extra_fields.splitlines())

    if not content.startswith("---"):
        header = "---\n" + "\n".join(lines) + "\n---\n\n"
        return header + content

    end = content.find("\n---", 3)
    if end == -1:
        return content

    injection = "\n" + "\n".join(lines)
    return content[:end] + injection + content[end:]


def _wm_frontmatter_fields(beat: dict, config: dict, now: datetime) -> str:
    """Return additional YAML frontmatter lines for working-memory beats."""
    from datetime import timedelta

    ttl_config = config.get("working_memory_ttl", {})
    beat_type = beat.get("type", "")
    default_days = ttl_config.get(
        "default", config.get("working_memory_review_days", 28)
    )
    review_days = ttl_config.get(beat_type, default_days)
    review_after = (now + timedelta(days=review_days)).strftime("%Y-%m-%d")
    return f"cb_ephemeral: true\ncb_review_after: {review_after}"


_FOLDER_TO_DOMAIN: dict[str, str] = {
    "work": "work",
    "personal": "personal",
    "knowledge": "knowledge",
    "ai": "knowledge",
}


def _infer_domain_tag(output_dir: Path, vault_path: str) -> str | None:
    """Infer the domain tag from the output directory path within the vault."""
    vault = Path(vault_path)
    try:
        rel = output_dir.resolve().relative_to(vault.resolve())
    except ValueError:
        return None
    parts = rel.parts
    if not parts:
        return None
    return _FOLDER_TO_DOMAIN.get(parts[0].lower())


def write_beat(
    beat: dict,
    config: dict,
    session_id: str,
    cwd: str,
    now: datetime,
    vault_titles: set | None = None,
    source: str = "hook-extraction",
) -> Path | None:
    """Write a single beat to a markdown file. Returns the file path, or None if routing fails."""
    beat_type = beat.get("type", "reference")
    if beat_type not in _DEFAULT_VALID_BEAT_TYPES:
        beat_type = "reference"

    durability = beat.get("durability", "durable")

    # Map beat type to vault entity type
    entity_type = _resolve_entity_type(beat_type, durability)

    scope = beat.get("scope", "general")
    if scope not in VALID_SCOPES:
        scope = "general"

    title = beat.get("title", "Untitled").strip()
    summary = beat.get("summary", "").strip()
    tags = beat.get("tags", [])
    body = beat.get("body", "").strip()

    if not isinstance(tags, list):
        tags = []
    tags = [str(t).lower() for t in tags if t]

    if vault_titles is None:
        vault_titles = build_vault_titles_set(config["vault_path"])
    raw_relations = beat.get("relations", [])
    resolved_relations = resolve_relations(raw_relations, vault_titles)

    related_wikilinks = [f"[[{r['target']}]]" for r in resolved_relations]

    project_name = config.get("project_name", Path(cwd).name)
    date_str = now.strftime("%Y-%m-%dT%H:%M:%S")

    beat_id = str(uuid.uuid4())

    output_dir = resolve_output_dir(beat, config)
    if output_dir is None:
        return None

    # Inject domain tag based on output folder
    domain_tag = _infer_domain_tag(output_dir, config["vault_path"])
    if domain_tag and domain_tag not in tags:
        tags.insert(0, domain_tag)

    output_path = output_dir / make_filename(title)
    counter = 2
    while output_path.exists():
        output_path = output_dir / f"{counter} {make_filename(title)}"
        counter += 1

    wm_fields = ""
    if durability == "working-memory":
        wm_fields = "\n" + _wm_frontmatter_fields(beat, config, now)

    uncertain_routing_field = ""
    if "_autofile_low_confidence" in beat:
        confidence_val = beat["_autofile_low_confidence"]
        uncertain_routing_field = f"\ncb_uncertain_routing: {confidence_val:.2f}"

    status = "active"

    # Use json.dumps for all string fields to safely handle quotes, colons,
    # and special chars. JSON string syntax is valid YAML scalar syntax.
    front_matter = f"""---
id: {beat_id}
date: {date_str}
session_id: {json.dumps(session_id)}
type: {json.dumps(entity_type)}
beat_type: {json.dumps(beat_type)}
scope: {json.dumps(scope)}
title: {json.dumps(title)}
project: {json.dumps(project_name)}
cwd: {json.dumps(cwd)}
tags: {json.dumps(tags)}
related: {json.dumps(related_wikilinks)}
status: {json.dumps(status)}
summary: {json.dumps(summary)}
cb_source: {json.dumps(source)}
cb_created: {date_str}{wm_fields}{uncertain_routing_field}
---"""

    relations_section = ""
    if resolved_relations:
        rel_lines = []
        for r in resolved_relations:
            rel_lines.append(f"- {r['type']}: [[{r['target']}]]")
        relations_section = "\n\n## Relations\n\n" + "\n".join(rel_lines)

    content = f"{front_matter}\n\n## {title}\n\n{body}{relations_section}\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    # Update search index (FTS5/hybrid) post-write
    from cyberbrain.extractors.search_index import update_search_index

    update_search_index(
        str(output_path),
        {
            "id": beat_id,
            "title": title,
            "summary": summary,
            "tags": tags,
            "related": related_wikilinks,
            "type": entity_type,
            "beat_type": beat_type,
            "scope": scope,
            "project": project_name,
            "date": date_str,
        },
        config,
    )

    return output_path


# ---------------------------------------------------------------------------
# Vault write abstraction layer
# ---------------------------------------------------------------------------


def _is_within_vault_check(vault: Path, target: Path) -> None:
    """Raise ValueError if target is not within vault."""
    if not _is_within_vault(vault, target):
        raise ValueError(f"Path {target} is not within vault {vault}")


def write_vault_note(path: Path, content: str, vault_path: str) -> Path:
    """Write content to path within vault, creating parent dirs as needed."""
    vault = Path(vault_path)
    _is_within_vault_check(vault, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def update_vault_note(path: Path, content: str, vault_path: str) -> Path:
    """Overwrite an existing vault note with new content."""
    vault = Path(vault_path)
    _is_within_vault_check(vault, path)
    if not path.exists():
        raise FileNotFoundError(f"Note does not exist: {path}")
    path.write_text(content, encoding="utf-8")
    return path


def move_vault_note(src: Path, dest: Path, vault_path: str) -> Path:
    """Move a vault note from src to dest within the vault."""
    vault = Path(vault_path)
    _is_within_vault_check(vault, src)
    _is_within_vault_check(vault, dest)
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dest)
    return dest
