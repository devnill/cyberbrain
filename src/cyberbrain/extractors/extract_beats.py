#!/usr/bin/env python3
"""
extract_beats.py
Extracts structured knowledge "beats" from a Claude Code session transcript
and writes them as Obsidian-compatible markdown files.

Usage:
    python3 extract_beats.py \
        --transcript /path/to/transcript.jsonl \
        --session-id abc123 \
        --trigger auto \
        --cwd /Users/dan/code/my-project
"""

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Direct imports needed by main()
# ---------------------------------------------------------------------------
from cyberbrain.extractors.autofile import autofile_beat
from cyberbrain.extractors.backends import (
    CLI_DEFAULT_MODEL,
    DEFAULT_BACKEND,
    BackendError,
)
from cyberbrain.extractors.config import resolve_config
from cyberbrain.extractors.extractor import extract_beats
from cyberbrain.extractors.run_log import (
    is_session_already_extracted,
    write_extract_log_entry,
    write_journal_entry,
    write_runs_log_entry,
)
from cyberbrain.extractors.transcript import parse_jsonl_transcript
from cyberbrain.extractors.vault import (
    make_filename,
    read_vault_claude_md,
    resolve_output_dir,
    write_beat,
)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Extract knowledge beats from a Claude Code transcript"
    )
    parser.add_argument("--transcript", help="Path to transcript JSONL file")
    parser.add_argument(
        "--beats-json",
        help="Path to pre-extracted beats JSON (skips transcript parsing and API call)",
    )
    parser.add_argument("--session-id", required=True, help="Session ID")
    parser.add_argument(
        "--trigger",
        default="auto",
        help="Compaction trigger type (auto, manual, session-end, or any value Claude passes)",
    )
    parser.add_argument(
        "--cwd", required=True, help="Working directory of the Claude Code session"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview beats without writing to vault or log",
    )
    args = parser.parse_args()

    if not args.transcript and not args.beats_json:
        print("[extract_beats] Provide --transcript or --beats-json.", file=sys.stderr)
        sys.exit(1)

    config = resolve_config(args.cwd)
    autofile_enabled = config.get("autofile", False)
    journal_enabled = config.get("daily_journal", False)

    # Derive session ID from transcript filename stem if possible
    session_id = args.session_id
    if args.transcript:
        transcript_stem = Path(args.transcript).stem
        if transcript_stem:
            session_id = transcript_stem

    # Deduplication check (skip in dry-run mode — no writes happen)
    if not args.dry_run and is_session_already_extracted(session_id):
        print(
            f"[extract_beats] Session '{session_id}' already extracted. Skipping.",
            file=sys.stderr,
        )
        sys.exit(0)

    start = time.monotonic()
    llm_duration = 0.0

    if args.beats_json:
        print(
            f"[extract_beats] Loading pre-extracted beats from: {args.beats_json}",
            file=sys.stderr,
        )
        try:
            with open(args.beats_json, encoding="utf-8") as f:
                beats = json.load(f)
        except (OSError, json.JSONDecodeError, ValueError) as e:
            print(f"[extract_beats] Failed to load beats JSON: {e}", file=sys.stderr)
            sys.exit(1)
        if not isinstance(beats, list):
            print(
                "[extract_beats] --beats-json must contain a JSON array.",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        print(f"[extract_beats] Parsing transcript: {args.transcript}", file=sys.stderr)
        transcript_text = parse_jsonl_transcript(args.transcript)

        if not transcript_text.strip():
            print(
                "[extract_beats] Transcript is empty or has no user/assistant turns. Nothing to extract.",
                file=sys.stderr,
            )
            sys.exit(0)

        print("[extract_beats] Calling LLM to extract beats...", file=sys.stderr)
        try:
            llm_start = time.monotonic()
            beats = extract_beats(transcript_text, config, args.trigger, args.cwd)
            llm_duration = time.monotonic() - llm_start
        except BackendError as e:
            print(f"[extract_beats] Backend error: {e}", file=sys.stderr)
            sys.exit(0)

    if not beats:
        print("[extract_beats] No beats extracted.", file=sys.stderr)
        sys.exit(0)

    if args.dry_run:
        total = len(beats)
        separator = "━" * 52
        lines_out = []
        for idx, beat in enumerate(beats, 1):
            title = beat.get("title", "Untitled")
            beat_type = beat.get("type", "reference")
            tags = beat.get("tags", [])
            summary = beat.get("summary", "")
            body = beat.get("body", "").strip()

            # Compute would-be destination path (flat, no autofile LLM call in dry-run)
            try:
                output_dir = resolve_output_dir(beat, config)
                filename = make_filename(title)
                would_be_path = output_dir / filename  # type: ignore[operator]  # output_dir is None-guarded by except below
                vault = Path(config["vault_path"])
                rel_path = os.path.relpath(str(would_be_path), str(vault))
            except Exception:  # intentional: path resolution can fail for missing config keys, bad vault_path, etc.
                rel_path = "(could not compute path)"

            autofile_note = (
                " (routing not simulated in dry-run)" if autofile_enabled else ""
            )

            lines_out.append(
                f"━━━ Beat {idx} of {total} {separator[: max(0, 48 - len(str(idx)) - len(str(total)))]}"
            )
            lines_out.append(f"Type:    {beat_type}")
            lines_out.append(f"Title:   {title}")
            tags_str = ", ".join(str(t) for t in tags) if tags else "(none)"
            lines_out.append(f"Tags:    {tags_str}")
            lines_out.append(f"Summary: {summary}")
            lines_out.append("")
            for body_line in body.splitlines():
                lines_out.append(f"> {body_line}")
            lines_out.append("")
            lines_out.append(f"Action:  would create → {rel_path}{autofile_note}")
            lines_out.append(separator)
            lines_out.append("")

        for line in lines_out:
            print(line)
        print(f"{total} beat(s) would be written. Vault not modified.")
        sys.exit(0)

    now = datetime.now(UTC)
    written = []
    run_errors = []
    beat_records = []

    # Cache vault CLAUDE.md once for the whole autofile run (avoids N disk reads for N beats)
    vault_context = None
    if autofile_enabled:
        vault_context_text = read_vault_claude_md(config["vault_path"])
        vault_context = (
            vault_context_text
            if vault_context_text is not None
            else "File notes using human-readable names with spaces. Use types: decision, insight, problem, reference."
        )

    for beat in beats:
        try:
            if autofile_enabled:
                try:
                    path = autofile_beat(
                        beat,
                        config,
                        session_id,
                        args.cwd,
                        now,
                        vault_context=vault_context,
                    )
                except BackendError as e:
                    print(
                        f"[extract_beats] autofile failed, filing to inbox: {e}",
                        file=sys.stderr,
                    )
                    path = write_beat(beat, config, session_id, args.cwd, now)
            else:
                path = write_beat(beat, config, session_id, args.cwd, now)
            if path:
                written.append(path)
                beat_records.append(
                    {
                        "title": beat.get("title", ""),
                        "type": beat.get("type", ""),
                        "scope": beat.get("scope", ""),
                        "path": os.path.relpath(str(path), config["vault_path"]),
                    }
                )
                print(f"[extract_beats] Wrote: {path}", file=sys.stderr)
        except Exception as e:  # intentional: per-beat write failure is non-fatal; log and continue to next beat
            err_msg = f"write error on '{beat.get('title', '?')}': {e}"
            run_errors.append(err_msg)
            print(
                f"[extract_beats] Failed on '{beat.get('title', '?')}': {e}",
                file=sys.stderr,
            )

    project_name = config.get("project_name", Path(args.cwd).name)

    if journal_enabled and written:
        write_journal_entry(written, config, session_id, project_name, now)

    # Write deduplication log entry
    write_extract_log_entry(session_id, len(written))

    # Write structured runs log entry
    duration = time.monotonic() - start
    write_runs_log_entry(
        {
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "session_id": session_id,
            "trigger": args.trigger,
            "project": project_name,
            "backend": config.get("backend", DEFAULT_BACKEND),
            "model": config.get("model", CLI_DEFAULT_MODEL),
            "duration_seconds": round(duration, 1),
            "llm_duration_seconds": round(llm_duration, 1),
            "beats_extracted": len(beats),
            "beats_written": len(written),
            "beats": beat_records,
            "errors": run_errors,
        }
    )

    print(f"[extract_beats] Done. {len(written)} beat(s) written.", file=sys.stderr)


if __name__ == "__main__":
    main()
