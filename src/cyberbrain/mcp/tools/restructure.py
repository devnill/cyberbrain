"""cb_restructure tool — split large notes and merge clusters of related notes to keep the vault clean."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from cyberbrain.mcp.shared import _load_config, _get_search_backend, _parse_frontmatter, _prune_index, _index_paths, _move_to_trash, _load_tool_prompt as _load_prompt, _is_within_vault

_GROUPS_CACHE = Path.home() / ".claude" / "cyberbrain" / ".restructure-groups-cache.json"
_PREFS_HEADING = "## Cyberbrain Preferences"
_LOCK_FIELD = "cb_lock"


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


def _save_groups_cache(folder_path: str, clusters: list[list[dict]], strategy: str = "") -> None:
    """Save grouping result to cache so dry_run → preview → execute stay consistent."""
    cache_data = {
        "folder": folder_path,
        "strategy": strategy,
        "groups": [[n["rel_path"] for n in cluster] for cluster in clusters],
    }
    try:
        _GROUPS_CACHE.write_text(json.dumps(cache_data), encoding="utf-8")
    except OSError:
        pass


def _load_groups_cache(folder_path: str, notes: list[dict], strategy: str = "") -> list[list[dict]] | None:
    """Load cached grouping if it exists and matches the folder and strategy. Returns None on miss."""
    try:
        data = json.loads(_GROUPS_CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("folder") != folder_path:
        return None
    if strategy and data.get("strategy", "") != strategy:
        return None
    path_to_note = {n["rel_path"]: n for n in notes}
    clusters: list[list[dict]] = []
    for group_paths in data.get("groups", []):
        cluster_notes = [path_to_note[p] for p in group_paths if p in path_to_note]
        if len(cluster_notes) >= 2:
            clusters.append(cluster_notes)
    return clusters if clusters else None


def _clear_groups_cache() -> None:
    """Remove the groups cache file."""
    try:
        _GROUPS_CACHE.unlink(missing_ok=True)
    except OSError:
        pass


def _call_group_notes(
    notes: list[dict],
    folder_path: str,
    prefs_section: str,
    config: dict,
) -> list[list[dict]]:
    """Ask the LLM to propose semantic topic groups from a flat list of notes.

    Used in folder_hub mode instead of title-concept clustering, which only
    matches notes sharing a key title word. Returns a list of clusters
    (each cluster is a list of note dicts). Notes not assigned to any group
    are left for the standalone path.

    Results are cached so that dry_run → preview → execute use the same grouping.
    """
    if not notes:
        return []

    # Check cache first
    cached = _load_groups_cache(folder_path, notes, strategy="llm")
    if cached is not None:
        return cached

    from cyberbrain.extractors.backends import call_model, BackendError, get_model_for_tool
    tool_config = {**config, "model": get_model_for_tool(config, "restructure")}
    group_system = _load_prompt("restructure-group-system.md")
    notes_block = _build_audit_notes_block(notes)
    user_msg = (
        _load_prompt("restructure-group-user.md")
        .replace("{folder_path}", folder_path)
        .replace("{note_count}", str(len(notes)))
        .replace("{vault_prefs_section}", prefs_section)
        .replace("{notes_block}", notes_block)
    )
    try:
        raw = call_model(group_system, user_msg, tool_config)
    except BackendError:
        return []
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        groups = _repair_json(raw)
        if not isinstance(groups, list):
            return []
    except json.JSONDecodeError:
        return []

    # Map rel_path → note dict for quick lookup
    path_to_note = {n["rel_path"]: n for n in notes}
    clusters: list[list[dict]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        note_paths = group.get("note_paths", [])
        cluster_notes = [path_to_note[p] for p in note_paths if p in path_to_note]
        if len(cluster_notes) >= 2:
            clusters.append(cluster_notes)

    # Cache for subsequent calls (preview, execute)
    _save_groups_cache(folder_path, clusters, strategy="llm")
    return clusters


def _embedding_hierarchical_clusters(
    notes: list[dict],
    config: dict,
    distance_threshold: float = 0.25,
    min_cluster_size: int = 2,
) -> list[list[dict]]:
    """Deterministic clustering using search index embeddings + agglomerative clustering.

    Uses average-linkage hierarchical clustering on cosine distances.
    Deterministic: same embeddings always produce the same clusters.
    No LLM call needed.

    Loads embeddings from the usearch index (search-index.usearch) using the
    manifest (search-index-manifest.json) id_map for path-to-key mapping.
    """
    if len(notes) < min_cluster_size:
        return []
    import numpy as np

    # Load manifest for id_map and embedding_dim
    manifest_path = Path.home() / ".claude" / "cyberbrain" / "search-index-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    id_map = manifest.get("id_map", [])
    embedding_dim = manifest.get("embedding_dim", 0)
    if not embedding_dim or not id_map:
        return []

    # Load the usearch index
    index_path = manifest_path.parent / "search-index.usearch"
    try:
        from usearch.index import Index
        idx = Index(ndim=embedding_dim, metric="cos", dtype="f32")
        idx.load(str(index_path))
    except Exception:
        return []

    # Map note paths to usearch key positions via id_map
    path_to_emb_idx = {p: i for i, p in enumerate(id_map)}
    note_keys = []
    valid_notes = []
    for note in notes:
        abs_path = str(note["path"])
        if abs_path in path_to_emb_idx:
            note_keys.append(path_to_emb_idx[abs_path])
            valid_notes.append(note)

    if len(valid_notes) < min_cluster_size:
        return []

    # Extract embeddings from usearch index
    keys_array = np.array(note_keys, dtype=np.int64)
    emb_matrix = idx.get(keys_array)  # shape: (n, dim)

    # Normalize for cosine distance
    norms = np.linalg.norm(emb_matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    emb_normed = emb_matrix / norms

    # Cosine distance matrix: 1 - cosine_similarity
    sim_matrix = emb_normed @ emb_normed.T
    dist_matrix = 1.0 - sim_matrix

    # Average-linkage agglomerative clustering (no scipy needed)
    n = len(valid_notes)
    # Start: each note is its own cluster
    cluster_members: dict[int, list[int]] = {i: [i] for i in range(n)}
    active = set(range(n))

    while len(active) > 1:
        # Find closest pair of active clusters (average linkage)
        best_dist = float("inf")
        best_pair = (-1, -1)
        active_list = sorted(active)
        for ii in range(len(active_list)):
            for jj in range(ii + 1, len(active_list)):
                ci, cj = active_list[ii], active_list[jj]
                # Average distance between all pairs across the two clusters
                total_dist = 0.0
                count = 0
                for mi in cluster_members[ci]:
                    for mj in cluster_members[cj]:
                        total_dist += dist_matrix[mi, mj]
                        count += 1
                avg_dist = total_dist / count if count else float("inf")
                if avg_dist < best_dist:
                    best_dist = avg_dist
                    best_pair = (ci, cj)

        if best_dist > distance_threshold:
            break  # No more clusters close enough

        # Merge best pair
        ci, cj = best_pair
        cluster_members[ci] = cluster_members[ci] + cluster_members[cj]
        del cluster_members[cj]
        active.discard(cj)

    # Collect clusters with enough members
    clusters = []
    for members in cluster_members.values():
        if len(members) >= min_cluster_size:
            clusters.append([valid_notes[i] for i in members])

    return sorted(clusters, key=len, reverse=True)


def _llm_validate_clusters(
    clusters: list[list[dict]],
    all_notes: list[dict],
    folder_path: str,
    prefs_section: str,
    config: dict,
) -> list[list[dict]]:
    """Ask LLM to validate and refine algorithmically-produced clusters.

    Reuses the group-system prompt for consistent quality criteria, with an
    added section showing the algorithm's proposed clusters as a starting point.
    """
    from cyberbrain.extractors.backends import call_model, BackendError, get_model_for_tool
    tool_config = {**config, "model": get_model_for_tool(config, "restructure")}

    # Format embedding clusters as a hint section
    hint_lines = ["## Algorithm-proposed clusters (starting point — revise freely)\n"]
    for i, cluster in enumerate(clusters):
        titles = [n["title"] for n in cluster]
        hint_lines.append(f"- Group {i}: {', '.join(titles)}")
    hint_lines.append(
        "\nThese groups were produced by embedding similarity. "
        "Use them as a starting point: split weak groups, merge standalone notes "
        "into groups where they clearly fit, or discard groups entirely."
    )
    hint_section = "\n".join(hint_lines)

    # Use the standard grouping prompt for quality criteria
    group_system = _load_prompt("restructure-group-system.md")
    notes_block = _build_audit_notes_block(all_notes)
    user_msg = (
        _load_prompt("restructure-group-user.md")
        .replace("{folder_path}", folder_path)
        .replace("{note_count}", str(len(all_notes)))
        .replace("{vault_prefs_section}", prefs_section)
        .replace("{notes_block}", notes_block)
        + "\n\n" + hint_section
    )

    try:
        raw = call_model(group_system, user_msg, tool_config)
    except BackendError:
        return clusters  # Fall back to algorithmic result

    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        groups = _repair_json(raw)
        if not isinstance(groups, list):
            return clusters
    except json.JSONDecodeError:
        return clusters

    path_to_note = {n["rel_path"]: n for n in all_notes}
    refined: list[list[dict]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        note_paths = group.get("note_paths", [])
        cluster_notes = [path_to_note[p] for p in note_paths if p in path_to_note]
        if len(cluster_notes) >= 2:
            refined.append(cluster_notes)

    return refined if refined else clusters


def _dispatch_grouping(
    strategy: str,
    notes: list[dict],
    folder_path: str,
    prefs_section: str,
    config: dict,
) -> list[list[dict]]:
    """Dispatch to the selected clustering strategy. All strategies return list[list[dict]].

    Strategies:
      'llm'       — LLM-driven semantic grouping (always uses LLM)
      'embedding' — deterministic embedding hierarchical clustering, LLM fallback
      'hybrid'    — embedding clustering then LLM validation/refinement
      'auto'      — embedding clustering with LLM fallback (default)
    """
    # Check cache first (all strategies share the same cache keyed by strategy)
    cached = _load_groups_cache(folder_path, notes, strategy=strategy)
    if cached is not None:
        return cached

    if strategy == "llm":
        result = _call_group_notes(notes, folder_path, prefs_section, config)
    elif strategy == "embedding":
        clusters = _embedding_hierarchical_clusters(notes, config)
        result = clusters if clusters else _call_group_notes(notes, folder_path, prefs_section, config)
    elif strategy == "hybrid":
        # Algorithmic pre-group, then LLM validates/refines
        clusters = _embedding_hierarchical_clusters(notes, config)
        if not clusters:
            result = _call_group_notes(notes, folder_path, prefs_section, config)
        else:
            result = _llm_validate_clusters(clusters, notes, folder_path, prefs_section, config)
    else:  # "auto"
        clusters = _embedding_hierarchical_clusters(notes, config)
        result = clusters if clusters else _call_group_notes(notes, folder_path, prefs_section, config)

    # Cache for subsequent calls (preview, execute)
    _save_groups_cache(folder_path, result, strategy=strategy)
    return result


def _build_clusters(notes: list[dict], backend, min_cluster_size: int) -> list[list[dict]]:
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

def _build_cluster_summary_block(clusters: list[list[dict]]) -> str:
    """Compact cluster block for the decision call — titles and summaries only, no content."""
    parts = []
    for idx, cluster in enumerate(clusters):
        lines = [f"### Cluster {idx} ({len(cluster)} notes)"]
        for note in cluster:
            summary = note["summary"][:200] if note["summary"] else "(no summary)"
            lines.append(f"- **{note['title']}**: {summary}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts) if parts else "_No clusters._"


def _build_split_summary_block(splits: list[dict]) -> str:
    """Compact split candidates block for the decision call — titles and sizes only."""
    if not splits:
        return "_No split candidates._"
    lines = []
    for idx, note in enumerate(splits):
        size_kb = len(note["content"]) / 1000
        summary = note["summary"][:200] if note["summary"] else "(no summary)"
        lines.append(f"### Note {idx}: {note['title']} ({size_kb:.1f}KB)")
        lines.append(summary)
    return "\n\n".join(lines)




def _build_vault_structure(vault: Path) -> str:
    """Build a two-level folder listing of the vault for LLM context."""
    lines = []
    try:
        for top in sorted(vault.iterdir()):
            if not top.is_dir() or top.name.startswith("."):
                continue
            lines.append(f"- {top.name}/")
            try:
                for sub in sorted(top.iterdir()):
                    if sub.is_dir() and not sub.name.startswith("."):
                        lines.append(f"  - {sub.name}/")
            except PermissionError:
                pass
    except PermissionError:
        pass
    return "\n".join(lines) if lines else "(vault structure unavailable)"


def _build_standalone_notes_block(standalone: list[dict]) -> str:
    """Summary block for notes not in any cluster and not split candidates."""
    if not standalone:
        return "_No standalone notes._"
    lines = []
    for note in standalone:
        summary = note["summary"][:200] if note["summary"] else "(no summary)"
        lines.append(f"- **{note['title']}** (`{note['rel_path']}`): {summary}")
    return "\n".join(lines)

def _format_action_description(decision: dict) -> str:
    """Format a decision dict into a human-readable action description for the generation prompt."""
    action = decision.get("action", "")
    rationale = decision.get("rationale", "")
    if action == "merge":
        return (
            f"**merge** — Combine all source notes into a single, richer note.\n"
            f"Title: {decision.get('merged_title', '')}\n"
            f"Path: {decision.get('merged_path', '')}\n"
            f"Rationale: {rationale}"
        )
    elif action == "hub-spoke":
        return (
            f"**hub-spoke** — Create an index/hub note in the current folder linking the source notes.\n"
            f"Hub title: {decision.get('hub_title', '')}\n"
            f"Hub path: {decision.get('hub_path', '')}\n"
            f"Rationale: {rationale}"
        )
    elif action == "subfolder":
        return (
            f"**subfolder** — Move source notes into a new subdirectory and create a hub note inside it.\n"
            f"Subfolder: {decision.get('subfolder_path', '')}\n"
            f"Hub title: {decision.get('hub_title', '')}\n"
            f"Hub path: {decision.get('hub_path', '')}\n"
            f"Rationale: {rationale}"
        )
    elif action == "split":
        notes_desc = "\n".join(
            f"  - {n.get('title', '')} → {n.get('path', '')}"
            for n in decision.get("output_notes", [])
        )
        return (
            f"**split** — Break the source note into multiple focused notes.\n"
            f"Rationale: {rationale}\n"
            f"Output notes:\n{notes_desc}"
        )
    elif action == "split-subfolder":
        notes_desc = "\n".join(
            f"  - {n.get('title', '')} → {n.get('path', '')}"
            for n in decision.get("output_notes", [])
        )
        return (
            f"**split-subfolder** — Break the source note into multiple focused notes inside a new subfolder, plus a hub note.\n"
            f"Subfolder: {decision.get('subfolder_path', '')}\n"
            f"Hub title: {decision.get('hub_title', '')}\n"
            f"Hub path: {decision.get('hub_path', '')}\n"
            f"Rationale: {rationale}\n"
            f"Output notes:\n{notes_desc}"
        )
    elif action == "move-cluster":
        return (
            f"**move-cluster** — Move all notes in this cluster to a different folder.\n"
            f"Destination: {decision.get('destination', '')}\n"
            f"Rationale: {rationale}"
        )
    return f"**{action}**\nRationale: {rationale}"



def _format_flag_output(flag_decisions: list[dict]) -> str:
    """Format flag-misplaced and flag-low-quality decisions for display."""
    if not flag_decisions:
        return ""
    lines = ["### Flagged Notes (no files changed — review manually)\n"]
    for d in flag_decisions:
        action = d.get("action", "")
        note_path = d.get("note_path", "(unknown)")
        rationale = d.get("rationale", "")
        if action == "flag-misplaced":
            dest = d.get("suggested_destination", "(no suggestion)")
            lines.append(f"  🔀 **Misplaced**: `{note_path}`")
            lines.append(f"     Suggested destination: {dest}")
            lines.append(f"     Reason: {rationale}")
        elif action == "flag-low-quality":
            lines.append(f"  ⚠️  **Low quality**: `{note_path}`")
            lines.append(f"     Reason: {rationale}")
        lines.append("")
    return "\n".join(lines)


def _build_audit_notes_block(notes: list[dict]) -> str:
    """Format all notes for the audit call — title, path, tags, summary."""
    if not notes:
        return "_No notes._"
    lines = []
    for note in notes:
        summary = note["summary"][:300] if note["summary"] else "(no summary)"
        tags = note.get("tags", [])
        tags_str = f" [tags: {', '.join(tags)}]" if tags else ""
        lines.append(f"- **{note['title']}** (`{note['rel_path']}`){tags_str}: {summary}")
    return "\n".join(lines)


_AUDIT_BATCH_SIZE = 20
_AUDIT_MAX_WORKERS = 4


def _call_audit_notes_batch(
    notes: list[dict],
    folder_path: str,
    vault_structure: str,
    prefs_section: str,
    config: dict,
    audit_system: str,
    audit_user_tmpl: str,
) -> list[dict]:
    """Audit a single batch of notes. Returns flag decisions only."""
    from cyberbrain.extractors.backends import call_model, BackendError, get_model_for_tool
    tool_config = {**config, "model": get_model_for_tool(config, "restructure")}
    notes_block = _build_audit_notes_block(notes)
    user_msg = (
        audit_user_tmpl
        .replace("{folder_path}", folder_path)
        .replace("{note_count}", str(len(notes)))
        .replace("{vault_prefs_section}", prefs_section)
        .replace("{vault_structure}", vault_structure)
        .replace("{notes_block}", notes_block)
    )
    try:
        raw = call_model(audit_system, user_msg, tool_config)
    except BackendError:
        return []
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        result = _repair_json(raw)
        return [d for d in result if isinstance(d, dict) and d.get("action") in ("flag-misplaced", "flag-low-quality")]
    except json.JSONDecodeError:
        return []


def _call_audit_notes(
    notes: list[dict],
    folder_path: str,
    vault_structure: str,
    prefs_section: str,
    config: dict,
) -> list[dict]:
    """Audit all notes for quality and topical fit, in parallel batches.

    Notes are split into batches of _AUDIT_BATCH_SIZE and processed concurrently
    so audit quality stays high regardless of folder size.
    """
    if not notes:
        return []
    from concurrent.futures import ThreadPoolExecutor, as_completed
    audit_system = _load_prompt("restructure-audit-system.md")
    audit_user_tmpl = _load_prompt("restructure-audit-user.md")
    batches = [notes[i:i + _AUDIT_BATCH_SIZE] for i in range(0, len(notes), _AUDIT_BATCH_SIZE)]
    if len(batches) == 1:
        return _call_audit_notes_batch(batches[0], folder_path, vault_structure, prefs_section, config, audit_system, audit_user_tmpl)
    flags: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(len(batches), _AUDIT_MAX_WORKERS)) as executor:
        futures = {
            executor.submit(
                _call_audit_notes_batch, batch, folder_path, vault_structure, prefs_section, config, audit_system, audit_user_tmpl
            ): i
            for i, batch in enumerate(batches)
        }
        for future in as_completed(futures):
            try:
                flags.extend(future.result())
            except Exception:
                pass
    return flags

def _call_decisions(
    clusters: list[list[dict]],
    splits: list[dict],
    prefs_section: str,
    folder_context: str,
    config: dict,
    standalone: list[dict] | None = None,
    vault_structure: str = "",
    folder_note_count: int = 0,
) -> list[dict]:
    """Phase 1 LLM call: decide actions for all clusters and splits (no content generation)."""
    from cyberbrain.extractors.backends import call_model, BackendError, get_model_for_tool
    tool_config = {**config, "model": get_model_for_tool(config, "restructure")}
    _standalone = standalone or []
    decide_system = _load_prompt("restructure-decide-system.md")
    clusters_block = _build_cluster_summary_block(clusters)
    splits_block = _build_split_summary_block(splits)
    standalone_block = _build_standalone_notes_block(_standalone)
    user_msg = (
        _load_prompt("restructure-decide-user.md")
        .replace("{cluster_count}", str(len(clusters)))
        .replace("{split_count}", str(len(splits)))
        .replace("{standalone_count}", str(len(_standalone)))
        .replace("{vault_prefs_section}", prefs_section)
        .replace("{vault_structure}", vault_structure)
        .replace("{folder_context}", folder_context)
        .replace("{standalone_notes_block}", standalone_block)
        .replace("{clusters_summary_block}", clusters_block)
        .replace("{split_candidates_summary_block}", splits_block)
        .replace("{folder_note_count}", str(folder_note_count))
    )
    try:
        raw = call_model(decide_system, user_msg, tool_config)
    except BackendError as e:
        raise ToolError(f"Backend error during decision phase: {e}")
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        return _repair_json(raw)
    except json.JSONDecodeError as e:
        raise ToolError(f"LLM returned invalid JSON in decision phase: {e}\n\nRaw: {raw[:500]}")


def _call_generate_cluster(
    decision: dict,
    cluster_notes: list[dict],
    prefs_section: str,
    vault: Path,
    config: dict,
) -> dict:
    """Phase 2 LLM call: generate content for a single cluster decision."""
    from cyberbrain.extractors.backends import call_model, BackendError, get_model_for_tool
    tool_config = {**config, "model": get_model_for_tool(config, "restructure")}
    generate_system = _load_prompt("restructure-generate-system.md")
    action_desc = _format_action_description(decision)
    source_block = _format_cluster_block([cluster_notes], vault)
    user_msg = (
        _load_prompt("restructure-generate-user.md")
        .replace("{vault_prefs_section}", prefs_section)
        .replace("{action_description}", action_desc)
        .replace("{source_notes_block}", source_block)
    )
    try:
        raw = call_model(generate_system, user_msg, tool_config)
    except BackendError as e:
        raise ToolError(
            f"Backend error during generation for cluster {decision.get('cluster_index', '?')}: {e}"
        )
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise json.JSONDecodeError("expected object", raw, 0)
        return result
    except json.JSONDecodeError as e:
        raise ToolError(
            f"LLM returned invalid JSON in generation phase (cluster {decision.get('cluster_index', '?')}): "
            f"{e}\n\nRaw: {raw[:500]}"
        )


def _call_generate_split(
    decision: dict,
    split_note: dict,
    prefs_section: str,
    vault: Path,
    config: dict,
) -> dict:
    """Phase 2 LLM call: generate content for a single split decision."""
    from cyberbrain.extractors.backends import call_model, BackendError, get_model_for_tool
    tool_config = {**config, "model": get_model_for_tool(config, "restructure")}
    generate_system = _load_prompt("restructure-generate-system.md")
    action_desc = _format_action_description(decision)
    source_block = _format_cluster_block([[split_note]], vault)
    user_msg = (
        _load_prompt("restructure-generate-user.md")
        .replace("{vault_prefs_section}", prefs_section)
        .replace("{action_description}", action_desc)
        .replace("{source_notes_block}", source_block)
    )
    try:
        raw = call_model(generate_system, user_msg, tool_config)
    except BackendError as e:
        raise ToolError(
            f"Backend error during generation for split note {decision.get('note_index', '?')}: {e}"
        )
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise json.JSONDecodeError("expected object", raw, 0)
        return result
    except json.JSONDecodeError as e:
        raise ToolError(
            f"LLM returned invalid JSON in generation phase (split note {decision.get('note_index', '?')}): "
            f"{e}\n\nRaw: {raw[:500]}"
        )


def _is_gate_enabled(config: dict) -> bool:
    """Check if quality gate is enabled (default: True)."""
    return config.get("quality_gate_enabled", True)



def _gate_decisions(decisions: list[dict], clusters: list[list[dict]],
                    split_candidates: list[dict], config: dict) -> list[dict]:
    """Run quality gate on proposed decisions. Returns gate verdicts for each non-trivial decision.

    Each verdict dict has: decision_index, verdict, confidence, rationale, issues.
    Decisions that are simple (keep, keep-separate) skip the gate.
    """
    if not _is_gate_enabled(config):
        return []

    try:
        from quality_gate import quality_gate
    except ImportError:
        return []

    gate_results = []

    for i, decision in enumerate(decisions):
        action = decision.get("action", "")
        # Simple/no-op actions don't need gating
        if action in ("keep", "keep-separate", "flag-misplaced", "flag-low-quality"):
            continue

        # Build context describing what the decision proposes
        if "cluster_index" in decision:
            cidx = decision.get("cluster_index", -1)
            if cidx < 0 or cidx >= len(clusters):
                continue
            cluster = clusters[cidx]
            titles = [n["title"] for n in cluster]
            summaries = [n.get("summary", "") for n in cluster]
            input_ctx = (
                f"Cluster of {len(cluster)} notes proposed for action '{action}':\n"
                + "\n".join(f"- {t}: {s}" for t, s in zip(titles, summaries))
            )
        elif "note_index" in decision:
            nidx = decision.get("note_index", -1)
            if nidx < 0 or nidx >= len(split_candidates):
                continue
            note = split_candidates[nidx]
            input_ctx = (
                f"Large note proposed for action '{action}':\n"
                f"- {note['title']}: {note.get('summary', '')}\n"
                f"- Size: {len(note.get('content', ''))} chars"
            )
        else:
            continue

        output_text = json.dumps(decision, indent=2, default=str)
        if "cluster_index" in decision:
            op_action = decision.get("action", "merge")
            operation = "restructure_hub" if op_action in ("hub-spoke", "subfolder") else "restructure_merge"
        else:
            operation = "restructure_split"
        verdict = quality_gate(operation, input_ctx, output_text, config)

        gate_result = {
            "decision_index": i,
            "action": action,
            "verdict": verdict.verdict.value,
            "confidence": verdict.confidence,
            "rationale": verdict.rationale,
            "issues": verdict.issues,
            "passed": verdict.passed,
        }

        # If below threshold and not passed, mark the decision with gate info
        if not verdict.passed:
            decision["_gate_verdict"] = verdict.verdict.value
            decision["_gate_confidence"] = verdict.confidence
            decision["_gate_rationale"] = verdict.rationale
            decision["_gate_issues"] = verdict.issues
            if verdict.verdict.value == "uncertain":
                decision["_gate_needs_confirmation"] = True
            elif verdict.verdict.value == "fail":
                # Downgrade failed decisions to keep-separate/keep
                original_action = decision["action"]
                if "cluster_index" in decision:
                    decision["action"] = "keep-separate"
                else:
                    decision["action"] = "keep"
                decision["_gate_original_action"] = original_action
                decision["rationale"] = (
                    f"Quality gate failed (confidence: {verdict.confidence:.2f}): "
                    f"{verdict.rationale}. Original action was '{original_action}'."
                )

        gate_results.append(gate_result)

    return gate_results


def _gate_generated_content(decision: dict, config: dict) -> dict | None:
    """Run quality gate on generated content. Returns GateVerdict-like dict or None if skipped.

    On FAIL, returns the verdict with suggest_retry=True.
    """
    if not _is_gate_enabled(config):
        return None

    try:
        from quality_gate import quality_gate
    except ImportError:
        return None

    action = decision.get("action", "")

    # Determine the content to evaluate and the operation type
    if action in ("merge",):
        content = decision.get("merged_content", "")
        if not content:
            return None
        operation = "restructure_merge"
        input_ctx = f"Merge action for cluster {decision.get('cluster_index', '?')}"
    elif action in ("hub-spoke", "subfolder"):
        content = decision.get("hub_content", "")
        if not content:
            return None
        operation = "restructure_hub"
        input_ctx = f"{action} action for cluster {decision.get('cluster_index', '?')}"
    elif action in ("split", "split-subfolder"):
        notes = decision.get("output_notes", [])
        if not notes:
            return None
        content = "\n---\n".join(n.get("content", "") for n in notes)
        operation = "restructure_split"
        input_ctx = f"Split action for note {decision.get('note_index', '?')}"
    else:
        return None

    verdict = quality_gate(operation, input_ctx, content, config)
    return {
        "verdict": verdict.verdict.value,
        "confidence": verdict.confidence,
        "rationale": verdict.rationale,
        "issues": verdict.issues,
        "passed": verdict.passed,
        "suggest_retry": verdict.suggest_retry,
        "suggested_model": verdict.suggested_model,
    }


def _generate_all_parallel(
    decisions: list[dict],
    clusters: list[list[dict]],
    split_candidates: list[dict],
    prefs_section: str,
    vault: Path,
    config: dict,
) -> None:
    """Run all Phase 2 generation calls in parallel. Modifies decisions in-place.

    When the quality gate is enabled, generated content is validated. On FAIL,
    a single retry is attempted (with a stronger model if suggested). On
    UNCERTAIN, the gate verdict is attached to the decision for surfacing.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    gate_enabled = _is_gate_enabled(config)

    def _gen_one(decision: dict) -> None:
        action = decision.get("action", "")
        if "cluster_index" in decision and action in ("merge", "hub-spoke", "subfolder"):
            cidx = decision.get("cluster_index", -1)
            if 0 <= cidx < len(clusters):
                content = _call_generate_cluster(decision, clusters[cidx], prefs_section, vault, config)
                decision.update(content)
        elif "note_index" in decision and action in ("split", "split-subfolder"):
            nidx = decision.get("note_index", -1)
            if 0 <= nidx < len(split_candidates):
                content = _call_generate_split(decision, split_candidates[nidx], prefs_section, vault, config)
                decision.update(content)

        # Quality gate on generated content
        if gate_enabled:
            gate_result = _gate_generated_content(decision, config)
            if gate_result and not gate_result["passed"]:
                # Retry once on FAIL with stronger model if suggested
                if gate_result["verdict"] == "fail" and gate_result.get("suggest_retry"):
                    retry_config = dict(config)
                    if gate_result.get("suggested_model"):
                        retry_config["model"] = gate_result["suggested_model"]
                    # Re-generate
                    if "cluster_index" in decision and action in ("merge", "hub-spoke", "subfolder"):
                        cidx = decision.get("cluster_index", -1)
                        if 0 <= cidx < len(clusters):
                            try:
                                content = _call_generate_cluster(
                                    decision, clusters[cidx], prefs_section, vault, retry_config
                                )
                                decision.update(content)
                                # Re-check
                                gate_result = _gate_generated_content(decision, config)
                            except Exception:
                                pass
                    elif "note_index" in decision and action in ("split", "split-subfolder"):
                        nidx = decision.get("note_index", -1)
                        if 0 <= nidx < len(split_candidates):
                            try:
                                content = _call_generate_split(
                                    decision, split_candidates[nidx], prefs_section, vault, retry_config
                                )
                                decision.update(content)
                                gate_result = _gate_generated_content(decision, config)
                            except Exception:
                                pass

                # Attach gate info to the decision for surfacing
                if gate_result and not gate_result["passed"]:
                    decision["_gate_gen_verdict"] = gate_result["verdict"]
                    decision["_gate_gen_confidence"] = gate_result["confidence"]
                    decision["_gate_gen_rationale"] = gate_result["rationale"]
                    decision["_gate_gen_issues"] = gate_result["issues"]

    actionable = [
        d for d in decisions
        if d.get("action") not in ("keep", "keep-separate", "move-cluster", "flag-misplaced", "flag-low-quality")
    ]
    if not actionable:
        return
    with ThreadPoolExecutor(max_workers=min(len(actionable), 6)) as executor:
        futures = {executor.submit(_gen_one, d): d for d in actionable}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                pass


def _execute_cluster_decisions(
    decisions: list[dict],
    clusters: list[list[dict]],
    vault: Path,
    ts: str,
    result_lines: list[str],
    errata_entries: list[str],
    written_paths: list[Path],
    config: dict | None = None,
) -> tuple[int, int]:
    """Process cluster decisions (merge/hub-spoke/keep-separate). Returns (notes_created, notes_deleted)."""
    if config is None:
        config = {}
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

        elif action == "move-cluster":
            destination_rel = decision.get("destination", "")
            if not destination_rel:
                result_lines.append(f"  Cluster {cluster_idx}: move-cluster skipped — no destination")
                continue
            dest_dir = vault / destination_rel
            if not _is_within_vault(vault, dest_dir):
                result_lines.append(f"  Cluster {cluster_idx}: move-cluster skipped — path traversal rejected")
                continue
            dest_dir.mkdir(parents=True, exist_ok=True)
            moved_count = 0
            for src_path in source_paths:
                dest_path = dest_dir / src_path.name
                try:
                    src_path.rename(dest_path)
                    written_paths.append(dest_path)
                    moved_count += 1
                except OSError as e:
                    result_lines.append(f"    Warning: could not move {src_path.name}: {e}")
            result_lines.append(
                f"  Cluster {cluster_idx}: moved {moved_count} notes to '{destination_rel}' — {rationale}"
            )
            errata_entries.append(
                f"**Moved cluster:** {', '.join(repr(t) for t in source_titles)} → {destination_rel}/"
            )

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
                    _move_to_trash(src_path, vault, config)
                    notes_deleted += 1
                except OSError as e:
                    result_lines.append(f"    Warning: could not trash {src_path.name}: {e}")

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


def _format_gate_verdicts(decisions: list[dict], gate_results: list[dict]) -> str:
    """Format quality gate verdicts into human-readable output."""
    has_gen_gate = any(d.get("_gate_gen_verdict") for d in decisions)
    if not gate_results and not has_gen_gate:
        return ""
    lines = ["### Quality Gate Results\n"]
    has_issues = False
    for gr in gate_results:
        verdict = gr["verdict"]
        confidence = gr["confidence"]
        action = gr["action"]
        idx = gr["decision_index"]
        symbol = "PASS" if gr["passed"] else ("UNCERTAIN" if verdict == "uncertain" else "FAIL")
        line = f"- Decision {idx} ({action}): **{symbol}** (confidence: {confidence:.2f})"
        if gr.get("rationale"):
            line += f" — {gr['rationale']}"
        lines.append(line)
        if gr.get("issues"):
            for issue in gr["issues"]:
                lines.append(f"  - {issue}")
        if not gr["passed"]:
            has_issues = True

    # Surface generation-phase gate info from decisions
    for d in decisions:
        gen_verdict = d.get("_gate_gen_verdict")
        if gen_verdict and gen_verdict != "pass":
            action = d.get("action", "?")
            idx = d.get("cluster_index", d.get("note_index", "?"))
            lines.append(
                f"- Generated content ({action}, index {idx}): **{gen_verdict.upper()}** "
                f"(confidence: {d.get('_gate_gen_confidence', 0):.2f}) — "
                f"{d.get('_gate_gen_rationale', '')}"
            )
            for issue in d.get("_gate_gen_issues", []):
                lines.append(f"  - {issue}")
            has_issues = True

    if has_issues:
        lines.append("")
        lines.append(
            "**Note:** Some decisions were flagged by the quality gate. "
            "Failed decisions have been downgraded. Uncertain decisions may warrant review."
        )
        lines.append(
            "Call cb_configure(quality_gate_enabled=False) to disable quality gates."
        )

    return "\n".join(lines)


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
            elif action == "move-cluster":
                destination = decision.get("destination", "")
                lines.append(f"### Cluster {cluster_idx}: Move Cluster")
                lines.append(f"Notes: {titles}")
                lines.append(f"Destination: `{destination}`")
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
        min_cluster_size: Annotated[int, Field(
            ge=2, le=20,
            description="Minimum number of notes to form a cluster. Default: 2."
        )] = 2,
        max_clusters: Annotated[int, Field(
            ge=1, le=200,
            description="Maximum number of clusters to process in one run. Default: 100."
        )] = 100,
        split_threshold: Annotated[int, Field(
            ge=500,
            description="Minimum note size in characters to be considered a split candidate. Default: 3000."
        )] = 3000,
        max_splits: Annotated[int, Field(
            ge=1, le=100,
            description="Maximum number of large notes to evaluate for splitting in one run. Default: 50."
        )] = 50,
        preview: Annotated[bool, Field(
            description=(
                "Run the LLM and show the full proposed note content without writing any files. "
                "Use after dry_run=True to see exactly what would be written before committing. "
                "Mutually exclusive with dry_run=True. Set dry_run=False, preview=True to activate."
            )
        )] = False,
        grouping: Annotated[str, Field(
            description=(
                "Clustering strategy for folder_hub mode. "
                "'auto' uses embedding clustering with LLM fallback. "
                "'llm' uses LLM-driven semantic grouping. "
                "'embedding' uses deterministic embedding hierarchical clustering. "
                "'hybrid' uses embedding clustering then LLM validation. "
                "Default: 'auto'"
            )
        )] = "auto",
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
        from cyberbrain.extractors.backends import call_model, BackendError, get_model_for_tool

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
        vault_structure = _build_vault_structure(vault)
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

        # Validate grouping strategy
        valid_strategies = ("auto", "llm", "embedding", "hybrid")
        if grouping not in valid_strategies:
            raise ToolError(f"Invalid grouping strategy: {grouping!r}. Must be one of: {', '.join(valid_strategies)}")

        # ── FOLDER HUB MODE ────────────────────────────────────────────────────────
        if folder_hub:
            # Dispatch to the selected clustering strategy. Default 'auto' tries
            # embedding clustering first and falls back to LLM-driven grouping.
            folder_rel_for_group = str(scan_root.relative_to(vault))
            clusters = _dispatch_grouping(grouping, notes, folder_rel_for_group, prefs_section, config)
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
                        proposed = "subfolder" if len(cluster) >= 4 else "merge"
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

            # Audit all notes for quality and fit before structural decisions
            folder_rel_hub = str(scan_root.relative_to(vault))
            flag_decisions_hub: list[dict] = _call_audit_notes(notes, folder_rel_hub, vault_structure, prefs_section, config)

            # Remove flagged notes from clusters so they aren't merged/moved
            flagged_paths = {
                str(vault / d["note_path"])
                for d in flag_decisions_hub
                if d.get("action") in ("flag-misplaced", "flag-low-quality") and d.get("note_path")
            }
            if flagged_paths:
                filtered_clusters = []
                for cluster in clusters:
                    filtered = [n for n in cluster if str(n["path"]) not in flagged_paths]
                    if len(filtered) >= 2:
                        filtered_clusters.append(filtered)
                clusters = filtered_clusters

            if clusters:
                folder_context = _build_folder_context(scan_root, vault, notes, clusters)
                clustered_paths_hub = {str(n["path"]) for cl in clusters for n in cl}
                standalone_hub = [n for n in notes if str(n["path"]) not in clustered_paths_hub]

                # Phase 1a: decisions (summaries only — fast even for large folders)
                decisions1 = _call_decisions(
                    clusters, [], prefs_section, folder_context, config,
                    standalone=standalone_hub, vault_structure=vault_structure,
                    folder_note_count=len(notes),
                )

                # Phase 1b: generate content for non-flag decisions
                decisions1 = [d for d in decisions1 if d.get("action") not in ("flag-misplaced", "flag-low-quality")]

                # Quality gate on decisions
                decision_gate_results1 = _gate_decisions(decisions1, clusters, [], config)

                _generate_all_parallel(decisions1, clusters, [], prefs_section, vault, config)

                now = datetime.now(timezone.utc)
                ts = now.strftime("%Y-%m-%dT%H:%M:%S")
                if not preview:
                    nc, nd = _execute_cluster_decisions(
                        decisions1, clusters, vault, ts, result_lines, errata_entries, written_paths, config
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

            # Surface any flag decisions from Phase 1
            if "flag_decisions_hub" in dir() and flag_decisions_hub:
                result_lines.append("\n" + _format_flag_output(flag_decisions_hub))

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
                tool_config = {**config, "model": get_model_for_tool(config, "restructure")}
                raw2 = call_model(system_prompt, user_msg_phase2, tool_config)
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
                    elif action == "move-cluster":
                        preview_lines.append(f"Cluster {cidx}: Move cluster → `{d.get('destination', '')}` — {titles}")
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
                if flag_decisions_hub:
                    preview_lines.append("\n" + _format_flag_output(flag_decisions_hub))
                gate_section = _format_gate_verdicts(
                    decisions1 if isinstance(decisions1, list) else [],
                    decision_gate_results1 if clusters else [],
                )
                if gate_section:
                    preview_lines.append("\n" + gate_section)
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

            gate_section = _format_gate_verdicts(
                decisions1 if isinstance(decisions1, list) else [],
                decision_gate_results1 if clusters else [],
            )
            if gate_section:
                result_lines.append("")
                result_lines.append(gate_section)
            result_lines += ["", f"Notes created: {notes_created}", f"Notes deleted: {notes_deleted}"]
            if log_enabled and errata_entries:
                result_lines.append(f"Changes logged to: {log_rel}")
            _clear_groups_cache()
            return "\n".join(result_lines)

        # ── NORMAL MODE (cluster + split) ──────────────────────────────────────────
        clusters = _build_clusters(notes, backend, min_cluster_size)
        clusters = clusters[:max_clusters]
        clustered_paths = {str(n["path"]) for cluster in clusters for n in cluster}
        split_candidates = _find_split_candidates(notes, clustered_paths, split_threshold)[:max_splits]

        if not clusters and not split_candidates:
            return (
                f"Nothing to restructure (scanned {len(notes)} notes). "
                f"No clusters with {min_cluster_size}+ related notes and no notes over {split_threshold} chars. "
                "Try lowering min_cluster_size, split_threshold, "
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

        # Audit pass: quality and fit for every note (runs before structural decisions)
        folder_rel = str(scan_root.relative_to(vault))
        audit_flags = _call_audit_notes(notes, folder_rel, vault_structure, prefs_section, config)

        # Remove flagged notes from clusters so they aren't merged/moved
        flagged_paths_normal = {
            str(vault / d["note_path"])
            for d in audit_flags
            if d.get("action") in ("flag-misplaced", "flag-low-quality") and d.get("note_path")
        }
        if flagged_paths_normal:
            clusters = [
                [n for n in cluster if str(n["path"]) not in flagged_paths_normal]
                for cluster in clusters
            ]
            clusters = [c for c in clusters if len(c) >= 2]
            split_candidates = [n for n in split_candidates if str(n["path"]) not in flagged_paths_normal]

        # Phase 1: decisions (fast — summaries only, no content)
        folder_context = _build_folder_context(scan_root, vault, notes, clusters)
        clustered_note_paths = {str(n["path"]) for cluster in clusters for n in cluster}
        split_candidate_paths = {str(n["path"]) for n in split_candidates}
        standalone = [
            n for n in notes
            if str(n["path"]) not in clustered_note_paths
            and str(n["path"]) not in split_candidate_paths
        ]
        decisions = _call_decisions(
            clusters, split_candidates, prefs_section, folder_context, config,
            standalone=standalone, vault_structure=vault_structure,
            folder_note_count=len(notes),
        )
        if not isinstance(decisions, list):
            raise ToolError("LLM response was not a JSON array.")
        # Merge audit flags into decisions so they surface in output
        flag_decisions = audit_flags + [d for d in decisions if d.get("action") in ("flag-misplaced", "flag-low-quality")]
        decisions = [d for d in decisions if d.get("action") not in ("flag-misplaced", "flag-low-quality")]

        # Quality gate on decisions (before generation)
        decision_gate_results = _gate_decisions(decisions, clusters, split_candidates, config)

        # Phase 2: generate content for each decision that needs it (parallel)
        _generate_all_parallel(decisions, clusters, split_candidates, prefs_section, vault, config)

        if preview:
            out = _format_preview_output(decisions, clusters, split_candidates)
            gate_section = _format_gate_verdicts(decisions, decision_gate_results)
            if gate_section:
                out += "\n\n" + gate_section
            if flag_decisions:
                out += "\n\n" + _format_flag_output(flag_decisions)
            return out


        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y-%m-%dT%H:%M:%S")
        errata_entries: list[str] = []
        result_lines: list[str] = []
        written_paths: list[Path] = []

        nc, nd = _execute_cluster_decisions(decisions, clusters, vault, ts, result_lines, errata_entries, written_paths, config)
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
                        _move_to_trash(source_path, vault, config)
                        notes_deleted += 1
                    except OSError as e:
                        result_lines.append(f"  Warning: could not trash {source_path.name}: {e}")

                written_paths.extend(split_written)
                out_titles = [n.get("title", p.stem) for n, p in zip(output_notes, split_written)]
                result_lines.append(
                    f"Large note {note_idx} ({source_note['title']}): split into "
                    f"{len(split_written)} notes — {', '.join(repr(t) for t in out_titles)}"
                )
                errata_entries.append(
                    f"**Split:** **{source_note['title']}** → {', '.join(repr(t) for t in out_titles)}"
                )

            elif action == "split-subfolder":
                hub_content = decision.get("hub_content", "")
                hub_path_rel = decision.get("hub_path", "")
                output_notes = decision.get("output_notes", [])
                if not hub_path_rel or not hub_content or not output_notes:
                    result_lines.append(f"Large note {note_idx}: split-subfolder skipped — LLM did not return hub or notes")
                    continue
                hub_abs = vault / hub_path_rel
                if not _is_within_vault(vault, hub_abs):
                    result_lines.append(f"Large note {note_idx}: path traversal rejected for hub {hub_path_rel}")
                    continue
                hub_abs.parent.mkdir(parents=True, exist_ok=True)
                hub_abs.write_text(hub_content, encoding="utf-8")
                written_paths.append(hub_abs)
                notes_created += 1
                split_written_sf: list[Path] = []
                split_ok_sf = True
                for note_spec in output_notes:
                    note_path_rel = note_spec.get("path", "")
                    note_content = note_spec.get("content", "")
                    if not note_path_rel or not note_content:
                        result_lines.append(f"  Warning: skipping output note with missing path or content")
                        continue
                    out_path = vault / note_path_rel
                    if not _is_within_vault(vault, out_path):
                        result_lines.append(f"  Warning: path traversal rejected for {note_path_rel}")
                        split_ok_sf = False
                        continue
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(note_content, encoding="utf-8")
                    split_written_sf.append(out_path)
                    notes_created += 1
                if split_written_sf and split_ok_sf:
                    try:
                        _move_to_trash(source_path, vault, config)
                        notes_deleted += 1
                    except OSError as e:
                        result_lines.append(f"  Warning: could not trash {source_path.name}: {e}")
                written_paths.extend(split_written_sf)
                subfolder_name = decision.get("subfolder_path", hub_path_rel)
                out_titles_sf = [n.get("title", "") for n in output_notes]
                result_lines.append(
                    f"Large note {note_idx} ({source_note['title']}): split into subfolder '{subfolder_name}' — "
                    f"{len(split_written_sf) + 1} notes created"
                )
                errata_entries.append(
                    f"**Split-subfolder:** **{source_note['title']}** → {subfolder_name}/ "
                    f"({', '.join(repr(t) for t in out_titles_sf)})"
                )

        _index_paths(written_paths, config)
        _prune_index(config)

        log_enabled = config.get("consolidation_log_enabled", True)
        log_rel = config.get("consolidation_log", "AI/Cyberbrain-Log.md")
        if log_enabled and errata_entries:
            errata_entries.append(f"Notes deleted: {notes_deleted} | Notes created: {notes_created}")
            _append_errata_log(vault, log_rel, errata_entries)

        if flag_decisions:
            result_lines.append("")
            result_lines.append(_format_flag_output(flag_decisions))
        gate_section = _format_gate_verdicts(decisions, decision_gate_results)
        if gate_section:
            result_lines.append("")
            result_lines.append(gate_section)
        lines = ["## Restructure Complete\n"] + result_lines + [
            "",
            f"Notes created: {notes_created}",
            f"Notes deleted: {notes_deleted}",
        ]
        if log_enabled and errata_entries:
            lines.append(f"Changes logged to: {log_rel}")

        return "\n".join(lines)
