"""
run_log.py

Deduplication log, structured runs log, and daily journal for cyberbrain.
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from cyberbrain.extractors.state import extract_log_path, runs_log_path


def __getattr__(name: str):  # noqa: N807 — PEP 562 lazy module attributes
    """Lazy module attributes — tests can still patch by name via monkeypatch.setattr."""
    if name == "EXTRACT_LOG_PATH":
        return extract_log_path()
    if name == "RUNS_LOG_PATH":
        return runs_log_path()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def is_session_already_extracted(session_id: str) -> bool:
    """Check if a session ID already appears in the deduplication log."""
    import cyberbrain.extractors.run_log as _self

    log = _self.EXTRACT_LOG_PATH  # __getattr__ or test-patched
    if not log.exists():
        return False
    try:
        text = log.read_text(encoding="utf-8")
        for line in text.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1] == session_id:
                return True
        return False
    except OSError as e:
        print(
            f"[extract_beats] Warning: could not read deduplication log: {e}",
            file=sys.stderr,
        )
        return False


def write_extract_log_entry(session_id: str, beat_count: int) -> None:
    """Append a tab-separated entry to the deduplication log."""
    import cyberbrain.extractors.run_log as _self

    try:
        log = _self.EXTRACT_LOG_PATH
        log.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
        entry = f"{timestamp}\t{session_id}\t{beat_count}\n"
        with open(log, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError as e:
        print(
            f"[extract_beats] Warning: could not write deduplication log: {e}",
            file=sys.stderr,
        )


def write_runs_log_entry(entry: dict) -> None:
    """Append a JSON object to the runs log (one entry per extraction run)."""
    import cyberbrain.extractors.run_log as _self

    try:
        log = _self.RUNS_LOG_PATH
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        print(
            f"[extract_beats] Warning: could not write runs log: {e}", file=sys.stderr
        )


def write_journal_entry(
    written_paths: list, config: dict, session_id: str, project_name: str, now: datetime
) -> None:
    journal_folder = config.get("journal_folder", "AI/Journal")
    journal_name_tpl = config.get("journal_name", "%Y-%m-%d")
    date_str = now.strftime(journal_name_tpl)

    vault = Path(config["vault_path"])
    journal_dir = vault / journal_folder
    journal_dir.mkdir(parents=True, exist_ok=True)
    journal_path = journal_dir / f"{date_str}.md"

    # Build wikilinks for each written file (shortest-path format — title only)
    links = []
    for path in written_paths:
        stem = path.stem
        links.append(f"- [[{stem}]]")
    links_block = "\n".join(links) if links else "- (none)"

    # Format: ## Session abc12345 — YYYY-MM-DD HH:MM UTC (project-name)
    timestamp_str = now.strftime("%Y-%m-%d %H:%M")
    session_block = (
        f"\n## Session {session_id[:8]} — {timestamp_str} UTC ({project_name})\n\n"
        f"{len(written_paths)} note(s) captured:\n{links_block}\n"
    )

    if journal_path.exists():
        with open(journal_path, "a", encoding="utf-8") as f:
            f.write(session_block)
    else:
        header = f"---\ntype: journal\ndate: {now.strftime('%Y-%m-%d')}\n---\n\n# {date_str}\n"
        journal_path.write_text(header + session_block, encoding="utf-8")

    print(f"[extract_beats] Journal updated: {journal_path}", file=sys.stderr)
