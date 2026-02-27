#!/usr/bin/env python3
"""
Knowledge Graph MCP Server

Exposes kg_extract, kg_file, and kg_recall as MCP tools so Claude Desktop
can file beats into and search an Obsidian vault.

Install: see install.sh — copies this file to ~/.claude/mcp/server.py and
registers it in ~/Library/Application Support/Claude/claude_desktop_config.json.
"""

import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Reuse extract_beats logic from the installed extractor
sys.path.insert(0, str(Path.home() / ".claude" / "extractors"))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("knowledge-graph")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _load_config(cwd: str = "") -> dict:
    from extract_beats import resolve_config
    return resolve_config(cwd or str(Path.home()))


def _relpath(path: Path, vault_path: str) -> str:
    return os.path.relpath(str(path), vault_path)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def kg_extract(
    conversation: str,
    project_name: str = "",
    cwd: str = "",
    trigger: str = "manual",
) -> str:
    """
    Extract knowledge beats from conversation text and file them into the Obsidian vault.

    Pass the full text of a conversation (any format: plain text, Human/Assistant turns,
    or Claude Code JSONL). Beats will be extracted by Claude and filed according to the
    autofile setting in ~/.claude/knowledge.json.

    Returns a summary of every note created or extended.
    """
    from extract_beats import (
        call_model, load_prompt,
        write_beat, autofile_beat, write_journal_entry,
    )

    config = _load_config(cwd)
    if project_name:
        config["project_name"] = project_name

    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    # Truncate if necessary (keep tail — most recent content is most valuable)
    MAX_CHARS = 150_000
    if len(conversation) > MAX_CHARS:
        conversation = "...[earlier content truncated]...\n\n" + conversation[-MAX_CHARS:]

    system_prompt = load_prompt("extract-beats-system.md")
    user_message = load_prompt("extract-beats-user.md").format_map({
        "project_name": project_name or config.get("project_name", "unknown"),
        "cwd": cwd or "unknown",
        "trigger": trigger,
        "transcript": conversation,
    })

    raw = call_model(system_prompt, user_message, config)
    if not raw:
        return "No beats extracted — model returned empty response."

    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        beats = json.loads(raw)
    except json.JSONDecodeError as e:
        return f"Failed to parse model response as JSON: {e}\n\nRaw output (first 300 chars):\n{raw[:300]}"

    if not isinstance(beats, list) or not beats:
        return "No beats extracted."

    autofile_enabled = config.get("autofile", False)
    effective_cwd = cwd or str(Path.home())
    written = []
    lines = []

    for beat in beats:
        try:
            if autofile_enabled:
                path = autofile_beat(beat, config, session_id, effective_cwd, now)
            else:
                path = write_beat(beat, config, session_id, effective_cwd, now)
            if path:
                written.append(path)
                rel = _relpath(path, config["vault_path"])
                lines.append(f"✓ [{beat.get('type', 'note')}] {beat.get('title', '?')} → {rel}")
        except Exception as e:
            lines.append(f"✗ {beat.get('title', '?')}: {e}")

    if config.get("daily_journal", False) and written:
        project = config.get("project_name", project_name or "unknown")
        write_journal_entry(written, config, session_id, project, now)

    summary = f"Extracted {len(written)}/{len(beats)} beat(s):\n\n" + "\n".join(lines)
    return summary


@mcp.tool()
def kg_file(
    title: str,
    body: str,
    type: str = "reference",
    tags: list[str] | None = None,
    scope: str = "general",
    summary: str = "",
) -> str:
    """
    File a single note into the Obsidian vault.

    Use this to capture a specific piece of information — a decision, insight,
    reference, or pattern — without going through full beat extraction.
    """
    from extract_beats import write_beat

    config = _load_config()
    now = datetime.now(timezone.utc)
    session_id = str(uuid.uuid4())

    beat = {
        "title": title,
        "type": type,
        "scope": scope,
        "summary": summary or title,
        "tags": tags or [],
        "body": body,
    }

    try:
        path = write_beat(beat, config, session_id, str(Path.home()), now)
        rel = _relpath(path, config["vault_path"])
        return f"Filed: {rel}"
    except Exception as e:
        return f"Error filing note: {e}"


@mcp.tool()
def kg_recall(query: str, max_results: int = 5) -> str:
    """
    Search the Obsidian vault for notes relevant to a query.

    Returns the content of the most relevant notes, ranked by recency among
    those that match. Use this to retrieve context from past sessions before
    starting new work on a topic.
    """
    config = _load_config()
    vault_path = config["vault_path"]

    terms = [w for w in re.split(r"\W+", query) if len(w) >= 3][:8]
    if not terms:
        return "Query too short — provide at least one word with 3+ characters."

    found: dict[str, float] = {}
    for term in terms:
        result = subprocess.run(
            ["grep", "-r", "-l", "--include=*.md", "-i", term, vault_path],
            capture_output=True, text=True,
        )
        for path in result.stdout.strip().splitlines():
            if path and path not in found:
                try:
                    found[path] = os.path.getmtime(path)
                except OSError:
                    pass

    if not found:
        return f"No notes found matching: {query}"

    ranked = sorted(found, key=found.get, reverse=True)[:max_results]

    parts = []
    for path in ranked:
        try:
            content = Path(path).read_text(encoding="utf-8")
            rel = os.path.relpath(path, vault_path)
            parts.append(f"### {rel}\n\n{content[:3000]}")
        except OSError:
            pass

    header = f"Found {len(ranked)} note(s) matching '{query}':\n\n"
    return header + "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
