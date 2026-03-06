# Enhanced Retrieval Architecture

**Status:** Draft
**Date:** 2026-03-03
**Scope:** `/cb-recall` skill and `cb_recall` MCP tool
**Approach:** Layered. Phase 1 is zero-dependency improvements to precision and output quality. Phase 2 adds a semantic retrieval layer. Each phase is independently deployable and incrementally valuable.

---

## 1. Problem Statement

The current retrieval implementation does keyword grep across vault notes and returns the top-N results by match count and recency. It works for exact-match queries. It fails in three ways:

**Poor precision:** Any single keyword match qualifies a note as a candidate. A query for "Redis cache eviction" returns notes that mention "Python" once alongside unrelated content. Notes 3-8 in the result set are often noise that wastes context window and reduces signal.

**Poor recall (semantic gap):** A note titled "Memcached connection pool tuning" does not surface for a query about "cache eviction policy" even though it directly addresses the question. Synonym and concept matching are absent.

**Bulk injection:** The top 1-2 notes get their full body injected regardless of how much of that body is relevant to the query. A 400-word note with one relevant paragraph injects 400 words when 60 would suffice.

The experience goal from the v1 spec — "using this feels like having an excellent memory, not like managing a system" — requires high signal-to-noise in recalled content. The current implementation is a foundation that needs precision and semantic layers built on top.

---

## 2. Design Goals

**G1 — High signal-to-noise above all.** What gets injected into the context window must be directly useful. Irrelevant or diluted content is worse than nothing — it consumes context tokens and can mislead the LLM.

**G2 — Fast at the point of use.** Recall is invoked mid-conversation. Sub-second retrieval is required. Synthesis is acceptable if it adds real value, but latency budget is tight.

**G3 — Degrade gracefully.** The semantic index is optional infrastructure. When it does not exist (new install, index not yet built), fall back to the current grep-based implementation. The user should never hit an error because the index is absent.

**G4 — No heavy dependencies for the grep path.** Phase 1 improvements add zero new packages. Phase 2 adds lightweight dependencies only — no PyTorch, no server processes.

**G5 — Both paths matter equally.** The SKILL.md (Claude Code) and MCP (Claude Desktop) paths must both improve. The SKILL.md path can leverage the in-context LLM for free. The MCP path cannot — improvements there must be structural.

---

## 3. Architecture Overview

Retrieval is enhanced in three phases:

```
Phase 1 — Precision improvements (zero dependencies)
  ├── Relevance threshold: require minimum term hits before a note qualifies
  ├── Paragraph-level compression: inject only relevant paragraphs, not full body
  ├── Explicit LLM scoring in SKILL.md: 1-5 score per candidate, threshold at 3
  └── Synthesis trigger in SKILL.md: unify multi-note results when overlap is high

Phase 2 — Semantic retrieval layer
  ├── Embedding index: fastembed + sqlite-vec, stored at ~/.claude/cyberbrain/search-index.db
  ├── Hybrid search: BM25 (keyword) + semantic (vector) fused via RRF
  ├── Index management: incremental updates on note write, content-hash invalidation
  └── Graceful fallback: use grep path when index is absent or stale

Phase 3 — MCP synthesis (optional, adds latency)
  └── synthesize parameter on cb_recall: triggers claude -p synthesis pass when set
```

The SKILL.md path and MCP path diverge in Phase 1 because the SKILL.md path has an LLM in context and the MCP path does not. Phase 2 brings them to parity on retrieval quality. Phase 3 optionally closes the synthesis gap for the MCP path.

---

## 4. Phase 1: Zero-Dependency Precision Improvements

### 4.1 Relevance Threshold (both paths)

**Problem:** Single-term matches on common words are the main source of noise.

**Change:** For queries with 3 or more terms, require at least 2 distinct terms to match before a note enters the candidate set.

```python
# server.py — after building `found` dict at line ~325
min_hits = 2 if len(terms) >= 3 else 1
found = {p: v for p, v in found.items() if v[0] >= min_hits}
```

The SKILL.md path gets this for free via LLM scoring in 4.3 — the threshold there is semantic (score < 3 = dropped), which is strictly better. The code change above applies to the MCP path only.

### 4.2 Paragraph-Level Compression (MCP path)

**Problem:** The MCP path injects the full body of the top 2 matching notes. Most of the body is often not relevant to the specific query.

**Change:** Instead of injecting the full body, extract only the paragraphs that contain at least one query term. Fall back to full body if no paragraphs match.

```python
# server.py — replace top-2 body injection at line ~376
if idx < 2:
    body = content[end + 4:].strip() if content.startswith("---") else content
    paragraphs = [p.strip() for p in body.split('\n\n') if p.strip()]
    relevant = [p for p in paragraphs if any(t.lower() in p.lower() for t in terms)]
    card_lines.append(f"\n{'\n\n'.join(relevant) if relevant else body}")
```

This is a proxy for contextual compression — it works without an LLM and degrades gracefully. A 400-word note typically yields 50-100 words of compressed output for a specific query.

### 4.3 Explicit Candidate Scoring (SKILL.md path)

**Problem:** Step 5 of SKILL.md currently says "identify the 1–2 most directly relevant." This is implicit — Claude makes a judgment call but the criteria are not specified. Different queries get different treatment.

**Change:** Make scoring explicit. After reading frontmatter summary cards for all candidates:

```
Score each note 1-5 for relevance to the query:
  5 — Directly and completely answers the query
  4 — Directly relevant; addresses core of query
  3 — Partially relevant; contains useful context
  2 — Marginally relevant; shares topic but not query
  1 — Not relevant; keyword match only

Keep all notes scoring 3 or above, up to a maximum of 3 notes.
Drop notes scoring 1-2 entirely.
```

This turns implicit judgment into a reproducible precision gate. It also produces a score that drives the synthesis trigger in 4.4.

### 4.4 Synthesis Trigger (SKILL.md path)

**Problem:** When multiple notes partially address the same query, injecting all of them raw creates noise — the user receives fragmented, overlapping context instead of a coherent answer.

**Change:** After scoring, apply a synthesis trigger before injecting:

**Trigger synthesis when any of these are true:**
- Three or more notes score ≥ 3 on the same query
- The query contains aggregative language: "what do I know about", "summarize", "what patterns", "overview", "all"
- No note scores 5 (nothing directly answers the query — all results are partial)

**Synthesis behavior:**
Generate a unified answer to the query from the scored notes, then append the raw note cards as sources. The synthesis is generated in-context by Claude — zero additional LLM calls, zero latency cost.

```
## From your knowledge vault [synthesized]

[Unified answer to the query, drawing from all relevant notes]

---
### Supporting notes

[Note cards as usual]
```

**Inject raw (no synthesis) when:**
- One note scores 5 (a single note directly answers the query — inject it, nothing to synthesize)
- Only one or two notes score ≥ 3 and no aggregative language in query
- The query is a simple lookup ("what was the Redis config we used")

Synthesis should feel like a decision Claude makes naturally, not a mode the user has to trigger. The scoring output from 4.3 provides the input.

---

## 5. Phase 2: Semantic Retrieval Layer

### 5.1 Dependency Stack

| Component | Library | Rationale |
|---|---|---|
| Embedding model | `BAAI/bge-small-en-v1.5` | Best retrieval quality at small size; retrieval-optimized, not classification-optimized |
| Embedding runtime | `fastembed` | ONNX Runtime backend — no PyTorch, no CUDA. ~50MB package + ~127MB model download on first use. Cached at `~/.cache/fastembed/` |
| Vector + metadata store | `sqlite-vec` | Zero external dependencies (pure C extension). Single `.db` file. SQL API enables co-location of vectors, note metadata, and content hashes in one place. Trivial upsert-by-ID |
| BM25 lexical search | `bm25s` | numpy + scipy only. Fast. Better-maintained than `rank_bm25`. Produces ranked results for RRF fusion |
| Score fusion | RRF (hand-rolled) | ~15 lines. Reciprocal Rank Fusion fuses by rank position — no score normalization required |

**Total new install footprint:** ~200MB including model cache. No PyTorch, no server processes.

**Optional dependency pattern:** Phase 2 components are gated on import availability. If `fastembed` or `sqlite_vec` are not installed, the system falls back to Phase 1 grep-based retrieval silently. The user can opt in by running:

```bash
pip install fastembed sqlite-vec bm25s
```

A `cb_recall --build-index` command (or equivalent config option) triggers the initial index build.

### 5.2 What Gets Embedded

Each note is embedded as a concatenation of its highest-signal frontmatter fields:

```python
embed_text = f"{title}. {summary}. {' '.join(tags)}"
```

The full body is **not** embedded. Rationale: the `title` and `summary` fields are LLM-generated during extraction and explicitly optimized for search retrieval (the extraction prompt says so). The body provides context once a note is retrieved, not signal for whether to retrieve it. Embedding the full body dilutes the signal with prose that was not written for search.

### 5.3 Index Schema

The index is a single SQLite file at `~/.claude/cyberbrain/search-index.db`:

```sql
CREATE TABLE notes (
    id          TEXT PRIMARY KEY,   -- UUID from frontmatter
    path        TEXT NOT NULL,      -- absolute vault path
    content_hash TEXT NOT NULL,     -- SHA-256 of raw file content
    title       TEXT,
    summary     TEXT,
    tags        TEXT,               -- JSON array as stored
    type        TEXT,
    scope       TEXT,
    project     TEXT,
    date        TEXT,
    embedding   BLOB                -- float32 vector, 384 dims (sqlite-vec format)
);
```

The `content_hash` column is the incremental update mechanism. On every index sync:
1. Walk the vault and compute SHA-256 of each note's raw text
2. Compare against stored hashes
3. Re-embed only notes where the hash has changed or the note is new
4. Delete rows for notes that no longer exist on disk

This makes incremental updates cheap: a typical session that modifies 2-3 notes recomputes 2-3 embeddings.

### 5.4 Index Lifecycle

**Initial build:** Triggered manually (`cb_recall --build-index`) or on first recall attempt when `--auto-index` is set in config. Embeds all notes in the vault. For 1000 notes at ~5ms/note on CPU, initial build takes ~5 seconds.

**Incremental update:** Triggered automatically after every note write by `extract_beats.py`. The write pipeline calls `update_search_index(note_path)` after successfully writing a note. This keeps the index current without requiring a full rebuild.

**Stale index handling:** If the index `mtime` is older than the vault's most recently modified note, warn the user in recall output: `[Search index may be out of date — run cb_recall --build-index to refresh]`. Do not block retrieval.

**Index location:** `~/.claude/cyberbrain/search-index.db`. This is outside the vault — the index is derived data, not vault content. Users should not sync it with their vault.

### 5.5 Hybrid Search and RRF Fusion

The retrieval pipeline executes two independent searches and fuses them:

```python
def hybrid_recall(query: str, vault_path: str, top_k: int = 20) -> list[str]:
    # 1. BM25 lexical search
    bm25_ranks = bm25_search(query, corpus, top_k=top_k)        # returns ordered list of note IDs

    # 2. Vector semantic search
    query_embedding = embed(query)
    vec_ranks = sqlite_vec_search(query_embedding, top_k=top_k) # returns ordered list of note IDs

    # 3. Reciprocal Rank Fusion
    scores = {}
    k = 60  # standard RRF constant
    for rank, note_id in enumerate(bm25_ranks):
        scores[note_id] = scores.get(note_id, 0) + 1 / (k + rank + 1)
    for rank, note_id in enumerate(vec_ranks):
        scores[note_id] = scores.get(note_id, 0) + 1 / (k + rank + 1)

    return sorted(scores, key=scores.get, reverse=True)[:top_k]
```

The BM25 index is built at query time from the in-memory note corpus (title + summary + tags fields). At <2000 notes, this takes ~2ms. There is no need to persist the BM25 index.

**Why RRF over score normalization:** BM25 scores and cosine similarity scores have different scales and distributions. Normalizing them to combine is non-trivial and fragile. RRF uses only rank positions, which makes fusion robust by construction. The `k=60` constant is standard and well-studied — it controls how much weight is given to top-ranked results vs. lower-ranked ones.

**Retrieval size:** Retrieve top-20 from each ranker, fuse, return top-8 candidates to the ranking/scoring step. At <2000 notes, over-retrieving is cheap and improves fusion quality.

### 5.6 Graceful Fallback

The semantic layer wraps the existing grep pipeline — it does not replace it. The retrieval entry point checks for index availability:

```python
def recall(query, vault_path, top_k):
    if index_available(vault_path) and dependencies_installed():
        candidates = hybrid_recall(query, vault_path, top_k)
    else:
        candidates = grep_recall(query, vault_path, top_k)
    # Phase 1 scoring and compression applied to candidates regardless of path
    return score_and_compress(candidates, query)
```

This means Phase 1 improvements (threshold, compression, scoring, synthesis) apply to both the grep and semantic paths. Phase 2 improves which candidates are returned; Phase 1 improves what is done with them.

---

## 6. Phase 3: MCP Synthesis (Optional)

The MCP path currently has no LLM step. Synthesis requires calling `claude -p` as a subprocess, which adds latency (~2-5 seconds). This is acceptable for an opt-in parameter, not as default behavior.

**Change:** Add a `synthesize` parameter to `cb_recall` in `server.py`:

```python
def cb_recall(
    query: str,
    max_results: int = 5,
    synthesize: bool = False,   # new
) -> str:
```

When `synthesize=True`:
1. Run retrieval normally, collect top-N note cards
2. Call LLM backend with: retrieved note content + query + synthesis prompt
3. Return synthesized answer followed by note cards as sources

The synthesis prompt mirrors the SKILL.md synthesis trigger (section 4.4) — unified answer first, supporting sources second.

**Default:** `synthesize=False`. The MCP path remains fast by default. Users or the MCP client (Claude Desktop) can pass `synthesize=True` for aggregative queries.

---

## 7. Configuration Changes

One new optional config key:

```json
{
  "search_index": "auto"
}
```

| Value | Behavior |
|---|---|
| `"auto"` | Use semantic index if available; fall back to grep if not |
| `"semantic"` | Require semantic index; error if unavailable |
| `"grep"` | Always use grep path, skip semantic index entirely |
| `(absent)` | Same as `"auto"` |

A `build_index_on_install` boolean (default `false`) triggers initial index build during `install.sh` if fastembed is available. Disabled by default to avoid surprising users with a 5-second install step.

---

## 8. Not in Scope

**Cross-encoder reranking:** Adds 50-200ms latency at a scale (< 2000 notes) that doesn't warrant it. The hybrid BM25 + semantic approach returns high-quality results without a reranking step.

**HyDE (Hypothetical Document Embeddings):** Requires an LLM call before retrieval — unsuitable for the MCP path. Not warranted for a personal corpus where query author and note author are the same person. The SKILL.md path already does contextual query inference (Step 2) which achieves the same goal.

**Sub-note chunking:** Notes are 200-500 words — already at the ideal retrieval granularity. Chunking adds index complexity with no quality benefit at this size.

**Note graph / wikilink traversal:** Retrieval based on following `[[wikilinks]]` between notes could surface related context not directly matched by search. Explicitly deferred — useful but adds significant complexity; the `related` frontmatter field is the hook for this in a future iteration.

---

## 9. Implementation Order

**Phase 1** (no new dependencies, ship first):
1. `server.py` — minimum term-hit threshold (3 lines)
2. `server.py` — paragraph-level body compression for top-2 results (8 lines)
3. `skills/cb-recall/SKILL.md` — explicit 1-5 candidate scoring (Step 5 rewrite)
4. `skills/cb-recall/SKILL.md` — synthesis trigger logic (Step 5 addition)

**Phase 2** (semantic layer, ship as optional feature):
5. `extractors/search_index.py` — new module: index build, incremental update, hybrid search, RRF fusion
6. `extractors/extract_beats.py` — call `update_search_index()` after each note write
7. `mcp/server.py` — wire `hybrid_recall()` into `cb_recall()`, fallback to grep
8. `skills/cb-recall/SKILL.md` — surface index-based scoring to replace grep-based pass ranking
9. `install.sh` — add fastembed/sqlite-vec/bm25s as optional install step

**Phase 3** (MCP synthesis, optional):
10. `mcp/server.py` — add `synthesize` parameter and backend call
