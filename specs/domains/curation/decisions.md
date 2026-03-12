# Decisions: Curation

## D-1: cb_evaluate removed from MCP server; preserved as internal dev tooling
- **Decision**: The evaluation framework is not a product feature. `extractors/evaluate.py` remains for internal heuristic development but is not exposed through the MCP server.
- **Rationale**: "Unless the data captured by an MCP tool can be acted on during regular usage, it shouldn't be in the product." (interview, cycle 1 refinement). The tool was too heavy and laborious to align with the zero-ceremony goal.
- **Source**: specs/steering/interview.md (Refinement Interview 2026-03-09, first refinement)
- **Status**: settled

## D-2: Quality gates built into curation tools using LLM-as-judge pattern
- **Decision**: Rather than a separate evaluation tool, each curation tool (restructure, enrich, review) includes an LLM judge that validates output before writing. Low-quality output is surfaced to the user.
- **Rationale**: Addresses the frustration from poor curation without requiring manual invocation. "Want to formalize the ability to improve results without leaning on heavy, expensive models." (interview)
- **Source**: specs/steering/interview.md (Refinement Interview 2026-03-09, first refinement)
- **Status**: settled

## D-3: quality_gate_threshold removed (YAGNI); quality_gate_enabled is the only gate config
- **Decision**: The configurable `quality_gate_threshold` was removed. `quality_gate_enabled` (boolean) is the sole gate configuration option, manageable via `cb_configure`.
- **Rationale**: "Remove. YAGNI." (interview, cycle 2 refinement). The threshold added complexity without demonstrated need.
- **Source**: specs/steering/interview.md (Refinement Interview 2026-03-09, second refinement, cycle 2)
- **Status**: settled

## D-4: Restructure implements multi-phase pipeline: audit → group → decide → generate → execute
- **Decision**: Restructuring is split into five named phases with separate prompts for each phase (`restructure-audit`, `restructure-group`, `restructure-decide`, `restructure-generate`) and pluggable grouping strategies (auto, embedding, llm, hybrid).
- **Rationale**: The single-call-does-everything pattern (D10 in legacy deferred doc) was identified as a design tension. Phases allow intermediate validation.
- **Source**: specs/plan/architecture.md (Design Tension T3); Component Map entry for restructure
- **Assumes**: Restructure orchestration remains monolithic even with phase separation (T3 not yet resolved).
- **Status**: settled (monolith tension acknowledged)

## D-5: Graph expansion deferred until search improvements are validated
- **Decision**: Knowledge graph expansion (additional edge types, graph ML) is not implemented. The decision was to wait until RAG synthesis and improved retrieval are validated before adding graph infrastructure.
- **Rationale**: "Defer graph expansion (003 recommendations) until other search improvements are validated. Want to see if KG is needed after RAG synthesis and retrieval are improved." (interview, cycle 1 refinement)
- **Source**: specs/steering/interview.md (Refinement Interview 2026-03-09, first refinement)
- **Status**: settled (deferred)

## D-6: frontmatter.py is the canonical frontmatter parser; duplicate implementations are a known tech debt
- **Decision**: `frontmatter.py` was created to consolidate duplicated parsing implementations. It is canonical but `shared.py`, `analyze_vault.py`, and `search_backends.py` each still contain their own implementations.
- **Rationale**: Consolidation task was partially completed; full migration not yet done.
- **Source**: specs/plan/architecture.md (Design Tension T4)
- **Status**: settled (canonical source exists; dedup migration incomplete)
