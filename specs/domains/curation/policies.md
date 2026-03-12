# Policies: Curation

## P-1: LLM-as-judge quality gate on curation output
All curation tools (restructure, enrich, review) run their output through an LLM judge before writing. Low-confidence output surfaces a decision to the user rather than proceeding with a bad result.
- **Derived from**: GP-11 (Curation Quality is Paramount)
- **Established**: cycle 1 refinement interview
- **Status**: active

## P-2: Model selection is per-task, not global
Each curation tool resolves its model via `get_model_for_tool(config, tool)`, allowing cheap models for classification and enrichment and stronger models for synthesis and restructuring.
- **Derived from**: GP-7 (Cheap Models Where Possible, Quality Models Where Necessary)
- **Established**: WI-013 (resolved design tension T2)
- **Status**: active

## P-3: All vault deletions use soft delete (_move_to_trash)
No curation operation permanently deletes a vault note. Notes are moved to the trash folder with vault-relative path structure preserved, never hard-deleted.
- **Derived from**: GP-8 (Graceful Degradation Over Hard Failure) + Constraint C10
- **Established**: planning phase
- **Status**: active

## P-4: Dry-run is mandatory for curation operations
Every curation tool exposes a dry-run mode that executes the full pipeline and shows content, types, tags, destinations, and routing rationale without writing anything.
- **Derived from**: GP-9 (Dry Run as First-Class Feature)
- **Established**: planning phase
- **Status**: active

## P-5: Bad curation is worse than no curation
A false grouping, bad merge, or incorrectly split note actively harms vault discoverability. Curation tools must err on the side of surfacing decisions to the user rather than proceeding with low-confidence output.
- **Derived from**: GP-3 (High Signal-to-Noise Above All) + GP-11 (Curation Quality is Paramount)
- **Established**: planning phase
- **Status**: active

## P-6: Evaluation tooling is internal dev tooling, not a product feature
`extractors/evaluate.py` (and any evaluation harness) exists for iterating on curation heuristics, not for user-facing use. Evaluation results that cannot be acted on during regular usage do not belong in the MCP server.
- **Derived from**: GP-1 (Zero Ceremony for the Common Case) + GP-10 (YAGNI Discipline)
- **Established**: cycle 1 refinement interview
- **Status**: active
