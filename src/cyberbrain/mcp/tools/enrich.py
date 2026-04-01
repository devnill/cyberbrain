"""cb_enrich tool — scan vault and enrich notes with missing metadata."""

import io
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
    require_config,
    update_vault_note,
    write_vault_note,
)
from cyberbrain.mcp.shared import (
    _load_tool_prompt as _load_prompt,
)

_DAILY_JOURNAL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
_BATCH_SIZE = 10
_DEFAULT_ENTITY_TYPES = ["project", "note", "resource", "archived"]
_BEAT_TYPES = {"decision", "insight", "problem", "reference"}

# Placeholder values written by LLM when it has no real content to offer.
# Notes containing these values should be re-enriched as if the field were missing.
_PLACEHOLDER_SUMMARIES: set[str] = {"New accurate summary.", ""}
_PLACEHOLDER_TAGS: set[str] = {"new-tag", "updated"}


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


def _needs_enrichment(
    path: Path, fm: dict, valid_types: set[str] | list[str], overwrite: bool
) -> tuple[bool, str]:
    """Return (needs_enrichment, reason).

    Accepts a pre-parsed frontmatter dict and the note path (for context).
    valid_types is used for type validation.
    """
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

    # Detect placeholder summary written by LLM when it had no real content
    if str(summary).strip() in (_PLACEHOLDER_SUMMARIES - {""}):
        return True, "placeholder summary"

    tags = fm.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    elif not isinstance(tags, list):
        tags = []
    if not tags:
        return True, "missing tags"

    # Detect placeholder tags written by LLM when it had no real content
    existing_tag_set = {str(t) for t in tags}
    if existing_tag_set and existing_tag_set <= _PLACEHOLDER_TAGS:
        return True, "placeholder tags"

    trivial = {"personal", "work", "home", "general"}
    if all(t.lower() in trivial for t in tags):
        return True, "only generic tags"

    return False, ""


def _apply_frontmatter_update(
    path: Path,
    content: str,
    classification: dict,
    overwrite: bool,
    vault_path: str = "",
) -> bool:
    """Apply classification to the note's frontmatter using ruamel.yaml.

    Parses the full frontmatter block, updates fields in-place, and re-serializes.
    Never appends raw YAML strings — idempotent by design.

    Returns True on success, False on failure.
    """
    try:
        from ruamel.yaml import YAML
    except ImportError:
        # Graceful degradation: ruamel.yaml unavailable
        return False

    # Detect frontmatter boundaries
    stripped = content.lstrip()
    has_fm = stripped.startswith("---")
    if has_fm:
        # Find the closing --- (must be on its own line, after the opening)
        fm_end = content.find("\n---", 3)
        if fm_end == -1:
            # Malformed: opening --- with no closing ---
            return False
        # Consume the closing --- line (may be \n---\n or \n--- at EOF)
        after_close = content[fm_end + 4 :]  # skip "\n---"
        if after_close and after_close[0] == "\n":
            body_text = after_close[1:]
        else:
            body_text = after_close
        fm_raw = content[3:fm_end]  # text between opening and closing ---
    else:
        fm_raw = ""
        body_text = content

    # Parse existing frontmatter
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.default_flow_style = False
    try:
        fm_data = yaml.load(fm_raw) if fm_raw.strip() else None
    except Exception:  # intentional: ruamel.yaml can raise many error types
        return False

    if fm_data is None:
        fm_data = {}
    if not isinstance(fm_data, dict):
        return False

    changed = False
    now = datetime.now(UTC)

    # --- type ---
    new_type = classification.get("type")
    if new_type:
        existing_type = fm_data.get("type", "")
        if not existing_type or overwrite:
            fm_data["type"] = new_type
            changed = True

    # --- summary ---
    new_summary = classification.get("summary")
    if new_summary:
        existing_summary = str(fm_data.get("summary", "")).strip()
        is_placeholder = existing_summary in _PLACEHOLDER_SUMMARIES
        if not existing_summary or is_placeholder or overwrite:
            fm_data["summary"] = new_summary
            changed = True

    # --- tags ---
    new_tags = classification.get("tags", [])
    if new_tags:
        existing_tags = fm_data.get("tags", [])
        if isinstance(existing_tags, str):
            existing_tags = [t.strip() for t in existing_tags.split(",") if t.strip()]
        existing_tag_set = {str(t) for t in existing_tags} if existing_tags else set()
        is_placeholder_tags = (
            bool(existing_tag_set) and existing_tag_set <= _PLACEHOLDER_TAGS
        )
        if not existing_tags or is_placeholder_tags or overwrite:
            fm_data["tags"] = new_tags
            changed = True

    if not changed and has_fm:
        return True  # nothing to update

    # Always stamp cb_modified and updated when we write
    fm_data["cb_modified"] = now.strftime("%Y-%m-%dT%H:%M:%S")
    fm_data["updated"] = now.strftime("%Y-%m-%d")

    if not has_fm:
        # Prepend a complete frontmatter block for notes that had none
        if "id" not in fm_data:
            fm_data["id"] = str(uuid.uuid4())

    # Serialize the updated frontmatter
    out = io.StringIO()
    try:
        yaml.dump(fm_data, out)
    except Exception:  # intentional: ruamel.yaml serialization errors
        return False

    fm_text = out.getvalue().rstrip("\n")
    new_content = f"---\n{fm_text}\n---\n{body_text}"

    try:
        if vault_path and path.exists():
            update_vault_note(path, new_content, vault_path)
        elif vault_path:
            write_vault_note(path, new_content, vault_path)
        else:
            path.write_text(new_content, encoding="utf-8")
        return True
    except (OSError, ValueError):
        return False


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

        config = require_config()
        gate_enabled = config.get("quality_gate_enabled", True)
        vault_path_str = config.get("vault_path", "")

        vault = Path(vault_path_str).expanduser().resolve()

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

            if not content.strip().startswith("---"):
                fm: dict = {}
            else:
                fm = _parse_frontmatter(content)
            needs, reason = _needs_enrichment(f, fm, valid_types, overwrite)
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

                success = _apply_frontmatter_update(
                    f, content, cls, overwrite, vault_path=config["vault_path"]
                )
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
