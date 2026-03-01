# Knowledge-Graph: Critical Review Report
*Goals Alignment and Architecture Accuracy Assessment*
*Date: 2026-02-28*
*Source analyses: `.specs/review-implementation-map.md`, `.specs/review-goals-analysis.md`*

---

## Executive Summary

The system is working software with a sound architectural foundation. The PreCompact extraction pipeline — hook → extractor → vault write — functions correctly and reliably for Claude Code CLI users. The Phase 2 work has meaningfully improved the baseline: the `set -euo pipefail` compaction blocker is fixed, the SessionEnd hook is implemented, path traversal security is/i addressed, and the `/kg-enrich` skill fills a genuine capability gap. This is a credible Phase 1–2 implementation.

That said, the system does not yet deliver on its 17 stated goals in full. Three systemic problems cut across the goal set. First, retrieval is purely lexical: every use case involving "finding something you vaguely remember" — the central promise of the system — fails when the user's query doesn't use vocabulary that appears verbatim in the note. This undermines G3, G5, G6, G10, and G14 simultaneously. Second, automatic capture only works inside Claude Code CLI. Claude Desktop, Claude.ai, and mobile sessions produce zero vault beats. Given that the use case documents describe mobile Claude as "a primary interface and a significant source of knowledge," this is a scope gap that matters to most real users. Third, the documentation overpromises in specific and consequential ways: UC24 describes a local Ollama backend that does not exist; `/kg-file` is documented as writing to the vault "right now" when it generates output for manual paste; the MCP server is listed as working when it may not be.

The goal alignment ratings below are honest: 2 goals are STRONG, 8 are PARTIAL, 4 are WEAK, and 1 is NOT ADDRESSED. The system works well for the user who compacts Claude Code sessions regularly, knows their own note vocabulary, and never works outside the terminal. It falls short for the broader vision described in GOALS.md.

---

## Goals Alignment Matrix

| Goal | Name | Rating | One-line Assessment |
|---|---|---|---|
| G1 | Capture intellectual exhaust | PARTIAL | Covers Claude Code CLI only; Desktop/mobile/web produce nothing |
| G2 | Prevent context loss at boundaries | PARTIAL | Compaction path solid; SessionEnd implemented but unverified; non-CLI sessions lost |
| G3 | Bridge LLM/human memory gap | PARTIAL | Retrieval works on exact vocabulary; fails on vocabulary mismatch; no proactive recall |
| G4 | Multiple knowledge sources | PARTIAL | `/kg-file` doesn't write to vault; only 2 import formats; no browser/mobile path |
| G5 | Compounding value | PARTIAL | Beat structure is sound; compounding value undermined by lexical retrieval |
| G6 | Reduce rework | PARTIAL | Works when user recalls exact terms; fails on the "I vaguely remember" case |
| G7 | Signal-to-noise ratio | PARTIAL | Good extraction prompt; two incompatible type ontologies; no deduplication guard |
| G8 | Minimize cognitive burden | PARTIAL | Compaction is zero-friction; `/kg-file` requires manual paste; MCP integration uncertain |
| G9 | Extensible to new sources | STRONG | Clean pipeline architecture; demonstrated by import script pattern |
| G10 | Consciousness expansion | WEAK | Feels like keyword search; no proactive surfacing; name/commands communicate filing |
| G11 | Cross-device knowledge | WEAK | Vault sync is user-managed; capture tools require per-device install; mobile/web absent |
| G12 | Capture regardless of session end | PARTIAL | SessionEnd covers CLI graceful exits; hard kills and non-CLI interfaces uncovered |
| G13 | Automatic-to-curated spectrum | WEAK | Explicitly deferred to Phase 3; confidence routing not implemented |
| G14 | Efficient, semantic retrieval | PARTIAL | Token efficiency improved (summary cards); semantic capability formally deferred |
| G15 | Enrichable human notes | STRONG | `/kg-enrich` is complete and addresses the stated goal |
| G16 | Efficient LLM usage | PARTIAL | Haiku default and autofile_model are right; no dedup on hook path; no cost visibility |
| G17 | Non-Anthropic/local backends | NOT ADDRESSED | No local backend; UC24 describes a fictional Ollama implementation |

### G3 — Bridge the gap between LLM memory and human memory

The `/kg-recall` skill implements a reasonable two-phase grep (frontmatter scan → selective full-body read) and the MCP tool delivers summary cards efficiently. However, both use lexical search. SP12 documents the core failure mode precisely: a query for "how we handle authentication" returns nothing if the relevant note uses "JWT expiry" and "token invalidation." This vocabulary mismatch is not an edge case — it is the dominant scenario when memory is actually imperfect. UC6 (LLM proactively runs recall at session start without being asked) is unimplemented; nothing in the system prompts or hooks triggers automatic recall.

### G5 — Compounding value

The compounding value proposition depends on retrieval quality scaling with vault size. Lexical retrieval does the opposite: as the vault grows, the probability that the user's query contains the exact vocabulary of a relevant note decreases. Beat #1,000 adds storage but not proportionally to recall utility. The beat schema and filing structure are well-designed foundations, but the retrieval layer means the "vault with 1,000 beats is qualitatively different" claim is currently aspirational.

### G7 — Signal-to-noise ratio

Two parallel type ontologies coexist without reconciliation: the extractor uses 6 types (`decision`, `insight`, `task`, `problem-solution`, `error-fix`, `reference`); the `/kg-file` skill uses 13 types (`project`, `concept`, `tool`, `problem`, `resource`, `person`, `event`, `claude-context`, `domain`, `skill`, `place`). Both are present in `VALID_TYPES` — no validation error fires — but they are structurally incompatible for type-based queries. SP6 observed this empirically as "the most concrete finding" from vault examination. Additionally, no deduplication guard prevents two sessions covering the same topic from producing near-identical beats with different UUIDs.

### G10 — Consciousness expansion, not archival

The system is working software, but the experience it produces today is keyword search, not memory extension. The user must formulate queries using vocabulary that matches their past notes. There is no proactive surfacing of relevant context. The `/kg-file` skill interrupts flow rather than extending it. The name "knowledge-graph" and the `/kg-*` command vocabulary communicate infrastructure, not cognition. SP1 identifies the naming question as open; it has not been resolved.

### G11 — Knowledge across all devices and contexts

The vault storage layer is device-agnostic (plain markdown, any file sync). The capture layer is not. Hooks only work where Claude Code CLI is installed. Mobile and Claude.ai web have no capture path of any kind. The documentation acknowledges this gap but frames it as planned work — which is accurate, but means the goal is not addressed for a significant portion of real usage.

### G13 — Automatic-to-curated spectrum

G13 calls for a middle ground where the user is prompted only for genuinely ambiguous cases. The current implementation offers fully automatic (default, some classification errors) or manual Obsidian audit (full control, high friction). The `staging_folder` config key was intended to serve the middle path but is effectively unreachable — `resolve_output_dir()` routes all unrouted beats to `inbox`, never to `staging_folder`. Confidence scoring (SP6's highest-leverage recommendation) has not been implemented. PHASE2_SPEC explicitly defers G13 to Phase 3.

### G17 — Non-Anthropic and local LLM backends

The `call_model()` dispatch is clean and extensible. Three backends exist: `claude-cli`, `anthropic`, `bedrock` — all cloud. No local backend exists. The `else` branch in `call_model()` routes any unrecognized `backend` value to `_call_anthropic_sdk()`. UC24 in `USE_CASES.md` describes configuring `"backend": "ollama"` with specific config keys — this does not work and will silently send content to Anthropic's API (or fail with a missing key error). This is the most dangerous documentation problem in the project.

---

## Gap Analysis

### Critical Gaps (P1)

**GAP-1: Retrieval is lexical — the core value loop is broken**

The system promises: a user can query the vault with natural description and find relevant notes even without remembering exact terminology (G3, G6, G14).

The system delivers: a keyword grep that returns nothing when the query vocabulary doesn't match the note vocabulary verbatim.

Concrete failure: Developer searches "how we handle the token expiry problem" — vault contains a `decision` beat titled "JWT session invalidation on logout" tagged `[jwt, auth, session-management]`. Zero results. The two-hour debugging session recurs.

Semantic retrieval (sentence-transformers + SQLite-vec) is designed in SP12 and specced, but explicitly deferred to Phase 3. Until it ships, the "extending memory" use case works only when the user's memory is already precise enough to know what to search for — which is exactly when it's least needed.

---

**GAP-2: Mobile and Claude.ai sessions produce no vault beats**

The system promises: knowledge from any session on any interface is captured (G1, G11, G12). UC19 explicitly states mobile Claude is "a primary interface and a significant source of knowledge."

The system delivers: Claude Code CLI hooks only. Claude Desktop is uncertain (see GAP-4). Claude.ai and mobile have zero capture path.

Concrete failure: Developer resolves an architectural problem in a 45-minute Claude mobile session during a commute. They open Claude Code at their desk, run `/kg-recall` — nothing. The session produced no beats and is entirely absent from the vault.

This is blocked by platform constraints (no Claude.ai export API), not implementation choices. But the documentation treats it as a known gap rather than being explicit that this gap disqualifies the system from meeting G1 for a large share of real usage.

---

### High-Priority Gaps (P2)

**GAP-3: `/kg-file` does not write to the vault**

OVERVIEW.md says: "Manually file any piece of information into the vault right now."

The `/kg-file` slash command generates a formatted note as in-session output. The user must copy it to Obsidian manually. The `kg_file` MCP tool does write directly, but MCP integration is uncertain (GAP-4).

The 10-second filing experience described in G4 requires at minimum a context switch to Obsidian, opening or creating a file, and pasting. This is a documented primary use case that doesn't work as documented.

---

**GAP-4: MCP server integration status uncertain**

SP3 found the `mcp` package missing from the venv — all three MCP tools raise `ModuleNotFoundError` on import. PHASE2_SPEC documents a fix (prefer Python 3.12/3.11, verify FastMCP import after install). The implementation researcher confirms the fix is specified in `install.sh`'s logic, but empirical verification of the installed state is unconfirmed.

OVERVIEW.md lists `kg_recall`, `kg_file`, `kg_extract` as "currently implemented and working." If the venv issue persists post-install, every Claude Desktop user encounters a silent failure with no diagnostic output.

---

**GAP-5: UC24 (local LLM) is a fictional use case**

`USE_CASES.md` UC24 describes configuring `"backend": "ollama"` with `ollama_model` and `ollama_url` keys. This use case does not work. No `ollama` backend exists in `extract_beats.py`. Setting `"backend": "ollama"` routes to `_call_anthropic_sdk()` — which will either fail with a missing API key error or, worse, send content to Anthropic's servers.

The failure mode for a user with data residency or privacy requirements who follows UC24 is catastrophic: they believe content is staying on-device when it is being sent to a third-party API. This is not a missing feature — it is a false documentation claim with a dangerous failure mode.

---

### Medium-Priority Gaps (P3)

**GAP-6: OVERVIEW.md "What's Implemented" section is stale**

The following are implemented but not reflected in OVERVIEW.md:
- `/kg-enrich` skill (listed as 4 slash commands; there are 5)
- SessionEnd hook and session registry (still listed as a known gap)
- `autofile_model` config key (absent from config table)
- Summary-first `kg_recall` (MCP and skill both upgraded)
- VALID_TYPES expansion from 6 to 18 types

The following are still listed as known gaps but are implemented: "Session-end capture without compaction (SP7)."

---

**GAP-7: VALID_TYPES expanded to 18 — documented as 6**

OVERVIEW.md's "Core Concepts" table shows 6 beat types. `VALID_TYPES` in `extract_beats.py` (line 326–332) contains 18 types: the original 6 plus 12 from the `/kg-file` ontology. The two ontologies are incompatible — notes of type `resource` (from `/kg-file`) and notes of type `reference` (from the extractor) describe similar things but are distinct. There is no guidance on which to use when.

---

**GAP-8: Config table missing keys; two keys fully undocumented**

Four config keys are absent from OVERVIEW.md's config table but present in the code: `autofile_model`, `journal_folder`, `journal_name`, `claude_timeout`. Two keys are completely undocumented across all docs and examples: `claude_path` (customizes the path to the `claude` binary) and `bedrock_region` (customizes the AWS region for Bedrock). Users needing these must read source code.

`staging_folder` is listed as required (`REQUIRED_GLOBAL_FIELDS`) and documented as the routing destination for unrouted beats. The code routes unrouted beats to `inbox`. `staging_folder` is unreachable in normal operation, making it a required config field that serves no purpose at runtime.

---

**GAP-9: SessionEnd hook fires on `/clear` sessions**

The SessionEnd hook has no `matcher` restriction in `hooks.json`. SP7 recommended restricting to `other|logout|prompt_input_exit` to avoid extracting from `/clear` sessions (which reset context, not session end). As implemented, clearing context triggers an extraction — potentially producing low-value beats from a context that was intentionally discarded.

---

**GAP-10: No session deduplication on the hook path**

The import script deduplicates at the conversation level via a state file. The PreCompact hook has no such guard: running `/compact` twice on the same session (e.g., a failed compact followed by retry) processes the same transcript twice and creates duplicate beats. SP14 identifies this; the import script models the correct solution.

---

## Architecture Accuracy Assessment

**Accurate:**
- The PreCompact data flow diagram (OVERVIEW.md) matches the code exactly
- LLM backend descriptions are accurate for the three documented backends (though incomplete — `claude_timeout` and `bedrock_region` are omitted)
- Beat routing for project-scoped beats is correct
- The Obsidian vault as human review layer description is accurate
- Configuration key name asymmetry (`claude_model` vs. `model` by backend) is correctly noted

**Documented but implemented differently:**
- Beat routing for unrouted beats: OVERVIEW.md says → `staging_folder`; code routes to `inbox`
- MCP tool signatures have been extended (`include_body`, `cwd` params added) since OVERVIEW.md was written
- The extraction backbone exists but the "4 slash commands" count is wrong (5 exist)
- `/kg-file` behavior: described as immediate vault write; is actually in-session output generation

**Implemented but not documented:**
- `/kg-enrich` skill (5th slash command, full implementation)
- SessionEnd hook and session deduplication registry
- `autofile_model` config key (for per-task model selection)
- Summary-first recall mode (both skill and MCP tool)
- 12 additional VALID_TYPES from the `/kg-file` ontology
- `claude_path`, `bedrock_region`, `claude_timeout` config keys

---

## False Impressions in the Documentation

These are documentation claims that will cause a real user to expect behavior the system does not deliver.

**1. UC24 (USE_CASES.md): Local LLM configuration with Ollama**
Describes specific config keys (`backend: "ollama"`, `ollama_model`, `ollama_url`) and states "no content leaves the machine." This feature does not exist. The failure mode sends content to Anthropic's API. **Most dangerous false impression in the project.**

**2. OVERVIEW.md: "/kg-file — file any piece of information into the vault right now"**
The word "right now" implies immediate vault write. The skill generates output for manual paste. The MCP `kg_file` tool does write directly, but only from Claude Desktop (uncertain status).

**3. OVERVIEW.md: MCP server listed as "currently implemented and working"**
The `mcp` package installation failure documented in SP3 (CRIT-1) may not be resolved in the installed state. If the package is missing, all three MCP tools fail silently on import.

**4. OVERVIEW.md: "no project config → staging_folder" routing**
The code routes unrouted beats to `inbox`, not `staging_folder`. The staging path is unreachable. Users who configure a separate staging folder expecting unrouted beats to land there will find them in inbox instead.

**5. OVERVIEW.md: "Extraction is transparent. The user doesn't need to think about it."**
Accurate for Claude Code compaction. Does not apply to Claude Desktop, Claude.ai, or mobile — all of which the documentation acknowledges are primary interfaces.

**6. Implicit: `/kg-enrich` uses Haiku**
The enrichment prompts are designed for Haiku-level quality. But `/kg-enrich` is a skill that runs in-context — it uses whatever model is running the active session. On a large vault with Sonnet or Opus, the cost could be significant.

---

## What's Working Well

**PreCompact extraction (core happy path):** Hook → extractor → vault write is solid. The `set -euo pipefail` compaction blocker is fixed. The extractor correctly parses JSONL, strips noise (tool_use, thinking blocks, trimmed tool_results), and produces well-structured beat files.

**Extraction prompt quality:** `prompts/extract-beats-system.md` has type definitions, explicit exclusion criteria, and three worked examples. The `task` type definition was added; disambiguation between `decision`/`insight`/`task` is addressed.

**Import pipeline:** Resumable state file with atomic writes. Handles both Claude and ChatGPT export formats. Proper conversation-level deduplication. `--dry-run`, `--list`, date filtering.

**Beat schema:** UUID IDs, session tracking, type/scope/tags/summary/project fields. The right foundation for retrieval and curation.

**Security:** Path traversal guard (`_is_within_vault()`) on all autofile writes. Prompt injection mitigations (XML wrapping of untrusted content) in all three LLM call sites.

**Summary-card retrieval:** MCP tool defaults to ~80-token summary cards; full content available via `include_body=True`. Skill uses two-phase read (frontmatter scan → selective full body). Token efficiency is meaningfully improved.

**`/kg-enrich`:** A genuine Phase 2 addition. Addresses the human-authored notes gap (G15). Additive-only frontmatter editing, appropriate skip conditions, dry-run mode.

**SessionEnd hook architecture:** Deduplication design via `kg-sessions.json` is correct. The hook correctly checks whether the session was already captured by PreCompact before extracting.

---

## Recommendations

### Quick Wins

1. **Fix UC24 in USE_CASES.md immediately.** Remove or clearly mark the Ollama backend description as "not yet implemented." The current state is a documented security/privacy risk for users who follow it literally.

2. **Update OVERVIEW.md "What's Implemented" section.** Add `/kg-enrich`, SessionEnd hook, `autofile_model`, summary-card retrieval. Remove SessionEnd from the "known gaps" list.

3. **Fix the routing description.** Update OVERVIEW.md to describe the actual routing: unrouted beats → `inbox`. Remove `staging_folder` from `REQUIRED_GLOBAL_FIELDS` since it is unreachable at runtime (or make it reachable).

4. **Document `claude_path`, `bedrock_region`, `claude_timeout`** in OVERVIEW.md's config table and `knowledge.example.json`.

5. **Add a `matcher` restriction to the SessionEnd hook** in `hooks.json` to exclude `/clear` sessions: `"matcher": "other|logout|prompt_input_exit"`.

6. **Clarify `/kg-file` behavior** in OVERVIEW.md: "generates a vault-ready note for pasting into Obsidian" rather than "files right now." Add a note that `kg_file` (MCP) writes directly.

### Important Fixes

7. **Verify the MCP venv fix is applied and working.** Run a real Claude Desktop integration test end-to-end. Either confirm the fix works or add a clear status note to OVERVIEW.md.

8. **Add session deduplication to the PreCompact hook path.** Before invoking the extractor, check `kg-sessions.json` for the session ID. If already captured, skip. This mirrors the SessionEnd hook's dedup logic and prevents duplicate beats from failed compaction retries.

9. **Implement the local/OpenAI-compatible backend (G17).** The architecture is extensible — a new `_call_openai_compatible()` function and config keys (`ollama_url`, `ollama_model`) would cover Ollama, LM Studio, and llama.cpp. SP15 has already researched this. It's a moderate implementation task, not a redesign.

10. **Reconcile the two type ontologies.** Either merge the `/kg-file` ontology types into the 6-type beat schema with explicit mappings, or document the two systems as distinct and explain which to use when. The current state silently produces incompatible types in the same vault.

### Architectural Work

11. **Semantic retrieval (G3, G6, G14).** This is the highest-leverage gap in the entire system. SP12 has a concrete design: sentence-transformers for embeddings, SQLite-vec for storage, hybrid grep+vector for queries. The MCP tool integration is straightforward; the skill integration requires a query subprocess or a fallback strategy. Until this ships, the system's core memory-extension value proposition is impaired.

12. **Confidence-based routing (G13).** Add `confidence` (0–1 float) and `confidence_reason` to the extraction JSON schema. Update the extraction prompt to instruct self-assessment. Route low-confidence beats to a staging folder (and fix the staging folder routing bug simultaneously). This requires making the `staging_folder` path actually reachable in `resolve_output_dir()`.

13. **Mobile and Claude.ai capture (G11).** This is blocked by platform constraints — no export API exists for Claude.ai. The realistic near-term path is: (a) a periodic manual export flow using `import-desktop-export.py` via a user-scheduled job, and (b) documentation of this as the supported path rather than leaving it as an unaddressed gap. Full automatic capture requires platform support that may never arrive.
