"""cb_extract tool — extract beats from a transcript file."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from shared import (
    _extract_beats, parse_jsonl_transcript, write_beat, autofile_beat,
    write_journal_entry, BackendError, _load_config, _relpath,
)


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=ToolAnnotations(destructiveHint=False))
    def cb_extract(
        transcript_path: str,
        session_id: str | None = None,
        cwd: Annotated[str | None, Field(
            description="Absolute path to the project directory. Enables project-scoped routing to the project's dedicated vault folder (requires .claude/cyberbrain.local.json in that directory). Omit to route to the global inbox."
        )] = None,
    ) -> str:
        """
        Extract knowledge beats from a conversation transcript file and file them to the vault.

        Use this to process a complete Claude Code session transcript (a .jsonl file from
        ~/.claude/projects/). For filing a specific piece of information from the current
        conversation, use cb_file instead. For searching existing vault notes, use cb_recall.

        transcript_path must point to a file within ~/.claude/projects/.

        Returns a summary listing each beat created (title, type, vault path).
        Returns "No beats extracted." if the transcript contains nothing worth preserving.
        """
        transcript_file = Path(transcript_path).expanduser()

        # Restrict to ~/.claude/projects/ to prevent arbitrary file reads
        allowed_root = (Path.home() / ".claude" / "projects").resolve()
        try:
            transcript_file.resolve().relative_to(allowed_root)
        except ValueError:
            raise ToolError(
                f"transcript_path must be within ~/.claude/projects/. "
                f"Transcript files are stored there by Claude Code. Got: {transcript_path}"
            )

        if not transcript_file.exists():
            raise ToolError(f"Transcript file not found: {transcript_path}")

        effective_cwd = cwd or str(Path.home())
        config = _load_config(effective_cwd)

        effective_session_id = session_id or transcript_file.stem
        now = datetime.now(timezone.utc)

        # Parse transcript (JSONL or plain text)
        suffix = transcript_file.suffix.lower()
        if suffix == ".jsonl":
            try:
                transcript_text = parse_jsonl_transcript(str(transcript_file))
            except Exception as e:
                raise ToolError(f"Failed to parse transcript: {e}")
        else:
            try:
                transcript_text = transcript_file.read_text(encoding="utf-8")
            except OSError as e:
                raise ToolError(f"Failed to read transcript: {e}")

        if not transcript_text.strip():
            raise ToolError("Transcript is empty or has no user/assistant turns.")

        # Truncate to stay within model context limits (keep tail — most recent is most valuable)
        MAX_CHARS = 150_000
        if len(transcript_text) > MAX_CHARS:
            transcript_text = "...[earlier content truncated]...\n\n" + transcript_text[-MAX_CHARS:]

        try:
            beats = _extract_beats(transcript_text, config, "manual", effective_cwd)
        except BackendError as e:
            backend = config.get("backend", "claude-code")
            raise ToolError(f"Backend error ({backend}): {e}")

        if not beats:
            return "No beats extracted."

        autofile_enabled = config.get("autofile", False)
        written = []
        lines = []

        # Cache vault CLAUDE.md once for the autofile loop
        vault_context = None
        if autofile_enabled:
            vault = Path(config["vault_path"])
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
                if autofile_enabled:
                    path = autofile_beat(beat, config, effective_session_id, effective_cwd, now, vault_context=vault_context)
                else:
                    path = write_beat(beat, config, effective_session_id, effective_cwd, now)
                if path:
                    written.append(path)
                    rel = _relpath(path, config["vault_path"])
                    lines.append(f"  Created: {rel}  ({beat.get('type', 'note')})")
            except Exception as e:
                lines.append(f"  Error on '{beat.get('title', '?')}': {e}")

        if config.get("daily_journal", False) and written:
            project = config.get("project_name", "unknown")
            write_journal_entry(written, config, effective_session_id, project, now)

        summary = f"Extracted {len(written)}/{len(beats)} beat(s) from {transcript_file.name}:\n\n"
        summary += "\n".join(lines)
        return summary
