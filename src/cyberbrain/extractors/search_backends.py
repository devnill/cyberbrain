"""
search_backends.py

Pluggable search backend system for cyberbrain's cb_recall.

Three tiers of increasing capability:

  grep    — stdlib only; plain keyword match (current behaviour)
  fts5    — stdlib sqlite3; BM25 keyword search with length normalisation
  hybrid  — fastembed + usearch; BM25 + semantic (HNSW), fused via RRF

Select via cyberbrain.json:
  "search_backend": "auto"   # try hybrid → fts5 → grep (default)
  "search_backend": "hybrid" # require semantic layer; error if unavailable
  "search_backend": "fts5"   # BM25 only
  "search_backend": "grep"   # original grep behaviour

Embedding model is configurable:
  "embedding_model": "TaylorAI/bge-micro-v2"   # default; compatible with Smart Connections
"""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# SearchResult
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    path: str  # absolute path to the note
    title: str = ""
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    note_type: str = ""
    date: str = ""
    score: float = 0.0
    snippet: str = ""  # matching excerpt (FTS5/grep)
    backend: str = ""  # which backend produced this result


# ---------------------------------------------------------------------------
# SearchBackend Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class SearchBackend(Protocol):
    def search(self, query: str, top_k: int = 5, **filters) -> list[SearchResult]:
        """Search the vault and return ranked results."""
        ...

    def index_note(self, note_path: str, metadata: dict) -> None:
        """Index or re-index a single note after it is written."""
        ...

    def build_index(self) -> None:
        """Build or rebuild the full index from the vault."""
        ...

    def backend_name(self) -> str:
        """Human-readable name for this backend (shown in cb_recall output)."""
        ...


# ---------------------------------------------------------------------------
# GrepBackend — zero dependencies, always available
# ---------------------------------------------------------------------------


class GrepBackend:
    """Current grep-based search behaviour, wrapped as a SearchBackend."""

    def __init__(self, vault_path: str):
        self._vault = vault_path

    def backend_name(self) -> str:
        return "grep"

    def index_note(self, note_path: str, metadata: dict) -> None:
        pass  # grep needs no index

    def build_index(self) -> None:
        pass  # grep needs no index

    def search(self, query: str, top_k: int = 5, **filters) -> list[SearchResult]:
        terms = [w for w in re.split(r"\W+", query) if len(w) >= 3][:8]
        if not terms:
            return []

        found: dict[str, tuple[int, float]] = {}
        for term in terms:
            result = subprocess.run(
                ["grep", "-r", "-l", "--include=*.md", "-i", term, self._vault],
                capture_output=True,
                text=True,
            )
            for path in result.stdout.strip().splitlines():
                if path:
                    try:
                        mtime = found.get(path, (0, os.path.getmtime(path)))[1]
                    except OSError:
                        mtime = 0.0
                    count = found.get(path, (0, mtime))[0] + 1
                    found[path] = (count, mtime)

        ranked = sorted(found, key=lambda p: (found[p][0], found[p][1]), reverse=True)[
            :top_k
        ]
        results = []
        for path in ranked:
            fm = _read_frontmatter(path)
            results.append(
                SearchResult(
                    path=path,
                    title=fm.get("title", "") or Path(path).stem,
                    summary=fm.get("summary", ""),
                    tags=_normalise_list(fm.get("tags", [])),
                    related=_normalise_list(fm.get("related", [])),
                    note_type=fm.get("type", ""),
                    date=str(fm.get("date", ""))[:10],
                    score=float(found[path][0]),
                    backend="grep",
                )
            )
        return results


# ---------------------------------------------------------------------------
# FTS5Backend — SQLite FTS5 BM25, no new dependencies
# ---------------------------------------------------------------------------


class FTS5Backend:
    """
    BM25 keyword search using SQLite FTS5.

    Uses length-normalised BM25: bm25(notes_fts, 10.0, 0.0, 0.75)
    Column weights: title=10, summary=5, tags=3, body=1.
    b=0.75 is the standard Okapi BM25 length-normalisation parameter.

    Database: ~/.claude/cyberbrain/search-index.db
    """

    def __init__(self, vault_path: str, db_path: str):
        self._vault = vault_path
        self._db_path = db_path
        self._ensure_schema()

    def backend_name(self) -> str:
        return "fts5"

    def _connect(self) -> sqlite3.Connection:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS notes (
                    id           TEXT PRIMARY KEY,
                    path         TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    title        TEXT,
                    summary      TEXT,
                    tags         TEXT,
                    related      TEXT,
                    type         TEXT,
                    scope        TEXT,
                    project      TEXT,
                    date         TEXT,
                    body         TEXT,
                    embedding    BLOB
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                    title, summary, tags, body,
                    content=notes, content_rowid=rowid
                );
                CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
                    INSERT INTO notes_fts(rowid, title, summary, tags, body)
                    VALUES (new.rowid, new.title, new.summary, new.tags, new.body);
                END;
                CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
                    INSERT INTO notes_fts(notes_fts, rowid, title, summary, tags, body)
                    VALUES ('delete', old.rowid, old.title, old.summary, old.tags, old.body);
                END;
                CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
                    INSERT INTO notes_fts(notes_fts, rowid, title, summary, tags, body)
                    VALUES ('delete', old.rowid, old.title, old.summary, old.tags, old.body);
                    INSERT INTO notes_fts(rowid, title, summary, tags, body)
                    VALUES (new.rowid, new.title, new.summary, new.tags, new.body);
                END;
                CREATE TABLE IF NOT EXISTS relations (
                    from_id       TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    to_title      TEXT NOT NULL,
                    resolved      INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(from_id) REFERENCES notes(id)
                );
                CREATE INDEX IF NOT EXISTS idx_relations_to_title ON relations(to_title);
                CREATE INDEX IF NOT EXISTS idx_relations_from_id  ON relations(from_id);
            """)

    def index_note(self, note_path: str, metadata: dict) -> None:
        """Index or re-index a single note. Skips if content hash unchanged."""
        import hashlib
        import json

        try:
            text = Path(note_path).read_text(encoding="utf-8")
        except OSError:
            return

        content_hash = hashlib.sha256(text.encode()).hexdigest()
        note_id = metadata.get("id") or _derive_id(note_path)

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT content_hash FROM notes WHERE id = ?", (note_id,)
            ).fetchone()
            if existing and existing["content_hash"] == content_hash:
                return  # unchanged

            # Strip frontmatter from body
            body = text
            if text.startswith("---"):
                end = text.find("\n---", 3)
                if end != -1:
                    body = text[end + 4 :].strip()

            tags_json = json.dumps(metadata.get("tags", []))
            related_json = json.dumps(metadata.get("related", []))

            if existing:
                conn.execute(
                    """
                    UPDATE notes SET path=?, content_hash=?, title=?, summary=?,
                        tags=?, related=?, type=?, scope=?, project=?, date=?, body=?
                    WHERE id=?
                """,
                    (
                        note_path,
                        content_hash,
                        metadata.get("title", ""),
                        metadata.get("summary", ""),
                        tags_json,
                        related_json,
                        metadata.get("type", ""),
                        metadata.get("scope", ""),
                        metadata.get("project", ""),
                        str(metadata.get("date", ""))[:10],
                        body[:50_000],  # cap body stored in FTS
                        note_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO notes (id, path, content_hash, title, summary,
                        tags, related, type, scope, project, date, body)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        note_id,
                        note_path,
                        content_hash,
                        metadata.get("title", ""),
                        metadata.get("summary", ""),
                        tags_json,
                        related_json,
                        metadata.get("type", ""),
                        metadata.get("scope", ""),
                        metadata.get("project", ""),
                        str(metadata.get("date", ""))[:10],
                        body[:50_000],
                    ),
                )

    def build_index(self) -> None:
        """Build full index from vault. Incremental — skips unchanged notes."""
        import sys

        vault = Path(self._vault)
        md_files = list(vault.rglob("*.md"))
        total = len(md_files)
        print(
            f"[search_backends] FTS5 index: building from {total} notes...",
            file=sys.stderr,
        )
        count = 0
        for md_file in md_files:
            fm = _read_frontmatter(str(md_file))
            self.index_note(str(md_file), fm)
            count += 1
            if count % 100 == 0:
                print(
                    f"[search_backends] FTS5 index: {count}/{total} ({count * 100 // total}%)",
                    file=sys.stderr,
                )
        print(f"[search_backends] FTS5 index: {count}/{total} done", file=sys.stderr)
        self.prune_stale_notes()

    def prune_stale_notes(self) -> int:
        """
        Remove notes from the index whose vault files no longer exist on disk.
        Also deletes orphaned rows in the relations table.
        Returns the number of notes pruned.
        """
        import sys

        with self._connect() as conn:
            rows = conn.execute("SELECT id, path FROM notes").fetchall()
            stale_ids = [row["id"] for row in rows if not Path(row["path"]).exists()]
            if not stale_ids:
                return 0
            placeholders = ",".join("?" * len(stale_ids))
            conn.execute(
                f"DELETE FROM relations WHERE from_id IN ({placeholders})", stale_ids
            )
            conn.execute(f"DELETE FROM notes WHERE id IN ({placeholders})", stale_ids)
        print(
            f"[search_backends] Pruned {len(stale_ids)} stale note(s) from index",
            file=sys.stderr,
        )
        return len(stale_ids)

    def search(self, query: str, top_k: int = 5, **filters) -> list[SearchResult]:
        import json

        # Escape FTS5 special characters in query
        safe_query = re.sub(r"[^\w\s]", " ", query).strip()
        if not safe_query:
            return []

        # Prefix query: append * to each term for partial matching
        fts_query = " ".join(w + "*" for w in safe_query.split() if w)

        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT n.path, n.title, n.summary, n.tags, n.related,
                           n.type, n.date,
                           bm25(notes_fts, 10.0, 5.0, 3.0, 1.0) AS score,
                           snippet(notes_fts, 0, '<b>', '</b>', '...', 8) AS snip
                    FROM notes_fts
                    JOIN notes n ON notes_fts.rowid = n.rowid
                    WHERE notes_fts MATCH ?
                    ORDER BY score
                    LIMIT ?
                """,
                    (fts_query, top_k),
                ).fetchall()
        except sqlite3.OperationalError:
            # FTS5 table may be empty or query malformed — return nothing
            return []

        results = []
        for row in rows:
            try:
                tags = json.loads(row["tags"] or "[]")
            except (json.JSONDecodeError, TypeError):
                tags = []
            try:
                related = json.loads(row["related"] or "[]")
            except (json.JSONDecodeError, TypeError):
                related = []
            results.append(
                SearchResult(
                    path=row["path"],
                    title=row["title"] or Path(row["path"]).stem,
                    summary=row["summary"] or "",
                    tags=tags,
                    related=related,
                    note_type=row["type"] or "",
                    date=str(row["date"] or "")[:10],
                    score=abs(float(row["score"])),  # bm25() returns negative values
                    snippet=row["snip"] or "",
                    backend="fts5",
                )
            )
        return results


# ---------------------------------------------------------------------------
# HybridBackend — FTS5 BM25 + fastembed HNSW, fused via RRF
# ---------------------------------------------------------------------------


class HybridBackend:
    """
    Hybrid search: BM25 keyword (FTS5) + semantic (USearch HNSW), fused with RRF.

    Requires: fastembed, usearch (install into MCP venv)
    Falls back gracefully: if usearch/fastembed unavailable, delegates to FTS5Backend.

    Embedding model: configurable via embedding_model in cyberbrain.json.
    Default: TaylorAI/bge-micro-v2 (384-dim, ~22.9 MB, compatible with Smart Connections).

    Reads Smart Connections index (.smart-env/smart_sources.ajson) if it exists
    in the vault and was built with the same model — avoids double-indexing.
    """

    _RRF_K = 60  # standard RRF smoothing constant

    def __init__(self, vault_path: str, db_path: str, model_name: str):
        self._vault = vault_path
        self._db_path = db_path
        self._model_name = model_name
        self._fts5 = FTS5Backend(vault_path, db_path)
        self._usearch_path = str(Path(db_path).parent / "search-index.usearch")
        self._manifest_path = str(Path(db_path).parent / "search-index-manifest.json")
        self._model = None
        self._index = None
        self._id_map: list[str] = []  # position in usearch index → note path

    def backend_name(self) -> str:
        return f"hybrid ({self._model_name})"

    def _get_model(self):
        if self._model is None:
            from fastembed import TextEmbedding  # noqa: I001  # type: ignore[import-not-found]  # optional dependency

            self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    def _load_or_create_index(self):
        """Load usearch HNSW index; validate manifest; rebuild if stale."""
        import sys

        if self._index is not None:
            return

        import json  # noqa: I001

        import numpy as np  # noqa: I001  # type: ignore[import-not-found]  # optional dependency
        from usearch.index import Index  # noqa: I001  # type: ignore[import-not-found]  # optional dependency

        # Check manifest for model/dim consistency
        manifest_path = Path(self._manifest_path)
        index_path = Path(self._usearch_path)

        dim = 384  # bge-micro-v2 and bge-small both use 384 dims
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
                if manifest.get("model_name") != self._model_name:
                    print(
                        f"[search_backends] Index built with '{manifest['model_name']}' "
                        f"but config uses '{self._model_name}' — rebuilding index.",
                        file=sys.stderr,
                    )
                    if index_path.exists():
                        index_path.unlink()
                dim = manifest.get("embedding_dim", 384)
            except (
                Exception
            ):  # intentional: malformed manifest is non-fatal; fall back to default dim
                pass

        self._index = Index(ndim=dim, metric="cos", dtype="f32")

        if index_path.exists():
            try:
                self._index.load(str(index_path))
                # Load id_map from manifest
                if manifest_path.exists():
                    manifest = json.loads(manifest_path.read_text())
                    self._id_map = manifest.get("id_map", [])
            except Exception as e:  # intentional: usearch load or JSON parse can fail; rebuild from scratch
                print(
                    f"[search_backends] USearch load failed: {e}. Rebuilding.",
                    file=sys.stderr,
                )
                self._index = Index(ndim=dim, metric="cos", dtype="f32")

        # Warm-up query to force page faults during init, not at query time
        zero_vec = np.zeros(dim, dtype=np.float32)
        if len(self._id_map) > 0:
            self._index.search(zero_vec, k=1)

    def _embed(self, text: str):
        """Embed a single text string. Returns numpy float32 array."""
        import numpy as np  # type: ignore[import-not-found]  # optional dependency

        model = self._get_model()
        vecs = list(model.embed([text]))
        return np.array(vecs[0], dtype=np.float32)

    def index_note(self, note_path: str, metadata: dict) -> None:
        """Index a note into both FTS5 and usearch."""
        self._fts5.index_note(note_path, metadata)

        # Only embed if semantic layer is available
        try:
            self._embed_note(note_path, metadata)
        except Exception as e:  # intentional: embedding failure is non-fatal; FTS5 result still available
            import sys

            print(
                f"[search_backends] Embedding skipped for {Path(note_path).name}: {e}",
                file=sys.stderr,
            )

    def _embed_note(self, note_path: str, metadata: dict) -> None:
        """Compute and store embedding for a note's metadata fields."""
        import json

        self._load_or_create_index()

        # Only embed title + summary + tags (not full body) — these LLM-generated fields
        # are optimised for search signal; full body dilutes with prose and code.
        title = metadata.get("title", "") or Path(note_path).stem
        summary = metadata.get("summary", "")
        tags_raw = metadata.get("tags", [])
        if isinstance(tags_raw, list):
            tags_str = " ".join(str(t) for t in tags_raw)
        else:
            try:
                tags_str = " ".join(json.loads(str(tags_raw)))
            except (json.JSONDecodeError, TypeError, ValueError):
                tags_str = str(tags_raw)

        embed_text = f"{title}. {summary} {tags_str}".strip()
        if not embed_text:
            return

        vec = self._embed(embed_text)
        note_id = len(self._id_map)
        self._id_map.append(note_path)
        self._index.add(note_id, vec)  # type: ignore[reportOptionalMemberAccess]  # _index loaded by _load_or_create_index

    def build_index(self) -> None:
        """Build full FTS5 + usearch index from vault. Opportunistically reuses SC index."""
        import sys

        self._fts5.build_index()

        # Try to reuse Smart Connections embeddings if available and model matches
        if self._try_import_smart_connections_index():
            return

        # Fall back to embedding everything
        print(
            "[search_backends] Building semantic index (this may take a moment)...",
            file=sys.stderr,
        )
        vault = Path(self._vault)
        for md_file in vault.rglob("*.md"):
            fm = _read_frontmatter(str(md_file))
            try:
                self._embed_note(str(md_file), fm)
            except Exception as e:  # intentional: individual note embedding failure is non-fatal; continue building
                print(
                    f"[search_backends] Embedding failed for {md_file.name}: {e}",
                    file=sys.stderr,
                )

        self._save_index()
        print(
            f"[search_backends] Semantic index built: {len(self._id_map)} notes",
            file=sys.stderr,
        )

    def _try_import_smart_connections_index(self) -> bool:
        """
        Opportunistically read Smart Connections' .ajson index if it exists in the vault
        and was built with a compatible model. Returns True if import succeeded.
        """
        import json
        import sys

        sc_dir = Path(self._vault) / ".smart-env"
        if not sc_dir.exists():
            return False

        # SC stores model key in settings.json
        sc_settings = sc_dir / "settings.json"
        if sc_settings.exists():
            try:
                sc_cfg = json.loads(sc_settings.read_text())
                sc_model = sc_cfg.get("smart_sources", {}).get(
                    "embed_model"
                ) or sc_cfg.get("embed_model", "")
                # Normalise model name: SC may store short names like "TaylorAI/bge-micro-v2"
                if sc_model and sc_model != self._model_name:
                    print(
                        f"[search_backends] Smart Connections uses '{sc_model}', "
                        f"cyberbrain uses '{self._model_name}' — skipping SC import.",
                        file=sys.stderr,
                    )
                    return False
            except Exception:  # intentional: malformed SC settings.json is non-fatal; proceed with import attempt
                pass

        # Try multi-file mode first (one .ajson per note), then single-file
        self._load_or_create_index()
        imported = 0

        multi_dir = sc_dir / "multi"
        if multi_dir.exists():
            for ajson_file in multi_dir.glob("*.ajson"):
                imported += self._import_sc_ajson(ajson_file)
        else:
            for candidate in ["smart_sources.ajson", "smart_blocks.ajson"]:
                candidate_path = sc_dir / candidate
                if candidate_path.exists():
                    imported += self._import_sc_ajson(candidate_path)

        if imported > 0:
            self._save_index()
            print(
                f"[search_backends] Imported {imported} embeddings from Smart Connections index",
                file=sys.stderr,
            )
            return True
        return False

    def _import_sc_ajson(self, ajson_path: Path) -> int:
        """
        Parse a Smart Connections .ajson file and import vectors into usearch.
        Returns number of vectors imported.
        """
        import json
        import sys

        try:
            import numpy as np  # type: ignore[import-not-found]  # optional dependency
        except ImportError:
            return 0

        imported = 0
        try:
            raw = ajson_path.read_text(encoding="utf-8")
        except OSError:
            return 0

        for line in raw.splitlines():
            line = line.strip().rstrip(",")
            if not line:
                continue
            try:
                record = json.loads("{" + line + "}")
            except json.JSONDecodeError:
                continue

            for key, value in record.items():
                if not isinstance(value, dict):
                    continue
                # SC stores: {"path": "...", "embeddings": {"model_key": {"vec": [...]}}}
                path_in_vault = value.get("path", "")
                embeddings = value.get("embeddings", {})
                if not embeddings:
                    continue
                # Get the first (or only) model's vector
                vec_data = next(iter(embeddings.values()), {})
                vec = vec_data.get("vec", [])
                if not vec:
                    continue

                abs_path = (
                    str(Path(self._vault) / path_in_vault) if path_in_vault else ""
                )
                if not abs_path or abs_path in self._id_map:
                    continue

                try:
                    note_id = len(self._id_map)
                    self._id_map.append(abs_path)
                    self._index.add(note_id, np.array(vec, dtype=np.float32))  # type: ignore[reportOptionalMemberAccess]  # _index loaded by _load_or_create_index
                    imported += 1
                except Exception as e:  # intentional: usearch index.add can fail (dim mismatch, etc.); skip entry
                    print(
                        f"[search_backends] SC import failed for {path_in_vault}: {e}",
                        file=sys.stderr,
                    )

        return imported

    def _save_index(self) -> None:
        """Persist usearch index and manifest to disk."""
        import json
        import sys

        try:
            self._index.save(self._usearch_path)  # type: ignore[reportOptionalMemberAccess]  # _index loaded by _load_or_create_index
            manifest = {
                "model_name": self._model_name,
                "embedding_dim": self._index.ndim,  # type: ignore[reportOptionalMemberAccess]  # _index loaded by _load_or_create_index
                "id_map": self._id_map,
            }
            Path(self._manifest_path).write_text(json.dumps(manifest, indent=2))
        except Exception as e:  # intentional: usearch save or file write can fail; non-fatal, index will rebuild next time
            print(f"[search_backends] Could not save index: {e}", file=sys.stderr)

    def search(self, query: str, top_k: int = 5, **filters) -> list[SearchResult]:
        """Hybrid BM25 + semantic search with RRF fusion."""
        bm25_results = self._fts5.search(query, top_k=top_k * 2)

        # Semantic search (may fail gracefully if index not built)
        semantic_results = self._semantic_search(query, top_k=top_k * 2)

        if not semantic_results:
            # Semantic layer unavailable — return BM25 results
            for r in bm25_results:
                r.backend = "fts5 (semantic unavailable)"
            return bm25_results[:top_k]

        # RRF fusion
        return _rrf_fuse(
            bm25_results,
            semantic_results,
            top_k=top_k,
            backend_name=self.backend_name(),
        )

    def _semantic_search(self, query: str, top_k: int = 10) -> list[SearchResult]:
        """Run HNSW ANN search on query embedding. Returns empty list on any failure."""
        import sys

        try:
            self._load_or_create_index()
            if not self._id_map:
                return []

            vec = self._embed(query)
            matches = self._index.search(vec, k=min(top_k, len(self._id_map)))  # type: ignore[reportOptionalMemberAccess]  # _index loaded by _load_or_create_index

            results = []
            for match in matches:
                idx = int(match.key)
                if idx >= len(self._id_map):
                    continue
                path = self._id_map[idx]
                fm = _read_frontmatter(path)
                results.append(
                    SearchResult(
                        path=path,
                        title=fm.get("title", "") or Path(path).stem,
                        summary=fm.get("summary", ""),
                        tags=_normalise_list(fm.get("tags", [])),
                        related=_normalise_list(fm.get("related", [])),
                        note_type=fm.get("type", ""),
                        date=str(fm.get("date", ""))[:10],
                        score=float(match.distance),
                        backend="semantic",
                    )
                )
            return results
        except Exception as e:  # intentional: any semantic search failure degrades gracefully to BM25-only
            print(f"[search_backends] Semantic search error: {e}", file=sys.stderr)
            return []


# ---------------------------------------------------------------------------
# RRF fusion
# ---------------------------------------------------------------------------


def _rrf_fuse(
    bm25_results: list[SearchResult],
    semantic_results: list[SearchResult],
    top_k: int,
    backend_name: str,
    k: int = 60,
) -> list[SearchResult]:
    """
    Reciprocal Rank Fusion of two ranked lists.
    Score = 1/(k + rank_bm25) + 1/(k + rank_semantic); higher is better.
    """
    scores: dict[str, float] = {}
    by_path: dict[str, SearchResult] = {}

    for rank, result in enumerate(bm25_results, 1):
        scores[result.path] = scores.get(result.path, 0.0) + 1.0 / (k + rank)
        by_path[result.path] = result

    for rank, result in enumerate(semantic_results, 1):
        scores[result.path] = scores.get(result.path, 0.0) + 1.0 / (k + rank)
        if result.path not in by_path:
            by_path[result.path] = result

    ranked = sorted(scores, key=lambda p: scores[p], reverse=True)[:top_k]
    fused = []
    for path in ranked:
        r = by_path[path]
        r.score = scores[path]
        r.backend = backend_name
        fused.append(r)
    return fused


# ---------------------------------------------------------------------------
# Backend factory
# ---------------------------------------------------------------------------

from cyberbrain.extractors.state import SEARCH_DB_PATH as _STATE_DB_PATH

_DEFAULT_DB_PATH = str(_STATE_DB_PATH)
_DEFAULT_MODEL = "TaylorAI/bge-micro-v2"


def get_search_backend(config: dict) -> SearchBackend:
    """
    Select and return the appropriate search backend based on config.

    Config keys:
      search_backend  — "auto" | "hybrid" | "fts5" | "grep"  (default: "auto")
      embedding_model — HuggingFace model name                 (default: TaylorAI/bge-micro-v2)
    """

    vault_path = config.get("vault_path", "")
    db_path = config.get("search_db_path", _DEFAULT_DB_PATH)
    model_name = config.get("embedding_model", _DEFAULT_MODEL)
    preference = config.get("search_backend", "auto")

    def _has_fastembed() -> bool:
        try:
            import fastembed  # noqa: F401  # type: ignore[import-not-found]  # optional dependency

            return True
        except ImportError:
            return False

    def _has_usearch() -> bool:
        try:
            import usearch  # noqa: F401  # type: ignore[import-not-found]  # optional dependency

            return True
        except ImportError:
            return False

    if preference == "grep":
        return GrepBackend(vault_path)

    if preference == "fts5":
        return FTS5Backend(vault_path, db_path)

    if preference == "hybrid":
        if not _has_fastembed() or not _has_usearch():
            raise RuntimeError(
                "search_backend is set to 'hybrid' but fastembed and/or usearch are not installed. "
                "Install them: ~/.claude/cyberbrain/venv/bin/pip install fastembed usearch==2.23.0"
            )
        return HybridBackend(vault_path, db_path, model_name)

    # "auto" — try best available
    if _has_fastembed() and _has_usearch():
        return HybridBackend(vault_path, db_path, model_name)

    if _has_fastembed() or True:  # FTS5 is always available (stdlib sqlite3)
        return FTS5Backend(vault_path, db_path)

    return GrepBackend(vault_path)


# ---------------------------------------------------------------------------
# Shared helpers (canonical implementations live in frontmatter.py)
# ---------------------------------------------------------------------------

from cyberbrain.extractors.frontmatter import derive_id as _derive_id
from cyberbrain.extractors.frontmatter import normalise_list as _normalise_list
from cyberbrain.extractors.frontmatter import read_frontmatter as _read_frontmatter
