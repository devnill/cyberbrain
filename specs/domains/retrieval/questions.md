# Questions: Retrieval

## Q-1: Proactive recall — validated or still unconfirmed?
- **Question**: WI-002 (invocation test plan) and WI-020 (execution) were completed, but the interview noted "haven't seen it work without prompting in Claude Desktop." Is proactive recall reliably triggering in production sessions?
- **Source**: specs/steering/interview.md (initial interview: "This area has been minimally validated"); archive/cycles/001/gap-analysis.md (interview requirements coverage)
- **Impact**: If proactive recall is not triggering reliably, the core memory-extension UX (GP-4) is unmet. Users must manually invoke cb_recall, which contradicts the "feels like memory" goal.
- **Status**: open
- **Reexamination trigger**: Any user session where relevant vault notes exist but were not surfaced automatically; or after WI-030 manual re-test is executed.

## Q-2: Search backend cache invalidation after cb_configure
- **Question**: When a user changes `search_backend` or `embedding_model` via `cb_configure`, the `shared.py` module-level `_search_backend` global is not refreshed. Does this cause stale results within a long-lived Claude Desktop session?
- **Source**: specs/plan/architecture.md (Design Tension T6)
- **Impact**: Config changes silently don't take effect until the MCP server process restarts. The user has no indication their config change was ignored.
- **Status**: open
- **Reexamination trigger**: Any user report of recall behavior not matching their configured backend; or when modifying `cb_configure` or `shared.py`.

## Q-3: Knowledge graph expansion — when to revisit?
- **Question**: Graph expansion was deferred pending validation of RAG improvements (D-4). Have synthesis and retrieval improvements (WI-012) been validated enough to re-evaluate graph expansion?
- **Source**: specs/steering/interview.md (Refinement Interview 2026-03-09, first refinement); archive/cycles/001/gap-analysis.md (Deferred Work section)
- **Impact**: Without graph expansion, semantic links between notes depend entirely on embedding similarity, which may miss structural relationships (causality, supersession, contradiction).
- **Status**: open
- **Reexamination trigger**: After retrieval quality is empirically measured; or if users report missing relevant notes that are structurally related but semantically distant.

## Q-4: WI-045 (automatic indexing) not started
- **Question**: Has the lazy reindex on `cb_recall` plus SessionEnd hook approach (D-6) been implemented?
- **Source**: archive/cycles/002/decision-log.md (OQ3); archive/cycles/002/summary.md (Proposed Refinement Plan)
- **Impact**: Users must manually run `cb_reindex` to keep search index current after vault changes. Stale index produces degraded recall results without any warning.
- **Status**: open
- **Reexamination trigger**: Technical investigation of src/cyberbrain/mcp/tools/recall.py and SessionEnd hook for lazy reindex logic.

## Q-5: WI-046 (implement retrieval interface) not started
- **Question**: Has the `cb_read` multi-identifier, `synthesize`, and `max_chars_per_note` interface (D-7) been implemented?
- **Source**: archive/cycles/002/decision-log.md (OQ4); archive/cycles/002/summary.md (Proposed Refinement Plan)
- **Impact**: The design-approved retrieval interface remains a design document only. The current `cb_read` does not support multi-note reads or synthesis.
- **Status**: open
- **Reexamination trigger**: Technical investigation of src/cyberbrain/mcp/tools/recall.py against the WI-041 design spec.
