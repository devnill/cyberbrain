# Deferred Decisions & Future Work

This document captures design decisions, features, and architectural questions that are intentionally deferred. Items here are not forgotten — they are explicitly scoped out of the current implementation with a note on why and what would trigger revisiting them.

---

## D1: Scheduled maintenance jobs

**What:** `cb_review` and `cb_restructure` should eventually run automatically on a schedule — e.g., a weekly post-session hook or cron job — rather than requiring manual invocation.

**Why deferred:** Manual-first lets us validate behavior before automating it. Automated destructive jobs (note deletion, merging) carry more risk if they misbehave silently.

**Trigger to revisit:** Once `cb_review` and `cb_restructure` have been run manually several times and the outputs are consistently trustworthy, scheduling becomes a low-risk addition.

---

## D2: Human-in-the-loop synthesis quality testing

**What:** A script or tool for supervised evaluation of recall and synthesis quality. A human reviewer would see: the query that triggered recall, which notes were surfaced (including which were from working memory), and the synthesized output — then rate whether the result was useful or noisy.

**Why deferred:** Requires building an evaluation dataset and review UX. The working memory recall logging (`wm-recall.jsonl`) is being built now to collect the raw data needed. The evaluation tooling comes after enough data exists to review.

**Trigger to revisit:** Once working memory has been in use for several weeks and `wm-recall.jsonl` has meaningful volume, build a simple review script that loads the log and prompts for human ratings.

---

## D3: Search and RAG architecture improvements

**What:** Move from the current FTS5 + HNSW retrieval toward a more complete RAG pipeline: reranking (cross-encoder or LLM-based), query expansion, proper document chunking, and maximal marginal relevance for diversity in results.

Two specific known gaps:

1. **Chunking granularity** — The BM25 index currently stores each note as one document (title + summary + tags + body). The HNSW semantic index indexes only title + summary + tags. For long notes that cover multiple topics, this dilutes the retrieval signal: a search for a specific concept can surface a note that only mentions it briefly, at the same score as a note that is entirely about it. Chunk-level indexing (by paragraph or  section) would make both BM25 and semantic search more precise.

2. **Clustering signal quality** —  builds note clusters by querying the search index and using score > 0 adjacency. This has two weaknesses: (a) notes with no summary or tags produce very short BM25 queries that rely entirely on title keyword overlap, and (b) BM25 doesn't normalize for document length, so long multi-topic notes can appear adjacent to many unrelated clusters. Chunk-level indexing would naturally improve clustering too, since queries would match against focused section content rather than entire note bodies.

**Why deferred:** The current hybrid search is functional and the retrieval quality problems are not yet precisely characterized. Premature optimization here risks adding complexity before knowing which direction to optimize in.

**Trigger to revisit:** After D2's evaluation tooling exists and shows concrete failure modes in retrieval, or if  clustering quality is consistently poor on real vaults. Fix measured problems, not assumed ones.

---

## D4: Working memory search tuning

**What:** Determine the optimal treatment of working memory notes in search results. Current approach: index identically to durable notes, no special weighting. Open questions: should expired WM notes be excluded? Should WM notes be weighted lower in ranking? Should WM get a separate search tier that's only consulted in project-specific contexts?

**Why deferred:** Any tuning decision needs empirical data. The recall logging (D2) provides the data. Without it, any weighting choice is a guess.

**Trigger to revisit:** After D2 generates enough annotated examples to measure whether WM notes are helping or hurting precision.

---

## D5: Cross-device and cross-interface capture

**What:** The PreCompact hook only fires in Claude Code on desktop. Sessions on Claude.ai (web or mobile), other LLM interfaces, or sessions that close without compaction are not captured. G11 and G12 in GOALS.md describe the full scope: knowledge should be capturable from any interface and should not depend on a specific session lifecycle event.

**Why deferred:** Requires per-interface capture mechanisms. The Claude.ai web interface has no hook system. Mobile has no capture path at all. Each interface needs its own solution.

**Trigger to revisit:** When session-end capture (G12) or mobile/web capture (G11) becomes a felt pain point. Likely requires either a browser extension, a manual import workflow per interface, or waiting for platform-level support.

---

## D7: Natural language workflow discoverability

**What:** Users should be able to invoke cyberbrain tools through natural language without knowing which tools exist or how they are named. For example, "clean up my working memory" should trigger `cb_review`, "what do I know about authentication?" should trigger `cb_recall`, and "tidy up my vault" should trigger `cb_restructure` — without the user needing to know any of those tool names. Complex operations (like consolidation or review) should also automatically chain dry-run calls before destructive execution, so the user sees a preview before anything is committed.

**Why deferred:** Requires either a routing layer in the Claude Desktop system prompt, an orchestrator agent that maps intents to tool calls, or prompt engineering work to make Claude reliably map natural language to the right tool sequence. The tools themselves need to be stable and well-tested before the discoverability layer is worth building.

**Trigger to revisit:** Once the core tools (`cb_review`, `cb_restructure`, `cb_recall`, `cb_enrich`) are in regular use and their behavior is well-understood. The system prompt in `prompts/claude-desktop-project.md` is the natural place to add this intent-routing guidance.

---

## D8: cb_restructure dry-run content preview

**What:** The current dry-run mode for `cb_restructure` shows which notes would be merged or split but does not show the LLM-generated output content. The user commits to a restructure without seeing the resulting notes first. A more complete dry-run would run the full LLM call and present the proposed output for review — without writing any files — so the user can accept, reject, or adjust before anything is written or deleted.

**Why deferred:** Implementing this cleanly requires either a two-phase confirmation flow (dry-run → user approval → execute) or storing the LLM output between calls, neither of which fits naturally into the current single-call tool model. The current workaround (small `max_clusters` + checking the errata log) is sufficient for cautious use.

**Trigger to revisit:** Once `cb_restructure` has been used enough to know whether merge and split quality are reliably good. If LLM-generated output consistently requires manual correction, the preview becomes worth building.

---

## D6: Configurable TTL per beat type or topic

**What:** Working memory notes currently use a flat 28-day review window. Some topics warrant shorter windows (e.g., a transient bug mid-fix) and some warrant longer (e.g., an architectural decision still being evaluated over weeks). Per-type or per-topic TTL configuration would let the system be more precise.

**Why deferred:** The 28-day default covers most cases adequately. Adding per-type TTL before we have data on what typical review patterns look like is premature.

**Trigger to revisit:** After `cb_review` has been used enough to identify recurring patterns of notes that are always reviewed too early or always stale by the time they're reviewed.

---

## D9: Distribution and one-click install

**What:** The current install script (`install.sh`) requires a terminal and is not accessible to non-technical users. The end state is two supported deployment modes:

- **Local stdio** — server runs as a child process on the user's machine, vault on local disk. Always supported.
- **Remote hosted** — server runs on cloud infra, HTTPS + auth (OAuth or API key), vault backed by cloud storage (e.g. Obsidian Sync, S3). Optional, for users who want zero local footprint or multi-device access.

Both modes must be installable without a terminal for non-technical users.

The planned progression:

1. **`uvx` + PyPI** — publish the server as a Python package. Any MCP client can launch it via `uvx cyberbrain` without a manual install step. Low effort, eliminates the install script for technical users, and enables listing on Smithery (and similar MCP registries) for one-click config in supported clients.

2. **Claude Desktop Extension (`.dxt`)** — package for one-click install from Claude Desktop settings. Handles venv setup, MCP config registration, and vault path onboarding without a terminal. Best near-term path for non-technical Desktop users.

3. **Native setup app (Tauri)** — small cross-platform desktop app that shows a vault path picker, writes MCP config for detected clients, and registers the PreCompact hook if Claude Code is present. Universal one-click installer that makes no assumptions about which AI client the user has. Distributable as a direct download or Mac App Store.

4. **Remote hosted mode** — add Streamable HTTP transport alongside stdio. Self-hostable on any VPS or PaaS (Fly.io, Railway). Add OAuth or API key auth per the MCP spec. Vault access requires cloud-backed storage; local vault + local server remains a supported configuration permanently.

**Why deferred:** Core functionality comes before packaging. The install script is adequate for current users. Distribution work pays off once the tool is stable enough to recommend to non-technical users.

**Trigger to revisit:** When the primary friction to adoption is installation rather than functionality. Start with `uvx` + PyPI (low effort), then `.dxt` for Desktop users, then the Tauri app and remote hosted mode if demand warrants it.

---

## D10: cb_restructure decision/generation split

**What:** `cb_restructure` currently uses a single LLM call that must both decide what actions to take (merge, hub-spoke, subfolder, keep-separate, split, keep) and generate the full note content for every affected note. This conflates two very different tasks: classification (low token, low latency, small model viable) and content generation (high token, requires quality reasoning). The better architecture is:

1. **Decision call** — small/fast model sees cluster summaries and titles, returns action decisions only (no content generation)
2. **Generation calls** — per-cluster or per-note calls that receive the decided action and generate the actual merged/hub content

This would also enable showing the user decisions before committing to content generation (partially addressing D8), and would allow per-phase model selection.

**Why deferred:** The single-call approach works and is simpler. Splitting requires API changes (or a multi-step internal flow) and more complex state management between calls. The cost of the current approach is primarily latency and occasional timeouts on large prompts.

**Trigger to revisit:** When restructure timeouts become frequent on real vaults, or when D8 (dry-run content preview) is prioritized. The split naturally enables D8.

---

## D11: Per-tool model configuration

**What:** Currently there is a single `model` config key that applies to all LLM calls across all tools. Different tools have very different requirements: `cb_recall` synthesis is low-stakes and fast; `cb_restructure` content generation requires strong reasoning and long outputs; `cb_enrich` batch enrichment benefits from a fast cheap model. Per-tool model keys would allow mixing models by capability and cost:

```json
{
  "model": "claude-haiku-4-5",
  "restructure_model": "claude-sonnet-4-6",
  "recall_model": "claude-haiku-4-5"
}
```

For ollama users this matters especially: a 7B model is adequate for recall synthesis but will produce poor restructure output.

**Why deferred:** Most users run a single model. Adding per-tool keys before there's a clear pattern of "X tool needs a better model" is premature configuration complexity.

**Trigger to revisit:** Once D10 (decision/generation split) is implemented — the decision phase and generation phase naturally want different models. Also revisit if local model users report poor quality on specific tools.

---

## D12: Prompt tuning per model and PKMS methodology

**What:** Prompt behavior varies significantly across models. A prompt tuned for Claude Sonnet (strong instruction following, nuanced judgment) may produce poor results with a 7B local model (needs explicit rules and hard anchors) or a different frontier model (may interpret ambiguous guidance differently). Similarly, different personal knowledge management (PKMS) methodologies (Zettelkasten, PARA, LYT, Johnny.Decimal) have fundamentally different opinions about folder depth, note granularity, and hub vs. atomic note structure. The current prompts embed implicit assumptions about both.

Two directions to explore:

1. **Model-variant prompts** — ship predefined prompt variants tuned for different model capability tiers (e.g. `restructure-system-small.md` for local models ≤14B, `restructure-system-default.md` for frontier models). Selected automatically based on the configured model or manually overridable. Small-model variants use harder rules and explicit anchors; frontier variants use softer guidance with more room for judgment.

2. **PKMS methodology parameters** — allow the user to declare their organizational philosophy (Zettelkasten atomic notes, PARA project-area-resource-archive, LYT Maps of Content, etc.) and inject methodology-specific guidance into prompts. This could be part of the preferences system (D3/Change 3) or a separate `methodology` config key. For example, a Zettelkasten user wants atomic notes and explicit links over merged documents; a PARA user wants strict folder hierarchy over flat + hub structure.

**Why deferred:** The prompt system currently uses a single file per prompt. Multi-variant or parameterized prompts require a selection/injection layer that doesn't exist yet. The preferences system (already implemented via vault CLAUDE.md) is a lightweight version of this — users can already express methodology preferences in natural language. Full model-variant prompts are worth building once there's evidence that the gap between model tiers is causing consistent quality problems.

**Trigger to revisit:** When local model users report that the default prompts produce wrong action choices (e.g. always hub-spoke instead of subfolder), or when multiple users with different PKMS methodologies report that the prompts fight their organizational style. The preferences system is the first line of defense — check whether it solves the issue before building prompt variants.

---

## D13: Vault health audit against CLAUDE.md and reference materials

**What:** A tool (or `cb_review` extension) that critically evaluates whether the vault's actual contents conform to the organizational principles, type vocabulary, and folder conventions defined in the vault's CLAUDE.md and any reference materials linked from it. When deviations are found, the tool should determine whether to fix the vault (restructure/retype notes that violate conventions) or fix the CLAUDE.md (the convention itself evolved and the documentation is stale).

Two classes of deviation to detect:

1. **Vault violates CLAUDE.md** — notes using types not in the vocabulary, notes in folders that contradict stated organization rules, notes with missing required frontmatter fields, hub notes that don't link to everything they should. Resolution: fix the notes.

2. **CLAUDE.md is stale** — the vault has evolved organically in a way that consistently contradicts the documentation (e.g. a folder convention that nobody follows because it doesn't fit usage patterns). Resolution: update the CLAUDE.md to reflect reality, or make a deliberate choice to re-enforce the old convention.

The tool should produce a structured audit report: deviations found, severity, and recommended action (fix vault vs. fix docs) with rationale.

**Why deferred:** Requires reading and parsing vault CLAUDE.md conventions programmatically (not just the preferences section), then comparing against actual vault state. Non-trivial to implement well, especially the "is this a vault problem or a docs problem?" judgment. The restructure and enrich tools are the current proxies for vault health.

**Trigger to revisit:** Once the preferences system and restructure tooling are mature enough that the vault is reasonably well-organized. The audit tool is most valuable when the vault has stabilized and you want systematic assurance it matches its own documentation.

---

## D14: Interactive restructure actions (move-misplaced, delete-low-quality)

**What:** `cb_restructure`'s audit phase correctly identifies misplaced notes (with suggested destinations) and low-quality stubs, but currently only prints flags for manual review. Two actions need user confirmation before executing:

1. **Move misplaced notes** — the audit provides `flag-misplaced` with a `suggested_destination`. The tool should present the proposed move and execute it after user confirmation. False positives are possible (e.g., a note about radiant barriers in a Solar Power folder is topically adjacent but not really solar-specific), so automatic moves without confirmation are risky.

2. **Delete or enrich low-quality notes** — stubs with no real content beyond a wikilink reference should be deletable. Borderline notes could be enriched via `cb_enrich`. Both actions are destructive and need user approval.

The implementation likely requires either a multi-turn confirmation flow within the MCP tool (not currently supported cleanly), or a separate `cb_triage` tool that presents flagged items one at a time for accept/reject/skip decisions.

**Why deferred:** The audit flags are accurate and useful as-is for manual cleanup. Building the interactive confirmation UX is a separate concern from the audit logic itself. The current workaround (audit flags + manual file moves) works.

**Trigger to revisit:** When the volume of flagged notes per restructure run makes manual cleanup tedious, or when an MCP pattern for multi-turn user confirmation becomes available.
