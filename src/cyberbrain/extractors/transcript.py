"""
transcript.py

JSONL transcript parsing for cyberbrain beat extraction.
"""

import json


def parse_jsonl_transcript(transcript_path: str) -> str:
    """
    Parse a JSONL transcript and reconstruct conversation text.
    Extracts user and assistant text turns; skips tool_use, tool_result,
    and thinking blocks.
    Returns a plain-text representation of the conversation.
    """
    turns = []

    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_type = entry.get("type")
            if entry_type not in ("user", "assistant"):
                continue

            message = entry.get("message", {})
            role = message.get("role", entry_type)
            content = message.get("content", "")

            text = _extract_text_blocks(content)
            if text.strip():
                turns.append(f"[{role.upper()}]\n{text.strip()}")

    return "\n\n---\n\n".join(turns)


def _extract_text_blocks(content) -> str:
    """
    Extract plain text from a content field (string or list of blocks).
    Skips tool_use and thinking blocks — only text blocks are included.
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            # Only include plain text blocks; skip tool_use, tool_result, thinking
            if block_type == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)

    return ""
