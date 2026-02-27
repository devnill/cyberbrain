---
name: kg-file
description: >
  File a piece of information into a personal knowledge graph stored as Obsidian markdown.
  Use this skill whenever the user wants to capture, store, log, or save information into
  their knowledge base — including insights, decisions, problems, project notes, Claude
  context summaries, concepts learned, or any other information that deserves a permanent
  home. Trigger on phrases like "save this", "add this to my notes", "file this", "capture
  this", "make a note of", "log this", "add to my knowledge base", or whenever the user
  shares a piece of information and implies they want it preserved. Also trigger when the
  user asks Claude to summarize a session or conversation for later retrieval.
---

# Knowledge Graph Filing Skill

Produces a complete, ready-to-paste Obsidian markdown note for a personal knowledge graph
built on the ontology defined in `references/ontology.md`.

## Core Behavior

When invoked, Claude should:

1. **Classify** the input into the correct entity type and domain
2. **Extract** structured fields (relationships, status, confidence, source)
3. **Generate** a complete Obsidian note: YAML frontmatter + formatted body
4. **Suggest** the canonical file path for the note
5. **Identify** likely wikilinks to existing or needed stub notes
6. **Ask** one clarifying question only if critical information is truly missing — otherwise make reasonable inferences and proceed

Read `references/ontology.md` for the full entity type definitions, field schemas, and relationship vocabulary.

---

## Process

### Step 1 — Classify the input

Determine the primary entity type by asking: *what kind of thing is this note fundamentally about?*

| If the input describes... | Use type |
|---|---|
| Something actively being worked on | `project` |
| A principle, method, or technique | `concept` |
| A specific tool, app, device, or library | `tool` |
| A choice made with reasoning | `decision` |
| A lesson, realization, or pattern noticed | `insight` |
| Something broken, unknown, or unsolved | `problem` |
| A book, article, doc, URL | `resource` |
| A person | `person` |
| A one-time or recurring occurrence | `event` |
| Claude session context for a domain | `claude-context` |
| A broad area of knowledge or practice | `domain` |
| A capability possessed or being developed | `skill` |
| A physical or logical location | `place` |

When ambiguous between two types, prefer the more specific one. A realization from working on a project is an `insight`, not a `project`.

### Step 2 — Extract structured fields

From the input, identify:

- **domain**: The broad topic area (e.g., `amateur-radio`, `electronics`, `landscaping`, `iOS-dev`, `home`, `personal`, `woodworking`). Infer from context.
- **status**: Current state of this thing. Default to `active` for projects/problems, `evergreen` for concepts/insights.
- **confidence**: How certain is this information? `high` if from direct experience or verified docs. `medium` if recalled or inferred. `low` if speculative.
- **source**: Where this came from. Options: `personal-experience`, `claude-context`, `documentation`, `book`, `conversation`, `research`.
- **relationships**: What other notes does this connect to? Generate wikilinks even as stubs — the link matters even if the target note doesn't exist yet.

### Step 3 — Draft the note

Produce the note in this structure:

```
---
[YAML frontmatter per ontology schema for this type]
---

[one-sentence summary of what this note is about]

[body content — see formatting rules below]
```

#### Body Formatting Rules

- Use **explicit wikilinks**: `[[concept/fft-analysis]]` not bare mentions
- Express relationships in the sentence around the link: *"This decision was made to resolve [[problem/ctcss-false-triggers]]"*
- Keep the body focused — this is a permanent note, not a journal entry
- For `insight` and `decision` notes, always include a **Rationale** or **Why This Matters** section
- For `problem` notes, always include a **Symptoms** section and a **Possible Causes** section if known
- For `claude-context` notes, use a structured template (see ontology reference)
- For `concept` notes, include a brief definition, then practical application

### Step 4 — Output

Present the result as:

1. **Suggested path**: `type/kebab-case-title.md`
2. **Complete note**: Full markdown including frontmatter, ready to paste
3. **Stub notes needed**: A list of wikilinked notes that don't exist yet but should be created
4. **One optional follow-up**: If there's a natural next action (e.g., "this problem note suggests creating a related decision note"), mention it briefly

---

## Tone and Style

- Be direct and terse in the generated note — this is reference material, not prose
- Use present tense for facts, past tense for events
- Prefer concrete specifics over vague generalities
- The note should read as if written by the user, not by an AI assistant

---

## Edge Cases

**Input is a conversation or session summary**: Classify as `claude-context`. Structure it by domain with subsections for active projects, known concepts, and open problems.

**Input spans multiple entity types**: File the dominant entity type as the main note. Create brief stub notes (frontmatter only, one-line description) for the secondary entities. List them in the output.

**Input is very short / low context**: Make reasonable inferences and proceed. State your assumptions clearly in a comment at the top of the output (not inside the note itself). Do not interrogate the user with multiple questions.

**Input already has structure** (e.g., bullet list, existing frontmatter): Preserve the structure, normalize to the schema, fill any missing required fields.

**Domain is unknown**: Default to `personal` and flag it for the user to correct.

---

## Reference Files

- `references/ontology.md` — Full entity type schemas, relationship vocabulary, domain taxonomy, and example notes. Read before generating output for unfamiliar entity types.
