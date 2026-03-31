"""
transcript.py

JSONL transcript parsing for cyberbrain beat extraction.
"""

import json
import re

# ---------------------------------------------------------------------------
# Noise filtering — strip content that is system/ephemeral and not
# worth feeding to the extraction LLM.  These patterns are matched
# against individual text blocks *before* they are joined into turns.
# ---------------------------------------------------------------------------

# Regex patterns for text blocks that should be dropped entirely.
_SKIP_BLOCK_PATTERNS = [
    # Skill prompt injections (ideate, cyberbrain, etc.)
    re.compile(r"^Base directory for this skill:", re.MULTILINE),
    # Command invocations / local-command output
    re.compile(r"<command-name>"),
    re.compile(r"<command-message>"),
    re.compile(r"<local-command-caveat>"),
    re.compile(r"<local-command-stdout>"),
    # Subagent task notifications
    re.compile(r"<task-notification>"),
]

# Regex patterns stripped inline — tags and their content are removed but
# surrounding text is preserved.
_INLINE_STRIP_PATTERNS = [
    re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL),
    re.compile(r"<usage>.*?</usage>", re.DOTALL),
]


def _is_noise_block(text: str) -> bool:
    """Return True if the text block is system/skill noise."""
    return any(pat.search(text) for pat in _SKIP_BLOCK_PATTERNS)


def _strip_inline_noise(text: str) -> str:
    """Remove inline noise tags (system-reminder, usage) from a text block."""
    for pat in _INLINE_STRIP_PATTERNS:
        text = pat.sub("", text)
    return text


def parse_jsonl_transcript(transcript_path: str) -> str:
    """
    Parse a JSONL transcript and reconstruct conversation text.
    Extracts user and assistant text turns; skips tool_use, tool_result,
    thinking blocks, skill prompts, command messages, and system reminders.
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
    Skips tool_use, thinking blocks, skill prompts, command messages,
    and system reminders — only substantive text blocks are included.
    """
    if isinstance(content, str):
        if _is_noise_block(content):
            return ""
        return _strip_inline_noise(content)

    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            # Only include plain text blocks; skip tool_use, tool_result, thinking
            if block_type == "text":
                text = block.get("text", "")
                if _is_noise_block(text):
                    continue
                text = _strip_inline_noise(text)
                if text.strip():
                    parts.append(text)
        return "\n".join(parts)

    return ""
