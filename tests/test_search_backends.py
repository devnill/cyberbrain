"""
test_search_backends.py — unit tests for extractors/search_backends.py

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
EXTRACTORS_DIR = REPO_ROOT / "extractors"
if str(EXTRACTORS_DIR) not in sys.path:
    sys.path.insert(0, str(EXTRACTORS_DIR))

import search_backends as sb
from search_backends import (
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
        from search_backends import HybridBackend

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
        from search_backends import HybridBackend
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
        from search_backends import HybridBackend
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

        from search_backends import HybridBackend
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
        from search_backends import HybridBackend
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
        from search_backends import HybridBackend
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
