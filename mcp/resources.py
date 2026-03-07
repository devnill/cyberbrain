"""Cyberbrain MCP resource and prompts — behavioral guide and session orientation."""

from fastmcp import FastMCP
from fastmcp.prompts import Message

from shared import _load_config


def _build_guide(recall_instruction: str, filing_instruction: str = "") -> str:
    if not filing_instruction:
        filing_instruction = (
            "- When something durable is learned or decided during the session\n"
            "- When the user says \"save this\", \"remember this\", \"file this\""
        )
    return f"""\
# Cyberbrain — AI Usage Guide

## What cyberbrain is
A personal knowledge vault — notes extracted from past Claude sessions, filed automatically.

## When to call cb_recall
{recall_instruction}
- When the user mentions a project, technology, or topic they have worked on before
- Mid-session when the conversation shifts to a new domain
- When the user asks "what do I know about X?" or "have I done this before?"

## Capture mode — when and how to call cb_file
{filing_instruction}

**Never create markdown files directly.** Always use cb_file — it handles classification,
formatting, routing, and deduplication. Writing raw files bypasses vault conventions and
makes notes unsearchable.

## When to call cb_read
- When cb_recall surfaces a note you want to read in full
- When the user names a specific note they want to retrieve

## When to call cb_extract
- Only when the user explicitly asks to process a transcript file

## When to call cb_status
- When the user asks about system health, index stats, or recent extraction runs

## When to call cb_configure
- When the user wants to change vault, inbox, or capture mode settings
- When vault health looks wrong (missing path, no notes indexed)
- At session start if vault is not configured

## Tool selection
| User intent | Tool |
|---|---|
| "Search my notes for X" | cb_recall |
| "Read the note about Y" | cb_read |
| "Save this" / "File this" | cb_file |
| "Process this transcript" | cb_extract |
| "Is everything healthy?" | cb_status |
| "Change vault / settings" | cb_configure |
"""


def _get_guide() -> str:
    """Build the behavioral guide from current config."""
    config = _load_config()
    proactive = config.get("proactive_recall", True)
    if proactive:
        recall_instruction = (
            "Call `cb_recall` proactively when the user mentions a known domain. "
            "Do not ask permission — just call it and integrate results naturally."
        )
    else:
        recall_instruction = (
            "When the user mentions a known domain, suggest calling `cb_recall` "
            "and confirm with the user before proceeding."
        )

    mode = config.get("desktop_capture_mode", "suggest")
    filing_instructions = {
        "suggest": (
            "When you identify something worth saving — a decision, a non-obvious insight, "
            "a useful pattern — offer first: \"That's worth capturing — should I file it?\" "
            "Call cb_file only after the user confirms."
        ),
        "auto": (
            "When you identify something worth saving, call cb_file immediately without asking. "
            "Mention what was saved: \"Filed: [title]\"."
        ),
        "manual": (
            "Only call cb_file when the user explicitly asks you to save or file something. "
            "Do not proactively identify or offer to file anything."
        ),
    }
    filing_instruction = filing_instructions.get(mode, filing_instructions["suggest"])
    return _build_guide(recall_instruction, filing_instruction)


def register(mcp: FastMCP) -> None:
    @mcp.resource("cyberbrain://guide")
    def cyberbrain_guide() -> str:
        """Behavioral guide describing when and how to use each cyberbrain tool."""
        return _get_guide()

    @mcp.prompt()
    def orient() -> list[Message]:
        """
        Orient at session start: load the cyberbrain usage guide and check vault status.
        Select this at the beginning of a new conversation to establish vault behavior.
        """
        guide = _get_guide()
        return [Message(
            role="user",
            content=(
                "I'm starting a new session. Please do the following:\n\n"
                "1. Read my cyberbrain usage guide below — use it to govern how you interact "
                "with my knowledge vault throughout this conversation.\n"
                "2. Call cb_status() to check vault health. If the vault is not configured "
                "or missing, guide me through cb_configure() before anything else.\n\n"
                "Usage guide:\n\n" + guide
            ),
        )]

    @mcp.prompt()
    def recall() -> list[Message]:
        """
        Scan the current conversation for unfamiliar topics and query the vault for each.
        Select this mid-session when context has been lost or you want the model to catch up.
        """
        return [Message(
            role="user",
            content=(
                "Scan our current conversation for topics you are uncertain about or that "
                "I may have prior context on in my knowledge vault. For each unfamiliar "
                "topic, call cb_recall to check what I know. If uncertain whether something "
                "is in the vault, check it — don't skip it. Summarize what you find and "
                "integrate it into our conversation naturally."
            ),
        )]
