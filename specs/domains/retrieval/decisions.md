# Decisions: Retrieval

## D-1: Three-tier search backend with RRF fusion for hybrid mode
- **Decision**: Implement three backends (grep, fts5, hybrid) with automatic cascade selection. Hybrid mode fuses BM25 (FTS5) and HNSW semantic results via Reciprocal Rank Fusion (k=60).
- **Rationale**: Lean architecture (no external servers) while allowing progressive capability upgrade. Grep requires no dependencies; fts5 uses stdlib sqlite3; hybrid adds fastembed and usearch only when installed.
- **Source**: specs/plan/architecture.md (Search Architecture section)
- **Status**: settled

## D-2: SQLite for all derived data; no external database servers
- **Decision**: FTS5 index, vector storage, and relation table all live in `search-index.db` (SQLite). No external database server.
- **Rationale**: "SQLite over Postgres. Flat files over daemons." (GP-6 / Constraint C4). Precomputed vectors into SQLite is an acceptable compromise for single-user scale.
- **Assumes**: Single-user deployment. If hosted/multi-tenant deployment is pursued, this constraint is explicitly tagged for revisitation.
- **Source**: specs/steering/constraints.md (C4); specs/steering/interview.md (initial interview)
- **Status**: settled (may revisit for hosted deployment)

## D-3: Default embedding model — TaylorAI/bge-micro-v2 (384-dim, metadata-only)
- **Decision**: Embed `"{title}. {summary} {tags}"` using TaylorAI/bge-micro-v2. Opportunistically import vectors from Smart Connections `.ajson` index when model matches.
- **Rationale**: Micro model keeps dependencies and index size small while providing useful semantic similarity. Metadata-only embedding focuses similarity on conceptual identity.
- **Source**: specs/plan/architecture.md (Embedding Strategy section)
- **Status**: settled

## D-4: Graph expansion deferred; validate retrieval improvements first
- **Decision**: Knowledge graph ML approaches (additional edge types, graph databases) are deferred until RAG synthesis and retrieval quality improvements are validated.
- **Rationale**: "Defer graph expansion until other search improvements are validated. Want to see if KG is needed after RAG synthesis and retrieval are improved." (interview, cycle 1 refinement). Graph ML at vault scale was also found non-viable in WI-003 research.
- **Source**: specs/steering/interview.md (Refinement Interview 2026-03-09, first refinement)
- **Status**: settled (deferred)

## D-5: Search backend cache in shared.py has no invalidation path
- **Decision**: `shared.py._get_search_backend()` uses a module-level global with no cache invalidation. If config changes mid-session via `cb_configure`, the cached backend is stale.
- **Rationale**: Not recorded. This is an acknowledged design tension (T6), not a deliberate decision.
- **Source**: specs/plan/architecture.md (Design Tension T6)
- **Status**: settled (tension acknowledged, not yet resolved)

## D-6: Auto-indexing strategy — lazy reindex on cb_recall plus SessionEnd hook complement
- **Decision**: Recommended approach (WI-039 research): trigger index rebuild lazily on `cb_recall` invocation, complemented by a SessionEnd hook. No persistent daemon. Research recorded at specs/steering/research/auto-indexing-strategy.md.
- **Rationale**: Lazy reindex on the retrieval path catches stale index entries at the point they matter. SessionEnd hook provides a background complement without blocking any user operation. A persistent daemon was evaluated and rejected as incompatible with GP-6 (lean architecture).
- **Source**: specs/archive/cycles/002/decision-log.md (DL8); specs/steering/research/auto-indexing-strategy.md
- **Status**: provisional (research complete; WI-045 implementation not started as of cycle 002)

## D-7: cb_read extended with multi-identifier, synthesize, and max_chars_per_note parameters
- **Decision**: `cb_read` gains: pipe `|` delimited multi-identifier support (up to 10 identifiers), `synthesize: bool` parameter, and `max_chars_per_note: int` (default 2000, 0 = no truncation). Empty-query synthesis uses a fallback message. Pipe `|` is the delimiter because it does not appear in Obsidian filenames.
- **Rationale**: Design approved in WI-041. `max_chars_per_note` was changed from hardcoded to an explicit parameter at user request. Net tool count remains 11.
- **Source**: specs/archive/cycles/002/decision-log.md (DL10); specs/plan/retrieval-interface-design.md
- **Status**: provisional (design approved; WI-046 implementation not started as of cycle 002)
