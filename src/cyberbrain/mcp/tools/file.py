"""cb_file tool — file a specific piece of information into the vault."""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from cyberbrain.mcp.shared import (
    BackendError,
    _extract_beats,
    _relpath,
    autofile_beat,
    require_config,
    write_beat,
    write_journal_entry,
)


def _parse_tags(tags_str: str) -> list[str]:
    """Parse a comma-separated tags string into a list, stripping whitespace."""
    return [t.strip() for t in tags_str.split(",") if t.strip()]


def _truncate_summary(body: str, max_chars: int = 200) -> str:
    """Generate a short summary from the first sentence or first max_chars of body."""
    if not body:
        return ""
    text = body.strip()
    # Try to truncate at sentence boundary
    for sep in (". ", ".\n", "! ", "!\n", "? ", "?\n"):
        idx = text.find(sep)
        if 0 < idx <= max_chars:
            return text[: idx + 1].strip()
    # Fall back to character truncation
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def cb_file(
        content: str,
        title: Annotated[
            str | None,
            Field(
                description="Note title. When provided, skips LLM extraction and files the document directly (document intake mode). When omitted, the content is passed through LLM extraction for classification, titling, and tagging (single-beat capture mode)."
            ),
        ] = None,
        type: Annotated[
            str | None,
            Field(
                description="Note type (e.g. 'reference', 'decision', 'insight', 'problem'). For document intake: defaults to 'reference'. For single-beat capture: overrides LLM classification if provided. Valid values from your vault CLAUDE.md."
            ),
        ] = None,
        tags: Annotated[
            str | None,
            Field(
                description="Comma-separated tags (e.g. 'python, async, performance'). For document intake: applied as-is. For single-beat capture: merged with LLM-generated tags."
            ),
        ] = None,
        durability: Annotated[
            str | None,
            Field(
                description="Durability for document intake. 'durable' (default) routes normally; 'working-memory' sends the note to the Working Memory folder. Ignored for single-beat capture — the LLM decides."
            ),
        ] = None,
        folder: Annotated[
            str | None,
            Field(
                description="Vault-relative folder path to file into, e.g. 'Personal/Recipes' or 'Work/Projects/hermes'. Omit to use the configured inbox folder."
            ),
        ] = None,
        cwd: Annotated[
            str | None,
            Field(
                description="Absolute path to the project directory. Enables project-scoped routing to the project's dedicated vault folder (requires .claude/cyberbrain.local.json in that directory). Omit to route to the global inbox."
            ),
        ] = None,
    ) -> str:
        """
        File content into the knowledge vault.

        Two modes, selected by whether `title` is provided:

        **Single-beat capture** (title omitted): Use when the user says "save this",
        "file this", "capture this". The content is passed through LLM extraction for
        classification, titling, and tagging. The `type` parameter overrides the
        LLM-assigned type if provided.

        **Document intake** (title provided): Use when the user has a pre-written
        document to file directly — no LLM extraction step. The document is filed as-is
        with the provided title, type (default: 'reference'), tags, and durability.

        For processing a complete session transcript, use cb_extract instead.
        For searching existing vault notes, use cb_recall.

        Returns confirmation with the note title, type, tags, and vault path where it was filed.
        Returns "No content worth filing" if the input contains nothing identifiable as knowledge
        (single-beat capture mode only).
        """
        effective_cwd = cwd or str(Path.home())
        config = require_config(effective_cwd)
        now = datetime.now(UTC)
        session_id = str(uuid.uuid4())

        # Apply folder override to config so routing uses it
        effective_config = dict(config)
        if folder:
            effective_config["inbox"] = folder

        # -----------------------------------------------------------------------
        # Mode switch: title present → document intake (UC3), else single-beat (UC2)
        # -----------------------------------------------------------------------
        if title:
            # UC3: Document intake — build beat dict directly, skip LLM extraction
            parsed_tags = _parse_tags(tags) if tags else []
            summary = _truncate_summary(content)
            beat = {
                "title": title,
                "type": type or "reference",
                "scope": "project" if cwd else "general",
                "summary": summary,
                "tags": parsed_tags,
                "body": content,
                "durability": durability or "durable",
                "relations": [],
            }
            beats = [beat]
            source = "document-intake"
        else:
            # UC2: Single-beat capture — use LLM extraction
            try:
                beats = _extract_beats(
                    content, effective_config, "manual", effective_cwd
                )
            except BackendError as e:
                backend = config.get("backend", "claude-code")
                raise ToolError(f"Backend error ({backend}): {e}")

            if not beats:
                return "No content worth filing was identified in the provided text."

            # Apply type override after extraction if requested
            if type:
                for beat in beats:
                    beat["type"] = type

            # Merge caller-provided tags with LLM-generated tags (union, no duplicates)
            if tags:
                caller_tags = [t.lower() for t in _parse_tags(tags)]
                for beat in beats:
                    existing = [str(t).lower() for t in (beat.get("tags") or [])]
                    merged = list(existing)
                    for t in caller_tags:
                        if t not in merged:
                            merged.append(t)
                    beat["tags"] = merged

            if durability:
                # durability is ignored for single-beat capture — LLM decides
                pass  # warning appended to return value below

            source = "manual-filing"

        autofile_enabled = effective_config.get("autofile", False)
        written = []
        lines = []

        vault_context = None
        if autofile_enabled:
            vault = Path(effective_config["vault_path"])
            claude_md = vault / "CLAUDE.md"
            if claude_md.exists():
                vault_context = claude_md.read_text(encoding="utf-8")[:3000]
            else:
                vault_context = (
                    "File notes using human-readable names with spaces. "
                    "Use ontology types: decision, insight, problem, reference."
                )

        for beat in beats:
            try:
                if autofile_enabled and not folder:
                    # can_ask only for single-beat scenarios: multi-beat extraction should
                    # not drop remaining beats by asking about the first one.
                    path = autofile_beat(
                        beat,
                        effective_config,
                        session_id,
                        effective_cwd,
                        now,
                        vault_context=vault_context,
                        source=source,
                        can_ask=(len(beats) == 1),
                    )
                else:
                    path = write_beat(
                        beat,
                        effective_config,
                        session_id,
                        effective_cwd,
                        now,
                        source=source,
                    )
                if path is None and "_autofile_ask" in beat:
                    ask_data = beat["_autofile_ask"]
                    confidence = ask_data["confidence"]
                    rationale = ask_data.get("rationale", "")
                    decision = ask_data.get("decision", {})
                    suggested = decision.get("path") or decision.get(
                        "target_path", "(unknown)"
                    )
                    return (
                        f"Confidence in routing is low (score: {confidence:.2f}). "
                        f"Suggested folder: {suggested}. "
                        f"Rationale: {rationale} "
                        f"Please confirm or specify a different folder, then I'll file the note."
                    )
                if path:
                    written.append(path)
                    rel = _relpath(path, config["vault_path"])
                    lines.append(
                        f'Filed: "{beat.get("title", "?")}"\n'
                        f"  Type:   {beat.get('type', 'reference')}\n"
                        f"  Action: created {rel}\n"
                        f"  Tags:   {beat.get('tags', [])}"
                    )
            except Exception as e:  # intentional: per-beat write failure is non-fatal; log and continue to next beat
                lines.append(f"Error filing '{beat.get('title', '?')}': {e}")

        if config.get("daily_journal", False) and written:
            project = config.get("project_name", "cb-file")
            write_journal_entry(written, config, session_id, project, now)

        if not written:
            raise ToolError(
                "No notes were filed — all beats encountered write errors. "
                "Check vault_path in cyberbrain.json."
            )

        return "\n\n".join(lines)
