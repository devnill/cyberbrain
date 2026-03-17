# Retrieval Interface Design

## Current State Analysis

### Existing Tools

**cb_recall** (`recall.py`, lines 159-324) — Search tool with synthesis mode.

Parameters:
- `query: str` — search query (required)
- `max_results: int` (1-50, default 5) — result limit
- `synthesize: bool` (default False) — LLM synthesis of results

Behavior: Searches via pluggable backend (hybrid > fts5 > grep). Returns note cards with title, type, tags, related links, summary, and full body for top 2. When `synthesize=True`, calls `_synthesize_recall()` which invokes `claude -p` to produce a concise answer from the retrieved notes, with quality gate validation.

**cb_read** (`recall.py`, lines 326-385) — Direct note reader.

Parameters:
- `identifier: str` — vault-relative path or note title (required)

Behavior: Resolves note by exact path, path+.md, FTS5 exact title match, or FTS5 fuzzy title match. Returns full note content including frontmatter and vault-relative path.

### Overlap and Redundancy

The tools are cleanly separated today:

1. **cb_recall** = search (find notes matching a query) + optional synthesis
2. **cb_read** = direct access (get a specific known note)

There is no functional redundancy between them. They serve different use cases with different input types (search query vs. identifier). The `synthesize` flag on `cb_recall` adds a third capability (context synthesis) as a mode of the search tool.

### Friction Points

1. **Synthesis is buried as a boolean flag.** The LLM calling it must know to set `synthesize=True`. The default is False, so the common proactive recall path returns raw note cards, leaving synthesis unused unless explicitly requested. This means the "feels like memory" experience (Principle 4) is opt-in rather than default.

2. **cb_read has no synthesis.** If the LLM already knows which 3 notes are relevant (e.g., from a previous recall or from wikilinks), there is no way to synthesize them without re-searching. The only path to synthesis goes through cb_recall's search pipeline.

3. **cb_recall returns full body for top 2 results.** This is a heuristic that works but wastes tokens when only metadata is needed (e.g., to decide which notes to read in full). Conversely, 2 full bodies may not be enough when synthesis needs content from all results.

---

## Use Cases

### UC1: Search
**Trigger:** User mentions a topic, project, or technology they may have worked on before. Or the session shifts to a new domain.

**Input:** A natural-language query describing the information need.

**Output:** A ranked list of matching notes with enough metadata to understand relevance (title, type, tags, summary, source path) and enough content to be immediately useful (body for top results).

**Current tool:** `cb_recall(query, max_results)` with `synthesize=False`.

### UC2: Direct Read
**Trigger:** User names a specific note, or a previous recall surfaced a note the LLM wants to read in full. Wikilinks in note bodies also create direct-read needs.

**Input:** A vault-relative path or note title.

**Output:** The complete note content (frontmatter + body) with source path.

**Current tool:** `cb_read(identifier)`.

### UC3: Context Synthesis
**Trigger:** The LLM needs to inject relevant prior knowledge into the conversation as a coherent context block, not as raw note dumps. This is the "feels like memory" experience.

**Input:** A query (to find relevant notes) or a set of known notes.

**Output:** A concise, LLM-generated synthesis that extracts only query-relevant information from the source notes, with citations and source list.

**Current tool:** `cb_recall(query, synthesize=True)`. No path exists to synthesize from a known set of notes without re-searching.

---

## Proposed Tool Set

### Tool 1: `cb_recall` (modified)

**Purpose:** Search the knowledge vault and return matching notes. This is the primary retrieval entry point.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `str` | required | Natural-language search query |
| `max_results` | `int` (1-50) | 5 | Maximum notes to return |
| `synthesize` | `bool` | False | If true, return an LLM-synthesized context block instead of raw note cards |

**Return value:** When `synthesize=False`: security-wrapped note cards (title, type, tags, related, summary, source path; full body for top 2). When `synthesize=True`: LLM-synthesized context block with citations and source list.

**Use cases covered:** UC1 (Search), UC3 (Context Synthesis — query-driven path).

**Changes from current:** None. The interface is unchanged. This tool already works correctly for both search and query-driven synthesis.

### Tool 2: `cb_read` (modified)

**Purpose:** Read one or more specific vault notes by path or title. Optionally synthesize them into a context block.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `identifier` | `str` | required | A vault-relative path, note title, or pipe-separated (`\|`) list of paths/titles (up to 10) |
| `synthesize` | `bool` | False | If true and multiple notes are provided, return an LLM-synthesized context block instead of concatenated note contents |
| `query` | `str` | `""` | When synthesizing, focus the synthesis on this query. If empty or None, `"Provide a general summary of these notes."` is substituted into the `{query}` slot of the `synthesize-user.md` template before calling `_synthesize_recall()`. |

**Return value:** When single identifier + `synthesize=False`: full note content with frontmatter and source path (current behavior). When multiple identifiers + `synthesize=False`: concatenated full note contents, each with source path. When `synthesize=True`: LLM-synthesized context block focused on `query`, with citations and source list. When a single note is provided and `synthesize=True`, synthesis still runs — useful when the note is long and the caller wants a query-focused excerpt.

**Resolution order** (per identifier, unchanged): exact vault-relative path, path+.md, FTS5 exact title match, FTS5 fuzzy title match.

**Use cases covered:** UC2 (Direct Read), UC3 (Context Synthesis — known-notes path).

**Changes from current:** Two new optional parameters (`synthesize`, `query`). Single-identifier + no-synthesize is identical to current behavior. The multi-identifier capability is new — it enables synthesizing a known set of notes without re-searching, closing the gap identified in the friction analysis.

---

## Tools Removed

None.

Both `cb_recall` and `cb_read` are retained. They serve genuinely different input patterns (query-based search vs. identifier-based lookup) and removing either would force the remaining tool to handle both patterns, making its interface confusing.

No new tools are added either. The synthesis capability for known notes is added as an optional parameter on `cb_read` rather than as a separate tool, keeping the tool count flat.

---

## Net Tool Count

- Before: 11 tools (cb_extract, cb_file, cb_recall, cb_read, cb_configure, cb_status, cb_setup, cb_enrich, cb_restructure, cb_review, cb_reindex)
- Removed: 0
- Added: 0
- After: 11 tools

Net change: 0. Constraint satisfied.

---

## Rationale

### Why not merge cb_recall and cb_read into a single tool?

A merged tool would need to distinguish "is this a search query or a note identifier?" — either via a mode parameter or by guessing from the input. Both options are worse than having two tools with clear input contracts. The LLM already knows whether it wants to search or read a specific note; forcing it through a dispatcher adds ambiguity.

### Why not create a separate cb_synthesize tool?

A standalone synthesis tool would require the caller to first search (cb_recall), collect paths, then call cb_synthesize with those paths. This adds a round-trip and increases tool count. Synthesis is better modeled as an output mode of retrieval tools — it answers "how should the results be formatted?" rather than "what operation should be performed?"

### Why add multi-identifier support to cb_read instead of cb_recall?

cb_recall's input is a search query. Passing a list of note titles to cb_recall and hoping they all match is fragile — it would search for notes, not retrieve them. cb_read's contract is "retrieve these specific notes," which is the correct entry point for "I know which notes I want, synthesize them."

### Why is synthesize=False the default?

Synthesis invokes an LLM subprocess (`claude -p`), adding 5-15 seconds of latency and consuming tokens. For proactive recall, raw note cards are usually sufficient — the calling LLM can read and integrate them directly. Synthesis is most valuable when:
- Many notes match and the calling LLM would struggle to extract the relevant parts
- The results will be injected into a context window where token economy matters
- The user explicitly asks for a summary of what cyberbrain knows about a topic

Making it opt-in keeps the common case fast. The `orient` prompt can instruct the LLM when to enable synthesis for specific vault configurations.

### Why comma-separated identifiers instead of an array parameter?

MCP tool parameters are flat. A comma-separated string is simpler for the LLM to construct than a JSON array and avoids parameter type complexity. The 10-identifier limit prevents abuse while covering all practical cases (synthesizing more than 10 notes at once would produce low-quality synthesis anyway).

---

## Implementation Concerns

### 1. Multi-identifier resolution failures
When `identifier` contains multiple items and some fail to resolve, the tool should resolve what it can and report which identifiers failed, rather than failing the entire call. Return a partial result with a warning line listing unresolved identifiers.

### 2. Synthesis prompt reuse
`cb_read` synthesis should reuse `_synthesize_recall()` and the existing `synthesize-system.md` / `synthesize-user.md` prompts. The `query` parameter maps directly to the `{query}` template variable. When `query` is empty, use a generic prompt like "Summarize the key information from these notes."

### 3. Token budget for multi-read
Reading 10 full notes could produce a very large payload. When `synthesize=False` and multiple identifiers are provided, truncate body content at `max_chars_per_note` chars per note (default 2000) with a note that cb_read can retrieve the full content of any individual note. When `synthesize=True`, no truncation is applied — the synthesis prompt handles token compression. The `max_chars_per_note` parameter should be added to `cb_read` with a default of 2000 and a value of 0 meaning no truncation.

### 4. Identifier parsing ambiguity
Note titles can contain commas, but pipe (`|`) never appears in Obsidian filenames because it breaks wikilink syntax. Pipe is therefore the unambiguous delimiter. The implementation must split `identifier` on `|`, and the parameter description documents this (see the parameters table above).

### 5. Quality gate for cb_read synthesis
The existing quality gate in `_synthesize_recall()` should apply equally to cb_read synthesis. No new gate logic needed — the same `quality_gate(operation="synthesis", ...)` call covers both paths.

### 6. Model selection
cb_read synthesis should use the same `recall_model` config key as cb_recall synthesis, since both are the same operation (LLM synthesis of vault content). No new per-tool model key needed.

### 7. Backwards compatibility
The cb_recall interface is unchanged. The cb_read interface adds two optional parameters with defaults that preserve current behavior. No existing callers break. The `orient` prompt must be updated to document multi-identifier synthesis: add a line explaining that `cb_read` accepts pipe-separated identifiers and can synthesize across multiple notes.
