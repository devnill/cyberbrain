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

## D-6: autofile_beat gains can_ask parameter to prevent silent beat loss
- **Decision**: Add `can_ask: bool = False` to `autofile_beat`. Non-interactive callers (hooks, `cb_extract`) receive `can_ask=False` and fall back to inbox routing when confidence is below threshold. Only `cb_file` passes `can_ask=True`.
- **Rationale**: Without this guard, hooks and `cb_extract` silently dropped beats when `uncertain_filing_behavior="ask"` was configured. Silent beat loss violates GP-8.
- **Source**: specs/archive/cycles/002/decision-log.md (DL11); specs/archive/incremental/043-filing-confidence-uncertainty-handling.md
- **Status**: settled

## D-7: Hardcoded confidence threshold branch removed from autofile.py (YAGNI)
- **Decision**: Remove the `elif confidence < 0.7` branch from `autofile.py`. The branch was unreachable when `uncertain_filing_threshold >= 0.7` and was not in the WI-043 spec.
- **Rationale**: YAGNI discipline (GP-10). An unreachable branch that imposes an invisible constraint on future threshold changes should not exist.
- **Source**: specs/archive/cycles/002/decision-log.md (DL12)
- **Status**: settled

## D-8: cb_uncertain_routing frontmatter field stores float confidence, not bare boolean
- **Decision**: Change `cb_uncertain_routing` frontmatter field from `cb_uncertain_routing: true` to `cb_uncertain_routing: {confidence:.2f}` (e.g. `cb_uncertain_routing: 0.58`).
- **Rationale**: The bare boolean discarded the confidence value, making it impossible to audit why a note was routed to inbox. The float preserves the signal for human review and future automation.
- **Source**: specs/archive/cycles/002/decision-log.md (DL13)
- **Status**: settled

## D-9: cb_file intake interface expanded with title and durability parameters
- **Decision**: `cb_file` gains a document intake mode: when `title` is provided, the tool accepts a pre-written document, applies frontmatter, and routes via autofile or a specified folder without running LLM extraction. A `durability` parameter (default "durable") is added for this mode; it is ignored in the original beat-extraction mode.
- **Rationale**: Designed in WI-040; approved with `durability` parameter addition before implementation. Net tool count stays at 11. WI-042 implements this design.
- **Source**: specs/archive/cycles/002/decision-log.md (DL9); specs/plan/intake-interface-design.md
- **Status**: provisional (design approved; implementation status in Q-4)
