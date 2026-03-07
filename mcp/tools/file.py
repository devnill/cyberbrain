"""cb_file tool — file a specific piece of information into the vault."""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from shared import (
    _extract_beats, write_beat, autofile_beat, write_journal_entry,
    BackendError, _load_config, _relpath,
)


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def cb_file(
        content: str,
        type_override: Annotated[str | None, Field(
            description="Force a specific note type. Valid values from your vault CLAUDE.md — defaults are: 'decision', 'insight', 'problem', 'reference'. Omit to let the system classify automatically."
        )] = None,
        folder: Annotated[str | None, Field(
            description="Vault-relative folder path to file into, e.g. 'Personal/Recipes' or 'Work/Projects/hermes'. Omit to use the configured inbox folder."
        )] = None,
        cwd: Annotated[str | None, Field(
            description="Absolute path to the project directory. Enables project-scoped routing to the project's dedicated vault folder (requires .claude/cyberbrain.local.json in that directory). Omit to route to the global inbox."
        )] = None,
    ) -> str:
        """
        File a specific piece of information into the knowledge vault.

        Use this when the user says "save this", "file this", "capture this", or confirms
        filing after it was suggested. Pass the content to preserve — it can be a fact, a
        decision, a recipe, a configuration snippet, or any text worth remembering. The
        system classifies, titles, and routes the note automatically using the vault's
        CLAUDE.md conventions. Do not create markdown files directly — always use this tool.

        For processing a complete session transcript, use cb_extract instead.
        For searching existing vault notes, use cb_recall.

        Returns confirmation with the note title, type, tags, and vault path where it was filed.
        Returns "No content worth filing" if the input contains nothing identifiable as knowledge.
        """
        effective_cwd = cwd or str(Path.home())
        config = _load_config(effective_cwd)
        now = datetime.now(timezone.utc)
        session_id = str(uuid.uuid4())

        # Apply folder override to config so routing uses it
        effective_config = dict(config)
        if folder:
            effective_config["inbox"] = folder

        try:
            beats = _extract_beats(content, effective_config, "manual", effective_cwd)
        except BackendError as e:
            backend = config.get("backend", "claude-code")
            raise ToolError(f"Backend error ({backend}): {e}")

        if not beats:
            return "No content worth filing was identified in the provided text."

        # Apply type override after extraction if requested
        if type_override:
            for beat in beats:
                beat["type"] = type_override

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
                    path = autofile_beat(beat, effective_config, session_id, effective_cwd, now, vault_context=vault_context, source="manual-filing")
                else:
                    path = write_beat(beat, effective_config, session_id, effective_cwd, now, source="manual-filing")
                if path:
                    written.append(path)
                    rel = _relpath(path, config["vault_path"])
                    lines.append(
                        f"Filed: \"{beat.get('title', '?')}\"\n"
                        f"  Type:   {beat.get('type', 'reference')}\n"
                        f"  Action: created {rel}\n"
                        f"  Tags:   {beat.get('tags', [])}"
                    )
            except Exception as e:
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
