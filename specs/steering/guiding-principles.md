# Guiding Principles

## 1. Zero Ceremony for the Common Case
Automatic capture requires no user action after initial setup. Manual filing requires minimal input. The system does the classification work. This extends to all curation operations — extraction, filing, enrichment, restructuring, and working memory review should default to automatic behavior that produces good results without user intervention.

## 2. The Vault is the Canonical Store
Everything lives in the user's Obsidian vault — human-readable markdown files they own and can read, edit, and sync. Obsidian is the human review layer. No derived database or index is authoritative; they are acceleration layers that can be rebuilt from vault content.

## 3. High Signal-to-Noise Above All
What gets captured, curated, and injected into context must be directly useful. Irrelevant or diluted content is worse than nothing — it consumes context tokens and can mislead the LLM. A vault full of noise is worse than a small vault with high-quality signal. This applies to extraction (don't capture noise), curation (merge/split to improve discoverability), and retrieval (inject only what's relevant).

## 4. Feels Like Memory, Not a Filing Cabinet
The experience goal is extended cognition — using this feels like having an excellent memory, not like managing a system. The interaction model, recall UX, and how beats are surfaced should feel like remembering, not searching a database. This applies especially to automatic invocation: the system should surface relevant knowledge without being asked.

## 5. Vault-Adaptive, Not Vault-Prescriptive
The system observes and works with the vault structure that already exists rather than imposing its own. The vault's CLAUDE.md is the single source of truth for types, tags, folders, and conventions. The system works whether the vault uses PARA, Zettelkasten, Johnny Decimal, or something idiosyncratic.

## 6. Lean Architecture, Heavy on Quality
Prefer minimal dependencies and simple infrastructure. SQLite over Postgres. Flat files over daemons. Precomputed vectors over real-time inference servers. But never sacrifice output quality for architectural simplicity — if a heavier component demonstrably improves results, it earns its place. The bar is: does this make the user think better?

## 7. Cheap Models Where Possible, Quality Models Where Necessary
Use the cheapest model that produces acceptable output for each task. Classification, routing, and metadata enrichment are cheap-model tasks. Content generation (merging notes, writing hub pages, synthesis) may need stronger models. Model selection should be per-task, not global, once the quality data supports it.

## 8. Graceful Degradation Over Hard Failure
Optional infrastructure (semantic index, embedding model, ruamel.yaml) enhances the system when present but never blocks it when absent. Missing features degrade to simpler alternatives (grep fallback, empty relations, no synthesis). Hooks always exit 0. Non-fatal errors are logged, not raised.

## 9. Dry Run as First-Class Feature
All destructive operations support dry-run mode showing full content, types, tags, destinations, and routing rationale without writing anything. The pipeline executes fully in dry-run — the only difference is the final write. This is necessary for building trust in automated curation.

## 10. YAGNI Discipline
Don't add what isn't needed. Don't design for hypothetical future requirements. The right amount of complexity is the minimum needed for the current task. Features earn their way in through demonstrated need, not anticipated need.

## 11. Curation Quality is Paramount
Notes must be highly discoverable as the vault grows. Restructuring, merging, splitting, hub creation, and clustering must produce results that are near perfect — a bad merge or false grouping actively harms the vault. When quality can't be guaranteed automatically, surface the decision to the user rather than proceeding with a bad result.

## 12. Iterative Refinement Over Big-Bang Releases
Curation heuristics are refined through repeated testing against real vault data. Each cycle produces measurable quality improvements. Evaluation tooling that enables rapid comparison of alternative outputs accelerates this cycle more than any single algorithmic improvement.

## 13. Works Everywhere the User Works
Claude Code is the primary interface, but Claude Desktop and mobile are equally important. Knowledge should be capturable from any interface and retrievable from any interface. Automatic invocation (proactive recall) should work without the user knowing which tools exist or how they're named.
