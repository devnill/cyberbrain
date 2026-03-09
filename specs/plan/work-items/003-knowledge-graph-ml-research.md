# 003: Knowledge Graph + ML Research Investigation

## Objective
Research ML approaches that can augment semantic search with knowledge graph structure. Evaluate whether typed edges, graph embeddings, or graph neural networks can improve retrieval quality beyond the current hybrid FTS5 + vector search. Produce a recommendation with concrete next steps.

## Acceptance Criteria
- [ ] Research report exists at `specs/steering/research/knowledge-graph-ml-approaches.md`
- [ ] Report covers at minimum: graph embedding methods (TransE, RotatE, node2vec), GNN approaches (GCN, GraphSAGE), typed-edge traversal strategies, and hybrid graph+vector retrieval architectures
- [ ] Each approach is evaluated against: implementation complexity, dependency footprint, quality improvement potential at personal vault scale (1K-10K notes), compatibility with current SQLite + flat-file architecture
- [ ] Report includes a comparison of graph database options (Neo4j, Kuzu, SQLite-based, in-memory) with tradeoffs for local vs. hosted deployment
- [ ] Report addresses the specific question: can typed edges (causes, implements, supersedes, etc.) improve retrieval precision beyond what embedding similarity provides?
- [ ] Concrete recommendation with rationale: which approach(es) to prototype first, and what infrastructure changes they require
- [ ] Assessment of whether the current `related:` frontmatter and `## Relations` body encoding is sufficient substrate for graph-enhanced retrieval, or whether a richer representation is needed

## File Scope
- `specs/steering/research/knowledge-graph-ml-approaches.md` (create) — research report

## Dependencies
- Depends on: none
- Blocks: 005

## Implementation Notes
This is a pure research task. No code changes.

The current state: cyberbrain has embedding-based semantic search (fastembed + usearch) and relation data in frontmatter (`related:` wikilinks) and body (`## Relations` section with typed predicates). The SQLite index has a `relations` table. The question is whether and how to leverage this relation data to improve retrieval.

Key research questions:
1. At personal vault scale (1K-10K notes, sparse graph), do graph methods add meaningful signal over dense vector similarity?
2. Is the current relation vocabulary (6 types) sufficient for graph-based methods, or do they need richer structure?
3. What's the minimum viable graph enhancement — typed edge traversal in SQL? Or does it require actual graph algorithms?
4. How do graph embeddings (learning vector representations of nodes from graph structure) compare to text embeddings for retrieval? Are they complementary?
5. If we move to hosted deployment later, which approaches scale well and which don't?

The output shapes the RAG architecture (work item 005) and may influence whether to invest in richer relation extraction during curation.

## Complexity
Medium
