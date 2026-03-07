"""cb_restructure tool — split large notes and merge clusters of related notes to keep the vault clean."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from shared import _load_config, _get_search_backend, _parse_frontmatter, _prune_index, _index_paths

_PROMPTS_DIR = Path.home() / ".claude" / "cyberbrain" / "prompts"
_PREFS_HEADING = "## Cyberbrain Preferences"
_LOCK_FIELD = "cb_lock"


def _load_prompt(filename: str) -> str:
    prompt_path = _PROMPTS_DIR / filename
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    dev_path = Path(__file__).parent.parent.parent / "prompts" / filename
    if dev_path.exists():
        return dev_path.read_text(encoding="utf-8")
    raise ToolError(
        f"Prompt file not found: {filename}. "
        "Run install.sh to ensure all prompt files are installed."
    )


def _repair_json(raw: str) -> list:
    """Try to parse raw as JSON array, with lightweight repair on failure."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try extracting complete JSON objects from a partial/truncated array
    repaired = raw.strip()
    if not repaired.startswith("["):
        repaired = "[" + repaired
    # Close any unclosed brackets/braces
    opens = repaired.count("{") - repaired.count("}")
    closes = repaired.count("[") - repaired.count("]")
    if opens > 0:
        repaired += "}" * opens
    if closes > 0:
        repaired += "]" * closes
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Last resort: extract all complete {...} objects from the string
    objects = []
    depth = 0
    start = None
    for i, ch in enumerate(raw):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    obj = json.loads(raw[start:i + 1])
                    objects.append(obj)
                except json.JSONDecodeError:
                    pass
                start = None
    if objects:
        return objects

    raise json.JSONDecodeError("Could not repair JSON", raw, 0)


_REQUIRED_FM_FIELDS = ("type", "summary", "tags")


def _validate_frontmatter(content: str, label: str) -> list[str]:
    """Return warning strings for any required frontmatter fields missing from content."""
    if not content.startswith("---"):
        return [f"  Warning: {label} — no YAML frontmatter found"]
    fm = _parse_frontmatter(content)
    missing = [f for f in _REQUIRED_FM_FIELDS if not fm.get(f)]
    if missing:
        return [f"  Warning: {label} — frontmatter missing: {', '.join(missing)}"]
    return []


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


def _is_locked(content: str) -> bool:
    """Return True if the note has cb_lock: true in frontmatter."""
    fm = _parse_frontmatter(content)
    return bool(fm.get(_LOCK_FIELD))


def _collect_notes(scan_root: Path, vault: Path, excluded_folders: list[str],
                   exclude_paths: set[Path] | None = None,
                   shallow: bool = False) -> list[dict]:
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
            except Exception:
                tags = []
        if not isinstance(tags, list):
            tags = []

        notes.append({
            "path": path,
            "title": str(title),
            "summary": str(summary),
            "tags": [str(t) for t in tags],
            "content": content,
            "rel_path": str(path.relative_to(vault)),
        })
    return notes



def _collect_notes_for_hub(scan_root: Path, vault: Path, excluded_folders: list[str],
                           exclude_paths: set[Path] | None = None) -> list[dict]:
    """Collect notes for hub creation in folder_hub mode.

    Returns:
    - All .md files directly in scan_root (flat notes)
    - The best representative hub note from each immediate subdirectory
      (prefers index.md, then the note whose stem matches the subfolder name,
       then the first .md found)

    This gives the LLM enough context to write a useful top-level hub without
    overwhelming it with every individual note inside subfolders.
    """
    flat_notes = _collect_notes(scan_root, vault, excluded_folders,
                                exclude_paths=exclude_paths, shallow=True)

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
        subfolder_notes.append({
            "path": chosen,
            "title": str(title),
            "summary": str(summary),
            "tags": [str(t) for t in tags],
            "content": content,
            "rel_path": str(chosen.relative_to(vault)),
        })

    return flat_notes + subfolder_notes


def _title_concept_clusters(notes: list[dict], min_cluster_size: int) -> list[list[dict]]:
    """
    Group notes by the primary distinctive concept word in their title.

    Better than search-based clustering for folder_hub mode because:
    - Notes within a folder are already topically related; what matters is which
      sub-topic each note covers (hooks vs plugins vs skills, etc.)
    - Content similarity is noisy — hook docs mention plugins, plugin docs mention
      hooks — creating false cross-group adjacency
    - Title words are the most intentional signal about what a note is primarily about

    Simple stemming: "hook" and "hooks" map to the same group.
    """
    _STOP = {"claude", "code", "the", "and", "for", "with", "using", "how",
             "what", "why", "non", "vs", "ai", "its", "are", "can", "via",
             "has", "that", "this", "from", "into", "not", "but"}

    def _stem(word: str) -> str:
        """Strip trailing 's' for simple plural normalization."""
        return word[:-1] if word.endswith("s") and len(word) > 3 else word

    # Map each note to its primary concept (first non-stop title word, stemmed)
    # Also track all title words per note for singleton fallback.
    concept_to_indices: dict[str, list[int]] = {}
    note_words: dict[int, list[str]] = {}
    for i, note in enumerate(notes):
        words = [_stem(w.lower()) for w in re.sub(r"[^\w\s]", " ", note["title"]).split()
                 if len(w) > 2 and w.lower() not in _STOP]
        if not words:
            continue
        note_words[i] = words
        concept_to_indices.setdefault(words[0], []).append(i)

    # Second pass: reassign singletons to an existing group if they share a
    # secondary title word with that group (e.g. "SessionEnd Hook" → hooks group).
    for concept in list(concept_to_indices.keys()):
        if len(concept_to_indices.get(concept, [])) == 1:
            i = concept_to_indices[concept][0]
            for word in note_words.get(i, [])[1:]:
                if word in concept_to_indices and len(concept_to_indices[word]) >= 1:
                    concept_to_indices[word].append(i)
                    del concept_to_indices[concept]
                    break

    clusters = []
    for indices in concept_to_indices.values():
        if len(indices) >= min_cluster_size:
            clusters.append([notes[i] for i in indices])

    return sorted(clusters, key=len, reverse=True)

def _build_clusters(notes: list[dict], backend, similarity_threshold: float, min_cluster_size: int) -> list[list[dict]]:
    """
    Build clusters of related notes using the search backend.

    For each note, searches for similar notes. Builds an adjacency graph and
    finds connected components. Returns clusters with >= min_cluster_size notes.
    """
    if backend is None:
        # Fallback: tag-based clustering when no search backend available
        return _tag_based_clusters(notes, min_cluster_size)

    # Build path -> note index map
    path_to_idx = {str(n["path"]): i for i, n in enumerate(notes)}
    note_paths = set(path_to_idx.keys())

    # Scale top_k to the folder size. A fixed small top_k misses local connections
    # when the global index has many unrelated notes ranked above folder peers.
    top_k = max(8, len(notes))

    # Adjacency set: pairs of note indices that are similar
    adjacency: dict[int, set[int]] = {i: set() for i in range(len(notes))}

    # Common words that appear in almost every note title in a folder and
    # carry no discriminating signal for clustering purposes.
    _STOP = {"claude", "code", "the", "and", "for", "with", "using",
             "how", "what", "why", "non", "vs"}

    # edge_weight[i][j] = number of per-word searches where note i found note j.
    # Requiring weight >= 2 avoids false adjacency through incidental shared words.
    edge_weight: dict[int, dict[int, int]] = {i: {} for i in range(len(notes))}

    for i, note in enumerate(notes):
        # Search for each distinctive word individually (single-term FTS5 query =
        # "contains this word"). Count how many of note i's searches return note j
        # to measure how strongly they are related.
        all_text = f"{note['title']} {note['summary']} {' '.join(note['tags'])}"
        words = [w.lower() for w in re.sub(r"[^\w\s]", " ", all_text).split()
                 if len(w) > 2 and w.lower() not in _STOP]
        seen: set[str] = set()
        unique_words = [w for w in words if not (w in seen or seen.add(w))][:6]  # type: ignore[func-returns-value]

        for word in unique_words:
            try:
                for result in backend.search(word, top_k=top_k):
                    rp = str(result.path)
                    if rp != str(note["path"]) and rp in note_paths and result.score > 0:
                        j = path_to_idx[rp]
                        edge_weight[i][j] = edge_weight[i].get(j, 0) + 1
            except Exception:
                continue

    # Build adjacency from strong edges only.
    # A pair is adjacent if EITHER note found the other in >= 2 of its per-word searches.
    for i in range(len(notes)):
        for j, w in edge_weight[i].items():
            if w >= 2 or edge_weight[j].get(i, 0) >= 2:
                adjacency[i].add(j)
                adjacency[j].add(i)

    # Find connected components
    visited = set()
    clusters = []
    for start in range(len(notes)):
        if start in visited:
            continue
        # BFS
        component = []
        queue = [start]
        while queue:
            node = queue.pop()
            if node in visited:
                continue
            visited.add(node)
            component.append(node)
            for neighbor in adjacency[node]:
                if neighbor not in visited:
                    queue.append(neighbor)
        if len(component) >= min_cluster_size:
            clusters.append([notes[i] for i in component])

    return clusters


def _tag_based_clusters(notes: list[dict], min_cluster_size: int) -> list[list[dict]]:
    """
    Simple tag-based clustering fallback when no search backend is available.
    Groups notes that share 2+ tags.
    """
    from collections import defaultdict
    tag_to_notes: dict[str, list[int]] = defaultdict(list)
    for i, note in enumerate(notes):
        for tag in note["tags"]:
            tag_to_notes[tag.lower()].append(i)

    adjacency: dict[int, set[int]] = {i: set() for i in range(len(notes))}
    pair_shared: dict[tuple, int] = {}
    for tag, idxs in tag_to_notes.items():
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                pair = (idxs[a], idxs[b])
                pair_shared[pair] = pair_shared.get(pair, 0) + 1

    for (a, b), count in pair_shared.items():
        if count >= 2:
            adjacency[a].add(b)
            adjacency[b].add(a)

    visited = set()
    clusters = []
    for start in range(len(notes)):
        if start in visited:
            continue
        component = []
        queue = [start]
        while queue:
            node = queue.pop()
            if node in visited:
                continue
            visited.add(node)
            component.append(node)
            for neighbor in adjacency[node]:
                if neighbor not in visited:
                    queue.append(neighbor)
        if len(component) >= min_cluster_size:
            clusters.append([notes[i] for i in component])

    return clusters


def _find_split_candidates(notes: list[dict], clustered_paths: set[str], min_size: int) -> list[dict]:
    """
    Return notes that are large enough to be worth splitting.

    Excludes notes already in a cluster (those are handled by merge/hub-spoke).
    """
    return [
        n for n in notes
        if str(n["path"]) not in clustered_paths and len(n["content"]) >= min_size
    ]


def _format_cluster_block(clusters: list[list[dict]], vault: Path) -> str:
    """Format clusters for the LLM prompt."""
    if not clusters:
        return "_No clusters found._"
    parts = []
    for idx, cluster in enumerate(clusters):
        lines = [f"### Cluster {idx} ({len(cluster)} notes)\n"]
        for note in cluster:
            lines.append(f"**{note['title']}** — `{note['rel_path']}`")
            if note["summary"]:
                lines.append(f"Summary: {note['summary']}")
            if note["tags"]:
                lines.append(f"Tags: {', '.join(note['tags'])}")
            content_body = note["content"]
            if len(content_body) > 600:
                content_body = content_body[:600] + "\n...[truncated]"
            lines.append(f"\n```\n{content_body}\n```\n")
        parts.append("\n".join(lines))
    return "\n---\n\n".join(parts)


def _format_folder_hub_block(notes: list[dict], vault: Path, hub_path: str = "",
                              existing_hub: str = "") -> str:
    """
    Format all folder notes as a single hub-spoke cluster.

    Uses titles + summaries only (no full content) — the LLM only needs enough
    to group notes into sections and write wikilinks, not to synthesize content.
    If existing_hub is provided, the LLM is asked to merge rather than replace.
    """
    lines = [
        f"### Cluster 0 ({len(notes)} notes) — FOLDER HUB\n",
    ]
    if existing_hub:
        lines += [
            "An existing hub note is shown below. Update it to reflect the current folder contents:",
            "- Preserve any sections, custom headings, or notes that are still accurate",
            "- Add wikilinks for any notes not yet referenced",
            "- Remove wikilinks for notes that no longer exist",
            "- Re-organize sections if the folder structure has changed significantly",
            "Do NOT merge or delete any sub-notes — this is hub-spoke only.",
        ]
        if hub_path:
            lines.append(f"The hub note path is: `{hub_path}`\n")
        existing_truncated = existing_hub[:3000] + "\n...[truncated]" if len(existing_hub) > 3000 else existing_hub
        lines.append(f"\nExisting hub content:\n```\n{existing_truncated}\n```\n")
    else:
        lines += [
            "Create a hub/index note that organizes all notes in this folder into logical sections.",
            "Group related notes under themed ## headings. Each note gets a wikilink and one-line description.",
            "Do NOT merge or delete any notes — this is hub-spoke only.",
        ]
        if hub_path:
            lines.append(f"The hub note MUST be placed at this exact path: `{hub_path}`\n")
        else:
            lines.append("")

    lines.append("Current notes in folder:")
    for note in notes:
        lines.append(f"**{note['title']}** — `{note['rel_path']}`")
        if note["summary"]:
            lines.append(f"Summary: {note['summary']}")
        if note["tags"]:
            lines.append(f"Tags: {', '.join(note['tags'][:5])}")
        lines.append("")
    return "\n".join(lines)


def _format_split_candidates_block(candidates: list[dict], vault: Path) -> str:
    """Format split candidates for the LLM prompt."""
    if not candidates:
        return "_No large notes found._"
    parts = []
    for idx, note in enumerate(candidates):
        content = note["content"]
        if len(content) > 4000:
            content = content[:4000] + "\n...[truncated]"
        parts.append(
            f"### Large Note {idx}: {note['title']}\n"
            f"Path: `{note['rel_path']}`\n\n"
            f"```\n{content}\n```"
        )
    return "\n\n---\n\n".join(parts)


def _append_errata_log(vault: Path, log_rel_path: str, entries: list[str]) -> None:
    """Append a restructure run entry to the errata log file."""
    if not entries:
        return
    log_path = vault / log_rel_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    header = f"\n## {date_str} — Restructure Run\n\n"
    body = "\n".join(f"- {e}" for e in entries) + "\n"

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(header + body)



def _build_folder_context(scan_root: Path, vault: Path, notes: list[dict],
                           clusters: list[list[dict]]) -> str:
    """
    Build a folder context block for the restructure LLM prompt.

    Provides relative signals (sibling folders, cluster density, note types,
    existing subfolder structure) so the LLM can make proportional decisions
    rather than relying on absolute word-count thresholds.
    """
    # Sibling folders at the same directory level
    parent = scan_root.parent
    siblings = sorted(
        d.name for d in parent.iterdir()
        if d.is_dir() and d.resolve() != scan_root.resolve()
        and not d.name.startswith(".")
    )

    # Does the target folder already have subfolders?
    existing_subfolders = sorted(
        d.name for d in scan_root.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ) if scan_root.exists() else []

    # Note type distribution across all notes in folder
    type_counts: dict[str, int] = {}
    for note in notes:
        fm = _parse_frontmatter(note["content"])
        note_type = fm.get("type", "untyped")
        type_counts[note_type] = type_counts.get(note_type, 0) + 1

    lines = [
        f"Scanned folder: {scan_root.relative_to(vault)}",
        f"Total notes in folder: {len(notes)}",
        f"Existing subfolders in this folder: {', '.join(existing_subfolders) if existing_subfolders else 'none'}",
        f"Sibling folders at same level: {', '.join(siblings) if siblings else 'none'}",
        f"Note type distribution: {dict(sorted(type_counts.items()))}",
        "",
        "Cluster breakdown:",
    ]
    for i, cluster in enumerate(clusters):
        density_pct = int(len(cluster) / len(notes) * 100) if notes else 0
        cluster_types: dict[str, int] = {}
        for note in cluster:
            fm = _parse_frontmatter(note["content"])
            t = fm.get("type", "untyped")
            cluster_types[t] = cluster_types.get(t, 0) + 1
        lines.append(
            f"  Cluster {i}: {len(cluster)} notes ({density_pct}% of folder)"
            f" — types: {dict(sorted(cluster_types.items()))}"
        )

    return "\n".join(lines)

def _is_within_vault(vault: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(vault.resolve())
        return True
    except ValueError:
        return False


def _execute_cluster_decisions(
    decisions: list[dict],
    clusters: list[list[dict]],
    vault: Path,
    ts: str,
    result_lines: list[str],
    errata_entries: list[str],
    written_paths: list[Path],
) -> tuple[int, int]:
    """Process cluster decisions (merge/hub-spoke/keep-separate). Returns (notes_created, notes_deleted)."""
    notes_created = 0
    notes_deleted = 0

    for decision in decisions:
        if "cluster_index" not in decision:
            continue
        cluster_idx = decision.get("cluster_index", -1)
        action = decision.get("action", "")
        rationale = decision.get("rationale", "")

        if cluster_idx < 0 or cluster_idx >= len(clusters):
            continue

        cluster = clusters[cluster_idx]
        source_titles = [n["title"] for n in cluster]
        source_paths = [n["path"] for n in cluster]

        if action == "keep-separate":
            result_lines.append(f"  Cluster {cluster_idx}: kept separate — {rationale}")

        elif action == "merge":
            merged_title = decision.get("merged_title", "Merged Note")
            merged_path_rel = decision.get("merged_path", "")
            merged_content = decision.get("merged_content", "")

            if not merged_path_rel or not merged_content:
                result_lines.append(f"  Cluster {cluster_idx}: merge skipped — missing path or content")
                continue

            output_path = vault / merged_path_rel
            if not _is_within_vault(vault, output_path):
                result_lines.append(f"  Cluster {cluster_idx}: merge skipped — path traversal rejected")
                continue

            provenance_lines = (
                f"\ncb_source: cb-restructure"
                f"\ncb_created: {ts}"
                f"\ncb_consolidated_from: {json.dumps(source_titles)}"
            )
            if merged_content.startswith("---"):
                end = merged_content.find("\n---", 3)
                if end != -1:
                    merged_content = merged_content[:end] + provenance_lines + merged_content[end:]

            result_lines.extend(_validate_frontmatter(merged_content, f"Cluster {cluster_idx} merged note"))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(merged_content, encoding="utf-8")
            notes_created += 1
            written_paths.append(output_path)

            for src_path in source_paths:
                if src_path.resolve() == output_path.resolve():
                    continue
                try:
                    src_path.unlink()
                    notes_deleted += 1
                except OSError as e:
                    result_lines.append(f"    Warning: could not delete {src_path.name}: {e}")

            merged_rel = str(output_path.relative_to(vault))
            result_lines.append(
                f"  Cluster {cluster_idx}: merged {len(source_paths)} notes → **{merged_title}** ({merged_rel})"
            )
            errata_entries.append(
                f"**Merged:** {', '.join(repr(t) for t in source_titles)} → **{merged_title}**"
            )

        elif action == "hub-spoke":
            hub_title = decision.get("hub_title", "Hub")
            hub_path_rel = decision.get("hub_path", "")
            hub_content = decision.get("hub_content", "")

            if not hub_path_rel or not hub_content:
                result_lines.append(f"  Cluster {cluster_idx}: hub-spoke skipped — missing path or content")
                continue

            output_path = vault / hub_path_rel
            if not _is_within_vault(vault, output_path):
                result_lines.append(f"  Cluster {cluster_idx}: hub-spoke skipped — path traversal rejected")
                continue

            provenance_lines = (
                f"\ncb_source: cb-restructure"
                f"\ncb_created: {ts}"
            )
            if hub_content.startswith("---"):
                end = hub_content.find("\n---", 3)
                if end != -1:
                    hub_content = hub_content[:end] + provenance_lines + hub_content[end:]

            result_lines.extend(_validate_frontmatter(hub_content, f"Cluster {cluster_idx} hub note"))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(hub_content, encoding="utf-8")
            notes_created += 1
            written_paths.append(output_path)

            hub_rel = str(output_path.relative_to(vault))
            result_lines.append(
                f"  Cluster {cluster_idx}: hub-spoke — created **{hub_title}** ({hub_rel}); "
                f"{len(source_paths)} sub-notes kept"
            )
            errata_entries.append(
                f"**Hub created:** **{hub_title}** indexing {len(source_paths)} notes"
            )

        elif action == "subfolder":
            subfolder_path_rel = decision.get("subfolder_path", "")
            hub_title = decision.get("hub_title", "Hub")
            hub_path_rel = decision.get("hub_path", "")
            hub_content = decision.get("hub_content", "")

            if not subfolder_path_rel or not hub_path_rel or not hub_content:
                result_lines.append(f"  Cluster {cluster_idx}: subfolder skipped — missing path or content")
                continue

            subfolder = vault / subfolder_path_rel
            hub_out = vault / hub_path_rel

            if not _is_within_vault(vault, subfolder) or not _is_within_vault(vault, hub_out):
                result_lines.append(f"  Cluster {cluster_idx}: subfolder skipped — path traversal rejected")
                continue

            subfolder.mkdir(parents=True, exist_ok=True)

            # Move cluster notes into the new subfolder
            moved: list[Path] = []
            for src_path in source_paths:
                dest = subfolder / src_path.name
                try:
                    src_path.rename(dest)
                    moved.append(dest)
                    written_paths.append(dest)
                except OSError as e:
                    result_lines.append(f"    Warning: could not move {src_path.name}: {e}")

            # Write hub note inside the subfolder
            provenance_lines = (
                f"\ncb_source: cb-restructure"
                f"\ncb_created: {ts}"
            )
            if hub_content.startswith("---"):
                end = hub_content.find("\n---", 3)
                if end != -1:
                    hub_content = hub_content[:end] + provenance_lines + hub_content[end:]

            result_lines.extend(_validate_frontmatter(hub_content, f"Cluster {cluster_idx} subfolder hub"))
            hub_out.parent.mkdir(parents=True, exist_ok=True)
            hub_out.write_text(hub_content, encoding="utf-8")
            notes_created += 1
            written_paths.append(hub_out)

            hub_rel = str(hub_out.relative_to(vault))
            result_lines.append(
                f"  Cluster {cluster_idx}: subfolder — moved {len(moved)} notes to {subfolder_path_rel!r}, "
                f"created hub **{hub_title}** ({hub_rel})"
            )
            errata_entries.append(
                f"**Subfolder created:** {subfolder_path_rel!r} with {len(moved)} notes, hub: **{hub_title}**"
            )

    return notes_created, notes_deleted


def _format_preview_output(decisions: list, clusters: list[list[dict]], split_candidates: list[dict]) -> str:
    """Format LLM decisions into a human-readable preview without writing any files."""
    lines = ["## Preview — Proposed Restructure (no files written)\n"]
    for decision in decisions:
        if "cluster_index" in decision:
            cluster_idx = decision.get("cluster_index", -1)
            action = decision.get("action", "")
            rationale = decision.get("rationale", "")
            if cluster_idx < 0 or cluster_idx >= len(clusters):
                continue
            cluster = clusters[cluster_idx]
            titles = ", ".join(f"'{n['title']}'" for n in cluster)
            if action == "keep-separate":
                lines.append(f"### Cluster {cluster_idx}: Keep Separate")
                lines.append(f"Notes: {titles}")
                lines.append(f"Rationale: {rationale}\n")
            elif action == "merge":
                merged_title = decision.get("merged_title", "")
                merged_path = decision.get("merged_path", "")
                content = decision.get("merged_content", "")
                if len(content) > 3000:
                    content = content[:3000] + "\n...[truncated]"
                lines.append(f"### Cluster {cluster_idx}: Merge → **{merged_title}**")
                lines.append(f"Path: `{merged_path}`")
                lines.append(f"Sources: {titles}\n")
                lines.append(f"```markdown\n{content}\n```\n")
            elif action == "hub-spoke":
                hub_title = decision.get("hub_title", "")
                hub_path_val = decision.get("hub_path", "")
                content = decision.get("hub_content", "")
                if len(content) > 3000:
                    content = content[:3000] + "\n...[truncated]"
                lines.append(f"### Cluster {cluster_idx}: Hub-Spoke → **{hub_title}**")
                lines.append(f"Path: `{hub_path_val}` (sub-notes kept)")
                lines.append(f"Sources: {titles}\n")
                lines.append(f"```markdown\n{content}\n```\n")
            elif action == "subfolder":
                hub_title = decision.get("hub_title", "")
                subfolder_path = decision.get("subfolder_path", "")
                hub_path_val = decision.get("hub_path", "")
                content = decision.get("hub_content", "")
                if len(content) > 3000:
                    content = content[:3000] + "\n...[truncated]"
                lines.append(f"### Cluster {cluster_idx}: Subfolder → **{hub_title}**")
                lines.append(f"New folder: `{subfolder_path}` (notes moved here)")
                lines.append(f"Hub: `{hub_path_val}`")
                lines.append(f"Sources: {titles}\n")
                lines.append(f"```markdown\n{content}\n```\n")
        elif "note_index" in decision:
            note_idx = decision.get("note_index", -1)
            action = decision.get("action", "")
            rationale = decision.get("rationale", "")
            if note_idx < 0 or note_idx >= len(split_candidates):
                continue
            source = split_candidates[note_idx]
            if action == "keep":
                lines.append(f"### Large Note {note_idx} ({source['title']}): Keep As-Is")
                lines.append(f"Rationale: {rationale}\n")
            elif action == "split":
                output_notes = decision.get("output_notes", [])
                lines.append(f"### Large Note {note_idx} ({source['title']}): Split into {len(output_notes)} notes")
                for spec in output_notes:
                    lines.append(f"- **{spec.get('title', '')}** → `{spec.get('path', '')}`")
                    content = spec.get("content", "")
                    if len(content) > 2000:
                        content = content[:2000] + "\n...[truncated]"
                    lines.append(f"\n```markdown\n{content}\n```\n")
    lines.append("To execute, call cb_restructure with the same parameters and preview=False.")
    return "\n".join(lines)


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def cb_restructure(
        folder: Annotated[str, Field(
            description="Vault-relative folder to scan, e.g. 'AI/LLM'. Empty string = entire vault."
        )] = "",
        dry_run: Annotated[bool, Field(
            description="Preview proposed changes without modifying any files. Always start here."
        )] = True,
        folder_hub: Annotated[bool, Field(
            description=(
                "Create a hub/index note for the entire scanned folder, linking all notes organized "
                "into logical sections. Also consolidates related notes within the folder first. "
                "Requires folder to be specified. Originals are only deleted when notes are merged."
            )
        )] = False,
        hub_path: Annotated[str, Field(
            description=(
                "Vault-relative path for the hub note when using folder_hub=True, e.g. "
                "'Knowledge/Claude Code.md' (one level up) or 'Knowledge/Claude Code/index.md' (inside folder). "
                "If empty, the LLM decides. If the file already exists it will be merged with new content."
            )
        )] = "",
        similarity_threshold: Annotated[float, Field(
            ge=0.1, le=1.0,
            description="Similarity threshold for clustering (0.1–1.0). Lower = more aggressive grouping. Default: 0.5"
        )] = 0.5,
        min_cluster_size: Annotated[int, Field(
            ge=2, le=20,
            description="Minimum number of notes to form a cluster. Default: 2."
        )] = 2,
        max_clusters: Annotated[int, Field(
            ge=1, le=50,
            description="Maximum number of clusters to process in one run. Default: 10."
        )] = 10,
        split_threshold: Annotated[int, Field(
            ge=500,
            description="Minimum note size in characters to be considered a split candidate. Default: 3000."
        )] = 3000,
        max_splits: Annotated[int, Field(
            ge=1, le=20,
            description="Maximum number of large notes to evaluate for splitting in one run. Default: 5."
        )] = 5,
        preview: Annotated[bool, Field(
            description=(
                "Run the LLM and show the full proposed note content without writing any files. "
                "Use after dry_run=True to see exactly what would be written before committing. "
                "Mutually exclusive with dry_run=True. Set dry_run=False, preview=True to activate."
            )
        )] = False,
    ) -> str:
        """
        Restructure the vault by merging related notes and splitting bloated ones.

        Three modes:
        - Default: find related note clusters (merge/hub-spoke) and large notes (split)
        - folder_hub=True: create a single hub/index note for the entire folder, organizing
          all notes into logical sections with wikilinks. Good for folders with many notes
          on a shared theme that need a navigation page.

        Uses the search index to find related note clusters. Notes already in a cluster
        are excluded from split evaluation (they're handled by the merge pass).

        Workflow: dry_run=True (see candidates) → preview=True (see proposed content) → dry_run=False (execute).
        Originals are deleted after a merge or split (never after hub-spoke or folder_hub).
        Changes are logged to AI/Cyberbrain-Log.md.

        Notes with cb_lock: true in frontmatter are never restructured.
        Preferences from vault CLAUDE.md (set via cb_configure) are respected.
        """
        from backends import call_model, BackendError

        config = _load_config()
        vault_path_str = config.get("vault_path", "")
        if not vault_path_str:
            raise ToolError("No vault configured. Run cb_configure(vault_path=...) first.")

        vault = Path(vault_path_str).expanduser().resolve()
        if not vault.exists():
            raise ToolError(f"Vault path does not exist: {vault}")

        scan_root = vault / folder if folder else vault
        if not scan_root.exists():
            raise ToolError(f"Folder not found in vault: {folder!r}")
        if not _is_within_vault(vault, scan_root):
            raise ToolError(f"Folder is outside vault: {folder!r}")

        if folder_hub and not folder:
            raise ToolError("folder_hub requires a specific folder to be specified.")

        if hub_path and not folder_hub:
            raise ToolError("hub_path is only used with folder_hub=True.")

        if dry_run and preview:
            raise ToolError(
                "dry_run and preview are mutually exclusive. "
                "Use dry_run=True to see candidates (no LLM), or preview=True with dry_run=False to see proposed content."
            )

        # Resolve hub path early for existence checks and exclusion from clustering
        hub_abs: Path | None = None
        if hub_path:
            hub_abs = (vault / hub_path).resolve()
            if not _is_within_vault(vault, hub_abs):
                raise ToolError(f"hub_path is outside the vault: {hub_path!r}")

        excluded_folders = ["AI/Journal", "Templates", "_templates", ".obsidian"]
        vault_prefs = _read_vault_prefs(vault_path_str)
        prefs_section = f"Vault preferences:\n\n{vault_prefs}" if vault_prefs else ""
        system_prompt = _load_prompt("restructure-system.md")

        # Exclude existing hub from notes so it isn't clustered or overwritten by a merge
        hub_exclude: set[Path] = {hub_abs} if hub_abs else set()
        notes = _collect_notes(scan_root, vault, excluded_folders, exclude_paths=hub_exclude, shallow=folder_hub)
        if not notes:
            return f"No eligible notes found in {'vault' if not folder else repr(folder)}."

        # Ensure all notes in the target folder are indexed before clustering.
        # Notes added since the last reindex won't appear in search results otherwise.
        backend = _get_search_backend(config)
        _index_paths([n["path"] for n in notes], config)

        # ── FOLDER HUB MODE ────────────────────────────────────────────────────────
        if folder_hub:
            # Use title-concept clustering for folder_hub: group by primary sub-topic
            # word rather than content similarity. Content similarity is noisy within
            # a folder (all notes mention the same concepts), while title words are
            # the clearest signal about what each note is primarily about.
            clusters = _title_concept_clusters(notes, min_cluster_size)
            clusters = clusters[:max_clusters]

            existing_hub = hub_abs.read_text(encoding="utf-8") if hub_abs and hub_abs.exists() else ""
            hub_path_display = hub_path if hub_path else "(LLM will decide)"
            hub_status = "will be merged with new content" if existing_hub else "will be created"

            if dry_run:
                lines = [
                    f"[DRY RUN] Folder hub mode for '{folder}':",
                    "",
                    f"Step 1 — Consolidate within folder ({len(clusters)} cluster(s) found):",
                ]
                if clusters:
                    for idx, cluster in enumerate(clusters):
                        density = len(cluster) / len(notes) if notes else 0
                        proposed = "subfolder" if density >= 0.25 and len(cluster) >= 5 else ("hub-and-spoke" if len(cluster) >= 6 else "merge")
                        lines.append(f"  Cluster {idx + 1} ({len(cluster)} notes) → proposed {proposed}:")
                        for note in cluster:
                            lines.append(f"    - {note['title']}")
                else:
                    lines.append("  No clusters found — no merges will occur.")
                lines += [
                    "",
                    f"Step 2 — Hub note ({hub_status}):",
                    f"  Hub path: {hub_path_display}",
                    f"  Notes to be linked: {len(notes)} (exact count depends on merge outcomes)",
                    "",
                    "Run with dry_run=False to execute.",
                ]
                return "\n".join(lines)

            # Execute Phase 1: cluster and merge
            result_lines: list[str] = ["## Folder Hub Restructure\n", "### Phase 1: Consolidate\n"]
            errata_entries: list[str] = []
            written_paths: list[Path] = []

            if clusters:
                clusters_block = _format_cluster_block(clusters, vault)
                folder_context = _build_folder_context(scan_root, vault, notes, clusters)
                user_msg_phase1 = (
                    _load_prompt("restructure-user.md")
                    .replace("{cluster_count}", str(len(clusters)))
                    .replace("{split_count}", "0")
                    .replace("{vault_prefs_section}", prefs_section)
                    .replace("{folder_context}", folder_context)
                    .replace("{clusters_block}", clusters_block)
                    .replace("{split_candidates_block}", "_No split candidates in folder hub mode._")
                )
                try:
                    raw1 = call_model(system_prompt, user_msg_phase1, config)
                except BackendError as e:
                    raise ToolError(f"Backend error during cluster phase: {e}")

                raw1 = re.sub(r"^```(?:json)?\s*", "", raw1.strip())
                raw1 = re.sub(r"\s*```$", "", raw1).strip()
                try:
                    decisions1 = _repair_json(raw1)
                except json.JSONDecodeError as e:
                    raise ToolError(f"LLM returned invalid JSON in cluster phase: {e}\n\nRaw: {raw1[:500]}")

                now = datetime.now(timezone.utc)
                ts = now.strftime("%Y-%m-%dT%H:%M:%S")
                if not preview:
                    nc, nd = _execute_cluster_decisions(
                        decisions1, clusters, vault, ts, result_lines, errata_entries, written_paths
                    )
                    notes_created = nc
                    notes_deleted = nd
                    if not result_lines[-1].strip():
                        result_lines.append("  No merges executed.")
                else:
                    notes_created = 0
                    notes_deleted = 0
            else:
                decisions1 = []
                result_lines.append("  No clusters found — skipping merge phase.")
                notes_created = 0
                notes_deleted = 0

            # Execute Phase 2: re-collect and create/update hub
            result_lines.append("\n### Phase 2: Hub Note\n")
            notes_after = _collect_notes_for_hub(scan_root, vault, excluded_folders, exclude_paths=hub_exclude)
            # Re-read existing hub (may have been updated if it was in the folder)
            existing_hub = hub_abs.read_text(encoding="utf-8") if hub_abs and hub_abs.exists() else ""

            hub_block = _format_folder_hub_block(notes_after, vault, hub_path=hub_path, existing_hub=existing_hub)
            folder_context_p2 = _build_folder_context(scan_root, vault, notes_after, [])
            user_msg_phase2 = (
                _load_prompt("restructure-user.md")
                .replace("{cluster_count}", "1")
                .replace("{split_count}", "0")
                .replace("{vault_prefs_section}", prefs_section)
                .replace("{folder_context}", folder_context_p2)
                .replace("{clusters_block}", hub_block)
                .replace("{split_candidates_block}", "_No split candidates in folder hub mode._")
            )
            try:
                raw2 = call_model(system_prompt, user_msg_phase2, config)
            except BackendError as e:
                raise ToolError(f"Backend error during hub creation phase: {e}")

            raw2 = re.sub(r"^```(?:json)?\s*", "", raw2.strip())
            raw2 = re.sub(r"\s*```$", "", raw2).strip()
            try:
                decisions2 = _repair_json(raw2)
            except json.JSONDecodeError as e:
                raise ToolError(f"LLM returned invalid JSON in hub phase: {e}\n\nRaw: {raw2[:500]}")

            if preview:
                preview_lines = ["## Preview — Folder Hub Restructure (no files written)\n"]
                preview_lines.append("### Phase 1: Cluster Consolidation\n")
                for d in (decisions1 if isinstance(decisions1, list) else []):
                    if "cluster_index" not in d:
                        continue
                    cidx = d.get("cluster_index", -1)
                    action = d.get("action", "")
                    if cidx < 0 or cidx >= len(clusters):
                        continue
                    cluster = clusters[cidx]
                    titles = ", ".join(f"'{n['title']}'" for n in cluster)
                    if action == "keep-separate":
                        preview_lines.append(f"Cluster {cidx}: Keep separate — {titles}")
                    elif action == "merge":
                        content = d.get("merged_content", "")
                        if len(content) > 3000:
                            content = content[:3000] + "\n...[truncated]"
                        preview_lines.append(f"Cluster {cidx}: Merge → **{d.get('merged_title', '')}** (`{d.get('merged_path', '')}`)")
                        preview_lines.append(f"\n```markdown\n{content}\n```\n")
                    elif action == "hub-spoke":
                        content = d.get("hub_content", "")
                        if len(content) > 3000:
                            content = content[:3000] + "\n...[truncated]"
                        preview_lines.append(f"Cluster {cidx}: Hub-spoke → **{d.get('hub_title', '')}** (`{d.get('hub_path', '')}`)")
                        preview_lines.append(f"\n```markdown\n{content}\n```\n")
                preview_lines.append("\n### Phase 2: Hub Note\n")
                for d in (decisions2 if isinstance(decisions2, list) else []):
                    if d.get("action") != "hub-spoke":
                        continue
                    hub_title = d.get("hub_title", "Hub")
                    final_hub_path = hub_path if hub_path else d.get("hub_path", "")
                    content = d.get("hub_content", "")
                    if len(content) > 3000:
                        content = content[:3000] + "\n...[truncated]"
                    preview_lines.append(f"Hub: **{hub_title}** → `{final_hub_path}`")
                    preview_lines.append(f"\n```markdown\n{content}\n```\n")
                    break
                preview_lines.append("To execute, call cb_restructure with the same parameters and preview=False.")
                return "\n".join(preview_lines)

            for decision in (decisions2 if isinstance(decisions2, list) else []):
                if decision.get("action") != "hub-spoke":
                    continue
                hub_title = decision.get("hub_title", "Hub")
                # Caller-supplied hub_path takes precedence
                final_hub_path = hub_path if hub_path else decision.get("hub_path", "")
                hub_content = decision.get("hub_content", "")

                if not final_hub_path or not hub_content:
                    result_lines.append("  Hub creation skipped — missing path or content from LLM.")
                    break

                out = vault / final_hub_path
                if not _is_within_vault(vault, out):
                    result_lines.append("  Hub creation skipped — path traversal rejected.")
                    break

                now2 = datetime.now(timezone.utc)
                ts2 = now2.strftime("%Y-%m-%dT%H:%M:%S")
                provenance = f"\ncb_source: cb-restructure\ncb_created: {ts2}"
                if hub_content.startswith("---"):
                    end = hub_content.find("\n---", 3)
                    if end != -1:
                        hub_content = hub_content[:end] + provenance + hub_content[end:]

                result_lines.extend(_validate_frontmatter(hub_content, "Folder hub note"))
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(hub_content, encoding="utf-8")
                notes_created += 1
                written_paths.append(out)

                action_word = "Updated" if existing_hub else "Created"
                hub_rel = str(out.relative_to(vault))
                result_lines.append(f"  {action_word} hub: **{hub_title}** ({hub_rel}) linking {len(notes_after)} notes")
                errata_entries.append(f"**Hub {action_word.lower()}:** **{hub_title}** linking {len(notes_after)} notes")
                break
            else:
                result_lines.append("  Hub creation skipped — LLM did not return a hub-spoke decision.")

            _index_paths(written_paths, config)
            _prune_index(config)

            log_enabled = config.get("consolidation_log_enabled", True)
            log_rel = config.get("consolidation_log", "AI/Cyberbrain-Log.md")
            if log_enabled and errata_entries:
                errata_entries.append(f"Notes deleted: {notes_deleted} | Notes created: {notes_created}")
                _append_errata_log(vault, log_rel, errata_entries)

            result_lines += ["", f"Notes created: {notes_created}", f"Notes deleted: {notes_deleted}"]
            if log_enabled and errata_entries:
                result_lines.append(f"Changes logged to: {log_rel}")
            return "\n".join(result_lines)

        # ── NORMAL MODE (cluster + split) ──────────────────────────────────────────
        clusters = _build_clusters(notes, backend, similarity_threshold, min_cluster_size)
        clusters = clusters[:max_clusters]
        clustered_paths = {str(n["path"]) for cluster in clusters for n in cluster}
        split_candidates = _find_split_candidates(notes, clustered_paths, split_threshold)[:max_splits]

        if not clusters and not split_candidates:
            return (
                f"Nothing to restructure (scanned {len(notes)} notes). "
                f"No clusters with {min_cluster_size}+ related notes and no notes over {split_threshold} chars. "
                "Try lowering similarity_threshold, min_cluster_size, split_threshold, "
                "or use folder_hub=True to create a navigation hub for the folder."
            )

        if dry_run:
            lines = [
                f"[DRY RUN] Scanned {len(notes)} notes.\n",
                f"Clusters found: {len(clusters)}",
                f"Large notes to consider splitting: {len(split_candidates)}",
                "",
            ]
            for idx, cluster in enumerate(clusters):
                lines.append(f"Cluster {idx + 1} ({len(cluster)} notes):")
                for note in cluster:
                    lines.append(f"  - {note['title']} ({note['rel_path']})")
                density = len(cluster) / len(notes) if notes else 0
                proposed = "subfolder" if density >= 0.25 and len(cluster) >= 5 else ("hub-and-spoke" if len(cluster) >= 6 else "merge")
                lines.append(f"  → Proposed action: {proposed}")
                lines.append("")
            if split_candidates:
                lines.append("Large notes (split candidates):")
                for note in split_candidates:
                    size_kb = len(note["content"]) / 1000
                    lines.append(f"  - {note['title']} ({note['rel_path']}) — {size_kb:.1f}KB")
                lines.append("")
            lines.append(
                "Run with dry_run=False to execute. "
                "The LLM will make final decisions on each cluster and large note."
            )
            return "\n".join(lines)

        # Execute
        clusters_block = _format_cluster_block(clusters, vault)
        split_candidates_block = _format_split_candidates_block(split_candidates, vault)
        folder_context = _build_folder_context(scan_root, vault, notes, clusters)
        user_message = (
            _load_prompt("restructure-user.md")
            .replace("{cluster_count}", str(len(clusters)))
            .replace("{split_count}", str(len(split_candidates)))
            .replace("{vault_prefs_section}", prefs_section)
            .replace("{folder_context}", folder_context)
            .replace("{clusters_block}", clusters_block)
            .replace("{split_candidates_block}", split_candidates_block)
        )

        try:
            raw = call_model(system_prompt, user_message, config)
        except BackendError as e:
            raise ToolError(f"Backend error during restructure: {e}")

        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw).strip()

        try:
            decisions = _repair_json(raw)
        except json.JSONDecodeError as e:
            raise ToolError(f"LLM returned invalid JSON: {e}\n\nRaw response:\n{raw[:500]}")

        if not isinstance(decisions, list):
            raise ToolError("LLM response was not a JSON array.")

        if preview:
            return _format_preview_output(decisions, clusters, split_candidates)


        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y-%m-%dT%H:%M:%S")
        errata_entries: list[str] = []
        result_lines: list[str] = []
        written_paths: list[Path] = []

        nc, nd = _execute_cluster_decisions(decisions, clusters, vault, ts, result_lines, errata_entries, written_paths)
        notes_created = nc
        notes_deleted = nd

        # Split decisions
        for decision in decisions:
            if "note_index" not in decision:
                continue
            note_idx = decision.get("note_index", -1)
            action = decision.get("action", "")
            rationale = decision.get("rationale", "")

            if note_idx < 0 or note_idx >= len(split_candidates):
                continue

            source_note = split_candidates[note_idx]
            source_path = source_note["path"]

            if action == "keep":
                result_lines.append(f"Large note {note_idx} ({source_note['title']}): kept as-is — {rationale}")
                continue

            if action == "split":
                output_notes = decision.get("output_notes", [])
                if not output_notes:
                    result_lines.append(f"Large note {note_idx}: split skipped — no output notes provided")
                    continue

                split_written: list[Path] = []
                split_ok = True
                for note_spec in output_notes:
                    note_path_rel = note_spec.get("path", "")
                    note_content = note_spec.get("content", "")
                    if not note_path_rel or not note_content:
                        result_lines.append(f"  Warning: skipping output note with missing path or content")
                        continue
                    out_path = vault / note_path_rel
                    if not _is_within_vault(vault, out_path):
                        result_lines.append(f"  Warning: path traversal rejected for {note_path_rel}")
                        split_ok = False
                        continue
                    provenance_lines = (
                        f"\ncb_source: cb-restructure"
                        f"\ncb_created: {ts}"
                        f"\ncb_split_from: {json.dumps(source_note['title'])}"
                    )
                    if note_content.startswith("---"):
                        end = note_content.find("\n---", 3)
                        if end != -1:
                            note_content = note_content[:end] + provenance_lines + note_content[end:]
                    result_lines.extend(_validate_frontmatter(note_content, f"Split note {note_path_rel}"))
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(note_content, encoding="utf-8")
                    split_written.append(out_path)
                    notes_created += 1

                if split_written and split_ok:
                    try:
                        source_path.unlink()
                        notes_deleted += 1
                    except OSError as e:
                        result_lines.append(f"  Warning: could not delete {source_path.name}: {e}")

                written_paths.extend(split_written)
                out_titles = [n.get("title", p.stem) for n, p in zip(output_notes, split_written)]
                result_lines.append(
                    f"Large note {note_idx} ({source_note['title']}): split into "
                    f"{len(split_written)} notes — {', '.join(repr(t) for t in out_titles)}"
                )
                errata_entries.append(
                    f"**Split:** **{source_note['title']}** → {', '.join(repr(t) for t in out_titles)}"
                )

        _index_paths(written_paths, config)
        _prune_index(config)

        log_enabled = config.get("consolidation_log_enabled", True)
        log_rel = config.get("consolidation_log", "AI/Cyberbrain-Log.md")
        if log_enabled and errata_entries:
            errata_entries.append(f"Notes deleted: {notes_deleted} | Notes created: {notes_created}")
            _append_errata_log(vault, log_rel, errata_entries)

        lines = ["## Restructure Complete\n"] + result_lines + [
            "",
            f"Notes created: {notes_created}",
            f"Notes deleted: {notes_deleted}",
        ]
        if log_enabled and errata_entries:
            lines.append(f"Changes logged to: {log_rel}")

        return "\n".join(lines)
