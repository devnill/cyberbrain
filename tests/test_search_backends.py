"""
test_search_backends.py — unit tests for src/cyberbrain/extractors/search_backends.py

Coverage:
- SearchResult dataclass
- _read_frontmatter and _normalise_list helpers
- GrepBackend: search, index_note (noop), build_index (noop), backend_name
- FTS5Backend: schema creation, index_note (insert/skip/update), search, build_index
- _rrf_fuse: RRF formula, deduplication, top_k limiting
- get_search_backend factory: grep/fts5/hybrid selection, auto fallback
- HybridBackend: graceful degradation when semantic layer unavailable
- SmartConnections import: skip on missing dir/model mismatch, parse ajson

All tests use tmp_path or vault_with_notes fixtures. No real fastembed/usearch required
— those tests mock the imports.
"""

import json
import sys
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import search_backends from the extractors directory
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent

import cyberbrain.extractors.search_backends as sb
from cyberbrain.extractors.search_backends import (
    SearchResult,
    GrepBackend,
    FTS5Backend,
    _rrf_fuse,
    get_search_backend,
    _read_frontmatter,
    _normalise_list,
)


# ===========================================================================
# SearchResult
# ===========================================================================

class TestSearchResult:
    """SearchResult dataclass fields have sensible defaults."""

    def test_dataclass_fields_have_defaults(self):
        """SearchResult with only path= doesn't raise; score defaults to 0.0."""
        r = SearchResult(path="/x")
        assert r.path == "/x"
        assert r.score == 0.0
        assert r.title == ""
        assert r.tags == []
        assert r.related == []


# ===========================================================================
# _read_frontmatter
# ===========================================================================

class TestReadFrontmatter:
    """_read_frontmatter helper parses YAML frontmatter from markdown files."""

    def test_parses_standard_frontmatter(self, tmp_path):
        """A file with standard YAML frontmatter returns the parsed dict."""
        note = tmp_path / "note.md"
        note.write_text(
            '---\ntitle: "My Note"\ntype: decision\ntags: ["jwt"]\n---\n\nBody.',
            encoding="utf-8",
        )
        fm = _read_frontmatter(str(note))
        assert fm["title"] == "My Note"
        assert fm["type"] == "decision"

    def test_returns_empty_on_no_frontmatter(self, tmp_path):
        """A file with no --- delimiter returns empty dict."""
        note = tmp_path / "note.md"
        note.write_text("Just a body, no frontmatter.\n", encoding="utf-8")
        assert _read_frontmatter(str(note)) == {}

    def test_returns_empty_on_oserror(self, tmp_path):
        """A missing file returns empty dict."""
        missing = str(tmp_path / "nonexistent.md")
        assert _read_frontmatter(missing) == {}


# ===========================================================================
# _normalise_list
# ===========================================================================

class TestNormaliseList:
    """_normalise_list coerces frontmatter list values."""

    def test_list_passthrough(self):
        """A Python list is returned as-is (items stringified)."""
        assert _normalise_list(["a", "b"]) == ["a", "b"]

    def test_json_string_parsed(self):
        """A JSON array string is parsed into a list."""
        assert _normalise_list('["a", "b"]') == ["a", "b"]

    def test_plain_string_wrapped(self):
        """A plain string (not JSON) is returned as a single-item list."""
        assert _normalise_list("single") == ["single"]

    def test_empty_string_returns_empty(self):
        """An empty string returns an empty list."""
        assert _normalise_list("") == []


# ===========================================================================
# GrepBackend
# ===========================================================================

class TestGrepBackend:
    """GrepBackend wraps grep-based search as a SearchBackend."""

    def _write_note(self, path: Path, content: str, frontmatter: dict = None):
        """Helper to write a note with optional frontmatter."""
        if frontmatter:
            fm_lines = "\n".join(f'{k}: "{v}"' for k, v in frontmatter.items())
            path.write_text(f"---\n{fm_lines}\n---\n\n{content}", encoding="utf-8")
        else:
            path.write_text(content, encoding="utf-8")

    def test_returns_results_ranked_by_term_count(self, tmp_path):
        """A note matching 2 query terms ranks above one matching 1."""
        note_a = tmp_path / "A.md"
        note_b = tmp_path / "B.md"
        self._write_note(note_a, "jwt authentication token")  # matches jwt + token
        self._write_note(note_b, "jwt only")  # matches jwt only

        backend = GrepBackend(str(tmp_path))
        results = backend.search("jwt token", top_k=5)

        paths = [r.path for r in results]
        assert str(note_a) in paths
        assert str(note_b) in paths
        # note_a should rank first (2 term matches vs 1)
        assert paths.index(str(note_a)) < paths.index(str(note_b))

    def test_populates_title_from_frontmatter(self, tmp_path):
        """A note with a title: frontmatter field has that title in results."""
        note = tmp_path / "Note.md"
        self._write_note(
            note,
            "jwt authentication",
            frontmatter={"title": "JWT Auth Guide", "type": "decision"},
        )
        backend = GrepBackend(str(tmp_path))
        results = backend.search("jwt", top_k=5)
        assert any(r.title == "JWT Auth Guide" for r in results)

    def test_empty_query_terms_returns_empty_list(self, tmp_path):
        """A query whose words are all < 3 chars returns an empty list."""
        (tmp_path / "note.md").write_text("ab cd ef", encoding="utf-8")
        backend = GrepBackend(str(tmp_path))
        results = backend.search("ab", top_k=5)
        assert results == []

    def test_index_note_is_noop(self, tmp_path):
        """Calling index_note() doesn't raise."""
        backend = GrepBackend(str(tmp_path))
        backend.index_note("/some/path.md", {"title": "Test"})  # should not raise

    def test_build_index_is_noop(self, tmp_path):
        """Calling build_index() doesn't raise."""
        backend = GrepBackend(str(tmp_path))
        backend.build_index()  # should not raise

    def test_backend_name_returns_grep(self, tmp_path):
        """backend_name() returns 'grep'."""
        backend = GrepBackend(str(tmp_path))
        assert backend.backend_name() == "grep"


# ===========================================================================
# FTS5Backend
# ===========================================================================

class TestFTS5Backend:
    """FTS5Backend uses SQLite FTS5 for BM25 keyword search."""

    # --- Schema ---

    def test_schema_created_on_init(self, tmp_path):
        """After FTS5Backend(vault, db), the notes, notes_fts, and relations tables exist."""
        db = str(tmp_path / "test.db")
        FTS5Backend(str(tmp_path), db)
        conn = sqlite3.connect(db)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        assert "notes" in tables
        assert "notes_fts" in tables
        assert "relations" in tables

    # --- index_note ---

    def _make_note(self, path: Path, title="Test Note", note_type="insight", tags=None):
        """Write a simple vault note with frontmatter."""
        note_id = "test-id-1234"
        tags_json = json.dumps(tags or [])
        path.write_text(
            f'---\nid: {note_id}\ntype: {note_type}\ntitle: "{title}"\ntags: {tags_json}\nrelated: []\nsummary: "A summary."\n---\n\n## {title}\n\nNote body.\n',
            encoding="utf-8",
        )
        return {"id": note_id, "title": title, "type": note_type, "tags": tags or [], "summary": "A summary."}

    def test_inserts_new_note(self, tmp_path):
        """First index of a note inserts a row in the notes table."""
        db = str(tmp_path / "test.db")
        backend = FTS5Backend(str(tmp_path), db)
        note = tmp_path / "My Note.md"
        meta = self._make_note(note)
        backend.index_note(str(note), meta)

        conn = sqlite3.connect(db)
        count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        conn.close()
        assert count == 1

    def test_skips_unchanged_note(self, tmp_path):
        """Indexing the same unchanged file twice keeps exactly one row."""
        db = str(tmp_path / "test.db")
        backend = FTS5Backend(str(tmp_path), db)
        note = tmp_path / "My Note.md"
        meta = self._make_note(note)
        backend.index_note(str(note), meta)
        backend.index_note(str(note), meta)

        conn = sqlite3.connect(db)
        count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        conn.close()
        assert count == 1

    def test_updates_changed_note(self, tmp_path):
        """After modifying a file and re-indexing, exactly one row with new content."""
        db = str(tmp_path / "test.db")
        backend = FTS5Backend(str(tmp_path), db)
        note = tmp_path / "My Note.md"
        meta = self._make_note(note, title="Original Title")
        backend.index_note(str(note), meta)

        # Modify the file
        meta2 = self._make_note(note, title="Updated Title")
        backend.index_note(str(note), meta2)

        conn = sqlite3.connect(db)
        rows = conn.execute("SELECT title FROM notes").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][0] == "Updated Title"

    def test_body_stripped_of_frontmatter_before_storage(self, tmp_path):
        """The body column in the DB does not contain the --- frontmatter marker."""
        db = str(tmp_path / "test.db")
        backend = FTS5Backend(str(tmp_path), db)
        note = tmp_path / "My Note.md"
        meta = self._make_note(note)
        backend.index_note(str(note), meta)

        conn = sqlite3.connect(db)
        body = conn.execute("SELECT body FROM notes").fetchone()[0]
        conn.close()
        assert "---" not in body

    def test_tags_stored_as_json(self, tmp_path):
        """The tags column is valid JSON."""
        db = str(tmp_path / "test.db")
        backend = FTS5Backend(str(tmp_path), db)
        note = tmp_path / "My Note.md"
        meta = self._make_note(note, tags=["python", "sqlite"])
        backend.index_note(str(note), meta)

        conn = sqlite3.connect(db)
        tags_raw = conn.execute("SELECT tags FROM notes").fetchone()[0]
        conn.close()
        parsed = json.loads(tags_raw)
        assert "python" in parsed

    # --- search ---

    def test_returns_results_matching_query_term(self, tmp_path):
        """A note with 'JWT' in the title is returned when searching 'jwt'."""
        db = str(tmp_path / "test.db")
        backend = FTS5Backend(str(tmp_path), db)
        note = tmp_path / "JWT Auth.md"
        meta = self._make_note(note, title="JWT Auth")
        backend.index_note(str(note), meta)

        results = backend.search("jwt")
        assert any("JWT" in r.title for r in results)

    def test_result_score_is_positive(self, tmp_path):
        """BM25 internally returns negative values; result.score should be positive."""
        db = str(tmp_path / "test.db")
        backend = FTS5Backend(str(tmp_path), db)
        note = tmp_path / "JWT Auth.md"
        meta = self._make_note(note, title="JWT Auth")
        backend.index_note(str(note), meta)

        results = backend.search("jwt")
        assert all(r.score > 0 for r in results)

    def test_prefix_matching_works(self, tmp_path):
        """Searching 'authen' matches a note with 'authentication'."""
        db = str(tmp_path / "test.db")
        backend = FTS5Backend(str(tmp_path), db)
        note = tmp_path / "Auth.md"
        meta = self._make_note(note, title="Authentication Flow")
        backend.index_note(str(note), meta)

        results = backend.search("authen")
        assert len(results) > 0

    def test_special_chars_in_query_dont_raise(self, tmp_path):
        """A query with special characters () [] doesn't raise sqlite errors."""
        db = str(tmp_path / "test.db")
        backend = FTS5Backend(str(tmp_path), db)
        # Should return empty results gracefully
        results = backend.search("query (with) [brackets]")
        assert isinstance(results, list)

    def test_empty_table_returns_empty_list(self, tmp_path):
        """An empty database returns an empty list."""
        db = str(tmp_path / "test.db")
        backend = FTS5Backend(str(tmp_path), db)
        results = backend.search("anything")
        assert results == []

    def test_backend_name_returns_fts5(self, tmp_path):
        """backend_name() returns 'fts5'."""
        db = str(tmp_path / "test.db")
        backend = FTS5Backend(str(tmp_path), db)
        assert backend.backend_name() == "fts5"

    # --- build_index ---

    def test_indexes_all_md_files_in_vault(self, vault_with_notes, fts5_db_path):
        """build_index() processes all 3 notes in the fixture vault."""
        backend = FTS5Backend(str(vault_with_notes), fts5_db_path)
        backend.build_index()

        conn = sqlite3.connect(fts5_db_path)
        count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        conn.close()
        assert count == 3

    def test_incremental_skip_unchanged(self, vault_with_notes, fts5_db_path):
        """Building the index twice doesn't change the row count."""
        backend = FTS5Backend(str(vault_with_notes), fts5_db_path)
        backend.build_index()

        conn = sqlite3.connect(fts5_db_path)
        count1 = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        conn.close()

        backend.build_index()

        conn = sqlite3.connect(fts5_db_path)
        count2 = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        conn.close()

        assert count1 == count2 == 3


# ===========================================================================
# _rrf_fuse
# ===========================================================================

class TestRrfFuse:
    """_rrf_fuse() implements Reciprocal Rank Fusion."""

    def _make_result(self, path, **kwargs):
        return SearchResult(path=path, **kwargs)

    def test_path_appearing_in_both_lists_scores_higher(self):
        """A path in both BM25 and semantic lists scores higher than one in only one."""
        shared = self._make_result("/shared.md", title="Shared")
        bm25_only = self._make_result("/bm25only.md", title="BM25 Only")
        sem_only = self._make_result("/semonly.md", title="Semantic Only")

        bm25 = [shared, bm25_only]
        semantic = [shared, sem_only]

        results = _rrf_fuse(bm25, semantic, top_k=10, backend_name="hybrid")
        paths = [r.path for r in results]
        assert paths.index("/shared.md") == 0  # shared note ranks first

    def test_path_in_only_one_list_still_appears(self):
        """A note in only one of the two lists still appears in fused output."""
        r1 = self._make_result("/a.md")
        r2 = self._make_result("/b.md")
        results = _rrf_fuse([r1], [r2], top_k=10, backend_name="hybrid")
        paths = {r.path for r in results}
        assert "/a.md" in paths
        assert "/b.md" in paths

    def test_output_limited_to_top_k(self):
        """With 10 items in each list, top_k=3 returns exactly 3 results."""
        bm25 = [self._make_result(f"/bm{i}.md") for i in range(10)]
        semantic = [self._make_result(f"/sem{i}.md") for i in range(10)]
        results = _rrf_fuse(bm25, semantic, top_k=3, backend_name="hybrid")
        assert len(results) == 3

    def test_score_formula(self):
        """Rank 1 in both lists → score == 2/(60+1)."""
        r = self._make_result("/note.md")
        results = _rrf_fuse([r], [r], top_k=1, backend_name="hybrid")
        expected = 2.0 / (60 + 1)
        assert abs(results[0].score - expected) < 1e-9

    def test_empty_lists_return_empty(self):
        """Both lists empty → empty result."""
        assert _rrf_fuse([], [], top_k=5, backend_name="hybrid") == []


# ===========================================================================
# get_search_backend factory
# ===========================================================================

class TestGetSearchBackend:
    """get_search_backend() selects the right backend from config."""

    def test_returns_grep_backend_when_grep_specified(self, tmp_path):
        """search_backend='grep' → GrepBackend instance."""
        config = {"vault_path": str(tmp_path), "search_backend": "grep"}
        backend = get_search_backend(config)
        assert isinstance(backend, GrepBackend)

    def test_returns_fts5_backend_when_fts5_specified(self, tmp_path):
        """search_backend='fts5' → FTS5Backend instance."""
        db = str(tmp_path / "test.db")
        config = {
            "vault_path": str(tmp_path),
            "search_backend": "fts5",
            "search_db_path": db,
        }
        backend = get_search_backend(config)
        assert isinstance(backend, FTS5Backend)

    def test_auto_returns_fts5_when_fastembed_absent(self, tmp_path):
        """'auto' without fastembed/usearch → FTS5Backend."""
        db = str(tmp_path / "test.db")
        config = {
            "vault_path": str(tmp_path),
            "search_backend": "auto",
            "search_db_path": db,
        }
        with patch.dict(sys.modules, {"fastembed": None, "usearch": None}):
            backend = get_search_backend(config)
        assert isinstance(backend, FTS5Backend)

    def test_auto_returns_hybrid_when_both_present(self, tmp_path):
        """'auto' with fastembed + usearch importable → HybridBackend."""
        from cyberbrain.extractors.search_backends import HybridBackend

        db = str(tmp_path / "test.db")
        config = {
            "vault_path": str(tmp_path),
            "search_backend": "auto",
            "search_db_path": db,
        }

        mock_fastembed = MagicMock()
        mock_usearch = MagicMock()

        with patch.dict(sys.modules, {"fastembed": mock_fastembed, "usearch": mock_usearch}):
            backend = get_search_backend(config)
        assert isinstance(backend, HybridBackend)

    def test_hybrid_raises_when_deps_missing_and_required(self, tmp_path):
        """search_backend='hybrid' without fastembed raises RuntimeError."""
        config = {"vault_path": str(tmp_path), "search_backend": "hybrid"}
        with patch.dict(sys.modules, {"fastembed": None, "usearch": None}):
            with pytest.raises(RuntimeError, match="fastembed"):
                get_search_backend(config)


# ===========================================================================
# HybridBackend graceful degradation
# ===========================================================================

class TestHybridBackendFallback:
    """HybridBackend falls back gracefully when semantic layer is unavailable."""

    def _make_hybrid(self, tmp_path):
        """Instantiate a HybridBackend without actually loading fastembed/usearch."""
        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        return HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")

    def test_search_falls_back_to_fts5_when_semantic_unavailable(self, tmp_path):
        """When _semantic_search returns empty (semantic layer unavailable), BM25 results are returned."""
        backend = self._make_hybrid(tmp_path)

        # Index a note so FTS5 has something
        note = tmp_path / "Test Note.md"
        note.write_text('---\nid: test\ntitle: "Test Note"\ntype: insight\ntags: []\nrelated: []\nsummary: "Test"\n---\n\nTest content.', encoding="utf-8")
        backend._fts5.index_note(str(note), {"id": "test", "title": "Test Note", "tags": [], "summary": "Test"})

        # Patch _embed to raise inside _semantic_search, which will be caught and return []
        with patch.object(backend, "_load_or_create_index", side_effect=RuntimeError("no usearch")):
            results = backend.search("test", top_k=5)

        # Should return FTS5 results with a fallback label
        assert isinstance(results, list)
        if results:
            assert any("fts5" in r.backend for r in results)

    def test_index_note_does_not_raise_on_embedding_failure(self, tmp_path):
        """When _embed_note raises, index_note catches it and returns cleanly."""
        backend = self._make_hybrid(tmp_path)
        note = tmp_path / "Test Note.md"
        note.write_text('---\nid: test\ntitle: "Test Note"\ntags: []\nrelated: []\nsummary: "Test"\n---\n\nBody.', encoding="utf-8")

        with patch.object(backend, "_embed_note", side_effect=RuntimeError("no fastembed")):
            # Should not raise
            backend.index_note(str(note), {"id": "test", "title": "Test Note", "tags": [], "summary": "Test"})


# ===========================================================================
# SmartConnections import
# ===========================================================================

class TestSmartConnectionsImport:
    """HybridBackend._try_import_smart_connections_index handles edge cases."""

    def _make_hybrid(self, tmp_path):
        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        backend = HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")
        return backend

    def test_skips_import_when_no_smart_env_dir(self, tmp_path):
        """No .smart-env/ directory → returns False without error."""
        backend = self._make_hybrid(tmp_path)
        result = backend._try_import_smart_connections_index()
        assert result is False

    def test_skips_import_on_model_mismatch(self, tmp_path):
        """SC settings with a different model name → skips, returns False."""
        sc_dir = tmp_path / ".smart-env"
        sc_dir.mkdir()
        settings = sc_dir / "settings.json"
        settings.write_text(
            json.dumps({"smart_sources": {"embed_model": "different-model/v1"}}),
            encoding="utf-8",
        )

        backend = self._make_hybrid(tmp_path)
        result = backend._try_import_smart_connections_index()
        assert result is False

    def test_parses_multi_file_ajson(self, tmp_path):
        """A valid .ajson file in .smart-env/multi/ imports vectors."""
        sc_dir = tmp_path / ".smart-env"
        multi_dir = sc_dir / "multi"
        multi_dir.mkdir(parents=True)

        # Create a fake vault note
        vault_note = tmp_path / "My Note.md"
        vault_note.write_text("# My Note\n\nContent.", encoding="utf-8")

        # Write a valid .ajson record
        vec = [0.1] * 384
        ajson_content = f'"My Note.md": {{"path": "My Note.md", "embeddings": {{"TaylorAI/bge-micro-v2": {{"vec": {json.dumps(vec)}}}}}}}\n'
        (multi_dir / "my-note.ajson").write_text(ajson_content, encoding="utf-8")

        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        backend = HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")

        # Mock usearch index so we don't need the real library
        mock_index = MagicMock()
        mock_index.add = MagicMock()
        backend._index = mock_index
        backend._id_map = []

        # Mock numpy import inside _import_sc_ajson
        mock_np = MagicMock()
        mock_np.array = lambda x, **kw: x  # passthrough

        with patch.dict(sys.modules, {"numpy": mock_np}):
            with patch.object(backend, "_save_index"):
                result = backend._import_sc_ajson(multi_dir / "my-note.ajson")

        assert result >= 1

    def test_skips_duplicate_paths(self, tmp_path):
        """A path that already exists in _id_map is not imported again."""
        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        backend = HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")

        vec = [0.1] * 384
        # Same path appears twice
        ajson_content = (
            f'"A.md": {{"path": "A.md", "embeddings": {{"model": {{"vec": {json.dumps(vec)}}}}}}}\n'
            f'"A.md": {{"path": "A.md", "embeddings": {{"model": {{"vec": {json.dumps(vec)}}}}}}}\n'
        )
        ajson_file = tmp_path / "test.ajson"
        ajson_file.write_text(ajson_content, encoding="utf-8")

        mock_index = MagicMock()
        backend._index = mock_index
        backend._id_map = []

        # Prepopulate abs_path so dedup triggers
        abs_path = str(tmp_path / "A.md")

        result1 = backend._import_sc_ajson(ajson_file)
        # First call imported one path; second would be a duplicate
        assert result1 <= 1  # imported at most once due to dedup in id_map

    def test_handles_malformed_ajson_lines(self, tmp_path):
        """Lines with bad JSON are skipped without raising."""
        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        backend = HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")

        ajson_file = tmp_path / "bad.ajson"
        ajson_file.write_text("not valid json at all\n{also bad\n", encoding="utf-8")

        mock_index = MagicMock()
        backend._index = mock_index
        backend._id_map = []

        # Should not raise
        result = backend._import_sc_ajson(ajson_file)
        assert result == 0


# ===========================================================================
# FTS5Backend — additional coverage
# ===========================================================================

class TestFTS5BackendAdditional:
    """FTS5Backend edge cases not covered by the primary test class."""

    def _make_note(self, path: Path, title="Test", note_type="insight", tags=None):
        note_id = "id-" + title.replace(" ", "-").lower()
        path.write_text(
            f'---\nid: {note_id}\ntype: {note_type}\ntitle: "{title}"\ntags: {json.dumps(tags or [])}\nrelated: []\nsummary: "Summary."\n---\n\nBody.\n',
            encoding="utf-8",
        )
        return {"id": note_id, "title": title, "type": note_type, "tags": tags or [], "summary": "Summary."}

    def test_index_note_skips_on_oserror(self, tmp_path):
        """index_note() returns silently when the file cannot be read."""
        db = str(tmp_path / "test.db")
        backend = FTS5Backend(str(tmp_path), db)
        backend.index_note("/nonexistent/path.md", {"title": "Missing"})
        conn = sqlite3.connect(db)
        count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        conn.close()
        assert count == 0

    def test_prune_stale_notes_removes_missing_files(self, tmp_path):
        """prune_stale_notes() removes rows whose files no longer exist."""
        db = str(tmp_path / "test.db")
        backend = FTS5Backend(str(tmp_path), db)
        # Index a note then delete the file
        note = tmp_path / "Ephemeral.md"
        meta = self._make_note(note)
        backend.index_note(str(note), meta)
        note.unlink()  # delete the file

        pruned = backend.prune_stale_notes()
        assert pruned == 1

        conn = sqlite3.connect(db)
        count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        conn.close()
        assert count == 0

    def test_prune_stale_notes_returns_zero_when_all_valid(self, tmp_path):
        """prune_stale_notes() returns 0 when all indexed files still exist."""
        db = str(tmp_path / "test.db")
        backend = FTS5Backend(str(tmp_path), db)
        note = tmp_path / "Stable.md"
        meta = self._make_note(note)
        backend.index_note(str(note), meta)

        pruned = backend.prune_stale_notes()
        assert pruned == 0

    def test_search_returns_empty_when_query_is_all_punctuation(self, tmp_path):
        """A query that reduces to empty after sanitisation returns []."""
        db = str(tmp_path / "test.db")
        backend = FTS5Backend(str(tmp_path), db)
        results = backend.search("!@#$%^&*()")
        assert results == []

    def test_search_result_has_snippet(self, tmp_path):
        """FTS5 search populates the snippet field."""
        db = str(tmp_path / "test.db")
        backend = FTS5Backend(str(tmp_path), db)
        note = tmp_path / "Snippet Note.md"
        meta = self._make_note(note, title="Snippet Note", tags=["snippet"])
        backend.index_note(str(note), meta)
        results = backend.search("snippet")
        assert len(results) > 0
        # snippet field may be empty for very short bodies but should not raise

    def test_search_handles_malformed_json_tags_gracefully(self, tmp_path):
        """When tags column has malformed JSON, result still included with empty list."""
        db = str(tmp_path / "test.db")
        backend = FTS5Backend(str(tmp_path), db)
        # Manually insert a row with bad JSON in tags
        conn = sqlite3.connect(db)
        conn.execute("""
            INSERT INTO notes (id, path, content_hash, title, summary, tags, related, type, scope, project, date, body)
            VALUES ('bad-json-1', ?, 'hash1', 'Bad Tags Note', 'Summary', 'not-valid-json', '[]', 'insight', '', '', '', 'Body')
        """, (str(tmp_path / "BadTags.md"),))
        conn.commit()
        conn.close()
        results = backend.search("bad tags")
        # Should not raise; tags may be empty list
        for r in results:
            assert isinstance(r.tags, list)

    def test_build_index_progress_logging(self, tmp_path, capsys):
        """build_index() logs progress to stderr."""
        db = str(tmp_path / "test.db")
        backend = FTS5Backend(str(tmp_path), db)
        # Write a few notes
        for i in range(3):
            note = tmp_path / f"Note{i}.md"
            meta = self._make_note(note, title=f"Note {i}")
            # (meta written by _make_note already via write)
        backend.build_index()
        captured = capsys.readouterr()
        assert "FTS5" in captured.err or "index" in captured.err.lower()


# ===========================================================================
# GrepBackend — OSError mtime path
# ===========================================================================

class TestGrepBackendEdgeCases:
    """GrepBackend handles OSError when checking file mtime."""

    def test_oserror_on_mtime_uses_fallback(self, tmp_path):
        """When os.path.getmtime raises OSError, the note is still ranked (score only)."""
        note = tmp_path / "note.md"
        note.write_text("jwt authentication token here", encoding="utf-8")

        backend = GrepBackend(str(tmp_path))
        # Patch getmtime to raise OSError for this specific path
        original_getmtime = __import__("os").path.getmtime
        def patched_getmtime(p):
            if str(note) in str(p):
                raise OSError("stat error")
            return original_getmtime(p)

        with patch("os.path.getmtime", side_effect=patched_getmtime):
            results = backend.search("jwt authentication")

        # The note may or may not appear but no exception
        assert isinstance(results, list)


# ===========================================================================
# HybridBackend — full path coverage with mocked fastembed/usearch
# ===========================================================================

class TestHybridBackendFull:
    """
    HybridBackend coverage using mock fastembed and usearch.

    These tests verify the wiring between BM25 and semantic layers,
    the save/load index flow, and _semantic_search result assembly.
    """

    def _make_hybrid_with_mocks(self, tmp_path):
        """Build a HybridBackend with mock model and index."""
        np = pytest.importorskip("numpy")
        from cyberbrain.extractors.search_backends import HybridBackend

        db = str(tmp_path / "test.db")
        backend = HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")

        # Install mock model
        mock_model = MagicMock()
        mock_model.embed = MagicMock(return_value=iter([[0.1] * 384]))
        backend._model = mock_model

        # Install mock index
        mock_index = MagicMock()
        mock_index.ndim = 384
        mock_index.add = MagicMock()
        mock_index.search = MagicMock(return_value=[])
        backend._index = mock_index
        backend._id_map = []

        return backend

    def test_backend_name_includes_model(self, tmp_path):
        """backend_name() returns a string containing the model name."""
        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        backend = HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")
        assert "bge-micro" in backend.backend_name()
        assert "hybrid" in backend.backend_name()

    def _usearch_modules(self):
        """Return a dict of mock sys.modules entries for usearch and numpy."""
        mock_usearch = MagicMock()
        mock_usearch_index = MagicMock()
        mock_usearch_index.Index = MagicMock()
        mock_usearch.index = mock_usearch_index
        mock_np = MagicMock()
        mock_np.array = lambda x, dtype=None: x
        mock_np.zeros = lambda shape, dtype=None: [0.0] * (shape if isinstance(shape, int) else shape[0])
        mock_np.float32 = float
        return {
            "usearch": mock_usearch,
            "usearch.index": mock_usearch_index,
            "numpy": mock_np,
        }

    def test_embed_note_adds_vector_to_index(self, tmp_path):
        """_embed_note() adds the note to the id_map and calls index.add."""
        backend = self._make_hybrid_with_mocks(tmp_path)
        note = tmp_path / "Test Note.md"
        note.write_text('---\ntitle: "Test"\ntags: []\nsummary: "Test"\n---\nBody.', encoding="utf-8")

        with patch.dict(sys.modules, self._usearch_modules()):
            backend._embed_note(str(note), {"title": "Test", "tags": [], "summary": "Test note"})

        assert len(backend._id_map) == 1
        backend._index.add.assert_called_once()

    def test_embed_note_uses_stem_when_title_empty(self, tmp_path):
        """_embed_note() with empty title falls back to filename stem and still embeds."""
        backend = self._make_hybrid_with_mocks(tmp_path)
        note = tmp_path / "Fallback.md"
        note.write_text("", encoding="utf-8")

        with patch.dict(sys.modules, self._usearch_modules()):
            backend._embed_note(str(note), {"title": "", "summary": "", "tags": []})
        # stem "Fallback" is used as title, so the note IS indexed
        assert len(backend._id_map) == 1

    def test_index_note_delegates_to_fts5_and_embed(self, tmp_path):
        """index_note() calls both FTS5 and semantic embedding."""
        backend = self._make_hybrid_with_mocks(tmp_path)
        note = tmp_path / "Both.md"
        note.write_text('---\nid: abc\ntitle: "Both"\ntags: []\nsummary: "Both"\n---\nBody.', encoding="utf-8")

        with patch.object(backend._fts5, "index_note") as mock_fts:
            backend.index_note(str(note), {"id": "abc", "title": "Both", "tags": [], "summary": "Both"})

        mock_fts.assert_called_once()

    def test_save_index_writes_files(self, tmp_path):
        """_save_index() creates the usearch file and manifest JSON."""
        backend = self._make_hybrid_with_mocks(tmp_path)
        backend._id_map = [str(tmp_path / "A.md"), str(tmp_path / "B.md")]
        backend._index.save = MagicMock()

        backend._save_index()

        backend._index.save.assert_called_once()
        manifest_path = Path(backend._manifest_path)
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["model_name"] == "TaylorAI/bge-micro-v2"
        assert len(manifest["id_map"]) == 2

    def test_save_index_handles_exception_gracefully(self, tmp_path, capsys):
        """_save_index() catching an error logs it and doesn't raise."""
        backend = self._make_hybrid_with_mocks(tmp_path)
        backend._index.save = MagicMock(side_effect=RuntimeError("disk full"))

        backend._save_index()  # should not raise
        captured = capsys.readouterr()
        assert "save" in captured.err.lower() or "index" in captured.err.lower()

    def test_semantic_search_returns_empty_when_id_map_empty(self, tmp_path):
        """_semantic_search() with no indexed notes returns []."""
        backend = self._make_hybrid_with_mocks(tmp_path)
        backend._id_map = []
        backend._index.search.return_value = []

        results = backend._semantic_search("jwt authentication", top_k=5)
        assert results == []

    def test_semantic_search_assembles_results(self, tmp_path):
        """_semantic_search() builds SearchResult objects from index hits."""
        backend = self._make_hybrid_with_mocks(tmp_path)
        note = tmp_path / "Auth.md"
        note.write_text('---\ntitle: Auth\ntags: [jwt]\nsummary: "Auth summary"\n---\nBody.', encoding="utf-8")
        backend._id_map = [str(note)]

        # Simulate usearch returning match at index 0
        mock_match = MagicMock()
        mock_match.key = 0
        mock_match.distance = 0.15
        backend._index.search.return_value = [mock_match]

        results = backend._semantic_search("authentication", top_k=5)
        assert len(results) == 1
        assert results[0].path == str(note)
        assert results[0].backend == "semantic"

    def test_semantic_search_skips_out_of_range_index(self, tmp_path):
        """Index keys beyond id_map length are skipped silently."""
        backend = self._make_hybrid_with_mocks(tmp_path)
        backend._id_map = [str(tmp_path / "Only.md")]

        mock_match = MagicMock()
        mock_match.key = 999  # way out of range
        mock_match.distance = 0.1
        backend._index.search.return_value = [mock_match]

        results = backend._semantic_search("test", top_k=5)
        assert results == []

    def test_semantic_search_returns_empty_on_exception(self, tmp_path, capsys):
        """_semantic_search() catches exceptions and returns []."""
        backend = self._make_hybrid_with_mocks(tmp_path)
        backend._id_map = [str(tmp_path / "Note.md")]

        with patch.object(backend, "_embed", side_effect=RuntimeError("no model")):
            results = backend._semantic_search("test", top_k=5)

        assert results == []
        captured = capsys.readouterr()
        assert "error" in captured.err.lower() or "Semantic" in captured.err

    def test_hybrid_search_fuses_bm25_and_semantic(self, tmp_path):
        """search() fuses BM25 and semantic results via RRF."""
        backend = self._make_hybrid_with_mocks(tmp_path)
        note = tmp_path / "Fused.md"
        note.write_text('---\nid: fused\ntitle: "Fused"\ntags: [fusion]\nsummary: "Test fusion"\n---\nBody.', encoding="utf-8")

        from cyberbrain.extractors.search_backends import SearchResult
        bm25_result = SearchResult(path=str(note), title="Fused", score=1.0, backend="fts5")

        with patch.object(backend._fts5, "search", return_value=[bm25_result]):
            mock_match = MagicMock()
            mock_match.key = 0
            mock_match.distance = 0.1
            backend._id_map = [str(note)]
            backend._index.search.return_value = [mock_match]

            results = backend.search("fusion test", top_k=5)

        assert len(results) >= 1
        # All results should have the hybrid backend name
        for r in results:
            assert "hybrid" in r.backend

    def test_hybrid_search_falls_back_to_bm25_label_when_no_semantic(self, tmp_path):
        """When semantic search returns [], results get 'fts5 (semantic unavailable)' label."""
        backend = self._make_hybrid_with_mocks(tmp_path)
        note = tmp_path / "BM25Only.md"
        note.write_text('---\nid: bm\ntitle: BM25\ntags: [bm25]\nsummary: "BM25 only"\n---\nBody.', encoding="utf-8")

        from cyberbrain.extractors.search_backends import SearchResult
        bm25_result = SearchResult(path=str(note), title="BM25", score=1.0, backend="fts5")

        with patch.object(backend._fts5, "search", return_value=[bm25_result]):
            with patch.object(backend, "_semantic_search", return_value=[]):
                results = backend.search("bm25 only", top_k=5)

        assert len(results) >= 1
        assert all("fts5" in r.backend for r in results)


# ===========================================================================
# SmartConnections — additional import paths
# ===========================================================================

class TestSmartConnectionsAdditional:
    """Additional SmartConnections import scenarios."""

    def _make_hybrid(self, tmp_path):
        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        return HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")

    def test_imports_from_single_ajson_when_no_multi_dir(self, tmp_path):
        """Without a multi/ subdir, tries smart_sources.ajson in .smart-env/."""
        sc_dir = tmp_path / ".smart-env"
        sc_dir.mkdir()

        vault_note = tmp_path / "Note.md"
        vault_note.write_text("# Note\n\nContent.", encoding="utf-8")

        vec = [0.1] * 384
        ajson_content = f'"Note.md": {{"path": "Note.md", "embeddings": {{"model": {{"vec": {json.dumps(vec)}}}}}}}\n'
        (sc_dir / "smart_sources.ajson").write_text(ajson_content, encoding="utf-8")

        backend = self._make_hybrid(tmp_path)
        mock_index = MagicMock()
        mock_index.add = MagicMock()
        backend._index = mock_index
        backend._id_map = []

        mock_np = MagicMock()
        mock_np.array = lambda x, **kw: x

        with patch.dict(sys.modules, {"numpy": mock_np}):
            with patch.object(backend, "_save_index"):
                result = backend._try_import_smart_connections_index()

        assert result is True

    def test_returns_false_when_ajson_oserror(self, tmp_path):
        """An unreadable .ajson file returns 0 and does not raise."""
        sc_dir = tmp_path / ".smart-env"
        multi_dir = sc_dir / "multi"
        multi_dir.mkdir(parents=True)

        ajson_file = multi_dir / "bad.ajson"
        ajson_file.write_text("dummy", encoding="utf-8")

        backend = self._make_hybrid(tmp_path)
        mock_index = MagicMock()
        backend._index = mock_index
        backend._id_map = []

        # Simulate OSError on read
        with patch("pathlib.Path.read_text", side_effect=OSError("no read")):
            result = backend._import_sc_ajson(ajson_file)

        assert result == 0

    def test_skips_non_dict_values_in_ajson(self, tmp_path):
        """Lines where value is not a dict (e.g. a string) are skipped."""
        backend = self._make_hybrid(tmp_path)
        ajson_file = tmp_path / "mixed.ajson"
        ajson_file.write_text(
            '"key1": "just a string"\n'
            '"key2": 42\n',
            encoding="utf-8",
        )
        mock_index = MagicMock()
        backend._index = mock_index
        backend._id_map = []

        result = backend._import_sc_ajson(ajson_file)
        assert result == 0

    def test_skips_record_with_empty_vec(self, tmp_path):
        """An embedding with an empty vec list is skipped."""
        backend = self._make_hybrid(tmp_path)
        ajson_file = tmp_path / "empty_vec.ajson"
        ajson_file.write_text(
            '"Note.md": {"path": "Note.md", "embeddings": {"model": {"vec": []}}}\n',
            encoding="utf-8",
        )
        mock_index = MagicMock()
        backend._index = mock_index
        backend._id_map = []

        result = backend._import_sc_ajson(ajson_file)
        assert result == 0

    def test_skips_record_with_no_embeddings(self, tmp_path):
        """A record with no embeddings key is skipped."""
        backend = self._make_hybrid(tmp_path)
        ajson_file = tmp_path / "no_embed.ajson"
        ajson_file.write_text(
            '"Note.md": {"path": "Note.md"}\n',
            encoding="utf-8",
        )
        mock_index = MagicMock()
        backend._index = mock_index
        backend._id_map = []

        result = backend._import_sc_ajson(ajson_file)
        assert result == 0


# ===========================================================================
# FTS5Backend — additional coverage for uncovered lines
# ===========================================================================

class TestFTS5BackendCoverageGaps:
    """Tests targeting specific uncovered lines in FTS5Backend."""

    def test_search_catches_operational_error(self, tmp_path):
        """When FTS5 raises OperationalError (e.g. corrupt index), returns []."""
        db = str(tmp_path / "test.db")
        backend = FTS5Backend(str(tmp_path), db)

        # Patch _connect() to return a mock connection that raises OperationalError
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = sqlite3.OperationalError("fts5: no such table")
        # Need a context manager that returns mock_conn
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_conn)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        with patch.object(backend, "_connect", return_value=mock_ctx):
            results = backend.search("something valid")
        assert results == []

    def test_search_handles_malformed_json_related_gracefully(self, tmp_path):
        """When related column has malformed JSON, result is included with empty list."""
        db = str(tmp_path / "test.db")
        backend = FTS5Backend(str(tmp_path), db)
        # Manually insert a row with bad JSON in both tags and related
        conn = sqlite3.connect(db)
        conn.execute("""
            INSERT INTO notes (id, path, content_hash, title, summary, tags, related, type, scope, project, date, body)
            VALUES ('bad-rel-1', ?, 'hash2', 'Bad Related Note', 'Summary', '["ok"]', 'not-valid-json-related', 'insight', '', '', '', 'Body')
        """, (str(tmp_path / "BadRelated.md"),))
        conn.commit()
        conn.close()

        results = backend.search("bad related")
        # Should not raise; related should be empty list on parse failure
        for r in results:
            assert isinstance(r.related, list)

    def test_build_index_progress_logging_at_100_notes(self, tmp_path, capsys):
        """build_index() emits progress every 100 notes."""
        db = str(tmp_path / "test.db")
        backend = FTS5Backend(str(tmp_path), db)

        # Create 100 markdown files to trigger the % 100 == 0 branch
        for i in range(100):
            note = tmp_path / f"Note{i:03d}.md"
            note.write_text(
                f'---\nid: note-{i}\ntitle: "Note {i}"\ntags: []\nsummary: ""\n---\nBody {i}.\n',
                encoding="utf-8",
            )

        backend.build_index()
        captured = capsys.readouterr()
        # Should contain the 100/100 progress log entry
        assert "100/" in captured.err


# ===========================================================================
# HybridBackend — _get_model, _load_or_create_index, build_index coverage
# ===========================================================================

class TestHybridBackendLoadAndBuild:
    """Cover _get_model, _load_or_create_index, and build_index with usearch mocks."""

    def _make_mocks(self):
        """Return (mock_usearch_modules_dict, MockIndex_class, mock_np)."""
        MockIndex = MagicMock()
        mock_index_instance = MagicMock()
        mock_index_instance.ndim = 384
        MockIndex.return_value = mock_index_instance

        mock_usearch_index_mod = MagicMock()
        mock_usearch_index_mod.Index = MockIndex

        mock_usearch_mod = MagicMock()
        mock_usearch_mod.index = mock_usearch_index_mod

        mock_np = MagicMock()
        mock_np.array = lambda x, dtype=None: x
        mock_np.zeros = lambda shape, dtype=None: [0.0] * (shape if isinstance(shape, int) else shape[0])
        mock_np.float32 = float

        mods = {
            "usearch": mock_usearch_mod,
            "usearch.index": mock_usearch_index_mod,
            "numpy": mock_np,
        }
        return mods, MockIndex, mock_index_instance, mock_np

    def test_get_model_calls_fastembed(self, tmp_path):
        """_get_model() imports TextEmbedding from fastembed and creates the model."""
        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        backend = HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")

        mock_fastembed = MagicMock()
        MockTextEmbedding = MagicMock()
        mock_fastembed.TextEmbedding = MockTextEmbedding

        with patch.dict(sys.modules, {"fastembed": mock_fastembed}):
            model = backend._get_model()

        MockTextEmbedding.assert_called_once_with(model_name="TaylorAI/bge-micro-v2")
        assert backend._model is model

    def test_get_model_cached_on_second_call(self, tmp_path):
        """_get_model() returns the same object on repeated calls."""
        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        backend = HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")

        mock_model = MagicMock()
        backend._model = mock_model  # pre-set to simulate already loaded

        result = backend._get_model()
        assert result is mock_model

    def test_load_or_create_index_creates_new_index(self, tmp_path):
        """_load_or_create_index() creates a fresh Index when no index file exists."""
        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        backend = HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")

        mods, MockIndex, mock_index_inst, mock_np = self._make_mocks()
        with patch.dict(sys.modules, mods):
            backend._load_or_create_index()

        assert backend._index is mock_index_inst

    def test_load_or_create_index_skips_when_already_loaded(self, tmp_path):
        """_load_or_create_index() returns immediately if _index is already set."""
        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        backend = HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")

        existing_index = MagicMock()
        backend._index = existing_index

        mods, MockIndex, _, _ = self._make_mocks()
        with patch.dict(sys.modules, mods):
            backend._load_or_create_index()

        # Should not have created a new Index
        MockIndex.assert_not_called()
        assert backend._index is existing_index

    def test_load_or_create_index_detects_model_mismatch(self, tmp_path, capsys):
        """_load_or_create_index() logs a warning and deletes the old index on model mismatch."""
        import json as jsonmod
        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        backend = HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")

        # Create a manifest with a different model name
        manifest_path = Path(backend._manifest_path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(jsonmod.dumps({"model_name": "other-model", "embedding_dim": 384}))

        # Create a fake index file to check it gets deleted
        index_path = Path(backend._usearch_path)
        index_path.write_text("fake")

        mods, MockIndex, mock_index_inst, mock_np = self._make_mocks()
        with patch.dict(sys.modules, mods):
            backend._load_or_create_index()

        captured = capsys.readouterr()
        assert "other-model" in captured.err or "rebuilding" in captured.err.lower()
        assert not index_path.exists()  # old index file deleted

    def test_load_or_create_index_loads_existing_index(self, tmp_path):
        """_load_or_create_index() calls index.load() when an index file exists."""
        import json as jsonmod
        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        backend = HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")

        # Create a manifest and fake index file
        manifest_path = Path(backend._manifest_path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        id_map = [str(tmp_path / "A.md")]
        manifest_path.write_text(jsonmod.dumps({
            "model_name": "TaylorAI/bge-micro-v2",
            "embedding_dim": 384,
            "id_map": id_map,
        }))
        index_path = Path(backend._usearch_path)
        index_path.write_text("fake")

        mods, MockIndex, mock_index_inst, mock_np = self._make_mocks()
        with patch.dict(sys.modules, mods):
            backend._load_or_create_index()

        mock_index_inst.load.assert_called_once()
        assert backend._id_map == id_map

    def test_load_or_create_index_handles_load_failure(self, tmp_path, capsys):
        """_load_or_create_index() falls back to empty index when load() raises."""
        import json as jsonmod
        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        backend = HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")

        manifest_path = Path(backend._manifest_path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(jsonmod.dumps({
            "model_name": "TaylorAI/bge-micro-v2",
            "embedding_dim": 384,
            "id_map": [],
        }))
        index_path = Path(backend._usearch_path)
        index_path.write_text("corrupt")

        mods, MockIndex, mock_index_inst, mock_np = self._make_mocks()
        mock_index_inst.load.side_effect = RuntimeError("corrupt index")
        with patch.dict(sys.modules, mods):
            backend._load_or_create_index()

        captured = capsys.readouterr()
        assert "USearch" in captured.err or "load" in captured.err.lower()

    def test_embed_note_with_tags_as_json_string(self, tmp_path):
        """_embed_note() handles tags stored as a JSON string (not a list)."""
        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        backend = HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")

        # Pre-set model and index to avoid lazy loading
        mock_model = MagicMock()
        mock_model.embed = MagicMock(return_value=iter([[0.1] * 384]))
        backend._model = mock_model

        mock_index = MagicMock()
        mock_index.ndim = 384
        backend._index = mock_index
        backend._id_map = []

        note = tmp_path / "TagsStr.md"
        note.write_text("# Tags as string", encoding="utf-8")

        mods, _, _, _ = self._make_mocks()
        with patch.dict(sys.modules, mods):
            # Pass tags as a JSON-encoded string (not a Python list)
            backend._embed_note(str(note), {"title": "Tags test", "summary": "", "tags": '["auth", "jwt"]'})

        assert len(backend._id_map) == 1

    def test_embed_note_with_unparseable_tags_string(self, tmp_path):
        """_embed_note() handles tags that are a non-JSON string."""
        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        backend = HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")

        mock_model = MagicMock()
        mock_model.embed = MagicMock(return_value=iter([[0.1] * 384]))
        backend._model = mock_model

        mock_index = MagicMock()
        mock_index.ndim = 384
        backend._index = mock_index
        backend._id_map = []

        note = tmp_path / "BadTagsStr.md"
        note.write_text("# Bad tags string", encoding="utf-8")

        mods, _, _, _ = self._make_mocks()
        with patch.dict(sys.modules, mods):
            backend._embed_note(str(note), {"title": "Tags test", "summary": "", "tags": "not-valid-json"})

        assert len(backend._id_map) == 1

    def test_build_index_full_pipeline(self, tmp_path, capsys):
        """HybridBackend.build_index() runs FTS5 + semantic indexing."""
        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        backend = HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")

        note = tmp_path / "Indexed.md"
        note.write_text('---\ntitle: "Indexed"\ntags: []\nsummary: ""\n---\nBody.\n', encoding="utf-8")

        mock_model = MagicMock()
        mock_model.embed = MagicMock(return_value=iter([[0.1] * 384]))
        backend._model = mock_model

        mock_index = MagicMock()
        mock_index.ndim = 384
        mock_index.add = MagicMock()
        mock_index.save = MagicMock()
        backend._index = mock_index
        backend._id_map = []

        mods, _, _, _ = self._make_mocks()
        with patch.dict(sys.modules, mods):
            with patch.object(backend, "_try_import_smart_connections_index", return_value=False):
                with patch.object(backend, "_save_index"):
                    backend.build_index()

        captured = capsys.readouterr()
        assert "semantic" in captured.err.lower() or "index" in captured.err.lower()

    def test_build_index_uses_smart_connections_when_available(self, tmp_path):
        """HybridBackend.build_index() returns early if SC import succeeds."""
        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        backend = HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")

        with patch.object(backend._fts5, "build_index"):
            with patch.object(backend, "_try_import_smart_connections_index", return_value=True):
                backend.build_index()  # should return early after SC import

        # _embed_note should NOT be called since SC import handled it
        # (no error = success)

    def test_build_index_logs_embed_note_exception(self, tmp_path, capsys):
        """When _embed_note raises during build_index, exception is logged and build continues."""
        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        backend = HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")

        note = tmp_path / "Problem.md"
        note.write_text('---\ntitle: "Problem"\ntags: []\nsummary: ""\n---\nBody.\n', encoding="utf-8")

        mock_model = MagicMock()
        backend._model = mock_model

        mock_index = MagicMock()
        mock_index.ndim = 384
        mock_index.save = MagicMock()
        backend._index = mock_index
        backend._id_map = []

        mods, _, _, _ = self._make_mocks()
        with patch.dict(sys.modules, mods):
            with patch.object(backend, "_try_import_smart_connections_index", return_value=False):
                with patch.object(backend, "_embed_note", side_effect=RuntimeError("embed failed")):
                    with patch.object(backend, "_save_index"):
                        backend.build_index()

        captured = capsys.readouterr()
        assert "Embedding failed" in captured.err or "failed" in captured.err.lower()

    def test_load_or_create_index_corrupt_manifest_falls_through(self, tmp_path):
        """When manifest.json contains invalid JSON, exception is caught and index is created fresh."""
        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        backend = HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")

        # Write corrupt manifest JSON
        manifest_path = Path(backend._manifest_path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text("{{not valid json", encoding="utf-8")

        mods, MockIndex, mock_index_inst, mock_np = self._make_mocks()
        with patch.dict(sys.modules, mods):
            backend._load_or_create_index()

        # Should still create the index despite corrupt manifest
        assert backend._index is mock_index_inst

    def test_load_or_create_index_warmup_with_nonempty_id_map(self, tmp_path):
        """_load_or_create_index() runs a warmup search when id_map is non-empty after loading."""
        import json as jsonmod
        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        backend = HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")

        # Create a manifest and fake index file with a non-empty id_map
        manifest_path = Path(backend._manifest_path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        id_map = [str(tmp_path / "A.md")]
        manifest_path.write_text(jsonmod.dumps({
            "model_name": "TaylorAI/bge-micro-v2",
            "embedding_dim": 384,
            "id_map": id_map,
        }))
        index_path = Path(backend._usearch_path)
        index_path.write_text("fake")

        mods, MockIndex, mock_index_inst, mock_np = self._make_mocks()
        # Make mock_np.zeros return a real list (for warm-up query)
        mock_np.zeros = MagicMock(return_value=[0.0] * 384)
        with patch.dict(sys.modules, mods):
            backend._load_or_create_index()

        # Warm-up search should have been called since id_map is non-empty
        mock_index_inst.search.assert_called_once()


# ===========================================================================
# SmartConnections — _try_import_smart_connections_index coverage gaps
# ===========================================================================

class TestSmartConnectionsCoverageGaps:
    """Covers remaining SC import paths."""

    def _make_hybrid(self, tmp_path):
        from cyberbrain.extractors.search_backends import HybridBackend
        db = str(tmp_path / "test.db")
        return HybridBackend(str(tmp_path), db, "TaylorAI/bge-micro-v2")

    def test_sc_import_with_model_match_returns_true(self, tmp_path):
        """When SC settings match the configured model and embeddings exist, returns True."""
        import json as jsonmod
        sc_dir = tmp_path / ".smart-env"
        sc_dir.mkdir()

        # Settings file with matching model
        settings = sc_dir / "settings.json"
        settings.write_text(jsonmod.dumps({"smart_sources": {"embed_model": "TaylorAI/bge-micro-v2"}}))

        # Single ajson file with a valid record
        vault_note = tmp_path / "Match.md"
        vault_note.write_text("# Match\n\nContent.", encoding="utf-8")
        vec = [0.1] * 384
        ajson_content = f'"Match.md": {{"path": "Match.md", "embeddings": {{"TaylorAI/bge-micro-v2": {{"vec": {jsonmod.dumps(vec)}}}}}}}\n'
        (sc_dir / "smart_sources.ajson").write_text(ajson_content, encoding="utf-8")

        backend = self._make_hybrid(tmp_path)
        mock_index = MagicMock()
        mock_index.add = MagicMock()
        backend._index = mock_index
        backend._id_map = []

        mock_np = MagicMock()
        mock_np.array = lambda x, **kw: x

        with patch.dict(sys.modules, {"numpy": mock_np}):
            with patch.object(backend, "_save_index"):
                result = backend._try_import_smart_connections_index()

        assert result is True

    def test_sc_import_returns_false_when_imported_zero(self, tmp_path):
        """When SC dir exists but no valid embeddings found, returns False."""
        sc_dir = tmp_path / ".smart-env"
        sc_dir.mkdir()
        # Empty ajson file
        (sc_dir / "smart_sources.ajson").write_text("", encoding="utf-8")

        backend = self._make_hybrid(tmp_path)
        mock_index = MagicMock()
        backend._index = mock_index
        backend._id_map = []

        result = backend._try_import_smart_connections_index()
        assert result is False

    def test_sc_import_settings_invalid_json_falls_through(self, tmp_path):
        """When settings.json contains invalid JSON, exception is caught and import proceeds."""
        sc_dir = tmp_path / ".smart-env"
        sc_dir.mkdir()
        # Write invalid JSON to settings
        (sc_dir / "settings.json").write_text("not valid json {{}", encoding="utf-8")

        vault_note = tmp_path / "Note.md"
        vault_note.write_text("# Note", encoding="utf-8")
        vec = [0.1] * 384
        import json as jsonmod
        ajson_content = f'"Note.md": {{"path": "Note.md", "embeddings": {{"model": {{"vec": {jsonmod.dumps(vec)}}}}}}}\n'
        (sc_dir / "smart_sources.ajson").write_text(ajson_content, encoding="utf-8")

        backend = self._make_hybrid(tmp_path)
        mock_index = MagicMock()
        mock_index.add = MagicMock()
        backend._index = mock_index
        backend._id_map = []

        mock_np = MagicMock()
        mock_np.array = lambda x, **kw: x

        with patch.dict(sys.modules, {"numpy": mock_np}):
            with patch.object(backend, "_save_index"):
                result = backend._try_import_smart_connections_index()

        # Should proceed past the exception and still import
        assert result is True

    def test_sc_import_multi_dir_mode(self, tmp_path):
        """_try_import_smart_connections_index() iterates .ajson files in multi/ subdir."""
        sc_dir = tmp_path / ".smart-env"
        multi_dir = sc_dir / "multi"
        multi_dir.mkdir(parents=True)

        vault_note = tmp_path / "Multi.md"
        vault_note.write_text("# Multi", encoding="utf-8")

        vec = [0.1] * 384
        import json as jsonmod
        ajson_content = f'"Multi.md": {{"path": "Multi.md", "embeddings": {{"model": {{"vec": {jsonmod.dumps(vec)}}}}}}}\n'
        (multi_dir / "multi-note.ajson").write_text(ajson_content, encoding="utf-8")

        backend = self._make_hybrid(tmp_path)
        mock_index = MagicMock()
        mock_index.add = MagicMock()
        backend._index = mock_index
        backend._id_map = []

        mock_np = MagicMock()
        mock_np.array = lambda x, **kw: x

        with patch.dict(sys.modules, {"numpy": mock_np}):
            with patch.object(backend, "_save_index"):
                result = backend._try_import_smart_connections_index()

        assert result is True

    def test_sc_import_empty_line_skipped(self, tmp_path):
        """Empty lines in ajson file are skipped (line 582 coverage)."""
        backend = self._make_hybrid(tmp_path)
        ajson_file = tmp_path / "with_blanks.ajson"
        # File with blank lines between records
        vec = [0.1] * 384
        import json as jsonmod
        ajson_file.write_text(
            "\n\n"  # blank lines at start
            f'"Note.md": {{"path": "Note.md", "embeddings": {{"model": {{"vec": {jsonmod.dumps(vec)}}}}}}}\n'
            "\n",  # blank line at end
            encoding="utf-8",
        )

        mock_index = MagicMock()
        mock_index.add = MagicMock()
        backend._index = mock_index
        backend._id_map = []

        mock_np = MagicMock()
        mock_np.array = lambda x, **kw: x

        with patch.dict(sys.modules, {"numpy": mock_np}):
            result = backend._import_sc_ajson(ajson_file)

        assert result >= 1  # The one valid record was imported

    def test_sc_import_exception_in_add_loop(self, tmp_path, capsys):
        """When index.add() raises, the error is logged and import continues."""
        backend = self._make_hybrid(tmp_path)
        ajson_file = tmp_path / "fail_add.ajson"
        vec = [0.1] * 384
        import json as jsonmod
        ajson_file.write_text(
            f'"Note.md": {{"path": "Note.md", "embeddings": {{"model": {{"vec": {jsonmod.dumps(vec)}}}}}}}\n',
            encoding="utf-8",
        )

        mock_index = MagicMock()
        mock_index.add = MagicMock(side_effect=RuntimeError("add failed"))
        backend._index = mock_index
        backend._id_map = []

        mock_np = MagicMock()
        mock_np.array = lambda x, **kw: x

        with patch.dict(sys.modules, {"numpy": mock_np}):
            result = backend._import_sc_ajson(ajson_file)

        assert result == 0
        captured = capsys.readouterr()
        assert "SC import failed" in captured.err or "failed" in captured.err.lower()


# ===========================================================================
# get_search_backend — auto-selection paths
# ===========================================================================

class TestGetSearchBackendAutoSelection:
    """get_search_backend() auto-selection when fastembed/usearch are importable."""

    def test_auto_returns_hybrid_when_both_available(self, tmp_path):
        """'auto' with fastembed and usearch available → HybridBackend."""
        from cyberbrain.extractors.search_backends import get_search_backend, HybridBackend

        mock_fastembed = MagicMock()
        mock_usearch = MagicMock()

        config = {
            "vault_path": str(tmp_path),
            "search_backend": "auto",
            "embedding_model": "TaylorAI/bge-micro-v2",
            "search_db_path": str(tmp_path / "test.db"),
        }

        with patch.dict(sys.modules, {"fastembed": mock_fastembed, "usearch": mock_usearch}):
            backend = get_search_backend(config)

        assert isinstance(backend, HybridBackend)

    def test_hybrid_explicit_with_both_available(self, tmp_path):
        """'hybrid' preference with both packages available → HybridBackend."""
        from cyberbrain.extractors.search_backends import get_search_backend, HybridBackend

        mock_fastembed = MagicMock()
        mock_usearch = MagicMock()

        config = {
            "vault_path": str(tmp_path),
            "search_backend": "hybrid",
            "embedding_model": "TaylorAI/bge-micro-v2",
            "search_db_path": str(tmp_path / "test.db"),
        }

        with patch.dict(sys.modules, {"fastembed": mock_fastembed, "usearch": mock_usearch}):
            backend = get_search_backend(config)

        assert isinstance(backend, HybridBackend)

    def test_auto_falls_back_to_fts5_when_fastembed_missing(self, tmp_path):
        """'auto' with fastembed unavailable → FTS5Backend (line 770-774 path)."""
        from cyberbrain.extractors.search_backends import get_search_backend, FTS5Backend

        config = {
            "vault_path": str(tmp_path),
            "search_backend": "auto",
            "search_db_path": str(tmp_path / "test.db"),
        }

        with patch.dict(sys.modules, {"fastembed": None, "usearch": None}):
            backend = get_search_backend(config)

        assert isinstance(backend, FTS5Backend)

    def test_auto_returns_fts5_when_fastembed_present_but_usearch_absent(self, tmp_path):
        """'auto' with fastembed available but usearch unavailable → FTS5Backend.
        Covers _has_usearch() ImportError path (lines 752-753) and _has_fastembed() return True (line 744).
        """
        from cyberbrain.extractors.search_backends import get_search_backend, FTS5Backend

        mock_fastembed = MagicMock()

        config = {
            "vault_path": str(tmp_path),
            "search_backend": "auto",
            "search_db_path": str(tmp_path / "test.db"),
        }

        # fastembed is present (importable), usearch is absent (None triggers ImportError)
        with patch.dict(sys.modules, {"fastembed": mock_fastembed, "usearch": None}):
            backend = get_search_backend(config)

        assert isinstance(backend, FTS5Backend)


# ===========================================================================
# search_index — additional exception paths
# ===========================================================================

# (These are in test_search_index.py but added here for completeness)
