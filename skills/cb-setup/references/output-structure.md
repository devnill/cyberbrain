# CLAUDE.md Output Structure Reference

This file defines the required sections, content, and tone for the CLAUDE.md
that this skill generates. Every generated CLAUDE.md must follow this structure.

---

## What CLAUDE.md Is

A `CLAUDE.md` placed at the root of an Obsidian vault is a persistent instruction document
for Claude. When Claude operates in or alongside this vault — filing notes, retrieving context,
analyzing sessions — it reads CLAUDE.md first to understand the vault's conventions.

The document must be **prescriptive, not descriptive**. It tells Claude what to do, not just
what exists. Every section should answer: "If I am Claude and I need to do X in this vault,
what exactly should I do?"

### Core output principles

These govern every section of the generated CLAUDE.md:

**No counts or percentages.** Never include note counts, percentages, or frequencies. They
go stale the moment the vault changes and add no value for filing decisions. Describe
patterns and rules, not the current state of the vault.

**Patterns over instances.** Describe structural rules using generic placeholders
(`Work/Projects/<project-name>/`) rather than listing specific areas by name. Only name a
specific folder or area when it is a first-class structural concept (e.g., `Inbox/`,
`Archive/`, `templates/`) — not when it is one instance of a repeating pattern. This keeps
the guidance valid as the vault grows.

**Domain-agnostic for general-purpose vaults.** When the vault is a whole-life or
multi-domain PKM, keep entity-type and filing guidance domain-agnostic. Do not reference
specific project names, people, or content areas as filing guides — these become outdated
and mislead rather than help. Describe the structural rule; Claude can apply it to any
specific content.

**Systematic rules only.** Every convention in CLAUDE.md must be generalizable. If a rule
only applies to one specific note, area, or one-off situation and cannot be stated as a
consistent pattern, omit it. The document should teach durable filing behaviour, not
catalogue exceptions.

---

## Required Sections (in order)

### 1. Vault Overview

**Purpose**: Orient Claude to the vault's scope and intent in 2–4 sentences.

**Content**:
- What this vault is for (personal PKM, project tracking, professional reference, etc.)
- The primary owner/user context inferred from domain distribution
- The organizational philosophy (PARA, area-based, domain-per-folder, flat, etc.)
- Any special conventions or non-standard patterns discovered

Do not include note counts or percentages. Do not list specific project or area names
unless they are first-class structural elements.

**Tone**: Direct, declarative. "This vault tracks..." not "This appears to be..."

---

### 2. Entity Type Reference

**Purpose**: Define every entity type found in the vault, with its schema and filing rules.

**Content per type** (only include types actually present in the vault; add scaffolding for types from the cb-file ontology that are absent but logically expected):

```markdown
#### `type-name`
**Folder**: `folder-name/` (if folder-per-type is used) or n/a
**File naming**: kebab-case | Title Case | etc. (from observed convention)
**Required frontmatter fields**: list them
**Optional frontmatter fields**: list them
**When to use**: one sentence defining what belongs here
**When NOT to use**: disambiguation from adjacent types
**Example**: `path/to/example-note.md`
```

For types absent from the vault but logically expected given the ontology:
```markdown
#### `type-name` *(not yet used)*
**When to create**: what circumstance warrants introducing this type
**Suggested folder**: `type-name/`
**Minimum frontmatter**: list required fields only
```

---

### 3. Frontmatter Schema

**Purpose**: Define every frontmatter field Claude should use or recognize.

**Content**: A table or structured list of all fields found, plus any standard fields
from the ontology that are missing but should be added to new notes.

Format:
```markdown
| Field | Type | Required | Valid values | Notes |
|---|---|---|---|---|
| type | string | yes | project, concept, ... | Entity class |
| domain | string | yes | see domain list | Broad topic area |
| status | string | yes | varies by type | Current state |
| ... | | | | |
```

Then a subsection: **Fields to add to all new notes** — any standard fields missing
from existing notes that Claude should include going forward (e.g., if `confidence`
or `source` are absent from the vault but prescribed by the ontology).

---

### 4. Domain Taxonomy

**Purpose**: Define the vault's domain organization so Claude can classify any new note.

**Content**:
- All domains or domain tags found in the vault with a brief description of what belongs there
- Rules for cross-domain notes (which domain to pick as primary; how to handle secondaries)
- Filing guidance: given a piece of content, how to determine which domain it belongs to
- How to add a new domain (what threshold justifies a new domain vs. a tag)

Do not include note counts per domain.

---

### 5. Tagging Conventions

**Purpose**: Define the vault's tagging system so Claude applies tags consistently.

**Content**:
- All tag namespaces in use (e.g., `#status/`, `#priority/`, `#context/`, `#domain/`, `#review/`)
- Valid values per namespace
- Rules for inline `#tags` vs. frontmatter `tags:` field
- Tags Claude should apply automatically (e.g., `#review/process` on draft notes)
- Tags to never create (if any patterns suggest clutter)
- The new-tag threshold: "Do not create a new tag unless at least N notes will use it"

---

### 6. Linking Conventions

**Purpose**: Define how wikilinks should be written and what must be linked.

**Content**:
- Link format in use: bare `[[note-name]]`, path-qualified `[[folder/note-name]]`, or aliased `[[note|alias]]`
- What must always be linked (proper nouns, entity types, known concepts)
- How to express relationship type in link context (the sentence around the link)
- Rules for linking to notes that don't exist yet (stubs are encouraged or discouraged?)
- Backlink expectations: if a note is linked-to, does the target need a reciprocal link?

---

### 7. File Naming and Organization

**Purpose**: Define exactly how new notes should be named and where they go.

**Content**:
- Observed naming convention (kebab-case / Title Case / etc.) and whether it's consistent
- Folder organization scheme (folder-per-type, folder-per-domain, flat, mixed)
- Rules for choosing between folder and frontmatter for organization
- The filing decision process: given a piece of content, how does Claude determine the
  correct folder? Express this as a rule, not as a lookup table of specific paths.
- Special structural folders: inbox, archive, templates, attachments — how they work
- Special files: index notes, MOCs (Maps of Content), daily notes — how they're structured

Describe the folder structure using **patterns with placeholders** (e.g.,
`Work/Areas/<area-name>/`), not by enumerating every specific named area currently in the
vault. A reader should be able to file any new note — including notes in areas that don't
yet exist — using the rules given.

---

### 8. Hub Notes and Index Structure

**Purpose**: Identify the vault's navigational anchor points.

**Content**:
- List the top hub nodes (most-linked notes) and their role
- Whether the vault uses area overview / MOC (Map of Content) notes — and if so, how to maintain them
- When to create a new hub note vs. relying on Dataview queries
- How hub notes should be structured

**Naming requirement**: Hub and navigation notes must use descriptive Title Case names that
reflect their content or scope (e.g., `Hermes Area Overview.md`, `Cryptography Concepts.md`).
Do not use generic names like `index.md`, `MOC.md`, or `_index.md` — these are opaque in
graph view, search results, and file listings. The name should tell a reader what the note
covers without opening it.

---

### 9. Extending the Ontology

**Purpose**: Give Claude explicit rules for when and how to add new entity types, domains, fields, and tags.

**Content** — this section must be concrete and decision-tree-like:

#### Adding a new entity type
Criteria: when is a new `type:` value warranted vs. using an existing type with tags?
- Rule: if you have 5+ notes that share a common structure not captured by any existing type → propose a new type
- Process: draft the frontmatter schema, add it to this file, create the folder, migrate existing notes if any
- Who decides: the vault owner (Claude should propose, not unilaterally create)

#### Adding a new domain
Criteria: when does a topic area become a `domain` vs. staying a tag?
- Rule: if 3+ entity types (projects, concepts, tools) all share this topic → promote to domain
- Process: add to domain taxonomy in this file, update existing notes in a batch

#### Adding a new frontmatter field
Criteria: when should a new field be added to the schema?
- Rule: if you find yourself wanting to query by some attribute that doesn't have a field → add it
- Rule: new fields must be added to this file first, then applied consistently
- Anti-pattern: do not add one-off fields to individual notes without updating the schema

#### Adding a new tag namespace
Criteria: when is a new `#namespace/` warranted?
- Rule: if a cross-cutting concern applies to 5+ notes of different types → create a namespace
- Existing namespaces must be exhausted before creating new ones

---

### 10. Quality and Maintenance Rules

**Purpose**: Prescribe ongoing curation behaviors.

**Content**:
- Orphan policy: what to do with notes that have no incoming links (stub, link, or archive)
- Staleness policy: when to update `updated:` date, when to archive
- Confidence decay: if `confidence: low` and no update in N months → flag for review
- Duplicate detection: what signals a duplicate and how to merge
- Review schedule: which tag triggers periodic review (`#review/weekly`, `#review/monthly`)

---

### 11. Claude-Specific Behaviors

**Purpose**: Instructions specific to Claude's operation in this vault (not general PKM guidance).

**Content**:
- When filing new information: always run through entity type classification first
- When linking: prefer path-qualified links over bare names when vault uses folders
- When frontmatter is incomplete: fill all required fields, use `confidence: low` if uncertain
- When a note's type is ambiguous: pick the more specific type, note the ambiguity in a comment
- `claude-context/` notes: how frequently to update, what triggers an update
- What Claude should NOT do autonomously (e.g., rename existing notes, delete stubs, restructure folders without asking)

---

## Tone and Writing Guidelines for Generated CLAUDE.md

- **Imperative mood throughout**: "Use kebab-case", "Always include `type:`", "Do not create..."
- **Specific over general**: "The `domain` field uses these values: ..." not "Use appropriate domains"
- **Show examples**: Every naming convention and link format needs a concrete example
- **Flag inferred conventions**: If Claude inferred a convention from limited evidence, mark it:
  `*(inferred — verify with vault owner)*`
- **No hedging in rules**: Avoid "you might want to" or "consider using". Just state the rule.
- **Tables for lookup content**: Field schemas, tag namespaces, domain lists → tables
- **Prose for judgment calls**: When to extend the ontology, how to handle edge cases → prose

## When to Ask vs. Infer

**Do not infer. Ask.**

When the vault analysis leaves a convention ambiguous, the skill must ask the vault owner
a clarifying question before generating the relevant section. Do not make a judgment call
and flag it as "inferred" — the owner knows things the vault cannot reveal.

Common situations that require clarification, not inference:
- The vault uses two conflicting naming styles with no clear dominant pattern
- Multiple `type:` values appear to overlap in meaning (e.g., `project` and `area`)
- Tags are used inconsistently across similar notes with no clear rule
- Folder organization mixes two different principles (e.g., by domain in some areas,
  by type in others)
- The purpose of the vault is ambiguous (personal PKM vs. project-specific reference)
- A significant portion of notes are missing required fields — unclear if intentional

When asking, be specific: quote the conflicting evidence and ask for the intended rule.
Do not ask multiple questions at once — ask the most important one, then continue.

Only proceed with a section once the rule is confirmed. If the owner cannot clarify,
note the ambiguity explicitly in the CLAUDE.md rather than guessing.

---

## What to Do With Vault Inconsistencies

When the analysis reveals inconsistencies (mixed naming styles, missing required fields,
orphan notes, duplicate entity types), the generated CLAUDE.md should:

1. **State the canonical form** going forward — what new notes should look like
2. **Include a Migration Notes section** if inconsistencies are significant, describing
   the pattern of the problem and the fix (but not prescribing that Claude should do
   this autonomously, and not listing specific affected files)

Example:
```markdown
> **Migration note**: Some notes use an inline `#project` tag rather than `type: project`
> frontmatter. New notes should always use the frontmatter field. Existing notes can be
> migrated opportunistically when editing for other reasons.
```

Do not describe the current broken state with counts ("40 notes do X"). Describe the
problem pattern and the correct going-forward behaviour.
