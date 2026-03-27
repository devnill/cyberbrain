"""cb_restructure tool — main orchestration and MCP registration."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from cyberbrain.mcp.shared import (
    _get_search_backend,
    _index_paths,
    _is_within_vault,
    _load_config,
    _move_to_trash,
    _prune_index,
    write_vault_note,
)
from cyberbrain.mcp.shared import (
    _load_tool_prompt as _load_prompt,
)
from cyberbrain.mcp.tools.restructure.audit import _call_audit_notes
from cyberbrain.mcp.tools.restructure.cache import _clear_groups_cache
from cyberbrain.mcp.tools.restructure.cluster import _build_clusters, _dispatch_grouping
from cyberbrain.mcp.tools.restructure.collect import (
    _collect_notes,
    _collect_notes_for_hub,
    _find_split_candidates,
    _read_vault_prefs,
)
from cyberbrain.mcp.tools.restructure.decide import _call_decisions, _gate_decisions
from cyberbrain.mcp.tools.restructure.execute import _execute_cluster_decisions
from cyberbrain.mcp.tools.restructure.format import (
    _append_errata_log,
    _build_folder_context,
    _build_vault_structure,
    _format_flag_output,
    _format_folder_hub_block,
    _format_gate_verdicts,
    _format_preview_output,
    _validate_frontmatter,
)
from cyberbrain.mcp.tools.restructure.generate import _generate_all_parallel
from cyberbrain.mcp.tools.restructure.utils import _repair_json


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def cb_restructure(
        folder: Annotated[
            str,
            Field(
                description="Vault-relative folder to scan, e.g. 'AI/LLM'. Empty string = entire vault."
            ),
        ] = "",
        dry_run: Annotated[
            bool,
            Field(
                description="Preview proposed changes without modifying any files. Always start here."
            ),
        ] = True,
        folder_hub: Annotated[
            bool,
            Field(
                description=(
                    "Create a hub/index note for the entire scanned folder, linking all notes organized "
                    "into logical sections. Also consolidates related notes within the folder first. "
                    "Requires folder to be specified. Originals are only deleted when notes are merged."
                )
            ),
        ] = False,
        hub_path: Annotated[
            str,
            Field(
                description=(
                    "Vault-relative path for the hub note when using folder_hub=True, e.g. "
                    "'Knowledge/Claude Code.md' (one level up) or 'Knowledge/Claude Code/index.md' (inside folder). "
                    "If empty, the LLM decides. If the file already exists it will be merged with new content."
                )
            ),
        ] = "",
        min_cluster_size: Annotated[
            int,
            Field(
                ge=2,
                le=20,
                description="Minimum number of notes to form a cluster. Default: 2.",
            ),
        ] = 2,
        max_clusters: Annotated[
            int,
            Field(
                ge=1,
                le=200,
                description="Maximum number of clusters to process in one run. Default: 100.",
            ),
        ] = 100,
        split_threshold: Annotated[
            int,
            Field(
                ge=500,
                description="Minimum note size in characters to be considered a split candidate. Default: 3000.",
            ),
        ] = 3000,
        max_splits: Annotated[
            int,
            Field(
                ge=1,
                le=100,
                description="Maximum number of large notes to evaluate for splitting in one run. Default: 50.",
            ),
        ] = 50,
        preview: Annotated[
            bool,
            Field(
                description=(
                    "Run the LLM and show the full proposed note content without writing any files. "
                    "Use after dry_run=True to see exactly what would be written before committing. "
                    "Mutually exclusive with dry_run=True. Set dry_run=False, preview=True to activate."
                )
            ),
        ] = False,
        grouping: Annotated[
            str,
            Field(
                description=(
                    "Clustering strategy for folder_hub mode. "
                    "'auto' uses embedding clustering with LLM fallback. "
                    "'llm' uses LLM-driven semantic grouping. "
                    "'embedding' uses deterministic embedding hierarchical clustering. "
                    "'hybrid' uses embedding clustering then LLM validation. "
                    "Default: 'auto'"
                )
            ),
        ] = "auto",
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
        from cyberbrain.extractors.backends import (
            BackendError,
            call_model,
            get_model_for_tool,
        )

        config = _load_config()
        vault_path_str = config.get("vault_path", "")
        if not vault_path_str:
            raise ToolError(
                "No vault configured. Run cb_configure(vault_path=...) first."
            )

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
        notes = _collect_notes(
            scan_root,
            vault,
            excluded_folders,
            exclude_paths=hub_exclude,
            shallow=folder_hub,
        )
        if not notes:
            return (
                f"No eligible notes found in {'vault' if not folder else repr(folder)}."
            )

        # Ensure all notes in the target folder are indexed before clustering.
        # Notes added since the last reindex won't appear in search results otherwise.
        backend = _get_search_backend(config)
        _index_paths([n["path"] for n in notes], config)

        # Validate grouping strategy
        valid_strategies = ("auto", "llm", "embedding", "hybrid")
        if grouping not in valid_strategies:
            raise ToolError(
                f"Invalid grouping strategy: {grouping!r}. Must be one of: {', '.join(valid_strategies)}"
            )

        # ── FOLDER HUB MODE ────────────────────────────────────────────────────────
        if folder_hub:
            # Dispatch to the selected clustering strategy. Default 'auto' tries
            # embedding clustering first and falls back to LLM-driven grouping.
            folder_rel_for_group = str(scan_root.relative_to(vault))
            clusters = _dispatch_grouping(
                grouping, notes, folder_rel_for_group, prefs_section, config
            )
            clusters = clusters[:max_clusters]

            existing_hub = (
                hub_abs.read_text(encoding="utf-8")
                if hub_abs and hub_abs.exists()
                else ""
            )
            hub_path_display = hub_path if hub_path else "(LLM will decide)"
            hub_status = (
                "will be merged with new content" if existing_hub else "will be created"
            )

            if dry_run:
                lines = [
                    f"[DRY RUN] Folder hub mode for '{folder}':",
                    "",
                    f"Step 1 — Consolidate within folder ({len(clusters)} cluster(s) found):",
                ]
                if clusters:
                    for idx, cluster in enumerate(clusters):
                        proposed = "subfolder" if len(cluster) >= 4 else "merge"
                        lines.append(
                            f"  Cluster {idx + 1} ({len(cluster)} notes) → proposed {proposed}:"
                        )
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
            result_lines: list[str] = [
                "## Folder Hub Restructure\n",
                "### Phase 1: Consolidate\n",
            ]
            errata_entries: list[str] = []
            written_paths: list[Path] = []

            # Audit all notes for quality and fit before structural decisions
            folder_rel_hub = str(scan_root.relative_to(vault))
            flag_decisions_hub: list[dict] = _call_audit_notes(
                notes, folder_rel_hub, vault_structure, prefs_section, config
            )

            # Remove flagged notes from clusters so they aren't merged/moved
            flagged_paths = {
                str(vault / d["note_path"])
                for d in flag_decisions_hub
                if d.get("action") in ("flag-misplaced", "flag-low-quality")
                and d.get("note_path")
            }
            if flagged_paths:
                filtered_clusters = []
                for cluster in clusters:
                    filtered = [
                        n for n in cluster if str(n["path"]) not in flagged_paths
                    ]
                    if len(filtered) >= 2:
                        filtered_clusters.append(filtered)
                clusters = filtered_clusters

            if clusters:
                folder_context = _build_folder_context(
                    scan_root, vault, notes, clusters
                )
                clustered_paths_hub = {str(n["path"]) for cl in clusters for n in cl}
                standalone_hub = [
                    n for n in notes if str(n["path"]) not in clustered_paths_hub
                ]

                # Phase 1a: decisions (summaries only — fast even for large folders)
                decisions1 = _call_decisions(
                    clusters,
                    [],
                    prefs_section,
                    folder_context,
                    config,
                    standalone=standalone_hub,
                    vault_structure=vault_structure,
                    folder_note_count=len(notes),
                )

                # Phase 1b: generate content for non-flag decisions
                decisions1 = [
                    d
                    for d in decisions1
                    if d.get("action") not in ("flag-misplaced", "flag-low-quality")
                ]

                # Quality gate on decisions
                decision_gate_results1 = _gate_decisions(
                    decisions1, clusters, [], config
                )

                _generate_all_parallel(
                    decisions1, clusters, [], prefs_section, vault, config
                )

                now = datetime.now(UTC)
                ts = now.strftime("%Y-%m-%dT%H:%M:%S")
                if not preview:
                    nc, nd = _execute_cluster_decisions(
                        decisions1,
                        clusters,
                        vault,
                        ts,
                        result_lines,
                        errata_entries,
                        written_paths,
                        config,
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
            notes_after = _collect_notes_for_hub(
                scan_root, vault, excluded_folders, exclude_paths=hub_exclude
            )
            # Re-read existing hub (may have been updated if it was in the folder)
            existing_hub = (
                hub_abs.read_text(encoding="utf-8")
                if hub_abs and hub_abs.exists()
                else ""
            )

            hub_block = _format_folder_hub_block(
                notes_after, vault, hub_path=hub_path, existing_hub=existing_hub
            )
            folder_context_p2 = _build_folder_context(scan_root, vault, notes_after, [])
            user_msg_phase2 = (
                _load_prompt("restructure-user.md")
                .replace("{cluster_count}", "1")
                .replace("{split_count}", "0")
                .replace("{vault_prefs_section}", prefs_section)
                .replace("{folder_context}", folder_context_p2)
                .replace("{clusters_block}", hub_block)
                .replace(
                    "{split_candidates_block}",
                    "_No split candidates in folder hub mode._",
                )
            )
            try:
                tool_config = {
                    **config,
                    "model": get_model_for_tool(config, "restructure"),
                }
                raw2 = call_model(system_prompt, user_msg_phase2, tool_config)
            except BackendError as e:
                raise ToolError(f"Backend error during hub creation phase: {e}")

            raw2 = re.sub(r"^```(?:json)?\s*", "", raw2.strip())
            raw2 = re.sub(r"\s*```$", "", raw2).strip()
            try:
                decisions2 = _repair_json(raw2)
            except json.JSONDecodeError as e:
                raise ToolError(
                    f"LLM returned invalid JSON in hub phase: {e}\n\nRaw: {raw2[:500]}"
                )

            if preview:
                preview_lines = [
                    "## Preview — Folder Hub Restructure (no files written)\n"
                ]
                preview_lines.append("### Phase 1: Cluster Consolidation\n")
                for d in decisions1 if isinstance(decisions1, list) else []:
                    if "cluster_index" not in d:
                        continue
                    cidx = d.get("cluster_index", -1)
                    action = d.get("action", "")
                    if cidx < 0 or cidx >= len(clusters):
                        continue
                    cluster = clusters[cidx]
                    titles = ", ".join(f"'{n['title']}'" for n in cluster)
                    if action == "keep-separate":
                        preview_lines.append(
                            f"Cluster {cidx}: Keep separate — {titles}"
                        )
                    elif action == "move-cluster":
                        preview_lines.append(
                            f"Cluster {cidx}: Move cluster → `{d.get('destination', '')}` — {titles}"
                        )
                    elif action == "merge":
                        content = d.get("merged_content", "")
                        if len(content) > 3000:
                            content = content[:3000] + "\n...[truncated]"
                        preview_lines.append(
                            f"Cluster {cidx}: Merge → **{d.get('merged_title', '')}** (`{d.get('merged_path', '')}`)"
                        )
                        preview_lines.append(f"\n```markdown\n{content}\n```\n")
                    elif action == "hub-spoke":
                        content = d.get("hub_content", "")
                        if len(content) > 3000:
                            content = content[:3000] + "\n...[truncated]"
                        preview_lines.append(
                            f"Cluster {cidx}: Hub-spoke → **{d.get('hub_title', '')}** (`{d.get('hub_path', '')}`)"
                        )
                        preview_lines.append(f"\n```markdown\n{content}\n```\n")
                preview_lines.append("\n### Phase 2: Hub Note\n")
                for d in decisions2 if isinstance(decisions2, list) else []:
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
                preview_lines.append(
                    "To execute, call cb_restructure with the same parameters and preview=False."
                )
                return "\n".join(preview_lines)

            for decision in decisions2 if isinstance(decisions2, list) else []:
                if decision.get("action") != "hub-spoke":
                    continue
                hub_title = decision.get("hub_title", "Hub")
                # Caller-supplied hub_path takes precedence
                final_hub_path = hub_path if hub_path else decision.get("hub_path", "")
                hub_content = decision.get("hub_content", "")

                if not final_hub_path or not hub_content:
                    result_lines.append(
                        "  Hub creation skipped — missing path or content from LLM."
                    )
                    break

                out = vault / final_hub_path
                now2 = datetime.now(UTC)
                ts2 = now2.strftime("%Y-%m-%dT%H:%M:%S")
                provenance = f"\ncb_source: cb-restructure\ncb_created: {ts2}"
                if hub_content.startswith("---"):
                    end = hub_content.find("\n---", 3)
                    if end != -1:
                        hub_content = hub_content[:end] + provenance + hub_content[end:]

                result_lines.extend(
                    _validate_frontmatter(hub_content, "Folder hub note")
                )
                try:
                    write_vault_note(out, hub_content, str(vault))
                except ValueError:
                    result_lines.append(
                        "  Hub creation skipped — path traversal rejected."
                    )
                    break
                notes_created += 1
                written_paths.append(out)

                action_word = "Updated" if existing_hub else "Created"
                hub_rel = str(out.relative_to(vault))
                result_lines.append(
                    f"  {action_word} hub: **{hub_title}** ({hub_rel}) linking {len(notes_after)} notes"
                )
                errata_entries.append(
                    f"**Hub {action_word.lower()}:** **{hub_title}** linking {len(notes_after)} notes"
                )
                break
            else:
                result_lines.append(
                    "  Hub creation skipped — LLM did not return a hub-spoke decision."
                )

            _index_paths(written_paths, config)
            _prune_index(config)

            log_enabled = config.get("consolidation_log_enabled", True)
            log_rel = config.get("consolidation_log", "AI/Cyberbrain-Log.md")
            if log_enabled and errata_entries:
                errata_entries.append(
                    f"Notes deleted: {notes_deleted} | Notes created: {notes_created}"
                )
                _append_errata_log(vault, log_rel, errata_entries)

            gate_section = _format_gate_verdicts(
                decisions1 if isinstance(decisions1, list) else [],
                decision_gate_results1 if clusters else [],
            )
            if gate_section:
                result_lines.append("")
                result_lines.append(gate_section)
            result_lines += [
                "",
                f"Notes created: {notes_created}",
                f"Notes deleted: {notes_deleted}",
            ]
            if log_enabled and errata_entries:
                result_lines.append(f"Changes logged to: {log_rel}")
            _clear_groups_cache()
            return "\n".join(result_lines)

        # ── NORMAL MODE (cluster + split) ──────────────────────────────────────────
        clusters = _build_clusters(notes, backend, min_cluster_size)
        clusters = clusters[:max_clusters]
        clustered_paths = {str(n["path"]) for cluster in clusters for n in cluster}
        split_candidates = _find_split_candidates(
            notes, clustered_paths, split_threshold
        )[:max_splits]

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
                proposed = (
                    "subfolder"
                    if density >= 0.25 and len(cluster) >= 5
                    else ("hub-and-spoke" if len(cluster) >= 6 else "merge")
                )
                lines.append(f"  → Proposed action: {proposed}")
                lines.append("")
            if split_candidates:
                lines.append("Large notes (split candidates):")
                for note in split_candidates:
                    size_kb = len(note["content"]) / 1000
                    lines.append(
                        f"  - {note['title']} ({note['rel_path']}) — {size_kb:.1f}KB"
                    )
                lines.append("")
            lines.append(
                "Run with dry_run=False to execute. "
                "The LLM will make final decisions on each cluster and large note."
            )
            return "\n".join(lines)

        # Audit pass: quality and fit for every note (runs before structural decisions)
        folder_rel = str(scan_root.relative_to(vault))
        audit_flags = _call_audit_notes(
            notes, folder_rel, vault_structure, prefs_section, config
        )

        # Remove flagged notes from clusters so they aren't merged/moved
        flagged_paths_normal = {
            str(vault / d["note_path"])
            for d in audit_flags
            if d.get("action") in ("flag-misplaced", "flag-low-quality")
            and d.get("note_path")
        }
        if flagged_paths_normal:
            clusters = [
                [n for n in cluster if str(n["path"]) not in flagged_paths_normal]
                for cluster in clusters
            ]
            clusters = [c for c in clusters if len(c) >= 2]
            split_candidates = [
                n
                for n in split_candidates
                if str(n["path"]) not in flagged_paths_normal
            ]

        # Phase 1: decisions (fast — summaries only, no content)
        folder_context = _build_folder_context(scan_root, vault, notes, clusters)
        clustered_note_paths = {str(n["path"]) for cluster in clusters for n in cluster}
        split_candidate_paths = {str(n["path"]) for n in split_candidates}
        standalone = [
            n
            for n in notes
            if str(n["path"]) not in clustered_note_paths
            and str(n["path"]) not in split_candidate_paths
        ]
        decisions = _call_decisions(
            clusters,
            split_candidates,
            prefs_section,
            folder_context,
            config,
            standalone=standalone,
            vault_structure=vault_structure,
            folder_note_count=len(notes),
        )
        if not isinstance(decisions, list):
            raise ToolError("LLM response was not a JSON array.")
        # Merge audit flags into decisions so they surface in output
        flag_decisions = audit_flags + [
            d
            for d in decisions
            if d.get("action") in ("flag-misplaced", "flag-low-quality")
        ]
        decisions = [
            d
            for d in decisions
            if d.get("action") not in ("flag-misplaced", "flag-low-quality")
        ]

        # Quality gate on decisions (before generation)
        decision_gate_results = _gate_decisions(
            decisions, clusters, split_candidates, config
        )

        # Phase 2: generate content for each decision that needs it (parallel)
        _generate_all_parallel(
            decisions, clusters, split_candidates, prefs_section, vault, config
        )

        if preview:
            out = _format_preview_output(decisions, clusters, split_candidates)
            gate_section = _format_gate_verdicts(decisions, decision_gate_results)
            if gate_section:
                out += "\n\n" + gate_section
            if flag_decisions:
                out += "\n\n" + _format_flag_output(flag_decisions)
            return out

        now = datetime.now(UTC)
        ts = now.strftime("%Y-%m-%dT%H:%M:%S")
        errata_entries = []
        result_lines = []
        written_paths = []

        nc, nd = _execute_cluster_decisions(
            decisions,
            clusters,
            vault,
            ts,
            result_lines,
            errata_entries,
            written_paths,
            config,
        )
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
                result_lines.append(
                    f"Large note {note_idx} ({source_note['title']}): kept as-is — {rationale}"
                )
                continue

            if action == "split":
                output_notes = decision.get("output_notes", [])
                if not output_notes:
                    result_lines.append(
                        f"Large note {note_idx}: split skipped — no output notes provided"
                    )
                    continue

                split_written: list[Path] = []
                split_ok = True
                for note_spec in output_notes:
                    note_path_rel = note_spec.get("path", "")
                    note_content = note_spec.get("content", "")
                    if not note_path_rel or not note_content:
                        result_lines.append(
                            "  Warning: skipping output note with missing path or content"
                        )
                        continue
                    out_path = vault / note_path_rel
                    provenance_lines = (
                        f"\ncb_source: cb-restructure"
                        f"\ncb_created: {ts}"
                        f"\ncb_split_from: {json.dumps(source_note['title'])}"
                    )
                    if note_content.startswith("---"):
                        end = note_content.find("\n---", 3)
                        if end != -1:
                            note_content = (
                                note_content[:end]
                                + provenance_lines
                                + note_content[end:]
                            )
                    result_lines.extend(
                        _validate_frontmatter(
                            note_content, f"Split note {note_path_rel}"
                        )
                    )
                    try:
                        write_vault_note(out_path, note_content, str(vault))
                    except ValueError:
                        result_lines.append(
                            f"  Warning: path traversal rejected for {note_path_rel}"
                        )
                        split_ok = False
                        continue
                    split_written.append(out_path)
                    notes_created += 1

                if split_written and split_ok:
                    try:
                        _move_to_trash(source_path, vault, config)
                        notes_deleted += 1
                    except OSError as e:
                        result_lines.append(
                            f"  Warning: could not trash {source_path.name}: {e}"
                        )

                written_paths.extend(split_written)
                out_titles = [
                    n.get("title", p.stem) for n, p in zip(output_notes, split_written)
                ]
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
                    result_lines.append(
                        f"Large note {note_idx}: split-subfolder skipped — LLM did not return hub or notes"
                    )
                    continue
                hub_abs = vault / str(hub_path_rel)
                try:
                    write_vault_note(hub_abs, hub_content, str(vault))
                except ValueError:
                    result_lines.append(
                        f"Large note {note_idx}: path traversal rejected for hub {hub_path_rel}"
                    )
                    continue
                written_paths.append(hub_abs)
                notes_created += 1
                split_written_sf: list[Path] = []
                split_ok_sf = True
                for note_spec in output_notes:
                    note_path_rel = note_spec.get("path", "")
                    note_content = note_spec.get("content", "")
                    if not note_path_rel or not note_content:
                        result_lines.append(
                            "  Warning: skipping output note with missing path or content"
                        )
                        continue
                    out_path = vault / note_path_rel
                    try:
                        write_vault_note(out_path, note_content, str(vault))
                    except ValueError:
                        result_lines.append(
                            f"  Warning: path traversal rejected for {note_path_rel}"
                        )
                        split_ok_sf = False
                        continue
                    split_written_sf.append(out_path)
                    notes_created += 1
                if split_written_sf and split_ok_sf:
                    try:
                        _move_to_trash(source_path, vault, config)
                        notes_deleted += 1
                    except OSError as e:
                        result_lines.append(
                            f"  Warning: could not trash {source_path.name}: {e}"
                        )
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
            errata_entries.append(
                f"Notes deleted: {notes_deleted} | Notes created: {notes_created}"
            )
            _append_errata_log(vault, log_rel, errata_entries)

        if flag_decisions:
            result_lines.append("")
            result_lines.append(_format_flag_output(flag_decisions))
        gate_section = _format_gate_verdicts(decisions, decision_gate_results)
        if gate_section:
            result_lines.append("")
            result_lines.append(gate_section)
        lines = (
            ["## Restructure Complete\n"]
            + result_lines
            + [
                "",
                f"Notes created: {notes_created}",
                f"Notes deleted: {notes_deleted}",
            ]
        )
        if log_enabled and errata_entries:
            lines.append(f"Changes logged to: {log_rel}")

        return "\n".join(lines)
