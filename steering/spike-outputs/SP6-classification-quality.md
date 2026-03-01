# SP6: Classification Quality and Human-in-the-Loop Options

**Date:** 2026-02-27
**Status:** Investigation complete

---

## Part 1: Analysis of Current Classification

### 1.1 The Extraction Prompt

The extraction system uses two prompts loaded from disk at runtime:

- `prompts/extract-beats-system.md` — the system prompt defining the extraction task
- `prompts/extract-beats-user.md` — the user message template injecting session context and the transcript

The system prompt is 34 lines. The user message template is 15 lines plus the injected transcript.

#### Beat Type Definitions

The system prompt defines beat types only in a narrative example list under the heading "A 'beat' is a self-contained unit of knowledge...":

```
- Decisions made (why X was chosen over Y)
- Problems solved (what went wrong and how it was fixed)
- Insights gained (non-obvious understanding about a system, library, or approach)
- Significant code patterns or configurations established
- Error fixes (the bug and the resolution)
- Reference facts (commands, API quirks, config values worth remembering)
```

The JSON schema then lists the valid type values inline: `"one of: decision, insight, task, problem-solution, error-fix, reference"`.

**Critical gap: the type definitions are inconsistent with themselves.** The narrative says "Problems solved" but the enum uses `problem-solution`. More importantly, `task` appears in the enum but has no corresponding narrative definition at all. The model must guess what "task" means from the name alone. This is almost certainly a source of miscategorization — anything that doesn't cleanly fit the other five types risks being labeled `task` or being assigned to the closest-sounding alternative.

The distinction between `problem-solution` and `error-fix` is also underspecified. Both describe something broken and how it was fixed. The prose distinction ("Problems solved" vs "Error fixes") is too fine to reliably separate in practice: an `error-fix` is effectively a specific, typically code-level instance of a `problem-solution`. Without explicit examples showing what makes one an error-fix vs a problem-solution, the model will apply these inconsistently.

Similarly, `decision` and `insight` can blur. A decision is a choice made, an insight is understanding gained — but a decision often contains the insight that led to it, and an insight about what approach to take often becomes a decision. Without disambiguation examples, both types will sometimes be applied to the same category of content.

#### Scope Determination

The system prompt defines scope with one bullet per option:

```
- "project": specific to this codebase/project (would only be useful in this project context)
- "general": broadly applicable across projects (would be useful anywhere)
```

This is a reasonable framing, but it has a structural problem: **the decision is made by a model that cannot see the vault's existing structure, the user's other projects, or the actual portability of the content in practice.** The model must guess at generalizability from the transcript alone.

The user message provides `project_name` and `cwd` as context. This helps identify what the "project" is, but offers no basis for judging whether a given insight is general or project-specific. For example: a pattern discovered while using Python's `subprocess` module is genuinely reusable across projects (scope: general), but a configuration value in a project's `.env` file is project-specific (scope: project). The model must make this judgment without any signal about the user's other projects or what they consider "general knowledge."

**Likely result:** the model applies `scope: project` too broadly — anything that mentions the project name or codebase will tend to be tagged project-scoped, even if the underlying insight (e.g., "always use stdin for subprocesses") is general. This means general-applicable beats end up in the project folder instead of the inbox, reducing their discoverability in other project contexts.

#### What Would Cause Systematic Miscategorization

Several structural issues identified:

1. **`task` is an orphan type.** It exists in the enum but has no definition in the system prompt. The model will invent a definition, which will vary between invocations. Some beats that should be `decision` or `insight` will be labeled `task` simply because the session describes work being done.

2. **`problem-solution` vs `error-fix` boundary is invisible.** No rule distinguishes a "problem" from an "error." In practice the model will apply these based on surface vocabulary (the word "error" or "bug" appearing in the beat = `error-fix`; otherwise `problem-solution`), which is noise-prone.

3. **Scope is underconstrained.** The model has no access to information that would let it make a principled scope judgment. The cwd and project name are present, but "would this be useful in other projects?" requires domain knowledge the model doesn't have.

4. **The transcript-to-beat boundary is unclear.** The prompt says to not extract "Exploratory dead-ends that went nowhere" but also to include "Error fixes (the bug and the resolution)." A debugging session that tries three wrong approaches before finding the right one contains both. The model must make a judgment call on which parts of a messy session to extract and which to discard, without clear rules for multi-part conversations.

5. **No examples.** The system prompt contains no few-shot examples of correct vs incorrect extraction. For a structured extraction task with subtle type distinctions, this is a significant limitation. Haiku is capable but benefits strongly from examples.

---

### 1.2 The Autofile Prompt

The autofile system uses `prompts/autofile-system.md` and `prompts/autofile-user.md`.

The autofile step is a separate LLM call that decides whether to **extend** an existing vault note or **create** a new one. It receives:
- The beat JSON (already classified)
- Up to 5 related vault documents found by grepping tags and title keywords
- Vault folder listing (top-level only)
- Vault filing context from `CLAUDE.md` if present

**Extend-vs-create decision quality issues:**

The system prompt says "Prefer extending over creating." This is sensible but creates a bias: if the grep-based search for related documents returns a loosely related note (similar tags, different topic), the model may extend that note rather than creating a new one. The search uses tags and title keywords, not semantic similarity — a beat about "subprocess error handling" and a note about "subprocess stdin delivery" share tags and will be returned as related, even though extending one with the other produces a muddled note.

The related-document search is also limited to 5 documents ranked by recency, not relevance. A highly relevant older note may lose to a less relevant newer one.

**Vault structure opacity:** The autofile prompt receives only a top-level folder listing. If the vault has nested structure (which is common in real Obsidian vaults), the model cannot see where existing notes actually live. It can guess at paths but not verify them. This produces the "wrong folder" error mode: a beat is filed in a plausible-looking path that doesn't match actual vault conventions.

**Content generation for `create` action:** When the model chooses to create a note, it generates the full note content as a string in the JSON response. This content is not validated against the beat's frontmatter fields. The title, type, and scope from the beat may or may not match the note content the autofile model creates. In practice, the autofile model may silently change the classification by generating different frontmatter.

---

### 1.3 Vault Note Analysis

The actual vault notes in `~/Documents/brain/Personal/Projects/knowledge-graph/Claude-Notes/` were examined. Observations:

**Classification quality: mostly correct, some structural anomalies.**

- The majority of notes are correctly typed `decision` — the sessions involved many design decisions about the project itself.
- `"Structured Logging for Beat Extraction Decisions"` is typed `decision` and is correct.
- `"Daily Journal After Each Compaction"` is typed `reference`. This is debatable — it describes both a feature implementation (which could be `decision`) and a reference for the config key format. Either type is defensible but `reference` loses the "why we built this" rationale that a `decision` type would capture.
- `"Human-Readable Filenames with Collision Handling"` and `"Human-Readable Filenames with Collision Numbering"` are **near-duplicates** in the same folder from the same session. This is the collision-handling system at work (the second note gets a numeric prefix), but both notes describe essentially the same thing. This is a deduplication problem as much as a classification problem.
- `"Pre-compact Hook Setup Troubleshooting"` has `type: resource` and `type: resource` in its frontmatter — this uses the `kg-file` skill's ontology types (`resource` = "a book, article, doc, URL") rather than the extraction prompt's types. The content is troubleshooting steps, which the extraction ontology would call `error-fix` or `problem-solution`. **This is a type-system inconsistency**: the `kg-file` skill and the automatic extractor use different type vocabularies. A note filed via `/kg-file` and a note extracted via the hook can have type values from different schemas, making vault-wide queries by type unreliable.
- `"Bedrock Backend Configuration"` also has `type: resource` — same inconsistency. This is `reference` in extractor terms.
- `"kg-extract In-Context Extraction Design"` has `type: resource` — the extractor would call this `decision`.

**The type-system inconsistency is the most concrete finding.** The `/kg-file` skill uses a 13-type ontology (`project`, `concept`, `tool`, `decision`, `insight`, `problem`, `resource`, `person`, `event`, `claude-context`, `domain`, `skill`, `place`). The automatic extractor uses a 6-type ontology (`decision`, `insight`, `task`, `problem-solution`, `error-fix`, `reference`). There is partial overlap but they are not the same schema. A vault containing notes from both paths has mixed type vocabularies.

**Scope assignments: plausible but possibly over-narrow.** All notes examined are `scope: project`. This is reasonable given these sessions were specifically about building the knowledge-graph project. But insights like "Human-Readable Filenames with Collision Numbering" are genuinely reusable patterns that could be valuable to recall in a future project with different naming requirements. The project-scope assignment makes them invisible to cross-project recall.

---

### 1.4 Expected Common Failure Modes (Summary)

Ranked by expected frequency:

1. **Type-system split between kg-file and extractor** — already present in the vault. Affects any vault with mixed ingestion paths. Makes `type:`-based queries unreliable.

2. **`task` type misassignment** — sessions involving "doing work" will frequently produce `task` beats that should be `decision`, `insight`, or `problem-solution`. `task` has no definition in the prompt.

3. **Scope over-narrowing** — general-applicable insights get `scope: project` because the session context mentions a specific project. They land in the project folder and are not surfaced in other project contexts.

4. **problem-solution vs error-fix conflation** — the model will apply these based on surface vocabulary rather than meaningful distinction. Both types represent the same knowledge shape; the split adds noise without adding retrieval value.

5. **Duplicate beats across sessions** — the same concept (e.g., "how collision numbering works") extracted in two sessions produces two notes. Without deduplication (SP8), the vault accumulates redundant beats with slightly different wording.

6. **Autofile extend-to-wrong-note** — the grep-based related-document search returns loosely related notes; the "prefer extend" bias then appends a beat to a note it doesn't actually belong to, corrupting both.

7. **Autofile path hallucination** — the model generates a path in the `create` response that doesn't reflect actual vault structure because it only sees the top-level folder list.

---

## Part 2: Human-in-the-Loop Options

### Option A: Staging Folder Review

**How it works:** All beats land in a staging folder first, regardless of confidence or type. The user reviews the folder in Obsidian and either edits frontmatter to correct classification, moves the file to its intended location, or deletes it. Nothing moves to a final location automatically.

**Triggering "move to final":** This is the fundamental weakness. Moving from staging to final requires manual action per note, with no tooling support. In Obsidian, this means drag-and-drop or the Move File command. There is no mechanism to batch-accept good beats or to propagate a corrected type back into the system's understanding.

**Assessment:**
- Implementation complexity: None — the staging folder already exists as a fallback. This option is the current state for users without project config.
- User friction: High. Every beat requires a conscious action to move or approve. In practice, most users will ignore the staging folder after a few sessions, and it will become a graveyard.
- Quality improvement: Low. Errors get fixed only if the user reviews, which they won't do consistently.

**Verdict:** Insufficient as a primary review mechanism. Useful as a fallback for uncertain beats, but not a review flow.

---

### Option B: Confidence Scoring

**How it works:** The extraction prompt is augmented to ask the LLM to produce a `confidence` score (0.0–1.0) alongside each beat. Beats above a threshold (e.g., 0.85) are auto-filed to their final destination; beats below threshold go to a staging queue.

**What the confidence signal looks like in the prompt:**

The extraction JSON schema would gain a field:

```json
{
  "title": "...",
  "type": "...",
  "scope": "...",
  "confidence": 0.0,
  "confidence_reason": "Brief explanation of uncertainty"
}
```

The system prompt would add:
- Rate your confidence that this beat's type and scope are correct (0.0 = guessing, 1.0 = certain).
- Use low confidence (< 0.7) when: the conversation was ambiguous about the outcome, the content spans multiple types, the scope could reasonably be either project or general, or the session was exploratory without a clear resolution.

**Routing logic:**

```python
CONFIDENCE_THRESHOLD = 0.80  # configurable

if beat.get("confidence", 1.0) >= CONFIDENCE_THRESHOLD:
    path = write_beat(beat, config, ...)  # direct to final destination
else:
    path = write_to_staging(beat, config, ...)  # hold for review
```

**Strengths:**
- Automatic: no user action required for high-confidence beats.
- Surfaced: low-confidence beats go to staging, which is already a known location.
- The confidence reason field gives the user actionable information when reviewing.
- The LLM is generally well-calibrated on self-assessed confidence for classification tasks when explicitly prompted.

**Weaknesses:**
- The confidence score is another LLM output that can be wrong. A miscategorized beat may still get a high confidence score (the model is confidently wrong). This is the known limitation of self-assessed confidence.
- The threshold requires tuning. Too high → everything goes to staging (same friction as Option A). Too low → miscategorized beats auto-file.
- Adds a field to the JSON schema, requiring the prompt and downstream code to change.
- Does not address the type-system split between `/kg-file` and the extractor — those beats have no confidence score at all.

**Implementation complexity:** Moderate. Prompt change, schema change, routing logic change. The staging path already exists. Estimated 1–2 hours to implement and validate the prompt change.

**User friction:** Low for high-confidence beats (none). Moderate for low-confidence beats (same as staging today, but at least the queue is smaller).

**Quality improvement:** Moderate-to-high. Catches the most ambiguous cases without adding friction to clear ones. The improvement depends on LLM calibration.

---

### Option C: Post-Extraction Review CLI (`/kg-review`)

**How it works:** A new `/kg-review` skill shows the user recent beats and allows correction of type, scope, and location interactively within a Claude Code session.

**UX design:**

```
/kg-review [--last N] [--session SESSION_ID]
```

Claude reads beats from the vault (most recent N files from the session or across all sessions), presents each with its title, type, scope, and summary, and accepts corrections:

```
Recent beats (last session):

1. "claude-cli backend eliminates API key requirement"
   type: decision  scope: project  ✓

2. "Human-Readable Filenames with Collision Numbering"
   type: decision  scope: general → SUGGEST: scope should be general (already is)
   Note: near-duplicate of #3

3. "Human-Readable Filenames with Collision Handling"
   type: decision  scope: project → SUGGEST: scope: general (same pattern, reusable)

Commands: [number] type=X | [number] scope=X | [number] delete | done
```

Claude makes edits to the vault file frontmatter using Write/Edit tools in response to corrections.

**Strengths:**
- Natural UX within the existing CLI workflow.
- Can present smart suggestions (e.g., detect near-duplicates, flag scope conflicts).
- Corrections are immediate and persistent (frontmatter edit).
- Can batch-process a whole session at once.

**Weaknesses:**
- Skills running inside an active Claude Code session cannot call `claude -p` (CLAUDECODE env var blocked). So the skill must do all classification work in-context using Claude's tools (Read, Edit), not via the extraction pipeline. This is fine for review, but means the skill cannot re-run extraction to generate alternative classifications.
- The review is in-session, so it's ephemeral context — the user must remember to run it. No automatic prompt.
- Implementation requires a non-trivial skill that reads vault files, presents structured output, and applies edits. More complex than confidence scoring.
- Does not help with the type-system split — correcting a `resource` to a `decision` in frontmatter doesn't change the ontology mismatch.

**Implementation complexity:** High. Requires a new skill with multi-step interactive behavior, vault reads, and frontmatter edits. Estimated 4–8 hours.

**User friction:** Moderate. Requires explicit invocation after each session. The user must remember to run it. But it's concentrated friction (one review session covers multiple beats).

**Quality improvement:** High, if actually used. Low if the user forgets to run it.

---

### Option D: Obsidian Plugin

**How it works:** A custom Obsidian plugin surfaces beats with `status: staged` (or in the staging folder) with an approve/reclassify/reject UI in the Obsidian sidebar.

**Realism assessment:**

Building an Obsidian plugin requires TypeScript development, understanding the Obsidian plugin API, and a separate build/distribution pipeline. This is a completely separate engineering surface from the current Python/bash codebase. The plugin would need to:

- Monitor a staging folder or query by `status` frontmatter field
- Render a review UI in the Obsidian sidebar
- Write frontmatter edits on approval/correction
- Optionally trigger a file move on approval

**Strengths:**
- Obsidian is already where the user reviews the vault. Review happens where the content lives.
- The UI can be rich: show the full note, allow inline editing, link to related notes.
- No command-line involvement after initial setup.
- Would work across all ingestion paths (hook extraction, `/kg-file`, import script).

**Weaknesses:**
- Development complexity is very high — a completely new codebase and discipline (TypeScript, Obsidian plugin API).
- Maintenance burden is high — plugins break across Obsidian versions.
- Distribution requires the Obsidian community plugin store or manual installation.
- Disproportionate to the project's current scope and user base (essentially one user at this stage).
- Would not help until the user opens Obsidian — if review is deferred, the staging queue grows stale.

**Implementation complexity:** Very high. New codebase, new language, new distribution channel. Not realistic for the current phase.

**User friction:** Low once built (review happens where content lives). Very high to build.

**Quality improvement:** High potential, but conditional on it actually being built and maintained.

**Verdict:** Not recommended for current phase. Revisit if the project reaches a user base that justifies a dedicated plugin.

---

## Part 3: Ranked Recommendations

### Recommendation 1 (Implement): Confidence scoring with staging threshold

**Priority: High. Implement before other options.**

Add a `confidence` field to the extraction JSON schema. Instruct the model to self-assess confidence on type and scope classification, and provide a brief reason when confidence is low. Route beats with confidence below a configurable threshold to the staging folder instead of final destination.

This is the highest-leverage change: it requires no new user workflow, improves quality automatically for the clear cases, and concentrates ambiguous beats in the staging folder where they can be reviewed with less cognitive overhead (the user knows that staging contains uncertainty, not just overflow).

**Suggested config key:** `confidence_threshold` (default: `0.80`).

**Changes required:**
- `prompts/extract-beats-system.md`: add `confidence` (float, 0.0–1.0) and `confidence_reason` (string) to the JSON schema
- `extractors/extract_beats.py`: read `confidence` from each beat; route to staging if below threshold
- `extractors/extract_beats.py`: log the confidence score alongside the beat title in the extraction log

**Risk:** LLM self-confidence is imperfect. A miscategorized beat can still score high confidence. But even imperfect confidence routing is better than no routing — it will correctly identify the ambiguous cases more often than not.

### Recommendation 2 (Fix immediately): Unify the type system

**Priority: High. Fix before adding more notes.**

The `/kg-file` skill and the automatic extractor use different type vocabularies. This is already present in the vault and will compound as both paths are used more. The fix is to choose one type vocabulary and apply it everywhere.

**Recommended resolution:** Extend the extractor's 6-type schema to cover the `/kg-file` ontology's additional types (`project`, `concept`, `tool`, `problem`, `resource`, `person`, `event`, `claude-context`, `domain`, `skill`, `place`), or collapse the `/kg-file` skill's types to the extractor's 6. The latter is simpler and preserves retrieval consistency.

The `/kg-file` skill's 13 types are richer and better suited to human-authored notes (the `person`, `event`, `place` types make no sense for automatically extracted beats). A practical resolution: keep both vocabularies but define a canonical mapping for the overlapping types, and ensure the `VALID_TYPES` set in `extract_beats.py` accepts all types from both schemas. This prevents the silent fallback to `reference` for any unknown type.

### Recommendation 3 (Implement): Define `task` or remove it

**Priority: Medium. Do before next extraction prompt iteration.**

The `task` type has no definition in the extraction system prompt. Either:
- Define it clearly: `task` = a completed unit of work, described by what was done and its outcome (vs. `decision` which captures why). Add an example. Or:
- Remove it from the enum. If no beat naturally fits `task`, it adds confusion without adding value.

Based on the vault notes examined, no currently filed note is typed `task`. This suggests either the model avoids it (because it's undefined) or the extraction sessions haven't produced task-shaped content. Either way, the undefined type is a prompt defect.

### Recommendation 4 (Implement): Add few-shot examples to the extraction prompt

**Priority: Medium.**

The extraction system prompt currently has zero examples. Adding 2–3 examples showing the full JSON for a correctly classified beat of different types — including one that illustrates the `problem-solution` vs `error-fix` distinction — would meaningfully reduce classification variance.

Example additions to `extract-beats-system.md`:

```json
// EXAMPLE: error-fix (specific code-level bug and its fix)
{
  "title": "subprocess.run with text=True fails on binary output",
  "type": "error-fix",
  "scope": "general",
  "summary": "...",
  "tags": ["subprocess", "python", "encoding"],
  "body": "..."
}

// EXAMPLE: problem-solution (design-level problem requiring judgment)
{
  "title": "Hook must exit 0 even on extraction failure",
  "type": "problem-solution",
  "scope": "project",
  "summary": "...",
  "tags": ["hook", "precompact", "error-handling"],
  "body": "..."
}
```

### Recommendation 5 (Design): `/kg-review` skill as phase 2

**Priority: Low. Design now, implement after confidence scoring is validated.**

The `/kg-review` skill is the right next step after confidence scoring is in place. By that point, the staging queue will contain only uncertain beats, making review sessions shorter and more purposeful. Design the skill to:

1. Read all notes in the staging folder (or from the last N sessions)
2. Present each with title, type, scope, confidence, and confidence_reason
3. Accept corrections as simple commands
4. Apply frontmatter edits to vault files via Edit tool
5. Move corrected notes to their final destination using Bash or Write

The skill does not need to re-run extraction — it works on already-extracted beats. This keeps the implementation within the skill constraint (no `claude -p` subprocess).

### Summary Table

| Option | Complexity | User Friction | Quality Gain | Recommended? |
|---|---|---|---|---|
| Confidence scoring (B) | Low | Low | Moderate-High | Yes — implement first |
| Type system unification | Low | None | High | Yes — fix immediately |
| Define/remove `task` type | Minimal | None | Low-Medium | Yes — quick win |
| Few-shot examples in prompt | Minimal | None | Medium | Yes — quick win |
| `/kg-review` skill (C) | High | Moderate | High (if used) | Phase 2 |
| Obsidian plugin (D) | Very High | Low | High | No — out of scope |
| Staging-only (A) | None | High | Low | No — already exists |

---

## Appendix: On CLAUDE.md and Autofile Accuracy

The SP6 spike asked whether improving the vault's `CLAUDE.md` quality reduces autofile errors. Based on the autofile prompt analysis:

The `CLAUDE.md` provides vault filing conventions to the autofile model. Its presence helps the model choose appropriate folder paths for `create` actions and understand the vault's ontology. However, the primary sources of autofile error are:
1. The grep-based related-document search (not semantic, returns loosely related results)
2. The top-level-only folder listing (model can't see nested structure)
3. The "prefer extend" bias when the related doc is wrong

Improving `CLAUDE.md` will help with folder selection (#2) but not with search quality (#1) or extend bias (#3). The improvement is real but bounded. Running `/kg-claude-md` after the vault has accumulated structure is worthwhile, but it is not a substitute for fixing the autofile search step itself.

The autofile search should be improved in a later spike (SP12 covers retrieval architecture). For now, users who find autofile making wrong extend-vs-create decisions should set `autofile: false` and use the flat write path until retrieval quality improves.
