# Phase 3 Specification

**Status:** Backlog
**Date:** 2026-02-28
**Informed by:** Phase 2 deferred items, GOALS.md, USE_CASES.md

---

## 1. Preamble

Phase 3 addresses the goals and use cases that Phase 2 intentionally deferred. It should not begin until Phase 2 is shipped and operational — several Phase 3 items depend on Phase 2 baseline data (miscategorization rate, vault scale, cost profiles) to validate their design assumptions.

Phase 3 is organized by theme rather than strict priority. Priority within each theme should be reassessed after Phase 2 ships, based on actual usage patterns.

---

## 2. Quality and Human Curation (G13)

Phase 2 deferred the full human-in-the-loop curation spectrum to collect baseline data after HP-2 (better extraction prompts) ships. Phase 3 implements it.

### P3-1: Confidence scoring on extraction → staging queue (from MP-1)

Add `confidence` (0.0–1.0) and `confidence_reason` fields to the extraction JSON schema. The extraction LLM self-assesses type and scope confidence. Beats below a configurable threshold (`confidence_threshold: 0.80` in `knowledge.json`) route to `staging_folder` instead of their final destination.

**Prerequisite:** At least 4 weeks of HP-2 extraction output to establish a baseline miscategorization rate. If HP-2 reduces errors to near zero, this item may be unnecessary.

**Full spec:** See MP-1 in `.specs/PHASE2_SPEC.md`.

---

### P3-2: `/kg-review` skill for correcting beats in bulk (from MP-3)

A skill that reads recent beats from the vault (from the staging folder or by session ID), presents each with title/type/scope/summary, and accepts corrections via simple commands (`[N] type=decision`, `[N] scope=general`, `[N] delete`). Applies corrections using the Edit tool.

**Prerequisite:** P3-1 (confidence scoring) — the review queue is most useful when it contains only uncertain beats. Without confidence scoring, the queue is the entire vault.

**Full spec:** See MP-3 in `.specs/PHASE2_SPEC.md`.

---

## 3. Retrieval Quality (G14, UC20)

Phase 2 addresses G14's token-efficiency problem (HP-6 summary-first recall). The vocabulary mismatch problem — where a searcher uses different terms than the stored beat — is unaddressed until Phase 3.

### P3-3: Semantic retrieval with sentence-transformers + SQLite-vec (from MP-2)

**Problem it solves:** UC20 — a user searching "how do we handle users losing their session" fails to find notes about "JWT expiry", "token invalidation", or "auth middleware" because the keyword doesn't match. Semantic retrieval would surface these.

**Recommended stack:** `sentence-transformers` (all-mpnet-base-v2 model, ~420MB) + `SQLite-vec` for vector storage.

**Key design constraints:**
- `scripts/build-index.py` — initial index build over existing vault
- `write_beat()` in `extract_beats.py` — upsert new notes at write time
- The `/kg-recall` skill cannot call a Python subprocess with a running model; this requires either a persistent indexing service or a query subprocess with model cold-start
- The MCP path (`mcp/server.py`) integrates more cleanly as it is already Python

**Prerequisite:** Vault at a scale where keyword misses are a daily frustration (roughly 500+ beats). The grep approach is adequate below this threshold.

**Full spec:** See MP-2 in `.specs/PHASE2_SPEC.md` and SP12 in `steering/SPIKES.md`.

---

## 4. Privacy and Local LLM (G17, UC24)

Phase 2 deferred SP15 with the rationale that `claude-cli` achieves zero-cost for Pro subscribers. This only addresses the cost rationale — the privacy rationale (data must not leave the machine in enterprise/client contexts) is unresolved until Phase 3.

### P3-4: Local LLM backend — Ollama/LM Studio (from SP15)

**Problem it solves:** G17 — users in enterprise or client-engagement contexts cannot send session content to any third-party API, even Anthropic's. UC24 — on-device processing with zero API cost and complete data privacy.

**Design:** The existing backend abstraction (`claude-cli`, `anthropic`, `bedrock` in `extract_beats.py`) is structurally ready. SP15 specced the Ollama/LM Studio extension in detail.

**Required before implementing:**
1. Model quality validation — run the extraction prompts against Llama 3.1 8B, Mistral 7B, and Qwen2.5 7B on a sample of real transcripts. Beat quality must be acceptable before shipping.
2. Decide whether to support both Ollama (local service) and LM Studio (local service) or pick one.
3. Update `install.sh` to detect and optionally configure a local backend.

**Full spec:** See SP15 in `steering/SPIKES.md`.

---

## 5. Capture Completeness (G11, G12, UC14, UC19)

Phase 2 reduces the mobile capture gap via documentation (HP-7 batch export). Real-time or near-real-time mobile capture and multi-device deployment are Phase 3.

### P3-5: Mobile capture automation — scheduled re-import (Tier 2)

**Problem it solves:** UC19 — HP-7's batch export requires manual trigger. A monthly cadence is too infrequent for active mobile users.

**What to build:** A scheduled job (launchd on macOS, cron on Linux) that periodically checks for a new Anthropic export ZIP in `~/Downloads` and auto-imports it. Alternatively, trigger import via a Shortcut on iOS after export completes.

**Prerequisite:** Confirm that the Anthropic export consistently includes mobile sessions before automating around it.

---

### P3-6: Multi-device setup guide and `knowledge.shared.json` (from SPEC-07)

**Problem it solves:** G11 — users running the system on multiple machines have no documented setup path and no way to share global config across machines.

**What to build:**
1. A `docs/multi-device.md` guide covering: vault sync options (Obsidian Sync, iCloud, Dropbox, git), tool installation on a second machine, and common pitfalls.
2. A `knowledge.shared.json` feature: a config file that lives in the vault itself (and therefore syncs automatically) and overrides specific keys in `~/.claude/knowledge.json`. Useful for sharing `vault_path`, `inbox`, and `staging_folder` across machines without duplicating config.

**Full spec:** See SPEC-07 in `.specs/phase2-spikes.md`.

---

## 6. Daily Journal (SP2)

The daily journal feature (`daily_journal: true`) appeared functional during the Phase 2 audit period. Deferred to Phase 3 pending more operational data.

### P3-7: Daily journal reliability audit

If sustained use reveals the daily journal is broken or unreliable, conduct a focused audit:
1. Verify the date rollover logic in `extract_beats.py` handles sessions that start before midnight and end after.
2. Verify the journal entry is written even when no beats are extracted (the session-end signal should be sufficient to create a journal entry).
3. Add the journal write to the smoke test script (`scripts/test-smoke.sh`).

If the feature is confirmed working across 30+ days of use, close this item.

---

## 7. Token Budget and Cost Visibility (G16)

### P3-8: Budget cap and token usage logging (from MP-6 / MP-7)

Add optional `daily_token_budget` config key. A token ledger at `~/.claude/kg-token-ledger.json` accumulates input/output token counts from `anthropic` and `bedrock` backend calls. If the daily budget is exceeded, further calls log a warning and skip (gracefully — do not block compaction).

Also add token usage logging for `anthropic`/`bedrock` backends: after each `messages.create()` call, log `[extract_beats] tokens: input=N output=N` to stderr.

**Note:** The `claude-cli` backend does not expose token counts. This feature is only meaningful for the `anthropic` and `bedrock` backends.

**Full spec:** See MP-7 in `.specs/PHASE2_SPEC.md`.

---

## 8. Naming and Identity (SP1, G10)

### P3-9: Project naming decision (from SP1)

Phase 2 ships with the current naming (`knowledge-graph`, `/kg-*` commands). G10 states the system should "feel like consciousness expansion, not archival" — the current naming is mechanism-focused, not capability-focused.

This is a decision exercise, not a build task. The options are known (see SP1 in `steering/SPIKES.md`). What's needed is committing to one:

1. Keep current naming (accept the mismatch with G10)
2. Rename to a capability-focused name (e.g., `remember`, `recall`, `/remember`, `/recall`)
3. Rename to a persona-focused name (e.g., `memory`, `/mem-save`, `/mem-recall`)

**When to do it:** After Phase 2 is shipped and the system has proven its value. The name should reflect actual capability, not aspirations.

**Impact of renaming:** Command names in all skill files, `hooks.json`, `install.sh`, `README.md`, and any user-configured settings. Not trivial but a focused half-day effort.

---

## 9. Implementation Sequence

Phase 3 items are loosely ordered by dependency and value. Reassess after Phase 2 ships:

1. **P3-7** — Daily journal audit (quick, confirms or closes a known gap)
2. **P3-1** — Confidence scoring (requires 4 weeks of HP-2 baseline data)
3. **P3-2** — `/kg-review` skill (requires P3-1)
4. **P3-4** — Local LLM backend (requires model quality validation)
5. **P3-3** — Semantic retrieval (requires vault at scale; ~500+ beats)
6. **P3-5** — Mobile capture automation (requires confirming export includes mobile)
7. **P3-6** — Multi-device guide + `knowledge.shared.json`
8. **P3-8** — Token budget logging
9. **P3-9** — Naming decision (last — name should reflect proven capability)
