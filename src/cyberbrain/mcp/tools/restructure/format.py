"""Output formatters and content builders for cb_restructure."""

from datetime import UTC, datetime
from pathlib import Path

from cyberbrain.mcp.shared import _parse_frontmatter, update_vault_note, write_vault_note

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


def _format_folder_hub_block(
    notes: list[dict], vault: Path, hub_path: str = "", existing_hub: str = ""
) -> str:
    """Format all folder notes as a single hub-spoke cluster.

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
        existing_truncated = (
            existing_hub[:3000] + "\n...[truncated]"
            if len(existing_hub) > 3000
            else existing_hub
        )
        lines.append(f"\nExisting hub content:\n```\n{existing_truncated}\n```\n")
    else:
        lines += [
            "Create a hub/index note that organizes all notes in this folder into logical sections.",
            "Group related notes under themed ## headings. Each note gets a wikilink and one-line description.",
            "Do NOT merge or delete any notes — this is hub-spoke only.",
        ]
        if hub_path:
            lines.append(
                f"The hub note MUST be placed at this exact path: `{hub_path}`\n"
            )
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

    now = datetime.now(UTC)
    date_str = now.strftime("%Y-%m-%d")
    header = f"\n## {date_str} — Restructure Run\n\n"
    body = "\n".join(f"- {e}" for e in entries) + "\n"
    new_content = header + body

    if log_path.exists():
        existing = log_path.read_text(encoding="utf-8")
        update_vault_note(log_path, existing + new_content, str(vault))
    else:
        write_vault_note(log_path, new_content, str(vault))


def _build_folder_context(
    scan_root: Path, vault: Path, notes: list[dict], clusters: list[list[dict]]
) -> str:
    """Build a folder context block for the restructure LLM prompt.

    Provides relative signals (sibling folders, cluster density, note types,
    existing subfolder structure) so the LLM can make proportional decisions
    rather than relying on absolute word-count thresholds.
    """
    # Sibling folders at the same directory level
    parent = scan_root.parent
    siblings = sorted(
        d.name
        for d in parent.iterdir()
        if d.is_dir()
        and d.resolve() != scan_root.resolve()
        and not d.name.startswith(".")
    )

    # Does the target folder already have subfolders?
    existing_subfolders = (
        sorted(
            d.name
            for d in scan_root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
        if scan_root.exists()
        else []
    )

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
        lines.append(
            f"- **{note['title']}** (`{note['rel_path']}`){tags_str}: {summary}"
        )
    return "\n".join(lines)


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
        symbol = (
            "PASS"
            if gr["passed"]
            else ("UNCERTAIN" if verdict == "uncertain" else "FAIL")
        )
        line = (
            f"- Decision {idx} ({action}): **{symbol}** (confidence: {confidence:.2f})"
        )
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


def _format_preview_output(
    decisions: list, clusters: list[list[dict]], split_candidates: list[dict]
) -> str:
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
                lines.append(
                    f"### Large Note {note_idx} ({source['title']}): Keep As-Is"
                )
                lines.append(f"Rationale: {rationale}\n")
            elif action == "split":
                output_notes = decision.get("output_notes", [])
                lines.append(
                    f"### Large Note {note_idx} ({source['title']}): Split into {len(output_notes)} notes"
                )
                for spec in output_notes:
                    lines.append(
                        f"- **{spec.get('title', '')}** → `{spec.get('path', '')}`"
                    )
                    content = spec.get("content", "")
                    if len(content) > 2000:
                        content = content[:2000] + "\n...[truncated]"
                    lines.append(f"\n```markdown\n{content}\n```\n")
    lines.append(
        "To execute, call cb_restructure with the same parameters and preview=False."
    )
    return "\n".join(lines)
