---
name: cb-setup
description: >
  Analyze an Obsidian vault, evaluate its ontology quality, and generate or update a
  CLAUDE.md at the vault root that provides durable guidance for filing, curating, and
  extending the knowledge graph. Trigger on: "Set up this vault to work with Claude.",
  "Analyze my vault.", "Update my vault's CLAUDE.md.", "Configure this vault.",
  "Create a CLAUDE.md for my vault.", "Show me what the CLAUDE.md would look like",
  "Preview the vault setup", "Draft a CLAUDE.md but don't save it yet."
compatibility: "Requires filesystem access to read the Obsidian vault. Python 3 required for analyze_vault.py."
allowed-tools: Bash, Glob, Grep, Read, Write, Edit
---

# Vault Setup — CLAUDE.md Generator

Arguments: $ARGUMENTS

Reads an Obsidian vault, evaluates its ontology quality, asks clarifying questions, and
produces a `CLAUDE.md` at the vault root that serves as authoritative guidance for
adding, curating, and extending the vault's knowledge graph.

---

## Step 0 — Parse Arguments

Parse `$ARGUMENTS` for:
- `<vault-path>` — explicit vault path (positional argument or bare path)
- `--types "<t1>, <t2>, ..."` — user-specified type vocabulary; if present, Phase 2 is skipped
- `--dry-run` — show generated CLAUDE.md without writing it

Check the invocation context for natural-language dry-run phrases: "show me what the
CLAUDE.md would look like", "preview the vault setup", "draft a CLAUDE.md but don't
save it yet", "what would you generate".

If dry-run mode is active, confirm at the start:
`[DRY RUN] CLAUDE.md will be shown but not written.`

---

## Phase 1 — Discovery

### 1. Determine vault path

In order of preference:
1. Path from `$ARGUMENTS` (if provided)
2. `vault_path` from `~/.claude/cyberbrain.json`:
   ```bash
   python3 -c "
   import json, os
   cfg = json.load(open(os.path.expanduser('~/.claude/cyberbrain.json')))
   print(cfg.get('vault_path', ''))
   "
   ```
3. If neither, ask the user: "What is the path to your Obsidian vault?"

### 2. Verify vault access

```bash
python3 -c "
import os, sys
from pathlib import Path
vault = sys.argv[1]
p = Path(vault).expanduser()
if not p.exists():
    print('ERROR: path does not exist')
    sys.exit(1)
has_obsidian = (p / '.obsidian').is_dir()
md_count = len(list(p.rglob('*.md')))
print('obsidian=' + str(has_obsidian).lower())
print('md_count=' + str(md_count))
" "$VAULT_PATH"
```

If the path does not exist, report the error and stop.

If `.obsidian/` is absent and there are very few `.md` files (< 5), ask the user to
confirm this is an Obsidian vault before proceeding.

### 3. Check for existing CLAUDE.md

```bash
ls "$VAULT_PATH/CLAUDE.md" 2>/dev/null
```

If it exists, read it using the Read tool. Note any custom sections the user has added
beyond the standard sections — these must be preserved in the output. This run is an
update, not a replacement.

### 4. Run the vault analyzer script

Locate the script:
```bash
ls ~/.claude/skills/cb-setup/scripts/analyze_vault.py 2>/dev/null \
  || ls "${CLAUDE_PLUGIN_ROOT}/skills/cb-setup/scripts/analyze_vault.py" 2>/dev/null
```

Verify pyyaml is available:
```bash
python3 -c "import yaml" 2>/dev/null || pip install pyyaml -q
```

Run the analyzer:
```bash
python3 <resolved_script_path> "$VAULT_PATH" --output /tmp/vault_report.json
cat /tmp/vault_report.json
```

The script produces a JSON report with: `total_notes`, `folder_structure`, `naming_conventions`,
`entity_types.distribution`, `entity_types.samples`, `domains`, `statuses`,
`frontmatter.field_usage`, `tags.top_tags`, `tags.hierarchy`, `links.hub_nodes`,
`links.notes_with_no_outgoing_links`, `links.notes_with_no_incoming_links`,
`links.orphan_sample`.

**If the script fails for any reason**, continue with degraded analysis using in-context
file reads. Do not abort. Note in the output that the analyzer could not run.

### 5. Deep-read a sample of notes

Priority order:
1. Hub nodes from `links.hub_nodes`
2. Index / MOC notes (names containing `index`, `map`, `MOC`, `_index`)
3. 2–3 notes per entity type from `entity_types.samples`
4. Any notes containing Dataview queries (reveal which fields are queried)
5. The vault README if present

Scale to vault size:

| Vault size | Notes to read |
|---|---|
| <50 notes | Read all |
| 50–200 | 25–35 |
| 200–500 | 40–50 |
| 500+ | 60–80 |

From each note, extract: body quality, link style, whether wikilinks carry relationship
context, frontmatter field patterns, recurring body structure.

---

## Phase 2 — Archetype and Quality Evaluation

**Skip this phase if `--types` was provided.** Proceed directly to Phase 3 with the
user-specified vocabulary as `RESOLVED_TYPES`.

### Step A — Identify the vault archetype

From content distribution, folder structure, and note types, identify which archetype
best fits:

| Archetype | Primary content | Natural type vocabulary |
|---|---|---|
| **Developer/Technical PKM** | Bug fixes, architecture, error patterns, references | `decision`, `problem`, `reference`, `insight` |
| **Research/Learning vault** | Concepts, papers, questions, arguments | `concept`, `source`, `question`, `argument`, `summary` |
| **Whole-life PKM** | Work + personal, projects + hobbies | `project`, `note`, `resource`, `archived` |
| **Project-specific vault** | Single codebase or domain | Types tuned to the project |
| **Hybrid** | Multiple of the above | Combination |

Record your archetype assessment and the evidence that supports it.

### Step B — Evaluate the existing type system

For each type currently in use, apply the quality criteria from Section 5.1 of the spec:

- Are types mutually exclusive? Can most notes be classified in under 5 seconds?
- Are types describing epistemic role, or topic/status/domain?
- Does the structure of notes actually differ meaningfully by type?
- Are there anti-patterns present?

**Anti-patterns to flag:**

| Anti-pattern | Signal | Fix |
|---|---|---|
| Topic-as-type | Types named after domains: `work-notes`, `personal`, `career` | Replace with domain tag + structural type |
| Type explosion | 10+ types; many with only a few notes | Audit; merge to ≤6; use tags for rest |
| Status-as-type | Types like `in-progress`, `done`, `archived` | Replace with `status` field |
| Overlapping types | `project` and `task` feel interchangeable | Define clear structural criterion; merge weaker type |
| Implicit schema | Same type has wildly different frontmatter | Establish required fields per type |
| No linking | Nearly all notes have 0 outgoing wikilinks | Flag as systemic gap |
| Generic summaries | Summaries say "Notes about X" or "Information on Y" | Require specific, information-dense summaries |

### Step C — Form a recommendation

Choose one of:
- **Adopt**: Existing types are well-designed. Document as-is.
- **Refine**: Mostly good but with 1–2 anti-patterns. Propose specific fixes.
- **Redesign**: Significantly misaligned. Propose a new vocabulary appropriate for the
  archetype, with a migration path.

Do not silently adopt a bad type system. If types need work, say so and explain why.

Record: `RECOMMENDATION` (adopt/refine/redesign), `DETECTED_TYPES` (existing types),
`ANTI_PATTERNS` (list of anti-patterns found).

---

## Phase 3 — Clarifying Questions

Before generating, present **all clarifying questions at once** in a structured list.
Limit to 2–3 questions total. Wait for the user to respond before proceeding.

**Always ask if unclear:**
- What the vault is primarily for (if the archetype is ambiguous)
- Whether AI-extracted beats should use the vault's own type vocabulary or a separate
  beat vocabulary (only ask if the vault uses a non-standard vocabulary)
- Where auto-extracted beats should land (existing structure vs. a dedicated `AI/` folder)

**Ask when the type system needs redesign:**
- "Your vault currently has [N] types, but [X] and [Y] appear to overlap. I'd recommend
  consolidating to [proposed set]. Does that fit how you think about these notes?"
- "I see types named [X] and [Y] — these look like statuses rather than types. Would it
  work to replace them with a `status` field and use [structural types] instead?"

**Ask when the vault is nascent:**
- "Your vault is new. What do you primarily want to capture — technical decisions and
  debugging sessions, general knowledge and learning, whole-life notes, or something
  else?"

**Do not ask:**
- Questions the vault makes obvious
- Questions about things you can infer with high confidence

After receiving answers, update `RESOLVED_TYPES` with the final agreed-upon type
vocabulary.

---

## Phase 4 — Generate the CLAUDE.md

Read `references/output-structure.md` before generating for full section definitions and
tone guidelines.

The generated CLAUDE.md must be **prescriptive, not descriptive** — every section
answers "what should Claude do?", not "here's what currently exists." Write in imperative
mood throughout: "Use X", "Always include Y", "Do not Z."

### Required sections (in order)

1. **Vault Overview** — 2–4 sentences orienting Claude to the vault's scope and intent

2. **Knowledge Graph Principles** — MANDATORY; always present; adapted to this vault's
   archetype and vocabulary. See the required content below.

3. **Folder Structure** — filing rules using structural patterns, not enumerated
   specific folders. Use placeholders: `Work/Projects/<project-name>/`

4. **Entity Types** — one subsection per type in `RESOLVED_TYPES`; each subsection
   includes: what this type captures, required frontmatter fields, a concrete YAML
   example with realistic values, and body structure guidance. Include "not yet used"
   types where logically expected for the archetype.

5. **Beat-to-Vault-Type Mapping** — ONLY if the vault uses its own type vocabulary
   distinct from the 4-type beat default. Make explicit: when `/cb-extract` produces an
   `insight` beat, which vault type does it file under?

6. **Frontmatter Schema** — required fields for all notes; type-specific required fields;
   optional fields. Classify fields as: universal, type-specific, optional, experimental.

7. **Domain Taxonomy** — how the vault is organized by domain/area (if applicable);
   domain tags and what they represent

8. **Tagging Conventions** — tag structure, tag namespaces, what gets a tag vs. a type,
   what NOT to tag

9. **Linking Conventions** — link style, how to express relationships in the sentence
   around a link, not just bare `[[wikilinks]]`

10. **File Naming and Organization** — naming style (Title Case, kebab-case, etc.),
    date prefixes (yes/no), length guidelines

11. **Extending the Ontology** — MANDATORY; always present. Explicit criteria for when
    to add a new type, tag, domain, or field — and when to resist. Include: "Add a new
    type only when the structure of the note differs from all existing types." "Add a new
    tag when a new topic or domain emerges." "Do not add a type because a new topic
    emerged."

12. **Quality and Maintenance Rules** — filing quality standards; what makes a good
    summary; link density expectations; enrichment expectations

13. **Claude-Specific Behaviors** — how Claude should behave when filing, recalling,
    or enriching notes in this vault; any vault-specific overrides

14. **Known Issues / Migration Notes** — ONLY if significant anti-patterns were found
    in Phase 2. List each with the recommended fix. Do not bury these.

### Knowledge Graph Principles section (required content)

Every generated CLAUDE.md must include this section, adapted to the vault's archetype
and vocabulary. Condense to ~300–400 words. The canonical text below must be adapted
— not copied verbatim:

---

**Knowledge Graph Principles**

Types describe what kind of thinking produced a note — not what it's about. `decision`
is a type. `authentication` is a tag. Types must remain valid for the lifetime of the
vault; topics change. Never add a new type because a new topic emerged — new topics get
tags.

Fewer types is better. Every type is a classification decision that compounds over time.
If you can't classify a note in under five seconds, the types are too similar or too
numerous. A vault with four well-defined types that cover everything is more useful than
twelve overlapping ones.

Write every note for your future self with no context. Assume the reader (you, in two
years) doesn't know anything about today's situation. Every note should answer: what was
the situation, what was decided or discovered, and why. Notes that record conclusions
without reasoning become hard to apply.

One idea per note. Each note captures one well-defined piece of knowledge and stands
alone. When you find yourself writing "and also...", that is usually a second note.
Atomic notes are composable — they can be linked from many places without pulling in
unrelated context.

Links express relationships, not just references. "See also: [[Note]]" is weak. "This
decision was made to resolve [[Note]]" carries semantic weight that compounds as the
vault grows. The sentence around a link matters as much as the link itself.

Write titles and summaries for retrieval. Titles and summaries are the primary search
surfaces. Make them specific and keyword-rich. "Fixed a bug" is not a title. "Postgres
connection pool timeout causes silent job drops under sustained load" is a title — it
surfaces in search and makes the content immediately obvious.

Capture first, refine later. A quick rough note is better than no note. Use the inbox
and the enrichment flow to upgrade rough captures. Do not let the desire for a perfect
note prevent capturing a useful one.

---

### Non-negotiable output rules

- Flag inferred conventions: `*(inferred — verify with vault owner)*`
- Never include specific note counts, percentages, or frequencies
- Describe folder structure using patterns, not enumerated specific folders
- Every rule must be generalizable — omit one-off conventions
- If custom sections from an existing CLAUDE.md were identified in Phase 1, preserve them

---

## Phase 5 — Save and Report

### Save (skip if `--dry-run`)

Write to `$VAULT_PATH/CLAUDE.md` using the Write tool.

If a `CLAUDE.md` already existed, use Edit to update it, preserving custom sections.
If it did not exist, use Write to create it.

### Report to user

```
Vault setup complete

Vault summary:
  Archetype:   [identified archetype]
  Notes found: [approximate scale — "small (< 50)", "medium (50–300)", "large (500+)"]
  Types found: [list of types discovered]

Ontology evaluation: [Adopted / Refined / Redesigned]
  [1–2 sentences explaining the recommendation and why]

Anti-patterns found:
  - [Anti-pattern 1]: [one-line recommended fix]
  - [Anti-pattern 2]: [one-line recommended fix]
  (None found) ← if clean

What was generated:
  - [N] sections
  - Flagged as inferred: [list of items]

CLAUDE.md [written to / displayed for] $VAULT_PATH/CLAUDE.md

Recommended next action:
  [One specific action — e.g., "Run `/cb-enrich --dry-run` to see how many notes are
  missing metadata" or "Review the Known Issues section — the proposed type consolidation
  requires a migration path."]
```

### Dry-run mode

Instead of writing, display the full generated CLAUDE.md in the terminal using a
markdown code block, preceded by the report above (excluding the "written to" line).
Add at the end:
```
[DRY RUN] No files were written. Run without --dry-run to save.
```

---

## Reference Files

- `references/output-structure.md` — Full section definitions, content requirements, and
  tone guidelines. **Read before Phase 4.**
- `references/analysis-process.md` — Detailed vault crawling process for Phase 1.
- `references/claude-md-template.md` — Compact section specs and field formatting reference.
- `scripts/analyze_vault.py` — Vault structure analyzer. Run in Phase 1.
