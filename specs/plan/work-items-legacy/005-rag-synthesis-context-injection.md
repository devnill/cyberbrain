# 005: RAG Synthesis and Context Injection

## Objective
Build production-quality RAG that synthesizes retrieved vault content into useful context for active sessions. Improve retrieval precision using findings from knowledge graph research (003). Ensure the retrieval pipeline works identically across Claude Code, Claude Desktop, and mobile.

## Acceptance Criteria
- [ ] `cb_recall` with `synthesize=True` produces coherent, accurate synthesis from multiple retrieved notes
- [ ] Synthesis is token-efficient: injects only relevant content, not full note bodies
- [ ] Retrieval precision is improved over current baseline (measured via evaluation tooling from 001)
- [ ] Knowledge graph research findings (003) are incorporated where they demonstrably improve precision
- [ ] The retrieval pipeline produces identical results regardless of which MCP client invokes it
- [ ] Context injection format is optimized for LLM consumption (not human reading)
- [ ] Existing test suite passes; new tests cover synthesis, context formatting, and any graph-enhanced retrieval

## File Scope
- `mcp/tools/recall.py` (modify) — synthesis implementation, context injection formatting
- `extractors/search_backends.py` (modify) — precision improvements, possible graph-enhanced retrieval
- `extractors/search_index.py` (modify) — index schema changes if graph features are added
- `prompts/synthesize-system.md` (create) — synthesis prompt
- `prompts/synthesize-user.md` (create) — synthesis prompt
- `tests/test_recall_read_tools.py` (modify) — synthesis and precision tests
- `tests/test_search_backends.py` (modify) — if search backend changes

## Dependencies
- Depends on: 001 (evaluation tooling for measuring precision), 003 (graph research for architecture decisions)
- Blocks: 006, 007

## Implementation Notes
The enhanced-retrieval spec (legacy) laid out three phases: precision improvements (done), semantic layer (partially done — FTS5 + embedding exist), and MCP synthesis (not done). This work item covers the MCP synthesis phase plus any precision improvements informed by the graph research.

Key design decisions:
1. **Synthesis prompt design:** The synthesis call uses `claude -p` as a subprocess. The prompt needs to produce a concise answer that integrates information from multiple notes, cite sources, and avoid hallucination. This is a quality-sensitive task — haiku may not be sufficient.

2. **Context injection format:** Currently `cb_recall` returns human-readable note cards. For RAG, the format should be optimized for LLM consumption — possibly structured XML or tagged sections that the receiving LLM can parse efficiently.

3. **Graph-enhanced retrieval:** If research (003) identifies viable graph methods at personal vault scale, integrate them here. This could mean typed-edge traversal in SQL (lightweight) or graph embeddings (heavier). The decision depends on 003's findings.

4. **Token efficiency:** Full note injection is wasteful. Options: paragraph-level extraction (already partially implemented), summary-only injection with full notes available via cb_read follow-up, or LLM-compressed excerpts.

5. **Cross-client parity:** The retrieval and synthesis pipeline runs in the MCP server process. The only client-side variation should be how results are displayed, not what results are returned.

## Complexity
High
