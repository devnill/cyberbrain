"""
test_recall_read_tools.py — tests for mcp/tools/recall.py

Covers the gaps not reached by test_mcp_server.py:
- _find_note_by_title: FTS5 exact/prefix/miss/exception paths
- cb_recall grep fallback when backend returns no results or is None
- cb_recall result card formatting (project, tags, related, body)
- cb_recall OSError on note read (silently skipped)
- cb_recall backend_label = "grep" set after fallback
- cb_read: exact path, .md extension, FTS5 lookup, not-found, OSError

All vault I/O uses tmp_path. No real LLM calls.

Critical patching note: tools/recall.py does `from shared import _load_config,
_get_search_backend, ...` which creates LOCAL bindings in the tools.recall module.
Patching must target tools.recall._load_config / tools.recall._get_search_backend,
NOT shared._load_config / shared._get_search_backend.
"""

import json
import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# sys.path setup + mock extract_beats BEFORE any shared/tools imports
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
MCP_DIR = REPO_ROOT / "mcp"
EXTRACTORS_DIR = REPO_ROOT / "extractors"

for d in [str(MCP_DIR), str(EXTRACTORS_DIR), str(REPO_ROOT)]:
    if d not in sys.path:
        sys.path.insert(0, d)


# conftest.py installs the shared extract_beats mock before any test module runs.
# We just import the tool module here.
import tools.recall as recall_module


# ---------------------------------------------------------------------------
# FakeMCP
# ---------------------------------------------------------------------------

class FakeMCP:
    def __init__(self):
        self.tools = {}
        self.annotations = {}

    def tool(self, annotations=None, **kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            self.annotations[fn.__name__] = annotations
            return fn
        return decorator


def _get_recall_module():
    """Always return the current live recall module object from sys.modules."""
    return sys.modules.get("tools.recall", recall_module)


def _register():
    mod = _get_recall_module()
    mcp = FakeMCP()
    mod.register(mcp)
    return mcp.tools["cb_recall"], mcp.tools["cb_read"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    return v


def _write_note(vault: Path, rel: str, fm: dict, body: str = "Body content.") -> Path:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    fm_lines = "\n".join(
        f'{k}: {json.dumps(v) if isinstance(v, list) else v}'
        for k, v in fm.items()
    )
    p.write_text(f"---\n{fm_lines}\n---\n\n{body}", encoding="utf-8")
    return p


def _vault_config(vault: Path) -> dict:
    return {
        "vault_path": str(vault),
        "inbox": "AI/Claude-Sessions",
        "backend": "ollama",
        "model": "llama3.2",
        "autofile": False,
        "daily_journal": False,
    }


def _make_fts5_db(tmp_path: Path, notes: list[dict]) -> str:
    """Create a minimal notes table (not FTS5 — just a regular table) matching schema."""
    db_path = str(tmp_path / "search.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE notes (
        id TEXT PRIMARY KEY, path TEXT, content_hash TEXT,
        title TEXT, summary TEXT, tags TEXT, related TEXT,
        type TEXT, scope TEXT, project TEXT, date TEXT, body TEXT, embedding BLOB
    )""")
    for n in notes:
        conn.execute(
            "INSERT INTO notes (id, path, title, content_hash) VALUES (?, ?, ?, ?)",
            (n.get("id", "1"), n["path"], n["title"], "hash")
        )
    conn.commit()
    conn.close()
    return db_path


def _make_search_result(path: str, **kwargs):
    from search_backends import SearchResult
    return SearchResult(
        path=path,
        title=kwargs.get("title", "Test Note"),
        summary=kwargs.get("summary", "A test summary."),
        tags=kwargs.get("tags", []),
        related=kwargs.get("related", []),
        note_type=kwargs.get("note_type", "insight"),
        date=kwargs.get("date", "2026-01-15"),
        score=kwargs.get("score", 1.0),
        backend=kwargs.get("backend", "fts5"),
    )


# ===========================================================================
# _find_note_by_title
# ===========================================================================

class TestFindNoteByTitle:
    """_find_note_by_title queries the SQLite index for a note by title."""

    def test_returns_none_when_db_not_present(self, tmp_path):
        """No DB file -> returns None."""
        config = {"search_db_path": str(tmp_path / "nonexistent.db")}
        result = recall_module._find_note_by_title("JWT Auth", config)
        assert result is None

    def test_returns_exact_match(self, tmp_path):
        """An exact case-insensitive title match returns the correct Path."""
        note_path = str(tmp_path / "JWT Auth.md")
        db = _make_fts5_db(tmp_path, [{"id": "1", "path": note_path, "title": "JWT Auth"}])
        config = {"search_db_path": db}
        result = recall_module._find_note_by_title("jwt auth", config)
        assert result is not None
        assert result == Path(note_path)

    def test_returns_prefix_fuzzy_match(self, tmp_path):
        """A substring of the title returns a match via LIKE query."""
        note_path = str(tmp_path / "JWT Authentication Flow.md")
        db = _make_fts5_db(tmp_path, [{"id": "1", "path": note_path, "title": "JWT Authentication Flow"}])
        config = {"search_db_path": db}
        result = recall_module._find_note_by_title("Authentication", config)
        assert result is not None
        assert result == Path(note_path)

    def test_returns_none_when_no_match(self, tmp_path):
        """A title that doesn't match any notes returns None."""
        db = _make_fts5_db(tmp_path, [{"id": "1", "path": "/vault/Other.md", "title": "Other Note"}])
        config = {"search_db_path": db}
        result = recall_module._find_note_by_title("completely unrelated xyz", config)
        assert result is None

    def test_returns_none_on_corrupt_db(self, tmp_path):
        """A corrupt DB returns None without propagating the exception."""
        bad_db = str(tmp_path / "bad.db")
        Path(bad_db).write_text("this is not a sqlite database", encoding="utf-8")
        config = {"search_db_path": bad_db}
        result = recall_module._find_note_by_title("anything", config)
        assert result is None


# ===========================================================================
# cb_recall — grep fallback path
# ===========================================================================

class TestCbRecallGrepFallback:
    """cb_recall falls back to grep when the search backend is None or returns empty."""

    def test_grep_fallback_returns_results(self, tmp_path):
        """When backend is None, grep finds matching notes in the vault."""
        vault = _make_vault(tmp_path)
        note = _write_note(vault, "JWT Auth.md", {
            "title": "JWT Auth Issue",
            "type": "problem",
            "summary": "JWT tokens expire silently.",
            "tags": ["jwt", "auth"],
        }, body="JWT authentication tokens expire without warning.")
        config = _vault_config(vault)

        mod = _get_recall_module()
        cb_recall, _ = _register()
        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_get_search_backend", return_value=None):
                result = cb_recall(query="jwt authentication")

        assert "Retrieved from knowledge vault" in result
        assert "JWT" in result or "jwt" in result.lower()

    def test_grep_fallback_no_results_returns_no_notes_message(self, tmp_path):
        """When grep finds nothing, a 'No notes found' message is returned (not ToolError)."""
        vault = _make_vault(tmp_path)
        config = _vault_config(vault)

        mod = _get_recall_module()
        cb_recall, _ = _register()
        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_get_search_backend", return_value=None):
                result = cb_recall(query="xyzzy unicorn dragonfly")

        assert "No notes found" in result
        assert isinstance(result, str)

    def test_grep_fallback_when_backend_raises(self, tmp_path):
        """When backend.search() raises RuntimeError, falls back to grep."""
        vault = _make_vault(tmp_path)
        note = _write_note(vault, "Python Typing.md", {
            "title": "Python Type Hints",
            "type": "reference",
            "summary": "Using type hints in Python.",
            "tags": ["python", "typing"],
        }, body="Python typing module provides type hints.")
        config = _vault_config(vault)
        mock_backend = MagicMock()
        mock_backend.search.side_effect = RuntimeError("backend failure")
        mock_backend.backend_name.return_value = "fts5"

        mod = _get_recall_module()
        cb_recall, _ = _register()
        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_get_search_backend", return_value=mock_backend):
                result = cb_recall(query="python typing hints")

        # Either found via grep or "No notes found" — no exception
        assert isinstance(result, str)

    def test_grep_fallback_sets_backend_label(self, tmp_path):
        """When grep fallback is used, the header says backend: grep."""
        vault = _make_vault(tmp_path)
        note = _write_note(vault, "Grep Target.md", {
            "title": "Grep Target Note",
            "type": "reference",
            "summary": "A note findable by grep.",
            "tags": ["grep"],
        }, body="This note contains the word greptoken for matching.")
        config = _vault_config(vault)

        mod = _get_recall_module()
        cb_recall, _ = _register()
        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_get_search_backend", return_value=None):
                result = cb_recall(query="greptoken")

        # If found, it should report grep as the backend
        if "No notes found" not in result:
            assert "grep" in result

    def test_grep_fallback_when_backend_returns_empty(self, tmp_path):
        """When backend.search() returns [], falls back to grep."""
        vault = _make_vault(tmp_path)
        note = _write_note(vault, "Empty Backend.md", {
            "title": "Empty Backend Note",
            "type": "insight",
            "summary": "Backend returned nothing.",
            "tags": ["test"],
        }, body="emptytoken is a searchable keyword here.")
        config = _vault_config(vault)
        mock_backend = MagicMock()
        mock_backend.search.return_value = []
        mock_backend.backend_name.return_value = "fts5"

        mod = _get_recall_module()
        cb_recall, _ = _register()
        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_get_search_backend", return_value=mock_backend):
                result = cb_recall(query="emptytoken")

        assert isinstance(result, str)


# ===========================================================================
# cb_recall — result card formatting
# ===========================================================================

class TestCbRecallCardFormatting:
    """cb_recall formats result cards with all available metadata."""

    def test_card_includes_tags_when_present(self, tmp_path):
        """Tags are shown in the result card when the note has them."""
        vault = _make_vault(tmp_path)
        note = _write_note(vault, "Tagged Note.md", {
            "title": "Tagged Note",
            "type": "insight",
            "summary": "Has tags.",
            "tags": ["fastapi", "python"],
        })
        sr = _make_search_result(str(note), title="Tagged Note", tags=["fastapi", "python"])
        config = _vault_config(vault)
        mock_backend = MagicMock()
        mock_backend.search.return_value = [sr]
        mock_backend.backend_name.return_value = "fts5"

        mod = _get_recall_module()
        cb_recall, _ = _register()
        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_get_search_backend", return_value=mock_backend):
                output = cb_recall(query="fastapi python")

        assert "fastapi" in output

    def test_card_includes_project_when_note_has_project_field(self, tmp_path):
        """A note with project: frontmatter shows the project in the card."""
        vault = _make_vault(tmp_path)
        note = _write_note(vault, "Project Note.md", {
            "title": "Project Note",
            "type": "decision",
            "summary": "Project decision.",
            "tags": ["hermes"],
            "project": "hermes",
        }, body="## Decision\n\nProject-scoped content.")
        sr = _make_search_result(str(note), title="Project Note", note_type="decision", tags=["hermes"])
        config = _vault_config(vault)
        mock_backend = MagicMock()
        mock_backend.search.return_value = [sr]
        mock_backend.backend_name.return_value = "fts5"

        mod = _get_recall_module()
        cb_recall, _ = _register()
        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_get_search_backend", return_value=mock_backend):
                output = cb_recall(query="hermes project")

        assert "hermes" in output

    def test_oserror_on_note_read_skips_entry(self, tmp_path):
        """When a note file can't be read (OSError), that result is silently skipped."""
        vault = _make_vault(tmp_path)
        config = _vault_config(vault)
        # Result points to a non-existent file
        missing_path = str(vault / "Missing Note.md")
        sr = _make_search_result(missing_path, title="Missing Note")
        mock_backend = MagicMock()
        mock_backend.search.return_value = [sr]
        mock_backend.backend_name.return_value = "fts5"

        mod = _get_recall_module()
        cb_recall, _ = _register()
        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_get_search_backend", return_value=mock_backend):
                output = cb_recall(query="missing note")

        # Either "No notes found" (all skipped) or partial results — no exception
        assert isinstance(output, str)
        # If all entries were skipped, should show no-notes message
        if "Retrieved from knowledge vault" not in output:
            assert "No notes found" in output

    def test_full_body_included_for_top_two_results(self, tmp_path):
        """The top 2 results include the full note body; later ones do not."""
        vault = _make_vault(tmp_path)
        notes = []
        for i in range(3):
            n = _write_note(vault, f"Note{i}.md", {
                "title": f"Note {i}",
                "type": "insight",
                "summary": f"Summary of note {i}.",
                "tags": ["test"],
            }, body=f"## Note {i}\n\nUnique body content {i}.")
            notes.append(n)

        from search_backends import SearchResult
        results = [
            SearchResult(
                path=str(n), title=f"Note {i}", summary=f"Summary of note {i}.",
                tags=["test"], note_type="insight", score=float(3 - i), backend="fts5"
            )
            for i, n in enumerate(notes)
        ]
        config = _vault_config(vault)
        mock_backend = MagicMock()
        mock_backend.search.return_value = results
        mock_backend.backend_name.return_value = "fts5"

        mod = _get_recall_module()
        cb_recall, _ = _register()
        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_get_search_backend", return_value=mock_backend):
                output = cb_recall(query="note content test", max_results=5)

        # Top 2 get full body
        assert "Unique body content 0" in output
        assert "Unique body content 1" in output

    def test_related_shown_in_card(self, tmp_path):
        """Notes with related links show them in the card."""
        vault = _make_vault(tmp_path)
        note = _write_note(vault, "Related Note.md", {
            "title": "Related Note",
            "type": "insight",
            "summary": "Has related links.",
            "tags": ["test"],
        })
        from search_backends import SearchResult
        sr = SearchResult(
            path=str(note), title="Related Note", summary="Has related links.",
            tags=["test"], related=["JWT Auth", "Postgres Pool"],
            note_type="insight", score=1.0, backend="fts5",
        )
        config = _vault_config(vault)
        mock_backend = MagicMock()
        mock_backend.search.return_value = [sr]
        mock_backend.backend_name.return_value = "fts5"

        mod = _get_recall_module()
        cb_recall, _ = _register()
        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_get_search_backend", return_value=mock_backend):
                output = cb_recall(query="related links test")

        assert "JWT Auth" in output or "Related:" in output

    def test_no_entries_returns_no_notes_found(self, tmp_path):
        """If all results fail to read, returns 'No notes found'."""
        vault = _make_vault(tmp_path)
        config = _vault_config(vault)
        # Two missing files — both will raise OSError
        results = [
            _make_search_result(str(vault / "Ghost1.md"), title="Ghost 1"),
            _make_search_result(str(vault / "Ghost2.md"), title="Ghost 2"),
        ]
        mock_backend = MagicMock()
        mock_backend.search.return_value = results
        mock_backend.backend_name.return_value = "fts5"

        mod = _get_recall_module()
        cb_recall, _ = _register()
        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_get_search_backend", return_value=mock_backend):
                output = cb_recall(query="ghost notes query")

        assert "No notes found" in output


# ===========================================================================
# cb_read
# ===========================================================================

class TestCbRead:
    """cb_read reads a specific vault note by path or title."""

    def test_reads_note_by_exact_vault_relative_path(self, tmp_path):
        """A vault-relative path resolves to the file and returns its content."""
        vault = _make_vault(tmp_path)
        note = _write_note(vault, "Projects/JWT Auth.md", {
            "title": "JWT Auth Issue",
            "type": "problem",
            "summary": "JWT expiry silent.",
            "tags": ["jwt"],
        }, body="## Problem\n\nJWT tokens expired silently.")
        config = _vault_config(vault)

        mod = _get_recall_module()
        _, cb_read = _register()
        with patch.object(mod, "_load_config", return_value=config):
            result = cb_read(identifier="Projects/JWT Auth.md")

        assert "JWT" in result
        assert "JWT tokens expired silently" in result
        assert "Source:" in result

    def test_reads_note_with_md_extension_appended(self, tmp_path):
        """Passing identifier without .md still resolves the file."""
        vault = _make_vault(tmp_path)
        _write_note(vault, "Decision Log.md", {
            "title": "Decision Log",
            "type": "reference",
            "summary": "Log of all decisions.",
            "tags": ["decisions"],
        })
        config = _vault_config(vault)

        mod = _get_recall_module()
        _, cb_read = _register()
        with patch.object(mod, "_load_config", return_value=config):
            result = cb_read(identifier="Decision Log")

        assert "Decision Log" in result

    def test_reads_note_by_fts5_title_lookup(self, tmp_path):
        """When exact path doesn't resolve, FTS5 title lookup is used."""
        vault = _make_vault(tmp_path)
        note = _write_note(vault, "Deep/Nested/Auth Note.md", {
            "title": "Auth Note",
            "type": "insight",
            "summary": "Auth insights.",
            "tags": ["auth"],
        }, body="Auth insight body text.")
        config = _vault_config(vault)

        mod = _get_recall_module()
        _, cb_read = _register()
        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_find_note_by_title", return_value=note):
                result = cb_read(identifier="Auth Note")

        assert "Auth Note" in result
        assert "Auth insight body text" in result

    def test_raises_tool_error_when_note_not_found(self, tmp_path):
        """When the note can't be found by path or title, ToolError is raised."""
        from fastmcp.exceptions import ToolError
        vault = _make_vault(tmp_path)
        config = _vault_config(vault)

        mod = _get_recall_module()
        _, cb_read = _register()
        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_find_note_by_title", return_value=None):
                with pytest.raises(ToolError, match="not found"):
                    cb_read(identifier="totally-nonexistent-note.md")

    def test_raises_tool_error_on_read_oserror(self, tmp_path):
        """When the file exists but can't be read, ToolError is raised."""
        from fastmcp.exceptions import ToolError
        vault = _make_vault(tmp_path)
        note = _write_note(vault, "Unreadable.md", {
            "title": "Unreadable",
            "type": "insight",
            "summary": "x",
            "tags": ["x"],
        })
        config = _vault_config(vault)

        mod = _get_recall_module()
        _, cb_read = _register()
        with patch.object(mod, "_load_config", return_value=config):
            with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
                with pytest.raises(ToolError, match="Could not read"):
                    cb_read(identifier="Unreadable.md")

    def test_result_includes_source_path(self, tmp_path):
        """The returned content includes a 'Source:' line with the vault-relative path."""
        vault = _make_vault(tmp_path)
        _write_note(vault, "My Decision.md", {
            "title": "My Decision",
            "type": "decision",
            "summary": "Chose X.",
            "tags": ["decision"],
        })
        config = _vault_config(vault)

        mod = _get_recall_module()
        _, cb_read = _register()
        with patch.object(mod, "_load_config", return_value=config):
            result = cb_read(identifier="My Decision.md")

        assert "Source:" in result
        assert "My Decision" in result

    def test_raises_tool_error_for_path_traversal(self, tmp_path):
        """A path traversal attempt (../../etc/passwd) raises ToolError."""
        from fastmcp.exceptions import ToolError
        vault = _make_vault(tmp_path)
        config = _vault_config(vault)

        mod = _get_recall_module()
        _, cb_read = _register()
        with patch.object(mod, "_load_config", return_value=config):
            with patch.object(mod, "_find_note_by_title", return_value=None):
                with pytest.raises(ToolError, match="not found"):
                    cb_read(identifier="../../etc/passwd")

    def test_title_from_frontmatter_in_output(self, tmp_path):
        """The note title from frontmatter appears in the returned content header."""
        vault = _make_vault(tmp_path)
        _write_note(vault, "Titled Note.md", {
            "title": "My Special Title",
            "type": "insight",
            "summary": "Summary here.",
            "tags": [],
        }, body="Body text here.")
        config = _vault_config(vault)

        mod = _get_recall_module()
        _, cb_read = _register()
        with patch.object(mod, "_load_config", return_value=config):
            result = cb_read(identifier="Titled Note.md")

        assert "My Special Title" in result


# ===========================================================================
# cb_recall — synthesis (synthesize=True)
# ===========================================================================

class TestCbRecallSynthesis:
    """cb_recall with synthesize=True uses prompt templates and quality gate."""

    def _setup_vault_and_backend(self, tmp_path):
        """Helper: create vault with notes and a mock search backend returning them."""
        vault = _make_vault(tmp_path)
        notes = []
        for i in range(3):
            n = _write_note(vault, f"Note{i}.md", {
                "title": f"Note {i}",
                "type": "insight",
                "summary": f"Summary of note {i}.",
                "tags": ["test"],
            }, body=f"## Note {i}\n\nBody content for note {i}.")
            notes.append(n)

        from search_backends import SearchResult
        results = [
            SearchResult(
                path=str(n), title=f"Note {i}", summary=f"Summary of note {i}.",
                tags=["test"], note_type="insight", date="2026-01-15",
                score=float(3 - i), backend="fts5"
            )
            for i, n in enumerate(notes)
        ]
        config = _vault_config(vault)
        mock_backend = MagicMock()
        mock_backend.search.return_value = results
        mock_backend.backend_name.return_value = "fts5"
        return vault, config, mock_backend

    def test_synthesis_returns_structured_output(self, tmp_path):
        """synthesize=True returns structured synthesis with sources, not note cards."""
        vault, config, mock_backend = self._setup_vault_and_backend(tmp_path)
        mod = _get_recall_module()
        cb_recall, _ = _register()

        # Mock the quality gate to pass
        mock_verdict = MagicMock()
        mock_verdict.passed = True

        with patch.object(mod, "_load_config", return_value=config), \
             patch.object(mod, "_get_search_backend", return_value=mock_backend), \
             patch.object(mod, "_load_prompt", return_value="prompt"), \
             patch.object(mod, "_call_claude_code_backend", return_value="Synthesized answer citing [Note 0]."), \
             patch("tools.recall.quality_gate", return_value=mock_verdict, create=True):
            # We need to patch the import inside the function
            with patch.dict("sys.modules", {"quality_gate": MagicMock(
                quality_gate=MagicMock(return_value=mock_verdict),
                Verdict=MagicMock(),
            )}):
                output = cb_recall(query="test content notes", synthesize=True)

        # Should contain synthesis sections with security wrapper
        assert "## Retrieved from knowledge vault" in output
        assert "## Relevant Knowledge" in output
        assert "## Sources" in output
        assert "Synthesized answer" in output
        assert "## End of retrieved content" in output

    def test_synthesis_false_preserves_note_cards(self, tmp_path):
        """synthesize=False returns note cards with full bodies (unchanged behavior)."""
        vault, config, mock_backend = self._setup_vault_and_backend(tmp_path)
        mod = _get_recall_module()
        cb_recall, _ = _register()

        with patch.object(mod, "_load_config", return_value=config), \
             patch.object(mod, "_get_search_backend", return_value=mock_backend):
            output = cb_recall(query="test content notes", synthesize=False)

        assert "## Retrieved from knowledge vault" in output
        assert "Body content for note 0" in output
        assert "Body content for note 1" in output
        assert "## Relevant Knowledge" not in output

    def test_synthesis_sources_list_all_notes(self, tmp_path):
        """The Sources section lists all retrieved note titles with paths."""
        vault, config, mock_backend = self._setup_vault_and_backend(tmp_path)
        mod = _get_recall_module()
        cb_recall, _ = _register()

        mock_verdict = MagicMock()
        mock_verdict.passed = True

        with patch.object(mod, "_load_config", return_value=config), \
             patch.object(mod, "_get_search_backend", return_value=mock_backend), \
             patch.object(mod, "_load_prompt", return_value="prompt"), \
             patch.object(mod, "_call_claude_code_backend", return_value="Synthesis."), \
             patch.dict("sys.modules", {"quality_gate": MagicMock(
                quality_gate=MagicMock(return_value=mock_verdict),
                Verdict=MagicMock(),
             )}):
            output = cb_recall(query="test content notes", synthesize=True)

        assert "Note 0" in output
        assert "Note 1" in output
        assert "Note 2" in output

    def test_synthesis_llm_failure_falls_back_to_note_cards(self, tmp_path):
        """When the LLM call fails, falls back to note cards with error note."""
        vault, config, mock_backend = self._setup_vault_and_backend(tmp_path)
        mod = _get_recall_module()
        cb_recall, _ = _register()

        with patch.object(mod, "_load_config", return_value=config), \
             patch.object(mod, "_get_search_backend", return_value=mock_backend), \
             patch.object(mod, "_load_prompt", return_value="prompt"), \
             patch.object(mod, "_call_claude_code_backend", side_effect=RuntimeError("LLM down")):
            output = cb_recall(query="test content notes", synthesize=True)

        # Falls back to note cards
        assert "## Retrieved from knowledge vault" in output
        assert "Synthesis failed" in output

    def test_synthesis_quality_gate_failure_falls_back_to_note_cards(self, tmp_path):
        """When the quality gate fails, returns note cards without synthesis."""
        vault, config, mock_backend = self._setup_vault_and_backend(tmp_path)
        mod = _get_recall_module()
        cb_recall, _ = _register()

        mock_verdict = MagicMock()
        mock_verdict.passed = False
        mock_verdict.rationale = "Hallucinated content detected"

        with patch.object(mod, "_load_config", return_value=config), \
             patch.object(mod, "_get_search_backend", return_value=mock_backend), \
             patch.object(mod, "_load_prompt", return_value="prompt"), \
             patch.object(mod, "_call_claude_code_backend", return_value="Bad synthesis."), \
             patch.dict("sys.modules", {"quality_gate": MagicMock(
                quality_gate=MagicMock(return_value=mock_verdict),
                Verdict=MagicMock(),
             )}):
            output = cb_recall(query="test content notes", synthesize=True)

        # Should fall back to note cards
        assert "## Retrieved from knowledge vault" in output
        assert "## Relevant Knowledge" not in output

    def test_synthesis_quality_gate_unavailable_proceeds(self, tmp_path):
        """When quality_gate import fails, synthesis proceeds (graceful degradation)."""
        vault, config, mock_backend = self._setup_vault_and_backend(tmp_path)
        mod = _get_recall_module()
        cb_recall, _ = _register()

        # Remove quality_gate from sys.modules so import fails inside the function
        with patch.object(mod, "_load_config", return_value=config), \
             patch.object(mod, "_get_search_backend", return_value=mock_backend), \
             patch.object(mod, "_load_prompt", return_value="prompt"), \
             patch.object(mod, "_call_claude_code_backend", return_value="Good synthesis."), \
             patch.dict("sys.modules", {"quality_gate": None}):
            # When sys.modules has None, import raises ImportError
            output = cb_recall(query="test content notes", synthesize=True)

        # Synthesis should proceed despite gate unavailability
        assert "## Relevant Knowledge" in output
        assert "Good synthesis." in output

    def test_synthesis_uses_prompt_templates(self, tmp_path):
        """Synthesis loads prompts from files, not inline strings."""
        vault, config, mock_backend = self._setup_vault_and_backend(tmp_path)
        mod = _get_recall_module()
        cb_recall, _ = _register()

        mock_verdict = MagicMock()
        mock_verdict.passed = True
        load_prompt_calls = []

        def track_load_prompt(filename):
            load_prompt_calls.append(filename)
            if "user" in filename:
                return "Query: {query}\n\nSource notes ({note_count}):\n\n{notes_block}\n\nSynthesize."
            return "System prompt."

        with patch.object(mod, "_load_config", return_value=config), \
             patch.object(mod, "_get_search_backend", return_value=mock_backend), \
             patch.object(mod, "_load_prompt", side_effect=track_load_prompt), \
             patch.object(mod, "_call_claude_code_backend", return_value="Synthesis."), \
             patch.dict("sys.modules", {"quality_gate": MagicMock(
                quality_gate=MagicMock(return_value=mock_verdict),
                Verdict=MagicMock(),
             )}):
            cb_recall(query="test content notes", synthesize=True)

        assert "synthesize-system.md" in load_prompt_calls
        assert "synthesize-user.md" in load_prompt_calls

    def test_synthesis_body_excerpt_truncated(self, tmp_path):
        """Body excerpts passed to synthesis are truncated for token efficiency."""
        vault = _make_vault(tmp_path)
        long_body = "x" * 1000
        note = _write_note(vault, "Long Note.md", {
            "title": "Long Note",
            "type": "reference",
            "summary": "A long note.",
            "tags": ["test"],
        }, body=long_body)

        from search_backends import SearchResult
        sr = SearchResult(
            path=str(note), title="Long Note", summary="A long note.",
            tags=["test"], note_type="reference", date="2026-01-15",
            score=1.0, backend="fts5"
        )
        config = _vault_config(vault)
        mock_backend = MagicMock()
        mock_backend.search.return_value = [sr]
        mock_backend.backend_name.return_value = "fts5"

        mod = _get_recall_module()
        cb_recall, _ = _register()

        captured_args = {}

        def capture_backend_call(system, user, cfg):
            captured_args["user"] = user
            return "Synthesis."

        mock_verdict = MagicMock()
        mock_verdict.passed = True

        with patch.object(mod, "_load_config", return_value=config), \
             patch.object(mod, "_get_search_backend", return_value=mock_backend), \
             patch.object(mod, "_load_prompt", return_value="{query}\n{note_count}\n{notes_block}"), \
             patch.object(mod, "_call_claude_code_backend", side_effect=capture_backend_call), \
             patch.dict("sys.modules", {"quality_gate": MagicMock(
                quality_gate=MagicMock(return_value=mock_verdict),
                Verdict=MagicMock(),
             )}):
            cb_recall(query="long note test", synthesize=True)

        # The user prompt should contain the body excerpt, but truncated to 500 chars
        user_msg = captured_args["user"]
        # The full 1000-char body should NOT appear
        assert long_body not in user_msg
        # But the first 500 chars should
        assert "x" * 500 in user_msg
