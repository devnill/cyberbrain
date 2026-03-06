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

from config import GLOBAL_CONFIG_PATH


# ---------------------------------------------------------------------------
# Beat type and scope vocabulary
# ---------------------------------------------------------------------------

_DEFAULT_VALID_TYPES = {"decision", "insight", "problem", "reference"}
VALID_SCOPES = {"project", "general"}


def parse_valid_types_from_claude_md(vault_claude_md_text: str) -> set:
    """
    Extract the type vocabulary from a vault CLAUDE.md.
    Looks for a ## Entity Types or ## Types section and reads subsection headings.
    Falls back to _DEFAULT_VALID_TYPES if nothing parseable is found.
    """
    if not vault_claude_md_text:
        return _DEFAULT_VALID_TYPES

    types: set = set()

    in_types_section = False
    for line in vault_claude_md_text.splitlines():
        stripped = line.strip()
        if re.match(r'^#{1,3}\s+(entity\s+types?|beat\s+types?|note\s+types?|types?)\s*$', stripped, re.IGNORECASE):
            in_types_section = True
            continue
        if in_types_section and re.match(r'^#{1,3}\s+\w', stripped):
            in_types_section = False
        if in_types_section:
            m = re.match(r'^#{2,4}\s+`?(\w[\w-]*)`?', stripped)
            if m:
                types.add(m.group(1).lower())
                continue
            for match in re.finditer(r'`(\w[\w-]+)`', stripped):
                candidate = match.group(1).lower()
                if 3 <= len(candidate) <= 20 and not candidate[0].isdigit():
                    types.add(candidate)

    if types:
        return types
    return _DEFAULT_VALID_TYPES


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
    """Return the valid beat types for this vault, read from vault CLAUDE.md if available."""
    vault_claude_md = read_vault_claude_md(config["vault_path"])
    if vault_claude_md:
        return parse_valid_types_from_claude_md(vault_claude_md)
    return _DEFAULT_VALID_TYPES


# ---------------------------------------------------------------------------
# Filename and path helpers
# ---------------------------------------------------------------------------

_FILENAME_INVALID = re.compile(r'[<>:"/\\|?*#\[\]^\x00-\x1f]')


def make_filename(title: str) -> str:
    """Convert a title to a clean human-readable filename."""
    clean = _FILENAME_INVALID.sub('', title)
    clean = re.sub(r'\s+', ' ', clean).strip()
    if len(clean) > 80:
        clean = clean[:80].rsplit(' ', 1)[0].strip()
    return clean + '.md'


def _is_within_vault(vault: Path, target: Path) -> bool:
    """Return True if target resolves to a path within vault."""
    try:
        target.resolve().relative_to(vault.resolve())
        return True
    except ValueError:
        return False


def resolve_output_dir(beat: dict, config: dict) -> Path | None:
    """
    Route a beat to the correct vault folder based on scope and project config.
    Returns the absolute directory path (created if needed), or None if inbox is not configured.
    """
    vault = Path(config["vault_path"])
    if beat.get("scope") == "project" and config.get("vault_folder"):
        folder = config["vault_folder"]
    elif config.get("inbox"):
        folder = config["inbox"]
    else:
        print(
            "[extract_beats] 'inbox' is not configured. "
            f"Set 'inbox' in {GLOBAL_CONFIG_PATH} before writing beats.",
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

# Controlled predicate vocabulary grounded in SKOS / Dublin Core / PROV-O.
VALID_PREDICATES = {"related", "references", "broader", "narrower", "supersedes", "wasDerivedFrom"}


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
            capture_output=True, text=True
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

def write_beat(beat: dict, config: dict, session_id: str, cwd: str, now: datetime,
               vault_titles: set | None = None) -> Path:
    """Write a single beat to a markdown file. Returns the file path."""
    valid_types = get_valid_types(config)
    beat_type = beat.get("type", "reference")
    if beat_type not in valid_types:
        beat_type = "reference"

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

    output_path = output_dir / make_filename(title)
    counter = 2
    while output_path.exists():
        output_path = output_dir / f"{counter} {make_filename(title)}"
        counter += 1

    # Use json.dumps for string fields to safely handle quotes and special chars.
    # JSON string syntax is valid YAML scalar syntax.
    front_matter = f"""---
id: {beat_id}
date: {date_str}
session_id: {session_id}
type: {beat_type}
scope: {scope}
title: {json.dumps(title)}
project: {project_name}
cwd: {cwd}
tags: {json.dumps(tags)}
related: {json.dumps(related_wikilinks)}
status: completed
summary: {json.dumps(summary)}
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

    # Update search index (FTS5/hybrid) post-write; non-fatal on failure
    try:
        from search_index import update_search_index
        update_search_index(str(output_path), {
            "id": beat_id,
            "title": title,
            "summary": summary,
            "tags": tags,
            "related": related_wikilinks,
            "type": beat_type,
            "scope": scope,
            "project": project_name,
            "date": date_str,
        }, config)
    except ImportError:
        pass  # search_index.py not yet installed; silent skip

    return output_path
