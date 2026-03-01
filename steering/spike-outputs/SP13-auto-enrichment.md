# SP13: Auto-enrichment of Human-Authored Notes

**Status:** Investigation complete
**Date:** 2026-02-27
**Output:** Definition of "needs enrichment", detection heuristic, quality assessment, and `/kg-enrich` skill spec

---

## Part 1: The Gap — Well-Formed vs. Needs Enrichment

### What a well-formed beat looks like

Every note written by `extract_beats.py` has a fixed YAML frontmatter schema:

```yaml
---
id: 397b693d-4949-4c9c-a4b5-52c2ca0c01be
date: 2026-02-27T02:36:27
session_id: 79a35831-b5d1-459b-8996-afbf92cbea0c
type: decision
scope: project
title: "claude-cli backend eliminates API key requirement for beat extraction"
project: knowledge-graph
cwd: /Users/dan/code/knowledge-graph
tags: ["claude-cli", "backend", "extract-beats", "api-key", "precompact-hook"]
related: []
status: completed
summary: "Made claude-cli the default backend for extract_beats.py so users with a Claude Pro subscription can run the precompact hook without any API key or AWS credentials, shelling out to `claude -p` instead of the anthropic SDK."
---
```

The body is structured markdown: an `## Title` heading, then `##` sub-sections (Decision, Rationale, Implementation, etc.) that make the note self-contained and scannable.

Functionally, a well-formed beat is findable by `/kg-recall` because:
- `type` is one of the 6 valid values (drives classification and filtering)
- `summary` is an information-dense sentence that surface in grep-based retrieval
- `tags` are 2–6 lowercase keywords that drive the vault search in `search_vault()`
- `scope` routes the note correctly for project-vs-general retrieval

### What human-authored notes look like

Two patterns observed in the vault:

**Pattern A — Obsidian-native frontmatter (sparse, wrong schema):**

```yaml
---
title: Pre-compact Hook Setup Troubleshooting
type: resource
status: done
created: 2026-02-26
updated: 2026-02-26
tags:
  - personal
aliases: []
---
```

This note has frontmatter, but:
- `type` is `resource` — not one of the 6 valid beat types (`decision`, `insight`, `task`, `problem-solution`, `error-fix`, `reference`)
- `tags` contains only `personal` — a domain tag, not content keywords
- No `id`, `session_id`, `scope`, `summary`, `project`, `cwd`
- The content is technically a `problem-solution` or `error-fix` — it documents two root causes and their fixes

**Pattern B — Richly authored but wrong schema (also human-added):**

The `kg-extract In-Context Extraction Design.md` note was added to the vault via a previous session but has the same Obsidian-native schema (title, type: resource, status: done, tags: personal). Despite having excellent body content — Decision, Rationale, Implementation, Implication sections — it lacks `summary`, `scope`, and a valid `type`.

**The retrieval consequence:** When `/kg-recall` searches the vault by tag, neither note surfaces on topic-relevant queries. A search for "python hook troubleshooting" or "anthropic package install" returns nothing, because the only tag on the troubleshooting note is `personal`. The `summary` field — the primary search signal — is absent entirely.

### The schema divergence

The vault contains two coexisting schemas:

| Field | Beat schema (extractor) | Obsidian-native schema (human) |
|---|---|---|
| `id` | UUID | absent |
| `type` | One of 6 beat types | Obsidian entity type (resource, concept, etc.) |
| `scope` | `project` or `general` | absent |
| `summary` | One-sentence retrieval hook | absent |
| `tags` | Content keywords | Domain tags (personal, work) |
| `session_id` | Present | absent |
| `project` / `cwd` | Present | absent |
| `status` | `completed` | `done`, `active`, `evergreen` |

Both schemas are valid markdown; neither is "wrong" in an absolute sense. But only the beat schema makes notes retrievable by the system's search and injection mechanisms.

---

## Part 2: Detection — "Needs Enrichment" Heuristic

### The core question

A note needs enrichment when it cannot be reliably found by `/kg-recall` and/or cannot be usefully injected into context because its frontmatter is missing or structurally incompatible with the beat schema.

### Primary signal: `type` field

The `type` field is the single most decisive indicator. The system only understands 6 types:

```
decision | insight | task | problem-solution | error-fix | reference
```

A note needs enrichment if **any** of these is true:

1. **No frontmatter at all** — the file has no `---` delimiters at the top
2. **Frontmatter exists but `type` is absent** — no type classification at all
3. **`type` is present but not one of the 6 valid beat types** — e.g., `type: resource`, `type: concept`, `type: note`, `type: journal`, `type: domain`
4. **`type` is valid but `summary` is absent** — the note has a type but no retrieval hook; it will be found by grep only if keywords happen to match
5. **`type` is valid, `summary` is present, but `tags` is empty or absent** — tag-based search returns nothing

### Secondary signals (lower priority, address if primary signals pass)

- `scope` is absent (cannot route the note for project-vs-general retrieval)
- `tags` contains only domain tags (`personal`, `work`) with no content keywords

### Detection algorithm

```
def needs_enrichment(note_path):
    fm = parse_frontmatter(note_path)

    if fm is None:
        return True, "no-frontmatter"

    note_type = fm.get("type")

    if note_type is None:
        return True, "missing-type"

    VALID_BEAT_TYPES = {
        "decision", "insight", "task",
        "problem-solution", "error-fix", "reference"
    }

    if note_type not in VALID_BEAT_TYPES:
        return True, "invalid-type"

    if not fm.get("summary"):
        return True, "missing-summary"

    tags = fm.get("tags", [])
    content_tags = [t for t in tags if t not in DOMAIN_TAGS]
    if not content_tags:
        return True, "no-content-tags"

    return False, None
```

Where `DOMAIN_TAGS` is a small set of known domain-level tags to exclude: `{"personal", "work", "home"}`.

### What is explicitly excluded from "needs enrichment"

The detection should **skip** notes that are:

- Journal or daily notes (type: `journal`, or filename matches `YYYY-MM-DD.md`)
- MOC / index notes (type: `moc`, `index`, or filenames like `_index.md`, `MOC.md`)
- Template files (in any folder named `templates/` or `_templates/`)
- Already-enriched beats with all required fields present
- Notes with a frontmatter marker `enrich: skip` (opt-out, see Part 4)

### Opt-out marker

A note should be able to declare itself non-enrichable. The simplest mechanism is a frontmatter field:

```yaml
enrich: skip
```

This covers: intentional freeform drafts, working documents, scratch notes, notes in formats that don't map to beats (meeting agendas, reading lists, etc.).

---

## Part 3: Enrichment Quality Assessment

### What the enrichment LLM is being asked to do

Unlike extraction (which reads a rich conversation transcript to find beats), enrichment reads **a single note the LLM did not author** and must:

1. Classify it into one of 6 typed categories from the note content alone
2. Write a one-sentence summary optimized for future search
3. Select 2–6 content-relevant tags
4. Optionally assign scope (`project` vs `general`)

This is a different task from extraction. The LLM has less context and must infer intent from the author's writing rather than a conversation it participated in.

### How well would Haiku perform at this?

**Strengths:** The task is well-bounded. The note body contains the content; the LLM is classifying what's already there, not inventing knowledge. For notes with clear structure (a bug description and fix, a documented decision, a command reference), Haiku should classify correctly and reliably.

**Specific failure modes to expect:**

**1. Type misclassification for ambiguous notes.** Many notes sit on the boundary between types:
- A note documenting "why we chose X" could be `decision` or `insight`
- A troubleshooting guide could be `problem-solution` or `reference` depending on framing
- A completed task description could be `task` or `decision`

Haiku will pick one, but without conversation context it lacks the author's intent. Misclassification rate on ambiguous notes is likely 20–30%. This is acceptable: the types are similar enough that a wrong type rarely causes the note to be unfindable.

**2. Over-tagging.** Haiku tends to enumerate every mentioned concept as a tag. A note about configuring Bedrock authentication for AWS will generate tags like `aws`, `bedrock`, `authentication`, `api-key`, `iam`, `credentials`, `boto3`, `configuration` — instead of the 3–4 most distinguishing terms. The extraction prompt enforces `2-6 tags`, but for external notes the model may not apply this discipline as strictly.

Mitigation: the enrichment prompt should be specific — "choose 2–6 tags that a future reader would use to search for this note, not an exhaustive list of topics mentioned."

**3. Inventing context that isn't there.** For sparse notes (a one-paragraph thought, a bullet list without context), the model may pad the summary with inferred context. Example: a note reading "CTCSS tone false triggers — check squelch tail settings" might generate a summary that invents a specific radio model or a specific symptom it wasn't told about.

Mitigation: the enrichment prompt should explicitly instruct "summarize only what the note says, do not infer or add context not present in the note."

**4. Wrong scope assignment.** Without knowing the note's place in the vault structure, the model will often assign `general` when the note is clearly project-specific, or `project` for broad reference content. Scope is also the field with the lowest retrieval impact — getting it wrong doesn't make the note unfindable, it just routes it to the wrong folder in future filing decisions.

**5. Summary not retrieval-optimized.** Haiku's default summaries tend to be descriptive prose: "This note describes the process of configuring X." A retrieval-optimized summary front-loads the key noun and verb: "Configuring X requires Y, which avoids Z." The enrichment prompt needs to model this explicitly.

### Model selection: Haiku vs. larger model

**Recommendation: Haiku is appropriate for enrichment, but with a more carefully crafted prompt than the extraction prompt.**

The extraction task is given rich conversational context and must identify what's worth saving. Enrichment is given a finished note and must classify it — a structurally simpler task even if the note is sparse. The classification space is small (6 types), the summary target is short (1 sentence), and the tag vocabulary is bounded. Haiku handles well-structured notes reliably.

A larger model (Sonnet or higher) would reduce misclassification on ambiguous notes and produce better summaries for sparse notes. However:
- The marginal quality gain on well-formed notes (the majority) is small
- The cost differential is 5–10x per note
- A vault with 500 notes enriched at Haiku cost is clearly preferable to 100 notes enriched at Sonnet cost

**Exception:** If the vault contains many very sparse notes (< 3 sentences of body content), consider a config option to use a larger model for enrichment. For notes with substantive body content, Haiku is sufficient.

### Minimum viable enrichment: what fields are required?

**Minimum set (required for retrieval to work):**
- `type` — one of the 6 valid values; enables type-based filtering
- `summary` — the primary search signal; drives grep-based recall
- `tags` — 2–6 content keywords; drives `search_vault()` in the autofile path

**Recommended additions (low cost, high value):**
- `scope` — `project` or `general`; needed for correct routing if the note is ever moved or re-filed

**Do not require:**
- `id` — can be generated locally without an LLM call
- `session_id` — not applicable for human-authored notes; leave absent or set to `human-authored`
- `cwd` — not applicable; leave absent

**Body restructuring: no, not by default.**

The note body should not be restructured. The author's voice and organization are intentional. Enrichment adds frontmatter; it does not rewrite the note. Two reasons:
- Destructive body edits are unrecoverable without version control
- The body may be read directly by humans; reformatting to the beat template (`## Title\n\n## Rationale`) may break the author's intent

An opt-in `--restructure-body` flag could be offered for notes where the author wants full beat normalization, but it should not be the default.

---

## Part 4: Interface Design — `/kg-enrich` Skill Spec

### Overview

`/kg-enrich` scans a set of vault notes, identifies those that need enrichment (per the detection algorithm above), calls the LLM to produce the missing frontmatter fields, and applies them to the files — either in place or to a staging area for review.

This is fundamentally different from `extract_beats.py`:
- Source: existing vault notes, not session transcripts
- Output: enriched frontmatter on existing files, not new beat files
- LLM input: note content (the file body), not conversation turns
- LLM output: a structured fields object (`type`, `summary`, `tags`, `scope`), not a full beat

### Trigger and invocation

```
/kg-enrich [--folder <vault-relative-path>] [--dry-run] [--since <date>] [--limit <n>]
```

| Flag | Meaning |
|---|---|
| *(no flags)* | Scan the entire vault |
| `--folder AI/Claude-Sessions` | Limit to a specific vault folder (vault-relative path) |
| `--since 2026-01-01` | Only notes modified on or after this date |
| `--limit 20` | Process at most N notes (useful for testing or incremental runs) |
| `--dry-run` | Report which notes would be enriched, make no changes |

### Scope selection: which notes to process

Priority order:
1. **If `--folder` is given:** scan only that folder, recursively
2. **If `--since` is given without `--folder`:** scan the entire vault but filter by modification time
3. **Otherwise:** scan the entire vault

Within any scope, always skip:
- Notes that already have all required fields (idempotency)
- Notes with `enrich: skip` in frontmatter
- Files matching journal/daily note patterns (`YYYY-MM-DD.md`)
- Files in `templates/` or `_templates/` folders

### Edit strategy: additive-only, in place

Three strategies were considered:

**A. Destructive (full rewrite in place):** Simple, but overwrites any existing frontmatter and risks destroying human-authored fields not in the beat schema. Not recommended.

**B. Staged (write to a review queue):** Safer, but requires a second review step. The user must approve each enrichment before it's applied. High quality but high friction — likely to be ignored.

**C. Additive only (add missing fields, never overwrite existing):** Lowest risk. If a field is already present, leave it unchanged. Only add fields that are absent. If `type` is already set to `resource`, leave it — enrichment only adds missing fields, it does not correct existing ones.

**Recommendation: Additive-only by default, with a `--overwrite` flag for correcting wrong types.**

The additive-only strategy is safe to run repeatedly (idempotent), never destroys human intent, and handles the common case (missing `summary` and `tags`) correctly. The `--overwrite` flag allows the user to explicitly request that existing `type` or `tags` values be replaced by LLM-generated ones — appropriate for notes where the author used the wrong schema intentionally or the type is clearly wrong.

**Idempotency check:** Before calling the LLM for a note, check which required fields are missing. If all required fields are present and non-empty with a valid type, skip. This means running `/kg-enrich` twice on the same vault produces no additional changes on already-enriched notes.

### LLM prompt design for enrichment

The extraction prompt is designed for transcripts. Enrichment needs a different prompt because:
- There is no conversation context — only the note itself
- The model should not invent context not present in the note
- The output format is narrower: fields object, not a full beat

**System prompt (enrichment-system.md):**

```
You are a knowledge tagging assistant. You read a single markdown note and produce structured
metadata for it so it can be retrieved in future search queries.

Your job is to classify, summarize, and tag — not to rewrite, interpret, or add information
not in the note. If the note is ambiguous, make the most defensible choice and move on.

Return ONLY a JSON object with exactly these fields:
{
  "type": "one of: decision, insight, task, problem-solution, error-fix, reference",
  "summary": "One sentence. Start with what the note is about, not with 'This note...'
               Front-load the key noun. Optimize for future search — include terms a reader
               would search for when looking for this knowledge.",
  "tags": ["2-6 lowercase keywords. Choose the most distinguishing terms. Omit generic words
            like 'note', 'information', 'guide'. Omit domain tags like 'personal' or 'work'."],
  "scope": "project (specific to one codebase or project) or general (broadly applicable)"
}

Type selection guide:
- decision: a choice made between alternatives, with rationale
- insight: a non-obvious understanding or pattern
- task: a completed unit of work and its outcome
- problem-solution: a problem encountered and how it was resolved
- error-fix: a specific error or bug and the exact fix
- reference: a fact, command, configuration value, or snippet worth looking up

If the note does not fit any of these types cleanly (it is a draft, freeform writing, meeting
notes, journal entry, or reading list), return:
{"type": null, "summary": null, "tags": [], "scope": null}

Return null fields for any value you cannot determine from the note content alone.
```

**User message template (enrichment-user.md):**

```
Note content:

---
{note_content}
---

Classify this note. Return the JSON object only.
```

### Handling intentionally unstructured notes

Some notes are not beats and should never be forced into the beat schema:
- Freeform drafts ("thinking out loud" writing)
- Meeting agendas and action item lists
- Reading lists, bookmarks, link dumps
- Daily / weekly journals

Two mechanisms handle this:

**1. Opt-out frontmatter marker:**

```yaml
enrich: skip
```

This is checked before any LLM call. Notes with this marker are completely skipped.

**2. LLM null return:** The enrichment prompt explicitly instructs the model to return null fields if the note doesn't fit the beat schema. When the LLM returns `{"type": null, ...}`, the skill:
- Skips the note (no changes)
- Reports it as "skipped — no beat type found"
- Optionally adds `enrich: skip` to prevent future attempts (with `--mark-skipped` flag)

### Applying the enriched frontmatter

For each note where enrichment produces non-null fields:

1. Parse the existing frontmatter (if any)
2. For each enriched field (`type`, `summary`, `tags`, `scope`):
   - If the field is absent from existing frontmatter: add it
   - If the field is present and `--overwrite` was not specified: leave it unchanged
   - If `--overwrite` was specified: replace it
3. If the note has no frontmatter: add a minimal `---` block with only the enriched fields plus a generated `id` field
4. Write the updated file in place

### Reporting

After a run, the skill reports:

```
/kg-enrich complete — 47 notes scanned

  Enriched:     23 notes
  Already done: 18 notes  (all required fields present, skipped)
  Skipped:       4 notes  (enrich: skip or null type returned)
  Errors:        2 notes  (LLM call failed or parse error)

Enriched notes:
  + Pre-compact Hook Setup Troubleshooting.md  → type: error-fix, tags: [pre-compact, hook, anthropic, python, backend]
  + kg-extract In-Context Extraction Design.md → type: decision, tags: [kg-extract, in-context, autofile, claude-cli]
  ...
```

### Differences from `extract_beats.py`

| Dimension | `extract_beats.py` | `/kg-enrich` |
|---|---|---|
| **Source** | Session transcript (JSONL or text) | Existing vault notes (markdown files) |
| **LLM input** | Full conversation reconstruction | Single note body |
| **LLM output** | Array of complete beat objects (title, type, scope, summary, tags, body) | Fields object (type, summary, tags, scope) only |
| **Output action** | Creates new vault files | Modifies existing vault files (frontmatter only) |
| **Body content** | LLM writes the body | Body is preserved as-is |
| **Session context** | Has full session context for correct classification | Reads only the note; infers from content |
| **Idempotency** | Creating duplicate beats is a separate deduplication problem | Designed to be idempotent; re-runs are safe |
| **Scope** | Always writes to configured inbox/vault_folder | Operates on whatever folder the note lives in |

### Implementation path

The skill follows the same in-context pattern as `/kg-extract`:

1. Scan the target scope to identify candidate notes (using Glob + Read to check frontmatter)
2. For each candidate, call the LLM with the note body via the enrichment prompt
3. Parse the returned JSON fields object
4. Apply additive-only frontmatter updates using the Edit tool
5. Log and report results

No changes to `extract_beats.py` are required. The skill handles everything in-context using existing tools (Glob, Read, Grep, Edit, Write). The enrichment prompts (`prompts/enrich-system.md`, `prompts/enrich-user.md`) are new files added alongside the existing prompt files.

### Edge cases

**Note has valid beat frontmatter already:** Skip entirely (idempotent).

**Note has partial beat frontmatter (e.g., `type` but no `summary`):** Add only the missing fields. Do not touch existing fields unless `--overwrite`.

**Note body is very short (< 50 words):** Still attempt enrichment. For extremely sparse notes (a title and one line), the model should return `type: null` per the prompt instructions, and the note is skipped. Do not hard-filter by length — a one-line reference note (`AWS_PROFILE=prod-readonly — use this for production read-only access`) is a valid `reference` beat.

**LLM call fails or returns malformed JSON:** Log the error, skip the note, continue to the next. Do not abort the whole run.

**File encoding issues or very large notes:** Read at most the first 3000 characters of the note body for the LLM call. This is sufficient for type, summary, and tag classification. Full body reads are unnecessary.

**Notes with the Obsidian-native schema (correct type field under a different vocabulary):** E.g., a note typed as `type: resource` where `resource` is also a valid beat type. This is handled correctly by the detection algorithm: `resource` is in `VALID_BEAT_TYPES`, so the note is not flagged for type enrichment — only for `summary` and `tags` if those are missing.

---

## Recommendations

1. **Build `/kg-enrich` as the next skill after system stabilization (SP3).** The gap is real: every human-authored note in the vault is currently invisible to recall.

2. **Use Haiku with an enrichment-specific prompt.** The extraction prompt is not appropriate for enrichment. A new prompt pair (`enrich-system.md`, `enrich-user.md`) is needed, with explicit instructions against inventing context and with clear null-return semantics for non-beat notes.

3. **Make the opt-out marker (`enrich: skip`) part of the spec from day one.** Without it, every draft or journal note in a general vault will require the LLM to make a null-return call — wasted API cost and noise in the report.

4. **Default to additive-only editing.** The risk of destroying human-authored frontmatter is not worth the convenience of `--overwrite` as a default. Make it explicit.

5. **Start with `--dry-run` validation before applying changes.** On first use, users should be able to see what the skill would do before it writes anything. The dry-run report (which notes would be enriched, what types and tags would be assigned) is a useful quality check.

6. **The `--since` flag is the key to sustainable operation.** A vault of 500 notes doesn't need full re-enrichment every week. Running `/kg-enrich --since 2026-01-01` after a batch of new notes were added is the intended ongoing usage pattern.
