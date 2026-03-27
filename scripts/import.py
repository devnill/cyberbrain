#!/usr/bin/env python3
"""
import.py — Import Claude Desktop or ChatGPT export into the knowledge graph vault.

Reads a conversations export file and extracts knowledge beats using the extract_beats
pipeline, writing results to the configured Obsidian vault. Fully resumable: a state
file tracks processed conversations so re-runs skip already-imported ones.

Usage:
    python3 import.py --export ~/Downloads/conversations.json --format claude
    python3 import.py --export ~/Downloads/conversations.json --format claude-web
    python3 import.py --export ~/Downloads/conversations.json --format chatgpt
    python3 import.py --export ~/Downloads/conversations.json --format claude --dry-run
    python3 import.py --export ~/Downloads/conversations.json --format claude --limit 10
    python3 import.py --export ~/Downloads/conversations.json --format claude --since 2026-01-01

All vault writes go through the extractor — import.py never writes vault files directly.
"""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATE_PATH = Path.home() / ".claude" / "cyberbrain" / "import-state.json"
MAX_TRANSCRIPT_CHARS = 150_000

# Minimum rendered character count to bother passing to the extraction LLM.
# Single-exchange "hi" / "hello" conversations produce no durable beats.
MIN_CHARS_FOR_EXTRACTION = 100


# ---------------------------------------------------------------------------
# cyberbrain library imports — direct from source modules
# ---------------------------------------------------------------------------

try:
    from cyberbrain.extractors.autofile import autofile_beat
    from cyberbrain.extractors.config import resolve_config
    from cyberbrain.extractors.extractor import extract_beats
    from cyberbrain.extractors.run_log import write_journal_entry
    from cyberbrain.extractors.vault import write_beat
except ImportError:
    print(
        "[import] cyberbrain package not found.\n"
        "[import] Install with: uv pip install -e . (or pip install cyberbrain-mcp)",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="import.py",
        description="Import Claude Desktop or ChatGPT export into the knowledge graph vault.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--export",
        required=True,
        metavar="PATH",
        help="Path to the export file (conversations.json)",
    )
    parser.add_argument(
        "--format",
        required=True,
        choices=["claude", "claude-web", "chatgpt"],
        help="Export format: 'claude' (Desktop app), 'claude-web' (claude.ai), or 'chatgpt' (OpenAI)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be imported without writing anything or updating state",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Process at most N conversations (useful for testing)",
    )
    parser.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        help="Only process conversations with a timestamp on or after this date",
    )
    parser.add_argument(
        "--cwd",
        default=os.getcwd(),
        metavar="PATH",
        help="Working directory for project routing lookup (default: current directory)",
    )
    return parser


# ---------------------------------------------------------------------------
# State file management
# ---------------------------------------------------------------------------


def load_state(state_path: Path) -> dict:
    """Load the import state file, returning a fresh dict if it doesn't exist or is corrupt."""
    if state_path.exists():
        try:
            with open(state_path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError) as e:
            print(
                f"[import] Warning: could not read state file {state_path}: {e}",
                file=sys.stderr,
            )
            print("[import] Starting with empty state.", file=sys.stderr)
    return {}


def save_state(state: dict, state_path: Path) -> None:
    """Atomically write the state file via rename to prevent corruption on interrupt."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, state_path)


def record_imported(state: dict, conv_id: str, beats_written: int) -> None:
    state[conv_id] = {
        "imported_at": datetime.now(UTC).isoformat(),
        "beats_written": beats_written,
    }


# ---------------------------------------------------------------------------
# Claude export parsing
# ---------------------------------------------------------------------------


def _render_claude_message_text(msg: dict) -> str:
    """
    Extract clean text from a Claude export message dict.

    Prefers content[].type=='text' blocks over the top-level 'text' field.
    The 'text' field sometimes contains "This block is not supported" artifacts
    for tool_use and tool_result blocks; the content array text blocks are clean.
    Skips non-human/assistant senders (system, tool).
    """
    sender = msg.get("sender", "")
    if sender not in ("human", "assistant"):
        return ""

    # Prefer content list text blocks
    text_blocks = [
        block
        for block in msg.get("content", [])
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    if text_blocks:
        return "".join(b.get("text", "") for b in text_blocks).strip()

    # Fallback to top-level text field
    return (msg.get("text") or "").strip()


def parse_claude_conversation(conv: dict) -> str:
    """
    Render a Claude Desktop export conversation to plain text for extraction.

    Format:
        ## {name}
        Date: YYYY-MM-DD

        Human: ...

        Assistant: ...

    Skips system messages, tool use, and empty turns.
    """
    parts: list[str] = []

    name = (conv.get("name") or "Untitled").strip()
    date = (conv.get("updated_at") or conv.get("created_at") or "")[:10]

    parts.append(f"## {name}")
    if date:
        parts.append(f"Date: {date}")
    parts.append("")

    for msg in conv.get("chat_messages", []):
        sender = msg.get("sender", "")
        if sender not in ("human", "assistant"):
            continue
        label = "Human" if sender == "human" else "Assistant"
        text = _render_claude_message_text(msg)
        if text:
            parts.append(f"{label}: {text}")
            parts.append("")

    rendered = "\n".join(parts).strip()
    if len(rendered) > MAX_TRANSCRIPT_CHARS:
        rendered = (
            "...[earlier content truncated]...\n\n" + rendered[-MAX_TRANSCRIPT_CHARS:]
        )
    return rendered


def get_claude_conv_id(conv: dict) -> str:
    return conv.get("uuid", "")


def get_claude_conv_date(conv: dict) -> str:
    """Return YYYY-MM-DD string for date filtering."""
    return (conv.get("updated_at") or conv.get("created_at") or "")[:10]


def get_claude_conv_title(conv: dict) -> str:
    return (conv.get("name") or "Untitled").strip()


# ---------------------------------------------------------------------------
# ChatGPT export parsing
# TODO: verify against a real ChatGPT export — structure based on widely-documented format
# ---------------------------------------------------------------------------


def _extract_chatgpt_thread(mapping: dict, current_node: str) -> list[dict]:
    """Walk from current_node back through parent links; return messages in order."""
    thread: list[dict] = []
    node_id = current_node
    while node_id:
        node = mapping.get(node_id)
        if node is None:
            break
        msg = node.get("message")
        if msg is not None:
            thread.append(msg)
        node_id = node.get("parent")
    thread.reverse()
    return thread


def _render_chatgpt_message_text(msg: dict) -> str:
    """Extract text from a ChatGPT message node. Returns empty string for non-text content."""
    content = msg.get("content") or {}
    # Only handle plain text content type
    if content.get("content_type") != "text":
        return ""
    parts = content.get("parts") or []
    return "".join(p for p in parts if isinstance(p, str)).strip()


def parse_chatgpt_conversation(conv: dict) -> str:
    """
    Render a ChatGPT export conversation to plain text for extraction.

    ChatGPT exports use a 'mapping' dict of message nodes linked by parent IDs.
    We walk from current_node back through parents to reconstruct the thread.

    Skips system and tool messages. Only includes user/assistant text turns.
    """
    parts: list[str] = []

    title = (conv.get("title") or "Untitled").strip()
    update_time = conv.get("update_time")
    if update_time:
        date = datetime.fromtimestamp(update_time, tz=UTC).strftime("%Y-%m-%d")
    else:
        create_time = conv.get("create_time")
        date = (
            datetime.fromtimestamp(create_time, tz=UTC).strftime("%Y-%m-%d")
            if create_time
            else ""
        )

    parts.append(f"## {title}")
    if date:
        parts.append(f"Date: {date}")
    parts.append("")

    mapping = conv.get("mapping") or {}
    current_node = conv.get("current_node", "")
    thread = _extract_chatgpt_thread(mapping, current_node)

    for msg in thread:
        author = msg.get("author") or {}
        role = author.get("role", "")
        if role in ("system", "tool"):
            continue
        if role not in ("user", "assistant"):
            continue
        label = "Human" if role == "user" else "Assistant"
        text = _render_chatgpt_message_text(msg)
        if text:
            parts.append(f"{label}: {text}")
            parts.append("")

    rendered = "\n".join(parts).strip()
    if len(rendered) > MAX_TRANSCRIPT_CHARS:
        rendered = (
            "...[earlier content truncated]...\n\n" + rendered[-MAX_TRANSCRIPT_CHARS:]
        )
    return rendered


def get_chatgpt_conv_id(conv: dict) -> str:
    return conv.get("id") or conv.get("conversation_id", "")


def get_chatgpt_conv_date(conv: dict) -> str:
    """Return YYYY-MM-DD for date filtering."""
    ts = conv.get("update_time") or conv.get("create_time")
    if ts:
        return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")
    return ""


def get_chatgpt_conv_title(conv: dict) -> str:
    return (conv.get("title") or "Untitled").strip()


# ---------------------------------------------------------------------------
# Format-agnostic dispatch
# ---------------------------------------------------------------------------


def get_conv_id(conv: dict, fmt: str) -> str:
    if fmt == "chatgpt":
        return get_chatgpt_conv_id(conv)
    return get_claude_conv_id(conv)


def get_conv_date(conv: dict, fmt: str) -> str:
    if fmt == "chatgpt":
        return get_chatgpt_conv_date(conv)
    return get_claude_conv_date(conv)


def get_conv_title(conv: dict, fmt: str) -> str:
    if fmt == "chatgpt":
        return get_chatgpt_conv_title(conv)
    return get_claude_conv_title(conv)


def render_conversation(conv: dict, fmt: str) -> str:
    if fmt == "chatgpt":
        return parse_chatgpt_conversation(conv)
    return parse_claude_conversation(conv)


# ---------------------------------------------------------------------------
# Export file loading
# ---------------------------------------------------------------------------


def load_export(path: str, fmt: str) -> list[dict]:
    """
    Load and parse the export file. Returns a list of conversation dicts.

    Both Claude and ChatGPT exports may be:
    - A JSON array at the top level, OR
    - A JSON object with a 'conversations' key containing the array
    """
    export_path = Path(path).expanduser()
    if not export_path.exists():
        print(f"[import] Export file not found: {export_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(export_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[import] Failed to parse export file as JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # Unwrap top-level object if needed
    if isinstance(data, dict):
        data = data.get("conversations", [])

    if not isinstance(data, list):
        print(
            f"[import] Expected a JSON array or an object with a 'conversations' key, "
            f"got {type(data).__name__}",
            file=sys.stderr,
        )
        sys.exit(1)

    return data


# ---------------------------------------------------------------------------
# Conversation timestamp for beat dating
# ---------------------------------------------------------------------------


def get_conv_timestamp(conv: dict, fmt: str) -> datetime:
    """Return a datetime for the conversation, used as the beat creation timestamp."""
    if fmt == "chatgpt":
        ts = conv.get("update_time") or conv.get("create_time")
        if ts:
            return datetime.fromtimestamp(ts, tz=UTC)
    else:
        ts_str = conv.get("updated_at") or conv.get("created_at") or ""
        if ts_str:
            try:
                return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                pass
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Processing a single conversation
# ---------------------------------------------------------------------------


def process_conversation(
    conv: dict,
    fmt: str,
    config: dict,
    cwd: str,
) -> tuple[int, list[Path]]:
    """
    Extract beats from one conversation and write them to the vault.

    Returns (beats_written_count, list_of_written_paths).
    Raises on any unrecoverable exception (caller records error in state).
    All vault writes go through write_beat / autofile_beat (P7).
    """
    conv_id = get_conv_id(conv, fmt)
    transcript = render_conversation(conv, fmt)
    if not transcript.strip():
        return 0, []

    autofile_enabled = config.get("autofile", False)
    now = get_conv_timestamp(conv, fmt)

    beats = extract_beats(transcript, config, "import", cwd)
    if not beats:
        return 0, []

    # Cache vault CLAUDE.md once per conversation for the autofile loop
    vault_context = None
    if autofile_enabled:
        vault = Path(config["vault_path"])
        claude_md_path = vault / "CLAUDE.md"
        if claude_md_path.exists():
            vault_context = claude_md_path.read_text(encoding="utf-8")[:3000]
        else:
            vault_context = (
                "File notes using human-readable names with spaces. "
                "Use ontology types: decision, insight, problem, reference."
            )

    cb_source = f"import-{fmt}"

    written: list[Path] = []
    for beat in beats:
        try:
            if autofile_enabled:
                path = autofile_beat(
                    beat,
                    config,
                    conv_id,
                    cwd,
                    now,
                    vault_context=vault_context,
                    source=cb_source,
                )
            else:
                path = write_beat(beat, config, conv_id, cwd, now, source=cb_source)
            if path:
                written.append(path)
        except Exception as exc:
            print(
                f"    [warn] beat '{beat.get('title', '?')}' failed to write: {exc}",
                file=sys.stderr,
            )

    return len(written), written


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    fmt = args.format
    export_path = args.export
    dry_run = args.dry_run
    limit = args.limit
    since = args.since
    cwd = args.cwd

    # Load the export file
    conversations = load_export(export_path, fmt)
    export_filename = Path(export_path).name
    print(f"Importing {export_filename} (format: {fmt})")

    # Load state
    state = load_state(STATE_PATH)

    # Partition into already-imported and to-process
    already_imported_ids = set(state.keys())

    to_process: list[dict] = []
    already_imported_count = 0
    skipped_no_id = 0

    for conv in conversations:
        uid = get_conv_id(conv, fmt)
        if not uid:
            skipped_no_id += 1
            continue
        if uid in already_imported_ids:
            already_imported_count += 1
            continue
        # Date filter
        if since:
            conv_date = get_conv_date(conv, fmt)
            if conv_date and conv_date < since:
                continue
        to_process.append(conv)

    # Apply limit
    if limit is not None:
        to_process = to_process[:limit]

    total_to_process = len(to_process)

    print(
        f"Processing {len(conversations)} conversations "
        f"({already_imported_count} already imported, {total_to_process} to process)"
    )

    if dry_run:
        print(f"\n[DRY RUN] Would process {total_to_process} conversations")

    if total_to_process == 0:
        if not dry_run:
            print("\nNothing to process — all conversations already imported.")
        return

    # Load config for actual processing
    if not dry_run:
        config = dict(resolve_config(cwd))
        # Run the extraction subprocess from $HOME so it doesn't pick up any
        # project-specific CLAUDE.md that would narrow extraction scope.
        config["subprocess_cwd"] = str(Path.home())
        journal_enabled = config.get("daily_journal", False)
        all_written_paths: list[Path] = []

    counts = {"processed": 0, "beats": 0, "skipped": 0, "errors": 0}

    for idx, conv in enumerate(to_process, 1):
        uid = get_conv_id(conv, fmt)
        title = get_conv_title(conv, fmt)
        date = get_conv_date(conv, fmt)
        date_str = f" ({date})" if date else ""

        # Check if too short to extract anything meaningful
        rendered = render_conversation(conv, fmt)
        if len(rendered.strip()) < MIN_CHARS_FOR_EXTRACTION:
            if dry_run:
                print(f"[{idx}/{total_to_process}] Skipping — too short to yield beats")
            else:
                print(f"[{idx}/{total_to_process}] Skipping — too short to yield beats")
            counts["skipped"] += 1
            continue

        if dry_run:
            print(f'[{idx}/{total_to_process}] "{title}" → would extract ~? beats')
            continue

        print(f'[{idx}/{total_to_process}] "{title}"{date_str}', end="", flush=True)

        try:
            beats_written, written_paths = process_conversation(conv, fmt, config, cwd)
            all_written_paths.extend(written_paths)
            counts["processed"] += 1
            counts["beats"] += beats_written
            print(f" → {beats_written} beats extracted")

            # Write to state file after each successful conversation
            record_imported(state, uid, beats_written)
            save_state(state, STATE_PATH)

        except Exception as exc:
            counts["errors"] += 1
            print(f" → error: {exc}")

    if dry_run:
        print("\nNo files were written.")
        return

    # Write journal entry if enabled and beats were written
    if journal_enabled and all_written_paths:
        now = datetime.now(UTC)
        project = config.get("project_name", f"{fmt}-import")
        write_journal_entry(all_written_paths, config, f"{fmt}-import", project, now)

    # Summary
    print(
        f"\nImport complete: {counts['processed']} conversations processed, "
        f"{counts['beats']} beats written"
    )
    print(f"Already imported: {already_imported_count} conversations (skipped)")
    print(f"Skipped: {counts['skipped']} conversations (too short or empty)")
    print(f"Errors: {counts['errors']}")


if __name__ == "__main__":
    main()
