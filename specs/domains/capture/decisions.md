# Decisions: Capture

## D-1: Two hook events — PreCompact (synchronous) and SessionEnd (detached)
- **Decision**: Register PreCompact as a synchronous hook and SessionEnd as a detached (nohup) hook; SessionEnd checks the dedup log before running.
- **Rationale**: PreCompact fires reliably before compaction; SessionEnd catches sessions that were never compacted. Running SessionEnd detached ensures it survives after the session exits. Dedup prevents double-extraction.
- **Source**: specs/plan/architecture.md (Hook Architecture section)
- **Status**: settled

## D-2: Three LLM backends — claude-code, bedrock, ollama
- **Decision**: Implement three pluggable backends dispatched by `config["backend"]`: a subprocess `claude -p` backend, an Anthropic Bedrock backend, and a local Ollama backend.
- **Rationale**: Different deployment contexts require different auth models. Claude Code sessions can reuse the session token; headless environments can use Bedrock; local-only setups can use Ollama.
- **Source**: specs/plan/architecture.md (LLM Backend Architecture section)
- **Status**: settled

## D-3: Autofile uses LLM filing decision (create vs. extend)
- **Decision**: When autofile is enabled, a separate LLM call determines whether a beat should create a new note or extend an existing one.
- **Rationale**: Rule-based routing by scope/durability is too coarse; LLM judgment produces better filing decisions, especially for "extend" cases where the beat belongs with an existing note.
- **Source**: specs/plan/architecture.md (Component Map: Autofile)
- **Status**: settled

## D-4: Working-memory beats route to a dedicated folder, independent of scope
- **Decision**: Beats with `durability=working-memory` route to `AI/Working Memory/<project>/` regardless of scope, overriding normal inbox/project routing. When autofile is enabled for WM beats, vault search is restricted to the WM folder subtree.
- **Rationale**: WM beats should cluster with other WM beats for easy review, not scatter into the general vault. The island effect (WM isolated from durable notes) is an accepted tradeoff.
- **Source**: specs/plan/architecture.md (Design Tension T8)
- **Status**: settled

## D-5: Hook vs MCP extraction paths share the extractor layer but diverge in orchestration
- **Decision**: Both the hook path (`extract_beats.py` as CLI) and MCP path (`cb_extract` tool) call the same extractor layer, but hooks go through `main()` (full orchestration including dedup, run log, journal) while `cb_extract` reimplements parts of that orchestration.
- **Rationale**: Not recorded. This is an acknowledged design tension (T5), not a deliberate decision.
- **Source**: specs/plan/architecture.md (Design Tension T5)
- **Status**: settled (tension acknowledged, not yet resolved)
