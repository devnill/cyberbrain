# Domain Registry

current_cycle: 12

## Domains

### capture
The knowledge capture pipeline: hooks (PreCompact, SessionEnd), transcript parsing, LLM extraction, autofile filing decisions, vault I/O, run log, and deduplication. This domain covers how knowledge gets into the vault automatically.
Files: domains/capture/policies.md, decisions.md, questions.md

### curation
Vault quality maintenance: enrichment (batch frontmatter), working memory review, restructuring (merge/split/hub), quality gates, and the LLM-as-judge validation pattern. This domain covers how vault quality is maintained over time.
Files: domains/curation/policies.md, decisions.md, questions.md

### retrieval
Knowledge retrieval: three-tier search backends (grep/fts5/hybrid), recall, LLM synthesis, automatic invocation (proactive recall), and the search index lifecycle. This domain covers how knowledge gets back out of the vault.
Files: domains/retrieval/policies.md, decisions.md, questions.md

### distribution
Packaging and delivery: Claude Code plugin system, pyproject.toml, uv dependency management, MCP server launch, hook script path resolution, two-level config, install.sh for Claude Desktop, and quality tooling (ruff, basedpyright, pre-commit). This domain covers how the system is installed, updated, configured, and quality-gated.
Files: domains/distribution/policies.md, decisions.md, questions.md

---

## Cross-Cutting Concerns

**Vault CLAUDE.md as shared contract**: The vault's `CLAUDE.md` is injected into extraction, autofile, enrichment, and restructure prompts. It is the single source of truth for beat type vocabulary and user preferences. Changes to it affect capture, curation, and retrieval simultaneously.

**Model selection**: Per-task model selection (`get_model_for_tool`) spans capture (extraction backends) and curation (enrich/review/restructure). The cheapest-model-where-possible principle (GP-7) applies across both domains but the specific model choices are domain-specific.

**Graceful degradation**: GP-8 applies differently in each domain — hooks must never block (capture), bad curation must surface to user rather than fail silently (curation), search degrades through tiers (retrieval), plugin paths must not hard-fail on missing files (distribution).

**Cycle 003 completion**: All 9 work items from cycles 002-003 are now complete and reviewed: WI-042 (intake interface), WI-044 (filing accuracy), WI-045 (automatic indexing), WI-046 (retrieval interface), WI-047 (vault CLAUDE.md update), WI-048 (pytest markers), WI-049 (affected-only plugin), WI-050 (quiet defaults), WI-051 (test wrapper). See archive/cycles/003/ for review artifacts.

**CLAUDE.md stale after restructure decomposition**: CLAUDE.md still references `restructure.py` as a single file. The module is now a sub-package. See distribution/Q-12.
