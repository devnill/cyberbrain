# Module: Search

## Scope

Search backends, index lifecycle management, and score fusion. Provides pluggable search with three tiers (grep, fts5, hybrid) and a coordination layer for incremental index updates.

NOT responsible for: note writing (vault module), MCP tool response formatting (mcp-tools module).

## Provides

### From `search_backends.py`:

- `SearchResult` dataclass — `{path, title, summary, tags, related, note_type, date, score, snippet, backend}`
- `SearchBackend` protocol — `search()`, `index_note()`, `build_index()`, `backend_name()`
- `GrepBackend` — Zero-dependency keyword search via subprocess grep. No index. Rank by hit count + mtime.
- `FTS5Backend` — SQLite FTS5 BM25 search. Column weights: title=10, summary=5, tags=3, body=1. Prefix matching (`term*`). Content-hash dedup on index. Relations table. Stale note pruning.
- `HybridBackend` — FTS5 + fastembed/usearch HNSW semantic search, fused via RRF (k=60). Metadata-only embedding (`title. summary tags`). Smart Connections index import. Model-aware manifest with auto-rebuild on model change.
- `get_search_backend(config) -> SearchBackend` — Factory function. Selects backend based on `config["search_backend"]` and dependency availability. Auto cascades: hybrid -> fts5 -> grep.
- `_rrf_fuse(bm25_results, semantic_results, top_k, backend_name, k=60) -> list[SearchResult]` — Reciprocal Rank Fusion of two ranked lists.

### From `search_index.py`:

- `update_search_index(note_path, metadata, config)` — Index/re-index a single note. Called after each write. Non-fatal on failure.
- `build_full_index(config)` — Full index rebuild from vault. Incremental (skips unchanged notes).
- `active_backend_name(config) -> str` — Returns name of active backend for display.

## Requires

- `read_frontmatter(path)`, `normalise_list(value)`, `derive_id(note_path)` (from: extraction/frontmatter) — Frontmatter parsing for index builds. Has inline fallback implementations.

## Boundary Rules

- Search index is derived data stored at `~/.claude/cyberbrain/search-index.db` — outside the vault.
- Index staleness is non-fatal: searches return results from whatever state the index is in.
- `update_search_index()` failures are logged and swallowed — search index is an acceleration layer.
- FTS5 content-hash dedup: `SHA-256(file_content)` stored in `notes.content_hash`. Re-index only on change.
- HybridBackend stores usearch index at `~/.claude/cyberbrain/search-index.usearch` with a JSON manifest recording model name, embedding dimension, and id_map.
- HybridBackend validates manifest model_name against config — auto-rebuilds if model changed.
- Smart Connections import is opportunistic: only if `.smart-env/` exists in vault and model matches.
- `search_index.py` caches backend instances per `(vault_path, backend_key, embedding_model)` tuple.
- Body text stored in FTS index is capped at 50,000 chars.
- BM25 query uses prefix matching: each term gets `*` appended.
- FTS5 special characters in queries are replaced with spaces.

## Internal Design Notes

- Files: `extractors/search_backends.py` (825 lines), `extractors/search_index.py` (121 lines)
- SQLite schema: `notes` table, `notes_fts` virtual table (content-sync triggers), `relations` table
- Default embedding model: `TaylorAI/bge-micro-v2` (384-dim, ~22.9 MB)
- Optional deps: `fastembed`, `usearch` (for hybrid backend)
- `GrepBackend.search()` spawns one `grep -r -l` subprocess per search term
- Usearch index does a warm-up zero-vector search during init to force page faults
