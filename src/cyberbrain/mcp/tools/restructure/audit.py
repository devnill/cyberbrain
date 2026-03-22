"""Audit phase for cb_restructure — quality and topical fit checks."""

import json
import re

from cyberbrain.mcp.shared import _load_tool_prompt as _load_prompt
from cyberbrain.mcp.tools.restructure.format import _build_audit_notes_block
from cyberbrain.mcp.tools.restructure.utils import _repair_json

_AUDIT_BATCH_SIZE = 20
_AUDIT_MAX_WORKERS = 4


def _call_audit_notes_batch(
    notes: list[dict],
    folder_path: str,
    vault_structure: str,
    prefs_section: str,
    config: dict,
    audit_system: str,
    audit_user_tmpl: str,
) -> list[dict]:
    """Audit a single batch of notes. Returns flag decisions only."""
    from cyberbrain.extractors.backends import (
        BackendError,
        call_model,
        get_model_for_tool,
    )

    tool_config = {**config, "model": get_model_for_tool(config, "restructure")}
    notes_block = _build_audit_notes_block(notes)
    user_msg = (
        audit_user_tmpl.replace("{folder_path}", folder_path)
        .replace("{note_count}", str(len(notes)))
        .replace("{vault_prefs_section}", prefs_section)
        .replace("{vault_structure}", vault_structure)
        .replace("{notes_block}", notes_block)
    )
    try:
        raw = call_model(audit_system, user_msg, tool_config)
    except BackendError:
        return []
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        result = _repair_json(raw)
        return [
            d
            for d in result
            if isinstance(d, dict)
            and d.get("action") in ("flag-misplaced", "flag-low-quality")
        ]
    except json.JSONDecodeError:
        return []


def _call_audit_notes(
    notes: list[dict],
    folder_path: str,
    vault_structure: str,
    prefs_section: str,
    config: dict,
) -> list[dict]:
    """Audit all notes for quality and topical fit, in parallel batches.

    Notes are split into batches of _AUDIT_BATCH_SIZE and processed concurrently
    so audit quality stays high regardless of folder size.
    """
    if not notes:
        return []
    from concurrent.futures import ThreadPoolExecutor, as_completed

    audit_system = _load_prompt("restructure-audit-system.md")
    audit_user_tmpl = _load_prompt("restructure-audit-user.md")
    batches = [
        notes[i : i + _AUDIT_BATCH_SIZE]
        for i in range(0, len(notes), _AUDIT_BATCH_SIZE)
    ]
    if len(batches) == 1:
        return _call_audit_notes_batch(
            batches[0],
            folder_path,
            vault_structure,
            prefs_section,
            config,
            audit_system,
            audit_user_tmpl,
        )
    flags: list[dict] = []
    with ThreadPoolExecutor(
        max_workers=min(len(batches), _AUDIT_MAX_WORKERS)
    ) as executor:
        futures = {
            executor.submit(
                _call_audit_notes_batch,
                batch,
                folder_path,
                vault_structure,
                prefs_section,
                config,
                audit_system,
                audit_user_tmpl,
            ): i
            for i, batch in enumerate(batches)
        }
        for future in as_completed(futures):
            try:
                flags.extend(future.result())
            except Exception:  # intentional: individual audit batch failure is non-fatal; other batches continue
                pass
    return flags
