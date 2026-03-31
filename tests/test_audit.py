"""
test_audit.py — unit tests for src/cyberbrain/mcp/tools/audit.py

Covers:
- _get_notes_from_index: index path (used_index=True)
- _get_notes_from_index: filesystem fallback (used_index=False when DB absent)
- Check 1 (frontmatter completeness): missing required field flagged
- Check 2 (type vocabulary): beat type flagged; valid entity type not flagged
- Check 5 (routing compliance): note in wrong folder flagged
- Check 7 (relation integrity): wikilink to non-existent title flagged
- Folder scoping: folder param restricts results
- Report write: JSON written to audit_report_path with expected keys
- ToolError raised when vault_path is empty
"""

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# sys.modules cleanup
#
# audit.py imports from cyberbrain.mcp.shared (which imports shared.py).
# Evict both so FakeMCP receives the registrations from this file's import.
# ---------------------------------------------------------------------------
from tests.conftest import _clear_module_cache

_clear_module_cache(["cyberbrain.mcp.shared", "cyberbrain.mcp.tools.audit"])

from fastmcp.exceptions import ToolError  # noqa: E402

import cyberbrain.mcp.tools.audit as audit_mod  # noqa: E402

# ---------------------------------------------------------------------------
# FakeMCP — captures the registered cb_audit function
# ---------------------------------------------------------------------------


class FakeMCP:
    def __init__(self):
        self._tools = {}

    def tool(self, annotations=None, **kwargs):
        def decorator(fn):
            self._tools[fn.__name__] = {"fn": fn}
            return fn

        return decorator


_fake_mcp = FakeMCP()
audit_mod.register(_fake_mcp)  # type: ignore[arg-type]


def _cb_audit():
    """Return the registered cb_audit function."""
    return _fake_mcp._tools["cb_audit"]["fn"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(db_path: str, rows: list[dict]) -> None:
    """Create a minimal search-index SQLite DB with a notes table."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notes (
            path TEXT,
            title TEXT,
            summary TEXT,
            tags TEXT,
            related TEXT,
            type TEXT,
            scope TEXT,
            project TEXT
        )
        """
    )
    for row in rows:
        conn.execute(
            "INSERT INTO notes (path, title, summary, tags, related, type, scope, project) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row.get("path", ""),
                row.get("title", ""),
                row.get("summary", ""),
                row.get("tags", "[]"),
                row.get("related", "[]"),
                row.get("type", ""),
                row.get("scope", ""),
                row.get("project", ""),
            ),
        )
    conn.commit()
    conn.close()


def _write_md(path: Path, frontmatter: dict, body: str = "") -> None:
    """Write a minimal markdown file with YAML frontmatter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for k, v in frontmatter.items():
        if isinstance(v, list):
            lines.append(f"{k}: {json.dumps(v)}")
        else:
            lines.append(f"{k}: {v!r}")
    lines.append("---")
    if body:
        lines.append(body)
    path.write_text("\n".join(lines), encoding="utf-8")


def _config(vault_path: str, **overrides) -> dict:
    return {
        "vault_path": vault_path,
        "inbox": "AI/Claude-Sessions",
        "backend": "claude-code",
        "model": "claude-haiku-4-5",
        "working_memory_folder": "AI/Working Memory",
        **overrides,
    }


# ===========================================================================
# _get_notes_from_index
# ===========================================================================


class TestGetNotesFromIndex:
    def test_returns_notes_and_used_index_true(self, tmp_path):
        """Index path: well-formed DB returns notes with used_index=True."""
        db_path = str(tmp_path / "search.db")
        vault_path = str(tmp_path / "vault")
        note_path = str(tmp_path / "vault" / "AI" / "Note.md")

        _make_db(
            db_path,
            [
                {
                    "path": note_path,
                    "title": "My Note",
                    "summary": "A summary.",
                    "tags": '["tag1"]',
                    "related": "[]",
                    "type": "insight",
                    "scope": "general",
                    "project": "",
                }
            ],
        )

        notes, used_index = audit_mod._get_notes_from_index(db_path, None, vault_path)

        assert used_index is True
        assert len(notes) == 1
        assert notes[0]["title"] == "My Note"
        assert notes[0]["type"] == "insight"
        # _all_titles should be attached
        assert "My Note" in notes[0]["_all_titles"]

    def test_returns_false_when_db_absent(self, tmp_path):
        """Fallback path: non-existent DB returns ([], False)."""
        db_path = str(tmp_path / "nonexistent.db")
        vault_path = str(tmp_path / "vault")

        notes, used_index = audit_mod._get_notes_from_index(db_path, None, vault_path)

        assert used_index is False
        assert notes == []

    def test_returns_false_when_db_empty(self, tmp_path):
        """Empty DB (0 rows) returns ([], False)."""
        db_path = str(tmp_path / "empty.db")
        vault_path = str(tmp_path / "vault")
        _make_db(db_path, [])

        notes, used_index = audit_mod._get_notes_from_index(db_path, None, vault_path)

        assert used_index is False
        assert notes == []

    def test_folder_scoping_filters_results(self, tmp_path):
        """Folder param restricts notes to paths under that folder."""
        db_path = str(tmp_path / "search.db")
        vault = tmp_path / "vault"
        vault.mkdir(parents=True)
        vault_path = str(vault)

        in_folder = str(vault / "Projects" / "alpha" / "Note A.md")
        out_folder = str(vault / "Projects" / "beta" / "Note B.md")

        _make_db(
            db_path,
            [
                {
                    "path": in_folder,
                    "title": "Note A",
                    "summary": "s",
                    "tags": "[]",
                    "related": "[]",
                    "type": "insight",
                    "scope": "project",
                    "project": "alpha",
                },
                {
                    "path": out_folder,
                    "title": "Note B",
                    "summary": "s",
                    "tags": "[]",
                    "related": "[]",
                    "type": "decision",
                    "scope": "project",
                    "project": "beta",
                },
            ],
        )

        notes, used_index = audit_mod._get_notes_from_index(
            db_path, "Projects/alpha", vault_path
        )

        assert used_index is True
        assert len(notes) == 1
        assert notes[0]["title"] == "Note A"


# ===========================================================================
# _run_checks — Check 1 (frontmatter completeness)
# ===========================================================================


class TestCheck1FrontmatterCompleteness:
    def test_missing_required_field_flagged(self, tmp_path):
        """A note missing 'summary' is flagged by check_1."""
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "Missing Summary.md"
        _write_md(
            note,
            {
                "type": "insight",
                "scope": "general",
                "durability": "durable",
                # summary intentionally absent
                "tags": ["test"],
            },
        )

        notes = [
            {
                "path": str(note),
                "title": "Missing Summary",
                "type": "insight",
                "scope": "general",
                "summary": "",
                "tags": '["test"]',
                "related": "[]",
                "project": "",
            }
        ]
        extra_fm = {str(note): {"durability": "durable", "cb_review_after": ""}}
        config = _config(str(vault))
        valid_beat_types = frozenset({"decision", "insight", "problem", "reference"})

        violations = audit_mod._run_checks(
            notes, extra_fm, set(), config, valid_beat_types, using_index=True
        )

        check1 = violations["check_1_frontmatter_completeness"]
        assert len(check1) == 1
        assert "summary" in check1[0]["missing_fields"]

    def test_complete_note_not_flagged(self, tmp_path):
        """A fully complete note is not flagged by check_1."""
        vault = tmp_path / "vault"
        vault.mkdir()

        notes = [
            {
                "path": str(vault / "Complete Note.md"),
                "title": "Complete Note",
                "type": "insight",
                "scope": "general",
                "summary": "A full summary.",
                "tags": '["test"]',
                "related": "[]",
                "project": "",
            }
        ]
        extra_fm = {
            str(vault / "Complete Note.md"): {
                "durability": "durable",
                "cb_review_after": "",
            }
        }
        config = _config(str(vault))
        valid_beat_types = frozenset({"decision", "insight", "problem", "reference"})

        violations = audit_mod._run_checks(
            notes, extra_fm, set(), config, valid_beat_types, using_index=True
        )

        assert violations["check_1_frontmatter_completeness"] == []


# ===========================================================================
# _run_checks — Check 2 (type vocabulary)
# ===========================================================================


class TestCheck2TypeVocabulary:
    def test_beat_type_in_valid_set_not_flagged(self, tmp_path):
        """Standard beat type 'insight' is not flagged when beat vocabulary is passed."""
        vault = tmp_path / "vault"
        vault.mkdir()

        notes = [
            {
                "path": str(vault / "Note.md"),
                "title": "Note",
                "type": "insight",
                "scope": "general",
                "summary": "S",
                "tags": '["t"]',
                "related": "[]",
                "project": "",
            }
        ]
        extra_fm = {
            str(vault / "Note.md"): {"durability": "durable", "cb_review_after": ""}
        }
        config = _config(str(vault))
        valid_beat_types = frozenset({"decision", "insight", "problem", "reference"})

        violations = audit_mod._run_checks(
            notes, extra_fm, set(), config, valid_beat_types, using_index=True
        )

        assert violations["check_2_type_vocabulary"] == []

    def test_invalid_type_flagged(self, tmp_path):
        """Type 'entity' (not in any known vocabulary) is flagged by check_2."""
        vault = tmp_path / "vault"
        vault.mkdir()

        notes = [
            {
                "path": str(vault / "Note.md"),
                "title": "Note",
                "type": "entity",
                "scope": "general",
                "summary": "S",
                "tags": '["t"]',
                "related": "[]",
                "project": "",
            }
        ]
        extra_fm = {
            str(vault / "Note.md"): {"durability": "durable", "cb_review_after": ""}
        }
        config = _config(str(vault))
        valid_beat_types = frozenset({"decision", "insight", "problem", "reference"})

        violations = audit_mod._run_checks(
            notes, extra_fm, set(), config, valid_beat_types, using_index=True
        )

        check2 = violations["check_2_type_vocabulary"]
        assert len(check2) == 1
        assert check2[0]["type"] == "entity"

    def test_entity_type_not_flagged_with_entity_vocabulary(self, tmp_path):
        """Entity type 'resource' is not flagged when entity vocabulary is used (index path)."""
        vault = tmp_path / "vault"
        vault.mkdir()

        notes = [
            {
                "path": str(vault / "Note.md"),
                "title": "Note",
                "type": "resource",
                "scope": "general",
                "summary": "S",
                "tags": '["t"]',
                "related": "[]",
                "project": "",
            }
        ]
        extra_fm = {
            str(vault / "Note.md"): {"durability": "durable", "cb_review_after": ""}
        }
        config = _config(str(vault))

        violations = audit_mod._run_checks(
            notes,
            extra_fm,
            set(),
            config,
            audit_mod._VALID_ENTITY_TYPES,
            using_index=True,
        )

        assert violations["check_2_type_vocabulary"] == []

    def test_filesystem_fallback_check2_accepts_beat_types(self, tmp_path):
        """In filesystem fallback mode (using_index=False), beat types are accepted (combined vocabulary)."""
        vault = tmp_path / "vault"
        vault.mkdir()

        note_path = str(vault / "Decision Note.md")
        notes = [
            {
                "path": note_path,
                "title": "Decision Note",
                "type": "decision",  # beat vocabulary type
                "scope": "general",
                "summary": "S",
                "tags": '["t"]',
                "related": "[]",
                "project": "",
                "durability": "durable",
                "cb_review_after": "",
            }
        ]
        combined_types = frozenset({"resource", "note", "project", "archived", "decision", "insight", "problem", "reference"})
        config = _config(str(vault))

        violations = audit_mod._run_checks(
            notes, {}, set(), config, combined_types, using_index=False
        )

        assert violations["check_2_type_vocabulary"] == []


# ===========================================================================
# _run_checks — Check 3 (scope validity)
# ===========================================================================


class TestCheck3ScopeValidity:
    def test_invalid_scope_flagged(self, tmp_path):
        """Scope value not in {project, general} is flagged by check_3."""
        vault = tmp_path / "vault"
        vault.mkdir()
        note_path = str(vault / "Note.md")

        notes = [
            {
                "path": note_path,
                "title": "Note",
                "type": "resource",
                "scope": "unknown",
                "summary": "S",
                "tags": '["t"]',
                "related": "[]",
                "project": "",
            }
        ]
        extra_fm = {note_path: {"durability": "durable", "cb_review_after": ""}}
        config = _config(str(vault))

        violations = audit_mod._run_checks(
            notes,
            extra_fm,
            set(),
            config,
            audit_mod._VALID_ENTITY_TYPES,
            using_index=True,
        )

        check3 = violations["check_3_scope_validity"]
        assert len(check3) == 1
        assert check3[0]["scope"] == "unknown"

    def test_valid_scope_not_flagged(self, tmp_path):
        """Scope value 'project' is not flagged by check_3."""
        vault = tmp_path / "vault"
        vault.mkdir()
        note_path = str(vault / "Note.md")

        notes = [
            {
                "path": note_path,
                "title": "Note",
                "type": "resource",
                "scope": "project",
                "summary": "S",
                "tags": '["t"]',
                "related": "[]",
                "project": "my-project",
            }
        ]
        extra_fm = {note_path: {"durability": "durable", "cb_review_after": ""}}
        config = _config(str(vault))

        violations = audit_mod._run_checks(
            notes,
            extra_fm,
            set(),
            config,
            audit_mod._VALID_ENTITY_TYPES,
            using_index=True,
        )

        assert violations["check_3_scope_validity"] == []


# ===========================================================================
# _run_checks — Check 4 (durability validity)
# ===========================================================================


class TestCheck4DurabilityValidity:
    def test_invalid_durability_flagged(self, tmp_path):
        """Durability value 'ephemeral' (not durable/working-memory) is flagged."""
        vault = tmp_path / "vault"
        vault.mkdir()
        note_path = str(vault / "Note.md")

        notes = [
            {
                "path": note_path,
                "title": "Note",
                "type": "resource",
                "scope": "general",
                "summary": "S",
                "tags": '["t"]',
                "related": "[]",
                "project": "",
            }
        ]
        # When using_index=True, durability is read from extra_fm
        extra_fm = {note_path: {"durability": "ephemeral", "cb_review_after": ""}}
        config = _config(str(vault))

        violations = audit_mod._run_checks(
            notes,
            extra_fm,
            set(),
            config,
            audit_mod._VALID_ENTITY_TYPES,
            using_index=True,
        )

        check4 = violations["check_4_durability_validity"]
        assert len(check4) == 1
        assert check4[0]["durability"] == "ephemeral"

    def test_valid_durability_not_flagged(self, tmp_path):
        """Durability value 'durable' is not flagged by check_4."""
        vault = tmp_path / "vault"
        vault.mkdir()
        note_path = str(vault / "Note.md")

        notes = [
            {
                "path": note_path,
                "title": "Note",
                "type": "resource",
                "scope": "general",
                "summary": "S",
                "tags": '["t"]',
                "related": "[]",
                "project": "",
            }
        ]
        extra_fm = {note_path: {"durability": "durable", "cb_review_after": ""}}
        config = _config(str(vault))

        violations = audit_mod._run_checks(
            notes,
            extra_fm,
            set(),
            config,
            audit_mod._VALID_ENTITY_TYPES,
            using_index=True,
        )

        assert violations["check_4_durability_validity"] == []


# ===========================================================================
# _run_checks — Check 6 (filename characters)
# ===========================================================================


class TestCheck6FilenameCharacters:
    def test_forbidden_chars_flagged(self, tmp_path):
        """Filename containing '#' is flagged by check_6."""
        vault = tmp_path / "vault"
        vault.mkdir()
        # File does not need to exist on disk; check uses the path string
        note_path = str(vault / "C# Feature Note.md")

        notes = [
            {
                "path": note_path,
                "title": "C# Feature Note",
                "type": "resource",
                "scope": "general",
                "summary": "S",
                "tags": '["t"]',
                "related": "[]",
                "project": "",
            }
        ]
        extra_fm = {note_path: {"durability": "durable", "cb_review_after": ""}}
        config = _config(str(vault))

        violations = audit_mod._run_checks(
            notes,
            extra_fm,
            set(),
            config,
            audit_mod._VALID_ENTITY_TYPES,
            using_index=True,
        )

        check6 = violations["check_6_filename_characters"]
        assert len(check6) == 1
        assert "#" in check6[0]["bad_chars"]

    def test_clean_filename_not_flagged(self, tmp_path):
        """Filename without forbidden characters is not flagged by check_6."""
        vault = tmp_path / "vault"
        vault.mkdir()
        note_path = str(vault / "Clean Filename Note.md")

        notes = [
            {
                "path": note_path,
                "title": "Clean Filename Note",
                "type": "resource",
                "scope": "general",
                "summary": "S",
                "tags": '["t"]',
                "related": "[]",
                "project": "",
            }
        ]
        extra_fm = {note_path: {"durability": "durable", "cb_review_after": ""}}
        config = _config(str(vault))

        violations = audit_mod._run_checks(
            notes,
            extra_fm,
            set(),
            config,
            audit_mod._VALID_ENTITY_TYPES,
            using_index=True,
        )

        assert violations["check_6_filename_characters"] == []


# ===========================================================================
# _run_checks — Check 8 (WM review date)
# ===========================================================================


class TestCheck8WorkingMemoryReviewDate:
    def test_wm_note_missing_review_date_flagged(self, tmp_path):
        """Working-memory note with no cb_review_after is flagged by check_8."""
        vault = tmp_path / "vault"
        vault.mkdir()
        note_path = str(vault / "WM Note.md")

        notes = [
            {
                "path": note_path,
                "title": "WM Note",
                "type": "note",
                "scope": "general",
                "summary": "S",
                "tags": '["t"]',
                "related": "[]",
                "project": "",
            }
        ]
        # durability=working-memory, cb_review_after absent
        extra_fm = {note_path: {"durability": "working-memory", "cb_review_after": ""}}
        config = _config(str(vault))

        violations = audit_mod._run_checks(
            notes,
            extra_fm,
            set(),
            config,
            audit_mod._VALID_ENTITY_TYPES,
            using_index=True,
        )

        check8 = violations["check_8_wm_review_date"]
        assert len(check8) == 1
        assert note_path == check8[0]["path"]

    def test_wm_note_with_review_date_not_flagged(self, tmp_path):
        """Working-memory note with cb_review_after set is not flagged by check_8."""
        vault = tmp_path / "vault"
        vault.mkdir()
        note_path = str(vault / "WM Note.md")

        notes = [
            {
                "path": note_path,
                "title": "WM Note",
                "type": "note",
                "scope": "general",
                "summary": "S",
                "tags": '["t"]',
                "related": "[]",
                "project": "",
            }
        ]
        extra_fm = {
            note_path: {"durability": "working-memory", "cb_review_after": "2026-04-26"}
        }
        config = _config(str(vault))

        violations = audit_mod._run_checks(
            notes,
            extra_fm,
            set(),
            config,
            audit_mod._VALID_ENTITY_TYPES,
            using_index=True,
        )

        assert violations["check_8_wm_review_date"] == []


# ===========================================================================
# _run_checks — Check 5 (routing compliance)
# ===========================================================================


class TestCheck5RoutingCompliance:
    def test_project_note_in_wrong_folder_flagged(self, tmp_path):
        """A project-scoped durable note stored outside vault_folder is flagged."""
        vault = tmp_path / "vault"
        wrong_folder = vault / "AI" / "Claude-Sessions"
        wrong_folder.mkdir(parents=True)
        expected_folder = vault / "Projects" / "my-project"
        expected_folder.mkdir(parents=True)

        note = wrong_folder / "Misrouted Note.md"
        _write_md(
            note,
            {
                "type": "insight",
                "scope": "project",
                "durability": "durable",
                "summary": "A summary.",
                "tags": ["test"],
            },
        )

        notes = [
            {
                "path": str(note),
                "title": "Misrouted Note",
                "type": "insight",
                "scope": "project",
                "summary": "A summary.",
                "tags": '["test"]',
                "related": "[]",
                "project": "my-project",
            }
        ]
        extra_fm = {str(note): {"durability": "durable", "cb_review_after": ""}}
        config = _config(
            str(vault),
            vault_folder="Projects/my-project",
            project_name="my-project",
        )
        valid_beat_types = frozenset({"decision", "insight", "problem", "reference"})

        violations = audit_mod._run_checks(
            notes, extra_fm, set(), config, valid_beat_types, using_index=True
        )

        check5 = violations["check_5_routing_compliance"]
        assert len(check5) == 1
        assert "project-scoped note not under vault_folder" in check5[0]["reason"]

    def test_project_note_correctly_placed_not_flagged(self, tmp_path):
        """A project-scoped durable note inside vault_folder is not flagged."""
        vault = tmp_path / "vault"
        project_folder = vault / "Projects" / "my-project"
        project_folder.mkdir(parents=True)

        note = project_folder / "Correct Note.md"
        _write_md(note, {"type": "resource", "scope": "project", "durability": "durable"})

        notes = [
            {
                "path": str(note),
                "title": "Correct Note",
                "type": "resource",
                "scope": "project",
                "summary": "S",
                "tags": '["t"]',
                "related": "[]",
                "project": "my-project",
            }
        ]
        extra_fm = {str(note): {"durability": "durable", "cb_review_after": ""}}
        config = _config(
            str(vault),
            vault_folder="Projects/my-project",
            project_name="my-project",
        )
        valid_types = frozenset({"resource", "note", "project", "archived"})

        violations = audit_mod._run_checks(
            notes, extra_fm, set(), config, valid_types, using_index=True
        )

        assert violations["check_5_routing_compliance"] == []

    def test_wm_note_outside_wm_folder_flagged(self, tmp_path):
        """A working-memory note stored outside working_memory_folder is flagged."""
        vault = tmp_path / "vault"
        wrong_folder = vault / "AI" / "Claude-Sessions"
        wrong_folder.mkdir(parents=True)
        wm_folder = vault / "AI" / "Working Memory"
        wm_folder.mkdir(parents=True)

        note = wrong_folder / "WM Note.md"
        _write_md(note, {"type": "note", "durability": "working-memory"})

        notes = [
            {
                "path": str(note),
                "title": "WM Note",
                "type": "note",
                "scope": "general",
                "summary": "S",
                "tags": '["t"]',
                "related": "[]",
                "project": "",
            }
        ]
        extra_fm = {str(note): {"durability": "working-memory", "cb_review_after": "2026-05-01"}}
        config = _config(str(vault), working_memory_folder="AI/Working Memory")
        valid_types = frozenset({"resource", "note", "project", "archived"})

        violations = audit_mod._run_checks(
            notes, extra_fm, set(), config, valid_types, using_index=True
        )

        check5 = violations["check_5_routing_compliance"]
        assert len(check5) == 1
        assert "working-memory note not under working_memory_folder" in check5[0]["reason"]

    def test_wm_note_correctly_placed_not_flagged(self, tmp_path):
        """A working-memory note inside working_memory_folder is not flagged."""
        vault = tmp_path / "vault"
        wm_folder = vault / "AI" / "Working Memory"
        wm_folder.mkdir(parents=True)

        note = wm_folder / "WM Note.md"
        _write_md(note, {"type": "note", "durability": "working-memory"})

        notes = [
            {
                "path": str(note),
                "title": "WM Note",
                "type": "note",
                "scope": "general",
                "summary": "S",
                "tags": '["t"]',
                "related": "[]",
                "project": "",
            }
        ]
        extra_fm = {str(note): {"durability": "working-memory", "cb_review_after": "2026-05-01"}}
        config = _config(str(vault), working_memory_folder="AI/Working Memory")
        valid_types = frozenset({"resource", "note", "project", "archived"})

        violations = audit_mod._run_checks(
            notes, extra_fm, set(), config, valid_types, using_index=True
        )

        assert violations["check_5_routing_compliance"] == []


# ===========================================================================
# _run_checks — Check 7 (relation integrity)
# ===========================================================================


class TestCheck7RelationIntegrity:
    def test_wikilink_to_nonexistent_title_flagged(self, tmp_path):
        """related JSON array referencing a non-existent title is flagged."""
        vault = tmp_path / "vault"
        vault.mkdir()

        note_path = str(vault / "Source Note.md")
        notes = [
            {
                "path": note_path,
                "title": "Source Note",
                "type": "insight",
                "scope": "general",
                "summary": "S",
                "tags": '["t"]',
                "related": json.dumps(["Ghost Note"]),
                "project": "",
            }
        ]
        extra_fm = {note_path: {"durability": "durable", "cb_review_after": ""}}
        # all_titles does NOT contain "Ghost Note"
        all_titles = {"Source Note"}
        config = _config(str(vault))
        valid_beat_types = frozenset({"decision", "insight", "problem", "reference"})

        violations = audit_mod._run_checks(
            notes, extra_fm, all_titles, config, valid_beat_types, using_index=True
        )

        check7 = violations["check_7_relation_integrity"]
        assert len(check7) == 1
        assert "Ghost Note" in check7[0]["broken_wikilinks"]

    def test_valid_wikilink_not_flagged(self, tmp_path):
        """related JSON array referencing an existing title is not flagged."""
        vault = tmp_path / "vault"
        vault.mkdir()

        note_path = str(vault / "Source Note.md")
        notes = [
            {
                "path": note_path,
                "title": "Source Note",
                "type": "insight",
                "scope": "general",
                "summary": "S",
                "tags": '["t"]',
                "related": json.dumps(["Existing Note"]),
                "project": "",
            }
        ]
        extra_fm = {note_path: {"durability": "durable", "cb_review_after": ""}}
        all_titles = {"Source Note", "Existing Note"}
        config = _config(str(vault))
        valid_beat_types = frozenset({"decision", "insight", "problem", "reference"})

        violations = audit_mod._run_checks(
            notes, extra_fm, all_titles, config, valid_beat_types, using_index=True
        )

        assert violations["check_7_relation_integrity"] == []

    def test_wikilink_format_not_flagged_as_broken(self, tmp_path):
        """related stored as [[Title]] wikilink syntax is resolved to plain title before lookup."""
        vault = tmp_path / "vault"
        vault.mkdir()

        note_path = str(vault / "Source Note.md")
        notes = [
            {
                "path": note_path,
                "title": "Source Note",
                "type": "resource",
                "scope": "general",
                "summary": "S",
                "tags": '["t"]',
                # write_beat() stores related as wikilink format
                "related": json.dumps(["[[Existing Note]]"]),
                "project": "",
            }
        ]
        extra_fm = {note_path: {"durability": "durable", "cb_review_after": ""}}
        # "Existing Note" is in all_titles (plain string, no brackets)
        all_titles = {"Source Note", "Existing Note"}
        config = _config(str(vault))
        valid_beat_types = frozenset({"decision", "insight", "problem", "reference"})

        violations = audit_mod._run_checks(
            notes, extra_fm, all_titles, config, valid_beat_types, using_index=True
        )

        assert violations["check_7_relation_integrity"] == []

    def test_wikilink_format_nonexistent_still_flagged(self, tmp_path):
        """related stored as [[NonExistentTitle]] is still flagged after bracket stripping."""
        vault = tmp_path / "vault"
        vault.mkdir()

        note_path = str(vault / "Source Note.md")
        notes = [
            {
                "path": note_path,
                "title": "Source Note",
                "type": "resource",
                "scope": "general",
                "summary": "S",
                "tags": '["t"]',
                "related": json.dumps(["[[Ghost Note]]"]),
                "project": "",
            }
        ]
        extra_fm = {note_path: {"durability": "durable", "cb_review_after": ""}}
        all_titles = {"Source Note"}
        config = _config(str(vault))
        valid_beat_types = frozenset({"decision", "insight", "problem", "reference"})

        violations = audit_mod._run_checks(
            notes, extra_fm, all_titles, config, valid_beat_types, using_index=True
        )

        check7 = violations["check_7_relation_integrity"]
        assert len(check7) == 1
        assert "Ghost Note" in check7[0]["broken_wikilinks"]

    def test_pipe_alias_wikilink_not_flagged(self, tmp_path):
        """related stored as [[Title|Alias]] resolves to plain 'Title' before lookup."""
        vault = tmp_path / "vault"
        vault.mkdir()

        note_path = str(vault / "Source Note.md")
        notes = [
            {
                "path": note_path,
                "title": "Source Note",
                "type": "resource",
                "scope": "general",
                "summary": "S",
                "tags": '["t"]',
                "related": json.dumps(["[[Existing Note|Display Alias]]"]),
                "project": "",
            }
        ]
        extra_fm = {note_path: {"durability": "durable", "cb_review_after": ""}}
        all_titles = {"Source Note", "Existing Note"}
        config = _config(str(vault))
        valid_beat_types = frozenset({"decision", "insight", "problem", "reference"})

        violations = audit_mod._run_checks(
            notes, extra_fm, all_titles, config, valid_beat_types, using_index=True
        )

        assert violations["check_7_relation_integrity"] == []

    def test_heading_anchor_wikilink_not_flagged(self, tmp_path):
        """related stored as [[Title#Section]] resolves to plain 'Title' before lookup."""
        vault = tmp_path / "vault"
        vault.mkdir()

        note_path = str(vault / "Source Note.md")
        notes = [
            {
                "path": note_path,
                "title": "Source Note",
                "type": "resource",
                "scope": "general",
                "summary": "S",
                "tags": '["t"]',
                "related": json.dumps(["[[Existing Note#Introduction]]"]),
                "project": "",
            }
        ]
        extra_fm = {note_path: {"durability": "durable", "cb_review_after": ""}}
        all_titles = {"Source Note", "Existing Note"}
        config = _config(str(vault))
        valid_beat_types = frozenset({"decision", "insight", "problem", "reference"})

        violations = audit_mod._run_checks(
            notes, extra_fm, all_titles, config, valid_beat_types, using_index=True
        )

        assert violations["check_7_relation_integrity"] == []


# ===========================================================================
# cb_audit tool — ToolError when vault_path missing
# ===========================================================================


class TestCbAuditToolError:
    def test_raises_tool_error_when_vault_path_empty(self):
        """cb_audit raises ToolError when vault_path is not configured."""
        with patch.object(audit_mod, "_load_config", return_value={"vault_path": ""}):
            with pytest.raises(ToolError, match="vault_path is not configured"):
                _cb_audit()()

    def test_raises_tool_error_when_vault_path_absent(self):
        """cb_audit raises ToolError when vault_path key is missing entirely."""
        with patch.object(audit_mod, "_load_config", return_value={}):
            with pytest.raises(ToolError, match="vault_path is not configured"):
                _cb_audit()()


# ===========================================================================
# cb_audit tool — report write
# ===========================================================================


class TestCbAuditReportWrite:
    def test_report_written_with_expected_keys(self, tmp_path):
        """cb_audit writes a JSON report with 'total_notes_scanned' and 'violations_by_check'."""
        vault = tmp_path / "vault"
        vault.mkdir()
        report_path = tmp_path / "audit-report.json"

        # No notes in vault, DB absent — fallback to filesystem (empty scan)
        db_path = str(tmp_path / "nonexistent.db")

        config = _config(str(vault), search_db_path=db_path)

        with (
            patch.object(audit_mod, "_load_config", return_value=config),
            patch(
                "cyberbrain.mcp.tools.audit.audit_report_path", return_value=report_path
            ),
            patch(
                "cyberbrain.extractors.vault.get_valid_beat_types",
                return_value={"decision", "insight", "problem", "reference"},
            ),
        ):
            result = _cb_audit()()

        assert report_path.exists(), "Report JSON was not written"
        report_data = json.loads(report_path.read_text(encoding="utf-8"))

        assert "total_notes_scanned" in report_data
        assert "violations_by_check" in report_data
        assert isinstance(result, str)
        assert "cb_audit Report" in result
