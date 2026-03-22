#!/usr/bin/env python3
"""
Standalone vault frontmatter repair script.

Walks all .md files in the vault and deduplicates YAML frontmatter keys,
keeping the last occurrence of each key (consistent with pyyaml behavior).

Usage:
    python scripts/repair_frontmatter.py [--apply] [--vault PATH]

Default mode is dry-run — no files are written without --apply.
"""

import argparse
import json
import sys
from pathlib import Path

CONFIG_PATH = Path.home() / ".claude" / "cyberbrain" / "config.json"


def get_vault_path(args):
    if args.vault:
        return Path(args.vault)
    if not CONFIG_PATH.exists():
        print(
            f"Error: config not found at {CONFIG_PATH} and --vault not provided.",
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
            "Error: 'vault_path' not set in config.json. Use --vault to override.",
            file=sys.stderr,
        )
        sys.exit(1)
    return Path(vault_path)


def parse_frontmatter(text):
    """
    Parse a markdown file's text into (frontmatter_lines, body_text, has_frontmatter).

    Returns:
        (frontmatter_lines, body, True)  if frontmatter block found
        (None, text, False)              if no frontmatter
    """
    if not text.startswith("---"):
        return None, text, False

    # Find the closing --- (must be on its own line, after the opening ---)
    # The opening --- must be followed by a newline
    rest = text[3:]
    if not rest.startswith("\n"):
        return None, text, False

    # Require closing --- to be followed by \n or end-of-string
    closing_idx = rest.find("\n---\n")
    if closing_idx == -1:
        # Check if file ends with \n---
        if rest.endswith("\n---"):
            closing_idx = len(rest) - 4
        else:
            return None, text, False

    frontmatter_block = rest[1:closing_idx]  # lines between opening and closing ---
    # Body is everything after the closing \n---
    after_closing = rest[closing_idx + 4 :]  # skip \n---
    # The closing --- may be followed by \n or end of file
    body = after_closing

    frontmatter_lines = frontmatter_block.splitlines(keepends=True)
    return frontmatter_lines, body, True


def find_duplicate_keys(frontmatter_lines):
    """
    Return a dict of {key: count} for keys appearing more than once.
    Only considers top-level keys (lines with ':' not starting with whitespace).
    """
    key_counts = {}
    for line in frontmatter_lines:
        # Top-level keys: line doesn't start with whitespace and contains ':'
        stripped = line.rstrip("\n")
        if stripped and not stripped[0].isspace() and ":" in stripped:
            key = stripped.split(":", 1)[0].strip()
            if key:
                key_counts[key] = key_counts.get(key, 0) + 1
    return {k: v for k, v in key_counts.items() if v > 1}


def deduplicate_frontmatter(frontmatter_lines):
    """
    Deduplicate frontmatter lines, keeping the last occurrence of each key
    (including any continuation lines for multi-line values).

    Returns deduplicated list of lines.
    """
    # Build blocks: each block is (key, [lines]) for top-level keys,
    # or (None, [lines]) for lines that are part of a value (indented/continuation).
    blocks = []  # list of [key_or_none, [lines]]
    current_key = None
    current_lines = []

    for line in frontmatter_lines:
        stripped = line.rstrip("\n")
        if stripped and not stripped[0].isspace() and ":" in stripped:
            # New top-level key
            if current_lines:
                blocks.append((current_key, current_lines))
            current_key = stripped.split(":", 1)[0].strip()
            current_lines = [line]
        else:
            # Continuation / indented / blank line within frontmatter
            current_lines.append(line)

    if current_lines:
        blocks.append((current_key, current_lines))

    # Keep last occurrence of each key, preserving order of last occurrence
    # Walk blocks in order, tracking last index for each key
    last_index = {}
    for i, (key, _) in enumerate(blocks):
        if key is not None:
            last_index[key] = i

    seen_keys = set()
    result_lines = []
    for i, (key, lines) in enumerate(blocks):
        if key is None:
            result_lines.extend(lines)
        elif last_index[key] == i:
            result_lines.extend(lines)
            seen_keys.add(key)
        # else: earlier duplicate — skip

    return result_lines


def repair_file(text):
    """
    Given file text, return (repaired_text, duplicate_keys_dict) where
    duplicate_keys_dict is {key: original_count} for keys that were duplicated.

    Returns (None, {}) if no frontmatter or no duplicates.
    """
    frontmatter_lines, body, has_frontmatter = parse_frontmatter(text)
    if not has_frontmatter:
        return None, {}

    duplicates = find_duplicate_keys(frontmatter_lines)
    if not duplicates:
        return None, {}

    deduped_lines = deduplicate_frontmatter(frontmatter_lines)
    new_frontmatter = "".join(deduped_lines)

    # Reconstruct: opening ---, newline, frontmatter, closing ---
    # Preserve the body exactly as-is
    repaired = "---\n" + new_frontmatter + "\n---" + body

    # Safety: if identical to original, return None (no change)
    if repaired == text:
        return None, {}

    return repaired, duplicates


def main():
    parser = argparse.ArgumentParser(
        description="Repair duplicate YAML frontmatter keys in vault .md files."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write repaired frontmatter to disk (default: dry-run, no writes)",
    )
    parser.add_argument(
        "--vault",
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

    scanned = 0
    found = 0
    repaired = 0

    for md_file in sorted(vault_path.rglob("*.md")):
        scanned += 1
        rel_path = md_file.relative_to(vault_path)

        try:
            text = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"  WARNING: Could not read {rel_path}: {e}")
            continue

        repaired_text, duplicates = repair_file(text)
        if not duplicates:
            continue

        found += 1

        if args.apply:
            prefix = "  Repaired:"
        else:
            prefix = "  [DRY RUN] Would repair:"

        print(f"{prefix} {rel_path}")
        for key, count in duplicates.items():
            print(f"    - {key} ({count} → 1)")

        if args.apply and repaired_text is not None:
            try:
                md_file.write_text(repaired_text, encoding="utf-8")
                repaired += 1
            except OSError as e:
                print(f"  WARNING: Could not write {rel_path}: {e}")

    print()
    if args.apply:
        print(
            f"Summary: {scanned} notes scanned, {found} with duplicate fields, {repaired} repaired"
        )
    else:
        print(
            f"Summary: {scanned} notes scanned, {found} with duplicate fields, 0 repaired (dry-run)"
        )
        if found > 0:
            print("Run with --apply to write repairs.")


if __name__ == "__main__":
    main()
