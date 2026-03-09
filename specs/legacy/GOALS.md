# Project Goals

This document describes the motivating goals behind the cyberbrain project. It is intended to guide development decisions, prioritization, and design tradeoffs — not to describe implementation.

---

## G1: Capture the intellectual exhaust of LLM interactions

Every conversation with an LLM produces knowledge. Prompts contain intent, domain context, and constraints the user has reasoned through. Responses contain explanations, decisions, solutions, and patterns. Most of this is read once and forgotten.

The goal is to treat these interactions as a source of persistent, structured knowledge — not ephemeral text. The signal is already being produced; this project exists to collect it.

**Success looks like:** A conversation produces beats automatically. The user does not need to manually decide what's worth saving during the session.

---

## G2: Prevent valuable context from being lost at session boundaries

Claude Code sessions end. Compaction truncates history. Context windows are finite. Any of these events can destroy the intellectual output of a session — architectural decisions, discovered gotchas, debugging conclusions — not because the work was unimportant but because the system had nowhere to put it.

The PreCompact hook is the primary mechanism here. It fires before the transcript is truncated and extracts beats from the full session content. But compaction is only one of many ways a session can end — the session may close, time out, or simply stop without a compaction step. The goal extends to all of these: any event that threatens context loss is an opportunity to trigger extraction. See also G12.

**Success looks like:** The developer can compact freely without anxiety about losing what was learned. Sessions that end without compaction are also captured. The transcript being compressed or closed is distinct from the knowledge it contained.

---

## G3: Bridge the gap between LLM memory and human memory

LLMs have no memory across sessions. Humans have imprecise memory across time. Neither is sufficient alone:

- An LLM starting a new session on a familiar project has no idea what was decided last week.
- A human returning to a project after three months may remember that a decision was made but not why, or not at all.

The knowledge graph sits between these two memory models. It provides precise, queryable recall of past context that neither party can reliably hold on their own. Recalling relevant context at session start can inject months of relevant history.

**Success looks like:** Resuming work on a project feels like continuing it, not restarting it. The LLM has access to the relevant history and can reason from it immediately.

---

## G4: Support multiple knowledge sources beyond LLM sessions

LLM chat sessions are a rich source, but not the only one. Useful knowledge surfaces in many places: a Stack Overflow answer, a decision made in a Slack thread, notes from a meeting, a pattern discovered while reading documentation. All of these have the same shelf life problem: read once, lost.

The project should provide low-friction paths to file knowledge from any source. The vault should be source-agnostic. A snippet filed manually should be as useful and retrievable as one extracted automatically from a session.

**Success looks like:** Filing a piece of knowledge takes less than 10 seconds and doesn't require the user to think about where it goes. The system handles classification and routing.

---

## G5: Maximize the compounding value of accumulated knowledge

A vault with 10 beats is marginally useful. A vault with 1,000 beats covering three years of work is qualitatively different — it functions as an externalized long-term memory that can be queried, searched, and injected into any session.

Each beat filed increases the value of future sessions. Decisions already made don't need to be re-made. Bugs already fixed don't need to be re-fixed. Patterns already validated don't need to be re-discovered. The compounding effect is the central value proposition.

**Success looks like:** The vault is demonstrably more valuable after 12 months of use than after 1 month. Users who use the system regularly build a meaningful intellectual asset.

---

## G6: Reduce rework caused by forgotten solutions

A large fraction of the time spent on technical problems is re-solving problems that have already been solved — either by the same person in a previous session or by someone on the same team. The root cause is not lack of skill; it's lack of recall.

Error-fix and problem-solution beats directly target this. When the same error recurs, the solution should surface immediately. When a decision was already made and documented, it shouldn't be re-litigated from scratch.

**Success looks like:** The developer searches for a problem they vaguely remember solving, finds it, and applies the fix in minutes rather than re-debugging from scratch.

---

## G7: Maintain a high signal-to-noise ratio through intentional structure

Not everything in an LLM session is worth preserving. Tool invocations, file reads, intermediate reasoning, and mechanical back-and-forth are noise. Decisions, insights, fixes, and validated patterns are signal.

The extraction LLM is responsible for this distinction. The beat schema (6 typed categories, required tags, scope classification) is a mechanism for structured signal extraction. Intentional tagging and scoping during filing determines whether a beat is findable later.

A vault full of noise is worse than a small vault with high-quality signal. Retrieval quality degrades when search results are cluttered with irrelevant beats.

**Success looks like:** A search for a specific error message returns the fix, not five unrelated notes that happened to mention a similar term.

---

## G8: Minimize the cognitive burden on the user

The system should do the work. Classification, tagging, routing, and filing decisions should default to automatic. The user's job is to work — the knowledge graph should capture the byproduct of that work without demanding additional attention.

Manual filing exists for cases where the user has something specific to capture immediately. But the dominant flow — extract on compaction, autofile to the right place — should require zero deliberate action.

**Success looks like:** After initial setup, the vault grows without the user actively managing it.

---

## G9: Be extensible to new ingestion sources

The current implementation focuses on Claude Code sessions and manual filing. Future sources include: other LLM interfaces (Claude.ai, API calls), messaging platforms, web research sessions, and document imports.

The architecture should not assume Claude Code sessions are the only input. The beat schema, filing pipeline, and vault format should work regardless of where a beat originated.

**Success looks like:** Adding a new ingestion source requires writing an extractor and calling the existing filing pipeline — not redesigning the system.

---

## G10: Feel like consciousness expansion, not archival

This system is not a filing cabinet. The framing of "storing information for posterity" undersells what it actually does — it makes the user think better in the present by making past thinking immediately accessible. The difference matters: an archive is something you visit rarely; extended cognition is something you rely on continuously.

This has implications beyond naming. The interaction model, the recall UX, and the way beats are surfaced should feel like remembering, not like searching a database. The goal is to make the user feel more capable, not better organized.

**Success looks like:** A user describes the system to someone else as something that makes them smarter, not something that stores their notes.

---

## G11: Knowledge should follow the user across all devices and contexts

A developer works across multiple devices — personal laptop, work laptop, phone, possibly others. Knowledge captured on any of them should be queryable from any other. The vault is a single source of truth, not a per-device silo.

This has two layers: the vault itself (a sync concern — Obsidian Sync, iCloud, Dropbox, or similar) and the capture mechanisms. The capture mechanisms are the harder problem. The PreCompact hook and CLI skills work on a laptop. Claude on a phone — which is a heavily-used primary interface — has no current capture path. Sessions on Claude.ai, whether on desktop or mobile, are outside the hook's reach entirely.

Every interface the user works in should have a capture path to the vault. "I was using Claude on my phone" should not be a reason knowledge was lost.

**Success looks like:** The user never thinks about which device a piece of knowledge was captured on. It's just in the vault.

---

## G12: Capture all important context regardless of how a session ends

The PreCompact hook fires when the user explicitly runs `/compact`. But many sessions end differently: the user closes the terminal, the session times out, the CLI crashes, or the work simply stops without a compaction step. In these cases, the PreCompact hook never fires and the session's knowledge is not captured.

This is a significant gap. A session that ended abruptly after two hours of productive debugging may contain as much value as one that was formally compacted. The system must not depend on a specific session lifecycle event to do its job.

**Success looks like:** Knowledge from a session is captured regardless of whether the user remembered to compact, regardless of whether the tool supports compaction, and regardless of how the session ended.

---

## G13: Support a spectrum from fully automatic to human-curated

Full automation is low friction but produces some errors: beats miscategorized, notes filed in the wrong folder, a decision beat that should have extended an existing note instead creating a duplicate. Human curation is higher quality but costs attention.

Neither extreme is right for all users or all situations. A developer who is deep in flow wants zero friction. The same developer doing an end-of-week review might want to look over what was filed and correct it. The system should support both modes — and ideally a middle ground where the user is only prompted for genuinely ambiguous cases.

**Success looks like:** The user can choose how much control they exercise over filing quality without having to choose between "fully automatic with errors" and "manually approve everything."

---

## G14: Retrieval should be efficient, token-aware, and semantically capable

The current retrieval mechanism is grep-based: search for keywords across all vault files, load the full content of matching notes into the LLM context. This has two problems. First, it's lexical — it misses notes that are relevant but use different vocabulary. Second, it's wasteful — loading five full notes to answer a question burns context window that could be used for the actual work.

Obsidian is the right interface for human review and manual authoring. It is not necessarily the right tool for programmatic retrieval. A better retrieval layer would find semantically relevant notes (not just keyword matches), return summaries or excerpts rather than full content, and operate fast enough to be used mid-session without friction.

This doesn't mean replacing Obsidian — the vault stays as the canonical store. It means the retrieval path into LLM context should be smarter than a full-text grep.

**Success looks like:** A query for "how we handle authentication" finds the relevant notes even if none of them contain the phrase "authentication." Context injection uses excerpts or summaries when the full note isn't needed, preserving context window for actual work.

---

## G15: Human-authored notes should be automatically enrichable

Notes added directly in Obsidian — quick thoughts, clippings, meeting notes, references — won't have the same structure as LLM-extracted beats. They'll lack typed frontmatter, coherent tags, scope classification, and summary fields. This makes them less findable and less useful when injected into context.

The system should provide a way to bring human-authored notes up to the same structural standard as extracted beats — automatically, on demand, without the human having to do the tagging work themselves. The LLM should be able to look at an unstructured note and produce the frontmatter, tags, type, and summary that a beat would have had.

**Success looks like:** A user can add a rough note to Obsidian in 10 seconds and later run a single command to enrich the whole vault. The enriched notes are as findable and injectable as any extracted beat.

---

## G16: LLM usage should be efficient — every call should earn its cost

LLM API calls are not free. The system makes LLM calls for extraction (on every compaction), for autofile decisions (once per beat when enabled), for retrieval context injection (on recall), and potentially for enrichment. As the vault grows and the system runs more frequently across more interfaces and devices, this cost compounds.

Efficiency is not about being cheap — it's about ensuring that every call produces proportionate value. Calls that could be avoided (re-extracting already-processed sessions), calls that are larger than necessary (loading full notes when summaries suffice, passing full transcripts when only text turns are needed), and calls that use a more expensive model than the task requires all represent waste.

The right model for the task matters: extraction is a structured JSON task that Haiku handles well. Autofile decisions benefit from more reasoning capacity. Retrieval context injection should prefer summaries over raw content. These choices should be deliberate, not defaulted.

**Success looks like:** The system's LLM usage is proportionate to the value it produces. A developer using the system daily does not face a surprising API bill. Adding new interfaces and sources scales the capture value without scaling the cost proportionally.

---

## G17: Support non-Anthropic and local LLM backends

The extraction tasks this system performs — structured JSON extraction from text, classification, tagging, summarization — do not require a frontier model. A capable local LLM running on the user's own hardware can handle them adequately, at zero per-call cost, with zero data leaving the machine.

This matters for two distinct reasons:

**Cost.** A local model running via Ollama or similar has no API cost. For a user who compacts frequently, imports large session backlogs, or runs enrichment across a large vault, the accumulated API cost of cloud-based extraction is real. A local backend eliminates it.

**Privacy.** The content being extracted is often sensitive: work codebases, internal architecture decisions, debugging sessions involving proprietary systems. Sending this content to a third-party API — even Anthropic's — may not be acceptable in all contexts. A local backend keeps all content on-device.

The system already has a backend abstraction (`claude-cli`, `anthropic`, `bedrock`). Extending it to support local inference runtimes (Ollama, LM Studio, llama.cpp) is architecturally consistent with how the system is already built.

Speed is not a primary concern for extraction — it happens in the background, and a few extra seconds of latency per session is acceptable.

**Success looks like:** A user can point the system at a locally-running model and have extraction, autofile, and enrichment work without any cloud API calls. Sensitive content never leaves the machine.

---

## G18: The system should be unopinionated about vault structure

Initial setup may offer an opinionated scaffold — a para-style folder layout, a suggested type vocabulary, a CLAUDE.md template — for users who are starting fresh. But the runtime behavior of the system must be adaptive. It observes and works with the structure that already exists rather than imposing its own.

This means:
- **Knowledge retrieval** finds relevant notes regardless of where they live in the vault
- **Vault maintenance** (merging, splitting, creating hub notes) respects the organizational conventions of the vault — hub notes may live inside a folder, one level above it, in a dedicated index directory, or anywhere the user prefers
- **Metadata enrichment** infers valid note types and conventions from the vault itself, not from a hardcoded list
- **Filing and routing** uses the vault's own CLAUDE.md to determine where notes belong, not assumptions baked into the system

The system should work well whether the vault uses PARA, Zettelkasten, Johnny Decimal, flat filing, or something entirely idiosyncratic. Setup scaffolding is optional and non-destructive; runtime behavior adapts.

**Success looks like:** A user with an existing Obsidian vault can point the system at it and have all features work sensibly without reorganizing their vault to match a prescribed layout.
