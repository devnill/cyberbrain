# Questions: Capture

## Q-1: WI-030 manual capture mode re-test pending
- **Question**: Has the emphatic prohibition wording added in WI-023 (manual mode: Claude must not offer to file beats) actually changed model behavior in a live Claude Desktop session?
- **Source**: archive/cycles/001/gap-analysis.md (M1); archive/cycles/001/decision-log.md (OQ11)
- **Impact**: The WI-023 fix is unvalidated. Claude may still offer to auto-file beats when operating in manual mode, confusing the user.
- **Status**: open
- **Reexamination trigger**: Any user session using Claude Desktop in manual capture mode.

## Q-2: Hook/MCP extraction path orchestration divergence
- **Question**: Should `cb_extract` (MCP path) be refactored to call `main()` rather than reimplementing orchestration, or is the current divergence intentional?
- **Source**: specs/plan/architecture.md (Design Tension T5)
- **Impact**: Risk of dedup, run log, or journal behavior diverging silently between hook-triggered and manually-triggered extraction.
- **Status**: open
- **Reexamination trigger**: Any bug involving duplicate extraction or missing journal entries from MCP-triggered extraction.

## Q-3: Relation vocabulary mismatch between code and prompts
- **Question**: `vault.py` validates against a SKOS/Dublin Core vocabulary (`related`, `references`, `broader`, `narrower`, `supersedes`, `wasDerivedFrom`), while extraction prompts instruct the LLM to use a different vocabulary (`related-to`, `causes`, `caused-by`, `implements`, `contradicts`). Relations with prompt-vocabulary predicates are silently normalized to "related". Which vocabulary should be canonical?
- **Source**: specs/plan/architecture.md (Design Tension T7)
- **Impact**: Relation types specified by the LLM are silently discarded, producing less useful knowledge graphs than intended.
- **Status**: open
- **Reexamination trigger**: Any work on knowledge graph quality or relation-based retrieval.
