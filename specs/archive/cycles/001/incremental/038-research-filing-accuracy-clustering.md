## Verdict: Pass

The research report satisfies all acceptance criteria with concrete, actionable proposals, but contains two inaccuracies in its code citations that an implementor needs to know about.

## Critical Findings

None.

## Significant Findings

### S1: Line number for `_build_clusters()` is wrong
- **File**: `specs/steering/research/filing-accuracy-clustering.md:7`
- **Issue**: The report states `_build_clusters()` is at line 543. In the current source, the function definition is at line 543 and the adjacency/OR logic the report criticises is at line 598. The report's description is correct; only the anchor line number is off by the preamble length. Not critical for a research doc, but the implementor will use this number as a jump target.
- **Impact**: Implementor wastes time hunting for the wrong line.
- **Suggested fix**: Replace "line 543" with "line 543 (function definition); adjacency OR logic at line 596-600".

### S2: `_dispatch_grouping()` line number is wrong
- **File**: `specs/steering/research/filing-accuracy-clustering.md:21`
- **Issue**: The report states `_dispatch_grouping()` is at line 502. In the current source it is at line 502, but `_embedding_hierarchical_clusters()` is stated as starting at line 326. The actual function definition is at line 326, which matches. This cross-check passes. However, the report also states the embedding strategy uses `TaylorAI/bge-micro-v2` (384-dim) as a factual claim about the embedding model. The source code in `restructure.py` does not reference this model name at all — it loads whatever embeddings are in the usearch index, which is built by the search indexer. The model name is an assumption that may be correct or may not, depending on what the user installed. If the model is different (e.g., a 768-dim model), the calibration analysis in the report (e.g., "cosine distance compressed into a narrow range" for short texts) may not apply with the same parameters.
- **Impact**: An implementor who tests on a different embedding model may find the adaptive threshold formula behaves unexpectedly.
- **Suggested fix**: Qualify the embedding model claim: "embeddings from the configured model (default `TaylorAI/bge-micro-v2`, 384-dim, but user-configurable via the search index)" and note that the adaptive threshold formula was reasoned from metadata-only short-text characteristics, which should be validated against actual distance distributions before hardcoding the `median - 0.5 * std` formula.

## Minor Findings

### M1: `_build_folder_examples()` uses `import random` inside a function body
- **File**: `specs/steering/research/filing-accuracy-clustering.md:289`
- **Issue**: The proposed implementation code has `import random` inside the inner `for` loop body, which will be evaluated on every iteration. This is cosmetically wrong (imports belong at module level) and while Python caches module imports, it is a code quality issue that will draw review comments during implementation.
- **Suggested fix**: Move `import random` to the top of the proposed function, or add it to the module-level imports shown in the code snippet.

### M2: Confidence fallback default is ambiguous
- **File**: `specs/steering/research/filing-accuracy-clustering.md:166`
- **Issue**: The routing logic code proposes `confidence = decision.get("confidence", 0.5)` as the default for responses missing the field. The report later states (line 341) "Old LLM responses without a `confidence` field should default to 0.5 (uncertain), triggering the logging path." However, 0.5 is exactly at the boundary of the `0.5-0.69` logging range — it does not fall below 0.5, so the code will execute the action and log, not fall back to inbox. This is internally consistent but the prose description ("uncertain, triggering the logging path") is slightly misleading since the actual behavior is "proceed with logging", not "fall back to inbox". Not a logic error, but a documentation inconsistency.
- **Suggested fix**: Clarify the prose: "Old LLM responses without a `confidence` field default to 0.5, which triggers the uncertain-filing log but proceeds with the LLM's routing decision."

### M3: Random sampling seeding proposal is incomplete
- **File**: `specs/steering/research/filing-accuracy-clustering.md:347`
- **Issue**: The report recommends seeding `random.choice` with a hash of the beat title to make sampling deterministic. The proposed `_build_folder_examples()` code (lines 288-290) does not implement this — it uses `random.choice(md_files[1:])` without seeding. The code and the recommendation contradict each other.
- **Suggested fix**: Either update the code snippet to use `random.Random(hash(beat_title)).choice(md_files[1:])` or explicitly note the code is a sketch and the seeding must be added.

## Unmet Acceptance Criteria

None.
