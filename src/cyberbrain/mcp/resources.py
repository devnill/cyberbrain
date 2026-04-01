"""Cyberbrain MCP resource and prompts — behavioral guide and session orientation."""

import json

from fastmcp import FastMCP
from fastmcp.prompts import Message

from cyberbrain.extractors.config import ConfigError
from cyberbrain.mcp.shared import _load_config


def _build_guide(recall_instruction: str, filing_instruction: str = "") -> str:
    if not filing_instruction:
        filing_instruction = (
            "- When something durable is learned or decided during the session\n"
            '- When the user says "save this", "remember this", "file this"'
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

## When to call cb_file
- When the user says "save this", "remember this", "file this", or "capture this"
- When a durable insight, decision, or reference emerges that should survive the session
- Omit `title` for single-beat capture: cb_file calls the LLM to extract and classify the beat automatically
- Provide `title` for document intake mode: the content is filed directly without LLM classification (use when the user provides a complete document or structured reference)
- Set `durability="working-memory"` for current project state unlikely to matter in six months (open bugs, in-flight refactors, temporary workarounds)
- Set `durability="durable"` (or omit, as it is the default) for knowledge that passes the six-month test

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

## When to call cb_audit
- When the user asks about vault health, schema compliance, or curation quality
- When troubleshooting note routing issues (wrong folder, missing fields)
- When investigating whether frontmatter is consistent across notes
- cb_audit is read-only and saves a detailed report to ~/.claude/cyberbrain/audit-report.json

## When to call cb_setup
- When setting up a new vault for the first time
- When the vault structure has changed and the CLAUDE.md needs regenerating
- When the user asks to (re)analyze the vault layout or update vault guidance

## When to call cb_enrich
- When notes are missing frontmatter fields (type, tags, aliases)
- When backfilling metadata on a batch of existing notes
- When the user asks to improve or standardize note metadata

## When to call cb_restructure
- When notes in a folder become disorganized, redundant, or overlapping
- When the user asks to merge, split, or reorganize vault notes
- When a folder needs a hub page to group related notes

## When to call cb_review
- When working-memory notes are past their review date
- When the user wants to promote, extend, or delete temporary notes
- When cleaning up stale in-progress or working-memory notes

## When to call cb_reindex
- When the search index is stale or returning incorrect results
- When notes have been added or removed outside of cyberbrain tools
- When the user asks to rebuild or prune the search index

## Tool selection
| User intent | Tool |
|---|---|
| "Search my notes for X" | cb_recall |
| "Read the note about Y" | cb_read |
| "Save this" / "File this" | cb_file |
| "Process this transcript" | cb_extract |
| "Is everything healthy?" | cb_status |
| "Change vault / settings" | cb_configure |
| "Audit vault schema / compliance" | cb_audit |
| "Set up / regenerate vault CLAUDE.md" | cb_setup |
| "Enrich / backfill note metadata" | cb_enrich |
| "Merge, split, or reorganize notes" | cb_restructure |
| "Review working-memory notes" | cb_review |
| "Rebuild or prune search index" | cb_reindex |
"""


def _get_guide() -> str:
    """Build the behavioral guide from current config."""
    try:
        config = _load_config()
    except (ConfigError, json.JSONDecodeError):
        return (
            "Cyberbrain is not configured yet. "
            "Run /cyberbrain:config to set up your vault."
        )
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
            'a useful pattern — offer first: "That\'s worth capturing — should I file it?" '
            "Call cb_file only after the user confirms."
        ),
        "auto": (
            "When you identify something worth saving, call cb_file immediately without asking. "
            'Mention what was saved: "Filed: [title]".'
        ),
        "manual": (
            "NEVER suggest, offer, or mention filing. Do NOT proactively identify content worth saving. "
            "Only call cb_file when the user explicitly says words like 'save', 'file', 'capture', or "
            "'remember this'. If unsure whether the user is asking to file, do nothing."
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
        return [
            Message(
                role="user",
                content=(
                    "I'm starting a new session. Please do the following:\n\n"
                    "1. Read my cyberbrain usage guide below — use it to govern how you interact "
                    "with my knowledge vault throughout this conversation.\n"
                    "2. Call cb_status() to check vault health. If the vault is not configured "
                    "or missing, guide me through cb_configure() before anything else.\n\n"
                    "Usage guide:\n\n" + guide
                ),
            )
        ]

    @mcp.prompt()
    def recall() -> list[Message]:
        """
        Scan the current conversation for unfamiliar topics and query the vault for each.
        Select this mid-session when context has been lost or you want the model to catch up.
        """
        return [
            Message(
                role="user",
                content=(
                    "Scan our current conversation for topics you are uncertain about or that "
                    "I may have prior context on in my knowledge vault. For each unfamiliar "
                    "topic, call cb_recall to check what I know. If uncertain whether something "
                    "is in the vault, check it — don't skip it. Summarize what you find and "
                    "integrate it into our conversation naturally."
                ),
            )
        ]
