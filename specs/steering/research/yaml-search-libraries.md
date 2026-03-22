---
topic: YAML and search/embedding library evaluation
date: 2026-03-21
skill: refine
---

## Summary

The current stack (PyYAML + ruamel.yaml + SQLite FTS5 + fastembed + usearch 2.23.0) is defensible and mostly current. The two-library YAML situation is not ideal on the surface, but has a clear justification: ruamel.yaml is used exclusively for round-trip writes where comment and order preservation matters, while PyYAML is used for read-only frontmatter parsing. These are genuinely distinct operations. The search and embedding libraries are actively maintained at their pinned versions. The only notable maturity concern is sqlite-vec, which is still pre-v1 and not a safe drop-in replacement for usearch without explicit testing.

## Key Facts

**YAML Libraries**

- PyYAML 6.x: Based on YAML 1.1. `yaml.safe_load()` is the standard read-only parse path. Does not preserve comments or key order on round-trip. Latest: 6.0.2 (2024). Actively maintained.
- ruamel.yaml: Based on YAML 1.2. The only Python library that correctly preserves comments, key order, and quoting on round-trip. 2.5M monthly installs, growing. Latest: 0.18.x (2024-2025). Actively maintained.
- Cyberbrain's actual split: PyYAML (`yaml.safe_load`) is used in `frontmatter.py` and `manage.py` for read-only parsing. ruamel.yaml is used in `autofile.py` for exactly two write operations: updating the `cb_modified` timestamp and merging `related` fields into existing notes. This is not redundancy — it is two different operations with different fidelity requirements.
- python-frontmatter: Latest 1.1.0, released January 16, 2024. Uses PyYAML internally. Classified inactive by Snyk (no new releases in >12 months as of early 2025). Adds a dependency for functionality cyberbrain already implements manually in `frontmatter.py`. Not a meaningful upgrade.
- StrictYAML: Deliberately strips many YAML features for safety. Incompatible with standard Obsidian frontmatter format. Not applicable.

**Text Search**

- SQLite FTS5: Part of stdlib `sqlite3`. BM25 ranking. Zero additional dependencies. Current implementation uses content-based triggers to keep the FTS index synchronized with the `notes` table.
- tantivy-py: Python bindings for Rust Tantivy (Lucene-inspired). Latest: 0.25.1, December 2, 2025. Actively maintained via PyO3. Faster than FTS5 on large corpora. Adds a Rust-compiled binary dependency. Overkill at the 2K–10K note scale of a personal vault.
- sqlite-vec: SQLite C extension for vector ANN search. Latest: v0.1.7, March 17, 2026. Still pre-v1 with explicit breaking-change warnings in the README. Can coexist with FTS5 in the same database, enabling hybrid search without a separate vector store. Author has published a working FTS5 + sqlite-vec + RRF hybrid example.

**Embedding Libraries**

- fastembed 0.7.4 (December 5, 2025): Qdrant-maintained. Uses ONNX Runtime, not PyTorch. No GPU required. No multi-GB install. Regular releases. v0.7.4 explicitly fixed: "don't do any network calls if model is loaded from cache."
- sentence-transformers: PyTorch-based. Wider model selection. Requires PyTorch (multi-GB). Conflicting benchmark reports vs. fastembed on Apple Silicon — unconfirmed which is faster at this use case's scale.
- Default model `TaylorAI/bge-micro-v2`: 384-dim, ~22.9 MB. Compatible with Obsidian Smart Connections' embedding format, enabling the existing SC index import path.

**Vector Index**

- usearch 2.23.0: Latest stable release January 11, 2026. Labeled Production/Stable. Breaking changes planned for v3 (no timeline found). HNSW. Smaller codebase than FAISS. Used for the current `HybridBackend` HNSW index.
- hnswlib: Last release v0.8.0 (December 2024). Classified inactive by Snyk — no new PyPI releases in past 12 months. Effectively maintenance-only.
- voyager (Spotify): v2.1.1, September 23, 2024. No 2025 releases. Used in production at Spotify. Based on hnswlib with 8-bit memory efficiency. Not actively developed.
- sqlite-vec as vector storage: Could replace usearch for both storage and ANN. Pre-v1 risk. At 2K–10K notes, flat cosine scan is viable even without HNSW. Would consolidate vector storage into the existing SQLite DB.

## Recommendations

**Option 1: Keep current stack as-is**
- Pros: Working, tested. usearch 2.23.0 is the latest stable release. fastembed 0.7.4 is current. FTS5 is zero-dependency. The PyYAML/ruamel.yaml split is doing two distinct jobs, not duplicating effort.
- Cons: Two YAML libraries in `pyproject.toml` looks like debt to contributors unfamiliar with the rationale. usearch v3 will require a migration when it arrives.
- When to use: No active search quality complaints, no install size pressure, no plans to change the semantic optional dependency group.

**Option 2: Replace usearch with sqlite-vec**
- Pros: Consolidates vector storage into the existing SQLite database. Eliminates the separate `.usearch` binary file and the `id_map` manifest JSON. Reduces the `[semantic]` optional dependency from two packages to one (just fastembed). Simplifies `HybridBackend`.
- Cons: sqlite-vec is pre-v1 with explicit breaking-change warnings. Requires rewriting `_embed_note`, `_load_or_create_index`, `_save_index`, and `_semantic_search`. The Smart Connections embedding import path would also need rework.
- When to use: When usearch v3 breaking changes land and a migration is required anyway, or when reducing file-system artifacts and dependency count is a priority. Not before sqlite-vec reaches v1.

**Option 3: Consolidate on ruamel.yaml only (drop PyYAML)**
- Pros: Single YAML library. ruamel.yaml supports `YAML(typ='safe').load()` which is functionally equivalent to `yaml.safe_load()`.
- Cons: ruamel.yaml is a heavier import for the read-only case. API is more verbose. `frontmatter.py` and `manage.py` would need updating.
- When to use: If dependency count matters cosmetically. The functional difference is negligible; this is cleanup only.

**Option 4: Drop ruamel.yaml, rewrite round-trip edits manually**
- Pros: Removes one dependency.
- Cons: The two operations that use ruamel.yaml — updating `cb_modified` and merging `related` list fields — are precisely the use case where hand-rolled regex field updates are fragile and error-prone. Not a safe tradeoff.
- When to use: Not recommended.

## Risks

- **usearch v3 breaking changes**: Explicitly noted in GitHub, no timeline. The `==2.23.0` pin prevents accidental upgrade. When v3 releases, `HybridBackend` will need audit before upgrading.
- **sqlite-vec pre-v1 instability**: API and on-disk format may change between releases. Not suitable as a quiet upgrade to the existing stack.
- **fastembed cold-start network dependency**: Models are downloaded on first use. If the environment has no internet on first run (before the model cache is warm), the `[semantic]` optional group will fail. Must be documented in installation instructions.
- **hnswlib**: Effectively abandoned. Not a viable alternative for new work.
- **voyager**: Stable but no 2025 development. Not an improvement over usearch for this use case.
- **python-frontmatter**: Not a current dependency. If considered in future, its inactive maintenance and PyYAML dependency add without subtracting anything cyberbrain doesn't already handle.
- **fastembed vs. sentence-transformers on Apple Silicon**: Conflicting benchmark reports exist. The current design (metadata-only embedding, not full-body) limits performance exposure regardless of which library is faster at body embedding.

## Sources

- `/Users/dan/code/cyberbrain/pyproject.toml`
- `/Users/dan/code/cyberbrain/src/cyberbrain/extractors/frontmatter.py`
- `/Users/dan/code/cyberbrain/src/cyberbrain/extractors/search_backends.py`
- `/Users/dan/code/cyberbrain/src/cyberbrain/extractors/search_index.py`
- `/Users/dan/code/cyberbrain/src/cyberbrain/extractors/autofile.py`
- usearch PyPI — latest 2.23.0, January 11, 2026
- fastembed PyPI — latest 0.7.4, December 5, 2025
- python-frontmatter PyPI — latest 1.1.0, January 16, 2024
- sqlite-vec GitHub — v0.1.7, March 17, 2026, pre-v1
- tantivy-py GitHub — v0.25.1, December 2, 2025
- voyager GitHub releases — v2.1.1, September 23, 2024
- hnswlib GitHub — v0.8.0, December 2024, inactive
- ruamel.yaml PyPI
