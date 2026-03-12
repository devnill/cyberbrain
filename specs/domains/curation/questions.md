# Questions: Curation

## Q-1: Restructure false groupings — model tier or algorithm?
- **Question**: Are restructure false groupings primarily a model tier issue (haiku vs. sonnet/opus) or a fundamental algorithmic problem with the clustering approach?
- **Source**: specs/steering/interview.md (initial interview: "In a future refinement, want to critically evaluate deferred tasks to ensure they serve the overarching goals. The current approach needs several passes, but there might be a better solution.")
- **Impact**: If it's a model tier issue, upgrading the restructure model resolves it. If it's algorithmic, the current multi-phase pipeline may need architectural rethinking.
- **Status**: open
- **Reexamination trigger**: After running restructure with sonnet/opus and comparing output quality to haiku results; or after collecting user feedback on specific false grouping examples.

## Q-2: Restructure.py monolith — when to split?
- **Question**: `restructure.py` is 2,171 lines. The phase separation (audit/group/decide/generate/execute prompts) exists but orchestration is monolithic. Is the current size creating maintenance risk?
- **Source**: specs/plan/architecture.md (Design Tension T3)
- **Impact**: Monolithic orchestration makes it harder to test individual phases, debug failures, and add new grouping strategies.
- **Status**: open
- **Reexamination trigger**: When adding a new grouping strategy or debugging a phase-specific failure.

## Q-3: Frontmatter parsing consolidation — complete migration to frontmatter.py?
- **Question**: Three files (`shared.py`, `analyze_vault.py`, `search_backends.py`) still contain their own frontmatter parsing implementations despite `frontmatter.py` being canonical. Should all be migrated?
- **Source**: specs/plan/architecture.md (Design Tension T4)
- **Impact**: Parsing behavior can diverge silently between callers. Bugs fixed in `frontmatter.py` may not propagate to the other implementations.
- **Status**: open
- **Reexamination trigger**: Any frontmatter parsing bug or when touching any of the three files with duplicate implementations.
