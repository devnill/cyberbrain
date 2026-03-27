"""cb_enrich tool — scan vault and enrich notes with missing metadata."""

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from cyberbrain.extractors.frontmatter import parse_frontmatter as _parse_frontmatter
from cyberbrain.mcp.shared import (
    _index_paths,
    _load_config,
)
from cyberbrain.mcp.shared import (
    _load_tool_prompt as _load_prompt,
)

_DAILY_JOURNAL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
_BATCH_SIZE = 10
_DEFAULT_ENTITY_TYPES = ["project", "note", "resource", "archived"]
_BEAT_TYPES = {"decision", "insight", "problem", "reference"}


def _get_valid_types(vault: Path) -> list[str]:
    """Extract valid entity type vocabulary from vault CLAUDE.md, or return defaults."""
    claude_md = vault / "CLAUDE.md"
    if not claude_md.exists():
        return _DEFAULT_ENTITY_TYPES[:]

    content = claude_md.read_text(encoding="utf-8")
    # Look for `type: typename` patterns in YAML examples within the CLAUDE.md,
    # but exclude beat types (decision/insight/problem/reference) which are a
    # separate vocabulary used during extraction, not vault entity types.
    yaml_types = re.findall(r"\btype:\s+([a-z][a-z-]+)\b", content)
    if yaml_types:
        seen: list[str] = []
        skip = {"journal", "moc", "template", "skip"} | _BEAT_TYPES
        for t in yaml_types:
            if t not in seen and t not in skip:
                seen.append(t)
        if len(seen) >= 2:
            return seen[:10]

    return _DEFAULT_ENTITY_TYPES[:]


def _get_vault_type_context(vault: Path) -> str:
    """Return the type context string to inject into the enrich system prompt."""
    claude_md = vault / "CLAUDE.md"
    if claude_md.exists():
        content = claude_md.read_text(encoding="utf-8")
        return (
            "Use ONLY the vault entity type vocabulary from the CLAUDE.md below. "
            "Valid entity types are: project, note, resource, archived. "
            "Do NOT use beat types (decision, insight, problem, reference) — "
            "those are a separate extraction vocabulary and must not appear as `type:` values.\n\n"
            "For domain tags, every note MUST have at least one of: work, personal, knowledge. "
            "Add this based on the note's folder location and content. "
            "Then add 2-5 specific topic tags.\n\n"
            f"Vault CLAUDE.md (excerpt):\n{content[:3000]}"
        )
    types = _DEFAULT_ENTITY_TYPES
    return (
        f"Use these four entity types: {', '.join(types)}.\n"
        "- project: active work being built or maintained\n"
        "- note: quick capture, meeting note, or uncertain item\n"
        "- resource: stable reference used for lookup\n"
        "- archived: completed, retired, or superseded\n\n"
        "Do NOT use beat types (decision, insight, problem, reference) as `type:` values."
    )


def _should_skip(path: Path, vault: Path, content: str) -> bool:
    """Return True if this note should be skipped for enrichment."""
    if _DAILY_JOURNAL_RE.match(path.name):
        return True

    parts = [p.lower() for p in path.relative_to(vault).parts[:-1]]
    if any(p in ("templates", "_templates") for p in parts):
        return True

    fm = _parse_frontmatter(content)
    if fm.get("enrich") == "skip":
        return True
    if fm.get("type") in ("journal", "moc"):
        return True

    return False


def _needs_enrichment(content: str, valid_types: list[str]) -> tuple[bool, str]:
    """Return (needs_enrichment, reason). valid_types used for type validation."""
    if not content.strip().startswith("---"):
        return True, "no frontmatter"

    fm = _parse_frontmatter(content)
    if not fm:
        return True, "no frontmatter"

    note_type = fm.get("type", "")
    if not note_type:
        return True, "missing type"
    if note_type not in valid_types:
        return True, f"invalid type: '{note_type}'"

    summary = fm.get("summary", "")
    if not summary or not str(summary).strip():
        return True, "missing summary"

    tags = fm.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    elif not isinstance(tags, list):
        tags = []
    if not tags:
        return True, "missing tags"

    trivial = {"personal", "work", "home", "general"}
    if all(t.lower() in trivial for t in tags):
        return True, "only generic tags"

    return False, ""


def _apply_frontmatter_update(
    path: Path,
    content: str,
    classification: dict,
    overwrite: bool,
) -> bool:
    """Apply classification to the note's frontmatter. Returns True on success."""
    fm = _parse_frontmatter(content)
    # Check for actual frontmatter: starts with --- and has a closing ---
    has_fm = content.strip().startswith("---") and content.find("\n---\n", 3) != -1
    # Malformed: starts with --- but no closing ---
    if content.strip().startswith("---") and not has_fm:
        return False

    fields_to_set: dict = {}

    if classification.get("type"):
        if not fm.get("type") or overwrite:
            fields_to_set["type"] = classification["type"]

    if classification.get("summary"):
        if not fm.get("summary") or overwrite:
            fields_to_set["summary"] = classification["summary"]

    new_tags = classification.get("tags", [])
    if new_tags:
        existing_tags = fm.get("tags", [])
        if isinstance(existing_tags, str):
            existing_tags = [t.strip() for t in existing_tags.split(",") if t.strip()]
        if not existing_tags or overwrite:
            fields_to_set["tags"] = new_tags

    if not fields_to_set:
        return True  # nothing to update

    fields_to_set["cb_modified"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")

    if has_fm:
        # Insert new fields before the closing ---
        # Find the closing --- separator (not the opening one at position 0)
        fm_end = content.find("\n---\n", 3)
        if fm_end == -1:
            # Check if file ends with --- (malformed or empty frontmatter)
            stripped_end = content.rstrip()
            if stripped_end.endswith("---"):
                # Find where the trailing --- starts
                fm_end = content.rfind("---")
                if fm_end <= 3:  # Must be after the opening ---
                    return False
            else:
                return False

        lines_to_add = _format_fm_fields(fields_to_set)
        new_content = (
            content[:fm_end] + "\n" + "\n".join(lines_to_add) + content[fm_end:]
        )
    else:
        # Prepend a complete frontmatter block
        new_id = str(uuid.uuid4())
        fm_lines = ["---", f"id: {new_id}"] + _format_fm_fields(fields_to_set) + ["---"]
        new_content = "\n".join(fm_lines) + "\n\n" + content

    try:
        path.write_text(new_content, encoding="utf-8")
        return True
    except OSError:
        return False


def _format_fm_fields(fields: dict) -> list[str]:
    """Format frontmatter fields as YAML lines."""
    lines = []
    if "type" in fields:
        lines.append(f"type: {fields['type']}")
    if "summary" in fields:
        escaped = fields["summary"].replace('"', '\\"')
        lines.append(f'summary: "{escaped}"')
    if "tags" in fields:
        tags_str = "[" + ", ".join(fields["tags"]) + "]"
        lines.append(f"tags: {tags_str}")
    if "cb_modified" in fields:
        lines.append(f"cb_modified: {fields['cb_modified']}")
    return lines


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def cb_enrich(
        folder: Annotated[
            str,
            Field(
                description="Vault-relative subfolder to scan. Empty = entire vault."
            ),
        ] = "",
        dry_run: Annotated[
            bool,
            Field(description="Report what would change without modifying any files."),
        ] = False,
        since: Annotated[
            str,
            Field(
                description="ISO date (YYYY-MM-DD). Only process notes modified on or after this date."
            ),
        ] = "",
        limit: Annotated[
            int,
            Field(
                ge=0, description="Maximum number of notes to enrich. 0 = unlimited."
            ),
        ] = 0,
        overwrite: Annotated[
            bool,
            Field(
                description="Replace existing type/summary/tags values instead of additive-only."
            ),
        ] = False,
    ) -> str:
        """
        Scan the vault for notes missing metadata (type, summary, tags) and enrich them.

        Makes manually-authored notes findable via cb_recall by adding classification
        metadata. Additive-only by default — existing fields are never overwritten
        unless overwrite=True.

        Use dry_run=True first to preview how many notes would be affected and why.
        Processes up to 10 notes per LLM call; large vaults may take multiple calls.
        """
        from cyberbrain.extractors.backends import call_model, get_model_for_tool
        from cyberbrain.extractors.quality_gate import quality_gate as _quality_gate

        config = _load_config()
        gate_enabled = config.get("quality_gate_enabled", True)
        vault_path_str = config.get("vault_path", "")
        if not vault_path_str:
            raise ToolError(
                "No vault configured. Run cb_configure(vault_path=...) first."
            )

        vault = Path(vault_path_str).expanduser().resolve()
        if not vault.exists():
            raise ToolError(f"Vault path does not exist: {vault}")

        valid_types = _get_valid_types(vault)
        vault_type_context = _get_vault_type_context(vault)

        scan_root = vault / folder if folder else vault
        since_dt = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since).replace(tzinfo=UTC)
            except ValueError:
                raise ToolError(f"Invalid date for 'since': {since}. Use YYYY-MM-DD.")

        # ── Scan for candidate files ──
        all_files = sorted(
            f
            for f in scan_root.rglob("*.md")
            if not any(part.startswith(".") for part in f.relative_to(vault).parts)
        )

        if since_dt:
            all_files = [
                f
                for f in all_files
                if datetime.fromtimestamp(f.stat().st_mtime, tz=UTC) >= since_dt
            ]

        needs_enrichment: list[tuple[Path, str, str]] = []
        already_done = 0
        skipped = 0

        for f in all_files:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                skipped += 1
                continue

            if _should_skip(f, vault, content):
                skipped += 1
                continue

            needs, reason = _needs_enrichment(content, valid_types)
            if needs or overwrite:
                needs_enrichment.append(
                    (f, content, reason if needs else "overwrite mode")
                )
            else:
                already_done += 1

        if limit > 0:
            needs_enrichment = needs_enrichment[:limit]

        total_scanned = len(all_files)

        if dry_run:
            lines = [
                f"[DRY RUN] Would enrich {len(needs_enrichment)} of {total_scanned} notes scanned",
                f"Valid types: {', '.join(valid_types)}",
            ]
            if not needs_enrichment:
                lines.append("All notes already have required metadata.")
            if needs_enrichment:
                lines.append("\nWould enrich:")
                for f, _, reason in needs_enrichment:
                    rel = f.relative_to(vault)
                    lines.append(f"  + {rel}  — {reason}")
            lines.append(f"\nAlready done: {already_done} notes")
            lines.append(
                f"Skipped:      {skipped} notes (templates, daily journals, enrich:skip)"
            )
            lines.append("\nNo files were modified. Run without dry_run=True to apply.")
            return "\n".join(lines)

        if not needs_enrichment:
            return (
                f"cb_enrich complete — {total_scanned} notes scanned. "
                "All notes already have required metadata."
            )

        # ── Load prompt templates ──
        system_prompt_template = _load_prompt("enrich-system.md")
        user_prompt_template = _load_prompt("enrich-user.md")

        enriched: list[tuple[Path, dict]] = []
        errors: list[tuple[Path, str]] = []
        from cyberbrain.extractors.quality_gate import GateVerdict as _GateVerdict

        gate_skipped: list[tuple[Path, dict, _GateVerdict]] = []

        # ── Process in batches ──
        for batch_start in range(0, len(needs_enrichment), _BATCH_SIZE):
            batch = needs_enrichment[batch_start : batch_start + _BATCH_SIZE]

            notes_block_parts = []
            for idx, (f, content, _) in enumerate(batch):
                rel = f.relative_to(vault)
                notes_block_parts.append(f"--- Note {idx}: {rel} ---\n{content[:3000]}")
            notes_block = "\n\n".join(notes_block_parts)

            system_prompt = system_prompt_template.replace(
                "{vault_type_context}", vault_type_context
            )
            user_message = user_prompt_template.replace(
                "{count}", str(len(batch))
            ).replace("{notes_block}", notes_block)

            tool_config = {**config, "model": get_model_for_tool(config, "enrich")}
            try:
                raw = call_model(system_prompt, user_message, tool_config)
                stripped = re.sub(r"^```(?:json)?\s*", "", raw.strip())
                stripped = re.sub(r"\s*```$", "", stripped).strip()
                classifications = json.loads(stripped)
            except json.JSONDecodeError as e:
                for f, _, _ in batch:
                    errors.append((f, f"JSON parse error: {e}"))
                continue
            except Exception as e:  # intentional: catches BackendError and any other LLM call failure; batch is skipped
                for f, _, _ in batch:
                    errors.append((f, str(e)))
                continue

            if not isinstance(classifications, list):
                for f, _, _ in batch:
                    errors.append((f, "expected JSON array from model"))
                continue

            for idx, (f, content, _) in enumerate(batch):
                if idx >= len(classifications):
                    errors.append((f, "missing from model response"))
                    continue

                cls = classifications[idx]
                if cls.get("skip"):
                    skipped += 1
                    continue

                # ── Quality gate ──
                if gate_enabled:
                    gate_input = f"Note path: {f.relative_to(vault)}\n\nNote content:\n{content[:2000]}"
                    gate_output = json.dumps(cls)
                    verdict = _quality_gate(
                        "enrich_classify", gate_input, gate_output, config
                    )
                    if not verdict.passed:
                        gate_skipped.append((f, cls, verdict))
                        continue

                success = _apply_frontmatter_update(f, content, cls, overwrite)
                if success:
                    enriched.append((f, cls))
                else:
                    errors.append((f, "frontmatter update failed"))

        # Update search index with enriched notes (metadata changed)
        _index_paths([f for f, _ in enriched], config)

        # ── Report ──
        lines = [
            f"cb_enrich complete — {total_scanned} notes scanned\n",
            f"  Enriched:     {len(enriched)} notes",
            f"  Already done: {already_done} notes",
            f"  Skipped:      {skipped} notes (templates, daily journals, enrich:skip, no-match)",
            f"  Gate blocked: {len(gate_skipped)} notes",
            f"  Errors:       {len(errors)} notes",
        ]
        if enriched:
            lines.append("\nEnriched:")
            for f, cls in enriched:
                rel = f.relative_to(vault)
                tags_str = ", ".join(cls.get("tags", [])[:3])
                lines.append(
                    f"  + {rel}  → type: {cls.get('type', '?')}, tags: [{tags_str}]"
                )
        if gate_skipped:
            lines.append("\nBlocked by quality gate (not applied):")
            for f, cls, verdict in gate_skipped:
                rel = f.relative_to(vault)
                lines.append(
                    f"  ✗ {rel}  → type: {cls.get('type', '?')} — {verdict.rationale}"
                )
            lines.append(
                "\nCall cb_configure(quality_gate_enabled=False) to disable quality gates."
            )
        if errors:
            lines.append("\nErrors:")
            for f, reason in errors:
                rel = f.relative_to(vault)
                lines.append(f"  ✗ {rel}  — {reason}")

        return "\n".join(lines)
