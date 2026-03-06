"""
extractor.py

LLM-based beat extraction from a session transcript.
"""

import json
import re
import sys
from pathlib import Path

from backends import call_model, MAX_TRANSCRIPT_CHARS
from config import load_prompt
from vault import read_vault_claude_md


def extract_beats(transcript_text: str, config: dict, trigger: str, cwd: str) -> list:
    project_name = config.get("project_name", Path(cwd).name)

    # Truncate transcript if too long (keep tail — most recent content is most valuable)
    if len(transcript_text) > MAX_TRANSCRIPT_CHARS:
        transcript_text = "...[earlier content truncated]...\n\n" + transcript_text[-MAX_TRANSCRIPT_CHARS:]

    # Read vault CLAUDE.md for type vocabulary context
    vault_claude_md = read_vault_claude_md(config["vault_path"])

    if vault_claude_md:
        vault_claude_md_section = (
            "<vault_claude_md>\n"
            "The following is the vault's CLAUDE.md, which defines the type vocabulary "
            "and filing conventions for this vault. Use the type vocabulary defined here "
            "instead of the default four-type vocabulary.\n\n"
            f"{vault_claude_md}\n"
            "</vault_claude_md>\n\n"
        )
    else:
        vault_claude_md_section = (
            "No vault CLAUDE.md was found. Use the default four-type vocabulary only: "
            "decision, insight, problem, reference.\n\n"
        )

    system_prompt = load_prompt("extract-beats-system.md")
    user_message = load_prompt("extract-beats-user.md").format_map({
        "project_name": project_name,
        "cwd": cwd,
        "trigger": trigger,
        "transcript": transcript_text,
        "vault_claude_md_section": vault_claude_md_section,
    })

    raw = call_model(system_prompt, user_message, config)
    if not raw:
        return []

    # Strip markdown code fences if model added them despite instructions
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        # Use raw_decode so trailing explanatory text after the JSON is ignored
        beats, _ = json.JSONDecoder().raw_decode(raw.lstrip())
    except json.JSONDecodeError as e:
        print(f"[extract_beats] Failed to parse model response as JSON: {e}", file=sys.stderr)
        print(f"[extract_beats] Raw response: {raw[:500]}", file=sys.stderr)
        return []

    if not isinstance(beats, list):
        print(f"[extract_beats] Model returned non-list JSON: {type(beats)}", file=sys.stderr)
        return []

    return beats
