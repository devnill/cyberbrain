"""Groups cache save/load/clear for cb_restructure."""

import json

from cyberbrain.extractors.state import groups_cache_path as _groups_cache_path


def _save_groups_cache(
    folder_path: str, clusters: list[list[dict]], strategy: str = ""
) -> None:
    """Save grouping result to cache so dry_run → preview → execute stay consistent."""
    cache_data = {
        "folder": folder_path,
        "strategy": strategy,
        "groups": [[n["rel_path"] for n in cluster] for cluster in clusters],
    }
    try:
        _groups_cache_path().write_text(json.dumps(cache_data), encoding="utf-8")
    except OSError:
        pass


def _load_groups_cache(
    folder_path: str, notes: list[dict], strategy: str = ""
) -> list[list[dict]] | None:
    """Load cached grouping if it exists and matches the folder and strategy. Returns None on miss."""
    try:
        data = json.loads(_groups_cache_path().read_text(encoding="utf-8"))
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
        _groups_cache_path().unlink(missing_ok=True)
    except OSError:
        pass
