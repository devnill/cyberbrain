"""cb_extract tool — extract beats from a transcript file."""

from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from cyberbrain.extractors.extract_beats import run_extraction
from cyberbrain.mcp.shared import (
    BackendError,
    parse_jsonl_transcript,
    require_config,
)


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=ToolAnnotations(destructiveHint=False))
    def cb_extract(
        transcript_path: str,
        session_id: str | None = None,
        cwd: Annotated[
            str | None,
            Field(
                description="Absolute path to the project directory. Enables project-scoped routing to the project's dedicated vault folder (requires .claude/cyberbrain.local.json in that directory). Omit to route to the global inbox."
            ),
        ] = None,
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
        config = require_config(effective_cwd)

        effective_session_id = session_id or transcript_file.stem

        # Parse transcript (JSONL or plain text)
        suffix = transcript_file.suffix.lower()
        if suffix == ".jsonl":
            try:
                transcript_text = parse_jsonl_transcript(str(transcript_file))
            except Exception as e:  # intentional: JSONL parsing can raise various errors (malformed lines, encoding, etc.)
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
            transcript_text = (
                "...[earlier content truncated]...\n\n" + transcript_text[-MAX_CHARS:]
            )

        try:
            result = run_extraction(
                transcript_text,
                effective_session_id,
                "manual",
                effective_cwd,
                config=config,
            )
        except BackendError as e:
            backend = config.get("backend", "claude-code")
            raise ToolError(f"Backend error ({backend}): {e}")

        if result["skipped"]:
            return f"Session '{effective_session_id}' already extracted. Skipping."

        if result["beats_count"] == 0:
            return "No beats extracted."

        lines = []
        for record in result["beat_records"]:
            lines.append(f"  Created: {record['path']}  ({record['type']})")
        for err in result["run_errors"]:
            lines.append(f"  {err}")

        summary = f"Extracted {result['beats_written']}/{result['beats_count']} beat(s) from {transcript_file.name}:\n\n"
        summary += "\n".join(lines)
        return summary
