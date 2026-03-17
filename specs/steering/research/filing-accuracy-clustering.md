# Research: Filing Accuracy and Clustering

## Clustering Bug Diagnosis

There are two distinct clustering codepaths in `restructure.py`, used in different modes:

### 1. Normal mode: `_build_clusters()` (defined at line 543) — search-backend adjacency graph

This method builds an adjacency graph by issuing **per-word FTS5 searches** for each note. For each note, it extracts up to 6 distinctive words from title + summary + tags, searches the backend for each word, and records which other notes appear in results. An edge is added between notes i and j if **either** note found the other in >= 2 of its per-word searches. Connected components of the adjacency graph become clusters.

**Failure modes identified:**

- **Over-merging through transitive closure.** The algorithm uses BFS connected components. If note A is linked to B, and B is linked to C, then A-B-C form one cluster even if A and C have nothing in common. This is the classic "chaining problem" with single-linkage-like graph clustering. A folder about cooking, programming, and finance could end up with a single giant cluster if there are bridge notes (e.g., "Budgeting App Architecture" shares words with both finance and programming notes).

- **Noisy word-level search signal.** Searching for individual words like "claude", "code", "configuration" against the full vault index returns many false positives. The `_STOP` set only filters 10 words. Common domain terms that appear frequently in a project vault (e.g., "API", "model", "error", "test") are not stopped and create spurious edges.

- **Global index pollution.** `backend.search(word, top_k=top_k)` searches the entire vault index, not just the target folder. The `top_k` is `max(8, len(notes))`, but when the vault has thousands of notes, folder-local notes may be ranked below irrelevant vault-wide results. The code filters by `note_paths` (folder membership) after search, but if relevant folder peers are pushed out of `top_k` by unrelated vault notes, real connections are missed.

- **Edge weight threshold is binary.** Requiring `w >= 2` word-search co-occurrences as the adjacency threshold is the same for a 3-note folder and a 300-note folder. For small folders where notes share a domain, nearly everything may share 2+ words. For large diverse folders, 2 may be too lenient.

### 2. Folder-hub mode: `_dispatch_grouping()` (line 502) — embedding or LLM clustering

This delegates to `_embedding_hierarchical_clusters()` (embedding/auto strategies) or `_call_group_notes()` (LLM strategy).

**Embedding clustering (`_embedding_hierarchical_clusters`, line 326):**

- Algorithm: hand-rolled agglomerative clustering with **average linkage** on **cosine distance**.
- Distance threshold: **0.25** (hardcoded default).
- Embedding source: metadata-only embeddings from the search index: `"{title}. {summary} {tags}"`.
- Minimum cluster size: 2.

**Failure modes identified:**

- **Threshold of 0.25 is aggressive for metadata-only embeddings.** The embeddings are computed from `"{title}. {summary} {tags}"` using `TaylorAI/bge-micro-v2` (384-dim) — this is the assumed default model; the model is user-configurable, so distance characteristics will vary. Metadata-only strings are short (typically 20-80 tokens). Short texts produce embeddings where cosine similarity is compressed into a narrow range. Two clearly related notes may have cosine distance of 0.30-0.40, while unrelated notes may have distance of 0.50-0.70. A threshold of 0.25 means only extremely similar notes cluster together, causing **under-clustering** (many singleton notes that should be grouped are left standalone).

- **No calibration to corpus statistics.** The 0.25 threshold is absolute. Different vaults with different note styles, lengths, and embedding distributions will have different natural distance distributions. A threshold that works for terse technical notes fails for verbose narrative notes, and vice versa.

- **O(n^3) merge loop.** The inner loop scans all active cluster pairs on every merge step. For a folder with 200 notes, this is ~8M operations per merge step with potentially 199 merge steps. Not a correctness bug, but a performance limitation that may cause timeouts on larger folders.

- **Average linkage masks outliers.** If a cluster has 5 tightly related notes and 1 marginally related note, the average distance to a new candidate is diluted by the tight core, potentially absorbing notes that only relate to 1-2 of the existing members. Single-linkage would be worse (more chaining), but complete linkage would be more conservative and prevent this.

### Summary of the primary bug

The work item hypothesis about the 0.25 threshold is partially correct: it causes **under-clustering** in embedding mode (notes that should group together don't because 0.25 is too tight for short metadata embeddings). In normal mode, the opposite problem exists: **over-clustering** through transitive BFS connected components, where unrelated notes end up in the same cluster via word-search bridge edges.

---

## Proposed Clustering Fix

### Fix 1: Embedding clustering — adaptive threshold

Replace the hardcoded `distance_threshold=0.25` with an adaptive approach:

1. Compute the full pairwise cosine distance matrix (already done).
2. Compute the distribution statistics: mean, median, and standard deviation of all off-diagonal distances.
3. Set threshold = `median - 0.5 * std`, clamped to `[0.15, 0.40]`.

This automatically adjusts to the vault's embedding distribution. Terse technical vaults with compressed similarity ranges get a tighter threshold; verbose narrative vaults get a looser one.

**Specific parameter recommendations:**
- Floor: 0.15 (never cluster notes with cosine distance below this without reason)
- Ceiling: 0.40 (beyond this, clusters become too loose)
- Default fallback if stats are degenerate: 0.30 (slightly looser than current 0.25)

Note: these floor and ceiling values are based on analysis of the assumed default embedding model (`TaylorAI/bge-micro-v2`). Because the embedding model is user-configurable, the 0.15 floor and 0.40 ceiling should be validated against actual corpus distance distributions before being committed as constants — different models may have meaningfully different similarity ranges.

**Code change:** In `_embedding_hierarchical_clusters()`, after computing `dist_matrix`:

```python
# Adaptive threshold from corpus statistics
off_diag = dist_matrix[np.triu_indices(n, k=1)]
if len(off_diag) > 2:
    median_dist = float(np.median(off_diag))
    std_dist = float(np.std(off_diag))
    adaptive_threshold = max(0.15, min(0.40, median_dist - 0.5 * std_dist))
else:
    adaptive_threshold = 0.30
distance_threshold = adaptive_threshold
```

### Fix 2: Normal mode — replace BFS connected components with direct distance clustering

The `_build_clusters()` function should stop using BFS connected components. Instead:

1. Keep the per-word search edge-weight computation (it's useful signal).
2. Normalize edge weights to [0, 1] similarity scores: `sim(i,j) = edge_weight[i][j] / max(len(unique_words_i), 1)`.
3. Apply the same agglomerative clustering used in embedding mode, with average linkage and an adaptive threshold based on the distribution of nonzero similarities.

This eliminates the transitive chaining problem entirely.

**Alternative (simpler):** Keep the graph-based approach but require **mutual** edges with weight >= 2 (both `edge_weight[i][j] >= 2` AND `edge_weight[j][i] >= 2`) instead of the current OR logic (lines 596-600). This is a one-line change that significantly reduces false adjacency.

**Recommended approach:** The simpler mutual-edge fix first (immediate improvement, minimal risk), followed by the agglomerative migration if quality data shows further need.

### Fix 3: Expand the stop word set

The `_STOP` set in `_build_clusters()` should be expanded to include common domain terms that carry no discriminating signal:

```python
_STOP = {
    "claude", "code", "the", "and", "for", "with", "using",
    "how", "what", "why", "non", "vs",
    # Add common domain noise words:
    "api", "model", "error", "test", "file", "config",
    "note", "setup", "tool", "data", "project", "system",
    "new", "use", "get", "set", "run", "add",
}
```

Better yet, compute stop words dynamically: any word appearing in > 40% of notes in the folder should be excluded from search queries for that folder.

---

## Confidence Scoring Design

### What the score means

A **filing confidence score** (0.0-1.0) represents how certain the autofile LLM is that its routing decision is correct. It combines two signals:

1. **Folder certainty**: Is there a clearly correct destination, or are multiple folders plausible?
2. **Action certainty**: Is create-vs-extend unambiguous, or is the boundary unclear?

### How to extract it

**Approach: structured JSON output with confidence field.** Extend the existing autofile JSON response schema to include a `confidence` field. This is the simplest approach and avoids a second LLM call.

**Changes to `autofile-system.md` prompt — add to the return schema:**

```
For extend:
{"action": "extend", "target_path": "...", "insertion": "...", "confidence": 0.85, "rationale": "..."}

For create:
{"action": "create", "path": "...", "content": "...", "confidence": 0.85, "rationale": "..."}
```

**Add this guidance to the prompt:**

```
## Confidence scoring

Include a `confidence` field (0.0 to 1.0) and a `rationale` field (1-2 sentences) in your response:

- **0.9-1.0**: Obvious match. The beat clearly extends an existing note, or clearly belongs in a specific folder with no ambiguity.
- **0.7-0.89**: Good match. The routing is reasonable but a different folder or action could also work.
- **0.5-0.69**: Uncertain. Multiple folders or actions seem equally plausible. The beat may not fit cleanly into existing structure.
- **0.0-0.49**: Low confidence. The vault structure doesn't have a clear home for this beat, or the beat's topic is ambiguous.

Base your confidence on:
1. How well the beat's topic matches the destination folder's existing notes
2. Whether the related documents returned are genuinely about the same topic
3. Whether the folder structure has an obvious home for this topic
```

### Routing logic based on confidence

| Confidence | Action |
|---|---|
| >= 0.7 | Execute the LLM's decision as-is |
| 0.5-0.69 | Execute but log a warning to the consolidation log for later review |
| < 0.5 | Fall back to inbox routing (ignore the LLM's folder suggestion) |

**Implementation in `autofile.py`:**

```python
decision = json.loads(raw)
confidence = decision.get("confidence", 0.5)
rationale = decision.get("rationale", "")

if confidence < 0.5:
    print(f"[extract_beats] autofile: low confidence ({confidence:.2f}), falling back to inbox: {rationale}", file=sys.stderr)
    return write_beat(beat, config, session_id, cwd, now, source=source)

if confidence < 0.7:
    # Log for review but proceed
    _log_uncertain_filing(beat, decision, confidence, rationale, config)

action = decision.get("action")
# ... proceed with existing action handling
```

### Reliability of LLM-produced confidence scores

LLM self-reported confidence is known to be miscalibrated (overconfident on average). However, it is **directionally useful**: when the LLM reports low confidence, the routing is genuinely more likely to be wrong. The thresholds above are tuned conservatively:

- The 0.5 fallback threshold catches the worst misroutes.
- The 0.7 logging threshold flags borderline cases for manual review.
- Over time, reviewing the logged uncertain filings can calibrate whether the thresholds need adjustment.

**Alternative considered: separate validation call.** A second LLM call to verify the first call's routing decision. Rejected because it doubles latency and cost for every autofile operation, violating principle 7 (cheap models where possible). The single-call confidence approach provides 80% of the benefit at zero additional cost.

---

## Vault History Injection Design

### Problem

The current autofile prompt provides:
1. The beat to file (full JSON).
2. Up to 5 related vault documents (found by `search_vault()` grep search).
3. The vault CLAUDE.md (conventions).
4. A flat folder listing of the vault root.

What's missing: **examples of what a well-filed note looks like in each candidate folder.** The LLM sees folder names but has no signal about what kind of content lives in each folder. A folder called "Recipes" is self-explanatory, but "Projects/hermes/Claude-Notes" or "Knowledge/AI" gives no filing guidance beyond the name.

### Sampling strategy

For each **candidate folder** (top-level directories visible in the vault folder listing), sample **2 representative notes** per folder:

1. **Most recent note** (by file mtime) — represents the folder's current active topic.
2. **A random sample** from the remaining notes — provides topic diversity.

If a folder has only 1 note, include just that one. If a folder has 0 notes, skip it.

**Maximum folders to sample:** 8 (to stay within context budget). Prioritize folders that are most likely candidates by ranking them by the number of search hits from `search_vault()` results. If `search_vault()` returns results from 3 distinct folders, sample those 3 plus up to 5 more from the vault.

**Maximum total notes sampled:** 16 (8 folders x 2 notes). Each note is truncated to its frontmatter + first 200 characters of body.

### Formatting in the prompt

Add a new section to `autofile-user.md`:

```markdown
<vault_folder_examples>
{folder_examples}
</vault_folder_examples>
```

The `folder_examples` variable contains:

```markdown
### Projects/hermes/Claude-Notes/ (2 sample notes)

**MCP Tool Registration Patterns.md** (2026-03-10)
type: reference | tags: [mcp, fastmcp, tool-design]
Summary: Patterns for registering tools with FastMCP including...

**Bedrock Auth Configuration.md** (2026-03-05)
type: reference | tags: [aws, bedrock, authentication]
Summary: How to configure AWS credentials for the Bedrock...

### Knowledge/AI/ (2 sample notes)

**Prompt Engineering Strategies.md** (2026-03-08)
type: insight | tags: [prompting, llm, techniques]
Summary: Key strategies for effective prompt engineering...

**Embedding Model Comparison.md** (2026-02-28)
type: reference | tags: [embeddings, models, comparison]
Summary: Comparison of embedding models for semantic search...
```

### Add guidance to `autofile-system.md`

Add after the existing rules:

```
- Use the folder examples section to understand what kind of content lives in each folder.
  Match the beat's topic to the folder whose existing notes are most topically similar.
  Do not create a new folder unless no existing folder's examples match the beat's topic.
```

### Implementation in `autofile.py`

Add a new function `_build_folder_examples()`:

```python
import random

def _build_folder_examples(vault_path: str, search_results: list[str],
                            max_folders: int = 8, notes_per_folder: int = 2) -> str:
    vault = Path(vault_path)
    # Identify candidate folders from search results
    result_folders = set()
    for path in search_results:
        rel = Path(path).relative_to(vault)
        if len(rel.parts) > 1:
            result_folders.add(rel.parts[0])

    # Collect all top-level folders, prioritizing those with search hits
    all_folders = sorted(
        (d for d in vault.iterdir() if d.is_dir() and not d.name.startswith(".")),
        key=lambda d: (d.name not in result_folders, d.name)
    )[:max_folders]

    lines = []
    for folder in all_folders:
        md_files = sorted(folder.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not md_files:
            continue
        samples = [md_files[0]]  # most recent
        if len(md_files) > 1:
            # Use a seeded random keyed on the folder name for determinism across calls
            samples.append(random.Random(hash(folder.name)).choice(md_files[1:]))

        folder_rel = str(folder.relative_to(vault))
        lines.append(f"### {folder_rel}/ ({len(samples)} sample notes)\n")
        for sample in samples:
            fm = parse_frontmatter(sample.read_text(encoding="utf-8", errors="replace"))
            title = fm.get("title") or sample.stem
            note_type = fm.get("type", "unknown")
            tags = fm.get("tags", [])
            summary = fm.get("summary", "")[:200]
            mtime = datetime.fromtimestamp(sample.stat().st_mtime).strftime("%Y-%m-%d")
            lines.append(f"**{title}** ({mtime})")
            lines.append(f"type: {note_type} | tags: {tags}")
            lines.append(f"Summary: {summary}\n")

    return "\n".join(lines) if lines else "(no folder examples available)"
```

Call it in `autofile_beat()` after `search_vault()`:

```python
related_paths = search_vault(beat, search_root, max_results=5)
folder_examples = _build_folder_examples(vault_path, related_paths)
```

And pass it to the prompt:

```python
user_message = load_prompt("autofile-user.md").format_map({
    "beat_json": json.dumps(beat, indent=2),
    "related_docs": "\n\n---\n\n".join(related_docs) if related_docs else "(none found)",
    "vault_context": vault_context,
    "vault_folders": vault_folders or "(empty)",
    "folder_examples": folder_examples,
})
```

### Context budget

The folder examples section adds approximately 1,500-3,000 tokens to the autofile prompt (16 notes x ~100-180 tokens each). The current prompt is already lightweight (beat JSON + related docs + CLAUDE.md + folder list). Total prompt size with examples stays well under 8K tokens, which is reasonable for a cheap model call.

---

## Risks and Edge Cases

### Confidence scoring risks

1. **Overconfidence bias.** LLMs tend to report confidence in the 0.7-0.9 range even when uncertain. Mitigation: start with conservative thresholds (0.5/0.7) and calibrate from logged data after 2-4 weeks of production use. If < 5% of filings fall below 0.5, the floor threshold should be raised.

2. **Confidence gaming.** If the prompt is too explicit about what happens at each threshold, the LLM may game the score to avoid fallback. Mitigation: the prompt describes what confidence means semantically, not what routing action each range triggers.

3. **Backward compatibility.** Old LLM responses without a `confidence` field should default to 0.5, which falls in the 0.5–0.69 range and triggers uncertain-filing logging but proceeds with the LLM's routing decision (not the inbox fallback). This ensures no silent regression.

### Vault history injection risks

1. **Stale examples.** If the vault structure changes frequently, sampled examples may not represent current folder intent. Mitigation: always use the most recent note as one of the two samples. Mtime-based selection naturally tracks evolving folder content.

2. **Random sampling variance.** The second sample is random, so repeated autofile calls for the same beat may see different examples and make different decisions. Mitigation: seed the random choice with a hash of the folder name (as shown in the code snippet above), making it deterministic for the same folder across calls.

3. **Empty or sparse vaults.** New vaults with few notes provide poor examples. Mitigation: fall back to the existing behavior (folder listing only) when fewer than 3 folders have any notes.

4. **Large vaults with deep hierarchies.** `rglob("*.md")` on a folder with thousands of notes is expensive. Mitigation: limit the glob to depth 2 (`*/**.md` patterns) or use `iterdir()` + sample rather than full recursive glob.

### Clustering fix risks

1. **Adaptive threshold may over-cluster in homogeneous vaults.** If all notes in a vault are about the same broad topic, the distance distribution will be tight and `median - 0.5 * std` could be very low, causing everything to cluster. Mitigation: the 0.15 floor prevents this.

2. **Mutual-edge requirement may under-cluster asymmetric relationships.** If note A is very specific and note B is very broad, A's words may match B but B's words may not match A. Requiring mutual edges drops this link. This is acceptable: asymmetric relationships are weak signals and are better left unclustered than forced together.

3. **Dynamic stop words require folder-scoped computation.** Computing word frequencies per folder adds a loop over all notes before the search loop. For a folder with 100 notes, this is negligible. For 1000+, it should be memoized.

### Implementation ordering

For the implementation agent:

- **WI-043 (autofile accuracy)**: Implement confidence scoring first (prompt change + routing logic), then vault history injection. Test confidence scoring in isolation before adding the examples, so quality impact can be measured independently.

- **WI-044 (clustering fix)**: Implement the mutual-edge fix in `_build_clusters()` first (one-line change). Then implement the adaptive threshold in `_embedding_hierarchical_clusters()`. Then expand the stop word set. Each change is independently testable and measurable.
