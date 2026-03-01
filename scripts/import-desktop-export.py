#!/usr/bin/env python3
"""
import-desktop-export.py — Import Claude or ChatGPT export into an Obsidian vault.

Reads conversations.json from an Anthropic data export or a ChatGPT export and
extracts knowledge beats using extract_beats.py, writing results to the vault.
Fully resumable: a state file tracks every conversation so the run can be
interrupted and restarted without duplicating work.

Usage:
    python3 import-desktop-export.py PATH/TO/conversations.json [options]
    python3 import-desktop-export.py --input PATH/TO/conversations.json [options]

Quick examples:
    # Test on 5 conversations first (dry run)
    python3 import-desktop-export.py conversations.json --limit 5 --dry-run

    # Process 5 real conversations to check autofile results
    python3 import-desktop-export.py conversations.json --limit 5

    # Show full status table
    python3 import-desktop-export.py conversations.json --list

    # Process all remaining (skips already-done ones automatically)
    python3 import-desktop-export.py conversations.json

    # Retry anything that errored
    python3 import-desktop-export.py conversations.json --reprocess-errors

    # Only process conversations from the last 6 months
    python3 import-desktop-export.py conversations.json --since 2025-08-01

    # Import a ChatGPT export
    python3 import-desktop-export.py chatgpt-conversations.json --format chatgpt --dry-run
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_STATE_PATH = Path.home() / ".claude" / "kg-import-state.json"
EXTRACTORS_DIR = Path.home() / ".claude" / "extractors"
MAX_TRANSCRIPT_CHARS = 150_000


# ---------------------------------------------------------------------------
# extract_beats library import (fail fast if not installed)
# ---------------------------------------------------------------------------

def _import_extract_beats():
    extractor_path = EXTRACTORS_DIR / "extract_beats.py"
    if not extractor_path.exists():
        print(
            f"[import] extract_beats.py not found at {extractor_path}\n"
            f"[import] Run install.sh first.",
            file=sys.stderr,
        )
        sys.exit(1)
    if str(EXTRACTORS_DIR) not in sys.path:
        sys.path.insert(0, str(EXTRACTORS_DIR))
    import extract_beats as eb  # noqa: PLC0415
    return eb


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import Claude Desktop export (conversations.json) into the knowledge graph vault.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Input
    parser.add_argument(
        "input_pos", nargs="?", metavar="FILE",
        help="Path to conversations.json",
    )
    parser.add_argument(
        "--input", dest="input_flag", metavar="FILE",
        help="Path to conversations.json (alternative to positional)",
    )

    # State
    parser.add_argument(
        "--state", default=str(DEFAULT_STATE_PATH), metavar="FILE",
        help=f"State file for resuming (default: {DEFAULT_STATE_PATH})",
    )

    # Filtering
    parser.add_argument(
        "--limit", type=int, default=None, metavar="N",
        help="Process at most N unprocessed conversations this run",
    )
    parser.add_argument(
        "--since", metavar="YYYY-MM-DD",
        help="Only process conversations updated on or after this date",
    )
    parser.add_argument(
        "--until", metavar="YYYY-MM-DD",
        help="Only process conversations updated on or before this date",
    )
    parser.add_argument(
        "--min-chars", type=int, default=100, metavar="N",
        help="Skip conversations with fewer than N rendered chars (default: 100)",
    )

    # Modes
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be processed; do not call the API or write beats",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="Show tabular status of all conversations and exit",
    )
    parser.add_argument(
        "--reprocess-errors", action="store_true",
        help="Retry conversations that previously resulted in an error",
    )

    # Format
    parser.add_argument(
        "--format", choices=["claude", "chatgpt"], default="claude",
        help="Export format: 'claude' (Anthropic, default) or 'chatgpt' (OpenAI)",
    )

    # Behaviour
    parser.add_argument(
        "--delay", type=float, default=2.0, metavar="SECONDS",
        help="Pause between API calls in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--cwd", default=os.getcwd(),
        help="Working directory for knowledge.local.json resolution (default: current dir)",
    )
    parser.add_argument(
        "--project-name", default="claude-desktop-import",
        help="Project name written into beat frontmatter (default: claude-desktop-import)",
    )

    args = parser.parse_args()

    # Resolve input path from either positional or flag
    args.input = args.input_pos or args.input_flag
    if not args.input and not args.list:
        parser.error("a conversations.json path is required (positional or --input)")

    return args


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def load_state(state_path: Path) -> dict:
    if state_path.exists():
        try:
            with open(state_path, encoding="utf-8") as f:
                state = json.load(f)
            state.setdefault("conversations", {})
            return state
        except (json.JSONDecodeError, OSError) as e:
            print(f"[import] Warning: could not load state from {state_path}: {e}", file=sys.stderr)
            print("[import] Starting with fresh state.", file=sys.stderr)
    return {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "conversations": {},
    }


def record_state(
    state: dict,
    uuid: str,
    status: str,
    beats_written: int,
    error: str | None,
    name: str,
) -> None:
    state["conversations"][uuid] = {
        "status": status,
        "beats_written": beats_written,
        "error": error,
        "name": name,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }
    state["updated_at"] = datetime.now(timezone.utc).isoformat()


def save_state(state: dict, state_path: Path) -> None:
    """Atomically write state (via rename) so a crash never corrupts it."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, state_path)


# ---------------------------------------------------------------------------
# Conversation loading
# ---------------------------------------------------------------------------

def load_conversations(input_path: str) -> list[dict]:
    path = Path(input_path).expanduser()
    if not path.exists():
        print(f"[import] Input file not found: {path}", file=sys.stderr)
        sys.exit(1)
    print(f"[import] Loading {path}...", file=sys.stderr)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[import] JSON parse error: {e}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(data, list):
        print(f"[import] Expected JSON array, got {type(data).__name__}", file=sys.stderr)
        sys.exit(1)
    print(f"[import] Loaded {len(data)} conversation(s)", file=sys.stderr)
    return data


# ---------------------------------------------------------------------------
# Conversation rendering
# ---------------------------------------------------------------------------

def render_message_text(msg: dict) -> str:
    """
    Extract clean text from a message.

    Prefers content[].type==text blocks over msg['text']. In this export format,
    the text field contains "This block is not supported" rendering artifacts for
    tool_use/tool_result blocks in ~38% of conversations.  The content text blocks
    are always clean.
    """
    text_blocks = [
        block for block in msg.get("content", [])
        if block.get("type") == "text"
    ]
    if text_blocks:
        return "".join(b.get("text", "") for b in text_blocks).strip()
    # Fallback for messages that have no content list (e.g., simple human turns)
    return (msg.get("text") or "").strip()


def conversation_char_count(conv: dict) -> int:
    """Count rendered text characters (using content blocks for accuracy)."""
    return sum(len(render_message_text(m)) for m in conv.get("chat_messages", []))


def render_conversation(conv: dict) -> str:
    """
    Render a conversation to a plain-text transcript for LLM extraction.

    Format:
        ## {name}
        Date: YYYY-MM-DD
        Summary: ...

        **Human:** ...

        **Assistant:** ...
    """
    parts: list[str] = []

    name = conv.get("name") or "Untitled"
    date = (conv.get("updated_at") or "")[:10]
    summary = (conv.get("summary") or "").strip()

    parts.append(f"## {name}")
    if date:
        parts.append(f"Date: {date}")
    if summary:
        parts.append(f"Summary: {summary}")
    parts.append("")

    for msg in conv.get("chat_messages", []):
        sender = msg.get("sender", "unknown")
        label = "Human" if sender == "human" else "Assistant"
        text = render_message_text(msg)
        if text:
            parts.append(f"**{label}:** {text}")
            parts.append("")

    rendered = "\n".join(parts).strip()

    # Truncate at the same limit as extract_beats, keeping the tail
    if len(rendered) > MAX_TRANSCRIPT_CHARS:
        rendered = "...[earlier content truncated]...\n\n" + rendered[-MAX_TRANSCRIPT_CHARS:]

    return rendered


# ---------------------------------------------------------------------------
# Format-agnostic conversation helpers
# ---------------------------------------------------------------------------

def conv_id(conv: dict, fmt: str) -> str:
    """Return conversation unique ID for the given format."""
    if fmt == "chatgpt":
        return conv.get("id") or conv.get("conversation_id", "")
    return conv["uuid"]


def conv_updated_date(conv: dict, fmt: str) -> str:
    """Return YYYY-MM-DD date string for date filtering."""
    if fmt == "chatgpt":
        ts = conv.get("update_time") or conv.get("create_time") or 0
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    return (conv.get("updated_at") or "")[:10]


# ---------------------------------------------------------------------------
# ChatGPT conversation rendering
# ---------------------------------------------------------------------------

def extract_chatgpt_thread(mapping: dict, current_node: str) -> list[dict]:
    """Walk from current_node back through parent links; return ordered messages."""
    thread, node_id = [], current_node
    while node_id:
        node = mapping.get(node_id)
        if node is None:
            break
        if node.get("message") is not None:
            thread.append(node["message"])
        node_id = node.get("parent")
    thread.reverse()
    return thread


def render_chatgpt_message_text(msg: dict) -> str:
    content = msg.get("content") or {}
    if content.get("content_type") != "text":
        return ""
    parts = content.get("parts") or []
    return "".join(p for p in parts if isinstance(p, str)).strip()


def render_chatgpt_conversation(conv: dict) -> str:
    """Render a ChatGPT conversation to plain-text for LLM extraction."""
    parts = []
    title = conv.get("title") or "Untitled"
    update_time = conv.get("update_time")
    if update_time:
        date = datetime.fromtimestamp(update_time, tz=timezone.utc).strftime("%Y-%m-%d")
        parts.extend([f"## {title}", f"Date: {date}", ""])
    else:
        parts.extend([f"## {title}", ""])
    mapping = conv.get("mapping") or {}
    current_node = conv.get("current_node", "")
    thread = extract_chatgpt_thread(mapping, current_node)
    for msg in thread:
        role = (msg.get("author") or {}).get("role", "")
        if role in {"system", "tool"}:
            continue
        label = "Human" if role == "user" else "Assistant"
        text = render_chatgpt_message_text(msg)
        if text:
            parts.extend([f"**{label}:** {text}", ""])
    rendered = "\n".join(parts).strip()
    if len(rendered) > MAX_TRANSCRIPT_CHARS:
        rendered = "...[earlier content truncated]...\n\n" + rendered[-MAX_TRANSCRIPT_CHARS:]
    return rendered


def conv_char_count(conv: dict, fmt: str) -> int:
    """Count rendered text characters for the given format."""
    if fmt == "chatgpt":
        return len(render_chatgpt_conversation(conv))
    return conversation_char_count(conv)


def conv_has_content(conv: dict, fmt: str) -> bool:
    """Return True if the conversation has extractable message content."""
    if fmt == "chatgpt":
        return bool(conv.get("mapping") and conv.get("current_node"))
    return bool(conv.get("chat_messages"))


# ---------------------------------------------------------------------------
# Work queue builder
# ---------------------------------------------------------------------------

def build_work_queue(
    conversations: list[dict],
    state: dict,
    *,
    fmt: str,
    reprocess_errors: bool,
    since: str | None,
    until: str | None,
) -> list[dict]:
    """
    Return conversations that need processing, sorted oldest-first.

    Date-filtered conversations are excluded silently (no state entry written).
    Only truly skipped conversations (too short, no messages) get state entries.
    """
    done_statuses = {"ok", "skipped"}
    if not reprocess_errors:
        done_statuses.add("error")

    sorted_convs = sorted(conversations, key=lambda c: conv_updated_date(c, fmt))
    queue = []

    for conv in sorted_convs:
        uid = conv_id(conv, fmt)
        existing_status = state["conversations"].get(uid, {}).get("status")

        if existing_status in done_statuses:
            continue

        updated = conv_updated_date(conv, fmt)
        if since and updated < since:
            continue
        if until and updated > until:
            continue

        queue.append(conv)

    return queue


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def process_conversation(
    conv: dict,
    config: dict,
    autofile_enabled: bool,
    cwd: str,
    eb,
    fmt: str = "claude",
) -> tuple[int, list[Path]]:
    """
    Extract beats from one conversation and write them to the vault.

    Returns (beats_written_count, list_of_written_paths).
    Raises on any exception (caller records error in state).
    """
    uid = conv_id(conv, fmt)

    # Use the conversation's own timestamp so beats carry their original date.
    # Claude format: full ISO string; ChatGPT format: unix float → datetime.
    now = datetime.now(timezone.utc)
    if fmt == "chatgpt":
        ts = conv.get("update_time") or conv.get("create_time")
        if ts:
            now = datetime.fromtimestamp(ts, tz=timezone.utc)
    else:
        updated_at_str = conv.get("updated_at") or ""
        if updated_at_str:
            try:
                now = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
            except ValueError:
                pass

    if fmt == "chatgpt":
        transcript = render_chatgpt_conversation(conv)
    else:
        transcript = render_conversation(conv)
    if not transcript.strip():
        return 0, []

    beats = eb.extract_beats(transcript, config, "import", cwd)
    if not beats:
        return 0, []

    written: list[Path] = []
    for beat in beats:
        try:
            if autofile_enabled:
                path = eb.autofile_beat(beat, config, uid, cwd, now)
            else:
                path = eb.write_beat(beat, config, uid, cwd, now)
            if path:
                written.append(path)
        except Exception as e:
            print(
                f"    [warn] beat '{beat.get('title', '?')}' failed: {e}",
                file=sys.stderr,
            )

    return len(written), written


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_table(conversations: list[dict], state: dict, fmt: str = "claude") -> None:
    sorted_convs = sorted(conversations, key=lambda c: conv_updated_date(c, fmt))
    totals: dict[str, int] = {"ok": 0, "skipped": 0, "error": 0, "pending": 0}

    print(f"{'ID':<15} {'Status':<9} {'Beats':>5}  {'Updated':<10}  {'Chars':>6}  Name")
    print("-" * 88)

    for conv in sorted_convs:
        uid = conv_id(conv, fmt)
        short_uid = uid[:12] + "..."
        name = (conv.get("name") or conv.get("title") or "(unnamed)")[:42]
        updated = conv_updated_date(conv, fmt)
        chars = conv_char_count(conv, fmt)

        entry = state["conversations"].get(uid, {})
        status = entry.get("status", "pending")
        beats = str(entry.get("beats_written", "")) if status != "pending" else ""

        totals[status] = totals.get(status, 0) + 1

        # Colour-code status using ANSI if the terminal supports it
        if sys.stdout.isatty():
            colour = {"ok": "\033[32m", "error": "\033[31m",
                      "skipped": "\033[33m", "pending": ""}.get(status, "")
            reset = "\033[0m" if colour else ""
        else:
            colour = reset = ""

        print(
            f"{short_uid:<15} {colour}{status:<9}{reset} {beats:>5}  "
            f"{updated:<10}  {chars:>6}  {name}"
        )

    print("-" * 88)
    print(
        f"Total: {len(conversations)}  "
        f"ok={totals['ok']}  skipped={totals['skipped']}  "
        f"error={totals['error']}  pending={totals['pending']}"
    )


def print_dry_run_plan(
    work_queue: list[dict],
    state: dict,
    min_chars: int,
    fmt: str = "claude",
) -> None:
    print(f"Dry run — no API calls will be made.\n")
    print(f"Work queue: {len(work_queue)} conversation(s) to process")
    print(f"Processing order: oldest-first by date\n")

    for idx, conv in enumerate(work_queue, 1):
        chars = conv_char_count(conv, fmt)
        name = (conv.get("name") or conv.get("title") or "(unnamed)")[:55]
        updated = conv_updated_date(conv, fmt)
        skip_note = ""
        if chars < min_chars:
            skip_note = f" -> SKIP: too short ({chars} chars < {min_chars})"
        elif not conv_has_content(conv, fmt):
            skip_note = " -> SKIP: no messages"
        print(f"  [{idx:>3}] {updated}  {chars:>6} chars  {name}{skip_note}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    # Fail fast: ensure extract_beats is available before loading anything
    eb = _import_extract_beats()

    # Load conversations
    if args.input:
        conversations = load_conversations(args.input)
    else:
        conversations = []

    # Load state
    state_path = Path(args.state)
    state = load_state(state_path)

    fmt = args.format

    # --list mode
    if args.list:
        print_table(conversations, state, fmt=fmt)
        return

    # Resolve config and inject project name
    config = dict(eb.resolve_config(args.cwd))
    config["project_name"] = args.project_name
    autofile_enabled = config.get("autofile", False)
    journal_enabled = config.get("daily_journal", False)

    if autofile_enabled:
        print("[import] autofile=true — each beat will be filed intelligently into the vault")
    else:
        print("[import] autofile=false — beats will be written to staging folder")

    # Build work queue
    work_queue = build_work_queue(
        conversations,
        state,
        fmt=fmt,
        reprocess_errors=args.reprocess_errors,
        since=args.since,
        until=args.until,
    )

    if args.limit is not None:
        work_queue = work_queue[: args.limit]

    already_done = len(conversations) - len(
        [c for c in conversations if state["conversations"].get(conv_id(c, fmt), {}).get("status") not in {"ok", "skipped", "error"}]
    ) - len(work_queue) + (len(work_queue) if args.limit else 0)

    # --dry-run mode
    if args.dry_run:
        print_dry_run_plan(work_queue, state, args.min_chars, fmt=fmt)
        return

    if not work_queue:
        print("[import] Nothing to do — all conversations already processed.")
        print("[import] Use --reprocess-errors to retry errors, or --list to review status.")
        return

    total = len(work_queue)
    done_count = len(state["conversations"])
    print(
        f"[import] {total} conversation(s) to process "
        f"({done_count} already in state)\n"
    )

    session_written: list[Path] = []
    counts = {"ok": 0, "skipped": 0, "error": 0}

    try:
        for idx, conv in enumerate(work_queue, 1):
            uid = conv_id(conv, fmt)
            name = (conv.get("name") or conv.get("title") or "(unnamed)")[:70]
            chars = conv_char_count(conv, fmt)

            print(f"[{idx:>{len(str(total))}}/{total}] {name}")

            # Skip: no messages
            if not conv_has_content(conv, fmt):
                reason = "No messages"
                print(f"  -> skipped: {reason}")
                record_state(state, uid, "skipped", 0, reason, name)
                save_state(state, state_path)
                counts["skipped"] += 1
                continue

            # Skip: too short
            if chars < args.min_chars:
                reason = f"Too short ({chars} chars < {args.min_chars} min)"
                print(f"  -> skipped: {reason}")
                record_state(state, uid, "skipped", 0, reason, name)
                save_state(state, state_path)
                counts["skipped"] += 1
                continue

            # Extract
            try:
                beats_written, written_paths = process_conversation(
                    conv, config, autofile_enabled, args.cwd, eb, fmt=fmt
                )
                session_written.extend(written_paths)
                print(f"  -> ok: {beats_written} beat(s) written")
                record_state(state, uid, "ok", beats_written, None, name)
                save_state(state, state_path)
                counts["ok"] += 1

            except Exception as exc:
                error_msg = repr(exc)[:500]
                print(f"  -> error: {error_msg}")
                record_state(state, uid, "error", 0, error_msg, name)
                save_state(state, state_path)
                counts["error"] += 1

            # Delay between API calls
            if idx < total and args.delay > 0:
                time.sleep(args.delay)

    except KeyboardInterrupt:
        processed = counts["ok"] + counts["skipped"] + counts["error"]
        remaining = total - processed
        print(
            f"\n[import] Interrupted after {processed} conversation(s). "
            f"{remaining} remaining."
        )
        print(f"[import] State saved. Re-run the same command to continue.")

    # Journal entry
    if journal_enabled and session_written:
        now = datetime.now(timezone.utc)
        eb.write_journal_entry(
            session_written, config, "desktop-import",
            config.get("project_name", "claude-desktop-import"), now,
        )

    # Summary
    processed = counts["ok"] + counts["skipped"] + counts["error"]
    print(f"\n[import] Done. Processed {processed}/{total} conversation(s) this run:")
    print(f"  ok={counts['ok']}  skipped={counts['skipped']}  error={counts['error']}")
    print(f"  Beats written this run: {len(session_written)}")
    if counts["error"]:
        print(f"\n  {counts['error']} error(s) recorded. Re-run with --reprocess-errors to retry.")
    if counts["ok"] + counts["error"] < total - counts["skipped"]:
        remaining = total - processed
        print(f"  {remaining} conversation(s) remaining. Re-run to continue.")


if __name__ == "__main__":
    main()
