# SP14: LLM Cost Profiling and Efficiency Improvements

**Date:** 2026-02-27
**Status:** Investigation complete

---

## Part 1: LLM Call Site Map

### All LLM Call Sites

| Call site | Function | Trigger frequency | Model (default) | Configurable? | Notes |
|---|---|---|---|---|---|
| `extract_beats.py: extract_beats()` | `call_model()` | Once per compaction / manual extract | `claude-haiku-4-5` | Yes — `claude_model` (cli) or `model` (sdk) | Main extraction call |
| `extract_beats.py: autofile_beat()` | `call_model()` | Once per beat (when `autofile: true`) | same as above | Yes — same config | Per-beat filing decision |
| `mcp/server.py: kg_extract()` | `call_model()` (via import) | On demand (Claude Desktop) | same as above | Yes | Delegates to same logic |
| `mcp/server.py: kg_file()` | none | On demand | — | — | No LLM call; writes beat directly |
| `mcp/server.py: kg_recall()` | none | On demand | — | — | No LLM call; grep + file read only |
| `scripts/import-desktop-export.py` | `eb.extract_beats()` / `eb.autofile_beat()` | Once per conversation (batch) | same as above | Yes | One extraction call per conversation; autofile calls per beat if enabled |

### Call Details

#### 1. `extract_beats()` — the extraction call

**Function:** `extract_beats()` → `call_model()` in `extract_beats.py`

**What it sends:**

- **System prompt:** `prompts/extract-beats-system.md` — 1,899 bytes (~475 tokens)
- **User message:** `prompts/extract-beats-user.md` template (~267 bytes / ~67 tokens for the wrapper) + the transcript text

The user message template injects:
- `project_name`, `cwd`, `trigger` — negligible (~20 tokens total)
- `{transcript}` — up to `MAX_TRANSCRIPT_CHARS = 150,000` characters (~37,500 tokens at 4 chars/token)

**Input token estimate:**
- System prompt: ~475 tokens
- User wrapper: ~90 tokens
- Transcript (typical 2-hour session, after filtering): ~5,000–20,000 tokens
- **Typical total input: ~6,000–21,000 tokens**

The 150,000-char hard cap equates to ~37,500 tokens — this is the ceiling, not the typical case. A moderately active 1–2 hour session with tool results trimmed to 500 chars likely produces 20,000–80,000 chars of filtered transcript text, which is 5,000–20,000 tokens.

**Output token estimate:**
- The model returns a JSON array of beats. Each beat has 6 fields: title (~8 words), type, scope, summary (~20 words), tags (~5 words), body (~150 words).
- Per beat: ~200 tokens. Typical 5 beats per session: ~1,000 tokens output.
- Range: 0 (no beats) to ~2,000 tokens (10 rich beats).

**`max_tokens` setting:** The `anthropic` SDK backend caps output at 4,096 tokens (hardcoded in `_call_anthropic_sdk()`). The `claude-cli` backend does not set an explicit `--max-tokens` flag, so it defaults to the model's own maximum.

**Avoidability:** Not generally avoidable — this is the core value-producing call. Could be skipped if the session was already processed (see Part 4, deduplication).

---

#### 2. `autofile_beat()` — the per-beat filing decision

**Function:** `autofile_beat()` → `call_model()` in `extract_beats.py`

**What it sends:**

- **System prompt:** `prompts/autofile-system.md` — 1,667 bytes (~417 tokens)
- **User message:** `prompts/autofile-user.md` template + dynamic content:
  - `{beat_json}`: the beat as indented JSON (~300–500 tokens)
  - `{related_docs}`: up to 5 vault notes, each truncated to 2,000 chars. At 5 notes × 500 tokens each = up to 2,500 tokens
  - `{vault_context}`: `CLAUDE.md` truncated to 3,000 chars (~750 tokens)
  - `{vault_folders}`: top-level folder listing (~20–100 tokens)

**Input token estimate per beat:**
- System prompt: ~417 tokens
- Beat JSON: ~400 tokens
- Related docs (up to 5): 0–2,500 tokens (0 on empty vault, more as vault grows)
- Vault CLAUDE.md: 0–750 tokens
- Vault folders: ~50 tokens
- **Typical total input: ~1,500–4,200 tokens per beat**

On a vault with substantial content and a mature CLAUDE.md, expect input closer to the upper bound.

**Output token estimate:** The model returns a single JSON decision object — either `{"action":"extend","target_path":"...","insertion":"..."}` or `{"action":"create","path":"...","content":"..."}`. The `content` or `insertion` field can be substantial (a full note or a new section). Estimate: 150–800 tokens per call.

**Avoidability:** Entirely avoidable by setting `autofile: false`. Every beat currently triggers one autofile call; there is no confidence threshold or batching.

---

#### 3. `kg_recall` — the recall path

**`/kg-recall` skill (`skills/kg-recall/SKILL.md`):** This skill makes **zero direct LLM calls**. It is a set of instructions for the active Claude session to execute — Claude uses `Bash` (grep), `Read`, and `Glob` tools. The skill itself does not call any external model. The tokens consumed are those of the active session executing the instructions.

**`mcp/server.py: kg_recall()`:** Also makes **zero LLM calls**. It runs `grep` subprocesses and reads file content, returning the assembled text directly to the Claude Desktop context.

The "cost" of recall is in context window consumption (reading up to 5 notes × 3,000 chars each = 15,000 chars = ~3,750 tokens injected into the active session), not in additional API charges.

---

#### 4. `/kg-file` skill and `kg_file()` MCP tool

**No LLM calls.** The skill has Claude (the active session) classify and format the beat itself, then write the file directly using `Write`. The MCP tool writes directly without calling any model.

---

#### 5. `/kg-claude-md` skill

**No LLM calls from the extractor.** It uses Claude (the active session) to read vault files and synthesize the CLAUDE.md. The token cost is borne by the current session's context, not by an extraction model call.

---

#### 6. `import-desktop-export.py` — batch import

Calls `eb.extract_beats()` once per conversation and, if `autofile: true`, calls `eb.autofile_beat()` once per extracted beat. Identical cost model to the main extraction path, applied at volume. The state file (`~/.claude/kg-import-state.json`) tracks processed conversations by UUID, preventing re-extraction of already-done conversations.

---

## Part 2: Cost Baseline Estimate

**Pricing used:** Claude Haiku 4.5 (as of early 2026)
- Input: $0.80 / 1M tokens
- Output: $4.00 / 1M tokens

**Scenario:** Typical day — 3 compactions, 5 beats per compaction (15 beats total), autofile enabled, 3 recall queries.

### Extraction calls (3 per day)

| Component | Tokens (per call) | Calls/day | Total tokens |
|---|---|---|---|
| Input — system prompt | 475 | 3 | 1,425 |
| Input — user wrapper | 90 | 3 | 270 |
| Input — transcript (mid estimate) | 10,000 | 3 | 30,000 |
| Output — 5 beats × 200 tok | 1,000 | 3 | 3,000 |

**Extraction total:**
- Input: 31,695 tokens → 31,695 / 1,000,000 × $0.80 = **$0.025**
- Output: 3,000 tokens → 3,000 / 1,000,000 × $4.00 = **$0.012**
- **Extraction subtotal: ~$0.037/day**

### Autofile calls (15 per day, assuming ~3,000 tokens input each)

| Component | Tokens (per call) | Calls/day | Total tokens |
|---|---|---|---|
| Input — system + beat + docs + CLAUDE.md | 3,000 | 15 | 45,000 |
| Output — create/extend decision | 400 | 15 | 6,000 |

**Autofile total:**
- Input: 45,000 tokens → **$0.036**
- Output: 6,000 tokens → **$0.024**
- **Autofile subtotal: ~$0.060/day**

### Recall (3 queries/day)

Recall makes no LLM calls. The token cost is absorbed into the active session's context window and is not billed as a separate API call (under `claude-cli` backend; under the `anthropic` backend, the session itself would bear this cost).

**Recall subtotal: $0.00 in external API charges**

### Daily cost summary

| Call type | $/day |
|---|---|
| Extraction (3 compactions) | $0.037 |
| Autofile (15 beats) | $0.060 |
| Recall (3 queries) | $0.000 |
| **Total** | **~$0.097/day** |

**Assessment:** Under $0.10/day for normal use. This is extremely cheap by any measure — roughly $3/month. The cost is not surprising given Haiku's pricing, but the split is notable: autofile (60%) costs more than extraction (37%) despite being the secondary feature. This is because autofile is called per-beat with substantial vault context re-read on every call, while extraction is called once per session.

At high-volume use (10 compactions/day, 8 beats each, autofile on): ~$0.50/day, or ~$15/month. Still very reasonable.

---

## Part 3: Transcript Trimming Analysis

### What `parse_transcript()` currently skips or trims

`extract_text()` in `extract_beats.py` processes each content block:

1. **`tool_use` blocks** — **skipped entirely** (the comment says "too noisy"). These contain tool calls with their input parameters.
2. **`thinking` blocks** — **skipped entirely**. These are Claude's internal reasoning steps, often large.
3. **`tool_result` blocks** — **included but trimmed to 500 characters**. The first 500 chars of each tool result are included with a `[tool result: ...]` prefix.
4. **Non-user/non-assistant entries** — **skipped entirely**. System messages, metadata entries, and other JSONL entry types are dropped at the outer loop.

### What fraction of raw JSONL is filtered for a typical 2-hour coding session?

For a heavy coding session using Claude Code tools:

- **Tool calls** are extremely high volume. A 2-hour session might involve 200–500 tool invocations (Read, Write, Edit, Bash, Grep). Each tool_use block contains the tool name and full input parameters, typically 100–500 bytes each. That's 20,000–250,000 bytes filtered.
- **Tool results** are the highest-volume content type. A Read of a large file could return 50,000+ characters; Bash output from test runs or build logs can be tens of thousands of characters. With 200–500 tool results, raw output could total 500,000–5,000,000 bytes. After trimming to 500 chars each, this becomes 100,000–250,000 bytes (a 5–20x reduction).
- **Thinking blocks** (when extended thinking is enabled) add substantial volume — potentially 500–2,000 tokens of internal reasoning per response.

**Rough estimate:** In a tool-heavy session, the raw JSONL might be 2–20 MB. After filtering out tool_use and thinking blocks, and trimming tool_results to 500 chars, the filtered transcript is likely 5–30% of the raw size. The `MAX_TRANSCRIPT_CHARS = 150,000` cap provides a further safety net.

### High-volume, low-signal content not currently filtered

1. **Repeated tool results of the same type** — if the agent runs `grep` or `ls` 30 times during an investigation, each trimmed 500-char result is included. These are often near-identical (same directory listing, similar file contents). A single representative result per tool type per investigation phase would suffice.

2. **Short, trivial tool results** — `tool_result` blocks that are just `"OK"`, `""`, `"true"`, `"null"`, or very short error codes. These consume tokens with no extraction value. Currently all tool results ≥1 char are included.

3. **Interstitial assistant text** — very short assistant responses like "Done.", "Let me check...", "I see.", "OK." These are included in full as `[ASSISTANT]` turns. They add to token count but carry no extractable knowledge.

4. **Large code blocks that are incidental** — when the assistant outputs a full file listing or a long code block as part of a `Write` operation, that full text is included in the assistant message's text content. This is different from tool_result (which is trimmed) — assistant text blocks are passed through in full with no size limit.

---

## Part 4: Efficiency Opportunities

### 1. Session deduplication

**Current state: No deduplication guard on the main extraction path.**

The `pre-compact-extract.sh` hook fires every time `/compact` runs. There is no check in `extract_beats.py` or the hook that asks "has this session's transcript already been processed?" The session_id is recorded in each written beat's frontmatter (as `session_id`), but this is not checked before making the extraction call.

In practice, the risk of re-extraction is real: if the user runs `/compact` twice in succession (e.g., a failed compact followed by a successful one), the transcript would be processed twice, creating duplicate beats with different UUIDs.

The `import-desktop-export.py` script **does** have deduplication — it maintains a state file keyed by conversation UUID and skips already-processed conversations. This is the right model.

**The main extraction path needs a processed-session state file.**

**Estimated savings:** Eliminates 100% of cost for any re-processed session. Low expected frequency under normal use, but non-zero.

---

### 2. Transcript trimming improvements

**Current state:** tool_use skipped, thinking skipped, tool_result trimmed to 500 chars.

**Additional opportunities:**

**a. Filter trivial tool results entirely** — tool results shorter than ~10 chars (empty strings, "OK", "true", error codes) carry no extraction signal. Filtering these would save a small but free amount of tokens.

**b. Deduplicate repeated tool result patterns** — if the same grep term or the same file path appears in 10 consecutive tool results, include only the first 2 and annotate `[... N similar results omitted]`. This could save 30–50% of tool result tokens in investigation-heavy sessions.

**c. Filter very short assistant turns** — assistant turns with fewer than ~30 characters of text content ("Got it.", "Let me look.", "Done.") carry no extraction signal and could be skipped.

**d. Reduce the tool result trim limit** — 500 chars per tool result may be more than necessary. The first 200–300 chars typically contain the meaningful part of a file or command output. Reducing to 250 chars would cut tool result token volume by ~50% with minimal information loss.

**Estimated savings:** Combined, these changes could reduce typical transcript token counts by 20–40% without meaningfully harming extraction quality.

---

### 3. Retrieval (recall) efficiency

**Current state:** `kg_recall()` in `mcp/server.py` reads up to `max_results` notes (default 5) × 3,000 chars each = up to 15,000 chars injected into the calling context. The `/kg-recall` skill notes "If a document's `summary` field alone is sufficient, you may skip reading the full body" — but this is advisory and the MCP tool always reads full content.

**Opportunity:** Return only YAML frontmatter + `summary` field for initial results, then let the caller request full content for specific notes. Each note's frontmatter is ~400 chars, summary is ~200 chars — call it 600 chars per note. Five notes = 3,000 chars instead of 15,000 chars. That's an 80% reduction in tokens injected per recall query.

**However:** Recall injections are part of the active session's context, not separate API calls (under `claude-cli` backend). This doesn't directly reduce API billing — it affects context window pressure and response quality. Under the `anthropic` or `bedrock` backends, it does reduce costs.

**Estimated savings:** ~80% reduction in tokens per recall invocation. Primarily valuable for context window pressure management and for users on `anthropic`/`bedrock` backends.

---

### 4. Model tiering

**Current state:** Both extraction and autofile use the same model (default `claude-haiku-4-5`), configured by a single `claude_model` key. There is no per-task model selection.

**Assessment by task:**

| Task | What it requires | Haiku appropriate? | Alternative |
|---|---|---|---|
| **Extraction** | Follow a strict JSON schema, classify content into 6 types, write concise summaries | Yes — highly structured, template-following task | None needed |
| **Autofile** | Reason about vault structure, judge semantic fit between a new beat and existing notes, choose between extend/create with good judgment | Borderline — requires multi-step reasoning about relationships | Sonnet for better quality |
| **Import (batch)** | Same as extraction | Yes | None needed |
| **/kg-file (skill)** | Active session — no separate model call | N/A | N/A |
| **/kg-recall (skill)** | Active session — no separate model call | N/A | N/A |

**Autofile is the weakest link.** It needs to reason about semantic overlap between a new beat and 3 existing notes, understand vault structure from a CLAUDE.md, and choose a filing path. Haiku handles the structured-JSON output requirement well, but may produce suboptimal extend/create decisions — especially on vaults with nuanced structure. Sonnet (10x the price) would produce meaningfully better filing decisions, particularly for edge cases.

**Recommendation:** Add a separate `autofile_model` config key (defaulting to `claude_model`) so users can upgrade autofile to Sonnet without changing extraction. At 15 beats/day, the autofile cost on Sonnet would be ~$0.60/day vs. $0.06/day — a 10x increase for that call site only, from $0.06 to $0.60. Still under $20/month. For users with large, well-structured vaults who use autofile heavily, the quality improvement likely justifies this.

---

### 5. Caching

**Current state:** No caching. Every `autofile_beat()` call re-reads `CLAUDE.md` from disk (up to 3,000 chars) and re-runs grep searches against the vault. Within a single extraction run processing 5 beats, `CLAUDE.md` is read 5 times and the same vault paths are likely scanned multiple times.

**Opportunities:**

**a. CLAUDE.md caching within a run** — the vault's `CLAUDE.md` does not change during an extraction run. Reading it once and passing it to all `autofile_beat()` calls would save 5 disk reads and ~750 tokens × 4 beats = ~3,000 tokens of redundant context per run. This is a trivial code change.

**b. Vault search caching within a run** — if two beats have overlapping tags (e.g., both tagged `python` and `subprocess`), the grep results for those terms are computed independently. A simple in-memory cache keyed by search term within one extraction run would eliminate redundant subprocess calls.

**c. CLAUDE.md caching across sessions** — not applicable for the `claude-cli` backend (each extraction is a fresh process). Would require a file-based cache with invalidation on CLAUDE.md mtime.

**Estimated savings:** CLAUDE.md caching eliminates ~3,000 tokens of input per 5-beat extraction run. Vault search caching reduces subprocess overhead (latency, not token cost). These are small wins but free to implement.

---

### 6. Batch extraction for import script

**Current state:** `import-desktop-export.py` calls `extract_beats()` once per conversation. For a 2-second delay between calls and 500 conversations in an export, a full import takes ~17 minutes. Each call independently pays the system prompt overhead (~475 tokens).

**Opportunity:** Batch multiple short conversations (those under, say, 2,000 chars rendered) into a single extraction call separated by clear delimiters. A batch of 5 short conversations shares the 475-token system prompt overhead instead of paying it 5 times. For 500 conversations averaging 1,000 chars, batching into groups of 5 reduces extraction calls from 500 to 100.

**Challenges:** The beats returned need to be associated back to their source conversation for correct session_id and timestamp assignment. This requires adjusting the prompt to label beats with a conversation index. Implementation complexity is moderate.

**Estimated savings:** ~80% reduction in system prompt overhead for batch import. For a 500-conversation import, saves ~190,000 input tokens (~$0.15). More significantly, reduces import time from ~17 minutes to ~4 minutes.

---

## Part 5: Cost Visibility

### Current logging

The system logs the following to stderr per run:
- Which backend and model is in use: `[extract_beats] Using claude-cli backend (model=claude-haiku-4-5)`
- Each beat written: `[extract_beats] Wrote: /path/to/beat.md`
- Each autofile decision: `[extract_beats] autofile: created /path/to/note.md`
- Final count: `[extract_beats] Done. N beat(s) written.`

**There is no token usage logging.** Neither the input token count, the output token count, nor the cost per call is logged anywhere.

Under the `claude-cli` backend, token counts are not directly accessible — the CLI returns only the model's text output. Under the `anthropic` SDK backend, the `response.usage` object contains `input_tokens` and `output_tokens` and could be logged trivially:

```python
# In _call_anthropic_sdk():
response = client.messages.create(...)
usage = response.usage
print(f"[extract_beats] tokens: input={usage.input_tokens} output={usage.output_tokens}", file=sys.stderr)
return response.content[0].text.strip()
```

### Token usage logging recommendation

For the `anthropic` and `bedrock` backends: log `input_tokens`, `output_tokens`, and estimated cost to stderr after each call. Accumulate totals per run and print a summary.

For the `claude-cli` backend: token counts are not available from the CLI output. The best proxy is to count characters in the input prompt and estimate at 4 chars/token.

### Daily token cap

**Current state:** No cap exists. A misconfigured import run (e.g., `--limit` not set on a 5,000-conversation export with autofile enabled) could make thousands of API calls before the user notices.

**Recommendation:** Add an optional `daily_token_budget` config key. If set, the extractor checks a lightweight token ledger (a JSON file updated after each call) and refuses to make further calls once the budget is exceeded. This is especially important for the import script and for users on the `anthropic` backend where costs are billed directly.

A simple implementation:
- Ledger at `~/.claude/kg-token-ledger.json` with `{"date": "YYYY-MM-DD", "input_tokens": N, "output_tokens": N}`
- Reset on date change
- Check before each call; if over budget, log a warning and skip

---

## Ranked Efficiency Opportunities

| Rank | Opportunity | Estimated savings | Implementation cost | Priority |
|---|---|---|---|---|
| 1 | **Per-beat autofile model selection** (`autofile_model` config key, default Sonnet) | Quality improvement worth 10x cost increase; alternatively, savings if users consciously choose Haiku only for autofile | Low — add one config key and one code path | High |
| 2 | **Session deduplication** (state file for extraction, similar to import script) | Eliminates 100% of cost for re-processed sessions; prevents duplicate beats | Medium — requires state file and session_id lookup | High |
| 3 | **Transcript trimming improvements** (filter trivial tool results, reduce 500→250 char limit, skip short assistant turns) | 20–40% reduction in extraction input tokens | Low — small changes to `extract_text()` | Medium |
| 4 | **Summary-only recall responses** (return frontmatter+summary by default, full content on request) | 80% reduction in tokens per recall invocation; primarily context window benefit | Medium — requires MCP and skill changes | Medium |
| 5 | **CLAUDE.md in-run caching** (read once per extraction run, pass to all autofile calls) | ~3,000 tokens saved per 5-beat run; latency improvement | Very low — trivial code change | Medium |
| 6 | **Token usage logging** (`anthropic`/`bedrock` backends) | Visibility only; enables informed decisions | Very low | Medium |
| 7 | **Batch extraction in import script** (group short conversations) | ~80% reduction in system prompt overhead for batch import; 4x speed increase | Medium-high — requires prompt changes to label beats by conversation | Low |
| 8 | **Daily token budget cap** | Risk management; prevents runaway cost | Low | Low |
| 9 | **Vault search caching within a run** | Subprocess latency savings; no token savings | Low | Low |

---

## Model Tiering Recommendation

| Task | Current model | Recommended model | Rationale |
|---|---|---|---|
| Extraction (compaction hook) | Haiku (default) | Haiku | Structured JSON template-following — Haiku is fully capable |
| Extraction (import batch) | Haiku (default) | Haiku | Same task; cost per call matters at volume |
| Autofile decisions | Haiku (shared with extraction) | **Sonnet (optional)** | Semantic reasoning about vault structure benefits from a stronger model; make configurable via `autofile_model` |
| /kg-file (skill) | Active session model | Active session model | No separate call |
| /kg-recall (skill) | Active session model | Active session model | No separate call |

The key change is decoupling the extraction model from the autofile model. A single `claude_model` config key controls both today, which means users must choose between cheap extraction for everything (risking autofile quality) or expensive models for everything (wasteful for extraction). A separate `autofile_model` key resolves this.

---

## Summary

The system's LLM cost is very low in absolute terms (~$0.10/day at normal use), making cost reduction a secondary concern compared to quality and reliability. However, three issues stand out:

1. **Autofile is the dominant cost driver** (60% of daily spend) and also the most quality-sensitive call. It currently uses the same model as extraction despite needing stronger reasoning. Decoupling model selection per task type is the highest-leverage change.

2. **No session deduplication on the main path** means duplicate extraction is possible (though infrequent), and no state tracking means there's no way to audit what has or hasn't been processed.

3. **No cost visibility** means users have no way to understand where their budget goes, which makes it hard to make informed tradeoffs. Adding token logging to the `anthropic`/`bedrock` backends is a trivial change with high informational value.
