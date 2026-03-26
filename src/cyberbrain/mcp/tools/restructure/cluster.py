"""Clustering strategies for cb_restructure."""

import json
import re

from cyberbrain.extractors.state import search_manifest_path as _search_manifest_path
from cyberbrain.mcp.shared import _load_tool_prompt as _load_prompt
from cyberbrain.mcp.tools.restructure.cache import (
    _load_groups_cache,
    _save_groups_cache,
)
from cyberbrain.mcp.tools.restructure.format import _build_audit_notes_block
from cyberbrain.mcp.tools.restructure.utils import _repair_json


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

    from cyberbrain.extractors.backends import (
        BackendError,
        call_model,
        get_model_for_tool,
    )

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
    import numpy as np  # type: ignore[import-not-found]  # optional dependency

    # Load manifest for id_map and embedding_dim
    manifest_path = _search_manifest_path()
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
        from usearch.index import Index  # noqa: I001  # type: ignore[import-not-found]  # optional dependency

        idx = Index(ndim=embedding_dim, metric="cos", dtype="f32")
        idx.load(str(index_path))
    except Exception:  # intentional: usearch import or index load can fail if not installed or index is corrupt
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

    # Adaptive threshold from corpus statistics: adjusts to the vault's embedding
    # distribution so that terse technical vaults and verbose narrative vaults both
    # cluster appropriately. Formula: median - 0.5 * std, clamped to [0.15, 0.40].
    n = len(valid_notes)
    off_diag = dist_matrix[np.triu_indices(n, k=1)]
    if len(off_diag) > 2:
        median_dist = float(np.median(off_diag))
        std_dist = float(np.std(off_diag))
        adaptive_threshold = max(0.15, min(0.40, median_dist - 0.5 * std_dist))
    else:
        adaptive_threshold = 0.30
    distance_threshold = adaptive_threshold

    # Average-linkage agglomerative clustering (no scipy needed)
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
    from cyberbrain.extractors.backends import (
        BackendError,
        call_model,
        get_model_for_tool,
    )

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
        + "\n\n"
        + hint_section
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
        result = (
            clusters
            if clusters
            else _call_group_notes(notes, folder_path, prefs_section, config)
        )
    elif strategy == "hybrid":
        # Algorithmic pre-group, then LLM validates/refines
        clusters = _embedding_hierarchical_clusters(notes, config)
        if not clusters:
            result = _call_group_notes(notes, folder_path, prefs_section, config)
        else:
            result = _llm_validate_clusters(
                clusters, notes, folder_path, prefs_section, config
            )
    else:  # "auto"
        clusters = _embedding_hierarchical_clusters(notes, config)
        result = (
            clusters
            if clusters
            else _call_group_notes(notes, folder_path, prefs_section, config)
        )

    # Cache for subsequent calls (preview, execute)
    _save_groups_cache(folder_path, result, strategy=strategy)
    return result


def _build_clusters(
    notes: list[dict], backend, min_cluster_size: int
) -> list[list[dict]]:
    """Build clusters of related notes using the search backend.

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
    _STOP = {
        "claude",
        "code",
        "the",
        "and",
        "for",
        "with",
        "using",
        "how",
        "what",
        "why",
        "non",
        "vs",
    }

    # edge_weight[i][j] = number of per-word searches where note i found note j.
    # Requiring weight >= 2 avoids false adjacency through incidental shared words.
    edge_weight: dict[int, dict[int, int]] = {i: {} for i in range(len(notes))}

    for i, note in enumerate(notes):
        # Search for each distinctive word individually (single-term FTS5 query =
        # "contains this word"). Count how many of note i's searches return note j
        # to measure how strongly they are related.
        all_text = f"{note['title']} {note['summary']} {' '.join(note['tags'])}"
        words = [
            w.lower()
            for w in re.sub(r"[^\w\s]", " ", all_text).split()
            if len(w) > 2 and w.lower() not in _STOP
        ]
        seen: set[str] = set()
        unique_words = [w for w in words if not (w in seen or seen.add(w))][:6]  # type: ignore[func-returns-value]

        for word in unique_words:
            try:
                for result in backend.search(word, top_k=top_k):
                    rp = str(result.path)
                    if (
                        rp != str(note["path"])
                        and rp in note_paths
                        and result.score > 0
                    ):
                        j = path_to_idx[rp]
                        edge_weight[i][j] = edge_weight[i].get(j, 0) + 1
            except Exception:  # intentional: per-word search failure is non-fatal; skip this word's adjacency contribution
                continue

    # Build adjacency from strong edges only.
    # A pair is adjacent if BOTH notes found the other in >= 2 of their per-word searches
    # (mutual edge requirement). This prevents over-merging through transitive closure
    # caused by asymmetric word-search results where one side picks up spurious matches.
    for i in range(len(notes)):
        for j, w in edge_weight[i].items():
            if w >= 2 and edge_weight[j].get(i, 0) >= 2:
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
    """Simple tag-based clustering fallback when no search backend is available.

    Groups notes that share 2+ tags.
    """
    from collections import defaultdict

    tag_to_notes: dict[str, list[int]] = defaultdict(list)
    for i, note in enumerate(notes):
        for tag in note["tags"]:
            tag_to_notes[tag.lower()].append(i)

    adjacency: dict[int, set[int]] = {i: set() for i in range(len(notes))}
    pair_shared: dict[tuple, int] = {}
    for _tag, idxs in tag_to_notes.items():
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
