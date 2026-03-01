# SP12: Retrieval Architecture — Beyond Grep

**Status:** Research complete
**Date:** 2026-02-27
**Scope:** Semantic search options, token efficiency, Obsidian's role

---

## Part 1: Current Retrieval Path Analysis

### kg-recall (SKILL.md)

The slash command uses Claude's in-context tools (Bash, Read, Glob — no subprocess spawning). The retrieval logic is described as a multi-pass grep:

1. **Keyword extraction from query** — the query string is used as-is for grep terms
2. **Step 1:** `grep -r -l --include="*.md" -i QUERY $VAULT_PATH | head -20` — file-level match on any query term in summary/title
3. **Step 2:** `grep -r -l --include="*.md" "tags:.*QUERY" $VAULT_PATH | head -10` — tag-specific match
4. **Step 3:** Another body-content grep sweep
5. **Step 4:** Project-specific preference — prefer files from the current project's `vault_folder`
6. **Step 5:** Recency bias — sort by modification time, prefer last 30 days
7. **Read top 5 matching documents** — full content of each
8. **Synthesize** — LLM produces a structured context block from what it read

The instruction says "If a document's `summary` field alone is sufficient, you may skip reading the full body" — but in practice, the LLM reads the full file because grep returns file paths, not parsed frontmatter, and reading the full file is simpler than parsing YAML frontmatter first.

**Key problems:**
- Purely lexical: query "database connection pooling" misses a note titled "PgBouncer configuration decisions" unless those exact words appear in the body
- No ranking by relevance — only recency among matched files
- Loads full note content regardless of whether it's needed
- Grep is run multiple times on the same directory (inefficient, though fast at small scale)
- No deduplication across the three grep passes (same file could appear in results from multiple passes)

### MCP kg_recall (mcp/server.py)

The MCP implementation is different and notably simpler:

```python
terms = [w for w in re.split(r"\W+", query) if len(w) >= 3][:8]

found: dict[str, float] = {}
for term in terms:
    result = subprocess.run(
        ["grep", "-r", "-l", "--include=*.md", "-i", term, vault_path],
        capture_output=True, text=True,
    )
    for path in result.stdout.strip().splitlines():
        found[path] = os.path.getmtime(path)

ranked = sorted(found, key=found.get, reverse=True)[:max_results]

for path in ranked:
    content = Path(path).read_text(encoding="utf-8")
    parts.append(f"### {rel}\n\n{content[:3000]}")
```

Key differences from SKILL.md:
- Tokenizes the query into individual words (3+ chars, max 8 terms)
- Runs one grep per token, not one grep per "step"
- Ranks solely by recency (mtime) — no project preference, no multi-pass prioritization
- Returns up to `max_results` notes (default 5), truncated at 3000 chars each
- No tag-specific pass, no summary-vs-body distinction

**Both paths share the same fundamental problem:** keyword match only, ranked by recency, full content injected.

---

## Part 2: Semantic Search Options

### Obsidian Plugins

**Smart Connections**

Runs entirely inside Obsidian. Uses Transformers.js (a JavaScript port of the Transformers library) to embed notes locally using a bundled quantized sentence-transformer model (~20MB). Can optionally use OpenAI embeddings instead. Similarity results surface in the Obsidian sidebar.

- No external API. Cannot be queried from Python, from the hook, or from the MCP server.
- The embedding data is written to disk (`.smart-env/` JSON files) but in an undocumented format not designed for external consumption.
- Setup complexity: 2/5
- Privacy: local
- **Verdict for this use case: Not usable.** The retrieval path runs outside Obsidian. Smart Connections is an Obsidian-UI-only tool and cannot be integrated into kg_recall without building an Obsidian plugin to bridge the gap — a significant architectural commitment.

**Omnisearch**

Enhanced full-text search using BM25 ranking. Significantly better than Obsidian's built-in search: fuzzy matching, better relevance ranking, excerpt snippets in results, search-as-you-type. Does NOT do semantic or vector search — it is a lexical search improvement.

The key differentiator: Omnisearch exposes an **HTTP API on localhost** (default port 51361). Querying from Python is a `requests.get("http://localhost:51361/search?q=query")` call. Results include file paths and ranked excerpt snippets.

- Setup complexity: 2/5 (install plugin, enable Local REST API in settings)
- Privacy: local
- What it adds over grep: better ranking (BM25 vs raw match), fuzzy tolerance, excerpts already extracted, single query instead of multi-pass
- **Verdict:** A genuine improvement over the current grep approach for zero implementation cost — but still lexical only. Worth considering as a quick win (Phase A) while semantic search is built. Requires Obsidian to be running, which is a dependency the current system does not have.

**Text Generator plugin** — designed for LLM-assisted writing, not retrieval. Not relevant to this use case.

### Local Embedding + Vector Search

#### Ollama with nomic-embed-text

Ollama is a local model server for macOS/Linux. `nomic-embed-text` is a 768-dimensional embedding model (8192 token context, Apache 2.0 license) available via Ollama. Competitive with OpenAI ada-002 on MTEB benchmarks, specifically strong on retrieval tasks.

- Installation: `brew install ollama && ollama pull nomic-embed-text` — two commands, ~270MB download
- API: `POST localhost:11434/api/embed` with JSON body — no SDK required, just `requests`
- Latency per query embedding: ~5–15ms on Apple Silicon (Metal-accelerated)
- Batch embedding 1000 notes: ~10–30 seconds one-time, then incremental on new notes only
- Setup complexity: 2/5
- Privacy: fully local
- Dependency: requires Ollama running as a background service
- **Verdict:** Excellent option if the user already has or is comfortable running Ollama. Zero cost, fast, local. The background service requirement is the only friction point.

#### sentence-transformers (Python)

Python library (`pip install sentence-transformers`) that runs transformer embedding models in-process. No separate server required.

Models for technical content:
- `all-MiniLM-L6-v2` — 384-dim, ~80MB, fastest, good general quality
- `all-mpnet-base-v2` — 768-dim, ~420MB, better quality, 2–3x slower
- `BAAI/bge-large-en-v1.5` — 1024-dim, ~1.3GB, top MTEB scores, best quality, 5x slower than MiniLM
- `nomic-ai/nomic-embed-text-v1.5` — same model as Ollama's nomic-embed-text, runs in-process

For a technical knowledge vault (code decisions, error fixes, architecture notes), `all-mpnet-base-v2` or `bge-large-en-v1.5` are the best local choices. MiniLM is fast but may miss domain-specific technical relationships.

- Installation: `pip install sentence-transformers` (pulls PyTorch dependency, ~2GB total)
- First use: downloads chosen model (one-time, cached)
- Latency per query embedding: ~5–20ms on CPU (Apple Silicon)
- Setup complexity: 2/5
- Privacy: fully local
- No separate process required — runs inside the Python extractor or MCP server
- **Verdict:** The most natural fit for this project. The knowledge-graph system is already Python. sentence-transformers integrates with zero architectural change — it's a library call, not a service dependency.

#### SQLite-vec

A SQLite extension (by Alex Garcia) that adds vector similarity search directly inside SQLite. Loadable as a shared library, works with Python's standard `sqlite3` module via `conn.load_extension()`.

- `pip install sqlite-vec` — installs the extension binary
- Stores vectors as float32 in a virtual table alongside regular columns (title, path, tags, summary, date)
- Query: cosine distance search, returns paths and metadata in a single SQL query
- At 1000 notes, brute-force scan is microseconds. ANN indexing not needed until 100k+ notes.
- Single `.db` file — no server, no daemon, portable, inspectable with any SQLite tool
- Mature enough for production use (v0.1.x, actively maintained, used widely in the community)
- Setup complexity: 2/5
- Privacy: local
- **Verdict:** Near-perfect storage layer for this use case. Pairs with sentence-transformers or Ollama for embedding. The `.db` file can live alongside the vault or in `~/.claude/`. Single file, zero moving parts, directly queryable from Python.

#### ChromaDB (local mode)

Open-source vector database with a Python API. Local `PersistentClient` stores data on disk (SQLite + Parquet). Good abstractions for embedding functions (can plug in sentence-transformers, OpenAI, etc.).

- `pip install chromadb`
- API: `collection.query(query_embeddings=[vec], n_results=5)`
- At 1000 notes: low resource usage (tens of MB on disk, low RAM)
- Setup complexity: 2/5
- Privacy: local
- Downside: heavier than necessary for this scale. Chroma has broken APIs between major versions. More moving parts than SQLite-vec for the same outcome.
- **Verdict:** Works, but SQLite-vec is a better fit. Chroma's advantage is its built-in embedding function abstraction — unnecessary since sentence-transformers is simple to call directly. SQLite-vec's single-file design is more appropriate for a personal tool.

#### LanceDB

Column-oriented vector database that stores data as Lance format files on disk. No server required. Designed explicitly for local file-based use.

- `pip install lancedb`
- API: `table.search(query_vec).limit(5).to_df()`
- Strong performance at scale; trivially fast at 1000 notes
- Notable: native hybrid search (vector + BM25 in one query) in recent versions
- Setup complexity: 2/5
- Privacy: local
- **Verdict:** Good choice, especially if the vault grows significantly (10k+ notes). The hybrid search capability (vector + keyword in one pass) is a genuine advantage over SQLite-vec + separate grep. Slightly heavier API surface than SQLite-vec, but well-documented and actively maintained.

### Cloud Embedding Options

#### OpenAI text-embedding-3-small

- 1536-dim, strong general-purpose retrieval performance (MTEB-competitive)
- Cost: $0.02/million tokens. At 500 tokens/note, 1000 notes = **$0.01 total** to embed the full vault. Incremental cost per new note is a fraction of a cent.
- Setup complexity: 1/5 (`pip install openai`, one API call)
- Latency per query: ~100–300ms (network round trip)
- Privacy: vault content is sent to OpenAI servers — the primary concern
- Requires adding OpenAI as a dependency; current project only uses Anthropic SDK
- **Verdict:** Trivially cheap at this scale. Quality is good. The only meaningful barrier is privacy (content leaves the device) and the philosophical position of sending a personal knowledge vault to OpenAI.

#### Voyage AI (voyage-code-3)

- Retrieval-specialized embedding models. `voyage-code-3` is trained on code repositories and technical documentation.
- Outperforms OpenAI embeddings on code retrieval benchmarks (Voyage's own MTEB results; independently validated on CodeSearchNet)
- Cost: ~$0.02–0.06/million tokens depending on model tier
- Setup complexity: 1/5 (`pip install voyageai`, one API key)
- Privacy: content leaves device — same concern as OpenAI
- **Verdict:** The best cloud option for a technically-focused vault. The code-specific training meaningfully improves precision for the types of content this vault stores (error fixes, architecture decisions, code patterns). Cost is equivalent to OpenAI at this scale.

#### Anthropic Embeddings

Anthropic does not offer a public embedding API as of early 2026. There is no embedding endpoint in the Anthropic API. Cross off the list.

---

## Part 3: Token Efficiency Analysis

### Current Token Cost Baseline

A typical recall query in the MCP implementation:
- Returns 5 notes, each truncated at 3000 characters (~750 tokens per note)
- Total retrieval context: **~3,750 tokens** per recall call
- Plus the query itself and the overhead of formatting headers/separators: ~4,000–4,500 tokens total

Sampling actual vault notes reveals:
- Short notes (error fixes, references): ~200–400 words (~300–600 tokens)
- Medium notes (decisions, insights with code): ~400–800 words (~600–1200 tokens)
- Long notes (architecture, with code blocks): 800–1500 words (~1200–2200 tokens)

At the 3000-char truncation limit, a long note is already cut off — the tail of the note (often the most specific implementation detail) may be dropped. This means full-note loading is simultaneously expensive AND lossy for longer notes.

At 500 notes in the vault, there is no scaling problem. At 5000 notes, nothing changes for the retrieval call — it still loads 5 notes regardless of vault size. The problem is not scaling but precision: loading the wrong 5 notes wastes all those tokens and produces irrelevant context.

### Frontmatter-First Approach (Summary Mode)

Each beat has a `summary` field: one dense sentence capturing the note's core content. A structured summary-first response would look like:

```
### [title] (type: decision, date: 2026-02-15, project: my-api)
summary: "Chose Redis over Postgres for session storage because read latency under concurrent load was 10x better in benchmarks."
tags: ["redis", "sessions", "performance"]
path: Projects/my-api/Claude-Notes/Redis-Session-Storage.md
```

Token cost for 10 candidates in summary mode: ~80 tokens/candidate × 10 = **~800 tokens**

This is a 5x reduction vs. loading 5 full notes, while covering twice as many candidates.

### Proposed Hybrid Retrieval Flow

```
Stage 1: Semantic search (vector similarity)
  → Find top 10 candidates
  → Return frontmatter + summary for each (~800 tokens)

Stage 2: LLM relevance filtering (in-context)
  → LLM identifies the 1-3 most relevant candidates from summaries
  → Requests full content only for those

Stage 3: Full content load
  → Read 1-3 full notes (~600-2400 tokens)
```

**Token comparison:**

| Approach | Tokens per recall | Notes loaded | Coverage |
|---|---|---|---|
| Current (MCP) | ~3,750–4,500 | 5 (by recency, lexical) | Low — keyword match only |
| Current (SKILL) | ~2,500–4,000 | Up to 5 (multi-pass grep) | Low — keyword match only |
| Hybrid Stage 1 only (summaries) | ~800–1,200 | 0 full notes | Medium — semantic, no body |
| Hybrid Stage 1+2+3 | ~2,000–4,000 | 1-3 full notes | High — semantic + selective |

The hybrid approach delivers higher retrieval quality at comparable or lower token cost, because:
1. Semantic search finds more relevant candidates than grep
2. The LLM reads summaries (not full bodies) to decide which notes matter
3. Only the actually-relevant notes are loaded in full

This is strictly better than the current approach in all dimensions.

### Implementation Sketch

```python
# Stage 1: embed the query, find top-N by cosine similarity
query_vec = embed(query)
candidates = db.search(query_vec, n=10)  # returns path, title, summary, tags, date

# Stage 2: format summary block, ask LLM to rank
summary_block = format_summaries(candidates)  # ~800 tokens
top_paths = llm_rank(query, summary_block)  # returns 1-3 paths

# Stage 3: load full content for top picks
for path in top_paths:
    full_content = read_note(path)
    inject_into_context(full_content)
```

For the kg-recall skill (which runs in-context, not as a subprocess), Stage 2 is implicit — the skill itself can be instructed to use summary mode first and only read full bodies for the top 1-2 notes.

---

## Part 4: Obsidian's Role in Retrieval

### Should retrieval go through Obsidian or bypass it?

**Verdict: Bypass Obsidian entirely for LLM retrieval.**

The vault is a folder of plain markdown files. The system already reads them directly via Python and grep. There is no reason to route LLM retrieval through Obsidian:

- Obsidian must be running for Obsidian-plugin APIs (Smart Connections, Omnisearch HTTP API) to be available. The hook fires at compaction time, which may be at 2am with Obsidian closed.
- Obsidian's data formats (`.obsidian/` config, SQLite cache files) are not designed for external consumption.
- File-direct reading is simpler, faster, and has no dependency on Obsidian's process state.

Obsidian's role in this system is correct as currently designed: **human review and curation interface only.** The LLM retrieval path should be file-direct.

### What does Obsidian's built-in search add over grep?

Obsidian's native search supports:
- Boolean operators (AND, OR, NOT, path:, tag:, file:, line:, section: qualifiers)
- Fuzzy matching
- Regular expressions

Over bare grep, this adds structured field filtering that the current multi-pass grep approximates manually. But Obsidian's search is only accessible through the UI or its internal API (not externally). It does not do semantic search.

**Omnisearch's HTTP API** is the one Obsidian-plugin approach worth noting: it wraps BM25 search in a queryable endpoint. This would be a marginal improvement over the current multi-pass grep — better ranking, no multi-pass, excerpts included — but still lexical only. It also requires Obsidian to be running, which is a soft dependency the current system avoids.

**Conclusion:** For the current use case, direct file access + a vector index is the right architecture. Obsidian plugins that require Obsidian to be running add fragility without adding capability over what Python can do directly.

---

## Ranked Options

Options ranked by overall fit for this project's constraints (personal tool, macOS, Python codebase, single user, hundreds to low thousands of notes):

### Tier 1: Recommended

**sentence-transformers + SQLite-vec**

- Setup: `pip install sentence-transformers sqlite-vec` — two pip installs
- No new services, no background processes, no API keys
- Integrates directly into the existing Python codebase
- Vector index is a single `.db` file alongside the vault
- Model recommendation: `all-mpnet-base-v2` (good quality, manageable size) or `BAAI/bge-large-en-v1.5` (best quality, ~1.3GB)
- Build index once; update incrementally as new notes are added
- Full control over the retrieval pipeline

**Why this wins:** It fits the existing architecture with the least friction. The knowledge-graph system is already Python. Adding two pip packages and ~100 lines of code gives semantic search with no new service dependencies.

### Tier 2: Strong Alternatives

**Ollama + nomic-embed-text + SQLite-vec**

- Identical to Tier 1 except embeddings are generated via Ollama's REST API rather than in-process
- Advantage: Ollama is a known quantity for users who already have it (common for LLM experimentation)
- Disadvantage: requires Ollama running as a background service; adds an HTTP call per query where an in-process call suffices
- Best choice if the user already uses Ollama for other purposes

**LanceDB + sentence-transformers**

- Stronger if the vault will grow to 10k+ notes or if hybrid search (vector + BM25 in one query) is wanted
- Same embedding approach, different storage layer
- Slightly heavier API than SQLite-vec but native hybrid search is a genuine advantage

### Tier 3: Useful Partial Improvements

**Omnisearch (HTTP API)**

- Zero embedding work, easy to query from Python via HTTP
- Better than current grep: BM25 ranking, fuzzy matching, excerpts
- Still lexical only — does not solve semantic gap
- Requires Obsidian to be running (soft dependency)
- Value: quick win as a bridge while semantic indexing is built; not a destination

### Tier 4: Cloud Options (Privacy Trade-off Required)

**Voyage AI voyage-code-3**

- Best cloud option for a technically-focused vault
- Code-specific training improves precision for error fixes, architecture decisions, code snippets
- Cost is negligible (~$0.01–0.03 for the whole vault)
- Main barrier: vault content leaves the device

**OpenAI text-embedding-3-small**

- Good quality, trivial cost
- Same privacy concern as Voyage; no domain-specific advantage for technical content
- Worth considering if the user is already an OpenAI customer and has no privacy objection

### Tier 5: Not Suitable

**Smart Connections** — no external API, Obsidian UI only
**Anthropic embeddings** — do not exist
**ChromaDB** — works but heavier than SQLite-vec for no benefit at this scale

---

## Recommendation for Next Phase

**Implement sentence-transformers + SQLite-vec with frontmatter-first retrieval.**

This is the recommendation because it:
1. Requires no new services or API keys
2. Integrates cleanly into the existing Python codebase
3. Delivers semantic search quality for zero ongoing cost
4. Enables the frontmatter-first hybrid flow (token savings + better relevance)
5. The `.db` file is portable, inspectable, and can live in `~/.claude/` or the vault root

### Implementation plan

**Step 1: Build the index**

A new script `scripts/build-index.py` (or added to `extract_beats.py`):
- Walk all `.md` files in the vault
- Parse YAML frontmatter for each (title, summary, tags, type, date, path)
- Embed: `title + " " + summary + " " + " ".join(tags)` (not full body — summary is dense enough, and body embedding is slower and noisier)
- Store in SQLite-vec: `(id, path, title, summary, tags_json, date, embedding)`
- Run once on existing vault; new beats add themselves at write time

**Step 2: Query path**

Replace the multi-pass grep in `kg_recall` (MCP) with:
```python
query_vec = model.encode(query)
rows = db.search(query_vec, n=10)  # returns path, title, summary, tags, date
```

**Step 3: Frontmatter-first presentation**

Return summaries for all 10 candidates, then load full content only for the 1-2 the LLM identifies as most relevant. This replaces the current "load top 5 full notes" with "summarize top 10, load top 2."

**Step 4: Incremental update**

In `write_beat()` (called when a note is written to the vault), add a call to embed the new note and upsert it into the index. This keeps the index current without a full rebuild.

### Tradeoffs of this recommendation

**What you gain:**
- Semantic recall: notes are found by meaning, not keyword presence
- Token efficiency: summary-first mode reduces retrieval context by ~50–70%
- Better candidate ranking: vector similarity vs. recency-of-keyword-match

**What you accept:**
- ~2GB disk for the model (one-time download, cached)
- ~1–2 second cold-start on first use (model load into memory)
- A build step for the initial index (~30–60 seconds for 1000 notes)
- A dependency on PyTorch (pulled in by sentence-transformers) — large package

**When to prefer Ollama instead:**
- If the user already has Ollama installed for other reasons
- If adding PyTorch to the Python environment is undesirable
- If model management via Ollama's CLI is preferred over pip packages

**When to consider cloud embeddings:**
- If installation simplicity is paramount (no large downloads)
- If the user has no privacy objection to vault content leaving the device
- If Voyage voyage-code-3 quality on technical content is materially better than local models (validate with a test on a sample of the vault)

### What this does NOT solve

- The `kg-recall` skill (Claude Code slash command) runs in-context and cannot call a Python script with a running model. The skill would need to either: (a) use a subprocess call to a small query script, (b) fall back to enhanced grep if the index isn't available, or (c) be redesigned to use a background indexing service. This is an implementation detail to resolve in the spec phase.
- The MCP server can integrate the vector search directly (it's already Python), so the MCP path is simpler.
- Index freshness: notes added directly in Obsidian (not via the extractor) won't be indexed until the build script is re-run or a file-watcher is added.
