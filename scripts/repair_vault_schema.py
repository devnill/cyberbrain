#!/usr/bin/env python3
"""Standalone vault schema repair script.

Walks all .md files and fixes schema violations in cyberbrain-generated notes.
Only processes notes containing cb_source: or cb_created: in frontmatter.

Usage:
    python scripts/repair_vault_schema.py [--apply] [--vault-path PATH]

Default mode is dry-run — no files are written without --apply.
"""

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML

CONFIG_PATH = Path.home() / ".claude" / "cyberbrain" / "config.json"

_PYTEST_TMPDIR_PATTERN = re.compile(r"/pytest-\d+/|/pytest_[^/]+/|/tmp/pytest[-_]")
_BEAT_TO_ENTITY: dict[str, str] = {
    "decision": "resource",
    "insight": "resource",
    "problem": "note",
    "reference": "resource",
}


def get_vault_path(args: argparse.Namespace) -> Path:
    if args.vault_path:
        return Path(args.vault_path)
    if not CONFIG_PATH.exists():
        print(
            f"Error: config not found at {CONFIG_PATH} and --vault-path not provided.",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        config = json.loads(CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error reading config {CONFIG_PATH}: {e}", file=sys.stderr)
        sys.exit(1)
    vault_path = config.get("vault_path")
    if not vault_path:
        print(
            "Error: 'vault_path' not set in config.json. Use --vault-path to override.",
            file=sys.stderr,
        )
        sys.exit(1)
    return Path(vault_path)


def _extract_date(value: object) -> str | None:
    """Extract YYYY-MM-DD string from a frontmatter date value (str or datetime)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    s = str(value)
    if len(s) >= 10:
        return s[:10]
    return None


def _is_cyberbrain_note(fm: dict[str, object]) -> bool:
    """Return True if the frontmatter contains cb_source or cb_created."""
    return "cb_source" in fm or "cb_created" in fm


def repair_note(text: str, today: date | None = None) -> tuple[str, list[str]]:
    """Parse, repair, and re-serialise a single .md file's content.

    Returns:
        (repaired_text, changes)  where changes is a list of human-readable
        descriptions of what was modified.  If no changes are needed, changes
        is empty and repaired_text equals text.
    """
    if today is None:
        today = date.today()

    yaml = YAML()
    yaml.preserve_quotes = True

    # --- locate frontmatter block ---
    if not text.startswith("---"):
        return text, []

    rest = text[3:]
    if not rest.startswith("\n"):
        return text, []

    closing_idx = rest.find("\n---\n")
    if closing_idx == -1:
        if rest.endswith("\n---"):
            closing_idx = len(rest) - 4
            body = ""
        else:
            return text, []
    else:
        body = rest[closing_idx + 5 :]

    fm_block = rest[1:closing_idx]

    try:
        fm = yaml.load(fm_block)
    except Exception:
        return text, []

    if not isinstance(fm, dict):
        return text, []

    if not _is_cyberbrain_note(fm):
        return text, []

    changes: list[str] = []

    # --- type correction ---
    note_type = fm.get("type")
    if isinstance(note_type, str) and note_type in _BEAT_TO_ENTITY:
        new_type = _BEAT_TO_ENTITY[note_type]
        fm["type"] = new_type
        changes.append(f"type: {note_type!r} → {new_type!r}")

    # --- status correction ---
    status = fm.get("status")
    if isinstance(status, str) and status == "completed":
        # Use explicit truthy check: the string "false" must not be treated as ephemeral
        _cb_eph = fm.get("cb_ephemeral")
        is_ephemeral = _cb_eph is True or _cb_eph == "true" or _cb_eph == 1
        if is_ephemeral:
            # Check if expired working-memory
            review_after_raw = fm.get("cb_review_after")
            expired = False
            if review_after_raw is not None:
                review_after_str = _extract_date(review_after_raw)
                if review_after_str:
                    try:
                        review_after_date = date.fromisoformat(review_after_str)
                        expired = review_after_date < today
                    except ValueError:
                        pass
            new_status = "done" if expired else "active"
        else:
            new_status = "active"
        fm["status"] = new_status
        changes.append(f"status: 'completed' → {new_status!r}")

    # --- add durability if missing ---
    if "durability" not in fm:
        _cb_eph = fm.get("cb_ephemeral")
        is_ephemeral = _cb_eph is True or _cb_eph == "true" or _cb_eph == 1
        durability_val = "working-memory" if is_ephemeral else "durable"
        fm["durability"] = durability_val
        changes.append(f"durability: added '{durability_val}'")

    # --- add cb_review_after for ephemeral notes if missing ---
    _cb_eph = fm.get("cb_ephemeral")
    if (_cb_eph is True or _cb_eph == "true" or _cb_eph == 1) and "cb_review_after" not in fm:
        review_date = today + timedelta(days=28)
        review_str = review_date.strftime("%Y-%m-%d")
        fm["cb_review_after"] = review_str
        changes.append(f"cb_review_after: added {review_str} (28 days from today)")

    # --- add aliases if missing ---
    if "aliases" not in fm:
        fm["aliases"] = []
        changes.append("aliases: added []")

    # --- add created from cb_created if missing ---
    if "created" not in fm:
        cb_created_raw = fm.get("cb_created")
        created_str = _extract_date(cb_created_raw)
        if created_str:
            fm["created"] = created_str
            changes.append(f"created: derived from cb_created ({created_str})")

    # --- add updated if missing ---
    if "updated" not in fm:
        cb_modified_raw = fm.get("cb_modified")
        updated_str = _extract_date(cb_modified_raw)
        if updated_str is None:
            cb_created_raw = fm.get("cb_created")
            updated_str = _extract_date(cb_created_raw)
        if updated_str:
            fm["updated"] = updated_str
            changes.append(
                f"updated: derived from cb_modified/cb_created ({updated_str})"
            )

    if not changes:
        return text, []

    # Re-serialise frontmatter with ruamel.yaml
    buf = StringIO()
    yaml.dump(fm, buf)
    new_fm_block = buf.getvalue().rstrip("\n")

    repaired = "---\n" + new_fm_block + "\n---\n" + body
    return repaired, changes


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repair schema violations in cyberbrain-generated vault notes."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write repairs to disk (default: dry-run, no writes)",
    )
    parser.add_argument(
        "--vault-path",
        metavar="PATH",
        help="Override vault path (default: read from ~/.claude/cyberbrain/config.json)",
    )
    args = parser.parse_args()

    vault_path = get_vault_path(args)

    if not vault_path.is_dir():
        print(
            f"Error: vault path does not exist or is not a directory: {vault_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Scanning vault: {vault_path}")
    if not args.apply:
        print("Mode: dry-run (use --apply to write repairs)")
    print()

    today = date.today()

    scanned = 0
    needs_repair = 0
    repaired_count = 0
    test_artifacts: list[Path] = []

    for md_file in sorted(vault_path.rglob("*.md")):
        # Skip hidden directories and .obsidian/
        parts = md_file.relative_to(vault_path).parts
        if any(p.startswith(".") for p in parts[:-1]):
            continue

        scanned += 1
        rel_path = md_file.relative_to(vault_path)

        try:
            text = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"  WARNING: Could not read {rel_path}: {e}")
            continue

        # Check for pytest test artifact via cwd field
        cwd_match = re.search(r"^cwd:\s*(.+)$", text, re.MULTILINE)
        if cwd_match:
            cwd_value = cwd_match.group(1).strip()
            if _PYTEST_TMPDIR_PATTERN.search(cwd_value):
                test_artifacts.append(md_file)

        repaired_text, changes = repair_note(text, today=today)
        if not changes:
            continue

        needs_repair += 1

        if args.apply:
            prefix = "  Repaired:"
        else:
            prefix = "  [DRY RUN] Would repair:"

        print(f"{prefix} {rel_path}")
        for change in changes:
            print(f"    - {change}")

        if args.apply:
            try:
                md_file.write_text(repaired_text, encoding="utf-8")
                repaired_count += 1
            except OSError as e:
                print(f"  WARNING: Could not write {rel_path}: {e}")

    print()
    if args.apply:
        print(
            f"Summary: {scanned} notes scanned, {needs_repair} needing repair, "
            f"{repaired_count} repaired"
        )
    else:
        print(
            f"Summary: {scanned} notes scanned, {needs_repair} needing repair, "
            f"0 repaired (dry-run)"
        )
        if needs_repair > 0:
            print("Run with --apply to write repairs.")

    # --- test artifact report ---
    if test_artifacts:
        print()
        print(f"Test artifacts detected ({len(test_artifacts)}):")
        for p in test_artifacts:
            print(f"  {p.relative_to(vault_path)}")

        if args.apply:
            print()
            answer = (
                input("Move these test artifact notes to trash? [y/N] ").strip().lower()
            )
            if answer == "y":
                trashed = 0
                # Note: this script intentionally does not call _move_to_trash() from
                # src/cyberbrain/mcp/shared.py. As a standalone CLI tool it uses stdlib
                # only and cannot import the MCP layer without pulling in fastmcp/mcp
                # dependencies. The logic here is semantically equivalent: vault-relative
                # path preserved under .trash/, numeric suffix on collision, no hard deletes.
                trash_root = vault_path / ".trash"
                for p in test_artifacts:
                    try:
                        rel = p.relative_to(vault_path)
                        dest = trash_root / rel
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        if dest.exists():
                            stem = dest.stem
                            suffix = dest.suffix
                            counter = 1
                            while dest.exists():
                                dest = dest.parent / f"{stem}_{counter}{suffix}"
                                counter += 1
                        p.rename(dest)
                        trashed += 1
                        print(f"  Moved to trash: {rel}")
                    except OSError as e:
                        print(
                            f"  WARNING: Could not trash {p.relative_to(vault_path)}: {e}"
                        )
                print(f"  {trashed} test artifact(s) moved to trash.")
            else:
                print("  Skipped — no test artifacts moved.")
        else:
            print("  (dry-run: test artifacts are listed but not deleted)")


if __name__ == "__main__":
    main()
