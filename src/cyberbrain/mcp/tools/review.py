"""cb_review tool — review working memory notes that are due, and promote, extend, or delete."""

import json
import re
from datetime import UTC, date, datetime, timedelta
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
    _parse_frontmatter,
    _prune_index,
    update_vault_note,
    write_vault_note,
)
from cyberbrain.mcp.shared import (
    _load_tool_prompt as _load_prompt,
)

_PREFS_HEADING = "## Cyberbrain Preferences"


def _read_vault_prefs(vault_path: str) -> str:
    claude_md = Path(vault_path) / "CLAUDE.md"
    if not claude_md.exists():
        return ""
    text = claude_md.read_text(encoding="utf-8")
    idx = text.find(_PREFS_HEADING)
    if idx == -1:
        return ""
    rest = text[idx:]
    for m in re.finditer(r"^## ", rest, re.MULTILINE):
        if m.start() > 0:
            return rest[: m.start()].strip()
    return rest.strip()


def _find_due_notes(vault: Path, wm_root: Path, days_ahead: int) -> list[dict]:
    """Find working memory notes with cb_review_after <= today + days_ahead."""
    cutoff = date.today() + timedelta(days=days_ahead)
    due = []
    for path in sorted(wm_root.rglob("*.md")):
        if any(p.startswith(".") for p in path.parts):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fm = _parse_frontmatter(content)
        if not fm.get("cb_ephemeral"):
            continue
        review_after_raw = fm.get("cb_review_after", "")
        if not review_after_raw:
            continue
        try:
            review_after = date.fromisoformat(str(review_after_raw))
        except ValueError:
            continue
        if review_after <= cutoff:
            days_overdue = (date.today() - review_after).days
            due.append(
                {
                    "path": path,
                    "rel_path": str(path.relative_to(vault)),
                    "content": content,
                    "fm": fm,
                    "title": str(fm.get("title") or path.stem),
                    "summary": str(fm.get("summary", "")),
                    "tags": fm.get("tags", []),
                    "review_after": review_after,
                    "days_overdue": days_overdue,
                }
            )
    return due


def _cluster_notes(notes: list[dict], backend) -> list[list[int]]:
    """
    Group related notes into clusters using the search backend.
    Returns list of index groups. Singletons are their own cluster.
    """
    if len(notes) <= 1 or backend is None:
        return [[i] for i in range(len(notes))]

    note_paths = {str(n["path"]) for n in notes}
    path_to_idx = {str(n["path"]): i for i, n in enumerate(notes)}
    adjacency: dict[int, set[int]] = {i: set() for i in range(len(notes))}

    for i, note in enumerate(notes):
        query = f"{note['title']}. {note['summary']}"
        try:
            results = backend.search(query, top_k=6)
        except Exception:  # intentional: per-note search failure is non-fatal; skip adjacency for this note
            continue
        for result in results:
            rp = str(result.path)
            if rp == str(note["path"]) or rp not in note_paths:
                continue
            j = path_to_idx[rp]
            if result.score > 0:
                adjacency[i].add(j)
                adjacency[j].add(i)

    visited: set[int] = set()
    clusters: list[list[int]] = []
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
            for nb in adjacency[node]:
                if nb not in visited:
                    queue.append(nb)
        clusters.append(component)
    return clusters


def _format_notes_block(notes: list[dict], clusters: list[list[int]]) -> str:
    parts = []
    for cluster in clusters:
        if len(cluster) == 1:
            i = cluster[0]
            note = notes[i]
            overdue_str = (
                f"{note['days_overdue']} days overdue"
                if note["days_overdue"] > 0
                else "due today"
            )
            lines = [
                f"### Note {i}: {note['title']} ({overdue_str})",
                f"Path: {note['rel_path']}",
                f"Review after: {note['review_after']}",
            ]
            if note["summary"]:
                lines.append(f"Summary: {note['summary']}")
            body = note["content"]
            if len(body) > 2000:
                body = body[:2000] + "\n...[truncated]"
            lines.append(f"\n```\n{body}\n```")
            parts.append("\n".join(lines))
        else:
            header = f"### Cluster ({len(cluster)} related notes)"
            cluster_parts = [header]
            for i in cluster:
                note = notes[i]
                overdue_str = (
                    f"{note['days_overdue']} days overdue"
                    if note["days_overdue"] > 0
                    else "due today"
                )
                cluster_parts.append(f"\n**Note {i}: {note['title']}** ({overdue_str})")
                cluster_parts.append(f"Path: {note['rel_path']}")
                if note["summary"]:
                    cluster_parts.append(f"Summary: {note['summary']}")
                body = note["content"]
                if len(body) > 1200:
                    body = body[:1200] + "\n...[truncated]"
                cluster_parts.append(f"```\n{body}\n```")
            parts.append("\n".join(cluster_parts))
    return "\n\n---\n\n".join(parts)


def _extend_review_after(path: Path, weeks: int = 4, vault_path: str = "") -> bool:
    """Bump cb_review_after by `weeks` weeks. Returns True on success."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False

    new_date = (date.today() + timedelta(weeks=weeks)).isoformat()
    updated = re.sub(
        r"^cb_review_after:\s*.+$",
        f"cb_review_after: {new_date}",
        text,
        flags=re.MULTILINE,
    )
    if updated == text:
        return False
    try:
        update_vault_note(path, updated, vault_path)
        return True
    except (OSError, FileNotFoundError):
        return False


def _append_errata(vault: Path, config: dict, entries: list[str]) -> None:
    if not entries or not config.get("consolidation_log_enabled", True):
        return
    log_rel = config.get("consolidation_log", "AI/Cyberbrain-Log.md")
    log_path = vault / log_rel
    vault_path_str = str(vault)
    now = datetime.now(UTC)
    header = f"\n## {now.strftime('%Y-%m-%d')} — Working Memory Review\n\n"
    body = "\n".join(f"- {e}" for e in entries) + "\n"
    new_content = header + body
    if log_path.exists():
        existing = log_path.read_text(encoding="utf-8")
        update_vault_note(log_path, existing + new_content, vault_path_str)
    else:
        write_vault_note(log_path, new_content, vault_path_str)


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def cb_review(
        days_ahead: Annotated[
            int,
            Field(
                ge=0,
                le=90,
                description="Also include notes whose review date is within this many days (0 = only past-due notes).",
            ),
        ] = 0,
        folder: Annotated[
            str,
            Field(
                description="Vault-relative subfolder to scan. Defaults to your configured working_memory_folder."
            ),
        ] = "",
        dry_run: Annotated[
            bool,
            Field(
                description="Preview proposed actions without modifying any files. Always start here."
            ),
        ] = True,
        extend_weeks: Annotated[
            int,
            Field(
                ge=1,
                le=26,
                description="How many weeks to extend the review date when action is 'extend'. Default: 4.",
            ),
        ] = 4,
        limit: Annotated[
            int,
            Field(ge=0, description="Max notes to review in one run. 0 = no limit."),
        ] = 0,
    ) -> str:
        """
        Review working memory notes that are due and decide what to do with each one.

        For each note (or cluster of related notes), an LLM proposes one of:
        - promote: convert to a durable vault note (the note is valuable long-term)
        - extend: bump the review date forward (topic is still active)
        - delete: remove the note (no longer relevant)

        Always run dry_run=True first. Changes are logged to AI/Cyberbrain-Log.md.
        Working memory notes are created automatically from extraction when beats
        are classified as 'working-memory' durability.
        """
        from cyberbrain.extractors.backends import (
            BackendError,
            call_model,
            get_model_for_tool,
        )
        from cyberbrain.extractors.quality_gate import quality_gate as _quality_gate

        config = _load_config()
        gate_enabled = config.get("quality_gate_enabled", True)
        vault_path_str = config.get("vault_path", "")
        if not vault_path_str:
            raise ToolError(
                "No vault configured. Run cb_configure(vault_path=...) first."
            )

        vault = Path(vault_path_str).expanduser().resolve()
        if not vault.exists():
            raise ToolError(f"Vault path does not exist: {vault}")

        wm_root_rel = folder or config.get("working_memory_folder", "AI/Working Memory")
        wm_root = vault / wm_root_rel
        if not wm_root.exists():
            return f"Working memory folder not found: {wm_root_rel}\nNo working memory notes to review."

        notes = _find_due_notes(vault, wm_root, days_ahead)
        if not notes:
            return (
                f"No working memory notes due for review "
                f"(checked {wm_root_rel}, cutoff: today + {days_ahead} days)."
            )

        if limit > 0:
            notes = notes[:limit]

        if dry_run:
            lines = [f"[DRY RUN] {len(notes)} working memory note(s) due for review:\n"]
            for note in notes:
                overdue = (
                    f"{note['days_overdue']} days overdue"
                    if note["days_overdue"] > 0
                    else "due today"
                )
                lines.append(f"  - {note['title']} ({overdue}) → {note['rel_path']}")
            lines.append(
                "\nRun without dry_run=True to process. "
                "The LLM will propose promote / extend / delete for each note."
            )
            return "\n".join(lines)

        # Cluster related notes
        backend = _get_search_backend(config)
        clusters = _cluster_notes(notes, backend)

        vault_prefs = _read_vault_prefs(vault_path_str)
        prefs_section = f"Vault preferences:\n\n{vault_prefs}" if vault_prefs else ""
        notes_block = _format_notes_block(notes, clusters)

        system_prompt = _load_prompt("review-system.md")
        user_message = (
            _load_prompt("review-user.md")
            .replace("{note_count}", str(len(notes)))
            .replace("{vault_prefs_section}", prefs_section)
            .replace("{notes_block}", notes_block)
        )

        tool_config = {**config, "model": get_model_for_tool(config, "review")}
        try:
            raw = call_model(system_prompt, user_message, tool_config)
        except BackendError as e:
            raise ToolError(f"Backend error during review: {e}")

        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw).strip()

        try:
            decisions = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ToolError(f"LLM returned invalid JSON: {e}\n\nRaw:\n{raw[:400]}")

        if not isinstance(decisions, list):
            raise ToolError("LLM response was not a JSON array.")

        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
        errata: list[str] = []
        result_lines: list[str] = []
        gate_flagged: list[
            tuple[list[str], str, str, object]
        ] = []  # (titles, action, rationale, verdict)
        promoted = deleted = extended = 0
        written_paths: list[Path] = []

        # Track which note indices have been handled
        handled: set[int] = set()

        for decision in decisions:
            action = decision.get("action", "")
            indices = decision.get("indices", [])
            rationale = decision.get("rationale", "")
            if not indices:
                continue

            affected_notes = [notes[i] for i in indices if i < len(notes)]
            if not affected_notes:
                continue
            for i in indices:
                handled.add(i)

            titles = [n["title"] for n in affected_notes]

            # ── Quality gate ──
            if gate_enabled:
                gate_op = (
                    f"review_{action}"
                    if action in ("promote", "delete")
                    else "review_decide"
                )
                note_summaries = "\n".join(
                    f"- {n['title']} (overdue {n['days_overdue']}d): {n['summary']}"
                    for n in affected_notes
                )
                gate_input = f"Working memory notes:\n{note_summaries}"
                gate_output = json.dumps(decision)
                verdict = _quality_gate(gate_op, gate_input, gate_output, config)
                if not verdict.passed:
                    from cyberbrain.extractors.quality_gate import Verdict as _Verdict

                    if verdict.verdict == _Verdict.UNCERTAIN:
                        # Uncertain — flag for confirmation but still report
                        gate_flagged.append((titles, action, rationale, verdict))
                        result_lines.append(
                            f"**Needs confirmation** — {action} for {', '.join(repr(t) for t in titles)}: "
                            f"{verdict.rationale} (confidence: {verdict.confidence:.2f}). "
                            f"Call cb_configure(quality_gate_enabled=False) to disable quality gates."
                        )
                        continue
                    else:
                        # Failed — block entirely
                        gate_flagged.append((titles, action, rationale, verdict))
                        result_lines.append(
                            f"Gate blocked {action} for {', '.join(repr(t) for t in titles)} — "
                            f"{verdict.rationale} (confidence: {verdict.confidence:.2f}). "
                            f"Call cb_configure(quality_gate_enabled=False) to disable quality gates."
                        )
                        continue

            if action == "promote":
                promoted_title = decision.get("promoted_title", "Promoted Note")
                promoted_path_rel = decision.get("promoted_path", "")
                promoted_content = decision.get("promoted_content", "")

                if not promoted_path_rel or not promoted_content:
                    result_lines.append(
                        f"Promote skipped for {titles} — missing path or content"
                    )
                    continue

                output_path = vault / promoted_path_rel
                if not _is_within_vault(vault, output_path):
                    result_lines.append(
                        f"Promote skipped — path traversal rejected: {promoted_path_rel}"
                    )
                    continue

                # Inject provenance
                prov = f"\ncb_source: cb-review\ncb_created: {ts}"
                if promoted_content.startswith("---"):
                    end = promoted_content.find("\n---", 3)
                    if end != -1:
                        promoted_content = (
                            promoted_content[:end] + prov + promoted_content[end:]
                        )

                write_vault_note(output_path, promoted_content, vault_path_str)
                promoted += 1
                written_paths.append(output_path)

                for note in affected_notes:
                    try:
                        _move_to_trash(note["path"], vault, config)
                        deleted += 1
                    except OSError as e:
                        result_lines.append(
                            f"  Warning: could not trash {note['path'].name}: {e}"
                        )

                result_lines.append(
                    f"Promoted: {', '.join(repr(t) for t in titles)} → **{promoted_title}** ({promoted_path_rel})"
                )
                errata.append(
                    f"**Promoted:** {', '.join(titles)} → **{promoted_title}**"
                )

            elif action == "extend":
                extended_paths = []
                for note in affected_notes:
                    if _extend_review_after(note["path"], extend_weeks, vault_path_str):
                        extended += 1
                        extended_paths.append(note["title"])
                result_lines.append(
                    f"Extended ({extend_weeks}w): {', '.join(repr(t) for t in extended_paths)} — {rationale}"
                )

            elif action == "delete":
                for note in affected_notes:
                    try:
                        _move_to_trash(note["path"], vault, config)
                        deleted += 1
                        result_lines.append(f"Trashed: {note['title']} — {rationale}")
                        errata.append(f"**Trashed:** {note['title']}")
                    except OSError as e:
                        result_lines.append(
                            f"  Warning: could not trash {note['path'].name}: {e}"
                        )

            else:
                result_lines.append(f"Unknown action '{action}' for {titles} — skipped")

        # Handle any notes the LLM didn't address
        for i, note in enumerate(notes):
            if i not in handled:
                result_lines.append(
                    f"No decision returned for: {note['title']} — left unchanged"
                )

        _index_paths(written_paths, config)
        _prune_index(config)

        _append_errata(vault, config, errata)

        summary = (
            [
                "## Working Memory Review Complete\n",
            ]
            + result_lines
            + [
                "",
                f"Promoted:  {promoted}",
                f"Extended:  {extended}",
                f"Deleted:   {deleted}",
                f"Blocked:   {len(gate_flagged)}",
            ]
        )
        log_rel = config.get("consolidation_log", "AI/Cyberbrain-Log.md")
        if errata and config.get("consolidation_log_enabled", True):
            summary.append(f"Logged to:  {log_rel}")

        return "\n".join(summary)
