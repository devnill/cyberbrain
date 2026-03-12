#!/usr/bin/env python3
"""
analyze_vault.py — Obsidian vault structure analyzer

Walks an Obsidian vault and produces a JSON report covering:
- Directory structure
- Frontmatter field usage (fields, values, frequencies)
- Tag usage (all tags, frequencies, hierarchies)
- Wikilink patterns (most-linked nodes, orphan detection)
- Entity type distribution (from `type` frontmatter field)
- Domain distribution (from `domain` frontmatter field)
- Naming conventions (case, separators, folder usage)
- Sample notes per entity type

Usage:
    python analyze_vault.py <vault_path> [--max-samples N] [--output path.json]

Output: JSON printed to stdout (or file if --output is given)
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from cyberbrain.extractors.frontmatter import parse_frontmatter


# ── helpers ──────────────────────────────────────────────────────────────────

def extract_wikilinks(text: str) -> list[str]:
    """Extract all [[wikilink]] targets from markdown text."""
    # Remove frontmatter first
    body = re.sub(r"^---.*?---\n", "", text, flags=re.DOTALL)
    links = re.findall(r"\[\[([^\]|#]+?)(?:\|[^\]]*)?\]\]", body)
    return [l.strip() for l in links]


def extract_inline_tags(text: str) -> list[str]:
    """Extract #tags from markdown body (not frontmatter)."""
    body = re.sub(r"^---.*?---\n", "", text, flags=re.DOTALL)
    return re.findall(r"(?<!\S)#([a-zA-Z][a-zA-Z0-9/_-]+)", body)


def note_name_style(stem: str) -> str:
    """Classify the naming style of a note filename stem."""
    if "-" in stem and stem == stem.lower():
        return "kebab-case"
    if "_" in stem:
        return "snake_case"
    if stem[0].isupper() and " " not in stem:
        return "PascalCase"
    if " " in stem:
        return "Title Case"
    return "other"


# ── main analysis ─────────────────────────────────────────────────────────────

def analyze_vault(vault_path: str, max_samples: int = 3) -> dict:
    root = Path(vault_path).expanduser().resolve()
    if not root.exists():
        raise ValueError(f"vault path does not exist: {root}")

    # Exclude hidden directories (.obsidian, .trash, etc.)
    md_files = [
        f for f in root.rglob("*.md")
        if not any(part.startswith(".") for part in f.relative_to(root).parts)
    ]
    total_notes = len(md_files)

    # ── per-note data ──
    frontmatter_fields: Counter = Counter()          # field name → count of notes using it
    field_values: dict[str, Counter] = defaultdict(Counter)  # field → value → count
    tag_counter: Counter = Counter()
    link_counter: Counter = Counter()                # target note name → incoming link count
    # note: outgoing_links tracks which notes have any outgoing links;
    # the dict values aren't used in the report but the keys are (via the else branch)
    outgoing_links: dict[str, list] = {}
    type_to_samples: dict[str, list] = defaultdict(list)  # entity type → sample paths
    naming_styles: Counter = Counter()
    folder_depth_dist: Counter = Counter()
    orphans: list[str] = []
    notes_with_no_links: list[str] = []

    linked_notes: set[str] = set()

    for md in md_files:
        rel = md.relative_to(root)
        stem = md.stem
        text = md.read_text(encoding="utf-8", errors="replace")

        # folder depth (0 = vault root)
        depth = len(rel.parts) - 1
        folder_depth_dist[depth] += 1

        # naming style
        naming_styles[note_name_style(stem)] += 1

        # frontmatter
        fm = parse_frontmatter(text)
        for field, val in fm.items():
            frontmatter_fields[field] += 1
            if isinstance(val, list):
                for v in val:
                    # strip wikilink syntax for value counting
                    clean = re.sub(r"\[\[([^\]]+)\]\]", r"\1", str(v)).strip()
                    if clean:
                        field_values[field][clean] += 1
            elif val is not None:
                field_values[field][str(val)] += 1

        # collect samples per type
        entity_type = fm.get("type", "")
        if entity_type and len(type_to_samples[entity_type]) < max_samples:
            type_to_samples[entity_type].append(str(rel))

        # tags from frontmatter
        fm_tags = fm.get("tags", [])
        if isinstance(fm_tags, str):
            fm_tags = [t.strip() for t in fm_tags.split(",")]
        elif not isinstance(fm_tags, list):
            fm_tags = []
        for tag in fm_tags:
            tag = str(tag).strip().lstrip("#")
            if tag:
                tag_counter[tag] += 1

        # inline tags
        for tag in extract_inline_tags(text):
            tag_counter[tag] += 1

        # wikilinks
        links = extract_wikilinks(text)
        if links:
            outgoing_links[stem] = links
            for link in links:
                # normalize: take last path component, strip extension
                # note: this matches on stem only, so two notes with the same
                # stem in different folders will share incoming link counts
                target = Path(link).stem
                link_counter[target] += 1
                linked_notes.add(target.lower())
        else:
            notes_with_no_links.append(str(rel))

    # orphan detection: notes that have no incoming links
    for md in md_files:
        if md.stem.lower() not in linked_notes:
            orphans.append(str(md.relative_to(root)))

    # ── folder structure ──
    folders: dict = {}
    for md in md_files:
        rel = md.relative_to(root)
        parts = rel.parts
        if len(parts) > 1:
            top_folder = parts[0]
            folders[top_folder] = folders.get(top_folder, 0) + 1

    # ── tag hierarchy ──
    tag_hierarchy: dict[str, list] = defaultdict(list)
    for tag in tag_counter:
        if "/" in tag:
            parent = tag.rsplit("/", 1)[0]
            tag_hierarchy[parent].append(tag)

    # ── entity type distribution ──
    type_dist = {k: v for k, v in field_values.get("type", Counter()).items()}

    # ── domain distribution ──
    domain_dist = {k: v for k, v in field_values.get("domain", Counter()).items()}

    # ── status distribution ──
    status_dist = {k: v for k, v in field_values.get("status", Counter()).items()}

    # ── top fields ──
    top_fields = [
        {"field": f, "note_count": c, "top_values": dict(field_values[f].most_common(8))}
        for f, c in frontmatter_fields.most_common(30)
    ]

    # ── top tags ──
    top_tags = [{"tag": t, "count": c} for t, c in tag_counter.most_common(40)]

    # ── most linked notes (likely hub nodes) ──
    hub_nodes = [{"note": n, "incoming_links": c} for n, c in link_counter.most_common(20)]

    # ── build report ──
    report = {
        "vault_path": str(root),
        "total_notes": total_notes,
        "folder_structure": {
            "top_level_folders": dict(sorted(folders.items(), key=lambda x: -x[1])),
            "depth_distribution": dict(folder_depth_dist),
        },
        "naming_conventions": dict(naming_styles),
        "entity_types": {
            "distribution": type_dist,
            "samples": {k: v for k, v in type_to_samples.items()},
        },
        "domains": domain_dist,
        "statuses": status_dist,
        "frontmatter": {
            "field_usage": top_fields,
        },
        "tags": {
            "top_tags": top_tags,
            "hierarchy": {k: v for k, v in tag_hierarchy.items()},
            "total_unique_tags": len(tag_counter),
        },
        "links": {
            "hub_nodes": hub_nodes,
            "notes_with_no_outgoing_links": len(notes_with_no_links),
            "notes_with_no_incoming_links": len(orphans),
            "orphan_sample": orphans[:10],
        },
    }

    return report


def main():
    parser = argparse.ArgumentParser(description="Analyze an Obsidian vault structure")
    parser.add_argument("vault_path", help="Path to the Obsidian vault root")
    parser.add_argument("--max-samples", type=int, default=3, help="Max sample notes per entity type")
    parser.add_argument("--output", help="Write JSON to this file instead of stdout")
    args = parser.parse_args()

    try:
        report = analyze_vault(args.vault_path, args.max_samples)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    output = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(output)
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
