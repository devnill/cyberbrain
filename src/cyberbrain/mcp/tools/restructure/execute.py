"""Execution phase for cb_restructure — apply cluster decisions to vault files."""

import json
from pathlib import Path

from cyberbrain.mcp.shared import _is_within_vault, _move_to_trash
from cyberbrain.mcp.tools.restructure.format import _validate_frontmatter


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
                result_lines.append(
                    f"  Cluster {cluster_idx}: move-cluster skipped — no destination"
                )
                continue
            dest_dir = vault / destination_rel
            if not _is_within_vault(vault, dest_dir):
                result_lines.append(
                    f"  Cluster {cluster_idx}: move-cluster skipped — path traversal rejected"
                )
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
                    result_lines.append(
                        f"    Warning: could not move {src_path.name}: {e}"
                    )
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
                result_lines.append(
                    f"  Cluster {cluster_idx}: merge skipped — missing path or content"
                )
                continue

            output_path = vault / merged_path_rel
            if not _is_within_vault(vault, output_path):
                result_lines.append(
                    f"  Cluster {cluster_idx}: merge skipped — path traversal rejected"
                )
                continue

            provenance_lines = (
                f"\ncb_source: cb-restructure"
                f"\ncb_created: {ts}"
                f"\ncb_consolidated_from: {json.dumps(source_titles)}"
            )
            if merged_content.startswith("---"):
                end = merged_content.find("\n---", 3)
                if end != -1:
                    merged_content = (
                        merged_content[:end] + provenance_lines + merged_content[end:]
                    )

            result_lines.extend(
                _validate_frontmatter(
                    merged_content, f"Cluster {cluster_idx} merged note"
                )
            )
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
                    result_lines.append(
                        f"    Warning: could not trash {src_path.name}: {e}"
                    )

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
                result_lines.append(
                    f"  Cluster {cluster_idx}: hub-spoke skipped — missing path or content"
                )
                continue

            output_path = vault / hub_path_rel
            if not _is_within_vault(vault, output_path):
                result_lines.append(
                    f"  Cluster {cluster_idx}: hub-spoke skipped — path traversal rejected"
                )
                continue

            provenance_lines = f"\ncb_source: cb-restructure\ncb_created: {ts}"
            if hub_content.startswith("---"):
                end = hub_content.find("\n---", 3)
                if end != -1:
                    hub_content = (
                        hub_content[:end] + provenance_lines + hub_content[end:]
                    )

            result_lines.extend(
                _validate_frontmatter(hub_content, f"Cluster {cluster_idx} hub note")
            )
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
                result_lines.append(
                    f"  Cluster {cluster_idx}: subfolder skipped — missing path or content"
                )
                continue

            subfolder = vault / subfolder_path_rel
            hub_out = vault / hub_path_rel

            if not _is_within_vault(vault, subfolder) or not _is_within_vault(
                vault, hub_out
            ):
                result_lines.append(
                    f"  Cluster {cluster_idx}: subfolder skipped — path traversal rejected"
                )
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
                    result_lines.append(
                        f"    Warning: could not move {src_path.name}: {e}"
                    )

            # Write hub note inside the subfolder
            provenance_lines = f"\ncb_source: cb-restructure\ncb_created: {ts}"
            if hub_content.startswith("---"):
                end = hub_content.find("\n---", 3)
                if end != -1:
                    hub_content = (
                        hub_content[:end] + provenance_lines + hub_content[end:]
                    )

            result_lines.extend(
                _validate_frontmatter(
                    hub_content, f"Cluster {cluster_idx} subfolder hub"
                )
            )
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
