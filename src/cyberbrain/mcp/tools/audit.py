"""cb_audit tool — read-only vault health check."""

import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from cyberbrain.extractors.state import audit_report_path, search_db_path
from cyberbrain.mcp.shared import require_config

# Characters that break Obsidian wikilink resolution
_INVALID_FILENAME_CHARS = re.compile(r"[#\[\]\^]")

# Entity types stored in the search index (post-remap vocabulary)
_VALID_ENTITY_TYPES: frozenset[str] = frozenset(
    {"resource", "note", "project", "archived"}
)


def _get_notes_from_index(
    db_path: str, folder: str | None, vault_path: str
) -> tuple[list[dict], bool]:
    """
    Query the search index for all notes (optionally filtered by folder).

    Returns (notes, used_index) where used_index=True means the index was available.
    Each note dict has: path, title, summary, tags, related, type, scope, project.
    """
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        if count == 0:
            return [], False

        if folder:
            # Normalize to absolute path for LIKE matching
            vault = Path(vault_path)
            folder_abs = str((vault / folder).resolve())
            rows = conn.execute(
                "SELECT path, title, summary, tags, related, type, scope, project "
                "FROM notes WHERE path LIKE ?",
                (folder_abs.rstrip("/") + "/%",),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT path, title, summary, tags, related, type, scope, project FROM notes"
            ).fetchall()

        all_titles = {
            r[0] for r in conn.execute("SELECT title FROM notes").fetchall() if r[0]
        }
        notes = [dict(row) for row in rows]
        # Attach the full title set for relation integrity checks
        for note in notes:
            note["_all_titles"] = all_titles
        return notes, True
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return [], False
    finally:
        if conn is not None:
            conn.close()


def _get_notes_from_filesystem(
    vault_path: str, folder: str | None
) -> tuple[list[dict], set[str]]:
    """
    Walk the vault (or a subfolder) and read frontmatter directly.

    Returns (notes, all_titles).
    Each note dict has frontmatter fields plus 'path'.
    """
    from cyberbrain.extractors.frontmatter import read_frontmatter

    vault = Path(vault_path)
    scan_root = vault / folder if folder else vault

    md_files = [
        p
        for p in scan_root.rglob("*.md")
        if not any(part.startswith(".") for part in p.parts)
    ]

    notes = []
    for p in md_files:
        fm = read_frontmatter(str(p))
        fm["path"] = str(p)
        notes.append(fm)

    all_titles = {n.get("title", "") for n in notes if n.get("title")}
    return notes, all_titles


def _read_durability_and_review(paths: list[str]) -> dict[str, dict]:
    """
    Read durability and cb_review_after from frontmatter for a list of paths.
    Returns {path: {durability, cb_review_after}}.
    """
    from cyberbrain.extractors.frontmatter import read_frontmatter

    result: dict[str, dict] = {}
    for p in paths:
        fm = read_frontmatter(p)
        result[p] = {
            "durability": fm.get("durability", ""),
            "cb_review_after": fm.get("cb_review_after", ""),
        }
    return result


def _run_checks(
    notes: list[dict],
    extra_fm: dict[str, dict],
    all_titles: set[str],
    config: dict,
    valid_types: frozenset[str],
    using_index: bool,
) -> dict[str, list[dict]]:
    """
    Run all 8 checks. Returns {check_name: [violation_dicts]}.
    """
    vault_path = config.get("vault_path", "")
    vault = Path(vault_path)
    wm_folder = config.get("working_memory_folder", "AI/Working Memory")
    wm_root = vault / wm_folder
    vault_folder = config.get("vault_folder", "")
    project_name = config.get("project_name", "")

    violations: dict[str, list[dict]] = {
        "check_1_frontmatter_completeness": [],
        "check_2_type_vocabulary": [],
        "check_3_scope_validity": [],
        "check_4_durability_validity": [],
        "check_5_routing_compliance": [],
        "check_6_filename_characters": [],
        "check_7_relation_integrity": [],
        "check_8_wm_review_date": [],
    }

    required_fields = {"type", "scope", "durability", "summary", "tags"}

    for note in notes:
        path = note.get("path", "")
        p = Path(path)
        filename_stem = p.stem

        # --- Resolve durability (may need extra_fm) ---
        if using_index:
            durability = extra_fm.get(path, {}).get("durability", "")
            cb_review_after = extra_fm.get(path, {}).get("cb_review_after", "")
        else:
            durability = str(note.get("durability", "") or "")
            cb_review_after = note.get("cb_review_after", "")

        note_type = str(note.get("type", "") or "")
        scope = str(note.get("scope", "") or "")

        # Check 1 — Frontmatter completeness
        # When using index, durability comes from extra_fm
        missing = []
        for field in required_fields:
            if field == "durability":
                val = durability
            elif field == "tags":
                raw = note.get("tags", "") or ""
                if isinstance(raw, str):
                    try:
                        raw = json.loads(raw)
                    except (json.JSONDecodeError, ValueError):
                        pass
                val = raw if raw else None
            else:
                val = note.get(field)
            if not val:
                missing.append(field)
        if missing:
            violations["check_1_frontmatter_completeness"].append(
                {"path": path, "missing_fields": missing}
            )

        # Check 2 — Type vocabulary
        if note_type and note_type not in valid_types:
            violations["check_2_type_vocabulary"].append(
                {
                    "path": path,
                    "type": note_type,
                    "valid_types": sorted(valid_types),
                }
            )

        # Check 3 — Scope validity
        if scope and scope not in {"project", "general"}:
            violations["check_3_scope_validity"].append({"path": path, "scope": scope})

        # Check 4 — Durability validity
        if durability and durability not in {"durable", "working-memory"}:
            violations["check_4_durability_validity"].append(
                {"path": path, "durability": durability}
            )

        # Check 5 — Routing compliance
        if p.exists():
            resolved = p.resolve()
            if scope == "project" and vault_folder and project_name:
                expected_root = (vault / vault_folder).resolve()
                # WM notes should not be flagged here; they're handled by WM check below
                if durability != "working-memory":
                    try:
                        resolved.relative_to(expected_root)
                    except ValueError:
                        violations["check_5_routing_compliance"].append(
                            {
                                "path": path,
                                "reason": "project-scoped note not under vault_folder",
                                "expected_root": str(expected_root),
                            }
                        )
            if durability == "working-memory":
                wm_abs = wm_root.resolve()
                try:
                    resolved.relative_to(wm_abs)
                except ValueError:
                    violations["check_5_routing_compliance"].append(
                        {
                            "path": path,
                            "reason": "working-memory note not under working_memory_folder",
                            "expected_root": str(wm_abs),
                        }
                    )

        # Check 6 — Filename characters
        if _INVALID_FILENAME_CHARS.search(filename_stem):
            bad_chars = sorted(set(_INVALID_FILENAME_CHARS.findall(filename_stem)))
            violations["check_6_filename_characters"].append(
                {"path": path, "filename": p.name, "bad_chars": bad_chars}
            )

        # Check 7 — Relation integrity
        related_raw = note.get("related", "") or ""
        if isinstance(related_raw, list):
            related_titles = [str(r).strip() for r in related_raw if r]
        else:
            try:
                parsed = json.loads(related_raw)
                if isinstance(parsed, list):
                    related_titles = [str(r).strip() for r in parsed if r]
                else:
                    related_titles = (
                        [related_raw.strip()] if related_raw.strip() else []
                    )
            except (json.JSONDecodeError, ValueError):
                related_titles = [
                    t.strip() for t in related_raw.split(",") if t.strip()
                ]
        # Normalise wikilink formats before title lookup:
        # [[Title]] → "Title",  [[Title|Alias]] → "Title",  [[Title#Section]] → "Title"
        related_titles = [re.sub(r"^\[\[(.+?)(?:[|#].+)?\]\]$", r"\1", t).strip() if t.startswith("[[") else t.strip() for t in related_titles]
        broken = [t for t in related_titles if t and t not in all_titles]
        if broken:
            violations["check_7_relation_integrity"].append(
                {"path": path, "broken_wikilinks": broken}
            )

        # Check 8 — WM review date
        if durability == "working-memory" and not cb_review_after:
            violations["check_8_wm_review_date"].append(
                {"path": path, "reason": "working-memory note missing cb_review_after"}
            )

    return violations


def _build_report(
    generated_at: str,
    vault_path: str,
    folder_scope: str | None,
    total_notes_scanned: int,
    violations: dict[str, list[dict]],
) -> dict:
    """Build the JSON report dict."""
    violations_by_check: dict[str, int] = {k: len(v) for k, v in violations.items()}
    per_note: dict[str, list[str]] = {}
    for check_name, items in violations.items():
        for item in items:
            p = item.get("path", "unknown")
            if p not in per_note:
                per_note[p] = []
            per_note[p].append(check_name)

    return {
        "generated_at": generated_at,
        "vault_path": vault_path,
        "folder_scope": folder_scope,
        "total_notes_scanned": total_notes_scanned,
        "violations_by_check": violations_by_check,
        "per_note_violations": per_note,
    }


def _format_summary(
    report: dict,
    report_path: str,
    used_index: bool,
) -> str:
    """Format the markdown summary returned to the caller."""
    lines = ["## cb_audit Report", ""]

    if not used_index:
        lines.append(
            "_Note: Search index was absent or empty; fell back to direct frontmatter reads._"
        )
        lines.append("")

    scope_label = report["folder_scope"] or "(full vault)"
    lines.append(f"**Vault:** {report['vault_path']}")
    lines.append(f"**Scope:** {scope_label}")
    lines.append(f"**Notes scanned:** {report['total_notes_scanned']}")
    lines.append(f"**Generated:** {report['generated_at']}")
    lines.append("")

    total_violations = sum(report["violations_by_check"].values())
    lines.append(f"**Total violations:** {total_violations}")
    lines.append("")
    lines.append("### Violations by Check")
    lines.append("")

    check_labels = {
        "check_1_frontmatter_completeness": "Check 1 — Frontmatter completeness",
        "check_2_type_vocabulary": "Check 2 — Type vocabulary",
        "check_3_scope_validity": "Check 3 — Scope validity",
        "check_4_durability_validity": "Check 4 — Durability validity",
        "check_5_routing_compliance": "Check 5 — Routing compliance",
        "check_6_filename_characters": "Check 6 — Filename characters",
        "check_7_relation_integrity": "Check 7 — Relation integrity",
        "check_8_wm_review_date": "Check 8 — WM review date",
    }

    for key, label in check_labels.items():
        count = report["violations_by_check"].get(key, 0)
        status = "ok" if count == 0 else f"{count} violation(s)"
        lines.append(f"- **{label}:** {status}")

    lines.append("")
    lines.append(f"Full report written to: `{report_path}`")
    return "\n".join(lines)


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
    def cb_audit(
        folder: Annotated[
            str | None,
            Field(
                description=(
                    "Vault-relative folder to limit the audit scope, "
                    "e.g. 'Projects/my-project'. Omit to scan the full vault."
                )
            ),
        ] = None,
    ) -> str:
        """
        Audit vault note health: check frontmatter completeness, type/scope/durability
        validity, routing compliance, filename characters, relation integrity, and working
        memory review dates.

        Read-only — makes no changes to the vault, index, or config.

        Returns a markdown summary with violation counts per check. The full per-note
        report is written to ~/.claude/cyberbrain/audit-report.json.

        Pass folder='Projects/my-project' to limit the scan to one subfolder.
        """
        config = require_config()
        vault_path = config.get("vault_path", "")
        vault = Path(vault_path)

        # Validate folder param is within vault
        if folder:
            folder_path = (vault / folder).resolve()
            try:
                folder_path.relative_to(vault.resolve())
            except ValueError:
                raise ToolError(f"folder must be within the vault. Got: {folder!r}")

        db_path = config.get("search_db_path", str(search_db_path()))

        # --- Primary: query search index ---
        notes, used_index = _get_notes_from_index(db_path, folder, vault_path)
        all_titles: set[str] = set()

        if used_index:
            # Collect all titles from the per-note _all_titles set (same for all)
            if notes:
                all_titles = notes[0].get("_all_titles", set())
            # Remove helper key
            for note in notes:
                note.pop("_all_titles", None)
            # Read durability and cb_review_after directly from frontmatter
            paths = [n["path"] for n in notes]
            extra_fm = _read_durability_and_review(paths)
        else:
            # --- Fallback: walk filesystem ---
            notes_raw, all_titles = _get_notes_from_filesystem(vault_path, folder)
            notes = notes_raw
            extra_fm = {}

        # When reading from the index, types are entity vocabulary (post-remap).
        # When falling back to filesystem, legacy notes may have either vocabulary.
        if used_index:
            valid_types = _VALID_ENTITY_TYPES
        else:
            from cyberbrain.extractors.vault import get_valid_beat_types

            valid_types = _VALID_ENTITY_TYPES | get_valid_beat_types(config)

        violations = _run_checks(
            notes,
            extra_fm,
            all_titles,
            config,
            valid_types,
            using_index=used_index,
        )

        generated_at = datetime.now(tz=UTC).isoformat()
        report = _build_report(
            generated_at=generated_at,
            vault_path=vault_path,
            folder_scope=folder,
            total_notes_scanned=len(notes),
            violations=violations,
        )

        # Write full report
        report_file = audit_report_path()
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

        return _format_summary(
            report,
            report_path=str(report_file),
            used_index=used_index,
        )
