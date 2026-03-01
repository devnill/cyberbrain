# SP8: Deduplication Strategy

**Status:** Investigation complete
**Date:** 2026-02-27

---

## Part 1: Current State Analysis

### The import state file (`~/.claude/kg-import-state.json`)

The state file is managed entirely by `scripts/import-desktop-export.py`. Its structure is:

```json
{
  "version": 1,
  "created_at": "<ISO timestamp>",
  "updated_at": "<ISO timestamp>",
  "conversations": {
    "<conversation-uuid>": {
      "status": "ok" | "skipped" | "error",
      "beats_written": <int>,
      "error": null | "<error string>",
      "name": "<conversation name>",
      "processed_at": "<ISO timestamp>"
    }
  }
}
```

**Tracking granularity:** Conversation-level only. The state records whether a conversation UUID was processed and how many beats were written from it. It does not record which individual beat files were created, what their IDs are, or what session IDs they carry in their frontmatter.

**What happens if you import the same conversation twice:** The import script checks `state["conversations"].get(uid, {}).get("status")` before processing each conversation. If the status is `ok`, `skipped`, or `error` (unless `--reprocess-errors` is passed), the conversation is skipped entirely. So under normal operation, the same Anthropic Desktop export conversation will not produce duplicate beats on a second run.

**Atomic writes:** Yes. The `save_state()` function writes to a `.tmp` file and then calls `os.replace()` to atomically rename it into place. A crash cannot corrupt the state file.

**State file location:** Hardcoded to `~/.claude/kg-import-state.json`. Configurable via `--state` CLI flag.

---

### The PreCompact hook

The hook (`hooks/pre-compact-extract.sh`) receives a JSON payload on stdin containing `transcript_path`, `session_id`, `trigger`, and `cwd`. It invokes `extractors/extract_beats.py` with these values.

**Does the hook record what sessions it has processed?** No. There is no session registry, no log of processed session IDs, and no mechanism to detect that a given session was previously extracted. Every invocation is stateless with respect to prior runs.

**Does the hook communicate with the import script's state file?** No. The hook and the import script operate in completely separate namespaces. The hook knows about `session_id` values from Claude Code's JSONL transcript files. The import script knows about `uuid` values from Anthropic's `conversations.json` export format. These identifiers are not the same thing and there is no mapping between them.

---

### Beat ID generation in `extract_beats.py`

Beat IDs are generated at write time using `uuid.uuid4()` — a randomly generated UUID:

```python
beat_id = str(uuid.uuid4())
```

This is called inside `write_beat()` at line 380. The ID is written into the YAML frontmatter as the `id` field.

**The ID is not deterministic.** If the same beat content is written twice (from two different extraction runs on the same underlying conversation), each write produces a different `id`. There is no content-based or session-based component to the ID that would allow deduplication by comparing IDs across files.

**Is there any dedup check at write time?** No. The `write_beat()` function checks only for filename collisions (two beats with identical titles in the same folder) by prepending a counter (`2 <filename>.md`, `3 <filename>.md`, etc.). It does not check whether a beat with equivalent content or the same session already exists.

**The `session_id` field in frontmatter:** The `session_id` written to frontmatter is the Claude Code session ID (from the JSONL filename) when called from the hook or `/kg-extract`. When called from the import script, it is the Anthropic Desktop export conversation UUID. These two identifiers refer to the same underlying conversation from different system perspectives but are never equal.

---

### The `/kg-extract` skill

The skill (`skills/kg-extract/SKILL.md`) performs extraction in-context. It:
- Finds the current session's transcript file by path convention
- Reads and parses it
- Extracts beats using in-context reasoning
- Calls `extract_beats.py --beats-json` to write results

It records a log entry to `~/.claude/logs/kg-extract.log` (tab-separated, one line per beat). This log records what was written, but it is not consulted before extraction — it is write-only for dedup purposes.

---

## Part 2: Deduplication Problem Cases

### Case 1: PreCompact hook + later batch import of the same session

**Scenario:** User works on a session, runs `/compact`. The hook fires and extracts 5 beats from the session transcript. Six months later, the user downloads an Anthropic data export and runs the import script. That export includes the same conversation.

**What happens today:** The import script processes the conversation (it has no state entry) and calls `extract_beats.py` again on a rendered version of the same conversation. The LLM extracts beats again — likely overlapping substantially with the original 5. Five to ten new beat files are written to the vault. The original 5 remain. The vault now has duplicate (or near-duplicate) content.

**Severity:** High. This is the primary cross-path duplication risk. Every session ever compacted is a candidate for duplication when an export is imported.

**Complication:** The import script renders the conversation from the Desktop export JSON format (using `render_conversation()`), while the hook parsed the Claude Code JSONL transcript. The transcript formats are different and the rendered text may differ. The LLM may extract slightly different beats from each. These are not byte-identical duplicates — they are semantic duplicates.

---

### Case 2: Overlapping Anthropic data exports

**Scenario:** User runs the import script on export v1 (January export). In March, they download export v2, which includes all conversations from the past year — overlapping with export v1.

**What happens today:** The state file tracks conversation UUIDs. If the same UUID appears in export v2 that was already processed from export v1, the `build_work_queue()` function skips it (status is `ok`). **This case is already handled correctly.** The state file provides complete deduplication for the import-vs-import case as long as UUIDs are stable across exports (they are — Anthropic assigns permanent UUIDs to conversations).

**Severity:** None under normal operation. The existing state file mechanism handles this correctly.

---

### Case 3: Partial session captured by hook, full session in later export

**Scenario:** A long session (say, 3 hours) gets compacted halfway through. The hook fires and extracts beats from the first half. The session continues. At session end, the full transcript exists. Later, the full conversation appears in a Desktop export.

**What happens today:** The import script processes the conversation and extracts beats from the entire conversation — including both the first half (already extracted by the hook) and the second half (new material). The beats from the first half are duplicated in the vault. The beats from the second half are new and valuable.

**Severity:** Medium. This is a subset of Case 1. The deduplication problem exists, and a naive session-level skip would throw away the new second-half content.

**Note:** The hook uses `session_id` from Claude Code's JSONL filename. The Desktop export UUID is different. There is no linkage between them in any current data structure.

---

### Case 4: Manual `/kg-extract` + hook both run on the same session

**Scenario:** User runs `/kg-extract` mid-session to capture insights before a likely context loss. The hook later fires on `/compact` for the same session.

**What happens today:** Both the skill and the hook call `extract_beats.py` on the same transcript file (or an overlapping version of it). The transcript will have grown between the two runs — the second run has more content. The beats from the first run are a subset of what the second run might extract. No deduplication occurs. The vault gets duplicate beats, possibly with slightly different wording (since the LLM is non-deterministic).

**Severity:** Medium. Users who know about `/kg-extract` are the ones most likely to trigger this case, but it's also the case where they'd be most confused to see duplicates.

---

### Case 5: `/kg-extract` run on a session already captured by hook

**Scenario:** User manually runs `/kg-extract path/to/old/session.jsonl` on a session transcript that was already extracted by the hook when it was compacted.

**What happens today:** Same as Case 4 — duplicate beats written, no dedup check.

**Severity:** Low-medium. This is a user error scenario, but the system should handle it gracefully.

---

## Part 3: Deduplication Strategy

### Key observations that constrain the design

1. **Beat IDs are not reusable for dedup.** They're random UUIDs generated at write time. Two extractions of the same content produce two different IDs.

2. **Session IDs from the hook and UUIDs from the import script are not comparable.** There is no existing link between Claude Code session IDs and Anthropic Desktop export conversation UUIDs.

3. **The import-vs-import case is already solved.** The state file handles it completely via conversation UUID tracking.

4. **The main unsolved problem is hook-vs-import duplication** (Cases 1, 3). This is also the highest-severity case.

5. **Exact content dedup is impractical.** The LLM produces non-deterministic output. The same conversation run twice produces semantically equivalent but not byte-identical beats. A hash of the raw beat text will not match across two independent extraction runs.

6. **The transcript itself is the stable artifact.** The conversation content is fixed; only the extraction output varies.

---

### Recommended strategy: Two-layer deduplication

#### Layer 1: Session-level tracking (solves Cases 1, 4, 5)

Introduce a lightweight session registry at `~/.claude/kg-sessions.json`. The hook writes to it after each successful extraction:

```json
{
  "version": 1,
  "sessions": {
    "<session_id>": {
      "extracted_at": "<ISO timestamp>",
      "trigger": "compact" | "manual",
      "beats_written": <int>,
      "cwd": "<path>"
    }
  }
}
```

The hook writes an entry after extraction using the same atomic write pattern (`os.replace`) as the import script.

The `/kg-extract` skill also writes to this registry after a manual extraction.

**What this solves:** If the user later runs `/kg-extract` on the same session ID, the skill can warn: "Session `abc123` was already extracted on 2026-01-15 (3 beats written). Re-extract anyway?" This prevents accidental duplicate extraction from the same Claude Code session.

**What this does not solve:** The hook session IDs and the Desktop export UUIDs are still different namespaces. Session-level dedup alone does not prevent a hook-extracted session from being re-extracted via import.

#### Layer 2: Import-side session cross-reference (solves Cases 1, 3)

The import script needs to know which conversations have already been captured by the hook. This requires a bridge between the two namespaces. Options:

**Option A — Timestamp-based filtering (simplest, good enough for most cases)**

Add a `--since <date>` default that automatically excludes conversations that are older than the earliest known hook extraction. If the hook has been running since 2025-06-01, the import can be told to only process conversations from before that date (as historical backfill) or after the last import run.

This does not catch overlap at individual conversation granularity but prevents the common bulk-duplication scenario where an old export is imported into a vault that already has hook-extracted content from the same period.

**Limitation:** The user must know when to set the cutoff. Automatic cutoff detection is possible if the session registry records earliest and latest extraction timestamps.

**Option B — Content-hash index (catches Cases 1, 3 precisely)**

Maintain a content hash index at `~/.claude/kg-content-hashes.json`. After each beat is written (by hook, skill, or import script), record a hash of `normalize(title + summary)`.

```json
{
  "hashes": {
    "<sha256-hex>": {
      "written_at": "<ISO timestamp>",
      "source": "hook" | "import" | "manual",
      "session_id": "<id>",
      "vault_path": "<relative-path>"
    }
  }
}
```

Before writing any beat, compute the hash and check the index. If found, skip the write and log a dedup event.

**Normalization approach:** Lowercase, strip punctuation, collapse whitespace from both title and summary before hashing. This makes the check robust to minor LLM output variation (capitalization differences, minor rephrasing) while still catching genuine duplicates.

**Why title + summary, not full body?** The body is the most variable between two runs. The title and summary are the LLM's compressed representation of the beat's core claim — they converge more reliably across independent extractions of the same content.

**Limitation:** The LLM can produce genuinely different summaries of the same event. A hash match is near-certain for Case 5 (exact same session re-run manually) and less reliable for Case 1 (same conversation extracted via two different paths). This is a probabilistic, not guaranteed, deduplication.

**Implementation cost:** Moderate. Requires modifying `write_beat()` and `autofile_beat()` in `extract_beats.py` to load the hash index, check before writing, and update after writing. The index must also use atomic writes.

**Option C — Canonical ID derived from conversation content (most robust, highest cost)**

Generate beat IDs deterministically from a hash of `(conversation_id, turn_index, beat_title)` where `conversation_id` is derived from the transcript. For JSONL transcripts, use the session ID. For Desktop exports, use the conversation UUID.

The vault would then naturally prevent collisions at the ID level. Any existing note with the same ID would indicate a duplicate.

**Why this isn't straightforwardly implementable now:** For Case 1 (hook vs. import), the two extractions of the same conversation use different IDs for the conversation itself (`session_id` vs. `uuid`). Without a cross-reference, deterministic IDs from the two namespaces are still different even for the same underlying conversation.

This approach only becomes fully effective if there's a way to derive a stable, shared conversation identity across both paths — which requires either the Anthropic platform to expose transcript→export UUID mappings, or the hook to fingerprint the conversation content itself.

---

### Recommended implementation plan

**Phase 1 (high value, low cost): Session registry**

1. Create `~/.claude/kg-sessions.json` with the structure described above.
2. Modify the hook (`hooks/pre-compact-extract.sh`) to write to the registry after `extract_beats.py` completes successfully (read exit code from extractor, parse `[extract_beats] Done. N beat(s) written.` from stderr).
3. Modify the `/kg-extract` skill to read the registry before extraction and warn (but not block) if the session ID is already recorded.
4. Modify the skill to write to the registry after successful extraction.

This solves Cases 4 and 5 cleanly and provides an audit trail of all hook-driven extractions.

**Phase 2 (medium value, medium cost): Content-hash index**

1. Add a `kg-content-hashes.json` index at `~/.claude/`.
2. Modify `write_beat()` to check the hash index before writing and update it after writing.
3. Use the index in both the hook path and the import path.
4. Add a `--force-rewrite` flag to the import script to bypass hash checks for explicit reprocessing.

This provides probabilistic deduplication for Cases 1 and 3 — the hook-vs-import cross-path cases.

**Phase 3 (low value now, enables future robustness): Import-side timestamp filtering**

Extend the import script to read the session registry and automatically determine the earliest hook extraction date. Offer `--before-hook-history` as a flag that automatically sets `--until` to that date, making it easy to safely import historical conversations without touching content the hook has already captured.

---

### What to explicitly not do

**Do not vault-scan on every write.** Grepping the entire vault for duplicate titles or summaries before each write is expensive and gets slower as the vault grows. The hash index is the right approach — O(1) lookup.

**Do not block extraction on uncertainty.** If the dedup check is inconclusive (hash not found, registry lookup fails, index is corrupt), write the beat. A false negative (writing a duplicate) is far less harmful than a false positive (silently dropping a genuine beat). The system should err toward capture.

**Do not try to retroactively link hook session IDs to export UUIDs.** This mapping does not exist in any accessible data. Building it would require either Anthropic API access to conversation metadata or brittle heuristics (matching by timestamp + content length). The hash-based approach is more practical and does not require this mapping.

---

### Summary table

| Case | Root cause | Solved by |
|---|---|---|
| 1. Hook + import on same conversation | No cross-namespace dedup | Phase 2: content-hash index (probabilistic) |
| 2. Two overlapping exports | No state file | Already solved by import state file |
| 3. Partial hook capture + full import | No cross-namespace dedup | Phase 2: content-hash index (probabilistic) |
| 4. `/kg-extract` + hook on same session | No session registry | Phase 1: session registry |
| 5. Manual re-extract of hook-captured session | No session registry | Phase 1: session registry |

The highest-priority implementation is Phase 1 (session registry) because it is low-cost, fully deterministic, and addresses the cases users are most likely to encounter accidentally. Phase 2 (content-hash index) is the right long-term answer for cross-path deduplication and should follow once Phase 1 is validated.
