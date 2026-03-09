# Interview Transcript — 2026-03-09

## Context
Retroactive planning capture for cyberbrain, an existing knowledge capture and retrieval system. The project has a mature codebase (~7,200 LOC Python/Bash), comprehensive test suite (17,600 LOC), and detailed legacy specs. This planning session establishes a baseline for future `/ideate:refine` cycles.

The user provided all existing specs (v1_spec.md, GOALS.md, deferred.md, mcp_gaps.md, mcp-enhancements.md, mcp-architecture.md, enhanced-retrieval.md, knowledge-graph-enhancement.md) and the project CLAUDE.md. A full codebase survey was performed by the architect agent.

---

**Q: What is the scope of what you want to plan? Are you retroactively creating a plan for the existing system, or planning new changes?**
A: Retroactively capture the current state so we can continue to refine. Existing specs should be moved to a subfolder for safekeeping while assembling the correct ideate artifact structure.

**Q: What is the current focus?**
A: Two main goals:
1. Continue to refine the Obsidian vault curation logic — this covers the full pipeline: extraction, autofiling, daily journal, enrichment, working memory, and restructuring. Restructuring has proven particularly challenging as it requires intelligently rewriting notes by merging, combining, creating sub-hubs, and applying clustering heuristics. This needs to be near perfect because notes must be highly discoverable as the vault continuously grows.
2. Begin serious work on improving retrieval, aiming for a RAG system that can effectively supplement memory and context systems. Claude Code is the primary use case, but it should work equally well in Claude Desktop and mobile without manual tool invocation.

**Q: How do you want execution structured?**
A: As much work in parallel as possible. One tension: vault curation heuristics need human-in-the-loop refinement. Creating good heuristics has been tricky and required a lot of tweaking. LLMs can critically evaluate output quality but producing high-quality output has been harder. This might be a model tier issue (haiku vs sonnet/opus) but the process needs to become less hands-on, or at least faster to iterate on.

**Q: On restructure quality — is the right direction to split into decision/generation phases (D10), or is the problem more fundamental?**
A: Not sure about the best approach. In a future refinement, want to critically evaluate deferred tasks to ensure they serve the overarching goals. The current approach needs several passes, but there might be a better solution if we work through the problem. Cheap models are preferred where possible, but that's debatable. The logic itself is prone to false groupings at times which can be confusing.

**Q: On retrieval scope — what's missing to make it RAG-ready?**
A: Several things: fully implementing RAG including synthesis and context injection, automatic invocation (proactive recall without user triggering), and precision improvements. Has drifted away from the original goal of a full knowledge graph but wants to research ML approaches that could work with knowledge graphs to increase semantic search quality. This will require a large effort but is worthy of investigation.

**Q: What ML approaches are you thinking for knowledge graph augmentation?**
A: Currently using a transformer for semantic search. Not deeply versed in what's available, but having more types of edges could augment semantic search to find stronger links than just embedding chunks. This needs significant research and testing. Open to running a local graph database if it makes sense, but likes the lean nature of the project. Precomputing vectors into SQLite is a fine compromise but debatable. Worth noting: may want to reshape the app for hosted deployment in the future, in which case larger infrastructure footprints could make sense.

**Q: On automatic invocation — what's the gap?**
A: This area has been minimally validated. Haven't seen it work without prompting in Claude Desktop. Need a test plan for manual validation to gauge the state of the feature set before planning further revisions.

**Q: Any other areas of attention?**
A: Yes — developing better testing and planning tools is a cross-cutting concern. Dry run is a very crude instrument. It might be worth investing effort into creating dedicated evaluation tools that allow comparing which results look best when presented with several alternatives. This applies across the full curation pipeline, not just restructuring.
