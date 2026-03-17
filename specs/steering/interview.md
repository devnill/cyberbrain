# Steering Interview

## Initial Planning Interview — 2026-03-09

See `specs/legacy/v1_spec.md` for the original product vision captured in the initial planning session.

---

## Refinement Interview — 2026-03-12

**Context**: Cycle 002 capstone review identified critical bugs in the post-WI-034 (src layout migration) codebase. User also surfaced three new workstreams: intake/retrieval tool interface redesign, filing accuracy improvements, and automatic indexing.

**Q: Do the existing guiding principles still apply?**
A: Yes, with no changes needed. The user confirmed all principles still hold.

**Q: The cycle 002 review found critical bugs: install.sh references deleted directories, and vault.py/search_backends.py/evaluate.py have bare imports that fail in packaged installs. Should these be addressed first?**
A: Yes — critical bugs take priority. All three should be fixed before any new feature work begins. They block users from installing and running the package.

**Q: You mentioned wanting to reshape the MCP tools for intake and retrieval. What problems are you seeing with cb_extract and cb_file?**
A: cb_extract is for session extraction (extracting beats from a Claude conversation transcript). cb_file is for manually capturing a specific insight or note. But there's a third use case: I sometimes have Claude generate a research report or findings document as a standalone artifact, and I want to file that whole document into the vault — not just extract beats from a conversation about it. That "document intake" mode doesn't fit cleanly into either existing tool.

**Q: And for retrieval — what's the issue with cb_recall and cb_read?**
A: cb_recall does search (semantic/keyword) and returns matching notes. cb_read reads a specific note by path. The problem is that cb_recall can also synthesize context from multiple results, and cb_read can also be used for checking what's already in a folder. There's redundancy and unclear purpose separation. I want cleaner, non-redundant interfaces.

**Q: Should we add new tools for these use cases, or redesign the existing ones?**
A: Redesign. Adding interfaces alone is not good — we should remove redundancies. The tool count must not increase relative to what is removed. If we add document intake mode, something else needs to go or be merged.

**Q: On filing accuracy — what's broken?**
A: Two things. First, the clustering algorithm in cb_restructure sometimes produces bad clusters that don't reflect semantic relationships. Second, when autofile routes a beat to a folder, I'd like to know how confident it is. If confidence is low, I want the option to either let it go to the inbox or to ask me before filing.

**Q: For the uncertainty handling — should "ask me" mean a prompt at filing time, or a config flag?**
A: A config flag. I don't want to be interrupted every time there's a low-confidence filing. Set a config key like `uncertain_filing_behavior` with values `ask` or `inbox`, and apply it at filing time.

**Q: Should confidence scoring apply per-beat or per-session?**
A: Per-beat. Each beat might route differently — one might be highly certain (project-specific technical detail), another uncertain (general insight that could go anywhere).

**Q: On automatic indexing — what's the gap?**
A: When beats are written to the vault, they're indexed. But if I edit notes manually in Obsidian, add files, or move things around, the search index gets stale. I'd like the index to stay current without manual `cb_reindex` calls.

**Q: Should this be triggered by file system events, a scheduled job, or something else?**
A: I don't know — that's worth researching first. I'd prefer a lightweight approach that doesn't require a persistent daemon. If cron or a Claude Code hook can cover it, that's better than a file watcher.

**Q: Should we update the vault CLAUDE.md schema to reflect the new tool names and capabilities after all this is implemented?**
A: Yes, and regenerate the current vault's CLAUDE.md from the updated schema. But I want to review the proposed changes before anything is written to the live vault.

**Q: Any ordering constraints? Which items are blockers for others?**
A: The critical bug fixes (install.sh, bare imports) should go first but don't block design work. The design proposals for intake and retrieval (040, 041) should be presented to me before any implementation starts. The vault CLAUDE.md update (047) comes last and requires approval before writing.

**Q: Any execution preferences — sequential vs parallel, model choices?**
A: Parallel where possible, max 4 concurrent agents. Research and design work can use opus. Implementation uses sonnet. I only need to be consulted at the two pause points: design review for WI-040/041, and before WI-047 writes to the live vault. All other decisions are unilateral.
